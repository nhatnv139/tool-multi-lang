# -*- coding: utf-8 -*-
"""Lan toa video sang mang xa hoi (organic marketing) theo tung kenh YouTube.

   Moi kenh YouTube (yt_channel_id) co RIENG mot bo kenh MXH:
   - social_tokens/<yt_channel_id>/index.json  : trang thai 4 nen tang (nguon su that cho UI)
   - social_tokens/<yt_channel_id>/<platform>.json : token rieng tung nen tang
   - social_secrets/<platform>.json            : app credentials dung chung (optional)

   Da chay that: Facebook (Page), TikTok (Content Posting API). X / Instagram = stub.
"""
import os, json, glob, time

ROOT = os.path.dirname(os.path.abspath(__file__))
SECRETS_DIR = os.path.join(ROOT, "social_secrets")
TOKENS_ROOT = os.path.join(ROOT, "social_tokens")
PLATFORMS = ("facebook", "x", "tiktok", "instagram")
GRAPH = "https://graph.facebook.com/v21.0"
os.makedirs(TOKENS_ROOT, exist_ok=True)
os.makedirs(SECRETS_DIR, exist_ok=True)


# ======================= helpers =======================
def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _chan_dir(cid):
    d = os.path.join(TOKENS_ROOT, cid)
    os.makedirs(d, exist_ok=True)
    return d


# ======================= index.json (mapping YT -> MXH) =======================
def _default_platform(p):
    # TikTok mac dinh tat: chua audit thi bi ep private, khong phuc vu organic public.
    return {"enabled": p != "tiktok", "connected": False, "name": "",
            "account_id": "", "mode": {"x": "link", "tiktok": "inbox"}.get(p, "native"),
            "content_style": "video_promo", "custom_prompt": ""}


def _index_path(cid):
    return os.path.join(_chan_dir(cid), "index.json")


def load_index(cid, yt_name="", lang="zh"):
    p = _index_path(cid)
    if os.path.exists(p):
        idx = json.load(open(p, encoding="utf-8"))
        # bo sung nen tang/field moi neu thieu (forward-compatible)
        for pl in PLATFORMS:
            cur = idx.setdefault("platforms", {}).setdefault(pl, _default_platform(pl))
            for k, v in _default_platform(pl).items():
                cur.setdefault(k, v)
        if yt_name and not idx.get("yt_channel_name"):
            idx["yt_channel_name"] = yt_name
            save_index(cid, idx)
        return idx
    idx = {"yt_channel_id": cid, "yt_channel_name": yt_name, "lang": lang,
           "updated_at": _now(),
           "platforms": {pl: _default_platform(pl) for pl in PLATFORMS}}
    save_index(cid, idx)
    return idx


def save_index(cid, idx):
    idx["updated_at"] = _now()
    _write(_index_path(cid), json.dumps(idx, ensure_ascii=False, indent=2))
    return idx


def set_enabled(cid, platform, enabled):
    idx = load_index(cid)
    idx["platforms"][platform]["enabled"] = bool(enabled)
    return save_index(cid, idx)


def set_mode(cid, platform, mode):
    idx = load_index(cid)
    if mode in ("native", "link", "direct", "inbox"):
        idx["platforms"][platform]["mode"] = mode
        save_index(cid, idx)
    return idx


def set_content(cid, platform, style=None, custom_prompt=None):
    """Dat 'kieu noi dung' (content profile) cho 1 nen tang cua kenh."""
    idx = load_index(cid)
    p = idx["platforms"][platform]
    if style is not None:
        p["content_style"] = style
    if custom_prompt is not None:
        p["custom_prompt"] = custom_prompt
    return save_index(cid, idx)


