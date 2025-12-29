import streamlit as st
import time

st.title("🧠 مساعد العلوم المتكاملة")

password = st.text_input("ادخل كلمة الدخول", type="password")

if password != "SCIENCE60":
    st.warning("كلمة الدخول غير صحيحة")
    st.stop()

st.success("تم الدخول بنجاح ✅")
