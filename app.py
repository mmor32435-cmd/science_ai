import streamlit as st

# 1. إعدادات الصفحة (أول سطر إلزامي)
st.set_page_config(page_title="AI Science Tutor Pro", page_icon="🧬", layout="wide")

import time
import google.generativeai as genai
import asyncio
import edge_tts
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder
from io import BytesIO
import re
from datetime import datetime
import pytz
from PIL import Image
import PyPDF2
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import gspread
from fpdf import FPDF
import pandas as pd
import random
import graphviz
import matplotlib.pyplot as plt
import threading

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
    "هل تعلم؟ سرعة الضوء 300,000 كم/ث! ⚡"
]

# ==========================================
# 🛠️ الخدمات والدوال المساعدة
# ==========================================

@st.cache_resource
def get_gspread_client():
    if "gcp_service_account" in st.secrets:
        try:
            creds = service_account.Credentials.from_service_account_info(
                st.secrets["gcp_service_account"],
                scopes=['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
            )
            return gspread.authorize(creds)
        except:
            return None
    return None

def get_sheet_data():
    client = get_gspread_client()
    if not client:
        return None
    try:
        sheet = client.open(CONTROL_SHEET_NAME)
        return str(sheet.sheet1.acell('B1').value).strip()
    except:
        return None

def update_daily_password(new_pass):
    client = get_gspread_client()
    if not client:
        return False
    try:
        client.open(CONTROL_SHEET_NAME).sheet1.update_acell('B1', new_pass)
        return True
    except:
        return False

# --- دوال التسجيل في الخلفية ---

def _log_bg(user_name, user_type, details, log_type):
    client = get_gspread_client()
    if not client: return
    try:
        sheet_name = "Logs" if log_type == "login" else "Activity"
        try:
            sheet = client.open(CONTROL_SHEET_NAME).worksheet(sheet_name)
        except:
            sheet = client.open(CONTROL_SHEET_NAME).sheet1
        
        tz = pytz.timezone('Africa/Cairo')
        now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        
        if log_type == "login":
            sheet.append_row([now, user_type, user_name, details])
        else:
            sheet.append_row([now, user_name, details[0], str(details[1])[:500]])
    except:
        pass

def log_login(user_name, user_type, details):
    threading.Thread(target=_log_bg, args=(user_name, user_type, details, "login")).start()

def log_activity(user_name, input_type, text):
    threading.Thread(target=_log_bg, args=(user_name, input_type, [input_type, text], "activity")).start()

def _xp_bg(user_name, points):
    client = get_gspread_client()
    if not client: return
    try:
        try:
            sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
        except:
            return
        
        cell = sheet.find(user_name)
        if cell:
            curr = int(sheet.cell(cell.row, 2).value)
            sheet.update_cell(cell.row, 2, curr + points)
        else:
            sheet.append_row([user_name, points])
    except:
        pass

def update_xp(user_name, points):
    if 'current_xp' in st.session_state:
        st.session_state.current_xp += points
    threading.Thread(target=_xp_bg, args=(user_name, points)).start()

def get_current_xp(user_name):
    client = get_gspread_client()
    if not client: return 0
    try:
        sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
        cell = sheet.find(user_name)
        return int(sheet.cell(cell.row, 2).value) if cell else 0
    except:
        return 0

def get_leaderboard():
    client = get_gspread_client()
    if not client: return []
    try:
        sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        df['XP'] = pd.to_numeric(df['XP'], errors='coerce').fillna(0)
        return df.sort_values(by='XP', ascending=False).head(5).to_dict('records')
    except:
        return []

def clear_old_data():
    client = get_gspread_client()
    if not client: return False
    try:
        for s in ["Logs", "Activity", "Gamification"]:
            try: 
                ws = client.open(CONTROL_SHEET_NAME).worksheet(s)
                ws.resize(rows=1)
                ws.resize(rows=100)
            except:
                pass
        return True
    except:
        return False

def get_stats_for_admin():
    client = get_gspread_client()
    if not client: return 0, []
    try:
        sheet = client.open(CONTROL_SHEET_NAME)
        try:
            logs = sheet.worksheet("Logs").get_all_values()
            c = len(logs) - 1
        except:
            c = 0
        try:
            qs = sheet.worksheet("Activity").get_all_values()
            l = qs[-5:]
        except:
            l = []
        return c, l
    except:
        return 0, []

def create_certificate(student_name):
    txt = f"CERTIFICATE OF EXCELLENCE\nAwarded to: {student_name}\nSigned: Mr. Elsayed Elbadawy"
    return txt.encode('utf-8')

def get_chat_text(history):
    text = "--- Chat History ---\n"
    for q, a in history: text += f"Student: {q}\nTutor: {a}\n\n"
    return text

# --- دوال الذكاء الاصطناعي والصوت ---
def get_voice_config(lang):
    if lang == "English": return "en-US-AndrewNeural", "en-US"
    else: return "ar-EG-ShakirNeural", "ar-EG"

def clean_text_for_audio(text):
    text = re.sub(r'\\documentclass\{.*?\}', '', text) 
    text = re.sub(r'\\usepackage\{.*?\}', '', text)
    text = re.sub(r'\\begin\{.*?\}', '', text) 
    text = re.sub(r'\\end\{.*?\}', '', text)   
    text = re.sub(r'\\item', '', text)         
    text = re.sub(r'\\textbf\{(.*?)\}', r'\1', text) 
    text = re.sub(r'\\textit\{(.*?)\}', r'\1', text) 
    text = re.sub(r'\\underline\{(.*?)\}', r'\1', text)
    text = text.replace('*', '').replace('#', '').replace('-', '').replace('_', ' ').replace('`', '')
    return text

async def generate_audio_stream(text, voice_code):
    clean = clean_text_for_audio(text)
    if isinstance(voice_code, tuple) or isinstance(voice_code, list):
        voice_code = voice_code[0]
    communicate = edge_tts.Communicate(clean, voice_code, rate="-5%")
    mp3 = BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio": mp3.write(chunk["data"])
    return mp3

def speech_to_text(audio_bytes, lang_code):
    r = sr.Recognizer()
    try:
        audio_file = sr.AudioFile(BytesIO(audio_bytes))
        with audio_file as source:
            r.adjust_for_ambient_noise(source, duration=0.5)
            audio = r.record(source)
            return r.recognize_google(audio, language=lang_code)
    except:
        return None

def stream_text_effect(text):
    for word in text.split(" "):
        yield word + " "
        time.sleep(0.04)

@st.cache_resource
def get_drive_service():
    if "gcp_service_account" not in st.secrets:
        return None
    try:
        creds_dict = st.secrets["gcp_service_account"]
        scope = ['https://www.googleapis.com/auth/drive.readonly']
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scope)
        return build('drive', 'v3', credentials=creds)
    except:
        return None

