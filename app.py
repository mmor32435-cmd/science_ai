import streamlit as st
import os
import re
import io
import json
import time
import random
import asyncio
import tempfile
import hashlib
from typing import Optional, List, Dict, Any, Tuple

from PIL import Image

# Google & External Libs
import gspread
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder
import edge_tts
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# OCR & Image Processing
from pdf2image import convert_from_path
import pytesseract

# LangChain & AI
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import PromptTemplate
from langchain.chains.question_answering import load_qa_chain
from langchain_core.documents import Document

# =========================
# Page config + CSS
# =========================
st.set_page_config(
    page_title="المعلم العلمي | السيد البدوي",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
html, body, .stApp { font-family: 'Cairo', sans-serif !important; direction: rtl; text-align: right; }
.stApp { background: radial-gradient(circle at top, #f7fbff, #f4f6f8 55%, #eef2f6); }
.header-box {
  background: linear-gradient(90deg, #061a40 0%, #0353a4 50%, #006daa 100%);
  padding: 1.6rem; border-radius: 18px; text-align: center;
  margin-bottom: 1.2rem; box-shadow: 0 10px 30px rgba(0,0,0,0.14);
}
.header-box h1, .header-box h3 { color: #ffffff !important; margin: 0.15rem 0; }
.badge {
  display:inline-block; padding: 0.25rem 0.7rem; border-radius: 999px;
  background: rgba(255,255,255,0.18); color: #fff; font-size: 0.95rem;
  border: 1px solid rgba(255,255,255,0.25);
}
.stTextInput input, .stTextArea textarea {
  background-color: #ffffff !important; color: #000000 !important;
  border: 1.8px solid #0353a4 !important; border-radius: 10px !important;
}
div[data-baseweb="select"] > div {
  background-color: #ffffff !important; border: 1.8px solid #0353a4 !important; border-radius: 10px !important;
}
.stButton>button {
  background: linear-gradient(90deg, #0353a4 0%, #061a40 100%) !important;
  color: #ffffff !important; border: none; border-radius: 12px;
  height: 50px; width: 100%; font-size: 18px !important; font-weight: 700 !important;
}
.stChatMessage { background-color: #ffffff !important; border: 1px solid #d9e2ef !important; border-radius: 14px !important; }
small.muted { color: #6b7280; }
</style>
""", unsafe_allow_html=True)

# =========================
# Secrets
# =========================
TEACHER_NAME = st.secrets.get("TEACHER_NAME", "الأستاذ / السيد البدوي")
TEACHER_KEY = st.secrets.get("TEACHER_MASTER_KEY", "ADMIN")
SHEET_NAME = st.secrets.get("CONTROL_SHEET_NAME", "App_Control")
CONTROL_TAB_NAME = st.secrets.get("CONTROL_TAB_NAME", "")
FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "")
GOOGLE_API_KEYS = st.secrets.get("GOOGLE_API_KEYS", [])

RESULTS_TAB_NAME = st.secrets.get("RESULTS_TAB_NAME", "Results")
ASSIGNMENTS_TAB_NAME = st.secrets.get("ASSIGNMENTS_TAB_NAME", "Assignments")
SUBMISSIONS_TAB_NAME = st.secrets.get("SUBMISSIONS_TAB_NAME", "Submissions")

CHROMA_PERSIST_DIR = st.secrets.get("CHROMA_PERSIST_DIR", "./chroma_db")
os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)

if isinstance(GOOGLE_API_KEYS, str):
    GOOGLE_API_KEYS = [k.strip() for k in GOOGLE_API_KEYS.split(",") if k.strip()]

st.markdown(f"""
<div class="header-box">
  <h1>{TEACHER_NAME}</h1>
  <h3>المنصة التعليمية الذكية للعلوم</h3>
  <div class="badge">شات • ميكروفون • OCR • واجبات • اختبارات • عربي/English</div>
</div>
""", unsafe_allow_html=True)

# =========================
# Session State
# =========================
def init_state():
    if "user_data" not in st.session_state:
        st.session_state.user_data = {"logged_in": False, "role": None, "name": ""}
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "debug_enabled" not in st.session_state:
        st.session_state.debug_enabled = False
    if "debug_log" not in st.session_state:
        st.session_state.debug_log = []
    if "book_data" not in st.session_state:
        st.session_state.book_data = {}
    if "vector_store" not in st.session_state:
        st.session_state.vector_store = None
    if "uploaded_context" not in st.session_state:
        st.session_state.uploaded_context = {"name": "", "text": "", "vs": None}
    if "tts_enabled" not in st.session_state:
        st.session_state.tts_enabled = False
    if "quiz" not in st.session_state:
        st.session_state.quiz = {"state": "off", "q": "", "model": ""}

init_state()

def dbg(event: str, data: Any = None):
    if not st.session_state.debug_enabled:
        return
    st.session_state.debug_log.append({"t": time.strftime("%H:%M:%S"), "event": event, "data": data})
    st.session_state.debug_log = st.session_state.debug_log[-500:]

# =========================
# Maps
# =========================
STAGES = ["الابتدائية", "الإعدادية", "الثانوية"]
GRADES = {
    "الابتدائية": ["الرابع", "الخامس", "السادس"],
    "الإعدادية": ["الأول", "الثاني", "الثالث"],
    "الثانوية": ["الأول", "الثاني", "الثالث"],
}
TERMS = ["الترم الأول", "الترم الثاني"]
LANGS = ["العربية (علوم)", "English (Science)"]

def subjects_for(stage: str, grade: str) -> List[str]:
    if stage in ["الابتدائية", "الإعدادية"]:
        return ["علوم"]
    if grade == "الأول":
        return ["علوم متكاملة"]
    return ["كيمياء", "فيزياء", "أحياء"]

def is_english(lang_ui: str) -> bool:
    return "English" in (lang_ui or "")

def ocr_lang(lang_ui: str) -> str:
    return "eng" if is_english(lang_ui) else "ara"

def ui(lang_ui: str, ar: str, en: str) -> str:
    return en if is_english(lang_ui) else ar

def term_token(term: str) -> str:
    return "T2" if "الثاني" 
