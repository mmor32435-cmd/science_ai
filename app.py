import streamlit as st
import time
import google.generativeai as genai
import asyncio
import edge_tts
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder
from io import BytesIO
import re

# ===== إعداد الصفحة =====
st.set_page_config(page_title="المعلم المصري", page_icon="🇪🇬", layout="centered")

# ===== تنظيف النص ليصبح كلامًا مسموعًا =====
def prepare_text_for_audio(text):
    # إزالة الرموز غير المنطوقة
    text = re.sub(r"[*#\"\n]", " ", text)

    # تقصير الجمل الطويلة
    text = re.sub(r"\.{2,}", "،", text)

    # إجبار وقفات تنفّس طبيعية
    text = text.replace(".", "، ")
    text = text.replace("،", "، ")

    # إزالة التكرار الزائد
    text = re.sub(r"(،\s*){2,}", "، ", text)

    return text.strip()

# ===== توليد الصوت =====
async def generate_speech(text, output_file, voice_code):
    clean_text = prepare_text_for_audio(text)
    communicate = edge_tts.Communicate(
        clean_text,
        voice_code,
        rate="-10%",
        pitch="+2Hz"
    )
    await communicate.save(output_file)

# ===== العنوان =====
st.title("🎙️ المعلم المصري – شرح علوم بالذكاء الاصطناعي")

# ===== كلمة المرور =====
password = st.text_input("🔐 أدخل كلمة الدخول", type="password")
if password != "SCIENCE60":
    st.warning("كلمة المرور غير صحيحة")
    st.stop()

st.success("تم الدخول بنجاح ✅")

# ===== المؤقت =====
if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()

elapsed = time.time() - st.session_state.start_time
remaining = 3600 - elapsed

if remaining <= 0:
    st.error("⏱️ انتهت مدة الجلسة")
    st.stop()

st.info(f"⏳ الوقت المتبقي: {int(remaining//60)} دقيقة")

# ===== إعداد Gemini =====
genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
model = genai.GenerativeModel("gemini-pro")

# ===== اختيار الصوت =====
voice_options = {
    "مصري – راجل": "ar-EG-ShakirNeural",
    "مصري – ست": "ar-EG-SalmaNeural"
}
selected_voice = st.selectbox("🎧 اختر صوت الشرح", list(voice_options.keys()))
selected_voice_code = voice_options[selected_voice]

# ===== تسجيل السؤال =====
audio = mic_recorder(start_prompt="🎤 اضغط وتكلم", stop_prompt="⏹️ وقف", key="recorder")

if audio:
    recognizer = sr.Recognizer()

    audio_data = sr.AudioData(
        audio["bytes"],
        sample_rate=audio["sample_rate"],
        sample_width=2
    )

    try:
        question = recognizer.recognize_google(audio_data, language="ar-EG")
        st.write(f"🗣️ سؤالك: {question}")

        if st.button("📩 أجب"):
            with st.spinner("🤖 المعلم بيفكّر..."):
                prompt = f"""
اشرح لطالب أولى ثانوي بأسلوب مدرس مصري.
استخدم جمل قصيرة جدًا.
خلي الشرح كأنك بتتكلم مش بتكتب.
خد نفس بين الجمل.
ما تستخدمش فصحى تقيلة.

السؤال:
{question}
"""
                response = model.generate_content(prompt)

                st.markdown(f"### 📘 الشرح:\n{response.text}")

                output_file = "response.mp3"
                asyncio.run(
                    generate_speech(
                        response.text,
                        output_file,
                        selected_voice_code
                    )
                )
                st.audio(output_file, format="audio/mp3", autoplay=True)

    except Exception as e:
        st.warning("⚠️ الصوت مش واضح، جرّب تاني")

