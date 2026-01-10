import streamlit as st

# ==========================================
# 1. إعدادات الصفحة (يجب أن تكون في السطر الأول)
# ==========================================
st.set_page_config(page_title="AI Science Tutor Pro", page_icon="🧬", layout="wide")

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
# 🎛️ الثوابت والإعدادات
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
    "هل تعلم؟ سرعة الضوء 300,000 كم/ث! ⚡"
]

# ==========================================
# 🛠️ الخدمات الخلفية (Backend Services)
# ==========================================

# --- خدمة جداول جوجل ---
@st.cache_resource
def get_gspread_client():
    if "gcp_service_account" not in st.secrets:
        return None
    try:
        # تحويل Secrets إلى قاموس عادي لضمان التوافق
        creds_dict = dict(st.secrets["gcp_service_account"])
        scope = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds)
    except Exception as e:
        return None

def get_sheet_data():
    client = get_gspread_client()
    if not client: return None
    try:
        sheet = client.open(CONTROL_SHEET_NAME)
        # محاولة قراءة الخلية B1 (كلمة السر)
        val = sheet.sheet1.acell('B1').value
        return str(val).strip()
    except: return None

def update_daily_password(new_pass):
    client = get_gspread_client()
    if not client: return False
    try:
        client.open(CONTROL_SHEET_NAME).sheet1.update_acell('B1', new_pass)
        return True
    except: return False

# --- التسجيل والأنشطة (Background Tasks) ---
def _bg_task(task_type, data):
    """دالة موحدة تعمل في الخلفية لتسجيل البيانات في جوجل شيت"""
    try:
        if "gcp_service_account" not in st.secrets: return
        creds_dict = dict(st.secrets["gcp_service_account"])
        scope = ['https://www.googleapis.com/auth/spreadsheets']
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        
        tz = pytz.timezone('Africa/Cairo')
        now_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            wb = client.open(CONTROL_SHEET_NAME)
        except: return

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
    except Exception as e:
        print(f"BG Error: {e}")

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
        return int(sheet.cell(cell.row, 2).value) if cell else 0
    except: return 0

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
    except: return []

# --- جوجل درايف ---
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
        query = f"'{folder_id}' in parents and trashed = false"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        return results.get('files', [])
    except: return []

def download_pdf_text(service, file_id):
    try:
        request = service.files().get_media(fileId=file_id)
        fh = BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        fh.seek(0)
        reader = PyPDF2.PdfReader(fh)
        return "".join([page.extract_text() for page in reader.pages])
    except: return ""

# ==========================================
# 🔊 الصوت (TTS & STT)
# ==========================================
async def generate_audio_stream(text, voice_code):
    # تنظيف النص لإزالة الرموز التي تعيق القراءة
    clean_text = re.sub(r'[*#_`\[\]()><=]', ' ', text)
    clean_text = re.sub(r'\\.*', '', clean_text)
    
    communicate = edge_tts.Communicate(clean_text, voice_code, rate="-5%")
    mp3 = BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3.write(chunk["data"])
    return mp3

def speech_to_text(audio_bytes, lang_code):
    r = sr.Recognizer()
    try:
        with sr.AudioFile(BytesIO(audio_bytes)) as source:
            r.adjust_for_ambient_noise(source, duration=0.5)
            audio = r.record(source)
            return r.recognize_google(audio, language=lang_code)
    except: return None

# ==========================================
# 🧠 الذكاء الاصطناعي (Robust Model Selector)
# ==========================================
def get_working_model():
    """
    هذه الدالة هي الحل لمشكلة 404.
    تقوم بتجربة المفاتيح والنماذج بالترتيب حتى تجد واحداً يعمل.
    """
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys and "GOOGLE_API_KEY" in st.secrets:
        keys = [st.secrets["GOOGLE_API_KEY"]]
    
    if not keys: return None

    random.shuffle(keys)
    
    # قائمة النماذج: الأحدث أولاً، ثم الأقدم كخطة بديلة
    models_to_try = [
        'gemini-1.5-flash',
        'gemini-1.5-flash-latest',
        'gemini-1.5-pro',
        'gemini-pro'  # هذا النموذج يعمل دائماً إذا فشلت النماذج الجديدة
    ]

    for key in keys:
        genai.configure(api_key=key)
        for model_name in models_to_try:
            try:
                model = genai.GenerativeModel(model_name)
                # اختبار اتصال سريع (Ping)
                model.generate_content("Hi")
                return model # إذا نجح، أعد هذا النموذج
            except Exception:
                continue # جرب النموذج التالي
    return None

