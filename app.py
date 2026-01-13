import streamlit as st

# ==========================================
# 1. إعدادات الصفحة
# ==========================================
st.set_page_config(page_title="AI Science Tutor Pro", page_icon="🧬", layout="wide")

import time
import asyncio
import re
import random
import threading
from io import BytesIO
from datetime import datetime
import pytz

# المكتبات الخارجية
import google.generativeai as genai
import edge_tts
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder
from PIL import Image
import PyPDF2
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import gspread
import pandas as pd

# ==========================================
# 🎛️ الثوابت (تقرأ من secrets مع قيم افتراضية)
# ==========================================
TEACHER_MASTER_KEY = st.secrets.get("TEACHER_MASTER_KEY", "ADMIN_2024")
CONTROL_SHEET_NAME = st.secrets.get("CONTROL_SHEET_NAME", "App_Control")
SESSION_DURATION_MINUTES = int(st.secrets.get("SESSION_DURATION_MINUTES", 60))
DRIVE_FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "")

DAILY_FACTS = [
    "هل تعلم؟ المخ يولد كهرباء تكفي لمصباح! 💡",
    "هل تعلم؟ العظام أقوى من الخرسانة بـ 4 مرات! 🦴",
    "هل تعلم؟ الأخطبوط لديه 3 قلوب! 🐙",
    "هل تعلم؟ العسل لا يفسد أبداً! 🍯",
]

# ==========================================
# 🛠️ الخدمات الخلفية
# ==========================================

# --- جداول جوجل ---
@st.cache_resource
def get_gspread_client():
    if "gcp_service_account" not in st.secrets:
        return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        scope = [
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/spreadsheets",
        ]
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds)
    except Exception as e:
        # أثناء البناء: أظهر السبب بدل الصمت
        st.error(f"Service account error: {e}")
        return None


def get_sheet_data():
    client = get_gspread_client()
    if not client:
        return None
    try:
        sheet = client.open(CONTROL_SHEET_NAME)
        val = sheet.sheet1.acell("B1").value
        return str(val).strip() if val is not None else None
    except Exception as e:
        st.error(f"Google Sheet open/read error: {e}")
        return None


# --- التسجيل (Logs) ---
def _bg_task(task_type, data):
    if "gcp_service_account" not in st.secrets:
        return

    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        client = gspread.authorize(
            service_account.Credentials.from_service_account_info(
                creds_dict,
                scopes=["https://www.googleapis.com/auth/spreadsheets"],
            )
        )
        wb = client.open(CONTROL_SHEET_NAME)

        tz = pytz.timezone("Africa/Cairo")
        now_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

        if task_type == "login":
            try:
                sheet = wb.worksheet("Logs")
            except Exception:
                sheet = wb.sheet1
            sheet.append_row([now_str, data["type"], data["name"], data["details"]])

        elif task_type == "activity":
            try:
                sheet = wb.worksheet("Activity")
            except Exception:
                return
            clean_text = str(data["text"])[:1000]
            sheet.append_row([now_str, data["name"], data["input_type"], clean_text])

        elif task_type == "xp":
            try:
                sheet = wb.worksheet("Gamification")
            except Exception:
                return
            cell = sheet.find(data["name"])
            if cell:
                val = sheet.cell(cell.row, 2).value
                current_xp = int(val) if val else 0
                sheet.update_cell(cell.row, 2, current_xp + data["points"])
            else:
                sheet.append_row([data["name"], data["points"]])

    except Exception:
        pass


def log_login(user_name, user_type, details):
    threading.Thread(
        target=_bg_task,
        args=("login", {"name": user_name, "type": user_type, "details": details}),
        daemon=True,
    ).start()


def log_activity(user_name, input_type, text):
    threading.Thread(
        target=_bg_task,
        args=("activity", {"name": user_name, "input_type": input_type, "text": text}),
        daemon=True,
    ).start()


