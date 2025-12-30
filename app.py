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
st.set_page_config(page_title="اختبار العلوم التفاعلي", page_icon="⏱️", layout="wide")

# --- قائمة كلمات المرور المسموحة (يمكنك التعديل عليها) ---
# كل طالب تعطيه كلمة سر مختلفة
VALID_PASSWORDS = [
    "STUDENT_1", "STUDENT_2", "STUDENT_3", "SCIENCE2024", "CLASS_A"
]

# مدة الجلسة بالدقائق
SESSION_DURATION_MINUTES = 60 

# --- دوال الصوت والذكاء الاصطناعي (كما هي) ---
def prepare_text(text):
    text = re.sub(r'[\*\#\-\_]', '', text)
    return text

async def generate_speech(text, output_file, voice_code):
    clean_text = prepare_text(text)
    communicate = edge_tts.Communicate(clean_text, voice_code, rate="+0%")
    await communicate.save(output_file)

def speech_to_text(audio_bytes):
    r = sr.Recognizer()
    try:
        audio_file = sr.AudioFile(BytesIO(audio_bytes))
        with audio_file as source:
            r.adjust_for_ambient_noise(source)
            audio_data = r.record(source)
            text = r.recognize_google(audio_data, language="ar-SA")
            return text
    except:
        return None

# --- الاتصال بجوجل ---
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

# ==========================================
# ===== 2. نظام تسجيل الدخول وإدارة الوقت =====
# ==========================================

# التحقق من حالة تسجيل الدخول
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔐 بوابة الدخول للاختبار")
    st.markdown("---")
    password_input = st.text_input("أدخل كود الطالب الخاص بك:", type="password")
    
    if st.button("دخول وبدء الوقت"):
        if password_input in VALID_PASSWORDS:
            st.session_state.logged_in = True
            st.session_state.student_id = password_input
            # تسجيل وقت البداية
            st.session_state.start_time = time.time()
            st.rerun()
        else:
            st.error("⛔ كود الطالب غير صحيح. يرجى مراجعة المعلم.")
    st.stop() # يوقف الكود هنا إذا لم يسجل الدخول

# ==========================================
# ===== 3. حساب الوقت المتبقي (العداد) =====
# ==========================================

elapsed_time = time.time() - st.session_state.start_time
total_seconds = SESSION_DURATION_MINUTES * 60
remaining_seconds = total_seconds - elapsed_time

# إذا انتهى الوقت
if remaining_seconds <= 0:
    st.error("🛑 انتهى وقت الجلسة!")
    st.warning("لقد استنفذت الـ 60 دقيقة المخصصة لك. يرجى مراجعة المعلم للحصول على كود جديد.")
    # زر للخروج
    if st.button("خروج"):
        st.session_state.logged_in = False
        st.rerun()
    st.stop() # يوقف التطبيق تماماً

# ==========================================
# ===== 4. واجهة التطبيق والعداد الجانبي =====
# ==========================================

# القائمة الجانبية للعداد
with st.sidebar:
    st.title(f"👤 الطالب: {st.session_state.student_id}")
    st.markdown("---")
    
    # حساب الدقائق والثواني
    mins = int(remaining_seconds // 60)
    secs = int(remaining_seconds % 60)
    
    # لون العداد (يتغير للأحمر إذا بقي أقل من 5 دقائق)
    timer_color = "green" if mins > 5 else "red"
    st.markdown(f"<h1 style='text-align: center; color: {timer_color};'>{mins}:{secs:02d}</h1>", unsafe_allow_html=True)
    st.caption("الوقـت المتبقـي")
    
    # شريط التقدم
    progress_value = max(0.0, min(1.0, remaining_seconds / total_seconds))
    st.progress(progress_value)
    
    st.warning("⚠️ لا تقم بتحديث الصفحة (Refresh) وإلا سيعاد تشغيل العداد من البداية.")

# الواجهة الرئيسية
st.title("🎙️ اختبار العلوم الشفوي")
st.caption("تحدث مع المعلم الذكي للإجابة عن الأسئلة")

# --- خيارات الصوت (المجانية عالية الجودة) ---
voice_options = {
    "🇸🇦 المعلم حامد (رزين)": "ar-SA-HamedNeural",
    "🇸🇦 المعلمة زارية (واضحة)": "ar-SA-ZariyahNeural"
}
# نختار صوتاً افتراضياً أو نترك للطالب حرية الاختيار
selected_voice_code = voice_options["🇸🇦 المعلم حامد (رزين)"] 

# ===== 5. المحادثة =====
st.markdown("---")
col1, col2 = st.columns([1, 4])
with col1:
    st.image("https://cdn-icons-png.flaticon.com/512/377/377295.png", width=100)
with col2:
    st.info("اضغط على الزر، انتظر ثانية، ثم أجب عن السؤال أو استفسر.")

audio_input = mic_recorder(
    start_prompt="🎤 اضغط للتحدث",
    stop_prompt="⏹️ إنهاء الإجابة",
    key='recorder',
    format="wav"
)

if audio_input:
    with st.spinner("👂 المعلم يستمع إليك..."):
        user_text = speech_to_text(audio_input['bytes'])
    
    if user_text:
        st.success(f"🗣️ إجابتك/سؤالك: {user_text}")
        with st.spinner("🧠 المعلم يقيّم ويجيب..."):
            try:
                # التعليمات للموديل
                prompt = f"""
                أنت معلم علوم تجري اختباراً شفوياً لطالب.
                الطالب قال: '{user_text}'
                
                1. إذا كان كلام الطالب سؤالاً: أجب عليه بالفصحى المبسطة.
                2. إذا كان إجابة على سؤال منك: قيّم إجابته (ممتاز، جيد، أو صحح له الخطأ) بأسلوب مشجع.
                3. تكلم بأسلوب "المعلم حامد" الرزين والمحترم.
                4. اجعل ردك مختصراً (لا يزيد عن 3 جمل).
                """
                
                response = model.generate_content(prompt)
                st.markdown(f"### 📘 رد المعلم:\n{response.text}")
                
                output_file = "response.mp3"
                asyncio.run(generate_speech(response.text, output_file, selected_voice_code))
                st.audio(output_file, format='audio/mp3', autoplay=True)
                
            except Exception as e:
                st.error(f"خطأ: {e}")
    else:
        st.warning("⚠️ الصوت غير واضح، حاول مرة أخرى.")

st.markdown("---")
