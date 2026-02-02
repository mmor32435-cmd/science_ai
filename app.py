import streamlit as st

# لازم يكون أول أمر Streamlit
st.set_page_config(
    page_title="المعلم الذكي",
    layout="wide",
    page_icon="🎓"
)

# ======================================
# Imports + Safe availability checks
# ======================================
import os
import time
import tempfile
import logging
import random
from contextlib import contextmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("smart_teacher")

# Google Gemini
try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except Exception:
    GENAI_AVAILABLE = False

# Google Drive
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    DRIVE_AVAILABLE = True
except Exception:
    DRIVE_AVAILABLE = False

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


# ======================================
# CSS (RTL + Cairo)
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
""", unsafe_allow_html=True)


# ======================================
# Constants
# ======================================
FOLDER_ID = "1ub4ML8q4YCM_VZR991XXQ6hBBas2X6rS"

MAX_RETRIES = 4
BASE_RETRY_DELAY = 1.5  # seconds
MAX_BACKOFF = 12        # seconds

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
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-pro",
]


# ======================================
# Helpers
# ======================================
@contextmanager
def status_box(label: str):
    """Compatible status wrapper."""
    if hasattr(st, "status"):
        with st.status(label, expanded=True) as s:
            yield s
    else:
        with st.spinner(label):
            yield None


def subjects_for(stage, grade):
    if stage in ["الابتدائية", "الإعدادية"]:
        return ["علوم"]
    if stage == "الثانوية":
        if grade == "الأول":
            return ["علوم متكاملة"]
        return ["كيمياء", "فيزياء", "أحياء"]
    return ["علوم"]


def generate_file_name_search(stage, grade, subject, lang_type):
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


def get_api_keys():
    """Return list of Gemini API keys from Streamlit secrets."""
    try:
        keys = st.secrets.get("GOOGLE_API_KEYS", [])
        if isinstance(keys, str):
            return [k.strip() for k in keys.split(",") if k.strip()]
        if keys:
            return list(keys)
        return []
    except Exception as e:
        logger.error(f"Failed to read GOOGLE_API_KEYS: {e}")
        return []


GOOGLE_API_KEYS = get_api_keys()


def get_service_account_email():
    try:
        if "gcp_service_account" in st.secrets:
            creds = dict(st.secrets["gcp_service_account"])
            return creds.get("client_email", "غير متوفر")
        return "غير متوفر"
    except Exception:
        return "غير متوفر"


def configure_genai_by_key(key: str) -> bool:
    if not GENAI_AVAILABLE:
        return False
    try:
        genai.configure(api_key=key)
        return True
    except Exception as e:
        logger.error(f"genai.configure failed: {e}")
        return False


# ======================================
# Google Drive Service (cached)
# ======================================
@st.cache_resource(show_spinner=False)
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
            scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )
        return build("drive", "v3", credentials=credentials, cache_discovery=False)
    except Exception as e:
        logger.error(f"Drive service build error: {e}")
        return None


# ======================================
# Drive: find + download
# ======================================
def find_best_drive_file(service, search_name: str):
    query = (
        f"'{FOLDER_ID}' in parents and "
        f"name contains '{search_name}' and "
        f"mimeType='application/pdf' and trashed=false"
    )

    results = service.files().list(
        q=query,
        fields="files(id, name, size, modifiedTime)",
        pageSize=20
    ).execute()

    files = results.get("files", [])
    if not files:
        return None

    # pick largest size as best candidate (common if multiple matches)
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


def find_and_download_book(search_name: str):
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


# ======================================
# Gemini: upload PDF + create chat
# ======================================
def upload_to_gemini(local_path: str, key: str):
    if not configure_genai_by_key(key):
        return None

    try:
        gemini_file = genai.upload_file(local_path, mime_type="application/pdf")

        # Wait until processed
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
        st.error("مكتبة google-generativeai غير مثبتة.")
        return None
    if not GOOGLE_API_KEYS:
        st.error("لا يوجد GOOGLE_API_KEYS في secrets.")
        return None

    system_prompt = """
أنت مُعلّم مصري خبير.
مهمتك: الشرح والإجابة باستخدام محتوى الكتاب المرفق فقط.
قواعد إلزامية:
- لا تستخدم أي معلومات خارج الكتاب.
- لو السؤال غير مغطى في الكتاب: قل بوضوح "المعلومة دي مش موجودة في الكتاب المرفق".
- استخدم لهجة مصرية بسيطة ومنظمة: (تعريف → شرح → مثال من الكتاب إن أمكن → سؤال للتأكد).
"""

    last_error = None

    for key in GOOGLE_API_KEYS:
        if not configure_genai_by_key(key):
            continue

        for model_name in AVAILABLE_MODELS:
            try:
                model = genai.GenerativeModel(
                    model_name=model_name,
                    system_instruction=system_prompt,
                    generation_config={
                        "temperature": 0.2,
                        "top_p": 0.9,
                        "max_output_tokens": 1024
                    }
                )
                chat = model.start_chat(history=[])

                # bind file context
                chat.send_message([gemini_file, "ده كتاب المنهج. التزم بشرحه فقط."])
                return chat

            except Exception as e:
                last_error = e
                msg = str(e)
                # common transient errors
                if any(code in msg for code in ["429", "500", "503", "timeout"]):
                    continue
                # model not found/permission
                if "404" in msg or "not found" in msg.lower():
                    continue
                logger.error(f"Create chat failed for {model_name}: {e}")
                continue
