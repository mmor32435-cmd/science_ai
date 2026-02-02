import streamlit as st

# ✅ لازم يكون أول أمر Streamlit
st.set_page_config(page_title="المعلم الذكي", layout="wide", page_icon="🎓")

import os
import time
import tempfile
import logging
import random
from contextlib import contextmanager
from typing import Optional, List

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
    """list_models يرجّع models/xxx. نطبّعها للأمان."""
    if not name:
        return name
    return name.split("/", 1)[1] if name.startswith("models/") else name
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
        @st.cache_data(ttl=3600, show_spinner=False)
def list_generate_models_for_key(api_key: str) -> List[str]:
    """
    يرجّع أسماء موديلات متاحة لهذا المفتاح وتدعم generateContent.
    يحل مشكلة 404 مثل gemini-pro غير المتاح.
    """
    if not GENAI_AVAILABLE:
        return []

    genai.configure(api_key=api_key)

    # لو list_models غير متاحة في إصدار قديم
    if not hasattr(genai, "list_models"):
        return ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]

    models = []
    for m in genai.list_models():
        name = getattr(m, "name", "")
        methods = getattr(m, "supported_generation_methods", []) or []
        if "generateContent" in methods and name:
            models.append(name)

    preferred = [
        "models/gemini-2.0-flash",
        "models/gemini-2.0-flash-lite",
        "models/gemini-1.5-flash",
        "models/gemini-1.5-pro",
    ]

    models_sorted = []
    for p in preferred:
        if p in models:
            models_sorted.append(p)
    for x in models:
        if x not in models_sorted:
            models_sorted.append(x)

    return models_sorted


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

    st.error(f"فشل إنشاء جلسة المحادثة. آخر خطأ: {last_error}")
    return None


def send_message_with_retry(chat, message: str) -> str:
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = chat.send_message(message)
            text = getattr(resp, "text", None)
            return text if text else "لم يصل رد نصّي من النموذج."
        except Exception as e:
            last_error = e
            msg = str(e)
            retryable = any(code in msg for code in ["429", "500", "502", "503", "504", "timeout"])
            if not retryable:
                break

            backoff = min(MAX_BACKOFF, BASE_RETRY_DELAY * (2 ** attempt))
            backoff += random.uniform(0, 0.6)
            time.sleep(backoff)

    return f"حصل خطأ أثناء الإرسال: {last_error}"


# ---- Optional TTS ----
async def _tts_to_bytes_async(text: str, voice: str):
    communicate = edge_tts.Communicate(text=text, voice=voice)
    audio_bytes = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_bytes += chunk["data"]
    return audio_bytes


def tts_to_bytes(text: str, voice: str = VOICE_NAME) -> Optional[bytes]:
    if not TTS_AVAILABLE:
        return None
    try:
        return asyncio.run(_tts_to_bytes_async(text, voice))
    except Exception as e:
        logger.error(f"TTS error: {e}")
        return None
        # =========================
# Session State
# =========================
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


# =========================
# UI
# =========================
st.markdown(
    '<div class="header-box"><h1>المعلم الذكي 🎓</h1><div>اشرح من كتاب المنهج المرفق فقط</div></div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.subheader("الإعدادات")

    if not DRIVE_AVAILABLE:
        st.error(f"مكتبات Google Drive غير متاحة: {DRIVE_IMPORT_ERROR}")
    if not GENAI_AVAILABLE:
        st.error(f"مكتبة google-generativeai غير متاحة: {GENAI_IMPORT_ERROR}")
    if not GOOGLE_API_KEYS:
        st.warning("GOOGLE_API_KEYS غير موجودة في secrets.")

    stage = st.selectbox("المرحلة", STAGES, key="stage")
    grade = st.selectbox("الصف", GRADES[stage], key="grade")
    _term = st.selectbox("الترم", TERMS, key="term")
    lang = st.radio("لغة الكتاب", ["Arabic", "English"], horizontal=True, key="lang")
    subject = st.selectbox("المادة", subjects_for(stage, grade), key="subject")

    st.divider()
    colA, colB = st.columns(2)
    with colA:
        load_btn = st.button("تحميل الكتاب", type="primary", use_container_width=True)
    with colB:
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

# ---- Load book ----
if load_btn:
    if not DRIVE_AVAILABLE:
        st.error("لا يمكن التحميل: مكتبات Google Drive غير متاحة.")
    elif not GENAI_AVAILABLE:
        st.error("لا يمكن التحميل: مكتبة google-generativeai غير متاحة.")
    elif not GOOGLE_API_KEYS:
        st.error("أضف GOOGLE_API_KEYS داخل secrets.")
    else:
        search_name = generate_file_name_search(stage, grade, subject, lang)

        with status_box("جاري تجهيز الكتاب...") as status:
            if status:
                status.write(f"🔎 البحث عن: {search_name}")

            local_path, file_name_or_err = find_and_download_book(search_name)
            if not local_path:
                if status:
                    status.update(label="فشل", state="error")
                st.error(file_name_or_err)
            else:
                if status:
                    status.write(f"✅ تم العثور على: {file_name_or_err}")
                    status.write("☁️ رفع الكتاب إلى Gemini...")

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
                    st.error("فشل رفع الكتاب إلى Gemini. جرّب مفتاح API آخر أو تأكد من الملف.")
                else:
                    if status:
                        status.write("🧠 إنشاء جلسة المحادثة...")

                    chat = create_chat_session(gemini_file)
                    if not chat:
                        if status:
                            status.update(label="فشل", state="error")
                        st.error("فشل إنشاء الشات (تحقق من الموديلات المتاحة لمفتاحك).")
                    else:
                        st.session_state.gemini_file = gemini_file
                        st.session_state.chat = chat
                        st.session_state.book_label = file_name_or_err
                        st.session_state.messages = []
                        if status:
                            status.update(label="تم!", state="complete")
                        st.success(f"تم تحميل الكتاب وبدء جلسة الشرح: {file_name_or_err}")

# ---- Main layout ----
left, right = st.columns([1.15, 0.85])

with left:
    st.subheader("المحادثة")

    if st.session_state.book_label:
        st.markdown(
            f"<div class='small-muted'>الكتاب الحالي: <b>{st.session_state.book_label}</b></div>",
            unsafe_allow_html=True,
        )
    else:
        st.info("اختر الإعدادات من الشريط الجانبي ثم اضغط: تحميل الكتاب")

    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    if MIC_AVAILABLE and st.session_state.chat:
        audio = mic_recorder(
            start_prompt="🎙️ سجّل سؤالك",
            stop_prompt="⏹️ إيقاف",
            just_once=True,
            use_container_width=True,
        )
        if audio and isinstance(audio, dict) and audio.get("bytes"):
            st.warning("تم تسجيل الصوت، لكن تحويل الكلام لنص (STT) غير مفعّل. اكتب سؤالك نصيًا.")

    prompt = st.chat_input("اكتب سؤالك من الكتاب...") if hasattr(st, "chat_input") else st.text_input("اكتب سؤالك من الكتاب...")

    if prompt:
        if not st.session_state.chat:
            st.warning("لازم تحمل الكتاب الأول قبل ما تسأل.")
        else:
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
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
- اطلب: **تلخيص**، **شرح خطوة بخطوة**، **أمثلة**، **أسئلة تدريب**.
- لو سؤالك خارج الكتاب، النظام هيقولك إنه غير موجود.
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
            "API_KEYS_COUNT": len(GOOGLE_API_KEYS),
            "BOOK_LOADED": bool(st.session_state.book_label),
        }
    )
