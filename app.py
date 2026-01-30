import streamlit as st
import google.generativeai as genai
import requests
import tempfile
import os
import json
import time
import asyncio
from streamlit_mic_recorder import mic_recorder
import edge_tts
import speech_recognition as sr
from io import BytesIO

# =========================
# 1. إعدادات الصفحة والسرية
# =========================
st.set_page_config(
    page_title="المعلم الذكي | منهاج مصر",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# تنسيق CSS احترافي وعربي
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
html, body, .stApp { font-family: 'Cairo', sans-serif !important; direction: rtl; text-align: right; }
.header-box { background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); padding: 2rem; border-radius: 20px; text-align: center; color: white; margin-bottom: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
.stButton>button { background: #2a5298; color: white; border-radius: 10px; height: 50px; width: 100%; font-size: 18px; border: none; transition: 0.3s; }
.stButton>button:hover { background: #1e3c72; transform: scale(1.02); }
.book-card { background: #f8f9fa; padding: 15px; border-radius: 10px; border: 1px solid #ddd; margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

# مفاتيح API
GOOGLE_API_KEYS = st.secrets.get("GOOGLE_API_KEYS", [])
if isinstance(GOOGLE_API_KEYS, str):
    GOOGLE_API_KEYS = [k.strip() for k in GOOGLE_API_KEYS.split(",") if k.strip()]

# =========================
# 2. مكتبة كتب الوزارة (قابلة للتوسع)
# =========================
# يمكنك إضافة روابط الكتب الحقيقية هنا من موقع الوزارة
MINISTRY_BOOKS = {
    "الابتدائية": {
        "الرابع": {
            "علوم (عربي)": "https://example.com/grade4_science_ar.pdf", # استبدل هذا برابط حقيقي
            "Science (Lg)": "https://example.com/grade4_science_en.pdf"
        },
        "الخامس": { "علوم": "url...", "Science": "url..." },
        "السادس": { "علوم": "url...", "Science": "url..." },
    },
    "الإعدادية": {
        "الأول": { "علوم": "url...", "Science": "url..." },
        "الثاني": { "علوم": "url...", "Science": "url..." },
        "الثالث": { "علوم": "url...", "Science": "url..." },
    },
    "الثانوية": {
        "الأول": { "كيمياء": "url...", "فيزياء": "url...", "أحياء": "url..." },
        "الثاني": { "كيمياء": "url...", "فيزياء": "url...", "أحياء": "url..." },
        "الثالث": { "كيمياء": "url...", "فيزياء": "url...", "أحياء": "url..." },
    }
}

# =========================
# 3. محرك الذكاء الاصطناعي (Gemini Cloud)
# =========================
def configure_genai():
    if not GOOGLE_API_KEYS:
        st.error("⚠️ لم يتم العثور على مفاتيح API في Secrets")
        return False
    # تدوير المفاتيح لتجنب الحظر
    genai.configure(api_key=random.choice(GOOGLE_API_KEYS))
    return True

import random

def upload_to_gemini(path, mime_type="application/pdf"):
    """يرفع الملف إلى سيرفرات جوجل مباشرة للمعالجة السريعة"""
    try:
        file = genai.upload_file(path, mime_type=mime_type)
        # ننتظر حتى تتم معالجة الملف
        while file.state.name == "PROCESSING":
            time.sleep(2)
            file = genai.get_file(file.name)
        return file
    except Exception as e:
        st.error(f"فشل الرفع لسحابة جوجل: {e}")
        return None

def get_model(file_attachment=None):
    """يجهز الموديل مع الملف المرفق (الكتاب)"""
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
        model_name="gemini-1.5-flash",
        generation_config=config,
        system_instruction=system_prompt
    )
    
    # بدء الشات مع الملف المرفق (الكتاب)
    history = []
    if file_attachment:
        history.append({"role": "user", "parts": [file_attachment, "هذا هو الكتاب المدرسي. اعتمد عليه في كل إجاباتك."]})
        history.append({"role": "model", "parts": ["حسناً، لقد قرأت الكتاب المدرسي كاملاً وأنا مستعد للمساعدة."]})
    
    return model.start_chat(history=history)

# =========================
# 4. إدارة الملفات والتحميل
# =========================
def load_book_from_url(url, filename):
    """يحمل الكتاب من رابط الوزارة"""
    try:
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                for chunk in response.iter_content(chunk_size=8192):
                    tmp.write(chunk)
                return tmp.name
        return None
    except:
        return None

# =========================
# 5. الواجهة والتشغيل
# =========================
def main():
    # تهيئة الحالة
    if "chat_session" not in st.session_state:
        st.session_state.chat_session = None
    if "current_book" not in st.session_state:
        st.session_state.current_book = None
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # --- القائمة الجانبية (اختيار المنهج) ---
    with st.sidebar:
        st.image("https://cdn-icons-png.flaticon.com/512/3426/3426653.png", width=100)
        st.title("إعدادات المنهج")
        
        stage = st.selectbox("المرحلة", list(MINISTRY_BOOKS.keys()))
        grade = st.selectbox("الصف", list(MINISTRY_BOOKS[stage].keys()))
        subject = st.selectbox("المادة", list(MINISTRY_BOOKS[stage][grade].keys()))
        
        # خيار: استخدام رابط الوزارة أو رفع ملف
        input_method = st.radio("مصدر الكتاب", ["رابط مباشر (URL)", "رفع ملف PDF"])
        
        book_ready = False
        
        if input_method == "رابط مباشر (URL)":
            default_url = MINISTRY_BOOKS[stage][grade][subject]
            # إذا كان الرابط مثال، نتركه فارغاً ليقوم المعلم بوضعه
            val = "" if "example" in default_url else default_url
            book_url = st.text_input("رابط كتاب الوزارة (PDF)", value=val)
            
            if st.button("📥 تحميل وربط المنهج"):
                if book_url:
                    with st.status("جاري تحميل الكتاب وقراءته سحابياً..."):
                        local_path = load_book_from_url(book_url, f"{subject}_{grade}.pdf")
                        if local_path and configure_genai():
                            gemini_file = upload_to_gemini(local_path)
                            if gemini_file:
                                st.session_state.chat_session = get_model(gemini_file)
                                st.session_state.current_book = f"{subject} - {grade}"
                                st.session_state.messages = []
                                book_ready = True
                                st.success("تم قراءة الكتاب بالكامل (150+ صفحة) بنجاح!")
                else:
                    st.error("يرجى إدخال الرابط")
                    
        else: # رفع ملف
            uploaded_file = st.file_uploader("ارفع كتاب المدرسة (PDF)", type=['pdf'])
            if uploaded_file and st.button("🚀 معالجة الكتاب"):
                with st.status("جاري إرسال الكتاب للمعالجة السحابية..."):
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                        tmp.write(uploaded_file.getvalue())
                        local_path = tmp.name
                    
                    if configure_genai():
                        gemini_file = upload_to_gemini(local_path)
                        if gemini_file:
                            st.session_state.chat_session = get_model(gemini_file)
                            st.session_state.current_book = uploaded_file.name
                            st.session_state.messages = []
                            book_ready = True
                            st.success("تم استيعاب الكتاب بنجاح!")

        st.divider()
        if st.session_state.current_book:
            st.info(f"📘 المنهج الحالي: {st.session_state.current_book}")
            if st.button("مسح المحادثة"):
                st.session_state.messages = []
                st.rerun()

    # --- المنطقة الرئيسية ---
    st.markdown(f"""
    <div class="header-box">
        <h1>المنصة التعليمية الذكية</h1>
        <p>اشرح، قيّم، وصحح الواجبات من كتاب الوزارة مباشرة</p>
    </div>
    """, unsafe_allow_html=True)

    if not st.session_state.chat_session:
        st.warning("👈 يرجى اختيار المنهج وتحميل الكتاب من القائمة الجانبية للبدء.")
        return

    # التبويبات الوظيفية
    tabs = st.tabs(["💬 الشات والشرح", "📝 إنشاء اختبار", "✅ تصحيح الواجب"])

    # 1. تبويب الشات
    with tabs[0]:
        for msg in st.session_state.messages:
            role = "user" if msg["role"] == "user" else "assistant"
            with st.chat_message(role):
                st.write(msg["content"])

        # إدخال صوتي أو كتابي
        c1, c2 = st.columns([1, 8])
        with c1:
            audio = mic_recorder(start_prompt="🎙️", stop_prompt="🛑", key="mic")
        with c2:
            prompt = st.chat_input("اسأل عن أي درس في الكتاب...")

        input_text = None
        if prompt: input_text = prompt
        elif audio:
            # تحويل الصوت لنص (بسيط)
            r = sr.Recognizer()
            try:
                with sr.AudioFile(BytesIO(audio['bytes'])) as source:
                    input_text = r.recognize_google(r.record(source), language="ar-EG")
            except: pass

        if input_text:
            st.session_state.messages.append({"role": "user", "content": input_text})
            with st.chat_message("user"): st.write(input_text)
            
            with st.chat_message("assistant"):
                with st.spinner("جاري البحث في صفحات الكتاب..."):
                    try:
                        response = st.session_state.chat_session.send_message(input_text)
                        st.write(response.text)
                        st.session_state.messages.append({"role": "model", "content": response.text})
                        
                        # قراءة صوتية للإجابة
                        if st.checkbox("قراءة الإجابة", value=True, key="tts"):
                            async def play_tts():
                                v = edge_tts.Communicate(response.text, "ar-EG-ShakirNeural")
                                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                                    await v.save(f.name)
                                    st.audio(f.name)
                            asyncio.run(play_tts())
                    except Exception as e:
                        st.error(f"حدث خطأ: {e}")

    # 2. تبويب الاختبارات
    with tabs[1]:
        st.subheader("توليد اختبار من الكتاب")
        topic = st.text_input("موضوع الاختبار (مثلاً: الوحدة الأولى)")
        q_count = st.slider("عدد الأسئلة", 1, 10, 5)
        difficulty = st.select_slider("المستوى", ["سهل", "متوسط", "صعب"])
        
        if st.button("إنشاء الاختبار"):
            if topic:
                prompt = f"قم بإنشاء اختبار مكون من {q_count} أسئلة عن '{topic}' من الكتاب بمستوى {difficulty}. اجعل الأسئلة متنوعة (اختيار من متعدد، صح وخطأ). لا تجب عليها، فقط اعرض الأسئلة."
                with st.spinner("المعلم يكتب الاختبار..."):
                    resp = st.session_state.chat_session.send_message(prompt)
                    st.markdown(resp.text)
            else:
                st.error("حدد الموضوع أولاً")

    # 3. تبويب التصحيح
    with tabs[2]:
        st.subheader("تصحيح إجابة الطالب")
        question = st.text_input("السؤال")
        student_ans = st.text_area("إجابة الطالب")
        
        if st.button("قيّم الإجابة"):
            if question and student_ans:
                prompt = f"""
                السؤال: {question}
                إجابة الطالب: {student_ans}
                
                بناءً على المعلومات الموجودة في الكتاب:
                1. هل الإجابة صحيحة؟
                2. أعط درجة من 10.
                3. إذا كانت خاطئة، ما هي الإجابة النموذجية من الكتاب؟
                """
                with st.spinner("جاري التصحيح..."):
                    resp = st.session_state.chat_session.send_message(prompt)
                    st.success("النتيجة:")
                    st.write(resp.text)

if __name__ == "__main__":
    main()
