import streamlit as st
import time

st.title("🧠 مساعد العلوم المتكاملة")

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

st.info(f"الوقت المتبقي: {minutes}:{seconds:02d}")

# ===== محتوى بعد الدخول =====
st.subheader("اسأل سؤالك في العلوم المتكاملة 👇")

question = st.text_input("اكتب سؤالك هنا")

if st.button("إرسال"):
    if question.strip() == "":
        st.warning("من فضلك اكتب سؤالًا أولًا")
    else:
        st.success("تم استلام السؤال ✅")
        st.write("🤖 (سيتم هنا عرض الإجابة لاحقًا)")
