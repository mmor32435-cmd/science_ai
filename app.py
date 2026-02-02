import streamlit as st

st.set_page_config(page_title="المعلم الذكي", layout="wide", page_icon="🎓")

import os
import time
import tempfile
import logging
import random
from contextlib import contextmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("smart_teacher")

APP_VERSION = "2026-02-02"

# ----------------------------
# Optional imports (safe)
# ----------------------------
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


# ----------------------------
# Cache compatibility
# ----------------------------
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


# ----------------------------
# CSS
# ----------------------------
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');
html, body, .stApp { font-family: 'Cairo', sans-serif !important; direction: rtl; text-align: right; }
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

# ----------------------------
# Constants
# ----------------------------
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


# ----------------------------
# Helpers
# ----------------------------
@contextmanager
def status_box(label):
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
            return [str(k).strip() for k in keys if str(k).strip()]
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


# ----------------------------
# Google Drive
# ----------------------------
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


# ----------------------------
# Gemini (dynamic models)
# ----------------------------
@_cache_data(ttl=3600, show_spinner=False)
def list_generate_models_for_key(api_key):
    if not GENAI_AVAILABLE:
        return []

    genai.configure(api_key=api_key)

    # Fallback if list_models not available
    if not hasattr(genai, "list_models"):
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
    if not GENAI_AVAILABLE:
        st.error("google-generativeai غير متاحة: " + GENAI_IMPORT_ERROR)
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
                last_error = "لا توجد موديلات تدعم generateContent."
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

    st.error("فشل إنشاء جلسة المحادثة. آخر خطأ: " + str(last_error))
    return None


def send_message_with_retry(chat, message):
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = chat.send_message(message)
            text = getattr(resp, "text", None)
            if text:
                return text
            return "لم يصل رد نصّي من النموذج."
        except Exception as e:
            last_error = e
            msg = str(e)
            retryable = False
            for code in ["429", "500", "502", "503", "504", "timeout"]:
                if code in msg:
                    retryable = True
                    break
            if not retryable:
                break

            backoff = min(MAX_BACKOFF, BASE_RETRY_DELAY * (2 ** attempt))
            backoff = backoff + random.uniform(0, 0.6)
            time.sleep(backoff)

    return "حصل خطأ أثناء الإرسال: " + str(last_error)


# ----------------------------
# Optional TTS
# ----------------------------
async def _tts_to_bytes_async(text, voice):
    communicate = edge_tts.Communicate(text=text, voice=voice)
    audio_bytes = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_bytes += chunk["data"]
    return audio_bytes


def tts_to_bytes(text, voice=VOICE_NAME):
    if not TTS_AVAILABLE:
        return None
    try:
        return asyncio.run(_tts_to_bytes_async(text, voice))
    except Exception as e:
        logger.error("TTS error: %s", e)
        return None


# ----------------------------
# Chat UI compatibility
# ----------------------------
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


# ----------------------------
# Session state
# ----------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []
if "chat" not in st.session_state:
    st.session_state.chat = None
if "gemini_file" not in st.session_state:
    st.session_state.gemini_file = None
if "book_label" not in st.session_state:
    st.session_state.book_label = None


def reset_chat():
    st.session_state.messages = []
    st.session_state.chat = None
    st.session_state.gemini_file = None
    st.session_state.book_label = None


