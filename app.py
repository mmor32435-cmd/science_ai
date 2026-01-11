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
# 1. إعدادات الصفحة
# ==========================================
st.set_page_config(
    page_title="AI Science Tutor Pro",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# 🎛️ الثوابت والإعدادات
# ==========================================
TEACHER_MASTER_KEY = "ADMIN_2024"
CONTROL_SHEET_NAME = "App_Control" # اسم ملف جوجل شيت
DRIVE_FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "") 

DAILY_FACTS = [
    "هل تعلم؟ المخ يولد كهرباء تكفي لمصباح! 💡",
    "هل تعلم؟ العظام أقوى من الخرسانة بـ 4 مرات! 🦴",
    "هل تعلم؟ الأخطبوط لديه 3 قلوب! 🐙",
    "هل تعلم؟ العسل لا يفسد أبداً! 🍯",
    "هل تعلم؟ سرعة الضوء هي 300,000 كم/ثانية! ⚡",
]

# ==========================================
# 🛠️ الخدمات الخلفية (Backend Services)
# ==========================================

# --- 1. الاتصال بجداول جوجل (Sheets) ---
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
        st.error(f"خطأ في الاتصال بقاعدة البيانات: {e}")
        return None

def get_sheet_data():
    """جلب كلمة المرور الشهرية من الشيت"""
    client = get_gspread_client()
    if not client: return None
    try:
        # نفترض أن كلمة المرور في الخلية B1 في الورقة الأولى
        sheet = client.open(CONTROL_SHEET_NAME)
        val = sheet.sheet1.acell('B1').value
        return str(val).strip()
    except Exception:
        return None

# --- 2. نظام التسجيل (Logging) والتلعيب (Gamification) ---
def _bg_task(task_type, data):
    """وظيفة تعمل في الخلفية لتحديث الشيت دون تعطيل الواجهة"""
    if "gcp_service_account" not in st.secrets: return

    try:
        client = get_gspread_client()
        if not client: return
        wb = client.open(CONTROL_SHEET_NAME)
        
        tz = pytz.timezone('Africa/Cairo')
        now_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

        if task_type == "login":
            try: sheet = wb.worksheet("Logs")
            except: sheet = wb.add_worksheet("Logs", 1000, 5)
            sheet.append_row([now_str, data['type'], data['name'], data['details']])

        elif task_type == "activity":
            try: sheet = wb.worksheet("Activity")
            except: sheet = wb.add_worksheet("Activity", 1000, 5)
            clean_text = str(data['text'])[:1000]
            sheet.append_row([now_str, data['name'], data['input_type'], clean_text])

        elif task_type == "xp":
            try: sheet = wb.worksheet("Gamification")
            except: sheet = wb.add_worksheet("Gamification", 1000, 3)
            
            # البحث عن الطالب وتحديث نقاطه
            try:
                cell = sheet.find(data['name'])
                if cell:
                    current_val = sheet.cell(cell.row, 2).value
                    current_xp = int(current_val) if current_val else 0
                    sheet.update_cell(cell.row, 2, current_xp + data['points'])
                else:
                    sheet.append_row([data['name'], data['points']])
            except:
                sheet.append_row([data['name'], data['points']])

    except Exception as e:
        print(f"Background task error: {e}")

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
        if cell:
            val = sheet.cell(cell.row, 2).value
            return int(val) if val else 0
    except:
        return 0
    return 0

def get_leaderboard():
    client = get_gspread_client()
    if not client: return []
    try:
        sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        if df.empty: return []
        # التأكد من أسماء الأعمدة (نفترض Column 1: Name, Column 2: XP)
        if 'XP' not in df.columns:
            df.columns = ['Student_Name', 'XP']
        
        df['XP'] = pd.to_numeric(df['XP'], errors='coerce').fillna(0)
        return df.sort_values(by='XP', ascending=False).head(5).to_dict('records')
    except Exception:
        return []

# --- 3. خدمات جوجل درايف (Drive) ---
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
    except Exception as e:
        return f"Error reading PDF: {e}"

# ==========================================
# 🔊 معالجة الصوت (Audio Processing)
# ==========================================
async def generate_audio_stream(text, voice_code):
    """توليد الصوت باستخدام Edge TTS"""
    # تنظيف النص من رموز الماركداون والرموز الخاصة لتجنب مشاكل النطق
    clean = re.sub(r'[*#_`\[\]()><=]', ' ', text)
    clean = re.sub(r'\\.*', '', clean) # إزالة الصيغ الرياضية المعقدة
    
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
    except sr.UnknownValueError:
        return None
    except Exception:
        return None