def update_xp(user_name, points):
    if "current_xp" in st.session_state:
        st.session_state.current_xp += points
    threading.Thread(
        target=_bg_task,
        args=("xp", {"name": user_name, "points": points}),
        daemon=True,
    ).start()


def get_current_xp(user_name):
    client = get_gspread_client()
    if not client:
        return 0
    try:
        sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
        cell = sheet.find(user_name)
        val = sheet.cell(cell.row, 2).value
        return int(val) if val else 0
    except Exception:
        return 0


def get_leaderboard():
    client = get_gspread_client()
    if not client:
        return []
    try:
        sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        if df.empty:
            return []
        if "XP" not in df.columns:
            return []
        df["XP"] = pd.to_numeric(df["XP"], errors="coerce").fillna(0)
        return df.sort_values(by="XP", ascending=False).head(5).to_dict("records")
    except Exception:
        return []


# --- Google Drive ---
@st.cache_resource
def get_drive_service():
    if "gcp_service_account" not in st.secrets:
        return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )
        return build("drive", "v3", credentials=creds)
    except Exception:
        return None


def list_drive_files(service, folder_id):
    try:
        q = f"'{folder_id}' in parents and trashed = false"
        res = service.files().list(q=q, fields="files(id, name)").execute()
        return res.get("files", [])
    except Exception:
        return []


def download_pdf_text(service, file_id):
    try:
        req = service.files().get_media(fileId=file_id)
        fh = BytesIO()
        downloader = MediaIoBaseDownload(fh, req)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        fh.seek(0)
        reader = PyPDF2.PdfReader(fh)
        text = ""
        for page in reader.pages:
            text += (page.extract_text() or "") + "\n"
        return text
    except Exception:
        return ""


# ==========================================
# 🔊 الصوت
# ==========================================
async def generate_audio_stream(text, voice_code):
    clean = re.sub(r"[*#_`\[\]()><=]", " ", text)
    clean = re.sub(r"\\.*", "", clean)
    comm = edge_tts.Communicate(clean, voice_code, rate="-5%")
    mp3 = BytesIO()
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            mp3.write(chunk["data"])
    mp3.seek(0)
    return mp3


def generate_audio_bytes(text, voice_code):
    try:
        return asyncio.run(generate_audio_stream(text, voice_code))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(generate_audio_stream(text, voice_code))
        finally:
            loop.close()


def speech_to_text(audio_bytes, lang_code):
    r = sr.Recognizer()
    try:
        with sr.AudioFile(BytesIO(audio_bytes)) as source:
            r.adjust_for_ambient_noise(source, duration=0.5)
            audio_data = r.record(source)
            return r.recognize_google(audio_data, language=lang_code)
    except Exception:
        return None


# ==========================================
# 🧠 الذكاء الاصطناعي
# ==========================================
@st.cache_resource
def get_model_names_to_try():
    # أسماء أكثر شيوعاً في google-generativeai (قد تختلف حسب حسابك)
    return [
        "models/gemini-1.5-flash",
        "models/gemini-1.5-pro",
    ]


def pil_to_png_bytes(img: Image.Image) -> bytes:
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def get_working_model():
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys:
        return None

    random.shuffle(keys)
    models_to_try = get_model_names_to_try()

    for key in keys:
        genai.configure(api_key=key)
        for model_name in models_to_try:
            try:
                model = genai.GenerativeModel(model_name)
                model.generate_content("ping")
                return model
            except Exception:
                continue
    return None