# ----------------------------
# UI
# ----------------------------
st.markdown(
    '<div class="header-box"><h1>المعلم الذكي</h1><div>اشرح من كتاب المنهج المرفق فقط</div><div class="small-muted">Version: {}</div></div>'.format(APP_VERSION),
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
    lang = st.radio("لغة الكتاب", ["Arabic", "English"], horizontal=True, key="lang")
    subject = st.selectbox("المادة", subjects_for(stage, grade), key="subject")

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        load_btn = st.button("تحميل الكتاب", type="primary", use_container_width=True)
    with c2:
        reset_btn = st.button("إعادة تعيين", use_container_width=True)

    st.divider()
    enable_tts = st.toggle("تشغيل الصوت (TTS)", value=False, disabled=not TTS_AVAILABLE)
    if not TTS_AVAILABLE:
        st.caption("لتفعيل الصوت: ثبّت edge-tts")
    if not MIC_AVAILABLE:
        st.caption("للميكروفون: ثبّت streamlit-mic-recorder")

if reset_btn:
    reset_chat()
    st.rerun()

if load_btn:
    if not DRIVE_AVAILABLE:
        st.error("لا يمكن التحميل: Drive غير متاح.")
    elif not GENAI_AVAILABLE:
        st.error("لا يمكن التحميل: Gemini غير متاح.")
    elif not GOOGLE_API_KEYS:
        st.error("أضف GOOGLE_API_KEYS داخل secrets.")
    else:
        search_name = generate_file_name_search(stage, grade, subject, lang)

        with status_box("جاري تجهيز الكتاب...") as status:
            if status:
                status.write("البحث عن: " + search_name)

            local_path, result_msg = find_and_download_book(search_name)
            if not local_path:
                if status:
                    status.update(label="فشل", state="error")
                st.error(result_msg)
            else:
                if status:
                    status.write("تم العثور على: " + str(result_msg))
                    status.write("رفع الكتاب إلى Gemini...")

                gemini_file = None
                for key in GOOGLE_API_KEYS:
                    gemini_file = upload_to_gemini(local_path, key)
                    if gemini_file:
                        break

                try:
                    os.unlink(local_path)
                except Exception:
                    pass

                if not gemini_file:
                    if status:
                        status.update(label="فشل الرفع", state="error")
                    st.error("فشل رفع الكتاب إلى Gemini.")
                else:
                    if status:
                        status.write("إنشاء جلسة المحادثة...")

                    chat = create_chat_session(gemini_file)
                    if not chat:
                        if status:
                            status.update(label="فشل", state="error")
                    else:
                        st.session_state.gemini_file = gemini_file
                        st.session_state.chat = chat
                        st.session_state.book_label = str(result_msg)
                        st.session_state.messages = []
                        if status:
                            status.update(label="تم", state="complete")
                        st.success("تم تحميل الكتاب وبدء الشرح.")

left, right = st.columns([1.15, 0.85])

with left:
    st.subheader("المحادثة")

    if st.session_state.book_label:
        st.markdown(
            "<div class='small-muted'>الكتاب الحالي: <b>{}</b></div>".format(st.session_state.book_label),
            unsafe_allow_html=True,
        )
    else:
        st.info("اختر الإعدادات من الشريط الجانبي ثم اضغط: تحميل الكتاب")

    for m in st.session_state.messages:
        with render_msg(m.get("role", "assistant")):
            st.markdown(m.get("content", ""))

    if MIC_AVAILABLE and st.session_state.chat:
        audio = mic_recorder(
            start_prompt="🎙️ سجّل سؤالك",
            stop_prompt="⏹️ إيقاف",
            just_once=True,
            use_container_width=True,
        )
        if audio and isinstance(audio, dict) and audio.get("bytes"):
            st.warning("تم تسجيل الصوت، لكن تحويل الكلام لنص (STT) غير مفعّل. اكتب سؤالك نصيًا.")

    prompt = get_user_input("اكتب سؤالك من الكتاب...")

    if prompt:
        if not st.session_state.chat:
            st.warning("لازم تحمل الكتاب الأول قبل ما تسأل.")
        else:
            st.session_state.messages.append({"role": "user", "content": prompt})
            with render_msg("user"):
                st.markdown(prompt)

            with render_msg("assistant"):
                with st.spinner("جارٍ التفكير..."):
                    answer = send_message_with_retry(st.session_state.chat, prompt)
                st.markdown(answer)

                if enable_tts and TTS_AVAILABLE:
                    audio_bytes = tts_to_bytes(answer, VOICE_NAME)
                    if audio_bytes:
                        st.audio(audio_bytes, format="audio/mpeg")

            st.session_state.messages.append({"role": "assistant", "content": answer})

with right:
    st.subheader("مساعدات سريعة")
    st.markdown(
        """
- اسأل أسئلة مباشرة من محتوى الدرس.
- اطلب: تلخيص، شرح خطوة بخطوة، أمثلة، أسئلة تدريب.
- لو سؤالك خارج الكتاب، النظام سيقول إن المعلومة غير موجودة.
"""
    )
    st.divider()
    st.subheader("حالة المكونات")
    st.write(
        {
            "GENAI_AVAILABLE": GENAI_AVAILABLE,
            "DRIVE_AVAILABLE": DRIVE_AVAILABLE,
            "MIC_AVAILABLE": MIC_AVAILABLE,
            "TTS_AVAILABLE": TTS_AVAILABLE,
            "HAS_CHAT_UI": HAS_CHAT_UI,
            "API_KEYS_COUNT": len(GOOGLE_API_KEYS),
            "BOOK_LOADED": bool(st.session_state.book_label),
        }
    )
