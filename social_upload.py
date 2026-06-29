# -*- coding: utf-8 -*-
"""Lan toa video sang mang xa hoi (organic marketing) theo tung kenh YouTube.

   Moi kenh YouTube (yt_channel_id) co RIENG mot bo kenh MXH:
   - social_tokens/<yt_channel_id>/index.json  : trang thai 4 nen tang (nguon su that cho UI)
   - social_tokens/<yt_channel_id>/<platform>.json : token rieng tung nen tang
   - social_secrets/<platform>.json            : app credentials dung chung (optional)

   Giai doan 1: chi Facebook (Page) duoc cai dat that. X / TikTok / Instagram = stub.
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
            "account_id": "", "mode": "link" if p == "x" else "native",
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
    if mode in ("native", "link"):
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
            warn = "Chưa duyệt app → chỉ đăng được private. Bật public sau khi qua audit."
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
    return False     # x / tiktok / instagram: giai doan sau


def disconnect(cid, platform):
    idx = load_index(cid)
    tok = os.path.join(_chan_dir(cid), platform + ".json")
    if os.path.exists(tok):
        os.remove(tok)
    idx["platforms"][platform].update(connected=False, name="", account_id="")
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


# ======================= dispatch (orchestration mini) =======================
def post_to(cid, platform, caption, media):
    """Dispatch theo nen tang. Giai doan 1: chi facebook that."""
    if platform == "facebook":
        return fb_post(cid, caption, media)
    return {"ok": False, "permanent": True,
            "error": f"{platform}: chưa hỗ trợ (giai đoạn sau).",
            "hint": "Hiện chỉ Facebook đã sẵn sàng."}
