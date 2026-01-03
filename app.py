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

# ==========================================
# 🎛️ إعدادات التحكم
# ==========================================

TEACHER_MASTER_KEY = "ADMIN_2024"
CONTROL_SHEET_NAME = "App_Control"
SESSION_DURATION_MINUTES = 60
DRIVE_FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "") 

st.set_page_config(page_title="Science AI Pro", page_icon="⚡", layout="wide")

# --- دوال الاتصال بالشيت ---
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

def get_daily_password():
    client = get_gspread_client()
    if client:
        try:
            sheet = client.open(CONTROL_SHEET_NAME).sheet1
            return str(sheet.acell('B1').value).strip()
        except: return None
    return None

# --- دالة تسجيل الدخول (الجديدة) ---
def log_login_to_sheet(user_type, password_used):
    """تسجيل الدخول في الصفحة الثانية من ملف الإكسل"""
    client = get_gspread_client()
    if client:
        try:
            # نفتح الصفحة الثانية المسماة Logs
            sheet = client.open(CONTROL_SHEET_NAME).worksheet("Logs")
            
            # توقيت القاهرة
            tz = pytz.timezone('Africa/Cairo')
            now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
            
            # إضافة صف جديد
            sheet.append_row([now, user_type, password_used])
        except Exception as e:
            print(f"Log Error: {e}") # لن يوقف التطبيق، فقط يطبع في الكونسول

# --- التحقق من الدخول (مع التسجيل) ---
def check_login(password):
    # 1. المعلم
    if password == TEACHER_MASTER_KEY:
        log_login_to_sheet("Teacher", "MASTER_KEY") # سجل أن المعلم دخل
        return True, "teacher"
    
    # 2. الطالب
    daily_pass = get_daily_password()
    if daily_pass and password == daily_pass:
        log_login_to_sheet("Student", password) # سجل أن طالب دخل بالكود الصحيح
        return True, "student"
    
    # محاولة فاشلة (اختياري: يمكن تسجيلها أيضاً لكشف محاولات الاختراق)
    # log_login_to_sheet("Failed", password) 
    
    return False, "none"

# --- (باقي الكود كما هو تماماً بدون تغيير) ---
# ... انسخ باقي الدوال من الكود السابق (get_drive_service, audio, AI, الواجهة...)
# ... (لعدم التكرار، استخدم نفس الجزء السفلي من الكود الأخير الذي أعطيته لك)

# --- دوال الخدمات ---
def get_drive_service():
    if "gcp_service_account" in st.secrets:
        try:
            creds = service_account.Credentials.from_service_account_info(
                st.secrets["gcp_service_account"],
                scopes=['https://www.googleapis.com/auth/drive.readonly']
            )
            return build('drive', 'v3', credentials=creds)
        except: return None
    return None

def list_drive_files(service, folder_id):
    try:
        results = service.files().list(
            q=f"'{folder_id}' in parents and mimeType='application/pdf'",
            fields="nextPageToken, files(id, name)").execute()
        return results.get('files', [])
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

async def generate_audio_stream(text, voice_code):
    clean_text = re.sub(r'[\*\#\-\_]', '', text)
    communicate = edge_tts.Communicate(clean_text, voice_code, rate="-5%")
    mp3_fp = BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3_fp.write(chunk["data"])
    return mp3_fp

def speech_to_text(audio_bytes, lang_code):
    r = sr.Recognizer()
    try:
        audio_file = sr.AudioFile(BytesIO(audio_bytes))
        with audio_file as source:
            r.adjust_for_ambient_noise(source, duration=0.5)
            audio_data = r.record(source)
            text = r.recognize_google(audio_data, language=lang_code)
            return text
    except: return None

# Gemini Config
try:
    if "GOOGLE_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
        all_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        active_model_name = next((m for m in all_models if 'flash' in m), None)
        if not active_model_name:
            active_model_name = next((m for m in all_models if 'pro' in m), all_models[0])
        model = genai.GenerativeModel(active_model_name)
    else: st.stop()
except: st.stop()


# ==========================================
# ===== تصميم الواجهة الاحترافي =====
# ==========================================

def draw_header():
    st.markdown("""
        <style>
        .header-container {
            padding: 2rem 1rem;
            border-radius: 15px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-align: center;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            margin-bottom: 2rem;
        }
        .main-title {
            font-size: 3rem;
            font-weight: 800;
            margin: 0;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
            font-family: 'Helvetica Neue', sans-serif;
        }
        .sub-title {
            font-size: 1.5rem;
            margin-top: 10px;
            font-weight: 300;
            color: #f0f0f0;
        }
        .teacher-name {
            background-color: rgba(255, 255, 255, 0.2);
            padding: 5px 15px;
            border-radius: 20px;
            font-weight: bold;
            letter-spacing: 1px;
            border: 1px solid rgba(255,255,255,0.4);
        }
        </style>
        
        <div class="header-container">
            <div class="main-title">🧬 AI Science Tutor</div>
            <div class="sub-title">
                Supervised by <span class="teacher-name">Mr. Elsayed Elbadawy</span>
            </div>
        </div>
    """, unsafe_allow_html=True)

# ==========================================
# ===== المنطق والتشغيل =====
# ==========================================

if "auth_status" not in st.session_state:
    st.session_state.auth_status = False
    st.session_state.user_type = "none"

# شاشة الدخول
if not st.session_state.auth_status:
    draw_header()
    st.info(f"🔒 Student Session Limit: {SESSION_DURATION_MINUTES} Minutes")
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        pwd = st.text_input("Enter Password / أدخل كود الدخول:", type="password")
        if st.button("Login / دخول", use_container_width=True):
            with st.spinner("Verifying..."):
                valid, u_type = check_login(pwd)
                if valid:
                    st.session_state.auth_status = True
                    st.session_state.user_type = u_type
                    st.session_state.start_time = time.time()
                    st.success("Welcome!"); time.sleep(0.5); st.rerun()
                else:
                    st.error("Invalid Password")
    st.stop()

# منطق الوقت
time_up = False
remaining_minutes = 0
if st.session_state.user_type == "student":
    elapsed = time.time() - st.session_state.start_time
    allowed = SESSION_DURATION_MINUTES * 60
    if elapsed > allowed: time_up = True
    else: remaining_minutes = int((allowed - elapsed) // 60)

# الشريط الجانبي
with st.sidebar:
    if st.session_state.user_type == "teacher":
        st.success("👨‍🏫 Teacher Mode (Unlimited)")
    else:
        if time_up: st.error("🛑 Time's Up")
        else:
            st.metric("Time Left", f"{remaining_minutes} min")
            st.progress(max(0, (SESSION_DURATION_MINUTES * 60 - (time.time() - st.session_state.start_time)) / (SESSION_DURATION_MINUTES * 60)))

    st.markdown("---")
    st.header("⚙️ Settings")
    language = st.radio("Language:", ["العربية", "English"])
    lang_code = "ar-EG" if language == "العربية" else "en-US"
    voice_code, sr_lang = get_voice_config(language)
    
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
                        st.success("Active!")

if time_up and st.session_state.user_type == "student":
    st.error("Session Expired / انتهت الجلسة"); st.stop()

# عرض الهيدر
draw_header()

# التطبيق الرئيسي
tab1, tab2, tab3 = st.tabs(["🎙️ Voice Chat", "✍️ Text Chat", "📁 Upload File"])
user_input = ""
input_mode = "text"

with tab1:
    st.write("Tap the microphone to speak:")
    audio_in = mic_recorder(start_prompt="🎤 Start Speaking", stop_prompt="⏹️ Stop & Send", key='mic', format="wav")
    if audio_in: user_input = speech_to_text(audio_in['bytes'], sr_lang)

with tab2:
    txt_in = st.text_area("Type your question here:")
    if st.button("Send Message", use_container_width=True): user_input = txt_in

with tab3:
    up_file = st.file_uploader("Upload Image or PDF", type=['png','jpg','pdf'])
    up_q = st.text_input("Add details about the file:")
    if st.button("Analyze File", use_container_width=True) and up_file:
        if up_file.type == 'application/pdf':
             pdf = PyPDF2.PdfReader(up_file)
             ext = ""
             for p in pdf.pages: ext += p.extract_text()
             user_input = f"PDF:\n{ext}\nQ: {up_q}"
        else:
            img = Image.open(up_file)
            st.image(img, width=300)
            user_input = [up_q if up_q else "Explain", img]
            input_mode = "image"

if user_input:
    status = st.status("🧠 Mr. Elsayed's AI is thinking...", expanded=True)
    try:
        role_lang = "Arabic" if language == "العربية" else "English"
        ref = st.session_state.get("ref_text", "")
        
        sys_prompt = f"""
        Role: Professional Science Tutor. Lang: {role_lang}.
        Context: You are assisting Mr. Elsayed Elbadawy's students.
        Goal: Explain clearly & Interactively.
        Instructions:
        1. Answer in {role_lang}.
        2. BE CONCISE (under 60 words).
        3. Reference: {ref[:20000]}
        """
        
        status.write("Analyzing...")
        if input_mode == "image":
             if 'vision' in active_model_name or 'flash' in active_model_name or 'pro' in active_model_name:
                response = model.generate_content([sys_prompt, user_input[0], user_input[1]])
             else: st.error("Model doesn't support images."); st.stop()
        else:
            response = model.generate_content(f"{sys_prompt}\nUser: {user_input}")
        
        status.write("Generating Voice...")
        st.markdown(f"### 💡 Answer:\n{response.text}")
        
        audio = asyncio.run(generate_audio_stream(response.text, voice_code))
        st.audio(audio, format='audio/mp3', autoplay=True)
        status.update(label="Done", state="complete", expanded=False)
        
    except Exception as e:
        status.update(label="Error", state="error")
        st.error(f"Error: {e}")
