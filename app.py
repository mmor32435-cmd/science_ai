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
# 2. التصميم عالي التباين (High Contrast CSS)
# ==========================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Cairo', sans-serif;
        direction: rtl;
        text-align: right;
        color: #000000 !important; /* فرض اللون الأسود للنصوص */
    }
    
    /* خلفية التطبيق */
    .stApp {
        background-color: #f0f2f6;
    }
    
    /* صندوق العنوان */
    .header-box {
        background: linear-gradient(135deg, #004e92 0%, #000428 100%);
        padding: 2rem;
        border-radius: 15px;
        color: #ffffff !important; /* نص أبيض داخل العنوان فقط */
        text-align: center;
        margin-bottom: 2rem;
        box-shadow: 0 4px 10px rgba(0,0,0,0.2);
    }
    .header-box h1, .header-box h3 { color: #ffffff !important; }

    /* تحسين فقاعات الشات لتكون واضحة */
    .stChatMessage {
        background-color: #ffffff;
        border: 1px solid #ddd;
        border-radius: 10px;
        color: #000000 !important;
    }
    
    /* الأزرار */
    .stButton>button {
        background-color: #004e92;
        color: white !important;
        border-radius: 8px;
        height: 50px;
        width: 100%;
        font-weight: bold;
        font-size: 18px;
    }
    .stButton>button:hover { background-color: #003366; }

    /* النصوص داخل الحقول */
    .stTextInput input, .stSelectbox div, .stTextArea textarea {
        color: #000000 !important;
        font-weight: bold;
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
# 5. تقنيات الصوت والذكاء (The Brain)
# ==========================================

# 🎤 دالة تحويل الصوت لنص (تم إصلاحها بملف مؤقت)
def speech_to_text(audio_bytes):
    r = sr.Recognizer()
    try:
        # حفظ الصوت في ملف مؤقت ليتمكن Google Recognizer من قراءته
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
            tmp_file.write(audio_bytes)
            tmp_filename = tmp_file.name
        
        # قراءة الملف
        with sr.AudioFile(tmp_filename) as source:
            audio_data = r.record(source)
            # التعرف (يدعم اللهجة المصرية والسعودية والعربية الفصحى)
            text = r.recognize_google(audio_data, language="ar-EG")
        
        # تنظيف الملف
        os.remove(tmp_filename)
        return text
    except Exception:
        return None

# 🔊 دالة تحويل النص لصوت (بشري واحترافي)
async def generate_speech_async(text, voice="ar-EG-SalmaNeural"):
    communicate = edge_tts.Communicate(text, voice)
    # حفظ في ملف مؤقت
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
        await communicate.save(tmp_file.name)
        return tmp_file.name

def text_to_speech_pro(text):
    # تشغيل الدالة اللامتزامنة
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        file_path = loop.run_until_complete(generate_speech_async(text))
        return file_path
    except Exception:
        return None

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
        
        sys_prompt = f"""
        أنت الأستاذ السيد البدوي. الطالب: {u['name']} ({u['stage']}-{u['grade']}).
        التعليمات:
        1. التزم بالمنهج المصري.
        2. {lang_prompt}
        3. ⛔ كن مختصراً جداً (Brief & Concise).
        4. ✅ استخدم نقاط (Bullet points).
        5. كن مرحاً.
        """
        
        model_name = get_best_model()
        model = genai.GenerativeModel(model_name)
        
        inputs = [sys_prompt, user_text]
        if img_obj: inputs.extend([img_obj, "اشرح الصورة باختصار."])
        
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
        st.success(f"أهلاً: {st.session_state.user_data['name']}")
        if st.button("خروج"):
            st.session_state.user_data["logged_in"] = False
            st.rerun()

    st.subheader("💬 اسأل المعلم (تحدث أو اكتب)")
    
    # منطقة الميكروفون
    c_mic, c_img = st.columns([1, 1])
    with c_mic:
        st.info("🎙️ اضغط للتحدث، واضغط مرة أخرى للإرسال:")
        # هذا الزر يعيد بايتات الصوت
        audio = mic_recorder(start_prompt="تسجيل ⏺️", stop_prompt="إرسال ⏹️", key='recorder')
    
    with c_img:
        with st.expander("📸 إرفاق صورة"):
            f = st.file_uploader("اختر صورة", type=['jpg', 'png'])
            img = Image.open(f) if f else None
            if img: st.image(img, width=150)

    # معالجة الإدخال الصوتي
    voice_text = None
    if audio:
        with st.spinner("جاري سماعك..."):
            voice_text = speech_to_text(audio['bytes'])
            if not voice_text:
                st.warning("⚠️ لم أسمع جيداً، حاول الاقتراب من الميكروفون.")

    # عرض المحادثة
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # الإدخال النصي
    text_input = st.chat_input("اكتب سؤالك...")
    
    # تحديد السؤال النهائي (صوت أو نص)
    final_q = text_input if text_input else voice_text

    if final_q:
        # إضافة السؤال
        st.session_state.messages.append({"role": "user", "content": final_q})
        with st.chat_message("user"): st.write(final_q)
        
        # الإجابة
        with st.chat_message("assistant"):
            with st.spinner("جاري التفكير وتجهيز الرد الصوتي..."):
                # 1. النص
                resp_text = get_ai_response(final_q, img)
                st.write(resp_text)
                
                # 2. الصوت (Edge TTS)
                audio_file = text_to_speech_pro(resp_text)
                if audio_file:
                    st.audio(audio_file, format='audio/mp3')
        
        st.session_state.messages.append({"role": "assistant", "content": resp_text})

if __name__ == "__main__":
    if st.session_state.user_data["logged_in"]:
        main_app()
    else:
        login_page()
