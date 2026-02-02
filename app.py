import streamlit as st
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import tempfile
import os
import time
import asyncio
import logging
from io import BytesIO
from typing import Optional, Tuple, List

# محاولة استيراد المكتبات الاختيارية
try:
    from streamlit_mic_recorder import mic_recorder
    MIC_AVAILABLE = True
except ImportError:
    MIC_AVAILABLE = False

try:
    import edge_tts
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False

try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False

# إعداد التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# إعدادات الصفحة
st.set_page_config(
    page_title="المعلم الذكي",
    layout="wide",
    page_icon="🎓",
    initial_sidebar_state="expanded"
)

# CSS محسّن
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');

html, body, .stApp {
    font-family: 'Cairo', sans-serif !important;
    direction: rtl;
    text-align: right;
}

.header-box {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    padding: 1.5rem;
    border-radius: 15px;
    color: white;
    text-align: center;
    margin-bottom: 1.5rem;
    box-shadow: 0 4px 15px rgba(0,0,0,0.2);
}

.stButton > button {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    border-radius: 10px;
    height: 50px;
    width: 100%;
    border: none;
    font-size: 16px;
    font-weight: 600;
    transition: all 0.3s ease;
}

.stButton > button:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}
</style>
""", unsafe_allow_html=True)
# الثوابت
FOLDER_ID = "1ub4ML8q4YCM_VZR991XXQ6hBBas2X6rS"
MAX_RETRIES = 3
RETRY_DELAY = 2
VOICE_NAME = "ar-EG-ShakirNeural"

# الحصول على المفاتيح
def get_api_keys():
    """الحصول على مفاتيح API بشكل آمن"""
    try:
        keys = st.secrets.get("GOOGLE_API_KEYS", [])
        if isinstance(keys, str):
            return [k.strip() for k in keys.split(",") if k.strip()]
        return list(keys) if keys else []
    except Exception as e:
        logger.error(f"خطأ في قراءة المفاتيح: {e}")
        return []

GOOGLE_API_KEYS = get_api_keys()

# خرائط البيانات
STAGES = ["الابتدائية", "الإعدادية", "الثانوية"]

GRADES = {
    "الابتدائية": ["الرابع", "الخامس", "السادس"],
    "الإعدادية": ["الأول", "الثاني", "الثالث"],
    "الثانوية": ["الأول", "الثاني", "الثالث"],
}

TERMS = ["الترم الأول", "الترم الثاني"]

GRADE_MAP = {
    "الرابع": "4",
    "الخامس": "5", 
    "السادس": "6",
    "الأول": "1",
    "الثاني": "2",
    "الثالث": "3"
}

SUBJECT_MAP = {
    "كيمياء": "Chem",
    "فيزياء": "Physics",
    "أحياء": "Biology"
}

AVAILABLE_MODELS = [
    'gemini-2.0-flash',
    'gemini-2.0-flash-lite',
    'gemini-1.5-flash',
    'gemini-1.5-pro',
    'gemini-pro'
]
def subjects_for(stage, grade):
    """الحصول على المواد حسب المرحلة والصف"""
    if stage in ["الابتدائية", "الإعدادية"]:
        return ["علوم"]
    elif stage == "الثانوية":
        if grade == "الأول":
            return ["علوم متكاملة"]
        return ["كيمياء", "فيزياء", "أحياء"]
    return ["علوم"]


def generate_file_name_search(stage, grade, subject, lang_type):
    """توليد اسم الملف للبحث"""
    g_num = GRADE_MAP.get(grade, "1")
    lang_code = "En" if "English" in lang_type else "Ar"

    if stage == "الابتدائية":
        return f"Grade{g_num}_{lang_code}"
    elif stage == "الإعدادية":
        return f"Prep{g_num}_{lang_code}"
    elif stage == "الثانوية":
        if grade == "الأول":
            return f"Sec1_Integrated_{lang_code}"
        else:
            sub_code = SUBJECT_MAP.get(subject, "Chem")
            return f"Sec{g_num}_{sub_code}_{lang_code}"
    return ""
    @st.cache_resource(ttl=3600)
def get_service_account_email():
    """الحصول على إيميل حساب الخدمة"""
    try:
        creds = dict(st.secrets.get("gcp_service_account", {}))
        return creds.get("client_email", "غير متوفر")
    except Exception as e:
        logger.error(f"خطأ: {e}")
        return "خطأ"


def configure_genai(key_index=0):
    """تهيئة Gemini API"""
    if not GOOGLE_API_KEYS:
        return False
    try:
        idx = key_index % len(GOOGLE_API_KEYS)
        genai.configure(api_key=GOOGLE_API_KEYS[idx])
        return True
    except Exception as e:
        logger.error(f"خطأ: {e}")
        return False


@st.cache_resource(ttl=3600)
def get_drive_service():
    """الحصول على خدمة Google Drive"""
    try:
        if "gcp_service_account" not in st.secrets:
            return None
        
        creds_dict = dict(st.secrets["gcp_service_account"])
        
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        
        credentials = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )
        
        return build("drive", "v3", credentials=credentials)
    
    except Exception as e:
        logger.error(f"خطأ: {e}")
        return None
        def find_and_download_book(search_name):
    """البحث عن الكتاب وتحميله"""
    service = get_drive_service()
    
    if not service:
        return None, "فشل الاتصال بـ Google Drive"
    
    query = f"'{FOLDER_ID}' in parents and name contains '{search_name}' and trashed=false"
    
    try:
        results = service.files().list(
            q=query,
            fields="files(id, name, size)",
            pageSize=10
        ).execute()
        
        files = results.get('files', [])
        
        if not files:
            error_msg = "لم يتم العثور على ملف: " + search_name
            return None, error_msg
        
        target_file = files[0]
        logger.info(f"تم العثور على: {target_file['name']}")
        
        # تحميل الملف
        request = service.files().get_media(fileId=target_file['id'])
        
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        tmp_path = tmp_file.name
        
        try:
            downloader = MediaIoBaseDownload(tmp_file, request)
            done = False
            
            while not done:
                status, done = downloader.next_chunk()
            
            tmp_file.close()
            
            # التحقق من الحجم
            actual_size = os.path.getsize(tmp_path)
            if actual_size < 1000:
                os.unlink(tmp_path)
                return None, "الملف فارغ! تأكد من مشاركة المجلد"
            
            return tmp_path, target_file['name']
            
        except Exception as e:
            tmp_file.close()
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise e
            
    except Exception as e:
        logger.error(f"خطأ: {e}")
        return None, str(e)
        def upload_to_gemini(local_path, file_name):
    """رفع الملف إلى Gemini"""
    if not configure_genai():
        return None
    
    try:
        logger.info(f"جاري رفع {file_name}...")
        
        gemini_file = genai.upload_file(local_path, mime_type="application/pdf")
        
        max_wait = 60
        waited = 0
        
        while gemini_file.state.name == "PROCESSING" and waited < max_wait:
            time.sleep(2)
            waited += 2
            gemini_file = genai.get_file(gemini_file.name)
        
        if gemini_file.state.name == "FAILED":
            return None
        
        return gemini_file
        
    except Exception as e:
        logger.error(f"خطأ: {e}")
        return None


def get_book_file(stage, grade, subject, lang_type):
    """الحصول على ملف الكتاب"""
    
    search_name = generate_file_name_search(stage, grade, subject, lang_type)
    
    with st.status("جاري تجهيز الكتاب...", expanded=True) as status:
        st.write("🔍 جاري البحث...")
        local_path, result_msg = find_and_download_book(search_name)
        
        if not local_path:
            status.update(label="فشل", state="error")
            st.error(result_msg)
            return None
        
        st.write(f"✅ تم العثور على: {result_msg}")
        
        try:
            st.write("☁️ جاري الرفع...")
            gemini_file = upload_to_gemini(local_path, result_msg)
            
            if gemini_file:
                status.update(label="تم بنجاح!", state="complete")
                return gemini_file
            else:
                status.update(label="فشل الرفع", state="error")
                return None
                
        finally:
            if os.path.exists(local_path):
                try:
                    os.unlink(local_path)
                except OSError:
                    pass
                    def create_chat_session(gemini_file):
    """إنشاء جلسة محادثة جديدة"""
    
    system_prompt = """أنت معلم مصري خبير. مهمتك:
    1. اشرح من الكتاب المرفق فقط
    2. استخدم اللهجة المصرية البسيطة
    3. قدم أمثلة عملية
    4. شجع الطالب"""
    
    last_error = ""
    
    for api_key in GOOGLE_API_KEYS:
        try:
            genai.configure(api_key=api_key)
            
            for model_name in AVAILABLE_MODELS:
                try:
                    logger.info(f"محاولة: {model_name}")
                    
                    model = genai.GenerativeModel(
                        model_name=model_name,
                        system_instruction=system_prompt
                    )
                    
                    chat = model.start_chat(history=[])
                    
                    # إرسال الكتاب
                    chat.send_message([
                        gemini_file,
                        "تم تحميل الكتاب. أنا جاهز."
                    ])
                    
                    logger.info(f"نجح: {model_name}")
                    return chat
                    
                except Exception as model_error:
                    error_str = str(model_error)
                    
                    if "404" in error_str:
                        continue
                    elif "429" in error_str:
                        time.sleep(RETRY_DELAY)
                        continue
                    else:
                        last_error = error_str
                        
        except Exception as key_error:
            last_error = str(key_error)
    
    st.error("جميع الموديلات غير متاحة حالياً")
    return None


def send_message_with_retry(chat, message, max_retries=3):
    """إرسال رسالة مع إعادة المحاولة"""
    
    for attempt in range(max_retries):
        try:
            response = chat.send_message(message)
            return response.text
            
        except Exception as e:
            error_str = str(e)
            
            if "429" in error_str:
                wait_time = (attempt + 1) * RETRY_DELAY
                time.sleep(wait_time)
                continue
            elif "500" in error_str or "503" in error_str:
                time.sleep(RETRY_DELAY)
                continue
            else:
                logger.error(f"خطأ: {e}")
                return None
    
    return None
   def recognize_speech(audio_bytes):
    """التعرف على الكلام"""
    if not SR_AVAILABLE:
        return None
    
    try:
        recognizer = sr.Recognizer()
        audio_file = BytesIO(audio_bytes)
        
        with sr.AudioFile(audio_file) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language="ar-EG")
            return text
            
    except sr.UnknownValueError:
        st.warning("لم أفهم الكلام")
        return None
    except Exception as e:
        logger.error(f"خطأ: {e}")
        return None


def text_to_speech(text):
    """تحويل النص إلى كلام"""
    if not TTS_AVAILABLE:
        return None
    
    try:
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        tmp_path = tmp_file.name
        tmp_file.close()
        
        async def generate():
            communicate = edge_tts.Communicate(text, VOICE_NAME)
            await communicate.save(tmp_path)
        
        # تشغيل async
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
        
        loop.run_until_complete(generate())
        
        return tmp_path
        
    except Exception as e:
        logger.error(f"خطأ: {e}")
        return None
def init_session_state():
    """تهيئة حالة الجلسة"""
    defaults = {
        "user": {"logged_in": False},
        "chat": None,
        "messages": [],
        "current_book": None,
        "gemini_file": None,
        "tts_enabled": True,
        "login_stage": "الابتدائية"
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def clear_chat():
    """مسح المحادثة"""
    st.session_state.chat = None
    st.session_state.messages = []
    st.session_state.current_book = None
    st.session_state.gemini_file = None


def login_page():
    """صفحة تسجيل الدخول"""
    
    st.markdown("""
    <div class="header-box">
        <h1>🎓 المعلم الذكي</h1>
        <p>منصة تعليمية بالذكاء الاصطناعي</p>
    </div>
    """, unsafe_allow_html=True)
    
    if not GOOGLE_API_KEYS:
        st.error("لم يتم تكوين مفاتيح API")
        return
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("### 📝 بيانات الدخول")
        
        selected_stage = st.selectbox(
            "المرحلة:",
            STAGES,
            index=STAGES.index(st.session_state.login_stage)
        )
        st.session_state.login_stage = selected_stage
        
        with st.form("login_form"):
            name = st.text_input("اسم الطالب:", max_chars=50)
            
            col_a, col_b = st.columns(2)
            
            with col_a:
                grade = st.selectbox("الصف:", GRADES.get(selected_stage, []))
            
            with col_b:
                term = st.selectbox("الترم:", TERMS)
            
            lang_type = st.radio(
                "نوع الدراسة:",
                ["عربي", "English"],
                horizontal=True
            )
            
            submitted = st.form_submit_button("🚀 دخول", use_container_width=True)
            
            if submitted:
                name = name.strip()
                if len(name) < 3:
                    st.error("الاسم قصير جداً")
                else:
                    st.session_state.user = {
                        "logged_in": True,
                        "name": name,
                        "stage": selected_stage,
                        "grade": grade,
                        "term": term,
                        "lang_type": lang_type
                    }
                    st.rerun()
                    def main_app():
    """التطبيق الرئيسي"""
    
    user = st.session_state.user
    
    # الشريط الجانبي
    with st.sidebar:
        st.markdown(f"### 👋 مرحباً {user['name']}")
        
        st.info(f"📚 {user['stage']} - {user['grade']}")
        
        st.divider()
        
        subjects = subjects_for(user['stage'], user['grade'])
        selected_subject = st.radio("📖 المادة:", subjects)
        
        if st.button("📚 فتح الكتاب", use_container_width=True):
            gemini_file = get_book_file(
                user['stage'],
                user['grade'],
                selected_subject,
                user['lang_type']
            )
            
            if gemini_file:
                chat = create_chat_session(gemini_file)
                if chat:
                    st.session_state.chat = chat
                    st.session_state.gemini_file = gemini_file
                    st.session_state.messages = []
                    st.session_state.current_book = selected_subject
                    st.success("تم فتح الكتاب!")
                    st.rerun()
        
        if st.session_state.current_book:
            st.success(f"📖 {st.session_state.current_book}")
        
        st.divider()
        
        with st.expander("⚙️ الإعدادات"):
            st.session_state.tts_enabled = st.checkbox(
                "🔊 القراءة الصوتية",
                value=st.session_state.tts_enabled
            )
            
            if st.button("🗑️ مسح المحادثة"):
                clear_chat()
                st.rerun()
        
        st.divider()
        
        if st.button("🚪 خروج", use_container_width=True):
            clear_chat()
            st.session_state.user = {"logged_in": False}
            st.rerun()
               # المحتوى الرئيسي (تكملة main_app)
    st.markdown("""
    <div class="header-box">
        <h2>🎓 المعلم الذكي</h2>
    </div>
    """, unsafe_allow_html=True)
    
    if not st.session_state.chat:
        st.info("👈 اختر المادة واضغط 'فتح الكتاب'")
        return
    
    # عرض المحادثة
    for msg in st.session_state.messages:
        role = msg["role"]
        content = msg["content"]
        
        with st.chat_message("user" if role == "user" else "assistant"):
            st.markdown(content)
    
    # منطقة الإدخال
    col1, col2 = st.columns([1, 9])
    
    with col1:
        if MIC_AVAILABLE:
            audio_data = mic_recorder(
                start_prompt="🎙️",
                stop_prompt="⏹️",
                key="mic"
            )
        else:
            audio_data = None
    
    with col2:
        text_input = st.chat_input("اكتب سؤالك...")
    
    # معالجة المدخلات
    user_message = text_input
    
    if not user_message and audio_data:
        audio_bytes = audio_data.get('bytes', b'')
        if audio_bytes:
            recognized = recognize_speech(audio_bytes)
            if recognized:
                user_message = recognized
                st.info(f"🎤 {recognized}")
    
    if user_message:
        # إضافة رسالة المستخدم
        st.session_state.messages.append({
            "role": "user",
            "content": user_message
        })
        
        with st.chat_message("user"):
            st.markdown(user_message)
        
        # الرد
        with st.chat_message("assistant"):
            with st.spinner("جاري التفكير..."):
                response = send_message_with_retry(
                    st.session_state.chat,
                    user_message
                )
                
                if response:
                    st.markdown(response)
                    
                    st.session_state.messages.append({
                        "role": "assistant", 
                        "content": response
                    })
                    
                    # الصوت
                    if st.session_state.tts_enabled and TTS_AVAILABLE:
                        audio_path = text_to_speech(response)
                        if audio_path:
                            st.audio(audio_path)
                            try:
                                os.unlink(audio_path)
                            except:
                                pass
                else:
                    st.error("حدث خطأ، حاول مرة أخرى")
        
        st.rerun()
def main():
    """نقطة الدخول"""
    init_session_state()
    
    if st.session_state.user.get("logged_in", False):
        main_app()
    else:
        login_page()


if __name__ == "__main__":
    main()
