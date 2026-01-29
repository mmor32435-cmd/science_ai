import streamlit as st
import os
import re
import io
import json
import time
import random
import asyncio
import tempfile
import hashlib
from typing import Optional, List, Dict, Any, Tuple

from PIL import Image

# Google & External Libs
import gspread
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder
import edge_tts
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# OCR & Image Processing
from pdf2image import convert_from_path
import pytesseract

# LangChain & AI Imports (Standardized for version 0.1.x)
try:
    from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
except ImportError:
    import langchain_google_genai
    from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI

from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import PromptTemplate
from langchain_core.documents import Document

# QA Chain Import (Fixed)
from langchain.chains.question_answering import load_qa_chain

# =========================
# Page config + CSS
# =========================
st.set_page_config(
    page_title="المعلم العلمي | السيد البدوي",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

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

# =========================
# Secrets
# =========================
TEACHER_NAME = st.secrets.get("TEACHER_NAME", "الأستاذ / السيد البدوي")
TEACHER_KEY = st.secrets.get("TEACHER_MASTER_KEY", "ADMIN")
SHEET_NAME = st.secrets.get("CONTROL_SHEET_NAME", "App_Control")
CONTROL_TAB_NAME = st.secrets.get("CONTROL_TAB_NAME", "")
FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "")
GOOGLE_API_KEYS = st.secrets.get("GOOGLE_API_KEYS", [])

RESULTS_TAB_NAME = st.secrets.get("RESULTS_TAB_NAME", "Results")
ASSIGNMENTS_TAB_NAME = st.secrets.get("ASSIGNMENTS_TAB_NAME", "Assignments")
SUBMISSIONS_TAB_NAME = st.secrets.get("SUBMISSIONS_TAB_NAME", "Submissions")

CHROMA_PERSIST_DIR = st.secrets.get("CHROMA_PERSIST_DIR", "./chroma_db")
os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)

if isinstance(GOOGLE_API_KEYS, str):
    GOOGLE_API_KEYS = [k.strip() for k in GOOGLE_API_KEYS.split(",") if k.strip()]

st.markdown(f"""
<div class="header-box">
  <h1>{TEACHER_NAME}</h1>
  <h3>المنصة التعليمية الذكية للعلوم</h3>
  <div class="badge">شات • ميكروفون • OCR • واجبات • اختبارات • عربي/English</div>
</div>
""", unsafe_allow_html=True)

# =========================
# Session State
# =========================
def init_state():
    if "user_data" not in st.session_state:
        st.session_state.user_data = {"logged_in": False, "role": None, "name": ""}
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
        st.session_state.uploaded_context = {"name": "", "text": "", "vs": None}
    if "tts_enabled" not in st.session_state:
        st.session_state.tts_enabled = False
    if "quiz" not in st.session_state:
        st.session_state.quiz = {"state": "off", "q": "", "model": ""}

init_state()

def dbg(event: str, data: Any = None):
    if not st.session_state.debug_enabled:
        return
    st.session_state.debug_log.append({"t": time.strftime("%H:%M:%S"), "event": event, "data": data})
    st.session_state.debug_log = st.session_state.debug_log[-500:]

# =========================
# Maps
# =========================
STAGES = ["الابتدائية", "الإعدادية", "الثانوية"]
GRADES = {
    "الابتدائية": ["الرابع", "الخامس", "السادس"],
    "الإعدادية": ["الأول", "الثاني", "الثالث"],
    "الثانوية": ["الأول", "الثاني", "الثالث"],
}
TERMS = ["الترم الأول", "الترم الثاني"]
LANGS = ["العربية (علوم)", "English (Science)"]

def subjects_for(stage: str, grade: str) -> List[str]:
    if stage in ["الابتدائية", "الإعدادية"]:
        return ["علوم"]
    if grade == "الأول":
        return ["علوم متكاملة"]
    return ["كيمياء", "فيزياء", "أحياء"]

def is_english(lang_ui: str) -> bool:
    return "English" in (lang_ui or "")

def ocr_lang(lang_ui: str) -> str:
    return "eng" if is_english(lang_ui) else "ara"

def ui(lang_ui: str, ar: str, en: str) -> str:
    return en if is_english(lang_ui) else ar

def term_token(term: str) -> str:
    return "T2" if "الثاني" in term else "T1"

def drive_tokens(stage: str, grade: str, subject: str, term: str, lang_ui: str) -> Tuple[List[str], List[str]]:
    stage_map = {"الابتدائية": "Grade", "الإعدادية": "Prep", "الثانوية": "Sec"}
    grade_map = {"الرابع": "4", "الخامس": "5", "السادس": "6", "الأول": "1", "الثاني": "2", "الثالث": "3"}
    subject_map = {
        "علوم": "Science",
        "علوم متكاملة": "Integrated",
        "كيمياء": "Chemistry",
        "فيزياء": "Physics",
        "أحياء": "Biology",
    }
    lang_code = "En" if is_english(lang_ui) else "Ar"
    sg = f"{stage_map.get(stage, '')}{grade_map.get(grade, '')}"
    sub = subject_map.get(subject, subject)
    tt = term_token(term)
    with_term = [sg, sub, tt, lang_code]
    no_term = [sg, sub, lang_code]
    return with_term, no_term

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

