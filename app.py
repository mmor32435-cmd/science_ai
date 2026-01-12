# ============================================================
# 🧬 AI Science Tutor Pro — FINAL PRODUCTION VERSION
# ============================================================

import streamlit as st
import time, json, re, os, base64, asyncio, random, logging
from io import BytesIO
from datetime import datetime
from typing import List, Tuple, Optional
from PIL import Image
import pytz

# =========================
# Optional Providers
# =========================
try:
    import google.generativeai as genai
except:
    genai = None

try:
    import openai
except:
    openai = None

try:
    import edge_tts
except:
    edge_tts = None

try:
    import speech_recognition as sr
except:
    sr = None

# =========================
# Streamlit Config
# =========================
st.set_page_config(
    page_title="AI Science Tutor Pro",
    page_icon="🧬",
    layout="wide"
)

# =========================
# Secrets
# =========================
OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY", "")
GOOGLE_API_KEYS = st.secrets.get("GOOGLE_API_KEYS", [])
SESSION_DURATION_MINUTES = int(st.secrets.get("SESSION_DURATION_MINUTES", 60))
RATE_LIMIT_SECONDS = 1

# =========================
# Logging
# =========================
logger = logging.getLogger("Tutor")
logger.setLevel(logging.INFO)

# =========================
# Utilities
# =========================
def now():
    return datetime.now(pytz.timezone("Africa/Cairo")).strftime("%Y-%m-%d %H:%M:%S")

def safe_rerun():
    try:
        st.rerun()
    except:
        st.stop()

# =========================
# AI Abstraction Layer
# =========================
_last_provider_errors: List[str] = []

def call_ai(prompt: str) -> str:
    global _last_provider_errors
    _last_provider_errors = []

    # ---- Google Gemini ----
    if genai and GOOGLE_API_KEYS:
        for key in GOOGLE_API_KEYS:
            try:
                genai.configure(api_key=key)
                model = genai.GenerativeModel("gemini-1.5-flash")
                return model.generate_content(prompt).text
            except Exception as e:
                _last_provider_errors.append(f"Google: {e}")

    # ---- OpenAI ----
    if openai and OPENAI_API_KEY:
        try:
            openai.api_key = OPENAI_API_KEY
            r = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=700
            )
            return r.choices[0].message.content
        except Exception as e:
            _last_provider_errors.append(f"OpenAI: {e}")

    raise RuntimeError("No AI provider available")

def safe_call(prompt: str, retries=3) -> Tuple[bool, str]:
    last_err = ""
    for i in range(retries):
        try:
            return True, call_ai(prompt)
        except Exception as e:
            last_err = str(e)
            time.sleep(2 ** i)
    return False, last_err

# =========================
# TTS
# =========================
async def _tts_async(text: str, voice: str):
    comm = edge_tts.Communicate(text, voice)
    buf = BytesIO()
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    return buf.getvalue()

def tts(text: str, lang: str):
    if not edge_tts:
        return None
    voice = "ar-EG-ShakirNeural" if lang == "العربية" else "en-US-ChristopherNeural"
    try:
        return asyncio.run(_tts_async(text[:1200], voice))
    except:
        return None

# =========================
# Session Init
# =========================
if "auth" not in st.session_state:
    st.session_state.update({
        "auth": False,
        "user": "",
        "xp": 0,
        "lang": "العربية",
        "start": time.time(),
        "last_req": None
    })

# =========================
# Session Expiry
# =========================
if time.time() - st.session_state.start > SESSIO_