def process_ai_response(user_text, input_type="text"):
    log_activity(st.session_state.user_name, input_type, user_text)

    with st.spinner("🧠 جاري المعالجة..."):
        try:
            model = get_working_model()
            if not model:
                st.error("⚠️ فشل الاتصال بـ Gemini. تحقق من المفاتيح/النماذج.")
                return

            lang = st.session_state.language
            ref = st.session_state.get("ref_text", "")
            grade = st.session_state.get("student_grade", "General")

            lang_instr = "Arabic" if lang == "العربية" else "English"

            base_prompt = f"""
Role: Science Tutor. Grade: {grade}.
Context: {ref[:10000]}
Instructions: Answer in {lang_instr}. Be helpful.
If diagram needed, use Graphviz DOT code inside ```dot ... ``` block.
""".strip()

            if input_type == "image":
                prompt = f"{base_prompt}\nStudent: {user_text[0]}"
                img_bytes = pil_to_png_bytes(user_text[1].convert("RGB"))
                resp = model.generate_content([prompt, {"mime_type": "image/png", "data": img_bytes}])
            else:
                resp = model.generate_content(f"{base_prompt}\nStudent: {user_text}")

            full_text = getattr(resp, "text", "") or ""
            st.session_state.chat_history.append((str(user_text)[:50], full_text))

            # عرض + Graphviz
            disp_text = full_text.split("```dot")[0].strip()
            dot_code = None
            if "```dot" in full_text:
                try:
                    dot_code = full_text.split("```dot")[1].split("```")[0].strip()
                except Exception:
                    dot_code = None

            st.markdown("---")
            st.chat_message("assistant").write(disp_text)

            if dot_code:
                try:
                    st.graphviz_chart(dot_code)
                except Exception:
                    pass

            # الصوت
            vc = "ar-EG-ShakirNeural" if lang == "العربية" else "en-US-AndrewNeural"
            try:
                audio = generate_audio_bytes(disp_text[:400], vc)
                st.audio(audio, format="audio/mp3", autoplay=True)
            except Exception:
                pass

        except Exception as e:
            st.error(f"حدث خطأ: {e}")


# ==========================================
# 🎨 الواجهة (UI)
# ==========================================
def draw_header():
    st.markdown(
        """
<div style='background:linear-gradient(135deg,#6a11cb,#2575fc);padding:1.5rem;border-radius:15px;text-align:center;color:white;margin-bottom:1rem;'>
    <h1 style='margin:0;'>🧬 AI Science Tutor</h1>
</div>
""",
        unsafe_allow_html=True,
    )


if "auth_status" not in st.session_state:
    st.session_state.update(
        {
            "auth_status": False,
            "user_type": "none",
            "chat_history": [],
            "student_grade": "",
            "current_xp": 0,
            "last_audio_bytes": None,
            "language": "العربية",
            "ref_text": "",
        }
    )

# --- تسجيل الدخول ---
if not st.session_state.auth_status:
    draw_header()

    with st.expander("🔧 Diagnostics", expanded=False):
        st.write("Has GOOGLE_API_KEYS:", bool(st.secrets.get("GOOGLE_API_KEYS", [])))
        st.write("Has gcp_service_account:", "gcp_service_account" in st.secrets)
        st.write("CONTROL_SHEET_NAME:", CONTROL_SHEET_NAME)
        st.write("Has DRIVE_FOLDER_ID:", bool(DRIVE_FOLDER_ID))

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.info(f"💡 {random.choice(DAILY_FACTS)}")
        with st.form("login"):
            name = st.text_input("الاسم:")
            grade = st.selectbox("الصف:", ["الرابع", "الخامس", "السادس", "الأول ع", "الثاني ع", "الثالث ع", "ثانوي"])
            code = st.text_input("الكود:", type="password")
            if st.form_submit_button("دخول"):
                db_pass = get_sheet_data()
                is_teacher = (code == TEACHER_MASTER_KEY)

                # لو الشيت غير متاح: اسمح للمعلم فقط
                if db_pass is None and not is_teacher:
                    st.error("تعذر الاتصال بقاعدة أكواد الطلاب (Google Sheet). راجع secrets ومشاركة الشيت مع service account.")
                    st.stop()

                is_student = (db_pass is not None and code == db_pass)

                if is_teacher or is_student:
                    st.session_state.auth_status = True
                    st.session_state.user_type = "teacher" if is_teacher else "student"
                    st.session_state.user_name = name if is_student else "Mr. Elsayed"
                    st.session_state.student_grade = grade
                    st.session_state.start_time = time.time()
                    if is_student:
                        st.session_state.current_xp = get_current_xp(name)
                        log_login(name, "student", grade)
                    st.success("تم الدخول!")
                    time.sleep(0.4)
                    st.rerun()
                else:
                    st.error("الكود غير صحيح")
    st.stop()

