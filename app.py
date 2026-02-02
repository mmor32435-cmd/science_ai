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
from dataclasses import dataclass
from contextlib import contextmanager

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

# =========================
# إعداد التسجيل (Logging)
# =========================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =========================
# 1. إعدادات الصفحة
# =========================
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

.status-box {
    padding: 1rem;
    border-radius: 10px;
    margin: 0.5rem 0;
}

.success-box { background: #d4edda; border: 1px solid #c3e6cb; }
.error-box { background: #f8d7da; border: 1px solid #f5c6cb; }
.info-box { background: #d1ecf1; border: 1px solid #bee5eb; }
</style>
""", unsafe_allow_html=True)

# =========================
# 2. الثوابت والإعدادات
# =========================
@dataclass
class AppConfig:
    """إعدادات التطبيق"""
    FOLDER_ID: str = "1ub4ML8q4YCM_VZR991XXQ6hBBas2X6rS"
    MAX_RETRIES: int = 3
    RETRY_DELAY: int = 2
    FILE_EXPIRY_HOURS: int = 1
    VOICE_NAME: str = "ar-EG-ShakirNeural"

CONFIG = AppConfig()

# الحصول على المفاتيح بشكل آمن
def get_api_keys() -> List[str]:
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

# =========================
# 3. خرائط البيانات
# =========================
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

SUBJECT_MAP = {
    "كيمياء": "Chem",
    "فيزياء": "Physics",
    "أحياء": "Biology"
}

# =========================
# 4. وظائف مساعدة
# =========================
def subjects_for(stage: str, grade: str) -> List[str]:
    """الحصول على المواد حسب المرحلة والصف"""
    if stage in ["الابتدائية", "الإعدادية"]:
        return ["علوم"]
    elif stage == "الثانوية":
        if grade == "الأول":
            return ["علوم متكاملة"]
        return ["كيمياء", "فيزياء", "أحياء"]
    return ["علوم"]


def generate_file_name_search(stage: str, grade: str, subject: str, lang_type: str) -> str:
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


@contextmanager
def temp_file_manager(suffix: str = ".pdf"):
    """مدير الملفات المؤقتة مع التنظيف التلقائي"""
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
            yield tmp
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError as e:
                logger.warning(f"فشل حذف الملف المؤقت: {e}")

# =========================
# 5. خدمات جوجل
# =========================
@st.cache_resource(ttl=3600)
def get_service_account_email() -> str:
    """الحصول على إيميل حساب الخدمة"""
    try:
        creds = dict(st.secrets.get("gcp_service_account", {}))
        return creds.get("client_email", "غير متوفر")
    except Exception as e:
        logger.error(f"خطأ في قراءة إيميل الخدمة: {e}")
        return "خطأ في القراءة"


def configure_genai(key_index: int = 0) -> bool:
    """تهيئة Gemini API"""
    if not GOOGLE_API_KEYS:
        logger.error("لا توجد مفاتيح API")
        return False
    
    try:
        idx = key_index % len(GOOGLE_API_KEYS)
        genai.configure(api_key=GOOGLE_API_KEYS[idx])
        return True
    except Exception as e:
        logger.error(f"خطأ في تهيئة Gemini: {e}")
        return False


@st.cache_resource(ttl=3600)
def get_drive_service():
    """الحصول على خدمة Google Drive"""
    try:
        if "gcp_service_account" not in st.secrets:
            logger.error("لم يتم العثور على بيانات حساب الخدمة")
            return None
        
        creds_dict = dict(st.secrets["gcp_service_account"])
        
        # إصلاح المفتاح الخاص
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        
        credentials = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )
        
        return build("drive", "v3", credentials=credentials)
    
    except Exception as e:
        logger.error(f"خطأ في إنشاء خدمة Drive: {e}")
        return None


def find_and_download_book(search_name: str) -> Tuple[Optional[str], str]:
    """البحث عن الكتاب وتحميله"""
    service = get_drive_service()
    
    if not service:
        return None, "❌ فشل الاتصال بـ Google Drive"
    
    query = f"'{CONFIG.FOLDER_ID}' in parents and name contains '{search_name}' and trashed=false"
    
    try:
        results = service.files().list(
            q=query,
            fields="files(id, name, size)",
            pageSize=10
        ).execute()
        
        files = results.get('files', [])
        
        if not files:
            return None, f"❌ لم يتم العثور 
