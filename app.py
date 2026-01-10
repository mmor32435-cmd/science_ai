import streamlit as st
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


# =========================
# Helpers / Styling
# =========================
def inject_css():
    st.markdown("""
    <style>
      .block-container { padding-top: 1.2rem; }
      .app-header {
        background: linear-gradient(135deg, #6a11cb, #2575fc);
        padding: 18px 18px;
        border-radius: 16px;
        color: white;
        margin-bottom: 12px;
        box-shadow: 0 10px 25px rgba(0,0,0,.12);
      }
      .app-header h1 { margin: 0; font-size: 28px; }
      .app-sub { opacity: .95; margin-top: 6px; font-size: 14px; }
      .card {
        border: 1px solid rgba(0,0,0,.08);
        border-radius: 14px;
        padding: 14px;
        box-shadow: 0 6px 18px rgba(0,0,0,.06);
        background: white;
      }
      .small-muted { color: rgba(0,0,0,.6); font-size: 12px; }
      .stTabs [data-baseweb="tab-list"] button { font-weight: 600; }
    </style>
    """, unsafe_allow_html=True)


def header():
    st.markdown("""
    <div class="app-header">
      <h1>AI Science Tutor Pro</h1>
      <div class="app-sub">منصة علوم: محادثة + صوت + صور + مكتبة + اختبارات + نقاط</div>
    </div>
    """, unsafe_allow_html=True)


def secret(key: str, default=None):
    return st.secrets.get(key, default)


DAILY_FACTS = [
    "هل تعلم؟ المخ يولد إشارات كهربائية يمكن قياسها.",
    "هل تعلم؟ العظام قوية جدًا مقارنة بوزنها.",
    "هل تعلم؟ الأخطبوط يملك ثلاثة قلوب.",
    "هل تعلم؟ العسل قد يبقى صالحًا لفترات طويلة جدًا.",
]


# =========================
# Config / Constants
# =========================
TEACHER_MASTER_KEY = secret("TEACHER_MASTER_KEY", "ADMIN_2024")
CONTROL_SHEET_NAME = secret("CONTROL_SHEET_NAME", "App_Control")
DRIVE_FOLDER_ID = secret("DRIVE_FOLDER_ID", "")

SESSION_DURATION_MINUTES = 60

GEMINI_MODELS_TO_TRY = [
    "gemini-2.5-flash",
    "gemini-flash-latest",
    "gemini-pro-latest",
    "gemini-2.0-flash",
]


# =========================
# Google Sheets / Drive
# =========================
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
    # Background logging (do not crash app)
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
        target=_bg_task, args=("login", {"name": user_name, "type": user_type, "details": details}),
        daemon=True
    ).start()


def log_activity(user_name, input_type, text):
    threading.Thread(
        target=_bg_task, args=("activity", {"name": user_name, "input_type": input_type, "text": text}),
        daemon=True
    ).start()


def update_xp(user_name, points: int):
    st.session_state.current_xp = int(st.session_state.current_xp) + int(points)
    threading.Thread(
        target=_bg_task, args=("xp", {"name": user_name, "points": int(points)}),
        daemon=True
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
        # Expect columns: Student_Name, XP (adjust if different)
        if "XP" not in df.columns:
            return []
        df["XP"] = pd.to_numeric(df["XP"], errors="coerce").fillna(0)
        return df.sort_values(by="XP", ascending=False).head(5).to_dict("records")
    except Exception:
        return []


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


def download_pdf_text(file_id: str):
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
        chunks = []
        for page in reader.pages:
            t = page.extract_text() or ""
            chunks.append(t)
        return "\n".join(chunks).strip()
    except Exception:
        return ""


# =========================
# Gemini Router (stable, no repeated ping each time)
# =========================
class GeminiRouter:
    def __init__(self, api_keys):
        self.api_keys = list(api_keys) if api_keys else []
        self.models = GEMINI_MODELS_TO_TRY

    def _try_generate(self, api_key: str, model_name: str, payload):
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        return model.generate_content(payload)

    def generate(self, payload):
        # Use cached last working first
        last_key = st.session_state.get("working_api_key")
        last_model = st.session_state.get("working_model_name")
        if last_key and last_model:
            try:
                return self._try_generate(last_key, last_model, payload)
            except Exception:
                pass

        keys = self.api_keys[:]
        random.shuffle(keys)

        for key in keys:
            for model_name in self.models:
                try:
                    resp = self._try_generate(key, model_name, payload)
                    st.session_state.working_api_key = key
                    st.session_state.working_model_name = model_name
                    return resp
                except Exception:
                    continue
        raise RuntimeError("No working Gemini model/key available.")


@st.cache_resource
def get_gemini_router():
    keys = secret("GOOGLE_API_KEYS", [])
    if isinstance(keys, str):
        keys = [keys]
    return GeminiRouter(keys)


# =========================
# Audio: STT + TTS (with WAV conversion)
# =========================
def is_wav_bytes(b: bytes) -> bool:
    return isinstance(b, (bytes, bytearray)) and len(b) > 12 and b[0:4] == b"RIFF" and b[8:12] == b"WAVE"


def ensure_wav(audio_bytes: bytes) -> bytes:
    """
    If not WAV, try convert using pydub (requires ffmpeg for webm/ogg).
    """
    if is_wav_bytes(audio_bytes):
        return audio_bytes

    # Attempt conversion via pydub
    try:
        from pydub import AudioSegment  # noqa
        audio = AudioSegment.from_file(BytesIO(audio_bytes))
        wav_io = BytesIO()
        audio.export(wav_io, format="wav")
        return wav_io.getvalue()
    except Exception as e:
        raise RuntimeError(
            "التسجيل الصوتي ليس بصيغة WAV، ولم أستطع تحويله. "
            "ثبّت ffmpeg أو اجعل mic_recorder يخرج WAV إن أمكن. "
            f"تفاصيل تقنية: {type(e).__name__}"
        )


def speech_to_text(audio_bytes: bytes, lang_code: str) -> str:
    r = sr.Recognizer()
    r.dynamic_energy_threshold = True

    wav_bytes = ensure_wav(audio_bytes)
    with sr.AudioFile(BytesIO(wav_bytes)) as source:
        # لا نستخدم adjust_for_ambient_noise لتجنب مشاكل التسجيلات القصيرة
        audio_data = r.record(source)

    try:
        return r.recognize_google(audio_data, language=lang_code)
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


# =========================
# AI Prompting + Rendering
# =========================
def build_prompt(user_text: str) -> str:
    lang = st.session_state.language
    grade = st.session_state.student_grade
    ref = st.session_state.get("ref_text", "")

    lang_instr = "Arabic" if lang == "العربية" else "English"
    # مرجع محدود لحماية الأداء
    ref = ref[:12000]

    return f"""
Role: Expert Science Tutor.
Target grade: {grade}.
Answer language: {lang_instr}.

Rules:
- Explain clearly with examples.
- If the student is wrong, correct gently and show the right reasoning.
- If a diagram helps, provide Graphviz DOT code inside a fenced block:
  ```dot
  digraph G {{ ... }}
