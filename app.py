import streamlit as st
import nest_asyncio
from datetime import datetime
import google.generativeai as genai
import edge_tts
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder
from PIL import Image
from google.oauth2 import service_account
import gspread
from io import BytesIO
import asyncio

nest_asyncio.apply()
st.set_page_config(page_title="المعلم الذكي", layout="wide")

# تصميم بسيط وواضح
st.markdown("""
<style>
* { color: black !important; font-family: sans-serif; }
.stApp { background: white; }
.msg { padding: 10px; border-radius: 8px; margin: 5px; border: 1px solid #ddd; }
.user { background: #E3F2FD; text-align: right; }
.bot { background: #F1F8E9; text-align: right; }
</style>
""", unsafe_allow_html=True)

# دوال الاتصال بجوجل شيت (للتأكد من كود الطالب)
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
        # قراءة كلمة سر الطالب من الخلية B1
        return str(client.open("App_Control").sheet1.acell('B1').value).strip()
    except: return None

# الذكاء الاصطناعي
def get_ai(vision=False):
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys: return None
    import random
    genai.configure(api_key=random.choice(keys))
    if vision: return genai.GenerativeModel('gemini-pro-vision')
    return genai.GenerativeModel('gemini-pro')

# الصوت
async def tts_gen(text):
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
# الشاشة 1: تسجيل الدخول (كاملة)
# ============================
if "auth" not in st.session_state:
    st.session_state.auth = False
    st.session_state.msgs = []

if not st.session_state.auth:
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        st.title("🔐 تسجيل الدخول")
        st.info("أهلاً بك في منصة العلوم")
        
        with st.form("login_form"):
            # حقول الإدخال
            name = st.text_input("الاسم:")
            grade = st.selectbox("الصف:", ["الرابع", "الخامس", "السادس", "إعدادي", "ثانوي"])
            code = st.text_input("كود الدخول:", type="password")
            
            # زر الدخول
            submitted = st.form_submit_button("دخول")
            
            if submitted:
                real_student_pass = get_student_pass()
                admin_key = "ADMIN_2024"
                
                is_admin = (code == admin_key)
                is_student = (real_student_pass and code == real_student_pass)
                
                if is_admin or is_student:
                    st.session_state.auth = True
                    st.session_state.user = name
                    st.success("تم الدخول!")
                    st.rerun()
                else:
                    st.error("الكود غير صحيح")
    st.stop()

# ============================
# الشاشة 2: التطبيق
# ============================
st.sidebar.title(f"👤 {st.session_state.user}")
if st.sidebar.button("خروج"):
    st.session_state.auth = False
    st.rerun()

st.title("🧬 المعلم الذكي")

t1, t2, t3 = st.tabs(["🎙️ صوت", "📝 كتابة", "📷 صورة"])

with t1:
    aud = mic_recorder(start_prompt="🎤 تحدث", stop_prompt="⏹️ توقف", key='mic')
    if aud:
        try:
            r = sr.Recognizer()
            src = sr.AudioFile(BytesIO(aud['bytes']))
            with src as s:
                r.adjust_for_ambient_noise(s)
                txt = r.recognize_google(r.record(s), language="ar-EG")
            st.success(f"قلت: {txt}")
            m = get_ai()
            if m:
                ans = m.generate_content(f"اشرح بالعربي: {txt}").text
                st.session_state.msgs.append(("user", txt))
                st.session_state.msgs.append(("bot", ans))
        except: st.error("صوت غير واضح")

with t2:
    q = st.text_input("سؤالك:")
    if st.button("إرسال") and q:
        m = get_ai()
        if m:
            ans = m.generate_content(f"اشرح بالعربي: {q}").text
            st.session_state.msgs.append(("user", q))
            st.session_state.msgs.append(("bot", ans))

with t3:
    up = st.file_uploader("صورة", type=['png','jpg'])
    if up and st.button("تحليل"):
        img = Image.open(up)
        st.image(img, width=150)
        m = get_ai(vision=True)
        if m:
            ans = m.generate_content(["اشرح الصورة", img]).text
            st.session_state.msgs.append(("user", "صورة"))
            st.session_state.msgs.append(("bot", ans))

st.divider()
for role, txt in reversed(st.session_state.msgs):
    cls = "user" if role == "user" else "bot"
    st.markdown(f"<div class='msg {cls}'>{txt}</div>", unsafe_allow_html=True)
    if role == "bot":
        if st.button("🔊", key=str(hash(txt))): play_audio(txt)
