from __future__ import annotations

import os
import re
import time
import random
import tempfile
from typing import Optional, Dict, Any, List, Tuple

import streamlit as st

# ----------------------------
# Page config (must be first Streamlit command)
# ----------------------------
st.set_page_config(page_title="المعلم الذكي", layout="wide", page_icon="🎓")

# ----------------------------
# Optional imports with graceful degradation
# ----------------------------
GENAI_OK, GENAI_ERR = True, ""
DRIVE_OK, DRIVE_ERR = True, ""

try:
    import google.generativeai as genai
except Exception as e:
    GENAI_OK, GENAI_ERR = False, str(e)

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
except Exception as e:
    DRIVE_OK, DRIVE_ERR = False, str(e)

# ----------------------------
# Constants / Config
# ----------------------------
FOLDER_ID = "1ub4ML8q4YCM_VZR991XXQ6hBBas2X6rS"

MAX_RETRIES = 4
BASE_DELAY = 1.5
MAX_DELAY = 12.0

ALLOWED_MODELS = [
    "models/gemini-2.0-flash",
    "models/gemini-2.0-flash-lite",
    "models/gemini-1.5-flash",
    "models/gemini-1.5-pro",
]

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

HAS_CHAT_UI = hasattr(st, "chat_message") and hasattr(st, "chat_input")


# ----------------------------
# Utilities
# ----------------------------
def _rerun():
    """Compat rerun across Streamlit versions."""
    try:
        st.rerun()
    except Exception:
        st.experimental_rerun()


def normalize_model_name(name: str) -> str:
    """google-generativeai accepts 'gemini-...' not necessarily 'models/...'.
    We'll keep behavior robust."""
    if not name:
        return name
    return name.split("/", 1)[1] if name.startswith("models/") else name


def is_quota_hard_fail(err: Exception | None) -> bool:
    if err is None:
        return False
    s = str(err).lower()
    return (
        "check your plan and billing" in s
        or "limit: 0" in s
        or "requests per day" in s
        or "billing" in s and "not enabled" in s
    )


def extract_retry_seconds(err: Exception | None) -> Optional[float]:
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


def escape_drive_query_value(value: str) -> str:
    """Escape single quotes for Drive query strings."""
    return (value or "").replace("'", "\\'")


def get_api_keys() -> List[str]:
    """Reads keys from Streamlit secrets. Supports list or comma-separated string."""
    try:
        keys = st.secrets.get("GOOGLE_API_KEYS", [])
        if isinstance(keys, str):
            return [k.strip() for k in keys.split(",") if k.strip()]
        if isinstance(keys, (list, tuple)):
            return [str(k).strip() for k in keys if str(k).strip()]
        return []
    except Exception:
        return []


def subjects_for(stage: str, grade: str) -> List[str]:
    if stage in ["الابتدائية", "الإعدادية"]:
        return ["علوم"]
    if stage == "الثانوية":
        if grade == "الأول":
            return ["علوم متكاملة"]
        return ["كيمياء", "فيزياء", "أحياء"]
    return ["علوم"]


def generate_search_name(stage: str, grade: str, subject: str, lang: str) -> str:
    g = GRADE_MAP.get(grade, "1")
    code = "En" if lang == "English" else "Ar"

    if stage == "الابتدائية":
        return f"Grade{g}_{code}"
    if stage == "الإعدادية":
        return f"Prep{g}_{code}"
    if stage == "الثانوية":
        if grade == "الأول":
            return f"Sec1_Integrated_{code}"
        s = SUBJECT_MAP.get(subject, "Chem")
        return f"Sec{g}_{s}_{code}"
    return ""


# ----------------------------
# Google Drive helpers (cached)
# 
