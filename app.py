import streamlit as st
from google.oauth2 import service_account
import gspread
import time

# =========================================================
# 1. إعدادات الصفحة والتصميم (Page Config)
# =========================================================
st.set_page_config(
    page_title="المعلم العلمي الذكي",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# تحسين التصميم للغة العربية
st.markdown("""
<style>
    .stApp { direction: rtl; text-align: right; }
    .stTextInput label, .stSelectbox label {
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
    
    /* أزرار أنيقة */
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

# =========================================================
# 2. تحميل الثوابت (Secrets)
# =========================================================
TEACHER_MASTER_KEY = st.secrets.get("TEACHER_MASTER_KEY", "ADMIN_DEFAULT")
CONTROL_SHEET_NAME = st.secrets.get("CONTROL_SHEET_NAME", "App_Control")

# =========================================================
# 3. دوال الاتصال الخلفية (Backend)
# =========================================================

@st.cache_resource
def get_gspread_client():
    """إنشاء اتصال مع Google Sheets مع معالجة الأخطاء"""
    # 1. التأكد من وجود البيانات
    if "gcp_service_account" not in st.secrets:
        st.error("⚠️ خطأ حرج: بيانات [gcp_service_account] مفقودة في ملف secrets.toml")
        return 
