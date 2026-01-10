import streamlit as st
import nest_asyncio
import threading
import time
from io import BytesIO
from datetime import datetime

# مكتبات Google والوسائط
import google.generativeai as genai
import edge_tts
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder
from PIL import Image
from google.oauth2 import service_account
import gspread
import asyncio

# 1. تفعيل التزامن وإعداد الصفحة
nest_asyncio.apply()
st.set_page_config(page_title="المعلم الذكي", layout="wide")

# 2. حل مشكلة الألوان نهائياً (إجبار الوضع الفاتح)
st.markdown("""
<style>
    /* إجبار الخلفية البيضاء والنص الأسود */
    [data-testid="stAppViewContainer"] {
        background-color: #ffffff;
    }
    [data-testid="stHeader"] {
        background-color: #ffffff;
    }
    [data-testid="stSidebar"] {
        background-color: #f0f2f6;
    }
    /* جعل جميع النصوص سوداء */
    h1, h2, h3, p, span, div, label {
        color: #000000 !important;
    }
    /* تنسيق رسائل الشات */
    .stChatMessage {
        background-color: #f9f9f9;
        border-radius: 10px;
        padding: 10px;
        margin-bottom: 10px;
        border: 1px solid #ddd;
    }
</style>
""", unsafe_allow_html=True)

# 3. إعدادات الجلسة
if "auth" not in st.session_state:
    st.session_state.auth = False
    st.session_state.user = ""
    st.session_state.msgs = []

# 4. دوال الاتصال (تم تبسيطها)
def get_db():
    if "gcp_service_account" not in st.secrets: return None
    try:
        cred = service_account.Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]),
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        return gspread.authorize(cred)
    except: return None

def get_student_pass():
    client = get_db()
    if not client: return None
    try:
        # قراءة الخلية B1 من شيت App_Control
        val = client.open("App_Control").sheet1.acell('B1').value
        return str(val).strip() if val else None
    except: return None

def get_ai():
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys: return None
    import random
    genai.configure(api_key=random.choice(keys))
    # نستخدم الموديل القديم لأنه الأضمن
    return genai.GenerativeModel('gemini-pro')

def get_vision_ai():
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys: return None
    import random
    genai.configure(api_key=random.choice(keys))
    return genai.GenerativeModel('gemini-pro-vision')

# دوال الصوت
async def tts_gen(text):
    # إزالة الرموز قبل القراءة
    text = text.replace("*", "").replace("#", "")
    cm = edge_tts.Communicate(text, "ar-EG-ShakirNeural")
    out = BytesIO()
    async for ch in cm.stream():
        if ch["type"] == "audio": out.write(ch["data"])
    return out

def play_audio(txt):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        aud = loop.run_until_complete(tts_gen(txt[:200]))
        st.audio(aud, format='audio/mp3', autoplay=True)
    except: pass

# ============================
# الشاشة 1: تسجيل الدخول
# ============================
if not st.session_state.auth:
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        st.title("🔐 تسجيل الدخول")
        with st.form("login_form"):
            name = st.text_input("الاسم:")
            code = st.text_input("الكود:", type="password")
            btn = st.form_submit_button("دخول")
            
            if btn:
                real_pass = get_student_pass()
                # كود المعلم الثابت
                is_admin = (code == "ADMIN_2024")
                # كود الطالب من الشيت
                is_student = (real_pass and code == real_pass)
                
                if is_admin or is_student:
                    st.session_state.auth = True
                    st.session_state.user = name
                    st.success("تم الدخول بنجاح")
                    st.rerun()
                else:
                    st.error("الكود غير صحيح أو لا يوجد اتصال")
    st.stop()

# ============================
# الشاشة 2: التطبيق الرئيسي
# ============================
st.sidebar.title(f"مرحباً {st.session_state.user}")
if st.sidebar.button("خروج"):
    st.session_state.auth = False
    st.rerun()

st.title("🧬 المعلم الذكي")

# التبويبات (أدوات)
t1, t2, t3 = st.tabs(["🎙️ صوت", "📝 كتابة", "📷 صورة"])

with t1:
    st.write("تحدث الآن:")
    audio = mic_recorder(start_prompt="🎤 ابدأ", stop_prompt="⏹️ إرسال")
    
    if audio:
        try:
            r = sr.Recognizer()
            audio_data = BytesIO(audio['bytes'])
            with sr.AudioFile(audio_data) as source:
                r.adjust_for_ambient_noise(source)
                voice = r.record(source)
                txt = r.recognize_google(voice, language="ar-EG")
                
            st.success(f"سمعت: {txt}")
            
            # إرسال للذكاء الاصطناعي
            m = get_ai()
            if m:
                reply = m.generate_content(f"رد باختصار: {txt}").text
                st.session_state.msgs.append({"role": "user", "txt": txt})
                st.session_state.msgs.append({"role": "ai", "txt": reply})
                st.rerun()
        except:
            st.error("لم أتمكن من فهم الصوت، حاول مرة أخرى")

with t2:
    q = st.text_input("اكتب سؤالك:")
    if st.button("إرسال") and q:
        m = get_ai()
        if m:
            reply = m.generate_content(f"اشرح: {q}").text
            st.session_state.msgs.append({"role": "user", "txt": q})
            st.session_state.msgs.append({"role": "ai", "txt": reply})
            st.rerun()

with t3:
    up = st.file_uploader("صورة", type=['png','jpg'])
    if up and st.button("تحليل"):
        img = Image.open(up)
        st.image(img, width=200)
        m = get_vision_ai()
        if m:
            reply = m.generate_content(["اشرح الصورة", img]).text
            st.session_state.msgs.append({"role": "user", "txt": "قام برفع صورة"})
            st.session_state.msgs.append({"role": "ai", "txt": reply})
            st.rerun()

# عرض السجل (باستخدام مكونات Streamlit الأصلية)
st.divider()
st.subheader("المحادثة")

# نعكس الترتيب لنرى الأحدث أولاً
for msg in reversed(st.session_state.msgs):
    role = msg["role"]
    txt = msg["txt"]
    
    if role == "user":
        with st.chat_message("user"):
            st.write(txt)
    else:
        with st.chat_message("assistant"):
            st.write(txt)
            # زر صوت فريد
            key = f"btn_{hash(txt)}"
            if st.button("🔊 استمع", key=key):
                play_audio(txt)
