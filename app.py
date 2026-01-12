"""
AI Science Tutor Pro - Instrumented Final Version
- Adds detailed debugging in process_ai_response and sidebar
- Keeps previous features: TTS, STT, Drive activation, MCQ generation with JSON, local fallbacks
- Displays a fancy user name after login (no changes to auth logic)
"""
import streamlit as st
import time
import asyncio
import re
import random
import threading
from io import BytesIO
from datetime import datetime
import pytz
import os
import json
import base64
import logging
import subprocess
import shutil
from typing import Optional, Dict, Any, List, Tuple
from PIL import Image
import PyPDF2

# Optional provider & tools imports
try:
    import google.generativeai as genai
except Exception:
    genai = None

try:
    import openai
except Exception:
    openai = None

try:
    import edge_tts
except Exception:
    edge_tts = None

try:
    import speech_recognition as sr
except Exception:
    sr = None

try:
    from streamlit_mic_recorder import mic_recorder
except Exception:
    mic_recorder = None

# Google API optional dependencies
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    import gspread
    import pandas as pd
except Exception:
    service_account = None
    build = None
    MediaIoBaseDownload = None
    gspread = None
    pd = None

# ==========================================
# Config & secrets
# ==========================================
st.set_page_config(page_title="AI Science Tutor Pro", page_icon="🧬", layout="wide")

TEACHER_MASTER_KEY = st.secrets.get("TEACHER_MASTER_KEY", "ADMIN_2024_PLACEHOLDER")
DRIVE_FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "")
GOOGLE_API_KEYS = st.secrets.get("GOOGLE_API_KEYS", [])
OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY", "")
GCP_SA = st.secrets.get("gcp_service_account", None)

SESSION_DURATION_MINUTES = int(st.secrets.get("SESSION_DURATION_MINUTES", 60))
RATE_LIMIT_MIN_SECONDS = int(st.secrets.get("RATE_LIMIT_MIN_SECONDS", 1))

DAILY_FACTS = st.secrets.get("DAILY_FACTS", [
    "هل تعلم؟ المخ يولد كهرباء تكفي لمصباح! 💡",
    "هل تعلم؟ العظام أقوى من الخرسانة بـ 4 مرات! 🦴",
    "هل تعلم؟ الأخطبوط لديه 3 قلوب! 🐙",
    "هل تعلم؟ العسل لا يفسد أبداً! 🍯",
])

LOCAL_LOG_FILE = "logs_local.json"
CHAT_HISTORY_DIR = "chat_histories"
os.makedirs(CHAT_HISTORY_DIR, exist_ok=True)

# ==========================================
# Logging
# ==========================================
logger = logging.getLogger("ai_science_tutor")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# ==========================================
# Helpers: rerun, time, logs, chat history
# ==========================================
def safe_rerun():
    try:
        if hasattr(st, "experimental_rerun") and callable(st.experimental_rerun):
            st.experimental_rerun()
            return
        if hasattr(st, "rerun") and callable(st.rerun):
            st.rerun()
            return
    except Exception:
        logger.exception("safe_rerun failed")
    try:
        st.stop()
    except Exception:
        logger.exception("safe_rerun.stop failed")

def now_str():
    return datetime.now(pytz.timezone("Africa/Cairo")).strftime("%Y-%m-%d %H:%M:%S")

def safe_write_local_log(entry: Dict[str, Any]):
    try:
        with open(LOCAL_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        logger.exception("Failed to write local log")

def append_chat_history_local(user_name: str, entry: Dict[str, Any]):
    path = os.path.join(CHAT_HISTORY_DIR, f"{user_name}.jsonl")
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        logger.exception("Failed to append chat history locally")

# ==========================================
# Google Sheets & Drive helpers (optional)
# ==========================================
if gspread and GCP_SA:
    @st.cache_resource
    def get_gspread_client():
        try:
            creds_dict = dict(GCP_SA)
            scope = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
            creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scope)
            return gspread.authorize(creds)
        except Exception:
            logger.exception("Failed to authorize gspread")
            return None
else:
    def get_gspread_client():
        return None

def safe_get_control_sheet_value():
    client = get_gspread_client()
    if not client:
        return None
    try:
        wb = client.open("App_Control")
        return wb.sheet1.acell('B1').value
    except Exception:
        logger.exception("safe_get_control_sheet_value failed")
        return None

