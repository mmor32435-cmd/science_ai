import streamlit as st
import time
import google.generativeai as genai
import asyncio
import edge_tts
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder
from io import BytesIO
import re
from datetime import datetime
import pytz
from PIL import Image
import PyPDF2
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ==========================================
# 🎛️ إعدادات التحكم
# ==========================================

TEACHER_MASTER_KEY = "ADMIN_2024"  # كلمة سر المعلم
DAILY_STUDENT_PASS = "SCIENCE_DAY1" # كلمة سر الطلاب
MY_TIMEZONE = 'Africa/Cairo'
ALLOWED_HOURS = [17, 19, 21] # الساعة 5، 7، 9

# جلب كود المجلد من الإعدادات
DRIVE_FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "") 

st.set_page_config(page_title="Science AI Pro", page_icon="🧬", layout="wide")

# --- التحقق من الدخول ---
def check_access(password):
    if password == TEACHER_MASTER_KEY:
        return True, "👨‍🏫 مرحباً أستاذي! (وصول كامل)", "teacher"
    
    if password == DAILY_STUDENT_PASS:
        tz = pytz.timezone(MY_TIMEZONE)
        now = datetime.now(tz)
        if now.hour in ALLOWED_HOURS:
            remaining = 60 - now.minute
            return True, f"✅ أهلاً بك يا بطل. متبقي {remaining} دقيقة.", "student"
        else:
            return False, "⏳ المنصة مغلقة حالياً. المواعيد: 5-6م، 7-8م، 9-10م.", "student"
    
    return False, "⛔ كلمة المرور غير صحيحة.", "none"

# --- دوال جوجل درايف ---
def get_drive_service():
    # هنا نقرأ البيانات الصحيحة من Secrets مباشرة
    if "gcp_service_account" in st.secrets:
        try:
            creds = service_account.Credentials.from_service_account_info(
                st.secrets["gcp_service_account"],
                scopes=['https://www.googleapis.com/auth/drive.readonly']
            )
            return build('drive', 'v3', credentials=creds)
        except Exception as e:
            st.error(f"خطأ في قراءة مفتاح الخدمة: {e}")
            return None
    return None

def list_drive_files(service, folder_id):
    try:
        results = service.files().list(
            q=f"'{folder_id}' in parents and mimeType='application/pdf'",
            fields="nextPageToken, files(id, name)").execute()
        return results.get('files', [])
    except Exception as e:
        st.error(f"خطأ في الوصول للمجلد: {e}")
        return []

