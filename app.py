import streamlit as st

st.set_page_config(
    page_title="المعلم الذكي",
    layout="wide",
    page_icon="🎓",
)

import os
import time
import re
import random
import tempfile
from typing import List, Optional, Tuple

try:
    import google.generativeai as genai
    GENAI_OK = True
except Exception:
    GENAI_OK = False

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    DRIVE_OK = True
except Exception:
    DRIVE_OK = False


FOLDER_ID = "1ub4ML8q4YCM_VZR991XXQ6hBBas2X6rS"

MAX_RETRIES = 4
BASE_DELAY = 1.5
MAX_DELAY = 12.0

ALLOWED_MODELS = [
    "models/gemini-2.0-flash",
    "models/gemini-1.5-flash",
    "models/gemini-1.5-pro",
]


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
SUBJECT_MAP = {
    "كيمياء": "Chem",
    "فيزياء": "Physics",
    "أحياء": "Biology",
}


def get_api_keys() -> List[str]:
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
    except Exception:
        return []


GOOGLE_API_KEYS = get_api_keys()


def subjects_for(stage: str, grade: str) -> List[str]:
    if stage in ["الابتدائية", "الإعدادية"]:
        return ["علوم"]
    if stage == "الثانوية":
        if grade == "الأول":
            return ["علوم متكاملة"]
        return ["كيمياء", "فيزياء", "أحياء"]
    return ["علوم"]


def generate_search_name(stage: str, grade: str, subject: str, lang: str) -> str:
    g = GRADE_MAP.get(grade, "1")
    code = "En" if lang == "English" else "Ar"

    if stage == "الابتدائية":
        return "Grade{}_{}".format(g, code)
    if stage == "الإعدادية":
        return "Prep{}_{}".format(g, code)
    if stage == "الثانوية":
        if grade == "الأول":
            return "Sec1_Integrated_{}".format(code)
        s = SUBJECT_MAP.get(subject, "Chem")
        return "Sec{}_{}_{}".format(g, s, code)

    return ""


def normalize_model_name(name: str) -> str:
    if not name:
        return name
    if name.startswith("models/"):
        return name.split("/", 1)[1]
    return name
   def _cache_resource(func):
    if hasattr(st, "cache_resource"):
        return st.cache_resource(show_spinner=False)(func)
    return st.cache(allow_output_mutation=True)(func)


def _cache_data(func):
    if hasattr(st, "cache_data"):
        return st.cache_data(ttl=3600, show_spinner=False)(func)
    return st.cache(ttl=3600)(func)


