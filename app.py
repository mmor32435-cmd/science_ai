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
import pytz
from PIL import Image
import PyPDF2

# ==========================================
# 🎛️ لوحة تحكم المعلم
# ==========================================

# كلمة المرور الموحدة للدخول
DAILY_PASSWORD = "SCIENCE_CHAT" 

# توقيتك المحلي
MY_TIMEZONE = 'Africa/Cairo' 

# المواعيد المسموحة (الساعة بنظام 24)
# 17 = 5 مساءً | 19 = 7 مساءً | 21 = 9 مساءً
ALLOWED_HOURS = [17, 19, 21] 

# ==========================================

st.set_page_config(page_title="منصة المناقشة الذكية", page_icon="💡", layout="wide")

# --- 1. دالة حارس الوقت (Time Guard) ---
def check_discussion_time():
    tz = pytz.timezone(MY_TIMEZONE)
    now = datetime.now(tz)
    current_hour = now.hour
    
    # هل الساعة الحالية موجودة ضمن الساعات المسموحة؟
    if current_hour in ALLOWED_HOURS:
        # حساب الوقت المتبقي لنهاية الساعة الحالية
        minutes_passed = now.minute
        minutes_remaining = 60 - minutes_passed
        return True, f"✅ الجلسة مفتوحة! متبقي {minutes_remaining} دقيقة للإغلاق."
    else:
        # رسالة الخطأ توضح المواعيد
        msg = f"""
        🛑 المنصة مغلقة حالياً.
        
        ⏰ مواعيد المناقشة اليومية (بتوقيت القاهرة):
        1️⃣ من 5:00 م إلى 6:00 م
        2️⃣ من 7:00 م إلى 8:00 م
        3️⃣ من 9:00 م إلى 10:00 م
        
        الساعة الآن: {now.strftime('%I:%M %p')}
        """
        return False, msg

# تنفيذ التحقق من الوقت فوراً
is_open, status_msg = check_discussion_time()

if not is_open:
    st.error(status_msg)
    st.image("https://cdn-icons-png.flaticon.com/512/2972/2972531.png", width=150)
    st.stop() # يغلق التطبيق

# --- 2. دوال المساعدة (صوت، PDF، صور) ---

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

