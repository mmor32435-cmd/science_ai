# (تم اختصار التعليقات الطويلة في رأس الملف لاقتصاد المساحة)
import streamlit as st
import time, asyncio, re, random, threading, subprocess, shutil, base64, json, logging
from io import BytesIO
from datetime import datetime
import pytz, os
from typing import Optional, Dict, Any, List, Tuple
from PIL import Image
import PyPDF2

# Optional imports
try: import google.generativeai as genai
except Exception: genai = None
try: import openai
except Exception: openai = None
try: import edge_tts
except Exception: edge_tts = None
try: import speech_recognition as sr
except Exception: sr = None
try: from streamlit_mic_recorder import mic_recorder
except Exception: mic_recorder = None
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    import gspread, pandas as pd
except Exception:
    service_account = build = MediaIoBaseDownload = None
    gspread = pd = None

# config
st.set_page_config(page_title="AI Science Tutor Pro", page_icon="🧬", layout="wide")
TEACHER_MASTER_KEY = st.secrets.get("TEACHER_MASTER_KEY", "ADMIN_2024_PLACEHOLDER")
DRIVE_FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "")
GOOGLE_API_KEYS = st.secrets.get("GOOGLE_API_KEYS", [])
OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY", "")
GCP_SA = st.secrets.get("gcp_service_account", None)
SESSION_DURATION_MINUTES = int(st.secrets.get("SESSION_DURATION_MINUTES", 60))
RATE_LIMIT_MIN_SECONDS = int(st.secrets.get("RATE_LIMIT_MIN_SECONDS", 1))
LOCAL_LOG_FILE = "logs_local.json"
CHAT_HISTORY_DIR = "chat_histories"
os.makedirs(CHAT_HISTORY_DIR, exist_ok=True)

# logging
logger = logging.getLogger("ai_science_tutor")
if not logger.handlers:
    h = logging.StreamHandler(); h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s")); logger.addHandler(h)
logger.setLevel(logging.INFO)

# safe rerun
def safe_rerun():
    try:
        if hasattr(st, "experimental_rerun"): st.experimental_rerun(); return
        if hasattr(st, "rerun"): st.rerun(); return
    except Exception:
        logger.exception("safe_rerun failed")
    try: st.stop()
    except Exception: logger.exception("safe_rerun stop failed")

def now_str():
    return datetime.now(pytz.timezone("Africa/Cairo")).strftime("%Y-%m-%d %H:%M:%S")

