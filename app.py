import streamlit as st
import time
import google.generativeai as genai
import asyncio
import edge_tts
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder
from io import BytesIO
import re
from datetime import datetime
import pytz # مكتبة المناطق الزمنية

# ==========================================
# 🎛️ لوحة تحكم المعلم (عدل هنا يومياً)
# ==========================================

# 1. كود الدخول لهذا اليوم
DAILY_PASSWORD = "SCIENCE_DAY1" 

# 2. تاريخ الامتحان (السنة-الشهر-اليوم)
EXAM_DATE = "2024-05-20" 

# 3. وقت البداية والنهاية (بناظم 24 ساعة)
# مثال: من 1 ظهرًا (13) إلى 2 ظهرًا (14)
START_HOUR = 13 
END_HOUR = 14   

# 4. توقيتك المحلي (مهم جداً لضبط الساعة)
# لمصر: 'Africa/Cairo' | للسعودية: 'Asia/Riyadh'
MY_TIMEZONE = 'Africa/Cairo' 

# ==========================================

st.set_page_config(page_title="الاختبار المحدد بوقت", page_icon="⏳", layout="centered")

# --- دالة التحقق من الوقت (الحارس الذكي) ---
def check_time_window():
    # الحصول على الوقت الحالي بتوقيت بلدك
    tz = pytz.timezone(MY_TIMEZONE)
    now = datetime.now(tz)
    
    current_date = now.strftime("%Y-%m-%d")
    current_hour = now.hour
    current_minute = now.minute
    
    # 1. التحقق من اليوم
    if current_date != EXAM_DATE:
        return False, f"⛔ الامتحان ليس اليوم. تاريخ الامتحان المقرر: {EXAM_DATE}"
    
    # 2. التحقق من الساعة (قبل الموعد)
    if current_hour < START_HOUR:
        return False, f"⏳ لم يبدأ الامتحان بعد. يبدأ الساعة {START_HOUR}:00 بتوقيت {MY_TIMEZONE}"
    
    # 3. التحقق من الساعة (بعد الموعد)
    # المسموح: أن تكون الساعة أكبر من أو تساوي البداية، وأقل تماماً من النهاية
    # مثال: من 13:00 حتى 13:59 (بمجرد أن تأتي 14:00 يغلق)
    if current_hour >= END_HOUR:
        return False, "🛑 انتهى وقت الامتحان! تم إغلاق النظام تلقائياً."
        
    # حساب الدقائق المتبقية للإغلاق
    # وقت النهاية هو END_HOUR:00
    # الدقائق المتبقية = (ساعة النهاية * 60) - (الساعة الحالية * 60 + الدقائق الحالية)
    end_minutes = END_HOUR * 60
    current_total_minutes = current_hour * 60 + current_minute
    remaining = end_minutes - current_total_minutes
    
    return True, remaining

# ==========================================
# تنفيذ التحقق (قبل تشغيل أي كود آخر)
is_open, message = check_time_window()

if not is_open:
    st.error(message)
    st.image("https://cdn-icons-png.flaticon.com/512/483/483696.png", width=150)
    st.stop() # يقتل التطبيق هنا، لن يظهر أي شيء بالأسفل
# ==========================================


# --- باقي كود التطبيق (لا يعمل إلا إذا كان الوقت صحيحاً) ---

# ... دوال الصوت والذكاء الاصطناعي المعتادة ...
def prepare_text(text):
    text = re.sub(r'[\*\#\-\_]', '', text)
    return text

async def generate_speech(text, output_file, voice_code):
    clean_text = prepare_text(text)
    communicate = edge_tts.Communicate(clean_text, voice_code, rate="-5%")
    await communicate.save(output_file)

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

try:
    if "GOOGLE_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    else:
        st.error("مفتاح جوجل مفقود"); st.stop()
    
    all_models = genai.list_models()
    my_models = [m.name for m in all_models if 'generateContent' in m.supported_generation_methods]
    active_model = next((m for m in my_models if 'flash' in m), my_models[0])
    model = genai.GenerativeModel(active_model)
except:
    st.error("خطأ تقني"); st.stop()


# ===== واجهة تسجيل الدخول اليومية =====
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔐 امتحان العلوم اليومي")
    st.caption(f"متاح اليوم فقط من {START_HOUR}:00 إلى {END_HOUR}:00")
    
    password = st.text_input("أدخل كود اليوم:", type="password")
    if st.button("دخول"):
        if password == DAILY_PASSWORD:
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("الكود غير صحيح لهذا اليوم.")
    st.stop()

# ===== واجهة الامتحان (بعد الدخول) =====

# عرض العداد المتبقي للإغلاق العام
is_still_open, remaining_mins = check_time_window()
if not is_still_open:
    st.session_state.logged_in = False
    st.rerun()

st.sidebar.title(f"⏳ باقي: {remaining_mins} دقيقة")
st.sidebar.warning(f"سيغلق النظام تماماً الساعة {END_HOUR}:00")

st.title("🎙️ المعلم الذكي (اختبار)")

# خيارات الصوت
voice_options = {
    "🇪🇬 مستر شاكر": "ar-EG-ShakirNeural",
    "🇪🇬 مس سلمى": "ar-EG-SalmaNeural"
}
selected_voice_code = voice_options["🇪🇬 مستر شاكر"] 

st.markdown("---")
st.write("اضغط وتحدث:")

audio_input = mic_recorder(
    start_prompt="🎤 تحدث",
    stop_prompt="⏹️ إرسال",
    key='recorder',
    format="wav"
)

if audio_input:
    with st.spinner("👂 ..."):
        user_text = speech_to_text(audio_input['bytes'])
    
    if user_text:
        st.success(f"🗣️: {user_text}")
        with st.spinner("🧠 ..."):
            try:
                prompt = f"""
                أنت معلم مصري. الطالب يسألك أو يجيبك: '{user_text}'.
                رد عليه باللهجة المصرية وبإيجاز شديد.
                """
                response = model.generate_content(prompt)
                st.markdown(f"### 📘 الرد:\n{response.text}")
                
                output_file = "response.mp3"
                asyncio.run(generate_speech(response.text, output_file, selected_voice_code))
                st.audio(output_file, format='audio/mp3', autoplay=True)
                
            except Exception as e:
                st.error(f"خطأ: {e}")
