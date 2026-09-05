# -*- coding: utf-8 -*-
"""AI sinh hinh anh video: intro/outro (Veo qua Gemini) + bg/thumbnail (OpenAI gpt-image-1).

- Intro/Outro  -> Veo (key Gemini). Prompt ghep tu 10 o input co cau truc.
- Bg + Thumbnail -> OpenAI Images (key OpenAI / ChatGPT).

Key doc tu file config (khong commit): gemini_config.json / openai_config.json,
hoac truyen thang tu request. Chua co key -> ham nem RuntimeError co thong bao ro.
"""
import os, json, time, base64, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.abspath(__file__))

# ---- Model mac dinh (doi duoc qua config) ----
VEO_MODEL      = "veo-3.1-fast-generate-preview"   # video-gen Gemini (fast: re+nhanh)
OPENAI_IMG_MODEL = "gpt-image-1-mini"              # anh OpenAI — RE NHAT ($8/1M token ra;
                                                   # gpt-image-1 cu la $40/1M, dat gap 5)
GEMINI_IMG_MODEL = "imagen-4.0-fast-generate-001"  # anh Gemini (fallback neu OpenAI ket)

# 10 o input theo thu tu hien thi tren web -> (khoa, nhan tieng Viet)
VEO_FIELDS = [
    ("subject",   "Chủ thể"),
    ("context",   "Bối cảnh"),
    ("action",    "Hành động"),
    ("camera",    "Góc máy"),
    ("lighting",  "Ánh sáng"),
    ("color",     "Màu sắc"),
    ("style",     "Phong cách"),
    ("emotion",   "Cảm xúc"),
    ("detail",    "Chi tiết"),
    ("aspect",    "Tỷ lệ khung hình"),
]

# ---------- KEY ----------
def load_key(kind, override=None):
    """kind = 'gemini' | 'openai'. Uu tien override (tu request) -> file config -> env."""
    if override and override.strip():
        return override.strip()
    path = os.path.join(ROOT, f"{kind}_config.json")
    if os.path.exists(path):
        try:
            d = json.load(open(path, encoding="utf-8"))
            k = d.get("api_key") or d.get("key") or d.get("apiKey")
            if k:
                return k.strip()
        except Exception:
            pass
    env = os.environ.get(f"{kind.upper()}_API_KEY") or os.environ.get(f"{kind.upper()}_KEY")
    if env:
        return env.strip()
    raise RuntimeError(
        f"Chua co key {kind}. Tao file {kind}_config.json (\"api_key\": \"...\") "
        f"hoac nhap key tren web.")

# ---------- VEO: ghep prompt tu 10 o input ----------
def build_veo_prompt(fields):
    """Ghep dict 10 o input thanh 1 cau prompt tieng Anh tu nhien cho Veo.
       O trong -> bo qua. 'aspect' KHONG vao cau chu (dua qua tham so aspectRatio)."""
    order = ["subject", "context", "action", "camera", "lighting",
             "color", "style", "emotion", "detail"]
    parts = []
    for k in order:
        v = (fields.get(k) or "").strip()
        if v:
            parts.append(v)
    return ", ".join(parts)

def _aspect_ratio(fields):
    a = (fields.get("aspect") or "").strip()
    if a in ("16:9", "9:16", "1:1"):
        return a
    # doan tu chu (vd 'ngang', 'doc')
    low = a.lower()
    if "9:16" in low or "doc" in low or "dọc" in low or "vertical" in low:
        return "9:16"
    return "16:9"

# ---------- VEO: goi API (async, phai poll) ----------
def gen_veo(fields, key=None, model=VEO_MODEL, poll_sec=10, timeout_sec=360, log=None):
    """Sinh 1 clip Veo tu 10 o input. Tra ve BYTES mp4.
       Veo chay bat dong bo: predictLongRunning -> lay operation -> poll toi khi done."""
    key = load_key("gemini", key)
    prompt = build_veo_prompt(fields)
    if not prompt:
        raise RuntimeError("Prompt Veo rong — nhap it nhat 'Chủ thể' va 'Hành động'.")
    aspect = _aspect_ratio(fields)
    _log = log or (lambda m: None)

    base = "https://generativelanguage.googleapis.com/v1beta"
    start_url = f"{base}/models/{model}:predictLongRunning?key={key}"
    body = json.dumps({
        "instances": [{"prompt": prompt}],
        "parameters": {"aspectRatio": aspect, "personGeneration": "allow_all"},
    }).encode()
    op = _post_json(start_url, body)
    op_name = op.get("name")
    if not op_name:
        raise RuntimeError(f"Veo khong tra ve operation: {str(op)[:300]}")
    _log(f"Veo dang render (op={op_name.split('/')[-1]})...")

    waited = 0
    while waited < timeout_sec:
        time.sleep(poll_sec)
        waited += poll_sec
        st = _get_json(f"{base}/{op_name}?key={key}")
        if st.get("done"):
            if "error" in st:
                raise RuntimeError(f"Veo loi: {str(st['error'])[:300]}")
            uri = _veo_video_uri(st)
            if not uri:
                raise RuntimeError(f"Veo done nhung khong co video uri: {str(st)[:300]}")
            sep = "&" if "?" in uri else "?"
            return _get_bytes(f"{uri}{sep}key={key}")
        _log(f"Veo... {waited}s")
    raise RuntimeError(f"Veo qua thoi gian ({timeout_sec}s).")

