import streamlit as st

# ==========================================
# 1. إعدادات الصفحة والتصميم المحسن
# ==========================================
st.set_page_config(
    page_title="AI Science Tutor Pro", 
    page_icon="🧬", 
    layout="wide",
    initial_sidebar_state="expanded"
)

import time
import asyncio
import re
import random
import threading
from io import BytesIO, StringIO
from datetime import datetime, timedelta
import pytz
import json
import uuid
import base64

# المكتبات الخارجية
try:
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
    import plotly.express as px
    import plotly.graph_objects as go
except ImportError as e:
    st.error(f"خطأ في تحميل المكتبات: {e}")
    st.stop()

# ==========================================
# 🎛️ الثوابت والإعدادات
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
    "gold": "#FFD700",
    "gradient": "linear-gradient(135deg, #1A2980, #26D0CE, #FF3CAC)",
    "glass": "rgba(255, 255, 255, 0.1)"
}

DAILY_FACTS = [
    "هل تعلم؟ المخ يولد كهرباء تكفي لمصباح! 💡",
    "هل تعلم؟ العظام أقوى من الخرسانة بـ 4 مرات! 🦴",
    "هل تعلم؟ الأخطبوط لديه 3 قلوب! 🐙",
    "هل تعلم؟ العسل لا يفسد أبداً! 🍯",
    "هل تعلم؟ الضوء يستغرق 8 دقائق للوصول من الشمس إلى الأرض! ☀️",
    "هل تعلم؟ الزرافة تنام فقط 30 دقيقة يومياً! 🦒",
    "هل تعلم؟ الفضاء لا يحتوي على صوت! 🌌",
    "هل تعلم؟ الماء المغلي يتجمد أسرع من الماء البارد! ❄️"
]

SUBJECTS = ["فيزياء", "كيمياء", "أحياء", "علوم عامة", "فلك", "جيولوجيا"]

# ==========================================
# 🎨 تحسينات الواجهة
# ==========================================
def set_custom_theme():
    # تطبيق CSS مخصص للواجهة الجديدة
    st.markdown(f"""
    <style>
        /* الخلفية والألوان الأساسية */
        .stApp {{
            background: {COLORS["deep_blue"]};
            background: linear-gradient(135deg, {COLORS["deep_blue"]}, #0D1B4E);
            color: white;
        }}
        
        /* تنسيق العناوين */
        h1, h2, h3 {{
            font-family: 'Tajawal', sans-serif;
            background: linear-gradient(90deg, {COLORS["royal_purple"]}, {COLORS["neon_pink"]});
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: bold;
        }}
        
        /* تنسيق البطاقات */
        .card {{
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 1.5rem;
            border: 1px solid rgba(255, 255, 255, 0.1);
            margin-bottom: 1rem;
            transition: all 0.3s ease;
        }}
        .card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 10px 20px rgba(0, 0, 0, 0.2);
        }}
        
        /* تنسيق الأزرار */
        .stButton>button {{
            background: linear-gradient(90deg, {COLORS["royal_purple"]}, {COLORS["neon_pink"]});
            color: white;
            border: none;
            border-radius: 25px;
            padding: 0.5rem 2rem;
            font-weight: bold;
            transition: all 0.3s ease;
        }}
        .stButton>button:hover {{
            transform: scale(1.05);
            box-shadow: 0 0 15px {COLORS["neon_pink"]};
        }}
        
        /* تنسيق الشريط الجانبي */
        [data-testid="stSidebar"] {{
            background: rgba(10, 20, 50, 0.7);
            backdrop-filter: blur(10px);
        }}
        
        /* تنسيق مربعات الإدخال */
        .stTextInput>div>div>input {{
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 10px;
            color: white;
        }}
        
        /* تنسيق القوائم المنسدلة */
        .stSelectbox>div>div {{
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 10px;
            color: white;
        }}
        
        /* تأثيرات متحركة */
        @keyframes glow {{
            0% {{ box-shadow: 0 0 5px {COLORS["royal_purple"]}; }}
            50% {{ box-shadow: 0 0 20px {COLORS["neon_pink"]}; }}
            100% {{ box-shadow: 0 0 5px {COLORS["royal_purple"]}; }}
        }}
        .glow-effect {{
            animation: glow 3s infinite;
        }}
        
        /* تنسيق علامات التبويب */
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
        
        /* تنسيق رسائل الدردشة */
        [data-testid="stChatMessage"] {{
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(5px);
            border-radius: 15px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}
        
        /* تنسيق الرسوم البيانية */
        .js-plotly-plot {{
            background: rgba(255, 255, 255, 0.03);
            border-radius: 15px;
            padding: 10px;
        }}
    </style>
    
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;700&display=swap" rel="stylesheet">
    """, unsafe_allow_html=True)

