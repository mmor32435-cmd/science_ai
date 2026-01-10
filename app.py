import streamlit as st
import nest_asyncio

# تفعيل المعالجة المتزامنة للصوت
nest_asyncio.apply()

# ==========================================
# 1. إعدادات الصفحة (يجب أن يكون أول سطر)
# ==========================================
st.set_page_config(page_title="المعلم الذكي", page_icon="🎓", layout="wide")

# ==========================================
# 2. تهيئة المتغيرات (أهم خطوة لمنع الشاشة البيضاء)
# ==========================================
if "auth_status" not in st.session_state:
    st.session_state.auth_status = False
    st.session_state.user_type = "none"
    st.session_state.user_name = ""
    st.session_state.student_grade = ""
    st.session_state.current_xp = 0
    st.session_state.last_audio_bytes = None
    st.session_state.language = "العربية"
    st.session_state.ref_text = ""
    st.session_state.chat_history = []

# ==========================================
# 3. التصميم (CSS) - بسيط ومضمون
# ==========================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@500;800&display=swap');
    
    /* تطبيق الخط واللون الأسود على كل العناصر */
    html, body, [class*="css"], .stMarkdown, h1, h2, h3, p, div {
        font-family: 'Tajawal', sans-serif !important;
        color: #000000 !important;
    }
    
    /* خلفية بيضاء نظيفة */
    .stApp {
        background-color: #ffffff;
    }

    /* تحسين شكل الأزرار */
    .stButton>button {
        background-color: #2196F3;
        color: white !important;
        border-radius: 10px;
        width: 100%;
    }

    /* رسائل الشات */
    .user-msg {
        background-color: #E3F2FD;
        padding: 10px;
        border-radius: 10px;
        margin: 5px 0;
        text-align: right;
        border: 1px solid #90CAF9;
    }
    .ai-msg {
        background-color: #F5F5F5;
        padding: 10px;
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
    "هل تعلم؟ الزرافة لا تمتلك أحبالاً صوتية!",
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
        return str(client.open(CONTROL_SHEET_NAME).sheet1.acell('B1').value).strip()
    except: return None

def _bg_task(task_type, data):
    if "gcp_service_account" not in st.secrets: return
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        client = gspread.authorize(service_account.Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets']))
        wb = client.open(CONTROL_SHEET_NAME)
        tz = pytz.timezone('Africa/Cairo')
        now_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

        if task_type == "login":
            try: sheet = wb.worksheet("Logs")
            except: sheet = wb.sheet1
            sheet.append_row([now_str, data['type'], data['name'], data['details']])
        elif task_type == "activity":
            try: sheet = wb.worksheet("Activity")
            except: return
            sheet.append_row([now_str, data['name'], data['input_type'], str(data['text'])[:1000]])
        elif task_type == "xp":
            try: sheet = wb.worksheet("Gamification")
            except: return
            cell = sheet.find(data['name'])
            if cell:
                curr = int(sheet.cell(cell.row, 2).value or 0)
                sheet.update_cell(cell.row, 2, curr + data['points'])
            else:
                sheet.append_row([data['name'], data['points']])
    except: pass

def log_login(user_name, user_type, details):
    threading.Thread(target=_bg_task, args=("login", {'name': user_name, 'type': user_type, 'details': details})).start()

def log_activity(user_name, input_type, text):
    threading.Thread(target=_bg_task, args=("activity", {'name': user_name, 'input_type': input_type, 'text': text})).start()

def update_xp(user_name, points):
    if 'current_xp' in st.session_state:
        st.session_state.current_xp += points
    threading.Thread(target=_bg_task, args=("xp", {'name': user_name, 'points': points})).start()

def get_current_xp(user_name):
    client = get_gspread_client()
    if not client: return 0
    try:
        sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
        cell = sheet.find(user_name)
        return int(sheet.cell(cell.row, 2).value or 0) if cell else 0
    except: return 0

# --- Google Drive ---
@st.cache_resource
def get_drive_service():
    if "gcp_service_account" not in st.secrets: return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/drive.readonly'])
        return build('drive', 'v3', credentials=creds)
    except: return None

def list_drive_files(service, folder_id):
    try:
        res = 