def _veo_video_uri(st):
    r = st.get("response", {})
    for path in (("generateVideoResponse", "generatedSamples"),
                 ("generatedVideos",), ("predictions",)):
        node = r
        for p in path:
            node = node.get(p, {}) if isinstance(node, dict) else {}
        if isinstance(node, list) and node:
            v = node[0]
            uri = (v.get("video", {}) or {}).get("uri") or v.get("uri") or v.get("videoUri")
            if uri:
                return uri
    return None

# ---------- OPENAI: bg + thumbnail ----------
def gen_openai_image(prompt, key=None, size="1536x1024", model=OPENAI_IMG_MODEL,
                     quality="medium"):
    """Sinh 1 anh tu prompt bang OpenAI Images. Tra ve BYTES png.
       size hop le gpt-image-1: 1024x1024 / 1536x1024 (ngang) / 1024x1536 (doc).
       quality: low | medium | high | auto (cang cao cang dep + dat)."""
    key = load_key("openai", key)
    if not (prompt or "").strip():
        raise RuntimeError("Prompt anh rong.")
    url = "https://api.openai.com/v1/images/generations"
    body = json.dumps({"model": model, "prompt": prompt, "size": size,
                       "quality": quality, "n": 1}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    })
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=120).read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:300]
        raise RuntimeError(f"OpenAI image loi {e.code}: {detail}")
    d = (resp.get("data") or [{}])[0]
    if d.get("b64_json"):
        return base64.b64decode(d["b64_json"])
    if d.get("url"):
        return _get_bytes(d["url"])
    raise RuntimeError(f"OpenAI khong tra ve anh: {str(resp)[:300]}")

# ---------- GEMINI IMAGE (imagen) — fallback khi OpenAI ket billing ----------
def gen_gemini_image(prompt, key=None, aspect="16:9", model=GEMINI_IMG_MODEL):
    """Sinh 1 anh bang Imagen (Gemini API). Tra ve BYTES png.
       aspect: '16:9' | '9:16' | '1:1' | '4:3' | '3:4'."""
    key = load_key("gemini", key)
    if not (prompt or "").strip():
        raise RuntimeError("Prompt anh rong.")
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:predict?key={key}")
    body = json.dumps({
        "instances": [{"prompt": prompt}],
        "parameters": {"sampleCount": 1, "aspectRatio": aspect},
    }).encode()
    resp = _post_json(url, body)
    preds = resp.get("predictions") or []
    if preds and preds[0].get("bytesBase64Encoded"):
        return base64.b64decode(preds[0]["bytesBase64Encoded"])
    raise RuntimeError(f"Imagen khong tra ve anh: {str(resp)[:300]}")

# ---------- HTTP helpers ----------
def _post_json(url, body):
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    return _open_json(req)

def _get_json(url):
    return _open_json(urllib.request.Request(url))

def _open_json(req):
    try:
        return json.loads(urllib.request.urlopen(req, timeout=60).read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:300]
        raise RuntimeError(f"API loi {e.code}: {detail}")

def _get_bytes(url):
    try:
        return urllib.request.urlopen(url, timeout=180).read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Tai file loi {e.code}: {e.reason}")

if __name__ == "__main__":
    # test nhanh phan KHONG can key: ghep prompt
    demo = {
        "subject": "a cute cartoon girl travel vlogger with backpack",
        "context": "standing before the Great Wall of China on green mountains",
        "action": "waving hello and smiling at the camera",
        "camera": "slow cinematic dolly-in, eye level",
        "lighting": "warm golden hour sunlight",
        "color": "vibrant warm palette",
        "style": "flat 2D illustration, anime-inspired",
        "emotion": "joyful, welcoming",
        "detail": "gentle wind in hair, soft clouds moving",
        "aspect": "16:9",
    }
    print("PROMPT:", build_veo_prompt(demo))
    print("ASPECT:", _aspect_ratio(demo))
