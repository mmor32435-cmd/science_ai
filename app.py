import streamlit as st
import os, re, io, json, time, random, asyncio, tempfile, hashlib
from typing import Optional, List, Dict, Any, Tuple

from PIL import Image
import gspread
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder
import edge_tts

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from pdf2image import convert_from_path
import pytesseract

from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain.prompts import PromptTemplate
from langchain.chains import load_qa_chain
from langchain_core.documents import Document


# =========================
# Page
# =========================
st.set_page_config(page_title="المعلم العلمي | السيد البدوي", page_icon="🧬", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
html, body, .stApp { font-family: 'Cairo', sans-serif !important; direction: rtl; text-align: right; }
.stApp { background: radial-gradient(circle at top, #f7fbff, #f4f6f8 55%, #eef2f6); }
.header-box {
  background: linear-gradient(90deg, #061a40 0%, #0353a4 50%, #006daa 100%);
  padding: 1.6rem; border-radius: 18px; text-align: center;
  margin-bottom: 1.2rem; box-shadow: 0 10px 30px rgba(0,0,0,0.14);
}
.header-box h1, .header-box h3 { color: #ffffff !important; margin: 0.15rem 0; }
.badge {
  display:inline-block; padding: 0.25rem 0.7rem; border-radius: 999px;
  background: rgba(255,255,255,0.18); color: #fff; font-size: 0.95rem;
  border: 1px solid rgba(255,255,255,0.25);
}
.stTextInput input, .stTextArea textarea {
  background-color: #ffffff !important; color: #000000 !important;
  border: 1.8px solid #0353a4 !important; border-radius: 10px !important;
}
div[data-baseweb="select"] > div {
  background-color: #ffffff !important; border: 1.8px solid #0353a4 !important; border-radius: 10px !important;
}
.stButton>button {
  background: linear-gradient(90deg, #0353a4 0%, #061a40 100%) !important;
  color: #ffffff !important; border: none; border-radius: 12px;
  height: 50px; width: 100%; font-size: 18px !important; font-weight: 700 !important;
}
.stChatMessage { background-color: #ffffff !important; border: 1px solid #d9e2ef !important; border-radius: 14px !important; }
small.muted { color: #6b7280; }
</style>
""", unsafe_allow_html=True)

TEACHER_NAME = st.secrets.get("TEACHER_NAME", "الأستاذ / السيد البدوي")
st.markdown(f"""
<div class="header-box">
  <h1>{TEACHER_NAME}</h1>
  <h3>المنصة التعليمية الذكية للعلوم</h3>
  <div class="badge">شات • ميكروفون • OCR • واجبات • اختبارات • عربي/English</div>
</div>
""", unsafe_allow_html=True)


# =========================
# Secrets
# =========================
TEACHER_KEY = st.secrets.get("TEACHER_MASTER_KEY", "ADMIN")
SHEET_NAME = st.secrets.get("CONTROL_SHEET_NAME", "App_Control")
CONTROL_TAB = st.secrets.get("CONTROL_TAB_NAME", "")  # optional

FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "")
GOOGLE_API_KEYS = st.secrets.get("GOOGLE_API_KEYS", [])

RESULTS_TAB = st.secrets.get("RESULTS_TAB_NAME", "Results")
ASSIGNMENTS_TAB = st.secrets.get("ASSIGNMENTS_TAB_NAME", "Assignments")
SUBMISSIONS_TAB = st.secrets.get("SUBMISSIONS_TAB_NAME", "Submissions")

CHROMA_BASE_DIR = st.secrets.get("CHROMA_PERSIST_DIR", "./chroma_db")
os.makedirs(CHROMA_BASE_DIR, exist_ok=True)

if isinstance(GOOGLE_API_KEYS, str):
    GOOGLE_API_KEYS = [k.strip() for k in GOOGLE_API_KEYS.split(",") if k.strip()]


# =========================
# Session State
# =========================
def init_state():
    if "user_data" not in st.session_state:
        st.session_state.user_data = {"logged_in": False, "role": None, "name": None}
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "debug_enabled" not in st.session_state:
        st.session_state.debug_enabled = False
    if "debug_log" not in st.session_state:
        st.session_state.debug_log = []

    if "book_data" not in st.session_state:
        st.session_state.book_data = {}
    if "vector_store" not in st.session_state:
        st.session_state.vector_store = None

    if "uploaded_context" not in st.session_state:
        st.session_state.uploaded_context = {"text": "", "vs": None, "name": ""}

    if "tts_enabled" not in st.session_state:
        st.session_state.tts_enabled = False

    if "quiz" not in st.session_state:
        st.session_state.quiz = {"state": "off", "question": "", "model_answer": "", "last_score": None}

    if "hw" not in st.session_state:
        st.session_state.hw = {"selected_id": None}

init_state()

def dbg(event, data=None):
    if not st.session_state.debug_enabled:
        return
    rec = {"t": time.strftime("%H:%M:%S"), "event": event}
    if data is not None:
        rec["data"] = data
    st.session_state.debug_log.append(rec)
    st.session_state.debug_log = st.session_state.debug_log[-500:]


# =========================
# Constants / Maps
# =========================
STAGES = ["الابتدائية", "الإعدادية", "الثانوية"]
GRADE_OPTIONS = {
    "الابتدائية": ["الرابع", "الخامس", "السادس"],
    "الإعدادية": ["الأول", "الثاني", "الثالث"],
    "الثانوية": ["الأول", "الثاني", "الثالث"],
}
TERMS = ["الترم الأول", "الترم الثاني"]
LANG_OPTIONS = ["العربية (علوم)", "English (Science)"]

def subjects_for(stage: str, grade: str) -> List[str]:
    if stage in ["الابتدائية", "الإعدادية"]:
        return ["علوم"]
    if grade == "الأول":
        return ["علوم متكاملة"]
    return ["كيمياء", "فيزياء", "أحياء"]

def is_english(lang_ui: str) -> bool:
    return "English" in (lang_ui or "")

def ocr_lang_code(lang_ui: str) -> str:
    return "eng" if is_english(lang_ui) else "ara"

def ui_str(lang_ui: str, ar: str, en: str) -> str:
    return en if is_english(lang_ui) else ar

def term_token(term: str) -> str:
    return "T2" if "الثاني" in term else "T1"

def drive_tokens(stage: str, grade: str, subject: str, term: str, lang_ui: str) -> List[str]:
    stage_map = {"الثانوية": "Sec", "الإعدادية": "Prep", "الابتدائية": "Grade"}
    grade_map = {"الأول": "1", "الثاني": "2", "الثالث": "3", "الرابع": "4", "الخامس": "5", "السادس": "6"}
    subject_map = {"علوم": "Science", "علوم متكاملة": "Integrated", "كيمياء": "Chemistry", "فيزياء": "Physics", "أحياء": "Biology"}
    lang_code = "En" if is_english(lang_ui) else "Ar"
    return [
        f"{stage_map.get(stage,'')}{grade_map.get(grade,'')}".strip(),
        subject_map.get(subject, subject),
        term_token(term),
        lang_code,
    ]


# =========================
# Google Credentials + Sheets helpers
# =========================
@st.cache_resource
def get_credentials():
    if "gcp_service_account" not in st.secrets:
        return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        return service_account.Credentials.from_service_account_info(creds_dict, scopes=scopes)
    except Exception as e:
        dbg("creds_error", str(e))
        return None

@st.cache_resource
def get_gspread_client():
    creds = get_credentials()
    return gspread.authorize(creds) if creds else None

def open_control_sheet():
    client = get_gspread_client()
    if not client:
        return None
    try:
        sh = client.open(SHEET_NAME)
        return sh
    except Exception as e:
        dbg("open_sheet_error", str(e))
        return None

def ensure_worksheet(sh, title: str, headers: List[str]):
    """
    ينشئ Worksheet إن لم توجد + يضع headers في الصف الأول إن كانت فاضية
    """
    try:
        try:
            ws = sh.worksheet(title)
        except Exception:
            ws = sh.add_worksheet(title=title, rows=2000, cols=max(10, len(headers) + 2))

        # وضع الهيدر إن لم يكن موجود
        first_row = ws.row_values(1)
        if not first_row or all((c.strip() == "" for c in first_row)):
            ws.update("A1", [headers])
        return ws
    except Exception as e:
        dbg("ensure_ws_error", {"title": title, "err": str(e)})
        return None

def safe_cell(s: Any, max_len: int = 35000) -> str:
    if s is None:
        return ""
    t = str(s)
    return t[:max_len]

def append_row(ws, row: List[Any]):
    try:
        ws.append_row([safe_cell(x) for x in row], value_input_option="USER_ENTERED")
        return True
    except Exception as e:
        dbg("append_row_error", str(e))
        return False

def check_student_code(input_code: str) -> bool:
    sh = open_control_sheet()
    if not sh:
        return False
    try:
        ws = sh.worksheet(CONTROL_TAB) if CONTROL_TAB else sh.sheet1
        real_code = str(ws.acell("B1").value).strip()
        return str(input_code).strip() == real_code
    except Exception as e:
        dbg("check_student_code_error", str(e))
        return False

def get_logging_worksheets():
    sh = open_control_sheet()
    if not sh:
        return None, None, None

    results_headers = [
        "timestamp", "student_name", "role", "stage", "grade", "subject", "term", "lang",
        "type", "ref_book", "question", "student_answer", "score", "feedback"
    ]
    assignments_headers = [
        "assignment_id", "created_at", "teacher_name", "stage", "grade", "subject", "term", "lang",
        "title", "difficulty", "questions_json", "active"
    ]
    submissions_headers = [
        "submission_id", "submitted_at", "assignment_id", "student_name", "stage", "grade", "subject", "term", "lang",
        "answers_json", "grading_json", "total_score"
    ]

    ws_results = ensure_worksheet(sh, RESULTS_TAB, results_headers)
    ws_assign = ensure_worksheet(sh, ASSIGNMENTS_TAB, assignments_headers)
    ws_sub = ensure_worksheet(sh, SUBMISSIONS_TAB, submissions_headers)
    return ws_results, ws_assign, ws_sub

def log_result(
    kind: str,
    question: str,
    student_answer: str,
    score: str,
    feedback: str,
):
    ws_results, _, _ = get_logging_worksheets()
    if not ws_results:
        return
    u = st.session_state.user_data
    book = st.session_state.book_data.get("name", "")
    row = [
        time.strftime("%Y-%m-%d %H:%M:%S"),
        u.get("name",""),
        u.get("role",""),
        u.get("stage",""),
        u.get("grade",""),
        u.get("subject",""),
        u.get("term",""),
        u.get("lang",""),
        kind,
        book,
        question,
        student_answer,
        score,
        feedback,
    ]
    append_row(ws_results, row)


# =========================
# Drive: list + download
# =========================
@st.cache_data(ttl=300, show_spinner=False)
def list_drive_pdfs(folder_id: str) -> List[Dict[str, str]]:
    creds = get_credentials()
    if not creds:
        return []
    service = build("drive", "v3", credentials=creds)
    query = f"'{folder_id}' in parents and mimeType='application/pdf' and trashed=false"
    res = service.files().list(q=query, fields="files(id, name, modifiedTime, size)").execute()
    return res.get("files", [])

def download_drive_pdf(file_id: str, file_name: str) -> Optional[str]:
    creds = get_credentials()
    if not creds:
        return None
    try:
        service = build("drive", "v3", credentials=creds)
        safe_name = re.sub(r"[^a-zA-Z0-9_\-\.]+", "_", file_name)
        local_path = os.path.join(CHROMA_BASE_DIR, "books_cache", f"{file_id}_{safe_name}")
        os.makedirs(os.path.dirname(local_path), exist_ok=True)

        if os.path.exists(local_path) and os.path.getsize(local_path) > 10_000:
            return local_path

        request = service.files().get_media(fileId=file_id)
        with open(local_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        return local_path
    except Exception as e:
        dbg("download_drive_pdf_error", str(e))
        return None

def load_book_from_drive(stage: str, grade: str, subject: str, term: str, lang_ui: str) -> Optional[Dict[str, str]]:
    if not FOLDER_ID:
        return None
    try:
        toks = drive_tokens(stage, grade, subject, term, lang_ui)
        files = list_drive_pdfs(FOLDER_ID)
        matched = None
        for f in files:
            name_low = (f.get("name") or "").lower()
            if all(tok.lower() in name_low for tok in toks if tok):
                matched = f
                break
        if not matched:
            dbg("book_not_found", {"tokens": toks, "files_count": len(files)})
            return None

        path = download_drive_pdf(matched["id"], matched["name"])
        if not path:
            return None
        return {"id": matched["id"], "name": matched["name"], "path": path}
    except Exception as e:
        dbg("load_book_error", str(e))
        return None


# =========================
# OCR
# =========================
def _hash_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

@st.cache_data(show_spinner=False)
def ocr_image_bytes(img_bytes: bytes, lang: str) -> str:
    try:
        im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        return (pytesseract.image_to_string(im, lang=lang) or "").strip()
    except Exception as e:
        return f"__OCR_ERROR__:{e}"

@st.cache_data(show_spinner="جاري قراءة PDF (OCR)...")
def ocr_pdf_path(pdf_path: str, lang: str, max_pages: Optional[int] = None) -> str:
    try:
        texts = []
        batch = 6
        start = 1
        pages_done = 0

        while True:
            if max_pages is not None and pages_done >= max_pages:
                break
            end = start + batch - 1
            pages = convert_from_path(pdf_path, dpi=200, first_page=start, last_page=end)
            if not pages:
                break
            for im in pages:
                if max_pages is not None and pages_done >= max_pages:
                    break
                texts.append(pytesseract.image_to_string(im, lang=lang))
                pages_done += 1
            if len(pages) < batch:
                break
            start += batch

        return "\n\n--- نهاية الصفحة ---\n\n".join(texts).strip()
    except Exception as e:
        return f"__OCR_ERROR__:{e}"


# =========================
# RAG (Chroma Persist)
# =========================
def pick_api_key() -> Optional[str]:
    return random.choice(GOOGLE_API_KEYS) if GOOGLE_API_KEYS else None

def get_embeddings():
    k = pick_api_key()
    if not k:
        return None
    return GoogleGenerativeAIEmbeddings(model="models/embedding-001", google_api_key=k)

def get_llm(temperature: float = 0.2):
    k = pick_api_key()
    if not k:
        return None
    return ChatGoogleGenerativeAI(model="gemini-1.5-flash-latest", google_api_key=k, temperature=temperature)

def split_to_docs(text: str) -> List[Document]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=1800, chunk_overlap=220, add_start_index=True)
    return [Document(page_content=ch) for ch in splitter.split_text(text) if ch.strip()]

def collection_key(stage: str, grade: str, subject: str, term: str, lang_ui: str, book_id: str) -> str:
    raw = f"{stage}|{grade}|{subject}|{term}|{lang_ui}|{book_id}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()

def load_or_create_book_vectorstore(persist_dir: str, collection_name: str, full_text: str) -> Optional[Chroma]:
    try:
        embeddings = get_embeddings()
        if not embeddings:
            return None
        os.makedirs(persist_dir, exist_ok=True)
        has_existing = any(os.scandir(persist_dir))
        if has_existing:
            return Chroma(collection_name=collection_name, persist_directory=persist_dir, embedding_function=embeddings)

        docs = split_to_docs(full_text)
        if not docs:
            return None

        vs = Chroma.from_documents(
            docs,
            embedding=embeddings,
            collection_name=collection_name,
            persist_directory=persist_dir
        )
        try:
            vs.persist()
        except Exception:
            pass
        return vs
    except Exception as e:
        dbg("chroma_error", str(e))
        return None

def 
