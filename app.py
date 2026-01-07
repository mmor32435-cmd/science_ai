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
import threading

# ==========================================
# 🎛️ إعدادات التحكم
# ==========================================

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

st.set_page_config(page_title="AI Science Tutor Pro", page_icon="🧬", layout="wide")

# ==========================================
# 🛠️ الخدمات (شيت، درايف، صوت)
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
    if client:
        try:
            sheet = client.open(CONTROL_SHEET_NAME)
            daily_pass = str(sheet.sheet1.acell('B1').value).strip()
            return daily_pass, sheet
        except: return None, None
    return None, None

def update_daily_password(new_pass):
    client = get_gspread_client()
    if client:
        try:
            client.open(CONTROL_SHEET_NAME).sheet1.update_acell('B1', new_pass)
            return True
        except: return False
    return False

# --- التسجيل في الخلفية (لزيادة السرعة) ---
def _log_login_bg(user_name, user_type, details):
    client = get_gspread_client()
    if client:
        try:
            try: sheet = client.open(CONTROL_SHEET_NAME).worksheet("Logs")
            except: sheet = client.open(CONTROL_SHEET_NAME).sheet1
            tz = pytz.timezone('Africa/Cairo')
            now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
            sheet.append_row([now, user_type, user_name, details])
        except: pass

def log_login_to_sheet(user_name, user_type, details=""):
    threading.Thread(target=_log_login_bg, args=(user_name, user_type, details)).start()

def _log_activity_bg(user_name, input_type, question_text):
    client = get_gspread_client()
    if client:
        try:
            try: sheet = client.open(CONTROL_SHEET_NAME).worksheet("Activity")
            except: return
            tz = pytz.timezone('Africa/Cairo')
            now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
            final_text = question_text
            if isinstance(question_text, list): final_text = f"[Image] {question_text[0]}"
            sheet.append_row([now, user_name, input_type, str(final_text)[:500]])
        except: pass

def log_activity(user_name, input_type, question_text):
    threading.Thread(target=_log_activity_bg, args=(user_name, input_type, question_text)).start()

def _update_xp_bg(user_name, points_to_add):
    client = get_gspread_client()
    if client:
        try:
            try: sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
            except: return
            cell = sheet.find(user_name)
            if cell:
                current_xp = int(sheet.cell(cell.row, 2).value)
                sheet.update_cell(cell.row, 2, current_xp + points_to_add)
            else:
                sheet.append_row([user_name, points_to_add])
        except: pass

def update_xp(user_name, points_to_add):
    if 'current_xp' in st.session_state:
        st.session_state.current_xp += points_to_add
    threading.Thread(target=_update_xp_bg, args=(user_name, points_to_add)).start()
    return st.session_state.current_xp

def get_current_xp(user_name):
    client = get_gspread_client()
    if client:
        try:
            sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
            cell = sheet.find(user_name)
            if cell: return int(sheet.cell(cell.row, 2).value)
        except: return 0
    return 0

def get_leaderboard():
    client = get_gspread_client()
    if client:
        try:
            try: sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
            except: return []
            data = sheet.get_all_records()
            if not data: return []
            df = pd.DataFrame(data)
            df['XP'] = pd.to_numeric(df['XP'])
            top_5 = df.sort_values(by='XP', ascending=False).head(5)
            return top_5.to_dict('records')
        except: return []
    return []

def clear_old_data():
    client = get_gspread_client()
    if client:
        try:
            for s in ["Logs", "Activity", "Gamification"]:
                try: 
                    ws = client.open(CONTROL_SHEET_NAME).worksheet(s)
                    ws.resize(rows=1); ws.resize(rows=100)
                except: pass
            return True
        except: return False
    return False

def get_stats_for_admin():
    client = get_gspread_client()
    if client:
        try:
            logs = client.open(CONTROL_SHEET_NAME).worksheet("Logs").get_all_values()
            qs = client.open(CONTROL_SHEET_NAME).worksheet("Activity").get_all_values()
            return len(logs)-1, qs[-5:]
        except: return 0, []
    return 0, []

def get_chat_text(history):
    text = "--- Chat History ---\n\n"
    for q, a in history:
        text += f"Student: {q}\nAI Tutor: {a}\n\n"
    return text

def create_certificate(student_name):
    txt = f"CERTIFICATE OF EXCELLENCE\n\nAwarded to: {student_name}\n\nFor achieving 100 XP.\n\nSigned: Mr. Elsayed Elbadawy"
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
    # 🔥 تسريع الصوت: نطق أول 300 حرف فقط إذا كان النص طويلاً
    # هذا يجعل الاستجابة أسرع 3 أضعاف
    text_to_speak = clean_text_for_audio(text)
    if len(text_to_speak) > 400:
        text_to_speak = text_to_speak[:400] + "..."
        
    communicate = edge_tts.Communicate(text_to_speak, voice_code, rate="-5%")
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