def list_drive_files(service, folder_id):
    try:
        query = f"'{folder_id}' in parents"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        return results.get('files', [])
    except:
        return []

def download_pdf_text(service, file_id):
    try:
        request = service.files().get_media(fileId=file_id)
        fh = BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        fh.seek(0)
        reader = PyPDF2.PdfReader(fh)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except:
        return ""

# ==========================================
# 🧠 الذكاء الاصطناعي (المفاتيح)
# ==========================================
def get_working_genai_model():
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys and "GOOGLE_API_KEY" in st.secrets:
        keys = [st.secrets["GOOGLE_API_KEY"]]
    
    if not keys:
        return None
    
    random.shuffle(keys)

    for key in keys:
        try:
            genai.configure(api_key=key)
            return genai.GenerativeModel('gemini-1.5-flash')
        except:
            continue
    return None

def smart_generate_content(prompt_content):
    model = get_working_genai_model()
    if not model:
        raise Exception("API Keys Busy")
    
    try:
        return model.generate_content(prompt_content)
    except Exception as e:
        time.sleep(1)
        model = get_working_genai_model()
        if model:
            return model.generate_content(prompt_content)
        raise e

# 🔥 دالة المعالجة المركزية 🔥
def process_ai_response(user_text, input_type="text"):
    log_activity(st.session_state.user_name, input_type, user_text)
    st.toast("🧠 Thinking...", icon="🤔")
    
    try:
        role_lang = "Arabic" if st.session_state.language == "العربية" else "English"
        ref = st.session_state.get("ref_text", "")
        s_name = st.session_state.user_name
        s_level = st.session_state.get("student_grade", "General")
        curr = st.session_state.get("study_lang", "Arabic")
        
        map_instr = ""
        check_map = ["مخطط", "خريطة", "رسم", "map", "diagram"]
        if any(x in str(user_text).lower() for x in check_map):
            map_instr = "Output Graphviz DOT code inside ```dot ... ``` block."

        prompt = f"""
        Role: Science Tutor. Target: {s_level}.
        Curriculum: {curr}. Lang: {lang}. Name: {s_name}.
        Instructions: Use LaTeX for math. No bold/underline.
        BE CONCISE. {map_instr}
        Ref: {ref[:20000]}
        """
        
        if input_type == "image":
             resp = smart_generate_content([prompt, user_text[0], user_text[1]])
        else:
            resp = smart_generate_content(f"{prompt}\nInput: {user_text}")
        
        st.session_state.chat_history.append((str(user_text)[:50], resp.text))
        
        final_text = resp.text
        dot_code = None
        
        if "```dot" in resp.text:
            try:
                parts = resp.text.split("```dot")
                final_text = parts[0]
                dot_code = parts[1].split("```")[0].strip()
            except:
                pass
        
        st.markdown("---")
        st.write_stream(stream_text_effect(final_text))
        
        if dot_code:
            try:
                st.graphviz_chart(dot_code)
            except:
                pass

        vc = get_voice_config(st.session_state.language)
        vc_name = vc[0]
        audio = asyncio.run(generate_audio_stream(final_text, vc_name))
        st.audio(audio, format='audio/mp3', autoplay=True)
        
    except Exception as e:
        st.error(f"Error: {e}")

