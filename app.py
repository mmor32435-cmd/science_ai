import streamlit as st
from google.oauth2 import service_account
import google.generativeai as genai
import gspread
import time
import random
from PIL import Image

# =========================================================
# 1. إعدادات الصفحة والتصميم الاحترافي (UI/UX)
# =========================================================
st.set_page_config(
    page_title="AI Science Tutor | الأستاذ السيد البدوي",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# حقن CSS لتجميل الواجهة بالألوان والخطوط
st.markdown("""
<style>
    /* استيراد خط عربي جميل */
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Cairo', sans-serif;
        direction: rtl;
    }
    
    /* خلفية متدرجة هادئة */
    .stApp {
        background: linear-gradient(135deg, #fdfbfb 0%, #ebedee 100%);
    }

    /* كارت العنوان الرئيسي */
    .header-card {
        background: linear-gradient(90deg, #00C9FF 0%, #92FE9D 100%);
        padding: 20px;
        border-radius: 15px;
        color: #005c4b;
        text-align: center;
        margin-bottom: 25px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        border: 2px solid white;
    }
    .header-name-ar { font-size: 2.2em; font-weight: bold; margin: 0; }
    .header-name-en { font-size: 1.1em; font-weight: bold; margin-top: 5px; color: #004d40; }

    /* تحسين شكل الرسائل */
    .stChatMessage {
        background-color: white;
        border-radius: 15px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        border: 1px solid #eee;
    }
    
    /* الأزرار */
    .stButton>button {
        background: linear-gradient(45deg, #1fa2ff, #12d8fa, #a6ffcb);
        color: #005c4b;
        border: none;
        border-radius: 20px;
        font-weight: bold;
        transition: transform 0.2s;
    }
    .stButton>button:hover {
        transform: scale(1.02);
    }
</style>
""", unsafe_allow_html=True)

# بانر الاسم
st.markdown("""
<div class="header-card">
    <div class="header-name-ar">الأستاذ / السيد البدوي</div>
    <div class="header-name-en">Mr. Elsayed Elbadawy - Science Expert</div>
</div>
""", unsafe_allow_html=True)

# تحميل الثوابت
TEACHER_MASTER_KEY = st.secrets.get("TEACHER_MASTER_KEY", "ADMIN_DEFAULT")
CONTROL_SHEET_NAME = st.secrets.get("CONTROL_SHEET_NAME", "App_Control")
# =========================================================
# 2. المحرك الذكي (Backend Logic)
# =========================================================

@st.cache_resource
def get_gspread_client():
    if "gcp_service_account" not in st.secrets: return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds)
    except: return None

def get_student_code_from_sheet():
    client = get_gspread_client()
    if not client: return None
    try:
        sh = client.open(CONTROL_SHEET_NAME)
        return str(sh.sheet1.acell("B1").value).strip()
    except: return None

# إدارة بيانات الجلسة
if 'user_data' not in st.session_state:
    st.session_state.user_data = {
        "logged_in": False, "role": None, "name": "",
        "grade": "", "lang": "", "stage": ""
    }

# --- أهم دالة: اختيار الموديل المتاح تلقائياً ---
def get_best_available_model(api_key):
    try:
        genai.configure(api_key=api_key)
        # 1. جلب كل النماذج المتاحة للحساب
        models = genai.list_models()
        
        # 2. تصفية النماذج التي تدعم الشات (generateContent)
        chat_models = [m.name for m in models if 'generateContent' in m.supported_generation_methods]
        
        if not chat_models: return 'models/gemini-pro' # احتياطي
        
        # 3. محاولة العثور على Flash (الأسرع والأفضل للصور)
        for m in chat_models:
            if 'flash' in m.lower(): return m
            
        # 4. محاولة العثور على Pro
        for m in chat_models:
            if 'pro' in m.lower(): return m
            
        # 5. إذا لم يجد، يأخذ أول واحد متاح
        return chat_models[0]
    except:
        return 'models/gemini-pro'

