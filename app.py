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
import shutil
from io import BytesIO
from datetime import datetime
from typing import Optional, List, Tuple
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
# 5) Gemini Router
# ==========================================
class GeminiRouter:
    def __init__(self, api_keys: List[str]):
        self.api_keys = list(api_keys) if api_keys else []
        self.models 
