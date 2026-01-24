import streamlit as st
from google.oauth2 import service_account
import gspread
import pandas as pd
import time

# =========================================================
# 1. إعدادات الصفحة والتصميم (Configuration & CSS)
# =========================================================
st.set_page_config(
    page_title="المعلم العلمي الذكي",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# تطبيق تنسيق اللغة العربية وتحسين المظهر العام
st.markdown("""
<style>
    /* جعل الاتجاه من اليمين لليسار */
    .stApp {
        direction: rtl;
        text-align: right;
    }
    /* تنسيق الحقول والنصوص */
    .stTextInput label, .stSelectbox label {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        font-size: 1.1rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: right;
    }
    .stTextInput input {
        text-align: right;
    }
    /* إخفاء العلامات المائية الافتراضية */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* تنسيق الأزرار */
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        height: 3em;
        background-color: #1f77b4;
        color: white;
        font-weight: bold;
    }
    .stButton>button:hover {
        background-color: #0d47a1;
        color: white;
    }
    
    /* رسائل النجاح والخطأ */
    .stAlert {
        direction: rtl;
        text-align: right;
    }
</style>
""", unsafe_allow_html=True)

# =========================================================
# 2. تحميل الأسرار والثوابت (Secrets & Constants)
# =========================================================
TEACHER_MASTER_KEY = st.secrets.get("TEACHER_MASTER_KEY", "ADMIN_DEFAULT")
CONTROL_SHEET_NAME = st.secrets.get("CONTROL_SHEET_NAME", "App_Control")

# =========================================================
# 3. دوال الاتصال الخلفية (Backend Functions)
# =========================================================

@st.cache_resource
def get_gspread_client():
    """إنشاء اتصال آمن ومخزن مؤقتاً مع Google Sheets"""
    if "gcp_service_account" not in st.secrets:
        st.error("⚠️ خطأ في الإعدادات: لم يتم العثور على بيانات حساب الخدمة في ملف الأسرار.")
        return None
    
    try:
        # تحويل كائن الأسرار إلى قاموس عادي
        creds_dict = dict(st.secrets["gcp_service_account"])
        
        scopes = [
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/spreadsheets",
        ]
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"⚠️ فشل الاتصال بخدمات جوجل: {e}")
        return None

def get_student_code_from_sheet():
    """جلب الكود الموحد للطلاب من ورقة التحكم"""
    client = get_gspread_client()
    if not client:
        return None
        
    try:
        sh = client.open(CONTROL_SHEET_NAME)
        # نفترض أن الكود موجود في الورقة الأولى، الخلية B1
        sheet = sh.sheet1
        val = sheet.acell("B1").value
        return str(val).strip() if val else None
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"⚠️ الملف غير موجود: تأكد من أن اسم الورقة في جوجل شيت هو '{CONTROL_SHEET_NAME}'")
        return None
    except Exception as e:
        st.error(f"حدث خطأ غير متوقع: {e}")
        return None

# =========================================================
# 4. إدارة حالة الجلسة (Session State)
# =========================================================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_role' not in st.session_state:
    st.session_state.user_role = None  # 'Teacher' or 'Student'
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
# 5. واجهة تسجيل الدخول (Login Page)
# =========================================================
def show_login_page():
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("<h1 style='text-align: center; color: #1f77b4;'>🧪 المعلم العلمي الذكي</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; font-size: 1.2em; color: #555;'>منصة تعليمية متطورة مدعومة بالذكاء الاصطناعي</p>", unsafe_allow_html=True)
        st.markdown("---")
        
        with st.form("login_form", clear_on_submit=False):
            name_input = st.text_input("الاسم الثلاثي", placeholder="سجل اسمك هنا...")
            code_input = st.text_input("كود الدخول", type="password", placeholder="أدخل الكود السري...")
            
            submitted = st.form_submit_button("تسجيل الدخول")
            
            if submitted:
                if not name_input or not code_input:
                    st.warning("⚠️ الرجاء إدخال الاسم وكود الدخول.")
                else:
                    with st.spinner("جاري التحقق من البيانات..."):
                        # 1. التحقق هل هو معلم؟
                        if code_input == TEACHER_MASTER_KEY:
                            st.success(f"مرحباً بك يا معلم {name_input}")
                            time.sleep(0.5)
                            do_login(name_input, "Teacher")
                            return

                        # 2. التحقق هل هو طالب؟ (من جوجل شيت)
                        db_code = get_student_code_from_sheet()
                        
                        if db_code:
                            if code_input == db_code:
                                st.success(f"أهلاً بك يا طالب {name_input}")
                                time.sleep(0.5)
                                do_login(name_input, "Student")
                            else:
                                st.error("⛔ كود الدخول غير صحيح.")
                        else:
                            st.error("تعذر الاتصال بقاعدة البيانات للتحقق من كود الطالب.")

# =========================================================
# 6. واجهة التطبيق الرئيسية (Main App Interface)
# =========================================================
def show_main_app():
    # --- القائمة الجانبية ---
    with st.sidebar:
        st.markdown(f"### 👤 {st.session_state.user_name}")
        st.info(f"الصلاحية: {'معلم 👨‍🏫' if st.session_state.user_role == 'Teacher' else 'طالب 👨‍🎓'}")
        
        st.markdown("---")
        menu = st.radio("القائمة الرئيسية", ["💬 المحادثة الذكية", "📚 المكتبة الرقمية", "⚙️ الإعدادات"])
        
        st.markdown("---")
        if st.button("تسجيل الخروج"):
            do_logout()

    # --- محتوى الصفحات ---
    if menu == "💬 المحادثة الذكية":
        st.header("المساعد العلمي (Gemini AI)")
        st.write("مرحباً بك في واجهة المحادثة. يمكنك طرح أسئلتك العلمية هنا.")
        
        # حاوية المحادثة (Placeholder للكود المستقبلي)
        chat_container = st.container()
        with chat_container:
            if "messages" not in st.session_state:
                st.session_state.messages = [{"role": "assistant", "content": "أهلاً! أنا معلمك الذكي، اسألني في أي موضوع علمي."}]

            for msg in st.session_state.messages:
                with st.chat_message(msg["role"]):
                    st.write(msg["content"])

        prompt = st.chat_input("اكتب سؤالك هنا...")
        if prompt:
            # إضافة رسالة المستخدم
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.write(prompt)
            
            # محاكاة الرد (يتم استبدال هذا لاحقاً بربط Gemini API الفعلي)
            with st.chat_message("assistant"):
                response_text = "هذا رد تجريبي.. (سيتم تفعيل الذكاء الاصطناعي قريباً)"
                st.write(response_text)
            st.session_state.messages.append({"role": "assistant", "content": response_text})

    elif menu == "📚 المكتبة الرقمية":
        st.header("المكتبة والمراجع")
        st.warning("جاري الاتصال بـ Google Drive لجلب الكتب...")
        # يمكنك هنا استخدام دالة لجلب الملفات باستخدام DRIVE_FOLDER_ID

    elif menu == "⚙️ الإعدادات":
        st.header("إعدادات التطبيق")
        st.toggle("تفعيل القراءة الصوتية (TTS)", value=True)
        st.selectbox("اختر النموذج", ["Gemini Pro", "Gemini Flash"])

# =========================================================
# 7. نقطة الانطلاق (Entry Point)
# =========================================================
if __name__ == "__main__":
    if st.session_state.logged_in:
        show_main_app()
    else:
        show_login_page()
