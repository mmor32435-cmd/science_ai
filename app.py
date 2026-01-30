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
from io import BytesIO
from streamlit_mic_recorder import mic_recorder
import edge_tts
import speech_recognition as sr

# =========================
# 1. إعدادات الصفحة
# =========================
st.set_page_config(page_title="المعلم الذكي", layout="wide", page_icon="🎓")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
html, body, .stApp { font-family: 'Cairo', sans-serif !important; direction: rtl; text-align: right; }
.header-box { background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); padding: 2rem; border-radius: 20px; color: white; text-align: center; margin-bottom: 20px; }
.stButton>button { background: #2a5298; color: white; border-radius: 10px; height: 50px; width: 100%; border: none; }
</style>
""", unsafe_allow_html=True)

# أسرار
FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "")
GOOGLE_API_KEYS = st.secrets.get("GOOGLE_API_KEYS", [])
if isinstance(GOOGLE_API_KEYS, str): GOOGLE_API_KEYS = [k.strip() for k in GOOGLE_API_KEYS.split(",")]

# =========================
# 2. الخرائط
# =========================
STAGES = ["الابتدائية", "الإعدادية", "الثانوية"]
GRADES = {"الابتدائية": ["الرابع", "الخامس", "السادس"], "الإعدادية": ["الأول", "الثاني", "الثالث"], "الثانوية": ["الأول", "الثاني", "الثالث"]}
TERMS = ["الترم الأول", "الترم الثاني"]

def get_target_filename(stage, grade, subject, term):
    s_map = {"الابتدائية": "Primary", "الإعدادية": "Prep", "الثانوية": "Sec"}
    g_map = {"الأول": "1", "الثاني": "2", "الثالث": "3", "الرابع": "4", "الخامس": "5", "السادس": "6"}
    sub_map = {"علوم": "Science", "علوم متكاملة": "Integrated", "كيمياء": "Chemistry", "فيزياء": "Physics", "أحياء": "Biology"}
    t_map = {"الترم الأول": "T1", "الترم الثاني": "T2"}
    return f"{s_map[stage]}_{g_map[grade]}_{sub_map[subject]}_{t_map[term]}.pdf"

def subjects_for(stage, grade):
    if stage == "الثانوية": return ["كيمياء", "فيزياء", "أحياء"] if grade != "الأول" else ["علوم متكاملة"]
    return ["علوم"]

# =========================
# 3. الخدمات (Global Caching Magic)
# =========================
def configure_genai():
    if not GOOGLE_API_KEYS: return False
    genai.configure(api_key=random.choice(GOOGLE_API_KEYS))
    return True

@st.cache_resource
def get_drive_service():
    if "gcp_service_account" not in st.secrets: return None
    try:
        creds = dict(st.secrets["gcp_service_account"])
        creds["private_key"] = creds["private_key"].replace("\\n", "\n")
        return build("drive", "v3", credentials=service_account.Credentials.from_service_account_info(creds))
    except: return None

def download_from_drive(filename):
    srv = get_drive_service()
    if not srv: return None
    results = srv.files().list(q=f"'{FOLDER_ID}' in parents and name = '{filename}'", fields="files(id)").execute()
    files = results.get('files', [])
    if not files: return None
    
    try:
        request = srv.files().get_media(fileId=files[0]['id'])
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            downloader = MediaIoBaseDownload(tmp, request)
            done = False
            while not done: _, done = downloader.next_chunk()
            return tmp.name
    except: return None

# --- السحر هنا: دالة محفوظة في الذاكرة المشتركة ---
@st.cache_resource(show_spinner="جاري تجهيز الكتاب للجميع (يحدث مرة واحدة)...")
def get_global_gemini_file(book_filename):
    """
    هذه الدالة تعمل مرة واحدة فقط لكل كتاب!
    النتيجة تخزن في RAM السيرفر وتشارك بين كل الطلاب.
    """
    if not configure_genai(): return None
    
    # 1. نحمل الكتاب من Drive
    local_path = download_from_drive(book_filename)
    if not local_path: return None # الكتاب غير موجود في Drive
    
    try:
        # 2. نرفعه لسحابة Gemini
        print(f"Uploading {book_filename} to Cloud...")
        file = genai.upload_file(local_path, mime_type="application/pdf")
        
        # 3. ننتظر المعالجة
        while file.state.name == "PROCESSING":
            time.sleep(1)
            file = genai.get_file(file.name)
            
        # 4. نرجع كائن الملف (سيتم حفظه في الكاش)
        return file
    except Exception as e:
        print(f"Error: {e}")
        return None

def get_model_session(gemini_file):
    model_name = 'gemini-1.5-flash'
    sys_prompt = """أنت معلم مصري خبير.
    - اعتمد فقط على الكتاب المدرسي المرفق.
    - اشرح بلهجة مصرية بسيطة ومحببة.
    - استخدم إيموجي لتوضيح المعنى.
    """
    model = genai.GenerativeModel(model_name=model_name, system_instruction=sys_prompt)
    return model.start_chat(history=[{"role": "user", "parts": [gemini_file, "ابدأ الدرس."]}])

# =========================
# 4. التطبيق والواجهة
# =========================
def init_session():
    if "user" not in st.session_state: st.session_state.user = {"logged_in": False}
    if "chat" not in st.session_state: st.session_state.chat = None
    if "messages" not in st.session_state: st.session_state.messages = []

def login_page():
    st.markdown("<h2 style='text-align: center;'>🔐 دخول الطالب</h2>", unsafe_allow_html=True)
    with st.form("login"):
        name = st.text_input("الاسم")
        c1, c2 = st.columns(2)
        stage = c1.selectbox("المرحلة", STAGES)
        grade = c2.selectbox("الصف", GRADES[stage])
        term = st.selectbox("الترم", TERMS)
        if st.form_submit_button("دخول"):
            st.session_state.user = {"logged_in": True, "name": name, "stage": stage, "grade": grade, "term": term}
            st.rerun()

def main_app():
    u = st.session_state.user
    with st.sidebar:
        st.success(f"أهلاً {u['name']}")
        
        # اختيار المادة
        subj = st.radio("المادة", subjects_for(u['stage'], u['grade']))
        
        # تحديد اسم الملف المطلوب
        target_file = get_target_filename(u['stage'], u['grade'], subj, u['term'])
        
        if st.button(f"📖 فتح كتاب: {subj}"):
            # هنا يتم استدعاء الدالة المخزنة (Global Cache)
            # إذا كان الكتاب مرفوعاً من قبل، ستعود النتيجة فوراً (Instant)
            gemini_file = get_global_gemini_file(target_file)
            
            if gemini_file:
                st.session_state.chat = get_model_session(gemini_file)
                st.session_state.messages = []
                st.success("تم فتح الكتاب بنجاح! 🚀")
            else:
                st.error(f"عذراً، لم نجد كتاب '{target_file}' في المكتبة.")
                
        st.divider()
        if st.button("خروج"):
            st.session_state.user["logged_in"] = False
            st.rerun()

    # منطقة الشات
    st.markdown('<div class="header-box"><h1>المعلم الذكي</h1></div>', unsafe_allow_html=True)

    if not st.session_state.chat:
        st.info("👈 اختر المادة من القائمة الجانبية.")
        return

    # عرض الرسائل
    for m in st.session_state.messages:
        with st.chat_message("user" if m["role"]=="user" else "assistant"): st.write(m["content"])

    # الإدخال
    c1, c2 = st.columns([1, 8])
    with c1: audio = mic_recorder(start_prompt="🎙️", stop_prompt="🛑", key="mic")
    with c2: prompt = st.chat_input("اكتب سؤالك...")

    # معالجة الصوت
    input_text = prompt
    if not input_text and audio:
        r = sr.Recognizer()
        try:
            with sr.AudioFile(BytesIO(audio['bytes'])) as source:
                input_text = r.recognize_google(r.record(source), language="ar-EG")
        except: pass

    if input_text:
        st.session_state.messages.append({"role": "user", "content": input_text})
        with st.chat_message("user"): st.write(input_text)
        
        with st.chat_message("assistant"):
            with st.spinner("جاري التفكير..."):
                try:
                    # نستخدم الجلسة المجهزة بالكتاب
                    res = st.session_state.chat.send_message(input_text).text
                    st.write(res)
                    st.session_state.messages.append({"role": "model", "content": res})
                    
                    # قراءة صوتية
                    if st.toggle("قراءة صوتية", value=True):
                        async def play():
                            v = edge_tts.Communicate(res, "ar-EG-ShakirNeural")
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                                await v.save(f.name)
                                st.audio(f.name)
                        asyncio.run(play())
                except Exception as e:
                    st.error("حدث خطأ في الاتصال، حاول مجدداً.")

if __name__ == "__main__":
    init_session()
    if st.session_state.user["logged_in"]: main_app()
    else: login_page()
