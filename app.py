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

# =========================
# 1. إعدادات الصفحة
# =========================
st.set_page_config(page_title="المعلم الذكي | منهاج مصر", layout="wide", page_icon="🇪🇬")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
html, body, .stApp { font-family: 'Cairo', sans-serif !important; direction: rtl; text-align: right; }
.header-box { background: linear-gradient(135deg, #1cb5e0 0%, #000046 100%); padding: 2rem; border-radius: 20px; color: white; text-align: center; margin-bottom: 20px; }
.stButton>button { background: #000046; color: white; border-radius: 10px; height: 50px; width: 100%; border: none; font-size: 18px; }
</style>
""", unsafe_allow_html=True)

# الأسرار والمفاتيح
FOLDER_ID = "1ub4ML8q4YCM_VZR991XXQ6hBBas2X6rS" # مجلد الكتب الذي أرسلته
GOOGLE_API_KEYS = st.secrets.get("GOOGLE_API_KEYS", [])
if isinstance(GOOGLE_API_KEYS, str): GOOGLE_API_KEYS = [k.strip() for k in GOOGLE_API_KEYS.split(",")]

# =========================
# 2. الخرائط ومنطق التسمية
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
    if stage == "الثانوية" and grade == "الأول": return ["علوم متكاملة"] # أو مواد منفصلة حسب نظامك
    if stage == "الثانوية": return ["كيمياء", "فيزياء", "أحياء"]
    return ["علوم"]

def get_search_tokens(stage, grade, subject, lang_type):
    # تحويل الاختيارات العربية إلى أجزاء اسم الملف
    # النمط: Sec2_Physics_Ar.pdf.pdf
    
    # 1. المرحلة والصف
    s_map = {"الابتدائية": "Grade", "الإعدادية": "Prep", "الثانوية": "Sec"}
    g_map = {"الأول": "1", "الثاني": "2", "الثالث": "3", "الرابع": "4", "الخامس": "5", "السادس": "6"}
    
    stage_code = f"{s_map[stage]}{g_map[grade]}" # مثال: Sec2
    
    # 2. المادة
    sub_map = {
        "علوم": "Science",
        "علوم متكاملة": "Integrated", # تأكد من اسم المادة في الملفات
        "كيمياء": "Chemistry",
        "فيزياء": "Physics",
        "أحياء": "Biology"
    }
    sub_code = sub_map.get(subject, "Science")
    
    # 3. اللغة
    # lang_type تأتي من الراديو: "علوم (عربي)" أو "Science (Lg)"
    lang_code = "En" if "Lg" in lang_type else "Ar"
    
    # اسم الملف المتوقع (بدون الامتداد المكرر لنسهل البحث)
    # مثال: Sec2_Physics_Ar
    expected_name = f"{stage_code}_{sub_code}_{lang_code}"
    
    return expected_name

# =========================
# 3. خدمات جوجل والبحث الذكي
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

def find_and_download_book(search_name):
    """
    يبحث في المجلد المحدد عن ملف يحتوي اسمه على search_name
    """
    srv = get_drive_service()
    if not srv: return None, "خطأ في خدمة Drive"
    
    # البحث في المجلد المحدد
    # name contains '{search_name}'
    q = f"'{FOLDER_ID}' in parents and name contains '{search_name}' and trashed=false"
    
    try:
        results = srv.files().list(q=q, fields="files(id, name)").execute()
        files = results.get('files', [])
        
        if not files:
            return None, f"لم يتم العثور على كتاب باسم يحتوي على: {search_name}"
        
        # نأخذ أول نتيجة (عادة هي الأصح)
        target_file = files[0]
        file_id = target_file['id']
        file_real_name = target_file['name']
        
        # التحميل
        request = srv.files().get_media(fileId=file_id)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            downloader = MediaIoBaseDownload(tmp, request)
            done = False
            while not done: _, done = downloader.next_chunk()
            return tmp.name, file_real_name
            
    except Exception as e:
        return None, str(e)

# --- الذاكرة الذكية العالمية ---
@st.cache_resource(show_spinner="جاري تجهيز الكتاب ورفعه للسحابة (مرة واحدة لكل الطلاب)...")
def get_global_gemini_file(stage, grade, subject, lang_type):
    if not configure_genai(): return None
    
    # 1. تحديد اسم البحث
    search_name = get_search_tokens(stage, grade, subject, lang_type)
    
    # 2. البحث والتحميل من درايف
    local_path, msg = find_and_download_book(search_name)
    
    if not local_path:
        st.error(msg)
        return None
        
    try:
        # 3. الرفع لـ Gemini
        print(f"Uploading {msg}...")
        file = genai.upload_file(local_path, mime_type="application/pdf")
        
        while file.state.name == "PROCESSING":
            time.sleep(1)
            file = genai.get_file(file.name)
            
        return file
    except Exception as e:
        st.error(f"خطأ في المعالجة السحابية: {e}")
        return None

def get_model_session(gemini_file):
    model_name = 'gemini-1.5-flash'
    sys_prompt = "أنت معلم مصري خبير. اشرح من الكتاب المرفق فقط. بسط المعلومة."
    model = genai.GenerativeModel(model_name=model_name, system_instruction=sys_prompt)
    return model.start_chat(history=[{"role": "user", "parts": [gemini_file, "اشرح لي."]}])

# =========================
# 4. التطبيق والواجهة
# =========================
def init_session():
    if "user" not in st.session_state: st.session_state.user = {"logged_in": False}
    if "chat" not in st.session_state: st.session_state.chat = None
    if "messages" not in st.session_state: st.session_state.messages = []

def login_page():
    st.markdown("<h2 style='text-align: center;'>بوابة الطالب الذكية 🇪🇬</h2>", unsafe_allow_html=True)
    
    with st.form("login"):
        name = st.text_input("اسم الطالب")
        
        # جعل الاختيارات داخل الفورم بسيطة
        c1, c2 = st.columns(2)
        stage = c1.selectbox("المرحلة", STAGES)
        grade = c2.selectbox("الصف", GRADES[stage]) # سيتم تحديثها عند الضغط، لكن كبداية لا بأس
        
        term = st.selectbox("الترم", TERMS)
        lang_type = st.radio("نوع الدراسة", ["عربي (مدارس حكومي/تجريبي)", "English (Lg)"], horizontal=True)
        
        if st.form_submit_button("دخول المنصة 🚀"):
            if len(name) > 2:
                st.session_state.user = {
                    "logged_in": True,
                    "name": name,
                    "stage": stage,
                    "grade": grade,
                    "term": term,
                    "lang_type": lang_type
                }
                st.rerun()
            else:
                st.error("اكتب اسمك")

def main_app():
    u = st.session_state.user
    
    with st.sidebar:
        st.success(f"أهلاً: {u['name']}")
        st.info(f"{u['stage']} | {u['grade']}")
        
        # اختيار المادة ديناميكياً
        subjects = subjects_for(u['stage'], u['grade'])
        selected_subject = st.radio("اختر المادة:", subjects)
        
        if st.button(f"📖 فتح كتاب: {selected_subject}"):
            # استدعاء الدالة الذكية التي تبحث في المجلد مباشرة
            gemini_file = get_global_gemini_file(u['stage'], u['grade'], selected_subject, u['lang_type'])
            
            if gemini_file:
                st.session_state.chat = get_model_session(gemini_file)
                st.session_state.messages = []
                st.success("تم فتح الكتاب!")
            else:
                st.warning("تأكد أن الكتاب موجود في المجلد بالاسم الصحيح.")

        st.divider()
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
                    res = st.session_state.chat.send_message(input_text).text
                    st.write(res)
                    st.session_state.messages.append({"role": "model", "content": res})
                    if st.checkbox("قراءة صوتية", value=True):
                        async def play():
                            v = edge_tts.Communicate(res, "ar-EG-ShakirNeural")
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                                await v.save(f.name)
                                st.audio(f.name)
                        asyncio.run(play())
                except: st.error("خطأ في الاتصال")

if __name__ == "__main__":
    init_session()
    if st.session_state.user["logged_in"]: main_app()
    else: login_page()
