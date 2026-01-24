import streamlit as st
from google.oauth2 import service_account
import google.generativeai as genai
import gspread
from PIL import Image
import random
import time

# =========================================================
# 1. إعدادات الصفحة (يجب أن تكون في أول سطر)
# =========================================================
st.set_page_config(
    page_title="المعلم العلمي | الأستاذ السيد البدوي",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =========================================================
# 2. التنسيق والتصميم (CSS)
# =========================================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Cairo', sans-serif;
        direction: rtl;
        text-align: right;
    }
    
    .stApp {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    }
    
    .header-container {
        background: linear-gradient(90deg, #000428 0%, #004e92 100%);
        padding: 2rem;
        border-radius: 15px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    
    .stButton>button {
        width: 100%;
        background-color: #004e92;
        color: white;
        border-radius: 8px;
        height: 50px;
        font-weight: bold;
    }
    .stButton>button:hover {
        background-color: #000428;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# بانر العنوان
st.markdown("""
<div class="header-container">
    <h1>الأستاذ / السيد البدوي</h1>
    <h3>Mr. Elsayed Elbadawy - Expert Science Tutor</h3>
</div>
""", unsafe_allow_html=True)

# =========================================================
# 3. تهيئة الجلسة (Session State)
# =========================================================
if 'user_data' not in st.session_state:
    st.session_state.user_data = {
        "logged_in": False,
        "role": None,
        "name": "",
        "grade": "الصف الأول",
        "stage": "الإعدادية",
        "lang": "العربية"
    }

if 'messages' not in st.session_state:
    st.session_state.messages = []

# =========================================================
# 4. دوال الاتصال (Backend)
# =========================================================
TEACHER_KEY = st.secrets.get("TEACHER_MASTER_KEY", "ADMIN")
SHEET_NAME = st.secrets.get("CONTROL_SHEET_NAME", "App_Control")

@st.cache_resource
def get_gspread_client():
    if "gcp_service_account" not in st.secrets:
        return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        # إصلاح المفتاح الخاص
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds)
    except:
        return None

def check_student_code(input_code):
    client = get_gspread_client()
    if not client:
        return False
    try:
        sh = client.open(SHEET_NAME)
        real_code = str(sh.sheet1.acell("B1").value).strip()
        return input_code == real_code
    except:
        return False

# =========================================================
# 5. الذكاء الاصطناعي (AI Engine)
# =========================================================
def get_ai_response(user_text, image_obj=None):
    try:
        keys = st.secrets.get("GOOGLE_API_KEYS", [])
        if not keys:
            return "⚠️ خطأ: لم يتم العثور على مفاتيح API."
        
        # إعداد المفتاح
        genai.configure(api_key=random.choice(keys))
        
        # محاولة استخدام نموذج Flash لأنه يدعم الصور
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # تجهيز تعليمات المعلم (Prompt)
        u = st.session_state.user_data
        lang_instruction = "اشرح باللغة العربية." if "العربية" in u['lang'] else "Explain in English."
        
        system_prompt = f"""
        أنت الأستاذ السيد البدوي، معلم علوم خبير.
        تحدث مع الطالب: {u['name']}
        الصف الدراسي: {u['stage']} - {u['grade']}
        
        التعليمات:
        1. التزم بمنهج الطالب.
        2. {lang_instruction}
        3. كن مختصراً ومفيداً.
        4. إذا أرسل الطالب صورة، قم بحلها.
        """
        
        # تجهيز المدخلات للنموذج
        inputs = [system_prompt, user_text]
        if image_obj:
            inputs.append(image_obj)
            inputs.append("قم بحل وشرح محتوى هذه الصورة.")

        response = model.generate_content(inputs)
        return response.text
        
    except Exception as e:
        # إذا فشل Flash، نحاول استخدام Pro (للنصوص فقط)
        try:
            if image_obj: return "عذراً، حدث خطأ أثناء تحليل الصورة."
            model_pro = genai.GenerativeModel('gemini-pro')
            response = model_pro.generate_content(user_text)
            return response.text
        except:
            return f"حدث خطأ في الاتصال: {str(e)}"

# =========================================================
# 6. واجهات العرض (UI Pages)
# =========================================================

def login_page():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### 🔐 تسجيل الدخول")
        with st.form("login"):
            name = st.text_input("الاسم")
            code = st.text_input("الكود", type="password")
            
            st.markdown("---")
            c1, c2 = st.columns(2)
            with c1:
                stage = st.selectbox("المرحلة", ["الابتدائية", "الإعدادية", "الثانوية"])
                lang = st.selectbox("اللغة", ["العربية (علوم)", "English (Science)"])
            with c2:
                grade = st.selectbox("الصف", ["الرابع", "الخامس", "السادس", "الأول", "الثاني", "الثالث"])
                
            submitted = st.form_submit_button("دخول")
            
            if submitted:
                if code == TEACHER_KEY:
                    st.session_state.user_data.update({"logged_in": True, "role": "Teacher", "name": name})
                    st.rerun()
                elif check_student_code(code):
                    st.session_state.user_data.update({
                        "logged_in": True, "role": "Student", "name": name,
                        "stage": stage, "grade": grade, "lang": lang
                    })
                    st.rerun()
                else:
                    st.error("الكود غير صحيح")

def main_app():
    # القائمة الجانبية
    with st.sidebar:
        u = st.session_state.user_data
        st.success(f"مرحباً: {u['name']}")
        st.info(f"{u['stage']} | {u['grade']}")
        
        page = st.radio("التنقل", ["💬 اسأل المعلم", "📝 اختبارات", "⚙️ خروج"])
        
        if page == "⚙️ خروج":
            st.session_state.user_data["logged_in"] = False
            st.rerun()

    # الصفحة الرئيسية (الشات)
    if page == "💬 اسأل المعلم":
        st.subheader("🧬 المساعد العلمي الذكي")
        
        # منطقة رفع الصور
        with st.expander("📸 إرفاق صورة (اختياري)"):
            upl_file = st.file_uploader("اختر صورة مسألة", type=['png', 'jpg', 'jpeg'])
            img = Image.open(upl_file) if upl_file else None
            if img: st.image(img, width=200)

        # عرض الرسائل السابقة
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

        # مربع الإدخال
        if prompt := st.chat_input("اكتب سؤالك العلمي هنا..."):
            # إضافة سؤال المستخدم
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.write(prompt)
            
            # معالجة الرد
            with st.chat_message("assistant"):
                with st.spinner("جاري التفكير..."):
                    response_text = get_ai_response(prompt, img)
                    st.write(response_text)
            
            # حفظ الرد
            st.session_state.messages.append({"role": "assistant", "content": response_text})

    elif page == "📝 اختبارات":
        st.header("🎯 بنك الأسئلة")
        if st.button("أنشئ اختباراً جديداً"):
            with st.spinner("جاري إعداد الأسئلة..."):
                q = get_ai_response("اكتب لي 3 أسئلة اختيار من متعدد في منهجي مع الحل.")
                st.markdown(q)

# =========================================================
# 7. نقطة التشغيل الرئيسية
# =========================================================
if __name__ == "__main__":
    if st.session_state.user_data["logged_in"]:
        main_app()
    else:
        login_page()