# ==========================================
# 🧠 الذكاء الاصطناعي (Gemini AI)
# ==========================================
def get_working_model():
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys: return None

    # خلط المفاتيح لتوزيع الحمل
    random.shuffle(keys)
    
    # قائمة الموديلات بالأولوية
    models_to_try = [
        'gemini-1.5-flash',
        'gemini-2.0-flash-exp',
        'gemini-1.5-pro',
        'gemini-pro'
    ]

    for key in keys:
        genai.configure(api_key=key)
        for model_name in models_to_try:
            try:
                model = genai.GenerativeModel(model_name)
                # اختبار سريع للتحقق من العمل
                model.generate_content("test")
                return model
            except Exception:
                continue
    return None

def process_ai_response(user_input, input_type="text"):
    """المعالج الرئيسي للذكاء الاصطناعي"""
    
    # تسجيل النشاط
    user_text_log = user_input if input_type != "image" else "Image Analysis Request"
    log_activity(st.session_state.user_name, input_type, user_text_log)
    
    with st.spinner("🧠 جاري التفكير..."):
        try:
            model = get_working_model()
            if not model:
                st.error("⚠️ خطأ في الاتصال بالذكاء الاصطناعي. يرجى المحاولة لاحقاً.")
                return

            lang = st.session_state.language
            ref_text = st.session_state.get("ref_text", "")
            grade = st.session_state.get("student_grade", "General")
            
            lang_instruction = "Arabic" if lang == "العربية" else "English"
            
            # هندسة الأوامر (Prompt Engineering)
            base_prompt = f"""
            Act as an expert Science Tutor for grade {grade}.
            Answer in {lang_instruction}. Be encouraging, clear, and educational.
            Use emojis to make it fun.
            
            Context from textbook:
            {ref_text[:8000]} (Use this context if relevant, otherwise general science knowledge)
            
            Format instructions:
            - If a diagram/process is explained, you CAN optionally provide a Graphviz DOT code inside a block starting with ```dot and ending with ```.
            - Keep the explanation simple.
            """
            
            response = None
            if input_type == "image":
                # user_input هنا عبارة عن قائمة [نص, صورة]
                response = model.generate_content([base_prompt, user_input[0], user_input[1]])
            else:
                response = model.generate_content(f"{base_prompt}\nStudent Question: {user_input}")
            
            full_text = response.text
            
            # إضافة للمحفوظات
            short_q = str(user_text_log)[:50] + "..." if len(str(user_text_log)) > 50 else str(user_text_log)
            st.session_state.chat_history.append({"role": "user", "content": short_q})
            st.session_state.chat_history.append({"role": "ai", "content": full_text})
            
            # --- معالجة العرض (فصل الكود عن النص) ---
            parts = full_text.split("```dot")
            display_text = parts[0]
            dot_code = None
            
            if len(parts) > 1:
                dot_code = parts[1].split("```")[0]
                if len(parts) > 2:
                    display_text += parts[2] # بقية النص بعد الرسم

            # عرض النص (Streaming Effect)
            st.markdown("---")
            st.chat_message("ai").write(display_text)
            
            # عرض الرسم البياني إذا وجد
            if dot_code:
                try:
                    st.graphviz_chart(dot_code)
                except Exception:
                    pass

            # --- تشغيل الصوت ---
            voice_code = "ar-EG-ShakirNeural" if lang == "العربية" else "en-US-AndrewNeural"
            try:
                # إنشاء حلقة أحداث جديدة لتشغيل الكود غير المتزامن
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                audio_bytes = loop.run_until_complete(generate_audio_stream(display_text[:500], voice_code))
                st.audio(audio_bytes, format='audio/mp3', autoplay=True)
            except Exception as e:
                print(f"TTS Error: {e}")

        except Exception as e:
            st.error(f"حدث خطأ غير متوقع: {e}")

# ==========================================
# 🎨 واجهة المستخدم (UI Flow)
# ==========================================

# تهيئة متغيرات الجلسة
if "auth_status" not in st.session_state:
    st.session_state.update({
        "auth_status": False, 
        "user_type": "none", 
        "chat_history": [],
        "student_grade": "", 
        "current_xp": 0, 
        "last_audio_bytes": None,
        "language": "العربية", 
        "ref_text": "",
        "user_name": "Guest",
        "q_active": False,
        "q_curr": ""
    })

