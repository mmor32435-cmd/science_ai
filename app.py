import streamlit as st
from google.oauth2 import service_account
import google.generativeai as genai
import gspread
from PIL import Image
import random
import speech_recognition as sr
from gtts import gTTS
from streamlit_mic_recorder import mic_recorder
import io
import tempfile

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
# 2. التصميم (CSS)
# ==========================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Cairo', sans-serif; direction: rtl; text-align: right; }
    .stApp { background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%); }
    .header-box {
        background: linear-gradient(90deg, #141E30 0%, #243B55 100%);
        padding: 2rem; border-radius: 15px; color: white; text-align: center; margin-bottom: 2rem;
    }
    .stButton>button { background-color: #243B55; color: white; border-radius: 10px; height: 50px; width: 100%; font-weight: bold; }
    
    /* تنسيق زر الميكروفون */
    .mic-btn { text-align: center; margin: 10px 0; }
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
# 4. دوال الاتصال (Backend)
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
# 5. الصوت والذكاء الاصطناعي
# ==========================================

# دالة تحويل الصوت لنص (للطلاب)
def speech_to_text(audio_bytes):
    r = sr.Recognizer()
    try:
        # تحويل البايتات إلى ملف صوتي مؤقت
        audio_file = io.BytesIO(audio_bytes.read())
        with sr.AudioFile(audio_file) as source:
            audio_data = r.record(source)
            # التعرف على الكلام (يدعم العربية)
            text = r.recognize_google(audio_data, language="ar-EG")
            return text
    except Exception:
        return None

# دالة تحويل النص لصوت (للمعلم)
def text_to_speech(text):
    try:
        # إنشاء ملف صوتي مؤقت
        tts = gTTS(text=text, lang='ar', slow=False)
        # حفظه في ذاكرة مؤقتة
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        return fp
    except:
        return None

def get_best_model():
    try:
        models = genai.list_models()
        chat_models = [m.name for m in models if 'generateContent' in m.supported_generation_methods]
        if not chat_models: return 'models/gemini-1.5-flash'
        for m in chat_models:
            if 'flash' in m.lower(): return m
        for m in chat_models:
            if 'pro' in m.lower() and '1.5' in m.lower(): return m
        return chat_models[0]
    except: return 'models/gemini-1.5-flash'

def get_ai_response(user_text, img_obj=None):
    try:
        keys = st.secrets.get("GOOGLE_API_KEYS", [])
        if not keys: return "⚠️ المفاتيح مفقودة."
        genai.configure(api_key=random.choice(keys))
        
        u = st.session_state.user_data
        lang_prompt = "اشرح بالعربية." if "العربية" in u['lang'] else "Explain in English."
        
        # 🔥 تعديل التعليمات لتكون الإجابة مختصرة ومركزة
        sys_prompt = f"""
        أنت الأستاذ السيد البدوي. الطالب: {u['name']} ({u['stage']}-{u['grade']}).
        
        تعليمات صارمة:
        1. التزم بالمنهج المصري.
        2. {lang_prompt}
        3. ⛔ ممنوع الإجابات الطويلة.
        4. ✅ أعط الإجابة "الخلاصة المختصرة المفيدة" في نقاط محددة (Bullet points).
        5. كن مرحاً ومشجعاً.
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
        st.success(f"مرحباً: {st.session_state.user_data['name']}")
        if st.button("خروج"):
            st.session_state.user_data["logged_in"] = False
            st.rerun()

    st.subheader("💬 اسأل المعلم (صوت أو كتابة)")
    
    # 1. الميكروفون
    col_mic, col_cam = st.columns([1, 1])
    with col_mic:
        st.write("🎙️ اضغط للتحدث:")
        audio = mic_recorder(start_prompt="ابدأ التسجيل", stop_prompt="توقف", key='recorder')
    
    with col_cam:
        with st.expander("📸 إرفاق صورة"):
            f = st.file_uploader("اختر صورة", type=['jpg', 'png'])
            img = Image.open(f) if f else None
            if img: st.image(img, width=150)

    # معالجة الصوت المسجل
    user_input = None
    if audio:
        with st.spinner("جاري تحويل صوتك لنص..."):
            # تحويل البايتات إلى كائن قابل للقراءة
            audio_bio = io.BytesIO(audio['bytes'])
            audio_bio.name = 'audio.wav'
            # استخدام SpeechRecognition
            r = sr.Recognizer()
            try:
                with sr.AudioFile(audio_bio) as source:
                    audio_data = r.record(source)
                    user_input = r.recognize_google(audio_data, language="ar-EG")
            except:
                st.warning("لم أتمكن من سماعك بوضوح، حاول مرة أخرى.")

    # 2. عرض المحادثة السابقة
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            # إذا كانت رسالة المعلم، نعرض زر تشغيل الصوت القديم (اختياري)

    # 3. استقبال المدخلات (كتابة أو صوت)
    prompt = st.chat_input("أو اكتب سؤالك هنا...")
    
    # تحديد مصدر السؤال (كتابة أم صوت)
    final_prompt = prompt if prompt else user_input

    if final_prompt:
        # عرض سؤال الطالب
        st.session_state.messages.append({"role": "user", "content": final_prompt})
        with st.chat_message("user"): st.write(final_prompt)
        
        # معالجة الرد
        with st.chat_message("assistant"):
            with st.spinner("جاري التفكير..."):
                resp_text = get_ai_response(final_prompt, img)
                st.write(resp_text)
                
                # توليد الصوت للإجابة
                audio_fp = text_to_speech(resp_text)
                if audio_fp:
                    st.audio(audio_fp, format='audio/mp3')
        
        st.session_state.messages.append({"role": "assistant", "content": resp_text})

if __name__ == "__main__":
    if st.session_state.user_data["logged_in"]:
        main_app()
    else:
        login_page()