def safe_write_local_log(entry: Dict[str, Any]):
    try:
        with open(LOCAL_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        logger.exception("write local log failed")

def append_chat_history_local(user_name: str, entry: Dict[str, Any]):
    path = os.path.join(CHAT_HISTORY_DIR, f"{user_name}.jsonl")
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        logger.exception("append chat history failed")

# Initialize session_state
if "auth_status" not in st.session_state:
    st.session_state.update({
        "auth_status": False, "user_type":"none", "chat_history":[], "student_grade":"General",
        "current_xp":0, "last_audio_bytes":None, "language":"العربية", "ref_text":"",
        "last_request_time":None, "start_time": time.time(), "q_active":False, "q_answer":None,
        "q_explanation":None, "book_activated":None, "drive_files": None
    })

# Provider init
_last_provider_errors: List[str] = []
def init_google_genai_if_available():
    if genai and GOOGLE_API_KEYS:
        for k in GOOGLE_API_KEYS:
            try:
                genai.configure(api_key=k)
                return True
            except Exception:
                continue
    return False
_GOOGLE_INITIALIZED = init_google_genai_if_available()

def call_model(prompt: str, *, model_preferences: Optional[List[str]] = None) -> str:
    global _last_provider_errors
    _last_provider_errors = []
    if not prompt: return ""
    if genai and _GOOGLE_INITIALIZED:
        try:
            if hasattr(genai, "TextGenerationModel"):
                for candidate in (model_preferences or ["gemini-2.5-flash","gemini-flash-latest"]):
                    try:
                        m = genai.TextGenerationModel.from_pretrained(candidate)
                        r = m.generate(prompt=prompt, max_output_tokens=512)
                        if hasattr(r, "candidates"): return r.candidates[0].content
                        if hasattr(r, "outputs"): return r.outputs[0].content
                    except Exception as e:
                        _last_provider_errors.append(f"Google({candidate}): {e}")
            if hasattr(genai, "generate_text"):
                try:
                    r = genai.generate_text(model="gemini-2.5-flash", prompt=prompt)
                    if isinstance(r, dict) and "candidates" in r: return r["candidates"][0].get("content","")
                    return str(r)
                except Exception as e:
                    _last_provider_errors.append(f"Google(generate_text): {e}")
        except Exception as e:
            _last_provider_errors.append(f"Google general: {e}")
    if openai and OPENAI_API_KEY:
        try:
            openai.api_key = OPENAI_API_KEY
            try:
                resp = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=[{"role":"user","content":prompt}], max_tokens=512)
                return resp.choices[0].message.content
            except Exception as e:
                _last_provider_errors.append(f"OpenAI ChatCompletion: {e}")
        except Exception as e:
            _last_provider_errors.append(f"OpenAI general: {e}")
    if not _last_provider_errors:
        _last_provider_errors.append("No AI providers configured.")
    raise RuntimeError("No AI provider available. Attempts:\n" + "\n".join(_last_provider_errors))

def safe_call_model(prompt: str) -> Tuple[bool,str,Optional[str]]:
    try:
        t = call_model(prompt)
        return True, t, None
    except Exception as e:
        logger.exception("call_model failed")
        return False, "", str(e)

def safe_call_model_with_retries(prompt: str, max_retries: int = 3, base_delay: float = 2.0) -> Tuple[bool,str,Optional[str]]:
    attempt = 0; last_err = None
    while attempt < max_retries:
        attempt += 1
        ok, text, err = safe_call_model(prompt)
        if ok: return True, text, None
        last_err = err or "unknown"
        lowered = last_err.lower()
        if any(k in lowered for k in ["quota","rate limit","429","retry"]):
            m = re.search(r"retry in\s*([0-9\.]+)s", last_err, flags=re.IGNORECASE)
            delay = (float(m.group(1))+0.5) if m else base_delay * (2**(attempt-1))
            logger.warning("Retrying after %.1f s due to provider rate/quota", delay)
            time.sleep(delay)
            continue
        break
    return False, "", last_err

# Audio conversion helpers
def _has_ffmpeg(): return shutil.which("ffmpeg") is not None
def convert_audio_to_wav_bytes(raw_bytes: bytes, input_format: Optional[str]=None) -> Optional[bytes]:
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
            if p.returncode==0: return out
            logger.error("ffmpeg conversion failed: %s", err.decode(errors="ignore"))
        except Exception:
            logger.exception("ffmpeg conversion exception")
    logger.debug("No conversion available")
    return None

def speech_to_text_bytes(audio_bytes: bytes, lang_code: str = "ar-EG") -> Optional[str]:
    if not sr: logger.warning("speech_recognition missing"); return None
    try:
        if isinstance(audio_bytes, str):
            if audio_bytes.startswith("data:"): audio_bytes = audio_bytes.split(",",1)[1]
            audio_bytes = base64.b64decode(audio_bytes)
    except Exception:
        logger.exception("decode base64 failed")
    wav_bytes = None
    try:
        if isinstance(audio_bytes, (bytes,bytearray)) and audio_bytes[:4]==b'RIFF': wav_bytes = bytes(audio_bytes)
    except Exception: pass
    if not wav_bytes:
        wav_bytes = convert_audio_to_wav_bytes(audio_bytes, None)
    if not wav_bytes:
        logger.error("conversion to wav failed")
        return None
    r = sr.Recognizer()
    try:
        with sr.AudioFile(BytesIO(wav_bytes)) as source:
            r.adjust_for_ambient_noise(source, duration=0.5)
            audio_data = r.record(source)
            return r.recognize_google(audio_data, language=lang_code)
    except sr.UnknownValueError:
        logger.info("speech not understood"); return None
    except sr.RequestError as e:
        logger.exception("speech req error: %s", e); return None
    except Exception:
        logger.exception("speech to text general"); return None

