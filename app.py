import streamlit as st
import gspread
from google.oauth2 import service_account
import google.generativeai as genai
from googleapiclient.discovery import build

st.set_page_config(page_title="وضع الفحص والصيانة", page_icon="🛠️", layout="wide")

st.title("🛠️ مركز صيانة التطبيق")
st.write("سيقوم هذا الكود بفحص كل الاتصالات لمعرفة سبب الخطأ بدقة.")

# 1. فحص الأسرار (Secrets)
st.header("1️⃣ فحص ملف الأسرار (Secrets)")
secrets_status = True

if "gcp_service_account" in st.secrets:
    st.success("✅ بيانات حساب الخدمة (JSON) موجودة.")
    # عرض الإيميل للتأكد منه
    client_email = st.secrets["gcp_service_account"]["client_email"]
    st.info(f"📧 **هذا هو إيميل الموظف الآلي:**\n\n`{client_email}`\n\n(تأكد أنك أضفته في زر المشاركة Share داخل ملف الإكسل والدرايف!)")
else:
    st.error("❌ بيانات gcp_service_account مفقودة!")
    secrets_status = False

if "GOOGLE_API_KEY" in st.secrets:
    st.success("✅ مفتاح الذكاء الاصطناعي موجود.")
else:
    st.error("❌ مفتاح GOOGLE_API_KEY مفقود!")
    secrets_status = False

if "DRIVE_FOLDER_ID" in st.secrets:
    st.success("✅ كود مجلد الدرايف موجود.")
else:
    st.error("❌ كود DRIVE_FOLDER_ID مفقود!")
    secrets_status = False

st.markdown("---")

# 2. فحص الاتصال بجوجل شيت (Google Sheets)
st.header("2️⃣ فحص ملف الإكسل (App_Control)")

if secrets_status:
    try:
        creds = service_account.Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        client = gspread.authorize(creds)
        
        # محاولة فتح الملف
        sheet_name = "App_Control"
        try:
            spreadsheet = client.open(sheet_name)
            st.success(f"✅ تم العثور على ملف '{sheet_name}' بنجاح!")
            
            # فحص الصفحة الأولى وقراءة الباسورد
            try:
                sheet1 = spreadsheet.sheet1
                val = sheet1.acell('B1').value
                if val:
                    st.success(f"✅ تمت قراءة الباسورد من الخلية B1: `{val}`")
                else:
                    st.warning("⚠️ الملف موجود، لكن الخلية B1 فارغة! اكتب فيها باسورد الطلاب.")
            except Exception as e:
                st.error(f"❌ مشكلة في الصفحة الأولى (Sheet1): {e}")

            # فحص صفحة Logs
            try:
                logs = spreadsheet.worksheet("Logs")
                st.success("✅ صفحة 'Logs' موجودة.")
            except:
                st.error("❌ صفحة 'Logs' غير موجودة! (أنشئ صفحة جديدة وسمّها Logs).")

            # فحص صفحة Activity
            try:
                act = spreadsheet.worksheet("Activity")
                st.success("✅ صفحة 'Activity' موجودة.")
            except:
                st.error("❌ صفحة 'Activity' غير موجودة! (أنشئ صفحة جديدة وسمّها Activity).")
                
        except gspread.SpreadsheetNotFound:
            st.error(f"❌ لم يتم العثور على ملف اسمه '{sheet_name}'.")
            st.warning("تأكد من الآتي:\n1. اسم الملف App_Control تماماً (بدون مسافات).\n2. أنك شاركت الملف مع الإيميل الموضح بالأعلى (Editor).")
            
    except Exception as e:
        st.error(f"❌ حدث خطأ في الاتصال: {e}")

st.markdown("---")

# 3. فحص جوجل درايف
st.header("3️⃣ فحص مجلد الكتب (Drive)")
if secrets_status:
    try:
        creds = service_account.Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        service = build('drive', 'v3', credentials=creds)
        folder_id = st.secrets["DRIVE_FOLDER_ID"]
        
        results = service.files().list(
            q=f"'{folder_id}' in parents",
            fields="files(id, name)").execute()
        files = results.get('files', [])
        
        if files:
            st.success(f"✅ الاتصال نجح! وجدت {len(files)} ملفات داخل المجلد.")
            for f in files:
                st.caption(f"📄 {f['name']}")
        else:
            st.warning("⚠️ الاتصال نجح، لكن المجلد فارغ (أو أنك لم تشاركه مع الإيميل).")
            
    except Exception as e:
        st.error(f"❌ خطأ في الدرايف: {e}")

st.markdown("---")
st.info("بعد إصلاح الأخطاء وظهور العلامات الخضراء ✅، أخبرني لأعطيك الكود النهائي.")
