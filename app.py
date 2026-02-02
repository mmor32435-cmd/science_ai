import streamlit as st
st.set_page_config(page_title="المعلم الذكي", layout="wide", page_icon="🎓")

import os, time, tempfile, random, re

# ===== Imports =====
try:
    import google.generativeai as genai
    GENAI_OK = True
    GENAI_ERR = ""
except Exception as e:
    GENAI_OK = False
    GENAI_ERR = str(e)

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    DRIVE_OK = True
    DRIVE_ERR = ""
except Exception as e:
    DRIVE_OK = False
    DRIVE_ERR = str(e)

# ===== Constants =====
FOLDER_ID = "1ub4ML8q4YCM_VZR991XXQ6hBBas2X6rS"

MAX_RETRIES = 4
BASE_DELAY = 1.5
MAX_DELAY = 12.0

ALLOWED_MODELS = [
    "models/gemini-2.0-flash",
    "models/gemini-2.0-flash-lite",
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

GRADE_MAP = {"الرابع": "4", "الخامس": "5", "السادس": "6", "الأول": "1", "الثاني": "2", "الثالث": "3"}
SUBJECT_MAP = {"كيمياء": "Chem", "فيزياء": "Physics", "أحياء": "Biology"}

HAS_CHAT_UI = hasattr(st, "chat_message") and hasattr(st, "chat_input")

# ===== Helpers =====
def get_api_keys():
    try:
        keys = st.secrets.get("GOOGLE_API_KEYS", [])
        if isinstance(keys, str):
            return [k.strip() for k in keys.split(",") if k.strip()]
        if isinstance(keys, (list, tuple)):
            return [str(k).strip() for k in keys if str(k).strip()]
        return []
    except Exception:
        return []

def subjects_for(stage, grade):
    if stage in ["الابتدائية", "الإعدادية"]:
        return ["علوم"]
    if stage == "الثانوية":
        if grade == "الأول":
            return ["علوم متكاملة"]
        return ["كيمياء", "فيزياء", "أحياء"]
    return ["علوم"]

def generate_search_name(stage, grade, subject, lang):
    g = GRADE_MAP.get(grade, "1")
    code = "En" if lang == "English" else "Ar"
    if stage == "الابتدائية":
        return f"Grade{g}_{code}"
    if stage == "الإعدادية":
        return f"Prep{g}_{code}"
    if stage == "الثانوية":
        if grade == "الأول":
            return f"Sec1_Integrated_{code}"
        s = SUBJECT_MAP.get(subject, "Chem")
        return f"Sec{g}_{s}_{code}"
    return ""

def normalize_model_name(name):
    if not name:
        return name
    return name.split("/", 1)[1] if name.startswith("models/") else name

def is_quota_hard_fail(err):
    if err is None:
        return False
    s = str(err).lower()
    return ("check your plan and billing" in s) or ("limit: 0" in s) or ("requests per day" in s)

def extract_retry_seconds(err):
    if not err:
        return None
    s = str(err)
    m = re.search(r"retry in ([0-9.]+)s", s, flags=re.IGNORECASE)
    if m:
        try: return float(m.group(1))
        except: return None
    m2 = re.search(r"retry_delay\s*\{\s*seconds:\s*(\d+)\s*\}", s, flags=re.IGNORECASE)
    if m2:
        try: return float(m2.group(1))
        except: return None
    return None

# ===== Google Drive (Cached) =====
@st.cache_resource
def get_drive_service_cached(service_account_info: dict):
    info = dict(service_account_info)
    if "private_key" in info and isinstance(info["private_key"], str):
        info["private_key"] = info["private_key"].replace("\\n", "\n")
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)

def get_drive_service():
    if not DRIVE_OK:
        return None
    if "gcp_service_account" not in st.secrets:
        return None
    return get_drive_service_cached(dict(st.secrets["gcp_service_account"]))

@st.cache_data(ttl=300)
def find_best_pdf_cached(folder_id: str, search_name: str):
    service = get_drive_service()
    if service is None:
        return None

    q = (
        f"'{folder_id}' in parents and "
        f"name contains '{search_name}' and "
        "mimeType='application/pdf' and trashed=false"
    )
    res = service.files().list(
        q=q,
        fields="files(id,name,size,modifiedTime)",
        pageSize=20,
    ).execute()

    files = res.get("files", [])
    if not files:
        return None

    def to_int(x):
        try: return int(x)
        except: return 0

    files.sort(key=lambda f: to_int(f.get("size", 0)), reverse=True)
    return files[0]  # {id,name,size,...}

