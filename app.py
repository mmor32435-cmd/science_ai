import streamlit as st

# ✅ يجب أن يكون أول أمر Streamlit
st.set_page_config(page_title="المعلم الذكي", layout="wide", page_icon="🎓")

# =========================================================
# Imports + Availability checks (بدون إسقاط التطبيق)
# =========================================================
import os
import time
import tempfile
import logging
import random
from contextlib import contextmanager
from typing import List, Optional, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("smart_teacher")

# Google Gemini
try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
    GENAI_IMPORT_ERROR = ""
except Exception as e:
    GENAI_AVAILABLE = False
    GENAI_IMPORT_ERROR = str(e)

# Google Drive
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    DRIVE_AVAILABLE = True
    DRIVE_IMPORT_ERROR = ""
except Exception as e:
    DRIVE_AVAILABLE = False
    DRIVE_IMPORT_ERROR = str(e)

# Optional: mic recorder
try:
    from streamlit_mic_recorder import mic_recorder
    MIC_AVAILABLE = True
except Exception:
    MIC_AVAILABLE = False

# Optional: TTS
try:
    import edge_tts
    import asyncio
    TTS_AVAILABLE = True
except Exception:
    TTS_AVAILABLE = False


# =========================================================
# Streamlit cache compatibility (لتفادي اختلاف الإصدارات)
# =========================================================
def _cache_resource(*dargs, **dkwargs):
    if hasattr(st, "cache_resource"):
        return st.cache_resource(*dargs, **dkwargs)
    if hasattr(st, "experimental_singleton"):
        return st.experimental_singleton(*dargs, **dkwargs)
    return st.cache(*dargs, **dkwargs)


def _cache_data(*dargs, **dkwargs):
    if hasattr(st, "cache_data"):
        return st.cache_data(*dargs, **dkwargs)
    if hasattr(st, "experimental_memo"):
        return st.experimental_memo(*dargs, **dkwargs)
    return st.cache(*dargs, **dkwargs)


