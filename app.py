import streamlit as st
import time
import google.generativeai as genai
import asyncio
import edge_tts
from streamlit_mic_recorder import mic_recorder
from io import BytesIO

# ===== 1. إعداد الصفحة =====
st.set_page_config(page_title="المعلم الصوتي الذكي", page_icon="🎙️", layout="centered")

# --- دالة تحويل رد المعلم إلى صوت ---
async def generate_speech(text, output_file):
    # نستخدم صوت 'شاكر' الطبيعي
    communicate = edge_tts.Communicate(text, "ar-EG-ShakirNeural")
    await communicate.save(output_file)

# --- إعداد اتصال جوجل ---
active_model_name = None
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
    
    # نستخدم gemini-1.5-flash حصراً لأنه يدعم استقبال الصوت مباشرة
    model = genai.GenerativeModel('gemini-1.5-flash')
    
except Exception as e:
    st.error(f"⚠️ خطأ في الاتصال بجوجل: {e}")
    st.stop()

# ===== 2. واجهة التطبيق =====
st.title("🎙️ المعلم الذكي (يسمع ويتكلم)")
st.caption("✅ تم تفعيل وضع الاستماع المباشر (Multimodal)")

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

# ===== 5. المحادثة الصوتية المباشرة =====
st.markdown("---")
st.subheader("تحدث مع المعلم 👇")

st.write("اضغط على الميكروفون، تحدث، ثم اضغط مرة أخرى للإرسال:")

# إعداد الميكروفون
audio_input = mic_recorder(
    start_prompt="🎤 ابدأ التسجيل",
    stop_prompt="⏹️ إرسال السؤال",
    key='recorder',
    format="wav"
)

if audio_input:
    # هنا يكمن السحر: نأخذ الصوت كما هو
    audio_bytes = audio_input['bytes']
    
    # عرض مشغل صوتي ليتأكد الطالب أن صوته تم تسجيله
    st.audio(audio_bytes, format='audio/wav')
    
    with st.spinner("🎧 المستشار يسمع سؤالك الآن..."):
        try:
            # تعليمات للمعلم حول كيفية الرد
            prompt_text = """
            استمع لهذا التسجيل الصوتي من طالب في الصف الأول الثانوي.
            1. أجب على سؤاله بدقة علمية ولكن بأسلوب مبسط ومرح (شخصية مستر شاكر).
            2. تحدث باللهجة العربية القريبة من الفصحى السهلة.
            3. لا تذكر أنك استمعت لملف صوتي، بل أجب مباشرة كأنك في محادثة.
            4. اجعل الإجابة مختصرة (لا تزيد عن 3 جمل) ومفيدة.
            """
            
            # إرسال الصوت + التعليمات للموديل مباشرة (Multimodal)
            response = model.generate_content([
                prompt_text,
                {
                    "mime_type": "audio/wav",
                    "data": audio_bytes
                }
            ])
            
            answer_text = response.text
            
            # عرض الإجابة كتابة
            st.markdown(f"### 📘 الإجابة:\n{answer_text}")
            
            # تحويل الإجابة لصوت
            output_file = "response.mp3"
            asyncio.run(generate_speech(answer_text, output_file))
            
            # تشغيل الرد الصوتي تلقائياً
            st.audio(output_file, format='audio/mp3', autoplay=True)
            
        except Exception as e:
            st.error(f"حدث خطأ أثناء المعالجة: {e}")
            st.info("نصيحة: تأكد أنك تتحدث بصوت واضح وأن الميكروفون يعمل.")

st.markdown("---")