# =========================
# Google Services
# =========================
@st.cache_resource
def get_credentials():
    if "gcp_service_account" not in st.secrets:
        return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        return service_account.Credentials.from_service_account_info(creds_dict, scopes=scopes)
    except Exception as e:
        dbg("creds_error", str(e))
        return None

@st.cache_resource
def get_gspread_client():
    creds = get_credentials()
    return gspread.authorize(creds) if creds else None

def open_sheet():
    client = get_gspread_client()
    if not client:
        return None
    try:
        return client.open(SHEET_NAME)
    except Exception as e:
        dbg("open_sheet_error", str(e))
        return None

def ensure_ws(sh, title: str, headers: List[str]):
    try:
        try:
            ws = sh.worksheet(title)
        except Exception:
            ws = sh.add_worksheet(title=title, rows=2000, cols=max(12, len(headers) + 2))
        first = ws.row_values(1)
        if not first or all((c.strip() == "" for c in first)):
            ws.update("A1", [headers])
        return ws
    except Exception as e:
        dbg("ensure_ws_error", {"title": title, "err": str(e)})
        return None

def append_row(ws, row: List[Any]) -> bool:
    try:
        ws.append_row([str(x) if x is not None else "" for x in row], value_input_option="USER_ENTERED")
        return True
    except Exception as e:
        dbg("append_row_error", str(e))
        return False

def check_student_code(code: str) -> bool:
    sh = open_sheet()
    if not sh:
        return False
    try:
        ws = sh.worksheet(CONTROL_TAB_NAME) if CONTROL_TAB_NAME else sh.sheet1
        real = str(ws.acell("B1").value).strip()
        return str(code).strip() == real
    except Exception as e:
        dbg("check_student_code_error", str(e))
        return False

def get_logging_sheets():
    sh = open_sheet()
    if not sh:
        return None, None, None
    results_headers = [
        "timestamp", "student_name", "role", "stage", "grade", "subject", "term", "lang",
        "type", "ref_book", "question", "student_answer", "score", "feedback"
    ]
    assign_headers = [
        "assignment_id", "created_at", "teacher_name", "stage", "grade", "subject", "term", "lang",
        "title", "difficulty", "questions_json", "active"
    ]
    sub_headers = [
        "submission_id", "submitted_at", "assignment_id", "student_name", "stage", "grade", "subject", "term", "lang",
        "answers_json", "grading_json", "total_score"
    ]
    ws_results = ensure_ws(sh, RESULTS_TAB_NAME, results_headers)
    ws_assign = ensure_ws(sh, ASSIGNMENTS_TAB_NAME, assign_headers)
    ws_sub = ensure_ws(sh, SUBMISSIONS_TAB_NAME, sub_headers)
    return ws_results, ws_assign, ws_sub

def log_result(kind: str, question: str, student_answer: str, score: str, feedback: str):
    ws_results, _, _ = get_logging_sheets()
    if not ws_results:
        return
    u = st.session_state.user_data
    book = st.session_state.book_data.get("name", "")
    row = [
        time.strftime("%Y-%m-%d %H:%M:%S"), u.get("name", ""), u.get("role", ""),
        u.get("stage", ""), u.get("grade", ""), u.get("subject", ""),
        u.get("term", ""), u.get("lang", ""), kind, book,
        question, student_answer, score, feedback
    ]
    append_row(ws_results, row)

# =========================
# Drive helpers
# =========================
@st.cache_resource
def get_drive_service():
    creds = get_credentials()
    if not creds:
        return None
    return build("drive", "v3", credentials=creds)

@st.cache_data(ttl=300, show_spinner=False)
def list_drive_pdfs(folder_id: str) -> List[Dict[str, Any]]:
    service = get_drive_service()
    if not service or not folder_id:
        return []
    q = f"'{folder_id}' in parents and mimeType='application/pdf' and trashed=false"
    res = service.files().list(q=q, fields="files(id,name,modifiedTime,size)").execute()
    return res.get("files", [])

