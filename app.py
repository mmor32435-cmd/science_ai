import streamlit as st
import time
import google.generativeai as genai

# ===== 1. إعداد الصفحة والربط بجوجل =====
st.set_page_config(page_title="مساعد العلوم", page_icon="🧬", layout="centered")

# متغير لتخزين اسم الموديل الذي سنجده
active_model_name = None

try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
    
    # --- الحل الذكي: البحث عن الموديلات المتاحة تلقائياً ---
    available_models = []
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            available_models.append(m.name)
            
    if len(available_models) > 0:
        # نفضل موديل flash إذا وجدناه لأنه أسرع
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
        st.error("⚠️ لم يتم العثور على أي موديلات متاحة في مفتاح API الخاص بك.")
        st.stop()

except Exception as e:
    st.error(f"⚠️ مشكلة في الاتصال بجوجل: {e}")
    st.stop()

# ===== 2. عنوان التطبيق =====
st.title("🧠 مساعد العلوم المتكاملة – أولى ثانوي")
if active_model_name:
    st.caption(f"✅ متصل حالياً بالموديل: {active_model_name}")

# ===== 3. نظام تسجيل الدخول =====
password = st.text_input("🔑 ادخل كلمة الدخول", type="password")

if password != "SCIENCE60":
    if password: 
        st.warning("⛔ كلمة الدخول غير صحيحة")
    st.stop() 

st.success("تم الدخول بنجاح ✅ ابدأ المذاكرة!")

# ===== 4. عداد الوقت (60 دقيقة) =====
if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()

elapsed = time.time() - st.session_state.start_time
remaining = 3600 - elapsed

if remaining <= 0:
    st.error("⏱️ انتهت مدة الجلسة")
    st.stop()

minutes = int(remaining // 60)
seconds = int(remaining % 60)
st.info(f"⏳ الوقت المتبقي للجلسة: {minutes} دقيقة و {seconds:02d} ثانية")

# ===== 5. الشات والذكاء الاصطناعي =====
st.markdown("---")
st.subheader("✍️ اسأل المساعد الذكي")

question = st.text_area("اكتب سؤالك هنا:", placeholder="مثال: اشرح لي قانون الجاذبية...")

if st.button("إرسال السؤال 🚀"):
    if question.strip() == "":
        st.warning("⚠️ من فضلك اكتب سؤالًا أولًا")
    else:
        with st.spinner("🤖 جاري التفكير..."):
            try:
                prompt = f"أنت مدرس علوم ممتاز. اشرح لطالب في الصف الأول الثانوي بأسلوب مبسط ومختصر: {question}"
                response = model.generate_content(prompt)
                st.markdown("### 💡 الإجابة:")
                st.write(response.text)
            except Exception as e:
                st.error(f"حدث خطأ أثناء المعالجة: {e}")
