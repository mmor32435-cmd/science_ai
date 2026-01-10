import streamlit as st

# ==========================================================
# AI Science Tutor Pro — نسخة مستقرة (Login + Chat + Voice + Image + PDF + Quiz + XP)
# ملاحظة مهمة للصوت (STT):
# - mic_recorder غالبًا يُخرج webm/ogg، ويلزم ffmpeg للتحويل إلى wav عبر pydub.
# - على Streamlit Cloud: أضف ملف packages.txt وفيه: ffmpeg
# ==========================================================

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
from typing import Optional, List, Dict, Any, Tuple

import pytz
import pandas as pd
from PIL import Image
import PyPDF2

import google.generativeai as genai
import edge_tts
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import gspread


# =========================
# UI
# =========================
def inject_css():
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1rem; }
        .app-header {
          background: linear-gradient(135deg, #6a11cb, #2575fc);
          padding: 18px;
          border-radius: 16px;
          color: white;
          margin-bottom: 14px;
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


def draw_header():
    st.markdown(
        """
        <div class="app-header">
          <h1>🧬 AI Science Tutor Pro</h1>
          <div class="app-sub">دخول + محادثة + ميكروفون + صورة + مكتبة PDF + اختبارات + XP</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================
# Secrets / Constants
# =========================
def secret(key: str, default=None):
    return st.secrets.get(key, default)


TEACHER_MASTER_KEY = secret("TEACHER_MASTER_KEY", "ADMIN_2024")
CONTROL_SHEET_NAME = secret("CONTROL_SHEET_NAME", "App_Control")
DRIVE_FOLDER_ID = secret("DRIVE_FOLDER_ID", "")

SESSION_DURATION_MINUTES = 60

DAILY_FACTS = [
    "هل تعلم؟ الدماغ يستهلك تقريبًا 20% من طاقة الجسم.",
    "هل تعلم؟ الصوت يحتاج وسطًا لينتقل (هواء/ماء/صلب).",
    "هل تعلم؟ النباتات تصنع غذاءها بالبناء الضوئي.",
    "هل تعلم؟ بعض المعادن موصل جيد للكهرباء.",
]

GEMINI_MODELS_TO_TRY = [
    "gemini-2.5-flash",
    "gemini-flash-latest",
    "gemini-pro-latest",
    "gemini-2.0-flash",
]


# =========================
# Google: Sheets
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


def get_control_password() -> Optional[str]:
    client = get_gspread_client()
    if not client:
        return None
    try:
        sheet = client.open(CONTROL_SHEET_NAME).sheet1
        val = sheet.acell("B1").value
        return str(val).strip() if val else None
    except Exception:
        return None


def _bg_task(task_type: str, data: Dict[str, Any]):
    """Background logging/XP — لا تُسقط التطبيق أبدًا."""
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
            sheet.append_row([now_str, data.get("type", ""), data.get("name", ""), data.get("details", "")])

        elif task_type == "activity":
            try:
                sheet = wb.worksheet("Activity")
            except Exception:
                return
            clean_text = str(data.get("text", ""))[:1000]
            sheet.append_row([now_str, data.get("name", ""), data.get("input_type", ""), clean_text])

        elif task_type == "xp":
            try:
                sheet = 
