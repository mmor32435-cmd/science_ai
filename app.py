import streamlit as st
import time
import google.generativeai as genai
import asyncio
import edge_tts
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder
from io import BytesIO
import re

# ===== 1. إعداد الصفحة =====
st.set_page_config(page_title="المعلم الذكي", page_icon="🎙️", layout="centered")

# --- دالة تنظيف النص ---
def prepare_text(text):
    text = re.sub(r'[\*\#\-\_]', '', text)
    return text

# --- دالة توليد الصوت (أصوات خليجية فخمة) ---
async def generate_speech(text, output_file, voice_code):
    clean_text = prepare_text(text)
    # السرعة طبيعية (0%) لضمان مخارج الحروف
    communicate = edge_tts.Communicate(clean_text, voice_code, rate="+0%")
    await communicate.save(output_file)

# --- دالة تحويل الصوت لنص ---
def speech_to_text(audio_bytes):
    r = sr.Recognizer()
    try:
        audio_file = sr.AudioFile(BytesIO(audio_bytes))
        with audio_file as source:
            r.adjust_for_ambient_noise(source)
            audio_data = r.record(source)
            # نحاول التعرف بلهجة عامة
            text = r.recognize_google(audio_data, language="ar-SA")
            return text
    except:
        return None

# --- إعداد جوجل ---
try:
    if "GOOGLE_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    else:
        st.error("مفتاح جوجل مفقود!"); st.stop()
        
    all_models = genai.list_models()
    my_models = [m.name for m in all_models if 'generateContent' in m.supported_generation_methods]
    active_model = next((m for m in my_models if 'flash' in m), my_models[0])
    model = genai.GenerativeModel(active_model)
except:
    st.error("خطأ في الاتصال بجوجل"); st.stop()

# ===== 2. الواجهة =====
st.title("🎙️ المعلم الذكي")
st.caption("يعمل بأصوات عربية فصيحة عالية الجودة (مجاني)")

# --- خيارات الصوت (أصوات جديدة) ---
st.subheader("🔊 اختر المعلق الصوتي")
voice_options = {
    "🇸🇦 الأستاذ حامد (صوت فخيم ورزين)": "ar-SA-HamedNeural",
    "🇸🇦 الأستاذة زارية (صوت إخباري واضح)": "ar-SA-ZariyahNeural",
    "🇯🇴 الأستاذ تيم (صوت عربي محايد)": "ar-JO-TaimNeural"
}
selected_voice_name = st.selectbox("المتحدث:", list(voice_options.keys()))
selected_voice_code = voice_options[selected_voice_name]

# ===== 3. الدخول =====
if "logged_in" not in st.session_state:
    password = st.text_input("🔑 الرقم السري", type="password")
    if password == "SCIENCE60":
        st.session_state.logged_in = True
        st.rerun()
    elif password: st.warning("خطأ")
    st.stop()

# ===== 4. المحادثة =====
st.markdown("---")
st.write("اضغط وتحدث:")

audio_input = mic_recorder(
    start_prompt="🎤 تحدث الآن",
    stop_prompt="⏹️ إرسال",
    key='recorder',
    format="wav"
)

if audio_input:
    with st.spinner("👂 أسمعك..."):
        user_text = speech_to_text(audio_input['bytes'])
    
    if user_text:
        st.success(f"🗣️: {user_text}")
        with st.spinner("🧠 جاري التحضير..."):
            try:
                # توجيه للتحدث بالفصحى البسيطة لأنها الأنسب لهذه الأصوات
                prompt = f"""
                أنت معلم علوم متميز.
                السؤال: '{user_text}'
                التعليمات:
                1. أجب باللغة العربية الفصحى البسيطة والواضحة (تليق بالصوت الرزين).
                2. اجعل الإجابة قصيرة ومباشرة.
                3. تجنب الرموز والقوائم.
                """
                
                response = model.generate_content(prompt)
                st.markdown(f"### 📘 الرد:\n{response.text}")
                
                output_file = "response.mp3"
                asyncio.run(generate_speech(response.text, output_file, selected_voice_code))
                st.audio(output_file, format='audio/mp3', autoplay=True)
                
            except Exception as e:
                st.error(f"خطأ: {e}")
    else:
        st.warning("⚠️ الصوت غير واضح")
