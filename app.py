import streamlit as st
import time
import google.generativeai as genai
from gtts import gTTS
from io import BytesIO

# ===== 1. إعداد الصفحة والربط بجوجل =====
st.set_page_config(page_title="مساعد العلوم المتكلم", page_icon="🗣️", layout="centered")

# متغير لتخزين اسم الموديل الذي سنجده
active_model_name = None

try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
    
    # البحث الذكي عن الموديلات المتاحة لتجنب أخطاء 404
    available_models = []
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            available_models.append(m.name)
            
    if len(available_models) > 0:
        # نفضل موديل flash للسرعة، ثم pro، ثم أي شيء آخر
        flash_models = [m for m in available_models if 'flash' in m]
        pro_models = [m for m in available_models if 'pro' in m]
        
        if flash_models:
            active_model_name = flash_models[0]
        elif pro_models:
            active_model_name = pro_models[0]
        else:
            active_model_name = available_models[0]
            
        model = genai.GenerativeModel(active_model_name)
    else:
        st.error("⚠️ لم يتم العثور على أي موديلات متاحة.")
        st.stop()

except Exception as e:
    st.error(f"⚠️ مشكلة في الاتصال بجوجل: {e}")
    st.stop()

# ===== 2. واجهة التطبيق =====
st.title("🧠 مساعد العلوم (الناطق) – أولى ثانوي")
if active_model_name:
    st.caption(f"✅ متصل بـ: {active_model_name}")

# ===== 3. تسجيل الدخول =====
password = st.text_input("🔑 ادخل كلمة الدخول", type="password")

if password != "SCIENCE60":
    if password: 
        st.warning("⛔ كلمة الدخول غير صحيحة")
    st.stop() 

st.success("تم الدخول بنجاح ✅")

# ===== 4. العداد =====
if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()

elapsed = time.time() - st.session_state.start_time
remaining = 3600 - elapsed

if remaining <= 0:
    st.error("⏱️ انتهت الجلسة")
    st.stop()

minutes = int(remaining // 60)
seconds = int(remaining % 60)
st.info(f"⏳ الوقت المتبقي: {minutes} دقيقة و {seconds:02d} ثانية")

# ===== 5. الشات والصوت =====
st.markdown("---")
st.subheader("✍️ اسأل وسأجيبك بصوت مسموع")

question = st.text_area("اكتب سؤالك:", placeholder="اشرح لي نظرية التطور...")

if st.button("إرسال وسماع الإجابة 🔊"):
    if question.strip() == "":
        st.warning("⚠️ اكتب سؤالاً أولاً")
    else:
        with st.spinner("🤖 أفكر وأجهز الصوت..."):
            try:
                # 1. جلب الإجابة النصية
                prompt = f"أنت مدرس علوم. اشرح لطالب أولى ثانوي بأسلوب مبسط جداً ومختصر: {question}"
                response = model.generate_content(prompt)
                answer_text = response.text
                
                # عرض النص
                st.markdown("### 💡 الإجابة:")
                st.write(answer_text)
                
                # 2. تحويل النص إلى صوت
                # نستخدم BytesIO لتخزين الصوت في الذاكرة بدلاً من ملف للحفاظ على السرعة
                sound_file = BytesIO()
                tts = gTTS(text=answer_text, lang='ar') # اللغة العربية
                tts.write_to_fp(sound_file)
                
                # تشغيل الصوت
                st.audio(sound_file, format='audio/mp3')
                
            except Exception as e:
                st.error(f"حدث خطأ: {e}")
