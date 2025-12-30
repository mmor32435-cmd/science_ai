import streamlit as st
import time
import google.generativeai as genai
import asyncio
import edge_tts

# ===== 1. إعداد الصفحة والستايل =====
st.set_page_config(page_title="المعلم الذكي", page_icon="🎓", layout="centered")

# دالة لتوليد الصوت الطبيعي (Neural Voice)
async def generate_speech(text, output_file):
    # نختار صوت 'ar-EG-ShakirNeural' لأنه صوت عربي طبيعي وممتاز للتعليم
    # يمكنك تغييره إلى 'ar-SA-HamedNeural' للهجة السعودية
    communicate = edge_tts.Communicate(text, "ar-EG-ShakirNeural")
    await communicate.save(output_file)

# البحث الذكي عن الموديل (كما اتفقنا سابقاً لضمان العمل)
active_model_name = None
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
    
    available_models = []
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            available_models.append(m.name)
            
    if available_models:
        # تفضيل الموديلات السريعة والقوية
        priority_models = [m for m in available_models if 'flash' in m] + \
                          [m for m in available_models if 'pro' in m]
        active_model_name = priority_models[0] if priority_models else available_models[0]
        
        # --- التعديل الجوهري: إضافة تعليمات النظام (System Instruction) ---
        # هذه التعليمات هي التي ستغير شخصية الموديل
        system_instruction = """
        أنت معلم علوم محترف ومرح ومحبوب للطلاب اسمه 'المستشار الذكي'.
        جمهورك هم طلاب الصف الأول الثانوي (سن 15-16 سنة).
        أسلوبك في الحديث:
        1. تحدث باللغة العربية الفصحى البسيطة والواضحة جداً (ابتعد عن الكلمات المعقدة).
        2. كن مهذباً جداً ومشجعاً (استخدم عبارات مثل: يا بطل، سؤال ذكي، أحسنت).
        3. استخدم التشبيهات الممتعة من الحياة اليومية لتبسيط العلوم.
        4. اجعل الإجابة قصيرة ومركزة ومقسمة لنقاط.
        5. استخدم الإيموجي المناسب 🌟 لتجعل النص حياً.
        """
        
        model = genai.GenerativeModel(active_model_name, system_instruction=system_instruction)
    else:
        st.error("⚠️ لا توجد موديلات متاحة.")
        st.stop()

except Exception as e:
    st.error(f"⚠️ خطأ في الاتصال: {e}")
    st.stop()

# ===== 2. واجهة التطبيق =====
st.title("🎓 مساعد العلوم المتكاملة – أولى ثانوي")

# ===== 3. تسجيل الدخول =====
password = st.text_input("🔑 كلمة المرور", type="password")
if password != "SCIENCE60":
    if password: st.warning("⛔ كلمة المرور خطأ")
    st.stop()
st.success("أهلاً بك يا بطل! 🚀")

# ===== 4. العداد =====
if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()
elapsed = time.time() - st.session_state.start_time
remaining = 3600 - elapsed
if remaining <= 0:
    st.error("انتهى الوقت!"); st.stop()
st.info(f"⏳ باقي من الوقت: {int(remaining//60)} دقيقة")

# ===== 5. الشات والصوت المتطور =====
st.markdown("---")
st.subheader("💡 اسأل معلمك الخاص")

question = st.text_area("اكتب سؤالك هنا:", placeholder="مثال: لماذا السماء زرقاء؟")

if st.button("شرح السؤال 🎙️"):
    if not question.strip():
        st.warning("اكتب سؤالاً أولاً يا صديقي!")
    else:
        with st.spinner("🤖 المستشار الذكي يفكر ويجهز صوته..."):
            try:
                # 1. الحصول على الإجابة النصية (بالشخصية الجديدة)
                response = model.generate_content(question)
                answer_text = response.text
                
                st.markdown("### 📘 الإجابة:")
                st.write(answer_text)
                
                # 2. توليد الصوت الطبيعي
                output_sound_file = "response.mp3"
                # تشغيل الدالة بشكل غير متزامن
                asyncio.run(generate_speech(answer_text, output_sound_file))
                
                # 3. عرض المشغل
                st.audio(output_sound_file, format='audio/mp3')
                
            except Exception as e:
                st.error(f"حدث خطأ تقني: {e}")
