import streamlit as st
from google.oauth2 import service_account
import google.generativeai as genai
import gspread
from PIL import Image
import random

# -----------------------------------------------------------------------------
# 1. إعدادات الصفحة (يجب أن تكون في السطر الأول)
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="المعلم العلمي | السيد البدوي",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------------------------------------------------------
# 2. تصميم الواجهة الاحترافي (CSS)
# -----------------------------------------------------------------------------
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
    
    .header-style {
        background: linear-gradient(90deg, #000428 0%, #004e92 100%);
        padding: 1.5rem;
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
        font-size: 18px;
    }
    .stButton>button:hover {
        background-color: #000428;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 3. دوال الاتصال والمنطق (Backend)
# -----------------------------------------------------------------------------

def get_keys_and_secrets():
    """جلب المفاتيح بأمان لتجنب الأخطاء"""
    teacher_key = st.secrets.get("TEACHER_MASTER_KEY", "ADMIN")
    sheet_name = st.secrets.get("CONTROL_SHEET_NAME", "App_Control")
    api_keys = st.secrets.get("GOOGLE_API_KEYS", [])
    return teacher_key, sheet_name, api_keys

@st.cache_resource
def get_gspread_client():
    """الاتصال بجوجل شيت"""
    if "gcp_service_account" not in st.secrets:
        return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        # إصلاح مشكلة السطر الجديد في المفتاح
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds)
    except:
        return None

def check_student_code(input_code):
    """التحقق من كود الطالب"""
    client = get_gspread_client()
    # إذا فشل الاتصال نعيد خطأ
    if not client: return False
    
    try:
        _, sheet_name, _ = get_keys_and_secrets()
        sh = client.open(sheet_name)
        real_code = str(sh.sheet1.acell("B1").value).strip()
        return input_code == real_code
    except:
        return False

def get_ai_response(user_text, img_obj=None):
    """الذكاء الاصطناعي: يدعم النصوص والصور"""
    try:
        _, _, api_keys = get_keys_and_secrets()
        if not api_keys:
            return "⚠️ خطأ: لم يتم العثور على مفاتيح API."
        
        # إعداد المفتاح
        genai.configure(api_key=random.choice(api_keys))
        
        # بيانات الطالب
        u = st.session_state.user_data
        lang_prompt = "اشرح باللغة العربية" if "العربية" in u['lang'] else "Explain in English"
        
        system_prompt = f"""
        أنت الأستاذ السيد البدوي، معلم علوم خبير.
        الطالب: {u['name']}
        الصف: {u['grade']} ({u['stage']})
        
        التعليمات:
        1. التزم بالمنهج المصري.
        2. {lang_prompt}.
        3. كن مختصراً ومفيداً.
        4. حلل الصور بدقة إذا وجدت.
        """
        
        # المحاولة الأولى: استخدام نموذج Flash (يدعم الصور)
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            inputs = [system_prompt, user_text]
            if img_obj:
                inputs.append(img_obj)
                inputs.append("قم بحل وشرح هذه الصورة.")
            
            response = model.generate_content(inputs)
            return response.text
            
        except Exception:
            # المحاولة الثانية: استخدام نموذج Pro (احتياطي للنصوص فقط)
            if img_obj:
                return "عذراً، حدث خطأ في تحليل الصورة، لكن يمكنني الرد على سؤالك النصي."
            
            model = genai.GenerativeModel('gemini-pro')
            response = model.generate_content(f"{system_prompt}\nالسؤال: {user_text}")
            return response.text
            
    except Exception as e:
        return f"حدث خطأ في الاتصال: {e}"

# -----------------------------------------------------------------------------
# 4. تهيئة المتغيرات (Session State)
# -----------------------------------------------------------------------------
if 'user_data' not in st.session_state:
    st.session_state.user_data = {
        "logged_in": False, "role": None, "name": "",
        "grade": "الصف الأول", "stage": "الإعدادية", "lang": "العربية"
    }

if 'messages' not in st.session_state:
    st.session_state.messages = []

# -----------------------------------------------------------------------------
# 5. واجهة تسجيل الدخول
# -----------------------------------------------------------------------------
def show_login():
    st.markdown("""
    <div class="header-style">
        <h1>الأستاذ / السيد البدوي</h1>
        <p>Expert Science Tutor Application</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### 🔐 تسجيل الدخول")
        with st.form("login_form"):
            name = st.text_input("الاسم الثلاثي")
            code = st.text_input("الكود السري", type="password")
            
            st.markdown("---")
            c1, c2 = st.columns(2)
            with c1:
                stage = st.selectbox("المرحلة", ["الابتدائية", "الإعدادية", "الثانوية"])
                lang = st.selectbox("لغة الدراسة", ["العربية (علوم)", "English (Science)"])
            with c2:
                grade = st.selectbox("الصف الدراسي", ["الرابع", "الخامس", "السادس", "الأول", "الثاني", "الثالث"])
            
            submitted = st.form_submit_button("بدء التعلم")
            
            if submitted:
                teacher_key, _, _ = get_keys_and_secrets()
                
                if code == teacher_key:
                    st.session_state.user_data.update({"logged_in": True, "role": "Teacher", "name": name})
                    st.rerun()
                elif check_student_code(code):
                    st.session_state.user_data.update({
                        "logged_in": True, "role": "Student", "name": name,
                        "grade": grade, "stage": stage, "lang": lang
                    })
                    st.rerun()
                else:
                    st.error("❌ الكود غير صحيح، حاول مرة أخرى.")

# -----------------------------------------------------------------------------
# 6. واجهة التطبيق الرئيسية
# -----------------------------------------------------------------------------
def show_app():
    # القائمة الجانبية
    with st.sidebar:
        u = st.session_state.user_data
        st.success(f"مرحباً بك: {u['name']}")
        st.info(f"{u['stage']} | {u['grade']}")
        
        if st.button("🚪 تسجيل الخروج"):
            st.session_state.user_data["logged_in"] = False
            st.rerun()

    # العنوان
    st.markdown(f"### 🧬 المساعد العلمي ({u['lang']})")
    
    # منطقة رفع الصور
    with st.expander("📸 إرفاق صورة مسألة (اختياري)"):
        uploaded_file = st.file_uploader("اختر صورة من جهازك", type=['jpg', 'png', 'jpeg'])
        image_data = Image.open(uploaded_file) if uploaded_file else None
        if image_data:
            st.image(image_data, width=250, caption="الصورة المرفقة")

    # عرض المحادثة
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # مربع الكتابة
    if prompt := st.chat_input("اكتب سؤالك العلمي هنا..."):
        # عرض سؤال المستخدم
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)
        
        # التفكير والرد
        with st.chat_message("assistant"):
            with st.spinner("جاري استحضار المعلومات من المنهج..."):
                response_text = get_ai_response(prompt, image_data)
                st.write(response_text)
        
        st.session_state.messages.append({"role": "assistant", "content": response_text})

# -----------------------------------------------------------------------------
# 7. نقطة التشغيل الرئيسية
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    if st.session_state.user_data["logged_in"]:
        show_app()
    else:
        show_login()
