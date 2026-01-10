import streamlit as st

# 1. إعدادات الصفحة (أول سطر إلزامي)
st.set_page_config(page_title="AI Science Tutor Pro", page_icon="🧬", layout="wide")

import time
import google.generativeai as genai
import asyncio
import edge_tts
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder
from io import BytesIO
import re
from datetime import datetime
import pytz
from PIL import Image
import PyPDF2
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import gspread
from fpdf import FPDF
import pandas as pd
import random
import graphviz
import matplotlib.pyplot as plt
import threading

# ==========================================
# 🎛️ الثوابت
# ==========================================
TEACHER_MASTER_KEY = "ADMIN_2024"
CONTROL_SHEET_NAME = "App_Control"
SESSION_DURATION_MINUTES = 60
DRIVE_FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "") 

DAILY_FACTS = [
    "هل تعلم؟ المخ يولد كهرباء تكفي لمصباح! 💡",
    "هل تعلم؟ العظام أقوى من الخرسانة بـ 4 مرات! 🦴",
    "هل تعلم؟ الأخطبوط لديه 3 قلوب! 🐙",
    "هل تعلم؟ العسل لا يفسد أبداً! 🍯",
    "هل تعلم؟ سرعة الضوء 300,000 كم/ث! ⚡"
]

# ==========================================
# 🛠️ الخدمات والدوال المساعدة
# ==========================================

@st.cache_resource
def get_gspread_client():
    if "gcp_service_account" not in st.secrets:
        return None
    try:
        creds_dict = st.secrets["gcp_service_account"]
        scopes = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds)
    except:
        return None

def get_sheet_data():
    client = get_gspread_client()
    if not client: return None
    try:
        sheet = client.open(CONTROL_SHEET_NAME)
        val = sheet.sheet1.acell('B1').value
        return str(val).strip()
    except: return None

def update_daily_password(new_pass):
    client = get_gspread_client()
    if not client: return False
    try:
        client.open(CONTROL_SHEET_NAME).sheet1.update_acell('B1', new_pass)
        return True
    except: return False

# --- دوال التسجيل في الخلفية ---
def _log_bg(user_name, user_type, details, log_type):
    client = get_gspread_client()
    if not client: return
    try:
        sheet = None
        if log_type == "login":
            try: sheet = client.open(CONTROL_SHEET_NAME).worksheet("Logs")
            except: sheet = client.open(CONTROL_SHEET_NAME).sheet1
        else:
            try: sheet = client.open(CONTROL_SHEET_NAME).worksheet("Activity")
            except: return

        tz = pytz.timezone('Africa/Cairo')
        now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        
        if log_type == "login":
            row = [now, user_type, user_name, details]
            sheet.append_row(row)
        else:
            q_text = str(details[1])[:500]
            row = [now, user_name, details[0], q_text]
            sheet.append_row(row)
    except: pass

def log_login(user_name, user_type, details):
    t = threading.Thread(target=_log_bg, args=(user_name, user_type, details, "login"))
    t.start()

def log_activity(user_name, input_type, text):
    t = threading.Thread(target=_log_bg, args=(user_name, input_type, [input_type, text], "activity"))
    t.start()

def 
