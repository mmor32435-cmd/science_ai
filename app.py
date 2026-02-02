# diagnostic_app.py
import streamlit as st

st.set_page_config(page_title="تشخيص التطبيق", layout="wide", page_icon="🧪")

import os, sys, platform, traceback, time, json
from datetime import datetime
from typing import Dict, Any, List

# ---------- إعدادات (عدّلها لو لزم) ----------
FOLDER_ID = "1ub4ML8q4YCM_VZR991XXQ6hBBas2X6rS"
AVAILABLE_MODELS = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]

# ---------- أدوات مساعدة ----------
def redacted(s: str, keep_last: int = 4) -> str:
    if not s:
        return ""
    s = str(s)
    if len(s) <= keep_last:
        return "*" * len(s)
    return "*" * (len(s) - keep_last) + s[-keep_last:]

def safe_version(pkg: str) -> str:
    try:
        from importlib.metadata import version
        return version(pkg)
    except Exception:
        return "غير مثبت/غير معروف"

def run_check(name: str, fn):
    t0 = time.time()
    try:
        data = fn()
        return {
            "check": name,
            "ok": True,
            "ms": int((time.time() - t0) * 1000),
            "details": data,
            "error": ""
        }
    except Exception as e:
        return {
            "check": name,
            "ok": False,
            "ms": int((time.time() - t0) * 1000),
            "details": {},
            "error": f"{e}\n\n{traceback.format_exc()}"
        }

def show_results(results: List[Dict[str, Any]]):
    ok = sum(1 for r in results if r["ok"])
    bad = len(results) - ok
    st.subheader(f"النتائج: ✅ {ok} | ❌ {bad}")

    for r in results:
        with st.expander(f"{'✅' if r['ok'] else '❌'} {r['check']}  ({r['ms']} ms)", expanded=not r["ok"]):
            if r["ok"]:
                st.json(r["details"])
            else:
                st.error("فشل الاختبار")
                st.code(r["error"], language="text")

# ---------- اختبارات ----------
def check_boot():
    return {
        "time": datetime.utcnow().isoformat() + "Z",
        "file": os.path.basename(__file__) if "__file__" in globals() else "unknown",
        "cwd": os.getcwd()
    }

def check_python_env():
    return {
        "python_version": sys.version,
        "platform": platform.platform(),
        "executable": sys.executable,
    }

def check_streamlit_features():
    feats = {
        "streamlit_version": safe_version("streamlit"),
        "has_st_status": hasattr(st, "status"),
        "has_chat_input": hasattr(st, "chat_input"),
        "has_chat_message": hasattr(st, "chat_message"),
        "has_cache_resource": hasattr(st, "cache_resource"),
    }
    # تنبيه لأسباب الصفحة البيضاء الشائعة
    warnings = []
    v = feats["streamlit_version"]
    try:
        # مقارنة بسيطة
        major_minor = tuple(int(x) for x in v.split(".")[:2])
        if major_minor < (1, 25):
            warnings.append("نسخة Streamlit قديمة جدًا وقد تسبب صفحة بيضاء خصوصًا مع chat_input/chat_message.")
    except Exception:
        pass

    feats["warnings"] = warnings
    return feats

def check_common_conflicts():
    # مشاكل شائعة: تسمية الملف بأسماء مكتبات
    bad_names = {"streamlit.py", "google.py", "asyncio.py"}
    me = os.path.basename(__file__).lower() if "__file__" in globals() else ""
    return {
        "current_filename": me,
        "conflict_risk": me in bad_names,
        "note": "لو اسم ملفك streamlit.py أو google.py إلخ قد يحدث Crash/صفحة بيضاء."
    }

def check_installed_packages():
    pkgs = [
        "streamlit",
        "google-generativeai",
        "google-api-python-client",
        "google-auth",
        "edge-tts",
        "streamlit-mic-recorder",
        "speechrecognition",
    ]
    return {p: safe_version(p) for p in pkgs}

