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

st.markdown("""
<style>
    .stApp { direction: rtl; text-align: right; }
    .stTextInput label, .stSelectbox label {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
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

# =========================================================
# 2. تحميل الأسرار
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
        st.error("⚠️ خطأ في الإعدادات: بيانات حساب الخدمة مفقودة.")
        return None
    
    try:
        # قراءة البيانات وتحويلها لقاموس
        creds_dict = dict(st.secrets["gcp_service_account"])
        
        # --- إصلاح مشكلة المفتاح الخاص ---
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        
        # تحديد النطاقات (Scopes) - يجب أن تكون المسافة البادئة هنا صحيحة داخل try
        scopes = [
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/spreadsheets",
        ]
        
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds)
        
    except Exception as e:
        print(f"DEBUG ERROR: {e}")
        st.error("⚠️ فشل الاتصال 
