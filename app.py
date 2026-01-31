import streamlit as st
import google.generativeai as genai
import requests
import tempfile
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
st.set_page_config(page_title="المعلم الذكي | وزارة التربية والتعليم", layout="wide", page_icon="🇪🇬")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
html, body, .stApp { font-family: 'Cairo', sans-serif !important; direction: rtl; text-align: right; }
.header-box { background: linear-gradient(135deg, #b20a2c 0%, #fff 100%); padding: 2rem; border-radius: 20px; color: black; text-align: center; margin-bottom: 20px; border: 2px solid gold; }
.stButton>button { background: #b20a2c; color: white; border-radius: 10px; height: 50px; width: 100%; border: none; font-size: 18px; }
</style>
""", unsafe_allow_html=True)

# مفاتيح API
GOOGLE_API_KEYS = st.secrets.get("GOOGLE_API_KEYS", [])
if isinstance(GOOGLE_API_KEYS, str): GOOGLE_API_KEYS = [k.strip() for k in GOOGLE_API_KEYS.split(",")]

# =========================
# 2. مكتبة روابط الوزارة (أضف روابطك هنا)
# =========================
# مثال: استبدل الرابط أدناه بالرابط المباشر للـ PDF من موقع الوزارة
MINISTRY_LINKS = {
    "الابتدائية": {
        "الرابع": {
            "الترم الثاني": {
                "علوم (عربي)": "https://moe.gov.eg/books/primary4_science_ar_t2.pdf", 
                "Science (Lg)": "https://moe.gov.eg/books/primary4_science_en_t2.pdf"
            }
        }
    },
    # يمكنك إضافة باقي الصفوف بنفس النمط
}

def get_book_url(stage, grade, term, subject_type):
    try:
        return MINISTRY_LINKS[stage][grade][term][subject_type]
    except KeyError:
        return None

# =========================
# 3. محرك الذكاء والتخزين السحابي الذكي
# =========================
def configure_genai():
    if not GOOGLE_API_KEYS: return False
    genai.configure(api_key=random.choice(GOOGLE_API_KEYS))
    return True

@st.cache_resource(show_spinner="جاري إحضار الكتاب من موقع الوزارة ورفعه للسحابة (لأول مرة فقط)...")
def get_global_gemini_file(book_url, book_name):
    """
    هذه الدالة هي العقل المدبر:
    1. تحمل الكتاب من رابط الوزارة.
    2. ترفعه لسحابة Gemini.
    3. تحفظ النتيجة في ذاكرة السيرفر لجميع الطلاب.
    """
    if not configure_genai(): return None
    
    try:
        # 1. تحميل من الرابط
        response = requests.get(book_url, stream=True)
        if response.status_code != 200:
            st.error(f"رابط الكتاب لا يعمل (كود {response.status_code})")
            return None
            
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            for chunk in response.iter_content(chunk_size=8192):
                tmp.write(chunk)
            local_path = tmp.name

        # 2. رفع للسحابة
        print(f"Uploading {book_name} to Cloud...")
        file = genai.upload_file(local_path, mime_type="application/pdf")
        
        while file.state.name == "PROCESSING":
            time.sleep(1)
            file = genai.get_file(file.name)
            
        return file
    except Exception as e:
        st.error(f"خطأ أثناء المعالجة: {e}")
        return None

def get_model_session(gemini_file):
    model_name = 'gemini-1.5-flash'
    sys_prompt = "أنت معلم مصري خبير. اشرح للطالب من الكتاب المدرسي المرفق فقط. بسط المعلومة واستخدم لهجة مصرية لطيفة."
    model = genai.GenerativeModel(model_name=model_name, system_instruction=sys_prompt)
    return model.start_chat(history=[{"role": "user", "parts": [gemini_file, "اشرح لي."]}])

# =========================
# 4. الواجهة والتطبيق
# =========================
def init_session():
    if "user" not in st.session_state: st.session_state.user = {"logged_in": False}
    if "chat" not in st.session_state: st.session_state.chat = None
    if "messages" not in st.session_state: st.session_state.messages = []

def login_page():
    st.markdown("<h2 style='text-align: center;'>بوابة الطالب الذكية 🇪🇬</h2>", unsafe_allow_html=True)
    
    with st.form("login"):
        name = st.text_input("اسم الطالب الثلاثي")
        
        c1, c2 = st.columns(2)
        stage = c1.selectbox("المرحلة", ["الابتدائية", "الإعدادية", "الثانوية"])
        
        grades_map = {
            "الابتدائية": ["الرابع", "الخامس", "السادس"],
            "الإعدادية": ["الأول", "الثاني", "الثالث"],
            "الثانوية": ["الأول", "الثاني", "الثالث"]
        }
        grade = c2.selectbox("الصف", grades_map[stage])
        
        term = st.selectbox("الترم", ["الترم الأول", "الترم الثاني"])
        
        # اختيار نوع الدراسة (عربي / لغات)
        lang_type = st.radio("نوع الدراسة", ["علوم (عربي)", "Science (Lg)"], horizontal=True)
        
        if st.form_submit_button("دخول المنصة 🚀"):
            if len(name) > 2:
                st.session_state.user = {
                    "logged_in": True,
                    "name": name,
                    "stage": stage,
                    "grade": grade,
                    "term": term,
                    "subject_type": lang_type
                }
                st.rerun()
            else:
                st.error("يرجى كتابة الاسم")

def main_app():
    u = st.session_state.user
    
    with st.sidebar:
        st.success(f"مرحباً بك يا بطل: {u['name']}")
        st.info(f"{u['stage']} | {u['grade']}")
        
        # جلب الرابط من المكتبة
        book_url = get_book_url(u['stage'], u['grade'], u['term'], u['subject_type'])
        
        if book_url:
            if st.button("📖 فتح الكتاب وبدء الدرس"):
                # استدعاء الدالة السحرية (Cache)
                gemini_file = get_global_gemini_file(book_url, f"{u['grade']}_{u['subject_type']}")
                
                if gemini_file:
                    st.session_state.chat = get_model_session(gemini_file)
                    st.session_state.messages = []
                    st.success("الكتاب جاهز! تفضل اسألني.")
                else:
                    st.error("حدث خطأ في تحميل الكتاب.")
        else:
            st.warning("عذراً، كتاب هذا الصف لم تتم إضافته للمنصة بعد.")
            # حقل احتياطي للمعلم لوضع رابط سريع للتجربة
            temp_url = st.text_input("للمعلم فقط: ضع رابط PDF هنا")
            if temp_url and st.button("تحميل تجريبي"):
                gemini_file = get_global_gemini_file(temp_url, "temp_book")
                if gemini_file:
                    st.session_state.chat = get_model_session(gemini_file)
                    st.session_state.messages = []
                    st.rerun()

        st.divider()
        if st.button("خروج"):
            st.session_state.user["logged_in"] = False
            st.rerun()

    # منطقة الشات
    st.markdown('<div class="header-box"><h1>المعلم المدرسي الذكي</h1></div>', unsafe_allow_html=True)

    if not st.session_state.chat:
        st.info("👈 اضغط على زر 'فتح الكتاب' من القائمة الجانبية.")
        return

    for m in st.session_state.messages:
        with st.chat_message("user" if m["role"]=="user" else "assistant"): st.write(m["content"])

    c1, c2 = st.columns([1, 8])
    with c1: audio = mic_recorder(start_prompt="🎙️", stop_prompt="🛑", key="mic")
    with c2: prompt = st.chat_input("اسألني في الدرس...")

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
            with st.spinner("جاري الشرح..."):
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
