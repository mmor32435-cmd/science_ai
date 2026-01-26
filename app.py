import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import google.generativeai as genai
import gspread
from PIL import Image
import random
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder
import asyncio
import edge_tts
import tempfile
import os
import re
import io
import pdfplumber
import time
import traceback
import json

# =========================
# 1) إعدادات الصفحة
# =========================
st.set_page_config(
    page_title="المعلم العلمي | السيد البدوي",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =========================
# 2) تصميم الواجهة
# =========================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Cairo', sans-serif !important; direction: rtl; text-align: right; }
    .stApp { background-color: #f8f9fa; }
    div[data-baseweb="select"] * { background-color: transparent !important; border: none !important; color: #000000 !important; }
    div[data-baseweb="select"] > div { background-color: #ffffff !important; border: 2px solid #004e92 !important; border-radius: 8px !important; }
    ul[data-baseweb="menu"] { background-color: #ffffff !important; }
    li[data-baseweb="option"] { color: #000000 !important; }
    li[data-baseweb="option"]:hover { background-color: #e3f2fd !important; }
    .stTextInput input, .stTextArea textarea {
        background-color: #ffffff !important;
        color: #000000 !important;
        border: 2px solid #004e92 !important;
        border-radius: 8px !important;
    }
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
        padding: 2rem; border-radius: 15px; text-align: center; margin-bottom: 2rem;
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
# 3) إدارة الجلسة
# =========================
if 'user_data' not in st.session_state:
    st.session_state.user_data = {"logged_in": False, "role": None, "name": "", "grade": "", "stage": "", "lang": "العربية (علوم)"}
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'book_data' not in st.session_state:
    st.session_state.book_data = {"path": None, "text": None, "name": None}
if 'quiz_state' not in st.session_state:
    st.session_state.quiz_state = "off"  # off | asking | waiting_answer | correcting
if 'quiz_last_question' not in st.session_state:
    st.session_state.quiz_last_question = ""
if 'gemini_file_name' not in st.session_state:
    st.session_state.gemini_file_name = None
if 'gemini_model_name' not in st.session_state:
    st.session_state.gemini_model_name = None

# تشخيص
if 'debug_enabled' not in st.session_state:
    st.session_state.debug_enabled = True
if 'debug_log' not in st.session_state:
    st.session_state.debug_log = []  # قائمة رسائل

def dbg(event, data=None):
    if not st.session_state.debug_enabled:
        return
    rec = {"t": time.strftime("%H:%M:%S"), "event": event}
    if data is not None:
        rec["data"] = data
    st.session_state.debug_log.append(rec)
    st.session_state.debug_log = st.session_state.debug_log[-300:]

TEACHER_KEY = st.secrets.get("TEACHER_MASTER_KEY", "ADMIN")
SHEET_NAME = st.secrets.get("CONTROL_SHEET_NAME", "App_Control")
FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "")

# =========================
# 4) الاتصال والبيانات
# =========================
@st.cache_resource
def get_credentials():
    if "gcp_service_account" not in st.secrets:
        return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
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

def load_book_smartly(stage, grade, lang):
    creds = get_credentials()
    if not creds:
        return None
    try:
        target_tokens = []
        if "الثانوية" in stage:
            if "الأول" in grade: target_tokens.append("Sec1")
            elif "الثاني" in grade: target_tokens.append("Sec2")
            elif "الثالث" in grade: target_tokens.append("Sec3")
        elif "الإعدادية" in stage:
            if "الأول" in grade: target_tokens.append("Prep1")
            elif "الثاني" in grade: target_tokens.append("Prep2")
            elif "الثالث" in grade: target_tokens.append("Prep3")
        else:
            if "الرابع" in grade: target_tokens.append("Grade4")
            elif "الخامس" in grade: target_tokens.append("Grade5")
            elif "السادس" in grade: target_tokens.append("Grade6")

        lang_code = "Ar" if "العربية" in lang else "En"
        target_tokens.append(lang_code)

        service = build('drive', 'v3', credentials=creds)
        query = f"'{FOLDER_ID}' in parents and mimeType='application/pdf'"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        all_files = results.get('files', [])

        matched_file = None
        for f in all_files:
            if all(token.lower() in f['name'].lower() for token in target_tokens):
                matched_file = f
                break

        if not matched_file:
            dbg("book_not_found", {"stage": stage, "grade": grade, "lang": lang, "tokens": target_tokens, "files": [x["name"] for x in all_files]})
            return None

        request = service.files().get_media(fileId=matched_file['id'])
        file_path = os.path.join(tempfile.gettempdir(), matched_file['name'])

        with open(file_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()

        dbg("book_downloaded", {"name": matched_file["name"], "path": file_path, "size": os.path.getsize(file_path)})

        # استخراج نص محدود للفallback (قد يرجع 0 لو سكان)
        text_content = ""
        try:
            with pdfplumber.open(file_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    if i > 40:
                        break
                    extracted = page.extract_text()
                    if extracted:
                        text_content += extracted + "\n"
        except Exception as e:
            dbg("pdf_extract_error", str(e))

        dbg("book_text_stats", {"chars": len(text_content)})
        return {"path": file_path, "text": text_content, "name": matched_file['name']}
    except Exception as e:
        dbg("load_book_error", {"err": str(e), "trace": traceback.format_exc()})
        return None

# =========================
# 5) الصوت
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
# 6) Gemini helpers (تشخيصية)
# =========================
def list_available_models_for_key():
    """يرجع قائمة مختصرة بالموديلات الداعمة لـ generateContent."""
    try:
        ms = genai.list_models()
        out = []
        for m in ms:
            methods = getattr(m, "supported_generation_methods", []) or []
            if "generateContent" in methods:
                out.append(m.name)
        return out
    except Exception as e:
        dbg("list_models_error", {"err": str(e), "trace": traceback.format_exc()})
        return []

def pick_model_debug():
    """اختيار موديل صحيح من list_models بدل أسماء ثابتة."""
    if st.session_state.gemini_model_name:
        return st.session_state.gemini_model_name

    models = list_available_models_for_key()
    dbg("models_available", {"count": len(models), "models": models[:50]})  # أول 50 للاختصار

    # تفضيل flash ثم pro
    preferred = []
    for m in models:
        if "flash" in m.lower():
            preferred.append(m)
    for m in models:
        if "pro" in m.lower():
            preferred.append(m)
    for m in models:
        if m not in preferred:
            preferred.append(m)

    chosen = preferred[0] if preferred else None
    st.session_state.gemini_model_name = chosen
    dbg("model_chosen", {"model": chosen})
    return chosen

def ensure_book_loaded():
    u = st.session_state.user_data
    if st.session_state.book_data.get("name"):
        return True
    data = load_book_smartly(u['stage'], u['grade'], u['lang'])
    if not data:
        return False
    st.session_state.book_data = data
    st.session_state.gemini_file_name = None
    return True

def ensure_gemini_file_uploaded():
    """يرفع PDF مرة واحدة. لا يرجع الملف إلا إذا حالته صالحة."""
    book = st.session_state.book_data
    if not book.get("path") or not os.path.exists(book["path"]):
        dbg("gemini_file_missing_local", {"path": book.get("path")})
        return None

    try:
        # استعادة ملف سابق
        if st.session_state.gemini_file_name:
            f = genai.get_file(st.session_state.gemini_file_name)
            state = getattr(f, "state", None)
            dbg("gemini_get_file", {"name": f.name, "state": getattr(state, "name", None)})
            if state and state.name in ("FAILED",):
                st.session_state.gemini_file_name = None
                return None
            if state and state.name == "PROCESSING":
                return None
            return f

        # رفع جديد
        dbg("gemini_upload_start", {"display_name": book.get("name"), "path": book.get("path"), "size": os.path.getsize(book.get("path"))})
        uploaded = genai.upload_file(path=book["path"], display_name=book.get("name") or "book.pdf")

        # انتظر
        for i in range(60):
            f = genai.get_file(uploaded.name)
            state = getattr(f, "state", None)
            dbg("gemini_processing_poll", {"i": i, "file": f.name, "state": getattr(state, "name", None)})
            if not state:
                break
            if state.name == "PROCESSING":
                time.sleep(1)
                continue
            if state.name == "FAILED":
                return None
            st.session_state.gemini_file_name = f.name
            return f

        return None
    except Exception as e:
        dbg("gemini_upload_error", {"err": str(e), "trace": traceback.format_exc()})
        return None

def build_system_prompt(is_english: bool):
    if is_english:
        return (
            "You are Mr. El-Sayed El-Badawy, a science teacher. "
            "Use ONLY the provided textbook (PDF) as reference. "
            "Be concise. If the answer is not in the book, say you can't find it in the textbook."
        )
    else:
        return (
            "أنت الأستاذ السيد البدوي (معلم العلوم). "
            "استخدم فقط الكتاب المرفق كمرجع. "
            "كن مختصراً. إذا لم تجد الإجابة في الكتاب فقل: غير موجود في الكتاب."
        )

def get_ai_response(user_text, img_obj=None):
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys:
        return "⚠️ المفاتيح مفقودة."

    chosen_key = random.choice(keys)
    genai.configure(api_key=chosen_key)
    dbg("gemini_key_chosen", {"last4": chosen_key[-4:] if isinstance(chosen_key, str) else "?"})

    if not ensure_book_loaded():
        return "⚠️ لم يتم العثور على الكتاب."

    model_name = pick_model_debug()
    if not model_name:
        return "⚠️ لا توجد موديلات متاحة لهذا المفتاح تدعم generateContent."

    u = st.session_state.user_data
    is_english = "English" in u["lang"]
    sys_prompt = build_system_prompt(is_english)

    # منطق الاختبار
    quiz_state = st.session_state.quiz_state
    if quiz_state == "asking":
        user_text = (
            "Create ONE short quiz question from the textbook for my grade. Return only the question, no solution."
            if is_english else
            "كوّن سؤال اختبار واحد قصير من المنهج المناسب لصفّي. اكتب السؤال فقط بدون الحل."
        )
    elif quiz_state == "correcting":
        q = st.session_state.quiz_last_question.strip()
        a = user_text.strip()
        user_text = (
            f"Grade the student's answer based on the textbook.\nQuestion: {q}\nStudent answer: {a}\nGive a score out of 10 + 1-2 lines feedback."
            if is_english else
            f"صحح إجابة الطالب بالرجوع للكتاب.\nالسؤال: {q}\nإجابة الطالب: {a}\nأعط درجة من 10 مع تعليق مختصر (سطرين)."
        )

    # أثناء التشخيص: لا نرسل صورة
    img_obj = None

    file_part = ensure_gemini_file_uploaded()

    if file_part is not None:
        inputs = [sys_prompt, file_part, user_text]
        dbg("inputs_mode", {"mode": "pdf_file", "sys_len": len(sys_prompt), "user_len": len(user_text), "model": model_name})
