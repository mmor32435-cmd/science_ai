import streamlit as st

# ==========================================
# 1. إعدادات الصفحة والتصميم السحري
# ==========================================
st.set_page_config(page_title="Genius Science Lab", page_icon="🧪", layout="wide")

# حقن CSS لتحسين المظهر وجعله جذاباً للطلاب
st.markdown("""
<style>
    /* تحسين الخطوط والألوان */
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
    html, body, [class*="css"] {
        font-family: 'Cairo', sans-serif;
    }
    
    /* خلفية متدرجة جميلة */
    .stApp {
        background: linear-gradient(to bottom right, #fdfbfb, #ebedee);
    }
    
    /* كروت المحادثة */
    .stChatMessage {
        background-color: white;
        border-radius: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        padding: 10px;
        margin-bottom: 10px;
        border: 1px solid #eee;
    }
    
    /* الأزرار */
    .stButton>button {
        background: linear-gradient(45deg, #6a11cb, #2575fc);
        color: white;
        border-radius: 20px;
        border: none;
        padding: 10px 24px;
        font-weight: bold;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        transform: scale(1.05);
        box-shadow: 0 5px 15px rgba(37, 117, 252, 0.4);
    }

    /* شريط التقدم */
    .stProgress > div > div > div > div {
        background-image: linear-gradient(to right, #00b09b, #96c93d);
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
# 🎛️ الثوابت والإعدادات
# ==========================================
TEACHER_MASTER_KEY = "ADMIN_2024"
CONTROL_SHEET_NAME = "App_Control"
DRIVE_FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "") 

# حقائق علمية ممتعة
DAILY_FACTS = [
    "🧠 هل تعلم؟ دماغك يعمل بطاقة تكفي لإضاءة مصباح صغير!",
    "🦴 هل تعلم؟ عظمة الفخذ أقوى من الخرسانة بـ 4 مرات!",
    "🐙 هل تعلم؟ الأخطبوط لديه 3 قلوب و 9 أدمغة!",
    "⚡ هل تعلم؟ البرق يسخن الهواء 5 مرات أكثر من سطح الشمس!",
]

# نظام الرتب (Gamification)
RANKS = {
    0: "مبتدئ علوم 🌱",
    50: "مستكشف 🔭",
    150: "باحث ذكي 💡",
    300: "عالم صغير 🔬",
    500: "أينشتاين القادم 🚀"
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
# 🔊 الصوت (TTS & STT)
# ==========================================
async def generate_audio_stream(text, voice_code):
    clean = re.sub(r'[*#_`\[\]()><=]', ' ', text)
    comm = edge_tts.Communicate(clean, voice_code, rate="-5%")
    mp3 = BytesIO()
    async for chunk in comm.stream():
        if chunk["type"] == "audio": mp3.write(chunk["data"])
    return mp3

def speech_to_text(audio_bytes, lang_code):
    r = sr.Recognizer()
    try:
        with sr.AudioFile(BytesIO(audio_bytes)) as source:
            r.adjust_for_ambient_noise(source, duration=0.5)
            return r.recognize_google(r.record(source), language=lang_code)
    except: return None

# ==========================================
# 🧠 الذكاء الاصطناعي (العقل المدبر)
# ==========================================
def get_working_model():
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys: return None
    random.shuffle(keys)
    
    # القائمة الذهبية للنماذج (الأقوى فالأقوى)
    models = ['gemini-2.5-flash', 'gemini-flash-latest', 'gemini-2.0-flash', 'gemini-pro-latest']
    
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
    log_activity(st.session_state.user_name, input_type, user_text)
    
    with st.spinner("🧠 جاري تحليل البيانات..."):
        try:
            model = get_working_model()
            if not model:
                st.error("⚠️ خطأ في الاتصال.")
                return

            # تخصيص الإجابة حسب المرحلة العمرية (Personalization)
            grade = st.session_state.get("student_grade", "General")
            style_instruction = ""
            
            if "الابتدائي" in grade:
                style_instruction = "Style: Fun, Storyteller. Use simple words and lots of emojis (🌟, 🦁, 🚀). Explain like I'm 10."
            elif "الإعدادي" in grade:
                style_instruction = "Style: Engaging Teacher. Use real-world examples and clear structure."
            elif "الثانوي" in grade:
                style_instruction = "Style: Academic Mentor. Provide detailed explanations, formulas, and critical thinking points."

            lang = "Arabic" if st.session_state.language == "العربية" else "English"
            ref = st.session_state.get("ref_text", "")
            
            base_prompt = f"""
            Role: You are "Dr. Zewail", a genius and friendly AI Science Tutor.
            Student Name: {st.session_state.user_name}. Grade: {grade}.
            Context from Book: {ref[:8000]}
            Instructions: Answer in {lang}. {style_instruction}.
            Format: Use bold for key terms.
            Visuals: If a diagram helps, write valid Graphviz DOT code inside ```dot ... ``` block. Make nodes colorful.
            """
            
            if input_type == "image":
                 resp = model.generate_content([base_prompt, user_text[0], user_text[1]])
            else:
                resp = model.generate_content(f"{base_prompt}\nStudent asks: {user_text}")
            
            full_text = resp.text
            st.session_state.chat_history.append({"role": "user", "content": str(user_text)[:50]})
            st.session_state.chat_history.append({"role": "ai", "content": full_text})
            
            # العرض
            disp_text = full_text.split("```dot")[0]
            dot_code = None
            if "```dot" in full_text:
                try: dot_code = full_text.split("```dot")[1].split("```")[0]
                except: pass

            st.markdown("---")
            
            # عرض الإجابة بتأثير الكتابة
            placeholder = st.empty()
            accumulated_text = ""
            for char in disp_text:
                accumulated_text += char
                if len(accumulated_text) % 5 == 0: # تحديث كل 5 حروف للأداء
                    placeholder.markdown(accumulated_text + "▌")
                    time.sleep(0.005)
            placeholder.markdown(disp_text)
            
            if dot_code:
                st.graphviz_chart(dot_code)

            # الصوت
            vc = "ar-EG-ShakirNeural" if lang == "العربية" else "en-US-AndrewNeural"
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                audio = loop.run_until_complete(generate_audio_stream(disp_text[:300], vc))
                st.audio(audio, format='audio/mp3', autoplay=True)
            except: pass

        except Exception as e:
            st.error(f"حدث خطأ: {e}")

# ==========================================
# 🎨 واجهة المستخدم (UI)
# ==========================================

def draw_header():
    st.markdown("""
    <div style="text-align: center; margin-bottom: 2rem;">
        <h1 style="background: -webkit-linear-gradient(45deg, #FF512F, #DD2476); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 3.5rem;">🧬 مختبر العلوم الذكي</h1>
        <p style="font-size: 1.2rem; color: #555;">رفيقك الذكي للتفوق في العلوم</p>
    </div>
    """, unsafe_allow_html=True)

if "auth_status" not in st.session_state:
    st.session_state.update({
        "auth_status": False, "user_type": "none", "chat_history": [],
        "student_grade": "", "current_xp": 0, "last_audio_bytes": None,
        "language": "العربية", "ref_text": ""
    })

# --- شاشة الدخول المبهرة ---
if not st.session_state.auth_status:
    draw_header()
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown(f"""
        <div style="background-color: #f0f2f6; padding: 20px; border-radius: 10px; border-left: 5px solid #6a11cb;">
            <strong>💡 معلومة اليوم:</strong> {random.choice(DAILY_FACTS)}
        </div>
        <br>
        """, unsafe_allow_html=True)
        
        with st.form("login_form"):
            name = st.text_input("👤 اسم الطالب:")
            grade = st.selectbox("📚 المرحلة الدراسية:", 
                               ["الرابع الابتدائي", "الخامس الابتدائي", "السادس الابتدائي", 
                                "الأول الإعدادي", "الثاني الإعدادي", "الثالث الإعدادي", 
                                "الأول الثانوي", "الثاني الثانوي", "الثالث الثانوي"])
            code = st.text_input("🔑 كود الدخول:", type="password")
            
            if st.form_submit_button("🚀 انطلق في رحلة التعلم"):
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
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("⛔ الكود غير صحيح، حاول مرة أخرى!")
    st.stop()

# --- التطبيق الرئيسي ---
# الشريط الجانبي (لوحة التحكم)
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3069/3069172.png", width=80)
    st.markdown(f"### أهلاً يا بطل! 👋\n**{st.session_state.user_name}**")
    
    # عرض الرتبة والتقدم
    rank = get_rank_title(st.session_state.current_xp)
    st.markdown(f"**الرتبة الحالية:** {rank}")
    
    # شريط التقدم
    next_level = 100
    for t in RANKS.keys():
        if t > st.session_state.current_xp:
            next_level = t
            break
    progress = min(1.0, st.session_state.current_xp / next_level) if next_level > 0 else 1.0
    st.progress(progress)
    st.caption(f"{st.session_state.current_xp} / {next_level} XP للترقية")
    
    st.markdown("---")
    st.session_state.language = st.radio("🗣️ لغة التحدث:", ["العربية", "English"])
    
    # لوحة الشرف
    st.markdown("### 🏆 لوحة الشرف")
    leaders = get_leaderboard()
    if leaders:
        for i, l in enumerate(leaders):
            icon = "🥇" if i==0 else "🥈" if i==1 else "🥉" if i==2 else "🎖️"
            st.markdown(f"{icon} **{l['Student_Name']}**: {l['XP']} XP")
    
    # تحميل الكتب
    if DRIVE_FOLDER_ID:
        svc = get_drive_service()
        if svc:
            files = list_drive_files(svc, DRIVE_FOLDER_ID)
            if files:
                st.markdown("---")
                st.markdown("### 📚 مكتبتي")
                bn = st.selectbox("اختر الكتاب:", [f['name'] for f in files])
                if st.button("📖 تفعيل الكتاب"):
                    fid = next(f['id'] for f in files if f['name'] == bn)
                    with st.spinner("جاري قراءة الكتاب..."):
                        txt = download_pdf_text(svc, fid)
                        if txt:
                            st.session_state.ref_text = txt
                            st.toast("تم تفعيل الكتاب بنجاح! يمكنك سؤالي عنه الآن.", icon="✅")

# المنطقة الرئيسية
draw_header()

# التبويبات بأسماء جذابة
t1, t2, t3, t4 = st.tabs(["🎙️ المساعد الصوتي", "💬 اسأل المعلم", "📸 المختبر المصور", "🧠 تحدي الأذكياء"])

with t1:
    st.markdown("#### 🎙️ تحدث معي، أنا أسمعك!")
    c1, c2 = st.columns([1, 4])
    with c1:
        audio = mic_recorder(start_prompt="🔴 اضغط للتحدث", stop_prompt="⏹️ إرسال", key='mic_main')
    with c2:
        if audio and audio['bytes'] != st.session_state.last_audio_bytes:
            st.session_state.last_audio_bytes = audio['bytes']
            lang = "ar-EG" if st.session_state.language == "العربية" else "en-US"
            txt = speech_to_text(audio['bytes'], lang)
            if txt:
                st.info(f"🗣️ قلت: {txt}")
                update_xp(st.session_state.user_name, 10)
                process_ai_response(txt, "voice")

with t2:
    st.markdown("#### 💬 اكتب سؤالك وسأشرحه لك بذكاء")
    q = st.chat_input("ما هو سؤالك في العلوم اليوم؟")
    if q:
        st.chat_message("user").write(q)
        update_xp(st.session_state.user_name, 5)
        process_ai_response(q, "text")

with t3:
    st.markdown("#### 📸 صور أي مسألة أو رسمة وسأقوم بحلها")
    up = st.file_uploader("ارفع الصورة هنا", type=['png','jpg','jpeg'])
    if up:
        img = Image.open(up)
        st.image(img, width=300, caption="الصورة المرفقة")
        if st.button("🔍 تحليل الصورة"):
            update_xp(st.session_state.user_name, 15)
            process_ai_response(["اشرح لي هذه الصورة العلمية بالتفصيل", img], "image")

with t4:
    st.markdown("#### 🧠 هل أنت مستعد للتحدي؟")
    col_challenge, col_result = st.columns(2)
    
    with col_challenge:
        if st.button("🎲 سؤال جديد (20 XP)"):
            m = get_working_model()
            if m:
                try:
                    prompt = f"Create 1 fun MCQ science question for {st.session_state.student_grade}. {st.session_state.language}. No answer key yet."
                    st.session_state.q_curr = m.generate_content(prompt).text
                    st.session_state.q_active = True
                    st.rerun()
                except: st.error("حاول مرة أخرى")

    if st.session_state.get("q_active"):
        st.info(st.session_state.q_curr)
        ans = st.text_input("✍️ اكتب إجابتك:")
        if st.button("✅ تحقق من الإجابة"):
            m = get_working_model()
            if m:
                chk = f"Question: {st.session_state.q_curr}\nUser Answer: {ans}\nIs it correct? Answer Yes/No then explain briefly."
                res = m.generate_content(chk).text
                st.write(res)
                if "yes" in res.lower() or "نعم" in res or "correct" in res.lower() or "صحيح" in res:
                    st.balloons()
                    st.success("🎉 إجابة رائعة! +20 XP")
                    update_xp(st.session_state.user_name, 20)
                else:
                    st.warning("❌ حاول مرة أخرى، أنت تستطيع!")
                st.session_state.q_active = False