def safe_append_activity_log(entry: Dict[str, Any]):
    client = get_gspread_client()
    if client:
        try:
            wb = client.open("App_Control")
            try:
                sh = wb.worksheet("Activity")
                sh.append_row([entry.get("time"), entry.get("user"), entry.get("input_type"), entry.get("text")[:1000]])
                return
            except Exception:
                logger.exception("Failed to append to Activity worksheet")
        except Exception:
            logger.exception("Failed to open App_Control workbook")
    safe_write_local_log({"type":"activity", **entry})

def safe_update_xp_sheet(user_name: str, points: int):
    client = get_gspread_client()
    if client:
        try:
            wb = client.open("App_Control")
            try:
                sh = wb.worksheet("Gamification")
            except Exception:
                sh = wb.sheet1
            cell = sh.find(user_name)
            if cell:
                cur = sh.cell(cell.row, 2).value
                cur = int(cur) if cur else 0
                sh.update_cell(cell.row, 2, cur + points)
            else:
                sh.append_row([user_name, points])
            return
        except Exception:
            logger.exception("Failed to update XP sheet")
    safe_write_local_log({"type":"xp","time":now_str(),"user":user_name,"points":points})

# ==========================================
# Model abstraction and wrappers
# ==========================================
_last_provider_errors: List[str] = []

def init_google_genai_if_available():
    if genai and GOOGLE_API_KEYS:
        for k in GOOGLE_API_KEYS:
            try:
                genai.configure(api_key=k)
                logger.info("Configured google generativeai")
                return True
            except Exception:
                continue
    return False

_GOOGLE_INITIALIZED = init_google_genai_if_available()

def call_model(prompt: str, *, model_preferences: Optional[List[str]] = None) -> str:
    global _last_provider_errors
    _last_provider_errors = []
    if not prompt:
        return ""
    # Google
    if genai and _GOOGLE_INITIALIZED:
        try:
            if hasattr(genai, "TextGenerationModel"):
                for candidate in (model_preferences or ["gemini-2.5-flash","gemini-flash-latest"]):
                    try:
                        model = genai.TextGenerationModel.from_pretrained(candidate)
                        resp = model.generate(prompt=prompt, max_output_tokens=512)
                        if hasattr(resp, "candidates"):
                            return resp.candidates[0].content
                        if hasattr(resp, "outputs"):
                            return resp.outputs[0].content
                    except Exception as e:
                        _last_provider_errors.append(f"Google({candidate}): {e}")
            if hasattr(genai, "generate_text"):
                try:
                    r = genai.generate_text(model="gemini-2.5-flash", prompt=prompt)
                    if isinstance(r, dict) and "candidates" in r:
                        return r["candidates"][0].get("content","")
                    return str(r)
                except Exception as e:
                    _last_provider_errors.append(f"Google(generate_text): {e}")
        except Exception as e:
            _last_provider_errors.append(f"Google(general): {e}")
    # OpenAI
    if openai and OPENAI_API_KEY:
        try:
            openai.api_key = OPENAI_API_KEY
            try:
                resp = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=[{"role":"user","content":prompt}], max_tokens=512)
                return resp.choices[0].message.content
            except Exception as e:
                _last_provider_errors.append(f"OpenAI(ChatCompletion): {e}")
        except Exception as e:
            _last_provider_errors.append(f"OpenAI(general): {e}")
    if not _last_provider_errors:
        _last_provider_errors.append("No providers configured.")
    raise RuntimeError("No AI provider available. Attempts:\n" + "\n".join(_last_provider_errors))

def safe_call_model(prompt: str) -> Tuple[bool,str,Optional[str]]:
    try:
        t = call_model(prompt)
        return True, t, None
    except Exception as e:
        logger.exception("call_model failed")
        return False, "", str(e)

def safe_call_model_with_retries(prompt: str, max_retries: int = 3, base_delay: float = 2.0) -> Tuple[bool,str,Optional[str]]:
    attempt = 0
    last_err = None
    while attempt < max_retries:
        attempt += 1
        ok, text, err = safe_call_model(prompt)
        if ok:
            return True, text, None
        last_err = err or "unknown"
        lowered = last_err.lower()
        if any(k in lowered for k in ["quota","rate limit","429","retry"]):
            m = re.search(r"retry in\s*([0-9\.]+)s", last_err, flags=re.IGNORECASE)
            delay = (float(m.group(1))+0.5) if m else base_delay * (2**(attempt-1))
            logger.warning("Retry %d/%d after %.1fs (provider error)", attempt, max_retries, delay)
            time.sleep(delay)
            continue
        break
    return False, "", last_err

# ==========================================
# Audio conversion, STT, TTS helpers
# ==========================================
def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None