def public_links(cid, yt_name=""):
    """Trang thai cho UI: KHONG tra token, chi name/enabled/connected/warn."""
    idx = load_index(cid, yt_name=yt_name)
    out = {}
    for pl in PLATFORMS:
        st = idx["platforms"][pl]
        warn = ""
        if pl == "tiktok":
            sec = tt_secrets()
            if not sec.get("audited"):
                warn = ("App chưa qua audit → Direct Post bị ép 'Chỉ mình tôi'. "
                        "Chọn chế độ 'Gửi nháp vào app' để tự bấm Public trên điện thoại.")
        if pl == "instagram":
            warn = "Cần video public URL + IG Business. (giai đoạn sau)"
        out[pl] = {"enabled": st["enabled"], "connected": st["connected"],
                   "name": st["name"], "mode": st["mode"],
                   "content_style": st.get("content_style", "video_promo"),
                   "custom_prompt": st.get("custom_prompt", ""),
                   "configured": _is_configured(pl), "warn": warn}
    return {"yt_channel_id": cid, "yt_channel_name": idx.get("yt_channel_name", ""),
            "platforms": out}


def _is_configured(platform):
    if platform == "facebook":
        return True  # FB co the dung token dan tay, khong bat buoc app secret
    if platform == "tiktok":
        s = tt_secrets()
        return bool(s.get("client_key") and s.get("client_secret"))
    return False


def disconnect(cid, platform):
    idx = load_index(cid)
    tok = os.path.join(_chan_dir(cid), platform + ".json")
    if os.path.exists(tok):
        os.remove(tok)
    idx["platforms"][platform].update(connected=False, name="", account_id="")
    return save_index(cid, idx)


def set_connected(cid, platform, name, account_id):
    idx = load_index(cid)
    idx["platforms"][platform].update(connected=True, name=name, account_id=account_id)
    return save_index(cid, idx)


# ======================= FACEBOOK =======================
def fb_secrets():
    p = os.path.join(SECRETS_DIR, "facebook.json")
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    return {}


def fb_setup_hint():
    return ('Dán <b>User Access Token</b> lấy từ '
            '<a href="https://developers.facebook.com/tools/explorer/" target="_blank">Graph API Explorer</a> '
            'với quyền <code>pages_show_list</code>, <code>pages_manage_posts</code>, '
            '<code>pages_read_engagement</code>. '
            'Nếu đặt <code>social_secrets/facebook.json</code> {app_id, app_secret} thì token sẽ '
            'tự đổi sang loại không hết hạn.')


def _fb_token_path(cid):
    return os.path.join(_chan_dir(cid), "facebook.json")


def fb_list_pages(user_token):
    """Tu User Access Token -> doi sang long-lived (neu co app secret) -> liet ke Page
       kem page access token. Tra ve [{id, name, access_token}]."""
    import requests
    user_token = (user_token or "").strip()
    if not user_token:
        raise RuntimeError("Thiếu access token.")
    sec = fb_secrets()
    if sec.get("app_id") and sec.get("app_secret"):
        try:
            r = requests.get(f"{GRAPH}/oauth/access_token", params={
                "grant_type": "fb_exchange_token",
                "client_id": sec["app_id"], "client_secret": sec["app_secret"],
                "fb_exchange_token": user_token}, timeout=30)
            j = r.json()
            if j.get("access_token"):
                user_token = j["access_token"]   # long-lived user token
        except Exception:
            pass  # khong doi duoc -> dung token goc (van test duoc)
    r = requests.get(f"{GRAPH}/me/accounts",
                     params={"fields": "id,name,access_token", "access_token": user_token},
                     timeout=30)
    j = r.json()
    if "error" in j:
        raise RuntimeError("Facebook: " + j["error"].get("message", "lỗi không rõ"))
    pages = [{"id": p["id"], "name": p.get("name", p["id"]),
              "access_token": p.get("access_token", "")} for p in j.get("data", [])]
    if not pages:
        raise RuntimeError("Token này không quản lý Page nào. "
                           "Hãy dùng User token có quyền pages_show_list & chọn Page khi tạo token.")
    return pages


