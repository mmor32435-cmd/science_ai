import streamlit as st
import os
import google.generativeai as genai

# =========================
# 1) إعدادات الصفحة والتنسيق
# =========================
st.set_page_config(page_title="منصة الأستاذ السيد البدوي", page_icon="🔬", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
html, body, .stApp { font-family: 'Cairo', sans-serif !important; direction: rtl; text-align: right; }
.header-box { background: linear-gradient(90deg, #000428 0%, #004e92 100%); padding: 1.5rem; border-radius: 15px; text-align: center; color: white; margin-bottom: 2rem; }
</style>
""", unsafe_allow_html=True)

# =========================
# 2) جلب المفتاح والتأكد منه
# =========================
# نحاول جلب المفتاح بأكثر من طريقة لضمان العمل
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY") or st.secrets.get("gemini_api_key")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    st.warning("⚠️ تحذير: لم يتم العثور على مفتاح GEMINI_API_KEY في ملف الأسرار.")

# =========================
# 3) وظيفة الذكاء الاصطناعي
# =========================
def get_ai_response(user_input, stage, grade, lang):
    if not GEMINI_API_KEY:
        return "⚠️ نظام الذكاء الاصطناعي غير مفعل حالياً. تأكد من إضافة GEMINI_API_KEY في إعدادات Secrets."
    
    try:
        model = genai.GenerativeModel('gemini-pro')
        lang_str = "English" if "English" in lang else "العربية"
        
        prompt = f"""
        أنت المعلم 'السيد البدوي'. خبير مادة العلوم والفيزياء.
        المرحلة: {stage} | الصف: {grade} | اللغة المطلوبة: {lang_str}.
        سؤال الطالب: {user_input}
        أجب بأسلوب تعليمي مبسط ومحفز.
        """
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"❌ حدث خطأ أثناء جلب الإجابة: {str(e)}"

# =========================
# 4) نظام تسجيل الدخول
# =========================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.markdown('<div class="header-box"><h1>الأستاذ / السيد البدوي</h1><h3>منصة العلوم والفيزياء الذكية</h3></div>', unsafe_allow_html=True)
    with st.form("login"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("الاسم الثلاثي")
            code = st.text_input("الكود السري", type="password")
        with col2:
            lang = st.selectbox("اللغة", ["العربية (علوم)", "English (Science/Physics)"])
            stage = st.selectbox("المرحلة", ["الابتدائية", "الإعدادية", "الثانوية"])
        
        grades = {
            "الابتدائية": ["الرابع", "الخامس", "السادس"],
            "الإعدادية": ["الأول الإعدادي", "الثاني الإعدادي", "الثالث الإعدادي"],
            "الثانوية": ["الأول الثانوي", "الثاني الثانوي", "الثالث الثانوي"]
        }
        grade = st.selectbox("الصف", grades[stage])
        
        if st.form_submit_button("دخول"):
            if code in ["1234", "ADMIN"]:
                st.session_state.logged_in = True
                st.session_state.u = {"name": name, "stage": stage, "grade": grade, "lang": lang}
                st.rerun()
            else:
                st.error("الكود خاطئ")

else:
    # واجهة الدردشة
    u = st.session_state.u
    st.sidebar.title(f"مرحباً {u['name']}")
    if st.sidebar.button("خروج"):
        st.session_state.logged_in = False
        st.rerun()

    st.markdown(f"### 🤖 معلم {u['lang']} للمرحلة {u['stage']}")
    
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("اسأل المعلم السيد البدوي..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)

        with st.chat_message("assistant"):
            response = get_ai_response(prompt, u['stage'], u['grade'], u['lang'])
            st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})
