import streamlit as st
import nest_asyncio

# تفعيل المعالجة المتزامنة
nest_asyncio.apply()

# ==========================================
# 1. إعدادات الصفحة
# ==========================================
st.set_page_config(page_title="المعلم الذكي", page_icon="🎓", layout="wide")

# CSS: إجبار اللون الأسود
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@500;800&display=swap');
    
    html, body, [class*="css"], p, h1, h2, h3 {
        font-family: 'Tajawal', sans-serif;
        color: #000000 !important;
    }
    
    .stApp {
        background-color: #ffffff;
    }

    .chat-user {
        background-color: #E3F2FD;
        padding: 10px;
        border-radius: 10px;
        margin: 5px 0;
        text-align: right;
        border: 1px solid #BBDEFB;
    }
    
    .chat-ai {
        background-color: #F5F5F5;
        padding: 10px;
        border-radius: 10px;
        margin: 5px 0;
        text-align: right;
        border: 1px solid #E0E0E0;
    }
</style>
""", unsafe_allow_html=True)

import time
import asyncio
import random
import threading
from io import BytesIO
from datetime import datetime
import pytz

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
DRIVE_FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "") 

DAILY_FACTS = [
    "هل تعلم؟ المخ لا يشعر بالألم!",
    "هل تعلم؟ الضوء أسرع شيء في الكون!",
]

RANKS = {
    0: "مبتدئ 🌱", 
    50: "مستكشف 🔭", 
    150: "عبقري 🏆"
}

# ==========================================
# 🛠️ الخدمات الخلفية (تم تقصير الأسطر)
# ==========================================

@st.cache_resource
def get_gspread_client():
    if "gcp_service_account" not in st.secrets:
        return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        scopes = ['https://www.googleapis.com/auth/drive', 
                  'https://www.googleapis.com/auth/spreadsheets']
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, 
            scopes=scopes
        )
        return gspread.authorize(creds)
    except:
        return None

def get_sheet_data():
    client = get_gspread_client()
    if not client: return None
    try:
        sheet = client.open(CONTROL_SHEET_NAME)
        val = sheet.sheet1.acell('B1').value
        return str(val).strip()
    except: return None

def _bg_task(task_type, data):
    # تم حل مشكلة الخطأ هنا بتقسيم الأسطر
    if "gcp_service_account" not in st.secrets:
        return
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        scopes = ['https://www.googleapis.com/auth/spreadsheets']
        
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, 
            scopes=scopes
        )
        
        client = gspread.authorize(creds)
        wb = client.open(CONTROL_SHEET_NAME)
        
        tz = pytz.timezone('Africa/Cairo')
        now_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

        if task_type == "login":
            try:
                sheet = wb.worksheet("Logs")
            except:
                sheet = wb.sheet1
            
            row = [now_str, data['type'], data['name'], data['details']]
            sheet.append_row(row)

        elif task_type == "activity":
            try:
                sheet = wb.worksheet("Activity")
            except:
                return
            
            txt_safe = str(data['text'])[:1000]
            row = [now_str, data['name'], data['input_type'], txt_safe]
            sheet.append_row(row)

        elif task_type == "xp":
            try:
                sheet = wb.worksheet("Gamification")
            except:
                return
            
            cell = sheet.find(data['name'])
            if cell:
                curr = int(sheet.cell(cell.row, 2).value or 0)
                sheet.update_cell(cell.row, 2, curr + data['points'])
            else:
                sheet.append_row([data['name'], data['points']])
    except:
        pass

def log_login(user, u_type, det):
    t = threading.Thread(target=_bg_task, args=("login", {'name': user, 'type': u_type, 'details': det}))
    t.start()

def log_activity(user, i_type, txt):
    t = threading.Thread(target=_bg_task, args=("activity", {'name': user, 'input_type': i_type, 'text': txt}))
    t.start()

def update_xp(user, pts):
    if 'current_xp' in st.session_state:
        st.session_state.current_xp += pts
    t = threading.Thread(target=_bg_task, args=("xp", {'name': user, 'points': pts}))
    t.start()

def get_current_xp(user):
    client = get_gspread_client()
    if not client: return 0
    try:
        sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
        cell = sheet.find(user)
        return int(sheet.cell(cell.row, 2).value or 0) if cell else 0
    except: return 0

# --- Google Drive ---
@st.cache_resource
def get_drive_service():
    if "gcp_service_account" not in st.secrets: return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        scopes = ['https://www.googleapis.com/auth/drive.readonly']
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, 
            scopes=scopes
        )
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
        while not done:
            _, done = downloader.next_chunk()
        fh.seek(0)
        reader = PyPDF2.PdfReader(fh)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        return text
    except: return ""

# ==========================================
# 🔊 الصوت
# ==========================================
def clean_text_for_audio(text):
    text = text.replace('*', ' ').replace('#', ' ')
    text = text.replace('-', ' ').replace('`', ' ')
    return text

async def edge_tts_generate(text, voice):
    clean = clean_text_for_audio(text)
    comm = edge_tts.Communicate(clean, voice, rate="-2%")
    mp3 = BytesIO()
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            mp3.write(chunk["data"])
    return mp3

def get_audio_bytes(text, lang="Arabic"):
    voice = "ar-EG-ShakirNeural" if lang == "Arabic" else "en-US-AndrewNeural"
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(edge_tts_generate(text, voice))
    except: return None

def speech_to_text(audio_bytes, lang_code):
    r = sr.Recognizer()
    try:
        with sr.AudioFile(BytesIO(audio_bytes)) as source:
            r.adjust_for_ambient_noise(source, duration=0.5)
            return r.recognize_google(r.record(source), language=lang_code)
    except: return None

# ==========================================
# 🧠 الذكاء الاصطناعي
# ==========================================
def get_working_model():
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys: return None
    random.shuffle(keys)
    models = ['gemini-2.5-flash', 'gemini-flash-latest', 'gemini-pro']
    
    for key in keys:
        genai.configure(api_key=key)
        for m in models:
            try:
                model = genai.GenerativeModel(m)
                model.generate_content("ping")
                return model
            except: continue
    return None

def get_rank_title(xp):
    title = "مبتدئ"
    for threshold, name in RANKS.items():
        if xp >= threshold: title = name
    return title

def process_ai_response(user_text, input_type="text"):
    with st.spinner("🧠 جاري المعالجة..."):
        try:
            log_activity(st.session_state.user_name, input_type, user_text)
            model = get_working_model()
            if not model:
                st.error("خطأ اتصال")
                return

            grade = st.session_state.get("student_grade", "General")
            lang = "Arabic" if st.session_state.language == "العربية" else "English"
            ref = st.session_state.get("ref_text", "")
            
            prompt = f"""
            Role: Science Tutor. Grade: {grade}.
            Context: {ref[:8000]}
            Instructions: Answer in {lang}. Clear text.
            No asterisks (*). No markdown symbols.
            """
            
            if input_type == "image":
                 resp = model.generate_content([prompt, user_text[0], user_text[1]])
            else:
                resp = model.generate_content(f"{prompt}\nStudent: {user_text}")
            
            full_text = resp.text
            
            # حفظ في السجل
            st.session_state.chat_history.insert(0, {
                "role": "ai", 
                "content": full_text
            })
            st.session_state.chat_history.insert(0, {
                "role": "user", 
                "content": user_text if isinstance(user_text, str) else "صورة/صوت"
            })
            
            st.rerun()

        except Exception as e:
            st.error(f"Error: {e}")

# ==========================================
# 🎨 التطبيق
# ==========================================

if "auth_status" not in st.session_state:
    st.session_state.auth_status = False
    st.session_state.user_name = "Guest"
    st.session_state.current_xp = 0
    st.session_state.language = "العربية"
    st.session_state.chat_history = []
    st.session_state.last_audio_bytes = None
    st.session_state.ref_text = ""

# الدخول
if not st.session_state.auth_status:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🎓 بوابة العلوم")
        st.info(random.choice(DAILY_FACTS))
        with st.form("login"):
            name = st.text_input("الاسم:")
            grade = st.selectbox("الصف:", ["الرابع", "الخامس", "السادس", "الإعدادي", "الثانوي"])
            code = st.text_input("الكود:", type="password")
            if st.form_submit_button("دخول"):
                db_pass = get_sheet_data()
                if code == TEACHER_MASTER_KEY or (db_pass and code == db_pass):
                    st.session_state.auth_status = True
                    st.session_state.user_name = name
                    st.session_state.student_grade = grade
                    st.session_state.user_type = "teacher" if code == TEACHER_MASTER_KEY else "student"
                    if st.session_state.user_type == "student":
                        st.session_state.current_xp = get_current_xp(name)
                        log_login(name, "student", grade)
                    st.rerun()
                else: st.error("الكود خطأ")
    st.stop()

# الشريط الجانبي
with st.sidebar:
    st.header(f"👤 {st.session_state.user_name}")
    st.success(f"الرتبة: {get_rank_title(st.session_state.current_xp)}")
    st.write(f"XP: {st.session_state.current_xp}")
    st.divider()
    st.session_state.language = st.radio("اللغة:", ["العربية", "English"])
    
    if DRIVE_FOLDER_ID:
        svc = get_drive_service()
        if svc:
            files = list_drive_files(svc, DRIVE_FOLDER_ID)
            if files:
                st.divider()
                bn = st.selectbox("الكتاب:", [f['name'] for f in files])
                if st.button("تفعيل"):
                    fid = next(f['id'] for f in files if f['name'] == bn)
                    with st.spinner("تحميل..."):
                        txt = download_pdf_text(svc, fid)
                        if txt: st.session_state.ref_text = txt; st.toast("تم!")

# المحتوى الرئيسي
st.title("🧬 المعلم الذكي")

t1, t2, t3, t4 = st.tabs(["🎙️ تحدث", "✍️ اكتب", "📸 صور", "🧠 تحدي"])

with t1:
    st.write("اضغط الميكروفون:")
    c1, c2 = st.columns([1, 4])
    with c1:
        aud = mic_recorder(start_prompt="🎤", stop_prompt="⏹️", key='mic')
    
    if aud and aud['bytes'] != st.session_state.last_audio_bytes:
        st.session_state.last_audio_bytes = aud['bytes']
        lang = "ar-EG" if st.session_state.language == "العربية" else "en-US"
        txt = speech_to_text(aud['bytes'], lang)
        if txt:
            st.success(f"سمعت: {txt}")
            update_xp(st.session_state.user_name, 10)
            process_ai_response(txt, "voice")
        else:
            st.error("لم 
