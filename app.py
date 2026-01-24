import streamlit as st
from google.oauth2 import service_account
import gspread
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

# تحسين الواجهة لدعم العربية وتنسيق الأزرار
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
    }
    .stButton>button:hover {
        background-color: #0d47a1;
        color: white;
    }
    
    /* رسائل التنبيه */
    .stAlert {
        direction: rtl;
        text-align: right;
    }
</style>
""", unsafe_allow_html=True)

# =========================================================
# 2. تحميل الأسرار والثوابت
# =========================================================
TEACHER_MASTER_KEY = st.secrets.get("TEACHER_MASTER_KEY", "ADMIN_DEFAULT")
CONTROL_SHEET_NAME = st.secrets.get("CONTROL_SHEET_NAME", "App_Control")

# =========================================================
# 3. دوال الاتصال الخلفية (Backend Functions)
# =========================================================

@st.cache_resource
def get_gspread_client():
    """إنشاء اتصال آمن مع Google Sheets مع إصلاح مشكلة المفتاح"""
    if "gcp_service_account" not in st.secrets:
        st.error("⚠️ خطأ في الإعدادات: لم يتم العثور على بيانات حساب الخدمة.")
        return None
    
    try:
        # قراءة البيانات
        creds_dict = dict(st.secrets["gcp_service_account"])
        
        # --------------------------------------------------------
        # 🔥 إصلاح خطأ ASN1 Error (المفتاح الخاص) 🔥
        # هذا السطر يقوم بتحويل الرموز النصية \n إلى أسطر حقيقية
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        # --------------------------------------------------------

        scopes 
