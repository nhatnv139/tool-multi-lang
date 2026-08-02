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
                        "seo": j.get("seo"), "short": j.get("short"),
                        "short_seo": j.get("short_seo"), "status": "done",
                        "recipe": j.get("recipe")}
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
            _vid_ok = _v.get("video") and os.path.exists(os.path.join(OUT, _v["video"]))
            _sh_ok = _v.get("short") and os.path.exists(os.path.join(OUT, _v["short"]))
            if _vid_ok or _sh_ok:                 # giu ca job Short-only (studio, khong video dai)
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
# Cap nhat 2026-07: bo sung giong MOI NHAT (DragonHD Omni, Xiaoxiao2, MAI-Voice-2) — da test that voi key.
AZURE_VOICES = [
    # ===== MỚI NHẤT — thế hệ Omni (siêu thật, tự nhiên nhất) =====
    ("azure:zh-CN-Xiaoyue:DragonHDOmniLatestNeural", "Hiểu Nguyệt Omni — Nữ, SIÊU THẬT ⭐ (mới nhất)"),
    ("azure:zh-CN-Yunqi:DragonHDOmniLatestNeural",   "Vân Kỳ Omni — Nam, SIÊU THẬT ⭐ (mới nhất)"),
    # ===== MAI-Voice-2 (mới, biểu cảm nhiều style) =====
    ("azure:zh-CN-Mei:MAI-Voice-2", "Mai MAI-2 — Nữ, biểu cảm phong phú ⭐ (mới)"),
    ("azure:zh-CN-Lan:MAI-Voice-2", "Lan MAI-2 — Nữ, ấm, tự nhiên (mới)"),
    ("azure:zh-CN-Bo:MAI-Voice-2",  "Bác MAI-2 — Nam, biểu cảm phong phú ⭐ (mới)"),
    ("azure:zh-CN-Wei:MAI-Voice-2", "Vĩ MAI-2 — Nam, trầm ấm (mới)"),
    # ===== DragonHD Latest (siêu thật) =====
    ("azure:zh-CN-Xiaochen:DragonHDLatestNeural", "Hiểu Trần HD — Nữ, siêu thật ⭐"),
    ("azure:zh-CN-Yunfan:DragonHDLatestNeural",   "Vân Phàm HD — Nam, siêu thật ⭐"),
    # ===== DragonHD Flash (siêu thật, nhanh) =====
    ("azure:zh-CN-Xiaoxiao:DragonHDFlashLatestNeural",  "Hiểu Hiểu HD — Nữ, ấm, kể chuyện"),
    ("azure:zh-CN-Xiaoxiao2:DragonHDFlashLatestNeural", "Hiểu Hiểu 2 HD — Nữ, bản nâng cấp ⭐"),
    ("azure:zh-CN-Xiaohan:DragonHDFlashLatestNeural",   "Hiểu Hàm HD — Nữ, dịu dàng"),
    ("azure:zh-CN-Xiaoyi:DragonHDFlashLatestNeural",    "Hiểu Y HD — Nữ, trẻ trung"),
    ("azure:zh-CN-Yunxiao:DragonHDFlashLatestNeural",   "Vân Tiêu HD — Nam, trẻ, tự nhiên ⭐"),
    ("azure:zh-CN-Yunyi:DragonHDFlashLatestNeural",     "Vân Nghị HD — Nam, ấm"),
    ("azure:zh-CN-Yunxi:DragonHDFlashLatestNeural",     "Vân Hi HD — Nam, nắng ấm"),
    ("azure:zh-CN-Yunye:DragonHDFlashLatestNeural",     "Vân Diệp HD — Nam, kể chuyện"),
    # ===== Đa ngữ (đọc tốt cả Trung + Việt + Anh) =====
    ("azure:zh-CN-XiaoxiaoMultilingualNeural", "Hiểu Hiểu Đa ngữ — Nữ, rất tự nhiên ⭐"),
    ("azure:zh-CN-XiaochenMultilingualNeural", "Hiểu Trần Đa ngữ — Nữ trẻ"),
    ("azure:zh-CN-XiaoyuMultilingualNeural",   "Hiểu Vũ Đa ngữ — Nữ, ấm"),
    ("azure:zh-CN-YunyiMultilingualNeural",    "Vân Nghị Đa ngữ — Nam"),
    ("azure:zh-CN-YunfanMultilingualNeural",   "Vân Phàm Đa ngữ — Nam"),
    ("azure:zh-CN-YunxiaoMultilingualNeural",  "Vân Tiêu Đa ngữ — Nam, trẻ"),
    # ===== Neural biểu cảm (nhiều style cảm xúc) =====
    ("azure:zh-CN-XiaoxiaoNeural", "Hiểu Hiểu — Nữ, 20 style cảm xúc"),
    ("azure:zh-CN-XiaomoNeural",   "Hiểu Mặc — Nữ, đa cảm xúc"),
    ("azure:zh-CN-XiaohanNeural",  "Hiểu Hàm — Nữ, dịu dàng"),
    ("azure:zh-CN-XiaozhenNeural", "Hiểu Trinh — Nữ, nghiêm túc"),
    ("azure:zh-CN-XiaoruiNeural",  "Hiểu Duệ — Nữ, lớn tuổi, điềm đạm"),
    ("azure:zh-CN-XiaoyiNeural",   "Hiểu Y — Nữ, trẻ, hoạt náo"),
    ("azure:zh-CN-XiaoshuangNeural", "Hiểu Sảng — Bé gái, dễ thương"),
    ("azure:zh-CN-YunxiNeural",    "Vân Hi — Nam, trẻ, nắng ấm"),
    ("azure:zh-CN-YunjianNeural",  "Vân Kiện — Nam, kể chuyện biểu cảm"),
    ("azure:zh-CN-YunyangNeural",  "Vân Dương — Nam, tin tức"),
    ("azure:zh-CN-YunzeNeural",    "Vân Trạch — Nam, điềm tĩnh"),
    ("azure:zh-CN-YunfengNeural",  "Vân Phong — Nam, sôi nổi"),
    # ===== Giọng vùng miền =====
    ("azure:zh-CN-sichuan-YunxiNeural",    "Vân Hi — Nam, giọng Tứ Xuyên"),
    ("azure:zh-CN-liaoning-XiaobeiNeural", "Hiểu Bối — Nữ, giọng Đông Bắc"),
    ("azure:zh-CN-shaanxi-XiaoniNeural",   "Hiểu Ni — Nữ, giọng Thiểm Tây"),
    # ===== Quan Thoại Đài Loan =====
    ("azure:zh-TW-HsiaoChenNeural", "Hiểu Trăn — Nữ, Đài Loan"),
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

# Giong TIENG VIET — cho video thuan Viet (ke chuyen, nhan qua, co tich...)
# edge: free 100% khong can key; azure: dung key da luu; gemini: cac giong da ngu
# o nhom Gemini ben tren cung doc duoc tieng Viet rat tot (them cau dan cam xuc).
VI_VOICES = [
    ("edge:vi-VN-NamMinhNeural",  "Nam Minh — Nam, trầm, kể chuyện ⭐ (edge free)"),
    # edge chi co 2 giong Viet -> che bien the TRAM hon bang ha pitch (@-XHz, xem _edge_pitch_split)
    ("edge:vi-VN-NamMinhNeural@-15Hz", "Nam Minh Trầm — hạ tông, truyện xưa ⭐ (edge free)"),
    ("edge:vi-VN-NamMinhNeural@-25Hz", "Nam Minh Trầm Sâu — già dặn, chậm rãi (edge free)"),
    ("edge:vi-VN-HoaiMyNeural",   "Hoài My — Nữ, ấm, dễ nghe ⭐ (edge free)"),
    ("edge:vi-VN-HoaiMyNeural@-12Hz", "Hoài My Trầm — Nữ, tông thấp kể chuyện (edge free)"),
    ("azure:vi-VN-NamMinhNeural", "Nam Minh — Nam (Azure, cần key)"),
    ("azure:vi-VN-HoaiMyNeural",  "Hoài My — Nữ (Azure, cần key)"),
    ("gemini:Gacrux",             "Gacrux — Giọng già dặn, hợp truyện xưa ⭐ (Gemini)"),
    ("gemini:Algenib",            "Algenib — Nam, khàn trầm (Gemini)"),
    ("gemini:Sulafat",            "Sulafat — Nữ, ấm áp truyền cảm ⭐ (Gemini)"),
    ("gemini:Charon",             "Charon — Nam, trầm vững, dẫn chuyện (Gemini)"),
    ("gemini:Enceladus",          "Enceladus — Nam, thủ thỉ tâm tình (Gemini)"),
]

# Giong FPT.AI Voicemaker — thuan Viet, gioi lam noi dung VN dung nhieu nhat.
# FREE 100.000 ky tu/thang khi dang ky (fpt.ai) — value tien to "fpt:<ma-giong>".
FPT_VOICES = [
    ("fpt:banmai",    "Ban Mai — Nữ Bắc, kể chuyện, hot nhất ⭐ (FPT free 100k/tháng)"),
    ("fpt:leminh",    "Lê Minh — Nam Bắc, trầm ấm ⭐ (FPT)"),
    ("fpt:thuminh",   "Thu Minh — Nữ Bắc, khỏe khoắn (FPT)"),
    ("fpt:giahuy",    "Gia Huy — Nam Huế, truyền cảm (FPT)"),
    ("fpt:ngoclam",   "Ngọc Lam — Nữ Huế, dịu dàng (FPT)"),
    ("fpt:myan",      "Mỹ An — Nữ Huế (FPT)"),
    ("fpt:linhsan",   "Linh San — Nữ Nam, ngọt ngào (FPT)"),
    ("fpt:minhquang", "Minh Quang — Nam Nam (FPT)"),
]

# Giong VieNeu-TTS v3 Turbo — model TIENG VIET local (offline, free, khong quota).
# Chay bang .venv-vieneu (Python 3.11) qua vieneu_tts.py; giu nguyen tien to
# "vieneu:" trong ten giong de generate.synth() tu dispatch.
VIENEU_VOICES = [
    ("vieneu:Văn Minh 2",   "Văn Minh 2 — GIONG CUA BAN, mau doc truyen (VieNeu local) 🎙⭐"),
    ("vieneu:Văn Minh Taa", "Văn Minh Taa — GIONG CUA BAN, mau cu (VieNeu local) 🎙"),
    ("vieneu:Thanh Bình", "Thanh Bình — Nam Bắc, kể chuyện ⭐ (VieNeu local)"),
    ("vieneu:Thái Sơn",   "Thái Sơn — Nam Nam, kể chuyện ⭐ (VieNeu local)"),
    ("vieneu:Ngọc Linh",  "Ngọc Linh — Nữ Bắc, kể chuyện (VieNeu local)"),
    ("vieneu:Thục Đoan",  "Thục Đoan — Nữ Nam, kể chuyện (VieNeu local)"),
    ("vieneu:Phạm Tuyên", "Phạm Tuyên — Nam Bắc, tự nhiên (VieNeu local)"),
    ("vieneu:Xuân Vĩnh",  "Xuân Vĩnh — Nam Nam, tự nhiên (VieNeu local)"),
    ("vieneu:Trúc Ly",    "Trúc Ly — Nữ Bắc, tự nhiên (VieNeu local)"),
    ("vieneu:Đoan Trang", "Đoan Trang — Nữ Bắc, tự nhiên (VieNeu local)"),
    ("vieneu:Quang Sơn",  "Quang Sơn — Nam Trung, tự nhiên (VieNeu local)"),
    ("vieneu:Ngọc Trân",  "Ngọc Trân — Nữ Trung, tự nhiên (VieNeu local)"),
    ("vieneu:Minh Đức",   "Minh Đức — Nam Bắc, tin tức (VieNeu local)"),
    ("vieneu:Mai Anh",    "Mai Anh — Nữ Bắc, tin tức (VieNeu local)"),
    ("vieneu:Minh Triết", "Minh Triết — Nam Nam, tin tức (VieNeu local)"),
    ("vieneu:Thùy Dung",  "Thùy Dung — Nữ Nam, tin tức (VieNeu local)"),
]

# Giong Vbee (vbee.vn) — thuan Viet, "Anh Khoi" la giong ke chuyen nhan qua/co tich
# ma rat nhieu kenh YouTube VN dang dung. Tra phi theo ky tu (goi nho vai chuc k/thang).
# Value tien to "vbee:<voice_code>" -> generate.synth() tu dispatch (nhu VieNeu).
VBEE_VOICES = [
    ("vbee:hn_male_phuthang_stor80dt_48k-fhg", "Anh Khôi — Nam Bắc trầm, kể chuyện/lịch sử/phật pháp ⭐⭐ (Vbee)"),
    ("vbee:hn_male_manhdung_news_48k-fhg",     "Mạnh Dũng — Nam Bắc thanh niên, tin tức/thuyết minh (Vbee)"),
    ("vbee:hn_male_manhdung_news_48k-phg",     "Mạnh Dũng QC — Nam Bắc thanh niên, quảng cáo (Vbee)"),
    ("vbee:hn_male_thanhlong_talk_48k-fhg",    "Thanh Long — Nam Bắc, điềm tĩnh, podcast chữa lành (Vbee)"),
    ("vbee:sg_male_chidat_ebook_48k-phg",      "Chí Đạt — Nam Nam, sách nói, gần gũi (Vbee)"),
    ("vbee:sg_male_trungkien_vdts_48k-fhg",    "Trung Kiên — Nam Nam, trầm, thuyết minh (Vbee)"),
    ("vbee:hn_female_ngochuyen_full_48k-fhg",  "Ngọc Huyền — Nữ Bắc, truyền cảm (Vbee)"),
]

VBEE_CFG = os.path.join(ROOT, "vbee_config.json")
def load_vbee():
    try:
        import json as _j
        d = _j.load(open(VBEE_CFG, encoding="utf-8"))
        return d.get("token", ""), d.get("app_id", "")
    except Exception:
        return "", ""
def save_vbee(token, app_id):
    import json as _j
    _j.dump({"token": token, "app_id": app_id}, open(VBEE_CFG, "w", encoding="utf-8"))

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

FPT_CFG = os.path.join(ROOT, "fpt_config.json")
def load_fpt():
    try:
        import json as _j
        return _j.load(open(FPT_CFG, encoding="utf-8")).get("key", "")
    except Exception:
        return ""
def save_fpt(key):
    import json as _j
    _j.dump({"key": key}, open(FPT_CFG, "w", encoding="utf-8"))

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
        # ban doi tone do slider tao (<goc>.tone-2.mp4) -> khong hien thanh card rieng
        if re.search(r"\.tone[+-][\d.]+\.mp4$", fn, re.I):
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
    short_name = base + "_short.mp4"                         # video Short (neu da tao)
    has_short = os.path.exists(os.path.join(OUT, short_name))
    return {
        "video": target,
        "thumb": thumb,
        "seo": {"title": title, "titles": [title], "description": "",
                "tags": [], "hashtags": [], "pinned_comment": "",
                "privacy": "public"},
        "short": (short_name if has_short else None),
        "short_seo": ({"title": f"{title} #Shorts", "description": ""} if has_short else {}),
        "status": "done",
    }

@app.route("/")
def index():
    akey, aregion = load_azure()
    return render_template("index.html", edge_voices=EDGE_VOICES,
                           azure_voices=AZURE_VOICES, chattts_voices=CHATTTS_VOICES,
                           chattts_styles=CHATTTS_STYLES, eleven_voices=ELEVEN_VOICES,
                           edge_ml_voices=EDGE_ML_VOICES, gemini_voices=GEMINI_VOICES,
                           vi_voices=VI_VOICES, vieneu_voices=VIENEU_VOICES,
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

@app.route("/pdf", methods=["POST"])
def pdf_route():
    """Xuất NỘI DUNG BÀI ĐỌC ra PDF Study Guide đẹp (Hán + pinyin tô thanh điệu + nghĩa)."""
    import study_pdf
    d = request.get_json(force=True) or {}
    content = (d.get("content") or "").strip()
    if not content:
        return jsonify(error="Chưa có nội dung."), 400
    # tiêu đề file từ @title
    title = "bai-doc"
    for ln in content.splitlines():
        if ln.strip().lower().startswith("@title") and " " in ln.strip():
            title = slugify(ln.split(" ", 1)[1].strip())[:60] or "bai-doc"; break
    out_pdf = os.path.join(OUT, f"pdf_{int(time.time()*1000)}.pdf")
    try:
        study_pdf.build_pdf(content, out_pdf, link=(d.get("link") or PROMO_LINK))
    except Exception as e:
        traceback.print_exc()
        return jsonify(error="Tạo PDF lỗi: " + str(e)), 500
    from flask import send_file
    import unicodedata
    ascii_name = (unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
                  or "bai-doc")                                  # "Vịt"->"Vit"; header HTTP phải ASCII
    resp = send_file(out_pdf, mimetype="application/pdf", as_attachment=True,
                     download_name=ascii_name + ".pdf")
    resp.headers["X-Filename"] = ascii_name
    return resp


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
            # Tên kênh (watermark) tự lấy từ @header, bỏ phần "· HSK ..." -> chỉ giữ tên kênh
            _hdr = (ctx.get("header") or "").strip()
            ctx["_channel_auto"] = re.split(r"\s*[·|]\s*", _hdr)[0].strip() if _hdr else ""
            # giong: value dang "edge:..." hoac "azure:..."
            engine, _, vname = (data.get("voice") or "edge:zh-CN-XiaoxiaoNeural").partition(":")
            print(f"[DEBUG-TTS] raw voice={data.get('voice')!r} engine={engine!r} vname={vname!r} "
                  f"eleven_voice={data.get('eleven_voice')!r} eleven_model={data.get('eleven_model')!r}")
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
            elif engine == "vieneu":
                # VieNeu local (tieng Viet): GIU tien to trong ten giong ->
                # generate.synth() tu nhan "vieneu:" va goi model local.
                vname = "vieneu:" + vname
                voice_vi = vname

            # GIONG TIENG VIET chon rieng (dropdown "Giọng đọc tiếng Việt") —
            # ghi de moi mac dinh o tren. "vieneu:" giu tien to (synth tu dispatch);
            # edge/azure bo tien to (di theo engine chinh); gemini: giong da ngu,
            # chi hop khi engine chinh cung la gemini (khac engine -> bo qua, giu auto).
            vi_sel = (data.get("voice_vi") or "").strip()
            if vi_sel:
                e2, _, n2 = vi_sel.partition(":")
                if e2 == "vieneu":
                    voice_vi = "vieneu:" + n2
                elif e2 == "gemini":
                    if engine == "gemini":
                        voice_vi = n2
                    else:
                        jobs[job_id]["label"] = ("Giọng Việt Gemini cần engine chính "
                                                 "cũng là Gemini — dùng giọng Việt tự động.")
                else:
                    # edge:/azure: vi-VN-* la CUNG giong Microsoft -> bo tien to,
                    # doc theo engine chinh (edge free hay Azure deu co giong nay)
                    voice_vi = n2

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
            # auto_voices=False (nguoi dung tat) -> DUNG 1 GIONG DA CHON cho tat ca (khong tu chia).
            # auto_voices=True -> nhan vat CHON TAY (dialogue_map) duoc uu tien, con lai TU GAN.
            auto_voices = bool(data.get("auto_voices", True))
            if (auto_voices and not ctx.get("voices")
                    and auto_speakers and engine in ("edge", "azure")):
                auto_map = lesson_parser.assign_speaker_voices(auto_speakers)
                for _sp, _v in auto_map.items():
                    dialogue_map.setdefault(_sp, _v)          # chon tay thang, auto lap cho chua chon
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
                "rate":     data.get("rate", "-12%"),          # 85-90% natural (mac dinh)
                "pad":      float(data.get("pad", 1.2)),        # nghi sau dau cham cau (1-1.5s)
                "comma_pause": float(data.get("comma_pause", 0.0)),   # THEM nghi sau dau phay (0=tu nhien ~0.2-0.3s)
                "para_gap": float(data.get("para_gap", 2.5)),  # nghi giua 2 doan (2-3s)
                "expressive": int(data.get("expressive", 60)),
                "theme":    data.get("theme", "pink"),
                "music":    bool(data.get("music", True)),
                "music_vol": float(data.get("music_vol", 0.5)),
                "mascot":   data.get("mascot", ""),
                "channel":  ctx.get("_channel_auto") or (data.get("channel") or "").strip() or "Học Tiếng Trung",
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
                "panel_h": int(data.get("panel_h", 0) or 0),
                "tone_colors": bool(data.get("tone_colors", True)),
                "podcast_frame": bool(data.get("podcast_frame", True)),
                "seal_text": (data.get("seal_text") or "").strip(),
                # chu viet tay dau trang cua bien the "showhead" (mac dinh: Podcast)
                "show_word": (data.get("show_word") or "").strip(),
                "pinyin_mode": (data.get("pinyin_mode") or "").strip(),
                # bong do sau chu: ''=tu dong (chi khi co anh nen) / 'on' / 'off'
                "text_shadow": (data.get("text_shadow") or "").strip(),
                "waveform": (data.get("waveform") or "auto").strip(),
                "fx": (data.get("fx") or "").strip(),
                "zh_px": _px_opt(data.get("zh_px")),
                "bottom_bar": bool(data.get("bottom_bar", False)),
                "bar_left": ctx.get("title") or (data.get("bar_left") or "").strip(),
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
                "bg_images": [p.strip() for p in (data.get("bg_images") or [])
                              if isinstance(p, str) and p.strip()],
                "bg_by_scene": bool(data.get("bg_by_scene")),
                "hide_section_slides": bool(data.get("hide_section_slides")),
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
            # tao 1 video Short 9:16 NATIVE (1 cau dat, khong crop) — loi short KHONG chan luong chinh
            try:
                import short_native as _shorts
                _sh = _shorts.make_short(final, OUT)
                jobs[job_id]["short"] = os.path.basename(_sh["file"])
                jobs[job_id]["short_seo"] = {"title": _sh["title"],
                                             "description": _sh["desc"]}
            except Exception:
                traceback.print_exc()
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

@app.route("/film/retone", methods=["POST"])
def film_retone():
    """Đổi tone (pitch) audio của video ĐÃ render — hình copy nguyên, chỉ xử lý audio.
    Luôn tính từ video GỐC (frontend giữ tên gốc) để kéo qua lại không bị cộng dồn."""
    d = request.get_json(force=True) or {}
    fn = os.path.basename(d.get("video") or "")
    st = float(d.get("semitones") or 0)
    src = os.path.join(OUT, fn)
    if not fn or not os.path.isfile(src):
        return jsonify(error="Không thấy file video."), 404
    if not st:
        return jsonify(video=fn)
    import retone as _rt
    root, ext = os.path.splitext(src)
    out = f"{root}.tone{st:+g}{ext}"
    if not os.path.isfile(out):                      # cache: kéo lại giá trị cũ -> trả ngay
        try:
            _rt.retone(src, st, out)
        except Exception as e:
            return jsonify(error=f"ffmpeg lỗi: {str(e)[:120]}"), 500
    return jsonify(video=os.path.basename(out))

@app.route("/thumb/<path:fn>")
def thumb(fn):
    return send_from_directory(OUT, fn, as_attachment=False)

@app.route("/skins")
def skins_list():
    """Danh sach phong cach layout (key + nhan) cho gallery /shorts."""
    import short_native as _sn
    order = ["ink", "royal", "night", "sunset", "ocean", "gradient", "neon",
             "cute", "kawaii", "candy", "comic", "memphis", "sakura",
             "notebook", "grid", "chalk", "bamboo", "paper", "white"]
    keys = [k for k in order if k in _sn.SKINS] + [k for k in _sn.SKINS if k not in order]
    return jsonify(skins=[{"key": k, "label": _sn.SKINS[k]["label"]} for k in keys])

@app.route("/skin_prev/<name>")
def skin_prev(name):
    """Anh xem truoc 1 phong cach (render layout 'Tu moi' mau, cache lai, thu nho)."""
    import short_native as _sn
    from PIL import Image
    name = name if name in _sn.SKINS else "ink"
    fp = os.path.join(OUT, f"_skinprev_{name}.png")
    fresh = request.args.get("fresh")
    if fresh or not (os.path.exists(fp) and os.path.getsize(fp) > 0):
        big = os.path.join(OUT, f"_skinprev_{name}_big.png")
        _sn._apply_skin(name)
        _sn.render_vocab_frame("学习", "học tập", "我天天学习中文", big,
                               ex_viet="Tôi học tiếng Trung mỗi ngày")
        im = Image.open(big).convert("RGB")
        im.thumbnail((400, 711), Image.LANCZOS)   # 9:16 thu nho
        im.save(fp, "PNG")
        try: os.remove(big)
        except OSError: pass
    return send_from_directory(OUT, os.path.basename(fp), as_attachment=False)

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
    _td = _read_meta(job["video"]).get("total_dur") or 0
    video_len = "%d:%02d" % (int(_td) // 60, int(_td) % 60) if _td else ""
    return render_template("youtube.html", job_id=job_id,
                           video=job["video"], thumb=job.get("thumb"),
                           seo=job.get("seo", {}),
                           short=job.get("short"), short_seo=job.get("short_seo", {}),
                           video_len=video_len)

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
    # cac ban doi tone do slider tao ra: <base>.tone-2.mp4, <base>.tone+3.mp4...
    tones = [f for f in os.listdir(OUT)
             if f.startswith(base + ".tone") and f.endswith(video[-4:])]
    for name in [video, base + ".thumb.jpg", video + ".meta.json"] + tones:
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

# ---------- SHORTS STUDIO: sinh Short doc TRUC TIEP tu cau (khong can video dai) ----------
@app.route("/shorts")
def shorts_page():
    return render_template("shorts.html", edge_voices=EDGE_VOICES, promo_link=PROMO_LINK,
                           azure_voices=AZURE_VOICES, azure_ready=bool(load_azure()[0]),
                           vi_voices=VI_VOICES, vieneu_voices=VIENEU_VOICES)

@app.route("/shorts/extract", methods=["POST"])
def shorts_extract():
    """Nhan noi dung 1 bai (content.md) -> tu rut N cau 'dat' nhat lam Short.
    Tra ve {lines: '汉字 | nghia\\n...'} de do thang vao o tao Short."""
    d = request.get_json(force=True) or {}
    content = (d.get("content") or "").strip()
    if not content:
        return jsonify(error="Chưa dán nội dung bài."), 400
    try:
        n = max(1, min(12, int(d.get("n") or 5)))
    except Exception:
        n = 5
    import short_native as _sn
    cands = _sn.extract_candidates(content, n)
    if not cands:
        return jsonify(error="Không tìm thấy câu phù hợp (câu quá dài hoặc thiếu nghĩa)."), 400
    lines = "\n".join(f"{c['hanzi']} | {c['viet']}" for c in cands)
    return jsonify(lines=lines, count=len(cands))

def _azure_for(voice):
    """Neu voice la 'azure:...' -> tra (key, region) tu azure_config; con lai None (edge free)."""
    if isinstance(voice, str) and voice.startswith("azure:"):
        k, r = load_azure()
        if k and r:
            return (k, r)
    return None


def _gemini_for(voice):
    """Neu voice la 'gemini:...' -> tra key Gemini; con lai None. Thieu key -> None
    (nguoi goi phai tu doi giong khac, KHONG duoc de roi xuong edge-tts voi ten giong Gemini)."""
    if isinstance(voice, str) and voice.startswith("gemini:"):
        return load_gemini() or None
    return None


def _eleven_for(voice):
    """Neu voice la 'eleven:<voice_id>' -> tra key ElevenLabs; con lai None."""
    if isinstance(voice, str) and voice.startswith("eleven:"):
        return load_eleven() or None
    return None


def _fpt_for(voice):
    """Neu voice la 'fpt:<ma-giong>' -> tra key FPT.AI; con lai None."""
    if isinstance(voice, str) and voice.startswith("fpt:"):
        return load_fpt() or None
    return None


def _render_one_short(fmt, cols, hook, voice, reads, ui_lang, bg, skin, jid, py_color=None):
    """Render 1 Short tu cac cot da parse (dung chung boi /shorts/make va /shorts/rehook)."""
    import short_native as _sn
    az = _azure_for(voice)
    hanzi = cols[0]
    viet = cols[1] if len(cols) > 1 else ""
    note = cols[2] if len(cols) > 2 else ""
    if fmt == "vocab":
        return _sn.make_vocab_from_text(hanzi, viet, example=(cols[2] if len(cols) > 2 else ""),
                                        ex_viet=(cols[3] if len(cols) > 3 else ""),
                                        voice=voice, out_dir=OUT, reads=reads, name=jid,
                                        lang=ui_lang, bg=bg, skin=skin, label=(hook or None), azure=az)
    if fmt == "pattern":
        exs = []
        for c in cols[2:]:
            han, _, vi = c.partition("=")
            if han.strip():
                exs.append((han.strip(), vi.strip()))
        return _sn.make_pattern_from_text(hanzi, viet, examples=exs, voice=voice, out_dir=OUT,
                                          name=jid, lang=ui_lang, bg=bg, skin=skin,
                                          label=(hook or None), azure=az)
    if fmt == "quiz":
        return _sn.make_quiz_from_text(hanzi, viet, voice=voice, hook=hook, out_dir=OUT,
                                       name=jid, lang=ui_lang, bg=bg, skin=skin, azure=az)
    return _sn.make_short_from_text(hanzi, viet, voice=voice, hook=hook, out_dir=OUT,
                                    reads=reads, name=jid, note=note, lang=ui_lang, bg=bg,
                                    skin=skin, azure=az, py_color=py_color)


@app.route("/shorts/rehook/<job_id>", methods=["POST"])
def shorts_rehook(job_id):
    """Sua hook/nhan tren cung cua 1 Short da tao roi render lai (ghi de dung file)."""
    import short_native as _sn
    d = request.get_json(force=True) or {}
    new_hook = (d.get("hook") or "").strip() or None
    job = jobs.get(job_id)
    if not job or not job.get("recipe"):
        return jsonify(error="Không tìm thấy công thức Short này (có thể server đã khởi động lại)."), 404
    rc = job["recipe"]
    try:
        if rc.get("kind") == "combine":
            rows = [tuple(x) for x in rc["rows"]]
            r = _sn.make_short_from_lines(rows, voice=rc["voice"], hook=new_hook, out_dir=OUT,
                                          reads=rc["reads"], name=job_id, lang=rc["ui_lang"],
                                          bg=rc["bg"], skin=rc["skin"], title=rc.get("title"),
                                          azure=_azure_for(rc["voice"]), py_color=rc.get("py_color"))
        else:
            r = _render_one_short(rc["fmt"], rc["cols"], new_hook, rc["voice"], rc["reads"],
                                  rc["ui_lang"], rc["bg"], rc["skin"], job_id, py_color=rc.get("py_color"))
    except Exception as e:
        traceback.print_exc()
        return jsonify(error=str(e)), 500
    fn = os.path.basename(r["file"])
    desc_i = _append_link(r["desc"], rc.get("link"))
    job["short"] = fn
    job["short_seo"] = {"title": r["title"], "description": desc_i}
    _save_job(job_id)
    return jsonify(short=fn, title=r["title"], description=desc_i,
                   hook=r["hook"], dur=r.get("dur"))


# Link playlist gioi thieu / nghe bo tro — TU DONG noi vao mo ta moi Short.
# Doi link kenh cua ban o day (hoac nhap o UI de ghi de tung dot).
PROMO_LINK = "https://www.youtube.com/playlist?list=PLb7JsPPf3Pls"

def _append_link(desc, link, lang=None):
    """Noi dong gioi thieu playlist vao cuoi mo ta. lang tu dong theo short_native.UI_LANG neu None."""
    link = (link or "").strip()
    if not link:
        return desc
    if lang is None:
        try:
            import short_native as _sn
            lang = _sn.UI_LANG
        except Exception:
            lang = "vi"
    if lang == "en":
        return (f"{desc}\n\n▶️ Watch the full playlist here:\n{link}"
                "\n👉 Subscribe to learn Chinese every day!")
    return (f"{desc}\n\n▶️ Xem thêm & nghe bổ trợ — playlist đầy đủ:\n{link}"
            "\n👉 Đăng ký kênh để học tiếng Trung mỗi ngày!")


_SEC_LABEL = re.compile(r"^S\s*\d+\s*[·:.\-–—]\s*")   # bo tien to "S1 · " trong tieu de

def _parse_sections(raw):
    """Tach 1 khoi dan NHIEU BAI -> list section. Moi section:
      - 1 dong TIEU DE (khong co '|'); ho tro '## S1 · Tieu de' hoac 'Tieu de' tran.
      - cac @tag tuy chon: @title / @hook / @skin / @reads
      - cac dong '汉字 | nghia | ghi chu'
    Dong trong = ngan cach. Dong '#' don (1 dau thang) = comment -> bo qua.
    Tra ve list dict {title, title_ov, hook, skin, reads, rows[(hz,vi,nt)]}."""
    sections = []
    cur = None
    def _new(title=""):
        s = {"title": title.strip(), "title_ov": "", "hook": "", "skin": "", "reads": "", "rows": []}
        sections.append(s)
        return s
    for ln in raw.splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith("##"):                             # tieu de section (## S1 · ...)
            cur = _new(_SEC_LABEL.sub("", s.lstrip("#").strip()))
        elif s.startswith("#"):                             # comment 1 dau thang -> bo qua (ke ca co '|')
            continue
        elif s.startswith("@"):                             # @tag
            k, _, v = s[1:].partition(" ")
            k, v = k.lower(), v.strip()
            if cur is None:                                 # @tag truoc section dau (file-level) -> bo
                continue
            if k == "title":   cur["title_ov"] = v
            elif k == "hook":  cur["hook"] = v
            elif k == "skin":  cur["skin"] = v
            elif k == "reads": cur["reads"] = v
        elif "|" in s or "｜" in s or "\t" in s:            # dong noi dung
            parts = re.split(r"\s*[|｜\t]\s*", s, maxsplit=2)
            hz = parts[0].strip()
            if not hz:
                continue
            if cur is None:
                cur = _new("")
            vi = parts[1].strip() if len(parts) > 1 else ""
            nt = parts[2].strip() if len(parts) > 2 else ""
            cur["rows"].append((hz, vi, nt))
        else:                                               # dong tran khong co '|' = tieu de bai
            cur = _new(_SEC_LABEL.sub("", s))
    return [s for s in sections if s["rows"]]


@app.route("/shorts/make", methods=["POST"])
def shorts_make():
    """Nhan danh sach cau ('汉字 | nghia' moi dong) -> sinh loat Short native.
    Moi Short thanh 1 job Short-only (upload/hen gio tai dung /yt/upload use_short)."""
    import uuid
    d = request.get_json(force=True) or {}
    raw = (d.get("lines") or "").strip()
    if not raw:
        return jsonify(error="Chưa nhập câu nào."), 400
    voice = d.get("voice") or "edge:zh-CN-XiaoxiaoNeural"
    hook = (d.get("hook") or "").strip() or None
    fmt = (d.get("format") or "flash").strip()          # 'flash' | 'quiz'
    ui_lang = (d.get("uiLang") or "auto").strip()       # ngon ngu chu co dinh (hook/nut/quiz)
    if ui_lang not in ("vi", "en", "auto"):
        ui_lang = "auto"
    bg = (d.get("bg") or "").strip() or None            # anh nen tuy chon (path da upload)
    if bg and not os.path.exists(bg):
        bg = None
    skin = (d.get("skin") or "ink").strip()             # phong cach giao dien
    import short_native as _snmod
    if skin not in _snmod.SKINS:
        skin = "ink"
    try:
        reads = max(1, min(3, int(d.get("reads") or 2)))
    except Exception:
        reads = 2
    combine = bool(d.get("combine"))                    # True: GOP tat ca cau -> 1 Short
    py_color = (d.get("py_color") or "").strip() or None   # pinyin 1 màu (None=tô thanh điệu)
    # Link gioi thieu/nghe bo tro -> tu noi vao mo ta. Mac dinh PROMO_LINK; UI co the ghi de.
    link = d.get("link")
    link = link.strip() if isinstance(link, str) else PROMO_LINK
    if "link" not in d:
        link = PROMO_LINK
    import short_native as _sn

    # ---- GOP / DAN NHIEU BAI: moi 'section' (co dong tieu de) -> 1 Short gop rieng ----
    # Dong tieu de (khong co '|') -> HOOK (chi HIEN, KHONG doc); cac dong '|' -> noi dung doc.
    sections = _parse_sections(raw)

    # TICK "Gop tat ca" -> DON HET moi cau (moi nhom) vao 1 Short duy nhat (bo qua tach nhom)
    if combine:
        rows = [r for sec in sections for r in sec["rows"]]
        if not rows:
            return jsonify(error="Không có câu hợp lệ."), 400
        hook_c = hook or (sections[0]["title"] or sections[0]["hook"] or None if sections else None)
        jid = "std_" + uuid.uuid4().hex[:10]
        try:
            r = _sn.make_short_from_lines(rows, voice=voice, hook=hook_c, out_dir=OUT,
                                          reads=reads, name=jid, lang=ui_lang, bg=bg, skin=skin,
                                          azure=_azure_for(voice), py_color=py_color)
        except Exception as e:
            traceback.print_exc()
            return jsonify(error=str(e)), 500
        fn = os.path.basename(r["file"])
        thumb = _short_thumb(fn)
        desc_i = _append_link(r["desc"], link)
        jobs[jid] = {"status": "done", "video": None, "short": fn, "thumb": thumb,
                     "short_seo": {"title": r["title"], "description": desc_i},
                     "recipe": {"kind": "combine", "rows": rows, "voice": voice, "reads": reads,
                                "ui_lang": ui_lang, "bg": bg, "skin": skin, "title": None, "link": link, "py_color": py_color}}
        _save_job(jid)
        return jsonify(shorts=[{"job_id": jid, "short": fn, "thumb": thumb, "title": r["title"],
                                "description": desc_i, "hanzi": rows[0][0], "pinyin": "",
                                "viet": rows[0][1], "hook": hook_c or "",
                                "count": r["count"], "dur": r["dur"]}])

    # KHONG tick gop: co nhieu nhom/tieu de -> tu tach moi nhom 1 Short
    multi = len(sections) > 1 or any(
        s["title"] or s["title_ov"] or s["skin"] or s["hook"] for s in sections)
    if multi:
        if not sections:
            return jsonify(error="Không có câu hợp lệ."), 400
        out = []
        for sec in sections:
            rows = sec["rows"]
            if not rows:
                continue
            hook_i = sec["hook"] or sec["title"] or hook          # tieu de -> hook (chi hien)
            skin_i = sec["skin"] if sec["skin"] in _snmod.SKINS else skin
            title_i = sec["title_ov"] or (
                f'{sec["title"]} | Tiếng Trung mỗi ngày #Shorts' if sec["title"] else None)
            try:
                reads_i = max(1, min(3, int(sec["reads"]))) if sec["reads"] else reads
            except Exception:
                reads_i = reads
            jid = "std_" + uuid.uuid4().hex[:10]
            try:
                r = _sn.make_short_from_lines(rows, voice=voice, hook=hook_i, out_dir=OUT,
                                              reads=reads_i, name=jid, lang=ui_lang, bg=bg,
                                              skin=skin_i, title=title_i, azure=_azure_for(voice), py_color=py_color)
            except Exception as e:
                traceback.print_exc()
                out.append({"error": str(e), "hanzi": rows[0][0]})
                continue
            fn = os.path.basename(r["file"])
            thumb = _short_thumb(fn)
            desc_i = _append_link(r["desc"], link)
            jobs[jid] = {"status": "done", "video": None, "short": fn, "thumb": thumb,
                         "short_seo": {"title": r["title"], "description": desc_i},
                         "recipe": {"kind": "combine", "rows": rows, "voice": voice,
                                    "reads": reads_i, "ui_lang": ui_lang, "bg": bg,
                                    "skin": skin_i, "title": title_i, "link": link, "py_color": py_color}}
            _save_job(jid)
            out.append({"job_id": jid, "short": fn, "thumb": thumb, "title": r["title"],
                        "description": desc_i, "hanzi": rows[0][0],
                        "pinyin": "", "viet": rows[0][1], "hook": hook_i or "",
                        "count": r["count"], "dur": r["dur"]})
        if not out:
            return jsonify(error="Không có câu hợp lệ."), 400
        return jsonify(shorts=out)

    out = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        cols = [c.strip() for c in re.split(r"\s*[|｜\t]\s*", line)]
        hanzi = cols[0]
        viet = cols[1] if len(cols) > 1 else ""
        note = cols[2] if len(cols) > 2 else ""             # cot 3 tuy chon: ghi chu cach dung
        if not hanzi:
            continue
        jid = "std_" + uuid.uuid4().hex[:10]
        try:
            r = _render_one_short(fmt, cols, hook, voice, reads, ui_lang, bg, skin, jid, py_color=py_color)
        except Exception as e:
            traceback.print_exc()
            out.append({"error": str(e), "hanzi": hanzi})
            continue
        fn = os.path.basename(r["file"])
        thumb = _short_thumb(fn)
        desc_i = _append_link(r["desc"], link)
        jobs[jid] = {"status": "done", "video": None, "short": fn, "thumb": thumb,
                     "short_seo": {"title": r["title"], "description": desc_i},
                     "recipe": {"kind": "line", "fmt": fmt, "cols": cols, "voice": voice, "py_color": py_color,
                                "reads": reads, "ui_lang": ui_lang, "bg": bg, "skin": skin,
                                "link": link}}
        _save_job(jid)
        out.append({"job_id": jid, "short": fn, "thumb": thumb, "title": r["title"],
                    "description": desc_i, "hanzi": r["hanzi"],
                    "pinyin": r["pinyin"], "viet": r["viet"], "hook": r.get("hook", ""),
                    "dur": r["dur"]})
    if not out:
        return jsonify(error="Không có câu hợp lệ."), 400
    return jsonify(shorts=out)

@app.route("/yt/make_short/<job_id>", methods=["POST"])
def yt_make_short(job_id):
    """Cat lai video Short tai moc thoi gian nguoi dung chon (at='mm:ss').
    at rong -> tu chon doan diem cao nhat. Ghi de file Short cu, cap nhat job."""
    job = jobs.get(job_id) or _job_from_disk(job_id)
    if not job or not job.get("video"):
        return jsonify(error="Không tìm thấy video của phiên này."), 400
    jobs[job_id] = job                              # cache lai vao RAM
    video_path = os.path.join(OUT, job["video"])
    if not os.path.exists(video_path):
        return jsonify(error="File video không tồn tại."), 400
    d = request.get_json(force=True) or {}
    at = (d.get("at") or "").strip() or None
    try:
        import short_native as _shorts
        sh = _shorts.make_short(video_path, OUT, at=at)
        job["short"] = os.path.basename(sh["file"])
        job["short_seo"] = {"title": sh["title"], "description": sh["desc"]}
        _save_job(job_id)
        return jsonify(short=job["short"], title=sh["title"],
                       description=sh["desc"], start=sh["start"], dur=sh["dur"])
    except Exception as e:
        traceback.print_exc()
        return jsonify(error=str(e)), 500

@app.route("/yt/upload", methods=["POST"])
def yt_upload():
    d = request.get_json(force=True)
    job = jobs.get(d.get("job_id"))
    if not job:
        return jsonify(error="Không tìm thấy phiên này."), 400
    if d.get("use_short"):                       # dang ban Short 9:16 (co the la Short-only, khong video dai)
        short_name = job.get("short")
        if not short_name:
            return jsonify(error="Phiên này chưa có video Short."), 400
        video_path = os.path.join(OUT, short_name)
    else:
        if not job.get("video"):
            return jsonify(error="Không tìm thấy video của phiên này."), 400
        video_path = os.path.join(OUT, job["video"])
    if not os.path.exists(video_path):
        return jsonify(error="File video không tồn tại."), 400
    try:
        res = youtube_upload.upload(
            d["channel"], video_path,
            title=d.get("title", ""), description=d.get("description", ""),
            tags=d.get("tags", ""), privacy=d.get("privacy", "public"),
            category=d.get("category", "27"),
            publish_at=d.get("publish_at"))
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

# =========================== TRANG DUNG PHIM (/film) ===========================
def _parse_film(content):
    """Tach content.md phim -> (voices_spec, scenes). Moi scene: {label, subs:[{hz,vi}]}.
    '#' = ranh gioi canh; '@voices' = khai giong; '---' = het (phu luc bo qua)."""
    import lesson_parser as lp
    voices_spec, scenes, cur = {}, [], None
    for raw in (content or "").splitlines():
        line = raw.strip()
        if lp._HR_RE.match(line):
            break
        if not line:
            continue
        if line.startswith("@"):
            key, _, val = line[1:].partition(" ")
            k = key.strip().lower()
            if k == "voices":
                voices_spec = lp._parse_voices(val)
            elif k == "bg" and cur is not None:
                cur["bg"] = val.strip()          # prompt ảnh nền AI riêng của cảnh (EN, có thể tả nhân vật)
            continue
        if line.startswith("#"):
            cur = {"label": line.lstrip("#").strip(), "subs": []}
            scenes.append(cur)
            continue
        if cur is None:
            cur = {"label": "", "subs": []}
            scenes.append(cur)
        hz, _, vi = line.partition("|")
        hz, vi = hz.strip(), vi.strip()
        # TAG CẢM XÚC đầu dòng: '{sad}汉字…' -> đọc buồn (Azure express-as). Bóc khỏi hz hiển thị.
        emo_name = ""
        m = re.match(r"^\{([a-zA-Z]+)\}\s*", hz)
        if m:
            emo_name = m.group(1).lower()
            hz = hz[m.end():].strip()
        if hz or vi:
            cur["subs"].append({"hz": hz, "vi": vi, "emo_name": emo_name})
    scenes = [s for s in scenes if s["subs"]]
    return voices_spec, scenes


def _film_char_voices(spec, overrides=None, prefer_azure=False, lang="zh"):
    """spec {ten: 'nam'/'nữ'/ma-giong} + overrides {ten: voice} -> {ten: voice cu the}.
    prefer_azure=True (co key): cast nhan vat bang giong Azure (dien cam xuc express-as duoc).
    Nguoc lai gan giong edge free, moi nhan vat 1 giong. lang='vi': cast giong Viet."""
    import lesson_parser as lp
    AZ_F = ["azure:zh-CN-XiaoxiaoNeural", "azure:zh-CN-XiaoyiNeural", "azure:zh-CN-XiaomengNeural"]
    AZ_M = ["azure:zh-CN-YunxiNeural", "azure:zh-CN-YunjianNeural", "azure:zh-CN-YunyangNeural"]
    if lang == "vi":
        VF = ["edge:vi-VN-HoaiMyNeural", "vieneu:Ngọc Linh", "vieneu:Thục Đoan"]
        VM = ["edge:vi-VN-NamMinhNeural", "vieneu:Thanh Bình", "vieneu:Xuân Vĩnh"]
    else:
        VF = AZ_F if prefer_azure else ["edge:" + v for v in lp.VOICES_F]
        VM = AZ_M if prefer_azure else ["edge:" + v for v in lp.VOICES_M]
    out, fi, mi = {}, 0, 0
    for name, v in (spec or {}).items():
        vl = (v or "").strip().lower()
        if vl in ("nữ", "nu", "female", "f", "女", "gái", "gai"):
            out[name] = VF[fi % len(VF)]; fi += 1
        elif vl in ("nam", "male", "m", "男", "trai"):
            out[name] = VM[mi % len(VM)]; mi += 1
        elif v:                                  # ma giong cu the (edge:/azure:/zh-CN-...)
            out[name] = v if ":" in v else ("edge:" + v)
    for name, v in (overrides or {}).items():    # override tay tu UI (uu tien cao nhat)
        if (v or "").strip():
            out[name] = v.strip()
    return out


@app.route("/film")
def film_page():
    akey, _ = load_azure()
    return render_template("film.html", edge_voices=EDGE_VOICES, promo_link=PROMO_LINK,
                           azure_voices=AZURE_VOICES, azure_ready=bool(akey),
                           gemini_ready=bool(load_gemini()),
                           together_ready=bool(_load_together_key()),
                           vi_voices=VI_VOICES, vieneu_voices=VIENEU_VOICES,
                           eleven_voices=ELEVEN_VOICES, eleven_ready=bool(load_eleven()),
                           fpt_voices=FPT_VOICES, fpt_ready=bool(load_fpt()),
                           vbee_voices=VBEE_VOICES,
                           vbee_ready=all(load_vbee()))


@app.route("/ttskey", methods=["POST"])
def ttskey_save():
    """Luu nhanh key TTS tu trang phim: {engine: 'gemini'|'eleven', key: '...'}."""
    d = request.get_json(force=True) or {}
    eng, key = (d.get("engine") or "").strip(), (d.get("key") or "").strip()
    if not key:
        return jsonify(error="Chưa nhập key."), 400
    if eng == "gemini":
        save_gemini(key)
    elif eng == "eleven":
        save_eleven(key)
    elif eng == "fpt":
        save_fpt(key)
    elif eng == "vbee":
        app_id = (d.get("app_id") or "").strip()
        if not app_id:
            return jsonify(error="Vbee cần cả token và app_id."), 400
        save_vbee(key, app_id)
    else:
        return jsonify(error="Engine lạ: " + eng), 400
    return jsonify(ok=True)


@app.route("/film/parse", methods=["POST"])
def film_parse():
    """Nhan content.md -> tra ve danh sach canh (label + subs) + ten nhan vat @voices.
    De UI hien 1 o upload nen cho MOI canh + xem truoc phu de."""
    d = request.get_json(force=True) or {}
    spec, scenes = _parse_film(d.get("content") or "")
    if not scenes:
        return jsonify(error="Chưa tách được cảnh nào. Cần dòng '# Cảnh N — ...' và câu '汉字 | nghĩa'."), 400
    import film as _fl
    out = [{"label": s["label"] or f"Cảnh {i+1}", "count": len(s["subs"]),
            "subs": s["subs"], "prompt": s.get("bg") or _film_bg_base(s["label"]),
            "sfx": _sfx_suggest(s["label"])}
           for i, s in enumerate(scenes)]
    kinds = {k: v[0] for k, v in _fl.AMBIENCES.items()}
    has_bg = any(s.get("bg") for s in scenes)
    return jsonify(scenes=out, voices=list(spec.keys()), sfx_kinds=kinds, has_bg=has_bg)


# goi y SFX khong khi tu boi canh cua canh (tu khoa tieng Viet trong label)
_SFX_MAP = [
    (("cà phê", "cafe", "quán", "nhà hàng", "chợ", "tiệm"), "cafe"),
    (("đường", "phố", "xe", "bến", "ga", "sân bay"), "street"),
    (("mưa",), "rain"),
    (("biển", "bãi", "đảo"), "ocean"),
    (("công viên", "vườn", "rừng", "núi", "cánh đồng", "gió"), "wind"),
    (("đêm", "tối", "khuya"), "night"),
    (("suối", "sông", "hồ", "thác"), "stream"),
    (("nhà", "phòng", "văn phòng", "lớp", "trường", "bệnh viện"), "room"),
]

def _sfx_suggest(label):
    low = (label or "").lower()
    for keys, kind in _SFX_MAP:
        if any(k in low for k in keys):
            return kind
    return ""


def _resolve_sfx(spec, label):
    """spec tu UI: '' / 'none' / 'auto' / ten-kind / path file upload -> path file (hoac '')."""
    import film as _fl
    spec = (spec or "").strip()
    if not spec or spec == "none":
        return ""
    if spec == "auto":
        spec = _sfx_suggest(label)
        if not spec:
            return ""
    if spec in _fl.AMBIENCES:
        try:
            return _fl.ensure_ambience(spec)
        except Exception:
            traceback.print_exc()
            return ""
    return spec if os.path.exists(spec) else ""


# style nền cảnh — CÂU MÔ TẢ TỰ NHIÊN (Sana/FLUX ra đẹp hơn keyword-soup nhiều)
_BG_STYLES = {
    "2d":    ("A warm, highly detailed flat 2D storybook illustration of {S}. "
              "Soft rounded shapes, cozy cream and amber colour palette, gentle golden lighting, "
              "nostalgic peaceful atmosphere, beautiful composition, masterpiece, no people, no text."),
    "anime": ("A beautiful Studio Ghibli style anime background painting of {S}. "
              "Painterly hand-drawn detail, warm golden hour light, lush and cozy, soft shadows, "
              "dreamy nostalgic mood, masterpiece, highly detailed, no people, no text."),
    "photo": ("A cinematic photograph of {S}. Realistic, shallow depth of field, soft natural window "
              "light, warm film-grain colour grade, atmospheric, professional composition, no people, no text."),
    "ink":   ("A traditional Chinese ink wash painting (shuimo) of {S}. Elegant minimal brushwork, "
              "muted ink tones, poetic empty space, serene mood, masterpiece, no people, no text."),
    # PHIM KỂ CHUYỆN: prompt cảnh tự tả nhân vật (@bg trong kịch bản) -> KHÔNG ép 'no people',
    # không ép 'empty establishing shot'; chỉ khoá chất tranh + cấm chữ.
    "story": ("{S}. 2D flat cartoon storybook illustration, thick clean outlines, expressive characters, "
              "cinematic composition, masterpiece, no text, no watermark."),
}
# dịch nhanh vài từ bối cảnh VN -> EN (đủ để Pollinations bắt đúng khung cảnh)
_LOC_VN2EN = {
    "quán cà phê": "cozy cafe interior", "cà phê": "cafe", "quán ăn": "small restaurant interior",
    "nhà hàng": "restaurant interior", "đường phố": "city street", "phố": "street",
    "công viên": "park", "nhà": "living room interior", "phòng": "room interior",
    "văn phòng": "office", "trường": "school", "lớp học": "classroom", "chợ": "market",
    "ga": "train station", "bến xe": "bus station", "sân bay": "airport", "biển": "seaside",
    "núi": "mountain landscape", "vườn": "garden", "bếp": "kitchen", "phòng khách": "living room",
    "quán trà": "tea house", "sáng": "morning light", "chiều": "afternoon light",
    "tối": "night", "đêm": "night", "hoàng hôn": "sunset", "mưa": "rainy",
}

def _film_bg_base(label):
    """Mô tả bối cảnh (EN) từ label cảnh — CHƯA gồm phong cách (style ghép sau)."""
    lab = re.sub(r"^\s*C[ảa]nh\s*\d+\s*[—\-–:·]*\s*", "", (label or "").strip(), flags=re.IGNORECASE).strip()
    low = lab.lower()
    hits = [en for vn, en in _LOC_VN2EN.items() if vn in low]
    return ", ".join(dict.fromkeys(hits)) if hits else (lab or "quiet indoor scene")


def _load_together_key():
    """Key Together.ai từ together_config.json {api_key|key} hoặc env TOGETHER_API_KEY."""
    p = os.path.join(ROOT, "together_config.json")
    if os.path.exists(p):
        try:
            dd = json.load(open(p, encoding="utf-8"))
            k = dd.get("api_key") or dd.get("key")
            if k:
                return k.strip()
        except Exception:
            pass
    return (os.environ.get("TOGETHER_API_KEY") or "").strip()


def _ai_together(prompt, w=1024, h=576):
    """Together.ai FLUX.1 [schnell] Free -> PNG bytes. Cần key (free tier)."""
    import urllib.request, base64
    key = _load_together_key()
    if not key:
        raise RuntimeError("chưa có key Together (together_config.json)")
    body = json.dumps({"model": "black-forest-labs/FLUX.1-schnell-Free", "prompt": prompt,
                       "width": w, "height": h, "steps": 4, "n": 1,
                       "response_format": "b64_json"}).encode()
    req = urllib.request.Request("https://api.together.xyz/v1/images/generations", data=body,
                                 headers={"Authorization": "Bearer " + key,
                                          "Content-Type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req, timeout=150).read())
    dd = (resp.get("data") or [{}])[0]
    if dd.get("b64_json"):
        return base64.b64decode(dd["b64_json"])
    if dd.get("url"):
        return urllib.request.urlopen(dd["url"], timeout=150).read()
    raise RuntimeError("Together không trả ảnh: " + str(resp)[:200])


def _ai_imagen(prompt):
    """Google Imagen 4 (Gemini API :predict) -> PNG bytes. Cần key có quyền Imagen."""
    import ai_visuals
    return ai_visuals.gen_gemini_image(prompt, aspect="16:9")


def _ai_gemini_nano(prompt):
    """Google Gemini image (Nano Banana, gemini-2.5-flash-image) -> PNG bytes. Free tier."""
    import urllib.request, base64
    key = load_gemini()
    if not key:
        raise RuntimeError("chưa có key Gemini (gemini_config.json)")
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           "gemini-2.5-flash-image:generateContent?key=" + key)
    body = json.dumps({"contents": [{"parts": [{"text": prompt + ", 16:9 wide cinematic aspect ratio"}]}]}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req, timeout=120).read())
    for c in resp.get("candidates", []):
        for part in (c.get("content", {}).get("parts") or []):
            inl = part.get("inlineData") or part.get("inline_data")
            if inl and inl.get("data"):
                return base64.b64decode(inl["data"])
    raise RuntimeError("Gemini image không trả ảnh: " + str(resp)[:200])


_AI_ENGINES = {                                       # backend -> (nhãn hiển thị, hàm -> PNG bytes)
    "together": ("Together FLUX", _ai_together),
    "imagen":   ("Imagen 4",      _ai_imagen),
    "gemini":   ("Gemini Nano",   _ai_gemini_nano),
}


@app.route("/film/ai_bg", methods=["POST"])
def film_ai_bg():
    """Tạo 1 ảnh nền AI cho 1 cảnh. backend: pollinations | together | imagen | gemini.
    Engine cần-key lỗi/thiếu key -> tự rơi về Pollinations (không bao giờ kẹt)."""
    import film as _fl, shutil
    d = request.get_json(force=True) or {}
    style = (d.get("style") or "2d").strip()
    seed = int(d.get("seed") or 0)
    backend = (d.get("backend") or "pollinations").strip().lower()
    base = (d.get("prompt") or "").strip() or _film_bg_base(d.get("label", ""))
    tmpl = _BG_STYLES.get(style, _BG_STYLES["2d"])
    suffix = "" if style == "story" else " (empty establishing shot, wide angle)"
    prompt = tmpl.replace("{S}", base + suffix)
    dst, used, note = None, "pollinations", ""

    if backend in _AI_ENGINES:
        label, fn = _AI_ENGINES[backend]
        try:
            png = fn(prompt + ", no text, no watermark")
            name = f"filmai_{int(time.time()*1000)}_{seed}.png"
            dst = os.path.join(UP, name)
            with open(dst, "wb") as f:
                f.write(png)
            used = backend
        except Exception as e:
            traceback.print_exc()
            note = f"{label} lỗi → dùng Pollinations. ({str(e)[:110]})"

    if not dst:                                       # Pollinations (mặc định / fallback)
        try:
            img = _fl.ai_scene_bg(prompt, seed=seed)
        except Exception as e:
            traceback.print_exc()
            return jsonify(error="Tạo ảnh AI lỗi: " + str(e)), 500
        name = f"filmai_{int(time.time()*1000)}_{seed}.jpg"
        dst = os.path.join(UP, name)
        shutil.copyfile(img, dst)

    return jsonify(path=dst, prompt=prompt, url="/filmimg/" + os.path.basename(dst),
                   backend=used, note=note)


@app.route("/filmimg/<path:fn>")
def filmimg(fn):
    """Xem preview ảnh nền đã tạo/upload (trong uploads/)."""
    return send_from_directory(UP, fn, as_attachment=False)


def _short_thumb(short_fn):
    """Trích 1 frame đầu của Short làm thumbnail (poster flashcard). Trả tên file thumb (hoặc None)."""
    import subprocess as _sp
    base = short_fn[:-4] if short_fn.lower().endswith(".mp4") else short_fn
    thumb = base + ".thumb.jpg"
    try:
        _sp.run(["ffmpeg", "-y", "-ss", "0.4", "-i", os.path.join(OUT, short_fn),
                 "-frames:v", "1", "-q:v", "3", os.path.join(OUT, thumb)],
                check=True, capture_output=True)
        return thumb if os.path.exists(os.path.join(OUT, thumb)) else None
    except Exception:
        return None


def _film_thumb(video_path, out_jpg):
    """Rut 1 khung giua lam thumbnail phim."""
    try:
        import film as _fl
        t = max(0.5, _fl._dur(video_path) * 0.4)
        subprocess = __import__("subprocess")
        subprocess.run(["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", video_path,
                        "-frames:v", "1", "-q:v", "3", out_jpg],
                       check=True, capture_output=True)
    except Exception:
        pass


def run_film_job(job_id, data):
    import film as _fl
    try:
        content = data.get("content") or ""
        spec, scenes = _parse_film(content)
        if not scenes:
            raise ValueError("Không có cảnh nào để dựng.")
        # PHIM TIENG VIET: kich ban khong co Han tu nao -> che do ke chuyen thuan Viet.
        # Chu phai nam o truong 'vi' (font Viet du dau) + 'tts' de doc; 'hz' bo trong
        # vi render_subtitle ve 'hz' bang font Han (mat dau tieng Viet).
        _cjk = re.compile(r"[一-鿿]")
        vn_mode = not any(_cjk.search(s["hz"]) for sc in scenes for s in sc["subs"])
        # tieu de + header phim (@title / @header)
        title, header = "Phim tiếng Trung", "PHIM TIẾNG TRUNG · HSK 2-3"
        if vn_mode:
            title, header = "Phim kể chuyện", "CHUYỆN CŨ KỂ LẠI"
        for ln in content.splitlines():
            s = ln.strip()
            if s.lower().startswith("@title") and " " in s:
                title = s.split(" ", 1)[1].strip()
            elif s.lower().startswith("@header") and " " in s:
                header = s.split(" ", 1)[1].strip()
        clips = data.get("clips") or []             # 1 path / canh (theo thu tu)
        base_voice = data.get("voice") or "edge:zh-CN-YunxiNeural"
        if vn_mode and "zh-CN" in base_voice:       # quen chon giong Trung -> tu doi giong ke chuyen Viet
            base_voice = "vieneu:Thái Sơn"
        if (base_voice.startswith("gemini:") and not load_gemini()) or \
           (base_voice.startswith("eleven:") and not load_eleven()) or \
           (base_voice.startswith("fpt:") and not load_fpt()):
            # chon giong can key ma chua co key -> doi giong free (de nguyen se rot xuong edge-tts va vo)
            _eng = {"g": "Gemini", "e": "ElevenLabs", "f": "FPT.AI"}[base_voice[0]]
            _old = base_voice.split(":", 1)[1]
            base_voice = "vieneu:Thái Sơn" if vn_mode else "edge:zh-CN-YunxiNeural"
            jobs[job_id]["note"] = (f"⚠ Giọng {_old} cần key {_eng} mà chưa lưu key → tạm dùng "
                                    f"{base_voice.split(':', 1)[1]}. Dán key vào ô 🔑 rồi dựng lại để đổi giọng.")
        base_az = _azure_for(base_voice)
        narrate = bool(data.get("narrate", True))
        keep_audio = bool(data.get("keep_audio", False))
        film_mode = bool(data.get("film_mode", True))
        has_azure = bool(load_azure()[0])
        cvoices = _film_char_voices(spec, data.get("char_voices") or {},
                                    prefer_azure=has_azure and not vn_mode,
                                    lang="vi" if vn_mode else "zh")

        # giọng DẪN: có Azure thì dùng Azure (diễn cảm xúc); người dùng ép edge thì vẫn tôn trọng
        narr_voice = base_voice
        if has_azure and not vn_mode and not base_voice.startswith("azure:"):
            narr_voice = "azure:zh-CN-XiaoxiaoNeural"       # giọng diễn cảm xúc giàu nhất (lyrical/sad/…)
        narr_az = _azure_for(narr_voice)
        narr_gm = _gemini_for(narr_voice)
        narr_el = _eleven_for(narr_voice)
        narr_fp = _fpt_for(narr_voice)

        # DAO DIEN THOAI + CẢM XÚC: thoại -> nhân vật đọc câu thoại; câu có tag {emo} -> diễn đúng
        # cảm xúc (Azure express-as). Câu buồn/nghẹn -> chậm + nghỉ dài hơn.
        names = list(cvoices)
        SLOW_EMO = {"sad", "sorrow", "tender", "lyrical"}
        for sc in scenes:
            for s in sc["subs"]:
                hz = s["hz"]
                emo_name = s.get("emo_name") or ""
                dlg = _fl_split(hz, names) if film_mode else None
                if dlg:
                    who, quote = dlg
                    s["tts"] = quote
                    s["pad"] = 0.4
                else:
                    who = _fl_tag(hz, names) if names else None
                    s["pad"] = 0.6
                    s.setdefault("voice", narr_voice)        # dẫn = giọng Azure ấm
                    s.setdefault("azure", narr_az)
                    s.setdefault("gemini", narr_gm)
                    s.setdefault("eleven", narr_el)
                    s.setdefault("fpt", narr_fp)
                # cảm xúc: tag tay > tự nhận theo từ khoá
                try:
                    s["emo"] = generate.emo_by_name(emo_name) if emo_name \
                        else generate.detect_emotion(s.get("tts") or hz)
                except Exception:
                    pass
                if s.get("emo", {}) and s["emo"].get("name") in SLOW_EMO:
                    s["pad"] = float(s["pad"]) + 0.6         # câu xúc động: nghỉ lâu hơn cho ngấm
                if who and who in cvoices:
                    v = cvoices[who]
                    if (v.startswith("gemini:") and not load_gemini()) or \
                       (v.startswith("eleven:") and not load_eleven()) or \
                       (v.startswith("fpt:") and not load_fpt()):
                        v = narr_voice                       # thiếu key -> về giọng dẫn
                    s["voice"] = v
                    s["azure"] = _azure_for(v)
                    s["gemini"] = _gemini_for(v)
                    s["eleven"] = _eleven_for(v)
                    s["fpt"] = _fpt_for(v)
                if vn_mode:                                  # chữ Việt -> 'vi' (font đủ dấu), đọc bằng 'tts'
                    s["tts"] = (s.get("tts") or hz)
                    s["vi"] = s.get("vi") or hz
                    s["hz"] = ""
            if sc["subs"]:                                  # BEAT cuối cảnh
                sc["subs"][-1]["pad"] = float(sc["subs"][-1].get("pad", 0.6)) + 0.8

        # dung scene model cho film.make_film (+ SFX khong khi tung canh)
        sfx_specs = data.get("sfx") or []
        scene_sfx = bool(data.get("scene_sfx", True))
        fscenes = []
        for i, sc in enumerate(scenes):
            clip = clips[i] if i < len(clips) else ""
            # YC3: client co the gui 1 LIST anh cho 1 canh -> multi-shot (doi anh theo group)
            multi = None
            if isinstance(clip, (list, tuple)):
                multi = [str(c).strip() for c in clip if c]
                clip = multi[0] if multi else ""
            spec = sfx_specs[i] if i < len(sfx_specs) else "auto"
            sfx = _resolve_sfx(spec, sc["label"]) if scene_sfx else ""
            fs = {"clip": clip, "subs": sc["subs"], "sfx": sfx,
                  "narrate": narrate, "keep_audio": keep_audio}
            if multi and len(multi) >= 2:
                fs["clips"] = multi
            fscenes.append(fs)
        clips = [fs["clip"] for fs in fscenes]          # chuan hoa lai (thumbnail dung path don)

        # NHẠC NỀN: file upload > bed cảm xúc built-in (warm/hope/sad) > không
        music_file = (data.get("music_file") or "").strip()
        bed = (data.get("music_bed") or "").strip().lower()
        if not music_file and bed and bed != "none":
            try:
                music_file = _fl.make_music_bed(bed)
            except Exception:
                traceback.print_exc()
        opts = {"voice": base_voice, "azure": base_az, "gemini": _gemini_for(base_voice),
                "eleven": _eleven_for(base_voice), "fpt": _fpt_for(base_voice),
                "sub_pinyin": bool(data.get("sub_pinyin", True)) and not vn_mode,
                "rate": data.get("rate") or "-8%",
                "music_file": music_file,
                "music_vol": float(data.get("music_vol") or 0.16),
                # nâng cấp điện ảnh
                "kenburns": bool(data.get("kenburns", True)),
                "film_mode": film_mode,               # da shot (fake coverage) + thoai dien
                "roomtone": bool(data.get("roomtone", True)),
                "transition": (data.get("transition") or "fade"),
                "grade": bool(data.get("grade", True)),
                "letterbox": bool(data.get("letterbox", False)),
                "duck": bool(data.get("duck", True)),
                # YC1: camera day vao nhan vat + dip-to-black chuan mau
                "focus_subject": bool(data.get("focus_subject", True)),
                "zoom_amt": (float(data["zoom_amt"]) if data.get("zoom_amt") else None),
                "dip_dur": float(data.get("dip_dur") or 0.5),
                "always_fade": bool(data.get("always_fade", True)),
                # YC2: lop hat bay overlay (none|firefly|dust|auto)
                "particles": (data.get("particles") or "auto"),
                # YC3: nhieu anh / canh (multi-shot) — film.py doc scene["clips"];
                # 2 opt nay cho build_film_story / client biet cau hinh sinh anh phu
                "shots_per_scene": (data.get("shots_per_scene") or "auto"),
                "auto_shots": bool(data.get("auto_shots", True)),
                "title_card": bool(data.get("title_card", True)),
                "end_card": bool(data.get("end_card", True)),
                "film_title": title, "film_header": header}

        total = len(fscenes)
        jobs[job_id].update(total=total + 2, label="Đang dựng cảnh 1...")

        # NANG CAP DIEN ANH: co cv2 -> chuyen canh bake vao duoi canh (plan_transitions),
        # join = cut -> TD=0, timing SRT/chapters TUYET DOI. Thieu cv2 -> xfade cu.
        if _fl._HAVE_CV2 and opts["transition"] != "none":
            _fl.plan_transitions(fscenes, opts)
            opts["transition"] = "none"

        seg_videos, seg_durs, tsec = [], [], 0.0
        scene_seg_idx = []                              # segment index của mỗi CẢNH (để tính chapter)
        # BÌA ĐẦU (title card)
        if opts["title_card"]:
            jobs[job_id].update(label="Dựng bìa đầu…")
            cp, cd = _fl.make_card("title", title, header, dur=3.5, opts=opts)
            seg_videos.append(cp); seg_durs.append(cd); tsec += cd
        # DỰNG TỪNG CẢNH (cập nhật tiến độ)
        for i, sc in enumerate(fscenes):
            if jobs[job_id].get("cancel"):
                raise _Cancelled()
            jobs[job_id].update(done=i, label=f"Dựng cảnh {i+1}/{total}: {scenes[i]['label'] or ''}")
            vp, dsec = _fl.make_scene(sc, opts, i)
            scene_seg_idx.append(len(seg_videos))
            seg_videos.append(vp); seg_durs.append(dsec); tsec += dsec
        # CARD "HẾT"
        if opts["end_card"]:
            cp, cd = _fl.make_card("end", "HẾT", "", dur=3.0, opts=opts)
            seg_videos.append(cp); seg_durs.append(cd); tsec += cd
        jobs[job_id].update(done=total, label="Ghép phim + chuyển cảnh + nhạc…")

        out_path = os.path.join(OUT, f"film_{job_id}.mp4")
        _fl._concat_and_music(seg_videos, opts, out_path, tsec)

        thumb = f"film_{job_id}.thumb.jpg"
        # ưu tiên 1 ảnh nền SẠCH (không dính phụ đề) làm thumbnail — chọn cảnh giữa cho "đắt"
        _clean_bg = next((c for c in (clips[len(clips)//2:] + clips) if c and os.path.exists(c)
                          and not _fl._is_video(c)), None)
        try:
            _fl.make_title_thumb(out_path, title, header, os.path.join(OUT, thumb), bg_image=_clean_bg)
        except Exception:
            traceback.print_exc()
            _film_thumb(out_path, os.path.join(OUT, thumb))       # fallback: khung trơn
        try:
            with open(out_path + ".meta.json", "w", encoding="utf-8") as f:
                json.dump({"title": title, "total_dur": round(tsec, 2)}, f, ensure_ascii=False)
        except Exception:
            pass
        # CHAPTERS: mốc bắt đầu mỗi segment (bù trừ transition overlap)
        TD = 0.75 if (opts["transition"] in ("fade", "dissolve") and len(seg_videos) >= 2) else 0.0
        seg_start, cum = [], 0.0
        for k, dd in enumerate(seg_durs):
            seg_start.append(max(0.0, cum - k * TD)); cum += dd
        scene_starts = [seg_start[si] for si in scene_seg_idx]
        seo = _film_seo(content, scenes, scene_starts, title, opts["title_card"])
        # SRT (hanzi / pinyin / viet) — offset mốc câu theo mốc cảnh
        try:
            seo.update(_film_srt(fscenes, scene_starts))
        except Exception:
            traceback.print_exc()
        jobs[job_id].update(status="done", video=f"film_{job_id}.mp4",
                            thumb=(thumb if os.path.exists(os.path.join(OUT, thumb)) else None),
                            seo=seo, dur=round(tsec, 1), label="Hoàn tất!")
        _save_job(job_id)
    except _Cancelled:
        jobs[job_id].update(status="cancelled", label="⏹ Đã huỷ")
    except Exception as e:
        traceback.print_exc()
        jobs[job_id].update(status="error", error=str(e), label="Lỗi: " + str(e))


def _mmss(sec):
    sec = int(round(sec)); return f"{sec//60}:{sec%60:02d}"

def _film_seo(content, scenes, scene_starts, title, has_title_card):
    """Sinh SEO YouTube cho phim: mô tả + CHAPTERS (mốc cảnh) + từ vựng (phụ lục sau ---) + hashtag."""
    # phụ lục sau dòng '---' (từ vựng/mẫu câu) -> đưa vào mô tả cho người học
    appendix = ""
    if "---" in content:
        appendix = content.split("---", 1)[1].strip()
        appendix = re.sub(r"^#+\s*", "", appendix, flags=re.MULTILINE)   # bỏ dấu ## markdown
    # chapters (YouTube cần mốc đầu 0:00)
    ch_lines = ["0:00 Mở đầu"]
    for i, sc in enumerate(scenes):
        t = scene_starts[i] if i < len(scene_starts) else 0
        lab = (sc.get("label") or f"Cảnh {i+1}").strip()
        if _mmss(t) != "0:00" or i == 0:
            ch_lines.append(f"{_mmss(t)} {lab}")
    chapters = "\n".join(dict.fromkeys(ch_lines))         # bỏ trùng mốc 0:00
    body = (f"🎬 {title}\n"
            f"Phim tình huống học tiếng Trung — luyện NGHE + đọc chữ Hán, pinyin & nghĩa (HSK 2-3).\n\n"
            f"⏱ NỘI DUNG PHIM:\n{chapters}\n")
    if appendix:
        body += f"\n📚 TỪ VỰNG & MẪU CÂU TRONG PHIM:\n{appendix}\n"
    body = _append_link(body, PROMO_LINK, lang="vi")     # phim = kênh tiếng Việt
    tags = ["học tiếng trung", "phim tiếng trung", "tiếng trung giao tiếp", "HSK",
            "luyện nghe tiếng trung", "chinese short film", "learn chinese", "chinese listening"]
    hashtags = ["#hoctiengtrung", "#phimtiengtrung", "#tiengtrung", "#HSK", "#learnchinese"]
    body += "\n\n" + " ".join(hashtags)
    return {"title": title, "titles": [title], "description": body,
            "tags": tags, "hashtags": hashtags, "privacy": "public",
            "chapters": chapters}


def _srt_time(sec):
    sec = max(0, sec); h = int(sec // 3600); m = int(sec % 3600 // 60)
    s = int(sec % 60); ms = int(round((sec - int(sec)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def _film_srt(fscenes, scene_starts):
    """Gộp _subtimes mọi cảnh -> 3 file SRT: hanzi / pinyin / viet (mốc offset theo cảnh)."""
    import style_pastel as _sp
    rows = []
    for i, sc in enumerate(fscenes):
        off = scene_starts[i] if i < len(scene_starts) else 0
        for st in sc.get("_subtimes", []):
            hz = st["hz"]
            try:
                py = " ".join(p for _, p, h in _sp.group_units(hz) if p) if hz else ""
            except Exception:
                py = ""
            rows.append((off + st["s"], off + st["e"], hz, py, st.get("vi", "")))
    def _build(idx):
        out = []
        for n, r in enumerate(rows, 1):
            txt = r[idx]
            if not txt:
                continue
            out.append(f"{n}\n{_srt_time(r[0])} --> {_srt_time(r[1])}\n{txt}\n")
        return "\n".join(out)
    return {"srt_hanzi": _build(2), "srt_pinyin": _build(3), "srt_viet": _build(4)}


def _fl_tag(hz, names):
    import lesson_parser as lp
    return lp._tag_speaker_by_names(hz, names)


def _fl_split(hz, names):
    import film as _fl
    return _fl.split_dialogue(hz, names)


@app.route("/film/make", methods=["POST"])
def film_make():
    data = request.get_json(force=True) or {}
    if not (data.get("content") or "").strip():
        return jsonify(error="Chưa dán nội dung phim."), 400
    job_id = str(int(time.time() * 1000))
    jobs[job_id] = {"done": 0, "total": 1, "label": "Đang xếp hàng...",
                    "status": "running", "video": None, "error": None, "cancel": False}
    threading.Thread(target=run_film_job, args=(job_id, data), daemon=True).start()
    return jsonify(job_id=job_id)


if __name__ == "__main__":
    print("\n  ✅ Mở trình duyệt: http://127.0.0.1:5001\n")
    app.run(host="127.0.0.1", port=5001, debug=False, threaded=True)
