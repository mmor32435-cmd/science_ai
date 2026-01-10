import streamlit as st
import nest_asyncio
import time
import asyncio
import random
import threading
from io import BytesIO
from datetime import datetime

# مكتبات خارجية
import google.generativeai as genai
import edge_tts
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder
from PIL import Image
import PyPDF2
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import gspread
import pandas as pd
import graphviz

# تفعيل التزامن
nest_asyncio.apply()

# 1. إعدادات الصفحة
st.set_page_config(
    page_title="المعلم الذكي", 
    page_icon="🎓", 
    layout="wide"
)

# CSS بسيط ونظيف (أسود وأبيض)
st.markdown("""
<style>
    * { font-family: sans-serif; color: #000000 !important; }
    .stApp { background-color: #ffffff; }
    
    .chat-msg {
        padding: 15px;
        border-radius: 10px;
        margin-bottom: 10px;
        border: 1px solid #ddd;
    }
    .user { background-color: #E3F2FD; text-align: right; }
    .ai { background-color: #F5F5F5; text-align: right; }
</style>
""", unsafe_allow_html=True)

# 2. الثوابت
TEACHER_KEY = "ADMIN_2024"
SHEET_NAME = "App_Control"
# جلب مجلد الدرايف بأمان
SECRETS = st.secrets
DRIVE_ID = SECRETS.get("DRIVE_FOLDER_ID", "")

RANKS = {0: "مبتدئ", 50: "مستكشف", 150: "عبقري"}

# 3. الدوال المساعدة (GSpread)
@st.cache_resource
def get_gspread_client():
    if "gcp_service_account" not in st.secrets:
        return None
    try:
        data = dict(st.secrets["gcp_service_account"])
        scopes = [
            'https://www.googleapis.com/auth/drive',
            'https://www.googleapis.com/auth/spreadsheets'
        ]
        creds = service_account.Credentials.from_service_account_info(
            data, scopes=scopes
        )
        return gspread.authorize(creds)
    except:
        return None

def get_sheet_pass():
    client = get_gspread_client()
    if not client: return None
    try:
        sh = client.open(CONTROL_SHEET_NAME)
        return str(sh.sheet1.acell('B1').value).strip()
    except: return None

# التسجيل في الخلفية
def _log_bg(user, text, type_):
    if "gcp_service_account" not in st.secrets:
        return
    try:
        data = dict(st.secrets["gcp_service_account"])
        scopes = ['https://www.googleapis.com/auth/spreadsheets']
        creds = service_account.Credentials.from_service_account_info(
            data, scopes=scopes
        )
        client = gspread.authorize(creds)
        sh = client.open(SHEET_NAME)
        
        # الوقت
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if type_ == "login":
            try: ws = sh.worksheet("Logs")
            except: ws = sh.sheet1
            ws.append_row([now, "Login", user, text])
            
        elif type_ == "xp":
            try: ws = sh.worksheet("Gamification")
            except: return
            cell = ws.find(user)
            if cell:
                cur = int(ws.cell(cell.row, 2).value or 0)
                ws.update_cell(cell.row, 2, cur + int(text))
            else:
                ws.append_row([user, text])
    except:
        pass

def save_log(user, txt, kind="activity"):
    # تشغيل في خيط منفصل
    t = threading.Thread(target=_log_bg, args=(user, txt, kind))
    t.start()

def add_xp(user, amount):
    if 'xp' in st.session_state:
        st.session_state.xp += amount
    save_log(user, amount, "xp")

# 4. دوال الصوت والذكاء الاصطناعي
def clean_text(text):
    # إزالة الرموز
    for ch in ['*', '#', '-', '`', '>']:
        text = text.replace(ch, ' ')
    return text

async def get_voice_stream(text):
    text = clean_text(text)
    # صوت عربي
    voice = "ar-EG-ShakirNeural"
    comm = edge_tts.Communicate(text, voice)
    out = BytesIO()
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            out.write(chunk["data"])
    return out

def play_audio(text):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        audio = loop.run_until_complete(get_voice_stream(text))
        st.audio(audio, format='audio/mp3', autoplay=True)
    except:
        pass

