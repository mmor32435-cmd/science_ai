import streamlit as st
import google.generativeai as genai
import requests
import tempfile
import os
import json
import time
import asyncio
import random
from io import BytesIO

# مكتبات الصوت (تأكد من وجودها في requirements.txt)
from streamlit_mic_recorder import mic_recorder
import edge_tts
import speech_recognition as sr

# =========================
# 1. إعدادات الصفحة
# =========================
st.set_page_config(
    page_title="المعلم الذكي | منهاج مصر",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
html, body, .stApp { font-family: 'Cairo', sans-serif !important; direction: rtl; text-align: right; }
.header-box { background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); padding: 2rem; border-radius: 20px; text-align: center; color: white; margin-bottom: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
.stButton>button { background: #2a5298; color: white; border-radius: 10px; height: 50px; width: 100%; font-size: 18px; border: none; transition: 0.3s; }
.stButton>button:hover { background: #1e3c72; transform: scale(1.02); }
</style>
""", unsafe_allow_html=True)

# جلب المفاتيح
GOOGLE_API_KEYS = st.secrets.get("GOOGLE_API_KEYS", [])
if isinstance(GOOGLE_API_KEYS, str):
    GOOGLE_API_KEYS = [k.strip() for k in GOOGLE_API_KEYS.split(",") if k.strip()]

# =========================
# 2. الذكاء الاصطناعي (الاختيار الذكي للموديل)
# =========================
def configure_genai():
    if not GOOGLE_API_KEYS:
        st.error("⚠️ لم يتم العثور على مفاتيح API")
        return False
    
    # اختيار مفتاح عشوائي وتفعيله
    selected_key = random.choice(GOOGLE_API_KEYS)
    genai.configure(api_key=selected_key)
    return True

def get_best_available_model():
    """دالة ذكية تبحث عن الموديل المتاح وتختاره تلقائياً"""
    try:
        # جلب قائمة الموديلات المتاحة للمفتاح
        models = list(genai.list_models())
        
        # ترتيب الأولويات (نفضل 1.5 لأنه يستوعب كتب كبيرة)
        priorities = [
            'gemini-1.5-flash',
            'gemini-1.5-pro',
            'gemini-1.5-flash-latest',
            'gemini-1.0-pro',
            'gemini-pro'
        ]
        
        # البحث عن أفضل موديل متاح في القائمة
        for priority in priorities:
            for m in models:
                if priority in m.name and 'generateContent' in m.supported_generation_methods:
                    return m.name
        
        # إذا لم نجد المفضل، نأخذ أي موديل يدعم التوليد
        for m in models:
            if 'generateContent' in m.supported_generation_methods:
                return m.name
                
        return "gemini-pro" # الحل الأخير
    except Exception as e:
        st.warning(f"تعذر البحث عن الموديلات، سيتم استخدام الافتراضي. الخطأ: {e}")
        return "gemini-1.5-flash"

def upload_to_gemini(path, mime_type="application/pdf"):
    """رفع الملف لسحابة جوجل"""
    try:
        file = genai.upload_file(path, mime_type=mime_type)
        # انتظار المعالجة
        while file.state.name == "PROCESSING":
            time.sleep(2)
            file = genai.get_file(file.name)
        return file
    except Exception as e:
        st.error(f"فشل الرفع لسحابة جوجل: {e}")
        return None

def get_model_session(file_attachment=None):
    """تجهيز الشات بالموديل المختار تلقائياً"""
    
    # 1. الاختيار التلقائي للموديل
    model_name = get_best_available_model()
    # st.toast(f"تم اختيار الموديل: {model_name}") # (اختياري: للتأكد من الموديل)

    config = {
        "temperature": 0.3,
        "top_p": 0.95,
        "top_k": 64,
        "max_output_tokens": 8192,
    }
    
    system_prompt = """أنت معلم خبير في المناهج المصرية.
    دورك هو مساعدة الطالب بناءً على محتوى الكتاب المدرسي المرفق فقط.
    - اشرح بوضوح وبساطة.
    - عند طلب اختبار، استخرج الأسئلة من الكتاب.
    - عند التصحيح، كن دقيقاً وأعط درجة من 10.
    """
    
    model = genai.GenerativeModel(
        model_name=model_name,
        generation_config=config,
        system_instruction=system_prompt
    )
    
    history = []
    if file_attachment:
        history.append({"role": "user", "parts": [file_attachment, "هذا هو الكتاب المدرسي. اعتمد عليه في الشرح."]})
        history.append({"role": "model", "parts": ["حسناً، لقد استوعبت الكتاب كاملاً وأنا جاهز للشرح والاختبار."]})
    
    return model.start_chat(history=history)

# =========================
# 3. إدارة التحميل
# =========================
def load_book_from_url(url):
    try:
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                for chunk in response.iter_content(chunk_size=8192):
                    tmp.write(chunk)
                return tmp.name
    except: pass
    return None

# =========================
# 4. الواجهة الرئيسية
# =========================
def main():
    if "chat_session" not in st.session_state:
        st.session_state.chat_session = None
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # --- القائمة الجانبية ---
    with st.sidebar:
        st.header("📚 إعداد الكتاب")
        
        # خيارات مبسطة
        upload_option = st.radio("المصدر", ["رفع ملف PDF", "رابط مباشر"])
        
        if upload_option == "رفع ملف PDF":
            uploaded_file = st.file_uploader("اختر كتاب الوزارة", type=['pdf'])
            if uploaded_file and st.button("🚀 بدء الدراسة"):
                with st.status("جاري إرسال الكتاب للمعلم الذكي..."):
                    # حفظ مؤقت
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                        tmp.write(uploaded_file.getvalue())
                        local_path = tmp.name
                    
                    if configure_genai():
                        gemini_file = upload_to_gemini(local_path)
                        if gemini_file:
                            st.session_state.chat_session = get_model_session(gemini_file)
                            st.session_state.messages = []
                            st.success("تم قراءة الكتاب بنجاح!")
                            
        else:
            url = st.text_input("لصق رابط الكتاب")
            if url and st.button("تحميل"):
                with st.status("جاري التحميل والمعالجة..."):
                    local_path = load_book_from_url(url)
                    if local_path and configure_genai():
                        gemini_file = upload_to_gemini(local_path)
                        if gemini_file:
                            st.session_state.chat_session = get_model_session(gemini_file)
                            st.session_state.messages = []
                            st.success("تم!")

        if st.session_state.chat_session:
            if st.button("إنهاء الجلسة"):
                st.session_state.chat_session = None
                st.session_state.messages = []
                st.rerun()

    # --- الشاشة الرئيسية ---
    st.markdown(f"""
    <div class="header-box">
        <h1>المعلم الذكي | منهاج مصر</h1>
    </div>
    """, unsafe_allow_html=True)

    if not st.session_state.chat_session:
        st.info("👈 يرجى رفع كتاب المدرسة من القائمة الجانبية للبدء.")
        return

    # التبويبات
    tabs = st.tabs(["💬 اسأل وافهم", "📝 اختبر نفسك", "✅ صحح واجبك"])

    # 1. تبويب الشات
    with tabs[0]:
        for msg in st.session_state.messages:
            role = "user" if msg["role"] == "user" else "assistant"
            with st.chat_message(role):
                st.write(msg["content"])

        c1, c2 = st.columns([1, 8])
        with c1: audio = mic_recorder(start_prompt="🎙️", stop_prompt="🛑", key="mic")
        with c2: prompt = st.chat_input("اكتب سؤالك هنا...")

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
                        response = st.session_state.chat_session.send_message(input_text)
                        st.write(response.text)
                        st.session_state.messages.append({"role": "model", "content": response.text})
                        
                        if st.checkbox("قراءة صوتية", value=True, key="tts_chat"):
                            async def play():
                                v = edge_tts.Communicate(response.text, "ar-EG-ShakirNeural")
                                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                                    await v.save(f.name)
                                    st.audio(f.name)
                            asyncio.run(play())
                    except Exception as e:
                        st.error(f"حدث خطأ: {e}")

    # 2. تبويب الاختبارات
    with tabs[1]:
        col1, col2 = st.columns(2)
        topic = col1.text_input("موضوع الاختبار (مثلاً: الدرس الأول)")
        level = col2.selectbox("المستوى", ["سهل", "متوسط", "صعب"])
        
        if st.button("أنشئ لي اختباراً"):
            if topic:
                p = f"أنشئ اختبار {level} عن '{topic}' من الكتاب. 5 أسئلة فقط. لا تظهر الإجابات."
                with st.spinner("جاري كتابة الأسئلة..."):
                    try:
                        resp = st.session_state.chat_session.send_message(p)
                        st.markdown(resp.text)
                    except Exception as e: st.error(f"خطأ: {e}")

    # 3. تبويب التصحيح
    with tabs[2]:
        q_val = st.text_input("السؤال:")
        a_val = st.text_area("إجابتك:")
        if st.button("صحح لي"):
            if q_val and a_val:
                p = f"السؤال: {q_val}\nإجابتي: {a_val}\nصحح الإجابة من الكتاب وأعطني درجة من 10."
                with st.spinner("جاري التصحيح..."):
                    try:
                        resp = st.session_state.chat_session.send_message(p)
                        st.success(resp.text)
                    except Exception as e: st.error(f"خطأ: {e}")

if __name__ == "__main__":
    main()
