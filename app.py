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
import generate, lesson_parser, seo

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "output")
app = Flask(__name__)

jobs = {}
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
    ("azure:zh-CN-XiaoxiaoMultilingualNeural", "Hiểu Hiểu Đa ngữ — Nữ, rất tự nhiên ⭐"),
    ("azure:zh-CN-XiaochenMultilingualNeural", "Hiểu Trần — Nữ trẻ, tự nhiên"),
    ("azure:zh-CN-YunyiMultilingualNeural",    "Vân Nghị — Nam, tự nhiên"),
    ("azure:zh-CN-Xiaochen:DragonHDLatestNeural", "Hiểu Trần HD — siêu thật (mới nhất)"),
    ("azure:zh-CN-Yunfan:DragonHDLatestNeural",   "Vân Phàm HD — Nam, siêu thật"),
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
    s = re.sub(r'[\\/:*?"<>|]', "", s).strip().replace(" ", "_")
    return s[:40] or "video"

@app.route("/")
def index():
    akey, aregion = load_azure()
    return render_template("index.html", edge_voices=EDGE_VOICES,
                           azure_voices=AZURE_VOICES, chattts_voices=CHATTTS_VOICES,
                           chattts_styles=CHATTTS_STYLES, eleven_voices=ELEVEN_VOICES,
                           edge_ml_voices=EDGE_ML_VOICES,
                           rates=RATES, themes=THEMES, mascots=MASCOTS, moods=MOODS,
                           azure_key=akey, azure_region=aregion,
                           eleven_key=load_eleven())

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
            eleven_key = None
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

            # Hoi thoai nhieu giong (MOI engine): map {nguoi_noi: voice}
            # voice = ten giong edge (vd zh-CN-YunjianNeural) hoac voice_id ElevenLabs,
            # dispatch theo dung engine cua giong chinh.
            dmap_raw = data.get("dialogue_map") or {}
            dialogue_map = {str(k).strip(): str(v).strip()
                            for k, v in dmap_raw.items() if str(v).strip()}
            ctx.update({
                "voice_zh": vname,
                "voice_vi": voice_vi,
                "_azure":   azure_tuple,
                "_eleven":  eleven_key,
                "_dialogue_map": dialogue_map,
                "_chattts": (data.get("chattts_style", "warm")
                             if engine == "chattts" else None),
                "rate":     data.get("rate", "-8%"),
                "pad":      float(data.get("pad", 0.8)),
                "theme":    data.get("theme", "pink"),
                "music":    bool(data.get("music", True)),
                "music_vol": float(data.get("music_vol", 0.5)),
                "mascot":   data.get("mascot", ""),
                "channel":  data.get("channel", "").strip() or "Học Tiếng Trung",
                "infobar":  data.get("infobar", "").strip(),
                "ai_mascot": bool(data.get("ai_mascot", False)),
                "mascot_motion": bool(data.get("mascot_motion", True)),
                "podcast":   bool(data.get("podcast", False)),
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
            seo_meta = seo.generate(ctx)        # Buoc 2: sinh thong tin YouTube
            thumb = os.path.basename(final)[:-4] + ".thumb.jpg"
            jobs[job_id].update(status="done", video=os.path.basename(final),
                                thumb=(thumb if os.path.exists(os.path.join(OUT, thumb)) else None),
                                seo=seo_meta, label="Hoàn tất!")
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
        return "Video chưa sẵn sàng. Hãy tạo video trước.", 404
    return render_template("youtube.html", job_id=job_id,
                           video=job["video"], thumb=job.get("thumb"),
                           seo=job.get("seo", {}))

@app.route("/api/seo/<job_id>")
def api_seo(job_id):
    job = jobs.get(job_id, {})
    return jsonify(video=job.get("video"), seo=job.get("seo", {}))

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
    print("\n  ✅ Mở trình duyệt: http://127.0.0.1:5000\n")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
