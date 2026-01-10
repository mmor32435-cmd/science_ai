import streamlit as st

# ==========================================
# 1. إعدادات الصفحة
# ==========================================
st.set_page_config(page_title="AI Diagnosis Mode", page_icon="🛠️", layout="wide")

import time
import asyncio
import re
import random
import threading
from io import BytesIO
from datetime import datetime
import pytz

# المكتبات الخارجية
import google.generativeai as genai
import edge_tts
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder
from PIL import Image
import PyPDF2
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import gspread
import pandas as pd
import graphviz

# ==========================================
# 🎛️ الثوابت
# ==========================================
TEACHER_MASTER_KEY = "ADMIN_2024"
CONTROL_SHEET_NAME = "App_Control"
SESSION_DURATION_MINUTES = 60
DRIVE_FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "") 

DAILY_FACTS = [
    "هل تعلم؟ المخ يولد كهرباء تكفي لمصباح! 💡",
    "هل تعلم؟ العظام أقوى من الخرسانة بـ 4 مرات! 🦴",
]

# ==========================================
# 🛠️ الخدمات الخلفية
# ==========================================

# --- جداول جوجل ---
@st.cache_resource
def get_gspread_client():
    if "gcp_service_account" not in st.secrets: return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        scope = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds)
    except: return None

def get_sheet_data():
    client = get_gspread_client()
    if not client: return None
    try:
        sheet = client.open(CONTROL_SHEET_NAME)
        val = sheet.sheet1.acell('B1').value
        return str(val).strip()
    except: return None

# --- Google Drive ---
@st.cache_resource
def get_drive_service():
    if "gcp_service_account" not in st.secrets: return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/drive.readonly'])
        return build('drive', 'v3', credentials=creds)
    except: return None

def list_drive_files(service, folder_id):
    try:
        q = f"'{folder_id}' in parents and trashed = false"
        res = service.files().list(q=q, fields="files(id, name)").execute()
        return res.get('files', [])
    except: return []

def download_pdf_text(service, file_id):
    try:
        req = service.files().get_media(fileId=file_id)
        fh = BytesIO()
        downloader = MediaIoBaseDownload(fh, req)
        done = False
        while not done: _, done = downloader.next_chunk()
        fh.seek(0)
        reader = PyPDF2.PdfReader(fh)
        return "".join([p.extract_text() for p in reader.pages])
    except: return ""

# ==========================================
# 🔊 الصوت
# ==========================================
async def generate_audio_stream(text, voice_code):
    clean = re.sub(r'[*#_`\[\]()><=]', ' ', text)
    comm = edge_tts.Communicate(clean, voice_code, rate="-5%")
    mp3 = BytesIO()
    async for chunk in comm.stream():
        if chunk["type"] == "audio": mp3.write(chunk["data"])
    return mp3

def speech_to_text(audio_bytes, lang_code):
    r = sr.Recognizer()
    try:
        with sr.AudioFile(BytesIO(audio_bytes)) as source:
            r.adjust_for_ambient_noise(source, duration=0.5)
            return r.recognize_google(r.record(source), language=lang_code)
    except: return None

# ==========================================
# 🛑🛑🛑 الكود التشخيصي (Diagnostic) 🛑🛑🛑
# ==========================================
def get_working_model():
    st.markdown("### 🛠 بدء فحص الاتصال...")
    
    # 1. فحص وجود المفاتيح
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys:
        st.error("❌ لا توجد مفاتيح في secrets.toml!")
        return None
    else:
        st.success(f"✅ تم العثور على {len(keys)} مفاتيح API.")

    models = ['gemini-1.5-flash', 'gemini-pro']

    # 2. تجربة كل مفتاح وكل موديل
    for i, key in enumerate(keys):
        st.write(f"🔄 **تجربة المفتاح رقم {i+1}**...")
        genai.configure(api_key=key)
        
        for model_name in models:
            try:
                # محاولة الاتصال
                model = genai.GenerativeModel(model_name)
                response = model.generate_content("Hi")
                
                # إذا وصلنا هنا، يعني الاتصال نجح
                st.success(f"🚀 نجح الاتصال! (الموديل: {model_name})")
                return model
            
            except Exception as e:
                # طباعة الخطأ بالتفصيل الممل
                st.error(f"❌ فشل {model_name} مع المفتاح {i+1}.")
                st.code(f"نص الخطأ: {str(e)}")
                
    st.error("🛑 انتهت جميع المحاولات بالفشل. يرجى قراءة الأخطاء أعلاه وارسالها للمطور.")
    return None

def process_ai_response(user_text, input_type="text"):
    # دالة المعالجة تستدعي التشخيص
    try:
        model = get_working_model()
        if not model:
            return

        st.info("جاري توليد الإجابة...")
        base_prompt = "Answer in Arabic. Be concise."
        
        if input_type == "image":
             resp = model.generate_content([base_prompt, user_text[0], user_text[1]])
        else:
            resp = model.generate_content(f"{base_prompt}\nUser: {user_text}")
        
        st.markdown("---")
        st.write(resp.text)

    except Exception as e:
        st.error(f"خطأ أثناء التوليد: {e}")

# ==========================================
# 🎨 الواجهة (UI)
# ==========================================
def draw_header():
    st.title("🛠️ وضع التشخيص وكشف الأخطاء")

if "auth_status" not in st.session_state:
    st.session_state.update({
        "auth_status": False, "user_type": "none", "last_audio_bytes": None, "language": "العربية"
    })

# --- تسجيل الدخول ---
if not st.session_state.auth_status:
    draw_header()
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        with st.form("login"):
            code = st.text_input("الكود:", type="password")
            if st.form_submit_button("دخول"):
                if code == TEACHER_MASTER_KEY or code == get_sheet_data():
                    st.session_state.auth_status = True
                    st.rerun()
                else:
                    st.error("الكود خطأ")
    st.stop()

# --- التطبيق ---
draw_header()

st.warning("⚠️ هذا الإصدار مخصص لكشف سبب فشل الاتصال.")
st.write("جرب كتابة أي شيء في الأسفل لتبدأ عملية الفحص:")

q = st.text_input("اكتب رسالة تجريبية:")
if st.button("ابـدأ الفحـص"):
    if q:
        process_ai_response(q, "text")
    else:
        process_ai_response("Test", "text")
