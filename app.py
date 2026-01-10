import streamlit as st

# ==========================================
# 1. إعدادات الصفحة (يجب أن تكون في أول سطر)
# ==========================================
st.set_page_config(page_title="AI Science Tutor Pro", page_icon="🧬", layout="wide")

# ==========================================
# 2. استيراد المكتبات
# ==========================================
import time
import asyncio
import re
import random
import threading
from io import BytesIO
from datetime import datetime
import pytz

# مكتبات الذكاء الاصطناعي والخدمات
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

# --- التسجيل والتلعيب (Gamification) ---
def _bg_task(task_type, data):
    """دالة واحدة للتعامل مع العمليات الخلفية"""
    try:
        if "gcp_service_account" not in st.secrets: return
        creds_dict = dict(st.secrets["gcp_service_account"])
        scope = ['https://www.googleapis.com/auth/spreadsheets']
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        
        tz = pytz.timezone('Africa/Cairo')
        now_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        
        wb = client.open(CONTROL_SHEET_NAME)

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
# 🔊 الصوت
# ==========================================
async def generate_audio_stream(text, voice_code):
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
# 🧠 الذكاء الاصطناعي (تم حل مشكلة 404 هنا)
# ==========================================
def get_gemini_model():
    """يحاول العثور على أي نموذج يعمل لتجنب التوقف"""
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys and "GOOGLE_API_KEY" in st.secrets:
        keys = [st.secrets["GOOGLE_API_KEY"]]
    
    if not keys: return None

    # خلط المفاتيح لتوزيع الحمل
    random.shuffle(keys)
    
    # قائمة النماذج التي سنجربها بالترتيب
    # نبدأ بالأسرع (Flash) وإذا فشل نعود للأقدم (Pro)
    candidate_models = [
        'gemini-1.5-flash',
        'gemini-1.5-flash-001',
        'gemini-1.5-pro',
        'gemini-pro'
    ]

    for key in keys:
        genai.configure(api_key=key)
        for model_name in candidate_models:
            try:
                model = genai.GenerativeModel(model_name)
                # تجربة وهمية سريعة للتأكد أن النموذج متاح
                model.generate_content("test")
                return model
            except Exception:
                continue # جرب النموذج التالي
    return None