def stream_text_to_placeholder(text: str, placeholder, delay: float = 0.02):
    buf=""; cnt=0
    for ch in text:
        buf += ch; cnt += 1
        if cnt % 20 == 0:
            placeholder.markdown(buf); time.sleep(delay)
    placeholder.markdown(buf)

def play_tts_bytes(audio_bytes: bytes):
    if not audio_bytes: return
    try:
        st.audio(BytesIO(audio_bytes), format="audio/mp3", start_time=0)
    except Exception:
        try: st.audio(BytesIO(audio_bytes), start_time=0)
        except Exception: logger.exception("play tts failed")

# Local search fallback: find sentences in ref_text that match keywords
def local_search_answer(question: str, ref_text: str) -> Optional[str]:
    if not ref_text: return None
    q_words = [w.lower() for w in re.findall(r"\w{3,}", question)]
    if not q_words: return None
    # split into sentences
    sents = re.split(r'(?<=[.!?])\s+', ref_text)
    matches = []
    for sent in sents:
        lw = sent.lower()
        score = sum(1 for w in q_words if w in lw)
        if score>0:
            matches.append((score, sent.strip()))
    matches.sort(reverse=True)
    if not matches: return None
    # return top 2 unique sentences
    out = []
    seen = set()
    for sc, s in matches[:3]:
        if s not in seen:
            out.append(s)
            seen.add(s)
    return "\n\n".join(out)

# Logging & XP helpers
def log_login(user_name, user_type, details): threading.Thread(target=safe_write_local_log, args=({"time":now_str(),"type":"login","user":user_name,"user_type":user_type,"details":details},)).start()
def log_activity(user_name, input_type, text): threading.Thread(target=safe_write_local_log, args=({"time":now_str(),"type":"activity","user":user_name,"input_type":input_type,"text":str(text)[:1000]},)).start()
def update_xp(user_name, points):
    if 'current_xp' in st.session_state: st.session_state.current_xp = st.session_state.get("current_xp",0)+points
    threading.Thread(target=safe_update_xp_sheet, args=(user_name, points)).start()
    safe_write_local_log({"type":"xp","time":now_str(),"user":user_name,"points":points})

# NOTE: safe_update_xp_sheet, get_gspread_client, etc. kept same (omitted here for brevity if needed reuse previous implementation)

# UI helpers
def draw_header():
    st.markdown("<div style='background:linear-gradient(135deg,#6a11cb,#2575fc);padding:1rem;border-radius:12px;color:white;text-align:center;'><h1 style='margin:0;'>🧬 AI Science Tutor Pro</h1></div>", unsafe_allow_html=True)

draw_header()

