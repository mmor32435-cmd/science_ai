import streamlit as st
import os
import re
import io
import json
import time
import random
import asyncio
import tempfile
import traceback

from PIL import Image
import pdfplumber
import gspread
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder
import edge_tts

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import google.generativeai as genai

# OCR deps (تحتاج packages.txt + requirements.txt على Streamlit Cloud)
from pdf2image import convert_from_path
import pytesseract

# =========================
# 1) إعدادات الصفحة
# =========================
st.set_page_config(
    page_title="المعلم العلمي | السيد البدوي",
    # =========================
# 2) CSS آمن
# =========================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');

html, body, .stApp {
  font-family: 'Cairo', sans-serif !important;
  direction: rtl;
  text-align: right;
}
.stApp { background-color: #f8f9fa; }

.stTextInput input, .stTextArea textarea {
  background-color: #ffffff !important;
  color: #000000 !important;
  border: 2px solid #004e92 !important;
  border-radius: 8px !important;
}

div[data-baseweb="select"] > div {
  background-color: #ffffff !important;
  border: 2px solid #004e92 !important;
  border-radius: 8px !important;
}
ul[data-baseweb="menu"] { background-color: #ffffff !important; }
li[data-baseweb="option"] { color: #000000 !important; }
li[data-baseweb="option"]:hover { background-color: #e3f2fd !important; }

h1, h2, h3, h4, h5, p, label, span { color: #000000 !important; }

.stButton>button {
  background: linear-gradient(90deg, #004e92 0%, #000428 100%) !important;
  color: #ffffff !important;
  border: none;
  border-radius: 10px;
  height: 55px;
  width: 100%;
  font-size: 20px !important;
  font-weight: bold !important;
}

.header-box {
  background: linear-gradient(90deg, #000428 0%, #004e92 100%);
  padding: 2rem;
  border-radius: 15px;
  text-align: center;
  margin-bottom: 2rem;
  box-shadow: 0 4px 15px rgba(0,0,0,0.2);
}
.header-box h1, .header-box h3 { color: #ffffff !important; }

.stChatMessage {
  background-color: #ffffff !important;
  border: 1px solid #d1d1d1 !important;
  border-radius: 12px !important;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="header-box">
  <h1>الأستاذ / السيد البدوي</h1>
  <h3>المنصة التعليمية الذكية</h3>
</div>
""", unsafe_allow_html=True)

# =========================
# 3) Session state + Debug
# =========================
if "user_data" not in st.session_state:
    st.session_state.user_data = {
        "logged_in": False,
        "role": None,
        "name": "",
        "grade": "",
        "stage": "",
        "lang": "العربية (علوم)"
    }

if "messages" not in st.session_state:
    st.session_state.messages = []

if "book_data" not in st.session_state:
    st.session_state.book_data = {"path": None, "text": None, "name": None}

if "quiz_state" not in st.session_state:
    st.session_state.quiz_state = "off"  # off | asking | waiting_answer | correcting

if "quiz_last_question" not in st.session_state:
    st.session_state.quiz_last_question = ""

if "gemini_model_name" not in st.session_state:
    st.session_state.gemini_model_name = None

if "debug_enabled" not in st.session_state:
    st.session_state.debug_enabled = True

if "debug_log" not in st.session_state:
    st.session_state.debug_log = []

def dbg(event, data=None):
    if not st.session_state.debug_enabled:
        return
    rec = {"t": time.strftime("%H:%M:%S"), "event": event}
    if data is not None:
        rec["data"] = data
    st.session_state.debug_log.append(rec)
    st.session_state.debug_log = st.session_state.debug_log[-400:]

# =========================
# 4) Secrets
# =========================
TEACHER_KEY = st.secrets.get("TEACHER_MASTER_KEY", "ADMIN")
SHEET_NAME = st.secrets.get("CONTROL_SHEET_NAME", "App_Control")
FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "")

# =========================
# 5) Google creds + Sheets
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
            "https://www.googleapis.com/auth/drive",
        ]
        return service_account.Credentials.from_service_account_info(creds_dict, scopes=scopes)
    except Exception as e:
        dbg("creds_error", str(e))
        return None

def get_gspread_client():
    creds = get_credentials()
    return gspread.authorize(creds) if creds else None

def check_student_code(input_code):
    client = get_gspread_client()
    if not client:
        return False
    try:
        sh = client.open(SHEET_NAME)
        real_code = str(sh.sheet1.acell("B1").value).strip()
        return str(input_code).strip() == real_code
    except Exception as e:
        dbg("check_student_code_error", str(e))
        return False
       # =========================
# 6) تحميل الكتاب من Drive + استخراج نص مبدئي
# =========================
def load_book_smartly(stage, grade, lang):
    creds = get_credentials()
    if not creds:
        return None

    try:
        target_tokens = []

        if "الثانوية" in stage:
            if "الأول" in grade:
                target_tokens.append("Sec1")
            elif "الثاني" in grade:
                target_tokens.append("Sec2")
            elif "الثالث" in grade:
                target_tokens.append("Sec3")

        elif "الإعدادية" in stage:
            if "الأول" in grade:
                target_tokens.append("Prep1")
            elif "الثاني" in grade:
                target_tokens.append("Prep2")
            elif "الثالث" in grade:
                target_tokens.append("Prep3")

        else:
            if "الرابع" in grade:
                target_tokens.append("Grade4")
            elif "الخامس" in grade:
                target_tokens.append("Grade5")
            elif "السادس" in grade:
                target_tokens.append("Grade6")

        lang_code = "Ar" if "العربية" in lang else "En"
        target_tokens.append(lang_code)

        service = build("drive", "v3", credentials=creds)
        query = f"'{FOLDER_ID}' in parents and mimeType='application/pdf'"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        all_files = results.get("files", [])

        matched_file = None
        for f in all_files:
            name = f.get("name", "")
            if all(tok.lower() in name.lower() for tok in target_tokens):
                matched_file = f
                break

        if not matched_file:
            dbg("book_not_found", {"tokens": target_tokens, "files": [x.get("name") for x in all_files]})
            return None

        request = service.files().get_media(fileId=matched_file["id"])
        file_path = os.path.join(tempfile.gettempdir(), matched_file["name"])

        with open(file_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()

        dbg("book_downloaded", {"name": matched_file["name"], "path": file_path, "size": os.path.getsize(file_path)})

        text_content = ""
        try:
            with pdfplumber.open(file_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    if i > 25:
                        break
                    extracted = page.extract_text()
                    if extracted:
                        text_content += extracted + "\n"
        except Exception as e:
            dbg("pdf_extract_error", str(e))

        dbg("book_text_stats", {"chars": len(text_content)})
        return {"path": file_path, "text": text_content, "name": matched_file["name"]}

    except Exception as e:
        dbg("load_book_error", {"err": str(e), "trace": traceback.format_exc()})
        return None

# =========================
# 7) OCR (مُحسّن للتشخيص)
# =========================
@st.cache_data(show_spinner=False)
def ocr_pdf_to_text(pdf_path: str, max_pages: int = 8, lang: str = "ara"):
    try:
        pages = convert_from_path(pdf_path, dpi=200, first_page=1, last_page=max_pages)
        out = []
        for idx, im in enumerate(pages, start=1):
            txt = pytesseract.image_to_string(im, lang=lang)
            out.append(f"\n--- PAGE {idx} ---\n{txt}")
        return "\n".join(out)
    except Exception as e:
        return f"__OCR_ERROR__:{type(e).__name__}:{e}"

def ensure_book_loaded_and_text_ready():
    u = st.session_state.user_data

    if not st.session_state.book_data.get("name"):
        data = load_book_smartly(u["stage"], u["grade"], u["lang"])
        if not data:
            return False
        st.session_state.book_data = data

    # لو النص صفر → OCR
    if not (st.session_state.book_data.get("text") or "").strip():
        pdf_path = st.session_state.book_data.get("path")
        if pdf_path and os.path.exists(pdf_path):
            with st.spinner("الكتاب يبدو مُصوَّراً.. جاري OCR لصفحات محدودة (قد يستغرق وقتاً)..."):
                ocr_lang = "eng" if "English" in u["lang"] else "ara"
                ocr_text = ocr_pdf_to_text(pdf_path, max_pages=8, lang=ocr_lang)
                dbg("ocr_done", {"len": len(ocr_text), "is_error": "__OCR_ERROR__" in ocr_text})
                dbg("ocr_text_preview", {"text": ocr_text[:400]})
                if "__OCR_ERROR__" not in ocr_text:
                    st.session_state.book_data["text"] = ocr_text

    return True

# =========================
# 8) Gemini (نصي فقط لتفادي 400 الخاص بالملفات)
# =========================
def list_models_supporting_generate():
    try:
        ms = genai.list_models()
        valid = []
        for m in ms:
            methods = getattr(m, "supported_generation_methods", []) or []
            if "generateContent" in methods:
                valid.append(m.name)
        return valid
    except Exception as e:
        dbg("list_models_error", {"err": str(e), "trace": traceback.format_exc()})
        return []

def pick_model():
    if st.session_state.gemini_model_name:
        return st.session_state.gemini_model_name

    models = list_models_supporting_generate()
    dbg("models_available", {"count": len(models), "models": models[:50]})

    preferred = []
    for m in models:
        if "latest" in m.lower():
            preferred.append(m)
    for m in models:
        if "flash" in m.lower() and m not in preferred:
            preferred.append(m)
    for m in models:
        if "pro" in m.lower() and m not in preferred:
            preferred.append(m)
    for m in models:
        if m not in preferred:
            preferred.append(m)

    chosen =
  # =========================
# 9) صوت (STT/TTS)
# =========================
def clean_text_for_speech(text):
    return re.sub(r'[\*\#\-\_]', '', text)

def speech_to_text(audio_bytes, lang_ui):
    r = sr.Recognizer()
    try:
        audio_io = io.BytesIO(audio_bytes)
        with sr.AudioFile(audio_io) as source:
            audio_data = r.record(source)
            code = "en-US" if "English" in lang_ui else "ar-EG"
            return r.recognize_google(audio_data, language=code)
    except Exception as e:
        dbg("stt_error", str(e))
        return None

async def generate_speech_async(text, lang_ui):
    cleaned = clean_text_for_speech(text)
    voice = "en-US-ChristopherNeural" if "English" in lang_ui else "ar-EG-ShakirNeural"
    communicate = edge_tts.Communicate(cleaned, voice)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
        await communicate.save(tmp_file.name)
        return tmp_file.name

def text_to_speech_pro(text, lang_ui):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(generate_speech_async(text, lang_ui))
    except Exception as e:
        dbg("tts_error", str(e))
        return None

# =========================
# 10) UI
# =========================
def celebrate_success():
    st.balloons()
    st.toast("أحسنت!", icon="🎉")

def login_page():
    st.markdown("### 🔐 تسجيل الدخول")
    with st.form("login"):
        name = st.text_input("الاسم الثلاثي")
        code = st.text_input("الكود السري", type="password")
        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            stage = st.selectbox("المرحلة", ["الابتدائية", "الإعدادية", "الثانوية"])
            lang = st.selectbox("اللغة", ["العربية (علوم)", "English (Science)"])
        with col2:
            grade = st.selectbox("الصف الدراسي", [
                "الرابع", "الخامس", "السادس", "الأول", "الثاني", "الثالث"
            ])

        submit = st.form_submit_button("🚀 بدء التعلم")
        if submit:
            if code == TEACHER_KEY:
                st.session_state.user_data.update({"logged_in": True, "role": "Teacher", "name": name})
                st.rerun()
            elif check_student_code(code):
                st.session_state.user_data.update({
                    "logged_in": True,
                    "role": "Student",
                    "name": name,
                    "stage": stage,
                    "grade": grade,
                    "lang": lang
                })
                st.session_state.book_data = {"path": None, "text": None, "name": None}
                st.session_state.gemini_model_name = None
                st.session_state.messages = []
                st.session_state.quiz_state = "off"
                st.session_state.quiz_last_question = ""
                st.session_state.debug_log = []
                st.rerun()
            else:
                st.error("❌ الكود غير صحيح")

def main_app():
    with st.sidebar:
        st.success(f"مرحباً: {st.session_state.user_data['name']}")
        st.info(f"{st.session_state.user_data.get('grade','')} | {st.session_state.user_data.get('lang','')}")
        st.write("---")

        st.session_state.debug_enabled = st.checkbox("DEBUG", value=True)

        colA, colB = st.columns(2)
        with colA:
            if st.button("مسح سجل DEBUG"):
                st.session_state.debug_log = []
                st.rerun()
        with colB:
            if st.button("تصفير اختيار الموديل"):
                st.session_state.gemini_model_name = None
                st.rerun()

        with st.expander("سجل DEBUG"):
            st.code(json.dumps(st.session_state.debug_log, ensure_ascii=False, indent=2))

        st.write("---")
        if st.button("📝 ابدأ اختبار"):
            st.session_state.quiz_state = "asking"
            st.session_state.quiz_last_question = ""
            st.session_state.messages.append({"role": "user", "content": "ابدأ اختبار"})
            with st.spinner("جاري إعداد السؤال..."):
                resp = get_ai_response("ابدأ اختبار")
                st.session_state.messages.append({"role": "assistant", "content": resp})  
    
