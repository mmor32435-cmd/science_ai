import streamlit as st

# ==========================================
# 0) إعدادات الصفحة
# ==========================================
st.set_page_config(page_title="AI Science Tutor Pro", page_icon="🧬", layout="wide")

import time
import asyncio
import re
import random
import threading
import hashlib
from io import BytesIO
from datetime import datetime
import pytz

# مكتبات خارجية
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
# 1) ستايل (واجهة أجمل)
# ==========================================
def inject_css():
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.1rem; }
        .app-header {
          background: linear-gradient(135deg, #6a11cb, #2575fc);
          padding: 18px 18px;
          border-radius: 16px;
          color: white;
          margin-bottom: 12px;
          box-shadow: 0 10px 25px rgba(0,0,0,.12);
        }
        .app-header h1 { margin: 0; font-size: 28px; }
        .app-sub { opacity: .95; margin-top: 6px; font-size: 13px; }
        .card {
          border: 1px solid rgba(0,0,0,.08);
          border-radius: 14px;
          padding: 14px;
          box-shadow: 0 6px 18px rgba(0,0,0,.06);
          background: white;
        }
        .muted { color: rgba(0,0,0,.6); font-size: 12px; }
        .stTabs [data-baseweb="tab-list"] button { font-weight: 700; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def header():
    st.markdown(
        """
        <div class="app-header">
          <h1>🧬 AI Science Tutor Pro</h1>
          <div class="app-sub">منصة علوم متكاملة: محادثة + صوت + صور + مكتبة PDF + اختبارات + XP</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


inject_css()
header()


# ==========================================
# 2) Secrets & ثوابت
# ==========================================
def secret(key: str, default=None):
    return st.secrets.get(key, default)


TEACHER_MASTER_KEY = secret("TEACHER_MASTER_KEY", "ADMIN_2024")
CONTROL_SHEET_NAME = secret("CONTROL_SHEET_NAME", "App_Control")
DRIVE_FOLDER_ID = secret("DRIVE_FOLDER_ID", "")

SESSION_DURATION_MINUTES = 60

DAILY_FACTS = [
    "هل تعلم؟ جسم الإنسان يحتوي على أكثر من 200 عظمة.",
    "هل تعلم؟ الدماغ يستهلك تقريبًا 20% من طاقة الجسم.",
    "هل تعلم؟ الصوت يحتاج وسطًا لينتقل (هواء/ماء/صلب).",
    "هل تعلم؟ النباتات تصنع غذاءها بالبناء الضوئي.",
]

GEMINI_MODELS_TO_TRY = [
    "gemini-2.5-flash",
    "gemini-flash-latest",
    "gemini-pro-latest",
    "gemini-2.0-flash",
]


# ==========================================
# 3) Google Sheets / Logs / XP
# ==========================================
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
    except Exception:
        return None


def get_control_password():
    client = get_gspread_client()
    if not client:
        return None
    try:
        sheet = client.open(CONTROL_SHEET_NAME).sheet1
        val = sheet.acell("B1").value
        return str(val).strip() if val else None
    except Exception:
        return None


def _bg_task(task_type, data):
    # لا تسمح لأي أخطاء هنا بإسقاط التطبيق
    if "gcp_service_account" not in st.secrets:
        return
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        client = gspread.authorize(creds)
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
                sheet.update_cell(cell.row, 2, current_xp + int(data["points"]))
            else:
                sheet.append_row([data["name"], int(data["points"])])
    except Exception:
        return


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


def update_xp(user_name, points: int):
    st.session_state.current_xp = int(st.session_state.current_xp) + int(points)
    threading.Thread(
        target=_bg_task, args=("xp", {"name": user_name, "points": int(points)}), daemon=True
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


@st.cache_data(ttl=60)
def get_leaderboard_cached():
    client = get_gspread_client()
    if not client:
        return []
    try:
        sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        if df.empty:
            return []

        # حاول العثور على عمود XP
        xp_col = "XP" if "XP" in df.columns else (df.columns[1] if len(df.columns) > 1 else None)
        name_col = "Student_Name" if "Student_Name" in df.columns else (df.columns[0] if len(df.columns) > 0 else None)
        if not xp_col or not name_col:
            return []

        df[xp_col] = pd.to_numeric(df[xp_col], errors="coerce").fillna(0)
        out = df.sort_values(by=xp_col, ascending=False).head(5)
        return [{"name": r[name_col], "xp": int(r[xp_col])} for _, r in out.iterrows()]
    except Exception:
        return []


# ==========================================
# 4) Google Drive (PDF Library)
# ==========================================
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


@st.cache_data(ttl=300)
def list_drive_files_cached(folder_id: str):
    svc = get_drive_service()
    if not svc or not folder_id:
        return []
    try:
        q = f"'{folder_id}' in parents and trashed = false"
        res = svc.files().list(q=q, fields="files(id, name)").execute()
        return res.get("files", [])
    except Exception:
        return []


def download_pdf_text(file_id: str) -> str:
    svc = get_drive_service()
    if not svc:
        return ""
    try:
        req = svc.files().get_media(fileId=file_id)
        fh = BytesIO()
        downloader = MediaIoBaseDownload(fh, req)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        fh.seek(0)

        reader = PyPDF2.PdfReader(fh)
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return "\n".join(pages).strip()
    except Exception:
        return ""


# ==========================================
# 5) Gemini Router (أسرع وأكثر ثباتًا)
# ==========================================
class GeminiRouter:
    def __init__(self, api_keys):
        self.api_keys = list(api_keys) if api_keys else []
        self.models = GEMINI_MODELS_TO_TRY

    def _generate(self, api_key: str, model_name: str, payload):
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        return model.generate_content(payload)

    def generate(self, payload):
        # استخدم آخر مفتاح/موديل شغالين أولاً لتقليل التأخير
        last_key = st.session_state.get("working_api_key")
        last_model = st.session_state.get("working_model_name")
        if last_key and last_model:
            try:
                return self._generate(last_key, last_model, payload)
            except Exception:
                pass

        keys = self.api_keys[:]
        if not keys:
            raise RuntimeError("Missing GOOGLE_API_KEYS in secrets.")

        random.shuffle(keys)
        for key in keys:
            for model_name in self.models:
                try:
                    resp = self._generate(key, model_name, payload)
                    st.session_state.working_api_key = key
                    st.session_state.working_model_name = model_name
                    return resp
                except Exception:
                    continue

        raise RuntimeError("No working Gemini key/model available.")


@st.cache_resource
def get_gemini_router():
    keys = secret("GOOGLE_API_KEYS", [])
    if isinstance(keys, str):
        keys = [keys]
    return GeminiRouter(keys)


# ==========================================
# 6) الصوت: تحويل إلى WAV + Speech-to-Text + TTS
# ==========================================
def is_wav_bytes(b: bytes) -> bool:
    return isinstance(b, (bytes, bytearray)) and len(b) > 12 and b[0:4] == b"RIFF" and b[8:12] == b"WAVE"


def ensure_wav(audio_bytes: bytes) -> bytes:
    """
    بعض المتصفحات ترسل WebM/OGG عبر mic_recorder.
    SpeechRecognition يحتاج WAV/AIFF/FLAC.
    هنا نحاول التحويل إلى WAV باستخدام pydub (ويحتاج ffmpeg للـ webm/ogg).
    """
    if is_wav_bytes(audio_bytes):
        return audio_bytes

    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(BytesIO(audio_bytes))
        wav_io = BytesIO()
        audio.export(wav_io, format="wav")
        return wav_io.getvalue()
    except Exception as e:
        raise RuntimeError(
            "الميكروفون سجّل بصيغة غير WAV ولم أستطع تحويلها.\n"
            "- ثبّت ffmpeg (ضروري لتحويل webm/ogg)\n"
            "- أو جرّب متصفح Chrome/Edge\n"
            f"تفاصيل: {type(e).__name__}"
        )


def speech_to_text(audio_bytes: bytes, lang_code: str) -> str:
    """
    تحويل الصوت إلى نص عبر Google Web Speech (SpeechRecognition).
    """
    r = sr.Recognizer()
    r.dynamic_energy_threshold = True

    wav_bytes = ensure_wav(audio_bytes)
    with sr.AudioFile(BytesIO(wav_bytes)) as source:
        audio_data = r.record(source)

    try:
        return r.recognize_google(audio_data, language=lang_code).strip()
    except sr.UnknownValueError:
        return ""
    except Exception:
        return ""


async def tts_edge_mp3(text: str, voice_code: str) -> BytesIO:
    clean = re.sub(r"[*#_`\[\]()><=]", " ", text)
    clean = re.sub(r"\\.*", "", clean)
    comm = edge_tts.Communicate(clean, voice_code, rate="-5%")
    mp3 = BytesIO()
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            mp3.write(chunk["data"])
    mp3.seek(0)
    return mp3


def run_tts(text: str, voice_code: str) -> BytesIO | None:
    try:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(tts_edge_mp3(text, voice_code))
        finally:
            loop.close()
    except Exception:
        return None


# ==========================================
# 7) Prompting + Rendering (Graphviz DOT)
# ==========================================
def build_prompt(user_text: str) -> str:
    lang = st.session_state.language
    grade = st.session_state.student_grade
    ref = (st.session_state.get("ref_text", "") or "")[:12000]
    lang_instr = "Arabic" if lang == "العربية" else "English"

    # ملاحظة مهمة:
    # نتجنب f-string ثلاثي الاقتباس الذي يحتوي على { } حتى لا يحدث SyntaxError.
    prompt = (
        "Role: Expert Science Tutor.\n"
        f"Target grade: {grade}.\n"
        f"Answer language: {lang_instr}.\n\n"
        "Rules:\n"
        "- Explain clearly with examples.\n"
        "- If the student is wrong, correct gently and show the right reasoning.\n"
        "- If a diagram helps, provide Graphviz DOT inside a fenced block exactly like:\n"
        "  ```dot\n"
        "  digraph G {\n"
        "    A -> B;\n"
        "  }\n"
        "  ```\n\n"
        "Reference (optional):\n"
        f"{ref}\n\n"
        "Student question:\n"
        f"{user_text}\n"
    )
    return prompt.strip()


def extract_dot_block(text: str):
    if "```dot" not in text:
        return text, None
    before = text.split("```dot")[0].strip()
    dot_code = None
    try:
        dot_code = text.split("```dot")[1].split("```")[0].strip()
    except Exception:
        dot_code = None
    return before, dot_code


def ai_answer(user_text: str, input_type="text", image: Image.Image | None = None):
    log_activity(st.session_state.user_name, input_type, user_text)
    router = get_gemini_router()
    prompt = build_prompt(user_text)

    with st.spinner("🧠 Processing..."):
        if input_type == "image" and image is not None:
            resp = router.generate([prompt, image])
        else:
            resp = router.generate(prompt)

    full = (getattr(resp, "text", "") or "").strip()
    disp, dot = extract_dot_block(full)

    # حفظ المحادثة
    st.session_state.messages.append({"role": "user", "content": user_text})
    st.session_state.messages.append({"role": "assistant", "content": full})

    # عرض رد المساعد
    with st.chat_message("assistant"):
        st.markdown(disp)

        if dot and st.session_state.show_diagrams:
            try:
                st.graphviz_chart(dot)
            except Exception:
                st.caption("تعذر عرض الرسم (Graphviz).")

        # صوت TTS
        if st.session_state.enable_tts:
            vc = "ar-EG-ShakirNeural" if st.session_state.language == "العربية" else "en-US-AndrewNeural"
            audio = run_tts(disp[:550], vc)
            if audio:
                st.audio(audio, format="audio/mp3", autoplay=st.session_state.autoplay_audio)


# ==========================================
# 8) Quiz (JSON)
# ==========================================
def generate_mcq():
    router = get_gemini_router()
    lang = st.session_state.language
    grade = st.session_state.student_grade
    lang_instr = "Arabic" if lang == "العربية" else "English"

    # نبني النص بدون f-string يحتوي { } لتفادي أي مشاكل
    schema = (
        '{\n'
        '  "question": "...",\n'
        '  "choices": ["A ...", "B ...", "C ...", "D ..."],\n'
        '  "answer_index": 0,\n'
        '  "explanation": "..." \n'
        '}\n'
    )

    prompt = (
        "Create 1 science MCQ suitable for grade: " + str(grade) + ".\n"
        "Return ONLY valid JSON with this schema:\n"
        + schema +
        "Language: " + lang_instr + "\n"
        "No markdown. No extra text.\n"
    )

    resp = router.generate(prompt)
    txt = (resp.text or "").strip()

    import json
    m = re.search(r"\{.*\}", txt, re.DOTALL)
    if not m:
        raise ValueError("Could not parse quiz JSON.")
    return json.loads(m.group(0))


# ==========================================
# 9) Session State init
# ==========================================
if "auth_status" not in st.session_state:
    st.session_state.auth_status = False
    st.session_state.user_type = "none"
    st.session_state.user_name = ""
    st.session_state.student_grade = ""
    st.session_state.start_time = None

    st.session_state.current_xp = 0
    st.session_state.language = "العربية"

    st.session_state.ref_text = ""
    st.session_state.messages = []

    st.session_state.last_rec_id = None

    st.session_state.enable_tts = True
    st.session_state.autoplay_audio = True
    st.session_state.show_diagrams = True

    st.session_state.quiz = None


# ==========================================
# 10) تسجيل الدخول
# ==========================================
if not st.session_state.auth_status:
    col1, col2, col3 = st.columns([1, 1.4, 1])
    with col2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.info(random.choice(DAILY_FACTS))

        with st.form("login_form", clear_on_submit=False):
            name = st.text_input("الاسم", value="")
            grade = st.selectbox("الصف", ["الرابع", "الخامس", "السادس", "الأول ع", "الثاني ع", "الثالث ع", "ثانوي"])
            code = st.text_input("الكود", type="password")
            ok = st.form_submit_button("دخول")

        if ok:
            name_clean = name.strip()
            if not name_clean:
                st.error("من فضلك اكتب الاسم.")
                st.stop()

            db_pass = get_control_password()
            is_teacher = (code == TEACHER_MASTER_KEY)
            is_student = (db_pass and code == db_pass)

            if is_teacher or is_student:
                st.session_state.auth_status = True
                st.session_state.user_type = "teacher" if is_teacher else "student"
                st.session_state.user_name = name_clean if is_student else "Teacher"
                st.session_state.student_grade = grade
                st.session_state.start_time = time.time()
                st.session_state.messages = []

                if is_student:
                    st.session_state.current_xp = get_current_xp(st.session_state.user_name)
                    log_login(st.session_state.user_name, "student", grade)
                else:
                    log_login("Teacher", "teacher", "admin")

                st.rerun()
            else:
                st.error("الكود غير صحيح")

        st.markdown("</div>", unsafe_allow_html=True)
    st.stop()


# ==========================================
# 11) انتهاء الجلسة
# ==========================================
if st.session_state.start_time and (time.time() - st.session_state.start_time) > SESSION_DURATION_MINUTES * 60:
    st.session_state.auth_status = False
    st.session_state.messages = []
    st.warning("انتهت الجلسة. سجّل الدخول مرة أخرى.")
    st.stop()


# ==========================================
# 12) Sidebar
# ==========================================
with st.sidebar:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.write(f"المستخدم: **{st.session_state.user_name}**")
    st.write(f"النوع: `{st.session_state.user_type}`")

    st.session_state.language = st.radio("اللغة", ["العربية", "English"], horizontal=True)

    st.markdown("---")
    st.session_state.enable_tts = st.toggle("تفعيل صوت المساعد (TTS)", value=st.session_state.enable_tts)
    st.session_state.autoplay_audio = st.toggle("تشغيل الصوت تلقائيًا", value=st.session_state.autoplay_audio)
    st.session_state.show_diagrams = st.toggle("عرض الرسوم (DOT/Graphviz)", value=st.session_state.show_diagrams)

    st.markdown("---")
    if st.session_state.user_type == "student":
        st.metric("XP", int(st.session_state.current_xp))
        xp = int(st.session_state.current_xp)
        badge = "Starter" if xp < 200 else "Rising" if xp < 600 else "Advanced" if xp < 1200 else "Expert"
        st.caption(f"Badge: {badge}")

        st.markdown("---")
        st.caption("🏆 المتصدرون")
        for i, r in enumerate(get_leaderboard_cached()):
            st.write(f"{i+1}. {r['name']} — {r['xp']} XP")

    st.markdown("---")
    if DRIVE_FOLDER_ID:
        files = list_drive_files_cached(DRIVE_FOLDER_ID)
        if files:
            book = st.selectbox("📚 المكتبة (PDF)", [f["name"] for f in files])
            if st.button("تفعيل الكتاب كمصدر", use_container_width=True):
                fid = next(f["id"] for f in files if f["name"] == book)
                with st.spinner("Downloading PDF..."):
                    txt = download_pdf_text(fid)
                if txt:
                    st.session_state.ref_text = txt
                    st.success("تم تفعيل الكتاب كمصدر مرجعي.")
                else:
                    st.error("لم أستطع استخراج النص من PDF.")

    st.markdown("---")
    if st.button("تسجيل خروج", use_container_width=True):
        st.session_state.auth_status = False
        st.session_state.messages = []
        st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)


# ==========================================
# 13) عرض تاريخ المحادثة
# ==========================================
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])


# ==========================================
# 14) Tabs: Text / Voice / Image / Quiz
# ==========================================
tab_text, tab_voice, tab_image, tab_quiz = st.tabs(["📝 Text", "🎙️ Voice", "📷 Image", "🧠 Quiz"])

with tab_text:
    user_q = st.chat_input("اكتب سؤالك هنا...")
    if user_q:
        with st.chat_message("user"):
            st.write(user_q)

        if st.session_state.user_type == "student":
            update_xp(st.session_state.user_name, 5)

        ai_answer(user_q, input_type="text")


with tab_voice:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.write("اضغط للتسجيل ثم انتظر التفريغ النصي.")
    st.caption("إذا ظهر خطأ تحويل الصوت: ثبّت ffmpeg لأن بعض المتصفحات تسجّل WebM/OGG.")

    aud = mic_recorder(start_prompt="Start recording", stop_prompt="Stop", key="mic1")

    if aud and aud.get("bytes"):
        # ID ثابت لمنع إعادة المعالجة عند rerun
        rec_id = aud.get("id") or hashlib.md5(aud["bytes"]).hexdigest()
        st.audio(aud["bytes"])  # تشغيل ما تم تسجيله (المتصفح يتعامل مع النوع غالبًا)

        if rec_id != st.session_state.last_rec_id:
            st.session_state.last_rec_id = rec_id

            lang = "ar-EG" if st.session_state.language == "العربية" else "en-US"
            with st.spinner("Transcribing..."):
                try:
                    text = speech_to_text(aud["bytes"], lang)
                except Exception as e:
                    st.error(str(e))
                    text = ""

            if text.strip():
                with st.chat_message("user"):
                    st.write(text)

                if st.session_state.user_type == "student":
                    update_xp(st.session_state.user_name, 10)

                ai_answer(text, input_type="voice")
            else:
                st.warning(
                    "لم أتمكن من تفريغ الصوت.\n"
                    "- تأكد من سماح الميكروفون في المتصفح\n"
                    "- تحدث بوضوح لمدة 2-4 ثوانٍ\n"
                    "- إن كانت الصيغة webm/ogg ثبّت ffmpeg للتحويل"
                )

    st.markdown("</div>", unsafe_allow_html=True)


with tab_image:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    up = st.file_uploader("ارفع صورة (PNG/JPG)", type=["png", "jpg", "jpeg"])
    prompt = st.text_input("ماذا تريد من الصورة؟", value="اشرح ما في الصورة علميًا بشكل مبسط")

    if st.button("تحليل الصورة", use_container_width=True) and up:
        img = Image.open(up).convert("RGB")
        st.image(img, use_container_width=True)

        with st.chat_message("user"):
            st.write(prompt)

        if st.session_state.user_type == "student":
            update_xp(st.session_state.user_name, 15)

        ai_answer(prompt, input_type="image", image=img)

    st.markdown("</div>", unsafe_allow_html=True)


with tab_quiz:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    colA, colB = st.columns([1, 1])
    with colA:
        if st.button("سؤال جديد", use_container_width=True):
            try:
                st.session_state.quiz = generate_mcq()
            except Exception:
                st.session_state.quiz = None
                st.error("تعذر إنشاء سؤال الآن. حاول مرة أخرى.")

    if st.session_state.quiz:
        qz = st.session_state.quiz
        st.subheader(qz.get("question", ""))
        choices = qz.get("choices", [])
        choice = st.radio("اختر الإجابة", choices, index=None)

        if st.button("تحقق", use_container_width=True):
            ai = int(qz.get("answer_index", -1))
            selected_idx = choices.index(choice) if (choice in choices) else -1

            if selected_idx == ai:
                st.success("إجابة صحيحة.")
                if st.session_state.user_type == "student":
                    update_xp(st.session_state.user_name, 50)
            else:
                st.error("إجابة غير صحيحة.")

            expl = qz.get("explanation", "")
            if expl:
                st.markdown("**الشرح:**")
                st.write(expl)

    st.markdown("</div>", unsafe_allow_html=True)
