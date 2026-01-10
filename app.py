import streamlit as st
import nest_asyncio

# تفعيل التزامن المتداخل لإصلاح مشاكل الصوت
nest_asyncio.apply()

# ==========================================
# 1. إعدادات الصفحة والتصميم الفاخر
# ==========================================
st.set_page_config(page_title="AI Genius Tutor", page_icon="🧬", layout="wide")

# CSS مخصص لتحويل الواجهة إلى تحفة فنية
st.markdown("""
<style>
    /* استيراد خط عربي حديث */
    @import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@400;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Tajawal', sans-serif;
    }
    
    /* خلفية التطبيق */
    .stApp {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    }

    /* تصميم بطاقة المحادثة للمستخدم */
    .user-card {
        background-color: #2b5876;
        color: white;
        padding: 15px;
        border-radius: 20px 20px 0px 20px;
        margin: 10px 0;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        text-align: right;
        font-size: 1.1rem;
    }

    /* تصميم بطاقة المحادثة للذكاء الاصطناعي */
    .ai-card {
        background-color: #ffffff;
        color: #333;
        padding: 20px;
        border-radius: 0px 20px 20px 20px;
        margin: 10px 0;
        border-left: 6px solid #ff4b1f; /* شريط برتقالي مميز */
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        font-size: 1.1rem;
        line-height: 1.6;
    }

    /* تحسين الأزرار */
    .stButton>button {
        background: linear-gradient(to right, #ff4b1f, #ff9068); 
        color: white;
        border: none;
        border-radius: 50px;
        padding: 10px 30px;
        font-weight: bold;
        transition: transform 0.2s;
    }
    .stButton>button:hover {
        transform: scale(1.05);
        box-shadow: 0 5px 15px rgba(255, 75, 31, 0.4);
    }
    
    /* رسائل التحذير والنجاح */
    .stSuccess, .stInfo, .stWarning {
        border-radius: 10px;
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

# المكتبات
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
    "🚀 هل تعلم؟ الصوت لا ينتقل في الفضاء لأنه فراغ!",
    "🧬 هل تعلم؟ الحمض النووي للإنسان يتطابق بنسبة 50% مع الموز!",
    "🐜 هل تعلم؟ النمل لا ينام أبداً وليس لديه رئتين!",
    "💧 هل تعلم؟ الماء الساخن يتجمد أسرع من الماء البارد (تأثير مبيمبا)!",
]

RANKS = {
    0: "مبتدئ 🌱",
    50: "مغامر 🧭",
    150: "مخترع 🛠️",
    300: "عالم 🔬",
    500: "عبقري 🧠"
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

# --- نظام المهام الخلفية ---
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
                val = sheet.cell(cell.row, 2).value
                curr = int(val) if val else 0
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
        val = sheet.cell(cell.row, 2).value
        return int(val) if val else 0
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
# 🔊 الصوت (تم إصلاح المشكلة هنا)
# ==========================================
async def edge_tts_generate(text, voice):
    # تنظيف النص من الرموز التي تربك القراءة
    clean = re.sub(r'[*#_`\[\]()><=]', ' ', text)
    clean = re.sub(r'[A-Za-z]', '', clean) if "ar-" in voice else clean # إزالة الإنجليزية إذا كان عربي والعكس
    communicate = edge_tts.Communicate(clean, voice, rate="-2%") # سرعة أبطأ قليلاً للوضوح
    mp3 = BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3.write(chunk["data"])
    return mp3

def get_audio_bytes(text, lang="Arabic"):
    voice = "ar-EG-ShakirNeural" if lang == "Arabic" else "en-US-AndrewNeural"
    try:
        # استخدام حلقة الأحداث الموجودة أو إنشاء جديدة بأمان
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(edge_tts_generate(text, voice))
    except RuntimeError:
        # Fallback for Streamlit Cloud specific threading
        new_loop = asyncio.new_event_loop()
        return new_loop.run_until_complete(edge_tts_generate(text, voice))
    except Exception as e:
        print(f"Audio Error: {e}")
        return None

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
    
    # قائمة النماذج المحدثة
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

# دالة عرض المحادثة بتصميم مخصص
def display_chat(role, text):
    if role == "user":
        st.markdown(f"""
        <div class="user-card">
            👤 <b>أنت:</b><br>{text}
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="ai-card">
            🤖 <b>المعلم الذكي:</b><br>{text}
        </div>
        """, unsafe_allow_html=True)

def process_ai_response(user_text, input_type="text"):
    log_activity(st.session_state.user_name, input_type, user_text)
    
    # عرض سؤال المستخدم فوراً
    if input_type != "voice": # الصوت يعرض في مكانه
        display_chat("user", user_text if isinstance(user_text, str) else user_text[0])
    
    with st.spinner("🧠 المعلم يفكر في إجابة عبقرية..."):
        try:
            model = get_working_model()
            if not model:
                st.error("⚠️ فشل الاتصال.")
                return

            grade = st.session_state.get("student_grade", "General")
            lang_setting = st.session_state.language
            lang = "Arabic" if lang_setting == "العربية" else "English"
            ref = st.session_state.get("ref_text", "")
            
            # برومبت محسن لتنسيق الإجابة
            base_prompt = f"""
            Role: Engaging Science Teacher "Dr. Zewail".
            Target: {grade}. Name: {st.session_state.user_name}.
            Context: {ref[:8000]}
            Instructions: Answer in {lang}.
            Structure your answer like this:
            1. 🌟 **Introduction**: A catchy starting sentence.
            2. 💡 **Explanation**: Clear, simple points (use bullet points).
            3. 🧪 **Fun Fact**: A "Did you know?" related fact.
            Format: Use bold for important terms. Use emojis.
            If a diagram helps, use Graphviz DOT inside ```dot ... ```.
            """
            
            if input_type == "image":
                 resp = model.generate_content([base_prompt, user_text[0], user_text[1]])
            else:
                resp = model.generate_content(f"{base_prompt}\nStudent: {user_text}")
            
            full_text = resp.text
            
            # استخراج النص والكود
            disp_text = full_text.split("```dot")[0]
            dot_code = None
            if "```dot" in full_text:
                try: dot_code = full_text.split("```dot")[1].split("```")[0]
                except: pass

            # عرض الإجابة (AI Card)
            display_chat("ai", disp_text)
            
            if dot_code:
                st.graphviz_chart(dot_code)

            # تشغيل الصوت تلقائياً
            audio_bytes = get_audio_bytes(disp_text[:400], lang)
            if audio_bytes:
                st.audio(audio_bytes, format='audio/mp3', autoplay=True)

        except Exception as e:
            st.error(f"حدث خطأ: {e}")

# ==========================================
# 🎨 واجهة المستخدم (UI)
# ==========================================

if "auth_status" not in st.session_state:
    st.session_state.update({
        "auth_status": False, "user_type": "none", "chat_history": [],
        "student_grade": "", "current_xp": 0, "last_audio_bytes": None,
        "language": "العربية", "ref_text": ""
    })

# --- الدخول ---
if not st.session_state.auth_status:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h1 style='text-align: center; color: #2b5876;'>🧬 بوابة العلوم الذكية</h1>", unsafe_allow_html=True)
        st.markdown(f"""
        <div style="background: white; padding: 20px; border-radius: 15px; box-shadow: 0 4px 10px rgba(0,0,0,0.1);">
            <h3 style="text-align:center;">👋 مرحباً بك يا بطل!</h3>
            <p style="text-align:center; color: #666;">{random.choice(DAILY_FACTS)}</p>
        </div>
        <br>
        """, unsafe_allow_html=True)
        
        with st.form("login"):
            name = st.text_input("اسم الطالب:")
            grade = st.selectbox("الصف:", ["الرابع الابتدائي", "الخامس الابتدائي", "السادس الابتدائي", "الأول الإعدادي", "الثاني الإعدادي", "الثالث الإعدادي", "الثانوي"])
            code = st.text_input("الكود السري:", type="password")
            if st.form_submit_button("🚀 دخول"):
                db_pass = get_sheet_data()
                is_admin = (code == TEACHER_MASTER_KEY)
                is_student = (db_pass and code == db_pass)
                
                if is_admin or is_student:
                    st.session_state.auth_status = True
                    st.session_state.user_type = "teacher" if is_admin else "student"
                    st.session_state.user_name = name if is_student else "المعلم"
                    st.session_state.student_grade = grade
                    if is_student:
                        st.session_state.current_xp = get_current_xp(name)
                        log_login(name, "student", grade)
                    st.balloons()
                    st.rerun()
                else:
                    st.error("الكود خطأ")
    st.stop()

# --- الشريط الجانبي ---
with st.sidebar:
    st.markdown(f"## 👤 {st.session_state.user_name}")
    
    # عرض الرتبة بشكل جميل
    rank = get_rank_title(st.session_state.current_xp)
    st.markdown(f"""
    <div style="background: linear-gradient(to right, #ff4b1f, #ff9068); color: white; padding: 10px; border-radius: 10px; text-align: center;">
        <b>الرتبة:</b> {rank} 🎖️
    </div>
    """, unsafe_allow_html=True)
    
    # شريط التقدم
    next_lvl = 100
    for t in RANKS.keys():
        if t > st.session_state.current_xp:
            next_lvl = t
            break
    prog = min(1.0, st.session_state.current_xp / next_lvl) if next_lvl > 0 else 1.0
    st.progress(prog)
    st.caption(f"نقاطك: {st.session_state.current_xp} / {next_lvl} للترقية")
    
    st.divider()
    st.session_state.language = st.radio("اللغة / Language:", ["العربية", "English"])
    
    st.markdown("### 🏆 الأوائل")
    for i, l in enumerate(get_leaderboard()):
        icon = ["🥇","🥈","🥉"][i] if i<3 else "🏅"
        st.write(f"{icon} {l['Student_Name']} ({l['XP']})")

    if DRIVE_FOLDER_ID:
        svc = get_drive_service()
        if svc:
            files = list_drive_files(svc, DRIVE_FOLDER_ID)
            if files:
                st.divider()
                st.markdown("### 📖 الكتاب المدرسي")
                bn = st.selectbox("اختر:", [f['name'] for f in files])
                if st.button("تفعيل"):
                    fid = next(f['id'] for f in files if f['name'] == bn)
                    with st.spinner("جاري القراءة..."):
                        txt = download_pdf_text(svc, fid)
                        if txt: st.session_state.ref_text = txt; st.toast("تم التفعيل!")

# --- المنطقة الرئيسية ---
st.markdown("<h1 style='text-align: center; color: #2b5876;'>🧬 المعلم الذكي</h1>", unsafe_allow_html=True)

t1, t2, t3, t4 = st.tabs(["🎙️ تحدث", "✍️ اكتب", "📸 صور", "🧠 تحدي"])

with t1:
    c1, c2 = st.columns([1,4])
    with c1:
        aud = mic_recorder(start_prompt="🎤 اضغط وتحدث", stop_prompt="⏹️ إرسال", key='m')
    with c2:
        if aud and aud['bytes'] != st.session_state.last_audio_bytes:
            st.session_state.last_audio_bytes = aud['bytes']
            lang = "ar-EG" if st.session_state.language == "العربية" else "en-US"
            txt = speech_to_text(aud['bytes'], lang)
            if txt:
                display_chat("user", txt)
                update_xp(st.session_state.user_name, 10)
                process_ai_response(txt, "voice")

with t2:
    q = st.chat_input("اكتب سؤالك هنا...")
    if q:
        update_xp(st.session_state.user_name, 5)
        process_ai_response(q, "text")

with t3:
    up = st.file_uploader("ارفع صورة", type=['jpg','png'])
    if up and st.button("تحليل"):
        img = Image.open(up)
        st.image(img, width=200)
        update_xp(st.session_state.user_name, 15)
        process_ai_response(["اشرح الصورة", img], "image")

with t4:
    if st.button("🎲 سؤال (20 نقطة)"):
        m = get_working_model()
        if m:
            try:
                p = f"Generate 1 fun MCQ science question for {st.session_state.student_grade}. {st.session_state.language}. No answer."
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
                res = m.generate_content(f"Q: {st.session_state.q_curr}\nAns: {ans}\nCheck if correct.").text
                st.write(res)
                if "correct" in res.lower() or "صحيح" in res:
                    st.balloons(); update_xp(st.session_state.user_name, 20)
                st.session_state.q_active = False
