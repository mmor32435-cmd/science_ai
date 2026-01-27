import streamlit as st
import os
import re
import io
import json
import time
import random
import asyncio
import tempfile
import traceback

from PIL import Image
import pdfplumber
import gspread
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder
import edge_tts

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import google.generativeai as genai

# OCR deps (تحتاج packages.txt + requirements.txt على Streamlit Cloud)
from pdf2image import convert_from_path
import pytesseract

# =========================
# 1) إعدادات الصفحة
# =========================
st.set_page_config(
    page_title="المعلم العلمي | السيد البدوي",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =========================
# 2) CSS آمن
# =========================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');

html, body, .stApp {
  font-family: 'Cairo', sans-serif !important;
  direction: rtl;
  text-align: right;
}
.stApp { background-color: #f8f9fa; }

.stTextInput input, .stTextArea textarea {
  background-color: #ffffff !important;
  color: #000000 !important;
  border: 2px solid #004e92 !important;
  border-radius: 8px !important;
}

div[data-baseweb="select"] > div {
  background-color: #ffffff !important;
  border: 2px solid #004e92 !important;
  border-radius: 8px !important;
}
ul[data-baseweb="menu"] { background-color: #ffffff !important; }
li[data-baseweb="option"] { color: #000000 !important; }
li[data-baseweb="option"]:hover { background-color: #e3f2fd !important; }

h1, h2, h3, h4, h5, p, label, span { color: #000000 !important; }

.stButton>button {
  background: linear-gradient(90deg, #004e92 0%, #000428 100%) !important;
  color: #ffffff !important;
  border: none;
  border-radius: 10px;
  height: 55px;
  width: 100%;
  font-size: 20px !important;
  font-weight: bold !important;
}

.header-box {
  background: linear-gradient(90deg, #000428 0%, #004e92 100%);
  padding: 2rem;
  border-radius: 15px;
  text-align: center;
  margin-bottom: 2rem;
  box-shadow: 0 4px 15px rgba(0,0,0,0.2);
}
.header-box h1, .header-box h3 { color: #ffffff !important; }

.stChatMessage {
  background-color: #ffffff !important;
  border: 1px solid #d1d1d1 !important;
  border-radius: 12px !important;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="header-box">
  <h1>الأستاذ / السيد البدوي</h1>
  <h3>المنصة التعليمية الذكية</h3>
</div>
""", unsafe_allow_html=True)


# =========================
# 3) Session state + Debug
# =========================
if "user_data" not in st.session_state:
    st.session_state.user_data = {
        "logged_in": False,
        "role": None,
        "name": "",
        "grade": "",
        "stage": "",
        "lang": "العربية (علوم)"
    }

if "messages" not in st.session_state:
    st.session_state.messages = []

if "book_data" not in st.session_state:
    st.session_state.book_data = {"path": None, "text": None, "name": None}

if "quiz_state" not in st.session_state:
    st.session_state.quiz_state = "off"  # off | asking | waiting_answer | correcting

if "quiz_last_question" not in st.session_state:
    st.session_state.quiz_last_question = ""

if "gemini_model_name" not in st.session_state:
    st.session_state.gemini_model_name = None

if "debug_enabled" not in st.session_state:
    st.session_state.debug_enabled = True

if "debug_log" not in st.session_state:
    st.session_state.debug_log = []

def dbg(event, data=None):
    if not st.session_state.debug_enabled:
        return
    rec = {"t": time.strftime("%H:%M:%S"), "event": event}
    if data is not None:
        rec["data"] = data
    st.session_state.debug_log.append(rec)
    st.session_state.debug_log = st.session_state.debug_log[-400:]


# =========================
# 4) Secrets
# =========================
TEACHER_KEY = st.secrets.get("TEACHER_MASTER_KEY", "ADMIN")
SHEET_NAME = st.secrets.get("CONTROL_SHEET_NAME", "App_Control")
FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "")


# =========================
# 5) Google creds + Sheets
# =========================
@st.cache_resource
def get_credentials():
    if "gcp_service_account" not in st.secrets:
        return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        return service_account.Credentials.from_service_account_info(creds_dict, scopes=scopes)
    except Exception as e:
        dbg("creds_error", str(e))
        return None


def get_gspread_client():
    creds = get_credentials()
    return gspread.authorize(creds) if creds else None


def check_student_code(input_code):
    client = get_gspread_client()
    if not client:
        return False
    try:
        sh = client.open(SHEET_NAME)
        real_code = str(sh.sheet1.acell("B1").value).strip()
        return str(input_code).strip() == real_code
    except Exception as e:
        dbg("check_student_code_error", str(e))
        return False


# =========================
# 6) تحميل الكتاب من Drive + استخراج نص كامل
# =========================
def load_book_smartly(stage, grade, lang):
    creds = get_credentials()
    if not creds:
        return None

    try:
        target_tokens = []

        if "الثانوية" 
