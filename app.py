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

# ==========================================
# 1. إعدادات الصفحة والتصميم
# ==========================================
st.set_page_config(
    page_title="المعلم العلمي | السيد البدوي",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Cairo', sans-serif !important; direction: rtl; text-align: right; }
    .stApp { background-color: #f8f9fa; }
    div[data-baseweb="select"] > div { background-color: #ffffff !important; border: 2px solid #004e92 !important; }
    .stTextInput input, .stTextArea textarea { background-color: #ffffff !important; border: 2px solid #004e92 !important; color: #000000 !important; }
    h1, h2, h3, p, label, span, div { color: #000000 !important; }
    .stButton>button { background: linear-gradient(90deg, #004e92 0%, #000428 100%) !important; color: #ffffff !important; border: none; height: 50px; width: 100%; font-weight: bold; }
    .header-box { background: linear-gradient(90deg, #000428 0%, #004e92 100%); padding: 2rem; border-radius: 15px; text-align: center; margin-bottom: 2rem; }
    .header-box h1, .header-box h3 { color: #ffffff !important; }
    .stChatMessage { background-color: #ffffff !important; border: 1px solid #d1d1d1 !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("""<div class="header-box"><h1>الأستاذ / السيد البدوي</h1><h3>المنصة التعليمية الذكية</h3></div>""", unsafe_allow_html=True)

# ==========================================
# 3. إدارة الجلسة
# ==========================================
if 'user_data' not in st.session_state: st.session_state.user_data = {"logged_in": False, "role": None, "name": "", "grade": "", "stage": "", "lang": "العربية"}
if 'messages' not in st.session_state: st.session_state.messages = []
# هنا التغيير: سنخزن "مرجع الملف" في Gemini وليس النص
if 'gemini_file' not in st.session_state: st.session_state.gemini_file = None
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
# 🔥 دالة رفع الكتاب إلى Gemini (الحل الجذري للصور)
# ---------------------------------------------------------
def upload_book_to_gemini(stage, grade, lang):
    creds = get_credentials()
    if not creds: return None
    try:
        # 1. البحث عن الملف في Drive
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
        
        # الفلترة
        matched_file = None
        for f in all_files:
            fname = f['name']
            if all(token in fname for token in target_tokens):
                matched_file = f
                break # نأخذ أول ملف مطابق
        
        if not matched_file: return None
        
        # 2. تحميل الملف مؤقتاً
        request = service.files().get_media(fileId=matched_file['id'])
        file_path = f"/tmp/{matched_file['name']}"
        with open(file_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while done is False: status, done = downloader.next_chunk()
            
        # 3. رفعه إلى Gemini
        keys = st.secrets.get("GOOGLE_API_KEYS", [])
        genai.configure(api_key=random.choice(keys))
        
        uploaded_file = genai.upload_file(path=file_path, display_name=matched_file['name'])
        
        # انتظار المعالجة
        while uploaded_file.state.name == "PROCESSING":
            time.sleep(2)
            uploaded_file = genai.get_file(uploaded_file.name)
            
        return uploaded_file

    except Exception as e:
        print(f"Error uploading to Gemini: {e}")
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
# 6. الذكاء الاصطناعي (مع الكتاب المرفق)
# ==========================================
def get_ai_response(user_text, img_obj=None):
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys: return "⚠️ المفاتيح مفقودة."
    genai.configure(api_key=random.choice(keys))
    
    u = st.session_state.user_data
    
    # رفع الكتاب لـ Gemini إذا لم يكن موجوداً
    if not st.session_state.gemini_file:
        with st.spinner("جاري قراءة الكتاب (قد يستغرق دقيقة لأول مرة)..."):
            st.session_state.gemini_file = upload_book_to_gemini(u['stage'], u['grade'], u['lang'])

    if not st.session_state.gemini_file:
        return f"⚠️ عذراً يا {u['name']}، لم أتمكن من العثور على كتاب المنهج في جوجل درايف."

    is_english = "English" in u['lang']
    lang_prompt = "Speak ONLY in English." if is_english else "تحدث بالعربية."

    if st.session_state.quiz_active:
        sys_prompt = f"""
        أنت مصحح اختبارات. السؤال السابق: "{st.session_state.last_question}". إجابة الطالب: "{user_text}".
        المرجع: الكتاب المرفق.
        1. صحح الإجابة. 2. اعط درجة من 10. 3. اشرح من الكتاب. 4. هل تريد سؤالاً آخر؟
        """
        st.session_state.quiz_active = False 
    else:
        is_quiz_request = "اختبار" in user_text or "quiz" in user_text.lower() or "سؤال" in user_text
        if is_quiz_request:
            sys_prompt = f"""
            أنت واضع اختبارات. استخدم الكتاب المرفق.
            1. صغ سؤالاً واحداً عن معلومة موجودة في الكتاب. 2. لا تذكر الإجابة. 3. انتظر الرد.
            """
            st.session_state.quiz_active = True 
        else:
            sys_prompt = f"""
            أنت معلم خاص. المرجع الوحيد هو الكتاب المرفق.
            1. أجب من الكتاب فقط. 2. {lang_prompt} 3. كن مختصراً.
            """

    # إعداد النموذج (Flash يدعم الملفات الكبيرة)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    inputs = [sys_prompt, st.session_state.gemini_file, user_text]
    if img_obj: inputs.append(img_obj)

    try:
        response = model.generate_content(inputs)
        text_response = response.text
        if st.session_state.quiz_active: st.session_state.last_question = text_response
        return text_response
    except Exception as e: return f"خطأ: {e}"

# ==========================================
# 7. الواجهات
# ==========================================
def celebrate_success():
    st.balloons()
    st.toast("🌟 أحسنت يا بطل!", icon="🎉")

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
                    st.session_state.gemini_file = None # تصفير الكتاب
                    st.rerun()
                else:
                    st.error("❌ الكود غير صحيح")

def main_app():
    with st.sidebar:
        st.success(f"مرحباً: {st.session_state.user_data['name']}")
        st.info(f"{st.session_state.user_data['grade']} | {st.session_state.user_data['lang']}")
        
        if st.session_state.gemini_file:
            st.success("✅ الكتاب متصل")
        else:
            st.warning("⚠️ جاري تحميل الكتاب...")
            
        if st.button("📝 ابدأ اختبار"):
             st.session_state.messages.append({"role": "user", "content": "أريد اختباراً."})
             with st.spinner("جاري البحث في الكتاب..."):
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
            with st.spinner("المعلم يراجع الكتاب..."):
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
