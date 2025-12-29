import streamlit as st
import time
import google.generativeai as genai

# ===== إعداد الذكاء الاصطناعي =====
import google.generativeai as genai

genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])

model = genai.GenerativeModel("models/text-bison-001")

# ===== عنوان التطبيق =====
st.title("🧠 مساعد العلوم المتكاملة – أولى ثانوي")

# ===== تسجيل الدخول =====
password = st.text_input("ادخل كلمة الدخول", type="password")

if password != "SCIENCE60":
    st.warning("كلمة الدخول غير صحيحة")
    st.stop()

st.success("تم الدخول بنجاح ✅")

# ===== عداد 60 دقيقة =====
if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()

elapsed = time.time() - st.session_state.start_time
remaining = 3600 - elapsed

if remaining <= 0:
    st.error("⏱️ انتهت مدة الجلسة")
    st.stop()

minutes = int(remaining // 60)
seconds = int(remaining % 60)

st.info(f"⏳ الوقت المتبقي: {minutes}:{seconds:02d}")

# ===== السؤال والإجابة =====
st.subheader("✍️ اكتب سؤالك في العلوم المتكاملة")

question = st.text_input("سؤالك هنا")

if st.button("إرسال"):
    if question.strip() == "":
        st.warning("من فضلك اكتب سؤالًا أولًا")
    else:
        with st.spinner("🤖 جاري التفكير..."):
            response = model.generate_content(
                f"أجب عن السؤال التالي بأسلوب مبسط لطالب الصف الأول الثانوي:\n{question}"
            )
        st.success("الإجابة:")
        st.write(response.text)