def download_drive_pdf(file_id: str, file_name: str) -> Optional[str]:
    service = get_drive_service()
    if not service:
        return None
    try:
        safe = re.sub(r"[^a-zA-Z0-9_\-\.]+", "_", file_name)
        local = os.path.join(CHROMA_PERSIST_DIR, "books_cache", f"{file_id}_{safe}")
        os.makedirs(os.path.dirname(local), exist_ok=True)
        if os.path.exists(local) and os.path.getsize(local) > 10_000:
            return local
        request = service.files().get_media(fileId=file_id)
        with open(local, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        return local
    except Exception as e:
        dbg("download_drive_pdf_error", str(e))
        return None

def load_book(stage: str, grade: str, subject: str, term: str, lang_ui: str) -> Optional[Dict[str, Any]]:
    files = list_drive_pdfs(FOLDER_ID)
    if not files:
        return None
    toks_with_term, toks_no_term = drive_tokens(stage, grade, subject, term, lang_ui)
    
    def match(token_list: List[str]) -> Optional[Dict[str, Any]]:
        for f in files:
            name_low = (f.get("name") or "").lower()
            if all(tok.lower() in name_low for tok in token_list if tok):
                return f
        return None

    matched = match(toks_with_term)
    matched_with_term = True
    if not matched:
        matched = match(toks_no_term)
        matched_with_term = False

    if not matched:
        dbg("book_not_found", {"with_term": toks_with_term, "no_term": toks_no_term})
        return None

    path = download_drive_pdf(matched["id"], matched["name"])
    if not path:
        return None

    return {
        "id": matched["id"],
        "name": matched["name"],
        "path": path,
        "matched_with_term": matched_with_term
    }

# =========================
# OCR Functions
# =========================
@st.cache_data(show_spinner=False)
def ocr_image(img_bytes: bytes, lang: str) -> str:
    try:
        im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        return (pytesseract.image_to_string(im, lang=lang) or "").strip()
    except Exception as e:
        return f"__OCR_ERROR__:{e}"

@st.cache_data(show_spinner="جاري OCR للـ PDF ...")
def ocr_pdf(pdf_path: str, lang: str, max_pages: Optional[int] = None) -> str:
    try:
        texts = []
        batch = 6
        start = 1
        done_pages = 0
        while True:
            if max_pages is not None and done_pages >= max_pages:
                break
            end = start + batch - 1
            try:
                pages = convert_from_path(pdf_path, dpi=200, first_page=start, last_page=end)
            except Exception:
                break
            if not pages:
                break
            for im in pages:
                if max_pages is not None and done_pages >= max_pages:
                    break
                texts.append(pytesseract.image_to_string(im, lang=lang))
                done_pages += 1
            if len(pages) < batch:
                break
            start += batch
        return "\n\n--- نهاية الصفحة ---\n\n".join(texts).strip()
    except Exception as e:
        return f"__OCR_ERROR__:{e}"

# =========================
# RAG / Chroma
# =========================
def pick_api_key() -> Optional[str]:
    return random.choice(GOOGLE_API_KEYS) if GOOGLE_API_KEYS else None

def get_embeddings():
    k = pick_api_key()
    if not k:
        return None
    return GoogleGenerativeAIEmbeddings(model="models/embedding-001", google_api_key=k)

def get_llm(temp: float = 0.2):
    k = pick_api_key()
    if not k:
        return None
    # FIX: Updated model name from 'gemini-1.5-flash-latest' to 'gemini-1.5-flash'
    return ChatGoogleGenerativeAI(model="gemini-1.5-flash", google_api_key=k, temperature=temp)

def split_docs(text: str) -> List[Document]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=1800, chunk_overlap=220, add_start_index=True)
    return [Document(page_content=ch) for ch in splitter.split_text(text) if ch.strip()]

def coll_key(base_sig: str, matched_with_term: bool, term: str, book_id: str) -> str:
    term_part = term_token(term) if matched_with_term else "NO_TERM"
    raw = f"{base_sig}|{term_part}|{book_id}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()

def load_or_create_chroma(persist_dir: str, collection_name: str, text: str) -> Optional[Chroma]:
    try:
        emb = get_embeddings()
        if not emb:
            return None
        os.makedirs(persist_dir, exist_ok=True)
        has_existing = any(os.scandir(persist_dir))
        if has_existing:
            return Chroma(collection_name=collection_name, persist_directory=persist_dir, embedding_function=emb)
        docs = split_docs(text)
        if not docs:
            return None
        vs = Chroma.from_documents(docs, embedding=emb, collection_name=collection_name, persist_directory=persist_dir)
        try:
            vs.persist()
        except Exception:
            pass
        return vs
    except Exception as e:
        dbg("chroma_error", str(e))
        return None

