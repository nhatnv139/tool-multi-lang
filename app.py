# -*- coding: utf-8 -*-
"""App web tao video hoc tieng Trung.
Chay:  python app.py   ->  mo http://127.0.0.1:5000
Ban chi can: dien NOI DUNG + chon GIONG DOC -> bam Tao video. Con lai tu dong.
"""
import os, sys, threading, time, traceback, re
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from flask import Flask, request, jsonify, send_from_directory, render_template
import generate, lesson_parser

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "output")
app = Flask(__name__)

jobs = {}
_build_lock = threading.Lock()      # render tuan tu (ffmpeg nang)

# Giong edge-tts (mien phi, khong can key) — value tien to "edge:"
EDGE_VOICES = [
    ("edge:zh-CN-XiaoxiaoNeural", "Hiểu Hiểu — Nữ, ấm (free)"),
    ("edge:zh-CN-XiaoyiNeural",   "Hiểu Y — Nữ, trẻ (free)"),
    ("edge:zh-CN-YunxiNeural",    "Vân Hi — Nam, trẻ (free)"),
    ("edge:zh-CN-YunyangNeural",  "Vân Dương — Nam, tin tức (free)"),
    ("edge:zh-CN-YunxiaNeural",   "Vân Hạ — Nam, dễ thương (free)"),
]
# Giong Azure (tu nhien hon, can key free) — value tien to "azure:"
AZURE_VOICES = [
    ("azure:zh-CN-XiaoxiaoMultilingualNeural", "Hiểu Hiểu Đa ngữ — Nữ, rất tự nhiên ⭐"),
    ("azure:zh-CN-XiaochenMultilingualNeural", "Hiểu Trần — Nữ trẻ, tự nhiên"),
    ("azure:zh-CN-YunyiMultilingualNeural",    "Vân Nghị — Nam, tự nhiên"),
    ("azure:zh-CN-Xiaochen:DragonHDLatestNeural", "Hiểu Trần HD — siêu thật (mới nhất)"),
    ("azure:zh-CN-Yunfan:DragonHDLatestNeural",   "Vân Phàm HD — Nam, siêu thật"),
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
RATES = [("-20%", "Chậm (người mới)"), ("-10%", "Hơi chậm"),
         ("-8%", "Vừa (khuyên)"), ("0%", "Bình thường")]
THEMES = [("pink", "Hồng pastel"), ("mint", "Xanh mint"), ("sky", "Xanh da trời"),
          ("cream", "Kem"), ("lavender", "Tím nhạt")]
MOODS = [("calm", "Piano nhẹ nhàng / thư giãn"), ("hope", "Piano hy vọng / tích cực"),
         ("happy", "Piano vui tươi"), ("sad", "Piano trầm buồn"),
         ("box", "Hộp nhạc (music box) trong trẻo"), ("deep", "Trầm sâu lắng")]

UP = os.path.join(ROOT, "uploads")
os.makedirs(UP, exist_ok=True)
MASCOTS = [("", "Tự đổi theo bài"), ("🐼", "Gấu trúc"), ("🐱", "Mèo"),
           ("🐰", "Thỏ"), ("🐻", "Gấu"), ("🦊", "Cáo"), ("🐧", "Chim cánh cụt"),
           ("none", "Không mascot")]

def slugify(s):
    s = re.sub(r'[\\/:*?"<>|]', "", s).strip().replace(" ", "_")
    return s[:40] or "video"

@app.route("/")
def index():
    akey, aregion = load_azure()
    return render_template("index.html", edge_voices=EDGE_VOICES,
                           azure_voices=AZURE_VOICES, chattts_voices=CHATTTS_VOICES,
                           chattts_styles=CHATTTS_STYLES,
                           rates=RATES, themes=THEMES, mascots=MASCOTS, moods=MOODS,
                           azure_key=akey, azure_region=aregion)

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
    return jsonify(path=p, name=f.filename)

@app.route("/generate", methods=["POST"])
def generate_route():
    data = request.get_json(force=True)
    if not (data.get("content") or "").strip():
        return jsonify(error="Bạn chưa nhập nội dung."), 400
    job_id = str(int(time.time() * 1000))
    jobs[job_id] = {"done": 0, "total": 1, "label": "Đang xếp hàng...",
                    "status": "running", "video": None, "error": None}
    threading.Thread(target=run_job, args=(job_id, data), daemon=True).start()
    return jsonify(job_id=job_id)

def run_job(job_id, data):
    try:
        with _build_lock:
            jobs[job_id]["label"] = "Đọc nội dung..."
            ctx = lesson_parser.parse_lesson(data["content"])
            # giong: value dang "edge:..." hoac "azure:..."
            engine, _, vname = (data.get("voice") or "edge:zh-CN-XiaoxiaoNeural").partition(":")
            azure_tuple = None
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
            ctx.update({
                "voice_zh": vname,
                "_azure":   azure_tuple,
                "_chattts": (data.get("chattts_style", "warm")
                             if engine == "chattts" else None),
                "rate":     data.get("rate", "-8%"),
                "theme":    data.get("theme", "pink"),
                "music":    bool(data.get("music", True)),
                "music_vol": float(data.get("music_vol", 0.5)),
                "mascot":   data.get("mascot", ""),
                "channel":  data.get("channel", "").strip() or "Học Tiếng Trung",
                "infobar":  data.get("infobar", "").strip(),
                "ai_mascot": bool(data.get("ai_mascot", False)),
                "mascot_motion": bool(data.get("mascot_motion", True)),
                "podcast":   bool(data.get("podcast", True)),
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
            def prog(done, total, label):
                jobs[job_id].update(done=done, total=total, label=label)
            final = generate.build(ctx, progress=prog)
            jobs[job_id].update(status="done", video=os.path.basename(final),
                                label="Hoàn tất!")
    except Exception as e:
        traceback.print_exc()
        jobs[job_id].update(status="error", error=str(e), label="Lỗi: " + str(e))

@app.route("/progress/<job_id>")
def progress(job_id):
    return jsonify(jobs.get(job_id, {"status": "unknown"}))

@app.route("/video/<path:fn>")
def video(fn):
    return send_from_directory(OUT, fn, as_attachment=False)

@app.route("/download/<path:fn>")
def download(fn):
    return send_from_directory(OUT, fn, as_attachment=True)

if __name__ == "__main__":
    print("\n  ✅ Mở trình duyệt: http://127.0.0.1:5000\n")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
