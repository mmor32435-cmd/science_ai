import streamlit as st

# ✅ لازم يكون أول أمر Streamlit
st.set_page_config(page_title="المعلم الذكي", layout="wide", page_icon="🎓")

import os
import time
import tempfile
import logging
import random
from contextlib import contextmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("smart_teacher")

APP_VERSION = "2026-02-02"

# =========================
# Optional imports (Safe)
# =========================
try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
    GENAI_IMPORT_ERROR = ""
except Exception as e:
    GENAI_AVAILABLE = False
    GENAI_IMPORT_ERROR = str(e)

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    DRIVE_AVAILABLE = True
    DRIVE_IMPORT_ERROR = ""
except Exception as e:
    DRIVE_AVAILABLE = False
    DRIVE_IMPORT_ERROR = str(e)

try:
    from streamlit_mic_recorder import mic_recorder
    MIC_AVAILABLE = True
except Exception:
    MIC_AVAILABLE = False

try:
    import edge_tts
    import asyncio
    TTS_AVAILABLE = True
except Exception:
    TTS_AVAILABLE = False


# =========================
# Cache compatibility
# =========================
def _cache_resource(*dargs, **dkwargs):
    if hasattr(st, "cache_resource"):
        return st.cache_resource(*dargs, **dkwargs)
    if hasattr(st, "experimental_singleton"):
        return st.experimental_singleton(*dargs, **dkwargs)
    return st.cache(*dargs, **dkwargs)


def _cache_data(*dargs, **dkwargs):
    if hasattr(st, "cache_data"):
        return st.cache_data(*dargs, **dkwargs)
    if hasattr(st, "experimental_memo"):
        return st.experimental_memo(*dargs, **dkwargs)
    return st.cache(*dargs, **dkwargs)


# =========================
# CSS
# =========================
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

# =========================
# Constants
# =========================
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

# Allowlist لمنع موديلات preview/deep-research اللي بتجيب quota=0
ALLOWED_MODELS = [
    "models/gemini-2.0-flash",
    "models/gemini-2.0-flash-lite",
    "models/gemini-1.5-flash",
    "models/gemini-1.5-pro",
]
BLOCKED_SUBSTRINGS = ["deep-research", "preview"]


# =========================
# Helpers
# =========================
@contextmanager
def status_box(label):
    if hasattr(st, "status"):
        with st.status(label, expanded=True) as s:
            yield s
    else:
        with st.spinner(label):
            yield None


def _status_update(status_obj, label=None, state=None):
    try:
        if status_obj is None:
            return
        if hasattr(status_obj, "update"):
            kwargs = {}
            if label is not None:
                kwargs["label"] = label
            if state is not None:
                kwargs["state"] = state
            status_obj.update(**kwargs)
    except Exception:
        pass


def subjects_for(stage, grade):
    if stage in ["الابتدائية", "الإعدادية"]:
        return ["علوم"]
    if stage == "الثانوية":
        if grade == "الأول":
            return ["علوم متكاملة"]
        return ["كيمياء", "فيزياء", "أحياء"]
    return ["علوم"]


def generate_file_name_search(stage, grade, subject, lang_type):
    g_num = GRADE_MAP.get(grade, "1")
    lang_code = "En" if lang_type == "English" else "Ar"

    if stage == "الابتدائية":
        return "Grade{}_{}".format(g_num, lang_code)
    if stage == "الإعدادية":
        return "Prep{}_{}".format(g_num, lang_code)
    if stage == "الثانوية":
        if grade == "الأول":
            return "Sec1_Integrated_{}".format(lang_code)
        sub_code = SUBJECT_MAP.get(subject, "Chem")
        return "Sec{}_{}_{}".format(g_num, sub_code, lang_code)
    return ""


def get_api_keys():
    try:
        keys = st.secrets.get("GOOGLE_API_KEYS", [])
        if isinstance(keys, str):
            return [k.strip() for k in keys.split(",") if k.strip()]
        if isinstance(keys, (list, tuple)):
            return [str(k).strip() for k in keys if str(k).strip()]
        return []
    except Exception as e:
        logger.error("Failed to read GOOGLE_API_KEYS: %s", e)
        return []


GOOGLE_API_KEYS = get_api_keys()


def configure_genai_by_key(key):
    if not GENAI_AVAILABLE:
        return False
    try:
        genai.configure(api_key=key)
        return True
    except Exception as e:
        logger.error("genai.configure failed: %s", e)
        return False


def normalize_model_name(name):
    if not name:
        return name
    if name.startswith("models/"):
        return name.split("/", 1)[1]
    return name


def _is_quota_zero_error(msg):
    if not msg:
        return False
    s = str(msg).lower()
    # حالات شائعة
    if "quota exceeded" in s and "limit: 0" in s:
        return True
    if "generate_content_free_tier_requests" in s and "limit: 0" in s:
        return True
    if "limit: 0" in s and "quota" in s:
