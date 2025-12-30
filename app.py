import streamlit as st
import time
import google.generativeai as genai
import asyncio
import edge_tts
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder
from io import BytesIO

# ===== 1. إعداد الصفحة =====
st.set_page_config(page_title="المعلم الصوتي", page_icon="🎙️", layout="centered")

# --- دالة نطق الإجابة ---
async def generate_speech(text, output_file):
    communicate = edge_tts.Communicate(text, "ar-EG-ShakirNeural")
    await communicate.save(output_file)

# --- دالة تحويل الصوت لنص ---
def speech_to_text(audio_bytes):
    r = sr.Recognizer()
    try:
        audio_file = sr.AudioFile(BytesIO(audio_bytes))
        with audio_file as source:
            r.adjust_for_ambient_noise(source)
            audio_data = r.record(source)
            # التعرف على الكلام (عربي)
            text = r.recognize_google(audio_data, language="ar-EG")
            return text
    except:
        return None

# --- الاتصال الذكي واختيار الموديل من القائمة ---
active_model_name = "غير متصل"
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
    
    # 1. نطلب من جوجل القائمة الكاملة للموديلات
    all_models = genai.list_models()
    
    # 2. نفلتر القائمة لنأخذ فقط الموديلات التي تولد نصوصاً
    my_models = []
    for m in all_models:
        if 'generateContent' in m.supported_generation_methods:
            my_models.append(m.name)
    
    if len(my_models) == 0:
        st.error("❌ حسابك لا يحتوي على أي موديلات متاحة حالياً.")
        st.stop()
        
    # 3. نختار أحدث موديل متاح تلقائياً
    # نحاول البحث عن موديلات flash أو pro أولاً
    preferred_model = None
    for m in my_models:
        if 'flash' in m:
            preferred_model = m
            break
    if not preferred_model:
        for m in my_models:
            if 'pro' in m:
                preferred_model = m
                break
    
    # إذا لم نجد المفضلين، نأخذ أول واحد في القائمة وخلاص
    if not preferred_model:
        preferred_model = my_models[0]
        
    active_model_name = preferred_model
    model = genai.GenerativeModel(active_model_name)
    
except Exception as e:
    st.error(f"⚠️ خطأ في الاتصال: {e}")
    st.stop()

# ===== 2. الواجهة =====
st.title("🎙️ المعلم الذكي (محادثة)")
# نعرض اسم الموديل الذي تم اختياره بنجاح
st.caption(f"✅ تم العثور على الموديل وتشغيله: `{active_model_name}`")

# ===== 3. الدخول =====
if "logged_in" not in st.session_state:
    password = st.text_input("🔑 كلمة المرور", type="password")
    if password == "SCIENCE60":
        st.session_state.logged_in = True
        st.rerun()
    elif password: st.warning("خطأ")
    st.stop()

# ===== 4. العداد =====
if "start_time" not in st.session_state: st.session_state.start_time = time.time()
remaining = 3600 - (time.time() - st.session_state.start_time)
if remaining <= 0: st.error("انتهى الوقت"); st.stop()
st.info(f"⏳ الوقت: {int(remaining//60)} دقيقة")

# ===== 5. المحادثة =====
st.markdown("---")
st.subheader("تحدث الآن 👇")

audio_input = mic_recorder(
    start_prompt="🎤 اضغط للتحدث",
    stop_prompt="⏹️ اضغط للإنهاء",
    key='recorder',
    format="wav"
)

if audio_input:
    with st.spinner("👂 أسمعك..."):
        user_text = speech_to_text(audio_input['bytes'])
    
    if user_text:
        st.success(f"🗣️: {user_text}")
        with st.spinner("🧠 أفكر..."):
            try:
                # تعليمات المدرس
                prompt = f"أنت معلم علوم مرح. أجب باختصار وبالعامية المصرية البسيطة على: {user_text}"
                response = model.generate_content(prompt)
                
                st.markdown(f"### 📘: {response.text}")
                
                asyncio.run(generate_speech(response.text, "audio.mp3"))
                st.audio("audio.mp3", format='audio/mp3', autoplay=True)
            except Exception as e:
                st.error(f"خطأ: {e}")
    else:
        st.warning("⚠️ الصوت غير واضح")

st.markdown("---")
