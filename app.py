import streamlit as st
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

# ==========================================
# 🎛️ إعدادات التحكم
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

st.set_page_config(page_title="AI Science Tutor Pro", page_icon="🧬", layout="wide")

# ==========================================
# 🛠️ الخدمات (شيت، درايف، صوت)
# ==========================================

# كاش للخدمات لمنع إعادة التحميل
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
    if client:
        try:
            sheet = client.open(CONTROL_SHEET_NAME)
            daily_pass = str(sheet.sheet1.acell('B1').value).strip()
            return daily_pass, sheet
        except: return None, None
    return None, None

def update_daily_password(new_pass):
    client = get_gspread_client()
    if client:
        try:
            client.open(CONTROL_SHEET_NAME).sheet1.update_acell('B1', new_pass)
            return True
        except: return False
    return False

# --- دالة تسجيل الدخول (تم إصلاح الخطأ هنا) ---
def log_login_to_sheet(user_name, user_type, details=""):
    client = get_gspread_client()
    if client:
        try:
            # محاولة فتح صفحة Logs، وإذا فشلت نفتح الصفحة الرئيسية
            try:
                sheet = client.open(CONTROL_SHEET_NAME).worksheet("Logs")
            except:
                sheet = client.open(CONTROL_SHEET_NAME).sheet1
            
            tz = pytz.timezone('Africa/Cairo')
            now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
            sheet.append_row([now, user_type, user_name, details])
        except:
            pass

# --- دالة تسجيل النشاط (تم إصلاح التنسيق) ---
def log_activity(user_name, input_type, question_text):
    client = get_gspread_client()
    if client:
        try:
            try:
                sheet = client.open(CONTROL_SHEET_NAME).worksheet("Activity")
            except:
                return # الخروج إذا لم توجد الصفحة
            
            tz = pytz.timezone('Africa/Cairo')
            now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
            
            final_text = question_text
            if isinstance(question_text, list): 
                final_text = f"[Image] {question_text[0]}"
            
            sheet.append_row([now, user_name, input_type, str(final_text)[:500]])
        except:
            pass

def update_xp(user_name, points_to_add):
    client = get_gspread_client()
    if client:
        try:
            try: 
                sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
            except: return 0
            
            cell = sheet.find(user_name)
            current_xp = 0
            if cell:
                current_xp = int(sheet.cell(cell.row, 2).value)
                new_xp = current_xp + points_to_add
                sheet.update_cell(cell.row, 2, new_xp)
                return new_xp
            else:
                sheet.append_row([user_name, points_to_add])
                return points_to_add
        except: return 0
    return 0

def get_current_xp(user_name):
    client = get_gspread_client()
    if client:
        try:
            sheet = client.open(CONTROL_SHEET_NAME).worksheet("Gamification")
            cell = sheet.find(user_name)
            if cell: return int(sheet.cell(cell.row, 2).value)
        except: return 0
    return 0

def get_leaderboard():
    client = get_gspread_client()
    if client:
        try:
            try: sheet = 
