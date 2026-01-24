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
# 2. تصميم "المستقبل" (Modern Gradient UI)
# ==========================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
    
    /* 1. الخط العام */
    html, body, [class*="css"] {
        font-family: 'Cairo', sans-serif !important;
        direction: rtl;
        text-align: right;
    }

    /* 2. خلفية التطبيق (تدرج لوني عصري - أزرق سماوي) */
    .stApp {
        background: linear-gradient(135deg, #00c6ff 0%, #0072ff 100%);
        background-attachment: fixed;
    }

    /* 3. البطاقات (Cards) - خلفية بيضاء مع ظلال */
    div[data-testid="stForm"], div[data-testid="stExpander"], .stChatMessage {
        background-color: rgba(255, 255, 255, 0.95) !important;
        border-radius: 20px !important;
        padding: 20px !important;
        box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.15) !important;
        border: 1px solid rgba(255, 255, 255, 0.18) !important;
        color: #000000 !important;
    }

    /* 4. تحسين حقول الإدخال لتكون واضحة جداً */
    .stTextInput input, .stSelectbox div, .stTextArea textarea {
        background-color: #f8f9fa !important;
        color: #000000 !important;
        border: 2px solid #e0e0e0 !important;
        border-radius: 10px !important;
        font-size: 16px !important;
        font-weight: bold !important;
    }
    
    /* التركيز على الحقل */
    .stTextInput input:focus, .stTextArea textarea:focus {
        border-color: #0072ff !important;
        box-shadow: 0 0 5px rgba(0, 114, 255, 0.5);
    }

    /* 5. القوائم المنسدلة (Dropdowns) - إصلاح الاختفاء */
    ul[data-baseweb="menu"] {
        background-color: #ffffff !important;
    }
    li[data-baseweb="option"] {
        color: #000000 !important;
    }
    li[data-baseweb="option"]:hover {
        background-color: #e6f2ff !important;
    }

    /* 6. الأزرار العصرية */
    .stButton>button {
        background: linear-gradient(45deg, #11998e, #38ef7d) !important;
        color: white !important;
        border: none;
        border-radius: 25px;
        height: 55px;
        width: 100%;
        font-size: 20px !important;
        font-weight: bold !important;
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(0,0,0,0.3);
    }

    /* 7. العناوين والنصوص */
    h1, h2, h3, h4, h5, p, label {
        color: #000000 !important; /* أسود داخل البطاقات */
    }
    
    /* استثناء للعنوان الرئيسي في الأعلى ليكون أبيض ليناسب الخلفية الزرقاء */
    .main-title {
        color: #ffffff !important;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        text-align: center;
        font-size: 2.5rem;
        font-weight: bold;
    }
    .sub-title {
        color: #f0f0f0 !important;
        text-align: center;
        margin-bottom: 30px;
    }

    /* 8. مربع الشات السفلي */
    .stChatInput {
        position: fixed;
        bottom: 20px;
        z-index: 1000;
    }
</style>
""", unsafe_allow_html=True)

# عنوان الصفحة الرئيسي (خارج البطاقات)
st.markdown('<div class="main-title">🧬 الأستاذ / السيد البدوي</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">المنصة التعليمية المتطورة (ابتدائي - إعدادي - ثانوي)</div>', unsafe_allow_html=True)

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
# 6. الذكاء الاصطناعي
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
# 7. الواجهات والتشغيل
# ==========================================
def celebrate_success():
    st.balloons()
    st.toast("🌟 ممتاز! أحسنت!", icon="🎉")

def login_page():
    # استخدام أعمدة لتوسيط البطاقة
    col_spacer1, col_main, col_spacer2 = st.columns([1, 6, 1])
    
    with col_main:
        with st.form("login_form"):
            st.markdown("<h3 style='text-align: center;'>🔐 بوابة تسجيل الدخول</h3>", unsafe_allow_html=True)
            st.write("---")
            
            name = st.text_input("الاسم الثلاثي", placeholder="اسمك...")
            code = st.text_input("الكود السري", type="password", placeholder="******")
            
            st.markdown("##### 📝 بياناتك الدراسية")
            col1, col2 = st.columns(2)
            with col1:
                stage = st.selectbox("المرحلة", ["الابتدائية", "الإعدادية", "الثانوية"])
                lang = st.selectbox("لغة الدراسة", ["العربية (علوم)", "English (Science)"])
            with col2:
                grade = st.selectbox("الصف الدراسي", ["الرابع", "الخامس", "السادس", "الأول", "الثاني", "الثالث"])
            
            st.write("")
            submit = st.form_submit_button("🚀 انطلق الآن")
            
            if submit:
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

    st.subheader("💬 غرفة الصف الذكية")
    
    c_mic, c_img = st.columns([1, 1])
    with c_mic:
        st.info("🎙️ تحدث مع المعلم:")
        audio = mic_recorder(start_prompt="تسجيل ⏺️", stop_prompt="إرسال ⏹️", key='recorder', format='wav')
    
    with c_img:
        with st.expander("📸 رفع صورة مسألة"):
            f = st.file_uploader("اختر صورة", type=['jpg', 'png'])
            img = Image.open(f) if f else None
            if img: st.image(img, width=150)

    voice_text = None
    if audio:
        with st.spinner("جاري الاستماع..."):
            voice_text = speech_to_text(audio['bytes'])

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    text_input = st.chat_input("اكتب سؤالك هنا...")
    final_q = text_input if text_input else voice_text

    if final_q:
        st.session_state.messages.append({"role": "user", "content": final_q})
        with st.chat_message("user"): st.write(final_q)
        
        with st.chat_message("assistant"):
            with st.spinner("الأستاذ السيد يكتب..."):
                is_quiz = "اختبار" in final_q or "سؤال" in final_q
                resp_text = get_ai_response(final_q, img, is_quiz_mode=is_quiz)
                st.write(resp_text)
                
                if any(w in resp_text for w in ["أحسنت", "ممتاز", "رائع"]): celebrate_success()
                
                audio_file = text_to_speech_pro(resp_text)
                if audio_file: st.audio(audio_file, format='audio/mp3')
        
        st.session_state.messages.append({"role": "assistant", "content": resp_text})

if __name__ == "__main__":
    if st.session_state.user_data["logged_in"]:
        main_app()
    else:
        login_page()
