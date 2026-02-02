import streamlit as st

# =========================
# لازم يكون أول أمر Streamlit
# =========================
st.set_page_config(page_title="المعلم الذكي", layout="wide", page_icon="🎓")

# =========================
# Imports
# =========================
import os
import time
import tempfile
import logging
import random
import re
from contextlib import contextmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("smart_teacher")

APP_VERSION = "2026-02-02"

# =========================
# Optional imports (Safe)
# =========================
try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
    GENAI_IMPORT_ERROR = ""
except Exception as e:
    GENAI_AVAILABLE = False
    GENAI_IMPORT_ERROR = str(e)

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    DRIVE_AVAILABLE = True
    DRIVE_IMPORT_ERROR = ""
except Exception as e:
    DRIVE_AVAILABLE = False
    DRIVE_IMPORT_ERROR = str(e)

try:
    from streamlit_mic_recorder import mic_recorder
    MIC_AVAILABLE = True
except Exception:
    MIC_AVAILABLE = False

try:
    import edge_tts
    import asyncio
    TTS_AVAILABLE = True
except Exception:
    TTS_AVAILABLE = False


# =========================
# Cache compatibility
# =========================
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


# =========================
# CSS
# =========================
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

# =========================
# Constants
# =========================
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

# منع موديلات preview/deep-research (غالبًا بتكون quota=0 أو غير مناسبة)
ALLOWED_MODELS = [
    "models/gemini-2.0-flash",
    "models/gemini-2.0-flash-lite",
    "models/gemini-1.5-flash",
    "models/gemini-1.5-pro",
]
BLOCKED_SUBSTRINGS = ["deep-research", "preview"]


# =========================
# Helpers
# =========================
@contextmanager
def status_box(label):
    if hasattr(st, "status"):
        with st.status(label, expanded=True) as s:
            yield s
    else:
        with st.spinner(label):
            yield None


def _status_write(status_obj, text):
    try:
        if status_obj is not None and hasattr(status_obj, "write"):
            status_obj.write(text)
    except Exception:
        pass


def _status_update(status_obj, label=None, state=None):
    try:
        if status_obj is None:
            return
        if hasattr(status_obj, "update"):
            kwargs = {}
            if label is not None:
                kwargs["label"] = label
            if state is not None:
                kwargs["state"] = state
            status_obj.update(**kwargs)
    except Exception:
        pass


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
        return "Grade{}_{}".format(g_num, lang_code)
    if stage == "الإعدادية":
        return "Prep{}_{}".format(g_num, lang_code)
    if stage == "الثانوية":
        if grade == "الأول":
            return "Sec1_Integrated_{}".format(lang_code)
        sub_code = SUBJECT_MAP.get(subject, "Chem")
        return "Sec{}_{}_{}".format(g_num, sub_code, lang_code)
    return ""


def get_api_keys():
    try:
        keys = st.secrets.get("GOOGLE_API_KEYS", [])
        if isinstance(keys, str):
            return [k.strip() for k in keys.split(",") if k.strip()]
        if isinstance(keys, (list, tuple)):
            out = []
            for k in keys:
                kk = str(k).strip()
                if kk:
                    out.append(kk)
            return out
        return []
    except Exception as e:
        logger.error("Failed to read GOOGLE_API_KEYS: %s", e)
        return []


GOOGLE_API_KEYS = get_api_keys()


def configure_genai_by_key(key):
    if not GENAI_AVAILABLE:
        return False
    try:
        genai.configure(api_key=key)
        return True
    except Exception as e:
        logger.error("genai.configure failed: %s", e)
        return False


def normalize_model_name(name):
    if not name:
        return name
    if name.startswith("models/"):
        return name.split("/", 1)[1]
    return name


def _is_quota_hard_fail(msg):
    """
    حالات لا ينفع معها Retry:
    - limit: 0
    - check your plan and billing
    - exceeded daily quota
    """
    if msg is None:
        return False
    s = str(msg).lower()

    if ("limit: 0" in s) and ("quota" in s or "free_tier" in s):
        return True
    if "check your plan and billing" in s:
        return True
    if "exceeded your current quota" in s:
        # قد تكون مؤقتة أو يومية؛ لكن نعتبرها hard fail لو ظهر معها billing
        if "billing" in s:
            return True
    if "requests per day" in s or "per day" in s:
        return True
    return False