def ensure_book_ready() -> bool:
    u = st.session_state.user_data
    base_sig = f"{u['stage']}|{u['grade']}|{u['subject']}|{u['lang']}"
    if st.session_state.book_data.get("base_sig") != base_sig:
        st.session_state.book_data = {"base_sig": base_sig}
        st.session_state.vector_store = None
    if not st.session_state.book_data.get("path"):
        data = load_book(u["stage"], u["grade"], u["subject"], u["term"], u["lang"])
        if not data:
            st.error("لم يتم العثور على كتاب مطابق في Drive. تأكد أن الاسم يحتوي مثل: Sec3 + Physics + En/Ar.")
            return False
        st.session_state.book_data.update(data)
    matched_with_term = bool(st.session_state.book_data.get("matched_with_term", False))
    final_sig = f"{base_sig}|{term_token(u['term']) if matched_with_term else 'NO_TERM'}"
    if st.session_state.book_data.get("final_sig") != final_sig:
        st.session_state.book_data["final_sig"] = final_sig
        st.session_state.vector_store = None
    if st.session_state.vector_store is None:
        pdf_path = st.session_state.book_data["path"]
        if not os.path.exists(pdf_path):
            st.error("ملف الكتاب غير موجود محلياً.")
            return False
        with st.spinner("OCR للكتاب + بناء/تحميل الفهرس (أول مرة قد يطول)..."):
            full_text = ocr_pdf(pdf_path, lang=ocr_lang(u["lang"]), max_pages=None)
        if not full_text or "__OCR_ERROR__" in full_text:
            st.error(f"فشل OCR: {full_text}")
            return False
        ckey = coll_key(base_sig, matched_with_term, u["term"], st.session_state.book_data.get("id", "noid"))
        persist_dir = os.path.join(CHROMA_PERSIST_DIR, "chroma_books", ckey)
        vs = load_or_create_chroma(persist_dir, ckey, full_text)
        if not vs:
            st.error("فشل إنشاء/تحميل Chroma.")
            return False
        st.session_state.vector_store = vs
    return True

def build_upload_vs(text: str) -> Optional[Chroma]:
    try:
        emb = get_embeddings()
        if not emb:
            return None
        docs = split_docs(text)
        if not docs:
            return None
        return Chroma.from_documents(docs, embedding=emb)
    except Exception as e:
        dbg("upload_vs_error", str(e))
        return None

