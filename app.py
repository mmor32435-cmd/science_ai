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
import gspread # مكتبة الشيت

# ==========================================
# 🎛️ إعدادات المعلم (الثابتة)
# ==========================================

TEACHER_MASTER_KEY = "ADMIN_2024" # مفتاحك الخاص (لا يتغير)
MY_TIMEZONE = 'Africa/Cairo'
ALLOWED_HOURS = [17, 19, 21] 
DRIVE_FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "") 
CONTROL_SHEET_NAME = "App_Control" # اسم ملف الشيت الذي أنشأته

st.set_page_config(page_title="Science AI Pro", page_icon="⚡", layout="wide")

# --- دالة جلب الباسورد اليومي من الشيت ---
def get_daily_password():
    # استخدام نفس بيانات الاعتماد الموجودة في Secrets
    if "gcp_service_account" in st.secrets:
        try:
            # إعداد الاتصال
            creds = service_account.Credentials.from_service_account_info(
                st.secrets["gcp_service_account"],
                scopes=['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
            )
            client = gspread.authorize(creds)
            
            # فتح الشيت وقراءة الخلية B1
            sheet = client.open(CONTROL_SHEET_NAME).sheet1
            daily_pass = sheet.acell('B1').value
            return daily_pass
        except Exception as e:
            st.error(f"خطأ في قراءة الشيت (تأكد من مشاركة الملف مع إيميل الخدمة): {e}")
            return "ERROR"
    return "ERROR"

# --- التحقق من الدخول ---
def check_access(password):
    if password == TEACHER_MASTER_KEY:
        return True, "👨‍🏫 مرحباً أستاذي!", "teacher"
    
    # هنا نجلب الباسورد المتغير من الشيت
    CURRENT_STUDENT_PASS = get_daily_password()
    
    if password == CURRENT_STUDENT_PASS:
        tz = pytz.timezone(MY_TIMEZONE)
        now = datetime.now(tz)
        if now.hour in ALLOWED_HOURS:
            remaining = 60 - now.minute
            return True, f"✅ أهلاً بك. متبقي {remaining} دقيقة.", "student"
        else:
            return False, "⏳ المنصة مغلقة حالياً.", "student"
    
    return False, "⛔ كلمة المرور غير صحيحة.", "none"

# --- باقي الكود (كما هو تماماً بدون تغيير) ---
# ... (انسخ باقي الدوال: get_drive_service, audio, ai, etc...)
# ... (نفس الكود السابق من عند دالة get_drive_service للنهاية)

# لكي لا يطول الرد، سأضع لك باقي الكود مختصراً هنا، 
# انسخ الدوال والواجهة من الكود السابق (النسخة السريعة) وضعه هنا بالأسفل 👇

# --- دوال جوجل درايف ---
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

# --- دوال الصوت ---
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

# --- إعداد Gemini ---
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
# ===== الواجهة =====
# ==========================================

if "auth_status" not in st.session_state:
    st.session_state.auth_status = False

if not st.session_state.auth_status:
    st.title("🔐 Science AI Platform")
    pwd = st.text_input("Password:", type="password")
    if st.button("Login"):
        allowed, msg, u_type = check_access(pwd)
        if allowed:
            st.session_state.auth_status = True
            st.session_state.user_type = u_type
            st.success(msg); time.sleep(0.5); st.rerun()
        else: st.error(msg)
    st.stop()

with st.sidebar:
    st.header("⚙️ Settings")
    language = st.radio("Language:", ["العربية", "English"])
    lang_code = "ar-EG" if language == "العربية" else "en-US"
    voice_code, sr_lang = get_voice_config(language)
    
    st.markdown("---")
    st.subheader("📚 Library")
    if DRIVE_FOLDER_ID:
        service = get_drive_service()
        if service:
            files = list_drive_files(service, DRIVE_FOLDER_ID)
            if files:
                sel_file = st.selectbox("Book:", [f['name'] for f in files])
                if st.button("Load"):
                    fid = next(f['id'] for f in files if f['name'] == sel_file)
                    with st.spinner("Downloading..."):
                        st.session_state.ref_text = download_pdf_text(service, fid)
                        st.success("Loaded!")
            else: st.warning("Empty Folder")

st.title("⚡ AI Science Tutor")
tab1, tab2, tab3 = st.tabs(["🎙️ Voice", "✍️ Chat", "📁 Upload"])
user_input = ""
input_mode = "text"

with tab1:
    audio_in = mic_recorder(start_prompt="🎤 Tap to Speak", stop_prompt="⏹️ Sending...", key='mic', format="wav")
    if audio_in:
        user_input = speech_to_text(audio_in['bytes'], sr_lang)

with tab2:
    txt_in = st.text_area("Question:")
    if st.button("Send"): user_input = txt_in

with tab3:
    up_file = st.file_uploader("File", type=['png','jpg','pdf'])
    up_q = st.text_input("Details:")
    if st.button("Analyze") and up_file:
        if up_file.type == 'application/pdf':
             pdf_reader = PyPDF2.PdfReader(up_file)
             extracted = ""
             for p in pdf_reader.pages: extracted += p.extract_text()
             user_input = f"PDF:\n{extracted}\nQ: {up_q}"
        else:
            image = Image.open(up_file)
            st.image(image, width=200)
            user_input = [up_q if up_q else "Explain", image]
            input_mode = "image"

if user_input:
    status_box = st.status("🧠 Processing...", expanded=True)
    try:
        role_lang = "Arabic" if language == "العربية" else "English"
        ref = st.session_state.get("ref_text", "")
        
        system_prompt = f"""
        Act as a professional Science Tutor. Language: {role_lang}.
        Instructions:
        1. Answer in {role_lang}.
        2. BE CONCISE (under 50 words).
        3. Reference: {ref[:20000]}
        """
        
        status_box.write("Thinking...")
        if input_mode == "image":
            response = model.generate_content([system_prompt, user_input[0], user_input[1]])
        else:
            response = model.generate_content(f"{system_prompt}\nUser: {user_input}")
        
        status_box.write("Generating Audio...")
        st.markdown(f"### 💡 Answer:\n{response.text}")
        
        audio_bytes = asyncio.run(generate_audio_stream(response.text, voice_code))
        st.audio(audio_bytes, format='audio/mp3', autoplay=True)
        
        status_box.update(label="✅ Complete!", state="complete", expanded=False)
        
    except Exception as e:
        status_box.update(label="❌ Error", state="error")
        st.error(f"Error: {e}")
