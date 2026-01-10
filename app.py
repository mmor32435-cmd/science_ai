import streamlit as st
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