# Sidebar (Drive loading + diagnostics) - keep logic to load files and activate book
with st.sidebar:
    st.write(f"أهلاً **{st.session_state.get('user_name','ضيف')}**")
    diag = st.expander("⚙️ Diagnostics")
    with diag:
        st.write(f"google.genai: {'✅' if genai else '❌'}")
        st.write(f"openai: {'✅' if openai else '❌'}")
        st.write(f"edge-tts: {'✅' if edge_tts else '❌'}")
        st.write(f"speech_recognition: {'✅' if sr else '❌'}")
        st.write(f"mic_recorder: {'✅' if mic_recorder else '❌'}")
        st.write("---")
        st.write(f"GOOGLE_API_KEYS: {len(GOOGLE_API_KEYS) if GOOGLE_API_KEYS else 0}")
        st.write(f"OPENAI_API_KEY: {'✅' if OPENAI_API_KEY else '❌'}")
        if st.button("AI ping test"):
            ok, resp, err = safe_call_model_with_retries("Say 'ping' in a short sentence.", max_retries=2)
            if ok: st.success("AI ping OK"); st.write(resp[:400])
            else:
                st.error("Ping failed"); st.write(err); st.write("\n".join(_last_provider_errors))
    st.markdown("---")
    st.session_state.language = st.radio("اللغة:", ["العربية","English"])
    st.markdown("---")
    if DRIVE_FOLDER_ID and build and GCP_SA:
        if st.button("تحميل قائمة ملفات Drive"):
            try:
                creds = service_account.Credentials.from_service_account_info(dict(GCP_SA), scopes=['https://www.googleapis.com/auth/drive.readonly'])
                drive_service = build('drive','v3', credentials=creds)
                q = f"'{DRIVE_FOLDER_ID}' in parents and trashed = false"
                res = drive_service.files().list(q=q, fields="files(id,name)").execute()
                st.session_state.drive_files = res.get('files',[])
                st.success(f"جلب {len(st.session_state.drive_files)} ملف")
            except Exception as e:
                st.error(f"فشل جلب: {e}")
        if st.session_state.get("drive_files"):
            st.markdown("اختر كتابًا ثم تفعيل")
            names = [f["name"] for f in st.session_state["drive_files"]]
            sel = st.selectbox("📚", names, key="drive_select")
            if st.button("تفعيل الكتاب"):
                fid = next((f["id"] for f in st.session_state["drive_files"] if f["name"]==sel), None)
                if fid:
                    try:
                        creds = service_account.Credentials.from_service_account_info(dict(GCP_SA), scopes=['https://www.googleapis.com/auth/drive.readonly'])
                        drive_service = build('drive','v3', credentials=creds)
                        req = drive_service.files().get_media(fileId=fid)
                        fh = BytesIO()
                        downloader = MediaIoBaseDownload(fh, req)
                        done=False
                        while not done:
                            _, done = downloader.next_chunk()
                        fh.seek(0)
                        reader = PyPDF2.PdfReader(fh)
                        text = ""
                        for p in reader.pages: text += (p.extract_text() or "")
                        st.session_state.ref_text = text
                        st.session_state.book_activated = sel
                        st.success(f"تم تفعيل {sel}")
                    except Exception as e:
                        st.error(f"فشل التفعيل: {e}")
        if st.session_state.get("book_activated"):
            st.info(f"الكتاب المفعل: {st.session_state['book_activated']}")

# Authentication (kept minimal)
if not st.session_state.auth_status:
    col1,col2,col3 = st.columns([1,2,1])
    with col2:
        with st.form("login"):
            name = st.text_input("الاسم:")
            grade = st.selectbox("الصف:", ["الرابع","الخامس","السادس","الأول ع","الثاني ع","الثالث ع","ثانوي","Other"])
            code = st.text_input("الكود:", type="password")
            if st.form_submit_button("دخول"):
                db_code = None
                try:
                    db_code = safe_get_control_sheet_value()
                except Exception:
                    db_code = None
                is_teacher = (code == TEACHER_MASTER_KEY)
                is_student = (db_code and code == db_code) or (not db_code and code == TEACHER_MASTER_KEY)
                if is_teacher or is_student:
                    st.session_state.auth_status = True
                    st.session_state.user_type = "teacher" if is_teacher else "student"
                    st.session_state.user_name = name if is_student else "Mr. Elsayed"
                    st.session_state.student_grade = grade
                    st.session_state.start_time = time.time()
                    st.session_state.current_xp = 0 if not is_student else st.session_state.get("current_xp",0)
                    log_login(st.session_state.user_name, "teacher" if is_teacher else "student", grade)
                    st.success("تم الدخول")
                    st.session_state["_needs_rerun"] = True
                else:
                    st.error("كود خاطئ")
    if st.session_state.pop("_needs_rerun", False):
        time.sleep(0.3); safe_rerun()
    st.stop()

