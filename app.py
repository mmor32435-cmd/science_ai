import streamlit as st
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
# 1. إعدادات الصفحة والستايل
# ==========================================
st.set_page_config(page_title="AI Science Tutor Pro 2026", page_icon="🧬", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { width: 100%; border-radius: 10px; height: 3em; background: linear-gradient(135deg,#6a11cb,#2575fc); color:white; border:none; }
    .stMetric { background: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 🎛️ الثوابت والإعدادات
# ==========================================
TEACHER_MASTER_KEY = "ADMIN_2026"
CONTROL_SHEET_NAME = "App_Control"
DRIVE_FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "") 

DAILY_FACTS = [
    "هل تعلم؟ قلب الحوت الأزرق كبير جداً لدرجة أن الإنسان يمكنه السباحة في شرايينه! 🐳",
    "هل تعلم؟ الألماس والجرافيت (رصاص القلم) مكونان من نفس العنصر: الكربون! 💎",
    "هل تعلم؟ الضوء يستغرق 8 دقائق و20 ثانية ليصل من الشمس إلى الأرض! ☀️",
    "هل تعلم؟ البكتيريا في جسمك تزن حوالي 2 كيلوجرام! 🦠",
]

# ==========================================
# 🛠️ الخدمات الخلفية (بيانات وجوجل)
# ==========================================

@st.cache_resource
def get_gcp_creds():
    if "gcp_service_account" not in st.secrets:
        return None
    return service_account.Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=[
            'https://www.googleapis.com/auth/drive',
            'https://www.googleapis.com/auth/spreadsheets'
        ]
    )

@st.cache_resource
def get_gspread_client():
    creds = get_gcp_creds()
    return gspread.authorize(creds) if creds else None

def get_sheet_data():
    client = get_gspread_client()
    if not client: return None
    try:
        sheet = client.open(CONTROL_SHEET_NAME).sheet1
        return str(sheet.acell('B1').value).strip()
    except: return None

# نظام التسجيل المحسن (Background Logging)
def _bg_task(task_type, data):
    client = get_gspread_client()
    if not client: return
    try:
        wb = client.open(CONTROL_SHEET_NAME)
        tz = pytz.timezone('Africa/Cairo')
        now_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

        if task_type == "login":
            wb.worksheet("Logs").append_row([now_str, data['type'], data['name'], data['details']])
        elif task_type == "activity":
            wb.worksheet("Activity").append_row([now_str, data['name'], data['input_type'], str(data['text'])[:500]])
        elif task_type == "xp":
            sh = wb.worksheet("Gamification")
            cell = sh.find(data['name'])
            if cell:
                curr = int(sh.cell(cell.row, 2).value or 0)
                sh.update_cell(cell.row, 2, curr + data['points'])
            else:
                sh.append_row([data['name'], data['points']])
    except: pass

def log_activity(input_type, text):
    threading.Thread(target=_bg_task, args=("activity", {
        'name': st.session_state.user_name, 'input_type': input_type, 'text': text
    })).start()

def update_xp(points):
    st.session_state.current_xp += points
    threading.Thread(target=_bg_task, args=("xp", {
        'name': st.session_state.user_name, 'points': points
    })).start()

# ==========================================
# 🧠 محرك الذكاء الاصطناعي (Gemini 2026)
# ==========================================

def get_working_model():
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys: return None
    
    random.shuffle(keys)
    # نماذج 2026 المحدثة
    models_to_try = ['gemini-2.0-flash', 'gemini-1.5-pro', 'gemini-1.5-flash']

    for key in keys:
        try:
            genai.configure(api_key=key)
            for m_name in models_to_try:
                try:
                    model = genai.GenerativeModel(m_name)
                    # فحص سريع للنموذج
                    model.generate_content("Hi", generation_config={"max_output_tokens": 10})
                    return model
                except: continue
        except: continue
    return None

async def text_to_speech(text, lang):
    voice = "ar-EG-ShakirNeural" if lang == "العربية" else "en-US-AndrewNeural"
    clean_text = re.sub(r'[#*`_]', '', text)[:500] # تنظيف النص للصوت
    communicate = edge_tts.Communicate(clean_text, voice)
    audio_data = BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data.write(chunk["data"])
    audio_data.seek(0)
    return audio_data

def process_ai_interaction(user_input, input_type="text"):
    log_activity(input_type, str(user_input))
    model = get_working_model()
    if not model:
        st.error("🔌 عذراً، نواجه ضغطاً في السيرفرات حالياً.")
        return

    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response = ""
        
        # تحضير التعليمات البرمجية (Prompt Engineering)
        prompt = f"""
        You are an expert Science Teacher for {st.session_state.student_grade} grade.
        Current Language: {st.session_state.language}.
        Reference Material: {st.session_state.get('ref_text', '')[:5000]}
        Rules:
        1. Be encouraging and fun.
        2. If a process is complex, provide a Graphviz 'dot' code block to visualize it.
        3. Use simple analogies.
        """

        try:
            if input_type == "image":
                resp = model.generate_content([prompt, user_input[0], user_input[1]], stream=True)
            else:
                resp = model.generate_content(f"{prompt}\nStudent says: {user_input}", stream=True)

            for chunk in resp:
                full_response += chunk.text
                response_placeholder.markdown(full_response + "▌")
            
            response_placeholder.markdown(full_response)
            
            # استخراج الرسم البياني إذا وجد
            if "```dot" in full_response:
                dot_code = full_response.split("```dot")[1].split("```")[0]
                st.graphviz_chart(dot_code)

            # تحويل النص إلى صوت تلقائياً
            audio_io = asyncio.run(text_to_speech(full_response, st.session_state.language))
            st.audio(audio_io, format='audio/mp3', autoplay=True)
            
            st.session_state.chat_history.append({"role": "assistant", "content": full_response})

        except Exception as e:
            st.error(f"حدث خطأ أثناء المعالجة: {e}")

# ==========================================
# 🎨 واجهة المستخدم (UI)
# ==========================================

if "auth_status" not in st.session_state:
    st.session_state.update({
        "auth_status": False, "user_name": "", "user_type": "", 
        "chat_history": [], "student_grade": "", "current_xp": 0,
        "language": "العربية", "ref_text": "", "q_active": False
    })

def login_screen():
    st.markdown("<h1 style='text-align: center;'>🧬 AI Science Tutor Pro</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.info(f"✨ حقيقة اليوم: {random.choice(DAILY_FACTS)}")
        with st.form("login_form"):
            name = st.text_input("الاسم الثلاثي")
            grade = st.selectbox("المرحلة الدراسية", ["الرابع الابتدائي", "الخامس الابتدائي", "السادس الابتدائي", "الأول الاعدادي", "الثاني الاعدادي", "الثالث الاعدادي", "ثانوي"])
            key = st.text_input("كود الدخول", type="password")
            if st.form_submit_button("دخول إلى المختبر"):
                db_key = get_sheet_data()
                if key == TEACHER_MASTER_KEY or (db_key and key == db_key):
                    st.session_state.auth_status = True
                    st.session_state.user_name = name if key != TEACHER_MASTER_KEY else "Mr. Elsayed"
                    st.session_state.user_type = "teacher" if key == TEACHER_MASTER_KEY else "student"
                    st.session_state.student_grade = grade
                    st.rerun()
                else:
                    st.error("❌ الكود غير صحيح، يرجى مراجعة المعلم.")

if not st.session_state.auth_status:
    login_screen()
    st.stop()

# --- واجهة التطبيق الرئيسية ---
with st.sidebar:
    st.title(f"مرحباً {st.session_state.user_name} 👋")
    st.session_state.language = st.radio("لغة الحوار", ["العربية", "English"])
    st.metric("رصيدك من XP 🏆", st.session_state.current_xp)
    
    if st.button("تسجيل الخروج"):
        st.session_state.clear()
        st.rerun()

st.markdown(f"### 🚀 مختبر العلوم الذكي - {st.session_state.student_grade}")

tab1, tab2, tab3 = st.tabs(["💬 حوار ذكي", "📷 تحليل صور", "📝 اختبار سريع"])

with tab1:
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            
    if prompt := st.chat_input("اسأل عن أي شيء في العلوم..."):
        st.chat_message("user").write(prompt)
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        update_xp(5)
        process_ai_interaction(prompt)

with tab2:
    st.subheader("تحليل الصور والرسومات العلمية")
    img_file = st.file_uploader("ارفع صورة لدرس أو تجربة", type=['jpg', 'png', 'jpeg'])
    if img_file:
        img = Image.open(img_file)
        st.image(img, caption="الصورة المرفوعة", width=300)
        if st.button("حلل الصورة الآن"):
            update_xp(15)
            process_ai_interaction(["اشرح هذه الصورة العلمية بالتفصيل وببساطة", img], "image")

with tab3:
    if st.button("توليد سؤال تحدي جديد 🎯"):
        model = get_working_model()
        if model:
            q_prompt = f"Generate one challenging MCQ question about science for {st.session_state.student_grade} in {st.session_state.language}. Mention options A, B, C, D."
            st.session_state.current_q = model.generate_content(q_prompt).text
            st.session_state.q_active = True
    
    if st.session_state.get("q_active"):
        st.info(st.session_state.current_q)
        answer = st.text_input("اكتب حرف الإجابة الصحيحة أو الإجابة كاملة:")
        if st.button("إرسال الإجابة"):
            model = get_working_model()
            check = model.generate_content(f"Question: {st.session_state.current_q}\nStudent Answer: {answer}\nIs it correct? Explain briefly in {st.session_state.language}").text
            st.write(check)
            if "correct" in check.lower() or "صحيح" in check:
                st.balloons()
                update_xp(50)
            st.session_state.q_active = False
