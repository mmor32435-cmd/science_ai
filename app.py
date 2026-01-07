import streamlit as st
import time
import google.generativeai as genai
import asyncio
import edge_tts
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder
from io import BytesIO
import re
from datetime import datetime
import pytz
from PIL import Image
import PyPDF2
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import gspread
from fpdf import FPDF
import pandas as pd
import random
import graphviz 

# ==========================================
# 1. إعدادات الصفحة (يجب أن تكون في السطر الأول)
# ==========================================
st.set_page_config(page_title="AI Science Tutor Pro", page_icon="🧬", layout="wide")

TEACHER_MASTER_KEY = "ADMIN_2024"
CONTROL_SHEET_NAME = "App_Control"
SESSION_DURATION_MINUTES = 60
DRIVE_FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "") 

DAILY_FACTS = [
    "هل تعلم؟ المخ يولد كهرباء تكفي لمصباح! 💡",
    "هل تعلم؟ العظام أقوى من الخرسانة بـ 4 مرات! 🦴",
    "هل تعلم؟ الأخطبوط لديه 3 قلوب! 🐙",
    "هل تعلم؟ العسل لا يفسد أبداً! 🍯",
    "هل تعلم؟ سرعة الضوء 300,000 كم/ث! ⚡"
]

# ==========================================
# 2. الخدمات والدوال المساعدة
# ==========================================

@st.cache_resource
def get_gspread_client():
    if "gcp_service_account" in st.secrets:
        try:
            creds = service_account.Credentials.from_service_account_info(
                st.secrets["gcp_service_account"],
                scopes=['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
            )
            return gspread.authorize(creds)
        except: return None
    return None

def get_sheet_data():
    client = get_gspread_client()
    if not client: return None, None
    try:
        sheet = client.open(CONTROL_SHEET_NAME)
        daily_pass = str(sheet.sheet1.acell('B1').value).strip()
        return daily_pass, sheet
    except: return None, None

def update_daily_password(new_pass):
    client = get_gspread_client()
    if not client: return False
    try:
        client.open(CONTROL_SHEET_NAME).sheet1.update_acell('B1', new_pass)
        return True
    except: return False

def log_login_to_sheet(user_name, user_type, details=""):
    client = get_gspread_client()
    if not client: return
    try:
        try: sheet = client.open(CONTROL_SHEET_NAME).worksheet("Logs")
        except: sheet = client.open(CONTROL_SHEET_NAME).sheet1
        tz = pytz.timezone('Africa/Cairo')
        now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([now, user_type, user_name, details])
    except: pass

def log_activity(user_name, input_type, question_text):
    client = get_gspread_client()
    if not client: return
    try:
        try: sheet = client.open(CONTROL_SHEET_NAME).worksheet("Activity")
        except: return 
        tz = pytz.timezone('Africa/Cairo')
        now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        final_text = question_text
        if isinstance(question_text, list): final_text = f"[Image] {question_text[0]}"
        sheet.append_row([now, user_name, input_type, str(final_text)[:500]])
    except: pass

def update_xp(user_name, points_to_add):
    client = get_gspread_client()
    if not client: return 0
    try:
        try: sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
        except: return 0
        cell = sheet.find(user_name)
        current_xp = 0
        if cell:
            val = sheet.cell(cell.row, 2).value
            current_xp = int(val) if val else 0
            new_xp = current_xp + points_to_add
            sheet.update_cell(cell.row, 2, new_xp)
            return new_xp
        else:
            sheet.append_row([user_name, points_to_add])
            return points_to_add
    except: return 0

def get_current_xp(user_name):
    client = get_gspread_client()
    if not client: return 0
    try:
        sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
        cell = sheet.find(user_name)
        if cell:
            val = sheet.cell(cell.row, 2).value
            return int(val) if val else 0
        return 0
    except: return 0

def get_leaderboard():
    client = get_gspread_client()
    if not client: return []
    try:
        sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
        data = sheet.get_all_records()
        if not data: return []
        df = pd.DataFrame(data)
        df['XP'] = pd.to_numeric(df['XP'], errors='coerce').fillna(0)
        top_5 = df.sort_values(by='XP', ascending=False).head(5)
        return top_5.to_dict('records')
    except: return []

def clear_old_data():
    client = get_gspread_client()
    if not client: return False
    try:
        for s in ["Logs", "Activity", "Gamification"]:
            try: 
                ws = client.open(CONTROL_SHEET_NAME).worksheet(s)
                ws.resize(rows=1); ws.resize(rows=100)
            except: pass
        return True
    except: return False

def get_stats_for_admin():
    client = get_gspread_client()
    if not client: return 0, []
    try:
        sheet = client.open(CONTROL_SHEET_NAME)
        try: logs = sheet.worksheet("Logs").get_all_values()
        except: logs = []
        try: qs = sheet.worksheet("Activity").get_all_values()
        except: qs = []
        return len(logs)-1 if logs else 0, qs[-5:] if qs else []
    except: return 0, []

def get_chat_text(history):
    text = "--- Chat History ---\n\n"
    for q, a in history: text += f"Student: {q}\nAI Tutor: {a}\n\n"
    return text

def create_certificate(student_name):
    txt = f"CERTIFICATE OF EXCELLENCE\n\nAwarded to: {student_name}\n\nFor achieving 100 XP in AI Science Tutor.\n\nSigned: Mr. Elsayed Elbadawy"
    return txt.encode('utf-8')

@st.cache_resource
def get_drive_service():
    if "gcp_service_account" in st.secrets:
        try:
            creds = service_account.Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=['https://www.googleapis.com/auth/drive.readonly'])
            return build('drive', 'v3', credentials=creds)
        except: return None
    return None

