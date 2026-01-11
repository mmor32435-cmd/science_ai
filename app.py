import streamlit as st
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
# 1. إعدادات الصفحة
# ==========================================
st.set_page_config(
    page_title="AI Science Tutor Pro",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# 🎛️ الثوابت والإعدادات
# ==========================================
TEACHER_MASTER_KEY = "ADMIN_2024"
CONTROL_SHEET_NAME = "App_Control" # تأكد من أن هذا الاسم يطابق اسم ملف جوجل شيت
DRIVE_FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "") 

DAILY_FACTS = [
    "هل تعلم؟ المخ يولد كهرباء تكفي لمصباح! 💡",
    "هل تعلم؟ العظام أقوى من الخرسانة بـ 4 مرات! 🦴",
    "هل تعلم؟ الأخطبوط لديه 3 قلوب! 🐙",
    "هل تعلم؟ العسل لا يفسد أبداً! 🍯",
    "هل تعلم؟ سرعة الضوء هي 300,000 كم/ثانية! ⚡",
]

# ==========================================
# 🛠️ الخدمات الخلفية (Backend Services)
# ==========================================

# --- 1. الاتصال بجداول جوجل (Sheets) ---
@st.cache_resource
def get_gspread_client():
    if "gcp_service_account" not in st.secrets:
        return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        scope = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds)
    except Exception as e:
        print(f"Sheet Error: {e}")
        return None

def get_sheet_data():
    client = get_gspread_client()
    if not client: return None
    try:
        sheet = client.open(CONTROL_SHEET_NAME)
        # نفترض أن كلمة المرور في الخلية B1
        val = sheet.sheet1.acell('B1').value
        return str(val).strip()
    except Exception:
        return None

# --- 2. نظام التسجيل (Logging) والتلعيب (Gamification) ---
def _bg_task(task_type, data):
    """وظيفة تعمل في الخلفية لتحديث الشيت دون تعطيل الواجهة"""
    if "gcp_service_account" not in st.secrets: return

    try:
        client = get_gspread_client()
        if not client: return
        wb = client.open(CONTROL_SHEET_NAME)
        
        tz = pytz.timezone('Africa/Cairo')
        now_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

        if task_type == "login":
            try: sheet = wb.worksheet("Logs")
            except: sheet = wb.add_worksheet("Logs", 1000, 5)
            sheet.append_row([now_str, data['type'], data['name'], data['details']])

        elif task_type == "activity":
            try: sheet = wb.worksheet("Activity")
            except: sheet = wb.add_worksheet("Activity", 1000, 5)
            clean_text = str(data['text'])[:1000]
            sheet.append_row([now_str, data['name'], data['input_type'], clean_text])

        elif task_type == "xp":
            try: sheet = wb.worksheet("Gamification")
            except: sheet = wb.add_worksheet("Gamification", 1000, 3)
            
            try:
                cell = sheet.find(data['name'])
                if cell:
                    current_val = sheet.cell(cell.row, 2).value
                    current_xp = int(current_val) if current_val else 0
                    sheet.update_cell(cell.row, 2, current_xp + data['points'])
                else:
                    sheet.append_row([data['name'], data['points']])
            except:
                sheet.append_row([data['name'], data['points']])

    except Exception:
        pass

def log_login(user_name, user_type, details):
    threading.Thread(target=_bg_task, args=("login", {'name': user_name, 'type': user_type, 'details': details})).start()

def log_activity(user_name, input_type, text):
    threading.Thread(target=_bg_task, args=("activity", {'name': user_name, 'input_type': input_type, 'text': text})).start()

def update_xp(user_name, points):
    if 'current_xp' in st.session_state:
        st.session_state.current_xp += points
    threading.Thread(target=_bg_task, args=("xp", {'name': user_name, 'points': points})).start()

def get_current_xp(user_name):
    client = get_gspread_client()
    if not client: return 0
    try:
        sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
        cell = sheet.find(user_name)
        if cell:
            val = sheet.cell(cell.row, 2).value
            return int(val) if val else 0
    except:
        return 0
    return 0