def download_pdf_by_id(service, file_id):
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
        try: tmp.close()
        except: pass
        if os.path.exists(path):
            os.unlink(path)
        raise

def find_and_download_book(search_name):
    service = get_drive_service()
    if service is None:
        return None, None, "فشل الاتصال بـ Google Drive"

    try:
        f = find_best_pdf_cached(FOLDER_ID, search_name)
        if not f:
            return None, None, f"لم يتم العثور على ملف: {search_name}"
        path = download_pdf_by_id(service, f["id"])
        return path, f["id"], f["name"]
    except Exception as e:
        return None, None, str(e)

# ===== Gemini (Unified key for upload + chat) =====
def list_allowed_models_for_key(api_key):
    genai.configure(api_key=api_key)
    if not hasattr(genai, "list_models"):
        return [m for m in ALLOWED_MODELS]
    available = []
    for m in genai.list_models():
        name = getattr(m, "name", "") or ""
        methods = getattr(m, "supported_generation_methods", []) or []
        if name and ("generateContent" in methods):
            available.append(name)
    return [m for m in ALLOWED_MODELS if m in available]

def pick_working_key_and_model():
    """اختيار مفتاح+موديل بنفسه. لا يرفع كتاب ولا ينشئ Chat هنا."""
    keys = get_api_keys()
    if not keys:
        return None, None, "GOOGLE_API_KEYS غير موجودة في secrets"

    system_text = "أنت معلم مصري. أجب بإيجاز ووضوح."
    last_err = None

    for key in keys:
        try:
            models = list_allowed_models_for_key(key)
            for m in models:
                try:
                    genai.configure(api_key=key)
                    model = genai.GenerativeModel(
                        model_name=normalize_model_name(m),
                        system_instruction=system_text,
                    )
                    # اختبار خفيف للتأكد أن الكوتا ليست limit:0 (يستهلك طلب واحد)
                    _ = model.generate_content("قل: جاهز.", generation_config={"max_output_tokens": 5})
                    return key, m, ""
                except Exception as e:
                    last_err = e
                    if is_quota_hard_fail(e):
                        # هذا المفتاح غير صالح للاستخدام الحالي
                        continue
                    continue
        except Exception as e:
            last_err = e
            continue

    return None, None, f"لا يوجد مفتاح صالح حاليًا. آخر خطأ: {last_err}"

def upload_pdf_to_gemini(local_path, api_key):
    genai.configure(api_key=api_key)
    gf = genai.upload_file(local_path, mime_type="application/pdf")

    waited = 0
    while getattr(gf, "state", None) and gf.state.name == "PROCESSING" and waited < 90:
        time.sleep(2)
        waited += 2
        gf = genai.get_file(gf.name)

    if getattr(gf, "state", None) and gf.state.name == "FAILED":
        raise RuntimeError("Gemini file processing FAILED")

    return gf  # has .name

def create_chat_session(api_key, model_full_name, system_text):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name=normalize_model_name(model_full_name),
        system_instruction=system_text,
    )
    return model.start_chat(history=[])

def send_message_with_retry(message: str):
    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            chat = st.session_state.chat
            if chat is None:
                return "لا توجد جلسة محادثة. حمّل الكتاب أولاً."

            # اربط الكتاب في أول رسالة فقط
            if (not st.session_state.book_bound) and st.session_state.gemini_file_name:
                genai.configure(api_key=st.session_state.active_key)
                gf = genai.get_file(st.session_state.gemini_file_name)
                payload = [gf, message]
            else:
                payload = message

            resp = chat.send_message(payload)
            text = getattr(resp, "text", "") or ""
            if not st.session_state.book_bound:
                st.session_state.book_bound = True

            return text.strip() or "لم يصل رد."
        except Exception as e:
            last_err = e
            if is_quota_hard_fail(e):
                return "الكوتا غير متاحة لهذا المفتاح/المشروع. فعّل Billing أو استخدم API Key آخر.\n" + str(e)

            msg = str(e).lower()
            retryable = ("429" in msg) or ("quota" in msg) or ("rate" in msg) or ("timeout" in msg) or ("503" in msg)
            if not retryable:
                break

            wait_s = extract_retry_seconds(e)
            if wait_s is None:
                wait_s = min(MAX_DELAY, BASE_DELAY * (2 ** attempt)) + random.uniform(0, 0.4)
            time.sleep(wait_s)

    return "خطأ أثناء الإرسال: " + str(last_err)

