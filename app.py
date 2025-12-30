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
st.set_page_config(page_title="المعلم المصري", page_icon="🇪🇬", layout="centered")

# --- دالة تنظيف ذكية (تبقي على الفواصل للنفس) ---
def prepare_text_for_audio(text):
    # نزيل النجوم والرموز التي لا تُنطق
    text = text.replace("*", "")
    text = text.replace("#", "")
    text = text.replace("- ", "")
    text = text.replace('"', "")
    # نُبقي على الفواصل والنقاط لأنها مهمة جداً للتنفس في الكلام
    return text

# --- دالة نطق الإجابة (ضبط دقيق للسرعة) ---
async def generate_speech(text, output_file, voice_code):
    clean_text = prepare_text_for_audio(text)
    # rate="-5%" : تبطيء طفيف جداً يعطي رزانة دون ملل
    communicate = edge_tts.Communicate(clean_text, voice_code, rate="-5%")
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
st.title("🇪🇬 المعلم المصري (دروس خصوصية)")
st.caption("يعمل بلهجة الدروس الخصوصية المصرية")

# --- خيارات الصوت ---
st.subheader("🔊 اختر المدرس")
voice_options = {
    "👨‍🏫 مستر شاكر (أداء درامي)": "ar-EG-ShakirNeural",
    "👩‍🏫 مس سلمى (أداء هادئ)": "ar-EG-SalmaNeural"
}
selected_voice_name = st.selectbox("مين هيشرحلك؟", list(voice_options.keys()))
selected_voice_code = voice_options[selected_voice_name]

# ===== 3. الدخول =====
if "logged_in" not in st.session_state:
    password = st.text_input("🔑 الرقم السري", type="password")
    if password == "SCIENCE60":
        st.session_state.logged_in = True
        st.rerun()
    elif password: st.warning("الباسورد غلط")
    st.stop()

# ===== 4. العداد =====
if "start_time" not in st.session_state: st.session_state.start_time = time.time()
remaining = 3600 - (time.time() - st.session_state.start_time)
if remaining <= 0: st.error("الحصة خلصت!"); st.stop()
st.info(f"⏳ باقي: {int(remaining//60)} دقيقة")

# ===== 5. المحادثة =====
st.markdown("---")
st.subheader("ابدأ الدردشة 👇")

audio_input = mic_recorder(
    start_prompt="🎤 دوس هنا واسأل",
    stop_prompt="⏹️ ابعت السؤال",
    key='recorder',
    format="wav"
)

if audio_input:
    with st.spinner("👂 بسمعك..."):
        user_text = speech_to_text(audio_input['bytes'])
    
    if user_text:
        st.success(f"🗣️ أنت: {user_text}")
        with st.spinner("🧠 بجهّز الرد..."):
            try:
                role = "مُدرسة علوم شاطرة" if "سلمى" in selected_voice_name else "مُدرس علوم شاطر"
                
                # --- سر الخلطة المصرية (البرومبت الهندسي) ---
                prompt = f"""
                أنت {role} بتدي دروس خصوصية لطلاب في مصر.
                الطالب سألك: '{user_text}'
                
                مهمتك: اشرح الإجابة كأنك بتتكلم صوتي مش بتكتب.
                
                قواعد صارمة جداً للهجة:
                1. استخدم "الفواصل" (،) كتير جداً بين الجمل، عشان القارئ ياخد نفسه ويبقى الصوت طبيعي.
                2. شكّل الكلمات العامية عشان تتنطق صح. اكتب: (كِدَه، دَه، طَبْعاً، بَس، عَشَان، دِلْوَقْتِي).
                3. استخدم "هـ" المستقبلية (هنشوف، هنعمل) بدل "سوف".
                4. استخدم كلمات ربط مصرية زي: (بص يا سيدي، خد بالك، تخيل معايا، المهم).
                5. بلاش تستخدم "حيث أن" أو "لأن"، استخدم "عَشَان".
                6. ممنوع استخدام القوائم المرقمة (1. 2.) أو النجوم (*). اتكلم في فقرة متصلة ومريحة.
                7. خلي الإجابة قصيرة ومفيدة وممتعة.
                
                مثال للطريقة اللي عايزك تكتب بيها:
                "بص يا بطل،، السؤال ده ذكي جداً.، الإجابة ببساطة هي كَذَا وكَذَا.. وعَشَان تفهمها أكتر،، تخيل لو معانا كورة..."
                """
                
                response = model.generate_content(prompt)
                
                st.markdown(f"### 📘 الرد:\n{response.text}")
                
                output_file = "response.mp3"
                asyncio.run(generate_speech(response.text, output_file, selected_voice_code))
                st.audio(output_file, format='audio/mp3', autoplay=True)
                
            except Exception as e:
                st.error(f"مشكلة تقنية: {e}")
    else:
        st.warning("⚠️ الصوت مش واصل، علي صوتك شوية.")

st.markdown("---")
