import streamlit as st
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
# 2) جلب المفتاح من قائمتك الخاصة
# =========================
# هنا قمت بتعديل الكود ليقرأ من "GOOGLE_API_KEYS" التي أرسلتها أنت
try:
    if "GOOGLE_API_KEYS" in st.secrets:
        # نأخذ أول مفتاح من القائمة التي وضعتها
        api_key = st.secrets["GOOGLE_API_KEYS"][0]
        genai.configure(api_key=api_key)
        configured = True
    else:
        st.error("⚠️ لم يتم العثور على GOOGLE_API_KEYS في Secrets")
        configured = False
except Exception as e:
    st.error(f"❌ خطأ في الإعداد: {e}")
    configured = False

# =========================
# 3) وظيفة الذكاء الاصطناعي
# =========================
def get_ai_response(user_input, stage, grade, lang):
    if not configured:
        return "⚠️ النظام غير جاهز، تأكد من صحة المفاتيح."
    
    try:
        model = genai.GenerativeModel('gemini-pro')
        lang_str = "English" if "English" in lang else "العربية"
        
        prompt = f"""
        أنت المعلم 'السيد البدوي'. خبير مادة العلوم والفيزياء.
        المرحلة: {stage} | الصف: {grade} | اللغة: {lang_str}.
        سؤال الطالب: {user_input}
        أجب بأسلوب تعليمي مشوق ومبسط جداً.
        """
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"❌ حدث خطأ: {str(e)}"

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
            code = st.text_input("الكود السري (جرب 1234)", type="password")
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
            # استخدمت ADMIN_2024 كما هو في ملف أسرارك
            if code in ["1234", "ADMIN", "ADMIN_2024"]:
                st.session_state.logged_in = True
                st.session_state.u = {"name": name, "stage": stage, "grade": grade, "lang": lang}
                st.rerun()
            else:
                st.error("❌ الكود خاطئ")
else:
    # واجهة الدردشة
    u = st.session_state.u
    st.sidebar.title(f"مرحباً {u['name']}")
    st.sidebar.write(f"المرحلة: {u['stage']}")
    st.sidebar.write(f"الصف: {u['grade']}")
    
    if st.sidebar.button("خروج"):
        st.session_state.logged_in = False
        st.rerun()

    st.markdown(f"### 🤖 معلم {u['lang']} الافتراضي معك")
    
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("اسأل المعلم السيد البدوي..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("جاري التفكير..."):
                response = get_ai_response(prompt, u['stage'], u['grade'], u['lang'])
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
