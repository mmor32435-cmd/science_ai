import streamlit as st

# ==========================================
# 1. إعدادات الصفحة (يجب أن تكون أول أمر Streamlit)
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

# مكتبات خارجية (يجب تثبيتها عبر requirements.txt)
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
        creds_dict = dict(st.secrets["gcp_service_account"]) # تحويل لقاموس لتجنب مشاكل التنسيق
        scope = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds)
    except Exception as e:
        print(f"GSpread Error: {e}")
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

# --- التسجيل في الخلفية (Logging) ---
def _log_bg(user_name, user_type, details, log_type):
    # ننشئ اتصال جديد داخل الـ Thread لتجنب تعارض الـ Cache
    try:
        if "gcp_service_account" not in st.secrets: return
        creds_dict = dict(st.secrets["gcp_service_account"])
        scope = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        
        tz = pytz.timezone('Africa/Cairo')
        now_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

        if log_type == "login":
            try: sheet = client.open(CONTROL_SHEET_NAME).worksheet("Logs")
            except: sheet = client.open(CONTROL_SHEET_NAME).sheet1
            sheet.append_row([now_str, user_type, user_name, str(details)])
        else:
            try: sheet = client.open(CONTROL_SHEET_NAME).worksheet("Activity")
            except: return
            q_text = str(details[1])[:1000] # قص النص الطويل
            sheet.append_row([now_str, user_name, details[0], q_text])
    except Exception as e:
        print(f"Logging Error: {e}")

def log_login(user_name, user_type, details):
    threading.Thread(target=_log_bg, args=(user_name, user_type, details, "login")).start()

def log_activity(user_name, input_type, text):
    threading.Thread(target=_log_bg, args=(user_name, input_type, [input_type, text], "activity")).start()