# ==========================================
# 🛠️ الخدمات الخلفية المحسنة مع معالجة الأخطاء
# ==========================================

# --- جداول جوجل ---
@st.cache_resource(ttl=3600)
def get_gspread_client():
    if "gcp_service_account" not in st.secrets:
        return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        scope = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds)
    except Exception as e:
        print(f"Error connecting to Google Sheets: {e}")
        return None

def get_sheet_data(max_retries=3):
    for attempt in range(max_retries):
        try:
            client = get_gspread_client()
            if not client: return None
            sheet = client.open(CONTROL_SHEET_NAME)
            val = sheet.sheet1.acell('B1').value
            return str(val).strip() if val else None
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"Failed to get sheet data after {max_retries} attempts: {e}")
                return None
            time.sleep(1)  # Wait before retrying

# --- التسجيل (Logs) مع تحسينات وإدارة الأخطاء ---
def _bg_task(task_type, data):
    if "gcp_service_account" not in st.secrets:
        return

    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        client = gspread.authorize(service_account.Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets']))
        wb = client.open(CONTROL_SHEET_NAME)
        
        tz = pytz.timezone('Africa/Cairo')
        now_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

        if task_type == "login":
            try: 
                sheet = wb.worksheet("Logs")
            except: 
                try:
                    sheet = wb.add_worksheet("Logs", 1000, 5)
                    sheet.append_row(["Timestamp", "Type", "Name", "Details", "Session_ID"])
                except:
                    sheet = wb.sheet1
            
            session_id = data.get('session_id', str(uuid.uuid4())[:8])
            sheet.append_row([now_str, data['type'], data['name'], data['details'], session_id])

        elif task_type == "activity":
            try: 
                sheet = wb.worksheet("Activity")
            except: 
                try:
                    sheet = wb.add_worksheet("Activity", 1000, 5)
                    sheet.append_row(["Timestamp", "Name", "Input_Type", "Text", "Session_ID"])
                except:
                    return
            
            clean_text = str(data['text'])[:1000]
            session_id = data.get('session_id', str(uuid.uuid4())[:8])
            sheet.append_row([now_str, data['name'], data['input_type'], clean_text, session_id])

        elif task_type == "xp":
            try: 
                sheet = wb.worksheet("Gamification")
            except: 
                try:
                    sheet = wb.add_worksheet("Gamification", 1000, 5)
                    sheet.append_row(["Student_Name", "XP", "Level", "Badges", "Last_Update"])
                except:
                    return
            
            cell = sheet.find(data['name'])
            if cell:
                row_data = sheet.row_values(cell.row)
                current_xp = int(row_data[1]) if len(row_data) > 1 and row_data[1] else 0
                current_level = int(row_data[2]) if len(row_data) > 2 and row_data[2] else 1
                badges = row_data[3] if len(row_data) > 3 and row_data[3] else ""
                
                new_xp = current_xp + data['points']
                new_level = max(1, int(new_xp / 100) + 1)
                
                # إضافة شارة جديدة إذا تم الوصول لمستوى جديد
                if new_level > current_level:
                    badges_list = badges.split(",") if badges else []
                    badges_list.append(f"Level {new_level}")
                    badges = ",".join(badges_list)
                
                sheet.update_cell(cell.row, 2, new_xp)
                sheet.update_cell(cell.row, 3, new_level)
                sheet.update_cell(cell.row, 4, badges)
                sheet.update_cell(cell.row, 5, now_str)
            else:
                sheet.append_row([data['name'], data['points'], 1, "", now_str])
    except Exception as e:
        print(f"Error in background task: {e}")

def log_login(user_name, user_type, details, session_id=None):
    if not session_id:
        session_id = str(uuid.uuid4())[:8]
        st.session_state.session_id = session_id
    
    threading.Thread(target=_bg_task, args=("login", {
        'name': user_name, 
        'type': user_type, 
        'details': details,
        'session_id': session_id
    })).start()
    
    return session_id

def log_activity(user_name, input_type, text):
    session_id = st.session_state.get('session_id', str(uuid.uuid4())[:8])
    threading.Thread(target=_bg_task, args=("activity", {
        'name': user_name, 
        'input_type': input_type, 
        'text': text,
        'session_id': session_id
    })).start()

def update_xp(user_name, points):
    if 'current_xp' in st.session_state:
        st.session_state.current_xp += points
    threading.Thread(target=_bg_task, args=("xp", {'name': user_name, 'points': points})).start()

def get_user_data(user_name, max_retries=3):
    for attempt in range(max_retries):
        try:
