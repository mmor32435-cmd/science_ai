import streamlit as st
from google.oauth2 import service_account
import google.generativeai as genai
import gspread
from PIL import Image
import random

# ==========================================
# 1. إعدادات الصفحة (يجب أن يكون أول سطر)
# ==========================================
st.set_page_config(
    page_title="المعلم العلمي | السيد البدوي",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# 2. التصميم (CSS)
# ==========================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
    html, body, [class*="css"] {
        font-family: 'Cairo', sans-serif;
        direction: rtl;
        text-align: right;
    }
    .stApp { background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%); }
    .header-box {
        background: linear-gradient(90deg, #141E30 0%, #243B55 100%);
        padding: 2rem; border-radius: 15px; color: white; text-align: center; margin-bottom: 2rem;
    }
    .stButton>button {
        background-color: #243B55; color: white; border-radius: 10px; height: 50px; width: 100%; font-weight: bold;
    }
    .stButton>button:hover { background-color: #141E30; }
</style>
""", unsafe_allow_html=True)

# بانر العنوان
st.markdown("""
<div class="header-box">
    <h1>الأستاذ / السيد البدوي</h1>
    <h3>Mr. Elsayed Elbadawy - Expert Science Tutor</h3>
</div>
""", unsafe_allow_html=True)

# ==========================================
# 3. إدارة الجلسة (Session State)
# ==========================================
if 'user_data' not in st.session_state:
    st.session_state.user_data = {
        "logged_in": False, "role": None, "name": "",
        "grade": "الصف الأول", "stage": "الإعدادية", "lang": "العربية"
    }

if 'messages' not in st.session_state:
    st.session_state.messages = []

# ==========================================
# 4. دوال الاتصال (Backend)
# ==========================================
TEACHER_KEY = st.secrets.get("TEACHER_MASTER_KEY", "ADMIN")
SHEET_NAME = st.secrets.get("CONTROL_SHEET_NAME", "App_Control")

@st.cache_resource
def get_gspread_client():
    if "gcp_service_account" not in st.secrets: return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds)
    except: return None

def check_student_code(input_code):
    client = get_gspread_client()
    if not client: return False
    try:
        sh = client.open(SHEET_NAME)
        real_code = str(sh.sheet1.acell("B1").value).strip()
        return input_code == real_code
    except: return False

# ==========================================
# 5. الذكاء الاصطناعي (AI Logic)
# ==========================================
def get_ai_response(user_text, img_obj=None):
    try:
        keys = st.secrets.get("GOOGLE_API_KEYS", [])
        if not keys: return "⚠️ خطأ: المفاتيح غير موجودة."
        
        genai.configure(api_key=random.choice(keys))
        
        # إعداد بيانات الطالب
        u = st.session_state.user_data
        lang_instruction = "اشرح بالعربية." if "العربية" in u['lang'] else "Explain in English."
        
        system_prompt = f"""
        أنت الأستاذ السيد البدوي، معلم علوم خبير.
        الطالب: {u['name']} ({u['stage']} - {u['grade']}).
        التعليمات: التزم بالمنهج، {lang_instruction}، كن مختصراً ومفيداً.
        """
        
        # محاولة استخدام Flash (يدعم الصور)
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            inputs = [system_prompt, user_text]
            if img_obj:
                inputs.append(img_obj)
                inputs.append("قم بحل الصورة.")
            response = model.generate_content(inputs)
            return response.text
        except:
            # محاولة بديلة (Gemini Pro) للنصوص فقط
            if img_obj: return "عذراً، حدث خطأ في تحليل الصورة، لكن يمكنني الرد على النصوص."
            model = genai.GenerativeModel('gemini-pro')
            response = model.generate_content(f"{system_prompt}\nالسؤال: {user_text}")
            return response.text

    except Exception as e:
        return f"حدث خطأ في الاتصال: {e}"

# ==========================================
# 6. الواجهات (UI)
# ==========================================
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
                lang = st.selectbox("اللغة", ["العربية", "English"])
            with c2:
                grade = st.selectbox("الصف", ["الرابع", "الخامس", "السادس", "الأول", "الثاني", "الثالث"])
            
            if st.form_submit_button("دخول"):
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
                    st.error("الكود خطأ")

def main_app():
    with st.sidebar:
        st.success(f"مرحباً: {st.session_state.user_data['name']}")
        if st.button("خروج"):
            st.session_state.user_data["logged_in"] = False
            st.rerun()

    st.subheader("💬 اسأل المعلم")
    
    # رفع صورة
    with st.expander("📸 إرفاق صورة (اختياري)"):
        f = st.file_uploader("اختر صورة", type=['jpg', 'png'])
        img = Image.open(f) if f else None
        if img: st.image(img, width=200)

    # المحادثة
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): st.write(msg["content"])

    if prompt := st.chat_input("سؤالك..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.write(prompt)
        
        with st.chat_message("assistant"):
            with st.spinner("جاري التفكير..."):
                resp = get_ai_response(prompt, img)
                st.write(resp)
        st.session_state.messages.append({"role": "assistant", "content": resp})

# ==========================================
# 7. التشغيل
# ==========================================
if __name__ == "__main__":
    if st.session_state.user_data["logged_in"]:
        main_app()
    else:
        login_page()