def get_ai_model():
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys: return None
    
    # خلط المفاتيح
    import random
    random.shuffle(keys)
    
    for k in keys:
        try:
            genai.configure(api_key=k)
            # استخدام الموديل القديم للثبات
            m = genai.GenerativeModel('gemini-pro') 
            return m
        except:
            continue
    return None

def ask_bot(prompt, img=None):
    model = get_ai_model()
    if not model: return "خطأ اتصال"
    
    try:
        if img:
            # رؤية
            vision = genai.GenerativeModel('gemini-pro-vision')
            res = vision.generate_content([prompt, img])
            return res.text
        else:
            # نص
            res = model.generate_content(prompt)
            return res.text
    except Exception as e:
        return f"خطأ: {e}"

# 5. حالة التطبيق
if "auth" not in st.session_state:
    st.session_state.auth = False
    st.session_state.user = ""
    st.session_state.grade = ""
    st.session_state.xp = 0
    st.session_state.msgs = []

# ============================
# الشاشة 1: تسجيل الدخول
# ============================
if not st.session_state.auth:
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        st.title("🔐 تسجيل الدخول")
        
        with st.form("log"):
            name = st.text_input("الاسم:")
            
            # قائمة الصفوف
            opts = ["الرابع", "الخامس", "السادس", "الإعدادي", "الثانوي"]
            grade = st.selectbox("الصف:", opts)
            
            code = st.text_input("الكود:", type="password")
            
            btn = st.form_submit_button("دخول")
            
            if btn:
                # التحقق
                real_pass = get_sheet_pass()
                
                # المعلم
                is_admin = (code == TEACHER_KEY)
                # الطالب
                is_student = (real_pass and code == real_pass)
                
                if is_admin or is_student:
                    # نجاح الدخول
                    st.session_state.auth = True
                    st.session_state.user = name
                    st.session_state.grade = grade # هنا كان الخطأ سابقاً
                    
                    if is_student:
                        save_log(name, grade, "login")
                    
                    st.rerun()
                else:
                    st.error("الكود غير صحيح")
    st.stop()

# ============================
# الشاشة 2: التطبيق الرئيسي
# ============================

# الشريط الجانبي
with st.sidebar:
    st.header(f"👤 {st.session_state.user}")
    
    # حساب الرتبة
    my_rank = "مبتدئ"
    for p, t in RANKS.items():
        if st.session_state.xp >= p:
            my_rank = t
            
    st.success(f"الرتبة: {my_rank}")
    st.info(f"نقاط XP: {st.session_state.xp}")
    
    if st.button("تسجيل خروج"):
        st.session_state.auth = False
        st.rerun()

# العنوان
st.title("🧬 المعلم الذكي")

# التبويبات
tab1, tab2, tab3 = st.tabs(["🎙️ صوت", "📝 كتابة", "📷 صورة"])

# 1. الصوت
with tab1:
    st.write("اضغط للتحدث:")
    audio = mic_recorder(start_prompt="🎤 ابدأ", stop_prompt="⏹️ توقف")
    
    if audio:
        # تحويل الصوت لنص
        r = sr.Recognizer()
        try:
            wav = BytesIO(audio['bytes'])
            with sr.AudioFile(wav) as src:
                r.adjust_for_ambient_noise(src)
                aud_data = r.record(src)
                txt = r.recognize_google(aud_data, language="ar-EG")
                
                st.success(f"أنت قلت: {txt}")
                
                # الرد
                pr = f"اشرح لي بأسلوب مبسط: {txt}"
                ans = ask_bot(pr)
                
                # حفظ وعرض
                st.session_state.msgs.append(("user", txt))
                st.session_state.msgs.append(("ai", ans))
                add_xp(st.session_state.user, 10)
                
        except:
            st.error("لم أفهم الصوت")

# 2. الكتابة
with tab2:
    q = st.text_area("اكتب سؤالك:")
    if st.button("إرسال"):
        if q:
            ans = ask_bot(f"اشرح للطالب: {q}")
            st.session_state.msgs.append(("user", q))
            st.session_state.msgs.append(("ai", ans))
            add_xp(st.session_state.user, 5)

# 3. الصور
with tab3:
    up = st.file_uploader("صورة", type=["jpg", "png"])
    if up and st.button("تحليل"):
        img = 
