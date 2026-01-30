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

# LangChain & AI Imports
try:
    from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
except ImportError:
    import langchain_google_genai
    from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI

from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import PromptTemplate
from langchain_core.documents import Document

# QA Chain Import
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
            st.error("لم يتم العثور على كتاب مطابق.")
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
        with st.spinner("OCR للكتاب + بناء/تحميل الفهرس..."):
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
    template = ui(lang_ui, "السياق: {context}\nالسؤال: {question}\nالإجابة:", "Context: {context}\nQuestion: {question}\nAnswer:")
    return PromptTemplate(template=template, input_variables=["context", "question"])

def prompt_grade(lang_ui: str) -> PromptTemplate:
    template = ui(lang_ui, "قيّم الإجابة.\nالسؤال: {question}\nإجابة الطالب: {student_answer}\nالنموذج: {model_answer}\nالسياق: {context}", "Grade answer.\nQ: {question}\nA: {student_answer}\nModel: {model_answer}\nContext: {context}")
    return PromptTemplate(template=template, input_variables=["context", "question", "student_answer", "model_answer"])

def run_chat(lang_ui: str, q: str) -> str:
    llm = get_llm(0.2)
    if not llm: return ui(lang_ui, "مفاتيح مفقودة", "Missing keys")
    docs = retrieve(q, k=6)
    chain = load_qa_chain(llm, chain_type="stuff", prompt=prompt_chat(lang_ui))
    out = chain.invoke({"input_documents": docs, "question": q}, return_only_outputs=True)
    return (out.get("output_text") or "").strip()

def extract_score(text: str) -> str:
    m = re.search(r'(\d{1,2})\s*/\s*10', text)
    return f"{m.group(1)}/10" if m else ""

def run_grade(lang_ui: str, q: str, student_answer: str, model_answer: str) -> str:
    llm = get_llm(0.2)
    if not llm: return ""
    docs = retrieve(q, k=7)
    chain = load_qa_chain(llm, chain_type="stuff", prompt=prompt_grade(lang_ui))
    out = chain.invoke({"input_documents": docs, "question": q, "student_answer": student_answer, "model_answer": model_answer}, return_only_outputs=True)
    return (out.get("output_text") or "").strip()

def generate_quiz(lang_ui: str) -> Tuple[str, str]:
    llm = get_llm(0.5)
    if not llm: return "", ""
    docs = retrieve("question", k=6)
    context = "\n".join(d.page_content for d in docs)
    prompt = f"Create 1 quiz question and short answer JSON from: {context}"
    try:
        resp = llm.invoke(prompt).content.strip().replace("json","").replace("`","")
        data = json.loads(resp)
        return data.get("question",""), data.get("answer","")
    except: return "", ""

def generate_assignment(lang_ui: str, title: str, difficulty: str, n: int) -> List[Dict[str, str]]:
    llm = get_llm(0.6)
    if not llm: return []
    docs = retrieve(title, k=8)
    context = "\n".join(d.page_content for d in docs)
    prompt = f"Create {n} homework questions difficulty {difficulty} as JSON list from: {context}"
    try:
        resp = llm.invoke(prompt).content.strip().replace("json","").replace("`","")
        arr = json.loads(resp)
        return [{"q": x.get("q",""), "a": x.get("a","")} for x in arr if "q" in x]
    except: return []

def create_assignment_in_sheet(title: str, difficulty: str, questions: List[Dict[str, str]]) -> bool:
    _, ws_assign, _ = get_logging_sheets()
    if not ws_assign: return False
    u = st.session_state.user_data
    row = [f"A{int(time.time())}", time.strftime("%Y-%m-%d"), u.get("name"), u.get("stage"), u.get("grade"), u.get("subject"), u.get("term"), u.get("lang"), title, difficulty, json.dumps(questions), "TRUE"]
    return append_row(ws_assign, row)

def fetch_assignments(stage: str, grade: str, subject: str, term: str, lang_ui: str) -> List[Dict[str, Any]]:
    _, ws_assign, _ = get_logging_sheets()
    if not ws_assign: return []
    try:
        recs = ws_assign.get_all_records()
        return [r for r in recs if r.get("active")=="TRUE" and r.get("grade")==grade]
    except: return []

def submit_assignment(aid: str, questions: List[Dict[str, str]], answers: List[str], lang_ui: str) -> Tuple[str, str]:
    grading = []
    total = 0
    for i, qa in enumerate(questions):
        gtext = run_grade(lang_ui, qa["q"], answers[i], qa["a"])
        score = extract_score(gtext)
        if score: total += int(score.split("/")[0])
        grading.append({"q": qa["q"], "score": score, "feedback": gtext})
    return f"{total}/{(len(questions)*10)}", json.dumps(grading)

