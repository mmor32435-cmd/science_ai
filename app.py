import streamlit as st
import nest_asyncio

# تفعيل المعالجة المتزامنة
nest_asyncio.apply()

# ==========================================
# 1. إعدادات الصفحة (تصميم نظيف جداً)
# ==========================================
st.set_page_config(page_title="المعلم الذكي", page_icon="🎓", layout="wide")

# CSS بسيط فقط لضبط الخط العربي (بدون خلفيات)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@400;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Tajawal', sans-serif;
    }
    
    /* تكبير حجم الخط للقراءة المريحة */
    p, .stMarkdown {
        font-size: 1.2rem !important;
        line-height: 1.8 !important;
    }
</style>
""", unsafe_allow_html=True)

import time
import asyncio
import re
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
    "هل تعلم؟ الضوء يستغرق 8 دقائق ليصل من الشمس للأرض!",
    "هل تعلم؟ قلبك ينبض 100 ألف مرة في اليوم!",
]

RANKS = {
    0: "مبتدئ 🌱", 50: "مستكشف 🔭", 150: "مبتكر 💡", 300: "عالم 🔬", 500: "عبقري 🏆"
}

# ==========================================
# 🛠️ الخدمات الخلفية
# ==========================================

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
        return str(client.open(CONTROL_SHEET_NAME).sheet1.acell('B1').value).strip()
    except: return None

def _bg_task(task_type, data):
    if "gcp_service_account" not in st.secrets: return
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        client = gspread.authorize(service_account.Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets']))
        wb = client.open(CONTROL_SHEET_NAME)
        tz = pytz.timezone('Africa/Cairo')
        now_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

        if task_type == "login":
            try: sheet = wb.worksheet("Logs")
            except: sheet = wb.sheet1
            sheet.append_row([now_str, data['type'], data['name'], data['details']])
        elif task_type == "activity":
            try: sheet = wb.worksheet("Activity")
            except: return
            sheet.append_row([now_str, data['name'], data['input_type'], str(data['text'])[:1000]])
        elif task_type == "xp":
            try: sheet = wb.worksheet("Gamification")
            except: return
            cell = sheet.find(data['name'])
            if cell:
                curr = int(sheet.cell(cell.row, 2).value or 0)
                sheet.update_cell(cell.row, 2, curr + data['points'])
            else:
                sheet.append_row([data['name'], data['points']])
    except: pass

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
        return int(sheet.cell(cell.row, 2).value or 0) if cell else 0
    except: return 0

def get_leaderboard():
    client = get_gspread_client()
    if not client: return []
    try:
        sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
        df = pd.DataFrame(sheet.get_all_records())
        if df.empty: return []
        df['XP'] = pd.to_numeric(df['XP'], errors='coerce').fillna(0)
        return df.sort_values(by='XP', ascending=False).head(5).to_dict('records')
    except: return []

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
        res = service.files().list(q=f"'{folder_id}' in parents and trashed = false", fields="files(id, name)").execute()
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
# 🔊 الصوت (التنظيف + الإصلاح)
# ==========================================
def clean_text_for_audio(text):
    # إزالة الرموز الخاصة فقط والإبقاء على الحروف
    clean = ""
    for char in text:
        if char.isalnum() or char.isspace() or char in ".,?!،؟":
            clean += char
    return clean

async def edge_tts_generate(text, voice):
    clean_text = clean_text_for_audio(text)
    communicate = edge_tts.Communicate(clean_text, voice, rate="-2%")
    mp3 = BytesIO()
    async for chunk in communicate.stream():
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
        # استخدام BytesIO مباشرة
        audio_file = BytesIO(audio_bytes)
        with sr.AudioFile(audio_file) as source:
            # تقليل مدة ضبط الضوضاء لتسريع الاستجابة
            r.adjust_for_ambient_noise(source, duration=0.5)
            audio = r.record(source)
            return r.recognize_google(audio, language=lang_code)
    except Exception as e:
        print(f"STT Error: {e}")
        return None

# ==========================================
# 🧠 الذكاء الاصطناعي
# ==========================================
def get_working_model():
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys: return None
    random.shuffle(keys)
    # النماذج الأقوى المتاحة لك
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
    # 1. عرض رسالة المستخدم في الشات فوراً (Native UI)
    if input_type != "voice":
        with st.chat_message("user"):
            st.write(user_text if isinstance(user_text, str) else user_text[0])
    
    # 2. المعالجة
    with st.chat_message("assistant"):
        with st.spinner("🧠 جاري التفكير..."):
            try:
                log_activity(st.session_state.user_name, input_type, user_text)
                model = get_working_model()
                if not model:
                    st.error("خطأ في الاتصال.")
                    return

                grade = st.session_state.get("student_grade", "General")
                lang = "Arabic" if st.session_state.language == "العربية" else "English"
                ref = st.session_state.get("ref_text", "")
                
                base_prompt = f"""
                Role: Friendly Teacher. Student Grade: {grade}.
                Context: {ref[:8000]}
                Instructions: Answer in {lang}. Be clear.
                Structure: Introduction, Points, Conclusion.
                No markdown symbols like * or # in the output, just clean text.
                """
                
                if input_type == "image":
                     resp = model.generate_content([base_prompt, user_text[0], user_text[1]])
                else:
                    resp = model.generate_content(f"{base_prompt}\nStudent: {user_text}")
                
                full_text = resp.text
                
                # فصل الكود إن وجد
                disp_text = full_text.split("```dot")[0]
                
                # عرض النص
                st.write(disp_text)
                
                # الرسم البياني
                if "```dot" in full_text:
                    try:
                        dot = full_text.split("```dot")[1].split("```")[0]
                        st.graphviz_chart(dot)
                    except: pass

                # الصوت
                audio_bytes = get_audio_bytes(disp_text, lang)
                if audio_bytes:
                    st.audio(audio_bytes, format='audio/mp3', autoplay=True)

            except Exception as e:
                st.error(f"خطأ: {e}")

# ==========================================
# 🎨 الواجهة
# ==========================================

if "auth_status" not in st.session_state:
    st.session_state.update({
        "auth_status": False, "user_type": "none", "student_grade": "", 
        "current_xp": 0, "last_audio_bytes": None, "language": "العربية", "ref_text": ""
    })

# --- الدخول ---
if not st.session_state.auth_status:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🎓 المعلم الذكي")
        st.info(random.choice(DAILY_FACTS))
        with st.form("login"):
            name = st.text_input("الاسم:")
            grade = st.selectbox("الصف:", ["الرابع الابتدائي", "الخامس الابتدائي", "السادس الابتدائي", "الأول الإعدادي", "الثاني الإعدادي", "الثالث الإعدادي", "الثانوي"])
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

# --- التطبيق ---
with st.sidebar:
    st.header(f"👤 {st.session_state.user_name}")
    st.success(f"الرتبة: {get_rank_title(st.session_state.current_xp)}")
    st.progress(min(1.0, st.session_state.current_xp/100))
    st.write(f"نقاط XP: {st.session_state.current_xp}")
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

st.title("🧬 مختبر العلوم")

# استخدام واجهة الشات 
