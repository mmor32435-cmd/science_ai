# ============================================================
# 🧬 AI Science Tutor Pro — FINAL STABLE VERSION
# ============================================================

import streamlit as st
import time, json, re, os, base64, asyncio, logging
from io import BytesIO
from datetime import datetime
from typing import List, Tuple
from PIL import Image
import pytz

# =========================
# Optional Providers
# =========================
try:
    import google.generativeai as genai
except:
    genai = None

try:
    import openai
except:
    openai = None

try:
    import edge_tts
except:
    edge_tts = None

try:
    import speech_recognition as sr
except:
    sr = None

# =========================
# Streamlit Config
# =========================
st.set_page_config(
    page_title="AI Science Tutor Pro",
    page_icon="🧬",
    layout="wide"
)

# =========================
# Secrets
# =========================
OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY", "")
GOOGLE_API_KEYS = st.secrets.get("GOOGLE_API_KEYS", [])
SESSION_DURATION_MINUTES = int(st.secrets.get("SESSION_DURATION_MINUTES", 60))
RATE_LIMIT_SECONDS = 1

# =========================
# Logging
# =========================
logger = logging.getLogger("Tutor")
logger.setLevel(logging.INFO)

# =========================
# Utilities
# =========================
def now():
    return datetime.now(pytz.timezone("Africa/Cairo")).strftime("%Y-%m-%d %H:%M:%S")

def safe_rerun():
    try:
        st.rerun()
    except:
        st.stop()

# =========================
# AI Providers Wrapper
# =========================
_last_provider_errors: List[str] = []

def call_ai(prompt: str) -> str:
    global _last_provider_errors
    _last_provider_errors = []

    if genai and GOOGLE_API_KEYS:
        for key in GOOGLE_API_KEYS:
            try:
                genai.configure(api_key=key)
                model = genai.GenerativeModel("gemini-1.5-flash")
                return model.generate_content(prompt).text
            except Exception as e:
                _last_provider_errors.append(f"Google: {e}")

    if openai and OPENAI_API_KEY:
        try:
            openai.api_key = OPENAI_API_KEY
            r = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=700
            )
            return r.choices[0].message.content
        except Exception as e:
            _last_provider_errors.append(f"OpenAI: {e}")

    raise RuntimeError("No AI provider available")

def safe_call(prompt: str, retries=3) -> Tuple[bool, str]:
    last_err = ""
    for i in range(retries):
        try:
            return True, call_ai(prompt)
        except Exception as e:
            last_err = str(e)
            time.sleep(2 ** i)
    return False, last_err

# =========================
# Session Init
# =========================
if "auth" not in st.session_state:
    st.session_state.update({
        "auth": False,
        "user": "Student",
        "xp": 0,
        "lang": "العربية",
        "start": time.time(),
        "last_req": None
    })

# =========================
# Session Expiry
# =========================
if time.time() - st.session_state.start > SESSION_DURATION_MINUTES * 60:
    st.warning("⏱️ انتهت الجلسة")
    st.session_state.clear()
    safe_rerun()
# =========================
# Header
# =========================
st.markdown("""
<div style="background:linear-gradient(135deg,#6a11cb,#2575fc);
padding:1.2rem;border-radius:12px;text-align:center;color:white">
<h1>🧬 AI Science Tutor Pro</h1>
<p>معلّم ذكي للعلوم – نص | صور | اختبارات</p>
</div>
""", unsafe_allow_html=True)

# =========================
# Sidebar
# =========================
with st.sidebar:
    st.radio("🌐 اللغة", ["العربية", "English"], key="lang")
    st.markdown("---")
    st.write(f"⭐ XP: {st.session_state.xp}")
    st.markdown("---")
    with st.expander("⚙️ Diagnostics"):
        st.write("Google:", "✅" if genai else "❌")
        st.write("OpenAI:", "✅" if openai else "❌")
        st.write("edge-tts:", "✅" if edge_tts else "❌")
        st.code("\n".join(_last_provider_errors) or "No errors")

# =========================
# TTS
# =========================
async def _tts_async(text: str, voice: str):
    comm = edge_tts.Communicate(text, voice)
    buf = BytesIO()
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    return buf.getvalue()

def tts(text: str):
    if not edge_tts:
        return None
    voice = "ar-EG-ShakirNeural" if st.session_state.lang == "العربية" else "en-US-ChristopherNeural"
    try:
        return asyncio.run(_tts_async(text[:1200], voice))
    except:
        return None

# =========================
# Tabs
# =========================
t1, t2, t3 = st.tabs(["📝 نص", "📷 صورة", "🧠 MCQ"])

# =========================
# TEXT TAB (SAFE)
# =========================
with t1:
    st.text_area("اكتب سؤالك:", key="text_q", height=120)

    def send_text():
        q = st.session_state.text_q.strip()
        if not q:
            st.warning("❗ اكتب السؤال أولاً")
            return
        st.session_state.to_process = q
        st.session_state.text_q = ""

    st.button("إرسال", on_click=send_text)

    if "to_process" in st.session_state:
        q = st.session_state.pop("to_process")
        st.write("🧑‍🎓 سؤالك:", q)

        if st.session_state.last_req and time.time() - st.session_state.last_req < RATE_LIMIT_SECONDS:
            st.warning("⏳ انتظر قليلاً")
        else:
            st.session_state.last_req = time.time()
            ok, res = safe_call(
                f"You are a science tutor. Answer clearly in {st.session_state.lang}:\n{q}"
            )

            if ok:
                st.success("🤖 الإجابة:")
                st.write(res)
                st.session_state.xp += 5
                audio = tts(res)
                if audio:
                    st.audio(audio)
            else:
                st.error("❌ فشل الاتصال")
                st.code(res)
# =========================
# IMAGE TAB
# =========================
with t2:
    img = st.file_uploader("ارفع صورة", type=["png", "jpg", "jpeg"])
    if img:
        image = Image.open(img)
        st.image(image, width=300)
        if st.button("تحليل الصورة"):
            ok, res = safe_call(
                "Explain the scientific concepts in this image clearly."
            )
            if ok:
                st.write(res)
                st.session_state.xp += 10
            else:
                st.error("فشل تحليل الصورة")

# =========================
# MCQ TAB
# =========================
with t3:
    if st.button("توليد سؤال MCQ"):
        ok, res = safe_call("""
Generate ONE science MCQ in JSON only:
{
 "question":"",
 "choices":["A)","B)","C)","D)"],
 "answer":"A",
 "explanation":""
}
""")
        if ok:
            try:
                q = json.loads(re.search(r"\{[\s\S]*\}", res).group())
                st.session_state.mcq = q
                st.write(q["question"])
                for c in q["choices"]:
                    st.write(c)
            except:
                st.error("خطأ في JSON")
                st.code(res)

    if "mcq" in st.session_state:
        ans = st.text_input("إجابتك (A/B/C/D):")
        if st.button("تحقق"):
            if ans.upper() == st.session_state.mcq["answer"]:
                st.success("🎉 صحيح")
                st.session_state.xp += 20
            else:
                st.error("❌ خطأ")
            st.write("📘 الشرح:", st.session_state.mcq["explanation"])

# =========================
# Footer
# =========================
st.markdown("---")
st.caption(f"🧬 AI Science Tutor Pro | {now()}")