def list_drive_files(service, folder_id):
    try: return service.files().list(q=f"'{folder_id}' in parents", fields="files(id, name)").execute().get('files', [])
    except: return []

def download_pdf_text(service, file_id):
    try:
        request = service.files().get_media(fileId=file_id)
        file_io = BytesIO()
        downloader = MediaIoBaseDownload(file_io, request)
        done = False
        while done is False: status, done = downloader.next_chunk()
        file_io.seek(0)
        reader = PyPDF2.PdfReader(file_io)
        text = ""
        for page in reader.pages: text += page.extract_text() + "\n"
        return text
    except: return ""

def get_voice_config(lang):
    if lang == "English": return "en-US-AndrewNeural", "en-US"
    else: return "ar-EG-ShakirNeural", "ar-EG"

def clean_text_for_audio(text):
    text = re.sub(r'\\begin\{.*?\}', '', text) 
    text = re.sub(r'\\end\{.*?\}', '', text)   
    text = re.sub(r'\\item', '', text)         
    text = re.sub(r'\\textbf\{(.*?)\}', r'\1', text) 
    text = re.sub(r'\\textit\{(.*?)\}', r'\1', text) 
    text = re.sub(r'\\underline\{(.*?)\}', r'\1', text)
    text = text.replace('*', '').replace('#', '').replace('-', '').replace('_', ' ').replace('`', '')
    return text

async def generate_audio_stream(text, voice_code):
    clean_text = clean_text_for_audio(text)
    communicate = edge_tts.Communicate(clean_text, voice_code, rate="-5%")
    mp3_fp = BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio": mp3_fp.write(chunk["data"])
    return mp3_fp

def speech_to_text(audio_bytes, lang_code):
    r = sr.Recognizer()
    try:
        audio_file = sr.AudioFile(BytesIO(audio_bytes))
        with audio_file as source:
            r.adjust_for_ambient_noise(source, duration=0.5)
            audio_data = r.record(source)
            return r.recognize_google(audio_data, language=lang_code)
    except: return None

# 🔥 دالة تحميل الموديل (بدون إيقاف التطبيق إذا فشلت) 🔥
@st.cache_resource
def load_ai_model():
    try:
        api_key = None
        if "GOOGLE_API_KEYS" in st.secrets:
            keys = st.secrets["GOOGLE_API_KEYS"]
            if isinstance(keys, list) and len(keys) > 0:
                api_key = random.choice(keys)
        elif "GOOGLE_API_KEY" in st.secrets:
            api_key = st.secrets["GOOGLE_API_KEY"]
            
        if api_key:
            genai.configure(api_key=api_key)
            all_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            active_model_name = next((m for m in all_models if 'flash' in m), None)
            if not active_model_name:
                active_model_name = next((m for m in all_models if 'pro' in m), all_models[0])
            return genai.GenerativeModel(active_model_name)
    except: pass
    return None