def process_ai_response(user_text, input_type="text"):
    log_activity(st.session_state.user_name, input_type, user_text)
    
    with st.spinner("🧠 جاري التفكير..."):
        try:
            model = get_gemini_model()
            if not model:
                st.error("عذراً، الخدمة مشغولة حالياً أو مفاتيح API غير صالحة.")
                return

            lang_pref = st.session_state.language
            ref = st.session_state.get("ref_text", "")
            s_grade = st.session_state.get("student_grade", "General")
            
            # بناء التوجيه (Prompt)
            lang_instr = "Answer in Arabic." if lang_pref == "العربية" else "Answer in English."
            base_prompt = f"""
            Role: Science Tutor. Student Grade: {s_grade}.
            Context from Book: {ref[:10000]}
            Instructions: {lang_instr} Be concise, clear, and encouraging.
            If the user asks for a diagram/map, output Graphviz DOT code inside ```dot ... ``` block.
            """
            
            response = None
            if input_type == "image":
                 # user_text = [prompt, image]
                 response = model.generate_content([base_prompt, user_text[0], user_text[1]])
            else:
                response = model.generate_content(f"{base_prompt}\nQuestion: {user_text}")
            
            full_text = response.text
            st.session_state.chat_history.append((str(user_text)[:50], full_text))
            
            # فصل الرسم البياني
            display_text = full_text
            dot_code = None
            if "```dot" in full_text:
                parts = full_text.split("```dot")
                display_text = parts[0]
                if len(parts) > 1:
                    dot_code = parts[1].split("```")[0].strip()

            # عرض النص
            st.markdown("---")
            
            # تأثير الكتابة
            def text_stream():
                for word in display_text.split(" "):
                    yield word + " "
                    time.sleep(0.02)
            st.write_stream(text_stream())
            
            # عرض الرسم البياني
            if dot_code:
                try: st.graphviz_chart(dot_code)
                except: pass

            # تشغيل الصوت (تم إصلاح مشكلة التزامن)
            vc = "ar-EG-ShakirNeural" if lang_pref == "العربية" else "en-US-AndrewNeural"
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
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
        <div style='background:linear-gradient(120deg,#2980b9,#8e44ad);padding:1rem;border-radius:10px;text-align:center;color:white;margin-bottom:1rem;'>
            <h1 style='margin:0;font-size: 1.8rem;'>🧬 AI Science Tutor</h1>
            <p style='margin:0;'>Interactive Learning Platform</p>
        </div>
    """, unsafe_allow_html=True)

# تهيئة الجلسة
if "auth_status" not in st.session_state:
    st.session_state.update({
        "auth_status": False, "user_type": "none", "chat_history": [],
        "student_grade": "", "study_lang": "", "quiz_active": False,
        "current_quiz_question": "", "current_xp": 0, "last_audio_bytes": None,
        "language": "العربية", "ref_text": ""
    })

# --- 1. الدخول ---
if not st.session_state.auth_status:
    draw_header()
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.info(f"💡 {random.choice(DAILY_FACTS)}")
        with st.form("login"):
            name = st.text_input("الاسم:")
            grade = st.selectbox("الصف:", ["الرابع", "الخامس", "السادس", "الأول ع", "الثاني ع", "الثالث ع", "ثانوي"])
            code = st.text_input("كود الدخول:", type="password")
            if st.form_submit_button("دخول", use_container_width=True):
                sheet_pass = get_sheet_data()
                if (sheet_pass and code == sheet_pass) or code == TEACHER_MASTER_KEY:
                    st.session_state.auth_status = True
                    st.session_state.user_type = "teacher" if code == TEACHER_MASTER_KEY else "student"
                    st.session_state.user_name = name if st.session_state.user_type == "student" else "Mr. Elsayed"
                    st.session_state.student_grade = grade
                    st.session_state.start_time = time.time()
                    if st.session_state.user_type == "student":
                        st.session_state.current_xp = get_current_xp(name)
                        log_login(name, "student", grade)
                    st.success("أهلاً بك!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("الكود غير صحيح")
    st.stop()

# --- 2. التحقق من الوقت ---
if st.session_state.user_type == "student":
    if (time.time() - st.session_state.start_time) > (SESSION_DURATION_MINUTES * 60):
        st.error("انتهت الجلسة. قم بتحديث الصفحة.")
        st.stop()

# --- 3. التطبيق الرئيسي ---
draw_header()

with st.sidebar:
    st.write(f"👤 **{st.session_state.user_name}**")
    st.session_state.language = st.radio("اللغة / Language:", ["العربية", "English"])
    
    if st.session_state.user_type == "student":
        st.metric("XP Points", st.session_state.current_xp)
        if st.session_state.current_xp >= 100:
            st.success("🎉 أحسنت!")
        
        st.divider()
        st.subheader("الترتيب")
        for i, l in enumerate(get_leaderboard()):
            st.caption(f"{i+1}. {l['Student_Name']} ({l['XP']})")
    
    if st.session_state.user_type == "teacher":
        new_code = st.text_input("تحديث الكود اليومي:")
        if st.button("حفظ الكود"):
            update_daily_password(new_code)
            st.success("تم!")

    # Google Drive Loader
    if DRIVE_FOLDER_ID:
        svc = get_drive_service()
        if svc:
            files = list_drive_files(svc, DRIVE_FOLDER_ID)
            if files:
                st.divider()
                bk = st.selectbox("📚 المكتبة:", [f['name'] for f in files])
                if st.button("تحميل الكتاب"):
                    fid = next(f['id'] for f in files if f['name'] == bk)
                    with st.spinner("جاري التحميل..."):
                        txt = download_pdf_text(svc, fid)
                        if txt:
                            st.session_state.ref_text = txt
                            st.toast("تم تحميل الكتاب!")

# التبويبات
tab1, tab2, tab3, tab4 = st.tabs(["🎙️ صوت", "📝 كتابة", "📷 صورة", "🧠 اختبار"])

with tab1:
    st.write("تحدث الآن:")
    audio = mic_recorder(start_prompt="🎤 ابدأ", stop_prompt="⏹️ أرسل", key='mic')
    if audio and audio['bytes'] != st.session_state.last_audio_bytes:
        st.session_state.last_audio_bytes = audio['bytes']
        lang_code = "ar-EG" if st.session_state.language == "العربية" else "en-US"
        txt = speech_to_text(audio['bytes'], lang_code)
        if txt:
            st.info(f"سمعت: {txt}")
            update_xp(st.session_state.user_name, 10)
            process_ai_response(txt, "voice")

with tab2:
    q = st.chat_input("اكتب سؤالك...")
    if q:
        st.chat_message("user").write(q)
        update_xp(st.session_state.user_name, 5)
        process_ai_response(q, "text")

with tab3:
    up = st.file_uploader("صورة سؤال/مخطط", type=['png','jpg'])
    prompt = st.text_input("سؤالك عن الصورة:")
    if st.button("تحليل") and up:
        img = Image.open(up)
        st.image(img, width=250)
        p = prompt if prompt else "اشرح هذه الصورة"
        update_xp(st.session_state.user_name, 15)
        process_ai_response([p, img], "image")

with tab4:
    if st.button("🎲 سؤال جديد"):
        model = get_gemini_model()
        if model:
            try:
                p = f"Generate 1 MCQ science question for {st.session_state.student_grade}. {st.session_state.language}. No answer."
                r = model.generate_content(p)
                st.session_state.current_quiz_question = r.text
                st.session_state.quiz_active = True
                st.rerun()
            except: st.error("خطأ")
            
    if st.session_state.quiz_active:
        st.markdown("---")
        st.write(st.session_state.current_quiz_question)
        ans = st.text_input("الإجابة:")
        if st.button("تحقق"):
            model = get_gemini_model()
            if model:
                chk = f"Q: {st.session_state.current_quiz_question}\nAns: {ans}\nVerify correctness."
                res = model.generate_content(chk)
                st.write(res.text)
                if "correct" in res.text.lower() or "صحيح" in res.text:
                    st.balloons()
                    update_xp(st.session_state.user_name, 50)
                st.session_state.quiz_active = False