def fb_save_page(cid, page_id, page_name, page_token):
    _write(_fb_token_path(cid), json.dumps({
        "page_id": page_id, "page_name": page_name,
        "page_access_token": page_token, "saved_at": _now()},
        ensure_ascii=False, indent=2))
    idx = load_index(cid)
    idx["platforms"]["facebook"].update(connected=True, name=page_name, account_id=page_id)
    save_index(cid, idx)
    return {"page_id": page_id, "page_name": page_name}


def _fb_creds(cid):
    p = _fb_token_path(cid)
    if not os.path.exists(p):
        raise RuntimeError("Facebook chưa được kết nối cho kênh này.")
    return json.load(open(p, encoding="utf-8"))


def fb_post(cid, caption, media):
    """Dang len Facebook Page.
       media = {'kind':'native','video_path':...} | {'kind':'link','url':...}
       Tra ve {'ok':True,'post_url':...} hoac {'ok':False,'error':...,'permanent':bool,'hint':...}."""
    import requests
    tok = _fb_creds(cid)
    page_id, page_token = tok["page_id"], tok["page_access_token"]
    try:
        if media.get("kind") == "native" and media.get("video_path"):
            vp = media["video_path"]
            if not os.path.exists(vp):
                return {"ok": False, "error": "File video không tồn tại.", "permanent": True}
            with open(vp, "rb") as fh:
                r = requests.post(f"{GRAPH}/{page_id}/videos",
                                  data={"description": caption, "access_token": page_token},
                                  files={"source": fh}, timeout=600)
            j = r.json()
            if "error" in j:
                return _fb_err(j)
            vid = j.get("id", "")
            return {"ok": True, "post_url": f"https://www.facebook.com/watch/?v={vid}",
                    "id": vid, "kind": "native"}
        else:  # link
            url = media.get("url", "")
            r = requests.post(f"{GRAPH}/{page_id}/feed",
                              data={"message": caption, "link": url, "access_token": page_token},
                              timeout=60)
            j = r.json()
            if "error" in j:
                return _fb_err(j)
            pid = j.get("id", "")
            return {"ok": True, "post_url": f"https://www.facebook.com/{pid}",
                    "id": pid, "kind": "link"}
    except requests.exceptions.RequestException as e:
        return {"ok": False, "error": f"Lỗi mạng: {e}", "permanent": False}


def _fb_err(j):
    err = j.get("error", {})
    msg = err.get("message", "lỗi không rõ")
    code = err.get("code")
    # 190 = token hong/het han; 200/10/3 = thieu quyen -> permanent (khong retry)
    permanent = code in (190, 200, 10, 3, 100)
    hint = ""
    if code == 190:
        hint = "Token Page hết hạn — bấm Kết nối lại."
    elif code in (200, 10, 3):
        hint = "Thiếu quyền pages_manage_posts trên Page này."
    return {"ok": False, "error": f"Facebook: {msg}", "permanent": permanent, "hint": hint}


# ======================= TIKTOK =======================
TT_AUTH = "https://www.tiktok.com/v2/auth/authorize/"
TT_API = "https://open.tiktokapis.com/v2"
TT_SCOPES = "user.info.basic,video.upload,video.publish"
TT_MIN_CHUNK = 5 * 1024 * 1024
TT_CHUNK = 10 * 1024 * 1024


def tt_secrets():
    p = os.path.join(SECRETS_DIR, "tiktok.json")
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    return {}


def tt_redirect_uri():
    return tt_secrets().get("redirect_uri") or "http://localhost:5001/social/tiktok/callback"


def tt_auth_url(state, code_verifier):
    import hashlib
    from urllib.parse import urlencode
    sec = tt_secrets()
    challenge = hashlib.sha256(code_verifier.encode()).hexdigest()
    return TT_AUTH + "?" + urlencode({
        "client_key": sec["client_key"], "scope": TT_SCOPES, "response_type": "code",
        "redirect_uri": tt_redirect_uri(), "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256"})


def _tt_token_path(cid):
    return os.path.join(_chan_dir(cid), "tiktok.json")


