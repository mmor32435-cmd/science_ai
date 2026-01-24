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
    page_title="المعلم العلمي | السيد البدوي",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# 2. تصميم آمن وواضح (Safe & Clear UI)
# ==========================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
    
    /* توحيد الخط والاتجاه */
    html, body, [class*="css"] {
        font-family: 'Cairo', sans-serif;
        direction: rtl;
        text-align: right;
    }
    
    /* خلفية التطبيق رمادية فاتحة جداً لتمييز العناصر */
    .stApp {
        background-color: #f7f9fc;
    }
    
    /* --- تنسيق حقول الإدخال لتكون ظاهرة بوضوح --- */
    /* حدود زرقاء، خلفية بيضاء، نص أسود */
    .stTextInput input, .stSelectbox div, .stTextArea textarea {
        background-color: #ffffff !important;
        color: #000000 !important;
        border: 1px solid #ced4da !important;
        border-radius: 8px !important;
    }
    
    /* عناوين الحقول (Label) */
    .stTextInput label, .stSelectbox label {
        color: #000000 !important;
        font-weight: bold !important;
        font-size: 16px !important;
    }

    /* --- تنسيق الأزرار --- */
    .stButton>button {
        background-color: #2c3e50; /* لون كحلي غامق */
        color: #ffffff !important;
        border-radius: 8px;
        height: 50px;
        width: 100%;
        font-size: 18px !important;
        font-weight: bold !important;
        border: none;
    }
    .stButton>button:hover {
        background-color: #34495e;
    }

    /* --- تنسيق العنوان الرئيسي --- */
    .header-box {
        background: linear-gradient(135deg, #000428 0%, #004e92 100%);
        padding: 2rem;
        border-radius: 15px;
        text-align: center;
        margin-bottom: 2rem;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .header-box h1, .header-box h3 {
        color: #ffffff !important;
        margin: 0;
    }
    
    /* --- تنسيق رسائل المحادثة --- */
    .stChatMessage {
        background-color: #ffffff !important;
        border: 1px solid #e1e4e8 !important;
        border-radius: 12px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
    }
    
    /* النصوص داخل الشات */
    .stChatMessage p {
        color: #000000 !important;
        font-size: 17px !important;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="header-box">
    <h1>الأستاذ / السيد البدوي</h1>
    <h3>المنصة التعليمية الذكية (ابتدائي - إعدادي - ثانوي)</h3>
</div>
""", unsafe_allow_html=True)

# ==========================================
# 3. إدارة الجلسة
# ==========================================
if 'user_data' not in st.session_state:
    st.session_state.user_data = {"logged_in": False, "role": None, "name": "", "grade": "", "stage": "", "lang": ""}
if 'messages' not in st.session_state: st.session_state.messages = []
if 'book_content' not in st.session_state: st.session_state.book_content = ""

# ==========================================
# 4. الاتصال والبيانات
# ==========================================
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
        # تحديد اسم الملف بدقة بناءً على المرحلة
        file_prefix = ""
        if "الثانوية" in stage:
            mapping = {"الأول": "Sec1", "الثاني": "Sec2", "الثالث": "Sec3"}
            file_prefix = mapping.get(grade, "Sec1")
        elif "الإعدادية" in stage:
            mapping = {"الأول": "Prep1", "الثاني": "Prep2", "الثالث": "Prep3"}
            file_prefix = mapping.get(grade, "Prep1")
        else: # ابتدائي
            mapping = {"الرابع": "Grade4", "الخامس": "Grade5", "السادس": "Grade6"}
            file_prefix = mapping.get(grade, "Grade4")
            
        lang_code = "Ar" if "العربية" in lang else "En"
        expected_name = f"{file_prefix}_{lang_code}"
        
        service = build('drive', 'v3', credentials=creds)
        # البحث عن الملف
        results = service.files().list(q=f"name contains '{expected_name}' and mimeType='application/pdf'", fields="files(id, name)").execute()
        files = results.get('files', [])
        
        if not files: return None
        
        # تحميل وقراءة
        request = service.files().get_media(fileId=files[0]['id'])
        file_stream = io.BytesIO()
        downloader = MediaIoBaseDownload(file_stream, request)
        done = False
        while done is False: status, done = downloader.next_chunk()
        
        file_stream.seek(0)
        pdf_reader = PyPDF2.PdfReader(file_stream)
        text = ""
        # قراءة أول 60 صفحة لعدم التحميل الزائد
        for page in pdf_reader.pages[:60]: text += page.extract_text() + "\n"
        return text
    except: return None

# ==========================================
# 5. الصوت والميكروفون
# ==========================================
def clean_text_for_speech(text):
    text = re.sub(r'[\*\#\-\_]', '', text)
    return text
