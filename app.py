import streamlit as st
import nest_asyncio
import threading
import os
import google.generativeai as genai
import edge_tts
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder
from PIL import Image
from google.oauth2 import service_account
import gspread
import asyncio

# تفعيل التزامن
nest_asyncio.apply()

# 1. إعداد الصفحة
st.set_page_config(page_title="المعلم الذكي", layout="wide")

# تصميم يجبر النصوص على اللون الأسود والخلفية بيضاء
st.markdown("""
<style>
    /* إجبار الوضع الفاتح */
    [data-testid="stAppViewContainer"] { background-color: #ffffff; }
    [data-testid="stSidebar"] { background-color: #f0f2f6; }
    [data-testid="stHeader"] { background-color: #ffffff; }
    
    /* النصوص سوداء */
    h1, h2, h3, p, div, span, label { color: #000000 !important; }
    
    /* رسائل الشات */
    .stChatMessage { background-color: #f8f9fa; border: 1px solid #ddd; }
    
    /* الأزرار */
    .stButton>button { width: 100%; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# 2. تهيئة المتغيرات
if "auth" not in st.session_state:
    st.session_state.auth = False
    st.session_state.user = ""
    st.session_state.grade = ""
    st.session_state.msgs = []

# 3. دوال النظام
def get_db_pass():
    if "gcp_service_account" not in st.secrets: return None
    try:
        cred = service_account.Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]),
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        client = gspread.authorize(cred)
        # جلب القيمة وتنظيف المسافات
        val = client.open("App_Control").sheet1.acell('B1').value
        return str(val).strip() if val else None
    except: return None

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

# 4. إصلاح الميكروفون (الحفظ في ملف مؤقت)
def transribe_audio(audio_bytes):
    r = sr.Recognizer()
    try:
        # حفظ الملف مؤقتاً لحل مشكلة القراءة
        with open("temp_audio.wav", "wb") as f:
            f.write(audio_bytes)
        
        with sr.AudioFile("temp_audio.wav") as source:
            r.adjust_for_ambient_noise(source)
            audio = r.record(source)
            # التعرف على الكلام
            text = r.recognize_google(audio, language="ar-EG")
            return text
    except Exception as e:
        return None

# ============================
# شاشة الدخول
# ============================
if not st.session_state.auth:
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.title("🔐 تسجيل الدخول")
        with st.form("login_form"):
            name = st.text_input("الاسم:")
            # إعادة قائمة الصفوف
            grade = st.selectbox("الصف:", ["الرابع", "الخامس", "السادس", "الإعدادي", "الثانوي"])
            code = st.text_input("الكود:", type="password")
            
            if st.form_submit_button("دخول"):
                real_pass = get_db_pass()
                # التحقق مع إزالة المسافات الزائدة
                user_code = code.strip()
                
                is_admin = (user_code == "ADMIN_2024")
                is_student = (real_pass and user_code == real_pass)
                
                if is_admin or is_student:
                    st.session_state.auth = True
                    st.session_state.user = name
                    st.session_state.grade = grade
                    st.rerun()
                else:
                    st.error("الكود غير صحيح (تأكد من الشيت)")
    st.stop()

# ============================
# التطبيق الرئيسي
# ============================
with st.sidebar:
    st.header(f"الطالب: {st.session_state.user}")
    st.info(f"الصف: {st.session_state.grade}")
    if st.button("خروج"):
        st.session_state.auth = False
        st.rerun()

st.title("🧬 المعلم الذكي")

# التبويبات
tab1, tab2, tab3 = st.tabs(["🎙️ تحدث", "✍️ اكتب", "📸 صور"])

# 1. تبويب الصوت (المصلح)
with tab1:
    st.write("اضغط وسجل سؤالك:")
    audio = mic_recorder(start_prompt="🎤 ابدأ التسجيل", stop_prompt="⏹️ إنهاء", key='mic')
    
    if audio:
        with st.spinner("جاري معالجة الصوت..."):
            text = transribe_audio(audio['bytes'])
            if text:
                st.success(f"سمعتك تقول: {text}")
                # الرد
                m = get_ai()
                if m:
                    res = m.generate_content(f"أجب باختصار: {text}").text
                    st.session_state.msgs.append({"role": "user", "content": text})
                    st.session_state.msgs.append({"role": "ai", "content": res})
                    st.rerun() # تحديث فوري
            else:
                st.error("لم أسمع جيداً، حاول مرة أخرى.")

# 2. تبويب الكتابة
with tab2:
    q = st.text_area("سؤالك:", height=70)
    if st.button("إرسال السؤال"):
        if q:
            m = get_ai()
            if m:
                prompt = f"اشرح لطالب في {st.session_state.grade}: {q}"
                res = m.generate_content(prompt).text
                st.session_state.msgs.append({"role": "user", "content": q})
                st.session_state.msgs.append({"role": "ai", "content": res})
                st.rerun()

# 3. تبويب الصور
with tab3:
    up = st.file_uploader("صورة", type=['jpg','png'])
    if up and st.button("تحليل الصورة"):
        img = Image.open(up)
        st.image(img, width=200)
        m = get_vision_ai()
        if m:
            res = m.generate_content(["اشرح الصورة علمياً", img]).text
            st.session_state.msgs.append({"role": "user", "content": "أرسل صورة"})
            st.session_state.msgs.append({"role": "ai", "content": res})
            st.rerun()

# عرض المحادثة (الأسفل)
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
            
            # زر قراءة الصوت (اختياري لتجنب التعقيد)
            if st.button("🔊 قراءة", key=str(hash(content))):
                async def play():
                    cm = edge_tts.Communicate(content[:200], "ar-EG-ShakirNeural")
                    out = b""
                    async for chunk in cm.stream():
                        if chunk["type"] == "audio": out += chunk["data"]
                    st.audio(out, format='audio/mp3')
                asyncio.run(play())
