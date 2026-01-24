import streamlit as st
from google.oauth2 import service_account
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
import re # مكتبة للتعامل مع النصوص وإزالة الرموز

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
# 2. تصميم الواجهة (إصلاح ألوان الكتابة)
# ==========================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Cairo', sans-serif;
        direction: rtl;
        text-align: right;
    }
    
    /* خلفية زرقاء فاتحة مريحة للعين */
    .stApp {
        background-color: #f0f8ff;
    }
    
    /* صندوق العنوان */
    .header-box {
        background: linear-gradient(90deg, #0f2027 0%, #203a43 50%, #2c5364 100%);
        padding: 2rem;
        border-radius: 15px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
        box-shadow: 0 4px 10px rgba(0,0,0,0.3);
    }
    
    /* إصلاح جذري لمشكلة اختفاء الكتابة */
    /* نجبر الحقول أن تكون بيضاء والنص أسود */
    .stTextInput input {
        color: #000000 !important;
        background-color: #ffffff !important;
        border: 1px solid #ccc;
    }
    .stSelectbox div[data-baseweb="select"] > div {
        color: #000000 !important;
        background-color: #ffffff !important;
    }
    
    /* الأزرار */
    .stButton>button {
        background-color: #2c5364;
        color: white !important;
        border-radius: 8px;
        height: 50px;
        width: 100%;
        font-size: 18px;
        font-weight: bold;
    }
    
    /* رسائل الشات */
    .stChatMessage {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        color: #000000;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="header-box">
    <h1>الأستاذ / السيد البدوي</h1>
    <h3>Mr. Elsayed Elbadawy - Expert Science Tutor</h3>
</div>
""", unsafe_allow_html=True)

# ==========================================
# 3. إدارة الجلسة
# ==========================================
if 'user_data' not in st.session_state:
    st.session_state.user_data = {
        "logged_in": False, "role": None, "name": "", "grade": "", "stage": "", "lang": ""
    }
if 'messages' not in st.session_state: st.session_state.messages = []

# ==========================================
# 4. دوال الاتصال
# ==========================================
TEACHER_KEY = st.secrets.get("TEACHER_MASTER_KEY", "ADMIN")
SHEET_NAME = st.secrets.get("CONTROL_SHEET_NAME", "App_Control")

@st.cache_resource
def get_gspread_client():
    if "gcp_service_account" not in st.secrets: return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds)
    except: return None

def check_student_code(input_code):
    client = get_gspread_client()
    if not client: return False
    try:
        sh = client.open(SHEET_NAME)
        real_code = str(sh.sheet1.acell("B1").value).strip()
        return str(input_code).strip() == real_code
    except: return False

# ==========================================
# 5. معالجة الصوت والذكاء (The Brain)
# ==========================================

# 🧹 دالة تنظيف النص من الرموز (لحل مشكلة نجمة نجمة)
def clean_text_for_speech(text):
    # إزالة النجوم والهاشتاج والشرطات
    clean = re.sub(r'[\*\#\-\_]', '', text)
    # إزالة المسافات الزائدة
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean

# 🎤 دالة الميكروفون (محسنة)
def speech_to_text(audio_bytes):
    r = sr.Recognizer()
    try:
        # حفظ كملف WAV مؤقت
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
            tmp_file.write(audio_bytes)
            tmp_filename = tmp_file.name
        
        with sr.AudioFile(tmp_filename) as source:
            # تقليل الضوضاء
            r.adjust_for_ambient_noise(source, duration=0.5)
            audio_data = r.record(source)
            text = r.recognize_google(audio_data, language="ar-EG")
        
        os.remove(tmp_filename)
        return text
    except:
        return None

# 🔊 دالة تحويل النص لصوت (بصوت شاكر - رجل مصري)
async def generate_speech_async(text, voice="ar-EG-ShakirNeural"):
    # تنظيف النص قبل النطق
    cleaned_text = clean_text_for_speech(text)
    communicate = edge_tts.Communicate(cleaned_text, voice)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
        await communicate.save(tmp_file.name)
        return tmp_file.name

def text_to_speech_pro(text):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        file_path = loop.run_until_complete(generate_speech_async(text))
        return file_path
    except: return None

# 🧠 الذكاء الاصطناعي
def get_best_model():
    try:
        models = genai.list_models()
        chat_models = [m.name for m in models if 'generateContent' in m.supported_generation_methods]
        if not chat_models: return 'models/gemini-1.5-flash'
        for m in chat_models:
            if 'flash' in m.lower(): return m
        return chat_models[0]
    except: return 'models/gemini-1.5-flash'

def get_ai_response(user_text, img_obj=None):
    try:
        keys = st.secrets.get("GOOGLE_API_KEYS", [])
        if not keys: return "⚠️ المفاتيح مفقودة."
        genai.configure(api_key=random.choice(keys))
        
        u = st.session_state.user_data
        lang_prompt = "اشرح بالعربية." if "العربية" in u['lang'] else "Explain in English."
        
        # تعليمات المعلم (الرد المختصر)
        sys_prompt = f"""
        أنت الأستاذ السيد البدوي. الطالب: {u['name']} ({u['stage']}-{u['grade']}).
        1. التزم بالمنهج.
        2. {lang_prompt}
        3. ⛔ الرد يجب أن يكون مختصراً جداً ومركزاً (Concise Summary).
        4. ✅ استخدم نقاط (Bullet points).
        5. تجنب المقدمات الطويلة.
        """
        
        model_name = get_best_model()
        model = genai.GenerativeModel(model_name)
        
        inputs = [sys_prompt, user_text]
        if img_obj: inputs.extend([img_obj, "اشرح الصورة."])
        
        return model.generate_content(inputs).text
    except Exception as e: return f"خطأ: {e}"

# ==========================================
# 6. الواجهات والتشغيل
# ==========================================
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
                stage = st.selectbox("المرحلة", ["الابتدائية", "الإعدادية", "الثانوية"])
                lang = st.selectbox("اللغة", ["العربية", "English"])
            with c2:
                grade = st.selectbox("الصف", ["الرابع", "الخامس", "السادس", "الأول", "الثاني", "الثالث"])
            
            if st.form_submit_button("دخول"):
                if code == TEACHER_KEY:
                    st.session_state.user_data.update({"logged_in": True, "role": "Teacher", "name": name})
                    st.rerun()
                elif check_student_code(code):
                    st.session_state.user_data.update({"logged_in": True, "role": "Student", "name": name, "stage": stage, "grade": grade, "lang": lang})
                    st.rerun()
                else:
                    st.error("الكود خطأ")

def main_app():
    with st.sidebar:
        st.success(f"مرحباً: {st.session_state.user_data['name']}")
        if st.button("خروج"):
            st.session_state.user_data["logged_in"] = False
            st.rerun()

    st.subheader("💬 اسأل المعلم (تحدث أو اكتب)")
    
    c_mic, c_img = st.columns([1, 1])
    with c_mic:
        st.info("🎙️ اضغط للتحدث:")
        audio = mic_recorder(start_prompt="بدء التسجيل ⏺️", stop_prompt="إنهاء ⏹️", key='recorder')
    
    with c_img:
        with st.expander("📸 إرفاق صورة"):
            f = st.file_uploader("اختر صورة", type=['jpg', 'png'])
            img = Image.open(f) if f else None
            if img: st.image(img, width=150)

    # معالجة الصوت
    voice_text = None
    if audio:
        with st.spinner("جاري معالجة الصوت..."):
            voice_text = speech_to_text(audio['bytes'])
            if not voice_text:
                st.warning("⚠️ الصوت غير واضح، يرجى المحاولة مرة أخرى.")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): st.write(msg["content"])

    text_input = st.chat_input("اكتب سؤالك...")
    final_q = text_input if text_input else voice_text

    if final_q:
        st.session_state.messages.append({"role": "user", "content": final_q})
        with st.chat_message("user"): st.write(final_q)
        
        with st.chat_message("assistant"):
            with st.spinner("جاري التحضير..."):
                resp_text = get_ai_response(final_q, img)
                st.write(resp_text)
                
                # الصوت (النظيف)
                audio_file = text_to_speech_pro(resp_text)
                if audio_file:
                    st.audio(audio_file, format='audio/mp3')
        
        st.session_state.messages.append({"role": "assistant", "content": resp_text})

if __name__ == "__main__":
    if st.session_state.user_data["logged_in"]:
        main_app()
    else:
        login_page()
