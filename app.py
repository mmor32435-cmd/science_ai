import streamlit as st
import nest_asyncio
import threading
from io import BytesIO
import google.generativeai as genai
import edge_tts
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder
from PIL import Image

nest_asyncio.apply()
st.set_page_config(page_title="AI Tutor", layout="wide")

st.markdown("""
<style>
* { color: black !important; font-weight: bold; }
.stApp { background-color: white; }
.chat { padding: 10px; border-radius: 5px; margin: 5px; border: 1px solid #ccc; }
.user { background: #e3f2fd; text-align: right; }
.bot { background: #f1f8e9; text-align: right; }
</style>
""", unsafe_allow_html=True)

if "auth" not in st.session_state: st.session_state.auth = False
if "msgs" not in st.session_state: st.session_state.msgs = []

keys = st.secrets.get("GOOGLE_API_KEYS", [])

def get_ai(vision=False):
    if not keys: return None
    import random
    genai.configure(api_key=random.choice(keys))
    if vision: return genai.GenerativeModel('gemini-pro-vision')
    return genai.GenerativeModel('gemini-pro')

async def tts(text):
    comm = edge_tts.Communicate(text, "ar-EG-ShakirNeural")
    out = BytesIO()
    async for chunk in comm.stream():
        if chunk["type"] == "audio": out.write(chunk["data"])
    return out

def play(text):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        audio = loop.run_until_complete(tts(text[:200]))
        st.audio(audio, format='audio/mp3')
    except: pass

if not st.session_state.auth:
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        st.title("🔐 دخول")
        code = st.text_input("الكود:", type="password")
        if st.button("دخول"):
            if code == "ADMIN_2024":
                st.session_state.auth = True
                st.rerun()
            else: st.error("خطأ")
    st.stop()

st.title("🧬 المعلم الذكي")
t1, t2, t3 = st.tabs(["🎙️ صوت", "✍️ كتابة", "📷 صورة"])

with t1:
    audio = mic_recorder(start_prompt="🎤 تحدث", stop_prompt="⏹️ توقف")
    if audio:
        r = sr.Recognizer()
        try:
            src = sr.AudioFile(BytesIO(audio['bytes']))
            with src as s:
                r.adjust_for_ambient_noise(s)
                txt = r.recognize_google(r.record(s), language="ar-EG")
            st.success(txt)
            m = get_ai()
            if m:
                res = m.generate_content(f"رد بالعربي: {txt}").text
                st.session_state.msgs.append(("user", txt))
                st.session_state.msgs.append(("bot", res))
        except: st.error("صوت غير واضح")

with t2:
    q = st.text_input("سؤالك:")
    if st.button("إرسال") and q:
        m = get_ai()
        if m:
            res = m.generate_content(f"اشرح بالعربي: {q}").text
            st.session_state.msgs.append(("user", q))
            st.session_state.msgs.append(("bot", res))

with t3:
    up = st.file_uploader("صورة", type=["png","jpg"])
    if up and st.button("تحليل"):
        img = Image.open(up)
        st.image(img, width=150)
        m = get_ai(vision=True)
        if m:
            res = m.generate_content(["اشرح الصورة بالعربية", img]).text
            st.session_state.msgs.append(("user", "صورة"))
            st.session_state.msgs.append(("bot", res))

st.divider()
for role, txt in reversed(st.session_state.msgs):
    cls = "user" if role == "user" else "bot"
    st.markdown(f"<div class='chat {cls}'>{txt}</div>", unsafe_allow_html=True)
    if role == "bot":
        if st.button("🔊", key=str(hash(txt))): play(txt)