@st.cache_resource
def load_ai_model():
    if "GOOGLE_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
        all_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        active_model_name = next((m for m in all_models if 'flash' in m), None)
        if not active_model_name: active_model_name = next((m for m in all_models if 'pro' in m), all_models[0])
        return genai.GenerativeModel(active_model_name)
    return None

try:
    model = load_ai_model()
    if not model: st.stop()
except: st.stop()


# ==========================================
# 🎨 الواجهة
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
                        st.session_state.current_xp = get_current_xp(st.session_state.user_name)
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

col_lang, col_stat = st.columns([2,1])
with col_lang:
    language = st.radio("Speaking Language / لغة التحدث:", ["العربية", "English"], horizontal=True)

lang_code = "ar-EG" if language == "العربية" else "en-US"
voice_code, sr_lang = get_voice_config(language)

with st.sidebar:
    st.write(f"👤 **{st.session_state.user_name}**")
    if st.session_state.user_type == "student":
        st.metric("🌟 Your XP", st.session_state.current_xp)
        if st.session_state.current_xp >= 100:
            st.success("🎉 100 XP Reached!")
            if st.button("🎓 Certificate"):
                st.download_button("⬇️ Download", create_certificate(st.session_state.user_name), "Certificate.txt")
        st.info(f"📚 {st.session_state.student_grade}")
        
        st.markdown("---")
        st.subheader("🏆 Leaderboard")
        leaders = get_leaderboard()
        if leaders:
            for i, leader in enumerate(leaders):
                medal = "🥇" if i==0 else "🥈" if i==1 else "🥉" if i==2 else f"{i+1}."
                st.write(f"{medal} **{leader['Student_Name']}**: {leader['XP']} XP")
    
    if st.session_state.user_type == "teacher":
        st.success("👨‍🏫 Admin Dashboard")
        st.markdown("---")
        with st.expander("📊 Stats"):
            count, last_qs = get_stats_for_admin()
            st.metric("Logins", count)
            for q in last_qs:
                if len(q) > 3:
                    st.caption(f"- {q[3][:25]}...")
        with st.expander("🔑 Password"):
            new_p = st.text_input("New Code:")
            if st.button("Update"):
                if update_daily_password(new_p): st.success("Updated!")
                else: st.error("Failed")
        with st.expander("⚠️ Danger"):
            if st.button("🗑️ Clear Logs"):
                if clear_old_data(): st.success("Cleared!")
    else:
        st.metric("⏳ Time Left", f"{remaining_minutes} min")
        st.progress(max(0, (SESSION_DURATION_MINUTES * 60 - (time.time() - st.session_state.start_time)) / (SESSION_DURATION_MINUTES * 60)))
        st.markdown("---")
        if st.session_state.chat_history:
            chat_txt = get_chat_text(st.session_state.chat_history)
            st.download_button("📥 Save Chat", chat_txt, file_name="Science_Session.txt")

    st.markdown("---")
    if DRIVE_FOLDER_ID:
        service = get_drive_service()
        if service:
            files = list_drive_files(service, DRIVE_FOLDER_ID)
            if files:
                st.subheader("📚 Library")
                sel_file = st.selectbox("Book:", [f['name'] for f in files])
                if st.button("Load Book", use_container_width=True):
                    fid = next(f['id'] for f in files if f['name'] == sel_file)
                    with st.spinner("Loading..."):
                        st.session_state.ref_text = download_pdf_text(service, fid)
                        st.toast("Book Loaded! ✅")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["🎙️ Voice", "✍️ Chat", "📁 File", "🧠 Quiz", "📊 Report"])
user_input = ""
input_mode = "text"

with tab1:
    st.caption("Click mic to speak")
    audio_in = mic_recorder(start_prompt="🎤 Start", stop_prompt="⏹️ Send", key='mic', format="wav")
    if audio_in: 
        user_input = speech_to_text(audio_in['bytes'], sr_lang)
        new_xp = update_xp(st.session_state.user_name, 10)
        st.session_state.current_xp = new_xp

with tab2:
    txt_in = st.text_area("Write here:")
    if st.button("Send", use_container_width=True): 
        user_input = txt_in
        new_xp = update_xp(st.session_state.user_name, 5)
        st.session_state.current_xp = new_xp

with tab3:
    up_file = st.file_uploader("Image/PDF", type=['png','jpg','pdf'])
    up_q = st.text_input("Details:")
    if st.button("Analyze", use_container_width=True) and up_file:
        if up_file.type == 'application/pdf':
             pdf = PyPDF2.PdfReader(up_file)
             ext = ""
             for p in pdf.pages: ext += p.extract_text()
             user_input = f"PDF:\n{ext}\nQ: {up_q}"
        else:
            img = Image.open(up_file)
            st.image(img, width=300)
            user_input 
