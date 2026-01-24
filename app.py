import streamlit as st
from google.oauth2 import service_account
import google.generativeai as genai
import gspread
import time
import random
from PIL import Image

# =========================================================
# 1. الإعدادات والتصميم (Configuration & UI)
# =========================================================
st.set_page_config(
    page_title="AI Science Tutor | الأستاذ السيد البدوي",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# تصميم CSS الاحترافي
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Cairo', sans-serif;
        direction: rtl;
        text-align: right;
    }
    
    .stApp {
        background: linear-gradient(135deg, #fdfbfb 0%, #ebedee 100%);
    }
    
    /* كارت العنوان */
    .header-box {
        background: linear-gradient(90deg, #1CB5E0 0%, #000851 100%);
        padding: 20px;
        border-radius: 15px;
        color: white;
        text-align: center;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        margin-bottom: 20px;
    }
    .header-title { font-size: 2.5em; font-weight: bold; margin: 0; }
    .header-subtitle { font-size: 1.2em; color: #ddd; margin-top: 5px; }
    
    /* رسائل الشات */
    .stChatMessage {
        background-color: #ffffff;
        border-radius: 12px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        border: 1px solid #f0f0f0;
    }
    
    /* الأزرار */
    .stButton>button {
        background-color: #000851;
        color: white;
        border-radius: 10px;
        width: 100%;
        height: 50px;
        font-weight: bold;
    }
    .stButton>button:hover {
        background-color: #1CB5E0;
        color: white;
        border: 1px solid white;
    }
</style>
""", unsafe_allow_html=True)

# عرض العنوان
st.markdown("""
<div class="header-box">
    <div class="header-title">الأستاذ / السيد البدوي</div>
    <div class="header-subtitle">Mr. Elsayed Elbadawy - Expert Science Tutor</div>
</div>
""", unsafe_allow_html=True)

# تحميل الثوابت
TEACHER_MASTER_KEY = st.secrets.get("TEACHER_MASTER_KEY", "ADMIN_DEFAULT")
CONTROL_SHEET_NAME = st.secrets.get("CONTROL_SHEET_NAME", "App_Control")

# =========================================================
# 2. المنطق الخلفي (Backend Logic)
# =========================================================

# تهيئة بيانات الجلسة
if 'user_data' not in st.session_state:
    st.session_state.user_data = {
        "logged_in": False, "role": None, "name": "",
        "grade": "الصف الأول الإعدادي", "lang": "العربية", "stage": "الإعدادية"
    }

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

def get_student_code_from_sheet():
    client = get_gspread_client()
    if not client: return None
    try:
        sh = client.open(CONTROL_SHEET_NAME)
        return str(sh.sheet1.acell("B1").value).strip()
    except: return None

def get_best_available_model(api_key):
    """البحث عن أفضل نموذج متاح"""
    try:
        genai.configure(api_key=api_key)
        models = genai.list_models()
        chat_models = [m.name for m in models if 'generateContent' in m.supported_generation_methods]
        
        if not chat_models: return 'models/gemini-pro'
        
        # 1. البحث عن Flash (للصور والسرعة)
        for m in chat_models:
            if 'flash' in m.lower(): return m
        # 2. البحث عن Pro
        for m in chat_models:
            if 'pro' in m.lower(): return m
            
        return chat_models[0]
    except:
        return 'models/gemini-pro'

def get_ai_response(user_text, image_data=None):
    try:
        keys = st.secrets.get("GOOGLE_API_KEYS", [])
        if not keys: return "⚠️ خطأ: المفاتيح غير موجودة."
        
        key = random.choice(keys)
        model_name = get_best_available_model(key)
        
        genai.configure(api_key=key)
        model = genai.GenerativeModel(model_name)
        
        # بيانات الطالب
        u = st.session_state.user_data
        lang_instruction = "اشرح باللغة العربية." if "العربية" in u['lang'] else "Explain in English."
        
        system_prompt = f"""
        أنت الأستاذ السيد البدوي، معلم علوم خبير.
        الطالب في: {u['stage']} - {u['grade']}.
        
        تعليماتك:
        1. التزم بمنهج الطالب.
        2. {lang_instruction}
        3. كن مختصراً ومفيداً.
        4. لو أرفق الطالب صورة، قم بحلها.
        """
        
        content = [f"{system_prompt}\n\nالسؤال: {user_text}"]
        if image_data:
            content.append(image_data)
            content[0] += "\n(يوجد صورة مرفقة من الطالب)."

        response = model.generate_content(content)
        return response.text
    except Exception as e:
        return f"حدث خطأ: {e}"

# =========================================================
# 3. واجهة المستخدم (UI Functions)
# =========================================================

def show_login_page():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            st.markdown("### 🔐 تسجيل الدخول")
            name = st.text_input("الاسم الثلاثي")
            code = st.text_input("الكود السري", type="password")
            
            st.markdown("---")
            st.markdown("###### ⚙️ إعدادات المنهج")
            col_a, col_b = st.columns(2)
            with col_a:
                stage = st.selectbox("المرحلة", ["الابتدائية", "الإعدادية", "الثانوية"])
                lang = st.selectbox("اللغة", ["العربية (علوم)", "English (Science)"])
            with col_b:
                grade = st.selectbox("الصف", ["الرابع", "الخامس", "السادس", "الأول", "الثاني", "الثالث"])
            
            if st.form_submit_button("دخول"):
                if code == TEACHER_MASTER_KEY:
                    st.session_state.user_data.update({"logged_in": True, "role": "Teacher", "name": name})
                    st.rerun()
                else:
                    db_code = get_student_code_from_sheet()
                    if db_code and code == db_code:
                        st.session_state.user_data.update({
                            "logged_in": True, "role": "Student", "name": name,
                            "stage": stage, "grade": grade, "lang": lang
                        })
                        st.rerun()
                    else:
                        st.error("الكود غير صحيح")

def show_main_app():
    with st.sidebar:
        u = st.session_state.user_data
        st.markdown(f"### أهلاً {u['name']}")
        st.info(f"{u['stage']} | {u['grade']}")
        
        menu = st.radio("القائمة", ["💬 المساعد الذكي", "📝 اختبارات", "📚 المكتبة"])
        
        if st.button("تسجيل الخروج"):
            st.session_state.user_data["logged_in"] = False
            st.rerun()

    if menu == "💬 المساعد الذكي":
        st.markdown("#### 🔬 اسأل الأستاذ السيد البدوي")
        
        # رفع صورة
        uploaded_file = st.file_uploader("📸 ارفع صورة مسألة (اختياري)", type=['png', 'jpg', 'jpeg'])
        image_data = None
        if uploaded_file:
            image_data = Image.open(uploaded_file)
            st.image(image_data, width=200, caption="الصورة المرفقة")

        # الشات
        if "messages" not in st.session_state: st.session_state.messages = []
        
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]): st.write(msg["content"])
            
        if prompt := st.chat_input("اكتب سؤالك هنا..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.write(prompt)
            
            with st.chat_message("assistant"):
                with st.spinner("جاري التفكير..."):
                    resp = get_ai_response(prompt, image_data)
                    st.write(resp)
            st.session_state.messages.append({"role": "assistant", "content": resp})

    elif menu == "📝 اختبارات":
        st.header("🎯 بنك الأسئلة")
        if st.button("أنشئ اختباراً جديداً"):
            with st.spinner("جاري الإعداد..."):
                q = get_ai_response("قم بإنشاء 3 أسئلة اختيار من متعدد في منهجي مع الإجابات.")
                st.markdown(q)

    elif menu == "📚 المكتبة":
        st.header("📚 المكتبة الرقمية")
        st.info("سيتم تفعيل عرض الكتب قريباً.")

# نقطة الانطلاق
if __name__ == "__main__":
    if st.session_state.user_data["logged_in"]:
        show_main_app()
    else:
        show_login_page()