# --- التلعيب (Gamification) ---
def _xp_bg(user_name, points):
    try:
        if "gcp_service_account" not in st.secrets: return
        creds_dict = dict(st.secrets["gcp_service_account"])
        client = gspread.authorize(service_account.Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets']))
        
        try: sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
        except: return
        
        cell = sheet.find(user_name)
        if cell:
            curr = int(sheet.cell(cell.row, 2).value or 0)
            sheet.update_cell(cell.row, 2, curr + points)
        else:
            sheet.append_row([user_name, points])
    except: pass

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

# --- دوال مساعدة ---
def create_certificate(student_name):
    txt = f"CERTIFICATE OF EXCELLENCE\n\nAwarded to: {student_name}\n\nFor achieving 100 XP in Science.\n\nSigned: Mr. Elsayed"
    return txt.encode('utf-8')

def stream_text_effect(text):
    for word in text.split(" "):
        yield word + " "
        time.sleep(0.02)

# ==========================================
# ☁️ خدمات جوجل درايف
# ==========================================
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
        response = service.files().list(q=query, fields="files(id, name)").execute()
        return response.get('files', [])
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
    # تنظيف النص من الرموز التي تربك القراءة
    clean_text = re.sub(r'[*#_`\[\]()><=]', ' ', text)
    clean_text = re.sub(r'\\.*', '', clean_text) # إزالة أوامر LaTeX
    
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
# 🧠 الذكاء الاصطناعي (Gemini) - تم الإصلاح هنا
# ==========================================
def configure_genai_model():
    """يحاول العثور على مفتاح وموديل صالحين"""
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys and "GOOGLE_API_KEY" in st.secrets:
        keys = [st.secrets["GOOGLE_API_KEY"]]
    
    if not keys: return None

    random.shuffle(keys)
    
    # قائمة النماذج حسب الأولوية لتجنب خطأ 404
    candidate_models = ['gemini-1.5-flash', 'gemini-1.5-flash-latest', 'gemini-1.5-flash-001', 'gemini-pro']

    for key in keys:
        genai.configure(api_key=key)
        for model_name in candidate_models:
            try:
                model = genai.GenerativeModel(model_name)
                # اختبار بسيط للتأكد من أن الموديل يعمل
                # model.generate_content("test") # يمكن تفعيل هذا السطر إذا أردت دقة 100%
                return model
            except Exception:
                continue # جرب الموديل التالي أو المفتاح التالي
    return None

def smart_generate_content(prompt_content):
    model = configure_genai_model()
    if not model:
        raise Exception("API Keys Error or Quota Exceeded")
    
    # محاولة التوليد مع إعادة المحاولة في حالة الخطأ المؤقت
    for _ in range(3):
        try:
            return model.generate_content(prompt_content)
        except Exception as e:
            if "404" in str(e): # إذا كان الخطأ 404، المشكلة في اسم الموديل، لا داعي لإعادة المحاولة بنفس الاسم
                raise e 
            time.sleep(1)
    raise Exception("Failed to generate content after retries")

# 🔥 المعالجة المركزية 🔥
def process_ai_response(user_text, input_type="text"):
    log_activity(st.session_state.user_name, input_type, user_text)
    
    with st.spinner("🧠 Thinking..."):
        try:
            lang_pref = st.session_state.language
            # تحديد تعليمات اللغة
            lang_instr = "Answer in Arabic." if lang_pref == "العربية" else "Answer in English."
            
            ref = st.session_state.get("ref_text", "")
            s_name = st.session_state.user_name
            s_level = st.session_state.get("student_grade", "General")
            
            # تعليمات الرسم البياني
            map_instr = ""
            check_map = ["مخطط", "خريطة", "رسم", "map", "diagram"]
            if any(x in str(user_text).lower() for x in check_map):
                map_instr = "If suitable, output Graphviz DOT code inside ```dot ... ``` block."

            base_prompt = f"""
            Role: Expert Science Tutor. 
            Target Student: {s_level}. Name: {s_name}.
            Instructions: {lang_instr} Use clear formatting. Be encouraging. {map_instr}
            Context/Reference Book Content: {ref[:15000]}
            """
            
            response = None
            if input_type == "image":
                 # user_text here is [prompt, image_object]
                 response = smart_generate_content([base_prompt, user_text[0], user_text[1]])
            else:
                response = smart_generate_content(f"{base_prompt}\nStudent Question: {user_text}")
            
            # معالجة الرد
            full_text = response.text
            st.session_state.chat_history.append((str(user_text)[:50], full_text))
            
            # فصل كود الرسم البياني إذا وجد
            dot_code = None
            display_text = full_text
            
            if "```dot" in full_text:
                parts = full_text.split("```dot")
                display_text = parts[0]
                if len(parts) > 1:
                    dot_code = parts[1].split("```")[0].strip()

            # العرض
            st.markdown("---")
            st.write_stream(stream_text_effect(display_text))
            
            if dot_code:
                try: st.graphviz_chart(dot_code)
                except: pass

            # تشغيل الصوت
            vc_code = "ar-EG-ShakirNeural" if lang_pref == "العربية" else "en-US-AndrewNeural"
            
            # إصلاح مشكلة Asyncio Loop
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                audio_data = loop.run_until_complete(generate_audio_stream(display_text[:500], vc_code)) # قراءة أول 500 حرف فقط لتسريع الاستجابة
                st.audio(audio_data, format='audio/mp3', autoplay=True)
            except Exception as e:
                print(f"Audio Error: {e}")
            
        except Exception as e:
            st.error(f"حدث خطأ: {e}")
            if "404" in str(e):
                st.warning("يرجى تحديث مكتبة google-generativeai أو التحقق من صلاحية مفتاح API.")

# ==========================================
# 🎨 واجهة المستخدم (UI)
# ==========================================

def draw_header():
    st.markdown("""
        <div style='background:linear-gradient(120deg,#89f7fe,#66a6ff);padding:1rem;border-radius:10px;text-align:center;color:#1a2a6c;margin-bottom:1rem;'>
            <h1 style='margin:0;font-size: 2rem;'>🧬 AI Science Tutor</h1>
            <p style='margin:0;font-size: 0.9rem;'>Supervised by: Mr. Elsayed</p>
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

# --- 1. شاشة تسجيل الدخول ---
if not st.session_state.auth_status:
    draw_header()
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.info(f"💡 {random.choice(DAILY_FACTS)}")
        with st.form("login_form"):
            s_name = st.text_input("Name / الاسم:")
            s_grade = st.selectbox("Grade / الصف:", [
                "الرابع الابتدائي", "الخامس الابتدائي", "السادس الابتدائي",
                "الأول الإعدادي", "الثاني الإعدادي", "الثالث الإعدادي",
                "الأول الثانوي", "الثاني الثانوي", "الثالث الثانوي"
            ])
            s_sys = st.radio("System:", ["عربي", "لغات"], horizontal=True)
            code = st.text_input("Code / الكود:", type="password")
            submitted = st.form_submit_button("دخول / Login", use_container_width=True)
        
        if submitted:
            sheet_pass = get_sheet_data()
            if not sheet_pass and code != TEACHER_MASTER_KEY:
                st.error("خطأ في الاتصال بقاعدة البيانات.")
            else:
                is_teacher = (code == TEACHER_MASTER_KEY)
                is_student = (sheet_pass and code == sheet_pass)
                
                if (is_teacher or is_student) and (s_name or is_teacher):
                    st.session_state.auth_status = True
                    st.session_state.user_type = "teacher" if is_teacher else "student"
                    st.session_state.user_name = s_name if is_student else "Mr. Elsayed"
                    st.session_state.student_grade = s_grade
                    st.session_state.study_lang = "English" if "لغات" in s_sys else "Arabic"
                    st.session_state.start_time = time.time()
                    
                    # استرجاع XP وتحديث السجل
                    if is_student:
                        st.session_state.current_xp = get_current_xp(st.session_state.user_name)
                        log_login(st.session_state.user_name, "student", f"{s_grade} | {s_sys}")
                    
                    st.success("تم تسجيل الدخول بنجاح!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("الكود غير صحيح أو الاسم مفقود.")
    st.stop()

# --- 2. التحقق من انتهاء الجلسة ---
if st.session_state.user_type == "student":
    if (time.time() - st.session_state.start_time) > (SESSION_DURATION_MINUTES * 60):
        st.error("انتهى وقت الجلسة (Session Expired). قم بتحديث الصفحة.")
        st.stop()

# --- 3. التطبيق الرئيسي ---
draw_header()

# الشريط الجانبي
with st.sidebar:
    st.write(f"مرحباً، **{st.session_state.user_name}** 👋")
    st.session_state.language = st.radio("لغة التحدث:", ["العربية", "English"], horizontal=True)
    
    if st.session_state.user_type == "student":
        st.metric("🌟 نقاط XP", st.session_state.current_xp)
        if st.session_state.current_xp >= 100:
            st.success("🎉 أحسنت! 100 XP")
            st.download_button("🎓 تحميل الشهادة", create_certificate(st.session_state.user_name), "Certificate.txt")
        
        st.markdown("---")
        st.subheader("🏆 لوحة الشرف")
        leaders = get_leaderboard()
        for i, l in enumerate(leaders):
            st.caption(f"#{i+1} {l['Student_Name']} ({l['XP']} XP)")

    if st.session_state.user_type == "teacher":
        st.success("وضع المعلم 👨‍🏫")
        with st.expander("Control Panel"):
            new_p = st.text_input("New Daily Code:")
            if st.button("Update Code"):
                if update_daily_password(new_p): st.success("Updated!")
                else: st.error("Failed")
    
    st.markdown("---")
    # تحميل كتاب من الدرايف
    if DRIVE_FOLDER_ID:
        service = get_drive_service()
        if service:
            files = list_drive_files(service, DRIVE_FOLDER_ID)
            if files:
                st.subheader("📚 المنهج الدراسي")
                bk = st.selectbox("اختر الكتاب:", [f['name'] for f in files])
                if st.button("تفعيل هذا الكتاب"):
                    fid = next(f['id'] for f in files if f['name'] == bk)
                    with st.spinner("جاري قراءة الكتاب..."):
                        txt = download_pdf_text(service, fid)
                        if txt:
                            st.session_state.ref_text = txt
                            st.toast("تم تفعيل الكتاب كمرجع! ✅")
                        else:
                            st.error("لم أتمكن من قراءة الملف.")

# التبويبات الرئيسية
tab1, tab2, tab3, tab4 = st.tabs(["🎙️ تحدث", "✍️ اسأل", "📷 صورة", "🧠 اختبرني"])

with tab1:
    st.info("اضغط على الميكروفون للتحدث:")
    audio_data = mic_recorder(start_prompt="🎤 اضغط للتحدث", stop_prompt="⏹️ إرسال", key='recorder')
    if audio_data:
        if audio_data['bytes'] != st.session_state.last_audio_bytes:
            st.session_state.last_audio_bytes = audio_data['bytes']
            # تحديد لغة التعرف حسب اختيار المستخدم
            rec_lang = "ar-EG" if st.session_state.language == "العربية" else "en-US"
            txt = speech_to_text(audio_data['bytes'], rec_lang)
            if txt:
                st.chat_message("user").write(txt)
                update_xp(st.session_state.user_name, 10)
                process_ai_response(txt, "voice")
            else:
                st.warning("لم أسمع جيداً، حاول مرة أخرى.")

with tab2:
    q = st.chat_input("اكتب سؤالك هنا...")
    if q:
        st.chat_message("user").write(q)
        update_xp(st.session_state.user_name, 5)
        process_ai_response(q, "text")

with tab3:
    up_file = st.file_uploader("رفع صورة مسألة أو مخطط", type=['png','jpg','jpeg'])
    img_prompt = st.text_input("ما هو سؤالك عن الصورة؟")
    if st.button("تحليل الصورة") and up_file:
        img = Image.open(up_file)
        st.image(img, caption="الصورة المرفقة", width=200)
        p_text = img_prompt if img_prompt else "اشرح هذه الصورة علمياً."
        update_xp(st.session_state.user_name, 15)
        process_ai_response([p_text, img], "image")

with tab4:
    col_q1, col_q2 = st.columns(2)
    with col_q1:
        if st.button("🎲 سؤال عشوائي"):
            p = f"Generate 1 multiple choice question for {st.session_state.student_grade} science. {st.session_state.language}. No answer key."
            try:
                r = smart_generate_content(p)
                st.session_state.current_quiz_question = r.text
                st.session_state.quiz_active = True
                st.rerun()
            except Exception as e: st.error(f"Error: {e}")

    if st.session_state.quiz_active:
        st.markdown("---")
        st.write(st.session_state.current_quiz_question)
        ans = st.text_input("إجابتك:")
        if st.button("تأكيد الإجابة"):
            chk_p = f"Question: {st.session_state.current_quiz_question}\nStudent Answer: {ans}\nVerify if correct. If correct say 'Correct' then explain. If wrong explain why."
            try:
                res = smart_generate_content(chk_p)
                st.write(res.text)
                if "correct" in res.text.lower() or "صحيح" in res.text:
                    st.balloons()
                    update_xp(st.session_state.user_name, 50)
                else:
                    st.warning("حاول مرة أخرى في المرة القادمة!")
                st.session_state.quiz_active = False
            except: pass
