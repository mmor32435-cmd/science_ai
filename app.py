import streamlit as st

# ⚠️ يجب أن يكون أول أمر Streamlit
st.set_page_config(
    page_title="المعلم الذكي",
    layout="wide",
    page_icon="🎓"
)

# ======================================
# استيراد المكتبات مع معالجة الأخطاء
# ======================================
import os
import time
import tempfile
import logging
from io import BytesIO

# إعداد التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# استيراد مكتبات Google
try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    st.error("❌ مكتبة google-generativeai غير مثبتة")

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    DRIVE_AVAILABLE = True
except ImportError:
    DRIVE_AVAILABLE = False
    st.error("❌ مكتبات Google Drive غير مثبتة")

# استيراد المكتبات الاختيارية
try:
    from streamlit_mic_recorder import mic_recorder
    MIC_AVAILABLE = True
except ImportError:
    MIC_AVAILABLE = False

try:
    import edge_tts
    import asyncio
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False

try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False

# ======================================
# CSS
# ======================================
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
}
.stButton > button {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    border-radius: 10px;
    height: 50px;
    width: 100%;
    border: none;
    font-size: 16px;
}
</style>
""", unsafe_allow_html=True)

# ======================================
# الثوابت
# ======================================
FOLDER_ID = "1ub4ML8q4YCM_VZR991XXQ6hBBas2X6rS"
MAX_RETRIES = 3
RETRY_DELAY = 2
VOICE_NAME = "ar-EG-ShakirNeural"

STAGES = ["الابتدائية", "الإعدادية", "الثانوية"]

GRADES = {
    "الابتدائية": ["الرابع", "الخامس", "السادس"],
    "الإعدادية": ["الأول", "الثاني", "الثالث"],
    "الثانوية": ["الأول", "الثاني", "الثالث"],
}

TERMS = ["الترم الأول", "الترم الثاني"]

GRADE_MAP = {
    "الرابع": "4", "الخامس": "5", "السادس": "6",
    "الأول": "1", "الثاني": "2", "الثالث": "3"
}

SUBJECT_MAP = {"كيمياء": "Chem", "فيزياء": "Physics", "أحياء": "Biology"}

AVAILABLE_MODELS = [
    'gemini-2.0-flash',
    'gemini-1.5-flash',
    'gemini-1.5-pro',
    'gemini-pro'
]

# ======================================
# الحصول على المفاتيح
# ======================================
def get_api_keys():
    try:
        keys = st.secrets.get("GOOGLE_API_KEYS", [])
        if isinstance(keys, str):
            return [k.strip() for k in keys.split(",") if k.strip()]
        if keys:
            return list(keys)
        return []
    except Exception as e:
        logger.error(f"خطأ في قراءة المفاتيح: {e}")
        return []

GOOGLE_API_KEYS = get_api_keys()

# ======================================
# وظائف مساعدة
# ======================================
def subjects_for(stage, grade):
    if stage in ["الابتدائية", "الإعدادية"]:
        return ["علوم"]
    elif stage == "الثانوية":
        if grade == "الأول":
            return ["علوم متكاملة"]
        return ["كيمياء", "فيزياء", "أحياء"]
    return ["علوم"]


def generate_file_name_search(stage, grade, subject, lang_type):
    g_num = GRADE_MAP.get(grade, "1")
    lang_code = "En" if "English" in lang_type else "Ar"

    if stage == "الابتدائية":
        return f"Grade{g_num}_{lang_code}"
    elif stage == "الإعدادية":
        return f"Prep{g_num}_{lang_code}"
    elif stage == "الثانوية":
        if grade == "الأول":
            return f"Sec1_Integrated_{lang_code}"
        sub_code = SUBJECT_MAP.get(subject, "Chem")
        return f"Sec{g_num}_{sub_code}_{lang_code}"
    return ""


# ======================================
# خدمات Google
# ======================================
def get_service_account_email():
    try:
        if "gcp_service_account" in st.secrets:
            creds = dict(st.secrets["gcp_service_account"])
            return creds.get("client_email", "غير متوفر")
        return "غير متوفر"
    except Exception:
        return "خطأ"


def configure_genai(key_index=0):
    if not GOOGLE_API_KEYS or not GENAI_AVAILABLE:
        return False
    try:
        idx = key_index % len(GOOGLE_API_KEYS)
        genai.configure(api_key=GOOGLE_API_KEYS[idx])
        return True
    except Exception as e:
        logger.error(f"خطأ: {e}")
        return False


def get_drive_service():
    if not DRIVE_AVAILABLE:
        return None
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


# ======================================
# البحث والتحميل
# ======================================
def find_and_download_book(search_name):
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
            return None, f"لم يتم العثور على ملف: {search_name}"

        target_file = files[0]
        request = service.files().get_media(fileId=target_file['id'])

        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        tmp_path = tmp_file.name

        downloader = MediaIoBaseDownload(tmp_file, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        tmp_file.close()

        if os.path.getsize(tmp_path) < 1000:
            os.unlink(tmp_path)
            return None, "الملف فارغ!"

        return tmp_path, target_file['name']

    except Exception as e:
        logger.error(f"خطأ: {e}")
        return None, str(e)


def upload_to_gemini(local_path, file_name):
    if not configure_genai():
        return None
    try:
        gemini_file = genai.upload_file(local_path, mime_type="application/pdf")
        
        waited = 0
        while gemini_file.state.name == "PROCESSING" and waited < 60:
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
    search_name = generate_file_name_search(stage, grade, subject, lang_type)

    with st.status("جاري تجهيز الكتاب...", expanded=True) as status:
        st.write("🔍 جاري البحث...")
        local_path, result_msg = find_and_download_book(search_name)

        if not local_path:
            status.update(label="فشل", state="error")
            st.error(result_msg)
            return None

        st.write(f"✅ {result_msg}")

        try:
            st.write("☁️ جاري الرفع...")
            gemini_file = upload_to_gemini(local_path, result_msg)

            if gemini_file:
                status.update(label="تم!", state="complete")
                return gemini_file
            status.update(label="فشل الرفع", state="error")
            return None
        finally:
            if os.path.exists(local_path):
                os.unlink(local_path)


# ======================================
# جلسة المحادثة
# ======================================
def create_chat_session(gemini_file):
    system_prompt = """أنت معلم مصري خبير. اشرح من الكتاب المرفق فقط باللهجة المصرية البسيطة."""

    for api_key in GOOGLE_API_KEYS:
        try:
            genai.configure(api_key=api_key)
            for model_name in AVAILABLE_MODELS:
                try:
                    model = genai.GenerativeModel(
                        model_name=model_name,
                        system_instruction=system_prompt
                    )
                    chat = model.start_chat(history=[])
                    chat.send_message([gemini_file, "تم تحميل الكتاب."])
                    return chat
                except Exception as e:
                    if "404" in str(e) or "429" in str(e):
                        continue
        except Exception:
            continue

    st.error("جميع الموديلات غير متاحة")
    return None


def send_message_with_retry(chat, message):
    for attempt in range(MAX_RETRIES):
        try:
            response = chat.send_message(message)
            return response.text
        except Exception as e:
            if "429" in str(e) or "500" in str(e):
                time.sleep((attempt + 1) * 
