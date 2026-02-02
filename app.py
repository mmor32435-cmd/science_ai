import streamlit as st

# ✅ لازم يكون أول أمر Streamlit
st.set_page_config(page_title="المعلم الذكي", layout="wide", page_icon="🎓")

# =========================================================
# Imports + Availability checks (بدون ما يوقع التطبيق)
# =========================================================
import os
import time
import tempfile
import logging
import random
from contextlib import contextmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("smart_teacher")

# Google Gemini
try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except Exception as e:
    GENAI_AVAILABLE = False
    GENAI_IMPORT_ERROR = str(e)

# Google Drive
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    DRIVE_AVAILABLE = True
except Exception as e:
    DRIVE_AVAILABLE = False
    DRIVE_IMPORT_ERROR = str(e)

# Optional: mic recorder
try:
    from streamlit_mic_recorder import mic_recorder
    MIC_AVAILABLE = True
except Exception:
    MIC_AVAILABLE = False

# Optional: TTS
try:
    import edge_tts
    import asyncio
    TTS_AVAILABLE = True
except Exception:
    TTS_AVAILABLE = False


# =========================================================
# CSS
# =========================================================
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');
html, body, .stApp {
    font-family: 'Cairo', sans-serif !important;
    direction: rtl;
    text-align: right;
}
.header-box {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    padding: 1.2rem 1.5rem;
    border-radius: 15px;
    color: white;
    text-align: center;
    margin-bottom: 1rem;
}
.small-muted { color: #666; font-size: 0.9rem; }
.stButton > button {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    border-radius: 10px;
    height: 46px;
    width: 100%;
    border: none;
    font-size: 16px;
}
</style>
""",
    unsafe_allow_html=True,
)

# =========================================================
# Constants
# =========================================================
FOLDER_ID = "1ub4ML8q4YCM_VZR991XXQ6hBBas2X6rS"

MAX_RETRIES = 4
BASE_RETRY_DELAY = 1.5
MAX_BACKOFF = 12

VOICE_NAME = "ar-EG-ShakirNeural"

STAGES = ["الابتدائية", "الإعدادية", "الثانوية"]
GRADES = {
    "الابتدائية": ["الرابع", "الخامس", "السادس"],
    "الإعدادية": ["الأول", "الثاني", "الثالث"],
    "الثانوية": ["الأول", "الثاني", "الثالث"],
}
TERMS = ["الترم الأول", "الترم الثاني"]

GRADE_MAP = {
    "الرابع": "4",
    "الخامس": "5",
    "السادس": "6",
    "الأول": "1",
    "الثاني": "2",
    "الثالث": "3",
}
SUBJECT_MAP = {"كيمياء": "Chem", "فيزياء": "Physics", "أحياء": "Biology"}


# =========================================================
# Helpers
# =========================================================
@contextmanager
def status_box(label: str):
    """يدعم st.status لو موجودة وإلا fallback إلى spinner."""
    if hasattr(st, "status"):
        with st.status(label, expanded=True) as s:
            yield s
    else:
        with st.spinner(label):
            yield None


def subjects_for(stage: str, grade: str):
    if stage in ["الابتدائية", "الإعدادية"]:
        return ["علوم"]
    if stage == "الثانوية":
        if grade == "الأول":
            return ["علوم متكاملة"]
        return ["كيمياء", "فيزياء", "أحياء"]
    return ["علوم"]


def 
