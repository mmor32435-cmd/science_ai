import streamlit as st
import nest_asyncio

# تفعيل المعالجة المتزامنة للصوت
nest_asyncio.apply()

# ==========================================
# 1. إعدادات الصفحة والتصميم عالي التباين
# ==========================================
st.set_page_config(page_title="المعلم الذكي", page_icon="🎓", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@500;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Tajawal', sans-serif;
    }

    /* خلفية التطبيق */
    .stApp {
        background-color: #f4f6f9;
    }

    /* بطاقة المعلم الذكي (الذكاء الاصطناعي) */
    .ai-card {
        background-color: #ffffff;
        color: #000000;  /* لون أسود غامق للقراءة */
        padding: 20px;
        border-radius: 15px;
        border-right: 5px solid #FF5722; /* شريط برتقالي */
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        margin-bottom: 15px;
        direction: rtl;
        text-align: right;
        font-size: 18px;
        line-height: 1.8;
    }

    /* بطاقة الطالب (المستخدم) */
    .user-card {
        background-color: #2196F3;
        color: #ffffff !important; /* لون أبيض ناصع */
        padding: 15px;
        border-radius: 15px;
        border-left: 5px solid #0D47A1;
        margin-bottom: 15px;
        direction: rtl;
        text-align: right;
        font-size: 18px;
    }

    /* العناوين */
    h1, h2, h3 {
        color: #1a237e;
        text-align: center;
    }
    
    /* تنظيف النص داخل البطاقات */
    .ai-card p, .user-card p {
        margin: 0;
    }