def draw_header():
    st.markdown("""
        <style>
        .header-container {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 1.5rem;
            border-radius: 15px;
            text-align: center;
            color: white;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            margin-bottom: 2rem;
        }
        .header-title { font-size: 2.5rem; font-weight: bold; margin: 0; }
        .header-subtitle { font-size: 1.2rem; opacity: 0.9; margin-top: 5px; }
        </style>
        <div class='header-container'>
            <div class='header-title'>🧬 AI Science Tutor Pro</div>
            <div class='header-subtitle'>معلمك الذكي للعلوم - يعمل بذكاء Gemini</div>
        </div>
    """, unsafe_allow_html=True)

# --- 1. شاشة تسجيل الدخول ---
if not st.session_state.auth_status:
    draw_header()
    
    col_main_1, col_main_2, col_main_3 = st.columns([1, 2, 1])
    with col_main_2:
        st.info(f"💡 {random.choice(DAILY_FACTS)}")
        
        with st.container(border=True):
            st.markdown("### 🔐 تسجيل الدخول")
            with st.form("login_form"):
                name = st.text_input("الاسم ثلاثي:")
                grade = st.selectbox("الصف الدراسي:", 
                                   ["الرابع الابتدائي", "الخامس الابتدائي", "السادس الابتدائي", 
                                    "الأول الإعدادي", "الثاني الإعدادي", "الثالث الإعدادي", "ثانوي"])
                code = st.text_input("كود الدخول:", type="password")
                
                submitted = st.form_submit_button("دخول 🚀", use_container_width=True)
                
                if submitted:
                    if not name or not code:
                        st.warning("يرجى إدخال البيانات كاملة")
                    else:
                        db_pass = get_sheet_data()
                        is_teacher = (code == TEACHER_MASTER_KEY)
                        is_student = (db_pass and code == db_pass)
                        
                        if is_teacher or is_student:
                            st.session_state.auth_status = True
                            st.session_state.user_type = "teacher" if is_teacher else "student"
                            st.session_state.user_name = name if is_student else "Mr. Elsayed (Admin)"
                            st.session_state.student_grade = grade
                            
                            if is_student:
                                st.session_state.current_xp = get_current_xp(name)
                                log_login(name, "student", grade)
                            
                            st.toast("✅ تم تسجيل الدخول بنجاح!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("❌ الكود غير صحيح، راجع المشرف.")
    st.stop()

# --- 2. التطبيق الرئيسي ---
draw_header()

# الشريط الجانبي (Sidebar)
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/4712/4712035.png", width=100)
    st.markdown(f"### أهلاً بك، {st.session_state.user_name} 👋")
    
    st.session_state.language = st.radio("🌐 لغة الشرح:", ["العربية", "English"])
    
    if st.session_state.user_type == "student":
        st.divider()
        st.markdown("### 🏆 إحصائياتك")
        col_xp1, col_xp2 = st.columns(2)
        with col_xp1: st.metric("XP", st.session_state.current_xp)
        with col_xp2: st.metric("Grade", st.session_state.student_grade.split(" ")[0])
        
        if st.session_state.current_xp >= 100:
            st.success("🎉 مستوى متقدم!")
        
        st.divider()
        with st.expander("🏅 لوحة الصدارة", expanded=False):
            leaders = get_leaderboard()
            if leaders:
                for i, r in enumerate(leaders):
                    name_display = r.get('Student_Name', 'Unknown')
                    xp_display = r.get('XP', 0)
                    st.text(f"{i+1}. {name_display} ({xp_display} XP)")
            else:
                st.caption("لا توجد بيانات بعد")

    # تكامل Google Drive
    if DRIVE_FOLDER_ID:
        st.divider()
        st.markdown("### 📚 مكتبة المنهج")
        svc = get_drive_service()
        if svc:
            files = list_drive_files(svc, DRIVE_FOLDER_ID)
            if files:
                book_names = [f['name'] for f in files]
                selected_book = st.selectbox("اختر الكتاب:", book_names)
                
                if st.button("تفعيل الكتاب كمرجع"):
                    file_id = next(f['id'] for f in files if f['name'] == selected_book)
                    with st.spinner("جاري قراءة الكتاب..."):
                        txt = download_pdf_text(svc, file_id)
                        if txt:
                            st.session_state.ref_text = txt
                            st.toast(f"✅ تم تحميل محتوى: {selected_book}", icon="📖")
            else:
                st.caption("المجلد فارغ أو لا يمكن الوصول إليه")

# التبويبات الرئيسية
tab_voice, tab_text, tab_image, tab_quiz = st.tabs([
    "🎙️ تحدث معي", 
    "📝 شات كتابي", 
    "📷 تحليل صورة", 
    "🧠 اختبر نفسك"
])

# 1. تبويب الصوت
with tab_voice:
    st.subheader("اضغط على الميكروفون واسأل 🎤")
    col_mic, col_res = st.columns([1, 4])
    with col_mic:
        audio_data = mic_recorder(
            start_prompt="بدء التسجيل 🔴",
            stop_prompt="إنهاء ⏹️",
            key='voice_recorder'
        )
    
    with col_res:
        if audio_data and audio_data['bytes'] != st.session_state.last_audio_bytes:
            st.session_state.last_audio_bytes = audio_data['bytes']
            
            # تحديد لغة التعرف الصوتي بناءً على اختيار المستخدم
            lang_code = "ar-EG" if st.session_state.language == "العربية" else "en-US"
            
            with st.spinner("جاري تحويل الصوت لنص..."):
                text_input = speech_to_text(audio_data['bytes'], lang_code)
            
            if text_input:
                st.info(f"🗣️ قلت: {text_input}")
                update_xp(st.session_state.user_name, 10) # نقاط النشاط الصوتي
                process_ai_response(text_input, "voice")
            else:
                st.warning("لم أتمكن من سماعك بوضوح، حاول مرة أخرى.")

# 2. تبويب النص
with tab_text:
    st.subheader("اسأل أي سؤال في العلوم 💬")
    
    # عرض المحادثات السابقة
    for msg in st.session_state.chat_history:
        role_icon = "👤" if msg['role'] == "user" else "🤖"
        with st.chat_message(msg['role'], avatar=role_icon):
            # نعرض فقط جزء من النص لتجنب تكرار الرسوم البيانية القديمة بشكل خاطئ
            # (يمكن تحسين هذا بحفظ الهيكل الكامل)
            clean_content = msg['content'].split("```dot")[0]
            st.write(clean_content)

    query = st.chat_input("اكتب سؤالك هنا...")
    if query:
        st.chat_message("user", avatar="👤").write(query)
        update_xp(st.session_state.user_name, 5) # نقاط النشاط الكتابي
        process_ai_response(query, "text")

# 3. تبويب الصور
with tab_image:
    st.subheader("أرسل صورة لمسألة أو رسم توضيحي 📸")
    uploaded_file = st.file_uploader("ارفع الصورة هنا", type=['png', 'jpg', 'jpeg'])
    
    if uploaded_file:
        image = Image.open(uploaded_file)
        st.image(image, caption="الصورة المرفقة", width=300)
        
        txt_prompt = st.text_input("ماذا تريد أن تعرف عن هذه الصورة؟", "اشرح لي هذه الصورة علمياً")
        
        if st.button("تحليل الصورة 🔍"):
            update_xp(st.session_state.user_name, 15) # نقاط تحليل الصور
            process_ai_response([txt_prompt, image], "image")

# 4. تبويب الاختبار (Quiz)
with tab_quiz:
    st.subheader("تحدي الذكاء 🧠")
    
    if st.button("أنشئ لي سؤالاً جديداً 🎲"):
        model = get_working_model()
        if model:
            try:
                prompt = f"""
                Create 1 multiple choice science question for {st.session_state.student_grade}.
                Language: {st.session_state.language}.
                Format: Question followed by 4 options (A, B, C, D). Do NOT give the answer yet.
                """
                res = model.generate_content(prompt)
                st.session_state.q_curr = res.text
                st.session_state.q_active = True
            except:
                st.error("فشل في توليد السؤال")
                
    if st.session_state.q_active:
        st.info(st.session_state.q_curr)
        answer = st.radio("اختر الإجابة:", ["A", "B", "C", "D"], index=None)
        
        if st.button("تحقق من الإجابة ✅"):
            if answer:
                model = get_working_model()
                check_prompt = f"""
                Question: {st.session_state.q_curr}
                Student Answer: {answer}
                Task: Is it correct? Explain briefly why. If correct, start with "CORRECT". If wrong, start with "WRONG".
                Language: {st.session_state.language}
                """
                res = model.generate_content(check_prompt).text
                
                if "CORRECT" in res.upper() or "صحيح" in res or "أحسنت" in res:
                    st.success(res)
                    st.balloons()
                    update_xp(st.session_state.user_name, 50) # نقاط الفوز
                    st.session_state.q_active = False
                else:
                    st.error(res)
                    st.session_state.q_active = False
            else:
                st.warning("الرجاء اختيار إجابة")

# تذييل الصفحة
st.markdown("---")
st.markdown("<div style='text-align: center; color: grey;'>Developed by Mr. Elsayed | AI Science Tutor v2.0</div>", unsafe_allow_html=True)
