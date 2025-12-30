import streamlit as st
import time
import google.generativeai as genai
import asyncio
import edge_tts
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder
from io import BytesIO

# ===== 1. إعداد الصفحة والستايل =====
st.set_page_config(page_title="المعلم الصوتي", page_icon="🎙️", layout="centered")

# --- دالة تحويل النص إلى صوت (المعلم يتحدث) ---
async def generate_speech(text, output_file):
    communicate = edge_tts.Communicate(text, "ar-EG-ShakirNeural")
    await communicate.save(output_file)

# --- دالة تحويل صوت الطالب إلى نص ---
def speech_to_text(audio_bytes):
    r = sr.Recognizer()
    try:
        # تحويل البيانات الخام إلى ملف صوتي في الذاكرة
        audio_file = sr.AudioFile(BytesIO(audio_bytes))
        with audio_file as source:
            audio_data = r.record(source)
            # التعرف على الكلام (اللهجة المصرية/العربية)
            text = r.recognize_google(audio_data, language="ar-EG")
            return text
    except sr.UnknownValueError:
        return None
    except Exception as e:
        return f"Error: {e}"

# --- إعداد اتصال جوجل (الذكي) ---
active_model_name = None
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
    
    available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    if available_models:
        priority = [m for m in available_models if 'flash' in m] + [m for m in available_models if 'pro' in m]
        active_model_name = priority[0] if priority else available_models[0]
        
        # شخصية المعلم
        system_instruction = """
        أنت معلم علوم صوتي اسمه 'مستر شاكر'.
        أسلوبك: صوتي، عفوي، مرح، باللهجة البيضاء المبسطة أو الفصحى السهلة.
        لا تستخدم تنسيقات معقدة (مثل الجداول) لأنك تتحدث صوتياً.
        اجعل إجاباتك قصيرة (فقرة واحدة أو فقرتين) حتى لا يمل الطالب من الاستماع.
        رحب بالطالب عند الحاجة وشجعه.
        """
        model = genai.GenerativeModel(active_model_name, system_instruction=system_instruction)
    else:
        st.error("⚠️ لا توجد موديلات متاحة"); st.stop()
except:
    st.error("⚠️ خطأ في الاتصال"); st.stop()

# ===== 2. واجهة التطبيق =====
st.title("🎙️ المعلم الذكي (محادثة صوتية)")

# ===== 3. تسجيل الدخول =====
if "logged_in" not in st.session_state:
    password = st.text_input("🔑 كلمة المرور", type="password")
    if password == "SCIENCE60":
        st.session_state.logged_in = True
        st.rerun()
    elif password:
        st.warning("كلمة المرور خطأ")
    st.stop()

# ===== 4. العداد =====
if "start_time" not in st.session_state: st.session_state.start_time = time.time()
remaining = 3600 - (time.time() - st.session_state.start_time)
if remaining <= 0: st.error("انتهى الوقت"); st.stop()
st.info(f"⏳ باقي: {int(remaining//60)} دقيقة")

# ===== 5. منطقة المحادثة الصوتية =====
st.markdown("---")
st.subheader("تحدث مع المعلم مباشرة 👇")

# عمودين: واحد للزر وواحد لعرض الحالة
col1, col2 = st.columns([1, 3])

with col1:
    st.write("اضغط للتحدث:")
    # زر التسجيل (يعيد بايتات الصوت)
    audio_input = mic_recorder(
        start_prompt="🎤 اضغط وسجّل",
        stop_prompt="⏹️ إنهاء وإرسال",
        key='recorder',
        format="wav" # مهم جداً للتعرف على الكلام
    )

user_text = ""

# منطق المعالجة
if audio_input:
    with st.spinner("🎧 أستمع إليك..."):
        # 1. تحويل صوت الطالب لنص
        transcribed_text = speech_to_text(audio_input['bytes'])
        
        if transcribed_text:
            user_text = transcribed_text
            st.success(f"🗣️ أنت قلت: {user_text}")
        else:
            st.warning("⚠️ لم أسمع صوتك بوضوح، حاول مرة أخرى.")

# إذا كان هناك نص (سواء من الصوت أو كتابة يدوية إذا أردت إضافتها لاحقاً)
if user_text:
    with st.spinner("🤖 المستشار يفكر ويجهز الرد..."):
        try:
            # 2. الحصول على الإجابة
            response = model.generate_content(user_text)
            answer_text = response.text
            
            # عرض النص
            st.markdown(f"### 📘 الإجابة:\n{answer_text}")
            
            # 3. تحويل الإجابة لصوت
            output_file = "response.mp3"
            asyncio.run(generate_speech(answer_text, output_file))
            
            # تشغيل الصوت تلقائياً
            st.audio(output_file, format='audio/mp3', autoplay=True)
            
        except Exception as e:
            st.error(f"حدث خطأ: {e}")

st.markdown("---")
st.caption("ملاحظة: تأكد من السماح للمتصفح باستخدام الميكروفون 🎤")
