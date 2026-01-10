import streamlit as st

# ==========================================
# 1. إعدادات الصفحة
# ==========================================
st.set_page_config(page_title="AI Science Tutor", page_icon="🧬", layout="wide")

# ==========================================
# 2. استيراد المكتبات (داخل Try لتجنب الانهيار)
# ==========================================
try:
    import time
    import randomimport streamlit as st
import google.generativeai as genai

st.set_page_config(page_title="Model Scanner", layout="wide")
st.title("🔍 فحص النماذج المتاحة")

# 1. جلب المفاتيح
keys = st.secrets.get("GOOGLE_API_KEYS", [])
if not keys:
    st.error("لا توجد مفاتيح في secrets.toml")
    st.stop()

# 2. الفحص
st.write(f"تم العثور على {len(keys)} مفاتيح. جاري فحص ماذا يرون...")

for i, key in enumerate(keys):
    st.markdown(f"### 🔑 المفتاح رقم {i+1}")
    genai.configure(api_key=key)
    
    try:
        # محاولة جلب القائمة
        models = list(genai.list_models())
        
        if not models:
            st.warning("المفتاح يعمل، لكنه لا يرى أي نماذج! (تأكد من تفعيل Generative Language API)")
        else:
            found_any = False
            for m in models:
                # نتحقق هل النموذج يدعم التوليد
                if 'generateContent' in m.supported_generation_methods:
                    st.success(f"✅ متاح: **{m.name}**")
                    found_any = True
            
            if not found_any:
                st.warning("لم نجد نماذج تدعم الشات (generateContent).")
                
    except Exception as e:
        st.error(f"❌ خطأ في هذا المفتاح: {e}")
        if "403" in str(e):
            st.info("💡 نصيحة: تأكد أنك لست في دولة محظورة، أو أنك قمت بتفعيل API.")

st.markdown("---")
st.info("إذا ظهرت لك أسماء نماذج باللون الأخضر (مثل models/gemini-pro)، أخبرني بها لأعدل لك الكود.")
st.warning("إذا ظهرت كلها أخطاء، فهذا يعني أنك بحاجة لتفعيل الخدمة من رابط Google Cloud Console.")
    import google.generativeai as genai
    from streamlit_mic_recorder import mic_recorder
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    import gspread
    from io import BytesIO
    import PyPDF2
    import edge_tts
    import asyncio
    import speech_recognition as sr
except Exception as e:
    st.error(f"خطأ في استيراد المكتبات: {e}")
    st.stop()

# ==========================================
# 3. إعدادات الذكاء الاصطناعي (Gemini Pro)
# ==========================================
def get_ai_model():
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys: return None
    
    # اختيار مفتاح عشوائي
    key = random.choice(keys)
    genai.configure(api_key=key)
    
    # استخدام Gemini Pro لأنه الأضمن حالياً
    return genai.GenerativeModel('gemini-pro')

def get_vision_model():
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys: return None
    key = random.choice(keys)
    genai.configure(api_key=key)
    return genai.GenerativeModel('gemini-pro-vision')

# ==========================================
# 4. دوال الخدمات
# ==========================================
@st.cache_resource
def get_gspread_client():
    if "gcp_service_account" not in st.secrets: return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds)
    except: return None

def get_sheet_pass():
    client = get_gspread_client()
    if not client: return None
    try:
        # اسم الشيت والخلية
        return client.open("App_Control").sheet1.acell('B1').value
    except: return None

# ==========================================
# 5. الواجهة الرئيسية
# ==========================================
st.title("🧬 AI Science Tutor")

if "auth" not in st.session_state:
    st.session_state.auth = False
    st.session_state.msgs = []

# شاشة الدخول
if not st.session_state.auth:
    with st.form("login"):
        st.info("مرحباً بك في منصة العلوم الذكية")
        name = st.text_input("الاسم:")
        code = st.text_input("كود الدخول:", type="password")
        if st.form_submit_button("دخول"):
            real_pass = get_sheet_pass()
            if code == "ADMIN_2024" or (real_pass and code == str(real_pass).strip()):
                st.session_state.auth = True
                st.session_state.user_name = name
                st.success("تم الدخول!")
                time.sleep(1)
                st.rerun()
            else:
                st.error("الكود غير صحيح")
    st.stop()

# التطبيق
st.sidebar.success(f"أهلاً {st.session_state.user_name}")

# التبويبات
t1, t2 = st.tabs(["📝 سؤال نصي", "📷 سؤال مصور"])

with t1:
    q = st.chat_input("اكتب سؤالك في العلوم...")
    if q:
        # عرض سؤال الطالب
        with st.chat_message("user"):
            st.write(q)
        
        # المعالجة
        with st.chat_message("assistant"):
            with st.spinner("جاري التفكير..."):
                try:
                    model = get_ai_model()
                    if model:
                        resp = model.generate_content(f"Answer in Arabic. Role: Science Tutor. Question: {q}")
                        st.write(resp.text)
                    else:
                        st.error("مشكلة في الاتصال")
                except Exception as e:
                    st.error(f"خطأ: {e}")

with t2:
    up = st.file_uploader("ارفع صورة", type=["jpg", "png"])
    if up and st.button("تحليل الصورة"):
        st.image(up, width=200)
        with st.spinner("جاري تحليل الصورة..."):
            try:
                model = get_vision_model()
                img = Image.open(up)
                resp = model.generate_content(["اشرح هذه الصورة العلمية بالعربية", img])
                st.write(resp.text)
            except Exception as e:
                st.error(f"خطأ: {e}")
