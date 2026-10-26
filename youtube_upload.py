# -*- coding: utf-8 -*-
"""Dang video len YouTube qua YouTube Data API v3 (OAuth).
   - Can file client_secret.json (tao o Google Cloud Console).
   - Moi kenh dang nhap 1 lan -> token luu trong yt_tokens/<channel_id>.json.
"""
import os, json, glob, time

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


# Trang thai cua lan ket noi dang cho (start_connect): UI hoi qua connect_status()
_CONNECT = {"state": "idle", "url": "", "title": "", "error": ""}


def _save_token(creds):
    info = _channel_info(creds)
    if not info:
        raise RuntimeError("Không lấy được thông tin kênh")
    with open(os.path.join(TOKENS_DIR, info["id"] + ".json"), "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    # luu kem ten kenh de liet ke nhanh
    with open(os.path.join(TOKENS_DIR, info["id"] + ".name"), "w", encoding="utf-8") as f:
        f.write(info["title"])
    return info


def start_connect(timeout_seconds=600):
    """Bat dau OAuth nhung KHONG chan request: tra ve NGAY url dang nhap Google de tab
    cua nguoi dung tu chuyen sang. Viec cho Google goi lai localhost chay o luong nen.

    connect() cu goi flow.run_local_server() -> no tu goi webbrowser.open() TU PHIA
    SERVER va chan request cho toi khi dang nhap xong. Server chay nen ma mo trinh duyet
    that bai thi khong ai thay gi ca, tab cu quay mai. Tra url ve cho client thi khong
    con phu thuoc vao chuyen do nua.
    """
    if not is_configured():
        raise RuntimeError("Chưa có client_secret.json")
    import threading, wsgiref.simple_server
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google_auth_oauthlib.flow import _RedirectWSGIApp, _WSGIRequestHandler

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
    wsgi_app = _RedirectWSGIApp("✅ Đã cấp quyền. Đóng tab này và quay lại tool.")
    wsgiref.simple_server.WSGIServer.allow_reuse_address = False
    # port 0: cong trong bat ky -> khong dam nhau khi ket noi nhieu kenh lien tiep
    server = wsgiref.simple_server.make_server("localhost", 0, wsgi_app,
                                               handler_class=_WSGIRequestHandler)
    flow.redirect_uri = f"http://localhost:{server.server_port}/"
    auth_url, _ = flow.authorization_url(prompt="consent")
    _CONNECT.update(state="waiting", url=auth_url, title="", error="")

    def _wait():
        try:
            server.timeout = timeout_seconds
            server.handle_request()
            resp = getattr(wsgi_app, "last_request_uri", None)
            if not resp:
                raise RuntimeError(f"Quá {timeout_seconds}s chưa thấy Google trả lời "
                                   "— bấm kết nối lại.")
            flow.fetch_token(authorization_response=resp.replace("http", "https"))
            info = _save_token(flow.credentials)
            _CONNECT.update(state="done", title=info["title"], error="")
        except Exception as e:
            _CONNECT.update(state="error", error=str(e))
        finally:
            try:
                server.server_close()
            except Exception:
                pass

    threading.Thread(target=_wait, daemon=True).start()
    return auth_url


def connect_status():
    """{state: idle|waiting|done|error, url, title, error} cho UI hoi."""
    return dict(_CONNECT)


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
           category="27", publish_at=None):
    """Tai video len. tags: list hoac chuoi phan tach dau phay. Tra ve {id,url}.
    publish_at: neu co (ISO8601, vd '2026-07-10T07:00:00Z') -> hen gio dang;
    YouTube bat buoc privacyStatus=private, den gio se tu dong cong khai."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    creds = _creds_for(channel_id)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    status = {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}
    if publish_at:
        status["privacyStatus"] = "private"      # yeu cau cua YouTube khi hen gio
        status["publishAt"] = publish_at
    body = {
        "snippet": {"title": title[:100], "description": description[:5000],
                    "tags": tags, "categoryId": category},
        "status": status,
    }
    # Chia khuc 8MB: chunksize=-1 day ca file (vai tram MB) trong MOT request -> mang
    # chap chon 1 giay (SSLEOFError) la hong ca luot. Khuc nho + thu lai thi chi gui lai
    # dung khuc dang do (resumable upload tu noi tiep tu byte server da nhan).
    media = MediaFileUpload(video_path, chunksize=8 * 1024 * 1024, resumable=True,
                            mimetype="video/mp4")
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp, fails = None, 0
    while resp is None:
        try:
            _status, resp = req.next_chunk(num_retries=5)
            fails = 0
        except (OSError, ConnectionError, TimeoutError) as e:   # ssl.SSLError la OSError
            fails += 1
            if fails > 8:
                raise RuntimeError(f"Mạng rớt liên tục khi tải lên YouTube: {e}") from e
            print(f"[YT] ⚠ mat ket noi khi upload ({e}) -> thu lai lan {fails} sau {min(60, 2 ** fails)}s")
            time.sleep(min(60, 2 ** fails))
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


def set_title(channel_id, video_id, title):
    """Doi tieu de video da dang (giu nguyen mo ta/the/danh muc). Tra ve tieu de cu."""
    from googleapiclient.discovery import build
    creds = _creds_for(channel_id)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    items = yt.videos().list(part="snippet", id=video_id).execute().get("items") or []
    if not items:
        raise RuntimeError(f"Khong thay video {video_id} tren kenh")
    sn = items[0]["snippet"]
    cu = sn["title"]
    body = {"id": video_id, "snippet": {"title": title[:100], "description": sn.get("description", ""),
                                        "tags": sn.get("tags", []), "categoryId": sn["categoryId"]}}
    if sn.get("defaultLanguage"):
        body["snippet"]["defaultLanguage"] = sn["defaultLanguage"]
    yt.videos().update(part="snippet", body=body).execute()
    return cu
