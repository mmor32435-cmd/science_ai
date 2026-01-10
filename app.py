# ==========================================
# استبدل دالة get_working_model القديمة بهذه الدالة التشخيصية
# ==========================================
def get_working_model():
    # 1. التأكد من قراءة المفاتيح
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys:
        st.error("❌ الخطأ: لم يتم العثور على قائمة GOOGLE_API_KEYS في ملف secrets.toml")
        return None

    st.toast(f"جاري تجربة {len(keys)} مفاتيح...", icon="🔑")

    # 2. تجربة المفاتيح والموديلات
    models = ['gemini-1.5-flash', 'gemini-pro']

    for i, key in enumerate(keys):
        genai.configure(api_key=key)
        for model_name in models:
            try:
                model = genai.GenerativeModel(model_name)
                # محاولة توليد نص بسيط للتأكد من العمل
                model.generate_content("Test")
                return model # نجاح!
            except Exception as e:
                # طباعة الخطأ بالتفصيل لنعرف السبب
                error_msg = str(e)
                st.warning(f"⚠️ فشل المفتاح رقم {i+1} مع {model_name}")
                st.code(error_msg, language="text")
                
                # تحليل سريع للخطأ
                if "404" in error_msg:
                    st.error("التشخيص: المكتبة قديمة. يجب عمل Reboot للتطبيق.")
                elif "400" in error_msg:
                    st.error("التشخيص: المفتاح غير صالح (INVALID_API_KEY).")
                elif "429" in error_msg:
                    st.error("التشخيص: انتهى رصيد المفتاح (Quota Exceeded).")
                
                continue

    st.error("❌ فشلت جميع المحاولات. راجع الأخطاء الصفراء أعلاه.")
    return None