@_cache_resource
def get_drive_service():
    if not DRIVE_OK:
        return None

    if "gcp_service_account" not in st.secrets:
        return None

    info = dict(st.secrets["gcp_service_account"])
    if "private_key" in info and isinstance(info["private_key"], str):
        info["private_key"] = info["private_key"].replace("\\n", "\n")

    creds = service_account.Credentials.from_service_account_info(
        info,
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def find_best_pdf(search_name: str):
    service = get_drive_service()
    if service is None:
        return None

    q = (
        "'{}' in parents and "
        "name contains '{}' and "
        "mimeType='application/pdf' and trashed=false"
    ).format(FOLDER_ID, search_name)

    res = service.files().list(
        q=q,
        fields="files(id,name,size,modifiedTime)",
        pageSize=20,
    ).execute()

    files = res.get("files", [])
    if not files:
        return None

    def to_int(x):
        try:
            return int(x)
        except Exception:
            return 0

    files.sort(key=lambda f: to_int(f.get("size", 0)), reverse=True)
    return files[0]


def download_pdf(file_id: str) -> str:
    service = get_drive_service()
    request = service.files().get_media(fileId=file_id)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    path = tmp.name

    downloader = MediaIoBaseDownload(tmp, request)
    done = False
    try:
        while not done:
            _, done = downloader.next_chunk()
        tmp.close()

        if os.path.getsize(path) < 1500:
            os.unlink(path)
            raise RuntimeError("Downloaded file too small")

        return path
    except Exception:
        try:
            tmp.close()
        except Exception:
            pass
        if os.path.exists(path):
            os.unlink(path)
        raise


def find_and_download_book(search_name: str) -> Tuple[Optional[str], str]:
    f = find_best_pdf(search_name)
    if not f:
        return None, "لم يتم العثور على ملف: " + str(search_name)

    try:
        path = download_pdf(f["id"])
        return path, f["name"]
    except Exception as e:
        return None, str(e)


def upload_pdf_to_gemini(local_path: str, api_key: str):
    if not GENAI_OK:
        return None

    genai.configure(api_key=api_key)
    gf = genai.upload_file(local_path, mime_type="application/pdf")

    waited = 0
    while getattr(gf, "state", None) and gf.state.name == "PROCESSING" and waited < 90:
        time.sleep(2)
        waited += 2
        gf = genai.get_file(gf.name)

    if getattr(gf, "state", None) and gf.state.name == "FAILED":
        return None

    return gf


@_cache_data
def list_allowed_models_for_key(api_key: str) -> List[str]:
    if not GENAI_OK:
        return []

    genai.configure(api_key=api_key)

    if not hasattr(genai, "list_models"):
        return [m.split("/", 1)[1] for m in ALLOWED_MODELS]

    available = []
    for m in genai.list_models():
        name = getattr(m, "name", "") or ""
        methods = getattr(m, "supported_generation_methods", []) or []
        if "generateContent" in methods and name:
            available.append(name)

    out = []
    for want in ALLOWED_MODELS:
        if want in available:
            out.append(want)

    return out
def create_chat_session() -> Optional[object]:
    if not GENAI_OK:
        st.error("Gemini غير متاح (مكتبة غير مثبتة).")
        return None

    if not GOOGLE_API_KEYS:
        st.error("GOOGLE_API_KEYS غير موجودة في secrets.")
        return None

    system_text = "أنت معلم. اشرح من الكتاب فقط."

    last_err = None
    for key in GOOGLE_API_KEYS:
        try:
            genai.configure(api_key=key)
            models = list_allowed_models_for_key(key)
            if not models:
                last_err = "No allowed models"
                continue

            for m in models:
                try:
                    model = genai.GenerativeModel(
                        model_name=normalize_model_name(m),
                        system_instruction=system_text,
                    )
                    chat = model.start_chat(history=[])
                    st.session_state.active_key = key
                    st.session_state.active_model = m
                    return chat
                except Exception as e:
                    last_err = e
                    continue
        except Exception as e:
            last_err = e
            continue

    st.error("فشل إنشاء جلسة المحادثة: " + str(last_err))
    return None


def extract_retry_seconds(err) -> Optional[float]:
    if not err:
        return None
    s = str(err)
    m = re.search(r"retry in ([0-9.]+)s", s, flags=re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            return None
    m2 = re.search(r"seconds:\s*(\d+)", s, flags=re.IGNORECASE)
    if m2:
        try:
            return float(m2.group(1))
        except Exception:
            return None
    return None


def send_message_with_retry(chat, user_text: str) -> str:
    last_err = None

    for attempt in range(MAX_RETRIES):
        try:
            if (not st.session_state.book_bound) and (st.session_state.gemini_file is not None):
                payload = [st.session_state.gemini_file, user_text]
            else:
                payload = user_text

            resp = chat.send_message(payload)
            text = getattr(resp, "text", None) or ""

            if not st.session_state.book_bound:
                st.session_state.book_bound = True

            if text.strip():
                return text
            return "لم يصل رد."

        except Exception as e:
            last_err = e
            msg = str(e).lower()

            hard = ("billing" in msg) or ("limit: 0" in msg)
            if hard:
                return "الكوتا غير متاحة. فعّل Billing أو استخدم API Key آخر.\n" + str(e)

            retryable = ("429" in msg) or ("quota" in msg) or ("rate" in msg)
            if not retryable:
                break

            wait_s = extract_retry_seconds(e)
            if wait_s is None:
                backoff = min(MAX_DELAY, BASE_DELAY * (2 ** attempt))
                wait_s = backoff + random.uniform(0, 0.4)

            time.sleep(wait_s)

    return "خطأ أثناء الإرسال: " + str(last_err)


# ---------- Session state ----------
if "messages" not in st.session_state:
    st.session_state.messages = []
if "chat" not in st.session_state:
    st.session_state.chat = None
if "gemini_file" not in st.session_state:
    st.session_state.gemini_file = None
if "book_name" not in st.session_state:
    st.session_state.book_name = None
if "book_bound" not in st.session_state:
    st.session_state.book_bound = False
if "active_key" not in st.session_state:
    st.session_state.active_key = None
if "active_model" not in st.session_state:
    st.session_state.active_model = None


def reset_app():
    st.session_state.messages = []
    st.session_state.chat = None
    st.session_state.gemini_file = None
    st.session_state.book_name = None
    st.session_state.book_bound = False
    st.session_state.active_key = None
    st.session_state.active_model = None


# ---------- UI ----------
st.title("المعلم الذكي")

with st.sidebar:
    st.subheader("الإعدادات")

    if not DRIVE_OK:
        st.error("مكتبات Drive غير متاحة.")
    if not GENAI_OK:
        st.error("مكتبة Gemini غير متاحة.")
    if not GOOGLE_API_KEYS:
        st.warning("لا توجد GOOGLE_API_KEYS في secrets.")

    stage = st.selectbox("المرحلة", STAGES, key="stage")
    grade = st.selectbox("الصف", GRADES[stage], key="grade")
    term = st.selectbox("الترم", TERMS, key="term")
    lang = st.radio("لغة الكتاب", ["Arabic", "English"], horizontal=True, key="lang")
    subject = st.selectbox("المادة", subjects_for(stage, grade), key="subject")

    c1, c2 = st.columns(2)
    load_btn = c1.button("تحميل", type="primary", use_container_width=True)
    reset_btn = c2.button("ريست", use_container_width=True)

if reset_btn:
    reset_app()
    st.rerun()

if load_btn:
    if not DRIVE_OK:
        st.error("Drive غير متاح.")
    elif not GENAI_OK:
        st.error("Gemini غير متاح.")
    elif not GOOGLE_API_KEYS:
        st.error("أضف GOOGLE_API_KEYS.")
    else:
        search_name = generate_search_name(stage, grade, subject, lang)
        with st.spinner("جاري تحميل الكتاب..."):
            path, name_or_err = find_and_download_book(search_name)
            if not path:
                st.error(name_or_err)
            else:
                gf = None
                for key in GOOGLE_API_KEYS:
                    gf = upload_pdf_to_gemini(path, key)
                    if gf:
                        break

                try:
                    os.unlink(path)
                except Exception:
                    pass

                if not gf:
                    st.error("فشل رفع الكتاب إلى Gemini.")
                else:
                    st.session_state.gemini_file = gf
                    st.session_state.book_name = str(name_or_err)
                    st.session_state.book_bound = False
                    st.session_state.messages = []
                    st.session_state.chat = create_chat_session()
                    if st.session_state.chat:
                        st.success("تم تحميل الكتاب. اسأل الآن.")
                    else:
                        st.error("تم رفع الكتاب لكن فشل إنشاء الشات.")


if st.session_state.book_name:
    st.caption("الكتاب: " + str(st.session_state.book_name))

# عرض المحادثة
for m in st.session_state.messages:
    role = m.get("role", "assistant")
    content = m.get("content", "")
    if hasattr(st, "chat_message"):
        with st.chat_message(role):
            st.markdown(content)
    else:
        st.write(role + ": " + content)

# إدخال المستخدم
prompt = st.chat_input("اكتب سؤالك...") if hasattr(st, "chat_input") else st.text_input("اكتب سؤالك...")

if prompt:
    if not st.session_state.chat:
        st.warning("حمّل الكتاب أولاً.")
    else:
        st.session_state.messages.append({"role": "user", "content": prompt})
        answer = send_message_with_retry(st.session_state.chat, prompt)
        st.session_state.messages.append({"role": "assistant", "content": answer})
        st.rerun()