def check_secrets_shape():
    # لا نطبع القيم الحساسة
    keys = []
    sa = False
    try:
        keys_raw = st.secrets.get("GOOGLE_API_KEYS", [])
        if isinstance(keys_raw, str):
            keys = [k.strip() for k in keys_raw.split(",") if k.strip()]
        elif isinstance(keys_raw, (list, tuple)):
            keys = list(keys_raw)
        else:
            keys = []
    except Exception:
        keys = []

    try:
        sa = "gcp_service_account" in st.secrets
    except Exception:
        sa = False

    return {
        "has_GOOGLE_API_KEYS": bool(keys),
        "keys_count": len(keys),
        "keys_preview": [redacted(k) for k in keys[:5]],
        "has_gcp_service_account": sa,
        "secrets_top_level_keys": list(getattr(st, "secrets", {}).keys()) if hasattr(st, "secrets") else []
    }

def check_network():
    # اختبار بسيط للاتصال بدون requests
    import urllib.request
    t0 = time.time()
    with urllib.request.urlopen("https://www.google.com", timeout=8) as resp:
        code = resp.getcode()
    return {"google_status_code": code, "latency_ms": int((time.time() - t0) * 1000)}

def check_imports_google():
    out = {}
    # genai
    try:
        import google.generativeai as genai  # noqa
        out["google_generativeai_import"] = True
    except Exception as e:
        out["google_generativeai_import"] = f"FAIL: {e}"

    # drive
    try:
        from google.oauth2 import service_account  # noqa
        from googleapiclient.discovery import build  # noqa
        from googleapiclient.http import MediaIoBaseDownload  # noqa
        out["google_drive_imports"] = True
    except Exception as e:
        out["google_drive_imports"] = f"FAIL: {e}"

    return out

def _get_api_keys() -> List[str]:
    keys_raw = st.secrets.get("GOOGLE_API_KEYS", [])
    if isinstance(keys_raw, str):
        return [k.strip() for k in keys_raw.split(",") if k.strip()]
    if isinstance(keys_raw, (list, tuple)):
        return [str(k).strip() for k in keys_raw if str(k).strip()]
    return []

def _get_drive_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    if "gcp_service_account" not in st.secrets:
        raise RuntimeError("لا يوجد gcp_service_account داخل secrets")

    creds_dict = dict(st.secrets["gcp_service_account"])
    if "private_key" in creds_dict and isinstance(creds_dict["private_key"], str):
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

    credentials = service_account.Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)

def check_drive_access_list_folder():
    service = _get_drive_service()
    q = f"'{FOLDER_ID}' in parents and trashed=false"
    res = service.files().list(q=q, fields="files(id,name,size,mimeType)", pageSize=5).execute()
    files = res.get("files", [])
    return {
        "folder_id": FOLDER_ID,
        "found_count": len(files),
        "sample_files": files
    }

def check_drive_can_query_specific_name():
    service = _get_drive_service()
    search_name = st.session_state.get("diag_search_name", "Grade4_Ar")
    q = (
        f"'{FOLDER_ID}' in parents and "
        f"name contains '{search_name}' and "
        f"mimeType='application/pdf' and trashed=false"
    )
    res = service.files().list(q=q, fields="files(id,name,size,modifiedTime)", pageSize=10).execute()
    files = res.get("files", [])
    return {
        "search_name": search_name,
        "matches": len(files),
        "top_results": files[:5]
    }

def check_gemini_simple_generate():
    import google.generativeai as genai

    keys = _get_api_keys()
    if not keys:
        raise RuntimeError("لا توجد GOOGLE_API_KEYS داخل secrets")

    last_err = None
    for key in keys:
        try:
            genai.configure(api_key=key)
            # جرّب نموذج من القائمة
            for m in AVAILABLE_MODELS:
                try:
                    model = genai.GenerativeModel(m)
                    r = model.generate_content("قل: اختبار الاتصال بنجاح في سطر واحد فقط.")
                    txt = getattr(r, "text", "") or ""
                    if txt.strip():
                        return {
                            "used_key": redacted(key),
                            "used_model": m,
                            "response_preview": txt[:300]
                        }
                except Exception as e:
                    last_err = e
                    continue
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(f"فشل اختبار Gemini. آخر خطأ: {last_err}")