# ===== Session State =====
def init_state():
    defaults = dict(
        messages=[],
        chat=None,
        gemini_file_name=None,
        book_name=None,
        book_drive_file_id=None,
        book_bound=False,
        active_key=None,
        active_model=None,
    )
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def reset_app():
    for k in list(st.session_state.keys()):
        if k in ["messages","chat","gemini_file_name","book_name","book_drive_file_id","book_bound","active_key","active_model"]:
            del st.session_state[k]
    init_state()

init_state()

# ===== UI =====
st.title("المعلم الذكي")

with st.sidebar:
    st.subheader("الإعدادات")

    if not DRIVE_OK:
        st.error("Drive غير متاح: " + DRIVE_ERR)
    if not GENAI_OK:
        st.error("Gemini غير متاح: " + GENAI_ERR)

    stage = st.selectbox("المرحلة", STAGES)
    grade = st.selectbox("الصف", GRADES[stage])
    _term = st.selectbox("الترم", TERMS)
    lang = st.radio("لغة الكتاب", ["Arabic", "English"], horizontal=True)
    subject = st.selectbox("المادة", subjects_for(stage, grade))

    c1, c2 = st.columns(2)
    load_btn = c1.button("تحميل الكتاب", type="primary", use_container_width=True)
    reset_btn = c2.button("إعادة تعيين", use_container_width=True)

if reset_btn:
    reset_app()
    st.rerun()

if load_btn:
    if not DRIVE_OK:
        st.error("Drive غير متاح.")
    elif not GENAI_OK:
        st.error("Gemini غير متاح.")
    elif not get_api_keys():
        st.error("أضف GOOGLE_API_KEYS في secrets.")
    else:
        search_name = generate_search_name(stage, grade, subject, lang)
        system_text = "أنت معلم مصري. اشرح من الكتاب المرفق فقط، واذكر رقم الصفحة إن أمكن."

        with st.spinner("اختيار مفتاح Gemini صالح..."):
            key, model, err = pick_working_key_and_model()
        if not key:
            st.error(err)
        else:
            with st.spinner("جاري تحميل الكتاب من Drive..."):
                path, drive_file_id, name_or_err = find_and_download_book(search_name)
            if not path:
                st.error(name_or_err)
            else:
                try:
                    with st.spinner("جاري رفع الكتاب إلى Gemini..."):
                        gf = upload_pdf_to_gemini(path, key)

                    st.session_state.active_key = key
                    st.session_state.active_model = model
                    st.session_state.gemini_file_name = gf.name
                    st.session_state.book_drive_file_id = drive_file_id
                    st.session_state.book_name = str(name_or_err)
                    st.session_state.book_bound = False
                    st.session_state.messages = []

                    with st.spinner("إنشاء جلسة الشات..."):
                        st.session_state.chat = create_chat_session(key, model, system_text)

                    st.success("تم تحميل الكتاب. اكتب سؤالك الآن.")
                except Exception as e:
                    st.error("فشل تجهيز Gemini: " + str(e))
                finally:
                    try: os.unlink(path)
                    except: pass

if st.session_state.book_name:
    st.caption("الكتاب الحالي: " + str(st.session_state.book_name))

# عرض المحادثة
for m in st.session_state.messages:
    role = m.get("role", "assistant")
    content = m.get("content", "")
    if HAS_CHAT_UI:
        with st.chat_message(role):
            st.markdown(content)
    else:
        st.write(role + ": " + content)

prompt = st.chat_input("اكتب سؤالك...") if HAS_CHAT_UI else st.text_input("اكتب سؤالك...")

if prompt:
    if not st.session_state.chat:
        st.warning("حمّل الكتاب أولاً.")
    else:
        st.session_state.messages.append({"role": "user", "content": prompt})
        answer = send_message_with_retry(prompt)
        st.session_state.messages.append({"role": "assistant", "content": answer})
        st.rerun()

st.sidebar.write({"MODEL": st.session_state.active_model, "BOOK_BOUND": st.session_state.book_bound})