</style>
""", unsafe_allow_html=True)

import time
import asyncio
import re
import random
import threading
from io import BytesIO
from datetime import datetime
import pytz

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

# ==========================================
# 🎛️ الثوابت
# ==========================================
TEACHER_MASTER_KEY = "ADMIN_2024"
CONTROL_SHEET_NAME = "App_Control"
DRIVE_FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "") 

DAILY_FACTS = [
    "🧠 هل تعلم؟ المخ لا يشعر بالألم أبداً!",
    "🦈 هل تعلم؟ أسنان القرش تنمو باستمرار طوال حياته!",
    "🌌 هل تعلم؟ عدد النجوم في الفضاء أكثر من حبات الرمل على الأرض!",
]

RANKS = {
    0: "مبتدئ 🌱", 50: "مستكشف 🔭", 150: "مبتكر 💡", 300: "عالم 🔬", 500: "عبقري 🏆"
}

# ==========================================
# 🛠️ الخدمات الخلفية
# ==========================================

@st.cache_resource
def get_gspread_client():
    if "gcp_service_account" not in st.secrets: return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        scope = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds)
    except: return None

def get_sheet_data():
    client = get_gspread_client()
    if not client: return None
    try:
        return str(client.open(CONTROL_SHEET_NAME).sheet1.acell('B1').value).strip()
    except: return None

# --- التسجيل الخلفي ---
def _bg_task(task_type, data):
    if "gcp_service_account" not in st.secrets: return
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        client = gspread.authorize(service_account.Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets']))
        wb = client.open(CONTROL_SHEET_NAME)
        tz = pytz.timezone('Africa/Cairo')
        now_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

        if task_type == "login":
            try: sheet = wb.worksheet("Logs")
            except: sheet = wb.sheet1
            sheet.append_row([now_str, data['type'], data['name'], data['details']])
        elif task_type == "activity":
            try: sheet = wb.worksheet("Activity")
            except: return
            sheet.append_row([now_str, data['name'], data['input_type'], str(data['text'])[:1000]])
        elif task_type == "xp":
            try: sheet = wb.worksheet("Gamification")
            except: return
            cell = sheet.find(data['name'])
            if cell:
                curr = int(sheet.cell(cell.row, 2).value or 0)
                sheet.update_cell(cell.row, 2, curr + data['points'])
            else:
                sheet.append_row([data['name'], data['points']])
    except: pass

def log_login(user_name, user_type, details):
    threading.Thread(target=_bg_task, args=("login", {'name': user_name, 'type': user_type, 'details': details})).start()

def log_activity(user_name, input_type, text):
    threading.Thread(target=_bg_task, args=("activity", {'name': user_name, 'input_type': input_type, 'text': text})).start()

def update_xp(user_name, points):
    if 'current_xp' in st.session_state:
        st.session_state.current_xp += points
    threading.Thread(target=_bg_task, args=("xp", {'name': user_name, 'points': points})).start()

def get_current_xp(user_name):
    client = get_gspread_client()
    if not client: return 0
    try:
        sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
        cell = sheet.find(user_name)
        return int(sheet.cell(cell.row, 2).value or 0) if cell else 0
    except: return 0

def get_leaderboard():
    client = get_gspread_client()
    if not client: return []
    try:
        sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
        df = pd.DataFrame(sheet.get_all_records())
        if df.empty: return []
        df['XP'] = pd.to_numeric(df['XP'], errors='coerce').fillna(0)
        return df.sort_values(by='XP', ascending=False).head(5).to_dict('records')
    except: return []

# --- Google Drive ---
@st.cache_resource
def get_drive_service():
    if "gcp_service_account" not in st.secrets: return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/drive.readonly'])
        return build('drive', 'v3', credentials=creds)
    except: return None

def list_drive_files(service, folder_id):
    try:
        res = service.files().list(q=f"'{folder_id}' in parents and trashed = false", fields="files(id, name)").execute()
        return res.get('files', [])
    except: return []

def download_pdf_text(service, file_id):
    try:
        req = service.files().get_media(fileId=file_id)
        fh = BytesIO()
        downloader = MediaIoBaseDownload(fh, req)
        done = False
        while not done: _, done = downloader.next_chunk()
        fh.seek(0)
        reader = PyPDF2.PdfReader(fh)
        return "".join([p.extract_text() for p in reader.pages])
    except: return ""

# ==========================================
# 🔊 الصوت المطور (Smart Audio Cleaning)
# ==========================================
def clean_text_for_audio(text):
    """
    وظيفة هذه الدالة هي تنظيف النص من الإيموجي والرموز والنجوم
    لكي يقرأ المتحدث الكلمات فقط بشكل سليم.
    """
    # 1. إزالة نجوم التنسيق Markdown (**text**)
    text = text.replace('*', ' ')
    text = text.replace('#', ' ')
    text = text.replace('-', ' ')
    
    # 2. إزالة الإيموجي (طريقة بسيطة: السماح فقط بالحروف والأرقام وعلامات الترقيم)
    # نسمح بالحروف العربية، الإنجليزية، الأرقام، والمسافات والنقاط
    allowed_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,?!،؟:;\n"
    # إضافة النطاق العربي يدوياً
    clean_str = ""
    for char in text:
        # فحص هل الحرف عربي أو من المسموحات
        if ('\u0600' <= char <= '\u06FF') or (char in allowed_chars):
            clean_str += char
        else:
            # استبدال الإيموجي بمسافة صامتة
            clean_str += " "
            
    return clean_str

async def edge_tts_generate(text, voice):
    # تنظيف النص قبل إرساله للصوت
    clean_text = clean_text_for_audio(text)
    communicate = edge_tts.Communicate(clean_text, voice, rate="-2%")
    mp3 = BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3.write(chunk["data"])
    return mp3

def get_audio_bytes(text, lang="Arabic"):
    voice = "ar-EG-ShakirNeural" if lang == "Arabic" else "en-US-AndrewNeural"
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(edge_tts_generate(text, voice))
    except:
        new_loop = asyncio.new_event_loop()
        return new_loop.run_until_complete(edge_tts_generate(text, voice))

def speech_to_text(audio_bytes, lang_code):
    r = sr.Recognizer()
    try:
        with sr.AudioFile(BytesIO(audio_bytes)) as source:
            r.adjust_for_ambient_noise(source, duration=0.5)
            return r.recognize_google(r.record(source), language=lang_code)
    except: return None

# ==========================================
# 🧠 الذكاء الاصطناعي
# ==========================================
def get_working_model():
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys: return None
    random.shuffle(keys)
    models = ['gemini-2.5-flash', 'gemini-flash-latest', 'gemini-2.0-flash', 'gemini-pro']
    
    for key in keys:
        genai.configure(api_key=key)
        for m in models:
            try:
                model = genai.GenerativeModel(m)
                model.generate_content("ping")
                return model
            except: continue
    return None

def get_rank_title(xp):
    title = "مبتدئ"
    for threshold, name in RANKS.items():
        if xp >= threshold: title = name
    return title

# دالة عرض المحادثة (تم تحسين الألوان هنا)
def display_chat(role, text):
    if role == "user":
        st.markdown(f"""
        <div class="user-card">
            <b>👤 الطالب:</b><br>{text}
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="ai-card">
            <b>🤖 المعلم:</b><br>{text}
        </div>
        """, unsafe_allow_html=True)

def process_ai_response(user_text, input_type="text"):
    log_activity(st.session_state.user_name, input_type, user_text)
    
    # عرض سؤال المستخدم إذا لم يكن صوتياً (الصوتي يعرض في التبويب)
    if input_type != "voice":
        display_chat("user", user_text if isinstance(user_text, str) else user_text[0])
    
    with st.spinner("🧠 المعلم يفكر في الإجابة..."):
        try:
            model = get_working_model()
            if not model:
                st.error("⚠️ فشل الاتصال.")
                return

            grade = st.session_state.get("student_grade", "General")
            lang = "Arabic" if st.session_state.language == "العربية" else "English"
            ref = st.session_state.get("ref_text", "")
            
            base_prompt = f"""
            Role: Friendly Science Teacher "Dr. Zewail".
            Student: {st.session_state.user_name} ({grade}).
            Context: {ref[:8000]}
            Instructions: Answer in {lang}. Use simple markdown.
            Format:
            1. **Introduction**: 1 sentence.
            2. **Details**: Bullet points.
            3. **Fun Fact**: 1 sentence.
            No complex symbols.
            """
            
            if input_type == "image":
                 resp = model.generate_content([base_prompt, user_text[0], user_text[1]])
            else:
                resp = model.generate_content(f"{base_prompt}\nStudent: {user_text}")
            
            full_text = resp.text
            
            # العرض
            disp_text = full_text.split("```dot")[0]
            display_chat("ai", disp_text)
            
            # الرسم البياني
            if "```dot" in full_text:
                try: 
                    dot = full_text.split("```dot")[1].split("```")[0]
                    st.graphviz_chart(dot)
                except: pass

            # الصوت (نظيف الآن)
            audio_bytes = get_audio_bytes(disp_text, lang)
            if audio_bytes:
                st.audio(audio_bytes, format='audio/mp3', autoplay=True)

        except Exception as e:
            st.error(f"خطأ: {e}")

# ==========================================
# 🎨 واجهة المستخدم
# ==========================================

if "auth_status" not in st.session_state:
    st.session_state.update({
        "auth_status": False, "user_type": "none", "student_grade": "", 
        "current_xp": 0, "last_audio_bytes": None, "language": "العربية", "ref_text": ""
    })

# الدخول
if not st.session_state.auth_status:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h1 style='text-align:center; color:#1a237e;'>🎓 بوابة العلوم</h1>", unsafe_allow_html=True)
        st.info(random.choice(DAILY_FACTS))
        with st.form("login"):
            name = st.text_input("الاسم:")
            grade = st.selectbox("الصف:", ["الرابع الابتدائي", "الخامس الابتدائي", "السادس الابتدائي", "الأول الإعدادي", "الثاني الإعدادي", "الثالث الإعدادي", "الثانوي"])
            code = st.text_input("الكود:", type="password")
            if st.form_submit_button("دخول"):
                db_pass = get_sheet_data()
                if code == TEACHER_MASTER_KEY or (db_pass and code == db_pass):
                    st.session_state.auth_status = True
                    st.session_state.user_name = name
                    st.session_state.student_grade = grade
                    st.session_state.user_type = "teacher" if code == TEACHER_MASTER_KEY else "student"
                    if st.session_state.user_type == "student":
                        st.session_state.current_xp = get_current_xp(name)
                        log_login(name, "student", grade)
                    st.rerun()
                else: st.error("الكود خطأ")
    st.stop()

# التطبيق
with st.sidebar:
    st.title(f"👤 {st.session_state.user_name}")
    st.info(f"الرتبة: {get_rank_title(st.session_state.current_xp)}")
    st.progress(min(1.0, st.session_state.current_xp/100))
    st.write(f"نقاط: {st.session_state.current_xp}")
    st.divider()
    st.session_state.language = st.radio("اللغة:", ["العربية", "English"])
    
    if DRIVE_FOLDER_ID:
        svc = get_drive_service()
        if svc:
            files = list_drive_files(svc, DRIVE_FOLDER_ID)
            if files:
                st.divider()
                bn = st.selectbox("الكتاب:", [f['name'] for f in files])
                if st.button("تفعيل"):
                    fid = next(f['id'] for f in files if f['name'] == bn)
                    with st.spinner("تحميل..."):
                        txt = download_pdf_text(svc, fid)
                        if txt: st.session_state.ref_text = txt; st.toast("تم!")

st.markdown("<h1 style='text-align:center; color:#1a237e;'>🧬 المعلم الذكي</h1>", unsafe_allow_html=True)

t1, t2, t3, t4 = st.tabs(["🎙️ تحدث", "✍️ اكتب", "📸 صور", "🧠 تحدي"])

with t1:
    c1, c2 = st.columns([1,4])
    with c1:
        # تسجيل الصوت
        aud = mic_recorder(start_prompt="🎤 اضغط للتحدث", stop_prompt="⏹️ إرسال", key='mic_input')
    with c2:
        if aud and aud['bytes'] != st.session_state.last_audio_bytes:
            st.session_state.last_audio_bytes = aud['bytes']
            st.info("جاري سماع الصوت وتحويله لنص...")
            lang_code = "ar-EG" if st.session_state.language == "العربية" else "en-US"
            txt = speech_to_text(aud['bytes'], lang_code)
            if txt:
                st.success(f"سمعت: {txt}")
                display_chat("user", txt)
                update_xp(st.session_state.user_name, 10)
                process_ai_response(txt, "voice")
            else:
                st.warning("لم أسمع جيداً، حاول مرة أخرى.")

with t2:
    q = st.chat_input("اكتب سؤالك...")
    if q:
        update_xp(st.session_state.user_name, 5)
        process_ai_response(q, "text")

with t3:
    up = st.file_uploader("صورة", type=['jpg','png'])
    if up and st.button("تحليل"):
        img = Image.open(up)
        st.image(img, width=200)
        update_xp(st.session_state.user_name, 15)
        process_ai_response(["اشرح الصورة", img], "image")

with t4:
    if st.button("سؤال (20 XP)"):
        m = get_working_model()
        if m:
            try:
                p = f"Generate 1 MCQ science question for {st.session_state.student_grade}. {st.session_state.language}. No answer."
                st.session_state.q_curr = m.generate_content(p).text
                st.session_state.q_active = True
                st.rerun()
            except: st.error("خطأ")
    
    if st.session_state.get("q_active"):
        st.info(st.session_state.q_curr)
        ans = st.text_input("إجابتك:")
        if st.button("تأكيد"):
            m = get_working_model()
            if m:
                res = m.generate_content(f"Q: {st.session_state.q_curr}\nAns: {ans}\nCheck correctness.").text
                st.write(res)
                if "correct" in res.lower() or "صحيح" in res:
                    st.balloons(); update_xp(st.session_state.user_name, 20)
                st.session_state.q_active = False
