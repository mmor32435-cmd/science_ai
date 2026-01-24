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
# 2. تصميم "إصلاح الألوان" (Color Fix CSS)
# ==========================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Cairo', sans-serif !important;
        direction: rtl;
        text-align: right;
    }
    
    h1, h2, h3, h4, h5, h6, p, span, div, li {
        color: #000000 !important;
    }
    
    .stApp {
        background-color: #eef2f5;
    }
    
    .stChatMessage {
        background-color: #ffffff !important;
        border: 1px solid #c0c0c0 !important;
        border-radius: 12px !important;
        padding: 15px !important;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1) !important;
    }
    
    .stChatMessage div[data-testid="stMarkdownContainer"] p {
        color: #000000 !important;
        font-weight: 500 !important;
    }

    .stChatInput {
        position: fixed !important;
        bottom: 20px !important;
        z-index: 999 !important;
    }
    
    .stChatInput textarea {
        background-color: #ffffff !important;
        color: #000000 !important;
        border: 2px solid #004e92 !important;
    }
    
    .stTextInput input, .stSelectbox div {
        color: #000000 !important;
        background-color: #ffffff !important;
        border-color: #aaa !important;
    }

    .header-box {
        background: linear-gradient(90deg, #141E30 0%, #243B55 100%);
        padding: 2rem; border-radius: 15px; margin-bottom: 2rem; text-align: center;
    }
    .header-box h1, .header-box h3 { color: #ffffff !important; }
    
    .stButton>button {
        background-color: #004e92;
        color: #ffffff !important;
        border-radius: 10px;
        height: 50px;
        font-size: 18px !important;
        font-weight: bold !important;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="header-box">
    <h1>الأستاذ / السيد البدوي</h1>
    <h3>المنصة التعليمية الذكية للمراحل (الابتدائية - الإعدادية - الثانوية)</h3>
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
    """
    جلب الكتاب بناءً على المرحلة والصف:
    - ثانوي: Sec1, Sec2...
    - إعدادي: Prep1, Prep2...
    - ابتدائي: Grade4, Grade5...
    """
    creds = get_credentials()
    if not creds: return None
    try:
        # تحديد كود الملف (Prefix) بناءً على المرحلة
        file_prefix = ""
        if "الثانوية" in stage:
            mapping = {"الأول": "Sec1", "الثاني": "Sec2", "الثالث": "Sec3"}
            file_prefix = mapping.get(grade, "Sec1")
        elif "الإعدادية" in stage:
            mapping = {"الأول": "Prep1", "الثاني": "Prep2", "الثالث": "Prep3"}
            file_prefix = mapping.get(grade, "Prep1")
        else: # الابتدائية
            mapping = {"الرابع": "Grade4", "الخامس": "Grade5", "السادس": "Grade6"}
            file_prefix = mapping.get(grade, "Grade4")
            
        lang_code = "Ar" if "العربية" in lang else "En"
        expected_name = f"{file_prefix}_{lang_code}"
        
        service = build('drive', 'v3', credentials=creds)
        results = service.files().list(q=f"name contains '{expected_name}' and mimeType='application/pdf'", fields="files(id, name)").execute()
        files = results.get('files', [])
        
        if not files: return None
        request = service.files().get_media(fileId=files[0]['id'])
        file_stream = io.BytesIO()
        downloader = MediaIoBaseDownload(file_stream, request)
        done = False
        while done is False: status, done = downloader.next_chunk()
        
        file_stream.seek(0)
        pdf_reader = PyPDF2.PdfReader(file_stream)
        text = ""
        for page in pdf_reader.pages[:50]: text += page.extract_text() + "\n"
        return text
    except: return None

# ==========================================
# 5. الصوت والميكروفون
# ==========================================
def clean_text_for_speech(text):
    text = re.sub(r'[\*\#\-\_]', '', text)
    return text

def speech_to_text(audio_bytes):
    r = sr.Recognizer()
    try:
        audio_io = io.BytesIO(audio_bytes)
        with sr.AudioFile(audio_io) as source:
            audio_data = r.record(source)
            text = r.recognize_google(audio_data, language="ar-EG")
            return text
    except: return None

async def generate_speech_async(text, voice="ar-EG-ShakirNeural"):
    cleaned = clean_text_for_speech(text)
    communicate = edge_tts.Communicate(cleaned, voice)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
        await communicate.save(tmp_file.name)
        return tmp_file.name

def text_to_speech_pro(text):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(generate_speech_async(text))
    except: return None

# ==========================================
# 6. الذكاء الاصطناعي (ديناميكي)
# ==========================================
def get_dynamic_model():
    try:
        all_models = genai.list_models()
        valid_models = [m.name for m in all_models if 'generateContent' in m.supported_generation_methods]
        
        if not valid_models: return None
        
        for m in valid_models:
            if 'flash' in m.lower(): return m
        
        for m in valid_models:
            if 'pro' in m.lower(): return m
            
        return valid_models[0]
    except: return None

def get_ai_response(user_text, img_obj=None, is_quiz_mode=False):
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys: return "⚠️ المفاتيح مفقودة."
    genai.configure(api_key=random.choice(keys))
    
    model_name = get_dynamic_model()
    if not model_name: return "عذراً، لا توجد نماذج متاحة."
    
    u = st.session_state.user_data
    
    # جلب الكتاب مع تمرير المرحلة (Stage)
    if not st.session_state.book_content:
        book_text = get_book_text_from_drive(u['stage'], u['grade'], u['lang'])
        if book_text: st.session_state.book_content = book_text

    lang_prompt = "اشرح بالعربية." if "العربية" in u['lang'] else "Explain in English."
    context = ""
    if st.session_state.book_content:
        context = f"استخدم هذا الكتاب للإجابة:\n{st.session_state.book_content[:30000]}..."
    
    quiz_instr = "أنشئ سؤالاً واحداً فقط." if is_quiz_mode else ""
    
    sys_prompt = f"""
    أنت الأستاذ السيد البدوي.
    {context}
    1. التزم بالمنهج.
    2. {lang_prompt}
    3. كن مختصراً (نقاط).
    4. {quiz_instr}
    """
    
    inputs = [sys_prompt, user_text]
    if img_obj: inputs.extend([img_obj, "اشرح الصورة."])

    try:
        model = genai.GenerativeModel(model_name)
        return model.generate_content(inputs).text
    except Exception as e:
        return f"خطأ: {e}"

# ==========================================
# 7. الواجهات والتشغيل
# 
