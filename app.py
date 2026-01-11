import streamlit as st

# ==========================================
# 1. إعدادات الصفحة (يجب أن يكون أول سطر)
# ==========================================
st.set_page_config(
    page_title="AI Science Tutor Pro",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

import time
import asyncio
import re
import random
import threading
from io import BytesIO
from datetime import datetime
import pytz

# المكتبات الخارجية
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
# 2. تهيئة المتغيرات
# ==========================================
# هذا الجزء يضمن وجود قيم افتراضية
if "auth_status" not in st.session_state:
    st.session_state["auth_status"] = False
if "user_name" not in st.session_state:
    st.session_state["user_name"] = "Guest"
if "user_type" not in st.session_state:
    st.session_state["user_type"] = "none"
if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []
if "student_grade" not in st.session_state:
    st.session_state["student_grade"] = ""
if "current_xp" not in st.session_state:
    st.session_state["current_xp"] = 0
if "last_audio_bytes" not in st.session_state:
    st.session_state["last_audio_bytes"] = None
if "language" not in st.session_state:
    st.session_state["language"] = "العربية"
if "ref_text" not in st.session_state:
    st.session_state["ref_text"] = ""
if "q_active" not in st.session_state:
    st.session_state["q_active"] = False
if "q_curr" not in st.session_state:
    st.session_state["q_curr"] = ""

# ==========================================
# 3. الثوابت
# ==========================================
TEACHER_MASTER_KEY = "ADMIN_2024"
CONTROL_SHEET_NAME = "App_Control"
DRIVE_FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "") 

DAILY_FACTS = [
    "هل تعلم؟ المخ يولد كهرباء تكفي لمصباح! 💡",
    "هل تعلم؟ العظام أقوى من الخرسانة بـ 4 مرات! 🦴",
    "هل تعلم؟ الأخطبوط لديه 3 قلوب! 🐙",
    "هل تعلم؟ العسل لا يفسد أبداً! 🍯",
]

# ==========================================
# 4. الخدمات (Backend)
# ==========================================

# --- جداول جوجل ---
@st.cache_resource
def get_gspread_client():
    if "gcp_service_account" not in st.secrets:
        return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        scope = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds)
    except Exception:
        return None

def get_sheet_data():
    client = get_gspread_client()
    if not client:
        return None
    try:
        sheet = client.open(CONTROL_SHEET_NAME)
        val = sheet.sheet1.acell('B1').value
        return str(val).strip()
    except Exception:
        return None

# --- الخلفية (Logs) ---
def _bg_task(task_type, data):
    if "gcp_service_account" not in st.secrets:
        return
    try:
        client = get_gspread_client()
        if not client:
            return
        wb = client.open(CONTROL_SHEET_NAME)
        tz = pytz.timezone('Africa/Cairo')
        now_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

        if task_type == "login":
            try:
                sheet = wb.worksheet("Logs")
            except:
                sheet = wb.add_worksheet("Logs", 1000, 5)
            sheet.append_row([now_str, data['type'], data['name'], data['details']])

        elif task_type == "activity":
            try:
                sheet = wb.worksheet("Activity")
            except:
                sheet = wb.add_worksheet("Activity", 1000, 5)
            clean_text = str(data['text'])[:1000]
            sheet.append_row([now_str, data['name'], data['input_type'], clean_text])

        elif task_type == "xp":
            try:
                sheet = wb.worksheet("Gamification")
            except:
                sheet = wb.add_worksheet("Gamification", 1000, 3)
            try:
                cell = sheet.find(data['name'])
                if cell:
                    val = sheet.cell(cell.row, 2).value
                    curr = int(val) if val else 0
                    sheet.update_cell(cell.row, 2, curr + data['points'])
                else:
                    sheet.append_row([data['name'], data['points']])
            except:
                sheet.append_row([data['name'], data['points']])
    except Exception:
        pass

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
    if not client:
        return 0
    try:
        sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
        cell = sheet.find(user_name)
        if cell:
            val = sheet.cell(cell.row, 2).value
            return int(val) if val else 0
        return 0
    except:
        return 0

def get_leaderboard():
    client = get_gspread_client()
    if not client:
        return []
    try:
        sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        if df.empty:
            return []
        if 'XP' not in df.columns:
            if len(df.columns) >= 2:
                df.columns = ['Student_Name', 'XP'] + list(df.columns[2:])
            else:
                return []
        df['XP'] = pd.to_numeric(df['XP'], errors='coerce').fillna(0)
        return df.sort_values(by='XP', ascending=False).head(5).to_dict('records')
    except Exception:
        return []

# --- جوجل درايف ---
@st.cache_resource
def get_drive_service():
    if "gcp_service_account" not in st.secrets:
        return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/drive.readonly'])
        return build('drive', 'v3', credentials=creds)
    except Exception:
        return None