# ==========================================
# 🎨 الواجهة الرئيسية (Main UI)
# ==========================================

def draw_header():
    st.markdown("""
        <div style='background:linear-gradient(120deg,#89f7fe,#66a6ff);padding:1.5rem;border-radius:15px;text-align:center;color:#1a2a6c;margin-bottom:1rem;'>
            <h1 style='margin:0;'>🧬 AI Science Tutor</h1>
            <p style='margin:5px;font-weight:600;'>Under Supervision of: Mr. Elsayed Elbadawy</p>
        </div>
    """, unsafe_allow_html=True)

# تهيئة الجلسة
if "auth_status" not in st.session_state:
    st.session_state.auth_status = False
    st.session_state.user_type = "none"
    st.session_state.chat_history = []
    st.session_state.student_grade = ""
    st.session_state.study_lang = ""
    st.session_state.quiz_active = False
    st.session_state.current_quiz_question = ""
    st.session_state.current_xp = 0
    st.session_state.last_audio_bytes = None
    st.session_state.language = "العربية"

# 1. شاشة الدخول
if not st.session_state.auth_status:
    draw_header()
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.info(f"💡 {random.choice(DAILY_FACTS)}")
        
        with st.form("login"):
            s_name = st.text_input("Name / الاسم:")
            stages = ["الرابع الابتدائي", "الخامس الابتدائي", "السادس الابتدائي",
                      "الأول الإعدادي", "الثاني الإعدادي", "الثالث الإعدادي",
                      "الأول الثانوي", "الثاني الثانوي", "الثالث الثانوي"]
            s_grade = st.selectbox("Grade / الصف:", stages)
            s_sys = st.radio("System:", ["عربي", "لغات"], horizontal=True)
            code = st.text_input("Code / الكود:", type="password")
            btn = st.form_submit_button("Login / دخول", use_container_width=True)
        
        if btn:
            if (not s_name) and code != TEACHER_MASTER_KEY:
                st.warning("اكتب الاسم")
            else:
                with st.spinner("Connecting..."):
                    sheet_pass = get_sheet_data()
                    is_teacher = (code == TEACHER_MASTER_KEY)
                    is_student = (sheet_pass and code == sheet_pass)
                    
                    if is_teacher or is_student:
                        st.session_state.auth_status = True
                        st.session_state.user_type = "teacher" if is_teacher else "student"
                        st.session_state.user_name = s_name if is_student else "Mr. Elsayed"
                        st.session_state.student_grade = s_grade
                        st.session_state.study_lang = "English" if "لغات" in s_sys else "Arabic"
                        st.session_state.start_time = time.time()
                        
                        log_login(st.session_state.user_name, st.session_state.user_type, f"{s_grade} | {s_sys}")
                        
                        try:
                            xp = get_current_xp(st.session_state.user_name)
                            st.session_state.current_xp = xp
                        except:
                            st.session_state.current_xp = 0
                            
                        st.success("Welcome!"); time.sleep(0.5); st.rerun()
                    else:
                        st.error("Invalid Code")
    st.stop()

# 2. فحص الوقت
if st.session_state.user_type == "student":
    elapsed = time.time() - st.session_state.start_time
    allowed = SESSION_DURATION_MINUTES * 60
    if elapsed > allowed:
        st.error("Session Expired"); st.stop()

# 3. التطبيق
draw_header()

col_L, col_R = st.columns([2,1])
with col_L:
    st.session_state.language = st.radio("اللغة:", ["العربية", "English"], horizontal=True)