def retrieve(query: str, k: int = 6) -> List[Document]:
    docs: List[Document] = []
    try:
        if st.session_state.vector_store is not None:
            docs.extend(st.session_state.vector_store.similarity_search(query, k=k))
    except Exception as e:
        dbg("retrieve_book_error", str(e))
    try:
        uvs = st.session_state.uploaded_context.get("vs")
        if uvs is not None:
            docs.extend(uvs.similarity_search(query, k=max(2, k // 2)))
    except Exception as e:
        dbg("retrieve_upload_error", str(e))
    seen, out = set(), []
    for d in docs:
        key = (d.page_content or "")[:140]
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out[:10]

def prompt_chat(lang_ui: str) -> PromptTemplate:
    template = ui(
        lang_ui,
        """أنت معلم علوم خبير. أجب بدقة ووضوح.
استخدم السياق (كتاب الطالب + ملف مرفوع) أولاً.
إذا لم تجد الإجابة في السياق، أجب من خبرتك ولكن صرّح أنها ليست نصاً حرفياً من الكتاب.
السياق: {context}
سؤال الطالب: {question}
الإجابة:""",
        """You are an expert science teacher. Answer clearly and accurately.
Use the context (textbook + uploaded file) first.
If not found in context, answer from general knowledge but clearly state it's not explicitly from the textbook.
Context: {context}
Question: {question}
Answer:"""
    )
    return PromptTemplate(template=template, input_variables=["context", "question"])

def prompt_grade(lang_ui: str) -> PromptTemplate:
    template = ui(
        lang_ui,
        """أنت معلم علوم خبير. قيّم إجابة الطالب اعتماداً على السياق.
السؤال: {question}
إجابة الطالب: {student_answer}
الإجابة النموذجية: {model_answer}
السياق: {context}
أخرج النتيجة بصيغة:
الدرجة: X/10
تعليق مختصر: ...""",
        """You are an expert science teacher. Grade the student's answer using the context.
Question: {question}
Student answer: {student_answer}
Model answer: {model_answer}
Context: {context}
Output:
Score: X/10
Short feedback: ..."""
    )
    return PromptTemplate(template=template, input_variables=["context", "question", "student_answer", "model_answer"])

def run_chat(lang_ui: str, q: str) -> str:
    llm = get_llm(0.2)
    if not llm:
        return ui(lang_ui, "⚠️ مفاتيح Google API غير متاحة.", "⚠️ Google API keys missing.")
    docs = retrieve(q, k=6)
    chain = load_qa_chain(llm, chain_type="stuff", prompt=prompt_chat(lang_ui))
    out = chain.invoke({"input_documents": docs, "question": q}, return_only_outputs=True)
    return (out.get("output_text") or "").strip() or ui(lang_ui, "لم أجد إجابة.", "No answer found.")

def extract_score(text: str) -> str:
    m = re.search(r'(\d{1,2})\s*/\s*10', text)
    return f"{m.group(1)}/10" if m else ""

def run_grade(lang_ui: str, q: str, student_answer: str, model_answer: str) -> str:
    llm = get_llm(0.2)
    if not llm:
        return ui(lang_ui, "⚠️ مفاتيح Google API غير متاحة.", "⚠️ Google API keys missing.")
    docs = retrieve(q, k=7)
    chain = load_qa_chain(llm, chain_type="stuff", prompt=prompt_grade(lang_ui))
    out = chain.invoke({
        "input_documents": docs, "question": q,
        "student_answer": student_answer, "model_answer": model_answer
    }, return_only_outputs=True)
    return (out.get("output_text") or "").strip()

def generate_quiz(lang_ui: str) -> Tuple[str, str]:
    llm = get_llm(0.5)
    if not llm:
        return "", ""
    seeds_ar = ["عرّف", "اشرح", "لماذا", "قارن", "اذكر", "ما وظيفة", "كيف يحدث"]
    seeds_en = ["define", "explain", "why", "compare", "describe", "function", "how"]
    seed = random.choice(seeds_en if is_english(lang_ui) else seeds_ar)
    docs = retrieve(seed, k=6)
    context = "\n\n".join(d.page_content for d in docs) if docs else ""
    if not context.strip():
        return "", ""
    prompt = ui(
        lang_ui,
        """من النص التالي: كوّن سؤال اختبار واحد + إجابة نموذجية قصيرة.
أخرج JSON فقط: {"question":"...","answer":"..."}
النص: {context}""",
        """From the text: create ONE quiz question + a short model answer.
Return JSON only: {"question":"...","answer":"..."}
Text: {context}"""
    )
    try:
        resp = llm.invoke(prompt.format(context=context)).content.strip()
        resp = resp.strip("```").replace("json", "").strip()
        data = json.loads(resp)
        return (data.get("question", "").strip(), data.get("answer", "").strip())
    except Exception as e:
        dbg("quiz_gen_error", str(e))
        return "", ""

def generate_assignment(lang_ui: str, title: str, difficulty: str, n: int) -> List[Dict[str, str]]:
    llm = get_llm(0.6)
    if not llm:
        return []
    docs = retrieve(title or ("science" if is_english(lang_ui) else "علوم"), k=8)
    context = "\n\n".join(d.page_content for d in docs) if docs else ""
    if not context.strip():
        return []
    prompt = ui(
        lang_ui,
        f"""من النص التالي كوّن واجب عدد أسئلته {n} بمستوى "{difficulty}".
أخرج JSON فقط: قائمة بالشكل: [{{"q":"...","a":"..."}}]
النص: {{context}}""",
        f"""From the text create homework with {n} questions difficulty "{difficulty}".
Return JSON only as list: [{{"q":"...","a":"..."}}]
Text: {{context}}"""
    )
    try:
        resp = llm.invoke(prompt.format(context=context)).content.strip()
        resp = resp.strip("```").replace("json", "").strip()
        arr = json.loads(resp)
        out = []
        for item in arr:
            q = (item.get("q") or "").strip()
            a = (item.get("a") or "").strip()
            if q:
                out.append({"q": q, "a": a})
        return out[:n]
    except Exception as e:
        dbg("assignment_gen_error", str(e))
        return []

def create_assignment_in_sheet(title: str, difficulty: str, questions: List[Dict[str, str]]) -> bool:
    _, ws_assign, _ = get_logging_sheets()
    if not ws_assign:
        return False
    u = st.session_state.user_data
    aid = f"A{int(time.time())}_{random.randint(1000, 9999)}"
    row = [
        aid, time.strftime("%Y-%m-%d %H:%M:%S"), u.get("name", ""),
        u.get("stage", ""), u.get("grade", ""), u.get("subject", ""), u.get("term", ""), u.get("lang", ""),
        title, difficulty, json.dumps(questions, ensure_ascii=False), "TRUE"
    ]
    return append_row(ws_assign, row)

def fetch_assignments(stage: str, grade: str, subject: str, term: str, lang_ui: str) -> List[Dict[str, Any]]:
    _, ws_assign, _ = get_logging_sheets()
    if not ws_assign:
        return []
    try:
        recs = ws_assign.get_all_records()
        out = []
        for r in recs:
            active = str(r.get("active", "")).lower()
            if active not in ["true", "1", "yes"]:
                continue
            if r.get("stage") == stage and r.get("grade") == grade and r.get("subject") == subject and r.get("term") == term and r.get("lang") == lang_ui:
                out.append(r)
        out.reverse()
        return out
    except Exception as e:
        dbg("fetch_assignments_error", str(e))
        return []

def submit_assignment(aid: str, questions: List[Dict[str, str]], answers: List[str], lang_ui: str) -> Tuple[str, str]:
    grading = []
    total = 0
    n = max(1, len(questions))
    for i, qa in enumerate(questions):
        q = qa.get("q", "")
        model = qa.get("a", "")
        ans = (answers[i] if i < len(answers) else "").strip()
        gtext = run_grade(lang_ui, q, ans, model)
        score = extract_score(gtext)
        try:
            num = int(score.split("/")[0]) if score else 0
        except Exception:
            num = 0
        total += num
        grading.append({"q": q, "student_answer": ans, "model_answer": model, "grading_text": gtext, "score": score})
    total_score = round((total / (10 * n)) * 10, 1)
    return f"{total_score}/10", json.dumps(grading, ensure_ascii=False)

def save_submission(aid: str, answers: List[str], grading_json: str, total_score: str) -> bool:
    _, _, ws_sub = get_logging_sheets()
    if not ws_sub:
        return False
    u = st.session_state.user_data
    sid = f"S{int(time.time())}_{random.randint(1000, 9999)}"
    row = [
        sid, time.strftime("%Y-%m-%d %H:%M:%S"), aid, u.get("name", ""),
        u.get("stage", ""), u.get("grade", ""), u.get("subject", ""), u.get("term", ""), u.get("lang", ""),
        json.dumps(answers, ensure_ascii=False), grading_json, total_score
    ]
    return append_row(ws_sub, row)

# =========================
# STT/TTS
# =========================
def clean_speech_text(text: str) -> str:
    text = re.sub(r'[*#_`]', '', text)
    return re.sub(r'\s+', ' ', text).strip()

def speech_to_text(audio_bytes: bytes, lang_ui: str) -> Optional[str]:
    r = sr.Recognizer()
    try:
        with sr.AudioFile(io.BytesIO(audio_bytes)) as source:
            audio_data = r.record(source)
        code = "en-US" if is_english(lang_ui) else "ar-EG"
        return r.recognize_google(audio_data, language=code)
    except Exception as e:
        dbg("stt_error", str(e))
        return None

async def tts_async(text: str, lang_ui: str) -> str:
    voice = "en-US-ChristopherNeural" if is_english(lang_ui) else "ar-EG-ShakirNeural"
    communicate = edge_tts.Communicate(clean_speech_text(text), voice)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
        await communicate.save(tmp.name)
        return tmp.name

def text_to_speech(text: str, lang_ui: str) -> Optional[str]:
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(tts_async(text, lang_ui))
    except Exception as e:
        dbg("tts_error", str(e))
        return None

# =========================
# Main Pages
# =========================
def login_page():
    st.markdown("### 🔐 تسجيل الدخول")
    with st.form("login_form"):
        name = st.text_input("الاسم الثلاثي")
        code = st.text_input("الكود السري", type="password")
        c1, c2 = st.columns(2)
        with c1:
            stage = st.selectbox("المرحلة", STAGES)
            grade = st.selectbox("الصف", GRADES[stage])
            term = st.selectbox("الترم", TERMS)
        with c2:
            lang_ui = st.selectbox("اللغة", LANGS)
            subject = st.selectbox("المادة", subjects_for(stage, grade))
        submit = st.form_submit_button("🚀 بدء التعلم")

    if submit:
        is_teacher = (code == TEACHER_KEY)
        is_student = check_student_code(code)
        if not (is_teacher or is_student):
            st.error("❌ الكود غير صحيح")
            return
        
        st.session_state.messages = []
        st.session_state.book_data = {}
        st.session_state.vector_store = None
        st.session_state.uploaded_context = {"name": "", "text": "", "vs": None}
        st.session_state.quiz = {"state": "off", "q": "", "model": ""}
        st.session_state.tts_enabled = False
        st.session_state.user_data = {
            "logged_in": True,
            "role": "Teacher" if is_teacher else "Student",
            "name": (name.strip() or ("Teacher" if is_teacher else "Student")),
            "stage": stage, "grade": grade, "subject": subject, "term": term, "lang": lang_ui
        }
        st.rerun()

def sidebar():
    u = st.session_state.user_data
    with st.sidebar:
        st.success(f"مرحباً: {u.get('name','')}")
        st.info(f"{u['grade']} {u['stage']} | {u['subject']} | {u['term']} | {u['lang']}")
        st.write("---")
        st.markdown("#### ⚙️ تغيير الإعدادات")
        stage = st.selectbox("المرحلة", STAGES, index=STAGES.index(u["stage"]))
        grade = st.selectbox("الصف", GRADES[stage], index=GRADES[stage].index(u["grade"]))
        term = st.selectbox("الترم", TERMS, index=TERMS.index(u["term"]))
        subject = st.selectbox("المادة", subjects_for(stage, grade), index=0)
        lang_ui = st.selectbox("اللغة", LANGS, index=LANGS.index(u["lang"]))
        if st.button("✅ تطبيق"):
            st.session_state.user_data.update({"stage": stage, "grade": grade, "term": term, "subject": subject, "lang": lang_ui})
            st.rerun()
        st.write("---")
        st.session_state.tts_enabled = st.checkbox("🔊 قراءة الإجابة بالصوت تلقائياً", value=st.session_state.tts_enabled)
        st.write("---")
        st.session_state.debug_enabled = st.checkbox("DEBUG", value=st.session_state.debug_enabled)
        if st.session_state.debug_enabled:
            with st.expander("سجل DEBUG"):
                st.code(json.dumps(st.session_state.debug_log, ensure_ascii=False, indent=2))
        st.write("---")
        if st.button("🚪 خروج"):
            st.session_state.user_data = {"logged_in": False, "role": None, "name": ""}
            st.rerun()

def upload_tab(lang_ui: str):
    st.markdown("### 📎 رفع صورة / PDF (مرجع إضافي)")
    up = st.file_uploader("ارفع صورة (PNG/JPG) أو PDF", type=["png", "jpg", "jpeg", "pdf"])
    if not up:
        return
    data = up.getvalue()
    name = up.name
    key = f"{name}:{sha256_bytes(data)}"
    if st.session_state.uploaded_context.get("name") == key:
        st.info("تم تحميل نفس الملف بالفعل.")
        return
    with st.spinner("جاري استخراج النص (OCR)..."):
        if name.lower().endswith(".pdf"):
            tmp = os.path.join(tempfile.gettempdir(), f"upload_{sha256_bytes(data)}.pdf")
            with open(tmp, "wb") as f:
                f.write(data)
            text = ocr_pdf(tmp, lang=ocr_lang(lang_ui), max_pages=25)
        else:
            text = ocr_image(data, lang=ocr_lang(lang_ui))
    if "__OCR_ERROR__" in (text or ""):
        st.error(f"فشل OCR: {text}")
        return
    st.success("✅ تم استخراج النص.")
    with st.expander("عرض جزء من النص"):
        st.write(text[:6000] + ("..." if len(text) > 6000 else ""))
    with st.spinner("جاري فهرسة الملف المرفوع..."):
        vs = build_upload_vs(text)
    st.session_state.uploaded_context = {"name": key, "text": text, "vs": vs}
    st.info("تم تفعيل الملف كمصدر إضافي للإجابات.")

def chat_tab():
    u = st.session_state.user_data
    lang_ui = u["lang"]
    st.markdown("### 💬 الشات")
    audio = mic_recorder(start_prompt="تحدث ⏺️", stop_prompt="إرسال ⏹️", key="recorder", format="wav", use_container_width=True)
    voice_text = None
    if audio:
        with st.spinner("تحويل الصوت إلى نص..."):
            voice_text = speech_to_text(audio["bytes"], lang_ui)
            if voice_text:
                st.info(voice_text)
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
    typed = st.chat_input(ui(lang_ui, "اكتب سؤالك أو واجبك هنا...", "Type your question/homework here..."))
    final_q = typed if typed else voice_text
    if final_q:
        st.session_state.messages.append({"role": "user", "content": final_q})
        with st.chat_message("assistant"):
            with st.spinner("المعلم يفكر..."):
                resp = run_chat(lang_ui, final_q)
                st.write(resp)
                want_tts = st.session_state.tts_enabled or ("اقرأ" in final_q) or ("read" in final_q.lower())
                if want_tts:
                    aud = text_to_speech(resp, lang_ui)
                    if aud:
                        st.audio(aud, format="audio/mp3")
                        try:
                            os.remove(aud)
                        except Exception:
                            pass
        st.session_state.messages.append({"role": "assistant", "content": resp})
        st.rerun()

def quiz_tab():
    u = st.session_state.user_data
    lang_ui = u["lang"]
    st.markdown("### 📝 اختبار سريع")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🎯 سؤال جديد"):
            st.session_state.quiz = {"state": "asking", "q": "", "model": ""}
            st.rerun()
    with c2:
        if st.button("🧹 إنهاء"):
            st.session_state.quiz = {"state": "off", "q": "", "model": ""}
            st.rerun()
    if st.session_state.quiz["state"] == "asking":
        with st.spinner("إنشاء سؤال..."):
            q, a = generate_quiz(lang_ui)
            if not q:
                st.error("تعذر إنشاء سؤال.")
                st.session_state.quiz = {"state": "off", "q": "", "model": ""}
            else:
                st.session_state.quiz = {"state": "waiting", "q": q, "model": a}
            st.rerun()
    if st.session_state.quiz["state"] == "waiting":
        st.write("**السؤال:**")
        st.write(st.session_state.quiz["q"])
        ans = st.text_area("إجابتك", height=120)
        if st.button("✅ تصحيح"):
            with st.spinner("تصحيح..."):
                gtext = run_grade(lang_ui, st.session_state.quiz["q"], ans, st.session_state.quiz["model"])
                score = extract_score(gtext)
                st.write(gtext)
                log_result("Quiz", st.session_state.quiz["q"], ans, score, gtext)
                if st.session_state.tts_enabled:
                    aud = text_to_speech(gtext, lang_ui)
                    if aud:
                        st.audio(aud, format="audio/mp3")
                        try:
                            os.remove(aud)
                        except Exception:
                            pass

def homework_tab():
    u = st.session_state.user_data
    lang_ui = u["lang"]
    st.markdown("### 📚 الواجبات")
    if u["role"] == "Teacher":
        with st.expander("➕ إنشاء واجب جديد", expanded=True):
            title = st.text_input("عنوان الواجب", value=ui(lang_ui, "واجب على الدرس الحالي", "Homework on current lesson"))
            difficulty = st.selectbox("الصعوبة", ["سهل", "متوسط", "صعب"])
            n = st.slider("عدد الأسئلة", 3, 10, 5)
            if st.button("✨ إنشاء وحفظ"):
                with st.spinner("توليد أسئلة الواجب من الكتاب..."):
                    qs = generate_assignment(lang_ui, title, difficulty, n)
                if not qs:
                    st.error("فشل إنشاء الواجب.")
                else:
                    ok = create_assignment_in_sheet(title, difficulty, qs)
                    st.success("تم حفظ الواجب ✅" if ok else "تعذر الحفظ في Sheets.")
    st.markdown("#### الواجبات المتاحة")
    assigns = fetch_assignments(u["stage"], u["grade"], u["subject"], u["term"], u["lang"])
    if not assigns:
        st.info("لا توجد واجبات حالياً.")
        return
    options = {f"{a.get('title','واجب')} | {a.get('created_at','')}": a for a in assigns}
    label = st.selectbox("اختر واجباً", list(options.keys()))
    chosen = options[label]
    try:
        questions = json.loads(chosen.get("questions_json", "[]"))
    except Exception:
        questions = []
    if not questions:
        st.error("صيغة أسئلة الواجب غير صحيحة.")
        return
    st.write(f"**العنوان:** {chosen.get('title','')}")
    st.write(f"**الصعوبة:** {chosen.get('difficulty','')}")
    st.write(f"**عدد الأسئلة:** {len(questions)}")
    answers = []
    for i, qa in enumerate(questions, start=1):
        st.write(f"**س{i}:** {qa.get('q','')}")
        answers.append(st.text_area(f"إجابتك عن س{i}", height=90, key=f"hw_{chosen.get('assignment_id','')}_{i}"))
    if u["role"] == "Student":
        if st.button("📨 تسليم وتصحيح"):
            aid = chosen.get("assignment_id", "")
            with st.spinner("تصحيح الواجب..."):
                total_score, grading_json = submit_assignment(aid, questions, answers, lang_ui)
                ok = save_submission(aid, answers, grading_json, total_score)
                log_result("Homework", chosen.get("title", ""), json.dumps(answers, ensure_ascii=False), total_score, grading_json)
                st.success(f"تم التسليم ✅ | درجتك: {total_score}" if ok else f"تم التصحيح لكن تعذر الحفظ | درجتك: {total_score}")
                if st.session_state.tts_enabled:
                    aud = text_to_speech(ui(lang_ui, f"درجتك {total_score}", f"Your score is {total_score}"), lang_ui)
                    if aud:
                        st.audio(aud, format="audio/mp3")
                        try:
                            os.remove(aud)
                        except Exception:
                            pass

def teacher_dashboard_tab():
    st.markdown("### 📊 متابعة (Sheets)")
    ws_results, ws_assign, ws_sub = get_logging_sheets()
    if not ws_results:
        st.error("لا يمكن الوصول إلى Google Sheets الآن.")
        return
    try:
        st.markdown("#### Results (آخر 200)")
        st.dataframe(ws_results.get_all_records()[-200:])
    except Exception as e:
        st.error(f"تعذر عرض Results: {e}")
    try:
        st.markdown("#### Assignments (آخر 200)")
        st.dataframe(ws_assign.get_all_records()[-200:])
    except Exception as e:
        st.error(f"تعذر عرض Assignments: {e}")
    try:
        st.markdown("#### Submissions (آخر 200)")
        st.dataframe(ws_sub.get_all_records()[-200:])
    except Exception as e:
        st.error(f"تعذر عرض Submissions: {e}")

def main_app():
    sidebar()
    if not ensure_book_ready():
        st.stop()
    u = st.session_state.user_data
    tabs = ["💬 الشات", "📎 رفع ملف/صورة", "📚 واجبات", "📝 اختبارات"]
    if u["role"] == "Teacher":
        tabs.append("📊 متابعة")
    t = st.tabs(tabs)
    with t[0]:
        chat_tab()
    with t[1]:
        upload_tab(u["lang"])
    with t[2]:
        homework_tab()
    with t[3]:
        quiz_tab()
    if u["role"] == "Teacher":
        with t[4]:
            teacher_dashboard_tab()

if __name__ == "__main__":
    if st.session_state.user_data.get("logged_in", False):
        main_app()
    else:
        login_page()