def convert_audio_to_wav_bytes(raw_bytes: bytes, input_format: Optional[str] = None) -> Optional[bytes]:
    try:
        from pydub import AudioSegment
        bio = BytesIO(raw_bytes)
        seg = AudioSegment.from_file(bio, format=input_format) if input_format else AudioSegment.from_file(bio)
        seg = seg.set_frame_rate(16000).set_channels(1)
        out = BytesIO(); seg.export(out, format="wav"); return out.getvalue()
    except Exception:
        pass
    if _has_ffmpeg():
        try:
            p = subprocess.Popen(["ffmpeg","-y","-hide_banner","-loglevel","error","-i","pipe:0","-ar","16000","-ac","1","-f","wav","pipe:1"],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out, err = p.communicate(raw_bytes, timeout=30)
            if p.returncode == 0:
                return out
            logger.error("ffmpeg conversion failed: %s", err.decode(errors="ignore"))
        except Exception:
            logger.exception("ffmpeg conversion exception")
    logger.debug("convert_audio_to_wav_bytes: no conversion available")
    return None

def speech_to_text_bytes(audio_bytes: bytes, lang_code: str = "ar-EG") -> Optional[str]:
    if not sr:
        logger.warning("speech_recognition not installed")
        return None
    try:
        if isinstance(audio_bytes, str):
            if audio_bytes.startswith("data:"):
                audio_bytes = audio_bytes.split(",",1)[1]
            audio_bytes = base64.b64decode(audio_bytes)
    except Exception:
        logger.exception("decode base64 audio failed")
    wav_bytes = None
    try:
        if isinstance(audio_bytes, (bytes,bytearray)) and audio_bytes[:4] == b'RIFF':
            wav_bytes = bytes(audio_bytes)
    except Exception:
        pass
    if not wav_bytes:
        wav_bytes = convert_audio_to_wav_bytes(audio_bytes, input_format=None)
    if not wav_bytes:
        logger.error("Could not convert audio to WAV")
        return None
    r = sr.Recognizer()
    try:
        with sr.AudioFile(BytesIO(wav_bytes)) as source:
            r.adjust_for_ambient_noise(source, duration=0.5)
            audio_data = r.record(source)
            return r.recognize_google(audio_data, language=lang_code)
    except sr.UnknownValueError:
        logger.info("Speech not understood")
        return None
    except sr.RequestError as e:
        logger.exception("Speech recognition request error: %s", e)
        return None
    except Exception:
        logger.exception("Speech to text failed")
        return None

async def _generate_audio_stream_async(text: str, voice: str = "en-US-AndrewNeural") -> bytes:
    if not edge_tts:
        raise RuntimeError("edge-tts not installed")
    clean = re.sub(r'[*#_`\[\]()><=]', ' ', text)
    comm = edge_tts.Communicate(clean, voice, rate="-5%")
    mp3 = BytesIO()
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            mp3.write(chunk["data"])
    return mp3.getvalue()

def generate_audio_sync(text: str, voice: str = "en-US-AndrewNeural") -> Optional[bytes]:
    try:
        return asyncio.run(_generate_audio_stream_async(text[:1500], voice))
    except Exception:
        logger.exception("TTS generation failed")
        return None

def play_tts_bytes(audio_bytes: bytes):
    if not audio_bytes:
        return
    try:
        st.audio(BytesIO(audio_bytes), format="audio/mp3", start_time=0)
    except Exception:
        try:
            st.audio(BytesIO(audio_bytes), start_time=0)
        except Exception:
            logger.exception("Failed to play TTS audio")

# ==========================================
# Utility: streaming text display
# ==========================================
def stream_text_to_placeholder(text: str, placeholder, delay: float = 0.02):
    buf = ""
    counter = 0
    for ch in text:
        buf += ch
        counter += 1
        if counter % 20 == 0:
            placeholder.markdown(buf)
            time.sleep(delay)
    placeholder.markdown(buf)

# ==========================================
# Local fallback util: search textbook for snippets
# ==========================================
def local_search_answer(question: str, ref_text: str) -> Optional[str]:
    if not ref_text:
        return None
    q_words = [w.lower() for w in re.findall(r"\w{3,}", question)]
    if not q_words:
        return None
    sents = re.split(r'(?<=[.!?])\s+', ref_text)
    matches = []
    for sent in sents:
        lw = sent.lower()
        score = sum(1 for w in q_words if w in lw)
        if score > 0:
            matches.append((score, sent.strip()))
    matches.sort(reverse=True)
    if not matches:
        return None
    out = []
    seen = set()
    for sc, s in matches[:3]:
        if s not in seen:
            out.append(s); seen.add(s)
    return "\n\n".join(out) if out else None

# ==========================================
# Small helpers: XP/log wrappers
# ==========================================
def log_login(user_name: str, user_type: str, details: str):
    entry = {"time": now_str(), "type":"login", "user": user_name, "user_type": user_type, "details": details}
    threading.Thread(target=safe_write_local_log, args=(entry,)).start()
    threading.Thread(target=safe_append_activity_log, args=(entry,)).start()

def log_activity(user_name: str, input_type: str, text: str):
    entry = {"time": now_str(), "user": user_name, "input_type": input_type, "text": text[:1000]}
    threading.Thread(target=safe_append_activity_log, args=(entry,)).start()
    safe_write_local_log({"type":"activity", **entry})

def update_xp(user_name: str, points: int):
    if 'current_xp' in st.session_state:
        st.session_state.current_xp = st.session_state.get("current_xp", 0) + points
    threading.Thread(target=safe_update_xp_sheet, args=(user_name, points)).start()
    safe_write_local_log({"type":"xp","time":now_str(),"user":user_name,"points":points})

# ==========================================
# Session initialization
# ==========================================
if "auth_status" not in st.session_state:
    st.session_state.update({
        "auth_status": False,
        "user_type": "none",
        "chat_history": [],
        "student_grade": "General",
        "current_xp": 0,
        "last_audio_bytes": None,
        "language": "العربية",
        "ref_text": "",
        "last_request_time": None,
        "start_time": time.time(),
        "q_active": False,
        "q_answer": None,
        "q_explanation": None,
        "book_activated": None,
        "drive_files": None,
        "last_ai_ok": None,
        "last_ai_resp": None,
        "last_ai_err": None,
    })

def session_expired() -> bool:
    start = st.session_state.get("start_time", time.time())
    return (time.time() - start) > (SESSION_DURATION_MINUTES * 60)

# ==========================================
# UI helpers: header and fancy name
# ==========================================
def draw_header():
    st.markdown("""
        <div style='background:linear-gradient(135deg,#6a11cb,#2575fc);padding:1.2rem;border-radius:12px;text-align:center;color:white;margin-bottom:1rem;'>
            <h1 style='margin:0;'>🧬 AI Science Tutor Pro</h1>
            <div style='font-size:0.95rem;opacity:0.95;'>مُنظّم للتعلم، مدعوم بعدة مزوّدين ونظام تعزيز تكاملي</div>
        </div>
    """, unsafe_allow_html=True)

def render_fancy_name(name: str):
    if not name:
        return
    html = f"""
    <div style="display:flex;align-items:center;justify-content:center;gap:1rem;margin-top:0.6rem;margin-bottom:0.6rem;">
      <div style="background:linear-gradient(90deg,#ff8a00,#e52e71);-webkit-background-clip:text;background-clip:text;color:transparent;font-size:28px;font-weight:800;letter-spacing:1px;text-shadow:0 2px 12px rgba(229,46,113,0.18);transform:skewX(-6deg);padding:6px 12px;border-radius:8px;">
        {name}
      </div>
      <div style="background: rgba(255,255,255,0.06);border-radius:999px;padding:6px 10px;box-shadow: 0 4px 18px rgba(0,0,0,0.12);color:#fff;font-weight:600;font-size:14px;">
        المرشد الذكي
      </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# ==========================================
# Instrumented process_ai_response (replace earlier versions)
# ==========================================
def process_ai_response(user_text: Any, input_type: str = "text"):
    # rate-limit guard
    last = st.session_state.get("last_request_time")
    if last and time.time() - last < RATE_LIMIT_MIN_SECONDS:
        st.warning("رجاءً انتظر قليلاً قبل إرسال طلب آخر.")
        return
    st.session_state["last_request_time"] = time.time()

    user_name = st.session_state.get("user_name", "anonymous")
    log_activity(user_name, input_type, str(user_text)[:1000])

    lang = st.session_state.get("language", "العربية")
    grade = st.session_state.get("student_grade", "General")
    ref = st.session_state.get("ref_text", "")[:20000]
    lang_instr = "Arabic" if lang == "العربية" else "English"

    base_prompt = f"""You are a kind and interactive Science Tutor for grade {grade}.
Language: {lang_instr}.
Context: {ref}
Instructions: Answer clearly, provide step-by-step explanations, give an example, and if appropriate include a small diagram using Graphviz DOT inside ```dot ... ``` tags.
When generating MCQ from the textbook content, return strict JSON only with fields:
{{"question":"...","choices":["A) ...","B) ...","C) ...","D) ..."],"answer":"B","explanation":"..."}}
Do NOT include any extra text outside the JSON.
"""

    st.markdown("---")
    placeholder = st.empty()

    # reset debug session fields
    st.session_state["last_ai_ok"] = None
    st.session_state["last_ai_resp"] = None
    st.session_state["last_ai_err"] = None

    try:
        # prepare prompt based on input type
        if input_type == "image":
            caption = "Please explain the image and highlight key science concepts."
            if isinstance(user_text, list) and len(user_text) >= 2 and isinstance(user_text[1], Image.Image):
                img = user_text[1]
                buf = BytesIO()
                img.convert("RGB").resize((480,480)).save(buf, format="JPEG", quality=70)
                img_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
                prompt = base_prompt + f"\nImage (base64 JPEG): {img_b64[:500]}... (trimmed)\nTask: Explain what is visible and the science behind it."
            else:
                prompt = base_prompt + f"\nTask: {caption}"
        elif input_type == "mcq_generate":
            if not ref or len(ref) < 50:
                st.error("لم يتم تفعيل كتاب الطالب أو أن نص الكتاب قصير جداً. في الشريط الجانبي اختر كتابًا من Drive ثم اضغط تفعيل.")
                return
            prompt = base_prompt + f"\nContextFromBook:\n{ref}\n\nTask: Generate 1 MCQ strictly based on the textbook content above for grade {grade}. Return only valid JSON as described."
        elif input_type == "mcq_check":
            q = st.session_state.get("q_curr")
            correct = st.session_state.get("q_answer")
            if not q or not correct:
                st.error("لا يوجد سؤال نشط أو الإجابة غير مخزنة.")
                return
            user_ans = user_text.get("answer") if isinstance(user_text, dict) else str(user_text)
            user_ans = (user_ans or "").strip().upper()
            if not user_ans:
                st.warning("اكتب إجابتك أولاً (A/B/C/D).")
                return
            if user_ans == correct:
                st.success("إجابتك صحيحة 🎉")
                if st.session_state.get("q_explanation"):
                    st.write(st.session_state["q_explanation"])
                update_xp(user_name, 50)
            else:
                st.error("الإجابة غير صحيحة.")
                st.write(f"الإجابة الصحيحة: {correct}")
                if st.session_state.get("q_explanation"):
                    st.write(st.session_state["q_explanation"])
                update_xp(user_name, -5)
            st.session_state.q_active = False
            return
        else:
            prompt = base_prompt + f"\nStudent: {user_text}\nAnswer:"

        # Call the model with retries
        ok, resp, err = safe_call_model_with_retries(prompt)

        # store debug fields for sidebar
        st.session_state["last_ai_ok"] = ok
        st.session_state["last_ai_resp"] = resp
        st.session_state["last_ai_err"] = err

        # show per-call debug expander in page
        with st.expander("Debug: آخر محاولة للمزود (اضغط لعرض التفاصيل)"):
            st.write("ok:", ok)
            st.write("err:", err)
            st.write("provider attempts/errors:")
            st.write("\n".join(_last_provider_errors or []))
            st.write("response (preview):")
            st.code((resp or "")[:2000])

        if not ok:
            # try local fallback
            local_ans = local_search_answer(str(user_text), ref)
            if local_ans:
                placeholder.warning("المزود غير متاح — عرض مقتطف من كتاب الطالب كمحاولة بديلة:")
                placeholder.write(local_ans)
                append_chat_history_local(user_name, {"time": now_str(), "input_type": input_type, "input": str(user_text)[:1000], "response": local_ans})
                update_xp(user_name, 2)
                return
            placeholder.error("تعذّر الحصول على استجابة من مزود الذكاء الاصطناعي.")
            if err:
                placeholder.write("خطأ: " + str(err))
            else:
                placeholder.write("راجع Diagnostics في الشريط الجانبي لمزيد من التفاصيل.")
            return

        if not resp or not resp.strip():
            placeholder.warning("الذكاء الاصطناعي أعاد استجابة فارغة.")
            local_ans = local_search_answer(str(user_text), ref)
            if local_ans:
                placeholder.write(local_ans)
                append_chat_history_local(user_name, {"time": now_str(), "input_type": input_type, "input": str(user_text)[:1000], "response": local_ans})
                update_xp(user_name, 2)
            return

        # MCQ generation flow
        if input_type == "mcq_generate":
            try:
                m = re.search(r"\{[\s\S]*\}", resp)
                json_str = m.group(0) if m else resp
                qobj = json.loads(json_str)
                st.session_state.q_curr = qobj["question"] + "\n\n" + "\n".join(qobj["choices"])
                st.session_state.q_answer = qobj["answer"].strip().upper()
                st.session_state.q_explanation = qobj.get("explanation", "")
                st.session_state.q_active = True
                placeholder.success("تم إنشاء سؤال:")
                placeholder.markdown(st.session_state.q_curr)
                append_chat_history_local(user_name, {"time": now_str(), "type":"mcq_generated","question": qobj})
                update_xp(user_name, 5)
            except Exception as e:
                logger.exception("Failed to parse MCQ JSON: %s", e)
                placeholder.error("تعذّر فهم استجابة الموديل. الرد الخام أدناه:")
                placeholder.code(resp)
            return

        # General response: display then TTS (best-effort)
        placeholder.empty()
        stream_text_to_placeholder(resp, placeholder)
        append_chat_history_local(user_name, {"time": now_str(), "input_type": input_type, "input": str(user_text)[:1000], "response": resp})
        update_xp(user_name, 5)
        try:
            vc = "ar-EG-ShakirNeural" if lang == "العربية" else "en-US-ChristopherNeural"
            audio_bytes = generate_audio_sync(re.sub(r'```dot[\s\S]*?```', '', resp)[:1200], vc) if edge_tts else None
            if audio_bytes:
                play_tts_bytes(audio_bytes)
        except Exception:
            logger.exception("TTS generation/playback failed")

    except Exception as e:
        logger.exception("Processing AI response failed")
        placeholder.error(f"خطأ داخلي أثناء المعالجة: {e}")
        safe_write_local_log({"type":"error","time":now_str(),"error":str(e),"context":str(user_text)[:1000]})

# ==========================================
# UI: header, sidebar (with debug expander), tabs
# ==========================================
draw_header()

# show fancy name if authenticated (no auth logic changed)
if st.session_state.get("auth_status"):
    render_fancy_name(st.session_state.get("user_name", "ضيف"))

with st.sidebar:
    st.write(f"أهلاً، **{st.session_state.get('user_name','ضيف')}**")
    if st.session_state.get("auth_status"):
        st.markdown(f"<div style='font-size:13px;color:#fff;padding:6px;border-radius:6px;background:linear-gradient(90deg,#6a11cb,#2575fc);text-align:center;margin-top:6px;'>المستخدم: <strong>{st.session_state.get('user_name')}</strong></div>", unsafe_allow_html=True)

    diag = st.expander("⚙️ Diagnostics (AI providers)")
    with diag:
        st.write("Installed modules:")
        st.write(f"- google.generativeai: {'✅' if genai else '❌'}")
        st.write(f"- openai: {'✅' if openai else '❌'}")
        st.write(f"- edge-tts: {'✅' if edge_tts else '❌'}")
        st.write(f"- speech_recognition: {'✅' if sr else '❌'}")
        st.write(f"- streamlit_mic_recorder: {'✅' if mic_recorder else '❌'}")
        st.write("---")
        st.write("Configured keys:")
        st.write(f"- GOOGLE_API_KEYS: {len(GOOGLE_API_KEYS) if GOOGLE_API_KEYS else 0}")
        st.write(f"- OPENAI_API_KEY: {'✅' if OPENAI_API_KEY else '❌'}")
        if st.button("Run quick AI ping test"):
            try:
                ok, resp, err = safe_call_model_with_retries("Say 'ping' in a short sentence.", max_retries=2)
                if ok:
                    st.success("AI ping OK")
                    st.write(resp[:500])
                else:
                    st.error("Ping failed. Summary:")
                    st.write(err)
                    st.write("---")
                    st.write("Collected provider attempt errors:")
                    st.write("\n".join(_last_provider_errors))
            except Exception as e:
                st.error("Ping routine failed: " + repr(e))

    st.markdown("---")
    st.session_state.language = st.radio("اللغة:", ["العربية", "English"])
    st.markdown("---")
    # show last AI debug data
    with st.expander("آخر حالة AI (Debug)"):
        st.write("last_ai_ok:", st.session_state.get("last_ai_ok"))
        st.write("last_ai_err:", st.session_state.get("last_ai_err"))
        st.write("last_ai_resp (preview):")
        resp = st.session_state.get("last_ai_resp", "")
        if resp:
            st.code((resp or "")[:800])
        else:
            st.write("لا يوجد استجابة محفوظة بعد.")
        st.write("provider attempts/errors:")
        st.write("\n".join(_last_provider_errors or []))

    st.markdown("---")
    # Drive listing and activation
    if DRIVE_FOLDER_ID and build and GCP_SA:
        if st.button("تحميل قائمة ملفات Drive"):
            try:
                creds = service_account.Credentials.from_service_account_info(dict(GCP_SA), scopes=['https://www.googleapis.com/auth/drive.readonly'])
                drive_service = build('drive', 'v3', credentials=creds)
                q = f"'{DRIVE_FOLDER_ID}' in parents and trashed = false"
                res = drive_service.files().list(q=q, fields="files(id, name)").execute()
                files = res.get('files', [])
                st.session_state.drive_files = files
                st.success(f"تم جلب {len(files)} ملف(ـاً).")
            except Exception as e:
                logger.exception("Drive listing failed")
                st.error(f"فشل جلب قائمة الملفات: {e}")

        if st.session_state.get("drive_files"):
            st.markdown("**اختر كتابًا ثم اضغط تفعيل**")
            names = [f["name"] for f in st.session_state["drive_files"]]
            sel = st.selectbox("📚 المكتبة:", names, key="drive_select")
            if st.button("تفعيل الكتاب"):
                fid = next((f["id"] for f in st.session_state["drive_files"] if f["name"] == sel), None)
                if fid:
                    try:
                        creds = service_account.Credentials.from_service_account_info(dict(GCP_SA), scopes=['https://www.googleapis.com/auth/drive.readonly'])
                        drive_service = build('drive', 'v3', credentials=creds)
                        req = drive_service.files().get_media(fileId=fid)
                        fh = BytesIO()
                        downloader = MediaIoBaseDownload(fh, req)
                        done = False
                        while not done:
                            _, done = downloader.next_chunk()
                        fh.seek(0)
                        reader = PyPDF2.PdfReader(fh)
                        text = ""
                        for page in reader.pages:
                            text += (page.extract_text() or "")
                        st.session_state.ref_text = text
                        st.session_state.book_activated = sel
                        st.success(f"تم تفعيل الكتاب: {sel}")
                    except Exception as e:
                        logger.exception("Failed activating book")
                        st.error(f"فشل تحميل الكتاب من Drive: {e}")
        if st.session_state.get("book_activated"):
            st.info(f"الكتاب المفعل حالياً: {st.session_state['book_activated']}")
    st.caption("نسخة محسّنة - تحكّم كامل")

# ==========================================
# Authentication UI
# ==========================================
if not st.session_state.auth_status:
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.info(random.choice(DAILY_FACTS))
        with st.form("login_form"):
            name = st.text_input("الاسم:")
            grade = st.selectbox("الصف:", ["الرابع","الخامس","السادس","الأول ع","الثاني ع","الثالث ع","ثانوي","Other"])
            code = st.text_input("الكود:", type="password")
            remember = st.checkbox("تذكرني على هذا الجهاز")
            if st.form_submit_button("دخول"):
                db_code = safe_get_control_sheet_value()
                is_teacher = (code == TEACHER_MASTER_KEY)
                is_student = (db_code and code == db_code) or (not db_code and code == TEACHER_MASTER_KEY)
                if is_teacher or is_student:
                    st.session_state.auth_status = True
                    st.session_state.user_type = "teacher" if is_teacher else "student"
                    st.session_state.user_name = name if is_student else "Mr. Elsayed"
                    st.session_state.student_grade = grade
                    st.session_state.start_time = time.time()
                    st.session_state.current_xp = 0 if not is_student else st.session_state.get("current_xp", 0)
                    log_login(st.session_state.user_name, "teacher" if is_teacher else "student", grade)
                    st.success("تم الدخول!")
                    st.session_state["_needs_rerun"] = True
                else:
                    st.error("الكود غير صحيح")
                    if not db_code:
                        st.info("ملاحظة: لم يتم العثور على كود الطلاب في ورقة التحكم App_Control. تحقق من إعدادات Google Drive/Sheet أو استخدم TEACHER_MASTER_KEY.")
    if st.session_state.pop("_needs_rerun", False):
        time.sleep(0.4); safe_rerun()
    st.stop()

# Session expiry
if session_expired():
    st.warning("انتهت الجلسة. يرجى تسجيل الدخول مرة أخرى.")
    st.session_state.auth_status = False
    safe_rerun()

# Tabs
t1, t2, t3, t4 = st.tabs(["🎙️ صوت","📝 نص","📷 صورة","🧠 تدريب/اختبار"])

# Voice tab
with t1:
    st.write("🎤 تحدث أو حمّل ملف صوتي")
    if not mic_recorder:
        st.info("mic_recorder غير متوفر. يمكنك رفع ملف صوتي بدلاً من التسجيل.")
        up = st.file_uploader("رفع ملف صوتي:", type=["wav","mp3","m4a","ogg"])
        if up:
            st.audio(up)
            if st.button("تحويل الملف إلى نص"):
                bytesa = up.read()
                lang = "ar-EG" if st.session_state.language=="العربية" else "en-US"
                txt = speech_to_text_bytes(bytesa, lang)
                if txt:
                    st.write("تم التحويل:", txt)
                    update_xp(st.session_state.user_name,10)
                    process_ai_response(txt, "voice")
                else:
                    st.error("تعذّر التحويل")
        st.stop()
    try:
        aud = mic_recorder(start_prompt="🎤", stop_prompt="⏹️", key="m")
    except Exception as e:
        logger.exception("mic_recorder invocation failed: %s", e)
        aud = None
    if aud:
        audio_bytes = None
        if isinstance(aud, dict):
            audio_bytes = aud.get("bytes") or aud.get("data")
        elif isinstance(aud, (bytes,bytearray)):
            audio_bytes = aud
        if audio_bytes:
            if isinstance(audio_bytes, str):
                try:
                    audio_bytes = base64.b64decode(audio_bytes.split(",",1)[1] if audio_bytes.startswith("data:") else audio_bytes)
                except Exception:
                    logger.exception("decode recorder string failed")
            if audio_bytes != st.session_state.get("last_audio_bytes"):
                st.session_state.last_audio_bytes = audio_bytes
                try:
                    st.audio(BytesIO(audio_bytes))
                except Exception:
                    try:
                        st.audio(BytesIO(audio_bytes), format="audio/wav")
                    except Exception:
                        st.warning("معاينة الصوت قد لا تعمل في هذا التنسيق.")
                lang = "ar-EG" if st.session_state.language=="العربية" else "en-US"
                with st.spinner("تحويل الصوت إلى نص..."):
                    txt = speech_to_text_bytes(audio_bytes, lang)
                if txt:
                    st.write("تم التحويل:", txt)
                    update_xp(st.session_state.user_name,10)
                    process_ai_response(txt, "voice")
                else:
                    st.error("تعذّر تحويل التسجيل إلى نص")

# Text tab (stable input)
with t2:
    st.markdown("اكتب سؤالك نصياً ثم اضغط إرسال:")
    q_text = st.text_area("سؤالك:", key="text_question", height=120)
    if st.button("إرسال السؤال"):
        if q_text and q_text.strip():
            st.write("سؤالك:", q_text)
            update_xp(st.session_state.user_name,5)
            process_ai_response(q_text, "text")
            st.session_state["text_question"] = ""
        else:
            st.warning("اكتب السؤال أولاً")

# Image tab
with t3:
    up = st.file_uploader("صورة (png/jpg)", type=["png","jpg","jpeg"])
    if up:
        try:
            img = Image.open(up)
            st.image(img, width=300)
            if st.button("تحليل الصورة"):
                update_xp(st.session_state.user_name, 15)
                process_ai_response(["اشرح الصورة وبيّن المفاهيم", img], "image")
        except Exception:
            st.exception("فشل فتح الصورة")

# MCQ tab
with t4:
    st.markdown("### 📝 أسئلة متعددة الاختيارات (MCQ)")
    colA, colB = st.columns(2)
    with colA:
        if st.button("توليد سؤال جديد"):
            process_ai_response(None, "mcq_generate")
    with colB:
        if st.session_state.get("q_active") and st.session_state.get("q_curr"):
            st.markdown("---")
            st.write(st.session_state.q_curr)
            ans = st.text_input("إجابتك (A/B/C/D):", key="mcq_ans")
            if st.button("تحقق الإجابة"):
                if ans:
                    process_ai_response({"answer": ans}, "mcq_check")
                else:
                    st.warning("اكتب إجابتك أولاً (A/B/C/D).")
        else:
            st.info("اضغط 'توليد سؤال جديد' لبدء.")

# Footer & persist chat history
st.markdown("---")
st.caption("AI Science Tutor Pro — راجع Diagnostics وآخر حالة AI للمعلومات التقنية.")

try:
    if st.session_state.get("chat_history"):
        append_chat_history_local(st.session_state.get("user_name","anonymous"), {"time": now_str(), "history": st.session_state.chat_history})
except Exception:
    logger.exception("Failed to persist session chat history")
