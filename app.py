import streamlit as st
from google.oauth2 import service_account
import gspread

st.set_page_config(page_title="فحص الاتصال", layout="wide")

st.title("🛠️ صفحة فحص الاتصال بخدمات جوجل")
st.markdown("---")

# 1. فحص وجود ملف الأسرار
st.header("1. فحص ملف الأسرار (Secrets)")
if "gcp_service_account" in st.secrets:
    st.success("✅ تم العثور على قسم [gcp_service_account] في ملف الأسرار.")
    secrets_found = True
    
    # عرض جزء من البيانات للتأكد (للأمان نعرض أول وآخر حرف فقط)
    creds = dict(st.secrets["gcp_service_account"])
    email = creds.get("client_email", "غير موجود")
    st.write(f"📧 **الإيميل المستخدم:** `{email}`")
    
    pk = creds.get("private_key", "")
    if pk:
        st.write(f"🔑 **المفتاح الخاص:** تم العثور عليه (الطول: {len(pk)})")
        if "-----BEGIN PRIVATE KEY-----" in pk:
            st.success("✅ بداية المفتاح صحيحة.")
        else:
            st.error("❌ بداية المفتاح خاطئة! يجب أن يبدأ بـ -----BEGIN PRIVATE KEY-----")
    else:
        st.error("❌ المفتاح الخاص (private_key) مفقود!")

else:
    st.error("❌ لم يتم العثور على قسم [gcp_service_account] في ملف secrets.toml")
    secrets_found = False

st.markdown("---")

# 2. محاولة الاتصال الفعلي
if secrets_found:
    st.header("2. محاولة الاتصال بجوجل (Connection Test)")
    
    try:
        # إصلاح المفتاح
        creds_dict = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        
        with st.spinner("جاري الاتصال بسيرفرات جوجل..."):
            creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scopes)
            client = gspread.authorize(creds)
            st.success("✅ **تم الاتصال بسيرفرات جوجل بنجاح!** (Authentication Successful)")
            
            # محاولة فتح الملف
            sheet_name = st.secrets.get("CONTROL_SHEET_NAME", "App_Control")
            st.write(f"📂 محاولة فتح الملف: `{sheet_name}`")
            
            sh = client.open(sheet_name)
            st.success(f"✅ **تم الوصول للملف بنجاح!** العنوان: {sh.title}")
            
            val = sh.sheet1.acell("B1").value
            st.info(f"🔢 **قيمة الكود الموجودة في الخلية B1 هي:** {val}")
            
    except Exception as e:
        st.error("❌ فشل الاتصال! انظر التفاصيل بالأسفل:")
        st.code(str(e), language="python")
        
        # تحليل الخطأ للمستخدم
        err_msg = str(e)
        if "SpreadsheetNotFound" in err_msg:
            st.warning("💡 الحل: تأكد من أنك قمت بمشاركة (Share) ملف الإكسل مع الإيميل الموضح بالأعلى.")
        elif "invalid_grant" in err_msg or "ASN1" in err_msg:
            st.warning("💡 الحل: المفتاح الخاص (Private Key) غير صحيح. انسخه مرة أخرى بدقة من ملف JSON.")
