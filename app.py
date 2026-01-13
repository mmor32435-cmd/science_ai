import streamlit as st
from google.oauth2 import service_account
import gspread

st.set_page_config(page_title="AI Science Tutor - Debug", layout="wide")

TEACHER_MASTER_KEY = st.secrets.get("TEACHER_MASTER_KEY", "ADMIN_2024")
CONTROL_SHEET_NAME = st.secrets.get("CONTROL_SHEET_NAME", "App_Control")

@st.cache_resource
def get_gspread_client():
    if "gcp_service_account" not in st.secrets:
        return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        scopes = [
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/spreadsheets",
        ]
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        st.error("Service account error:")
        st.exception(e)
        return None

def get_student_code_from_sheet():
    client = get_gspread_client()
    if not client:
        return None
    try:
        sh = client.open(CONTROL_SHEET_NAME)
        v = sh.sheet1.acell("B1").value
        return str(v).strip() if v is not None else None
    except Exception as e:
        st.error("Google Sheet error:")
        st.exception(e)
        return None

st.title("AI Science Tutor - Login (Debug)")

with st.expander("Diagnostics", expanded=True):
    st.write("CONTROL_SHEET_NAME:", CONTROL_SHEET_NAME)
    st.write("Has gcp_service_account:", "gcp_service_account" in st.secrets)
    if "gcp_service_account" in st.secrets:
        sa = dict(st.secrets["gcp_service_account"])
        st.write("client_email:", sa.get("client_email", ""))
        pk = str(sa.get("private_key", "")).strip()
        st.write("Has private_key:", bool(pk))
        st.write("private_key starts with BEGIN:", pk.startswith("-----BEGIN PRIVATE KEY-----"))

name = st.text_input("الاسم")
code = st.text_input("الكود", type="password")

if st.button("دخول"):
    is_teacher = (code == TEACHER_MASTER_KEY)
    db_pass = get_student_code_from_sheet()

    if db_pass is None and not is_teacher:
        st.error("تعذر الاتصال بقاعدة أكواد الطلاب (Google Sheet).")
    else:
        is_student = (db_pass is not None and code == db_pass)
        if is_teacher or is_student:
            st.success("تم الدخول بنجاح")
        else:
            st.error("الكود غير صحيح")