def check_gemini_list_models_if_possible():
    import google.generativeai as genai
    keys = _get_api_keys()
    if not keys:
        raise RuntimeError("لا توجد GOOGLE_API_KEYS داخل secrets")

    genai.configure(api_key=keys[0])
    # list_models قد لا تكون متاحة في بعض الإصدارات/الصلاحيات
    if not hasattr(genai, "list_models"):
        return {"supported": False, "note": "genai.list_models غير متاحة في هذا الإصدار"}
    models = []
    try:
        for m in genai.list_models():
            name = getattr(m, "name", "")
            models.append(name)
    except Exception as e:
        return {"supported": True, "error": str(e)}

    return {"supported": True, "models_count": len(models), "models_sample": models[:25]}


# ---------- واجهة التشخيص ----------
st.title("🧪 تشخيص شامل للتطبيق")
st.caption("الهدف: كشف أسباب الصفحة البيضاء + مشاكل الحزم + secrets + Drive + Gemini بدون ما نعرض أسرارك.")

col1, col2, col3 = st.columns(3)
with col1:
    run_all = st.button("تشغيل كل الاختبارات", type="primary", use_container_width=True)
with col2:
    run_drive = st.button("اختبارات Google Drive فقط", use_container_width=True)
with col3:
    run_gemini = st.button("اختبارات Gemini فقط", use_container_width=True)

st.text_input("اسم بحث تجريبي لملف PDF في Drive (اختياري)", value="Grade4_Ar", key="diag_search_name")

with st.expander("ملاحظة مهمة لو الصفحة البيضاء عندك في التطبيق الأساسي", expanded=True):
    st.write("""
- الصفحة البيضاء غالبًا تعني: **Exception حصل قبل رسم أي Widgets**.
- أشهر سببين: **Streamlit قديم** أو استخدام باراميتر غير مدعوم (مثل `vertical_alignment` في `st.columns` بإصدارات قديمة).
- شغّل التطبيق من Terminal أو افتح Logs على Streamlit Cloud عشان تشوف Traceback الحقيقي.
""")

results = []

if run_all or run_drive or run_gemini:
    # اختبارات عامة دائمًا
    results.append(run_check("BOOT / تشغيل الملف", check_boot))
    results.append(run_check("بيئة بايثون", check_python_env))
    results.append(run_check("مزايا Streamlit المتاحة (لتجنب الصفحة البيضاء)", check_streamlit_features))
    results.append(run_check("تعارض أسماء الملفات الشائع", check_common_conflicts))
    results.append(run_check("إصدارات الحزم المثبتة", check_installed_packages))
    results.append(run_check("شكل secrets (بدون كشف القيم)", check_secrets_shape))
    results.append(run_check("اختبار الاتصال بالإنترنت", check_network))
    results.append(run_check("اختبار Imports (Gemini/Drive)", check_imports_google))

    if run_all or run_drive:
        results.append(run_check("Drive: بناء الخدمة + قراءة محتويات الفولدر", check_drive_access_list_folder))
        results.append(run_check("Drive: البحث باسم ملف (contains)", check_drive_can_query_specific_name))

    if run_all or run_gemini:
        results.append(run_check("Gemini: اختبار generate_content بسيط", check_gemini_simple_generate))
        results.append(run_check("Gemini: محاولة list_models (إن أمكن)", check_gemini_list_models_if_possible))

    show_results(results)
else:
    st.info("اضغط زر من الأزرار بالأعلى لتشغيل التشخيص.")

st.divider()
st.subheader("تصدير تقرير التشخيص")
if results:
    report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "folder_id": FOLDER_ID,
        "results": results,
    }
    st.download_button(
        "تحميل التقرير JSON",
        data=json.dumps(report, ensure_ascii=False, indent=2),
        file_name="diagnostic_report.json",
        mime="application/json",
        use_container_width=True
    )