def _extract_retry_seconds(err_text):
    if not err_text:
        return None
    s = str(err_text)

    # Please retry in 6.508s
    m = re.search(r"retry in ([0-9.]+)s", s, flags=re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            pass

    # retry_delay { seconds: 6 }
    m2 = re.search(r"retry_delay\s*\{\s*seconds:\s*(\d+)\s*\}", s, flags=re.IGNORECASE)
    if m2:
        try:
            return float(m2.group(1))
        except Exception:
            pass

    return None


# =========================
# Google Drive
# =========================
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
        logger.error("Drive service build error: %s", e)
        return None


def find_best_drive_file(service, search_name):
    query = (
        "'{}' in parents and name contains '{}' and mimeType='application/pdf' and trashed=false"
    ).format(FOLDER_ID, search_name)

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


def download_drive_file(service, file_id):
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


def find_and_download_book(search_name):
    service = get_drive_service_cached()
    if not service:
        return None, "فشل الاتصال بـ Google Drive (تأكد من secrets)."

    try:
        target = find_best_drive_file(service, search_name)
        if not target:
            return None, "لم يتم العثور على ملف مطابق: " + str(search_name)

        local_path = download_drive_file(service, target["id"])
        return local_path, target["name"]

    except Exception as e:
        logger.error("Drive download error: %s", e)
        return None, str(e)


# =========================
# Gemini (Allowed models only)
# =========================
@_cache_data(ttl=3600, show_spinner=False)
def list_generate_models_for_key(api_key):
    if not GENAI_AVAILABLE:
        return []

    genai.configure(api_key=api_key)

    # لو list_models غير متاحة: رجّع allowlist بدون models/
    if not hasattr(genai, "list_models"):
        out = []
        for m in ALLOWED_MODELS:
            out.append(m.split("/", 1)[1])
        return out

    available = []
    for m in genai.list_models():
        name = getattr(m, "name", "") or ""
        methods = getattr(m, "supported_generation_methods", []) or []
        if name and ("generateContent" in methods):
            available.append(name)

    candidates = []
    for m in ALLOWED_MODELS:
        if m in available:
            candidates.append(m)

    cleaned = []
    for c in candidates:
        low = c.lower()
        blocked = False
        for b in BLOCKED_SUBSTRINGS:
            if b in low:
                blocked = True
                break
        if not blocked:
            cleaned.append(c)

    return cleaned


def upload_to_gemini(local_path, api_key):
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
        logger.error("Gemini upload error: %s", e)
        return None


def create_chat_session(gemini_file):
    """
    مهم: لا نرسل أي send_message هنا لتفادي استهلاك الكوتا عند إنشاء الجلسة.
    ربط الكتاب يتم عند أول سؤال فقط داخل send_message_with_retry.
    """
    if not GENAI_AVAILABLE:
        st.error("Gemini غير متاح: " + str(GENAI_IMPORT_ERROR))
        return None

    if not GOOGLE_API_KEYS:
        st.error("لا توجد GOOGLE_API_KEYS داخل secrets.")
        return None

    system_prompt = (
        "أنت مُعلّم مصري خبير. "
        "اشرح وأجب باستخدام محتوى الكتاب المرفق فقط. "
        "لو السؤال مش موجود في الكتاب قل: المعلومة دي مش موجودة في الكتاب المرفق."
    )

    last_error = None

    for key in GOOGLE_API_KEYS:
        try:
            genai.configure(api_key=key)

            candidates = list_generate_models_for_key(key)
            if not candidates:
                last_error = "لا توجد موديلات مسموحة/متاحة لهذا المفتاح."
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
                    return chat
                except Exception as e:
                    last_error = e
                    continue

        except Exception as e:
            last_error = e
            continue

    st.error("فشل إنشاء جلسة المحادثة. آخر خطأ: " + str(last_error))
    return None


def send_message_with_retry(chat, message):
    """
    - يربط الكتاب أول مرة فقط (payload = [file, message])
    - يقرأ retry_delay لو موجود
    - لو quota hard fail: يرجع رسالة واضحة
    """
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            if (not st.session_state.get("book_bound", False)) and (st.session_state.get("gemini_file") is not None):
                payload = [st.session_state.gemini_file, message]
            else:
                payload = message

            resp = chat.send_message(payload)
            text = getattr(resp, "text", None) or ""

            # إذا نجح أول إرسال وفيه الملف => اعتبرنا الكتاب اتربط
            if not st.session_state.get("book_bound", False):
                st.session_state.book_bound = True

            if text.strip():
                return text
            return "لم يصل رد نصّي من النموذج."

        except Exception as e:
            last_error = e
            msg = str(e)

            if _is_quota_hard_fail(msg):
                return (
                    "لا يمكن تنفيذ الطلب بسبب الكوتا/الخطة الحالية للمفتاح.\n"
                    "الحل: فعّل Billing أو استخدم API Key بمشروع/حساب لديه كوتا متاحة.\n"
                    "تفاصيل الخطأ: " + msg
                )

            retryable = False
            for token in ["429", "quota", "rate", "500", "502", "503", "504", "timeout"]:
                if token in msg.lower() or token in msg:
                    retryable = True
                    break

            if not retryable:
                break

            wait_s = _extract_retry_seconds(msg)
            if wait_s is None:
                backoff = min(MAX_BACKOFF, BASE_RETRY_DELAY * (2 ** attempt))
                wait_s = backoff + random.uniform(0, 0.6)

            time.sleep(wait_s)

    return "حصل خطأ أثناء الإرسال: " + str(last_error)


# =========================
# Optional TTS
# =========================
async def _tts_to_bytes_async(text, voice):
    communicate = edge_tts.Communicate(text=text, voice=voice)
    audio_bytes = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_bytes += chunk["data"]
    return audio_bytes


def _run_async_safely(coro):
    try:
        loop = asyncio.get_running_loop()
        _ = loop
        new_loop = asyncio.new_event_loop()
        try:
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()
    except RuntimeError:
        return asyncio.run(coro)


def tts_to_bytes(text, voice=VOICE_NAME):
    if not TTS_AVAILABLE:
        return None
    try:
        return _run_async_safely(_tts_to_bytes_async(text, voice))
    except Exception as e:
        logger.error("TTS error: %s", e)
        return None


# =========================
# Chat UI compatibility
# =========================
HAS_CHAT_UI = hasattr(st, "chat_message") and hasattr(st, "chat_input")


@contextmanager
def render_msg(role):
    if HAS_CHAT_UI:
        with st.chat_message(role):
            yield
    else:
        title = "المستخدم" if role == "user" else "المعلم"
        st.markdown("**{}:**".format(title))
        yield
        st.markdown("---")


def get_user_input(label):
    if HAS_CHAT_UI:
        return st.chat_input(label)
    return st.text_input(label)


# =========================
# Session state
# =========================
if "messages" not in st.session_state:
    st.session_state.messages = []
if "chat" not in st.session_state:
    st.session_state.chat = None
if "gemini_file" not in st.session_state:
    st.session_state.gemini_file = None
if "book_label" not in st.session_state:
    st.session_state.book_label = None
if "book_bound" not in st.session_state:
    st.session_state.book_bound = False


def reset_chat():
    st.session_state.messages = []
    st.session_state.chat = None
    st.session_state.gemini_file = None
    st.session_state.book_label = None
    st.session_state.book_bound = False


# =========================
# UI
# =========================
st.markdown(
    (
        '<div class="header-box">'
        "<h1>المعلم الذكي</h1>"
        "<div>اشرح من كتاب المنهج المرفق فقط</div>"
        '<div class="small-muted">Version: {}</div>'
        "</div>"
    ).format(APP_VERSION),
    unsafe_allow_html=True,
)

with st.sidebar:
    st.subheader("الإعدادات")

    if not DRIVE_AVAILABLE:
        st.error("Google Drive libs غير متاحة: " + DRIVE_IMPORT_ERROR)
    if not GENAI_AVAILABLE:
        st.error("Gemini libs غير متاحة: " + GENAI_IMPORT_ERROR)
    if not GOOGLE_API_KEYS:
        st.warning("GOOGLE_API_KEYS غير موجودة في secrets.")

    stage = st.selectbox("المرحلة", STAGES, key="stage")
    grade = st.selectbox("الصف", GRADES[stage], key="grade")
    st.selectbox("الترم", TERMS, key="term")
    lang = st.radio("لغة الكتاب", ["Arabic", "English"], 
