import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import google.generativeai as genai
import gspread
from PIL import Image
import random
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder
import asyncio
import edge_tts
import tempfile
import os
import re
import io
import PyPDF2

# ==========================================
# 1. إعدادات الصفحة والتصميم
# ==========================================
st.set_page_config(page_title="المعلم العلمي | السيد البدوي", page_icon="🧬", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Cairo', sans-serif !important; direction: rtl; text-align: right; }
    .stApp { background: linear-gradient(180deg, #f0f4f8 0%, #d9e2ec 100%); }
    
    /* تصميم الحقول */
    div[data-baseweb="select"] > div, .stTextInput input {
        background-color: #ffffff !important;
        border: 2px solid #004e92 !important;
        border-radius: 8px !important;
        color: #000000 !important;
        font-weight: bold !important;
    }
    div[data-baseweb="select"] span { color: #000000 !important; }
    ul[data-baseweb="menu"] { background-color: #ffffff !important; }
    li[data-baseweb="option"] { color: #000000 !important; }
    
    /* النصوص والأزرار */
    h1, h2, h3, h4, h5, p, label { color: #000000 !important; }
    .stButton>button {
        background: linear-gradient(90deg, #004e92 0%, #000428 100%) !important;
        color: #ffffff !important; border: none; border-radius: 10px; height: 55px; width: 100%; font-size: 20px !important;
    }
    
    /* العنوان والرسائل */
    .header-box {
        background: linear-gradient(90deg, #000428 0%, #004e92 100%);
        padding: 2rem; border-radius: 15px; text-align: center; margin-bottom: 2rem; box-shadow: 0 4px 15px rgba(0,0,0,0.2);
    }
    .header-box h1, .header-box h3 { color: #ffffff !important; }
    .stChatMessage { background-color: #ffffff !important; border: 1px solid #d1d1d1 !important; border-radius: 12px !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("""<div class="header-box"><h1>الأستاذ / السيد البدوي</h1><h3>المنصة التعليمية الذكية (ابتدائي - إعدادي - ثانوي)</h3></div>""", unsafe_allow_html=True)

# ==========================================
# 3. إدارة الجلسة والاتصال
# ==========================================
if 'user_data' not in st.session_state: st.session_state.user_data = {"logged_in": False, "role": None, "name": "", "grade": "", "stage": "", "lang": ""}
if 'messages' not in st.session_state: st.session_state.messages = []
if 'book_content' not in st.session_state: st.session_state.book_content = ""

TEACHER_KEY = st.secrets.get("TEACHER_MASTER_KEY", "ADMIN")
SHEET_NAME = st.secrets.get("CONTROL_SHEET_NAME", "App_Control")

@st.cache_resource
def get_credentials():
    if "gcp_service_account" not in st.secrets: return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_dict: creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        return service_account.Credentials.from_service_account_info(creds_dict, scopes=scopes)
    except: return None

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
    except: return False

# ---------------------------------------------------------
# 🔥 دالة جلب الكتب المحدثة (تدعم تعدد الكتب للثانوي) 🔥
# ---------------------------------------------------------
@st.cache_resource
def get_book_text_from_drive(stage, grade, lang):
    creds = get_credentials()
    if not creds: return None
    try:
        lang_code = "Ar" if "العربية" in lang else "En"
        search_query = ""
        
        # 1. منطق المرحلة الثانوية
        if "الثانوية" in stage:
            mapping = {"الأول": "Sec1", "الثاني": "Sec2", "الثالث": "Sec3"}
            prefix = mapping.get(grade, "Sec1")
            
            if prefix == "Sec1":
                # الصف الأول: كتاب واحد (علوم متكاملة)
                search_query = f"name contains '{prefix}_Integrated_{lang_code}'"
            else:
                # الصف الثاني والثالث: كتب متعددة (فيزياء، كيمياء، أحياء)
                # سنبحث عن أي ملف يبدأ بـ Sec2 أو Sec3 ويخص اللغة
                search_query = f"name contains '{prefix}_' and name contains '_{lang_code}'"
        
        # 2. منطق الإعدادي والابتدائي (كتاب واحد)
        elif "الإعدادية" in stage:
            mapping = {"الأول": "Prep1", "الثاني": "Prep2", "الثالث": "Prep3"}
            prefix = mapping.get(grade, "Prep1")
            search_query = f"name contains '{prefix}_{lang_code}'"
        else:
            mapping = {"الرابع": "Grade4", "الخامس": "Grade5", "السادس": "Grade6"}
            prefix = mapping.get(grade, "Grade4")
            search_query = f"name contains '{prefix}_{lang_code}'"

        # تنفيذ البحث
        service = build('drive', 'v3', credentials=creds)
        # البحث عن كل الملفات المطابقة بصيغة PDF
        query = f"{search_query} and mimeType='application/pdf'"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])
        
        if not files: return None
        
        full_text = ""
        # قراءة كل الملفات التي وجدناها (لدمج الفيزياء والكيمياء والأحياء معاً)
        for file in files:
            try:
                request = service.files().get_media(fileId=file['id'])
                file_stream = io.BytesIO()
                downloader = MediaIoBaseDownload(file_stream, request)
                done = False
                while done is False: status, done = downloader.next_chunk()
                
                file_stream.seek(0)
                pdf_reader = PyPDF2.PdfReader(file_stream)
                # نأخذ جزءاً من كل كتاب (مثلاً أول 40 صفحة لتوفير الذاكرة)
                for page in pdf_reader.pages[:40]: 
                    full_text += page.extract_text() + "\n"
                full_text += "\n--- نهاية الكتاب ---\n"
            except: continue
            
        return full_text if full_text else None
    except: return None

# ==========================================
# 4. الصوت والميكروفون
# ==========================================
def clean_text_for_speech(text): return re.sub(r'[\*\#\-\_]', '', text)

def speech_to_text(audio_bytes):
    r = sr.Recognizer()
    try:
        audio_io = io.BytesIO(audio_bytes)
        with sr.AudioFile(audio_io) as source:
            audio_data = r.record(source)
            return r.recognize_google(audio_data, language="ar-EG")
    except: return None

async def generate_speech_async(text, voice="ar-EG-ShakirNeural"):
    cleaned = clean_text_for_speech(text)
    communicate = edge_tts.Communicate(cleaned, voice)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
        await communicate.save(tmp_file.name)
        return tmp_file.name

def text_to_speech_pro(text):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(generate_speech_async(text))
    except: return None

# ==========================================
# 5. الذكاء الاصطناعي
# ==========================================
def get_dynamic_model():
    try:
        all_models = genai.list_models()
        valid_models = [m.name for m in all_models if 'generateContent' in m.supported_generation_methods]
        if not valid_models: return None
        for m in valid_models:
            if 'flash' in m.lower(): return m
        for m in valid_models:
            if 'pro' in m.lower(): return m
        return valid_models[0]
    except: return None

def get_ai_response(user_text, img_obj=None, is_quiz_mode=False):
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys: return "⚠️ المفاتيح مفقودة."
    genai.configure(api_key=random.choice(keys))
    
    model_name = get_dynamic_model()
    if not model_name: return "عذراً، لا توجد نماذج متاحة."
    
    u = st.session_state.user_data
    if not st.session_state.book_content:
        st.session_state.book_content = get_book_text_from_drive(u['stage'], u['grade'], u['lang'])

    context = ""
    if st.session_state.book_content:
        context = f"اعتمد في إجابتك على المعلومات التالية من كتب الطالب:\n{st.session_state.book_content[:40000]}..."
    
    quiz_instr = "أنشئ سؤالاً واحداً فقط." if is_quiz_mode else ""
    lang_prompt = "اشرح بالعربية." if "العربية" in u['lang'] else "Explain in English."
    
    sys_prompt = f"""
    أنت الأستاذ السيد البدوي.
    {context}
    1. التزم بالمنهج المصري والكتب المرفقة.
    2. {lang_prompt}
    3. كن مختصراً (نقاط).
    4. {quiz_instr}
    """
    
    inputs = [sys_prompt, user_text]
    if img_obj: inputs.extend([img_obj, "اشرح الصورة."])

    try:
        model = genai.GenerativeModel(model_name)
        return model.generate_content(inputs).text
    except Exception as e: return f"خطأ: {e}"

# ==========================================
# 6. الواجهات والتشغيل
# ==========================================
def celebrate_success():
    st.balloons()
    st.toast("🌟 ممتاز! أحسنت!", icon="🎉")

def login_page():
    with st.container():
        st.markdown("### 🔐 تسجيل الدخول")
        with st.form("login"):
            name = st.text_input("الاسم الثلاثي")
            code = st.text_input("الكود السري", type="password")
            st.markdown("---")
            st.markdown("**اختر بياناتك الدراسية:**")
            
            col1, col2 = st.columns(2)
            with col1:
                stage = st.selectbox("المرحلة", ["الابتدائية", "الإعدادية", "الثانوية"])
                lang = st.selectbox("اللغة", ["العربية (علوم)", "English (Science)"])
            with col2:
                # الصفوف تشمل الجميع
                grade = st.selectbox("الصف الدراسي", ["الرابع", "الخامس", "السادس", "الأول", "الثاني", "الثالث"])
            
            submit = st.form_submit_button("🚀 بدء التعلم")
            
            if submit:
                if code == TEACHER_KEY:
                    st.session_state.user_data.update({"logged_in": True, "role": "Teacher", "name": name})
                    st.rerun()
                elif check_student_code(code):
                    st.session_state.user_data.update({"logged_in": True, "role": "Student", "name": name, "stage": stage, "grade": grade, "lang": lang})
                    st.session_state.book_content = ""
                    st.rerun()
                else:
                    st.error("❌ الكود غير صحيح")

def main_app():
    with st.sidebar:
        st.success(f"مرحباً: {st.session_state.user_data['name']}")
        st.info(f"{st.session_state.user_data['stage']} - {st.session_state.user_data['grade']}")
        if st.button("📝 اختبار سريع"):
             st.session_state.messages.append({"role": "user", "content": "أريد سؤال اختبار."})
        st.write("---")
        if st.button("🚪 خروج"):
            st.session_state.user_data["logged_in"] = False
            st.rerun()

    st.subheader("💬 اسأل المعلم")
    
    col1, col2 = st.columns(2)
    with col1:
        st.info("🎙️ الميكروفون:")
        audio = mic_recorder(start_prompt="تسجيل ⏺️", stop_prompt="إرسال ⏹️", key='recorder', format='wav')
    with col2:
        with st.expander("📸 إرفاق صورة"):
            f = st.file_uploader("اختر صورة", type=['jpg', 'png'])
            img = Image.open(f) if f else None
            if img: st.image(img, width=150)

    voice_text = None
    if audio:
        with st.spinner("جاري السماع..."):
            voice_text = speech_to_text(audio['bytes'])

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): st.write(msg["content"])

    text_input = st.chat_input("اكتب سؤالك هنا...")
    final_q = text_input if text_input else voice_text

    if final_q:
        st.session_state.messages.append({"role": "user", "content": final_q})
        with st.chat_message("user"): st.write(final_q)
        
        with st.chat_message("assistant"):
            with st.spinner("جاري الرد..."):
                is_quiz = "اختبار" in final_q or "سؤال" in final_q
                resp = get_ai_response(final_q, img, is_quiz)
                st.write(resp)
                if any(x in resp for x in ["أحسنت", "ممتاز"]): celebrate_success()
                aud = text_to_speech_pro(resp)
                if aud: st.audio(aud, format='audio/mp3')
        st.session_state.messages.append({"role": "assistant", "content": resp})

if __name__ == "__main__":
    if st.session_state.user_data["logged_in"]:
        main_app()
    else:
        login_page()
