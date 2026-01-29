import streamlit as st
import os
import re
import io
import json
import time
import random
import asyncio
import tempfile
import traceback
import requests  # للتنزيل والـ scraping
from bs4 import BeautifulSoup  # للـ scraping

from PIL import Image
import pdfplumber
import gspread
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder
import edge_tts

import google.generativeai as genai

# OCR deps
from pdf2image import convert_from_path
import pytesseract
# =========================
# 1) إعدادات الصفحة
# =========================
st.set_page_config(
    page_title="المعلم العلمي | السيد البدوي",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =========================
# 2) CSS آمن
# =========================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');

html, body, .stApp {
  font-family: 'Cairo', sans-serif !important;
  direction: rtl;
  text-align: right;
}
.stApp { background-color: #f8f9fa; }

.stTextInput input, .stTextArea textarea {
  background-color: #ffffff !important;
  color: #000000 !important;
  border: 2px solid #004e92 !important;
  border-radius: 8px !important;
}

div[data-baseweb="select"] > div {
  background-color: #ffffff !important;
  border: 2px solid #004e92 !important;
  border-radius: 8px !important;
}
ul[data-baseweb="menu"] { background-color: #ffffff !important; }
li[data-baseweb="option"] { color: #000000 !important; }
li[data-baseweb="option"]:hover { background-color: #e3f2fd !important; }

h1, h2, h3, h4, h5, p, label, span { color: #000000 !important; }

.stButton>button {
  background: linear-gradient(90deg, #004e92 0%, #000428 100%) !important;
  color: #ffffff !important;
  border: none;
  border-radius: 10px;
  height: 55px;
  width: 100%;
  font-size: 20px !important;
  font-weight: bold !important;
}

.header-box {
  background: linear-gradient(90deg, #000428 0%, #004e92 100%);
  padding: 2rem;
  border-radius: 15px;
  text-align: center;
  margin-bottom: 2rem;
  box-shadow: 0 4px 15px rgba(0,0,0,0.2);
}
.header-box h1, .header-box h3 { color: #ffffff !important; }

.stChatMessage {
  background-color: #ffffff !important;
  border: 1px solid #d1d1d1 !important;
  border-radius: 12px !important;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="header-box">
  <h1>الأستاذ / السيد البدوي</h1>
  <h3>المنصة التعليمية الذكية</h3>
</div>
""", unsafe_allow_html=True)
# =========================
# 3) Session state + Debug
# =========================
if "user_data" not in st.session_state:
    st.session_state.user_data = {
        "logged_in": False,
        "role": None,
        "name": "",
        "grade": "",
        "stage": "",
        "lang": "العربية (علوم)"
    }

if "messages" not in st.session_state:
    st.session_state.messages = []

if "book_data" not in st.session_state:
    st.session_state.book_data = {"path": None, "text": None, "name": None}

if "quiz_state" not in st.session_state:
    st.session_state.quiz_state = "off"  # off | asking | waiting_answer | correcting

if "quiz_last_question" not in st.session_state:
    st.session_state.quiz_last_question = ""

if "gemini_model_name" not in st.session_state:
    st.session_state.gemini_model_name = None

if "debug_enabled" not in st.session_state:
    st.session_state.debug_enabled = True

if "debug_log" not in st.session_state:
    st.session_state.debug_log = []

def dbg(event, data=None):
    if not st.session_state.debug_enabled:
        return
    rec = {"t": time.strftime("%H:%M:%S"), "event": event}
    if data is not None:
        rec["data"] = data
    st.session_state.debug_log.append(rec)
    st.session_state.debug_log = st.session_state.debug_log[-400:]
  # =========================
# 4) Secrets
# =========================
TEACHER_KEY = st.secrets.get("TEACHER_MASTER_KEY", "ADMIN")
SHEET_NAME = st.secrets.get("CONTROL_SHEET_NAME", "App_Control")

# =========================
# 5) Google creds + Sheets (فقط للكود السري)
# =========================
@st.cache_resource
def get_credentials():
    if "gcp_service_account" not in st.session_state:
        return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        return service_account.Credentials.from_service_account_info(creds_dict, scopes=scopes)
    except Exception as e:
        dbg("creds_error", str(e))
        return None

def get_gspread_client():
    creds = get_credentials()
    return gspread.authorize(creds) if creds else None

def check_student_code(input_code):
    client = get_gspread_client()
    if not client:
        return False
    try:
        sh = client.open(SHEET_NAME)
        real_code = str(sh.sheet1.acell("B1").value).strip()
        return str(input_code).strip() == real_code
    except Exception as e:
        dbg("check_student_code_error", str(e))
        return False
# =========================
# 6) تحميل الكتاب من الموقع الرسمي + استخراج نص
# =========================
def load_book_smartly(stage, grade, lang):
    try:
        base_url = "https://ellibrary.moe.gov.eg/books/"
        headers = {"User-Agent": "Mozilla/5.0"}  # لتجنب الحظر

        # خريطة للاختيارات (غيرها إذا تغير هيكل الموقع)
        stages = {
            "الابتدائية": "primary",
            "الإعدادية": "preparatory",
            "الثانوية": "secondary"
        }
        grades = {
            "الرابع": "4",
            "الخامس": "5",
            "السادس": "6",
            "الأول": "1",
            "الثاني": "2",
            "الثالث": "3"
        }
        terms = "الفصل الدراسي الثاني"  # افتراضي للفصل الثاني
        subjects = {
            "علوم": "science",
            "علوم متكاملة": "integrated_science",
            "كيمياء": "chemistry",
            "فيزياء": "physics",
            "أحياء": "biology"
        }
        book_type = "كتاب الطالب"  # نوع الكتاب

        # بناء الاستعلام أو التنقل (هذا افتراضي؛ قد يحتاج تعديل بناءً على HTML الموقع)
        # هنا، نفترض أن الموقع يستخدم GET parameters أو forms؛ سنستخدم scraping لاستخراج الرابط
        response = requests.get(base_url, headers=headers)
        if response.status_code != 200:
            dbg("site_access_error", {"status": response.status_code})
            return None

        soup = BeautifulSoup(response.text, "lxml")

        # مثال على استخراج رابط (غير selectors بناءً على HTML الموقع)
        # افتراض: ابحث عن روابط تحتوي على stage/grade/term/subject
        book_link = None
        for a in soup.find_all("a", href=True):
            if all(term in a['href'] or term in a.text for term in [stages.get(stage, ""), grades.get(grade, ""), terms, subjects.get("علوم", "")]):  # تخصيص
                book_link = a['href']
                break

        if not book_link:
            dbg("book_link_not_found", {"stage": stage, "grade": grade})
            return None

        # إذا كان الرابط نسبي، أضف base
        if not book_link.startswith("http"):
            book_link = base_url + book_link

        # تنزيل الـ PDF
        pdf_response = requests.get(book_link, headers=headers)
        if pdf_response.status_code != 200:
            dbg("pdf_download_error", {"url": book_link, "status": pdf_response.status_code})
            return None

        book_name = f"{stage}_{grade}_{lang}.pdf"
        file_path = os.path.join(tempfile.gettempdir(), book_name)
        with open(file_path, "wb") as fh:
            fh.write(pdf_response.content)

        dbg("book_downloaded", {"name": book_name, "path": file_path, "size": os.path.getsize(file_path)})

        # استخراج النص
        text_content = ""
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text_content += extracted + "\n"
        except Exception as e:
            dbg("pdf_extract_error", str(e))

        dbg("book_text_stats", {"chars": len(text_content)})
        return {"path": file_path, "text": text_content, "name": book_name}

    except Exception as e:
        dbg("load_book_error", {"err": str(e), "trace": traceback.format_exc()})
        return None
        # =========================
# 7) OCR (لجميع الصفحات مع caching)
# =========================
@st.cache_data(show_spinner=False)
def ocr_pdf_to_text(pdf_path: str, lang: str = "ara"):
    try:
        pages = convert_from_path(pdf_path, dpi=200)
        out = []
        for idx, im in enumerate(pages, start=1):
            txt = pytesseract.image_to_string(im, lang=lang)
            out.append(f"\n--- PAGE {idx} ---\n{txt}")
        return "\n".join(out)
    except Exception as e:
        return f"__OCR_ERROR__:{type(e).__name__}:{e}"

def ensure_book_loaded_and_text_ready():
    u = st.session_state.user_data

    if not st.session_state.book_data.get("name"):
        data = load_book_smartly(u["stage"], u["grade"], u["lang"])
        if not data:
            return False
        st.session_state.book_data = data

    # لو النص صفر → OCR
    if not (st.session_state.book_data.get("text") or "").strip():
        pdf_path = st.session_state.book_data.get("path")
        if pdf_path and os.path.exists(pdf_path):
            with st.spinner("الكتاب scanned.. جاري OCR..."):
                ocr_lang = "eng" if "English" in u["lang"] else "ara"
                ocr_text = ocr_pdf_to_text(pdf_path, lang=ocr_lang)
                if "__OCR_ERROR__" not in ocr_text:
                    st.session_state.book_data["text"] = ocr_text

    return True
    # =========================
# 8) Gemini
# =========================
def list_models_supporting_generate():
    try:
        ms = genai.list_models()
        valid = []
        for m in ms:
            methods = getattr(m, "supported_generation_methods", []) or []
            if "generateContent" in methods:
                valid.append(m.name)
        return valid
    except Exception as e:
        dbg("list_models_error", {"err": str(e), "trace": traceback.format_exc()})
        return []

def pick_model():
    if st.session_state.gemini_model_name:
        return st.session_state.gemini_model_name

    models = list_models_supporting_generate()
    dbg("models_available", {"count": len(models), "models": models[:50]})

    preferred = []
    for m in models:
        if "latest" in m.lower():
            preferred.append(m)
    for m in models:
        if "flash" in m.lower() and m not in preferred:
            preferred.append(m)
    for m in models:
        if "pro" in m.lower() and m not in preferred:
            preferred.append(m)
    for m in models:
        if m not in preferred:
            preferred.append(m)

    chosen = preferred[0] if preferred else None
    st.session_state.gemini_model_name = chosen
    dbg("model_chosen", {"model": chosen})
    return chosen

def build_system_prompt(is_english: bool):
    if is_english:
        return "You are a science teacher. Answer ONLY from the provided textbook text. Be concise."
    return "أنت معلم علوم. أجب فقط من نص الكتاب المقدم لك. كن مختصراً."

def get_ai_response(user_text: str) -> str:
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys:
        return "⚠️ المفاتيح مفقودة."

    chosen_key = random.choice(keys)
    genai.configure(api_key=chosen_key)
    dbg("gemini_key_chosen", {"last4": chosen_key[-4:] if isinstance(chosen_key, str) else "?"})

    if not ensure_book_loaded_and_text_ready():
        return "⚠️ لم يتم العثور على الكتاب."

    model_name = pick_model()
    if not model_name:
        return "⚠️ لا توجد موديلات متاحة."

    u = st.session_state.user_data
    is_english = "English" in u["lang"]
    sys_prompt = build_system_prompt(is_english)

    quiz_state = st.session_state.quiz_state
    if quiz_state == "asking":
        user_text = "Create ONE short quiz question from the textbook text. Return only the question." if is_english else "كوّن سؤال اختبار واحد قصير من نص الكتاب. اكتب السؤال فقط."
    elif quiz_state == "correcting":
        q = st.session_state.quiz_last_question.strip()
        a = user_text.strip()
        user_text = (
            f"Grade the student's answer based on the textbook text.\nQuestion: {q}\nStudent answer: {a}\nScore /10 + short feedback."
            if is_english else
            f"صحح إجابة الطالب بالرجوع لنص الكتاب.\nالسؤال: {q}\nإجابة الطالب: {a}\nدرجة /10 + تعليق مختصر."
        )

    book_text = (st.session_state.book_data.get("text") or "")
    context = book_text[:100000]  # حد كبير لتغطية الكتب

    prompt = f"{sys_prompt}\n\nنص الكتاب (مقتطع):\n{context}\n\nسؤال/طلب المستخدم:\n{user_text}"
    dbg("prompt_stats", {"model": model_name, "prompt_len": len(prompt), "ctx_len": len(context)})

    try:
        model = genai.GenerativeModel(model_name)
        resp = (model.generate_content(prompt).text or "").strip()
        dbg("generate_ok", {"resp_len": len(resp)})

        if quiz_state == "asking":
            st.session_state.quiz_last_question = resp
            st.session_state.quiz_state = "waiting_answer"
        elif quiz_state == "correcting":
            st.session_state.quiz_last_question = ""
            st.session_state.quiz_state = "off"

        return resp if resp else "⚠️ لم يصل نص في الاستجابة."
    except Exception as e:
        dbg("generate_error", {"err": str(e), "trace": traceback.format_exc(), "model": model_name})
        return f"خطأ تقني: {e}"
       # =========================
# 9) صوت (STT/TTS)
# =========================
def clean_text_for_speech(text):
    return re.sub(r'[\*\#\-\_]', '', text)

def speech_to_text(audio_bytes, lang_ui):
    r = sr.Recognizer()
    try:
        audio_io = io.BytesIO(audio_bytes)
        with sr.AudioFile(audio_io) as source:
            audio_data = r.record(source)
            code = "en-US" if "English" in lang_ui else "ar-EG"
            return r.recognize_google(audio_data, language=code)
    except Exception as e:
        dbg("stt_error", str(e))
        return None

async def generate_speech_async(text, lang_ui):
    cleaned = clean_text_for_speech(text)
    voice = "en-US-ChristopherNeural" if "English" in lang_ui else "ar-EG-ShakirNeural"
    communicate = edge_tts.Communicate(cleaned, voice)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
        await communicate.save(tmp_file.name)
        return tmp_file.name

def text_to_speech_pro(text, 
                      # =========================
# 10) UI
# =========================
def celebrate_success():
    st.balloons()
    st.toast("أحسنت!", icon="🎉")

def login_page():
    st.markdown("### 🔐 تسجيل الدخول")
    with st.form("login"):
        name = st.text_input("الاسم الثلاثي")
        code = st.text_input("الكود السري", type="password")
        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            stage = st.selectbox("المرحلة", ["الابتدائية", "الإعدادية", "الثانوية"])
            lang = st.selectbox("اللغة", ["العربية (علوم)", "English (Science)"])
        with col2:
            grade = st.selectbox("الصف الدراسي", ["الرابع", "الخامس", "السادس", "الأول", "الثاني", "الثالث"])
            if "الثانوية" in stage and grade in ["الثاني", "الثالث"]:
                subject = st.selectbox("المادة", ["كيمياء", "فيزياء", "أحياء"])  # إضافة للثانوية

        submit = st.form_submit_button("🚀 بدء التعلم")
        if submit:
            if code == TEACHER_KEY:
                st.session_state.user_data.update({"logged_in": True, "role": "Teacher", "name": name})
                st.rerun()
            elif check_student_code(code):
                st.session_state.user_data.update({
                    "logged_in": True,
                    "role": "Student",
                    "name": name,
                    "stage": stage,
                    "grade": grade,
                    "lang": lang,
                    "subject": subject if "subject" in locals() else "علوم"  # حفظ المادة
                })
                st.session_state.book_data = {"path": None, "text": None, "name": None}
                st.session_state.gemini_model_name = None
                st.session_state.messages = []
                st.session_state.quiz_state = "off"
                st.session_state.quiz_last_question = ""
                st.session_state.debug_log = []
                st.rerun()
            else:
                st.error("❌ الكود غير صحيح")

# باقي main_app نفس السابق (انسخ من الرد السابق) 
