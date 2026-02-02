import streamlit as st

st.set_page_config(page_title="المعلم الذكي", layout="wide", page_icon="🎓")

import os
import time
import re
import random
import tempfile
import logging
from contextlib import contextmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("smart_teacher")

APP_VERSION = "2026-02-02"

# ---------- Safe imports ----------
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

# ---------- Cache wrappers (compat) ----------
def cache_resource(*dargs, **dkwargs):
    if hasattr(st, "cache_resource"):
        return st.cache_resource(*dargs, **dkwargs)
    if hasattr(st, "experimental_singleton"):
        return st.experimental_singleton(*dargs, **dkwargs)
    return st.cache(*dargs, **dkwargs)

def cache_data(*dargs, **dkwargs):
    if hasattr(st, "cache_data"):
        return st.cache_data(*dargs, **dkwargs)
    if hasattr(st, "experimental_memo"):
        return st.experimental_memo(*dargs, **dkwargs)
    return st.cache(*dargs, **dkwargs)

# ---------- UI helpers ----------
@contextmanager
def spinner_box(text):
    with st.spinner(text):
        yield

HAS_CHAT_UI = hasattr(st, "chat_message") and hasattr(st, "chat_input")

@contextmanager
def chat_block(role):
    if HAS_CHAT_UI:
        with st.chat_message(role):
            yield
    else:
        title = "المستخدم" if role == "user" else "المعلم"
        st.markdown("**{}:**".format(title))
        yield
        st.markdown("---")

def chat_input_box(label):
    if HAS_CHAT_UI:
        return st.chat_input(label)
    return st.text_input(label)

# ---------- Constants ----------
FOLDER_ID = "1ub4ML8q4YCM_VZR991XXQ6hBBas2X6rS"

MAX_RETRIES = 4
BASE_RETRY_DELAY = 1.5
MAX_BACKOFF = 12

STAGES = ["الابتدائية", "الإعدادية", "الثانوية"]
GRADES = {
    "الابتدائية": ["الرابع", "الخامس", "السادس"],
    "الإعدادية": ["الأول", "الثاني", "الثالث"],
    "الثانوية": ["الأول", "الثاني", "الثالث"],
}
TERMS = ["الترم الأول", "الترم الثاني"]

GRADE_MAP = {
    "الرابع": "4", "الخامس": "5", "السادس": "6",
    "الأول": "1", "الثاني": "2", "الثالث": "3"
}
SUBJECT_MAP = {"كيمياء": "Chem", "فيزياء": "Physics", "أحياء": "Biology"}

# موديلات مسموحة فقط (تجنب preview / deep-research)
ALLOWED_MODELS = [
    "models/gemini-2.0-flash",
    "models/gemini-2.0-flash-lite",
    "models/gemini-1.5-flash",
    "models/gemini-1.5-pro",
]
BLOCKED_SUBSTRINGS = ["deep-research", "preview"]

# ---------- Core helpers ----------
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
            out = []
            for k in keys:
                kk = str(k).strip()
                if kk:
                    out.append(kk)
            return out
        return []
    except Exception as e:
        logger.error("Failed to read GOOGLE_API_KEYS: %s", e)
        return []

GOOGLE_API_KEYS = get_api_keys()

def normalize_model_name(name):
    if not name:
        return name
    if name.startswith("models/"):
        return name.split("/", 1)[1]
    return name

def is_quota_hard_fail(err):
    if err is None:
        return False
    s = str(err).lower()
    if "check your plan and billing" in s:
        return True
    if ("limit: 0" in s) and ("quota" in s or "free_tier" in s):
        return True
    if "requests per day" in s or "per day" in s:
        return True
    return False

def extract_retry_seconds(err):
    if not err:
        return None
    s = str(err)
    m = re.search(r"retry in ([0-9.]+)s", s, flags=re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            return None
    m2 = re.search(r"retry_delay\s*\{\s*seconds:\s*(\d+)\s*\}", s, flags=re.IGNORECASE)
    if m2:
        try:
            return float(m2.group(1))
        except Exception:
            return None
    return None

# ---------- Google Drive ----------
@cache_resource(show_spinner=False)
def get_drive_service():
    if not DRIVE_AVAILABLE:
        return None
    try:
        if "gcp_service_account" not in st.secrets:
            return None
        creds_dict = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_dict and isinstance(creds_dict["private_key"], str):
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        credentials = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=["https://www.googleapis.com/auth/drive.readonly"],
        )
        return build("drive", "v3", credentials=credentials, cache_discovery=False)
    except Exception as e:
        logger.error("Drive service 