def download_pdf_text(service, file_id):
    try:
        request = service.files().get_media(fileId=file_id)
        file_io = BytesIO()
        downloader = MediaIoBaseDownload(file_io, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        
        file_io.seek(0)
        reader = PyPDF2.PdfReader(file_io)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        return f"Error reading PDF: {e}"

# --- دوال الصوت واللغة ---
def get_voice_config(lang):
    if lang == "English":
        return "en-US-AndrewNeural", "en-US"
    else:
        return "ar-EG-ShakirNeural", "ar-EG"

async def generate_speech(text, output_file, voice_code):
    clean_text = re.sub(r'[\*\#\-\_]', '', text)
    communicate = edge_tts.Communicate(clean_text, voice_code)
    await communicate.save(output_file)

def speech_to_text(audio_bytes, lang_code):
    r = sr.Recognizer()
    try:
        audio_file = sr.AudioFile(BytesIO(audio_bytes))
        with audio_file as source:
            r.adjust_for_ambient_noise(source)
            audio_data = r.record(source)
            text = r.recognize_google(audio_data, language=lang_code)
            return text
    except:
        return None

# --- إعداد Gemini ---
try:
    if "GOOGLE_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
        model = genai.GenerativeModel('gemini-1.5-flash')
    else:
        st.error("مفتاح GOOGLE_API_KEY غير موجود في Secrets")
        st.stop()
except:
    st.error("خطأ في الاتصال بالذكاء الاصطناعي"); st.stop()


# ==========================================
# ===== واجهة التطبيق =====
# ==========================================

# --- شاشة تسجيل الدخول ---
if "auth_status" not in st.session_state:
    st.session_state.auth_status = False
    st.session_state.user_type = "none"

if not st.session_state.auth_status:
    st.title("🔐 Science AI Platform")
    pwd = st.text_input("Password / كلمة المرور:", type="password")
    if st.button("Enter / دخول"):
        allowed, msg, u_type = check_access(pwd)
        if allowed:
            st.session_state.auth_status = True
            st.session_state.user_type = u_type
            st.success(msg)
            time.sleep(1)
            st.rerun()
        else:
            st.error(msg)
    st.stop()

# --- الشريط الجانبي (الإعدادات) ---
with st.sidebar:
    st.header("⚙️ Settings / الإعدادات")
    
    # 1. اختيار اللغة
    language = st.radio("Language / اللغة:", ["العربية", "English"])
    lang_code = "ar-EG" if language == "العربية" else "en-US"
    voice_code, sr_lang = get_voice_config(language)
    
    st.markdown("---")
    
    # 2. المكتبة (جوجل درايف)
    st.subheader("📚 Reference Books / المكتبة")
    reference_text = ""
    
    if DRIVE_FOLDER_ID:
        service = get_drive_service()
        if service:
            files = list_drive_files(service, DRIVE_FOLDER_ID)
            if files:
                selected_file_name = st.selectbox("Select Book / اختر كتاباً:", [f['name'] for f in files])
                selected_file_id = next(f['id'] for f in files if f['name'] == selected_file_name)
                
                if st.button("Load Book / تحميل الكتاب"):
                    with st.spinner("Downloading & Reading..."):
                        reference_text = download_pdf_text(service, selected_file_id)
                        st.session_state.ref_text = reference_text
                        st.success(f"تم تحميل {selected_file_name}!")
            else:
                st.warning("المجلد فارغ أو الكود خطأ.")
        else:
            st.warning("لم يتم الاتصال بجوجل درايف. تأكد من Secrets.")
    
    if "ref_text" in st.session_state:
        reference_text = st.session_state.ref_text
        st.info("✅ تم تفعيل مرجع الكتاب")

# --- الواجهة الرئيسية ---
st.title("🧬 AI Science Tutor")
st.caption("Physics | Chemistry | Biology | General Science")

# التبويبات
tab_voice, tab_text, tab_upload = st.tabs(["🎙️ Voice / صوت", "✍️ Chat / كتابة", "📁 Upload / ملفات"])
user_input = ""
input_mode = "text"

# 1. الصوت
with tab_voice:
    st.write("Click to speak / اضغط للتحدث:")
    audio_in = mic_recorder(start_prompt="🎤 Speak", stop_prompt="⏹️ Stop", key='mic', format="wav")
    if audio_in:
        with st.spinner("Listening..."):
            user_input = speech_to_text(audio_in['bytes'], sr_lang)
            if user_input: st.success(f"You said: {user_input}")

# 2. الكتابة
with tab_text:
    txt_in = st.text_area("Type your question / اكتب سؤالك:")
    if st.button("Send / إرسال"):
        user_input = txt_in

# 3. رفع ملفات
with tab_upload:
    up_file = st.file_uploader("Upload Image or PDF", type=['png', 'jpg', 'pdf'])
    up_q = st.text_input("Question about file:")
    if st.button("Analyze / تحليل") and up_file:
        if up_file.type == 'application/pdf':
             pdf_reader = PyPDF2.PdfReader(up_file)
             extracted = ""
             for p in pdf_reader.pages: extracted += p.extract_text()
             user_input = f"PDF Content:\n{extracted}\n\nQuestion: {up_q}"
        else:
            image = Image.open(up_file)
            st.image(image, width=300)
            user_input = [up_q if up_q else "Explain this image", image]
            input_mode = "image"

# --- المعالجة ---
if user_input:
    with st.spinner("Thinking... / جاري التحليل..."):
        try:
            role_lang = "Arabic" if language == "العربية" else "English"
            
            system_prompt = f"""
            You are a professional Science Tutor. Language: {role_lang}.
            Instructions:
            1. Answer strictly in {role_lang}.
            2. Explain simply and clearly.
            3. Use the Reference Book Context below if relevant.
            
            Reference Context:
            {reference_text[:50000] if reference_text else "No reference loaded."}
            """
            
            if input_mode == "image":
                response = model.generate_content([system_prompt, user_input[0], user_input[1]])
            else:
                response = model.generate_content(f"{system_prompt}\n\nUser Question: {user_input}")
            
            st.markdown("---")
            st.markdown(f"### 💡 Answer / الإجابة:\n{response.text}")
            
            out_audio = "resp.mp3"
            asyncio.run(generate_speech(response.text, out_audio, voice_code))
            st.audio(out_audio, format='audio/mp3', autoplay=True)
            
        except Exception as e:
            st.error(f"Error: {e}")
