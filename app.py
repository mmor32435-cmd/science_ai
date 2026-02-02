import streamlit as st
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import tempfile
import os
import time
import asyncio
import logging
from io import BytesIO
from typing import Optional, Tuple, List

# استيراد المكتبات الاختيارية
try:
    from streamlit_mic_recorder import mic_recorder
    MIC_AVAILABLE = True
except ImportError:
    MIC_AVAILABLE = False

try:
    import edge_tts
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False

try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False

# إعداد التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ======================================
# إعدادات الصفحة
# ======================================
st.set_page_config(
    page_title="المعلم الذكي",
    layout="wide",
    page_icon="🎓",
    initial_sidebar_state="expanded"
)