# دالة التوليد الآمنة
def safe_generate_content(model, prompt):
    if not model:
        # محاولة أخيرة للتحميل
        model = load_ai_model()
        if not model: raise Exception("AI Connection Failed")
        
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return model.generate_content(prompt)
        except Exception as e:
            if "429" in str(e) or "Quota" in str(e):
                time.sleep(1)
                st.cache_resource.clear() # إعادة ضبط الكاش لتغيير المفتاح
                continue
            else: raise e
    raise Exception("Busy")


# ==========================================
# 🎨 واجهة التطبيق (ترسم دائماً)
# ==========================================

def draw_header():
    st.markdown("""
        <style>
        .header-container {
            padding: 1.5rem;
            border-radius: 15px;
            background: linear-gradient(120deg, #89f7fe 0%, #66a6ff 100%);
            color: #1a2a6c;
            text-align: center;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            margin-bottom: 1rem;
        }
        .main-title {
            font-size: 2.2rem;
            font-weight: 900;
            margin: 0;
            font-family: 'Segoe UI', sans-serif;
        }
        .sub-text {
            font-size: 1.1rem;
            font-weight: 600;
            margin-top: 5px;
        }
        </style>
        <div class="header-container">
            <div class="main-title">🧬 AI Science Tutor</div>
            <div class="sub-text">Under Supervision of: Mr. Elsayed Elbadawy</div>
        </div>
    """, unsafe_allow_html=True)

# تهيئة الجلسة
if "auth_status" not in st.session_state:
    st.session_state.auth_status = False
    st.session_state.user_type = "none"
    st.session_state.chat_history = []
    st.session_state.student_grade = ""
    st.session_state.study_lang = ""
    st.session_state.quiz_active = False
    st.session_state.current_quiz_question = ""
    st.session_state.current_xp = 0

# --- شاشة الدخول ---
if not st.session_state.auth_status:
    draw_header()
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.info(f"💡 {random.choice(DAILY_FACTS)}")
        
        with st.form("login_form"):
            student_name = st.text_input("Name / اسمك الثلاثي:")
            
            all_stages = ["الرابع الابتدائي", "الخامس الابتدائي", "السادس الابتدائي",
                          "الأول الإعدادي", "الثاني الإعدادي", "الثالث الإعدادي",
                          "الأول الثانوي", "الثاني الثانوي", "الثالث الثانوي"]
            selected_grade = st.selectbox("Grade / الصف الدراسي:", all_stages)
            
            study_type = st.radio("System / النظام:", ["عربي", "لغات (English)"], horizontal=True)
            pwd = st.text_input("Access Code / كود الدخول:", type="password")
            
            submit_login = st.form_submit_button("Login / دخول", use_container_width=True)
        
        if submit_login:
            if (not student_name) and pwd != TEACHER_MASTER_KEY:
                st.warning("⚠️ يرجى كتابة الاسم")
            else:
                with st.spinner("Connecting..."):
                    daily_pass, _ = get_sheet_data()
                    
                    if pwd == TEACHER_MASTER_KEY:
                        u_type = "teacher"; valid = True
                    elif daily_pass and pwd == daily_pass:
                        u_type = "student"; valid = True
                    else:
                        u_type = "none"; valid = False
                    
                    if valid:
                        st.session_state.auth_status = True
                        st.session_state.user_type = u_type
                        st.session_state.user_name = student_name if u_type == "student" else "Mr. Elsayed"
                        
                        st.session_state.student_grade = selected_grade
                        st.session_state.study_lang = "English Science" if "لغات" in study_type else "Arabic Science"
                        st.session_state.start_time = time.time()
                        
                        log_login_to_sheet(st.session_state.user_name, u_type, f"{selected_grade} | {study_type}")
                        
                        try:
                            st.session_state.current_xp = get_current_xp(st.session_state.user_name)
                        except:
                            st.session_state.current_xp = 0

                        st.success(f"Welcome {st.session_state.user_name}!"); time.sleep(0.5); st.rerun()
                    else:
                        st.error("Code Error")
    st.stop()

# --- الوقت ---
time_up = False
remaining_minutes = 0
if st.session_state.user_type == "student":
    elapsed = time.time() - st.session_state.start_time
    allowed = SESSION_DURATION_MINUTES * 60
    if elapsed > allowed:
        time_up = True
    else:
        remaining_minutes = int((allowed - elapsed) // 60)

if time_up and st.session_state.user_type == "student":
    st.error("Session Expired"); st.stop()

# --- التطبيق ---
draw_header()

# تحميل الموديل هنا (بعد رسم الواجهة) لتجنب اختفاء العناصر
model = 
