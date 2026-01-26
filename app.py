import time

if "debug_log" not in st.session_state:
    st.session_state.debug_log = []
if "debug_enabled" not in st.session_state:
    st.session_state.debug_enabled = True

def dbg(event, data=None):
    if not st.session_state.debug_enabled:
        return
    rec = {"t": time.strftime("%H:%M:%S"), "event": event}
    if data is not None:
        rec["data"] = data
    st.session_state.debug_log.append(rec)
    st.session_state.debug_log = st.session_state.debug_log[-400:]
    from google.oauth2 import service_account

@st.cache_resource
def get_credentials():
    if "gcp_service_account" not in st.secrets:
        return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        return service_account.Credentials.from_service_account_info(creds_dict, scopes=scopes)
    except Exception as e:
        dbg("creds_error", str(e))
        return None
       import os
import tempfile
import pdfplumber
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

def load_book_smartly(stage, grade, lang):
    creds = get_credentials()
    if not creds:
        return None

    try:
        target_tokens = []

        # مرحلة + صف
        if "الثانوية" in stage:
            if "الأول" in grade:
                target_tokens.append("Sec1")
            elif "الثاني" in grade:
                target_tokens.append("Sec2")
            elif "الثالث" in grade:
                target_tokens.append("Sec3")

        elif "الإعدادية" in stage:
            if "الأول" in grade:
                target_tokens.append("Prep1")
            elif "الثاني" in grade:
                target_tokens.append("Prep2")
            elif "الثالث" in grade:
                target_tokens.append("Prep3")

        else:  # ابتدائي
            if "الرابع" in grade:
                target_tokens.append("Grade4")
            elif "الخامس" in grade:
                target_tokens.append("Grade5")
            elif "السادس" in grade:
                target_tokens.append("Grade6")

        # لغة
        lang_code = "Ar" if "العربية" in lang else "En"
        target_tokens.append(lang_code)

        service = build("drive", "v3", credentials=creds)
        query = f"'{FOLDER_ID}' in parents and mimeType='application/pdf'"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        all_files = results.get("files", [])

        matched_file = None
        for f in all_files:
            name = f.get("name", "")
            if all(tok.lower() in name.lower() for tok in target_tokens):
                matched_file = f
                break

        if not matched_file:
            dbg("book_not_found", {"tokens": target_tokens, "files": [x.get("name") for x in all_files]})
            return None

        request = service.files().get_media(fileId=matched_file["id"])
        file_path = os.path.join(tempfile.gettempdir(), matched_file["name"])

        with open(file_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()

        dbg("book_downloaded", {"name": matched_file["name"], "path": file_path, "size": os.path.getsize(file_path)})

        # استخراج نص (قد يكون 0 لو سكان)
        text_content = ""
        try:
            with pdfplumber.open(file_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    if i > 25:
                        break
                    extracted = page.extract_text()
                    if extracted:
                        text_content += extracted + "\n"
        except Exception as e:
            dbg("pdf_extract_error", str(e))

        dbg("book_text_stats", {"chars": len(text_content)})
        return {"path": file_path, "text": text_content, "name": matched_file["name"]}

    except Exception as e:
        dbg("load_book_error", {"err": str(e)})
        return None
def load_book_smartly(...):
    creds = ...
    if not creds: return None
    try:
        target_tokens = []
    lang_code = "Ar" if "العربية" in lang else "En"   # <-- خارج الـ try بالغلط