def list_drive_files(service, folder_id):
    try:
        q = f"'{folder_id}' in parents and trashed = false and mimeType = 'application/pdf'"
        res = service.files().list(q=q, fields="files(id, name)").execute()
        return res.get('files', [])
    except Exception:
        return []

def download_pdf_text(service, file_id):
    try:
        req = service.files().get_media(fileId=file_id)
        fh = BytesIO()
        downloader = MediaIoBaseDownload(fh, req)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        fh.seek(0)
        reader = PyPDF2.PdfReader(fh)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    except Exception:
        return ""

# --- الذكاء الاصطناعي والصوت ---
async def generate_audio_stream(text, voice_code):
    clean = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    clean = re.sub(r'[*#_`\[\]()><=~-]', ' ', clean)
    clean = re.sub(r'http\S+', ' ', clean)
    clean = " ".join(clean.split())
    if not clean:
        return None
    comm = edge_tts.Communicate(clean, voice_code, rate="-2%")
    mp3 = BytesIO()
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            mp3.write(chunk["data"])
    return mp3

def speech_to_text(audio_bytes, lang_code):
    r = sr.Recognizer()
    try:
        with sr.AudioFile(BytesIO(audio_bytes)) as source:
            r.adjust_for_ambient_noise(source, duration=0.5)
            audio_data = r.record(source)
            return r.recognize_google(audio_data, language=lang_code)
    except Exception:
        return None

def get_working_model():
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys:
        return None
    keys_copy = list(keys)
    random.shuffle(keys_copy)
    models = ['gemini-1.5-flash', 'gemini-pro', 'gemini-1.5-pro']
    for key in keys_copy:
        genai.configure(api_key=key)
        for m in models:
            try:
                model = genai.GenerativeModel(m)
                model.generate_content("test")
                return model
            except Exception:
                continue
    return None

def process_ai_response(user_input, input_type="text"):
    user_text_log = user_input if input_type != "image" else "Image Analysis Request"
    log_activity(st.session_state.user_name, input_type, user_text_log)
    
    with st.spinner("🧠 جاري التفكير..."):
        try:
            model = get_working_model()
            if not model:
                st.error("⚠️ خطأ في الاتصال بالذكاء الاصطناعي.")
                return

            lang = st.session_state.language
            ref_text = st.session_state.get("ref_text", "")
            grade = st.session_state.get("student_grade", "General")
            lang_instr = "Arabic" if lang == "العربية" else "English"
            
            base_prompt = (
                f"Act as a Science Tutor for grade {grade}. "
                f"Answer in {lang_instr}. "
                f"Context: {ref_text[:8000]}. "
                "Instructions: Be helpful and clear. "
                "If a diagram helps, use Graphviz DOT code inside ```dot ... ``` block."
            )
            
            response = None
            if input_type == "image":
                response = model.generate_content([base_prompt, user_input[0], user_input[1]])
            else:
                full_prompt = f"{base_prompt}\nStudent: {user_input}"
                response = model.generate_content(full_prompt)
            
            full_text = response.text
            short_q = str(user_text_log)[:50]
            st.session_state.chat_history.append({"role": "user", "content": short_q})
            st.session_state.chat_history.append({"role": "ai", "content": full_text})
            
            parts = full_text.split("```dot")
            display_text = parts[0]
            dot_code = None
            if len(parts) > 1:
                dot_code = parts[1].split("```")[0]
                if len(parts) > 2:
                    display_text += parts[2]

            st.markdown("---")
            with st.chat_message("ai", avatar="🤖"):
                st.write(display_text)
            
            if dot_code:
                try:
                    st.graphviz_chart(dot_code)
                except Exception:
                    pass

            vc = "ar-EG-ShakirNeural" if lang == "العربية" else "en-US-AndrewNeural"
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                audio_bytes = loop.run_until_complete(generate_audio_stream(display_text, vc))
                if audio_bytes:
                    st.audio(audio_bytes, format='audio/mp3', autoplay=True)
            except Exception:
                pass

        except Exception as e:
            st.error(f"حدث خطأ: {e}")

# ==========================================
# 5. واجهة المستخدم (تسجيل الدخول / التطبيق)
# ==========================================

def draw_header():
    st.markdown("""
        <div style='background:linear-gradient(135deg,#667eea,#764ba2);padding:1.5rem;border-radius:15px;text-align:center;color:white;margin-bottom:2rem;'>
            <h1 style='margin:0;'>🧬 AI Science Tutor Pro</h1>
        </div>
    """, unsafe_allow_html=True)

# إضافة زر لإعادة الضبط في الشريط الجانبي (لحل مشكلة اختفاء الدخول)
with st.sidebar:
    if st.button("🔄 إعادة ضبط التطبيق"):
        st.session_state.clear()
        st.rerun()

