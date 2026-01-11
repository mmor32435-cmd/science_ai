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
# 1. إعدادات الصفحة
# ==========================================
st.set_page_config(
    page_title="AI Science Tutor Pro",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# 2. الثوابت
# ==========================================
TEACHER_MASTER_KEY = "ADMIN_2024"
CONTROL_SHEET_NAME = "App_Control"
DRIVE_FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "") 

DAILY_FACTS = [
    "هل تعلم؟ المخ يولد كهرباء تكفي لمصباح! 💡",
    "هل تعلم؟ العظام أقوى من الخرسانة بـ 4 مرات! 🦴",
    "هل تعلم؟ الأخطبوط لديه 3 قلوب! 🐙",
    "هل تعلم؟ العسل لا يفسد أبداً! 🍯",
    "هل تعلم؟ سرعة الضوء هي 300,000 كم/ثانية! ⚡",
]

# ==========================================
# 3. دوال الخدمات (Backend)
# ==========================================

# --- جداول جوجل ---
@st.cache_resource
def get_gspread_client():
    if "gcp_service_account" not in st.secrets:
        return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        scope = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds)
    except Exception:
        return None

def get_sheet_data():
    client = get_gspread_client()
    if not client:
        return None
    try:
        sheet = client.open(CONTROL_SHEET_NAME)
        val = sheet.sheet1.acell('B1').value
        return str(val).strip()
    except Exception:
        return None

# --- المعالجة الخلفية (تم تبسيطها لمنع الأخطاء) ---
def _bg_task(task_type, data):
    if "gcp_service_account" not in st.secrets:
        return
    try:
        client = get_gspread_client()
        if not client:
            return
        wb = client.open(CONTROL_SHEET_NAME)
        tz = pytz.timezone('Africa/Cairo')
        now_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

        if task_type == "login":
            try:
                sheet = wb.worksheet("Logs")
            except:
                sheet = wb.add_worksheet("Logs", 1000, 5)
            sheet.append_row([now_str, data['type'], data['name'], data['details']])

        elif task_type == "activity":
            try:
                sheet = wb.worksheet("Activity")
            except:
                sheet = wb.add_worksheet("Activity", 1000, 5)
            clean_text = str(data['text'])[:1000]
            sheet.append_row([now_str, data['name'], data['input_type'], clean_text])

        elif task_type == "xp":
            try:
                sheet = wb.worksheet("Gamification")
            except:
                sheet = wb.add_worksheet("Gamification", 1000, 3)
            try:
                cell = sheet.find(data['name'])
                if cell:
                    val = sheet.cell(cell.row, 2).value
                    curr = int(val) if val else 0
                    sheet.update_cell(cell.row, 2, curr + data['points'])
                else:
                    sheet.append_row([data['name'], data['points']])
            except:
                sheet.append_row([data['name'], data['points']])
    except Exception:
        pass

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
    if not client:
        return 0
    try:
        sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
        cell = sheet.find(user_name)
        if cell:
            val = sheet.cell(cell.row, 2).value
            return int(val) if val else 0
        return 0
    except:
        return 0

def get_leaderboard():
    client = get_gspread_client()
    if not client:
        return []
    try:
        sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        if df.empty:
            return []
        # التأكد من الأعمدة
        if 'XP' not in df.columns:
            if len(df.columns) >= 2:
                df.columns = ['Student_Name', 'XP'] + list(df.columns[2:])
            else:
                return []
        df['XP'] = pd.to_numeric(df['XP'], errors='coerce').fillna(0)
        return df.sort_values(by='XP', ascending=False).head(5).to_dict('records')
    except Exception:
        return []

# --- جوجل درايف ---
@st.cache_resource
def get_drive_service():
    if "gcp_service_account" not in st.secrets:
        return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/drive.readonly'])
        return build('drive', 'v3', credentials=creds)
    except Exception:
        return None

def list_drive_files(service, folder_id):
    try:
        q = f"'{folder_id}' in parents and trashed = false and mimeType = 'application/pdf'"
        res = service.files().list(q=q, fields="files(id, name)").execute()
        return res.get('files', [])
    except Exception:
        return []

def download_pdf_text(service, file_id):
    try:
        req = service.files().get_media(fileId=file_id)
        fh = BytesIO()
        downloader = MediaIoBaseDownload(fh, req)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        fh.seek(0)
        reader = PyPDF2.PdfReader(fh)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    except Exception:
        return ""

# --- الصوت ---
async def generate_audio_stream(text, voice_code):
    clean = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    clean = re.sub(r'[*#_`\[\]()><=~-]', ' ', clean)
    clean = re.sub(r'http\S+', ' ', clean)
    clean = " ".join(clean.split())
    if not clean:
        return None
    comm = edge_tts.Communicate(clean, voice_code, rate="-2%")
    mp3 = BytesIO()
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            mp3.write(chunk["data"])
    return mp3

def speech_to_text(audio_bytes, lang_code):
    r = sr.Recognizer()
    try:
        with sr.AudioFile(BytesIO(audio_bytes)) as source:
            r.adjust_for_ambient_noise(source, duration=0.5)
            audio_data = r.record(source)
            return r.recognize_google(audio_data, language=lang_code)
    except Exception:
        return None

# --- الذكاء الاصطناعي ---
def get_working_model():
    keys = st.secrets.get("GOOGLE_API_KEYS", [])
    if not keys:
        return None
    keys_copy = list(keys)
    random.shuffle(keys_copy)
    models = ['gemini-1.5-flash', 'gemini-pro', 'gemini-1.5-pro']
    for key in keys_copy:
        genai.configure(api_key=key)
        for m in models:
            try:
                model = genai.GenerativeModel(m)
                return model
            except:
                continue
    return None