def process_ai_response(user_text, input_type="text"):
    log_activity(st.session_state.user_name, input_type, user_text)
    
    with st.spinner("🧠 جاري التفكير..."):
        try:
            model = get_working_model()
            if not model:
                st.error("عذراً، لم أتمكن من الاتصال بالذكاء الاصطناعي. تأكد من الإنترنت أو المفاتيح.")
                return

            lang_pref = st.session_state.language
            ref = st.session_state.get("ref_text", "")
            s_grade = st.session_state.get("student_grade", "General")
            
            # إعدادات اللغة
            lang_instr = "Answer in Arabic." if lang_pref == "العربية" else "Answer in English."
            
            # بناء السؤال (Prompt)
            base_prompt = f"""
            Role: Helpful Science Tutor. Student Grade: {s_grade}.
            Context from Book: {ref[:10000]}
            Instructions: {lang_instr} Use emojis. Be concise.
            If asked for a diagram, use Graphviz DOT code inside ```dot ... ```.
            """
            
            response = None
            if input_type == "image":
                 # user_text = [prompt, image_object]
                 response = model.generate_content([base_prompt, user_text[0], user_text[1]])
            else:
                response = model.generate_content(f"{base_prompt}\nStudent: {user_text}")
            
            full_text = response.text
            st.session_state.chat_history.append((str(user_text)[:50], full_text))
            
            # معالجة النص والرسم
            display_text = full_text
            dot_code = None
            
            if "```dot" in full_text:
                parts = full_text.split("```dot")
                display_text = parts[0]
                if len(parts) > 1:
                    dot_code = parts[1].split("```")[0].strip()

            st.markdown("---")
            
            # تأثير الكتابة المتدفق
            def stream():
                for word in display_text.split(" "):
                    yield word + " "
                    time.sleep(0.02)
            st.write_stream(stream())
            
            if dot_code:
                try: st.graphviz_chart(dot_code)
                except: pass

            # الصوت
            vc = "ar-EG-ShakirNeural" if lang_pref == "العربية" else "en-US-AndrewNeural"
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                # نقرأ جزءاً من النص لتسريع الاستجابة
                audio_data = loop.run_until_complete(generate_audio_stream(display_text[:400], vc))
                st.audio(audio_data, format='audio/mp3', autoplay=True)
            except Exception as e:
                print(f"Audio Error: {e}")

        except Exception as e:
            st.error(f"حدث خطأ: {e}")

# ==========================================
# 🎨 واجهة المستخدم (UI)
# ==========================================

def draw_header():
    st.markdown("""
        <div style='background:linear-gradient(135deg,#667eea,#764ba2);padding:1.5rem;border-radius:15px;text-align:center;color:white;margin-bottom:1rem;box-shadow: 0 4px 6px rgba(0,0,0,0.1);'>
            <h1 style='margin:0;font-size: 2rem;'>🧬 AI Science Tutor</h1>
            <p style='margin:5px;opacity:0.9;'>Mr. Elsayed Elbadawy</p>
        </div>
    """, unsafe_allow_html=True)

# تهيئة المتغيرات
if "auth_status" not in st.session_state:
    st.session_state.update({
        "auth_status": False, "user_type": "none", "chat_history": [],
        "student_grade": "", "study_lang": "", "quiz_active": False,
        "current_quiz_question": "", "current_xp": 0, "last_audio_bytes": None,
        "language": "العربية", "ref_text": ""
    })

# --- شاشة الدخول ---
if not st.session_state.auth_status:
    draw_header()
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.info(f"💡 معلومة اليوم: {random.choice(DAILY_FACTS)}")
        with st.form("login"):
            name = st.text_input("الاسم:")
            grade = st.selectbox("الصف:", ["الرابع الابتدائي", "الخامس الابتدائي", "السادس الابتدائي", "الأول الإعدادي", "الثاني الإعدادي", "الثالث الإعدادي", "الثانوي"])
            code = st.text_input("الكود:", type="password")
            
            if st.form_submit_button("تسجيل الدخول", use_container_width=True):
                db_pass = get_sheet_data()
                
                # التحقق: المعلم أو الطالب
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
                        
                    st.success("تم الدخول بنجاح! 🚀")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("الكود غير صحيح!")
    st.stop()

