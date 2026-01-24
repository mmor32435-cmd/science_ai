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
# 2. تصميم عالي التباين (إصلاح الألوان جذرياً)
# ==========================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
    
    /* تعميم الخط */
    html, body, [class*="css"] {
        font-family: 'Cairo', sans-serif !important;
        direction: rtl;
        text-align: right;
    }
    
    /* خلفية التطبيق */
    .stApp {
        background-color: #f0f2f6;
    }
    
    /* --- إصلاح ألوان الكتابة (أسود داكن) --- */
    .stTextInput input, .stTextArea textarea, .stSelectbox div, .stNumberInput input {
        color: #000000 !important; /* النص أسود */
        background-color: #ffffff !important; /* الخلفية بيضاء */
        font-weight: bold !important;
        border: 1px solid #aaa !important;
    }
    
    /* إصلاح القوائم المنسدلة */
    div[data-baseweb="select"] > div {
        background-color: #ffffff !important;
        color: #000000 !important;
    }
    
    /* إصلاح النصوص داخل الأيقونات والأزرار */
    .stButton>button {
        background-color: #004e92 !important;
        color: #ffffff !important;
        border-radius: 8px;
        height: 50px;
        font-size: 18px !important;
        font-weight: bold !important;
    }
    
    /* رسائل الشات */
    .stChatMessage {
        background-color: #ffffff !important;
        border: 1px solid #ccc !important;
        color: #000000 !important;
    }
    div[data-testid="stMarkdownContainer"] p {
        color: #000000 !important;
    }

    /* العنوان */
    .header-box {
        background: linear-gradient(90deg, #141E30 0%, #243B55 100%);
        padding: 2rem; border-radius: 15px; margin-bottom: 2rem; text-align: center;
    }
    .header-box h1, .header-box h3 { color: #ffffff !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="header-box">
    <h1>الأستاذ / السيد البدوي</h1>
    <h3>المنصة التعليمية الذكية</h3>
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
def get_book_text_from_drive(grade, lang):
    creds = get_credentials()
    if not creds: return None
    try:
        grade_map = {"الرابع": "Grade4", "الخامس": "Grade5", "السادس": "Grade6", "الأول": "Prep1", "الثاني": "Prep2", "الثالث": "Prep3"}
        lang_code = "Ar" if "العربية" in lang else "En"
        file_prefix = grade_map.get(grade, "Grade4")
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
# 5. الصوت والميكروفون (تم الإصلاح)
# ==========================================
def clean_text_for_speech(text):
    text = re.sub(r'[\*\#\-\_]', '', text)
    return text

def speech_to_text(audio_bytes):
    r = sr.Recognizer()
    try:
        # استخدام BytesIO مباشرة مع صيغة wav
        audio_io = io.BytesIO(audio_bytes)
        with sr.AudioFile(audio_io) as source:
            # تم إزالة calibration لأنه يسبب مشاكل
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
# 6. الذكاء الاصطناعي (ديناميكي بالكامل)
# ==========================================

def get_dynamic_model():
    """
    هذه الدالة تطبق طلبك حرفياً:
    لا تضع اسم موديل ثابت، بل ابحث في القائمة واختر المتاح.
    """
    try:
        # جلب القائمة
        all_models = genai.list_models()
        
        # تصفية النماذج التي تدعم الشات
        valid_models = []
        for m in all_models:
            if 'generateContent' in m.supported_generation_methods:
                valid_models.append(m.name)
        
        if not valid_models:
            # حالة نادرة جداً: لا يوجد أي موديل متاح
            return None
        
        # التفضيل: نبحث عن Flash أولاً، ثم Pro، ثم أي شيء
        for m in valid_models:
            if 'flash' in m.lower(): return m
        
        for m in valid_models:
            if 'pro' in m.lower(): return m
            
        # إذا لم نجد المفضلات، نأخذ أول واحد في القائمة أياً كان اسمه
        return valid_models[0]
        
    except Exception as e:
        return None

def get_ai_response(user_text, img_obj=None, is_quiz_mode=False):
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys: return "⚠️ المفاتيح مفقودة."
    genai.configure(api_key=random.choice(keys))
    
    # 🔥 الخطوة الحاسمة: جلب اسم الموديل المتاح فعلياً 🔥
    model_name = get_dynamic_model()
    if not model_name:
        return "عذراً، لا توجد نماذج ذكاء اصطناعي متاحة حالياً في حسابك."
    
    u = st.session_state.user_data
    if not st.session_state.book_content:
        book_text = get_book_text_from_drive(u['grade'], u['lang'])
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
        return f"حدث خطأ أثناء الاتصال بالنموذج ({model_name}): {e}"

# ==========================================
# 7. التشغيل والواجهات
# ==========================================
def celebrate_success():
    st.balloons()
    st.toast("🌟 ممتاز!", icon="🎉")

def login_page():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### 🔐 تسجيل الدخول")
        with st.form("login"):
            name = st.text_input("الاسم")
            code = st.text_input("الكود", type="password")
            st.markdown("---")
            c1, c2 = st.columns(2)
            with c1:
                stage = st.selectbox("المرحلة", ["الابتدائية", "الإعدادية"])
                lang = st.selectbox("اللغة", ["العربية (علوم)", "English (Science)"])
            with c2:
                grade = st.selectbox("الصف", ["الرابع", "الخامس", "السادس", "الأول", "الثاني", "الثالث"])
            
            if st.form_submit_button("دخول"):
                if code == TEACHER_KEY:
                    st.session_state.user_data.update({"logged_in": True, "role": "Teacher", "name": name})
                    st.rerun()
                elif check_student_code(code):
                    st.session_state.user_data.update({"logged_in": True, "role": "Student", "name": name, "stage": stage, "grade": grade, "lang": lang})
                    st.session_state.book_content = ""
                    st.rerun()
                else:
                    st.error("الكود خطأ")

def main_app():
    with st.sidebar:
        st.success(f"مرحباً: {st.session_state.user_data['name']}")
        if st.button("📝 اختبار سريع"):
             st.session_state.messages.append({"role": "user", "content": "أريد سؤال اختبار."})
        if st.button("🚪 خروج"):
            st.session_state.user_data["logged_in"] = False
            st.rerun()

    st.subheader("💬 اسأل المعلم")
    
    c_mic, c_img = st.columns([1, 1])
    with c_mic:
        st.info("🎙️ اضغط للتحدث:")
        # ضبط الصيغة على wav لحل مشكلة الميكروفون
        audio = mic_recorder(start_prompt="تسجيل ⏺️", stop_prompt="إرسال ⏹️", key='recorder', format='wav')
    
    with c_img:
        with st.expander("📸 إرفاق صورة"):
            f = st.file_uploader("اختر صورة", type=['jpg', 'png'])
            img = Image.open(f) if f else None
            if img: st.image(img, width=150)

    voice_text = None
    if audio:
        with st.spinner("جاري سماعك..."):
            voice_text = speech_to_text(audio['bytes'])
            if not voice_text: st.warning("⚠️ الصوت غير واضح.")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): st.write(msg["content"])

    text_input = st.chat_input("اكتب هنا...")
    final_q = text_input if text_input else voice_text

    if final_q:
        st.session_state.messages.append({"role": "user", "content": final_q})
        with st.chat_message("user"): st.write(final_q)
        
        with st.chat_message("assistant"):
            with st.spinner("جاري التحضير..."):
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
