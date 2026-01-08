import streamlit as st
# يجب أن يكون set_page_config أول أمر Streamlit يتم تنفيذه
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

# ==========================================
# 🎛️ إعدادات التحكم
# ==========================================

TEACHER_MASTER_KEY = "ADMIN_2024"
CONTROL_SHEET_NAME = "App_Control"
SESSION_DURATION_MINUTES = 60
# نقلنا استدعاء السيكرتس هنا بعد set_page_config
DRIVE_FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "") 

DAILY_FACTS = [
    "هل تعلم؟ المخ يولد كهرباء تكفي لمصباح! 💡",
    "هل تعلم؟ العظام أقوى من الخرسانة بـ 4 مرات! 🦴",
    "هل تعلم؟ الأخطبوط لديه 3 قلوب! 🐙",
    "هل تعلم؟ العسل لا يفسد أبداً! 🍯",
    "هل تعلم؟ سرعة الضوء 300,000 كم/ث! ⚡"
]

# ==========================================
# 🛠️ الخدمات (شيت، درايف، صوت)
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

def log_login_to_sheet(user_name, user_type, details=""):
    client = get_gspread_client()
    if not client: return
    try:
        try: sheet = client.open(CONTROL_SHEET_NAME).worksheet("Logs")
        except: sheet = client.open(CONTROL_SHEET_NAME).sheet1
        tz = pytz.timezone('Africa/Cairo')
        now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([now, user_type, user_name, details])
    except: pass

def log_activity(user_name, input_type, question_text):
    client = get_gspread_client()
    if not client: return
    try:
        try: sheet = client.open(CONTROL_SHEET_NAME).worksheet("Activity")
        except: return 
        tz = pytz.timezone('Africa/Cairo')
        now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        final_text = question_text
        if isinstance(question_text, list): final_text = f"[Image] {question_text[0]}"
        sheet.append_row([now, user_name, input_type, str(final_text)[:500]])
    except: pass

def update_xp(user_name, points_to_add):
    client = get_gspread_client()
    if not client: return 0
    try:
        try: sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
        except: return 0
        cell = sheet.find(user_name)
        current_xp = 0
        if cell:
            val = sheet.cell(cell.row, 2).value
            current_xp = int(val) if val else 0
            new_xp = current_xp + points_to_add
            sheet.update_cell(cell.row, 2, new_xp)
            return new_xp
        else:
            sheet.append_row([user_name, points_to_add])
            return points_to_add
    except: return 0

def get_current_xp(user_name):
    client = get_gspread_client()
    if not client: return 0
    try:
        sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
        cell = sheet.find(user_name)
        if cell:
            val = sheet.cell(cell.row, 2).value
            return int(val) if val else 0
        return 0
    except: return 0

def get_leaderboard():
    client = get_gspread_client()
    if not client: return []
    try:
        sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
        data = sheet.get_all_records()
        if not data: return []
        df = pd.DataFrame(data)
        df['XP'] = pd.to_numeric(df['XP'], errors='coerce').fillna(0)
        top_5 = df.sort_values(by='XP', ascending=False).head(5)
        return top_5.to_dict('records')
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

# Streaming Effect
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

def clean_text_for_audio(text):
    text = re.sub(r'\\documentclass\{.*?\}', '', text) 
    text = re.sub(r'\\usepackage\{.*?\}', '', text)
    text = re.sub(r'\\begin\{.*?\}', '', text) 
    text = re.sub(r'\\end\{.*?\}', '', text)   
    text = re.sub(r'\\item', '', text)         
    text = re.sub(r'\\textbf\{(.*?)\}', r'\1', text) 
    text = re.sub(r'\\textit\{(.*?)\}', r'\1', text) 
    text = re.sub(r'\\underline\{(.*?)\}', r'\1', text)
    text = text.replace('*', '').replace('#', '').replace('-', '').replace('_', ' ').replace('`', '')
    return text

async def generate_audio_stream(text, voice_code):
    clean_text = clean_text_for_audio(text)
    if isinstance(voice_code, tuple) or isinstance(voice_code, list):
        voice_code = voice_code[0]
    communicate = edge_tts.Communicate(clean_text, voice_code, rate="-5%")
    mp3_fp = BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio": mp3_fp.write(chunk["data"])
    return mp3_fp

def speech_to_text(audio_bytes, lang_code):
    r = sr.Recognizer()
    try:
        audio_file = sr.AudioFile(BytesIO(audio_bytes))
        with audio_file as source:
            r.adjust_for_ambient_noise(source, duration=0.5)
            audio_data = r.record(source)
            return r.recognize_google(audio_data, language=lang_code)
    except: return None

@st.cache_resource
def load_ai_model():
    try:
        api_key = None
        if "GOOGLE_API_KEYS" in st.secrets:
            keys = st.secrets["GOOGLE_API_KEYS"]
            if isinstance(keys, list) and len(keys) > 0:
                api_key = random.choice(keys)
        elif "GOOGLE_API_KEY" in st.secrets:
            api_key = st.secrets["GOOGLE_API_KEY"]
            
        if api_key:
            genai.configure(api_key=api_key)
            all_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            active_model_name = next((m for m in all_models if 'flash' in m), None)
            if not active_model_name:
                active_model_name = next((m for m in all_models if 'pro' in m), all_models[0])
            return genai.GenerativeModel(active_model_name)
    except: pass
    return None

try:
    model = load_ai_model()
    if not model: st.stop()
except: st.stop()

def safe_generate_content(model, prompt):
    if not model: raise Exception("AI Not Connected")
    max_retries = 3
    for attempt in range(max_retries):
        try: return model.generate_content(prompt)
        except Exception as e:
            if "429" in str(e) or "Quota" in str(e):
                time.sleep(1)
                st.cache_resource.clear()
                continue
            else: raise e
    raise Exception("Busy")

# 🔥 دالة المعالجة المركزية 🔥
def process_ai_response(user_text, input_type="text"):
    log_activity(st.session_state.user_name, input_type, user_text)
    st.toast("🧠 Mr. Elsayed's AI is thinking...", icon="🤔")
    
    try:
        model = load_ai_model()
        if not model:
            st.error("AI Service Unavailable")
            return

        role_lang = "Arabic" if st.session_state.language == "العربية" else "English"
        ref = st.session_state.get("ref_text", "")
        student_name = st.session_state.user_name
        student_level = st.session_state.get("student_grade", "General")
        curriculum = st.session_state.get("study_lang", "Arabic")
        
        map_instruction = ""
        check_map = ["مخطط", "خريطة", "رسم", "map", "diagram", "chart", 
