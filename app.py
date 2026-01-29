import streamlit as st
import sys
import os
import shutil
import importlib

st.set_page_config(page_title="أداة تشخيص الأخطاء", layout="wide", page_icon="🔧")

st.title("🔧 أداة تشخيص أخطاء التطبيق")
st.markdown("يقوم هذا الكود بفحص البيئة والمكتبات لتحديد سبب الخطأ.")

# ==========================================
# 1. فحص النظام (System Packages)
# ==========================================
st.header("1. فحص حزم النظام (Linux Packages)")
c1, c2 = st.columns(2)

with c1:
    st.write("**Tesseract OCR:**")
    tess_path = shutil.which("tesseract")
    if tess_path:
        st.success(f"موجود في: {tess_path}")
        try:
            ver = os.popen("tesseract --version").read().split()[1]
            st.info(f"الإصدار: {ver}")
        except:
            pass
    else:
        st.error("غير موجود! تأكد من ملف packages.txt")

with c2:
    st.write("**Poppler (pdf2image):**")
    pop_path = shutil.which("pdftoppm")
    if pop_path:
        st.success(f"موجود في: {pop_path}")
    else:
        st.error("غير موجود! تأكد من إضافة poppler-utils في packages.txt")

st.divider()

# ==========================================
# 2. فحص مكتبات بايثون (Python Libraries)
# ==========================================
st.header("2. فحص مكتبات بايثون والإصدارات")

libs_to_check = [
    "streamlit", "gspread", "langchain", "langchain_community", 
    "langchain_google_genai", "chromadb", "pytesseract", "pdf2image"
]

for lib in libs_to_check:
    try:
        mod = importlib.import_module(lib)
        ver = getattr(mod, "__version__", "Unknown")
        st.success(f"✅ {lib} : {ver}")
    except ImportError as e:
        st.error(f"❌ {lib} : غير مثبت ({e})")
    except Exception as e:
        st.warning(f"⚠️ {lib} : حدث خطأ أثناء التحقق ({e})")

st.divider()

# ==========================================
# 3. فحص استيراد LangChain (مصدر الخطأ)
# ==========================================
st.header("3. فحص استيرادات LangChain (Critical)")

st.write("محاولة استيراد `load_qa_chain` من مسارات مختلفة:")

paths_to_test = [
    "from langchain.chains.question_answering import load_qa_chain",
    "from langchain.chains import load_qa_chain",
    "from langchain_community.chains.question_answering import load_qa_chain",
]

for path in paths_to_test:
    try:
        exec(path)
        st.success(f"✅ نجح الاستيراد: `{path}`")
    except Exception as e:
        st.error(f"❌ فشل الاستيراد: `{path}` \nالسبب: {e}")

st.divider()

# ==========================================
# 4. فحص الأسرار (Secrets)
# ==========================================
st.header("4. فحص ملف الأسرار (Secrets.toml)")

required_secrets = [
    "TEACHER_NAME", "TEACHER_MASTER_KEY", "CONTROL_SHEET_NAME", 
    "DRIVE_FOLDER_ID", "GOOGLE_API_KEYS", "gcp_service_account"
]

missing = []
for sec in required_secrets:
    if sec not in st.secrets:
        missing.append(sec)

if not missing:
    st.success("✅ جميع الأسرار المطلوبة موجودة.")
else:
    st.error(f"❌ الأسرار التالية مفقودة: {missing}")

# فحص مفاتيح API
api_keys = st.secrets.get("GOOGLE_API_KEYS", [])
if isinstance(api_keys, str):
    st.info(f"تم العثور على مفاتيح Google API (String).")
elif isinstance(api_keys, list):
    st.info(f"تم العثور على {len(api_keys)} مفاتيح Google API.")
else:
    st.warning("⚠️ صيغة GOOGLE_API_KEYS غير متوقعة.")

st.divider()

# ==========================================
# 5. اختبار الاتصال (API Test)
# ==========================================
st.header("5. اختبار الاتصال بـ Google Gemini")
if st.button("بدء اختبار الاتصال"):
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        
        # جلب مفتاح
        keys = st.secrets.get("GOOGLE_API_KEYS", [])
        if isinstance(keys, str): keys = keys.split(",")
        if not keys: raise ValueError("لا توجد مفاتيح")
        
        llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", google_api_key=keys[0].strip())
        res = llm.invoke("Hello, reply with 'Connected' only.")
        st.success(f"✅ تم الاتصال بنجاح! الرد: {res.content}")
        
    except Exception as e:
        st.error(f"❌ فشل الاتصال: {e}")
