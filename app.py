import streamlit as st

# ==========================================
# 1. إعدادات الصفحة
# ==========================================
st.set_page_config(page_title="AI Science Tutor Pro", page_icon="🧬", layout="wide")

import time
import re
import random
import threading
from io import BytesIO
from datetime import datetime
import pytz

# المكتبات الخارجية - تحميل بأمان
try:
    import google.generativeai as genai
    import edge_tts
    import asyncio
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
except ImportError as e:
    st.error(f"خطأ في تحميل المكتبات: {e}")
    st.stop()

# ==========================================
# 🎛️ الثوابت
# ==========================================
TEACHER_MASTER_KEY = "ADMIN_2024"
CONTROL_SHEET_NAME = "App_Control"
SESSION_DURATION_MINUTES = 60
DRIVE_FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "") 

DAILY_FACTS = [
    "هل تعلم؟ المخ يولد كهرباء تكفي لمصباح! 💡",
    "هل تعلم؟ العظام أقوى من الخرسانة بـ 4 مرات! 🦴",
    "هل تعلم؟ الأخطبوط لديه 3 قلوب! 🐙",
    "هل تعلم؟ العسل لا يفسد أبداً! 🍯",
]

# ==========================================
# 🛠️ الخدمات الخلفية
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
    if not client: return None
    try:
        sheet = client.open(CONTROL_SHEET_NAME)
        val = sheet.sheet1.acell('B1').value
        return str(val).strip()
    except Exception:
        return None

# --- التسجيل (Logs) ---
def _bg_task(task_type, data):
    if "gcp_service_account" not in st.secrets:
        return

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
            clean_text = str(data['text'])[:1000]
            sheet.append_row([now_str, data['name'], data['input_type'], clean_text])

        elif task_type == "xp":
            try: sheet = wb.worksheet("Gamification")
            except: return
            cell = sheet.find(data['name'])
            if cell:
                val = sheet.cell(cell.row, 2).value
                current_xp = int(val) if val else 0
                sheet.update_cell(cell.row, 2, current_xp + data['points'])
            else:
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
    if not client: return 0
    try:
        sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
        cell = sheet.find(user_name)
        val = sheet.cell(cell.row, 2).value
        return int(val) if val else 0
    except Exception:
        return 0

def get_leaderboard():
    client = get_gspread_client()
    if not client: return []
    try:
        sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        if df.empty: return []
        df['XP'] = pd.to_numeric(df['XP'], errors='coerce').fillna(0)
        return df.sort_values(by='XP', ascending=False).head(5).to_dict('records')
    except Exception:
        return []

# --- Google Drive ---
@st.cache_resource
def get_drive_service():
    if "gcp_service_account" not in st.secrets: return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/drive.readonly'])
        return build('drive', 'v3', credentials=creds)
    except Exception:
        return None

def list_drive_files(service, folder_id):
    try:
        q = f"'{folder_id}' in parents and trashed = false"
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
            text += page.extract_text()
        return text
    except Exception:
        return ""

# ==========================================
# 🔊 الصوت
# ==========================================
async def generate_audio_stream(text, voice_code):
    clean = re.sub(r'[*#_`\[\]()><=]', ' ', text)
    clean = re.sub(r'\\.*', '', clean)
    comm = edge_tts.Communicate(clean, voice_code, rate="-5%")
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

# ==========================================
# 🧠 الذكاء الاصطناعي
# ==========================================
def get_working_model():
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys: return None

    random.shuffle(keys)
    
    # القائمة التي ظهرت في فحصك (الأحدث والأقوى)
    models_to_try = [
        'gemini-2.5-flash',       # الخيار الأول: الأسرع والأحدث
        'gemini-flash-latest',    # الخيار الثاني: مستقر
        'gemini-pro-latest',      # الخيار الثالث: احتياطي قوي
        'gemini-2.0-flash'        # الخيار الرابع
    ]

    for key in keys:
        genai.configure(api_key=key)
        for model_name in models_to_try:
            try:
                model = genai.GenerativeModel(model_name)
                # اختبار سريع
                model.generate_content("ping")
                return model
            except Exception:
                continue
    return None

