# =========================
# 0) المكتبات المطلوبة
# =========================
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

from PIL import Image
import gspread
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder
import edge_tts

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import google.generativeai as genai

# -- مكتبات الـ OCR والـ PDF --
from pdf2image import convert_from_path
import pytesseract

# -- مكتبات الحل الاحترافي (RAG) باستخدام LangChain --
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain.chains.question_answering import load_qa_chain
from langchain.prompts import PromptTemplate
from langchain_core.documents import Document

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
.stTextInput input, .stTextArea textarea { background-color: #ffffff !important; color: #000000 !important; border: 2px solid #004e92 !important; border-radius: 8px !important; }
div[data-baseweb="select"] > div { background-color: #ffffff !important; border: 2px solid #004e92 !important; border-radius: 8px !important; }
ul[data-baseweb="menu"] { background-color: #ffffff !important; }
li[data-baseweb="option"] { color: #000000 !important; }
li[data-baseweb="option"]:hover { background-color: #e3f2fd !important; }
h1, h2, h3, h4, h5, p, label, span { color: #000000 !important; }
.stButton>button { background: linear-gradient(90deg, #004e92 0%, #000428 100%) !important; color: #ffffff !important; border: none; border-radius: 10px; height: 55px; width: 100%; font-size: 20px !important; font-weight: bold !important; }
.header-box { background: linear-gradient(90deg, #000428 0%, #004e92 100%); padding: 2rem; border-radius: 15px; text-align: center; margin-bottom: 2rem; box-shadow: 0 4px 15px rgba(0,0,0,0.2); }
.header-box h1, .header-box h3 { color: #ffffff !important; }
.stChatMessage { background-color: #ffffff !important; border: 1px solid #d1d1d1 !important; border-radius: 12px !important; }
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
    st.session_state.user_data = {"logged_in": False, "role": None, "name": ""}
if "messages" not in st.session_state:
    st.session_state.messages = []
if "book_data" not in st.session_state:
    st.session_state.book_data = {"path": None, "name": None}
if "vector_store" not in st.session_state: # لتخزين فهرس الكتاب
    st.session_state.vector_store = None
if "quiz_state" not in st.session_state:
    st.session_state.quiz_state = "off"
if "quiz_last_question" not in st.session_state:
    st.session_state.quiz_last_question = ""
if "debug_enabled" not in st.session_state:
    st.session_state.debug_enabled = True
if "debug_log" not in st.session_state:
    st.session_state.debug_log = []

def dbg(event, data=None):
    if not st.session_state.debug_enabled: return
    rec = {"t": time.strftime("%H:%M:%S"), "event": event}
    if data is not None: rec["data"] = data
    st.session_state.debug_log.append(rec)
    st.session_state.debug_log = st.session_state.debug_log[-400:]

# =========================
# 4) Secrets
# =========================
TEACHER_KEY = st.secrets.get("TEACHER_MASTER_KEY", "ADMIN")
SHEET_NAME = st.secrets.get("CONTROL_SHEET_NAME", "App_Control")
FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "")
GOOGLE_API_KEYS = st.secrets.get("GOOGLE_API_KEYS", [])
# =========================
# 5) Google creds + Sheets
# =========================
@st.cache_resource
def get_credentials():
    if "gcp_service_account" not in st.secrets: return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        return service_account.Credentials.from_service_account_info(creds_dict, scopes=scopes)
    except Exception as e:
        dbg("creds_error", str(e))
        return None

def get_gspread_client():
    creds = get_credentials()
    return gspread.authorize(creds) if creds else None

def check_student_code(input_code):
    client = get_gspread_client()
    if not client: return False
    try:
        sh = client.open(SHEET_NAME)
        real_code = str(sh.sheet1.acell("B1").value).strip()
        return str(input_code).strip() == real_code
    except Exception as e:
        dbg("check_student_code_error", str(e))
        return False
       # =========================
# 6) تحميل الكتاب من Drive
# =========================
def load_book_from_drive(stage, grade, lang):
    creds = get_credentials()
    if not creds: return None
    try:
        target_tokens = []
        if "الثانوية" in stage:
            if "الأول" in grade: target_tokens.append("Sec1")
            elif "الثاني" in grade: target_tokens.append("Sec2")
            elif "الثالث" in grade: target_tokens.append("Sec3")
        elif "الإعدادية" in stage:
            if "الأول" in grade: target_tokens.append("Prep1")
            elif "الثاني" in grade: target_tokens.append("Prep2")
            elif "الثالث" in grade: target_tokens.append("Prep3")
        else:
            if "الرابع" in grade: target_tokens.append("Grade4")
            elif "الخامس" in grade: target_tokens.append("Grade5")
            elif "السادس" in grade: target_tokens.append("Grade6")

        lang_code = "Ar" if "العربية" in lang else "En"
        target_tokens.append(lang_code)

        service = build("drive", "v3", credentials=creds)
        query = f"'{FOLDER_ID}' in parents and mimeType='application/pdf'"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        all_files = results.get("files", [])
        matched_file = next((f for f in all_files if all(tok.lower() in f.get("name", "").lower() for tok in target_tokens)), None)

        if not matched_file:
            dbg("book_not_found", {"tokens": target_tokens, "files": [x.get("name") for x in all_files]})
            return None

        request = service.files().get_media(fileId=matched_file["id"])
        file_path = os.path.join(tempfile.gettempdir(), matched_file["name"])

        with open(file_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done: status, done = downloader.next_chunk()
        
        dbg("book_downloaded", {"name": matched_file["name"], "path": file_path, "size": os.path.getsize(file_path)})
        return {"path": file_path, "name": matched_file["name"]}

    except Exception as e:
        dbg("load_book_error", {"err": str(e), "trace": traceback.format_exc()})
        return None

# =========================
# 7) نظام RAG: معالجة وفهرسة الكتاب
# =========================
@st.cache_data(show_spinner="جاري قراءة الكتاب لأول مرة (قد يستغرق عدة دقائق)...")
def ocr_entire_pdf(_pdf_path: str, lang: str = "ara"):
    try:
        pages = convert_from_path(_pdf_path, dpi=200, first_page=1, last_page=None)
        full_text = [pytesseract.image_to_string(im, lang=lang) for im in pages]
        text = "\n\n--- نهاية الصفحة ---\n\n".join(full_text)
        dbg("full_ocr_complete", {"chars": len(text), "pages": len(pages)})
        return text
    except Exception as e:
        dbg("full_ocr_error", {"err": str(e), "trace": traceback.format_exc()})
        return f"__OCR_ERROR__:{e}"

@st.cache_resource(show_spinner="جاري فهرسة محتوى الكتاب...")
def create_vector_store_from_text(_text: str):
    if not _text or "__OCR_ERROR__" in _text: return None
    try:
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200, add_start_index=True)
        docs = [Document(page_content=chunk) for chunk in text_splitter.split_text(_text)]
        dbg("text_split_success", {"chunks_count": len(docs)})

        api_key = random.choice(GOOGLE_API_KEYS)
        embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001", google_api_key=api_key)
        vector_store = FAISS.from_documents(docs, embedding=embeddings)
        dbg("vector_store_created", "FAISS index built successfully.")
        return vector_store
    except Exception as e:
        dbg("vector_store_error", {"err": str(e), "trace": traceback.format_exc()})
        return None

def ensure_book_and_rag_are_ready():
    u = st.session_state.user_data
    if not st.session_state.book_data.get("path"):
        data = load_book_from_drive(u["stage"], u["grade"], u["lang"])
        if not data:
            st.error("لم يتم العثور على الكتاب المطابق للمرحلة والصف.")
            return False
        st.session_state.book_data = data
    
    if st.session_state.vector_store is None:
        pdf_path = st.session_state.book_data.get("path")
        if pdf_path and os.path.exists(pdf_path):
            ocr_lang = "eng" if "English" in u["lang"] else "ara"
            full_text = ocr_entire_pdf(pdf_path, lang=ocr_lang)
            if full_text and "__OCR_ERROR__" not in full_text:
                st.session_state.vector_store = create_vector_store_from_text(full_text)
                if st.session_state.vector_store is None:
                    st.error("فشل في إنشاء فهرس الكتاب.")
                    return False
            else:
                st.error(f"حدث خطأ أثناء قراءة الكتاب (OCR): {full_text}")
                return False
    return st.session_state.vector_store is not None
# =========================
# 8) Gemini (باستخدام RAG)
# =========================
def get_ai_response(user_text: str) -> str:
    if not GOOGLE_API_KEYS: return "⚠️ المفاتيح مفقودة."
    if not ensure_book_and_rag_are_ready():
        return "⚠️ لم يتم تحميل الكتاب أو فهرسته بنجاح. حاول تحديث الصفحة."

    api_key = random.choice(GOOGLE_API_KEYS)
    u = st.session_state.user_data
    is_english = "English" in u["lang"]
    quiz_state = st.session_state.quiz_state
    model = ChatGoogleGenerativeAI(model="gemini-1.5-flash-latest", google_api_key=api_key, temperature=0.2)
    
    try:
        if quiz_state == "asking":
            vector_store = st.session_state.vector_store
            random_doc_index = random.choice(list(vector_store.docstore._dict.keys()))
            random_context_doc = vector_store.docstore.get_document(random_doc_index)
            q_prompt_text = "From the text below, create ONE short, clear quiz question. Return ONLY the question itself, with no preamble.\n\nText: {context}" if is_english else "من النص أدناه، كوّن سؤال اختبار واحد قصير وواضح. أرجع السؤال فقط بدون أي مقدمات.\n\nالنص: {context}"
            response = model.invoke(q_prompt_text.format(context=random_context_doc.page_content))
            resp = response.content.strip()
            st.session_state.quiz_last_question = resp
            st.session_state.quiz_state = "waiting_answer"
            return resp

        search_query = st.session_state.quiz_last_question if quiz_state == "correcting" else user_text
        relevant_docs = st.session_state.vector_store.similarity_search(search_query, k=5)
        dbg("similarity_search_done", {"query": search_query, "docs_found": len(relevant_docs)})

        if quiz_state == "correcting":
            q = st.session_state.quiz_last_question.strip()
            a = user_text.strip()
            final_user_query = f"Based on the provided context, grade the student's answer.\nQuestion: {q}\nStudent answer: {a}\nGive a score out of 10 and short, encouraging feedback." if is_english else f"بناءً على النص المقدم، صحح إجابة الطالب.\nالسؤال: {q}\nإجابة الطالب: {a}\nأعطِ درجة من 10 مع تعليق مختصر ومشجع."
        else:
            final_user_query = user_text
        
        prompt_template_str = """You are an expert science teacher. Answer the student's question based ONLY on the provided textbook context. If the answer is not in the context, say 'I cannot find the answer in the provided text'. Be concise and clear. Context: {context} Question: {question} Answer:""" if is_english else """أنت معلم علوم خبير. أجب على سؤال الطالب بالاعتماد الكامل على النص المقدم من كتابه المدرسي. إذا كانت الإجابة غير موجودة، قل 'لا أجد الإجابة في النص المقدم'. كن مختصراً وواضحاً. النص المرجعي: {context} سؤال الطالب: {question} الإجابة:"""
        
        prompt = PromptTemplate(template=prompt_template_str, input_variables=["context", "question"])
        chain = load_qa_chain(model, chain_type="stuff", prompt=prompt)
        resp = chain.invoke({"input_documents": relevant_docs, "question": final_user_query}, return_only_outputs=True).get("output_text", "")
        
        if quiz_state == "correcting":
            st.session_state.quiz_last_question = ""
            st.session_state.quiz_state = "off"
        return resp if resp else "لم أجد إجابة في النص المقدم."
    except Exception as e:
        dbg("rag_chain_error", {"err": str(e), "trace": traceback.format_exc()})
        if quiz_state != "off": st.session_state.quiz_state = "off"
        return f"خطأ تقني أثناء البحث عن الإجابة: {e}"

# =========================
# 9) صوت (STT/TTS)
# =========================
def clean_text_for_speech(text):
    return re.sub(r'[*#_`]', '', text)

def speech_to_text(audio_bytes, lang_ui):
    r = sr.Recognizer()
    try:
        with sr.AudioFile(io.BytesIO(audio_bytes)) as source:
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

def text_to_speech_pro(text, lang_ui):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(generate_speech_async(text, lang_ui))
    except Exception as e:
        dbg("tts_error", str(e))
        return None
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
            grade_options = {"الابتدائية": ["الرابع", "الخامس", "السادس"], "الإعدادية": ["الأول", "الثاني", "الثالث"], "الثانوية": ["الأول", "الثاني", "الثالث"]}
            grade = st.selectbox("الصف الدراسي", grade_options[stage])
        
        submit = st.form_submit_button("🚀 بدء التعلم")
        if submit:
            is_teacher = code == TEACHER_KEY
            is_student = check_student_code(code)
            if is_teacher or is_student:
                for key in list(st.session_state.keys()):
                    if key != 'user_data': del st.session_state[key]
                st.session_state.user_data.update({
                    "logged_in": True, "role": "Teacher" if is_teacher else "Student", "name": name,
                    "stage": stage if is_student else None, "grade": grade if is_student else None, "lang": lang if is_student else "العربية (علوم)"
                })
                st.rerun()
            else:
                st.error("❌ الكود غير صحيح")

def main_app():
    with st.sidebar:
        st.success(f"مرحباً: {st.session_state.user_data['name']}")
        if st.session_state.user_data['role'] == 'Student':
            st.info(f"{st.session_state.user_data['grade']} {st.session_state.user_data['stage']} | {st.session_state.user_data['lang']}")
        st.write("---")
        st.session_state.debug_enabled = st.checkbox("DEBUG", value=False)
        if st.session_state.debug_enabled:
            if st.button("مسح سجل DEBUG"):
                st.session_state.debug_log = []
                st.rerun()
            with st.expander("سجل DEBUG"):
                st.code(json.dumps(st.session_state.debug_log, ensure_ascii=False, indent=2))
        st.write("---")
        if st.button("📝 ابدأ اختبار"):
            st.session_state.quiz_state = "asking"
            st.session_state.messages.append({"role": "user", "content": "ابدأ اختبار"})
            with st.spinner("جاري إعداد السؤال..."):
                resp = get_ai_response("ابدأ اختبار")
                st.session_state.messages.append({"role": "assistant", "content": resp})
            st.rerun()
        if st.session_state.quiz_state == "waiting_answer":
            st.info("وضع الاختبار: أجب على السؤال الأخير وسيتم تصحيحه.")
        st.write("---")
        if st.button("🚪 خروج"):
            st.session_state.user_data["logged_in"] = False
            st.rerun()

    st.subheader("💬 اسأل المعلم")
    audio = mic_recorder(start_prompt="تحدث ⏺️", stop_prompt="إرسال ⏹️", key="recorder", format="wav", use_container_width=True)
    voice_text = None
    if audio:
        with st.spinner("جاري السماع..."):
            voice_text = speech_to_text(audio["bytes"], st.session_state.user_data["lang"])

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    text_input = st.chat_input("اكتب إجابتك أو سؤالك هنا...")
    final_q = text_input if text_input else voice_text

    if final_q:
        if st.session_state.quiz_state == "waiting_answer":
            st.session_state.quiz_state = "correcting"
        st.session_state.messages.append({"role": "user", "content": final_q})
        with st.chat_message("user"):
            st.write(final_q)
        with st.chat_message("assistant"):
            with st.spinner("المعلم يفكر..."):
                resp = get_ai_response(final_q)
                st.write(resp)
                if any(x in resp.lower() for x in ["10/10", "9/10", "ممتاز", "أحسنت", "excellent", "great job"]):
                    celebrate_success()
                aud = text_to_speech_pro(resp, st.session_state.user_data["lang"])
                if aud:
                    st.audio(aud, format="audio/mp3")
                    try: os.remove(aud)
                    except: pass
        st.session_state.messages.append({"role": "assistant", "content": resp})
        st.rerun()
# =========================
# 11) نقطة تشغيل التطبيق
# =========================
if __name__ == "__main__":
    if st.session_state.user_data.get("logged_in", False):
        main_app()
    else:
        login_page()
