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

# تنسيق CSS لدعم اللغة العربية وتحسين المظهر
st.markdown("""
<style>
    /* اتجاه النص من اليمين لليسار */
    .stApp { direction: rtl; text-align: right; }
    
    /* تنسيق النصوص والعناوين */
    .stTextInput label, .stSelectbox label, .stTextARea label {
        font-family: sans-serif;
        font-size: 1.1rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: right;
    }
    .stTextInput input { text-align: right; }
    
    /* إخفاء القوائم الافتراضية */
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
        font-size: 16px;
    }
    .stButton>button:hover { background-color: #0d47a1; color: white; }
    
    /* رسائل التنبيه */
    .stAlert { direction: rtl; text-align: right; }
</style>
""", unsafe_allow_html=True)

# =========================================================
# 2. تحميل الثوابت من ملف الأسرار
# =========================================================
TEACHER_MASTER_KEY = st.secrets.get("TEACHER_MASTER_KEY", "ADMIN_DEFAULT")
CONTROL_SHEET_NAME = st.secrets.get("CONTROL_SHEET_NAME", "App_Control")

# =========================================================
# 3. دوال الاتصال الخلفية (Backend)
# =========================================================

@st.cache_resource
def get_gspread_client():
    """إنشاء اتصال آمن مع Google Sheets"""
    if "gcp_service_account" not in st.secrets:
        st.error("⚠️ خطأ: بيانات حساب الخدمة مفقودة في secrets.toml")
        return None
    
    try:
        # قراءة البيانات كقاموس
        creds_dict = dict(st.secrets["gcp_service_account"])
        
        # 🔥 خطوة هامة: إصلاح تنسيق المفتاح الخاص
        # نقوم باستبدال الرموز النصية \n بأسطر حقيقية ليعمل المفتاح
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
        st.error("⚠️ فشل الاتصال بخدمات جوجل. تأكد من صحة المفاتيح.")
        # طباعة الخطأ في الكونسول للمطور
        print(f"Connection Error: {e}")
        return None

def get_student_code_from_sheet():
    """جلب كود الطالب من ورقة التحكم"""
    client = get_gspread_client()
    if not client:
        return None
        
    try:
        sh = client.open(CONTROL_SHEET_NAME)
        # نفترض أن الكود في الورقة الأولى، الخلية B1
        sheet = sh.sheet1
        val = sheet.acell("B1").value
        return str(val).strip() if val else None
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"⚠️ الملف غير موجود: '{CONTROL_SHEET_NAME}'")
        st.warning("تأكد من مشاركة ملف الـ Google Sheet مع إيميل الخدمة (client_email).")
        return None
    except Exception as e:
        st.error("حدث خطأ أثناء قراءة البيانات.")
        return None

# =========================================================
# 4. إدارة الجلسة (Session State)
# =========================================================
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
# 5. واجهات التطبيق
# =========================================================

def show_login_page():
    """عرض صفحة تسجيل الدخول"""
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h1 style='text-align: center; color: #1f77b4;'>🧪 المعلم العلمي الذكي</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center;'>منصة التعليم التفاعلي</p>", 
