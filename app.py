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
import pdfplumber  # المكتبة الجديدة القوية

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
# 2. تصميم احترافي
# ==========================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Cairo', sans-serif !important;
        direction: rtl;
        text-align: right;
    }
    .stApp { background-color: #f7f9fc; }
    
    /* تنسيق الحقول */
    .stTextInput input, .stSelectbox div {
        background-color: #ffffff !important;
        border: 2px solid #004e92 !important;
        color: #000000 !important;
        font-weight: bold !important;
    }
    
    /* الأزرار */
    .stButton>button {
        background: linear-gradient(90deg, #004e92 0%, #000428 100%) !important;
        color: #ffffff !important; border: none; height: 50px; font-size: 18px !important;
    }
    
    .header-box {
        background: linear-gradient(90deg, #000428 0%, #004e92 100%);
        padding: 2rem; border-radius: 15px; text-align: center; margin-bottom: 2rem;
    }
    .header-box h1, .header-box h3 { color: #ffffff !important; }
    
    .stChatMessage {
        background-color: #ffffff !important;
        border: 1px solid #d1d1d1 !important;
        color: #000000 !important;
    }
    p, div, label { color: #000000 !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("""<div class="header-box"><h1>الأستاذ / السيد البدوي</h1><h3>المنصة التعليمية الذكية</h3></div>""", unsafe_allow_html=True)

# ==========================================
# 3. إدارة الجلسة
# ==========================================
if 'user_data' not in st.session_state: st.session_state.user_data = {"logged_in": False, "role": None, "name": "", "grade": "", "stage": "", "lang": "العربية"}
if 'messages' not in st.session_state: st.session_state.messages = []
if 'book_content' not in st.session_state: st.session_state.book_content = ""

TEACHER_KEY = st.secrets.get("TEACHER_MASTER_KEY", "ADMIN")
SHEET_NAME = st.secrets.get("CONTROL_SHEET_NAME", "App_Control")

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
# 🔥 دالة قراءة الكتب (باستخدام pdfplumber القوي)
# ---------------------------------------------------------
@st.cache_resource
def get_book_text_from_drive(stage, grade, lang):
    creds = get_credentials()
    if not creds: return None
    try:
        # تحديد اسم الملف
        file_prefix = ""
        if "الثانوية" in stage:
            mapping = {"الأول": "Sec1", "الثاني": "Sec2", "الثالث": "Sec3"}
            file_prefix = mapping.get(grade, "Sec1")
        elif "الإعدادية" in stage:
            mapping = {"الأول": "Prep1", "الثاني": "Prep2", "الثالث": "Prep3"}
            file_prefix = mapping.get(grade, "Prep1")
        else:
            mapping = {"الرابع": "Grade4", "الخامس": "Grade5", "السادس": "Grade6"}
            file_prefix = mapping.get(grade, "Grade4")
            
        lang_code = "Ar" if "العربية" in lang else "En"
        # البحث عن أي ملف يحتوي على الاسم (لتفادي أخطاء التسمية البسيطة)
        search_query = f"name contains '{file_prefix}_' and name contains '_{lang_code}'"
        
        service = build('drive', 'v3', credentials=creds)
        results = service.files().list(q=f"{search_query} and mimeType='application/pdf'", fields="files(id, name)").execute()
        files = results.get('files', [])
        
        if not files: return None
        
        full_text = ""
        for file in files:
            try:
                request = service.files().get_media(fileId=file['id'])
                file_stream = io.BytesIO()
                downloader = MediaIoBaseDownload(file_stream, request)
                done = False
                while done is False: status, done = downloader.next_chunk()
                
                file_stream.seek(0)
                # 🔥 استخدام pdfplumber بدلاً من PyPDF2 لدقة أعلى
                with pdfplumber.open(file_stream) as pdf:
                    # قراءة أول 100 صفحة (كمية كافية جداً)
                    for i, page in enumerate(pdf.pages):
                        if i > 100: break
                        text = page.extract_text()
                        if text: full_text += text + "\n"
            except: continue
            
        return full_text if full_text else None
    except: return None

# ==========================================
# 4. الصوت والميكروفون
# ==========================================
def clean_text_for_speech(text):
    return re.sub(r'[\*\#\-\_]', '', text)

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
# 5. الذكاء الاصطناعي (منطق مرن)
# ==========================================
def get_dynamic_model():
    try:
        all_models = genai.list_models()
        valid_models = [m.name for m in all_models if 'generateContent' in m.supported_generation_methods]
        if not valid_models: return None
        for m in valid_models:
            if 'flash' in m.lower(): return m
        for m in valid_models:
            if 'pro' in m.lower(): return m
        return valid_models[0]
    except: return None

def get_ai_response(user_text, img_obj=None, is_quiz_mode=False):
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys: return "⚠️ المفاتيح مفقودة."
    genai.configure(api_key=random.choice(keys))
    
    model_name = get_dynamic_model()
    if not model_name: return "عذراً، لا توجد نماذج متاحة."
    
    u = st.session_state.user_data
    if not st.session_state.book_content:
        st.session_state.book_content = get_book_text_from_drive(u['stage'], u['grade'], u['lang'])

    is_english = "English" in u['lang']
    lang_prompt = "Speak ONLY in English." if is_english else "تحدث بالعربية."
    
    context = ""
    if st.session_state.book_content:
        # زيادة حجم السياق
        context = f"استعن بهذا النص من كتاب الوزارة:\n{st.session_state.book_content[:50000]}..."
    
    quiz_instr = "أنشئ سؤالاً واحداً فقط وانتظر الإجابة." if is_quiz_mode else ""

    # تخفيف القيود قليلاً (Flexible Curriculum)
    sys_prompt = f"""
    أنت معلم علوم خبير (السيد البدوي).
    {context}
    
    التعليمات:
    1. حاول الإجابة من النص أعلاه قدر الإمكان.
    2. إذا لم تجد المعلومة حرفياً في النص ولكنها من صلب المنهج العام (علوم/فيزياء/كيمياء)، أجب عليها باختصار ولا تقل "غير موجود".
    3. {lang_prompt}
    4. كن مختصراً جداً.
    5. {quiz_instr}
    """
    
    inputs = [sys_prompt, user_text]
    if img_obj: inputs.extend([img_obj, "اشرح الصورة."])

    try:
        model = genai.GenerativeModel(model_name)
        return model.generate_content(inputs).text
    except Exception as e: return f"خطأ: {e}"

# ==========================================
# 6. الواجهات والتشغيل
# ==========================================
def celebrate_success():
    st.balloons()
    st.toast("🌟 Excellent! / ممتاز!", icon="🎉")

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
                    st.session_state.book_content = ""
                    st.rerun()
                else:
                    st.error("❌ الكود غير صحيح")

def main_app():
    with st.sidebar:
        st.success(f"مرحباً: {st.session_state.user_data['name']}")
        st.info(f"{st.session_state.user_data['grade']} | {st.session_state.user_data['lang']}")
        if st.button("📝 Quiz / اختبار"):
             st.session_state.messages.append({"role": "user", "content": "اختبرني / Quiz me"})
        st.write("---")
        if st.button("🚪 خروج"):
            st.session_state.user_data["logged_in"] = False
            st.rerun()

    st.subheader("💬 اسأل المعلم")
    
    col1, col2 = st.columns(2)
    with col1:
        st.info("🎙️ Mic:")
        audio = mic_recorder(start_prompt="Record ⏺️", stop_prompt="Send ⏹️", key='recorder', format='wav')
    with col2:
        with st.expander("📸 Image"):
            f = st.file_uploader("Upload", type=['jpg', 'png'])
            img = Image.open(f) if f else None
            if img: st.image(img, width=150)

    voice_text = None
    if audio:
        with st.spinner("Listening..."):
            voice_text = speech_to_text(audio['bytes'], st.session_state.user_data['lang'])

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): st.write(msg["content"])

    text_input = st.chat_input("Type here...")
    final_q = text_input if text_input else voice_text

    if final_q:
        st.session_state.messages.append({"role": "user", "content": final_q})
        with st.chat_message("user"): st.write(final_q)
        
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                is_quiz = "اختبار" in final_q or "quiz" in final_q.lower()
                resp = get_ai_response(final_q, img, is_quiz)
                st.write(resp)
                
                if any(x in resp.lower() for x in ["أحسنت", "ممتاز", "correct", "good"]): 
                    celebrate_success()
                
                aud = text_to_speech_pro(resp, st.session_state.user_data['lang'])
                if aud: st.audio(aud, format='audio/mp3')
        
        st.session_state.messages.append({"role": "assistant", "content": resp})

if __name__ == "__main__":
    if st.session_state.user_data["logged_in"]:
        main_app()
    else:
        login_page()