# --- التطبيق ---
draw_header()

with st.sidebar:
    st.write(f"أهلاً **{st.session_state.user_name}**")
    st.session_state.language = st.radio("اللغة:", ["العربية", "English"])

    if st.session_state.user_type == "student":
        st.metric("XP", st.session_state.current_xp)
        if st.session_state.current_xp >= 100:
            st.success("🎉 أحسنت!")
        st.markdown("---")
        st.caption("🏆 المتصدرون")
        for i, r in enumerate(get_leaderboard()):
            sn = r.get("Student_Name", "Unknown")
            xp = r.get("XP", 0)
            st.text(f"{i+1}. {sn} ({xp})")

    if DRIVE_FOLDER_ID:
        svc = get_drive_service()
        if svc:
            files = list_drive_files(svc, DRIVE_FOLDER_ID)
            if files:
                st.markdown("---")
                bn = st.selectbox("📚 المكتبة:", [f["name"] for f in files])
                if st.button("تفعيل"):
                    fid = next(f["id"] for f in files if f["name"] == bn)
                    with st.spinner("تحميل..."):
                        txt = download_pdf_text(svc, fid)
                        if txt:
                            st.session_state.ref_text = txt
                            st.toast("تم تفعيل الكتاب")

t1, t2, t3, t4 = st.tabs(["🎙️", "📝", "📷", "🧠"])

with t1:
    st.write("اضغط للتحدث:")
    aud = mic_recorder(start_prompt="🎤", stop_prompt="⏹️", key="m")
    if aud and aud.get("bytes") and aud["bytes"] != st.session_state.last_audio_bytes:
        st.session_state.last_audio_bytes = aud["bytes"]
        lang = "ar-EG" if st.session_state.language == "العربية" else "en-US"
        txt = speech_to_text(aud["bytes"], lang)
        if txt:
            st.chat_message("user").write(txt)
            update_xp(st.session_state.user_name, 10)
            process_ai_response(txt, "voice")
        else:
            st.warning("لم يتم التعرف على الصوت. جرّب مرة أخرى (قد تكون صيغة الصوت غير مدعومة).")

with t2:
    q = st.chat_input("اكتب سؤالك...")
    if q:
        st.chat_message("user").write(q)
        update_xp(st.session_state.user_name, 5)
        process_ai_response(q, "text")

with t3:
    up = st.file_uploader("صورة", type=["png", "jpg", "jpeg"])
    if st.button("تحليل") and up:
        img = Image.open(up).convert("RGB")
        st.image(img, width=150)
        update_xp(st.session_state.user_name, 15)
        process_ai_response(["اشرح الصورة", img], "image")

with t4:
    if st.button("سؤال جديد"):
        m = get_working_model()
        if m:
            try:
                p = (
                    f"Write 1 MCQ science question suitable for grade {st.session_state.student_grade}. "
                    f"Language: {st.session_state.language}. Do NOT include the answer."
                )
                st.session_state.q_curr = m.generate_content(p).text
                st.session_state.q_active = True
                st.rerun()
            except Exception:
                st.error("حاول مرة أخرى")

    if st.session_state.get("q_active"):
        st.markdown("---")
        st.write(st.session_state.q_curr)
        ans = st.text_input("إجابتك:")
        if st.button("تحقق"):
            m = get_working_model()
            if m:
                try:
                    prompt = (
                        f"Q: {st.session_state.q_curr}\n"
                        f"Student answer: {ans}\n"
                        "Check correctness. Reply briefly in the same language."
                    )
                    res = m.generate_content(prompt).text
                    st.write(res)
                    if "correct" in res.lower() or "صحيح" in res:
                        st.balloons()
                        update_xp(st.session_state.user_name, 50)
                    st.session_state.q_active = False
                except Exception:
                    st.error("خطأ في التحقق")
