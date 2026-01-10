import streamlit as st
import nest_asyncio
import threading
import os
import google.generativeai as genai
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder
from PIL import Image
import asyncio
import edge_tts

# ==========================================
# 1. إجبار الوضع الفاتح (Light Mode Force)
# ==========================================
st.set_page_config(page_title="المعلم الذكي", layout="wide", initial_sidebar_state="expanded")

# CSS قوي جداً لفرض اللون الأبيض والأسود
st.markdown("""
<style>
    /* إجبار الخلفية البيضاء على كل شيء */
    .stApp, header, footer, .stSidebar {
        background-color: #ffffff !important;
    }
    
    /* إجبار النص الأسود */
    h1, h2, h3, p, label, span, div {
        color: #000000 !important;
    }
    
    /* إصلاح القوائم المنسدلة (Selectbox) */
    div[data-baseweb="select"] > div {
        background-color: #f0f2f6 !important;
        color: #000000 !important;
    }
    
    /* رسائل الشات */
    .stChatMessage {
        background-color: #f9f9f9 !important;
        border: 1px solid #e0e0e0 !important;
    }
</style>
""", unsafe_allow_html=True)

# تفعيل التزامن
nest_asyncio.apply()

# 2. إعدادات الجلسة
if "auth" not in st.session_state:
    st.session_state.auth = False
    st.session_state.user = ""
    st.session_state.msgs = []

# 3. إعدادات الذكاء الاصطناعي
def get_ai():
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys: return None
    import random
    genai.configure(api_key=random.choice(keys))
    return genai.GenerativeModel('gemini-pro')

def get_vision_ai():
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys: return None
    import random
    genai.configure(api_key=random.choice(keys))
    return genai.GenerativeModel('gemini-pro-vision')

# 4. معالجة الصوت (مضمونة)
def transribe_audio(audio_bytes):
    r = sr.Recognizer()
    try:
        with open("temp.wav", "wb") as f:
            f.write(audio_bytes)
        with sr.AudioFile("temp.wav") as source:
            r.adjust_for_ambient_noise(source)
            audio = r.record(source)
            return r.recognize_google(audio, language="ar-EG")
    except: return None

# ==========================================
# شاشة الدخول (المبسطة والمضمونة)
# ==========================================
if not st.session_state.auth:
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.title("🔐 تسجيل الدخول")
        with st.form("login"):
            st.warning("⚠️ ملاحظة: كود الطالب المؤقت هو 12345")
            
            name = st.text_input("الاسم:")
            grade = st.selectbox("الصف:", ["الرابع", "الخامس", "السادس", "الإعدادي", "الثانوي"])
            code = st.text_input("الكود:", type="password")
            
            if st.form_submit_button("دخول"):
                # أكواد ثابتة ومضمونة الآن
                if code == "12345" or code == "ADMIN_2024":
                    st.session_state.auth = True
                    st.session_state.user = name
                    st.session_state.grade = grade
                    st.rerun()
                else:
                    st.error("الكود غير صحيح")
    st.stop()

# ==========================================
# التطبيق الرئيسي
# ==========================================
with st.sidebar:
    st.title(f"👤 {st.session_state.user}")
    st.info(f"الصف: {st.session_state.grade}")
    if st.button("خروج"):
        st.session_state.auth = False
        st.rerun()

st.title("🧬 المعلم الذكي")

# التبويبات
tab1, tab2, tab3 = st.tabs(["🎙️ تحدث", "✍️ اكتب", "📸 صور"])

with tab1:
    st.write("اضغط الميكروفون للتحدث:")
    audio = mic_recorder(start_prompt="🎤 تسجيل", stop_prompt="⏹️ إرسال", key='mic')
    
    if audio:
        with st.spinner("جاري التحليل..."):
            txt = transribe_audio(audio['bytes'])
            if txt:
                st.success(f"سمعت: {txt}")
                m = get_ai()
                if m:
                    res = m.generate_content(f"رد باختصار: {txt}").text
                    st.session_state.msgs.append({"role": "user", "content": txt})
                    st.session_state.msgs.append({"role": "ai", "content": res})
                    st.rerun()
            else:
                st.error("صوت غير واضح")

with tab2:
    q = st.text_area("سؤالك:", height=70)
    if st.button("إرسال"):
        if q:
            m = get_ai()
            if m:
                res = m.generate_content(f"اشرح للطالب: {q}").text
                st.session_state.msgs.append({"role": "user", "content": q})
                st.session_state.msgs.append({"role": "ai", "content": res})
                st.rerun()

with tab3:
    up = st.file_uploader("صورة", type=['jpg','png'])
    if up and st.button("تحليل"):
        img = Image.open(up)
        st.image(img, width=200)
        m = get_vision_ai()
        if m:
            res = m.generate_content(["اشرح الصورة", img]).text
            st.session_state.msgs.append({"role": "user", "content": "صورة"})
            st.session_state.msgs.append({"role": "ai", "content": res})
            st.rerun()

# عرض السجل
st.divider()
for msg in reversed(st.session_state.msgs):
    role = msg["role"]
    content = msg["content"]
    
    if role == "user":
        with st.chat_message("user"):
            st.write(content)
    else:
        with st.chat_message("assistant"):
            st.write(content)
            # زر قراءة
            if st.button("🔊", key=str(hash(content))):
                async def play():
                    cm = edge_tts.Communicate(content[:200], "ar-EG-ShakirNeural")
                    out = b""
                    async for chunk in cm.stream():
                        if chunk["type"] == "audio": out += chunk["data"]
                    st.audio(out, format='audio/mp3', autoplay=True)
                asyncio.run(play())