def get_leaderboard():
    client = get_gspread_client()
    if not client: return []
    try:
        sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        if df.empty: return []
        if 'XP' not in df.columns:
            df.columns = ['Student_Name', 'XP']
        
        df['XP'] = pd.to_numeric(df['XP'], errors='coerce').fillna(0)
        return df.sort_values(by='XP', ascending=False).head(5).to_dict('records')
    except Exception:
        return []

# --- 3. خدمات جوجل درايف (Drive) ---
@st.cache_resource
def get_drive_service():
    if "gcp_service_account" not in st.secrets: return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/drive.readonly'])
        return build('drive', 'v3', credentials=creds)
    except Exception:
        return None

def list_drive_files(service, folder_id):
    try:
        q = f"'{folder_id}' in parents and trashed = false and mimeType = 'application/pdf'"
        res = service.files().list(q=q, fields="files(id, name)").execute()
        return res.get('files', [])
    except Exception:
        return []

def download_pdf_text(service, file_id):
    try:
        req = service.files().get_media(fileId=file_id)
        fh = BytesIO()
        downloader = MediaIoBaseDownload(fh, req)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        fh.seek(0)
        reader = PyPDF2.PdfReader(fh)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    except Exception:
        return ""

# ==========================================
# 🔊 معالجة الصوت (Audio Processing) - تم التحديث ✅
# ==========================================
async def generate_audio_stream(text, voice_code):
    """
    توليد الصوت للنص الكامل مع تنظيف الرموز
    """
    # 1. إزالة كتل الأكواد البرمجية الطويلة لتجنب قراءتها
    clean = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    
    # 2. إزالة رموز الماركداون والرموز الخاصة (*, #, _, ~, >, etc)
    clean = re.sub(r'[*#_`\[\]()><=~-]', ' ', clean)
    
    # 3. إزالة الروابط
    clean = re.sub(r'http\S+', ' ', clean)
    
    # 4. توحيد المسافات
    clean = " ".join(clean.split())
    
    if not clean: return None

    # إرسال النص كاملاً
    comm = edge_tts.Communicate(clean, voice_code, rate="-2%")
    mp3 = BytesIO()
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            mp3.write(chunk["data"])
    return mp3

def speech_to_text(audio_bytes, lang_code):
    r = sr.Recognizer()
    try:
        with sr.AudioFile(BytesIO(audio_bytes)) as source:
            r.adjust_for_ambient_noise(source, duration=0.5)
            audio_data = r.record(source)
            return r.recognize_google(audio_data, language=lang_code)
    except Exception:
        return None

# ==========================================
# 🧠 الذكاء الاصطناعي (Gemini AI)
# ==========================================
def get_working_model():
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys: return None

    random.shuffle(keys)
    
    # قائمة الموديلات بالأولوية
    models_to_try = [
        'gemini-1.5-flash',
        'gemini-2.0-flash-exp',
        'gemini-1.5-pro',
        'gemini-pro'
    ]

    for key in keys:
        genai.configure(api_key=key)
        for model_name in models_to_try:
            try:
                model = genai.GenerativeModel(model_name)
                model.generate_content("test")
                return model
            except Exception:
                continue
    return None

def process_ai_response(user_input, input_type="text"):
    """المعالج الرئيسي للذكاء الاصطناعي"""
    
    user_text_log = user_input if input_type != "image" else "Image Analysis Request"
    log_activity(st.session_state.user_name, input_type, user_text_log)
    
    with st.spinner("🧠 جاري التفكير..."):
        try:
            model = get_working_model()
            if not model:
                st.error("⚠️ خطأ في الاتصال بالذكاء الاصطناعي.")
                return

            lang = st.session_state.language
            ref_text = st.session_state.get("ref_text", "")
            grade = st.session_state.get("student_grade", "General")
            
            lang_instruction = "Arabic" if lang == "العربية" else "English"
            
            base_prompt = f"""
            Act as an expert Science Tutor for grade {grade}.
            Answer in {lang_instruction}. Be encouraging, clear, and educational.
            Use emojis to make it fun.
            
            Context from textbook:
            {ref_text[:8000]} 
            
            Format instructions:
            - If a diagram/process is explained, you CAN optionally provide a Graphviz DOT code inside a block starting with ```dot and ending with ```.
            - Keep the explanation simple.
            """
            
            response = 