def _tt_save_token(cid, j, extra=None):
    tok = {"access_token": j["access_token"], "refresh_token": j.get("refresh_token", ""),
           "open_id": j.get("open_id", ""), "scope": j.get("scope", ""),
           "expires_at": time.time() + int(j.get("expires_in", 86400)) - 120,
           "refresh_expires_at": time.time() + int(j.get("refresh_expires_in", 31536000)),
           "saved_at": _now()}
    if extra:
        tok.update(extra)
    _write(_tt_token_path(cid), json.dumps(tok, ensure_ascii=False, indent=2))
    return tok


def tt_exchange_code(cid, code, code_verifier):
    import requests
    sec = tt_secrets()
    r = requests.post(f"{TT_API}/oauth/token/", data={
        "client_key": sec["client_key"], "client_secret": sec["client_secret"],
        "code": code, "grant_type": "authorization_code",
        "redirect_uri": tt_redirect_uri(), "code_verifier": code_verifier},
        headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    j = r.json()
    if not j.get("access_token"):
        raise RuntimeError("TikTok: " + (j.get("error_description") or j.get("error") or str(j)))
    tok = _tt_save_token(cid, j)
    name = tok["open_id"]
    try:
        u = requests.get(f"{TT_API}/user/info/", params={"fields": "open_id,display_name"},
                         headers={"Authorization": "Bearer " + tok["access_token"]}, timeout=30).json()
        name = u.get("data", {}).get("user", {}).get("display_name") or name
    except Exception:
        pass
    tok["display_name"] = name
    _write(_tt_token_path(cid), json.dumps(tok, ensure_ascii=False, indent=2))
    set_connected(cid, "tiktok", name, tok["open_id"])
    return {"name": name, "open_id": tok["open_id"]}


def _tt_creds(cid):
    import requests
    p = _tt_token_path(cid)
    if not os.path.exists(p):
        raise RuntimeError("TikTok chưa được kết nối cho kênh này.")
    tok = json.load(open(p, encoding="utf-8"))
    if time.time() < tok.get("expires_at", 0):
        return tok
    sec = tt_secrets()
    r = requests.post(f"{TT_API}/oauth/token/", data={
        "client_key": sec["client_key"], "client_secret": sec["client_secret"],
        "grant_type": "refresh_token", "refresh_token": tok["refresh_token"]},
        headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    j = r.json()
    if not j.get("access_token"):
        raise RuntimeError("TikTok: refresh token hết hạn — bấm Kết nối lại.")
    return _tt_save_token(cid, j, {"display_name": tok.get("display_name", "")})


def _tt_chunks(size):
    if size <= TT_MIN_CHUNK:
        return size, 1
    n = max(1, size // TT_CHUNK)
    return TT_CHUNK, n


def tt_post(cid, caption, media, poll_timeout=600):
    import requests
    vp = media.get("video_path")
    if not vp or not os.path.exists(vp):
        return {"ok": False, "permanent": True,
                "error": "TikTok chỉ nhận file video (không đăng link YouTube được)."}
    try:
        tok = _tt_creds(cid)
    except RuntimeError as e:
        return {"ok": False, "permanent": True, "error": str(e)}
    H = {"Authorization": "Bearer " + tok["access_token"],
         "Content-Type": "application/json; charset=UTF-8"}
    size = os.path.getsize(vp)
    chunk, count = _tt_chunks(size)
    source = {"source": "FILE_UPLOAD", "video_size": size,
              "chunk_size": chunk, "total_chunk_count": count}
    inbox = media.get("tt_mode", "inbox") == "inbox"
    try:
        if inbox:
            r = requests.post(f"{TT_API}/post/publish/inbox/video/init/", headers=H,
                              json={"source_info": source}, timeout=60)
        else:
            ci = requests.post(f"{TT_API}/post/publish/creator_info/query/", headers=H,
                               timeout=30).json()
            if ci.get("error", {}).get("code") not in (None, "ok"):
                return _tt_err(ci)
            opts = ci.get("data", {}).get("privacy_level_options") or ["SELF_ONLY"]
            want = "PUBLIC_TO_EVERYONE" if tt_secrets().get("audited") else "SELF_ONLY"
            privacy = want if want in opts else opts[-1]
            r = requests.post(f"{TT_API}/post/publish/video/init/", headers=H, json={
                "post_info": {"title": caption[:2200], "privacy_level": privacy,
                              "disable_comment": False, "disable_duet": False,
                              "disable_stitch": False},
                "source_info": source}, timeout=60)
        j = r.json()
        if j.get("error", {}).get("code") not in (None, "ok"):
            return _tt_err(j)
        upload_url = j["data"]["upload_url"]
        publish_id = j["data"]["publish_id"]
        with open(vp, "rb") as fh:
            for i in range(count):
                start = i * chunk
                end = size - 1 if i == count - 1 else start + chunk - 1
                fh.seek(start)
                body = fh.read(end - start + 1)
                pr = requests.put(upload_url, data=body, timeout=600, headers={
                    "Content-Type": "video/mp4", "Content-Length": str(len(body)),
                    "Content-Range": f"bytes {start}-{end}/{size}"})
                if pr.status_code not in (200, 201, 206):
                    return {"ok": False, "permanent": False,
                            "error": f"TikTok upload chunk {i+1}/{count} lỗi HTTP {pr.status_code}"}
        deadline = time.time() + poll_timeout
        status = ""
        while time.time() < deadline:
            s = requests.post(f"{TT_API}/post/publish/status/fetch/", headers=H,
                              json={"publish_id": publish_id}, timeout=30).json()
            d = s.get("data", {})
            status = d.get("status", "")
            if status == "FAILED":
                return {"ok": False, "permanent": False,
                        "error": "TikTok xử lý video thất bại: " + d.get("fail_reason", "")}
            if status in ("SEND_TO_USER_INBOX", "PUBLISH_COMPLETE"):
                break
            time.sleep(5)
        if inbox:
            return {"ok": True, "kind": "inbox", "id": publish_id, "post_url": "",
                    "note": "Đã gửi nháp vào hộp thư TikTok — mở app để bấm Đăng."}
        ids = d.get("publicaly_available_post_id") or []
        url = (f"https://www.tiktok.com/@{tok.get('display_name','')}/video/{ids[0]}"
               if ids else "")
        return {"ok": True, "kind": "direct", "id": publish_id, "post_url": url,
                "note": "" if status == "PUBLISH_COMPLETE" else f"Trạng thái: {status or 'đang xử lý'}"}
    except requests.exceptions.RequestException as e:
        return {"ok": False, "error": f"Lỗi mạng: {e}", "permanent": False}


def _tt_err(j):
    err = j.get("error", {})
    code = err.get("code", "")
    hint = ""
    if code in ("access_token_invalid", "scope_not_authorized"):
        hint = "Token/quyền TikTok không hợp lệ — bấm Kết nối lại."
    elif code == "unaudited_client_can_only_post_to_private_accounts":
        hint = "App chưa audit: tài khoản TikTok phải để Riêng tư, hoặc dùng chế độ 'Gửi nháp'."
    elif code == "spam_risk_too_many_posts":
        hint = "Đăng quá nhiều trong 24h — thử lại sau."
    return {"ok": False, "permanent": code != "rate_limit_exceeded",
            "error": f"TikTok: {err.get('message') or code}", "hint": hint}


# ======================= dispatch (orchestration mini) =======================
def post_to(cid, platform, caption, media):
    if platform == "facebook":
        return fb_post(cid, caption, media)
    if platform == "tiktok":
        idx = load_index(cid)
        m = dict(media)
        m["tt_mode"] = "direct" if idx["platforms"]["tiktok"].get("mode") == "direct" else "inbox"
        return tt_post(cid, caption, m)
    return {"ok": False, "permanent": True,
            "error": f"{platform}: chưa hỗ trợ (giai đoạn sau).",
            "hint": "Hiện chỉ Facebook và TikTok đã sẵn sàng."}
