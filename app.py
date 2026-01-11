import streamlit as st

# ==========================================
# 1. إعدادات الصفحة
# ==========================================
st.set_page_config(page_title="AI Science Tutor Pro", page_icon="🧬", layout="wide")

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
# 🎛️ الثوابت
# ==========================================
TEACHER_MASTER_KEY = "ADMIN_2024"
CONTROL_SHEET_NAME = "App_Control"
SESSION_DURATION_MINUTES = 60
DRIVE_FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "") 

# تعريف الألوان الجديدة
COLORS = {
    "deep_blue": "#1A2980",
    "royal_purple": "#26D0CE",
    "neon_pink": "#FF3CAC",
    "gold": "#FFD700"
}

DAILY_FACTS = [
    "هل تعلم؟ المخ يولد كهرباء تكفي لمصباح! 💡",
    "هل تعلم؟ العظام أقوى من الخرسانة بـ 4 مرات! 🦴",
    "هل تعلم؟ الأخطبوط لديه 3 قلوب! 🐙",
    "هل تعلم؟ العسل لا يفسد أبداً! 🍯",
    "هل تعلم؟ الضوء يستغرق 8 دقائق للوصول من الشمس إلى الأرض! ☀️",
    "هل تعلم؟ الزرافة تنام فقط 30 دقيقة يومياً! 🦒"
]

# ==========================================
# 🎨 تحسينات الواجهة
# ==========================================
def set_custom_theme():
    st.markdown(f"""
    <style>
        .stApp {{
            background: linear-gradient(135deg, {COLORS["deep_blue"]}, #0D1B4E);
            color: white;
        }}
        
        h1, h2, h3 {{
            font-family: 'Tajawal', sans-serif;
            background: linear-gradient(90deg, {COLORS["royal_purple"]}, {COLORS["neon_pink"]});
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: bold;
        }}
        
        .stButton>button {{
            background: linear-gradient(90deg, {COLORS["royal_purple"]}, {COLORS["neon_pink"]});
            color: white;
            border: none;
            border-radius: 25px;
            padding: 0.5rem 2rem;
            font-weight: bold;
            transition: all 0.3s ease;
        }}
        
        [data-testid="stSidebar"] {{
            background: rgba(10, 20, 50, 0.7);
        }}
        
        .stTextInput>div>div>input, .stSelectbox>div>div {{
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 10px;
            color: white;
        }}
        
        .stTabs [data-baseweb="tab-list"] {{
            background-color: rgba(255, 255, 255, 0.05);
            border-radius: 15px;
            padding: 0.5rem;
        }}
        
        .stTabs [data-baseweb="tab"] {{
            border-radius: 10px;
            color: white;
        }}
        
        .stTabs [aria-selected="true"] {{
            background-color: rgba(255, 255, 255, 0.1);
            color: {COLORS["gold"]};
        }}
    </style>
    
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;700&display=swap" rel="stylesheet">
    """, unsafe_allow_html=True)

# ==========================================
# 🛠️ الخدمات الخلفية
# ==========================================

# --- جداول جوجل ---
@st.cache_resource
def get_gspread_client():
    if "gcp_service_account" not in st.secrets:
        return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        scope = 
