import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import google.generativeai as genai
import gspread
from PIL import Image
import random
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder
import asyncio
import edge_tts
import tempfile
import os
import re
import io
import pdfplumber

# ==========================================
# 1. إعدادات الصفحة
# ==========================================
st.set_page_config(
    page_title="المعلم العلمي | السيد البدوي",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# 2. تصميم الواجهة (نظيف وعالي التباين)
# ==========================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Cairo', sans-serif !important;
        direction: rtl;
        text-align: right;
    }
    .stApp { background-color: #f8f9fa; }

    div[data-baseweb="select"] * {
        background-color: transparent !important;
        border: none !important;
        color: #000000 !important;
    }
    div[data-baseweb="select"] > div {
        background-color: #ffffff !important;
        border: 2px solid #004e92 !important;
        border-radius: 8px !important;
    }
    ul[data-baseweb="menu"] { background-color: #ffffff !important; }
    li[data-baseweb="option"] { color: #000000 !important; }
    li[data-baseweb="option"]:hover { background-color: #e3f2fd !important; }

    .stTextInput input, .stTextArea textarea {
        background-color: #ffffff !important;
        color: #000000 !important;
        border: 2px solid #004e92 !important;
        border-radius: 8px !important;
    }

    h1, h2, h3, h4, h5, p, label, span { color: #000000 !important; }

    .stButton>button {
        background: linear-gradient(90deg, #004e92 0%, #000428 100%) !important;
        color: #ffffff !important;
        border: none;
        border-radius: 10px;
        height: 55px;
        width: 100%;
        font-size: 20px !important;
        font-weight: bold !important;
    }

    .header-box {
        background: linear-gradient(90deg, #000428 0%, #004e92 100%);
        padding: 2rem; border-radius: 15px; text-align: center; margin-bottom: 2rem;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
    }
    .header-box h1, .header-box h3 { color: #ffffff !important; }

    .stChatMessage {
        background-color: #ffffff !important;
        border: 1px solid #d1d1d1 !important;
        border-radius: 12px !important;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""<div class="header-box"><h1>الأستاذ / السيد البدوي</h1><h3>المنصة التعليمية الذكية</h3></div>""", unsafe_allow_html=True)

# ==========================================
# 3. إدارة الجلسة
# ==========================================
if 'user_data' not in st.session_state: st.session_state.user_data = {"logged_in": False, "role": None, "name": "", "grade": "", "stage": "", "lang": "العربية"}
if 'messages' not in st.session_state: st.session_state.messages = []
# تخزين نوع الكتاب: إما ملف (للموديلات الحديثة) أو نص (للقديمة)
if 'book_data' not in st.session_state: st.session_state.book_data = {"type": None, "content": None} 
if 'quiz_active' not in st.session_state: st.session_state.quiz_active = False
if 'last_question' not in st.session_state: st.session_state.last_question = ""

TEACHER_KEY = st.secrets.get("TEACHER_MASTER_KEY", "ADMIN")
SHEET_NAME = st.secrets.get("CONTROL_SHEET_NAME", "App_Control")
FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "")

# ==========================================
# 4. الاتصال والبيانات
# ==========================================
@st.cache_resource
def get_credentials():
    if "gcp_service_account" not in st.secrets: return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_dict: creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        return service_account.Credentials.from_service_account_info(creds_dict, scopes=scopes)
    except: return None

def get_gspread_client():
    creds = get_credentials()
    return gspread.authorize(creds) if creds else None

def check_student_code(input_code):
    client = get_gspread_client()
    if not client: return False
    try:
        sh = client.open(SHEET_NAME)
        real_code = str(sh.sheet1.acell("B1").value).strip()
        return str(input_code).strip() == real_code
    except: return False

# ---------------------------------------------------------
# دالة تحميل الكتاب (ذكية وهجينة)
# ---------------------------------------------------------
def load_book_smartly(stage, grade, lang):
    """
    تحاول هذه الدالة تحميل الكتاب.
    وتعيد كائناً يحتوي على مسار الملف (للاستخدام مع Flash)
    ونص الملف (للاستخدام مع Pro كاحتياطي).
    """
    creds = get_credentials()
    if not creds: return None
    
    try:
        # 1. تحديد الاسم
        target_tokens = []
        if "الثانوية" in stage:
            if "الأول" in grade: target_tokens.append("Sec1")
            elif "الثاني" in grade: target_tokens.append("Sec2")
            elif "الثالث" in grade: target_tokens.append("Sec3")
        elif "الإعدادية" in stage:
            if "الأول" in grade: target_tokens.append("Prep1")
            elif "الثاني" in grade: target_tokens.append("Prep2")
            elif "الثالث" in grade: target_tokens.append("Prep3")
        else:
            if "الرابع" in grade: target_tokens.append("Grade4")
            elif "الخامس" in grade: target_tokens.append("Grade5")
            elif "السادس" in grade: target_tokens.append("Grade6")
            
        lang_code = "Ar" if "العربية" in lang else "En"
        target_tokens.append(lang_code)
        
        service = build('drive', 'v3', credentials=creds)
        query = f"'{FOLDER_ID}' in parents and mimeType='application/pdf'"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        all_files = results.get('files', [])
        
        matched_file = None
        for f in all_files:
            if all(token in f['name'] for token in target_tokens):
                matched_file = f
                break
        
        if not matched_file: return None
        
        # 2. تنزيل الملف
        request = service.files().get_media(fileId=matched_file['id'])
        file_path = f"/tmp/{matched_file['name']}" # حفظ مؤقت
        file_stream = io.BytesIO()
        with open(file_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while done is False: status, done = downloader.next_chunk()
        
        # 3. قراءة النص احتياطياً (Fallback Text)
        text_content = ""
        try:
            with open(file_path, "rb") as f:
                with pdfplumber.open(f) as pdf:
                    for i, page in enumerate(pdf.pages):
                        if i > 80: break
                        extracted = page.extract_text()
                        if extracted: text_content += extracted + "\n"
        except: pass

        return {"path": file_path, "text": text_content, "name": matched_file['name']}

    except Exception as e:
        print(f"Error: {e}")
        return None

# ==========================================
# 5. الصوت
# ==========================================
def clean_text_for_speech(text): return re.sub(r'[\*\#\-\_]', '', text)

def speech_to_text(audio_bytes, lang_code):
    r = sr.Recognizer()
    try:
        audio_io = io.BytesIO(audio_bytes)
        with sr.AudioFile(audio_io) as source:
            audio_data = r.record(source)
            code = "en-US" if "English" in lang_code else "ar-EG"
            return r.recognize_google(audio_data, language=code)
    except: return None

async def generate_speech_async(text, lang_code):
    cleaned = clean_text_for_speech(text)
    voice = "en-US-ChristopherNeural" if "English" in lang_code else "ar-EG-ShakirNeural"
    communicate = edge_tts.Communicate(cleaned, voice)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
        await communicate.save(tmp_file.name)
        return tmp_file.name

def text_to_speech_pro(text, lang_code):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(generate_speech_async(text, lang_code))
    except: return None

# ==========================================
# 6. الذكاء الاصطناعي (الهجين)
# ==========================================
def get_working_model():
    """
    تبحث عن موديل شغال في الحساب.
    تعيد: (اسم الموديل, هل يدعم الملفات؟)
    """
    try:
        all_models = genai.list_models()
        valid_models = [m.name for m in all_models if 'generateContent' in m.supported_generation_methods]
        
        # 1. البحث عن Flash (يدعم ملفات)
        for m in valid_models:
            if 'flash' in m.lower(): return m, True
            
        # 2. البحث عن Pro 1.5 (يدعم ملفات)
        for m in valid_models:
            if 'pro' in m.lower() and '1.5' in m.lower(): return m, True
            
        # 3. أي موديل آخر (غالباً لا يدعم ملفات مباشرة)
        if valid_models: return valid_models[0], False
        
        return None, False
    except: return None, False

def get_ai_response(user_text, img_obj=None):
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys: return "⚠️ المفاتيح مفقودة."
    genai.configure(api_key=random.choice(keys))
    
    u = st.session_state.user_data
    
    # تحميل الكتاب عند الحاجة
    if not st.session_state.book_data["content"]:
        with st.spinner("جاري جلب الكتاب..."):
            data = load_book_smartly(u['stage'], u['grade'], u['lang'])
            if data:
                st.session_state.book_data = data
            else:
                return "⚠️ لم يتم العثور على الكتاب."

    # تحديد الموديل
    model_name, supports_files = get_working_model()
    if not model_name: return "عذراً، لا توجد موديلات متاحة."

    # تجهيز المدخلات
    book_info = st.session_state.book_data
    inputs = []
    
    # التعليمات
    is_english = "English" in u['lang']
    lang_prompt = "Speak ONLY in English." if is_english else "تحدث بالعربية."
    quiz_instr = "أنشئ سؤالاً واحداً فقط." if st.session_state.quiz_active else ""
    
    # السيناريو 1: الموديل يدعم الملفات (Flash/Pro 1.5)
    if supports_files and os.path.exists(book_info['path']):
        # رفع الملف لـ Gemini
        try:
            gemini_file = genai.upload_file(path=book_info['path'], display_name=book_info['name'])
            # انتظار المعالجة
            while gemini_file.state.name == "PROCESSING":
                time.sleep(1)
                gemini_file = genai.get_file(gemini_file.name)
            
            sys_prompt = f"""
            أنت الأستاذ السيد البدوي.
            المرجع: الملف المرفق.
            1. التزم بالمنهج في الملف.
            2. {lang_prompt}
            3. كن مختصراً.
            4. {quiz_instr}
            """
            inputs = [sys_prompt, gemini_file, user_text]
        except:
            # فشل الرفع، نعود للنص
            supports_files = False

    # السيناريو 2: الموديل قديم أو فشل الرفع (نستخدم النص المستخرج)
    if not supports_files:
        context = book_info['text'][:40000] if book_info['text'] else "لا يوجد نص."
        sys_prompt = f"""
        أنت الأستاذ السيد البدوي.
        المرجع النصي:
        {context}
        
        1. أجب من النص أعلاه فقط.
        2. {lang_prompt}
        3. كن مختصراً.
        4. {quiz_instr}
        """
        inputs = [sys_prompt, user_text]

    if img_obj: inputs.append(img_obj)

    try:
        model = genai.GenerativeModel(model_name)
        
        # إدارة حالة الاختبار
        if st.session_state.quiz_active:
            # إذا كنا في وضع الاختبار، نعدل البرومبت ليصحح
            if st.session_state.last_question:
                 # تصحيح
                 prompt_correction = f"""
                 أنت مصحح. سألت الطالب: "{st.session_state.last_question}"
                 أجاب: "{user_text}"
                 صحح الإجابة من المرجع واعط درجة.
                 """
                 inputs[-1] = prompt_correction # استبدال السؤال بتعليمات التصحيح
                 st.session_state.quiz_active = False
                 st.session_state.last_question = ""
            else:
                 # طرح سؤال جديد
                 st.session_state.last_question = "PENDING" # علامة مؤقتة

        response = model.generate_content(inputs)
        resp_text = response.text
        
        if st.session_state.last_question == "PENDING":
            st.session_state.last_question = resp_text
            
        return resp_text
    except Exception as e: return f"خطأ تقني: {e}"

# ==========================================
# 7. الواجهات والتشغيل
# ==========================================
def celebrate_success():
    st.balloons()
    st.toast("🌟 أحسنت!", icon="🎉")

def login_page():
    with st.container():
        st.markdown("### 🔐 تسجيل الدخول")
        with st.form("login"):
            name = st.text_input("الاسم الثلاثي")
            code = st.text_input("الكود السري", type="password")
            st.markdown("---")
            col1, col2 = st.columns(2)
            with col1:
                stage = st.selectbox("المرحلة", ["الابتدائية", "الإعدادية", "الثانوية"])
                lang = st.selectbox("اللغة", ["العربية (علوم)", "English (Science)"])
            with col2:
                grade = st.selectbox("الصف الدراسي", ["الرابع", "الخامس", "السادس", "الأول", "الثاني", "الثالث"])
            
            submit = st.form_submit_button("🚀 بدء التعلم")
            
            if submit:
                if code == TEACHER_KEY:
                    st.session_state.user_data.update({"logged_in": True, "role": "Teacher", "name": name})
                    st.rerun()
                elif check_student_code(code):
                    st.session_state.user_data.update({"logged_in": True, "role": "Student", "name": name, "stage": stage, "grade": grade, "lang": lang})
                    st.session_state.book_data = {"type": None, "content": None} # تصفير
                    st.rerun()
                else:
                    st.error("❌ الكود غير صحيح")

def main_app():
    with st.sidebar:
        st.success(f"مرحباً: {st.session_state.user_data['name']}")
        st.info(f"{st.session_state.user_data['grade']} | {st.session_state.user_data['lang']}")
        
        if st.session_state.book_data["content"] or st.session_state.book_data.get("path"):
            st.success("✅ الكتاب جاهز")
        else:
            st.warning("⚠️ سيتم تحميل الكتاب عند أول سؤال...")
            
        if st.button("📝 ابدأ اختبار"):
             st.session_state.quiz_active = True
             st.session_state.last_question = "" # تصفير السؤال السابق
             st.session_state.messages.append({"role": "user", "content": "أريد اختباراً."})
             
             with st.spinner("جاري إعداد السؤال..."):
                 resp = get_ai_response("أريد اختباراً.")
                 st.session_state.messages.append({"role": "assistant", "content": resp})
                 st.rerun()

        st.write("---")
        if st.button("🚪 خروج"):
            st.session_state.user_data["logged_in"] = False
            st.rerun()

    st.subheader("💬 اسأل المعلم")
    
    col1, col2 = st.columns(2)
    with col1:
        st.info("🎙️ الميكروفون:")
        audio = mic_recorder(start_prompt="تحدث ⏺️", stop_prompt="إرسال ⏹️", key='recorder', format='wav')
    with col2:
        with st.expander("📸 صورة"):
            f = st.file_uploader("رفع", type=['jpg', 'png'])
            img = Image.open(f) if f else None
            if img: st.image(img, width=150)

    voice_text = None
    if audio:
        with st.spinner("جاري السماع..."):
            voice_text = speech_to_text(audio['bytes'], st.session_state.user_data['lang'])

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): st.write(msg["content"])

    text_input = st.chat_input("اكتب إجابتك أو سؤالك هنا...")
    final_q = text_input if text_input else voice_text

    if final_q:
        st.session_state.messages.append({"role": "user", "content": final_q})
        with st.chat_message("user"): st.write(final_q)
        
        with st.chat_message("assistant"):
            with st.spinner("المعلم يفكر..."):
                resp = get_ai_response(final_q, img)
                st.write(resp)
                
                if any(x in resp for x in ["10/10", "9/10", "ممتاز", "أحسنت"]): 
                    celebrate_success()
                
                aud = text_to_speech_pro(resp, st.session_state.user_data['lang'])
                if aud: st.audio(aud, format='audio/mp3')
        
        st.session_state.messages.append({"role": "assistant", "content": resp})

if __name__ == "__main__":
    if st.session_state.user_data["logged_in"]:
        main_app()
    else:
        login_page()
