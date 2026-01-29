import streamlit as st
import os
import time
import random

# 1) إعدادات الصفحة
st.set_page_config(
    page_title="المعلم العلمي | السيد البدوي",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2) تنسيق الواجهة (CSS) ليدعم العربية
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
    
    html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        font-family: 'Cairo', sans-serif;
        direction: rtl;
        text-align: right;
    }
    
    .stButton>button {
        width: 100%;
        border-radius: 10px;
        background: linear-gradient(90deg, #004e92 0%, #000428 100%);
        color: white !important;
        font-weight: bold;
        height: 3em;
    }
    
    .header-box {
        background: linear-gradient(90deg, #000428 0%, #004e92 100%);
        padding: 2rem;
        border-radius: 15px;
        text-align: center;
        color: white;
        margin-bottom: 2rem;
    }
</style>
""", unsafe_allow_html=True)

# 3) تهيئة جلسة المستخدم
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "messages" not in st.session_state:
    st.session_state.messages = []

# 4) صفحة تسجيل الدخول
def login_page():
    st.markdown('<div class="header-box"><h1>الأستاذ / السيد البدوي</h1><h3>منصة العلوم الذكية</h3></div>', unsafe_allow_html=True)
    
    with st.form("login_form"):
        st.subheader("🔐 تسجيل دخول الطالب")
        name = st.text_input("الاسم الثلاثي")
        code = st.text_input("الكود السري", type="password")
        grade = st.selectbox("الصف الدراسي", ["الرابع", "الخامس", "السادس", "الأول الإعدادي", "الثاني الإعدادي", "الثالث الإعدادي"])
        
        submit = st.form_submit_button("🚀 دخول")
        if submit:
            if code == "1234" or code == "ADMIN": # يمكنك تغيير الكود هنا
                st.session_state.logged_in = True
                st.session_state.user_name = name
                st.session_state.grade = grade
                st.success("تم تسجيل الدخول بنجاح!")
                st.rerun()
            else:
                st.error("❌ الكود غير صحيح، يرجى التواصل مع الأستاذ")

# 5) صفحة الدردشة والاختبارات
def main_app():
    st.sidebar.title(f"مرحباً يا {st.session_state.user_name}")
    st.sidebar.info(f"الصف: {st.session_state.grade}")
    
    if st.sidebar.button("تسجيل الخروج"):
        st.session_state.logged_in = False
        st.rerun()

    st.markdown(f"## 🤖 المعلم الافتراضي - صف {st.session_state.grade}")
    
    # عرض الرسائل السابقة
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # مدخلات الدردشة
    if prompt := st.chat_input("اسألني أي سؤال في العلوم أو اكتب 'اختبار'..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            response = ""
            if "اختبار" in prompt:
                response = "حسناً يا بطل! إليك سؤال سريع: ما هو العضو المسؤول عن ضخ الدم في جسم الإنسان؟"
            elif "شكرا" in prompt:
                response = "العفو يا بطل! أنا دائماً هنا لمساعدتك في فهم العلوم."
            else:
                response = f"أهلاً بك يا {st.session_state.user_name}. سؤالك عن '{prompt}' جميل جداً. في منهج {st.session_state.grade}، نتعلم أن العلوم ممتعة!"
            
            st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})

# التشغيل الرئيسي
if not st.session_state.logged_in:
    login_page()
else:
    main_app()
