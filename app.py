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
from langchain.chains.question_answering import load_qa_chain

# =========================
# Page config
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
.header-box { background: linear-gradient(90deg, #061a40 0%, #0353a4 50%, #006daa 100%); padding: 1.6rem; border-radius: 18px; text-align: center; margin-bottom: 1.2rem; color: white; }
.stButton>button { background: linear-gradient(90deg, #0353a4 0%, #061a40 100%) !important; color: #ffffff !important; border-radius: 12px; height: 50px; width: 100%; }
</style>
""", unsafe_allow_html=True)

# =========================
# Secrets
# =========================
TEACHER_NAME = st.secrets.get("TEACHER_NAME", "الأستاذ")
TEACHER_KEY = st.secrets.get("TEACHER_MASTER_KEY", "ADMIN")
SHEET_NAME = st.secrets.get("CONTROL_SHEET_NAME", "App_Control")
CONTROL_TAB_NAME = st.secrets.get("CONTROL_TAB_NAME", "")
FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "")
GOOGLE_API_KEYS = st.secrets.get("GOOGLE_API_KEYS", [])
if isinstance(GOOGLE_API_KEYS, str):
    GOOGLE_API_KEYS = [k.strip() for k in GOOGLE_API_KEYS.split(",") if k.strip()]

CHROMA_PERSIST_DIR = st.secrets.get("CHROMA_PERSIST_DIR", "./chroma_db")
os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)

# Constants
RESULTS_TAB_NAME = "Results"
ASSIGNMENTS_TAB_NAME = "Assignments"
SUBMISSIONS_TAB_NAME = "Submissions"
# =========================
# Session State & Maps
# =========================
def init_state():
    if "user_data" not in st.session_state:
        st.session_state.user_data = {"logged_in": False, "role": None, "name": ""}
    if "messages" not in st.session_state:
        st.session_state.messages = []
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

# Force initialization
init_state()

# --- هنا التعديل ليشمل كل المراحل ---
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
    if stage == "الثانوية":
        if grade == "الأول":
            return ["علوم متكاملة"]
        else:
            return ["كيمياء", "فيزياء", "أحياء"]
    return ["علوم"]

def is_english(lang_ui: str) -> bool:
    return "English" in (lang_ui or "")

def ocr_lang(lang_ui: str) -> str:
    return "eng" if is_english(lang_ui) else "ara"

def ui(lang_ui: str, ar: str, en: str) -> str:
    return en if is_english(lang_ui) else ar

def term_token(term: str) -> str:
    return "T2" if "الثاني" in term else "T1"

def drive_tokens(stage: str, grade: str, subject: str, term: str, lang_ui: str) -> Tuple[List[str], List[str]]:
    # خريطة تحويل الأسماء العربية إلى اختصارات الملفات
    stage_map = {"الابتدائية": "Grade", "الإعدادية": "Prep", "الثانوية": "Sec"}
    grade_map = {"الرابع": "4", "الخامس": "5", "السادس": "6", "الأول": "1", "الثاني": "2", "الثالث": "3"}
    
    # تحويل المواد
    subject_map = {
        "علوم": "Science",
        "علوم متكاملة": "Integrated",
        "كيمياء": "Chemistry",
        "فيزياء": "Physics",
        "أحياء": "Biology"
    }
    
    sub = subject_map.get(subject, subject)
    lang = "En" if is_english(lang_ui) else "Ar"
    
    # تكوين اسم الملف المتوقع: مثلاً Grade4_Science_T1_En
    sg = f"{stage_map.get(stage,'')}{grade_map.get(grade,'')}"
    
    # احتمالات البحث
    return [sg, sub, term_token(term), lang], [sg, sub, lang]

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()
    # =========================
# Services (Google, OCR, AI)
# =========================
@st.cache_resource
def get_credentials():
    if "gcp_service_account" not in st.secrets: return None
    try:
        creds = dict(st.secrets["gcp_service_account"])
        creds["private_key"] = creds["private_key"].replace("\\n", "\n")
        return service_account.Credentials.from_service_account_info(
            creds, 
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        )
    except: return None

@st.cache_resource
def get_gspread_client():
    c = get_credentials()
    return gspread.authorize(c) if c else None

def open_sheet():
    c = get_gspread_client()
    return c.open(SHEET_NAME) if c else None

def check_student_code(code: str) -> bool:
    try:
        sh = open_sheet()
        ws = sh.worksheet(CONTROL_TAB_NAME) if CONTROL_TAB_NAME else sh.sheet1
        return str(code).strip() == str(ws.acell("B1").value).strip()
    except: return False

@st.cache_resource
def get_drive_service():
    c = get_credentials()
    return build("drive", "v3", credentials=c) if c else None

def download_drive_pdf(file_id: str, name: str) -> Optional[str]:
    srv = get_drive_service()
    if not srv: return None
    safe = re.sub(r"[^a-zA-Z0-9]+", "_", name)
    path = os.path.join(CHROMA_PERSIST_DIR, "books_cache", f"{file_id}_{safe}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path): return path
    try:
        req = srv.files().get_media(fileId=file_id)
        with open(path, "wb") as f:
            d = MediaIoBaseDownload(f, req)
            done = False
            while not done: _, done = d.next_chunk()
        return path
    except: return None

def load_book(stage, grade, subject, term, lang):
    srv = get_drive_service()
    if not srv: return None
    q = f"'{FOLDER_ID}' in parents and mimeType='application/pdf'"
    try:
        results = srv.files().list(q=q, fields="files(id,name)").execute()
        files = results.get("files", [])
    except: return None
    
    t1, t2 = drive_tokens(stage, grade, subject, term, lang)
    
    # دالة مطابقة مرنة
    def match(tokens):
        for f in files:
            # نتأكد أن كل جزء من التوكن موجود في اسم الملف
            if all(t.lower() in f["name"].lower() for t in tokens if t): 
                return f
        return None
        
    f = match(t1) or match(t2)
    if not f: return None
    
    path = download_drive_pdf(f["id"], f["name"])
    return {"id": f["id"], "name": f["name"], "path": path} if path else None

@st.cache_data(show_spinner=False)
def ocr_pdf(path, lang):
    try:
        pages = convert_from_path(path, dpi=200)
        return "\n".join([pytesseract.image_to_string(p, lang=lang) for p in pages])
    except: return ""

def get_llm():
    k = random.choice(GOOGLE_API_KEYS) if GOOGLE_API_KEYS else None
    return ChatGoogleGenerativeAI(model="gemini-1.5-flash", google_api_key=k, temperature=0.2) if k else None

def ensure_book_ready():
    u = st.session_state.user_data
    sig = f"{u['stage']}|{u['grade']}|{u['subject']}|{u['lang']}"
    
    if st.session_state.book_data.get("base_sig") != sig:
        st.session_state.book_data = {"base_sig": sig}
        st.session_state.vector_store = None
    
    if not st.session_state.book_data.get("path"):
        d = load_book(u['stage'], u['grade'], u['subject'], u['term'], u['lang'])
        if not d:
            st.error(f"عذراً، لم يتم العثور على كتاب للمادة: {u['subject']} ({u['grade']}).")
            return False
        st.session_state.book_data.update(d)
    
    if not st.session_state.vector_store:
        with st.spinner("جاري تهيئة الكتاب للذكاء الاصطناعي..."):
            text = ocr_pdf(st.session_state.book_data["path"], ocr_lang(u['lang']))
            if not text: return False
            
            docs = [Document(page_content=c) for c in RecursiveCharacterTextSplitter(chunk_size=1500).split_text(text)]
            emb = GoogleGenerativeAIEmbeddings(model="models/embedding-001", google_api_key=random.choice(GOOGLE_API_KEYS))
            st.session_state.vector_store = Chroma.from_documents(docs, emb, persist_directory=os.path.join(CHROMA_PERSIST_DIR, "chroma_books", sig))
    return True

def run_chat(q):
    llm = get_llm()
    if not llm: return "No API Key"
    docs = st.session_state.vector_store.similarity_search(q, k=5)
    chain = load_qa_chain(llm, chain_type="stuff")
    return chain.invoke({"input_documents": docs, "question": q}, return_only_outputs=True).get("output_text", "")
   # =========================
# UI & Execution
# =========================
def login_page():
    st.markdown("### 🔐 تسجيل الدخول")
    with st.form("login"):
        name = st.text_input("الاسم")
        code = st.text_input("الكود", type="password")
        
        c1, c2 = st.columns(2)
        stage = c1.selectbox("المرحلة", STAGES)
        
        # تحديث الصفوف بناءً على المرحلة
        available_grades = GRADES.get(stage, [])
        grade = c1.selectbox("الصف", available_grades)
        
        term = c2.selectbox("الترم", TERMS)
        
        # تحديث المواد بناءً على المرحلة والصف
        avail_subs = subjects_for(stage, grade)
        subject = c2.selectbox("المادة", avail_subs)
        
        lang = st.selectbox("اللغة", LANGS)
        
        if st.form_submit_button("🚀 دخول"):
            if code == TEACHER_KEY or check_student_code(code):
                st.session_state.user_data = {
                    "logged_in": True,
                    "role": "Teacher" if code==TEACHER_KEY else "Student",
                    "name": name, "stage": stage, "grade": grade, 
                    "subject": subject, "term": term, "lang": lang
                }
                st.rerun()
            else:
                st.error("الكود غير صحيح")

def main_app():
    u = st.session_state.user_data
    with st.sidebar:
        st.success(f"مرحباً {u.get('name')}")
        st.info(f"{u['stage']} - {u['grade']}")
        if st.button("خروج"):
            st.session_state.user_data["logged_in"] = False
            st.rerun()
    
    if not ensure_book_ready():
        st.stop()
        
    st.markdown("### 💬 الشات")
    q = st.chat_input("سؤالك...")
    if q:
        with st.chat_message("user"): st.write(q)
        with st.chat_message("assistant"):
            with st.spinner("جاري البحث..."):
                res = run_chat(q)
                st.write(res)

if __name__ == "__main__":
    if "user_data" not in st.session_state:
        init_state()
        
    # استخدام .get لمنع الانهيار
    user_data = st.session_state.get("user_data", {})
    
    if user_data.get("logged_in", False):
        main_app()
    else:
        login_page() 
