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
# 2. تصميم عالي الوضوح والتباين (High Contrast UI)
# ==========================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
    
    /* 1. إعدادات الخط والاتجاه */
    html, body, [class*="css"] {
        font-family: 'Cairo', sans-serif !important;
        direction: rtl;
        text-align: right;
    }

    /* 2. خلفية التطبيق (رمادي فاتح جداً لراحة العين) */
    .stApp {
        background-color: #F5F7FA;
    }

    /* 3. إجبار النصوص العادية على اللون الأسود */
    h1, h2, h3, h4, h5, h6, p, span, label, div {
        color: #1E1E1E !important;
    }

    /* 4. تصميم حقول الإدخال (مهم جداً للوضوح) */
    .stTextInput input, .stSelectbox div[data-baseweb="select"], .stTextArea textarea {
        background-color: #FFFFFF !important; /* خلفية بيضاء */
        color: #000000 !important;           /* نص أسود */
        border: 2px solid #004e92 !important; /* حدود زرقاء واضحة */
        border-radius: 8px !important;
        font-weight: bold !important;
    }

    /* 5. إصلاح القوائم المنسدلة (Dropdown Options) - هذه كانت المشكلة */
    ul[data-baseweb="menu"] {
        background-color: #FFFFFF !important;
    }
    li[data-baseweb="option"] {
        color: #000000 !important;
        background-color: #FFFFFF !important;
    }
    li[data-baseweb="option"]:hover {
        background-color: #E3F2FD !important; /* لون عند المرور */
    }

    /* 6. الأزرار */
    .stButton>button {
        background-color: #004e92 !important;
        color: #FFFFFF !important; /* نص أبيض */
        border: none;
        border-radius: 8px;
        height: 50px;
        font-size: 18px !important;
        font-weight: bold !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.2);
    }
    .stButton>button:hover {
        background-color: #003366 !important;
    }

    /* 7. صندوق العنوان */
    .header-box {
        background: linear-gradient(135deg, #000428 0%, #004e92 100%);
        padding: 2rem;
        border-radius: 15px;
        text-align: center;
        margin-bottom: 2rem;
        border: 2px solid #FFFFFF;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    }
    /* استثناء للعنوان ليكون أبيض */
    .header-box h1, .header-box h3 {
        color: #FFFFFF !important;
    }

    /* 8. فقاعات المحادثة */
    .stChatMessage {
        background-color: #FFFFFF !important;
        border: 1px solid #D1D5DB !important;
        border-radius: 12px !important;
        padding: 15px !important;
    }
</style>
""", unsafe_allow_html=True)

# بانر العنوان
st.markdown("""
<div class="header-box">
    <h1>الأستاذ / السيد البدوي</h1>
    <h3>المنصة التعليمية الذكية (ابتدائي - إعدادي - ثانوي)</h3>
</div>
""", unsafe_allow_html=True)

# ==========================================
# 3. إدارة الجلسة والبيانات
# ==========================================
if 'user_data' not in st.session_state:
    st.session_state.user_data = {"logged_in": False, "role": None, "name": "", "grade": "", "stage": "", "lang": ""}
if 'messages' not in st.session_state: st.session_state.messages = []
if 'book_content' not in st.session_state: st.session_state.book_content = ""

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
    creds = get_credentials()
    if not creds: return None
    try:
        file_prefix = ""
        if "الثانوية" in stage:
            mapping = {"الأول": "Sec1", "الثاني": "Sec2", "الثالث": "Sec3"}
            file_prefix = mapping.get(grade, "Sec1")
        elif "الإعدادية" in stage:
            mapping = {"الأول": "Prep1", "الثاني": "Prep2", "الثالث": "Prep3"}
            file_prefix = mapping.get(grade, "Prep1")
        else: 
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
        for page in pdf_reader.pages[:60]: text += page.extract_text() + "\n"
        return text
    except: return None

# ==========================================
# 4. الصوت والميكروفون
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
# 5. الذكاء الاصطناعي
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
    except Exception as e: return f"خطأ: {e}"

# ==========================================
# 6. الواجهات والتشغيل
# ==========================================
def login_page():
    # استخدام Container لتجميع العناصر بوضوح
    with st.container():
        st.markdown("<h3 style='text-align: center;'>🔐 تسجيل الدخول</h3>", unsafe_allow_html=True)
        
        with st.form("login_form"):
            st.markdown("##### 👤 البيانات الشخصية")
            name = st.text_input("الاسم الثلاثي", placeholder="اكتب اسمك هنا")
            code = st.text_input("الكود السري", type="password", placeholder="******")
            
            st.markdown("---")
            st.markdown("##### 📚 البيانات الدراسية")
            
            col1, col2 = st.columns(2)
            with col1:
                stage = st.selectbox("المرحلة", ["الابتدائية", "الإعدادية", "الثانوية"])
                lang = st.selectbox("اللغة", ["العربية (علوم)", "English (Science)"])
            with col2:
                grade = st.selectbox("الصف الدراسي", ["الرابع", "الخامس", "السادس", "الأول", "الثاني", "الثالث"])
            
            st.write("") # مسافة
            submit_btn = st.form_submit_button("🚀 بدء الرحلة التعليمية")
            
            if submit_btn:
                if code == TEACHER_KEY:
                    st.session_state.user_data.update({"logged_in": True, "role": "Teacher", "name": name})
                    st.rerun()
                elif check_student_code(code):
                    st.session_state.user_data.update({"logged_in": True, "role": "Student", "name": name, "stage": stage, "grade": grade, "lang": lang})
                    st.session_state.book_content = ""
                    st.rerun()
                else:
                    st.error("❌ الكود غير صحيح، حاول مرة أخرى.")

def main_app():
    with st.sidebar:
        st.success(f"مرحباً: {st.session_state.user_data['name']}")
        st.info(f"{st.session_state.user_data['stage']} - {st.session_state.user_data['grade']}")
        
        st.markdown("---")
        if st.button("📝 اختبار سريع"):
             st.session_state.messages.append({"role": "user", "content": "أريد سؤال اختبار."})
        
        if st.button("🚪 تسجيل الخروج"):
            st.session_state.user_data["logged_in"] = False
            st.rerun()

    st.subheader("💬 اسأل المعلم")
    
    col1, col2 = st.columns(2)
    with col1:
        st.info("🎙️ الميكروفون:")
        audio = mic_recorder(start_prompt="تسجيل ⏺️", stop_prompt="إرسال ⏹️", key='recorder', format='wav')
    with col2:
        with st.expander("📸 صورة"):
            f = st.file_uploader("رفع", type=['jpg', 'png'])
            img = Image.open(f) if f else None
            if img: st.image(img, width=150)

    voice_text = None
    if audio:
        with st.spinner("جاري السماع..."):
            voice_text = speech_to_text(audio['bytes'])

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): st.write(msg["content"])

    text_input = st.chat_input("سؤالك...")
    final_q = text_input if text_input else voice_text

    if final_q:
        st.session_state.messages.append({"role": "user", "content": final_q})
        with st.chat_message("user"): st.write(final_q)
        
        with st.chat_message("assistant"):
            with st.spinner("جاري الرد..."):
                is_quiz = "اختبار" in final_q or "سؤال" in final_q
                resp = get_ai_response(final_q, img, is_quiz)
                st.write(resp)
                if any(x in resp for x in ["أحسنت", "ممتاز"]): st.balloons()
                aud = text_to_speech_pro(resp)
                if aud: st.audio(aud, format='audio/mp3')
        st.session_state.messages.append({"role": "assistant", "content": resp})

if __name__ == "__main__":
    if st.session_state.user_data["logged_in"]:
        main_app()
    else:
        login_page()
