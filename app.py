import streamlit as st
import google.generativeai as genai

# إعداد الصفحة
st.set_page_config(page_title="فاحص الموديلات", page_icon="🔍")
st.title("🔍 أداة كشف موديلات Gemini المتاحة")

# جلب المفاتيح من secrets
api_keys = st.secrets.get("GOOGLE_API_KEYS", [])
if isinstance(api_keys, str):
    api_keys = [k.strip() for k in api_keys.split(",")]

if not api_keys:
    st.error("❌ لا توجد مفاتيح API في ملف الأسرار (secrets.toml).")
    st.stop()

# زر الفحص
if st.button("🚀 ابدأ الفحص"):
    st.write(f"تم العثور على {len(api_keys)} مفتاح/مفاتيح. جاري الفحص...")
    
    for i, key in enumerate(api_keys):
        st.divider()
        st.subheader(f"🔑 المفتاح رقم {i+1}")
        
        try:
            genai.configure(api_key=key)
            
            # جلب القائمة
            models = list(genai.list_models())
            
            # تصفية الموديلات التي تدعم الشات (generateContent)
            chat_models = []
            for m in models:
                if 'generateContent' in m.supported_generation_methods:
                    chat_models.append(m.name)
            
            if chat_models:
                st.success(f"✅ الموديلات الصالحة للشات ({len(chat_models)}):")
                for m in chat_models:
                    st.code(m, language="text")
            else:
                st.warning("⚠️ هذا المفتاح لا يملك صلاحية الوصول لأي موديل شات!")
                
        except Exception as e:
            st.error(f"❌ حدث خطأ مع هذا المفتاح: {e}")

st.info("💡 انسخ أحد الأسماء التي ستظهر باللون الأخضر (مثل models/gemini-pro) واستخدمه في تطبيقك.")