# Session expiry
if (time.time() - st.session_state.get("start_time", time.time())) > SESSION_DURATION_MINUTES*60:
    st.warning("انتهت الجلسة"); st.session_state.auth_status=False; safe_rerun()

# Tabs
t1,t2,t3,t4 = st.tabs(["🎙️ صوت","📝 نص","📷 صورة","🧠 تدريب/اختبار"])

# Voice tab
with t1:
    st.write("سجل أو حمّل ملف صوتي")
    if not mic_recorder:
        st.info("mic_recorder غير متوفر. حمّل ملف صوتي بدلاً من ذلك.")
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
    # mic_recorder present
    try:
        aud = mic_recorder(start_prompt="🎤", stop_prompt="⏹️", key="m")
    except Exception as e:
        st.error("تعذر تشغيل المسجل (راجع Console)"); logger.exception(e); aud=None
    if aud:
        audio_bytes = None
        if isinstance(aud, dict): audio_bytes = aud.get("bytes") or aud.get("data")
        elif isinstance(aud, (bytes,bytearray)): audio_bytes = aud
        if audio_bytes:
            if isinstance(audio_bytes, str):
                try: audio_bytes = base64.b64decode(audio_bytes.split(",",1)[1] if audio_bytes.startswith("data:") else audio_bytes)
                except Exception: logger.exception("decode fail")
            if audio_bytes != st.session_state.get("last_audio_bytes"):
                st.session_state.last_audio_bytes = audio_bytes
                st.audio(BytesIO(audio_bytes))
                lang = "ar-EG" if st.session_state.language=="العربية" else "en-US"
                with st.spinner("تحويل الصوت ��لى نص..."):
                    txt = speech_to_text_bytes(audio_bytes, lang)
                if txt:
                    st.write("تم التحويل:", txt)
                    update_xp(st.session_state.user_name,10)
                    process_ai_response(txt, "voice")
                else:
                    st.error("تعذّر تحويل التسجيل إلى نص")
        else:
            st.info("اضغط زر التسجيل")

# Text tab: stable input
with t2:
    st.markdown("اكتب سؤالك ثم اضغط إرسال:")
    q_text = st.text_area("سؤالك:", key="q_text", height=120)
    if st.button("إرسال السؤال"):
        if q_text and q_text.strip():
            st.write("سؤالك:", q_text)
            update_xp(st.session_state.user_name,5)
            process_ai_response(q_text, "text")
            st.session_state.q_text = ""
        else:
            st.warning("اكتب السؤال أولاً")

# Image tab
with t3:
    up = st.file_uploader("صورة:", type=["png","jpg","jpeg"])
    if up:
        img = Image.open(up)
        st.image(img, width=300)
        if st.button("تحليل الصورة"):
            update_xp(st.session_state.user_name,15)
            process_ai_response(["اشرح الصورة وبيّن المفاهيم", img], "image")

# MCQ tab
with t4:
    st.markdown("MCQ من كتاب الطالب")
    if st.button("توليد سؤال جديد"):
        process_ai_response(None, "mcq_generate")
    if st.session_state.get("q_active") and st.session_state.get("q_curr"):
        st.write(st.session_state.q_curr)
        ans = st.text_input("إجابتك (A/B/C/D):", key="mcq_ans")
        if st.button("تحقق الإجابة"):
            if ans:
                process_ai_response({"answer": ans}, "mcq_check")
            else:
                st.warning("اكتب إجابتك")

# Footer
st.markdown("---")
st.caption("احتفظ بمفاتيحك في st.secrets. راجع Diagnostics في الشريط الجانبي عند المشاكل.")
