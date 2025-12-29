import streamlit as st
import time
import google.generativeai as genai

# ===== 1. إعداد الصفحة والربط بجوجل =====
st.set_page_config(page_title="مساعد العلوم", page_icon="🧬", layout="centered")

# محاولة جلب المفتاح وتشغيل المكتبة
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
    # إعداد الموديل
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    st.error("⚠️ حدث خطأ في مفتاح API. تأكد من إضافته في Secrets.")
    st.stop()

# ===== 2. عنوان التطبيق =====
st.title("🧠 مساعد العلوم المتكاملة – أولى ثانوي")

# ===== 3. نظام تسجيل الدخول =====
password = st.text_input("🔑 ادخل كلمة الدخول", type="password")

if password != "SCIENCE60":
    if password: # عشان ما تظهر الرسالة والخانة فاضية
        st.warning("⛔ كلمة الدخول غير صحيحة")
    st.stop() # يوقف التطبيق هنا حتى يتم إدخال الباسورد الصحيح

st.success("تم الدخول بنجاح ✅ ابدأ المذاكرة!")

# ===== 4. عداد الوقت (60 دقيقة) =====
if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()

elapsed = time.time() - st.session_state.start_time
remaining = 3600 - elapsed

if remaining <= 0:
    st.error("⏱️ انتهت مدة الجلسة")
    st.stop()

# عرض الوقت بشكل جميل
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
        with st.spinner("🤖 جاري التفكير وتحضير الإجابة..."):
            try:
                # توجيه الموديل ليشرح لطالب أولى ثانوي
                prompt = f"أنت مدرس علوم ممتاز. اشرح لطالب في الصف الأول الثانوي بأسلوب مبسط ومختصر: {question}"
                
                response = model.generate_content(prompt)
                
                st.markdown("### 💡 الإجابة:")
                st.write(response.text)
            except Exception as e:
                st.error(f"حدث خطأ أثناء الاتصال بجوجل: {e}")
