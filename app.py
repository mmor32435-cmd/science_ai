import streamlit as st
import time
import asyncio
import re
import random
import threading
from io import BytesIO
from datetime import datetime
import pytz

# المكتبات الخارجية
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
import graphviz

# ==========================================
# 1. إعدادات الصفحة (يجب أن تكون أول سطر)
# ==========================================
st.set_page_config(
    page_title="AI Science Tutor Pro",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# 2. تهيئة المتغيرات (لمنع اختفاء شاشة الدخول)
# ==========================================
if "auth_status" not in st.session_state:
    st.session_state["auth_status"] = False
if "user_type" not in st.session_state:
    st.session_state["user_type"] = "none"
if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []
if "student_grade" not in st.session_state:
    st.session_state["student_grade"] = ""
if "current_xp" not in st.session_state:
    st.session_state["current_xp"] = 0
if "last_audio_bytes" not in st.session_state:
    st.session_state["last_audio_bytes"] = None
if "language" not in st.session_state:
    st.session_state["language"] = "العربية"
if "ref_text" not in st.session_state:
    st.session_state["ref_text"] = ""
if "user_name" not in st.session_state:
    st.session_state["user_name"] = "Guest"
if "q_active" not in st.session_state:
    st.session_state["q_active"] = False
if "q_curr" not in st.session_state:
    st.session_state["q_curr"] = ""

# ==========================================
# 3. الثوابت
# ==========================================
TEACHER_MASTER_KEY = "ADMIN_2024"
CONTROL_SHEET_NAME = "App_Control"
DRIVE_FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "") 

DAILY_FACTS = [
    "هل تعلم؟ المخ يولد كهرباء تكفي لمصباح! 💡",
    "هل تعلم؟ العظام أقوى من الخرسانة بـ 4 مرات! 🦴",
    "هل تعلم؟ الأخطبوط لديه 3 قلوب! 🐙",
    "هل تعلم؟ العسل لا يفسد أبداً! 🍯",
]

# ==========================================
# 4. الدوال والخدمات
