import streamlit as st
import nest_asyncio

# تفعيل المعالجة المتزامنة
nest_asyncio.apply()

# ==========================================
# 1. إعدادات الصفحة
# ==========================================
st.set_page_config(page_title="المعلم الذكي", page_icon="🎓", layout="wide")

# CSS: إجبار النصوص على اللون الأسود وتوضيح العناصر
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@500;800&display=swap');
    
    html, body, [class*="css"], p, h1, h2, h3, div, span, label {
        font-family: 'Tajawal', sans-serif;
        color: #000000 !important;
    }
    
    /* خلفية بيضاء */
    .stApp {
        background-color: #ffffff;
    }

    /* تحسين التبويبات */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        background-color: #f0f2f6;
        border-radius: 8px;
        color: #000000;
        font-weight: bold;
    }
    .stTabs [aria-selected="true"] {
        background-color: #2196F3 !important;
        color: #FFFFFF !important;
    }

    /* رسائل المحادثة */
    .chat-user {
        background-color: #E3F2FD;
        padding: 12px;
        border-radius: 10px;
        margin: 5px 0;
        text-align: right;
        border: 1px solid #BBDEFB;
    }
    .chat-ai {
        background-color: #F5F5F5;
        padding: 12px;
        border-radius: 10px;
        margin: 5px 0;
        text-align: right;
        border: 1px solid #E0E0E0;
    }
</style>
""", unsafe_allow_html=True)

import time
import asyncio
import re
import random
import threading
from io import BytesIO
from datetime import datetime
import pytz

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
DRIVE_FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "") 

DAILY_FACTS = [
    "هل تعلم؟ قلب الجمبري يقع في رأسه!",
    "هل تعلم؟ العسل هو الطعام الوحيد الذي لا يفسد!",
]

RANKS = {
    0: "مبتدئ 🌱", 50: "مستكشف 🔭", 150: "مبتكر 💡", 300: "عالم 🔬", 500: "عبقري 🏆"
}

# ==========================================
# 🛠️ الخدمات الخلفية
# ==========================================

@st.cache_resource
def get_gspread_client():
    if "gcp_service_account" not in st.secrets: return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        scope = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds)
    except: return None

def get_sheet_data():
    client = get_gspread_client()
    if not client: return None
    try:
        val = client.open(CONTROL_SHEET_NAME).sheet1.acell('B1').value
        return str(val).strip()
    except: return None

def _bg_task(task_type, data):
    if "gcp_service_account" not in st.secrets: return
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        client = 