def save_submission(aid: str, answers: List[str], grading_json: str, total_score: str) -> bool:
    _, _, ws_sub = get_logging_sheets()
    if not ws_sub: return False
    u = st.session_state.user_data
    row = [f"S{int(time.time())}", time.strftime("%Y-%m-%d"), aid, u.get("name"), u.get("stage"), u.get("grade"), u.get("subject"), u.get("term"), u.get("lang"), json.dumps(answers), grading_json, total_score]
    return append_row(ws_sub, row)
    # =========================
# UI & Main Logic
# =========================
def clean_speech_text(text: str) -> str:
    return re.sub(r'[*#_`]', '', text).strip()

def speech_to_text(audio_bytes: bytes, lang_ui: str) -> Optional[str]:
    r = sr.Recognizer()
    try:
        with sr.AudioFile(io.BytesIO(audio_bytes)) as source:
            audio_data = r.record(source)
        return r.recognize_google(audio_data, language="en-US" if is_english(lang_ui) else "ar-EG")
    except: return None

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
    except: return None

def login_page():
    st.markdown("### 🔐 تسجيل الدخول")
    with st.form("login_form"):
        name = st.text_input("الاسم")
        code = st.text_input("الكود", type="password")
        c1, c2 = st.columns(2)
        with c1:
            stage = st.selectbox("المرحلة", STAGES)
            grade = st.selectbox("الصف", GRADES.get(stage, []))
            term = st.selectbox("الترم", TERMS)
        with c2:
            lang_ui = st.selectbox("اللغة", LANGS)
            subject = st.selectbox("المادة", subjects_for(stage, grade))
        if st.form_submit_button("🚀 دخول"):
            if code == TEACHER_KEY or check_student_code(code):
                st.session_state.user_data = {"logged_in": True, "role": "Teacher" if code==TEACHER_KEY else "Student", "name": name, "stage": stage, "grade": grade, "term": term, "subject": subject, "lang": lang_ui}
                st.rerun()
            else:
                st.error("الكود غير صحيح")

def sidebar():
    u = st.session_state.user_data
    with st.sidebar:
        st.success(f"مرحباً: {u.get('name')}")
        st.info(f"{u['grade']} | {u['subject']}")
        
        try: stage_idx = STAGES.index(u["stage"])
        except: stage_idx = 0
        stage = st.selectbox("المرحلة", STAGES, index=stage_idx)
        
        grades = GRADES.get(stage, [])
        grade = st.selectbox("الصف", grades, index=0)
        term = st.selectbox("الترم", TERMS)
        subject = st.selectbox("المادة", subjects_for(stage, grade))
        lang_ui = st.selectbox("اللغة", LANGS)

        if st.button("تحديث"):
            st.session_state.user_data.update({"stage": stage, "grade": grade, "term": term, "subject": subject, "lang": lang_ui})
            st.rerun()
            
        st.write("---")
        st.session_state.tts_enabled = st.checkbox("🔊 قراءة صوتية", value=st.session_state.tts_enabled)
        if st.button("خروج"):
            st.session_state.user_data["logged_in"] = False
            st.rerun()

def chat_tab():
    st.markdown("### 💬 الشات")
    audio = mic_recorder(start_prompt="تحدث", stop_prompt="إرسال", key="rec")
    vtext = speech_to_text(audio['bytes'], st.session_state.user_data['lang']) if audio else ""
    if vtext: st.info(vtext)
    
    for m in st.session_state.messages:
        with st.chat_message(m["role"]): st.write(m["content"])
    
    q = st.chat_input("سؤالك...")
    if q or vtext:
        fin_q = q if q else vtext
        st.session_state.messages.append({"role": "user", "content": fin_q})
        with st.chat_message("assistant"):
            resp = run_chat(st.session_state.user_data['lang'], fin_q)
            st.write(resp)
            if st.session_state.tts_enabled:
                aud = text_to_speech(resp, st.session_state.user_data['lang'])
                if aud: st.audio(aud)
        st.session_state.messages.append({"role": "assistant", "content": resp})

def main_app():
    sidebar()
    if not ensure_book_ready(): st.stop()
    tabs = st.tabs(["شات", "واجبات", "اختبارات"])
    with tabs[0]: chat_tab()
    with tabs[1]: homework_tab()
    with tabs[2]: quiz_tab()

if __name__ == "__main__":
    if st.session_state.user_data.get("logged_in"):
        main_app()
    else:
        login_page()
