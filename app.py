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
import re

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
# 2. تصميم عالي التباين (إصلاح الألوان)
# ==========================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
    
    /* 1. تعميم الخط والاتجاه واللون الأسود */
    html, body, [class*="css"], div, p, span, h1, h2, h3 {
        font-family: 'Cairo', sans-serif !important;
        direction: rtl;
        text-align: right;
    }
    
    /* 2. خلفية التطبيق */
    .stApp {
        background-color: #f4f6f9;
    }
    
    /* 3. إصلاح جذري لألوان الشات (أسود على خلفية فاتحة) */
    .stChatMessage {
        background-color: #ffffff !important;
        border: 1px solid #d1d1d1 !important;
        border-radius: 12px !important;
        padding: 15px !important;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1) !important;
    }
    
    /* إجبار النص داخل الشات أن يكون أسود */
    div[data-testid="stMarkdownContainer"] p {
        color: #000000 !important;
        font-size: 18px !important;
        line-height: 1.6 !important;
    }
    
    /* 4. إصلاح ألوان حقول الإدخال */
    .stTextInput input, .stTextArea textarea {
        color: #000000 !important;
        background-color: #ffffff !important;
        border: 1px solid #004e92 !important;
    }
    
    /* 5. صندوق العنوان */
    .header-box {
        background: linear-gradient(90deg, #141E30 0%, #243B55 100%);
        padding: 2rem;
        border-radius: 15px;
        margin-bottom: 2rem;
        text-align: center;
    }
    .header-box h1, .header-box h3 { color: #ffffff !important; }

    /* 6. الأزرار */
    .stButton>button {
        background-color: #004e92;
        color: #ffffff !important;
        border-radius: 10px;
        height: 50px;
        font-size: 18px;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# بانر العنوان
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
# 5. الصوت والذكاء (تم إصلاح الميكروفون)
# ==========================================

def clean_text_for_speech(text):
    # إزالة الرموز المزعجة عند القراءة
    text = re.sub(r'[\*\#\-\_]', '', text)
    return text

def speech_to_text(audio_bytes):
    r = sr.Recognizer()
    try:
        # حفظ الملف
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
            tmp_file.write(audio_bytes)
            tmp_filename = tmp_file.name
        
        with sr.AudioFile(tmp_filename) as source:
            # ⛔ تم إزالة (adjust_for_ambient_noise) لأنها كانت تحذف الصوت القصير
            # قراءة الصوت مباشرة
            audio_data = r.record(source)
            text = r.recognize_google(audio_data, language="ar-EG")
        
        os.remove(tmp_filename)
        return text
    except:
        return None

async def generate_speech_async(text, voice="ar-EG-ShakirNeural"):
    cleaned_text = clean_text_for_speech(text)
    communicate = edge_tts.Communicate(cleaned_text, voice)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
        await communicate.save(tmp_file.name)
        return tmp_file.name

def text_to_speech_pro(text):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(generate_speech_async(text))
    except: return None

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
        
        sys_prompt = f"""
        أنت الأستاذ السيد البدوي. الطالب: {u['name']} ({u['stage']}-{u['grade']}).
        1. التزم بالمنهج.
        2. {lang_prompt}
        3. كن مختصراً ومفيداً (Brief Summary).
        4. استخدم نقاط (Bullet points).
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
    
    # منطقة الميكروفون والصور
    c_mic, c_img = st.columns([1, 1])
    with c_mic:
        st.info("🎙️ اضغط للتحدث، واضغط مرة أخرى للإرسال:")
        audio = mic_recorder(start_prompt="بدء التسجيل ⏺️", stop_prompt="إرسال ⏹️", key='recorder')
    
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
                st.warning("⚠️ الصوت غير واضح.")

    # عرض الرسائل القديمة (تم حل مشكلة الألوان هنا)
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # الإدخال النصي
    text_input = st.chat_input("اكتب سؤالك...")
    final_q = text_input if text_input else voice_text

    if final_q:
        st.session_state.messages.append({"role": "user", "content": final_q})
        with st.chat_message("user"): st.write(final_q)
        
        with st.chat_message("assistant"):
            with st.spinner("جاري التحضير..."):
                resp_text = get_ai_response(final_q, img)
                st.write(resp_text)
                
                audio_file = text_to_speech_pro(resp_text)
                if audio_file:
                    st.audio(audio_file, format='audio/mp3')
        
        st.session_state.messages.append({"role": "assistant", "content": resp_text})

if __name__ == "__main__":
    if st.session_state.user_data["logged_in"]:
        main_app()
    else:
        login_page()
