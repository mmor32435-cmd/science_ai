import streamlit as st
import time
import google.generativeai as genai
from openai import OpenAI
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder
from io import BytesIO

# ===== 1. إعداد الصفحة =====
st.set_page_config(page_title="المعلم البشري", page_icon="🗣️", layout="centered")

# --- إعداد مفاتيح API (يجب التأكد من وجودها) ---
try:
    # 1. مفتاح جوجل (للتفكير والإجابة)
    if "GOOGLE_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    else:
        st.error("مفتاح GOOGLE_API_KEY مفقود في الـ Secrets")
        st.stop()

    # 2. مفتاح OpenAI (للصوت البشري)
    if "OPENAI_API_KEY" in st.secrets:
        openai_client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    else:
        st.error("مفتاح OPENAI_API_KEY مفقود في الـ Secrets. لا يمكن تشغيل الصوت البشري بدونه.")
        st.stop()

except Exception as e:
    st.error(f"خطأ في الإعدادات: {e}")
    st.stop()

# --- دالة نطق الإجابة باستخدام OpenAI (جودة بشرية) ---
def generate_human_audio(text, output_file, voice_name):
    try:
        response = openai_client.audio.speech.create(
            model="tts-1",       # الموديل السريع والواقعي
            voice=voice_name,    # الصوت المختار
            input=text
        )
        response.stream_to_file(output_file)
        return True
    except Exception as e:
        st.error(f"حدث خطأ أثناء توليد الصوت: {e}")
        return False

# --- دالة تحويل الصوت لنص ---
def speech_to_text(audio_bytes):
    r = sr.Recognizer()
    try:
        audio_file = sr.AudioFile(BytesIO(audio_bytes))
        with audio_file as source:
            r.adjust_for_ambient_noise(source)
            audio_data = r.record(source)
            # التعرف على اللهجة المصرية
            text = r.recognize_google(audio_data, language="ar-EG")
            return text
    except sr.UnknownValueError:
        return None
    except Exception as e:
        return None

# --- إعداد موديل جوجل ---
try:
    all_models = genai.list_models()
    my_models = [m.name for m in all_models if 'generateContent' in m.supported_generation_methods]
    
    # اختيار أفضل موديل متاح تلقائياً
    active_model_name = next((m for m in my_models if 'flash' in m), None)
    if not active_model_name:
        active_model_name = next((m for m in my_models if 'pro' in m), my_models[0])
        
    model = genai.GenerativeModel(active_model_name)
except:
    st.error("فشل الاتصال بموديلات جوجل."); st.stop()

# ===== 2. الواجهة =====
st.title("🎙️ المعلم الصوتي (جودة بشرية)")
st.caption("✅ التفكير: Google Gemini | ✅ الصوت: OpenAI TTS")

# --- خيارات الأصوات الاحترافية من OpenAI ---
st.subheader("🔊 اختر نبرة الصوت")
voice_options = {
    "👨‍🏫 صوت رجالي عميق ورزين (Onyx)": "onyx",
    "👨‍💼 صوت رجالي متوازن (Echo)": "echo",
    "👩‍🏫 صوت نسائي حيوي (Shimmer)": "shimmer",
    "👩‍💼 صوت نسائي هادئ (Nova)": "nova"
}
selected_voice_label = st.selectbox("المعلق الصوتي:", list(voice_options.keys()))
selected_voice_code = voice_options[selected_voice_label]

# ===== 3. الدخول =====
if "logged_in" not in st.session_state:
    password = st.text_input("🔑 الرقم السري", type="password")
    if password == "SCIENCE60":
        st.session_state.logged_in = True
        st.rerun()
    elif password: st.warning("خطأ في الرقم السري")
    st.stop()

# ===== 4. المحادثة =====
st.markdown("---")
st.write("اضغط وتحدث، وسأجيبك بصوت بشري طبيعي:")

audio_input = mic_recorder(
    start_prompt="🎤 تحدث الآن",
    stop_prompt="⏹️ إرسال",
    key='recorder',
    format="wav"
)

if audio_input:
    with st.spinner("👂 أستمع إليك..."):
        user_text = speech_to_text(audio_input['bytes'])
    
    if user_text:
        st.success(f"🗣️ سؤالك: {user_text}")
        with st.spinner("🧠 وصوت بشري يتم تحضيره..."):
            try:
                # هندسة النص للهجة المصرية
                prompt = f"""
                أنت معلم مصري مخضرم.
                السؤال: '{user_text}'
                
                التعليمات:
                1. أجب باللهجة المصرية العامية "المحترمة" (لغة المثقفين).
                2. تجنب الرموز تماماً (* أو -).
                3. استخدم علامات الترقيم (، .) بكثرة لأن الصوت البشري يحتاج للتنفس.
                4. اجعل الإجابة مركزة وقصيرة.
                """
                
                # 1. توليد النص من جوجل
                gemini_response = model.generate_content(prompt)
                answer_text = gemini_response.text
                
                st.markdown(f"### 📘 الرد:\n{answer_text}")
                
                # 2. توليد الصوت من OpenAI
                output_file = "human_response.mp3"
                success = generate_human_audio(answer_text, output_file, selected_voice_code)
                
                if success:
                    st.audio(output_file, format='audio/mp3', autoplay=True)
                
            except Exception as e:
                st.error(f"حدث خطأ: {e}")
    else:
        st.warning("⚠️ الصوت غير واضح، حاول مرة أخرى.")
