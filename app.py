import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import google.generativeai as genai
import gspread
from PIL import Image
import random
import speech_recognition as sr
from streamlit_mic_recorder import mic_recorder
import asyncio
import edge_tts
import tempfile
import os
import re
import io
import PyPDF2

# ==========================================
# 1. إعدادات الصفحة
# ==========================================
st.set_page_config(
    page_title="المعلم العلمي | السيد البدوي",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# 2. تصميم احترافي ونظيف (Clean & Clear UI)
# ==========================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
    
    /* 1. الخط والاتجاه */
    html, body, [class*="css"] {
        font-family: 'Cairo', sans-serif !important;
        direction: rtl;
        text-align: right;
    }

    /* 2. الخلفية العامة */
    .stApp {
        background: linear-gradient(180deg, #f0f4f8 0%, #d9e2ec 100%);
    }

    /* 3. إصلاح جذري للقوائم المنسدلة (Selectbox) - إزالة المربعات الداخلية */
    /* الإطار الخارجي فقط */
    div[data-baseweb="select"] > div {
        background-color: #ffffff !important;
        border: 2px solid #004e92 !important;
        border-radius: 8px !important;
        color: #000000 !important;
    }
    
    /* النص داخل القائمة (بدون خلفيات) */
    div[data-baseweb="select"] span {
        color: #000000 !important;
    }
    
    /* القائمة المنبثقة (عند الفتح) */
    ul[data-baseweb="menu"] {
        background-color: #ffffff !important;
    }
    li[data-baseweb="option"] {
        color: #000000 !important;
        font-weight: bold !important;
    }
    li[data-baseweb="option"]:hover {
        background-color: #e3f2fd !important;
    }

    /* 4. حقول الكتابة (Text Input) */
    .stTextInput input {
        background-color: #ffffff !important;
        color: #000000 !important;
        border: 2px solid #004e92 !important;
        border-radius: 8px !important;
    }

    /* 5. العناوين والنصوص */
    h1, h2, h3, h4, h5, p, label {
        color: #000000 !important;
    }

    /* 6. الأزرار */
    .stButton>button {
        background: linear-gradient(90deg, #004e92 0%, #000428 100%) !important;
        color: #ffffff !important;
        border: none;
        border-radius: 10px;
        height: 55px;
        width: 100%;
        font-size: 20px !important;
        font-weight: bold !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.2);
    }
    .stButton>button:hover {
        transform: scale(1.02);
    }

    /* 7. صندوق العنوان العلوي */
    .header-box {
        background: linear-gradient(90deg, #000428 0%, #004e92 100%);
        padding: 2rem;
        border-radius: 15px;
        text-align: center;
        margin-bottom: 2rem;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
    }
    .header-box h1, .header-box h3 { color: #ffffff !important; }

    /* 8. فقاعات الشات */
    .stChatMessage {
        background-color: #ffffff !important;
        border: 1px solid #d1d1d1 !important;
        border-radius: 12px !important;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05) !important;
    }
</style>
""", unsafe_allow_html=True)

# العنوان
st.markdown("""
<div class="header-box">
    <h1>الأستاذ / السيد البدوي</h1>
    <h3>المنصة التعليمية الذكية (ابتدائي - إعدادي - ثانوي)</h3>
</div>
""", unsafe_allow_html=True)

# ==========================================
# 3. إدارة الجلسة والبيانات
# ==========================================
if 'user_data' not in st.session_state:
    st.session_state.user_data = {"logged_in": False, "role": None, "name": "", "grade": "", "stage": "", "lang": ""}
if 'messages' not in 
