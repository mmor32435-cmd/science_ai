import streamlit as st
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import tempfile
import os
import time
import random
import asyncio
import re
from io import BytesIO
from streamlit_mic_recorder import mic_recorder
import edge_tts
import speech_recognition as sr
import pypdf  # مكتبة استخراج النص الجديدة

# =========================
# 1. إعدادات الصفحة
# =========================
st.set_page_config(page_title="المعلم الذكي | منهاج مصر", layout="wide", page_icon="🇪🇬")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
html, body, .stApp { font-family: 'Cairo', sans-serif !important; direction: rtl; text-align: right; }
.header-box { background: linear-gradient(135deg, #20002c 0%, #cbb4d4 100%); padding: 2rem; border-radius: 20px; color: white; text-align: center; margin-bottom: 20px; }
.stButton>button { background: #20002c; color: white; border-radius: 10px; height: 50px; width: 100%; border: none; font-size: 18px; }
</style>
""", unsafe_allow_html=True)

# الأسرار
FOLDER_ID = "1ub4ML8q4YCM_VZR991XXQ6hBBas2X6rS"
GOOGLE_API_KEYS = st.secrets.get("GOOGLE_API_KEYS", [])
if isinstance(GOOGLE_API_KEYS, str): GOOGLE_API_KEYS = [k.strip() for k in GOOGLE_API_KEYS.split(",")]

# =========================
# 2. الخرائط والمنطق
# =========================
STAGES = ["الابتدائية", "الإعدادية", "الثانوية"]
GRADES = {
    "الابتدائية": ["الرابع", "الخامس", "السادس"],
    "الإعدادية": ["الأول", "الثاني", "الثالث"],
    "الثانوية": ["الأول", "الثاني", "الثالث"],
}
TERMS = ["الترم الأول", "الترم الثاني"]

def subjects_for(stage, grade):
    if stage in ["الابتدائية", "الإعدادية"]: return ["علوم"]
    elif stage == "الثانوية":
        if grade == "الأول": return ["علوم متكاملة"]
        return ["كيمياء", "فيزياء", "أحياء"]
    return ["علوم"]

def generate_file_name_search(stage, grade, subject, lang_type):
    grade_map = {"الرابع": "4", "الخامس": "5", "السادس": "6", "الأول": "1", "الثاني": "2", "الثالث": "3"}
    g_num = grade_map.get(grade, "1")
    lang_code = "En" if "English" in lang_type else "Ar"

    if stage == "الابتدائية": return f"Grade{g_num}_{lang_code}"
    elif stage == "الإعدادية": return f"Prep{g_num}_{lang_code}"
    elif stage == "الثانوية":
        if grade == "الأول": return f"Sec1_Integrated_{lang_code}"
        else:
            sub_map = {"كيمياء": "Chem", "فيزياء": "Physics", "أحياء": "Biology"}
            sub_code = sub_map.get(subject, "Chem")
            return f"Sec{g_num}_{sub_code}_{lang_code}"
    return ""

# =========================
# 3. خدمات جوجل والتحميل
# =========================
def get_service_account_email():
    try:
        creds = dict(st.secrets["gcp_service_account"])
        return creds.get("client_email", "غير موجود")
    except: return "غير موجود"

def configure_genai(key_index=0):
    if not GOOGLE_API_KEYS: return False
    idx = key_index % len(GOOGLE_API_KEYS)
    genai.configure(api_key=GOOGLE_API_KEYS[idx])
    return True

@st.cache_resource
def get_drive_service():
    if "gcp_service_account" not in st.secrets: return None
    try:
        creds = dict(st.secrets["gcp_service_account"])
        creds["private_key"] = creds["private_key"].replace("\\n", "\n")
        return build("drive", "v3", credentials=service_account.Credentials.from_service_account_info(creds))
    except: return None

def find_and_download_book(search_name):
    srv = get_drive_service()
    if not srv: return None, "فشل الاتصال بـ Drive"
    
    q = f"'{FOLDER_ID}' in parents and name contains '{search_name}' and trashed=false"
    try:
        results = srv.files().list(q=q, fields="files(id, name, size)").execute()
        files = results.get('files', [])
        
        if not files: return None, f"لم يتم العثور على ملف: {search_name}"
        
        target_file = files[0]
        request = srv.files().get_media(fileId=target_file['id'])
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            downloader = MediaIoBaseDownload(tmp, request)
            done = False
            while not done: _, done = downloader.next_chunk()
            tmp_path = tmp.name
            
        if os.path.getsize(tmp_path) < 1000:
            return None, "الملف فارغ! تأكد من مشاركة المجلد مع إيميل الخدمة."
            
        return tmp_path, target_file['name']
    except Exception as e:
        return None, str(e)

# --- دالة استخراج النص (الحل البديل للرفع) ---
def extract_text_from_pdf(pdf_path):
    text_content = ""
    try:
        reader = pypdf.PdfReader(pdf_path)
        # قراءة أول 150 صفحة كحد أقصى لتفادي الثقل
        max_pages = min(len(reader.pages), 150)
        for i in range(max_pages):
            text_content += reader.pages[i].extract_text() + "\n"
    except Exception as e:
        return None
    return text_content

@st.cache_resource(show_spinner="جاري قراءة نص الكتاب...")
def get_book_text_content(stage, grade, subject, lang_type):
    search_name = generate_file_name_search(stage, grade, subject, lang_type)
    local_path, msg = find_and_download_book(search_name)
    
    if not local_path:
        st.error(msg)
        return None
    
    # استخراج النص بدلاً من رفع الملف
    text = extract_text_from_pdf(local_path)
    if not text or len(text) < 100:
        st.error("فشل استخراج النصوص من الكتاب. قد يكون صوراً ممسوحة ضوئياً.")
        return None
        
    return text

# =========================
# 4. إدارة الشات (إرسال النص مباشرة)
# =========================
def get_model_chat(book_text):
    # استخدام الموديل الأسرع
    model_name = "gemini-1.5-flash"
    
    # التعليمات + محتوى الكتاب
    sys_prompt = f"""
    أنت معلم مصري خبير.
    هذا هو محتوى الكتاب المدرسي للطالب:
    {book_text[:800000]}  # نرسل أول 800 ألف حرف لضمان عدم تجاوز الحدود
    
    - اشرح الدروس بناءً على هذا المحتوى فقط.
    - بسط المعلومة وتكلم باللهجة المصرية.
    """
    
    last_error = ""
    for api_key in GOOGLE_API_KEYS:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name=model_name)
            
            # بدء الشات مع تعليمات النظام
            chat = model.start_chat(history=[
                {"role": "user", "parts": [sys_prompt + "\n\nهل أنت جاهز؟"]},
                {"role": "model", "parts": ["أيوة يا بطل، أنا قريت الكتاب وجاهز للشرح. اسألني في أي حاجة."]}
            ])
            return chat
        except Exception as e:
            last_error = str(e)
            continue

    st.error(f"فشل الاتصال. الخطأ: {last_error}")
    return None

# =========================
# 5. الواجهة
# =========================
def init_session():
    if "user" not in st.session_state: st.session_state.user = {"logged_in": False}
    if "chat" not in st.session_state: st.session_state.chat = None
    if "messages" not in st.session_state: st.session_state.messages = []

def login_page():
    st.markdown("<h2 style='text-align: center;'>بوابة الطالب الذكية 🇪🇬</h2>", unsafe_allow_html=True)
    if "login_stage" not in st.session_state: st.session_state.login_stage = "الابتدائية"
    
    sel_stage = st.selectbox("المرحلة:", STAGES, index=STAGES.index(st.session_state.login_stage), key="stage_sel", on_change=lambda: st.session_state.update({"login_stage": st.session_state.stage_sel}))
    
    with st.form("login_form"):
        name = st.text_input("اسم الطالب")
        c1, c2 = st.columns(2)
        grade = c1.selectbox("الصف", GRADES.get(sel_stage, []))
        term = c2.selectbox("الترم", TERMS)
        lang_type = st.radio("نوع الدراسة", ["عربي (حكومي/تجريبي)", "English (Lg)"], horizontal=True)
        if st.form_submit_button("دخول المنصة 🚀"):
            if len(name) > 2:
                st.session_state.user = {"logged_in": True, "name": name, "stage": sel_stage, "grade": grade, "term": term, "lang_type": lang_type}
                st.rerun()
            else: st.error("الاسم قصير")

def main_app():
    u = st.session_state.user
    
    with st.sidebar:
        st.success(f"أهلاً: {u['name']}")
        st.info(f"{u['stage']} | {u['grade']}")
        subjects = subjects_for(u['stage'], u['grade'])
        selected_subject = st.radio("اختر المادة:", subjects)
        
        if st.button(f"📖 فتح كتاب: {selected_subject}"):
            # هنا التغيير: نجلب النص بدلاً من كائن الملف
            book_text = get_book_text_content(u['stage'], u['grade'], selected_subject, u['lang_type'])
            if book_text:
                session = get_model_chat(book_text)
                if session:
                    st.session_state.chat = session
                    st.session_state.messages = []
                    st.success("تم فتح الكتاب!")
        
        st.divider()
        svc_email = get_service_account_email()
        with st.expander("🛠️ إعدادات المعلم"):
            st.write("شارك مجلد Drive مع هذا الإيميل:")
            st.code(svc_email, language="text")
            
        if st.button("خروج"):
            st.session_state.user["logged_in"] = False
            st.rerun()

    st.markdown('<div class="header-box"><h1>المعلم المدرسي الذكي</h1></div>', unsafe_allow_html=True)

    if not st.session_state.chat:
        st.info("👈 اختر المادة واضغط 'فتح كتاب' من القائمة الجانبية.")
        return

    for m in st.session_state.messages:
        with st.chat_message("user" if m["role"]=="user" else "assistant"): st.write(m["content"])

    c1, c2 = st.columns([1, 8])
    with c1: audio = mic_recorder(start_prompt="🎙️", stop_prompt="🛑", key="mic")
    with c2: prompt = st.chat_input("اكتب سؤالك...")

    input_text = prompt
    if not input_text and audio:
        try:
            r = sr.Recognizer()
            with sr.AudioFile(BytesIO(audio['bytes'])) as source:
                input_text = r.recognize_google(r.record(source), language="ar-EG")
        except: pass

    if input_text:
        st.session_state.messages.append({"role": "user", "content": input_text})
        with st.chat_message("user"): st.write(input_text)
        
        with st.chat_message("assistant"):
            with st.spinner("..."):
                try:
                    response = None
                    for attempt in range(3):
                        try:
                            response = st.session_state.chat.send_message(input_text)
                            break
                        except Exception as e:
                            if "429" in str(e): time.sleep(2); continue
                            else: raise e
                    
                    if response:
                        st.write(response.text)
                        st.session_state.messages.append({"role": "model", "content": response.text})
                        if st.checkbox("قراءة صوتية", value=True):
                            async def play():
                                v = edge_tts.Communicate(response.text, "ar-EG-ShakirNeural")
                                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                                    await v.save(f.name)
                                    st.audio(f.name)
                            asyncio.run(play())
                    else: st.error("الخادم مشغول.")
                except Exception as e:
                    st.error(f"حدث خطأ: {e}")

if __name__ == "__main__":
    init_session()
    if st.session_state.user["logged_in"]: main_app()
    else: login_page()
