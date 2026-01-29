import streamlit as st
import os
import google.generativeai as genai

# =========================
# 1) إعدادات الصفحة والتنسيق
# =========================
st.set_page_config(
    page_title="منصة الأستاذ السيد البدوي التعليمية",
    page_icon="🔬",
    layout="wide"
)

# تنسيق CSS احترافي يدعم العربية والانجليزية
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
html, body, .stApp {
  font-family: 'Cairo', sans-serif !important;
  direction: rtl;
  text-align: right;
}
.header-box {
  background: linear-gradient(90deg, #000428 0%, #004e92 100%);
  padding: 1.5rem;
  border-radius: 15px;
  text-align: center;
  color: white;
  margin-bottom: 2rem;
}
</style>
""", unsafe_allow_html=True)

# =========================
# 2) تهيئة الجلسة ومفتاح الذكاء الاصطناعي
# =========================
if "messages" not in st.session_state:
    st.session_state.messages = []
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# تأكد من وضع المفتاح في Streamlit Secrets
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# =========================
# 3) وظيفة الذكاء الاصطناعي (المعلم الذكي)
# =========================
def get_ai_response(user_input, stage, grade, lang):
    if not GEMINI_API_KEY:
        return "⚠️ نظام الذكاء الاصطناعي غير مفعل حالياً. يرجى إضافة المفتاح."
    
    try:
        model = genai.GenerativeModel('gemini-pro')
        
        # توجيه الذكاء الاصطناعي بناءً على اللغة والمرحلة
        if "English" in lang:
            system_prompt = f"You are Mr. Sayyid Al-Badawi, a Science teacher for {stage} stage, {grade} grade. Answer in English only, in a simple and educational way."
        else:
            system_prompt = f"أنت المعلم السيد البدوي، خبير مادة العلوم للمرحلة {stage}، الصف {grade}. أجب باللغة العربية بأسلوب تعليمي مشوق ومبسط."
            
        full_prompt = f"{system_prompt}\nStudent question: {user_input}"
        response = model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        return f"حدث خطأ: {str(e)}"

# =========================
# 4) صفحة تسجيل الدخول المتطورة
# =========================
if not st.session_state.logged_in:
    st.markdown('<div class="header-box"><h1>الأستاذ / السيد البدوي</h1><h3>منصة العلوم والفيزياء الذكية</h3></div>', unsafe_allow_html=True)
    
    with st.form("login"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("الاسم الثلاثي للطالب")
            code = st.text_input("الكود السري", type="password")
        with col2:
            lang = st.selectbox("لغة الدراسة", ["العربية (علوم)", "English (Science/Physics)"])
            stage = st.selectbox("المرحلة الدراسية", ["الابتدائية", "الإعدادية", "الثانوية"])
        
        # تحديد الصفوف بناءً على المرحلة
        if stage == "الابتدائية":
            grades = ["الرابع", "الخامس", "السادس"]
        elif stage == "الإعدادية":
            grades = ["الأول الإعدادي", "الثاني الإعدادي", "الثالث الإعدادي"]
        else:
            grades = ["الأول الثانوي", "الثاني الثانوي", "الثالث الثانوي"]
            
        grade = st.selectbox("الصف الدراسي", grades)
        
        submit = st.form_submit_button("🚀 بدء رحلة التعلم")
        
        if submit:
            if code in ["1234", "ADMIN"]: # الأكواد المسموح بها
                st.session_state.logged_in = True
                st.session_state.user_data = {
                    "name": name, 
                    "stage": stage, 
                    "grade": grade, 
                    "lang": lang
                }
                st.rerun()
            else:
                st.error("❌ الكود غير صحيح")

# =========================
# 5) لوحة التحكم والدردشة
# =========================
else:
    u = st.session_state.user_data
    
    # القائمة الجانبية
    st.sidebar.markdown(f"### مرحباً: {u['name']}")
    st.sidebar.info(f"📍 {u['stage']} - {u['grade']}\n\n🌐 {u['lang']}")
    
    if st.sidebar.button("🔴 خروج"):
        st.session_state.logged_in = False
        st.session_state.messages = []
        st.rerun()

    # واجهة المحادثة
    st.markdown(f"### 🤖 معلم الـ {u['lang']} الافتراضي معك الآن")
    
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("اسأل المعلم السيد البدوي..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("جاري تحضير الإجابة العلمية..."):
                resp = get_ai_response(prompt, u['stage'], u['grade'], u['lang'])
                st.markdown(resp)
                st.session_state.messages.append({"role": "assistant", "content": resp})
