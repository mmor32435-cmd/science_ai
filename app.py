import streamlit as st
from google.oauth2 import service_account
import gspread

st.set_page_config(page_title="فحص الاتصال", layout="wide")

st.markdown("""
<style>
    .stApp { direction: rtl; text-align: right; }
    .success-box { padding: 15px; background-color: #d4edda; border-radius: 10px; color: #155724; margin-bottom: 10px; }
    .error-box { padding: 15px; background-color: #f8d7da; border-radius: 10px; color: #721c24; margin-bottom: 10px; }
    .info-box { padding: 15px; background-color: #d1ecf1; border-radius: 10px; color: #0c5460; margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

st.title("🛠️ أداة كشف أخطاء كود الدخول")
st.write("تقوم هذه الأداة بفحص الاتصال بجوجل شيت وقراءة الكود المخزن لمقارنته.")
st.markdown("---")

# 1. عرض بيانات الاتصال
st.header("1. بيانات حساب الخدمة (Service Account)")

if "gcp_service_account" in st.secrets:
    creds_data = st.secrets["gcp_service_account"]
    client_email = creds_data.get("client_email", "غير موجود")
    
    st.code(client_email, language="text")
    st.warning(f"⚠️ هام جداً: هل قمت بعمل 'مشاركة' (Share) لملف الإكسل مع هذا الإيميل وجعلته Editor؟")
else:
    st.error("❌ لم يتم العثور على بيانات [gcp_service_account] في ملف secrets.toml")
    st.stop()

# 2. محاولة الاتصال
st.header("2. اختبار الاتصال بجوجل شيت")

try:
    # إصلاح المفتاح
    creds_dict = dict(st.secrets["gcp_service_account"])
    if "private_key" in creds_dict:
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    st.markdown('<div class="success-box">✅ تم الاتصال بسيرفرات جوجل بنجاح (Authentication Success).</div>', unsafe_allow_html=True)

    # 3. محاولة فتح الملف
    sheet_name = st.secrets.get("CONTROL_SHEET_NAME", "App_Control")
    st.write(f"📂 اسم الملف المطلوب: `{sheet_name}`")
    
    sh = client.open(sheet_name)
    st.markdown(f'<div class="success-box">✅ تم العثور على الملف: {sh.title}</div>', unsafe_allow_html=True)
    
    # 4. قراءة الكود
    sheet = sh.sheet1
    raw_val = sheet.acell("B1").value
    clean_val = str(raw_val).strip() if raw_val else "فارغ"
    
    st.header("3. فحص الكود المخزن")
    st.markdown(f'<div class="info-box">القيمة الموجودة في الخلية <b>B1</b> هي: <h2 style="text-align:center; color:blue;">"{raw_val}"</h2></div>', unsafe_allow_html=True)
    
    if raw_val is None:
        st.error("❌ الخلية B1 فارغة! الرجاء وضع كود داخلها في ملف الإكسل.")
    else:
        st.write("---")
        st.subheader("جرب كتابة الكود هنا للمقارنة:")
        user_input = st.text_input("اكتب الكود كما كنت تكتبه في التطبيق:")
        
        if user_input:
            if user_input == clean_val:
                st.success("✅ الكود متطابق تماماً! المشكلة تم حلها.")
            else:
                st.error("❌ غير متطابق!")
                col1, col2 = st.columns(2)
                with col1:
                    st.write("الكود في الإكسل:")
                    st.code(f"'{clean_val}'")
                with col2:
                    st.write("ما كتبته أنت:")
                    st.code(f"'{user_input}'")
                
                if len(user_input) != len(clean_val):
                    st.warning(f"طول الكود مختلف! (الإكسل: {len(clean_val)} حروف، أنت: {len(user_input)} حروف). ربما توجد مسافات زائدة؟")

except gspread.exceptions.SpreadsheetNotFound:
    st.error(f"❌ لم يتم العثور على ملف باسم '{sheet_name}'.")
    st.info("الاحتمالات:")
    st.write("1. اسم الملف في جوجل درايف مختلف (حرف زائد أو ناقص).")
    st.write("2. لم تقم بمشاركة الملف مع الإيميل الموضح في الأعلى.")

except Exception as e:
    st.error("❌ حدث خطأ غير متوقع:")
    st.code(str(e))
