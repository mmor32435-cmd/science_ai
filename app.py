import streamlit as st
from google.oauth2 import service_account
import google.generativeai as genai
import gspread
import time
import random
import os
import base64
from PIL import Image

# =========================================================
# 1. إعدادات الصفحة والتصميم الفائق (Super UI/UX)
# =========================================================
st.set_page_config(
    page_title="AI Science Tutor | الأستاذ السيد البدوي",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# حقن CSS احترافي لتغيير شكل التطبيق بالكامل
st.markdown("""
<style>
    /* استيراد خطوط عربية جميلة */
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Cairo', sans-serif;
        direction: rtl;
    }
    
    /* خلفية متدرجة عصرية */
    .stApp {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    }

    /* تصميم كارت العنوان */
    .header-card {
        background: linear-gradient(90deg, #1CB5E0 0%, #000851 100%);
        padding: 20px;
        border-radius: 15px;
        color: white;
        text-align: center;
        margin-bottom: 20px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
    }
    .header-name-ar { font-size: 2.5em; font-weight: bold; margin: 0; }
    .header-name-en { font-size: 1.2em; font-weight: 300; margin-top: 5px; color: #e0e0e0; }

    /* تحسين فقاعات المحادثة */
    .stChatMessage {
        border-radius: 15px;
        padding: 10px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
    
    /* تنسيق المعادلات الكيميائية */
    .katex { font-size: 1.2em; color: #000851; }

    /* الأزرار */
    .stButton>button {
        background: linear-gradient(45deg, #11998e, #38ef7d);
        color: white;
        border: none;
        border-radius: 25px;
        font-weight: bold;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        transform: scale(1.05);
        box-shadow: 0 5px 15px rgba(0,0,0,0.2);
    }
</style>
""", unsafe_allow_html=True)

# عرض بانر الاسم المميز
st.markdown("""
<div class="header-card">
    <div class="header-name-ar">الأستاذ / السيد البدوي</div>
    <div class="header-name-en">Mr. Elsayed Elbadawy - Expert Science Tutor</div>
</div>
""", unsafe_allow_html=True)

# تحميل الثوابت
TEACHER_MASTER_KEY = st.secrets.get("TEACHER_MASTER_KEY", "ADMIN_DEFAULT")
CONTROL_SHEET_NAME = st.secrets.get("CONTROL_SHEET_NAME", "App_Control")
# =========================================================
# 2. المحرك الذكي (The Brain) والاتصال
# =========================================================

@st.cache_resource
def get_gspread_client():
    if "gcp_service_account" not in st.secrets: return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        
        scopes = ["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/spreadsheets"]
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

# إدارة الجلسة والبيانات الدراسية
if 'user_data' not in st.session_state:
    st.session_state.user_data = {
        "logged_in": False, "role": None, "name": "",
        "grade": "الصف الأول الإعدادي", "lang": "العربية", "stage": "الإعدادية"
    }

def get_ai_response(user_text, image_data=None):
    """دالة ذكية تحلل النص والصورة وتجيب حسب المنهج"""
    try:
        keys = st.secrets.get("GOOGLE_API_KEYS", [])
        if not keys: return "⚠️ خطأ: المفاتيح مفقودة."
        
        genai.configure(api_key=random.choice(keys))
        
        # استخدام نموذج Flash لأنه يدعم الصور والنصوص وسريع
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # بناء الشخصية (System Prompt) بناءً على بيانات الطالب
        u = st.session_state.user_data
        lang_instruction = "اشرح باللغة العربية." if u['lang'] == "العربية" else "Explain in English but clarify difficult terms in Arabic."
        
        system_prompt = f"""
        أنت الأستاذ السيد البدوي، معلم خبير.
        الطالب في المرحلة: {u['stage']}، الصف: {u['grade']}.
        يدرس العلوم باللغة: {u['lang']}.
        
        القواعد الصارمة:
        1. التزم بمنهج هذا الصف تحديداً ولا تخرج عنه.
        2. {lang_instruction}
        3. اكتب المعادلات الكيميائية والرموز داخل علامة $ لتظهر بشكل جميل (LaTeX).
        4. كن مختصراً ومفيداً، وفي نهاية الإجابة اسأل الطالب: "هل تحتاج تفاصيل أكثر أم ننتقل لنقطة أخرى؟".
        5. كن مرحاً ومشجعاً.
        """
        
        # تجهيز المدخلات (نص + صورة)
        content = [f"{system_prompt}\n\nسؤال الطالب: {user_text}"]
        if image_data:
            content.append(image_data)
            content[0] += "\n(قام الطالب بإرفاق صورة، قم بتحليلها وحل ما فيها بناءً على منهجه)."

        response = model.generate_content(content)
        return response.text
    except Exception as e:
        return f"حدث خطأ تقني: {str(e)}"
       # =========================================================
# 3. واجهة التطبيق التفاعلية
# =========================================================

def show_login_page():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            st.markdown("### 🔐 تسجيل الدخول")
            name = st.text_input("الاسم الثلاثي")
            code = st.text_input("الكود السري", type="password")
            
            # بيانات الطالب الإضافية (تظهر فقط للطلاب)
            st.markdown("---")
            st.markdown("### 📝 بياناتك الدراسية")
            col_a, col_b = st.columns(2)
            with col_a:
                stage = st.selectbox("المرحلة", ["الابتدائية", "الإعدادية", "الثانوية"])
                study_lang = st.selectbox("لغة الدراسة", ["العربية (علوم)", "English (Science)"])
            with col_b:
                grade = st.selectbox("الصف الدراسي", [
                    "الصف الرابع", "الصف الخامس", "الصف السادس",
                    "الصف الأول", "الصف الثاني", "الصف الثالث"
                ])
            
            submit = st.form_submit_button("بدء الرحلة التعليمية 🚀")
            
            if submit:
                if code == TEACHER_MASTER_KEY:
                    st.session_state.user_data.update({"logged_in": True, "role": "Teacher", "name": name})
                    st.rerun()
                else:
                    db_code = get_student_code_from_sheet()
                    if db_code and code == db_code:
                        st.session_state.user_data.update({
                            "logged_in": True, "role": "Student", "name": name,
                            "stage": stage, "grade": grade, "lang": study_lang
                        })
                        st.rerun()
                    else:
                        st.error("بيانات الدخول غير صحيحة")

def show_main_app():
    # الشريط الجانبي الذكي
    with st.sidebar:
        u = st.session_state.user_data
        st.image("https://cdn-icons-png.flaticon.com/512/3408/3408755.png", width=80)
        st.title(f"أهلاً {u['name']}")
        st.info(f"📚 {u['grade']} | {u['lang']}")
        
        st.markdown("---")
        action = st.radio("الأدوات", ["💬 اسأل المعلم", "📝 اختبرني (Quiz)", "📊 ملخص الدرس"])
        
        if st.button("تسجيل الخروج"):
            st.session_state.user_data["logged_in"] = False
            st.rerun()

    # الواجهة الرئيسية
    if action == "💬 اسأل المعلم":
        st.markdown("### 🧬 غرفة النقاش العلمي")
        
        # رفع صورة
        uploaded_img = st.file_uploader("📸 ارفع صورة مسألة أو معادلة لتحليلها", type=["jpg", "png"])
        image_part = None
        if uploaded_img:
            st.image(uploaded_img, width=200, caption="الصورة المرفقة")
            image_part = Image.open(uploaded_img)

        # سجل المحادثة
        if "messages" not in st.session_state: st.session_state.messages = []
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                # معالجة المعادلات الرياضية في النص
                st.markdown(msg["content"]) # يدعم LaTeX تلقائياً

        # المدخلات (نص + ميكروفون تخيلي)
        col_in1, col_in2 = st.columns([5, 1])
        with col_in2:
             # زر محاكاة الميكروفون (في التحديث القادم سنضيف التسجيل الفعلي)
             st.button("🎙️", help="تسجيل صوتي (قريباً)")
        
        with col_in1:
            prompt = st.chat_input("اكتب سؤالك هنا...")

        if prompt or (uploaded_img and prompt):
            # إضافة سؤال المستخدم
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.markdown(prompt)
            
            # الإجابة
            with st.chat_message("assistant"):
                with st.spinner("جاري استحضار المعلومات من المنهج..."):
                    response = get_ai_response(prompt, image_part)
                    st.markdown(response)
                    
                    # قراءة صوتية (اختياري - Placeholder)
                    # st.audio(generate_audio(response)) 
            
            st.session_state.messages.append({"role": "assistant", "content": response})

    elif action == "📝 اختبرني (Quiz)":
        st.header("🎯 بنك الأسئلة الذكي")
        if st.button("أنشئ اختباراً قصيراً على ما سبق"):
            with st.spinner("جاري إعداد الأسئلة..."):
                quiz = get_ai_response("أنشئ لي 3 أسئلة اختيار من متعدد بناءً على منهجي الحالي مع الحل في النهاية.")
                st.markdown(quiz)

    elif action == "📊 ملخص الدرس":
        st.header("📌 الخرائط الذهنية")
        st.info("ارفع ملف الدرس (PDF) لتلخيصه هنا (سيتم تفعيل الربط مع الدرايف في الخطوة القادمة).")

if __name__ == "__main__":
    if st.session_state.user_data["logged_in"]:
        show_main_app()
    else:
        show_login_page() 
