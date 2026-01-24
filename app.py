import streamlit as st
from google.oauth2 import service_account
import gspread
import time

# =========================================================
# 1. إعدادات الصفحة والتصميم
# =========================================================
st.set_page_config(
    page_title="المعلم العلمي الذكي",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# تنسيق CSS
st.markdown("""
<style>
    .stApp { direction: rtl; text-align: right; }
    .stTextInput label, .stSelectbox label, .stTextArea label {
        font-family: sans-serif;
        font-size: 1.1rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: right;
    }
    .stTextInput input { text-align: right; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        height: 3em;
        background-color: #1f77b4;
        color: white;
        font-weight: bold;
    }
    .stButton>button:hover { background-color: #0d47a1; color: white; }
    .stAlert { direction: rtl; text-align: right; }
</style>
""", unsafe_allow_html=True)

# تحميل الثوابت
TEACHER_MASTER_KEY = st.secrets.get("TEACHER_MASTER_KEY", "ADMIN_DEFAULT")
CONTROL_SHEET_NAME = st.secrets.get("CONTROL_SHEET_NAME", "App_Control")
# =========================================================
# 2. دوال الاتصال وإدارة الجلسة
# =========================================================
@st.cache_resource
def get_gspread_client():
    if "gcp_service_account" not in st.secrets:
        st.error("بيانات حساب الخدمة مفقودة.")
        return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        # إصلاح المفتاح الخاص
        if "private_key" in creds_dict:
            pk = creds_dict["private_key"]
            creds_dict["private_key"] = pk.replace("\\n", "\n")
        
        scopes = [
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/spreadsheets",
        ]
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        st.error("فشل الاتصال بجوجل.")
        print(e)
        return None

def get_student_code_from_sheet():
    client = get_gspread_client()
    if not client: return None
    try:
        sh = client.open(CONTROL_SHEET_NAME)
        return str(sh.sheet1.acell("B1").value).strip()
    except Exception as e:
        st.error("خطأ في قراءة ملف الإكسل.")
        return None

# إدارة الجلسة
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_role' not in st.session_state:
    st.session_state.user_role = None
if 'user_name' not in st.session_state:
    st.session_state.user_name = ""

def do_login(name, role):
    st.session_state.logged_in = True
    st.session_state.user_name = name
    st.session_state.user_role = role
    st.rerun()

def do_logout():
    st.session_state.logged_in = False
    st.session_state.user_role = None
    st.session_state.user_name = ""
    st.rerun()
    # =========================================================
# 3. واجهات التطبيق
# =========================================================
import google.generativeai as genai
import random

# =========================================================
# دالة التعامل مع الذكاء الاصطناعي
# =========================================================
def get_ai_response(user_prompt):
    try:
        # جلب المفاتيح من ملف الأسرار
        keys = st.secrets.get("GOOGLE_API_KEYS", [])
        if not keys:
            return "عذراً، لم يتم العثور على مفاتيح Gemini API في الإعدادات."
        
        # اختيار مفتاح عشوائي لتوزيع الحمل
        selected_key = random.choice(keys)
        genai.configure(api_key=selected_key)
        
        # إعداد النموذج
        model = genai.GenerativeModel('gemini-pro')
        
        # توجيه المعلم (System Prompt)
        # هنا نخبر الذكاء الاصطناعي كيف يتصرف
        role_instruction = """
        أنت معلم علوم خبير ومرح (فيزياء، كيمياء، أحياء).
        مهمتك هي شرح المفاهيم العلمية للطلاب بوضوح وباللغة العربية.
        استخدم أمثلة من الواقع، وبسط المعلومات المعقدة.
        إذا كان السؤال خارج نطاق العلوم، اعتذر بلطف وأخبر الطالب أنك متخصص في العلوم فقط.
        """
        
        full_prompt = f"{role_instruction}\n\nسؤال الطالب: {user_prompt}"
        
        response = model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        return f"حدث خطأ أثناء الاتصال بالذكاء الاصطناعي: {str(e)}"

# =========================================================
# 3. واجهات التطبيق
# =========================================================
def show_login_page():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h2 style='text-align: center; color:#1f77b4;'>🧪 المعلم العلمي</h2>", unsafe_allow_html=True)
        with st.form("login_form"):
            name = st.text_input("الاسم")
            code = st.text_input("الكود", type="password")
            submitted = st.form_submit_button("دخول")
            
            if submitted:
                if not name or not code:
                    st.warning("املأ البيانات")
                elif code == TEACHER_MASTER_KEY:
                    do_login(name, "Teacher")
                else:
                    db_code = get_student_code_from_sheet()
                    if db_code and code == db_code:
                        do_login(name, "Student")
                    else:
                        st.error("الكود خطأ")

def show_main_app():
    with st.sidebar:
        st.title(f"مرحباً {st.session_state.user_name}")
        st.caption(f"الصلاحية: {st.session_state.user_role}")
        st.markdown("---")
        menu = st.radio("القائمة", ["المحادثة", "المكتبة"])
        st.markdown("---")
        if st.button("خروج"): do_logout()

    if menu == "المحادثة":
        st.header("🤖 المحادثة الذكية")
        st.caption("اسألني في الفيزياء، الكيمياء، أو الأحياء...")
        
        # تهيئة سجل المحادثة
        if "messages" not in st.session_state:
            st.session_state.messages = []

        # عرض الرسائل القديمة
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])
        
        # استقبال السؤال الجديد
        if prompt := st.chat_input("اكتب سؤالك العلمي هنا..."):
            # 1. عرض سؤال المستخدم
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.write(prompt)
            
            # 2. التفكير والحصول على الإجابة من Gemini
            with st.chat_message("assistant"):
                with st.spinner("جاري تحليل السؤال واستحضار المعلومات العلمية... 🧬"):
                    response_text = get_ai_response(prompt)
                    st.write(response_text)
            
            # 3. حفظ الإجابة في السجل
            st.session_state.messages.append({"role": "assistant", "content": response_text})
            
    elif menu == "المكتبة":
        st.header("📚 المكتبة")
        st.info("سيتم ربط ملفات PDF هنا قريباً.")

if __name__ == "__main__":
    if st.session_state.logged_in:
        show_main_app()
    else:
        show_login_page()
