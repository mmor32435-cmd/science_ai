import streamlit as st
import time
import google.generativeai as genai
import asyncio
import edge_tts
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder
from io import BytesIO
import re # مكتبة للتعامل مع النصوص وتنظيفها

# ===== 1. إعداد الصفحة =====
st.set_page_config(page_title="المعلم الصوتي", page_icon="🎙️", layout="centered")

# --- دالة تنظيف النص من الرموز قبل النطق ---
def clean_text_for_audio(text):
    # إزالة النجوم (*) المستخدمة للخط العريض
    text = text.replace("*", "")
    # إزالة علامات الشباك (#) المستخدمة للعناوين
    text = text.replace("#", "")
    # إزالة الشرطات (-) في بداية السطور
    text = text.replace("- ", "")
    # إزالة علامات التنصيص
    text = text.replace('"', "").replace("'", "")
    # إزالة الأقواس المربعة والروابط [ ]
    text = re.sub(r'\[.*?\]', '', text)
    # إزالة الرموز الغريبة المتكررة
    text = re.sub(r'[_\-><]', '', text)
    return text

# --- دالة نطق الإجابة ---
async def generate_speech(text, output_file, voice_code):
    # ننظف النص أولاً قبل إرساله للقارئ الصوتي
    clean_text = clean_text_for_audio(text)
    communicate = edge_tts.Communicate(clean_text, voice_code)
    await communicate.save(output_file)

# --- دالة تحويل الصوت لنص ---
def speech_to_text(audio_bytes):
    r = sr.Recognizer()
    try:
        audio_file = sr.AudioFile(BytesIO(audio_bytes))
        with audio_file as source:
            r.adjust_for_ambient_noise(source)
            audio_data = r.record(source)
            text = r.recognize_google(audio_data, language="ar-EG")
            return text
    except:
        return None

# --- الاتصال الذكي واختيار الموديل ---
active_model_name = "غير متصل"
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
    
    all_models = genai.list_models()
    my_models = [m.name for m in all_models if 'generateContent' in m.supported_generation_methods]
    
    if not my_models:
        st.error("❌ لا توجد موديلات متاحة."); st.stop()
        
    preferred_model = next((m for m in my_models if 'flash' in m), None)
    if not preferred_model:
        preferred_model = next((m for m in my_models if 'pro' in m), my_models[0])
        
    active_model_name = preferred_model
    model = genai.GenerativeModel(active_model_name)
    
except Exception as e:
    st.error(f"⚠️ خطأ: {e}"); st.stop()

# ===== 2. الواجهة واختيار الصوت =====
st.title("🎙️ المعلم الذكي المحاور")
st.caption(f"✅ الموديل: `{active_model_name}`")

st.subheader("🔊 إعدادات الصوت")
voice_options = {
    "🇪🇬 مصر - سلمى (أنثى)": "ar-EG-SalmaNeural",
    "🇪🇬 مصر - شاكر (ذكر)": "ar-EG-ShakirNeural",
    "🇸🇦 السعودية - زارية (أنثى)": "ar-SA-ZariyahNeural",
    "🇸🇦 السعودية - حامد (ذكر)": "ar-SA-HamedNeural"
}
selected_voice_name = st.selectbox("اختر شخصية المعلم:", list(voice_options.keys()))
selected_voice_code = voice_options[selected_voice_name]

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
st.subheader("ابدأ الحوار 👇")

audio_input = mic_recorder(
    start_prompt="🎤 اضغط وتحدث",
    stop_prompt="⏹️ إرسال",
    key='recorder',
    format="wav"
)

if audio_input:
    with st.spinner("👂 أستمع إليك..."):
        user_text = speech_to_text(audio_input['bytes'])
    
    if user_text:
        st.success(f"🗣️ أنت: {user_text}")
        with st.spinner("🧠 أفكر..."):
            try:
                role = "معلمة" if "أنثى" in selected_voice_name else "معلم"
                
                # --- التعديل هنا لضبط الأسلوب ---
                prompt = f"""
                أنت {role} علوم لبق جداً ومحاور بارع لطلاب الثانوية.
                الطالب سألك: '{user_text}'
                
                تعليمات الرد الصارمة:
                1. تحدث بأسلوب قصصي حواري ممتع (Storytelling) وليس كسرد نقاط جامدة.
                2. استخدم العامية المصرية الراقية والمبسطة.
                3. تجنب تماماً استخدام الرموز مثل النجمة (*) أو الشباك (#) أو القوائم الرقمية داخل النص، لأنك تتحدث صوتياً.
                4. اجعل الجمل قصيرة ومترابطة لتكون سهلة الفهم عند سماعها.
                5. كن ودوداً جداً ونادِ الطالب بـ (يا بطل / يا دكتورة).
                """
                
                response = model.generate_content(prompt)
                
                # عرض النص (يمكن أن يحتوي على تنسيق خفيف إذا أضافه الموديل)
                st.markdown(f"### 📘 الرد:\n{response.text}")
                
                # النطق (سيتم تنظيفه تماماً من أي رموز قبل النطق)
                output_file = "response.mp3"
                asyncio.run(generate_speech(response.text, output_file, selected_voice_code))
                st.audio(output_file, format='audio/mp3', autoplay=True)
                
            except Exception as e:
                st.error(f"خطأ: {e}")
    else:
        st.warning("⚠️ الصوت غير واضح")

st.markdown("---")
