# -*- coding: utf-8 -*-
"""App web tao video hoc tieng Trung.
Chay:  python app.py   ->  mo http://127.0.0.1:5001
Ban chi can: dien NOI DUNG + chon GIONG DOC -> bam Tao video. Con lai tu dong.
"""
import os, sys, threading, time, traceback, re, json
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from flask import Flask, request, jsonify, send_from_directory, render_template
import generate, lesson_parser, seo

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "output")
app = Flask(__name__)

jobs = {}
JOBS_DB = os.path.join(OUT, "jobs.json")    # persist metadata job 'done' ra disk

def _save_job(job_id):
    """Ghi metadata cua MOT job done vao jobs.json (doc-merge-ghi). Nuot loi IO."""
    try:
        j = jobs.get(job_id) or {}
        if j.get("status") != "done":
            return                          # chi persist job done, bo qua running/error
        data = {}
        try:
            with open(JOBS_DB, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        except Exception:
            data = {}
        data[job_id] = {"video": j.get("video"), "thumb": j.get("thumb"),
                        "seo": j.get("seo"), "status": "done"}
        os.makedirs(OUT, exist_ok=True)
        with open(JOBS_DB, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        traceback.print_exc()

# Nap lai cac job done con file video tren disk (sau restart)
try:
    with open(JOBS_DB, "r", encoding="utf-8") as f:
        _saved = json.load(f) or {}
    for _jid, _v in _saved.items():
        try:
            if _v.get("video") and os.path.exists(os.path.join(OUT, _v["video"])):
                jobs[_jid] = _v
        except Exception:
            pass
except Exception:
    pass

_build_lock = threading.Lock()      # render tuan tu (ffmpeg nang)

# Giong edge-tts (mien phi, khong can key) — value tien to "edge:"
EDGE_VOICES = [
    ("edge:zh-CN-XiaoxiaoNeural", "Hiểu Hiểu — Nữ, ấm, kể chuyện ⭐ (free)"),
    ("edge:zh-CN-YunjianNeural",  "Vân Kiện — Nam, kể chuyện biểu cảm ⭐ (free)"),
    ("edge:zh-CN-XiaoyiNeural",   "Hiểu Y — Nữ, trẻ (free)"),
    ("edge:zh-CN-YunxiNeural",    "Vân Hi — Nam, trẻ (free)"),
    ("edge:zh-CN-YunyangNeural",  "Vân Dương — Nam, tin tức (free)"),
    ("edge:zh-CN-YunxiaNeural",   "Vân Hạ — Nam, dễ thương (free)"),
    ("edge:zh-CN-liaoning-XiaobeiNeural", "Hiểu Bối — Nữ, giọng Đông Bắc (free)"),
    ("edge:zh-CN-shaanxi-XiaoniNeural",   "Hiểu Ni — Nữ, giọng Thiểm Tây (free)"),
    # Quan Thoai Dai Loan (zh-TW) — van la tieng pho thong chuan, chi khac am dieu vung mien
    ("edge:zh-TW-HsiaoChenNeural", "Hiểu Trăn — Nữ, giọng Đài Loan (free)"),
    ("edge:zh-TW-HsiaoYuNeural",   "Hiểu Du — Nữ, giọng Đài Loan, nhẹ (free)"),
    ("edge:zh-TW-YunJheNeural",    "Vân Triết — Nam, giọng Đài Loan (free)"),
]
# Giong da ngu Microsoft (free, khong can key) — chat luong cao, doc duoc tieng Trung
# Luu y: phat am co the hoi "la" (am dieu khong phai nguoi ban xu) -> hay cho loi dan, can nhac cho phat am chuan.
EDGE_ML_VOICES = [
    ("edge:en-US-AvaMultilingualNeural",    "Ava — Nữ, biểu cảm, rất tự nhiên 🌐 (free)"),
    ("edge:en-US-AndrewMultilingualNeural", "Andrew — Nam, ấm, tự tin 🌐 (free)"),
    ("edge:en-US-EmmaMultilingualNeural",   "Emma — Nữ, vui tươi, rõ ràng 🌐 (free)"),
    ("edge:en-US-BrianMultilingualNeural",  "Brian — Nam, gần gũi, tự nhiên 🌐 (free)"),
    ("edge:de-DE-SeraphinaMultilingualNeural", "Seraphina — Nữ, nhẹ nhàng 🌐 (free)"),
    ("edge:fr-FR-VivienneMultilingualNeural",  "Vivienne — Nữ, êm 🌐 (free)"),
]

# Giong Azure (tu nhien hon, can key free) — value tien to "azure:"
AZURE_VOICES = [
    # --- HD / siêu thật (mới nhất) ---
    ("azure:zh-CN-Xiaochen:DragonHDLatestNeural", "Hiểu Trần HD — Nữ, siêu thật ⭐ (mới nhất)"),
    ("azure:zh-CN-Yunfan:DragonHDLatestNeural",   "Vân Phàm HD — Nam, siêu thật ⭐"),
    ("azure:zh-CN-Xiaoxiao:DragonHDFlashLatestNeural", "Hiểu Hiểu HD Flash — Nữ, siêu thật"),
    ("azure:zh-CN-Xiaochen:DragonHDFlashLatestNeural", "Hiểu Trần HD Flash — Nữ, nhanh"),
    # --- Đa ngữ (đọc tốt cả Trung + Việt + Anh) ---
    ("azure:zh-CN-XiaoxiaoMultilingualNeural", "Hiểu Hiểu Đa ngữ — Nữ, rất tự nhiên ⭐"),
    ("azure:zh-CN-XiaochenMultilingualNeural", "Hiểu Trần Đa ngữ — Nữ trẻ, tự nhiên"),
    ("azure:zh-CN-XiaoyuMultilingualNeural",   "Hiểu Vũ Đa ngữ — Nữ, ấm"),
    ("azure:zh-CN-YunyiMultilingualNeural",    "Vân Nghị Đa ngữ — Nam, tự nhiên"),
    # --- Nữ (giọng phổ thông biểu cảm) ---
    ("azure:zh-CN-XiaoxiaoNeural", "Hiểu Hiểu — Nữ, ấm, kể chuyện"),
    ("azure:zh-CN-XiaoyiNeural",   "Hiểu Y — Nữ, trẻ, hoạt náo"),
    ("azure:zh-CN-XiaohanNeural",  "Hiểu Hàm — Nữ, dịu dàng"),
    ("azure:zh-CN-XiaomengNeural", "Hiểu Mộng — Nữ, tươi vui"),
    ("azure:zh-CN-XiaomoNeural",   "Hiểu Mặc — Nữ, đa cảm xúc"),
    ("azure:zh-CN-XiaoruiNeural",  "Hiểu Duệ — Nữ, lớn tuổi, điềm đạm"),
    ("azure:zh-CN-XiaoxuanNeural", "Hiểu Tuyên — Nữ, chững chạc"),
    ("azure:zh-CN-XiaoyanNeural",  "Hiểu Yến — Nữ, dịch vụ KH"),
    ("azure:zh-CN-XiaozhenNeural", "Hiểu Trinh — Nữ, nghiêm túc"),
    ("azure:zh-CN-XiaoshuangNeural", "Hiểu Sảng — Bé gái, dễ thương"),
    # --- Nam ---
    ("azure:zh-CN-YunxiNeural",    "Vân Hi — Nam, trẻ, nắng ấm"),
    ("azure:zh-CN-YunjianNeural",  "Vân Kiện — Nam, kể chuyện biểu cảm"),
    ("azure:zh-CN-YunyangNeural",  "Vân Dương — Nam, tin tức chuyên nghiệp"),
    ("azure:zh-CN-YunxiaNeural",   "Vân Hạ — Nam, dễ thương"),
    ("azure:zh-CN-YunfengNeural",  "Vân Phong — Nam, sôi nổi"),
    ("azure:zh-CN-YunhaoNeural",   "Vân Hạo — Nam, quảng cáo"),
    ("azure:zh-CN-YunyeNeural",    "Vân Diệp — Nam, lớn tuổi, kể chuyện"),
    ("azure:zh-CN-YunzeNeural",    "Vân Trạch — Nam, lớn tuổi, điềm tĩnh"),
    # --- Giọng vùng miền (tiếng phổ thông + chất địa phương) ---
    ("azure:zh-CN-sichuan-YunxiNeural",   "Vân Hi — Nam, giọng Tứ Xuyên"),
    ("azure:zh-CN-henan-YundengNeural",   "Vân Đăng — Nam, giọng Hà Nam"),
    ("azure:zh-CN-shandong-YunxiangNeural", "Vân Tường — Nam, giọng Sơn Đông"),
    ("azure:zh-CN-liaoning-XiaobeiNeural", "Hiểu Bối — Nữ, giọng Đông Bắc"),
    ("azure:zh-CN-shaanxi-XiaoniNeural",   "Hiểu Ni — Nữ, giọng Thiểm Tây"),
    # --- Quan Thoại Đài Loan ---
    ("azure:zh-TW-HsiaoChenNeural", "Hiểu Trăn — Nữ, Đài Loan"),
    ("azure:zh-TW-HsiaoYuNeural",   "Hiểu Du — Nữ, Đài Loan, nhẹ"),
    ("azure:zh-TW-YunJheNeural",    "Vân Triết — Nam, Đài Loan"),
]

# Giong ElevenLabs (TRA PHI, chat luong cao nhat) — value tien to "eleven:<voice_id>"
# Day la cac giong mac dinh cua ElevenLabs (model eleven_multilingual_v2 noi duoc tieng Trung + Viet).
ELEVEN_VOICES = [
    ("eleven:21m00Tcm4TlvDq8ikWAM", "Rachel — Nữ, ấm, kể chuyện ⭐ (ElevenLabs)"),
    ("eleven:EXAVITQu4vr4xnSDxMaL", "Sarah — Nữ, nhẹ nhàng (ElevenLabs)"),
    ("eleven:9BWtsMINqrJLrRacOk9x", "Aria — Nữ, biểu cảm (ElevenLabs)"),
    ("eleven:pNInz6obpgDQGcFmaJgB", "Adam — Nam, trầm ấm (ElevenLabs)"),
    ("eleven:ErXwobaYiN019PkySvjV", "Antoni — Nam, trẻ (ElevenLabs)"),
]

# Giong ChatTTS chay local (mien phi, khong can key)
CHATTTS_VOICES = [
    ("chattts:local", "ChatTTS (local) — tự nhiên, free, không cần key 🔥"),
]
CHATTTS_STYLES = [
    ("warm",  "Truyền cảm (mặc định) ⭐"),
    ("clear", "Rõ ràng / ổn định"),
    ("story", "Kể chuyện - nhiều cảm xúc"),
]

# Giong Google Gemini TTS (AI Studio "Generate speech") — value tien to "gemini:<voiceName>"
# Da ngu: 1 giong doc duoc ca tieng Trung + tieng Viet. Can Gemini API key (free).
GEMINI_VOICES = [
    ("gemini:Kore",       "Kore — Nữ, chắc chắn, ấm ⭐ (Gemini)"),
    ("gemini:Aoede",      "Aoede — Nữ, nhẹ nhàng, dễ nghe ⭐ (Gemini)"),
    ("gemini:Leda",       "Leda — Nữ, trẻ trung (Gemini)"),
    ("gemini:Zephyr",     "Zephyr — Nữ, tươi sáng (Gemini)"),
    ("gemini:Callirrhoe", "Callirrhoe — Nữ, thoải mái (Gemini)"),
    ("gemini:Autonoe",    "Autonoe — Nữ, sáng (Gemini)"),
    ("gemini:Despina",    "Despina — Nữ, mượt (Gemini)"),
    ("gemini:Vindemiatrix","Vindemiatrix — Nữ, dịu dàng (Gemini)"),
    ("gemini:Sulafat",    "Sulafat — Nữ, ấm (Gemini)"),
    ("gemini:Puck",       "Puck — Nam, lạc quan, vui (Gemini)"),
    ("gemini:Charon",     "Charon — Nam, cung cấp thông tin (Gemini)"),
    ("gemini:Fenrir",     "Fenrir — Nam, hoạt náo (Gemini)"),
    ("gemini:Orus",       "Orus — Nam, chắc chắn (Gemini)"),
    ("gemini:Iapetus",    "Iapetus — Nam, rõ ràng (Gemini)"),
    ("gemini:Enceladus",  "Enceladus — Nam, thì thầm nhẹ (Gemini)"),
    ("gemini:Algenib",    "Algenib — Nam, trầm (Gemini)"),
    ("gemini:Rasalgethi", "Rasalgethi — Nam, nhiều thông tin (Gemini)"),
    ("gemini:Achird",     "Achird — Nam, thân thiện (Gemini)"),
]

AZURE_CFG = os.path.join(ROOT, "azure_config.json")
def load_azure():
    try:
        import json as _j
        d = _j.load(open(AZURE_CFG, encoding="utf-8"))
        return d.get("key", ""), d.get("region", "")
    except Exception:
        return "", ""
def save_azure(key, region):
    import json as _j
    _j.dump({"key": key, "region": region}, open(AZURE_CFG, "w", encoding="utf-8"))

BG_CFG = os.path.join(ROOT, "bg_config.json")
def load_bg():
    try:
        import json as _j
        p = _j.load(open(BG_CFG, encoding="utf-8")).get("path", "")
        return p if (p and os.path.exists(p)) else ""
    except Exception:
        return ""
def save_bg(path):
    import json as _j
    _j.dump({"path": path}, open(BG_CFG, "w", encoding="utf-8"))

ELEVEN_CFG = os.path.join(ROOT, "eleven_config.json")
def load_eleven():
    try:
        import json as _j
        return _j.load(open(ELEVEN_CFG, encoding="utf-8")).get("key", "")
    except Exception:
        return ""
def save_eleven(key):
    import json as _j
    _j.dump({"key": key}, open(ELEVEN_CFG, "w", encoding="utf-8"))

GEMINI_CFG = os.path.join(ROOT, "gemini_config.json")
def load_gemini():
    try:
        import json as _j
        return _j.load(open(GEMINI_CFG, encoding="utf-8")).get("key", "")
    except Exception:
        return ""
def save_gemini(key):
    import json as _j
    _j.dump({"key": key}, open(GEMINI_CFG, "w", encoding="utf-8"))
RATES = [("-20%", "Chậm (người mới)"), ("-10%", "Hơi chậm"),
         ("-8%", "Vừa (khuyên)"), ("+0%", "Bình thường")]
THEMES = [("pink", "Hồng pastel"), ("mint", "Xanh mint"), ("sky", "Xanh da trời"),
          ("cream", "Kem"), ("lavender", "Tím nhạt"),
          ("none", "Không phủ màu (giữ nguyên ảnh nền)")]
MOODS = [("calm", "Piano nhẹ nhàng / thư giãn"), ("hope", "Piano hy vọng / tích cực"),
         ("happy", "Piano vui tươi"), ("sad", "Piano trầm buồn"),
         ("box", "Hộp nhạc (music box) trong trẻo"), ("deep", "Trầm sâu lắng")]

UP = os.path.join(ROOT, "uploads")
os.makedirs(UP, exist_ok=True)
MASCOTS = [("", "Tự đổi theo bài"), ("🐼", "Gấu trúc"), ("🐱", "Mèo"),
           ("🐰", "Thỏ"), ("🐻", "Gấu"), ("🦊", "Cáo"), ("🐧", "Chim cánh cụt"),
           ("none", "Không mascot")]

def slugify(s):
    # bo ky tu dac biet (—, ", :, ...) — giu chu/so (ke ca Han), khoang trang -> gach duoi.
    # tranh em-dash trong ten file -> hong URL anh bia.
    s = re.sub(r"[^\w\s-]", "", s or "", flags=re.UNICODE)
    s = re.sub(r"[\s_]+", "_", s.strip()).strip("_")
    return s[:40] or "video"

def _hex_opt(v):
    """Mau '#rrggbb' tu form; sai dinh dang -> '' (dung mau mac dinh)."""
    v = str(v or "").strip()
    return v if re.fullmatch(r"#[0-9a-fA-F]{6}", v) else ""

def _px_opt(v):
    """Co chu px nguoi dung nhap (chuoi tu form). Rong/khong hop le -> None (tu dong)."""
    try:
        n = int(str(v).strip())
        return n if 20 <= n <= 320 else None
    except (TypeError, ValueError):
        return None

# ---------- Thu vien video tren disk ----------
def _job_id_from_fn(fn):
    """Tach job_id (timestamp ms) tu ten file mp4."""
    m = re.search(r'_(\d+)\.mp4$', fn)
    return m.group(1) if m else os.path.splitext(fn)[0]

def _read_meta(fn):
    """Doc <fn>.meta.json (vd <file>.mp4.meta.json). Tra dict (rong neu loi)."""
    try:
        with open(os.path.join(OUT, fn + ".meta.json"), "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}

def list_library():
    """Quet output/ -> danh sach video sort theo mtime giam dan.
    Moi item: job_id, title, video, thumb, date, size_mb, has_seo."""
    items = []
    try:
        names = os.listdir(OUT)
    except Exception:
        return items
    for fn in names:
        if not fn.lower().endswith(".mp4"):
            continue
        try:
            path = os.path.join(OUT, fn)
            if not os.path.isfile(path):
                continue
            job_id = _job_id_from_fn(fn)
            base = fn[:-4]
            thumb_name = base + ".thumb.jpg"
            thumb = thumb_name if os.path.exists(os.path.join(OUT, thumb_name)) else None
            st = os.stat(path)
            # title: jobs[job_id].seo.title -> meta.json title -> ten file
            jseo = (jobs.get(job_id, {}) or {}).get("seo") or {}
            title = (jseo.get("title")
                     or _read_meta(fn).get("title")
                     or base)
            seo_d = jobs.get(job_id, {}).get("seo") or {}
            has_seo = bool(seo_d.get("description") or seo_d.get("tags"))
            items.append({
                "job_id": job_id,
                "title": title,
                "video": fn,
                "thumb": thumb,
                "date": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime)),
                "size_mb": round(st.st_size / (1024 * 1024), 1),
                "has_seo": has_seo,
                "_mtime": st.st_mtime,
            })
        except Exception:
            continue
    items.sort(key=lambda x: x.get("_mtime", 0), reverse=True)
    for it in items:
        it.pop("_mtime", None)
    return items

def _job_from_disk(job_id):
    """Tim video tren disk theo job_id -> dung job dict toi thieu (status done).
    None neu khong tim thay file mp4."""
    try:
        names = os.listdir(OUT)
    except Exception:
        return None
    target = None
    suffix = f"_{job_id}.mp4"
    exact = f"{job_id}.mp4"
    for fn in names:
        if not fn.lower().endswith(".mp4"):
            continue
        if fn.endswith(suffix) or fn == exact:
            target = fn
            break
    if not target:
        return None
    base = target[:-4]
    thumb_name = base + ".thumb.jpg"
    thumb = thumb_name if os.path.exists(os.path.join(OUT, thumb_name)) else None
    title = _read_meta(target).get("title") or base
    return {
        "video": target,
        "thumb": thumb,
        "seo": {"title": title, "titles": [title], "description": "",
                "tags": [], "hashtags": [], "pinned_comment": "",
                "privacy": "public"},
        "status": "done",
    }

@app.route("/")
def index():
    akey, aregion = load_azure()
    return render_template("index.html", edge_voices=EDGE_VOICES,
                           azure_voices=AZURE_VOICES, chattts_voices=CHATTTS_VOICES,
                           chattts_styles=CHATTTS_STYLES, eleven_voices=ELEVEN_VOICES,
                           edge_ml_voices=EDGE_ML_VOICES, gemini_voices=GEMINI_VOICES,
                           rates=RATES, themes=THEMES, mascots=MASCOTS, moods=MOODS,
                           azure_key=akey, azure_region=aregion,
                           eleven_key=load_eleven(), bg_saved=load_bg(),
                           gemini_key=load_gemini())

@app.route("/eleven/voices")
def eleven_voices_list():
    """Lay danh sach giong cua tai khoan ElevenLabs (de dropdown chon)."""
    key = (request.args.get("key") or "").strip() or load_eleven()
    if not key:
        return jsonify(voices=[], error="Chưa có API key — nhập key rồi bấm tải lại.")
    try:
        import urllib.request, urllib.error, json as _j
        req = urllib.request.Request("https://api.elevenlabs.io/v1/voices",
                                     headers={"xi-api-key": key})
        data = _j.loads(urllib.request.urlopen(req, timeout=30).read())
        voices = [{"id": v.get("voice_id"),
                   "name": (v.get("name") or v.get("voice_id"))}
                  for v in data.get("voices", []) if v.get("voice_id")]
        save_eleven(key)                       # luu key de lan sau khoi nhap
        return jsonify(voices=voices)
    except urllib.error.HTTPError as e:
        msg = "Lỗi tải giọng."
        if e.code == 401:
            msg = ("Key thiếu quyền 'Voices → Read'. Vào ElevenLabs → API Keys → "
                   "sửa key → bật Voices = Read → Save.")
        return jsonify(voices=[], error=f"{msg} (HTTP {e.code})")
    except Exception as e:
        return jsonify(voices=[], error=str(e))

@app.route("/upload", methods=["POST"])
def upload():
    f = request.files.get("file")
    kind = request.form.get("kind", "file")
    if not f or not f.filename:
        return jsonify(error="Chưa chọn file"), 400
    ext = os.path.splitext(f.filename)[1].lower()[:6]
    name = f"{kind}_{int(time.time()*1000)}{ext}"
    p = os.path.join(UP, name)
    f.save(p)
    if kind == "bg":
        save_bg(p)               # nho anh nen de F5 khong mat
    return jsonify(path=p, name=f.filename)

BRAND_DIR = os.path.join(ROOT, "brand")
@app.route("/upload_brand", methods=["POST"])
def upload_brand():
    """Luu intro/outro mp4 vao brand/ (tu luu, dung lai moi video). kind=intro|outro."""
    f = request.files.get("file")
    kind = request.form.get("kind", "")
    if kind not in ("intro", "outro") or not f or not f.filename:
        return jsonify(error="Thiếu file hoặc loại không hợp lệ"), 400
    os.makedirs(BRAND_DIR, exist_ok=True)
    f.save(os.path.join(BRAND_DIR, kind + ".mp4"))
    return jsonify(ok=True, kind=kind)

@app.route("/brand_status")
def brand_status():
    """Bao intro/outro da co chua de UI hien trang thai."""
    return jsonify(intro=os.path.exists(os.path.join(BRAND_DIR, "intro.mp4")),
                   outro=os.path.exists(os.path.join(BRAND_DIR, "outro.mp4")))

@app.route("/brand_delete/<kind>", methods=["POST"])
def brand_delete(kind):
    if kind in ("intro", "outro"):
        p = os.path.join(BRAND_DIR, kind + ".mp4")
        if os.path.exists(p):
            os.remove(p)
    return jsonify(ok=True)

@app.route("/import_drive", methods=["POST"])
def import_drive():
    """Doc noi dung tu link Google Drive/Docs (file phai chia se cong khai)."""
    import requests, io, re as _re
    url = ((request.get_json(force=True) or {}).get("url") or "").strip()
    m = _re.search(r"/d/([A-Za-z0-9_-]{20,})", url) or _re.search(r"[?&]id=([A-Za-z0-9_-]{20,})", url)
    if not m:
        return jsonify(error="Link Google Drive/Docs không hợp lệ."), 400
    fid = m.group(1)
    is_doc = ("docs.google.com/document" in url) or ("/document/d/" in url)
    try:
        durl = (f"https://docs.google.com/document/d/{fid}/export?format=txt" if is_doc
                else f"https://drive.google.com/uc?export=download&id={fid}")
        data = requests.get(durl, timeout=25).content
        head = data[:400].lower()
        if data[:2] != b"PK" and (b"<!doctype html" in head or b"<html" in head):
            return jsonify(error="File chưa chia sẻ công khai. Mở Drive → Share → "
                                 "'Anyone with the link' (Viewer), rồi thử lại."), 400
        if data[:4] == b"PK\x03\x04":          # .docx (zip)
            from docx import Document
            text = "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
        else:
            text = data.decode("utf-8", errors="replace")
        text = text.replace("\r\n", "\n").replace("﻿", "").strip()
        if not text:
            return jsonify(error="File rỗng hoặc không đọc được."), 400
        return jsonify(content=text)
    except Exception as e:
        return jsonify(error=f"Lỗi đọc Drive: {e}"), 500

@app.route("/generate", methods=["POST"])
def generate_route():
    data = request.get_json(force=True)
    if not (data.get("content") or "").strip():
        return jsonify(error="Bạn chưa nhập nội dung."), 400
    job_id = str(int(time.time() * 1000))
    jobs[job_id] = {"done": 0, "total": 1, "label": "Đang xếp hàng...",
                    "status": "running", "video": None, "error": None, "cancel": False}
    threading.Thread(target=run_job, args=(job_id, data), daemon=True).start()
    return jsonify(job_id=job_id)

class _Cancelled(Exception):
    """Nguoi dung bam Huy -> dung job dang tao video."""
    pass

def run_job(job_id, data):
    try:
        with _build_lock:
            if jobs[job_id].get("cancel"):     # huy ngay khi con dang xep hang
                raise _Cancelled()
            jobs[job_id]["label"] = "Đọc nội dung..."
            ctx = lesson_parser.parse_lesson(data["content"])
            # giong: value dang "edge:..." hoac "azure:..."
            engine, _, vname = (data.get("voice") or "edge:zh-CN-XiaoxiaoNeural").partition(":")
            azure_tuple = None
            eleven_key = None
            gemini_key = None
            voice_vi = generate.VOICE_VI            # mac dinh: giong Viet edge-tts
            if engine == "azure":
                akey = (data.get("azure_key") or "").strip()
                aregion = (data.get("azure_region") or "").strip()
                if akey and aregion:
                    save_azure(akey, aregion)          # luu de lan sau khoi nhap
                else:
                    akey, aregion = load_azure()
                if not (akey and aregion):
                    raise RuntimeError("Giọng Azure cần Key + Region. "
                                       "Hãy nhập ở mục 'Giọng tự nhiên (Azure)'.")
                azure_tuple = (akey, aregion)
            elif engine == "eleven":
                eleven_key = (data.get("eleven_key") or "").strip() or load_eleven()
                if not eleven_key:
                    raise RuntimeError("Giọng ElevenLabs cần API key. "
                                       "Hãy nhập ở mục 'Giọng cao cấp (ElevenLabs)'.")
                save_eleven(eleven_key)                # luu de lan sau khoi nhap
                # cho phep dan voice_id rieng (uu tien) thay cho giong chon san
                custom = (data.get("eleven_voice") or "").strip()
                if custom:
                    vname = custom
                voice_vi = vname                       # 1 giong da ngu: doc ca Trung + Viet
            elif engine == "gemini":
                gemini_key = (data.get("gemini_key") or "").strip() or load_gemini()
                if not gemini_key:
                    raise RuntimeError("Giọng Gemini cần API key. "
                                       "Hãy nhập ở mục 'Giọng Google Gemini'.")
                save_gemini(gemini_key)                # luu de lan sau khoi nhap
                voice_vi = vname                       # 1 giong da ngu: doc ca Trung + Viet

            # Hoi thoai nhieu giong (MOI engine): map {nguoi_noi: voice}
            # voice = ten giong edge (vd zh-CN-YunjianNeural) hoac voice_id ElevenLabs,
            # dispatch theo dung engine cua giong chinh.
            dmap_raw = data.get("dialogue_map") or {}
            dialogue_map = {str(k).strip(): str(v).strip()
                            for k, v in dmap_raw.items() if str(v).strip()}
            # TU GAN GIONG: neu chua gan tay + engine free (edge/azure) + phat hien >=2 nguoi noi
            # -> tu doan gioi tinh & gan giong nam/nu khac nhau cho tung nguoi.
            auto_speakers = lesson_parser.detect_speakers(data["content"])
            # CHI tu-gan giong khi CHUA khai @voices va CHUA gan tay (tranh "mot dong giong sai").
            # Co @voices -> tin bang khai bao, khong doan mo nua.
            if (not dialogue_map and not ctx.get("voices")
                    and auto_speakers and engine in ("edge", "azure")):
                dialogue_map = lesson_parser.assign_speaker_voices(auto_speakers)
                jobs[job_id]["label"] = (f"Tự nhận diện {len(auto_speakers)} người nói, "
                                         "đã gán giọng…")
            elif ctx.get("voices"):
                jobs[job_id]["label"] = (f"@voices: {len(ctx['voices'])} nhân vật "
                                         f"({', '.join(ctx['voices'])})…")
            ctx.update({
                "voice_zh": vname,
                "voice_vi": voice_vi,
                "_azure":   azure_tuple,
                "_eleven":  eleven_key,
                "_eleven_model": (data.get("eleven_model") or "eleven_multilingual_v2"),
                "_gemini":  gemini_key,
                "_dialogue_map": dialogue_map,
                "_chattts": (data.get("chattts_style", "warm")
                             if engine == "chattts" else None),
                "rate":     data.get("rate", "-8%"),
                "pad":      float(data.get("pad", 0.8)),
                "expressive": int(data.get("expressive", 60)),
                "theme":    data.get("theme", "pink"),
                "music":    bool(data.get("music", True)),
                "music_vol": float(data.get("music_vol", 0.5)),
                "mascot":   data.get("mascot", ""),
                "channel":  data.get("channel", "").strip() or "Học Tiếng Trung",
                "infobar":  data.get("infobar", "").strip(),
                "ai_mascot": bool(data.get("ai_mascot", False)),
                "mascot_motion": bool(data.get("mascot_motion", True)),
                "intro_outro": bool(data.get("intro_outro", True)),
                "use_intro":   bool(data.get("use_intro", True)),
                "use_outro":   bool(data.get("use_outro", True)),
                "show_title":  bool(data.get("show_title", False)),
                "show_outro":  bool(data.get("show_outro", False)),
                "podcast_layout": bool(data.get("podcast_layout", False)),
                "podcast_variant": data.get("podcast_variant", "inkwash"),
                "panel_alpha": int(data.get("panel_alpha", 150)),
                "tone_colors": bool(data.get("tone_colors", True)),
                "podcast_frame": bool(data.get("podcast_frame", True)),
                "seal_text": (data.get("seal_text") or "").strip(),
                "pinyin_mode": (data.get("pinyin_mode") or "").strip(),
                "waveform": (data.get("waveform") or "auto").strip(),
                "fx": (data.get("fx") or "").strip(),
                "zh_px": _px_opt(data.get("zh_px")),
                "bottom_bar": bool(data.get("bottom_bar", False)),
                "bar_left": (data.get("bar_left") or "").strip(),
                "bar_badge": (data.get("bar_badge") or "PODCAST").strip(),
                "bar_bg": _hex_opt(data.get("bar_bg")),
                "zh_color": _hex_opt(data.get("zh_color")),
                "py_color": _hex_opt(data.get("py_color")),
                "vi_color": _hex_opt(data.get("vi_color")),
                "panel_color": _hex_opt(data.get("panel_color")),
                "py_px": _px_opt(data.get("py_px")),
                "vi_px": _px_opt(data.get("vi_px")),
                "pinyin_top": bool(data.get("pinyin_top", True)),
                "show_progress": bool(data.get("show_progress", True)),
                "repeat_slow": bool(data.get("repeat_slow", False)),
                "replay_loop": bool(data.get("replay_loop", False)),
                "podcast":   bool(data.get("podcast", False)),
                "emotion_auto": bool(data.get("emotion_auto", True)),
                "mood":      data.get("mood", "calm"),
                "bg_image":  (data.get("bg_image") or "").strip(),
                "music_file": (data.get("music_file") or "").strip(),
                "out_name":  slugify(ctx["title"]) + "_" + job_id,
            })
            if not bool(data.get("character", True)):     # tat nhan vat
                ctx["mascot"] = "none"
                ctx["ai_mascot"] = False
                ctx["mascot_motion"] = False
            ip = (data.get("image_prompt") or "").strip()
            if ip:
                ctx["image_prompt"] = ip
            hd = (data.get("header") or "").strip()
            if hd:
                ctx["header"] = hd
            # --- @voices: gan giong RIENG cho tung nhan vat da khai bao (tin cay) ---
            # spec = "nam"/"nu" (gioi tinh) HOAC ma giong edge cu the. Nhan vat khong khai
            # + phan ke -> dung giong nguoi dung chon (voice_zh). KHONG bao gio de-ngam.
            _GENDER_VOICE = {"nam": "zh-CN-YunjianNeural", "nu": "zh-CN-XiaoyiNeural",
                             "nữ": "zh-CN-XiaoyiNeural", "male": "zh-CN-YunjianNeural",
                             "female": "zh-CN-XiaoyiNeural"}
            named_voices = {nm: _GENDER_VOICE.get(str(spec).strip().lower(), str(spec).strip())
                            for nm, spec in (ctx.get("voices") or {}).items()}
            if named_voices:
                for s in ctx["segments"]:
                    if s.get("_sp") in named_voices:
                        s["_voice"] = named_voices[s["_sp"]]

            def prog(done, total, label):
                if jobs[job_id].get("cancel"):     # bam Huy giua chung -> dung o slide ke tiep
                    raise _Cancelled()
                jobs[job_id].update(done=done, total=total, label=label)
            final = generate.build(ctx, progress=prog)
            seo_meta = seo.generate(ctx)        # Buoc 2: sinh thong tin YouTube
            thumb = os.path.basename(final)[:-4] + ".thumb.jpg"
            jobs[job_id].update(status="done", video=os.path.basename(final),
                                thumb=(thumb if os.path.exists(os.path.join(OUT, thumb)) else None),
                                seo=seo_meta, label="Hoàn tất!")
            _save_job(job_id)               # persist metadata job done ra jobs.json
    except _Cancelled:
        jobs[job_id].update(status="cancelled", label="⏹ Đã huỷ")
    except Exception as e:
        traceback.print_exc()
        jobs[job_id].update(status="error", error=str(e), label="Lỗi: " + str(e))

@app.route("/progress/<job_id>")
def progress(job_id):
    return jsonify(jobs.get(job_id, {"status": "unknown"}))

@app.route("/cancel/<job_id>", methods=["POST"])
def cancel_route(job_id):
    """Bam Huy: danh dau job de dung o buoc ke tiep (build kiem co huy qua callback progress)."""
    j = jobs.get(job_id)
    if not j:
        return jsonify(ok=False, error="Job không tồn tại"), 404
    if j.get("status") == "running":
        j["cancel"] = True
        return jsonify(ok=True)
    return jsonify(ok=False, status=j.get("status"))

@app.route("/clear_tts_cache", methods=["POST"])
def clear_tts_cache():
    """Xoa sach cache giong TTS (file mp3 da sinh). Render sau se sinh moi 100%."""
    d = generate.TTS_CACHE
    n, freed = 0, 0
    if os.path.isdir(d):
        for f in os.listdir(d):
            p = os.path.join(d, f)
            try:
                freed += os.path.getsize(p); os.remove(p); n += 1
            except Exception:
                pass
    return jsonify(ok=True, files=n, mb=round(freed / 1e6, 1))

@app.route("/reset", methods=["POST"])
def reset_route():
    """RESET toan bo ve mac dinh: xoa cache giong + tat ca video da tao + lich su job.
       GIU NGUYEN: yt_tokens (kenh YouTube), social_tokens/secrets (MXH), brand (intro/outro/logo),
       cac file config key. Client tu xoa localStorage + reload de form ve mac dinh."""
    def _wipe_dir(d):
        n = 0
        if os.path.isdir(d):
            for f in os.listdir(d):
                p = os.path.join(d, f)
                if os.path.isfile(p):
                    try:
                        os.remove(p); n += 1
                    except Exception:
                        pass
        return n
    n_cache = _wipe_dir(generate.TTS_CACHE)   # cache giong
    n_out = _wipe_dir(OUT)                     # output/: video + thumb + jobs.json + meta
    jobs.clear()                              # lich su job trong RAM
    return jsonify(ok=True, cache_files=n_cache, output_files=n_out)

@app.route("/video/<path:fn>")
def video(fn):
    return send_from_directory(OUT, fn, as_attachment=False)

@app.route("/download/<path:fn>")
def download(fn):
    return send_from_directory(OUT, fn, as_attachment=True)

@app.route("/thumb/<path:fn>")
def thumb(fn):
    return send_from_directory(OUT, fn, as_attachment=False)

@app.route("/upload_thumb/<job_id>", methods=["POST"])
def upload_thumb(job_id):
    """Tai anh bia tu thiet ke len -> tu cat ve 1280x720, de len anh tu tao."""
    job = jobs.get(job_id)
    if not job or not job.get("video"):
        return jsonify(error="Phiên không hợp lệ (hãy tạo video lại)."), 400
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify(error="Chưa chọn ảnh"), 400
    try:
        from PIL import Image, ImageOps
        im = ImageOps.fit(Image.open(f.stream).convert("RGB"), (1280, 720), Image.LANCZOS)
        name = os.path.basename(job["video"])[:-4] + ".thumb.jpg"
        im.save(os.path.join(OUT, name), "JPEG", quality=90)
        job["thumb"] = name
        return jsonify(ok=True, thumb=name)
    except Exception as e:
        return jsonify(error=str(e)), 500

# ---------- BUOC 2: trang dang YouTube ----------
@app.route("/youtube/<job_id>")
def youtube_page(job_id):
    job = jobs.get(job_id)
    if not job or job.get("status") != "done":
        j = _job_from_disk(job_id)              # fallback: video co tren disk
        if j:
            jobs[job_id] = j                    # cache lai vao RAM
            job = j
        else:
            return "Video chưa sẵn sàng. Hãy tạo video trước.", 404
    return render_template("youtube.html", job_id=job_id,
                           video=job["video"], thumb=job.get("thumb"),
                           seo=job.get("seo", {}))

@app.route("/api/seo/<job_id>")
def api_seo(job_id):
    job = jobs.get(job_id)
    if not job or job.get("status") != "done":
        j = _job_from_disk(job_id)              # fallback: video co tren disk
        if j:
            jobs[job_id] = j                    # cache lai vao RAM
            job = j
        else:
            job = {}
    return jsonify(video=job.get("video"), seo=job.get("seo", {}))

# ---------- Thu vien video da tao ----------
@app.route("/library")
def library_page():
    return render_template("library.html", videos=list_library())

@app.route("/library/delete/<job_id>", methods=["POST"])
def library_delete(job_id):
    """Xoa file mp4 + thumb + meta.json cua job_id, go khoi jobs + jobs.json."""
    j = _job_from_disk(job_id)
    if not j:
        return jsonify(ok=False, error="not found"), 404
    video = j["video"]
    base = video[:-4]
    for name in (video, base + ".thumb.jpg", video + ".meta.json"):
        try:
            p = os.path.join(OUT, name)
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            traceback.print_exc()
    jobs.pop(job_id, None)
    # doc-merge-xoa-ghi jobs.json
    try:
        data = {}
        try:
            with open(JOBS_DB, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        except Exception:
            data = {}
        if job_id in data:
            data.pop(job_id, None)
            os.makedirs(OUT, exist_ok=True)
            with open(JOBS_DB, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
    except Exception:
        traceback.print_exc()
    return jsonify(ok=True)

@app.route("/import_video", methods=["POST"])
def import_video():
    """Dang video co san (multipart 'file' mp4 + 'title' optional) vao thu vien."""
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify(error="thiếu file"), 400
    title = (request.form.get("title") or "").strip()
    job_id = str(int(time.time() * 1000))
    slug = slugify(title or "video-co-san")
    fname = f"{slug}_{job_id}.mp4"
    os.makedirs(OUT, exist_ok=True)
    f.save(os.path.join(OUT, fname))
    try:
        with open(os.path.join(OUT, fname + ".meta.json"), "w", encoding="utf-8") as mf:
            json.dump({"title": title or slug, "segments": [], "imported": True},
                      mf, ensure_ascii=False)
    except Exception:
        traceback.print_exc()
    jobs[job_id] = {"status": "done", "video": fname, "thumb": None,
                    "seo": {"title": title or slug, "titles": [title or slug],
                            "description": "", "tags": [], "hashtags": [],
                            "pinned_comment": "", "privacy": "public"}}
    _save_job(job_id)
    return jsonify(job_id=job_id)

# ---------- YouTube upload (OAuth) ----------
import youtube_upload

@app.route("/yt/channels")
def yt_channels():
    if not youtube_upload.is_configured():
        return jsonify(channels=[], setup=youtube_upload.setup_hint())
    try:
        return jsonify(channels=youtube_upload.list_channels())
    except Exception as e:
        return jsonify(channels=[], error=str(e))

@app.route("/yt/connect")
def yt_connect():
    if not youtube_upload.is_configured():
        return ("Chưa có client_secret.json. " +
                youtube_upload.setup_hint().replace("<code>", "").replace("</code>", "")), 400
    try:
        info = youtube_upload.connect()      # mo trinh duyet dang nhap (blocking)
        return (f"<h2>✅ Đã kết nối kênh: {info['title']}</h2>"
                "<p>Đóng tab này và quay lại trang đăng video, danh sách kênh sẽ tự cập nhật.</p>")
    except Exception as e:
        return f"<h2>❌ Lỗi kết nối</h2><pre>{e}</pre>", 500

@app.route("/yt/upload", methods=["POST"])
def yt_upload():
    d = request.get_json(force=True)
    job = jobs.get(d.get("job_id"))
    if not job or not job.get("video"):
        return jsonify(error="Không tìm thấy video của phiên này."), 400
    video_path = os.path.join(OUT, job["video"])
    if not os.path.exists(video_path):
        return jsonify(error="File video không tồn tại."), 400
    try:
        res = youtube_upload.upload(
            d["channel"], video_path,
            title=d.get("title", ""), description=d.get("description", ""),
            tags=d.get("tags", ""), privacy=d.get("privacy", "public"),
            category=d.get("category", "27"))
        # tu dong upload phu de (CC): chu Han / pinyin / tieng Viet
        captions = {"caption_ok": [], "caption_err": []}
        if d.get("captions", True):
            seo_data = job.get("seo", {})
            tracks = [("zh-Hans", "中文 (Chữ Hán)", seo_data.get("srt_hanzi")),
                      ("zh-Latn", "Pinyin", seo_data.get("srt_pinyin")),
                      ("vi", "Tiếng Việt", seo_data.get("srt_viet"))]
            for lang, name, srt in tracks:
                if not srt:
                    continue
                try:
                    youtube_upload.upload_caption(d["channel"], res["id"], srt, lang, name)
                    captions["caption_ok"].append(name)
                except Exception as ce:
                    captions["caption_err"].append(f"{name}: {ce}")
        res.update(captions)
        # dat anh bia (thumbnail) — can kenh da bat custom thumbnail (xac minh SDT)
        if d.get("set_thumb", True) and job.get("thumb"):
            try:
                youtube_upload.set_thumbnail(d["channel"], res["id"],
                                             os.path.join(OUT, job["thumb"]))
                res["thumb_ok"] = True
            except Exception as te:
                res["thumb_err"] = str(te)
        # tu dong dang comment tu vung (API khong cho ghim -> user tu ghim)
        cmt = (d.get("comment") or "").strip()
        if d.get("post_comment", True) and cmt:
            try:
                youtube_upload.post_comment(d["channel"], res["id"], cmt)
                res["comment_ok"] = True
            except Exception as ce:
                res["comment_err"] = str(ce)
        return jsonify(res)
    except Exception as e:
        traceback.print_exc()
        return jsonify(error=str(e)), 500

# ---------- Lan toa MXH (organic marketing) — Giai doan 1: Facebook ----------
import social_upload, social_seo

social_tasks = {}          # task_id -> {done, results:{platform:{state,url,msg,caption}}}
_fb_page_cache = {}        # channel_id -> [{id,name,access_token}] (tam, sau khi liet ke Page)

def _yt_name(cid):
    for c in youtube_upload.list_channels():
        if c["id"] == cid:
            return c["title"]
    return ""

@app.route("/social/links/<channel_id>")
def social_links(channel_id):
    try:
        return jsonify(social_upload.public_links(channel_id, yt_name=_yt_name(channel_id)))
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route("/social/toggle/<channel_id>/<platform>", methods=["POST"])
def social_toggle(channel_id, platform):
    d = request.get_json(force=True)
    social_upload.set_enabled(channel_id, platform, bool(d.get("enabled")))
    return jsonify(ok=True)

@app.route("/social/mode/<channel_id>/<platform>", methods=["POST"])
def social_mode(channel_id, platform):
    d = request.get_json(force=True)
    social_upload.set_mode(channel_id, platform, d.get("mode", "native"))
    return jsonify(ok=True)

@app.route("/social/content/<channel_id>/<platform>", methods=["POST"])
def social_content(channel_id, platform):
    """Dat 'kieu noi dung' (content profile) cho 1 nen tang."""
    d = request.get_json(force=True)
    social_upload.set_content(channel_id, platform,
                              style=d.get("style"), custom_prompt=d.get("custom_prompt"))
    return jsonify(ok=True)

@app.route("/social/ai_caption/<job_id>/<channel_id>/<platform>", methods=["POST"])
def social_ai_caption(job_id, channel_id, platform):
    """Sinh 1 caption bang AI theo content_style cua nen tang (cho nut '✨ Sinh AI')."""
    import social_ai
    if not social_ai.is_configured():
        return jsonify(error="Chưa cấu hình Anthropic API key. " +
                       social_ai.setup_hint().replace("<code>", "").replace("</code>", "")), 400
    d = request.get_json(force=True)
    idx = social_upload.load_index(channel_id)
    st = idx["platforms"].get(platform, {})
    seo_data = jobs.get(job_id, {}).get("seo", {})
    try:
        text = social_seo.caption(
            seo_data, platform, lang=idx.get("lang", "zh"), yt_url=d.get("yt_url", ""),
            style=d.get("style") or st.get("content_style", "vocab_grammar"),
            custom_prompt=d.get("custom_prompt", st.get("custom_prompt", "")),
            channel_name=idx.get("yt_channel_name", ""))
        return jsonify(caption=text)
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route("/social/ai_status")
def social_ai_status():
    import social_ai
    return jsonify(configured=social_ai.is_configured(), styles=social_ai.CONTENT_STYLES)

@app.route("/social/disconnect/<channel_id>/<platform>", methods=["POST"])
def social_disconnect(channel_id, platform):
    social_upload.disconnect(channel_id, platform)
    return jsonify(ok=True)

@app.route("/social/fb/pages", methods=["POST"])
def social_fb_pages():
    """Buoc 1 ket noi FB: dan User token -> liet ke Page (khong tra token ra UI)."""
    d = request.get_json(force=True)
    cid = d.get("channel_id", "")
    try:
        pages = social_upload.fb_list_pages(d.get("token", ""))
        _fb_page_cache[cid] = pages
        return jsonify(pages=[{"id": p["id"], "name": p["name"]} for p in pages])
    except Exception as e:
        return jsonify(error=str(e)), 400

@app.route("/social/fb/save", methods=["POST"])
def social_fb_save():
    """Buoc 2 ket noi FB: chon Page -> luu page token."""
    d = request.get_json(force=True)
    cid, page_id = d.get("channel_id", ""), d.get("page_id", "")
    pages = _fb_page_cache.get(cid, [])
    page = next((p for p in pages if p["id"] == page_id), None)
    if not page or not page.get("access_token"):
        return jsonify(error="Phiên kết nối hết hạn, hãy dán lại token."), 400
    info = social_upload.fb_save_page(cid, page_id, page["name"], page["access_token"])
    _fb_page_cache.pop(cid, None)
    return jsonify(ok=True, **info)

@app.route("/social/fields/<job_id>")
def social_fields(job_id):
    """Trả về các TRƯỜNG soạn bài (hook/body/cta/hashtags/link) cho từng nền tảng."""
    seo_data = jobs.get(job_id, {}).get("seo", {})
    yt_url = request.args.get("yt_url", "")
    lang = request.args.get("lang", "zh")
    return jsonify(social_seo.all_fields(seo_data, lang=lang, yt_url=yt_url))

@app.route("/social/post", methods=["POST"])
def social_post():
    """Dang nen song song len cac nen tang enabled+connected. Tra task_id ngay."""
    d = request.get_json(force=True)
    cid = d.get("channel_id", "")
    job = jobs.get(d.get("job_id"))
    if not job:
        return jsonify(error="Không tìm thấy phiên video."), 400
    yt_url = d.get("yt_url", "")
    plats = d.get("platforms", {})           # {fb:{on,caption,mode}, ...}
    # che do auto (dung cho dang nhieu kenh YT): tu lay nen tang da bat+ket noi cua kenh
    # va tu sinh caption chuan SEO theo lang cua kenh.
    if d.get("auto"):
        idx = social_upload.load_index(cid)
        seo_data = job.get("seo", {})
        lang = idx.get("lang", "zh")
        cname = idx.get("yt_channel_name", "")
        plats = {}
        for p, st in idx["platforms"].items():
            if st.get("enabled") and st.get("connected"):
                plats[p] = {"on": True, "mode": st.get("mode", "native"),
                            "caption": social_seo.caption(
                                seo_data, p, lang=lang, yt_url=yt_url,
                                style=st.get("content_style", "video_promo"),
                                custom_prompt=st.get("custom_prompt", ""),
                                channel_name=cname)}
    video_path = os.path.join(OUT, job["video"]) if job.get("video") else None
    task_id = str(int(time.time() * 1000))
    targets = [p for p, cfg in plats.items() if cfg.get("on")]
    social_tasks[task_id] = {"done": False,
                             "results": {p: {"state": "pending"} for p in targets}}
    threading.Thread(target=_run_social, args=(task_id, cid, targets, plats,
                                               yt_url, video_path), daemon=True).start()
    return jsonify(task_id=task_id, targets=targets), 202

def _run_social(task_id, cid, targets, plats, yt_url, video_path):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    res = social_tasks[task_id]["results"]

    def _one(platform):
        cfg = plats.get(platform, {})
        res[platform] = {"state": "running"}
        mode = cfg.get("mode", "native")
        media = ({"kind": "native", "video_path": video_path}
                 if mode == "native" and video_path else {"kind": "link", "url": yt_url})
        out = social_upload.post_to(cid, platform, cfg.get("caption", ""), media)
        if out.get("ok"):
            res[platform] = {"state": "ok", "url": out.get("post_url", ""),
                             "msg": "Đã đăng" + (" (video)" if out.get("kind") == "native" else " (link)")}
        else:
            res[platform] = {"state": "error", "msg": out.get("error", "lỗi"),
                             "hint": out.get("hint", "")}

    try:
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = [ex.submit(_one, p) for p in targets]
            for _ in as_completed(futs):
                pass
    finally:
        social_tasks[task_id]["done"] = True

@app.route("/social/status/<task_id>")
def social_status(task_id):
    t = social_tasks.get(task_id)
    if not t:
        return jsonify(error="task không tồn tại"), 404
    return jsonify(t)

@app.route("/srt/<job_id>/<kind>")
def srt_download(job_id, kind):
    """Tai phu de .srt: kind = hanzi | pinyin | viet."""
    seo_data = jobs.get(job_id, {}).get("seo", {})
    text = seo_data.get("srt_" + kind, "")
    from flask import Response
    fn = f"{job_id}_{kind}.srt"
    return Response(text, mimetype="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{fn}"'})

if __name__ == "__main__":
    print("\n  ✅ Mở trình duyệt: http://127.0.0.1:5001\n")
    app.run(host="127.0.0.1", port=5001, debug=False, threaded=True)