with st.sidebar:
    st.write(f"👤 **{st.session_state.user_name}**")
    
    if st.session_state.user_type == "student":
        st.metric("🌟 XP", st.session_state.current_xp)
        if st.session_state.current_xp >= 100:
            st.success("🎉 100 XP!")
            st.download_button("🎓 شهادة", create_certificate(st.session_state.user_name), "Cert.txt")
        
        st.markdown("---")
        st.subheader("🏆 الأوائل")
        leaders = get_leaderboard()
        for i, l in enumerate(leaders):
            st.write(f"{i+1}. {l['Student_Name']}: {l['XP']}")

    if st.session_state.user_type == "teacher":
        st.success("👨‍🏫 المعلم")
        with st.expander("إحصائيات"):
            c, qs = get_stats_for_admin()
            st.write(f"الطلاب: {c}")
        with st.expander("تغيير الكود"):
            np = st.text_input("جديد:")
            if st.button("تحديث"):
                if update_daily_password(np): st.success("تم")
        with st.expander("حذف"):
            if st.button("تنظيف"):
                if clear_old_data(): st.success("تم")

    st.markdown("---")
    if DRIVE_FOLDER_ID:
        service = get_drive_service()
        if service:
            files = list_drive_files(service, DRIVE_FOLDER_ID)
            if files:
                st.subheader("📚 المكتبة")
                bk = st.selectbox("الكتاب:", [f['name'] for f in files])
                if st.button("تحميل"):
                    fid = next(f['id'] for f in files if f['name'] == bk)
                    with st.spinner("جاري التحميل..."):
                        st.session_state.ref_text = download_pdf_text(service, fid)
                        st.toast("تم التحميل! ✅")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["🎙️ صوت", "✍️ كتابة", "📁 ملف", "🧠 اختبار", "📊 تحليل"])

with tab1:
    st.write("اضغط للتحدث:")
    audio = mic_recorder(start_prompt="🎤 ابدأ", stop_prompt="⏹️ أرسل", key='mic')
    if audio:
        if audio['bytes'] != st.session_state.last_audio_bytes:
            st.session_state.last_audio_bytes = audio['bytes']
            vc = get_voice_config(st.session_state.language)[1]
            txt = speech_to_text(audio['bytes'], vc)
            if txt:
                update_xp(st.session_state.user_name, 10)
                process_ai_response(txt, "voice")

with tab2:
    txt = st.text_area("سؤالك:")
    if st.button("إرسال", key="txt_btn"):
        if txt:
            update_xp(st.session_state.user_name, 5)
            process_ai_response(txt, "text")

with tab3:
    up = st.file_uploader("صورة/PDF", type=['png','jpg','pdf'])
    det = st.text_input("تفاصيل:")
    if st.button("تحليل") and up:
        u_in = None
        i_type = "text"
        if up.type == 'application/pdf':
            pdf = PyPDF2.PdfReader(up)
            u_in = "PDF: " + "".join([p.extract_text() for p in pdf.pages]) + f"\nQ: {det}"
        else:
            img = Image.open(up)
            st.image(img, width=200)
            u_in = [det if det else "Explain", img]
            i_type = "image"
        update_xp(st.session_state.user_name, 15)
        process_ai_response(u_in, i_type)

with tab4:
    st.info(f"اختبار: {st.session_state.student_grade}")
    colq1, colq2 = st.columns(2)
    with colq1:
        if st.button("🎲 سؤال"):
            ref = st.session_state.get("ref_text", "")
            src = f"Source: {ref[:30000]}" if ref else "Source: Egyptian Curriculum"
            p = f"Generate 1 MCQ for {st.session_state.student_grade}. {src}. Arabic. No Answer."
            try:
                r = smart_generate_content(p)
                st.session_state.current_quiz_question = r.text
                st.session_state.quiz_active = True
                st.rerun()
            except: pass
    
    with colq2:
        if st.button("📝 امتحان PDF"):
            ref = st.session_state.get("ref_text", "")
            src = f"Source: {ref[:30000]}" if ref else "Source: Egyptian Curriculum"
            p = f"Create 5-Q Exam for {st.session_state.student_grade}. {src}. Arabic. Plain Text."
            try:
                r = smart_generate_content(p)
                st.download_button("تحميل", r.text, "Exam.txt")
            except: pass

    if st.session_state.quiz_active:
        st.markdown("---")
        st.markdown(f"**{st.session_state.current_quiz_question}**")
        ans = st.text_input("إجابتك:")
        if st.button("تحقق"):
            chk = f"Check: {ans} for Question: {st.session_state.current_quiz_question}. Arabic."
            res = smart_generate_content(chk)
            st.write(res.text)
            if "صح" in res.text or "Correct" in res.text:
                st.balloons()
                update_xp(st.session_state.user_name, 50)
            st.session_state.quiz_active = False

with tab5:
    if st.button("تحليل أدائي"):
        hist = get_chat_text(st.session_state.chat_history)
        process_ai_response(f"Analyze: {hist[:3000]}", "analysis")