def get_ai_response(user_text, image_data=None):
    try:
        keys = st.secrets.get("GOOGLE_API_KEYS", [])
        if not keys: return "⚠️ خطأ: المفاتيح غير موجودة."
        
        key = random.choice(keys)
        # اختيار الموديل ديناميكياً
        model_name = get_best_available_model(key)
        
        genai.configure(api_key=key)
        model = genai.GenerativeModel(model_name)
        
        # تعليمات المعلم (المنهج)
        u = st.session_state.user_data
        lang_note = "اشرح بالعربية." if "العربية" in u['lang'] else "Explain in English but clarify in Arabic."
        
        system_prompt = f"""
        أنت الأستاذ السيد البدوي، معلم علوم خبير.
        الطالب: {u['name']}، في {u['stage']} - {u['grade']}.
        اللغة: {u['lang']}.
        
        التعليمات:
        1. التزم بمنهج {u['grade']} بدقة.
        2. {lang_note}
        3. اكتب المعادلات الكيميائية بوضوح (LaTeX).
        4. كن مختصراً ومفيداً واسأل الطالب في النهاية للتأكد من فهمه.
        """
        
        content = [f"{system_prompt}\n\nسؤال الطالب: {user_text}"]
        if image_data:
            content.append(image_data)
            content[0] += "\n(يوجد صورة مرفقة، قم بحلها)."

        response = model.generate_content(content)
        return response.text
    except Exception as e:
        return f"خطأ تقني: {str(e)}"
       # =========================================================
# 3. واجهة التطبيق (Login & Chat)
# =========================================================

def show_login_page():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            st.markdown("### 🔐 تسجيل الدخول")
            name = st.text_input("الاسم الثلاثي")
            code = st.text_input("الكود السري", type="password")
            
            st.markdown("---")
            st.markdown("###### 📝 بياناتك الدراسية (لضبط المنهج)")
            col_a, col_b = st.columns(2)
            with col_a:
                stage = st.selectbox("المرحلة", ["الابتدائية", "الإعدادية", "الثانوية"])
                lang = st.selectbox("اللغة", ["العربية (علوم)", "English (Science)"])
            with col_b:
                grade = st.selectbox("الصف", [
                    "الصف الرابع", "الصف الخامس", "الصف السادس",
                    "الصف الأول", "الصف الثاني", "الصف الثالث"
                ])
            
            submit = st.form_submit_button("ابدأ التعلم 🚀")
            
            if submit:
                if code == TEACHER_MASTER_KEY:
                    st.session_state.user_data.update({"logged_in": True, "role": "Teacher", "name": name})
                    st.rerun()
                else:
                    db_code = get_student_code_from_sheet()
                    if db_code and code == db_code:
                        st.session_state.user_data.update({
                            "logged_in": True, "role": "Student", "name": name,
                            "stage": stage, "grade": grade, "lang": lang
                        })
                        st.rerun()
                    else:
                        st.error("الكود غير صحيح")

def show_main_app():
    # القائمة الجانبية
    with st.sidebar:
        u = st.session_state.user_data
        st.image("https://cdn-icons-png.flaticon.com/512/3408/3408755.png", width=70)
        st.markdown(f"### أهلاً، {u['name']}")
        st.info(f"📚 {u['grade']} | {u['lang']}")
        
        st.markdown("---")
        menu = st.radio("القائمة", ["💬 اسأل المعلم", "📝 اختبار سريع", "📊 تلخيص"])
        
        if st.button("خروج"):
            st.session_state.user_data["logged_in"] = False
            st.rerun()

    # المحتوى الرئيسي
    if menu == "💬 اسأل المعلم":
        st.markdown("#### 🧬 المساعد العلمي الذكي")
        
        # رفع صورة
        upl = st.file_uploader("📸 ارفع صورة مسألة (اختياري)", type=['png', 'jpg', 'jpeg'])
        img_data = Image.open(upl) if upl else None
        if img_data: st.image(img_data, width=200)

        # عرض المحادثة
        if "messages" not in st.session_state: st.session_state.messages = []
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]): st.write(msg["content"])

        # إدخال السؤال
        if prompt := st.chat_input("اكتب سؤالك هنا..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.write(prompt)
            
            with st.chat_message("assistant"):
                with st.spinner("جاري تحليل المنهج والإجابة..."):
                    resp = get_ai_response(prompt, img_data)
                    st.write(resp)
            st.session_state.messages.append({"role": "assistant", "content": resp})

    elif menu == "📝 اختبار سريع":
        st.header("🎯 بنك الأسئلة")
        if st.button("أنشئ لي اختباراً"):
            with st.spinner("جاري كتابة الأسئلة..."):
                q = get_ai_response("اكتب لي 3 أسئلة اختيار من متعدد في منهجي مع الحل.")
                st.markdown(q)

    elif menu == "📊 تلخيص":
        st.info("خدمة تلخيص الملفات قادمة قريباً...")

if __name__ == "__main__":
    if st.session_state.user_data["logged_in"]:
        show_main_app()
    else:
        show_login_page() 