# =========================================================
# CSS
# =========================================================
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');
html, body, .stApp {
    font-family: 'Cairo', sans-serif !important;
    direction: rtl;
    text-align: right;
}
.header-box {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    padding: 1.2rem 1.5rem;
    border-radius: 15px;
    color: white;
    text-align: center;
    margin-bottom: 1rem;
}
.small-muted { color: #666; font-size: 0.9rem; }
.stButton > button {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    border-radius: 10px;
    height: 46px;
    width: 100%;
    border: none;
    font-size: 16px;
}
</style>
""",
    unsafe_allow_html=True,
)

# =========================================================
# Constants
# =========================================================
FOLDER_ID = "1ub4ML8q4YCM_VZR991XXQ6hBBas2X6rS"

MAX_RETRIES = 4
BASE_RETRY_DELAY = 1.5
MAX_BACKOFF = 12

VOICE_NAME = "ar-EG-ShakirNeural"

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
    "الثالث": "3",
}
SUBJECT_MAP = {"كيمياء": "Chem", "فيزياء": "Physics", "أحياء": "Biology"}

# =========================================================
# Helpers
# =========================================================
@contextmanager
def status_box(label: str):
    """يدعم st.status لو موجودة وإلا fallback إلى spinner."""
    if hasattr(st, "status"):
        with st.status(label, expanded=True) as s:
            yield s
    else:
        with st.spinner(label):
            yield None


def subjects_for(stage: str, grade: str) -> List[str]:
    if stage in ["الابتدائية", "الإعدادية"]:
        return ["علوم"]
    if stage == "الثانوية":
        if grade == "الأول":
            return ["علوم متكاملة"]
        return ["كيمياء", "فيزياء", "أحياء"]
    return ["علوم"]


def generate_file_name_search(stage: str, grade: str, subject: str, lang_type: str) -> str:
    g_num = GRADE_MAP.get(grade, "1")
    lang_code = "En" if lang_type == "English" else "Ar"

    if stage == "الابتدائية":
        return f"Grade{g_num}_{lang_code}"
    if stage == "الإعدادية":
        return f"Prep{g_num}_{lang_code}"
    if stage == "الثانوية":
        if grade == "الأول":
            return f"Sec1_Integrated_{lang_code}"
        sub_code = SUBJECT_MAP.get(subject, "Chem")
        return f"Sec{g_num}_{sub_code}_{lang_code}"
    return ""


def get_api_keys() -> List[str]:
    """قراءة GOOGLE_API_KEYS من secrets (يدعم list أو string مفصول بفواصل)."""
    try:
        keys = st.secrets.get("GOOGLE_API_KEYS", [])
        if isinstance(keys, str):
            return [k.strip() for k in keys.split(",") if k.strip()]
        if isinstance(keys, (list, tuple)):
            return [str(k).strip() for k in keys if str(k).strip()]
        return []
    except Exception as e:
        logger.error(f"Failed to read GOOGLE_API_KEYS: {e}")
        return []


GOOGLE_API_KEYS = get_api_keys()


def configure_genai_by_key(key: str) -> bool:
    if not GENAI_AVAILABLE:
        return False
    try:
        genai.configure(api_key=key)
        return True
    except Exception as e:
        logger.error(f"genai.configure failed: {e}")
        return False


def normalize_model_name(name: str) -> str:
    """list_models قد يرجّع models/xxx. نطبّعها للأمان."""
    if not name:
        return name
    return name.split("/", 1)[1] if name.startswith("models/") else name


# =========================================================
# Google Drive (Service + Search + Download)
# =========================================================
@_cache_resource(show_spinner=False)
def get_drive_service_cached():
    if not DRIVE_AVAILABLE:
        return None
    try:
        if "gcp_service_account" not in st.secrets:
            return None

        creds_dict = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_dict and isinstance(creds_dict["private_key"], str):
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

        credentials = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=["https://www.googleapis.com/auth/drive.readonly"],
        )
        return build("drive", "v3", credentials=credentials, cache_discovery=False)
    except Exception as e:
        logger.error(f"Drive service build error: {e}")
        return None


def find_best_drive_file(service, search_name: str):
    query = (
        f"'{FOLDER_ID}' in parents and "
        f"name contains '{search_name}' and "
        f"mimeType='application/pdf' and trashed=false"
    )

    results = service.files().list(
        q=query,
        fields="files(id, name, size, modifiedTime, mimeType)",
        pageSize=20,
    ).execute()

    files = results.get("files", [])
    if not files:
        return None

    def to_int(x):
        try:
            return int(x)
        except Exception:
            return 0

    files.sort(key=lambda f: to_int(f.get("size", 0)), reverse=True)
    return files[0]


def download_drive_file(service, file_id: str) -> str:
    request = service.files().get_media(fileId=file_id)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp_path = tmp.name
    downloader = MediaIoBaseDownload(tmp, request)
    done = False

    try:
        while not done:
            _, done = downloader.next_chunk()
        tmp.close()

        if os.path.getsize(tmp_path) < 1500:
            os.unlink(tmp_path)
            raise RuntimeError("الملف تم تنزيله لكنه فارغ/صغير جدًا.")
        return tmp_path
    except Exception:
        try:
            tmp.close()
        except Exception:
            pass
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def find_and_download_book(search_name: str) -> Tuple[Optional[str], str]:
    service = get_drive_service_cached()
    if not service:
        return None, "فشل الاتصال بـ Google Drive (تأكد من Service Account في secrets)."

    try:
        target = find_best_drive_file(service, search_name)
        if not target:
            return None, f"لم يتم العثور على ملف مطابق: {search_name}"

        local_path = download_drive_file(service, target["id"])
        return local_path, target["name"]
    except Exception as e:
        logger.error(f"Drive download error: {e}")
        return None, str(e)


# =========================================================
# Gemini (Dynamic models + Upload + Chat)
# =========================================================
@_cache_data(ttl=3600, show_spinner=False)
def list_generate_models_for_key(api_key: str) -> List[str]:
    """
    يرجع موديلات هذا المفتاح التي تدعم generateContent.
    مهم: يمنع 404 مثل gemini-pro غير المتاح.
    """
    if not GENAI_AVAILABLE:
        return []

    genai.configure(api_key=api_key)

    # لو list_models غير متاحة في إصدار قديم
    if not hasattr(genai, "list_models"):
        # fallback بدون gemini-pro
        return ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]

    models = []
    for m in genai.list_models():
        name = getattr(m, "name", "")
        methods = getattr(m, "supported_generation_methods", []) or []
        if name and ("generateContent" in methods):
            models.append(name)

    preferred = [
        "models/gemini-2.0-flash",
        "models/gemini-2.0-flash-lite",
        "models/gemini-1.5-flash",
        "models/gemini-1.5-pro",
    ]

    ordered = []
    for p in preferred:
        if p in models:
            ordered.append(p)
    for x in models:
        if x not in ordered:
            ordered.append(x)

    return ordered


def upload_to_gemini(local_path: str, api_key: str):
    if not configure_genai_by_key(api_key):
        return None
    try:
        gemini_file = genai.upload_file(local_path, mime_type="application/pdf")

        waited = 0
        while getattr(gemini_file, "state", None) and gemini_file.state.name == "PROCESSING" and waited < 90:
            time.sleep(2)
            waited += 2
            gemini_file = genai.get_file(gemini_file.name)

        if getattr(gemini_file, "state", None) and gemini_file.state.name == "FAILED":
            return None

        return gemini_file
    except Exception as e:
        logger.error(f"Gemini upload error: {e}")
        return None


def create_chat_session(gemini_file):
    if not GENAI_AVAILABLE:
        st.error(f"مكتبة google-generativeai غير متاحة: {GENAI_IMPORT_ERROR}")
        return None
    if not GOOGLE_API_KEYS:
        st.error("لا توجد GOOGLE_API_KEYS داخل secrets.")
        return None

    system_prompt = """
أنت مُعلّم مصري خبير.
اشرح وأجب باستخدام محتوى الكتاب المرفق فقط.
قواعد إلزامية:
- لا تستخدم أي معلومات خارج الكتاب.
- لو السؤال مش موجود في الكتاب: قل "المعلومة دي مش موجودة في الكتاب المرفق".
- خلي الشرح منظم وبسيط باللهجة المصرية.
"""

    last_error = None

    for key in GOOGLE_API_KEYS:
        try:
            genai.configure(api_key=key)
            candidates = list_generate_models_for_key(key)
            if not candidates:
                last_error = "لا توجد موديلات تدعم generateContent لهذا المفتاح."
                continue

            for m in candidates:
                try:
                    model_name = normalize_model_name(m)
                    model = genai.GenerativeModel(
                        model_name=model_name,
                        system_instruction=system_prompt,
                        generation_config={"temperature": 0.2, "top_p": 0.9, "max_output_tokens": 1024},
                    )
                    chat = model.start_chat(history=[])
                    chat.send_message([gemini_file, "تم تحميل الكتاب. التزم بشرحه فقط."])
                    return chat
                except Exception as e:
                    last_error = e
                    continue

        except Exception as e:
            last_error = e
            continue

    st.error(f"فشل إنشاء 
