import streamlit as st

# 1. إعدادات الصفحة (يجب أن تكون أول سطر)
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
# 🎛️ إعدادات التحكم والثوابت
# ==========================================

TEACHER_MASTER_KEY = "ADMIN_2024"
CONTROL_SHEET_NAME = "App_Control"
SESSION_DURATION_MINUTES = 60
# نتأكد من وجود المفتاح، لكن لا نوقف التطبيق إذا لم يوجد
DRIVE_FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "") 

DAILY_FACTS = [
    "هل تعلم؟ المخ يولد كهرباء تكفي لمصباح! 💡",
    "هل تعلم؟ العظام أقوى من الخرسانة بـ 4 مرات! 🦴",
    "هل تعلم؟ الأخطبوط لديه 3 قلوب! 🐙",
    "هل تعلم؟ العسل لا يفسد أبداً! 🍯",
    "هل تعلم؟ سرعة الضوء 300,000 كم/ث! ⚡"
]

# ==========================================
# 🛠️ الخدمات والدوال (Backend)
# ==========================================

@st.cache_resource
def get_gspread_client():
    if "gcp_service_account" in st.secrets:
        try:
            creds = service_account.Credentials.from_service_account_info(
                st.secrets["gcp_service_account"],
                scopes=['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
            )
            return gspread.authorize(creds)
        except: return None
    return None

def get_sheet_data():
    client = get_gspread_client()
    if not client: return None, None
    try:
        sheet = client.open(CONTROL_SHEET_NAME)
        daily_pass = str(sheet.sheet1.acell('B1').value).strip()
        return daily_pass, sheet
    except: return None, None

def update_daily_password(new_pass):
    client = get_gspread_client()
    if not client: return False
    try:
        client.open(CONTROL_SHEET_NAME).sheet1.update_acell('B1', new_pass)
        return True
    except: return False

def _log_bg(user_name, user_type, details, log_type="login"):
    client = get_gspread_client()
    if not client: return
    try:
        sheet_name = "Logs" if log_type == "login" else "Activity"
        try: sheet = client.open(CONTROL_SHEET_NAME).worksheet(sheet_name)
        except: sheet = client.open(CONTROL_SHEET_NAME).sheet1
        
        tz = pytz.timezone('Africa/Cairo')
        now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        
        if log_type == "login":
            sheet.append_row([now, user_type, user_name, details])
        else:
            sheet.append_row([now, user_name, details[0], str(details[1])[:500]])
    except: pass

def log_login_to_sheet(user_name, user_type, details=""):
    threading.Thread(target=_log_bg, args=(user_name, user_type, details, "login")).start()

def log_activity(user_name, input_type, question_text):
    threading.Thread(target=_log_bg, args=(user_name, input_type, [input_type, question_text], "activity")).start()

def _xp_bg(user_name, points):
    client = get_gspread_client()
    if not client: return
    try:
        try: sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
        except: return
        cell = sheet.find(user_name)
        if cell:
            curr = int(sheet.cell(cell.row, 2).value)
            sheet.update_cell(cell.row, 2, curr + points)
        else:
            sheet.append_row([user_name, points])
    except: pass

def update_xp(user_name, points_to_add):
    if 'current_xp' in st.session_state:
        st.session_state.current_xp += points_to_add
    threading.Thread(target=_xp_bg, args=(user_name, points_to_add)).start()

def get_current_xp(user_name):
    client = get_gspread_client()
    if not client: return 0
    try:
        sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
        cell = sheet.find(user_name)
        if cell: return int(sheet.cell(cell.row, 2).value)
    except: return 0
    return 0

def get_leaderboard():
    client = get_gspread_client()
    if not client: return []
    try:
        sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        df['XP'] = pd.to_numeric(df['XP'], errors='coerce').fillna(0)
        return df.sort_values(by='XP', ascending=False).head(5).to_dict('records')
    except: return []

def clear_old_data():
    client = get_gspread_client()
    if not client: return False
    try:
        for s in ["Logs", "Activity", "Gamification"]:
            try: 
                ws = client.open(CONTROL_SHEET_NAME).worksheet(s)
                ws.resize(rows=1); ws.resize(rows=100)
            except: pass
        return True
    except: return False

def get_stats_for_admin():
    client = get_gspread_client()
    if not client: return 0, []
    try:
        sheet = client.open(CONTROL_SHEET_NAME)
        try: logs = sheet.worksheet("Logs").get_all_values()
        except: logs = []
        try: qs = sheet.worksheet("Activity").get_all_values()
        except: qs = []
        return len(logs)-1 if logs else 0, qs[-5:] if qs else []
    except: return 0, []

def get_chat_text(history):
    text = "--- Chat History ---\n\n"
    for q, a in history: text += f"Student: {q}\nAI Tutor: {a}\n\n"
    return text

def create_certificate(student_name):
    txt = f"CERTIFICATE OF EXCELLENCE\n\nAwarded to: {student_name}\n\nFor achieving 100 XP in AI Science Tutor.\n\nSigned: Mr. Elsayed Elbadawy"
    return txt.encode('utf-8')

def stream_text_effect(text):
    for word in text.split(" "):
        yield word + " "
        time.sleep(0.04)

@st.cache_resource
def get_drive_service():
    if "gcp_service_account" in st.secrets:
        try:
            creds = service_account.Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=['https://www.googleapis.com/auth/drive.readonly'])
            return build('drive', 'v3', credentials=creds)
        except: return None
    return None

def list_drive_files(service, folder_id):
    try: return service.files().list(q=f"'{folder_id}' in parents", fields="files(id, name)").execute().get('files', [])
    except: return []

def download_pdf_text(service, file_id):
    try:
        request = service.files().get_media(fileId=file_id)
        file_io = BytesIO()
        downloader = MediaIoBaseDownload(file_io, request)
        done = False
        while done is False: status, done = downloader.next_chunk()
        file_io.seek(0)
        reader = PyPDF2.PdfReader(file_io)
        text = ""
        for page in reader.pages: text += page.extract_text() + "\n"
        return text
    except: return ""

def get_voice_config(lang):
    if lang == "English": return "en-US-AndrewNeural", "en-US"
    else: return "ar-EG-ShakirNeural", "ar-EG"

def 
