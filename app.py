import streamlit as st
import nest_asyncio

# تفعيل المعالجة المتزامنة
nest_asyncio.apply()

# ==========================================
# 1. إعدادات الصفحة (تصميم عالي الوضوح)
# ==========================================
st.set_page_config(page_title="المعلم الذكي", page_icon="🎓", layout="wide")

# CSS لإجبار ظهور النصوص باللون الأسود وتوضيح التبويبات
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@500;800&display=swap');
    
    html, body, [class*="css"], p, h1, h2, h3, div {
        font-family: 'Tajawal', sans-serif;
        color: #000000 !important; /* لون أسود إجباري للنصوص */
    }
    
    /* خلفية التطبيق */
    .stApp {
        background-color: #ffffff;
    }

    /* تحسين شكل التبويبات */
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #f0f2f6;
        border-radius: 10px;
        color: #000000;
        font-weight: bold;
    }
    .stTabs [aria-selected="true"] {
        background-color: #2196F3 !important;
        color: #FFFFFF !important;
    }

    /* إطار للرسائل */
    .chat-box {
        padding: 15px;
        border-radius: 10px;
        margin-bottom: 10px;
        border: 1px solid #ddd;
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
    "هل تعلم؟ قلب الجمبري يقع في رأسه!",
    "هل تعلم؟ الزرافة لا تمتلك أحبالاً صوتية!",
    "هل تعلم؟ العسل هو الطعام الوحيد الذي لا يفسد!",
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
# 🔊 الصوت (نظيف)
# ==========================================
def clean_text_for_audio(text):
    clean = ""
    for char in text:
        if char.isalnum() or char.isspace() or char in ".,?!،؟":
            clean += char
    return clean

async def edge_tts_generate(text, voice):
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
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(edge_tts_generate(text, voice))
    except: return None

def speech_to_text(audio_bytes, lang_code):
    r = sr.Recognizer()
    try:
        audio_file = BytesIO(audio_bytes)
        with sr.AudioFile(audio_file) as source:
            r.adjust_for_ambient_noise(source, duration=0.5)
            audio = r.record(source)
            return r.recognize_google(audio, language=lang_code)
    except: return None

# ==========================================
# 🧠 الذكاء الاصطناعي
# ==========================================
def get_working_model():
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys: return None
    random.shuffle(keys)
    # النماذج الحديثة
    models = ['gemini-2.5-flash', 'gemini-flash-latest', 'gemini-pro']
    
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

def process_ai_response(user_text, input_type="text"):
    # عرض إشعار فقط للمعالجة
    with st.spinner("🧠 المعلم يفكر في الإجابة..."):
        try:
            log_activity(st.session_state.user_name, input_type, user_text)
            model = get_working_model()
            if not model:
                st.error("خطأ في الاتصال.")
                return

            grade = st.session_state.get("student_grade", "General")
            lang = "Arabic" if st.session_state.language == "العربية" else "English"
            ref = st.session_state.get("ref_text", "")
            
            base_prompt = f"""
            Role: Science Tutor. Student Grade: {grade}.
            Context: {ref[:8000]}
            Instructions: Answer in {lang}. Be helpful and clear.
            No bold asterisks in output. Just plain text.
            """
            
            if input_type == "image":
                 resp = model.generate_content([base_prompt, user_text[0], user_text[1]])
            else:
                resp = model.generate_content(f"{base_prompt}\nStudent: {user_text}")
            
            full_text = resp.text
            
            # حفظ في السجل
            st.session_state.chat_history.insert(0, {"role": "ai", "content": full_text})
            st.session_state.chat_history.insert(0, {"role": "user", "content": user_text if isinstance(user_text, str) else "صورة/صوت"})
            
            # تحديث الواجهة
            st.rerun()

        except Exception as e:
            st.error(f"خطأ: {e}")

# ==========================================
# 🎨 واجهة المستخدم (التصميم النظيف)
# ==========================================

if "auth_status" not in st.session_state:
    st.session_state.update({
        "auth_status": False, "user_type": "none", "student_grade": "", 
        "current_xp": 0, "last_audio_bytes": None, "language": "العربية", "ref_text": "",
        "chat_history": []
    })

# --- الدخول ---
if not st.session_state.auth_status:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h1 style='text-align:center;'>🎓 بوابة العلوم</h1>", unsafe_allow_html=True)
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

# --- الشريط الجانبي ---
with st.sidebar:
    st.header(f"👤 {st.session_state.user_name}")
    st.success(f"الرتبة: {get_rank_title(st.session_state.current_xp)}")
    st.write(f"نقاط XP: {st.session_state.current_xp}")
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

# --- المنطقة الرئيسية ---
st.title("🧬 المعلم الذكي")

# التبويبات (الأدوات)
t1, t2, t3, t4 = st.tabs(["🎙️ تحدث", "✍️ اكتب", "📸 صور", "🧠 تحدي"])

with t1:
    st.markdown("### اضغط للتحدث:")
    # تسجيل الصوت
    col_mic, col_res = st.columns([1, 3])
    with col_mic:
        aud = mic_recorder(start_prompt="🎤 اضغط هنا", stop_prompt="⏹️ تم", key='mic_main')
    
    if aud and aud['bytes'] != st.session_state.last_audio_bytes:
        st.session_state.last_audio_bytes = aud['bytes']
        lang_code = "ar-EG" if st.session_state.language == "العربية" else "en-US"
        txt = speech_to_text(aud['bytes'], lang_code)
        
        if txt:
            st.success(f"تم الاستماع: {txt}")
            update_xp(st.session_state.user_name, 10)
            process_ai_response(txt, "voice")
        else:
            st.error("لم أسمع جيداً")

with t2:
    q = st.text_area("اكتب سؤالك:", height=100)
    if st.button("إرسال السؤال"):
        if q:
            update_xp(st.session_state.user_name, 5)
            process_ai_response(q, "text")

with t3:
    up = st.file_uploader("ارفع صورة", type=['jpg','png'])
    if up and st.button("تحليل الصورة"):
        img = Image.open(up)
        st.image(img, width=200)
        update_xp(st.session_state.user_name, 15)
        process_ai_response(["اشرح الصورة", img], "image")

with t4:
    if st.button("🎲 سؤال جديد (20 نقطة)"):
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
        if st.button("تأكيد الإجابة"):
            m = get_working_model()
            if m:
                res = m.generate_content(f"Q: {st.session_state.q_curr}\nAns: {ans}\nCheck correctness.").text
                st.write(res)
                if "correct" in res.lower() or "صحيح" in res:
                    st.balloons(); update_xp(st.session_state.user_name, 20)
                st.session_state.q_active = False

# --- عرض سجل المحادثة (الأسفل) ---
st.divider()
st.markdown("### 🕒 سجل المحادثة")

for chat in st.session_state.chat_history:
    role = chat["role"]
    content = chat["content"]
    
    if role == "user":
        st.markdown(f"""
        <div style="background-color: #2196F3; color: white; padding: 10px; border-radius: 10px; margin-bottom: 5px; text-align: right;">
            👤 <b>أنت:</b> {content}
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="background-color: #f0f2f6; color: black; padding: 10px; border-radius: 10px; margin-bottom: 10px; text-align: right; border: 1px solid #ddd;">
            🤖 <b>المعلم:</b> {content}
        </div>
        """, unsafe_allow_html=True)
        
        # زر تشغيل الصوت لكل رسالة
        clean_key = str(hash(content))
        if st.button("🔊 استمع للإجابة", key=clean_key):
            lang = "Arabic" if st.session_state.language == "العربية" else "English"
            audio_bytes = get_audio_bytes(content[:400], lang)
            if audio_bytes:
                st.audio(audio_bytes, 
