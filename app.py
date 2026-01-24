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
import PyPDF2

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
# 2. تصميم عالي التباين
# ==========================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Cairo', sans-serif !important;
        direction: rtl;
        text-align: right;
    }
    .stApp { background-color: #f4f7f6; }
    
    /* نصوص سوداء واضحة */
    .stTextInput input, .stTextArea textarea, .stSelectbox div {
        color: #000000 !important;
        background-color: #ffffff !important;
        font-weight: bold;
    }
    
    .stChatMessage {
        background-color: #ffffff !important;
        border: 1px solid #ddd !important;
        color: #000000 !important;
        font-size: 18px !important;
    }
    
    /* صندوق العنوان */
    .header-box {
        background: linear-gradient(90deg, #16222A 0%, #3A6073 100%);
        padding: 2rem; border-radius: 15px; margin-bottom: 2rem; text-align: center;
    }
    .header-box h1, .header-box h3 { color: #ffffff !important; }
    
    /* الأزرار */
    .stButton>button {
        background-color: #3A6073; color: #ffffff !important; border-radius: 10px; height: 50px; font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="header-box">
    <h1>الأستاذ / السيد البدوي</h1>
    <h3>المنصة التعليمية الذكية - المنهج المصري</h3>
</div>
""", unsafe_allow_html=True)

# ==========================================
# 3. إدارة الجلسة
# ==========================================
if 'user_data' not in st.session_state:
    st.session_state.user_data = {"logged_in": False, "role": None, "name": "", "grade": "", "stage": "", "lang": ""}
if 'messages' not in st.session_state: st.session_state.messages = []
if 'book_content' not in st.session_state: st.session_state.book_content = "" # لتخزين محتوى الكتاب

# ==========================================
# 4. الاتصال بجوجل (Drive + Sheets)
# ==========================================
TEACHER_KEY = st.secrets.get("TEACHER_MASTER_KEY", "ADMIN")
SHEET_NAME = st.secrets.get("CONTROL_SHEET_NAME", "App_Control")
DRIVE_FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "")

@st.cache_resource
def get_credentials():
    if "gcp_service_account" not in st.secrets: return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
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
# 🔥 دالة جلب الكتاب من Drive (جديدة)
# ---------------------------------------------------------
@st.cache_resource
def get_book_text_from_drive(grade, lang):
    """
    تبحث عن ملف PDF المناسب في درايف وتقرأ نصوصه
    """
    creds = get_credentials()
    if not creds: return None
    
    try:
        # بناء اسم الملف المتوقع (مثلاً: Grade4_Ar.pdf)
        # تحويل الاسم العربي لرمز
        grade_map = {
            "الرابع": "Grade4", "الخامس": "Grade5", "السادس": "Grade6",
            "الأول": "Prep1", "الثاني": "Prep2", "الثالث": "Prep3"
        }
        lang_code = "Ar" if "العربية" in lang else "En"
        file_prefix = grade_map.get(grade, "Grade4")
        expected_name = f"{file_prefix}_{lang_code}" # جزء من الاسم للبحث عنه
        
        service = build('drive', 'v3', credentials=creds)
        
        # البحث عن الملف
        query = f"name contains '{expected_name}' and mimeType='application/pdf'"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])
        
        if not files:
            return None # لم يتم العثور على الكتاب
            
        file_id = files[0]['id']
        
        # تحميل الملف
        request = service.files().get_media(fileId=file_id)
        file_stream = io.BytesIO()
        downloader = MediaIoBaseDownload(file_stream, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            
        # استخراج النص من PDF
        file_stream.seek(0)
        pdf_reader = PyPDF2.PdfReader(file_stream)
        text = ""
        # قراءة أول 100 صفحة (لتجنب الحجم الضخم)
        for page in pdf_reader.pages[:100]:
            text += page.extract_text() + "\n"
            
        return text
    except Exception as e:
        print(f"Error reading book: {e}")
        return None

# ==========================================
# 5. الصوت والميكروفون
# ==========================================

def clean_text_for_speech(text):
    text = re.sub(r'[\*\#\-\_]', '', text)
    return text

def speech_to_text(audio_bytes):
    r = sr.Recognizer()
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
            tmp_file.write(audio_bytes)
            tmp_filename = tmp_file.name
        
        with sr.AudioFile(tmp_filename) as source:
            # زيادة الحساسية
            # r.energy_threshold = 300 
            audio_data = r.record(source)
            text = r.recognize_google(audio_data, language="ar-EG")
        os.remove(tmp_filename)
        return text
    except: return None

async def generate_speech_async(text, voice="ar-EG-ShakirNeural"):
    cleaned = clean_text_for_speech(text)
    communicate = edge_tts.Communicate(cleaned, voice)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
        await communicate.save(tmp_file.name)
        return tmp_file.name

def text_to_speech_pro(text):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(generate_speech_async(text))
    except: return None

# ==========================================
# 6. الذكاء الاصطناعي (مع الكتاب المدرسي)
# ==========================================
def get_ai_response(user_text, img_obj=None, is_quiz_mode=False):
    try:
        keys = st.secrets.get("GOOGLE_API_KEYS", [])
        if not keys: return "⚠️ المفاتيح مفقودة."
        genai.configure(api_key=random.choice(keys))
        
        u = st.session_state.user_data
        
        # تحميل محتوى الكتاب إذا لم يكن موجوداً
        if not st.session_state.book_content:
            with st.spinner("جاري تحميل الكتاب المدرسي من جوجل درايف..."):
                book_text = get_book_text_from_drive(u['grade'], u['lang'])
                if book_text:
                    st.session_state.book_content = book_text
                else:
                    st.toast("⚠️ لم أعثر على الكتاب في الدرايف، سأعتمد على معلوماتي العامة.", icon="⚠️")

        # تعليمات المعلم
        lang_prompt = "اشرح بالعربية." if "العربية" in u['lang'] else "Explain in English."
        
        # إضافة محتوى الكتاب للتعليمات (RAG)
        context_data = ""
        if st.session_state.book_content:
            context_data = f"استخدم محتوى الكتاب التالي للإجابة:\n{st.session_state.book_content[:50000]}..." # نأخذ جزءاً كبيراً
        
        quiz_instruction = ""
        if is_quiz_mode:
            quiz_instruction = """
            الطالب يطلب اختباراً. قم بإنشاء سؤال واحد فقط (اختيار من متعدد) بناءً على المنهج.
            لا تذكر الإجابة، انتظر رد الطالب.
            """
        
        sys_prompt = f"""
        أنت الأستاذ السيد البدوي.
        {context_data}
        
        تعليمات:
        1. التزم بالمنهج المصري والكتاب المرفق.
        2. {lang_prompt}
        3. كن مختصراً ومفيداً (نقاط).
        4. {quiz_instruction}
        5. إذا أجاب الطالب إجابة صحيحة، قل له عبارة تشجيعية قوية (أحسنت يا بطل، ممتاز..).
        """
        
        model = genai.GenerativeModel('gemini-1.5-flash')
        inputs = [sys_prompt, user_text]
        if img_obj: inputs.extend([img_obj, "اشرح الصورة."])
        
        return model.generate_content(inputs).text
    except Exception as e: return f"خطأ: {e}"

# ==========================================
# 7. وظائف التحفيز (Gamification)
# ==========================================
def celebrate_success():
    """تشغيل تأثيرات الاحتفال"""
    st.balloons()
    st.toast("🌟 إجابة ممتازة! أحسنت!", icon="🎉")

# ==========================================
# 8. الواجهات والتشغيل
# ==========================================
def login_page():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### 🔐 تسجيل الدخول")
        with st.form("login"):
            name = st.text_input("الاسم")
            code = st.text_input("الكود", type="password")
            st.markdown("---")
            c1, c2 = st.columns(2)
            with c1:
                stage = st.selectbox("المرحلة", ["الابتدائية", "الإعدادية"])
                lang = st.selectbox("اللغة", ["العربية (علوم)", "English (Science)"])
            with c2:
                grade = st.selectbox("الصف", ["الرابع", "الخامس", "السادس", "الأول", "الثاني", "الثالث"])
            
            if st.form_submit_button("دخول"):
                if code == TEACHER_KEY:
                    st.session_state.user_data.update({"logged_in": True, "role": "Teacher", "name": name})
                    st.rerun()
                elif check_student_code(code):
                    st.session_state.user_data.update({"logged_in": True, "role": "Student", "name": name, "stage": stage, "grade": grade, "lang": lang})
                    # تصفير الكتاب عند دخول جديد
                    st.session_state.book_content = ""
                    st.rerun()
                else:
                    st.error("الكود خطأ")

def main_app():
    with st.sidebar:
        st.success(f"مرحباً: {st.session_state.user_data['name']}")
        st.info(f"{st.session_state.user_data['grade']}")
        
        # أزرار تحكم سريعة
        if st.button("📝 اختبار سريع"):
             st.session_state.messages.append({"role": "user", "content": "أريد اختباراً قصيراً على الدرس الحالي."})
        
        if st.button("🚪 خروج"):
            st.session_state.user_data["logged_in"] = False
            st.rerun()

    st.subheader("💬 اسأل المعلم أو اطلب اختباراً")
    
    c_mic, c_img = st.columns([1, 1])
    with c_mic:
        st.info("🎙️ اضغط للتحدث:")
        audio = mic_recorder(start_prompt="تسجيل ⏺️", stop_prompt="إرسال ⏹️", key='recorder')
    
    with c_img:
        with st.expander("📸 إرفاق صورة"):
            f = st.file_uploader("اختر صورة", type=['jpg', 'png'])
            img = Image.open(f) if f else None
            if img: st.image(img, width=150)

    voice_text = None
    if audio:
        with st.spinner("جاري المعالجة..."):
            voice_text = speech_to_text(audio['bytes'])
            if not voice_text: st.warning("⚠️ الصوت غير واضح.")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): st.write(msg["content"])

    text_input = st.chat_input("اكتب هنا...")
    final_q = text_input if text_input else voice_text

    if final_q:
        st.session_state.messages.append({"role": "user", "content": final_q})
        with st.chat_message("user"): st.write(final_q)
        
        with st.chat_message("assistant"):
            with st.spinner("الأستاذ السيد يفكر..."):
                # فحص هل هذا طلب اختبار؟
                is_quiz = "اختبار" in final_q or "سؤال" in final_q or "quiz" in final_q.lower()
                
                resp_text = get_ai_response(final_q, img, is_quiz_mode=is_quiz)
                st.write(resp_text)
                
                # التحفيز: إذا احتوت إجابة المعلم على كلمات مدح، نشغل الاحتفال
                if any(word in resp_text for word in ["أحسنت", "ممتاز", "رائع", "Excellent", "Bravo"]):
                    celebrate_success()
                
                audio_file = text_to_speech_pro(resp_text)
                if audio_file:
                    st.audio(audio_file, format='audio/mp3')
        
        st.session_state.messages.append({"role": "assistant", "content": resp_text})

if __name__ == "__main__":
    if st.session_state.user_data["logged_in"]:
        main_app()
    else:
        login_page()