# --- التحقق من وقت الجلسة ---
if st.session_state.user_type == "student":
    elapsed = (time.time() - st.session_state.start_time) / 60
    if elapsed > SESSION_DURATION_MINUTES:
        st.error("انتهى وقت الجلسة.")
        st.stop()

# --- واجهة التطبيق ---
draw_header()

with st.sidebar:
    st.write(f"مرحباً **{st.session_state.user_name}** 👋")
    st.session_state.language = st.radio("اللغة:", ["العربية", "English"])
    
    if st.session_state.user_type == "student":
        st.metric("نقاط XP", st.session_state.current_xp)
        if st.session_state.current_xp >= 100:
            st.success("🎉 مبروك! لقد وصلت لـ 100 نقطة")
        
        st.markdown("---")
        st.caption("🏆 المتصدرون")
        for i, row in enumerate(get_leaderboard()):
            st.text(f"{i+1}. {row['Student_Name']} ({row['XP']})")

    # تحميل الكتب
    if DRIVE_FOLDER_ID:
        svc = get_drive_service()
        if svc:
            files = list_drive_files(svc, DRIVE_FOLDER_ID)
            if files:
                st.markdown("---")
                st.caption("📚 المنهج الدراسي")
                book_name = st.selectbox("اختر الكتاب:", [f['name'] for f in files])
                if st.button("تفعيل الكتاب"):
                    fid = next(f['id'] for f in files if f['name'] == book_name)
                    with st.spinner("جاري التحميل..."):
                        txt = download_pdf_text(svc, fid)
                        if txt:
                            st.session_state.ref_text = txt
                            st.toast("تم تفعيل الكتاب بنجاح!")

# التبويبات
tab_voice, tab_text, tab_img, tab_quiz = st.tabs(["🎙️ تحدث", "📝 كتابة", "📷 صورة", "🧠 اختبار"])

with tab_voice:
    st.info("اضغط وتحدث:")
    audio = mic_recorder(start_prompt="🎤 اضغط للتحدث", stop_prompt="⏹️ إنهاء", key='mic')
    if audio and audio['bytes'] != st.session_state.last_audio_bytes:
        st.session_state.last_audio_bytes = audio['bytes']
        lang_code = "ar-EG" if st.session_state.language == "العربية" else "en-US"
        text = speech_to_text(audio['bytes'], lang_code)
        if text:
            st.chat_message("user").write(text)
            update_xp(st.session_state.user_name, 10)
            process_ai_response(text, "voice")

with tab_text:
    q = st.chat_input("اكتب سؤالك هنا...")
    if q:
        st.chat_message("user").write(q)
        update_xp(st.session_state.user_name, 5)
        process_ai_response(q, "text")

with tab_img:
    up = st.file_uploader("ارفع صورة سؤال أو مخطط", type=['png', 'jpg'])
    p = st.text_input("ما هو سؤالك عن الصورة؟")
    if st.button("تحليل الصورة") and up:
        img = Image.open(up)
        st.image(img, width=200)
        prompt = p if p else "اشرح هذه الصورة بالتفصيل"
        update_xp(st.session_state.user_name, 15)
        process_ai_response([prompt, img], "image")

with tab_quiz:
    if st.button("🎲 سؤال عشوائي"):
        model = get_working_model()
        if model:
            try:
                p = f"Generate 1 MCQ science question for {st.session_state.student_grade}. {st.session_state.language}. No answer."
                r = model.generate_content(p)
                st.session_state.current_quiz_question = r.text
                st.session_state.quiz_active = True
                st.rerun()
            except: st.error("حاول مرة أخرى")

    if st.session_state.quiz_active:
        st.markdown("---")
        st.write(st.session_state.current_quiz_question)
        ans = st.text_input("إجابتك:")
        if st.button("تأكيد"):
            model = get_working_model()
            if model:
                chk = f"Q: {st.session_state.current_quiz_question}\nAns: {ans}\nCheck if correct."
                res = model.generate_content(chk)
                st.write(res.text)
                if "correct" in res.text.lower() or "صحيح" in res.text:
                    st.balloons()
                    update_xp(st.session_state.user_name, 50)
                st.session_state.quiz_active = False