def extract_text_from_pdf(pdf_file):
    reader = PyPDF2.PdfReader(pdf_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text

# --- 3. اتصال الذكاء الاصطناعي ---
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    # نحتاج موديل يدعم الصور (Vision) مثل flash أو pro
    all_models = genai.list_models()
    vision_models = [m.name for m in all_models if 'generateContent' in m.supported_generation_methods and 'flash' in m.name]
    
    if vision_models:
        active_model = vision_models[0]
    else:
        # احتياطي لو لم يجد flash
        active_model = "models/gemini-1.5-pro"
        
    model = genai.GenerativeModel(active_model)
except Exception as e:
    st.error(f"خطأ في الاتصال: {e}")
    st.stop()

# ==========================================
# ===== 4. واجهة التطبيق =====
# ==========================================

# تسجيل الدخول
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔐 بوابة المناقشة العلمية")
    st.success(status_msg) # نعرض رسالة أن الوقت متاح
    pwd = st.text_input("كلمة مرور الجلسة:", type="password")
    if st.button("دخول"):
        if pwd == DAILY_PASSWORD:
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("كلمة المرور غير صحيحة")
    st.stop()

# الواجهة الرئيسية بعد الدخول
st.sidebar.title("معلومات الجلسة")
st.sidebar.info(status_msg)
st.sidebar.markdown("---")
st.sidebar.write("🔊 صوت المعلم:")
voice_choice = st.sidebar.radio("اختر:", ["مستر شاكر (مصري)", "مس سلمى (مصرية)"])
voice_code = "ar-EG-ShakirNeural" if "شاكر" in voice_choice else "ar-EG-SalmaNeural"

st.title("💡 ساحة الحوار والمناقشة")
st.caption("اسأل، ناقش، أرسل صوراً أو ملفات.. المعلم الذكي معك!")

# --- نظام التبويبات (Tabs) لتنظيم المدخلات ---
tab1, tab2, tab3 = st.tabs(["🎙️ تحدث (صوت)", "✍️ كتابة وسؤال", "📁 رفع ملفات/صور"])

user_input_content = None # لتخزين السؤال النهائي
input_type = "text" # text, image, pdf

# --- تبويب 1: الصوت ---
with tab1:
    st.write("اضغط وتحدث للنقاش:")
    audio_input = mic_recorder(start_prompt="🎤 تحدث", stop_prompt="⏹️ إرسال", key='rec', format="wav")
    if audio_input:
        with st.spinner("👂 أسمعك..."):
            text = speech_to_text(audio_input['bytes'])
            if text:
                user_input_content = text
                st.success(f"🗣️ قلت: {text}")

# --- تبويب 2: الكتابة ---
with tab2:
    text_input = st.text_area("اكتب سؤالك أو موضوع المناقشة هنا:", height=100)
    if st.button("إرسال النص") and text_input:
        user_input_content = text_input

# --- تبويب 3: الملفات والصور ---
with tab3:
    uploaded_file = st.file_uploader("ارفع صورة (للمسائل) أو ملف PDF (للمذكرات)", type=['png', 'jpg', 'jpeg', 'pdf'])
    file_caption = st.text_input("أضف سؤالاً حول الملف (اختياري):")
    
    if st.button("تحليل الملف ومناقشته") and uploaded_file:
        if uploaded_file.type == "application/pdf":
            # معالجة PDF
            with st.spinner("📄 جاري قراءة ملف PDF..."):
                pdf_text = extract_text_from_pdf(uploaded_file)
                # ندمج نص الـ PDF مع سؤال الطالب
                user_input_content = f"النص المستخرج من الملف:\n{pdf_text}\n\nسؤالي هو: {file_caption}"
                input_type = "text" # لأننا حولنا الـ PDF لنص
        else:
            # معالجة الصور
            image = Image.open(uploaded_file)
            st.image(image, caption="الصورة المرفقة", width=300)
            user_input_content = [file_caption if file_caption else "اشرح هذه الصورة علمياً", image]
            input_type = "image"

# ==========================================
# ===== 5. المعالجة والرد =====
# ==========================================

if user_input_content:
    with st.spinner("🧠 المعلم يفكر ويحلل..."):
        try:
            # تجهيز التوجيه (Prompt) للمناقشة
            role_desc = "معلمة" if "سلمى" in voice_choice else "معلم"
            system_prompt = f"""
            أنت {role_desc} علوم مصري محب للنقاش والحوار.
            - هدفك ليس مجرد الإجابة، بل فتح حوار وفهم عمق سؤال الطالب.
            - تحدث باللهجة المصرية الراقية (بساطة مع دقة علمية).
            - إذا أرسل الطالب صورة، اشرح تفاصيلها بدقة.
            - إذا كان السؤال يحتاج تفكيراً، اشرح الخطوات "واحدة واحدة".
            - استخدم عبارات حوارية مثل: (بص يا سيدي، خد بالك من النقطة دي، إيه رأيك لو...).
            - اجعل الإجابة مسموعة (تجنب الرموز المعقدة).
            """
            
            # الإرسال للموديل حسب النوع
            if input_type == "image":
                # للصورة نرسل القائمة [النص, الصورة]
                full_prompt = [system_prompt, user_input_content[0], user_input_content[1]]
                response = model.generate_content(full_prompt)
            else:
                # للنص نرسل النص المدمج
                full_prompt = f"{system_prompt}\n\nسؤال الطالب/محتوى الملف:\n{user_input_content}"
                response = model.generate_content(full_prompt)
            
            # العرض
            st.markdown("---")
            st.markdown(f"### 📘 رد {role_desc}:")
            st.write(response.text)
            
            # الصوت
            output_file = "response.mp3"
            asyncio.run(generate_speech(response.text, output_file, voice_code))
            st.audio(output_file, format='audio/mp3', autoplay=True)
            
        except Exception as e:
            st.error(f"حدث خطأ أثناء المعالجة: {e}")
            if "404" in str(e):
                st.warning("قد يكون الموديل غير مدعوم في منطقتك للصور، حاول استخدام النص فقط.")

st.markdown("---")
