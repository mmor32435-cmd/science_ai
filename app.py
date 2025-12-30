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
st.set_page_config(page_title="المعلم المصري الذكي", page_icon="🇪🇬", layout="centered")

# --- دالة تنظيف وتجهيز النص للصوت ---
def prepare_text_for_audio(text):
    # إزالة الرموز التي تربك القارئ
    text = re.sub(r'[\*\#\-\_]', '', text)
    text = re.sub(r'\[.*?\]', '', text)
    # إزالة التشكيل الزائد إذا كان يسبب مشاكل (اختياري)
    # لكننا سنطلب من الذكاء الاصطناعي وضع تشكيل مفيد
    return text

# --- دالة نطق الإجابة (بتحسينات السرعة) ---
async def generate_speech(text, output_file, voice_code):
    clean_text = prepare_text_for_audio(text)
    # Rate=-10% يجعل الصوت أبطأ قليلاً وأكثر وضوحاً ورزانة
    # Pitch=+0Hz نتركه طبيعياً
    communicate = edge_tts.Communicate(clean_text, voice_code, rate="-10%")
    await communicate.save(output_file)

# --- دالة تحويل الصوت لنص ---
def speech_to_text(audio_bytes):
    r = sr.Recognizer()
    try:
        audio_file = sr.AudioFile(BytesIO(audio_bytes))
        with audio_file as source:
            r.adjust_for_ambient_noise(source)
            audio_data = r.record(source)
            # التعرف على اللهجة المصرية تحديداً
            text = r.recognize_google(audio_data, language="ar-EG")
            return text
    except:
        return None

# --- الاتصال الذكي ---
active_model_name = "غير متصل"
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
    
    all_models = genai.list_models()
    my_models = [m.name for m in all_models if 'generateContent' in m.supported_generation_methods]
    
    if not my_models: st.error("❌ لا توجد موديلات"); st.stop()
        
    preferred_model = next((m for m in my_models if 'flash' in m), None)
    if not preferred_model:
        preferred_model = next((m for m in my_models if 'pro' in m), my_models[0])
        
    active_model_name = preferred_model
    model = genai.GenerativeModel(active_model_name)
    
except Exception as e:
    st.error(f"⚠️ خطأ: {e}"); st.stop()

# ===== 2. الواجهة =====
st.title("🇪🇬 المعلم المصري الذكي")
st.caption("يعمل باللهجة المصرية الطبيعية")

# --- خيارات الصوت المصرية فقط ---
st.subheader("🔊 اختر صوت المدرس")
voice_options = {
    "👨‍🏫 مستر شاكر (صوت رخيم وقوي)": "ar-EG-ShakirNeural",
    "👩‍🏫 مس سلمى (صوت هادئ وواضح)": "ar-EG-SalmaNeural"
}
selected_voice_name = st.selectbox("المدرس:", list(voice_options.keys()))
selected_voice_code = voice_options[selected_voice_name]

# ===== 3. الدخول =====
if "logged_in" not in st.session_state:
    password = st.text_input("🔑 الرقم السري", type="password")
    if password == "SCIENCE60":
        st.session_state.logged_in = True
        st.rerun()
    elif password: st.warning("غلط يا بطل، حاول تاني")
    st.stop()

# ===== 4. العداد =====
if "start_time" not in st.session_state: st.session_state.start_time = time.time()
remaining = 3600 - (time.time() - st.session_state.start_time)
if remaining <= 0: st.error("الوقت خلص!"); st.stop()
st.info(f"⏳ باقي: {int(remaining//60)} دقيقة")

# ===== 5. المحادثة =====
st.markdown("---")
st.subheader("اسأل براحتك 👇")

audio_input = mic_recorder(
    start_prompt="🎤 دوس هنا واتكلم",
    stop_prompt="⏹️ دوس عشان تبعت",
    key='recorder',
    format="wav"
)

if audio_input:
    with st.spinner("👂 بسمعك..."):
        user_text = speech_to_text(audio_input['bytes'])
    
    if user_text:
        st.success(f"🗣️ أنت قلت: {user_text}")
        with st.spinner("🧠 بفكر في الرد..."):
            try:
                role = "مُدرسة" if "سلمى" in selected_voice_name else "مُدرس"
                
                # --- سر الجودة: التوجيه الدقيق للهجة المصرية ---
                prompt = f"""
                تقمص شخصية {role} علوم مصري شاطر جداً ومرح لطلاب أولى ثانوي.
                الطالب سألك: '{user_text}'
                
                تعليمات مهمة جداً عشان الصوت يطلع طبيعي:
                1. اكتب الإجابة **بالعامية المصرية البحتة** (اكتب "ده" بدل "هذا"، "عشان" بدل "لأن"، "كده" بدل "هكذا").
                2. شكّل الكلمات الصعبة فقط عشان النطق يطلع صح (زي: دَه، بَس، طَبْعاً).
                3. خليك لبق جداً ومحاور، وبلاش تسرد معلومات ورا بعض زي الكتاب.
                4. استخدم كلمات تشجيعية مصرية (يا بطل، يا دكتورة، يا وحش، بص يا سيدي).
                5. بلاش تستخدم أي نجوم (*) أو رموز أو ترقيم (1. 2.) في نص الإجابة عشان القارئ الصوتي ما يقرأهاش غلط. اتكلم بجمل ورا بعض.
                6. بسّط المعلومة العلمية بمثال من الحياة في مصر لو أمكن.
                """
                
                response = model.generate_content(prompt)
                
                st.markdown(f"### 📘 الرد:\n{response.text}")
                
                output_file = "response.mp3"
                asyncio.run(generate_speech(response.text, output_file, selected_voice_code))
                st.audio(output_file, format='audio/mp3', autoplay=True)
                
            except Exception as e:
                st.error(f"حصلت مشكلة: {e}")
    else:
        st.warning("⚠️ الصوت مش واضح، قرّب من المايك وقول تاني.")

st.markdown("---")