# 🛑 شاشة تسجيل الدخول
# الشرط هنا: إذا لم يكن مسجلاً للدخول، نعرض الشاشة ونوقف الباقي
if not st.session_state.get("auth_status", False):
    draw_header()
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.info(f"💡 {random.choice(DAILY_FACTS)}")
        
        with st.form("login_form"):
            st.markdown("### 🔐 تسجيل الدخول")
            name = st.text_input("الاسم ثلاثي:")
            grade = st.selectbox("الصف الدراسي:", ["الرابع الابتدائي", "الخامس الابتدائي", "السادس الابتدائي", "الأول الإعدادي", "الثاني الإعدادي", "الثالث الإعدادي", "ثانوي"])
            code = st.text_input("كود الدخول:", type="password")
            
            submitted = st.form_submit_button("دخول 🚀", use_container_width=True)
            
            if submitted:
                if not name or not code:
                    st.warning("الرجاء إدخال البيانات")
                else:
                    db_pass = get_sheet_data()
                    is_teacher = (code == TEACHER_MASTER_KEY)
                    is_student = (db_pass and code == db_pass)
                    
                    if is_teacher or is_student:
                        st.session_state["auth_status"] = True
                        st.session_state["user_type"] = "teacher" if is_teacher else "student"
                        st.session_state["user_name"] = name if is_student else "Mr. Elsayed"
                        st.session_state["student_grade"] = grade
                        
                        if is_student:
                            st.session_state["current_xp"] = get_current_xp(name)
                            log_login(name, "student", grade)
                        st.rerun()
                    else:
                        st.error("الكود غير صحيح")
    
    # أمر مهم جداً: إيقاف تنفيذ باقي الكود إذا لم يسجل الدخول
    st.stop()

# 🟢 ما بعد تسجيل الدخول (التطبيق الرئيسي)
draw_header()

with st.sidebar:
    st.write(f"أهلاً **{st.session_state.user_name}**")
    
    if st.button("🔴 تسجيل خروج"):
        st.session_state.auth_status = False
        st.rerun()
        
    st.session_state.language = st.radio("اللغة:", ["العربية", "English"])
    
    if st.session_state.user_type == "student":
        st.metric("XP", st.session_state.current_xp)
        if st.session_state.current_xp >= 100:
            st.success("🎉 مستوى ممتاز!")
        st.markdown("---")
        st.caption("🏆 المتصدرون")
        for i, r in enumerate(get_leaderboard()):
            st.text(f"{i+1}. {r.get('Student_Name','')} ({r.get('XP',0)})")

    if DRIVE_FOLDER_ID:
        st.divider()
        svc = get_drive_service()
        if svc:
            files = list_drive_files(svc, DRIVE_FOLDER_ID)
            if files:
                bn = st.selectbox("📚 المراجع:", [f['name'] for f in files])
                if st.button("تفعيل"):
                    fid = next(f['id'] for f in files if f['name'] == bn)
                    with st.spinner("جاري التحميل..."):
                        txt = download_pdf_text(svc, fid)
                        if txt:
                            st.session_state.ref_text = txt
                            st.toast("تم تفعيل الكتاب")

tab1, tab2, tab3, tab4 = st.tabs(["🎙️ تحدث", "📝 شات", "📷 صور", "🧠 اختبار"])

with tab1:
    st.write("اضغط للتحدث:")
    aud = mic_recorder(start_prompt="🎤", stop_prompt="⏹️", key='mic')
    if aud and aud['bytes'] != st.session_state.last_audio_bytes:
        st.session_state.last_audio_bytes = aud['bytes']
        lang = "ar-EG" if st.session_state.language == "العربية" else "en-US"
        txt = speech_to_text(aud['bytes'], lang)
        if txt:
            st.info(f"🗣️: {txt}")
            update_xp(st.session_state.user_name, 10)
            process_ai_response(txt, "voice")

with tab2:
    for m in st.session_state.chat_history:
        with st.chat_message(m['role']):
            st.write(m['content'].split("```dot")[0])
    
    q = st.chat_input("سؤالك...")
    if q:
        st.chat_message("user").write(q)
        update_xp(st.session_state.user_name, 5)
        process_ai_response(q, "text")

with tab3:
    up = st.file_uploader("صورة", type=['png','jpg'])
    if up:
        img = Image.open(up)
        st.image(img, width=200)
        p = st.text_input("سؤالك عن الصورة:", "اشرح هذا")
        if st.button("تحليل"):
            update_xp(st.session_state.user_name, 15)
            process_ai_response([p, img], "image")

with tab4:
    if st.button("سؤال جديد"):
        m = get_working_model()
        if m:
            try:
                p = f"1 MCQ science question for {st.session_state.student_grade} in {st.session_state.language}. No answer."
                st.session_state.q_curr 
