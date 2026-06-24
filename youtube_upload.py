# -*- coding: utf-8 -*-
"""Dang video len YouTube qua YouTube Data API v3 (OAuth).
   - Can file client_secret.json (tao o Google Cloud Console).
   - Moi kenh dang nhap 1 lan -> token luu trong yt_tokens/<channel_id>.json.
"""
import os, json, glob

ROOT = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRET = os.path.join(ROOT, "client_secret.json")
TOKENS_DIR = os.path.join(ROOT, "yt_tokens")
os.makedirs(TOKENS_DIR, exist_ok=True)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.force-ssl",   # de upload phu de (captions)
          "https://www.googleapis.com/auth/youtube.readonly"]
OAUTH_PORT = 8765


def is_configured():
    """Da co client_secret.json chua?"""
    return os.path.exists(CLIENT_SECRET)


def setup_hint():
    return ('Đặt file <code>client_secret.json</code> (Google Cloud → YouTube Data API v3 '
            '→ OAuth Client, loại "Desktop app") vào thư mục tool, rồi bấm "Kết nối kênh mới".')


# ---------- OAuth ----------
def _channel_info(creds):
    from googleapiclient.discovery import build
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    r = yt.channels().list(part="snippet", mine=True).execute()
    items = r.get("items", [])
    if not items:
        return None
    it = items[0]
    return {"id": it["id"], "title": it["snippet"]["title"]}


def connect():
    """Mo trinh duyet dang nhap Google, luu token theo channel_id. Tra ve {id,title}."""
    if not is_configured():
        raise RuntimeError("Chưa có client_secret.json")
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
    # port=0: tu chon cong trong moi lan -> khong bi "address already in use"
    creds = flow.run_local_server(port=0, prompt="consent",
                                  authorization_prompt_message="")
    info = _channel_info(creds)
    if not info:
        raise RuntimeError("Không lấy được thông tin kênh")
    with open(os.path.join(TOKENS_DIR, info["id"] + ".json"), "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    # luu kem ten kenh de liet ke nhanh
    with open(os.path.join(TOKENS_DIR, info["id"] + ".name"), "w", encoding="utf-8") as f:
        f.write(info["title"])
    return info


def list_channels():
    """Danh sach kenh da ket noi (tu token da luu)."""
    out = []
    for tok in glob.glob(os.path.join(TOKENS_DIR, "*.json")):
        cid = os.path.splitext(os.path.basename(tok))[0]
        name_file = os.path.join(TOKENS_DIR, cid + ".name")
        title = open(name_file, encoding="utf-8").read().strip() if os.path.exists(name_file) else cid
        out.append({"id": cid, "title": title})
    return out


def _creds_for(channel_id):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    tok = os.path.join(TOKENS_DIR, channel_id + ".json")
    if not os.path.exists(tok):
        raise RuntimeError("Kênh chưa được kết nối")
    creds = Credentials.from_authorized_user_file(tok, SCOPES)
    if not creds.valid and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(tok, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    return creds


# ---------- Upload ----------
def upload(channel_id, video_path, title, description, tags, privacy="public",
           category="27"):
    """Tai video len. tags: list hoac chuoi phan tach dau phay. Tra ve {id,url}."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    creds = _creds_for(channel_id)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    body = {
        "snippet": {"title": title[:100], "description": description[:5000],
                    "tags": tags, "categoryId": category},
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True,
                            mimetype="video/mp4")
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        _status, resp = req.next_chunk()
    vid = resp["id"]
    return {"id": vid, "url": f"https://youtu.be/{vid}"}


def upload_caption(channel_id, video_id, srt_text, lang, name=""):
    """Upload 1 track phu de (.srt) cho video. lang: 'zh-Hans'|'zh-Latn'|'vi'."""
    import io
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
    if not (srt_text or "").strip():
        return None
    creds = _creds_for(channel_id)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    body = {"snippet": {"videoId": video_id, "language": lang,
                        "name": name or lang, "isDraft": False}}
    media = MediaIoBaseUpload(io.BytesIO(srt_text.encode("utf-8")),
                              mimetype="application/octet-stream", resumable=False)
    r = yt.captions().insert(part="snippet", body=body, media_body=media).execute()
    return r.get("id")


def post_comment(channel_id, video_id, text):
    """Dang 1 comment (top-level) len video. Luu y: API KHONG cho ghim tu dong."""
    from googleapiclient.discovery import build
    if not (text or "").strip():
        return None
    creds = _creds_for(channel_id)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    body = {"snippet": {"videoId": video_id,
                        "topLevelComment": {"snippet": {"textOriginal": text}}}}
    r = yt.commentThreads().insert(part="snippet", body=body).execute()
    return r.get("id")


def set_thumbnail(channel_id, video_id, image_path):
    """Dat anh bia (thumbnail) cho video. Can kenh da bat 'custom thumbnail' (xac minh SDT)."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    if not os.path.exists(image_path):
        return None
    creds = _creds_for(channel_id)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    yt.thumbnails().set(videoId=video_id,
                        media_body=MediaFileUpload(image_path, mimetype="image/jpeg")).execute()
    return True
