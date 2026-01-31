import streamlit as st
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import tempfile
import os
import time
import random
import asyncio
import re
from io import BytesIO
from streamlit_mic_recorder import mic_recorder
import edge_tts
import speech_recognition as sr

# =========================
# 1. إعدادات الصفحة
# =========================
st.set_page_config(page_title="المعلم الذكي | منهاج مصر", layout="wide", page_icon="🇪🇬")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
html, body, .stApp { font-family: 'Cairo', sans-serif !important; direction: rtl; text-align: right; }
.header-box { background: linear-gradient(135deg, #1cb5e0 0%, #000046 100%); padding: 2rem; border-radius: 20px; color: white; text-align: center; margin-bottom: 20px; }
.stButton>button { background: #000046; color: white; border-radius: 10px; height: 50px; width: 100%; border: none; font-size: 18px; }
</style>
""", unsafe_allow_html=True)

# الأسرار
FOLDER_ID = "1ub4ML8q4YCM_VZR991XXQ6hBBas2X6rS"
GOOGLE_API_KEYS = st.secrets.get("GOOGLE_API_KEYS", [])
if isinstance(GOOGLE_API_KEYS, str): GOOGLE_API_KEYS = [k.strip() for k in GOOGLE_API_KEYS.split(",")]

# =========================
# 2. الخرائط ومنطق التسمية
# =========================
STAGES = ["الابتدائية", "الإعدادية", "الثانوية"]
GRADES = {
    "الابتدائية": ["الرابع", "الخامس", "السادس"],
    "الإعدادية": ["الأول", "الثاني", "الثالث"],
    "الثانوية": ["الأول", "الثاني", "الثالث"],
}
TERMS = ["الترم الأول", "الترم الثاني"]

def subjects_for(stage, grade):
    if stage in ["الابتدائية", "الإعدادية"]:
        return ["علوم"]
    elif stage == "الثانوية":
        if grade == "الأول": return ["علوم متكاملة"]
        return ["كيمياء", "فيزياء", "أحياء"]
    return ["علوم"]

def generate_file_name_search(stage, grade, subject, lang_type):
    # 1. كود الصف
    grade_map = {"الرابع": "4", "الخامس": "5", "السادس": "6", "الأول": "1", "الثاني": "2", "الثالث": "3"}
    g_num = grade_map.get(grade, "1")
    
    # 2. كود اللغة
    lang_code = "En" if "English" in lang_type else "Ar"

    # 3. تركيب الاسم
    if stage == "الابتدائية":
        return f"Grade{g_num}_{lang_code}"
    elif stage == "الإعدادية":
        return f"Prep{g_num}_{lang_code}"
    elif stage == "الثانوية":
        if grade == "الأول":
            return f"Sec1_Integrated_{lang_code}"
        else:
            sub_map = {"كيمياء": "Chem", "فيزياء": "Physics", "أحياء": "Biology"}
            sub_code = sub_map.get(subject, "Chem")
            return f"Sec{g_num}_{sub_code}_{lang_code}"
    return ""

# =========================
# 3. خدمات جوجل والبحث الذكي
# =========================
def configure_genai(key_index=0):
    if not GOOGLE_API_KEYS: return False
    # اختيار المفتاح بناءً على المحاولة الحالية
    idx = key_index % len(GOOGLE_API_KEYS)
    genai.configure(api_key=GOOGLE_API_KEYS[idx])
    return True

@st.cache_resource
def get_drive_service():
    if "gcp_service_account" not in st.secrets: return None
    try:
        creds = dict(st.secrets["gcp_service_account"])
        creds["private_key"] = creds["private_key"].replace("\\n", "\n")
        return build("drive", "v3", credentials=service_account.Credentials.from_service_account_info(creds))
    except: return None

def find_and_download_book(search_name):
    srv = get_drive_service()
    if not srv: return None, "خطأ Drive"
    
    q = f"'{FOLDER_ID}' in parents and name contains '{search_name}' and trashed=false"
    try:
        results = srv.files().list(q=q, fields="files(id, name)").execute()
        files = results.get('files', [])
        
        if 
