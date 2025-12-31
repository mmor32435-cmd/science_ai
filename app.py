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

st.set_page_config(page_title="Science AI Pro", page_icon="🐞", layout="wide")

# --- دالة جلب الباسورد (معدلة لكشف الخطأ) ---
def get_daily_password():
    if "gcp_service_account" in st.secrets:
        try:
            creds = service_account.Credentials.from_service_account_info(
                st.secrets["gcp_service_account"],
                scopes=['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
            )
            client = gspread.authorize(creds)
            
            # محاولة فتح الشيت
            try:
                sheet = client.open(CONTROL_SHEET_NAME).sheet1
            except gspread.SpreadsheetNotFound:
                st.error(f"❌ لم أجد ملف إكسل باسم '{CONTROL_SHEET_NAME}' في جوجل درايف. تأكد من الاسم والمشاركة.")
                return None
            
            # قراءة القيمة
            val = sheet.acell('B1').value
            
            # === كود كشف الخطأ (سيظهر لك ما في الشيت) ===
            st.toast(f"📢 النظام قرأ من الشيت الباسورد: {val}", icon="🕵️")
            # ==========================================
            
            return str(val).strip() if val else None
            
        except Exception as e:
            st.error(f"❌ خطأ تقني في الاتصال بالشيت: {e}")
            st.info("تأكد أنك فعلت Google Sheets API في Google Cloud Console")
            return None
    else:
        st.error("❌ بيانات حساب الخدمة (JSON) غير موجودة في Secrets")
        return None

# --- التحقق من الدخول ---
def check_login(password):
    # 1. المعلم
    if password == TEACHER_MASTER_KEY:
        return True, "teacher"
    
    # 2. الطالب
    daily_pass = get_daily_password()
    
    if not daily_pass:
        return False, "⚠️ لا يوجد باسورد مسجل في الشيت اليوم."
        
    if password == daily_pass:
        return True, "student"
    else:
        # رسالة سرية لك لتعرف الفرق
        return False, f"⛔ الباسورد خطأ. (أنت كتبت: {password} - والمطلوب: {daily_pass})"

# --- باقي الدوال (كما هي) ---
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

# Gemini
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
# ===== المنطق =====
# ==========================================

if "auth_status" not in st.session_state:
    st.session_state.auth_status = False
    st.session_state.user_type = "none"

# شاشة الدخول (مع كشف الأخطاء)
if not st.session_state.auth_status:
    st.title("🔐 Science AI Platform (Debug Mode)")
    st.info("⚠️ هذا الوضع يظهر لك سبب الخطأ لتتمكن من حله.")
    
    pwd = st.text_input("Password:", type="password")
    if st.button("Login"):
        valid, u_type_or_msg = check_login(pwd)
        if valid:
            st.session_state.auth_status = True
            st.session_state.user_type = u_type_or_msg
            st.session_state.start_time = time.time()
            st.success("تم الدخول!"); time.sleep(0.5); st.rerun()
        else:
            # هنا يظهر لك السبب الحقيقي
            st.error(u_type_or_msg)
    st.stop()

# وقت الجلسة
time_up = False
remaining_minutes = 0
if st.session_state.user_type == "student":
    elapsed_seconds = time.time() - st.session_state.start_time
    allowed_seconds = SESSION_DURATION_MINUTES * 60
    if elapsed_seconds > allowed_seconds: time_up = True
    else: remaining_minutes = int((allowed_seconds - elapsed_seconds) // 60)

# واجهة التطبيق
with st.sidebar:
    if st.session_state.user_type == "teacher": st.success("👨‍🏫 Teacher")
    else:
        if time_up: st.error("🛑 Time's up!")
        else: st.metric("Time Left", f"{remaining_minutes} min")

    st.markdown("---")
    language = st.radio("Language:", ["العربية", "English"])
    lang_code = "ar-EG" if language == "العربية" else "en-US"
    voice_code, sr_lang = get_voice_config(language)
    
    if DRIVE_FOLDER_ID:
        service = get_drive_service()
        if service:
            files = list_drive_files(service, DRIVE_FOLDER_ID)
            if files:
                st.subheader("📚 Library")
                sel_file = st.selectbox("Book:", [f['name'] for f in files])
                if st.button("Load"):
                    fid = next(f['id'] for f in files if f['name'] == sel_file)
                    with st.spinner("Loading..."):
                        st.session_state.ref_text = download_pdf_text(service, fid)
                        st.success("Loaded!")

if time_up and st.session_state.user_type == "student":
    st.error("Session Expired."); st.stop()

st.title("⚡ AI Science Tutor")
tab1, tab2, tab3 = st.tabs(["🎙️ Voice", "✍️ Chat", "📁 Upload"])
user_input = ""
input_mode = "text"

with tab1:
    audio_in = mic_recorder(start_prompt="🎤 Speak", stop_prompt="⏹️ Send", key='mic', format="wav")
    if audio_in: user_input = speech_to_text(audio_in['bytes'], sr_lang)

with tab2:
    txt_in = st.text_area("Question:")
    if st.button("Send"): user_input = txt_in

with tab3:
    up_file = st.file_uploader("File", type=['png','jpg','pdf'])
    up_q = st.text_input("Details:")
    if st.button("Analyze") and up_file:
        if up_file.type == 'application/pdf':
             pdf = PyPDF2.PdfReader(up_file)
             ext = ""
             for p in pdf.pages: ext += p.extract_text()
             user_input = f"PDF:\n{ext}\nQ: {up_q}"
        else:
            img = Image.open(up_file)
            st.image(img, width=200)
            user_input = [up_q if up_q else "Explain", img]
            input_mode = "image"

if user_input:
    status = st.status("🧠 Processing...", expanded=True)
    try:
        role_lang = "Arabic" if language == "العربية" else "English"
        ref = st.session_state.get("ref_text", "")
        sys_prompt = f"Role: Science Tutor. Lang: {role_lang}. Be concise. Ref: {ref[:20000]}"
        
        if input_mode == "image":
             if 'vision' in active_model_name or 'flash' in active_model_name or 'pro' in active_model_name:
                response = model.generate_content([sys_prompt, user_input[0], user_input[1]])
             else: st.error("Model error"); st.stop()
        else:
            response = model.generate_content(f"{sys_prompt}\nUser: {user_input}")
        
        status.write("Speaking...")
        st.markdown(f"### 💡 Answer:\n{response.text}")
        audio = asyncio.run(generate_audio_stream(response.text, voice_code))
        st.audio(audio, format='audio/mp3', autoplay=True)
        status.update(label="Done", state="complete", expanded=False)
    except Exception as e: st.error(f"Error: {e}")
