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
import PyPDF2

# ==========================================
# 1. إعدادات الصفحة
# ==========================================
st.set_page_config(
    page_title="المعلم العلمي",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# 2. الحل العبقري لمشكلة الاختفاء (CSS Reset)
# ==========================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
    
    /* 1. إجبار الخط العربي */
    html, body, [class*="css"] {
        font-family: 'Cairo', sans-serif !important;
        direction: rtl;
        text-align: right;
    }

    /* 2. إجبار الخلفية البيضاء تماماً */
    .stApp {
        background-color: #ffffff !important;
    }

    /* 3. الكود النووي: أي نص في التطبيق يجب أن يكون أسود */
    * {
        color: #000000 !important;
        --text-color: #000000 !important;
    }

    /* 4. تنسيق حقول الإدخال لتكون واضحة جداً */
    .stTextInput input, .stSelectbox div, .stTextArea textarea {
        background-color: #f0f2f6 !important; /* رمادي فاتح جداً */
        border: 2px solid #004e92 !important; /* حدود زرقاء */
        color: #000000 !important;
        font-weight: bold !important;
    }
    
    /* 5. الأزرار */
    .stButton>button {
        background-color: #004e92 !important;
        color: #ffffff !important; /* استثناء النص الأبيض للأزرار فقط */
        border-radius: 8px;
        height: 50px;
        font-size: 18px !important;
    }

    /* 6. رسائل الشات */
    .stChatMessage {
        background-color: #f9f9f9 !important;
        border: 1px solid #ccc !important;
    }
</style>
""", unsafe_allow_html=True)

# العنوان
st.title("🧬 الأستاذ / السيد البدوي")
st.markdown("### المنصة التعليمية الذكية")
st.markdown("---")

# ==========================================
# 3. إدارة الجلسة والاتصال (Backend)
# ==========================================
if 'user_data' not in st.session_state:
    st.session_state.user_data = {"logged_in": False, "role": None, "name": "", "grade": "", "stage": "", "lang": ""}
if 'messages' not in st.session_state: st.session_state.messages = []
if 'book_content' not in st.session_state: st.session_state.book_content = ""

TEACHER_KEY = st.secrets.get("TEACHER_MASTER_KEY", "ADMIN")
SHEET_NAME = st.secrets.get("CONTROL_SHEET_NAME", "App_Control")

@st.cache_resource
def get_credentials():
    if "gcp_service_account" not in st.secrets: return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        return service_account.Credentials.from_service_account_info(creds_dict, scopes=scopes)
    except: return None

def get_gspread_client():
    creds = get_credentials()
    return gspread.authorize(creds) if creds else None

def check_student_code(input_code):
    client = get_gspread_client()
    if not client: return False
    try:
        sh = client.open(SHEET_NAME)
        real_code = str(sh.sheet1.acell("B1").value).strip()
        return str(input_code).strip() == real_code
    except: return False

@st.cache_resource
def get_book_text_from_drive(stage, grade, lang):
    creds = get_credentials()
    if not creds: return None
    try:
        file_prefix = ""
        if "الثانوية" in stage:
            mapping = {"الأول": "Sec1", "الثاني": "Sec2", "الثالث": "Sec3"}
            file_prefix = mapping.get(grade, "Sec1")
        elif "الإعدادية" in stage:
            mapping = {"الأول": "Prep1", "الثاني": "Prep2", "الثالث": "Prep3"}
            file_prefix = mapping.get(grade, "Prep1")
        else: 
            mapping = {"الرابع": "Grade4", "الخامس": "Grade5", "السادس": "Grade6"}
            file_prefix = mapping.get(grade, "Grade4")
            
        lang_code = "Ar" if "العربية" in lang else "En"
        expected_name = f"{file_prefix}_{lang_code}"
        
        service = build('drive', 'v3', credentials=creds)
        results = service.files().list(q=f"name contains '{expected_name}' and mimeType='application/pdf'", fields="files(id, name)").execute()
        files = results.get('files', [])
        
        if not files: return None
        request = service.files().get_media(fileId=files[0]['id'])
        file_stream = io.BytesIO()
        downloader = MediaIoBaseDownload(file_stream, request)
        done = False
        while done is False: status, done = downloader.next_chunk()
        file_stream.seek(0)
        pdf_reader = PyPDF2.PdfReader(file_stream)
        text = ""
        for page in pdf_reader.pages[:50]: text += page.extract_text() + "\n"
        return text
    except: return None

# ==========================================
# 4. الصوت والميكروفون
# ==========================================
def clean_text_for_speech(text):
    text = re.sub(r'[\*\#\-\_]', '', text)
    return text

def speech_to_text(audio_bytes):
    r = sr.Recognizer()
    try:
        audio_io = io.BytesIO(audio_bytes)
        with sr.AudioFile(audio_io) as source:
            audio_data = r.record(source)
            text = r.recognize_google(audio_data, language="ar-EG")
            return text
    except: return None

async def generate_speech_async(text, voice="ar-EG-ShakirNeural"):
    cleaned = clean_text_for_speech(text)
    communicate = edge_tts.Communicate(cleaned, voice)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
        await communicate.save(tmp_file.name)
        return tmp_file.name

def text_to_speech_pro(text):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(generate_speech_async(text))
    except: return None

# ==========================================
# 5. الذكاء الاصطناعي
# ==========================================
def get_dynamic_model():
    try:
        all_models = genai.list_models()
        valid_models = [m.name for m in all_models if 'generateContent' in m.supported_generation_methods]
        if not valid_models: return None
        for m in valid_models:
            if 'flash' in m.lower(): return m
        for m in valid_models:
            if 'pro' in m.lower(): return m
        return valid_models[0]
    except: return None

def get_ai_response(user_text, img_obj=None, is_quiz_mode=False):
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys: return "⚠️ المفاتيح مفقودة."
    genai.configure(api_key=random.choice(keys))
    
    model_name = get_dynamic_model()
    if not model_name: return "عذراً، لا توجد نماذج متاحة."
    
    u = st.session_state.user_data
    if not st.session_state.book_content:
        book_text = get_book_text_from_drive(u['stage'], u['grade'], 