def process_ai_response(user_text, input_type="text"):
    log_activity(st.session_state.user_name, input_type, user_text)
    
    with st.spinner("🧠 جاري المعالجة..."):
        try:
            model = get_working_model()
            if not model:
                st.error("⚠️ فشل الاتصال. يرجى إعادة تحميل الصفحة.")
                return

            lang = st.session_state.language
            ref = st.session_state.get("ref_text", "")
            grade = st.session_state.get("student_grade", "General")
            
            lang_instr = "Arabic" if lang == "العربية" else "English"
            
            base_prompt = f"""
            Role: Science Tutor. Grade: {grade}.
            Context: {ref[:10000]}
            Instructions: Answer in {lang_instr}. Be helpful.
            If diagram needed, use Graphviz DOT code inside ```dot ... ``` block.
            """
            
            if input_type == "image":
                 resp = model.generate_content([base_prompt, user_text[0], user_text[1]])
            else:
                resp = model.generate_content(f"{base_prompt}\nStudent: {user_text}")
            
            full_text = resp.text
            st.session_state.chat_history.append((str(user_text)[:50], full_text))
            
            # العرض
            disp_text = full_text.split("```dot")[0]
            dot_code = None
            if "```dot" in full_text:
                try:
                    dot_code = full_text.split("```dot")[1].split("```")[0]
                except Exception:
                    pass

            st.markdown("---")
            
            def stream():
                for w in disp_text.split(" "):
                    yield w + " "
                    time.sleep(0.02)
            st.write_stream(stream())
            
            if dot_code:
                try:
                    st.graphviz_chart(dot_code)
                except Exception:
                    pass

            # الصوت
            vc = "ar-EG-ShakirNeural" if lang == "العربية" else "en-US-AndrewNeural"
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                audio = loop.run_until_complete(generate_audio_stream(disp_text[:400], vc))
                st.audio(audio, format='audio/mp3', autoplay=True)
            except Exception:
                pass

        except Exception as e:
            st.error(f"حدث خطأ: {e}")

# ==========================================
# 🎨 الواجهة (UI)
# ==========================================
def draw_header():
    st.markdown("""
        <div style='background:linear-gradient(135deg,#6a11cb,#2575fc);padding:1.5rem;border-radius:15px;text-align:center;color:white;margin-bottom:1rem;'>
            <h1 style='margin:0;'>🧬 AI Science Tutor</h1>
        </div>
    """, unsafe_allow_html=True)

if "auth_status" not in st.session_state:
    st.session_state.update({
        "auth_status": False, "user_type": "none", "chat_history": [],
        "student_grade": "", "current_xp": 0, "last_audio_bytes": None,
        "language": "العربية", "ref_text": ""
    })

# --- تسجيل الدخول ---
if not st.session_state.auth_status:
    draw_header()
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.info(f"💡 {random.choice(DAILY_FACTS)}")
        with st.form("login"):
            name = st.text_input("الاسم:")
            grade = st.selectbox("الصف:", ["الرابع", "الخامس", "السادس", "الأول ع", "الثاني ع", "الثالث ع", "ثانوي"])
            code = st.text_input("الكود:", type="password")
            if st.form_submit_button("دخول"):
                db_pass = get_sheet_data()
                is_teacher = (code == TEACHER_MASTER_KEY)
                is_student = (db_pass and code == db_pass)
                
                if is_teacher or is_student:
                    st.session_state.auth_status = True
                    st.session_state.user_type = "teacher" if is_teacher else "student"
                    st.session_state.user_name = name if is_student else "Mr. Elsayed"
                    st.session_state.student_grade = grade
                    st.session_state.start_time = time.time()
                    if is_student:
                        st.session_state.current_xp = get_current_xp(name)
                        log_login(name, "student", grade)
                    st.success("تم الدخول!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("الكود غير صحيح")
    st.stop()

# --- التطبيق ---
draw_
