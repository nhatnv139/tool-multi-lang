# -*- coding: utf-8 -*-
"""film.py — Dựng PHIM: ghép nhiều CẢNH (mỗi cảnh = 1 clip video/ảnh) thành 1 tập.
Mỗi cảnh: giữ TIẾNG gốc của clip (tuỳ chọn) + phụ đề (Hán / pinyin / nghĩa) + (tuỳ chọn) lời dẫn TTS.
Nối các cảnh -> tập phim, thêm nhạc nền. KHÔNG có layout học (phim thuần + phụ đề dưới)."""
import os, re, shutil, subprocess, hashlib
from PIL import Image, ImageDraw
import style_pastel as sp
from pypinyin import pinyin as _py, Style as _PyStyle

W, H, FPS = 1920, 1080, 30
_HERE = os.path.dirname(os.path.abspath(__file__))
FILM = os.path.join(_HERE, "assets", "film")
os.makedirs(FILM, exist_ok=True)
def _load_env(path):
    """Doc .env canh file nay vao os.environ (khong de ghi de bien da set san)."""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    except OSError:
        pass
_load_env(os.path.join(_HERE, ".env"))

def _env_flag(name, default=False):
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")

# FILM_SUB_FADE=1 -> phu de fade in/out (dep hon, cham hon: +2 filter/cau).
# Mac dinh TAT: chu hien/an tuc thi, filter graph gon -> encode nhanh hon.
SUB_FADE = _env_flag("FILM_SUB_FADE", False)

# FILM_FADE_FOCUS=1 -> dip-to-black dung mask radial quanh nhan vat (nhan vat tat sau cung).
# Mac dinh TAT: dip phang da chuan style, mask ton ~2-3ms/frame fade (c1, c3).
FADE_FOCUS = _env_flag("FILM_FADE_FOCUS", False)

X264 = ["-c:v", "libx264", "-preset", "fast", "-crf", "20"]
# Segment CANH/CARD la file TRUNG GIAN (bi re-encode lai o _join_video khi ghep + grade)
# -> encode nhanh + crf thap hon de khong mat chat qua 2 lan nen. veryfast ~3x medium.
X264_SEG = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"]
_VID_EXT = (".mp4", ".mov", ".webm", ".mkv", ".m4v", ".avi")

_TONE = {1: (255, 118, 118), 2: (255, 194, 92), 3: (126, 214, 126),
         4: (122, 176, 255), 0: (222, 222, 228)}

# ---------- SFX KHONG KHI (ambience) — tong hop DSP, khong can mang/key ----------
SFX_DIR = os.path.join(FILM, "sfx")
os.makedirs(SFX_DIR, exist_ok=True)

# moi loai: (nhan hien thi, filter_complex sinh 60s ket thuc bang [a])
AMBIENCES = {
    "cafe":   ("☕ Quán (rì rầm)",
               "anoisesrc=r=44100:color=pink:seed=6:d=60,bandpass=f=700:w=900,"
               "tremolo=f=0.6:d=0.45,volume=0.4[w];"
               "anoisesrc=r=44100:color=brown:seed=12:d=60,lowpass=f=400,volume=0.3[r];"
               "[w][r]amix=inputs=2:normalize=0[a]"),
    "street": ("🚗 Phố xe cộ",
               "anoisesrc=r=44100:color=brown:seed=3:d=60,lowpass=f=380,volume=0.7[low];"
               "anoisesrc=r=44100:color=pink:seed=9:d=60,bandpass=f=900:w=600,"
               "tremolo=f=0.15:d=0.5,volume=0.12[mid];"
               "[low][mid]amix=inputs=2:normalize=0[a]"),
    "rain":   ("🌧 Mưa",
               "anoisesrc=r=44100:color=white:seed=11:d=60,highpass=f=350,lowpass=f=8000,"
               "tremolo=f=0.3:d=0.12,volume=0.5[a]"),
    "ocean":  ("🌊 Biển",
               "anoisesrc=r=44100:color=brown:seed=5:d=60,lowpass=f=850,"
               "tremolo=f=0.1:d=0.85,volume=0.9[a]"),
    "wind":   ("🍃 Gió / công viên",
               "anoisesrc=r=44100:color=pink:seed=8:d=60,lowpass=f=520,highpass=f=60,"
               "tremolo=f=0.2:d=0.6,volume=0.5[a]"),
    "night":  ("🦗 Đêm (dế kêu)",
               "anoisesrc=r=44100:color=brown:seed=2:d=60,lowpass=f=300,volume=0.25[n];"
               "sine=f=4300:d=60,tremolo=f=12:d=1,volume=0.055[c1];"
               "sine=f=5200:d=60,tremolo=f=8.5:d=1,volume=0.04[c2];"
               "[n][c1][c2]amix=inputs=3:normalize=0,volume=1.5[a]"),
    "stream": ("💧 Suối / nước chảy",
               "anoisesrc=r=44100:color=white:seed=4:d=60,highpass=f=600,lowpass=f=4200,"
               "tremolo=f=1.7:d=0.25,volume=0.4[a]"),
    "room":   ("🏠 Phòng yên tĩnh",
               "anoisesrc=r=44100:color=brown:seed=7:d=60,lowpass=f=450,volume=0.4[a]"),
}

# ---------- NHAC NEN CAM XUC — music box arpeggio (sinh DSP, khong can nhac ban quyen) ----------
# Hop am C - G - Am - F (vong hoa am "lay nuoc mat"), moi hop 4 not arpeggio.
_NOTE = {"C4":261.63,"D4":293.66,"E4":329.63,"F4":349.23,"G4":392.00,"A4":440.00,"B4":493.88,
         "C5":523.25,"G3":196.00,"A3":220.00,"B3":246.94,"F3":174.61,"D5":587.33,"E5":659.25}
_MUSIC = {
    # ten: (list not arpeggio, list not PAD nen ngan)
    "warm":  (["C4","E4","G4","E4","G3","B3","D4","B3","A3","C4","E4","C4","F3","A3","C4","A3"],
              ["C4","E4","G4"]),
    "hope":  (["C4","G4","E5","G4","G3","D4","B4","D4","A3","E4","C5","E4","F3","C4","A4","C4"],
              ["C4","E4","G4"]),
    "sad":   (["A3","C4","E4","C4","F3","A3","C4","A3","C4","E4","G4","E4","G3","B3","D4","B3"],
              ["A3","C4","E4"]),
}

def make_music_bed(kind="warm", out_path=None):
    """Sinh 1 doan nhac box ~8s (loop duoc) theo vong hoa am cam xuc. Tra path m4a."""
    seq, pad = _MUSIC.get(kind, _MUSIC["warm"])
    out_path = out_path or os.path.join(SFX_DIR, "bed_" + kind + ".m4a")
    if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        return out_path
    NL = 0.5                                            # do dai 1 not
    inputs, fc, labs = [], [], []
    for i, n in enumerate(seq):                         # tung not: sine + envelope pluck
        inputs += ["-f", "lavfi", "-i", f"sine=frequency={_NOTE[n]}:duration={NL}"]
        fc.append(f"[{i}:a]afade=t=in:d=0.01,afade=t=out:st=0.09:d={NL-0.09:.2f},volume=0.5[n{i}]")
        labs.append(f"[n{i}]")
    fc.append("".join(labs) + f"concat=n={len(seq)}:v=0:a=1[arp]")
    # PAD nen am (hop am giu, rat nho) cho day dan
    total = len(seq) * NL
    pj = len(seq)
    padlabs = []
    for j, n in enumerate(pad):
        inputs += ["-f", "lavfi", "-i", f"sine=frequency={_NOTE[n]/2:.2f}:duration={total:.2f}"]
        fc.append(f"[{pj+j}:a]volume=0.10,tremolo=f=3:d=0.2[p{j}]"); padlabs.append(f"[p{j}]")
    fc.append("".join(padlabs) + f"amix=inputs={len(pad)}:normalize=0[pad]")
    # tron arpeggio + pad -> reverb am + lowpass mem
    fc.append("[arp][pad]amix=inputs=2:normalize=0,aecho=0.8:0.85:110|220:0.35|0.2,"
              "lowpass=f=3400,volume=1.5[a]")
    subprocess.run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc),
                    "-map", "[a]", "-t", f"{total:.2f}", "-c:a", "aac", "-b:a", "160k",
                    "-ar", "44100", "-ac", "2", out_path], check=True, capture_output=True)
    return out_path


def ensure_ambience(kind):
    """Sinh (1 lan, cache) file khong khi 60s cho 'kind'. Tra path m4a."""
    if kind not in AMBIENCES:
        return ""
    p = os.path.join(SFX_DIR, kind + ".m4a")
    if os.path.exists(p) and os.path.getsize(p) > 0:
        return p
    subprocess.run(["ffmpeg", "-y", "-filter_complex", AMBIENCES[kind][1],
                    "-map", "[a]", "-t", "60", "-c:a", "aac", "-b:a", "128k",
                    "-ar", "44100", "-ac", "2", p], check=True, capture_output=True)
    return p


# ---------- THOAI (dialogue) — tach loi thoai ra khoi menh de tuong thuat ----------
# '小明："你好!"'                (nhan truc tiep)
_DLG_LABEL = re.compile(r'^([一-鿿A-Za-z]{1,8})\s*[:：]\s*[«"“「『]?(.+?)[»"”」』]?\s*$')
# '小明高兴地说："你好!"'        (menh de + dong tu noi + trich dan)
_DLG_SAY = re.compile(r'^(.{1,16}?[说问道喊叫答想])\s*[:：]\s*[«"“「『](.+?)[»"”」』]\s*$')

def split_dialogue(hz, names):
    """Neu dong LA loi thoai -> (ten_nhan_vat|None, cau_thoai). Nguoc lai None.
    PHIM: nhan vat chi NOI cau thoai; phan 'X vui ve noi:' khong doc len (show, don't tell)."""
    hz = (hz or "").strip()
    m = _DLG_LABEL.match(hz)
    if m and m.group(1) in (names or []):
        return m.group(1), m.group(2).strip()
    m = _DLG_SAY.match(hz)
    if m:
        lead, quote = m.group(1), m.group(2).strip()
        who = next((n for n in (names or []) if lead.startswith(n)), None)
        return who, quote
    return None


# ---------- FAKE COVERAGE — cat 1 anh nen thanh nhieu SHOT may quay ----------
def _shot_geom(iw, ih, k, i, sub=None):
    """Toa do crop shot k cua canh i — DETERMINISTIC, dung chung cho render segment
    va cho viec tinh truoc frame dau cua canh ke tiep (transition zoom-blend).
    sub=(sx,sy) toa do anh goc (a12): neo shot quanh NHAN VAT THAT thay heuristic cung."""
    base_w = min(iw, ih * W // H)          # cua so 16:9 lon nhat trong anh
    base_h = base_w * H // W
    m = (k + i) % 4
    if sub:
        ox0 = min(max(sub[0] / float(iw), 0.30), 0.70)
        oy0 = min(max(sub[1] / float(ih), 0.32), 0.50)
    else:
        ox0 = oy0 = None
    # oy keo LEN TREN (0.40-0.45): mat nhan vat luon o nua tren anh,
    # crop lech xuong (0.54-0.56 cu) se cat cut dau khi vao trung/can canh.
    if m == 0:   f, ox, oy = 1.00, 0.50, 0.50                          # TOAN canh (wide)
    elif m == 1: f, ox, oy = 0.80, (ox0 - 0.08 if ox0 else 0.40), (oy0 or 0.45)  # TRUNG - lech trai
    elif m == 2: f, ox, oy = 0.80, (ox0 + 0.08 if ox0 else 0.60), (oy0 or 0.45)  # TRUNG - lech phai
    else:        f, ox, oy = 0.70, (ox0 or 0.50), (max(0.32, oy0 - 0.03) if oy0 else 0.40)  # CAN
    cw, ch = int(base_w * f), int(base_h * f)
    x0 = max(0, min(iw - cw, int(ox * iw) - cw // 2))
    y0 = max(0, min(ih - ch, int(oy * ih) - ch // 2))
    return x0, y0, cw, ch


def _shot_crops(img_path, n, i, tmp, sub=None):
    """1 anh -> n shot (toan canh / trung / can, dao goc trai-phai) nhu phim co nhieu cu may."""
    im = Image.open(img_path).convert("RGB")
    iw, ih = im.size
    outs = []
    for k in range(n):
        x0, y0, cw, ch = _shot_geom(iw, ih, k, i, sub=sub)
        # save 2x (supersample cho zoompan): crop toa do nguyen pixel -> zoom buoc <1px gay giat nac
        crop = im.crop((x0, y0, x0 + cw, y0 + ch)).resize((W * 2, H * 2), Image.LANCZOS)
        p = os.path.join(FILM, f"_shot_{i}_{k}.jpg")
        crop.save(p, quality=90)
        outs.append(p); tmp.append(p)
    return outs


# ---------- MULTI-SHOT (YC3) — moi group dung 1 ANH KHAC trong scene["clips"] ----------
def _scene_clips(scene):
    """Loc scene['clips'] -> list path ANH ton tai (>=2 moi bat multi-shot).
    DETERMINISTIC — make_scene va _next_kb_src goi chung 1 ham."""
    outs = []
    for c in ((scene or {}).get("clips") or []):
        c = (c or "").strip()
        if c and os.path.exists(c) and not _is_video(c):
            outs.append(c)
    return outs


def _clip_alloc(n_groups, n_clips):
    """Phan bo anh cho tung group: anh CHU DAO (index 0) MO va CHOT canh (nhan vat),
    anh phu xen giua; nhieu group hon anh -> lap vong anh phu, it hon -> bo anh thua."""
    if n_groups <= 1 or n_clips <= 1:
        return [0] * max(1, n_groups)
    if n_groups == 2:
        return [0, 1]                          # khong du cho chot bang chu dao -> phu chot
    mid = [1 + (k % (n_clips - 1)) for k in range(n_groups - 2)]
    return [0] + mid + [0]


def _split_groups(sub_dur, gt):
    """Chia cau LIEN TIEP thanh <=gt nhom can bang thoi luong (nhip loi thoai) —
    dung khi kich ban khong danh dau 'cut'. Chi doi NGUON ANH, khong doi tong frame."""
    total = sum(sub_dur) or 1.0
    gt = max(1, min(int(gt), len(sub_dur)))
    buckets = [[] for _ in range(gt)]
    cum = 0.0
    for k, dd in enumerate(sub_dur):
        buckets[min(gt - 1, int(cum / (total / gt)))].append(k)
        cum += dd
    return [b for b in buckets if b]


def _multi_groups(subs, sub_dur, n_clips, scene_dur):
    """Chia group cho multi-shot: uu tien danh dau 'cut' cua kich ban; khong co ->
    can bang theo nhip, du group cho moi anh + nhip doi anh ~6.5s (mau 5-10s)."""
    if any(s.get("cut") for s in subs):
        groups = [[0]]
        for k in range(1, len(subs)):
            groups.append([k]) if subs[k].get("cut") else groups[-1].append(k)
        return groups
    import math
    gt = min(len(subs), max(n_clips + 1, int(math.ceil(scene_dur / 6.5))))
    return _split_groups(sub_dur, gt)


def _clean_voice(voice):
    """Bo tien to engine ('edge:'/'azure:'/...) truoc khi goi generate.synth (giu ten HD nhieu ':')."""
    v = (voice or "zh-CN-XiaoxiaoNeural").strip()
    for p in ("azure:", "edge:", "eleven:", "gemini:", "chattts:", "fpt:"):
        if v.startswith(p):
            return v[len(p):]
    return v

def _is_video(p):
    return bool(p) and os.path.splitext(p)[1].lower() in _VID_EXT


_AIBG = os.path.join(FILM, "aibg")
os.makedirs(_AIBG, exist_ok=True)

_POLLEN_OUT = [False]   # True khi gen.pollinations.ai bao 402 (het pollen) -> dung endpoint cu

def _pollinations_token():
    """Token Pollinations (đăng ký free ở enter.pollinations.ai) -> MỞ LẠI model FLUX (đẹp hơn Sana).
    Đọc từ pollinations_config.json {token} hoặc env POLLINATIONS_TOKEN. Không có -> '' (ẩn danh = Sana)."""
    p = os.path.join(_HERE, "pollinations_config.json")
    if os.path.exists(p):
        try:
            import json as _j
            t = (_j.load(open(p, encoding="utf-8")).get("token") or "").strip()
            if t:
                return t
        except Exception:
            pass
    return (os.environ.get("POLLINATIONS_TOKEN") or "").strip()

def ai_scene_bg(prompt, path=None, seed=0, w=1280, h=720):
    """Tạo ảnh NỀN CẢNH 16:9 từ Pollinations. Có token -> FLUX (đẹp); không -> Sana (free ẩn danh).
    prompt nên là CÂU MÔ TẢ TỰ NHIÊN (không keyword-soup) — Sana/FLUX ra đẹp hơn nhiều."""
    import urllib.parse, urllib.request, hashlib
    full = prompt.strip().rstrip(",")
    if "no text" not in full.lower():
        full += ", no text, no watermark"
    tok = _pollinations_token()
    model = "flux" if tok else "sana"              # có token mới ép được flux; không thì đúng model đang phục vụ
    key = hashlib.md5((full + "|" + str(seed) + "|" + model).encode("utf-8")).hexdigest()
    path = path or os.path.join(_AIBG, key + ".jpg")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    # 2026: Pollinations tinh phi "pollen" cho endpoint moi gen.pollinations.ai (FLUX).
    # Het pollen -> 402 -> roi NGAY ve endpoint cu image.pollinations.ai (Sana, van free)
    # va nho co _POLLEN_OUT de ca batch khoi ton request 402 lap lai.
    hdrs = {"User-Agent": "Mozilla/5.0"}
    if tok:
        hdrs["Authorization"] = "Bearer " + tok
    q = f"?width={w}&height={h}&nologo=true&seed={seed}"
    cands = []
    if tok and not _POLLEN_OUT[0]:
        cands.append("https://gen.pollinations.ai/image/"
                     + urllib.parse.quote(full) + q + "&model=flux&enhance=true")
    cands.append("https://image.pollinations.ai/prompt/"
                 + urllib.parse.quote(full) + q + "&model=flux&enhance=true")
    # server co luc nghen/429 -> thu lai voi backoff (8/16/32s) thay vi chet giua phim
    last = None
    for attempt in range(4):
        for url in list(cands):
            try:
                data = urllib.request.urlopen(
                    urllib.request.Request(url, headers=hdrs), timeout=180).read()
                tmp = path + ".part"
                with open(tmp, "wb") as f:
                    f.write(data)
                Image.open(tmp).verify()           # đảm bảo là ảnh hợp lệ (không phải trang lỗi)
                os.replace(tmp, path)
                return path
            except Exception as e:
                last = e
                code = getattr(e, "code", None)
                if code == 402 and "gen.pollinations" in url:
                    _POLLEN_OUT[0] = True          # het pollen -> bo endpoint FLUX cho ca batch
                    cands.remove(url)
        if attempt < 3 and cands:
            import time as _t
            _t.sleep(8 * (2 ** attempt))
    raise last

def _tone_of(py):
    for ch in py:
        if ch in "āēīōūǖ": return 1
        if ch in "áéíóúǘ": return 2
        if ch in "ǎěǐǒǔǚ": return 3
        if ch in "àèìòùǜ": return 4
    return 0

def _flatten(hz):
    """[(char, pinyin)] — chu Han kem pinyin; ky tu khac (dau cau) pinyin rong."""
    out = []
    for seg in _py(hz, style=_PyStyle.TONE, errors=lambda x: [[c] for c in x]):
        out.append(seg[0])
    chars = list(hz)
    res, pi = [], 0
    for c in chars:
        if "一" <= c <= "鿿":
            res.append((c, out[pi] if pi < len(out) else "")); pi += 1
        else:
            res.append((c, "")); pi += 1
    return res

def _dur(p):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", p], capture_output=True, text=True)
        return float(r.stdout.strip())
    except Exception:
        return 0.0


try:
    import cv2
    import numpy as _np
    _HAVE_CV2 = True
except Exception:
    _HAVE_CV2 = False


# ---------- SUBJECT DETECT — tim nhan vat chinh trong anh (anime) ----------
_MODEL_DIR = os.path.join(FILM, "models")
os.makedirs(_MODEL_DIR, exist_ok=True)
_ANIME_XML_URL = ("https://raw.githubusercontent.com/nagadomi/"
                  "lbpcascade_animeface/master/lbpcascade_animeface.xml")
_anime_cascade = [None]        # None=chua thu, False=khong co, obj=OK (cache module)
_haar_cascades = [None]        # fallback mat nguoi that (co san trong cv2.data)


def _dl_model(url, path, magic=None):
    """Tai file model 1 lan, cache; loi mang -> None (khong chan phim)."""
    if not os.path.exists(path):
        try:
            import urllib.request
            data = urllib.request.urlopen(url, timeout=30).read()
            if magic and magic not in data[:2000]:
                raise RuntimeError("noi dung model khong hop le")
            with open(path, "wb") as f:
                f.write(data)
        except Exception:
            return None
    return path


def _get_anime_cascade():
    """Tai (1 lan, cache file) lbpcascade_animeface; loi mang / cv2>=5 (bo CascadeClassifier)
    -> bo qua tang nay."""
    if _anime_cascade[0] is not None:
        return _anime_cascade[0] or None
    if not hasattr(cv2, "CascadeClassifier"):        # OpenCV 5.x da bo API cascade
        _anime_cascade[0] = False
        return None
    p = _dl_model(_ANIME_XML_URL, os.path.join(_MODEL_DIR, "lbpcascade_animeface.xml"),
                  magic=b"<cascade")
    if not p:
        _anime_cascade[0] = False
        return None
    c = cv2.CascadeClassifier(p)
    _anime_cascade[0] = False if c.empty() else c
    return _anime_cascade[0] or None


def _get_haar_cascades():
    if _haar_cascades[0] is None:
        cs = []
        if hasattr(cv2, "CascadeClassifier"):
            try:
                for name in ("haarcascade_frontalface_default.xml",
                             "haarcascade_profileface.xml"):
                    c = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades, name))
                    if not c.empty():
                        cs.append(c)
            except Exception:
                pass
        _haar_cascades[0] = cs
    return _haar_cascades[0]


# YuNet (FaceDetectorYN, DNN co san trong cv2 5.x) — thay tang cascade khi API cascade bi bo.
# Train tren mat nguoi that: bat duoc 1 phan mat anime chinh dien; truot -> saliency lo.
_YUNET_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/"
              "face_detection_yunet/face_detection_yunet_2023mar.onnx")
_yunet = [None]


def _get_yunet():
    if _yunet[0] is not None:
        return _yunet[0] or None
    if not hasattr(cv2, "FaceDetectorYN_create"):
        _yunet[0] = False
        return None
    p = _dl_model(_YUNET_URL, os.path.join(_MODEL_DIR, "face_detection_yunet_2023mar.onnx"))
    if not p:
        _yunet[0] = False
        return None
    try:
        _yunet[0] = cv2.FaceDetectorYN_create(p, "", (320, 320), 0.6, 0.3, 500)
    except Exception:
        _yunet[0] = False
    return _yunet[0] or None


def _spectral_residual(gray, size=64):
    """Saliency Hou-Zhang 2007 bang numpy FFT (opencv-python KHONG co cv2.saliency).
    gray uint8 -> map float32 [0,1] cung shape."""
    small = cv2.resize(gray, (size, size), interpolation=cv2.INTER_AREA).astype(_np.float32)
    F = _np.fft.fft2(small)
    logamp = _np.log1p(_np.abs(F))
    avg = cv2.blur(logamp, (3, 3))                       # trung binh cuc bo 3x3
    sal = _np.abs(_np.fft.ifft2(_np.exp((logamp - avg) + 1j * _np.angle(F)))) ** 2
    sal = cv2.GaussianBlur(sal.astype(_np.float32), (9, 9), 2.5)
    sal -= sal.min()
    if sal.max() > 1e-9:
        sal /= sal.max()
    return cv2.resize(sal, (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_LINEAR)


def find_subject_center(img):
    """Tim (cx, cy, conf) nhan vat chinh — toa do ANH GOC, deterministic.
    Chuoi: animeface -> Haar frontal/profile -> saliency + prior nua tren -> (0.5W, 0.42H)."""
    im = cv2.imread(img) if isinstance(img, str) else img
    if im is None:
        return 0.0, 0.0, 0.0
    ih, iw = im.shape[:2]
    gray = cv2.equalizeHist(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY))

    def _pick(faces, base):                  # chon mat "chinh": to + gan tam + nua tren
        def _score(f):
            x, y, w, h = f
            d = abs((x + w / 2) / iw - 0.5) + max(0.0, (y + h / 2) / ih - 0.60)
            return (w * h) * (1.0 - 0.8 * min(1.0, d))
        x, y, w, h = max(faces, key=_score)
        conf = base + 0.25 * min(1.0, (w * h) / float(iw * ih) / 0.03)
        if len(faces) > 2:                   # dong nguoi -> co the chon nham
            conf = min(conf, base + 0.05)
        return float(x + w / 2), float(y + h * 0.55), float(min(0.95, conf))

    mins = (max(24, iw // 20), max(24, iw // 20))
    casc = _get_anime_cascade()
    if casc is not None:
        faces = casc.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=5, minSize=mins)
        if len(faces):
            return _pick(faces, 0.7)
    for hc in _get_haar_cascades():          # fallback mat nguoi that (cv2 4.x)
        faces = hc.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=mins)
        if len(faces):
            return _pick(faces, 0.5)
    yn = _get_yunet()                        # fallback DNN YuNet (cv2 5.x het cascade)
    if yn is not None:
        try:
            yn.setInputSize((iw, ih))
            _, dets = yn.detect(im)
            if dets is not None and len(dets):
                faces = [(int(f[0]), int(f[1]), int(f[2]), int(f[3]))
                         for f in dets if f[2] >= mins[0] * 0.6]
                if faces:
                    return _pick(faces, 0.6)
        except Exception:
            pass

    sal = _spectral_residual(gray)
    ys = _np.linspace(0, 1, ih, dtype=_np.float32)[:, None]
    sal = sal * _np.exp(-((ys - 0.38) ** 2) / (2 * 0.28 ** 2))   # prior Gauss nua tren
    mx, my = int(iw * 0.06), int(ih * 0.06)                       # bo 6% mep (watermark/vien)
    sal[:my, :] = 0; sal[-my:, :] = 0; sal[:, :mx] = 0; sal[:, -mx:] = 0
    total = float(sal.sum())
    if total > 1e-6:
        xs = _np.arange(iw, dtype=_np.float32); ys1 = _np.arange(ih, dtype=_np.float32)
        cx = float((sal.sum(axis=0) * xs).sum() / total)
        cy = float((sal.sum(axis=1) * ys1).sum() / total)
        x0, x1 = int(max(0, cx - iw / 6)), int(min(iw, cx + iw / 6))
        y0, y1 = int(max(0, cy - ih / 6)), int(min(ih, cy + ih / 6))
        focus = float(sal[y0:y1, x0:x1].sum() / total)            # do TAP TRUNG nang luong
        if focus > 0.22:
            for gx in (iw / 3, iw / 2, 2 * iw / 3):               # snap nhe rule-of-thirds
                if abs(cx - gx) < iw * 0.06:
                    cx = gx; break
            return cx, cy, min(0.6, 0.25 + focus)
    return iw * 0.5, ih * 0.42, 0.0                               # fallback = heuristic cu


_SUBJ_CACHE = {}    # path -> (cx, cy, conf, iw, ih) — DETERMINISM: _next_kb_src goi lai y het


def subject_of(img_path):
    if img_path not in _SUBJ_CACHE:
        im = cv2.imread(img_path)
        if im is None:
            _SUBJ_CACHE[img_path] = (0.0, 0.0, 0.0, 1, 1)
        else:
            cx, cy, conf = find_subject_center(im)
            _SUBJ_CACHE[img_path] = (cx, cy, conf, im.shape[1], im.shape[0])
    return _SUBJ_CACHE[img_path]


# ---------- QUY DAO CAMERA — chu ky 5 kieu nhu video mau (Chuyen Que Xua) ----------
_MOTIONS = ("push", "pan_r", "pan_l", "pushpan", "pull")


def _motion_plan(idx):
    """1 NGUON DUY NHAT cho luat chuyen dong theo chi so (b7): canh nguyen dung idx=i,
    shot dung idx=g+i, _next_kb_src dung y het -> zoomblend khong nhay hinh."""
    return _MOTIONS[idx % 5]


def _clamp_center(cx, cy, z):
    """Giu cua so crop (W/z x H/z quanh tam) nam tron trong nguon 2Wx2H — khong lo vien (a4).
    Chi clamp 2 DAU quy dao (z tang thi cua so co lai -> moi frame giua tu hop le)."""
    hw, hh = W / z, H / z
    return (min(max(cx, hw), 2 * W - hw), min(max(cy, hh), 2 * H - hh))


def _plan_camera(sx, sy, conf, mode, zoom, pan):
    """Quy dao 1 canh tren nguon 2x -> (z0, z1, c0, c1). (sx,sy) = nhan vat (toa do 2x).
    conf giam bien do keo ve nhan vat: detect yeu -> gan nhu zoom tam cu, sai khong hai."""
    AX, AY = 0.5, 0.42                       # nhan vat ket o giua ngang, 42% cao (headroom)
    cF = (float(W), float(H))                # tam nguon 2x = full frame

    def _target(zt):                         # tam crop de nhan vat roi vao anchor khi zoom zt
        s1 = zt / 2.0
        dx = (sx + (0.5 - AX) * W / s1) - cF[0]
        dy = (sy + (0.5 - AY) * H / s1) - cF[1]
        lim = 0.10 * (2 * W)                 # PAN_MAX 10% be ngang nguon
        k = min(1.0, conf) * min(1.0, lim / max(1e-6, (dx * dx + dy * dy) ** 0.5))
        return (cF[0] + dx * k, cF[1] + dy * k)

    if mode == "pull":                       # can nhan vat -> mo ve full frame
        z0, z1 = 1.0 + zoom, 1.0
        return z0, z1, _clamp_center(*_target(z0), z0), _clamp_center(*cF, z1)
    if mode == "pushpan":                    # day vao + truot ngang (xuat phat lech nguoc phia)
        z0, z1 = 1.0 + zoom * 0.35, 1.0 + zoom
        tx, ty = _target(z1)
        side = 1.0 if tx <= cF[0] else -1.0
        return (z0, z1, _clamp_center(cF[0] + side * pan * W, cF[1], z0),
                _clamp_center(tx, ty, z1))
    if mode in ("pan_r", "pan_l"):           # pan thuan ngang ~pan% be ngang khung
        zp = 1.0 + pan * 1.1                 # zoom vua du slack de pan het bien do
        half = pan * W / (zp / 2.0) / 2.0
        bx, by = _target(zp)
        d = 1.0 if mode == "pan_r" else -1.0
        return (zp, zp, _clamp_center(bx - d * half, by, zp),
                _clamp_center(bx + d * half, by, zp))
    z0, z1 = 1.0, 1.0 + zoom                 # push (mac dinh): full -> can nhan vat
    return z0, z1, _clamp_center(*cF, z0), _clamp_center(*_target(z1), z1)


def _scene_subject(clip, scene, opts):
    """(sx, sy, conf, iw, ih) tren ANH GOC; ho tro scene['focus']=[x,y] 0-1 ep tay (a18)
    + cong tac opts['focus_subject'] (tat -> conf=0, camera ve hanh vi zoom tam cu)."""
    cx, cy, conf, iw, ih = subject_of(clip)
    fxy = (scene or {}).get("focus")
    if isinstance(fxy, (list, tuple)) and len(fxy) == 2:
        cx, cy, conf = float(fxy[0]) * iw, float(fxy[1]) * ih, 0.95
    elif not (opts or {}).get("focus_subject", True):
        conf = 0.0
    return cx, cy, conf, iw, ih


def _cam_for(clip, idx, opts, scene=None, shot_rect=None):
    """Ke hoach camera (z0, z1, c0, c1, subj2x) cho canh nguyen (shot_rect=None) hoac
    1 shot crop (x0,y0,cw,ch). DETERMINISTIC — _next_kb_src goi lai y het (a8)."""
    opts = opts or {}
    sx, sy, conf, iw, ih = _scene_subject(clip, scene, opts)
    if shot_rect:                            # quy doi ve he toa do crop shot -> nguon 2x (a10)
        x0, y0, cw, ch = shot_rect
        sx2 = (sx - x0) * (W * 2.0) / max(1, cw)
        sy2 = (sy - y0) * (H * 2.0) / max(1, ch)
        zoom, pan = 0.03, 0.03               # shot da la crop can — chuyen dong nhe (bai hoc 4%->2.5%)
    else:                                    # quy doi qua _kb_norm2x (scale + crop giua) — cung cong thuc
        f = max(W * 2.0 / iw, H * 2.0 / ih)
        iw2, ih2 = max(W * 2, int(iw * f)), max(H * 2, int(ih * f))
        sx2 = sx * f - (iw2 - W * 2) // 2
        sy2 = sy * f - (ih2 - H * 2) // 2
        za = opts.get("zoom_amt")
        # cap 12%: anh AI nguon 1280x720, zoom sau hon lo net (so do mau ~10-15%/canh).
        # Bien do CO DINH (khong scale theo thoi luong that): _next_kb_src khong biet
        # duration TTS cua canh ke -> scale theo dur se pha determinism cua zoomblend.
        zoom = min(0.12, float(za)) if za else 0.10
        pan = 0.08                           # pan thuan ~8% be ngang (so do video mau)
    sx2 = min(max(sx2, 0.0), 2.0 * W)
    sy2 = min(max(sy2, 0.0), 2.0 * H)
    if opts.get("letterbox"):                # (a17) letterbox che 138px tren/duoi -> vung an toan
        sy2 = min(max(sy2, 2 * H * 0.16), 2 * H * 0.80)
    z0, z1, c0, c1 = _plan_camera(sx2, sy2, conf, _motion_plan(idx), zoom, pan)
    return z0, z1, c0, c1, ((sx2, sy2) if conf > 0 else None)


def _kb_norm2x(img):
    """Doc anh (path hoac ndarray BGR) -> nguon 2x (3840x2160) crop giua, du net khi phong 5%."""
    im = cv2.imread(img) if isinstance(img, str) else img
    if im is None:
        raise RuntimeError(f"khong doc duoc anh: {img}")
    ih, iw = im.shape[:2]
    if (iw, ih) != (W * 2, H * 2):
        f = max(W * 2 / iw, H * 2 / ih)
        im = cv2.resize(im, (max(W * 2, int(iw * f)), max(H * 2, int(ih * f))),
                        interpolation=cv2.INTER_LANCZOS4)
        ih2, iw2 = im.shape[:2]
        x0, y0 = (iw2 - W * 2) // 2, (ih2 - H * 2) // 2
        im = im[y0:y0 + H * 2, x0:x0 + W * 2]
    return im


def _kb_frame(im2x, z, cx=None, cy=None):
    """1 frame Ken Burns: crop-zoom z, TAM tai (cx,cy) tren nguon 2x (mac dinh = tam anh).
    Subpixel bilinear. Caller tu bao dam (cx,cy) da qua _clamp_center o 2 dau quy dao (a4)."""
    s = z / 2.0
    if cx is None:
        cx, cy = float(W), float(H)
    M = _np.float32([[s, 0, W / 2 - s * cx], [0, s, H / 2 - s * cy]])
    return cv2.warpAffine(im2x, M, (W, H), flags=cv2.INTER_LINEAR)


_FFM_GRID = [None]      # cache mgrid HxW cho mask fade (tao 1 lan)


def _focus_fade_mask(fx, fy, k):
    """Mask fade radial: k=0 sang het, k=1 den het; vung quanh (fx,fy) tat SAU CUNG (c1)."""
    if _FFM_GRID[0] is None:
        yy, xx = _np.mgrid[0:H, 0:W]
        _FFM_GRID[0] = (yy.astype(_np.float32), xx.astype(_np.float32))
    yy, xx = _FFM_GRID[0]
    r = _np.sqrt((xx - fx) ** 2 + (yy - fy) ** 2) / (0.75 * W)
    m = _np.clip((1.0 - k) + (1.0 - r) * k * 0.35, 0.0, 1.0)
    return (m * (1.0 - k * k))[..., None]


# ---------- HAT BAY (YC2) — dom dom / bui nang overlay procedural ----------
# Ve TRUC TIEP trong vong frame cua _kb_video, SAU fade/trans/head_black -> hat khong
# chim den theo dip (nhu video mau: hat + phu de + watermark khong fade theo canh).
# Phu de overlay o buoc ffmpeg SAU (make_scene) -> hat tu nhien nam DUOI phu de.
_P_SPRITES = {}          # (kieu, kich thuoc[, goc]) -> sprite float32, precompute 1 lan


def _p_sprite(r):
    """Sprite 1 hat SANG ban kinh loi r px: cham sang + quang gaussian, peak=1.0.
    Precompute vai co -> moi frame chi cong additive vung nho, KHONG blur ca frame."""
    r = int(max(1, min(5, r)))
    k = ("glow", r)
    if k not in _P_SPRITES:
        sig = r * 1.6
        S = (int(sig * 6) | 1)
        c = S // 2
        yy, xx = _np.mgrid[0:S, 0:S]
        d2 = ((xx - c) ** 2 + (yy - c) ** 2).astype(_np.float32)
        core = _np.exp(-d2 / (2.0 * (r * 0.65) ** 2))      # loi sang gon
        glow = _np.exp(-d2 / (2.0 * sig ** 2))             # quang mem xung quanh
        _P_SPRITES[k] = _np.clip(core + 0.5 * glow, 0.0, 1.0).astype(_np.float32)
    return _P_SPRITES[k]


def _p_puff(R):
    """Sprite KHOI / MAY: dam mem ban kinh R px, ria tan dan (khong co vien cung).
    R lam tron boi 16 -> cache chi vai sprite du R doi lien tuc theo thoi gian."""
    R = int(max(48, min(176, round(R / 16.0) * 16)))
    k = ("puff", R)
    if k not in _P_SPRITES:
        S = R * 2 | 1
        c = S // 2
        yy, xx = _np.mgrid[0:S, 0:S]
        d = (_np.sqrt(((xx - c) ** 2 + (yy - c) ** 2).astype(_np.float32)) / R)
        m = _np.clip(1.0 - d, 0.0, 1.0) ** 2.2             # ria tan rat dan
        m = m * _np.exp(-(d ** 2) / 0.42)                  # loi day hon o giua
        _P_SPRITES[k] = (m / max(1e-6, float(m.max()))).astype(_np.float32)
    return _P_SPRITES[k]


def _p_leaf(size, ang):
    """Sprite CHIEC LA: hinh thoi bau giua, nhon 2 dau, xoay ang do.
    size = nua chieu dai (px), lam tron 2px; goc lam tron 15 do -> 24 huong."""
    size = int(max(6, min(34, round(size / 2.0) * 2)))
    ang = int(round(ang / 15.0) * 15) % 360
    k = ("leaf", size, ang)
    if k not in _P_SPRITES:
        S = size * 4 | 1
        c = S // 2
        yy, xx = _np.mgrid[0:S, 0:S]
        x = (xx - c).astype(_np.float32) / float(size)
        y = (yy - c).astype(_np.float32) / float(size * 0.42)
        m = _np.clip(1.0 - (x * x + y * y), 0.0, 1.0) ** 0.7      # than la bau
        m = m * _np.clip(1.0 - _np.abs(x) ** 3, 0.0, 1.0)         # thuon dan ve 2 mui
        M = cv2.getRotationMatrix2D((c, c), float(ang), 1.0)
        _P_SPRITES[k] = cv2.warpAffine(m.astype(_np.float32), M, (S, S),
                                       flags=cv2.INTER_LINEAR, borderValue=0.0)
    return _P_SPRITES[k]


# kind: glow = cong sang (dom dom / bui nang) · puff = khoi-may (tron alpha)
#       leaf = la bay (tron alpha, co xoay). n = so hat @1920x1080.
_P_PRESETS = {
    "warm":   {"kind": "glow", "col": (90, 190, 255),  "a": 0.85, "n": (26, 40), "blink": True},
    "green":  {"kind": "glow", "col": (130, 225, 175), "a": 0.80, "n": (26, 40), "blink": True},
    "dust":   {"kind": "glow", "col": (235, 240, 245), "a": 0.30, "n": (34, 52), "blink": False},
    "smoke":  {"kind": "puff", "col": (176, 178, 184), "a": 0.14, "n": (6, 9)},
    "mist":   {"kind": "puff", "col": (214, 221, 233), "a": 0.09, "n": (5, 8)},
    "leaves": {"kind": "leaf", "col": (45, 112, 200),  "a": 0.88, "n": (14, 22), "sz": (14, 30)},
}

_P_ALIAS = {"domdom": "firefly", "dom-dom": "firefly", "bui": "dust", "buinang": "dust",
            "khoi": "smoke", "may": "mist", "gio": "mist", "maygio": "mist",
            "la": "leaves", "labay": "leaves", "leaf": "leaves", "fog": "mist"}


def _particle_preset(img, mode="auto"):
    """Tra DANH SACH lop hat se ve (nhieu lop chong nhau duoc) — [] la tat han.
    mode: none|firefly|dust|smoke|mist|leaves|auto, ghep nhieu lop bang dau '+'
    (vd 'firefly+leaves'). auto: doc tong mau anh -> canh toi chon dom dom (vang am
    hay vang-xanh tuy nhiet mau), canh sang chon bui nang; kem 1 lop may rat mo."""
    mode = (mode or "auto").strip().lower()
    if mode in ("none", "off", "tat", ""):
        return []
    parts = [p.strip().replace(" ", "") for p in mode.replace(",", "+").split("+")]
    parts = [_P_ALIAS.get(p, p) for p in parts if p]

    dark, warm = True, True                      # tong mau anh nguon -> chon mau hat
    im = cv2.imread(img) if isinstance(img, str) else img
    if im is not None:
        small = cv2.resize(im, (64, 36), interpolation=cv2.INTER_AREA)
        dark = float(cv2.cvtColor(small, cv2.COLOR_BGR2HSV)[..., 2].mean()) < 150
        warm = float(small[..., 2].mean()) > float(small[..., 0].mean()) + 8   # R > B

    out = []
    for p in parts:
        if p == "auto":
            out.append(dict(_P_PRESETS["warm" if warm else "green"] if dark
                            else _P_PRESETS["dust"]))
            mist = dict(_P_PRESETS["mist"])      # lop may mong -> tao chieu sau
            mist["a"] = mist["a"] * (0.8 if dark else 1.0)
            out.append(mist)
        elif p == "firefly":
            out.append(dict(_P_PRESETS["warm" if warm else "green"]))
        elif p in _P_PRESETS:
            out.append(dict(_P_PRESETS[p]))
    if not dark:
        # Canh SANG: hat cong sang bi nen trang nuot, khoi trang cung chim -> day len
        # va lam mau khoi/may toi hon nen mot chut de van doc duoc hinh.
        for L in out:
            if L["kind"] == "glow":
                L["a"] = min(1.0, L["a"] * 1.45)
                L["big"] = True                  # +1 px ban kinh loi
            elif L["kind"] == "puff":
                L["a"] = L["a"] * 1.5
                L["col"] = tuple(int(c * 0.72) for c in L["col"])
            elif L["kind"] == "leaf":
                # nen sang -> la phai TOI hon nen moi noi hinh (kieu bong la), va to hon
                L["col"] = (26, 60, 116)
                L["a"] = min(0.97, L["a"] * 1.1)
                L["sz"] = (18.0, 34.0)
    return out


def _particle_field(seed, specs):
    """Sinh tham so tung lop — DETERMINISM BAT BUOC: RandomState(seed canh + chi so lop),
    render lai ra dung vi tri. Hat chia 3 tang xa/giua/gan de co chieu sau."""
    if isinstance(specs, dict):
        specs = [specs]
    layers = []
    for li, sp in enumerate(specs):
        rng = _np.random.RandomState((int(seed) * 131 + li * 17) & 0x7FFFFFFF)
        kind = sp.get("kind", "glow")
        n0, n1 = sp["n"]
        n = int(rng.randint(n0, n1 + 1))
        col = _np.float32(sp["col"])
        base_a = float(sp["a"])
        if kind == "glow":
            M = 60.0
            lay = rng.randint(0, 3, n)                       # 0 xa · 1 giua · 2 gan
            L = {
                "kind": kind, "M": M, "blink": bool(sp.get("blink", True)),
                # moi hat lech mau mot chut -> khong bi "dan hat cung mot mau"
                "col": _np.clip(col[None, :] * rng.uniform(0.86, 1.14, (n, 1)),
                                0, 255).astype(_np.float32),
                "x": rng.uniform(-M, W + M, n),
                "y": rng.uniform(-M, H + M, n),
                "vy": 6.0 + lay * 7.0 + rng.uniform(0, 10, n),      # tang xa troi cham hon
                "amp": 8.0 + lay * 10.0 + rng.uniform(0, 14, n),    # lac ngang
                "per": rng.uniform(3.0, 8.0, n),
                "ph": rng.uniform(0, 2 * _np.pi, n),
                "vamp": rng.uniform(2.0, 11.0, n),                  # lac doc nhe -> bay luon
                "vper": rng.uniform(2.5, 6.0, n),
                "vph": rng.uniform(0, 2 * _np.pi, n),
                "bt": rng.uniform(1.2, 3.6, n),                     # chu ky nhap nhay
                "bp": rng.uniform(0, 2 * _np.pi, n),
                "duty": rng.uniform(0.22, 0.55, n),                 # % chu ky con sang
                "a": base_a * (0.45 + 0.28 * lay) * rng.uniform(0.7, 1.0, n),
                "r": (1 + lay + (1 if sp.get("big") else 0)).astype(_np.int32),
            }
        elif kind == "puff":
            M = 240.0
            L = {
                "kind": kind, "M": M,
                "col": _np.clip(col[None, :] * rng.uniform(0.94, 1.06, (n, 1)),
                                0, 255).astype(_np.float32),
                "x": rng.uniform(-M, W + M, n),
                "y": rng.uniform(H * 0.10, H * 1.05, n),
                "vx": rng.choice([-1.0, 1.0], n) * rng.uniform(5.0, 16.0, n),  # gio ngang
                "vy": -rng.uniform(1.5, 7.0, n),                    # boc len rat cham
                "R0": rng.uniform(60.0, 130.0, n),
                "gr": rng.uniform(1.5, 6.0, n),                     # no dan px/s
                "per": rng.uniform(6.0, 14.0, n),                   # nhip dam/nhat
                "ph": rng.uniform(0, 2 * _np.pi, n),
                "a": base_a * rng.uniform(0.6, 1.0, n),
            }
        else:                                                       # leaf
            M = 90.0
            L = {
                "kind": kind, "M": M,
                "col": _np.clip(col[None, :] * rng.uniform(0.75, 1.20, (n, 1)),
                                0, 255).astype(_np.float32),
                "x": rng.uniform(-M, W + M, n),
                "y": rng.uniform(-M, H + M, n),
                "vy": rng.uniform(28.0, 70.0, n),                   # roi xuong
                "amp": rng.uniform(26.0, 80.0, n),                  # dao qua lai khi roi
                "per": rng.uniform(2.4, 5.2, n),
                "ph": rng.uniform(0, 2 * _np.pi, n),
                "rot": rng.uniform(-110.0, 110.0, n),               # do/s
                "rot0": rng.uniform(0, 360, n),
                "sz": rng.uniform(sp.get("sz", (14.0, 30.0))[0],
                                  sp.get("sz", (14.0, 30.0))[1], n),  # nua chieu dai la
                "a": base_a * rng.uniform(0.55, 1.0, n),
            }
        L["n"] = n
        layers.append(L)
    return layers


def _p_edge_fade(xs, ys, M):
    """Mo dan khi hat ra sat le -> khong thay hat 'hien ra' / 'bien mat' o bien khung."""
    d = _np.minimum(_np.minimum(xs, W - xs), _np.minimum(ys, H - ys))
    return _np.clip(d / max(1.0, M) + 1.0, 0.0, 1.0)


def _p_blit_add(fr, spr, cx, cy, a, col):
    """Cong sang (additive) vung nho — dung cho dom dom / bui nang."""
    S = spr.shape[0]
    x0, y0 = int(round(cx)) - S // 2, int(round(cy)) - S // 2
    fx0, fy0 = max(0, x0), max(0, y0)
    fx1, fy1 = min(W, x0 + S), min(H, y0 + S)
    if fx1 <= fx0 or fy1 <= fy0:
        return                                    # hat ngoai khung
    sp = spr[fy0 - y0:fy1 - y0, fx0 - x0:fx1 - x0]
    add = (sp[:, :, None] * (a * col)).astype(_np.uint8)
    fr[fy0:fy1, fx0:fx1] = cv2.add(fr[fy0:fy1, fx0:fx1], add)


def _p_blit_alpha(fr, spr, cx, cy, a, col):
    """Tron alpha — dung cho khoi / may / la: KHONG cong sang nen khong chay trang."""
    S = spr.shape[0]
    x0, y0 = int(round(cx)) - S // 2, int(round(cy)) - S // 2
    fx0, fy0 = max(0, x0), max(0, y0)
    fx1, fy1 = min(W, x0 + S), min(H, y0 + S)
    if fx1 <= fx0 or fy1 <= fy0:
        return
    m = (spr[fy0 - y0:fy1 - y0, fx0 - x0:fx1 - x0] * float(a))[:, :, None]
    roi = fr[fy0:fy1, fx0:fx1].astype(_np.float32)
    fr[fy0:fy1, fx0:fx1] = _np.clip(roi * (1.0 - m) + col * m, 0, 255).astype(_np.uint8)


def _p_draw_glow(fr, L, t):
    M = L["M"]
    xs = L["x"] + L["amp"] * _np.sin(2 * _np.pi * t / L["per"] + L["ph"])
    ys = (L["y"] - L["vy"] * t + M) % (H + 2 * M) - M            # troi len, wrap day khung
    ys = ys + L["vamp"] * _np.sin(2 * _np.pi * t / L["vper"] + L["vph"])
    if L["blink"]:
        # dom dom that: TAT HAN roi bung sang thanh nhip, khong phai sin deu deu
        u = ((t / L["bt"]) + L["bp"] / (2 * _np.pi)) % 1.0
        e = _np.exp(-((u - 0.5) / _np.maximum(0.06, L["duty"] * 0.34)) ** 2)
        al = L["a"] * (0.06 + 0.94 * e)
    else:
        al = L["a"] * (0.70 + 0.30 * _np.sin(2 * _np.pi * t / L["bt"] + L["bp"]))
    al = al * _p_edge_fade(xs, ys, M)
    for i in range(L["n"]):
        a = float(al[i])
        if a <= 0.025:
            continue
        r = int(L["r"][i]) + (1 if a > float(L["a"][i]) * 0.82 else 0)   # sang manh -> no to
        _p_blit_add(fr, _p_sprite(r), xs[i], ys[i], a, L["col"][i])


def _p_draw_puff(fr, L, t):
    M = L["M"]
    xs = (L["x"] + L["vx"] * t + M) % (W + 2 * M) - M
    ys = (L["y"] + L["vy"] * t + M) % (H + 2 * M) - M
    al = L["a"] * (0.72 + 0.28 * _np.sin(2 * _np.pi * t / L["per"] + L["ph"]))
    al = al * _p_edge_fade(xs, ys, M)
    Rs = _np.minimum(L["R0"] + L["gr"] * t, L["R0"] * 1.8)       # no dan roi dung, khong giat
    for i in range(L["n"]):
        a = float(al[i])
        if a <= 0.012:
            continue
        _p_blit_alpha(fr, _p_puff(Rs[i]), xs[i], ys[i], a, L["col"][i])


def _p_draw_leaf(fr, L, t):
    M = L["M"]
    ph = 2 * _np.pi * t / L["per"] + L["ph"]
    xs = L["x"] + L["amp"] * _np.sin(ph)
    ys = (L["y"] + L["vy"] * t + M) % (H + 2 * M) - M            # roi xuong, wrap dinh khung
    ang = L["rot0"] + L["rot"] * t
    # luc thay mat rong, luc quay canh (mong di) -> nhin nhu la that dao trong gio
    al = L["a"] * (0.35 + 0.65 * _np.abs(_np.cos(ph))) * _p_edge_fade(xs, ys, M)
    for i in range(L["n"]):
        a = float(al[i])
        if a <= 0.03:
            continue
        _p_blit_alpha(fr, _p_leaf(L["sz"][i], ang[i]), xs[i], ys[i], a, L["col"][i])


def _particles_draw(fr, pf, t):
    """Ve TAT CA cac lop hat len frame BGR uint8 (in-place) tai thoi diem t giay."""
    if pf is None:
        return
    if isinstance(pf, dict):
        pf = [pf]
    for L in pf:
        k = L.get("kind", "glow")
        if k == "glow":
            _p_draw_glow(fr, L, t)
        elif k == "puff":
            _p_draw_puff(fr, L, t)
        else:
            _p_draw_leaf(fr, L, t)


def _kb_video(img_path, frames, zoom_in, out_path, zoom=0.05,
              trans_out=None, cut_at=None, head_black=0, cam=None, particles=None):
    """Ken Burns SUBPIXEL (cv2.warpAffine bilinear tung frame) -> mp4 segment.
    zoompan cua ffmpeg chi crop PIXEL NGUYEN nen zoom cham kieu gi cung giat nac
    (frame nhich 0px, frame nhich 1px). warpAffine lay mau duoi-pixel -> muot tuyet doi.

    cam=(z0, z1, c0, c1, subj2x): quy dao camera huong nhan vat (tu _cam_for);
      None -> duong cu: zoom_in/zoom quanh tam anh (make_card van dung).
      Zoom + pan noi suy CUNG easing smoothstep -> van toc man hinh = 0 o 2 dau (a5-a7).

    CHUYEN CANH BAKE TAI CHO (khong them frame nao -> timing toan cuc BAT BIEN):
      trans_out=(kind, T_f, next_src2x, next_z0, next_c0): GHI DE T_f frame cuoi (truoc cut_at):
        'black'     -> chim dan ve den (dip-to-black nua truoc, gamma-correct)
        'zoomblend' -> canh cu DAY zoom tiep + mo dan, canh moi ha canh ve dung frame dau
                       cua no (next_z0, next_c0) -> diem noi concat lien mach nhu 1 cu may
      cut_at: frame hien thi CUOI cua canh (-t cat tai day; segment co the render du them)
      head_black: N frame dau sang dan tu den (nua sau cua dip-to-black / fade-in mo phim)

    particles=(pf, t0): lop hat bay YC2 — pf tu _particle_field (deterministic theo seed
      canh), t0 = offset giay (shot g>0 tiep noi quy dao shot truoc, hat KHONG nhay vi tri
      qua moi noi shot). Ve SAU fade/trans -> hat sang xuyen dip nhu video mau."""
    im = _kb_norm2x(img_path)
    T = max(2, int(frames))
    end = min(T, int(cut_at)) if cut_at else T
    if cam:
        z0, z1, c0, c1, subj = cam
    else:                                        # duong cu: zoom quanh tam anh
        z0, z1 = (1.0, 1.0 + zoom) if zoom_in else (1.0 + zoom, 1.0)
        c0 = c1 = (float(W), float(H)); subj = None
    head_black = min(int(head_black or 0), end)
    pfield, pt0 = particles if particles else (None, 0.0)
    tkind = tTf = tnsrc = tnz0 = tnc0 = None
    if trans_out:
        tkind, tTf, tnsrc, tnz0, tnc0 = trans_out
        tTf = min(max(1, int(tTf)), end)         # (c9) dip khong dai hon phan hien thi
    cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-an", *X264_SEG, "-pix_fmt", "yuv420p", out_path]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        den = max(2, end) - 1                    # (b1) ease ve DICH tai cut_at, khong phai T
        for n in range(T):
            t = min(1.0, n / den)
            e = t * t * (3 - 2 * t)              # smoothstep ease in-out
            z = z0 + (z1 - z0) * e
            cx = c0[0] + (c1[0] - c0[0]) * e     # CUNG easing cho zoom + pan (a6)
            cy = c0[1] + (c1[1] - c0[1]) * e
            fr = _kb_frame(im, z, cx, cy)
            if head_black and n < head_black:    # sang dan tu den (gamma-correct, c2/c3)
                k = n / head_black
                ke = (k * k * (3 - 2 * k)) ** 1.6
                if FADE_FOCUS and subj is not None:
                    s = z / 2.0
                    fr = (fr * _focus_fade_mask(s * subj[0] + (W / 2 - s * cx),
                                                s * subj[1] + (H / 2 - s * cy),
                                                1.0 - ke)).astype(_np.uint8)
                else:
                    fr = (fr * ke).astype(_np.uint8)
            if tkind and end - tTf <= n < end:
                p = (n - (end - tTf)) / max(1, tTf)
                pe = p * p * (3 - 2 * p)
                if tkind == "black":             # chim dan (gamma-correct; mask neu bat)
                    if FADE_FOCUS and subj is not None:
                        s = z / 2.0
                        fr = (fr * _focus_fade_mask(s * subj[0] + (W / 2 - s * cx),
                                                    s * subj[1] + (H / 2 - s * cy),
                                                    pe)).astype(_np.uint8)
                    else:
                        fr = (fr * ((1.0 - pe) ** 1.6)).astype(_np.uint8)
                elif tkind == "zoomblend" and tnsrc is not None:
                    fa = _kb_frame(im, z * (1.0 + 0.06 * pe), cx, cy)   # A day zoom CUNG TAM (a7)
                    fb = _kb_frame(tnsrc, tnz0 * (1.0 + 0.06 * (1.0 - pe)),
                                   *(tnc0 or (float(W), float(H))))     # B ha canh ve frame 0
                    fr = cv2.addWeighted(fa, 1.0 - pe, fb, pe, 0)
            if pfield is not None:               # YC2: hat ve SAU fade -> khong chim theo dip
                _particles_draw(fr, pfield, pt0 + n / FPS)
            pr.stdin.write(fr.tobytes())
    finally:
        pr.stdin.close()
    if pr.wait() != 0:
        raise RuntimeError("ffmpeg encode _kb_video loi")
    return out_path


def _next_kb_src(scene, j, opts):
    """(src2x, z0, c0) cua FRAME HIEN THI DAU TIEN canh j — tinh truoc KHONG can render
    (deterministic: cung subject_of + _motion_plan + _cam_for voi make_scene, a8).
    None neu canh sau la video/khong co anh -> roi ve dip-to-black."""
    if not (_HAVE_CV2 and scene):
        return None
    clip = (scene.get("clip") or "").strip()
    clips_multi = _scene_clips(scene)
    if not clip and clips_multi:
        clip = clips_multi[0]                        # YC3: chi co "clips" -> chu dao lam clip
    if not clip or not os.path.exists(clip) or _is_video(clip):
        return None
    subs = [s for s in (scene.get("subs") or []) if (s.get("hz") or s.get("vi"))]
    use_multi = (len(clips_multi) >= 2 and len(subs) >= 1
                 and opts.get("film_mode", True))    # YC3 — DONG BO dieu kien voi make_scene
    use_shots = (bool(scene.get("narrate")) and len(subs) >= 2
                 and opts.get("film_mode", True) and not use_multi)
    try:
        if use_multi:                                # group dau canh j: anh clips[0], idx=0+j
            src = _kb_norm2x(clips_multi[0])
            cam = _cam_for(clips_multi[0], j, opts, scene=scene)
        elif use_shots:                              # shot dau: g=0 -> idx=j, geom m=(0+j)%4
            sx, sy, conf, _, _ = _scene_subject(clip, scene, opts)
            pim = Image.open(clip).convert("RGB")
            rect = _shot_geom(pim.size[0], pim.size[1], 0, j,
                              sub=((sx, sy) if conf > 0 else None))
            x0, y0, cw, ch = rect
            crop = pim.crop((x0, y0, x0 + cw, y0 + ch)).resize((W * 2, H * 2), Image.LANCZOS)
            src = _np.asarray(crop)[:, :, ::-1].copy()          # RGB -> BGR
            cam = _cam_for(clip, j, opts, scene=scene, shot_rect=rect)
        else:
            if not opts.get("kenburns", True):
                return None
            src = _kb_norm2x(clip)
            cam = _cam_for(clip, j, opts, scene=scene)
        return src, cam[0], cam[2]                   # e(t=0)=0 -> (z0, c0) tai frame dau
    except Exception:
        return None


# ---------- NGU PHAP DIEN ANH: chon chuyen canh theo BEAT ----------
_ROLE_KEYS = [                                       # thu tu = do uu tien khi match substring
    ("twist",      ("twist", "lat_bai", "latbai", "buoc_ngoat", "buocngoat", "bien_co",
                    "bienco", "bat_ngo", "batngo")),
    ("resolution", ("phuc_bao", "phucbao", "thang_hoa", "thanghoa", "doan_tu", "doantu",
                    "giai_thoat", "giaithoat")),     # truoc climax: "phuc_bao" chua "bao"
    ("ket",        ("ket", "bai_hoc", "baihoc", "loi_phan", "loiphan")),
    ("climax",     ("climax", "cao_trao", "caotrao", "sup_do", "supdo", "qua_bao",
                    "quabao", "dinh_diem", "dinhdiem", "bao")),
    ("timejump",   ("hoi_tuong", "hoituong", "con_lon", "conlon", "dai_kiep", "daikiep",
                    "vinh_quy", "vinhquy", "gap_lai", "gaplai", "nam_sau", "namsau",
                    "doan_vien", "doanvien")),
    ("hook",       ("hook", "mo_dau", "modau", "teaser")),
]

def _beat_role(b):
    b = (b or "").strip().lower().replace(" ", "_").replace("-", "_")
    if not b:
        return ""
    for role, keys in _ROLE_KEYS:
        if any(k in b for k in keys):
            return role
    return "body"


def plan_transitions(scenes, opts=None):
    """Gan chuyen canh cho tung moi noi theo NGU PHAP DIEN ANH (bake vao duoi canh truoc,
    timing toan cuc BAT BIEN — xem _kb_video):
      - cung phan doan (cung beat)      -> CUT thang (mac dinh cua phim that)
      - doi phan doan                   -> zoom-blend 0.7s ("thoi gian troi / doi khong gian")
      - nhay thoi gian lon / vao ket    -> zoom-blend cham 1.0-1.2s
      - VAO twist/climax                -> CUT thang (dissolve se "bao truoc" cu lat)
      - HET hook / HET climax           -> dip-to-black (nghi chuong, chi 2-3 lan/phim)
      - canh dau fade-in, canh cuoi fade-out (khop card dau/cuoi von fade den)
    Kich ban co the ep tay: scene["trans"] = cut|black|blend (ap cho moi noi TRUOC canh do).
    opts (c7): always_fade (mac dinh BAT — style Chuyen Que Xua: 100% dip, cac moi CUT
    doi thanh dip-to-black); dip_dur (mac dinh 0.5s ~ so do video mau 0.45s)."""
    opts = opts or {}
    always = bool(opts.get("always_fade", True))
    dip = max(0.2, float(opts.get("dip_dur") or 0.5))
    n = len(scenes)
    for i, sc in enumerate(scenes):
        sc["_trans_out"] = None
        sc["_head_black"] = 0.0
        sc["_next"] = scenes[i + 1] if i + 1 < n else None
        sc["_next_idx"] = i + 1
    if not n:
        return scenes
    scenes[0]["_head_black"] = 0.8                   # mo phim: sang dan tu den
    for i in range(n - 1):
        cur, nxt = scenes[i], scenes[i + 1]
        manual = (nxt.get("trans") or "").strip().lower()
        r0, r1 = _beat_role(cur.get("beat")), _beat_role(nxt.get("beat"))
        kind, dur = None, 0.0
        if manual in ("cut", "none"):
            pass                                     # ep tay CUT -> ton trong ca khi always_fade
        elif manual in ("black", "fadeblack", "dip"):
            kind, dur = "black", dip
        elif manual in ("blend", "zoomblend", "fade", "dissolve"):
            kind, dur = "zoomblend", 0.7
        elif r1 in ("twist", "climax"):
            if always:                               # (c7) video mau khong cut cung
                kind, dur = "black", dip
        elif r0 == "hook" and r1 == "hook":
            kind, dur = "zoomblend", 0.6             # hook = montage "trailer"
        elif r0 == "hook":
            kind, dur = "black", max(dip, 0.6)       # het loi tua -> vao truyen
        elif r0 == "climax":
            kind, dur = "black", max(dip, 0.7)       # tho sau cao trao
        elif r1 == "timejump":
            kind, dur = "zoomblend", 1.2
        elif r1 == "ket":
            kind, dur = "zoomblend", 1.0             # vao bai hoc -> dissolve cham
        elif r0 == r1 == "body":
            b0 = (cur.get("beat") or "").strip().lower().replace(" ", "_")
            b1 = (nxt.get("beat") or "").strip().lower().replace(" ", "_")
            if b0 != b1:
                kind, dur = "zoomblend", 0.7         # doi beat (du cung nhom body) = doi phan doan
            elif always:
                kind, dur = "black", dip             # (c7) cung beat: dip thay cut
        elif r0 == r1:
            if always:
                kind, dur = "black", dip             # (c7) cung phan doan: dip thay cut
        else:
            kind, dur = "zoomblend", 0.7
        cur["_trans_out"] = (kind, dur) if kind else None
        if kind == "black":                          # nua sau cua dip: canh ke sang dan
            nxt["_head_black"] = max(float(nxt.get("_head_black") or 0), dur / 2)
    scenes[-1]["_trans_out"] = ("black", max(dip, 0.6))  # ket phim -> end card (card tu fade-in)
    return scenes


def _kb_filter(i, frames):
    """(FALLBACK khi thieu cv2) Ken Burns bang zoompan — van hoi giat nac vi crop pixel nguyen.
    Supersample cao (3x) -> zoom mượt, không rung pixel.
    TODO (a14): x/y theo tam nhan vat (can subject detect khong-cv2) — hien zoom quanh tam."""
    T = max(2, frames)
    e = f"(3*pow(on/{T},2)-2*pow(on/{T},3))"        # smoothstep 0->1 (ease in-out)
    z = f"1.0+0.05*{e}" if i % 2 == 0 else f"1.05-0.05*{e}"   # ±5% rất nhẹ
    S, SH = W * 2, H * 2                            # 3x -> 2x: van muot voi zoom 5%, nhanh ~2.3x
    return (f"scale={S}:{SH}:force_original_aspect_ratio=increase,crop={S}:{SH},"
            f"zoompan=z='{z}':d={T}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"s={W}x{H}:fps={FPS},format=yuv420p")


# khung điện ảnh 2.39:1: thanh đen trên/dưới
LB_BAR = int(round((H - W / 2.39) / 2 / 2) * 2)          # ~138px mỗi thanh (chẵn)
LB_SUB_BOTTOM = (H - LB_BAR) - 34                         # đáy chữ phụ đề khi bật letterbox

def _letterbox_filter():
    return (f"drawbox=x=0:y=0:w={W}:h={LB_BAR}:color=black:t=fill,"
            f"drawbox=x=0:y={H-LB_BAR}:w={W}:h={LB_BAR}:color=black:t=fill")

# ---------- PHU DE (PNG trong suot, o DAY man hinh) ----------
def render_subtitle(hz, vi="", show_pinyin=True, path=None, bottom=None):
    """1 khung phu de: scrim toi o day + (pinyin) + Han + nghia. Nen TRONG SUOT -> overlay len clip.
    bottom: toa do đáy chữ (mặc định H-56; khi có letterbox -> đưa lên trong khung)."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if not (hz or vi):
        if path: im.save(path)
        return path
    base_y = bottom if bottom else (H - 56)
    # scrim NHẸ hơn (đỡ 'bar đen' thô) — chỉ đủ tách chữ; chữ tự có VIỀN nên vẫn rõ
    band = 300
    sd = ImageDraw.Draw(im)
    top_scrim = max(0, base_y - band + 56)
    for yy in range(top_scrim, min(H, base_y + 56)):
        a = int(130 * ((yy - top_scrim) / band) ** 1.3)
        sd.line([(0, yy), (W, yy)], fill=(0, 0, 0, a))
    d = ImageDraw.Draw(im)
    cx = W // 2
    zf = sp.font("zh", 76)
    pf = sp.font("pinyin", 40)
    vf = sp.font("viet", 48)
    py_h = (pf.size + 10) if show_pinyin else 0
    y = base_y
    _STK = (0, 0, 0, 210)                              # viền chữ (đọc rõ trên nền bất kỳ, khỏi cần scrim đậm)
    # nghia Viet (duoi cung)
    if vi:
        for ln in reversed(sp.wrap_text(d, vi, vf, int(W * 0.88))[:2]):
            y -= vf.size + 10
            d.text((cx, y), ln, font=vf, fill=(255, 240, 190), anchor="ma",
                   stroke_width=3, stroke_fill=_STK)
        y -= 6
    # Han (+ pinyin tren tung chu neu bat)
    cells = []
    for ch, py in _flatten(sp._strip_punct(hz) if hasattr(sp, "_strip_punct") else hz):
        wch = sp.text_w(d, ch, zf)
        wpy = sp.text_w(d, py, pf) if (py and show_pinyin) else 0
        cells.append((ch, py, wch, wpy, max(wch, wpy)))
    total = sum(c[4] for c in cells) + 8 * (len(cells) - 1) if cells else 0
    # xuong dong neu qua rong
    max_w = int(W * 0.92)
    row_h = py_h + zf.size + 4
    y -= zf.size + (py_h)
    # ve 1 dong (neu qua dai thi thu nho)
    if total > max_w and total > 0:
        sc = max_w / total
        zf = sp.font("zh", max(48, int(76 * sc)))
        pf = sp.font("pinyin", max(28, int(40 * sc)))
        cells = []
        for ch, py in _flatten(hz):
            wch = sp.text_w(d, ch, zf); wpy = sp.text_w(d, py, pf) if (py and show_pinyin) else 0
            cells.append((ch, py, wch, wpy, max(wch, wpy)))
        total = sum(c[4] for c in cells) + 8 * (len(cells) - 1)
    x = cx - total // 2
    for ch, py, wch, wpy, cw in cells:
        if py and show_pinyin:
            d.text((x + (cw - wpy) // 2, y), py, font=pf, fill=_TONE[_tone_of(py)],
                   stroke_width=2, stroke_fill=_STK)
        d.text((x + (cw - wch) // 2, y + py_h), ch, font=zf, fill=(250, 250, 246),
               stroke_width=3, stroke_fill=_STK)
        x += cw + 8
    if path:
        im.save(path)
    return path


# ---------- AUDIO helpers ----------
def _seg_audio(tts_mp3, dur, out_wav):
    """Chuan hoa 1 doan tieng -> wav 44100 stereo, dai DUNG 'dur' giay (pad im lang neu thieu)."""
    if tts_mp3 and os.path.exists(tts_mp3):
        subprocess.run(["ffmpeg", "-y", "-i", tts_mp3,
                        "-af", "aresample=44100,apad", "-t", f"{dur:.2f}",
                        "-ac", "2", "-ar", "44100", out_wav], check=True, capture_output=True)
    else:
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                        "-t", f"{dur:.2f}", out_wav], check=True, capture_output=True)
    return out_wav

def _concat_wav(files, out):
    lst = out + ".txt"
    with open(lst, "w") as f:
        for p in files:
            f.write(f"file '{p.replace(os.sep,'/')}'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                    "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2", out],
                   check=True, capture_output=True)
    try: os.remove(lst)
    except OSError: pass
    return out


# ---------- 1 CANH ----------
def make_scene(scene, opts, i):
    """Dung 1 canh: clip nen (video/anh) + phu de timed + tieng (clip goc / TTS / tron).
    Tra ve (path_mp4, thoi_luong)."""
    import generate
    clip = (scene.get("clip") or "").strip()
    clips_multi = _scene_clips(scene)                # YC3: danh sach anh (chu dao + phu)
    if not clip and clips_multi:
        clip = clips_multi[0]                        # chi co "clips" -> anh chu dao lam clip
    is_vid = _is_video(clip) and os.path.exists(clip)
    is_img = clip and os.path.exists(clip) and not is_vid
    subs = [s for s in (scene.get("subs") or []) if (s.get("hz") or s.get("vi"))]
    narrate = bool(scene.get("narrate"))
    keep = bool(scene.get("keep_audio", True)) and is_vid
    show_py = bool(opts.get("sub_pinyin", True))
    tmp = []

    # 1) TIMELINE (thoi luong tung phu de) + AUDIO track
    scene_audio = None
    # LOI KE NAP SAN: file mp3/wav nguoi dung tu tao (vd tai tu Vbee Studio bang giong
    # cong dong) -> dung nguyen, KHONG goi TTS. Moc phu de chia theo so ky tu tung cau.
    narr_pre = (scene.get("narr_audio") or "").strip()
    if narr_pre and not os.path.exists(narr_pre):
        narr_pre = ""
    if narrate and subs and narr_pre:
        adur = max(0.9, _dur(narr_pre))
        w = os.path.join(FILM, f"_sw_{i}_pre.wav")
        _seg_audio(narr_pre, adur, w); tmp.append(w)
        wts = [max(1, len((s.get("tts") or s.get("hz") or ""))) for s in subs]
        tot = sum(wts)
        sub_dur = [adur * x / tot for x in wts]
        scene_dur = adur
        ta = os.path.join(FILM, f"_ta_{i}.m4a"); _concat_wav([w], ta); tmp.append(ta)
        scene_audio = ta
    elif narrate and subs:
        seg_wavs, sub_dur = [], []
        # GOM CAU: cac cau LIEN TIEP cung giong + cung cam xuc -> 1 request TTS duy nhat.
        # Truoc day moi cau 1 request roi noi cung -> "gay" ngu dieu cho chuyen cau
        # (ro nhat voi Gemini/Eleven/Vbee: moi request mot chat giong hoi khac).
        # Gop lai de TTS tu ngat nghi tu nhien; moc phu de trong run chia theo so ky tu.
        def _sub_text(s):
            return ((s.get("tts") or s.get("hz") or "")).strip()
        def _run_key(s):
            t = _sub_text(s)
            if not t:
                return None                     # cau trong -> run rieng, khong gop
            emo = s.get("emo")
            en = emo.get("name") if isinstance(emo, dict) else emo
            return (s.get("voice") or opts.get("voice", "zh-CN-XiaoxiaoNeural"), en)
        runs, cur = [], object()
        for k, s in enumerate(subs):
            kk = _run_key(s)
            if (kk is not None and runs and kk == cur and
                    sum(len(_sub_text(subs[j])) for j in runs[-1]) + len(_sub_text(s)) <= 1200):
                runs[-1].append(k)
            else:
                runs.append([k]); cur = kk
        for run in runs:
            ss = [subs[k] for k in run]
            texts = [_sub_text(s) for s in ss]
            joined = " ".join(t for t in texts if t)
            k0 = run[0]
            if not joined:                       # cau trong (chi dau cau) -> im lang nhu cu
                w = os.path.join(FILM, f"_sw_{i}_{k0}.wav")
                _seg_audio(None, 1.4, w); tmp.append(w)
                seg_wavs.append(w); sub_dur.append(1.4)
                continue
            s0 = ss[0]
            vc = s0.get("voice") or opts.get("voice", "zh-CN-XiaoxiaoNeural")
            az = s0.get("azure") or (opts.get("azure") if vc == opts.get("voice") else None)
            gm = s0.get("gemini") or (opts.get("gemini") if vc == opts.get("voice") else None)
            el = s0.get("eleven") or (opts.get("eleven") if vc == opts.get("voice") else None)
            fp = s0.get("fpt") or (opts.get("fpt") if vc == opts.get("voice") else None)
            mp = os.path.join(FILM, f"_tts_{i}_{k0}.mp3")
            generate.synth(joined, _clean_voice(vc), mp, rate=opts.get("rate", "-8%"),
                           azure=az, gemini=gm, eleven=el, fpt=fp, emo=s0.get("emo"))
            tmp.append(mp)
            adur = max(0.9, _dur(mp))
            # NHIP PHIM: pad chi con SAU run (trong run TTS tu ngat); cau cuoi canh co 'beat'
            pad_end = float(ss[-1].get("pad", 0.55))
            w = os.path.join(FILM, f"_sw_{i}_{k0}.wav")
            _seg_audio(mp, adur + pad_end, w); tmp.append(w)
            seg_wavs.append(w)
            wts = [max(1, len(t)) for t in texts]
            durs = [adur * x / sum(wts) for x in wts]
            durs[-1] += pad_end
            sub_dur.extend(durs)
        scene_dur = sum(sub_dur)
        ta = os.path.join(FILM, f"_ta_{i}.m4a"); _concat_wav(seg_wavs, ta); tmp.append(ta)
        scene_audio = ta
    else:
        if is_vid:
            scene_dur = max(1.0, _dur(clip))
        else:
            scene_dur = float(scene.get("dur") or (max(1, len(subs)) * 3.6))
        n = max(1, len(subs))
        sub_dur = [scene_dur / n] * n if subs else []

    # moc thoi gian hien tung phu de
    starts, t = [], 0.0
    for dd in sub_dur:
        starts.append(t); t += dd
    # xuat timeline tung cau (cho SRT) — gan vao scene dict, offset boi app theo moc canh
    scene["_subtimes"] = [{"s": starts[k], "e": starts[k] + sub_dur[k],
                           "hz": subs[k].get("hz", ""), "vi": subs[k].get("vi", "")}
                          for k in range(len(subs))]

    # 2) PNG phu de
    sub_pngs = []
    for k, s in enumerate(subs):
        p = os.path.join(FILM, f"_sub_{i}_{k}.png")
        _sub_bottom = LB_SUB_BOTTOM if opts.get("letterbox") else None
        render_subtitle(s.get("hz", ""), s.get("vi", ""), show_py, p, bottom=_sub_bottom)
        sub_pngs.append(p); tmp.append(p)

    # 3) FFMPEG: base + overlay phu de timed + audio
    vp = os.path.join(FILM, f"scene_{i:02d}.mp4")
    inputs, fc = [], []
    # CHUYEN CANH bake vao duoi bg (plan_transitions da gan _trans_out/_head_black vao scene):
    _tk, _td = (scene.get("_trans_out") or (None, 0.0))
    _nsrc = None
    if _tk == "zoomblend":
        _nsrc = _next_kb_src(scene.get("_next"), int(scene.get("_next_idx", i + 1)), opts)
        if _nsrc is None:
            _tk = "black"                            # canh sau video/khong anh -> dip-to-black
    _trans = None
    if _HAVE_CV2 and _tk:
        # (c5) dip DOI XUNG nhu video mau: ra dur/2 (day canh nay) + vao dur/2 (head_black canh ke)
        _tf = float(_td) * (0.5 if _tk == "black" else 1.0)
        _trans = (_tk, max(1, int(_tf * FPS)),                       # (a9) tuple 5 phan tu
                  _nsrc[0] if _nsrc else None, _nsrc[1] if _nsrc else None,
                  _nsrc[2] if _nsrc else None)
    _hb_frames = int(float(scene.get("_head_black") or 0) * FPS) if _HAVE_CV2 else 0
    # HAT BAY (YC2): preset auto theo mau anh; scene["particles"] ghi de opts["particles"].
    # Chi co o duong cv2 (_kb_video); fallback zoompan BO QUA hat (khong crash).
    _pf = None
    if _HAVE_CV2 and is_img:
        _pmode = str(scene.get("particles") or opts.get("particles") or "auto")
        try:
            _pp = _particle_preset(clip, _pmode)
            if _pp:
                _pf = _particle_field(i, _pp)    # seed = chi so canh -> deterministic
        except Exception:
            _pf = None                           # loi phan tich anh -> bo hat, khong chan phim
    # FAKE COVERAGE: anh tinh + >=2 cau -> cat SHOT (toan/trung/can) nhu phim co nhieu cu may.
    # CHUYEN SHOT THEO NOI DUNG, khong phai 1 cau/1 shot (giat lien tuc):
    #   - sub co "cut": true  -> mo shot moi tai cau do (kich ban tu quyet dinh diem chuyen)
    #   - khong danh dau "cut" -> tu gom cac cau lien tiep den ~6.5s roi moi chuyen
    # YC3 MULTI-SHOT: canh co >=2 anh trong scene["clips"] -> moi group 1 ANH KHAC
    # (chu dao / can canh / quang canh) thay vi cat crop 1 anh. Timing group van chia
    # theo cau nhu co che san co -> TONG THOI LUONG CANH BAT BIEN. Chi o duong cv2.
    use_multi = (_HAVE_CV2 and is_img and len(clips_multi) >= 2 and len(subs) >= 1
                 and opts.get("film_mode", True))
    use_shots = (is_img and narrate and len(subs) >= 2 and opts.get("film_mode", True)
                 and not use_multi)
    if use_multi:
        groups = _multi_groups(subs, sub_dur, len(clips_multi), scene_dur)
        order = _clip_alloc(len(groups), len(clips_multi))
        segs = []
        _pt = 0.0                                # hat: t0 cong don qua group (nhu YC2)
        _f0, _cum = 0, 0.0
        for g, idxs in enumerate(groups):
            _cum += sum(sub_dur[k] for k in idxs)
            _f1 = int(round(_cum * FPS))
            fr = max(2, _f1 - _f0); _f0 = _f1    # lam tron TICH LUY -> tong frame chuan
            src = clips_multi[order[g]]
            last = (g == len(groups) - 1)
            kv = os.path.join(FILM, f"_kbv_{i}_{g}.mp4")
            # moi anh di duong subject-focused Ken Burns YC1; scene["focus"] ep tay chi
            # ap cho ANH CHU DAO (anh phu detect rieng). Giua group: CUT thang (khong dip),
            # dip chi o ranh gioi CANH: trans bake group cuoi, head_black group dau.
            _cam = _cam_for(src, g + i, opts, scene=(scene if order[g] == 0 else None))
            _kb_video(src, fr, zoom_in=((g + i) % 2 == 0), out_path=kv, zoom=0.05,
                      cam=_cam,
                      trans_out=(_trans if last else None), cut_at=(fr if last else None),
                      head_black=(_hb_frames if g == 0 else 0),
                      particles=((_pf, _pt) if _pf is not None else None))
            _pt += fr / FPS
            tmp.append(kv)
            inputs += ["-i", kv]
            fc.append(f"[{g}:v]setpts=PTS-STARTPTS[sh{g}]")
            segs.append(f"[sh{g}]")
        fc.append("".join(segs) + f"concat=n={len(groups)}:v=1:a=0,format=yuv420p[bg]")
        n_bg = len(groups)
    elif use_shots:
        has_cut = any(s.get("cut") for s in subs)
        groups = [[0]]
        for k in range(1, len(subs)):
            if has_cut:
                new = bool(subs[k].get("cut"))
            else:
                new = sum(sub_dur[j] for j in groups[-1]) >= 6.5
            groups.append([k]) if new else groups[-1].append(k)
        # subject 1 lan cho ca canh (cache) -> geometry shot + quy dao camera (a12-a13)
        _sj = _scene_subject(clip, scene, opts) if _HAVE_CV2 else (0, 0, 0.0, 1, 1)
        _sub = (_sj[0], _sj[1]) if _sj[2] > 0 else None
        shot_imgs = _shot_crops(clip, len(groups), i, tmp, sub=_sub)
        segs = []
        _pt = 0.0                                # offset giay cho hat: lien tuc qua cac shot
        for g, idxs in enumerate(groups):
            dd = sum(sub_dur[k] for k in idxs)
            fr = max(2, int(dd * FPS))
            if _HAVE_CV2:
                # 2.5-3% (truoc 4%): zoom sau qua lam mat dau nhan vat o shot can
                kv = os.path.join(FILM, f"_kbv_{i}_{g}.mp4")
                last = (g == len(groups) - 1)
                _rect = _shot_geom(_sj[3], _sj[4], g, i, sub=_sub)
                _cam = _cam_for(clip, g + i, opts, scene=scene, shot_rect=_rect)   # (a10)
                _kb_video(shot_imgs[g], fr, zoom_in=((g + i) % 2 == 0),
                          out_path=kv, zoom=0.025, cam=_cam,
                          trans_out=(_trans if last else None), cut_at=(fr if last else None),
                          head_black=(_hb_frames if g == 0 else 0),
                          particles=((_pf, _pt) if _pf is not None else None))
                _pt += fr / FPS
                tmp.append(kv)
                inputs += ["-i", kv]
                fc.append(f"[{g}:v]setpts=PTS-STARTPTS[sh{g}]")
            else:                                    # fallback zoompan (giat nhe)
                # TODO (a15): zoompan x/y theo tam nhan vat (hien van zoom quanh tam)
                # YC2: khong cv2 -> BO QUA lop hat (chi co o duong _kb_video)
                inputs += ["-loop", "1", "-i", shot_imgs[g]]
                e = f"(3*pow(on/{fr},2)-2*pow(on/{fr},3))"
                z = f"1.0+0.025*{e}" if (g + i) % 2 == 0 else f"1.025-0.025*{e}"
                fc.append(f"[{g}:v]scale={W*2}:{H*2},zoompan=z='{z}':d={fr}:"
                          f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},"
                          f"trim=end_frame={fr},setpts=PTS-STARTPTS[sh{g}]")
            segs.append(f"[sh{g}]")
        fc.append("".join(segs) + f"concat=n={len(groups)}:v=1:a=0,format=yuv420p[bg]")
        n_bg = len(groups)
    else:
        kb = is_img and opts.get("kenburns", True)
        if is_vid:
            inputs += ["-stream_loop", "-1", "-i", clip]
        elif is_img and kb and _HAVE_CV2:
            # +1s du phong: bg video huu han (khong -loop) phai dai hon audio
            kv = os.path.join(FILM, f"_kbv_{i}.mp4")
            _kb_video(clip, int(scene_dur * FPS) + FPS, zoom_in=(i % 2 == 0),
                      out_path=kv, zoom=0.05,
                      cam=_cam_for(clip, i, opts, scene=scene),      # (a11) camera huong nhan vat
                      trans_out=_trans, cut_at=int(scene_dur * FPS),
                      head_black=_hb_frames,
                      particles=((_pf, 0.0) if _pf is not None else None))
            tmp.append(kv)
            inputs += ["-i", kv]
        elif is_img:
            inputs += ["-loop", "1", "-i", clip]     # khong cv2 -> bo qua hat (YC2)
        else:
            inputs += ["-f", "lavfi", "-i", f"color=c=0x101018:s={W}x{H}:r={FPS}"]
        if kb and _HAVE_CV2:
            fc.append("[0:v]format=yuv420p[bg]")
        elif kb:
            frames = max(2, int(scene_dur * FPS) + 2)
            fc.append(f"[0:v]{_kb_filter(i, frames)}[bg]")
        else:
            fc.append(f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
                      f"crop={W}:{H},fps={FPS},format=yuv420p[bg]")
        n_bg = 1
    cur = "[bg]"
    for k, p in enumerate(sub_pngs):
        inputs += ["-loop", "1", "-i", p]
        idx = n_bg + k
        s0, e0 = starts[k], starts[k] + sub_dur[k]
        if SUB_FADE:
            fd = min(0.35, max(0.15, sub_dur[k] * 0.18))   # phụ đề FADE lên/xuống, không 'pop'
            sf = f"[sf{k}]"
            fc.append(f"[{idx}:v]format=rgba,fade=t=in:st={s0:.2f}:d={fd:.2f}:alpha=1,"
                      f"fade=t=out:st={max(s0, e0-fd):.2f}:d={fd:.2f}:alpha=1{sf}")
            src = sf
        else:                                              # tat fade (mac dinh): overlay thang
            src = f"[{idx}:v]"
        out = f"[v{k}]" if k < len(sub_pngs) - 1 else "[v]"
        fc.append(f"{cur}{src}overlay=0:0:enable='between(t,{s0:.2f},{e0:.2f})'{out}")
        cur = out
    if not sub_pngs:
        fc.append(f"[bg]null[v]")
    filt = ";".join(fc)

    # audio: giong/thoai + tieng clip + SFX khong khi — tron theo trong so
    sfx = (scene.get("sfx") or "").strip()
    srcs = []                              # (map_expr, volume)
    ai = n_bg + len(sub_pngs)              # index audio input ke tiep
    if scene_audio:
        inputs += ["-i", scene_audio]
        srcs.append((f"{ai}:a", 1.0)); ai += 1
    if keep:
        srcs.append(("0:a", 0.45 if scene_audio else 1.0))
    if sfx and os.path.exists(sfx):        # nen khong khi (quan/pho/mua...) lap vo han, am nho
        inputs += ["-stream_loop", "-1", "-i", sfx]
        srcs.append((f"{ai}:a", float(scene.get("sfx_vol", 0.2)))); ai += 1
    if not srcs:                           # cau: im lang
        inputs += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        srcs.append((f"{ai}:a", 1.0)); ai += 1
    if len(srcs) == 1 and srcs[0][1] >= 1.0:
        a_filt, amap = "", srcs[0][0] + ("?" if srcs[0][0] == "0:a" else "")
    else:
        parts, labs = [], []
        for j, (m, v) in enumerate(srcs):
            parts.append(f"[{m}]volume={v}[aa{j}]"); labs.append(f"[aa{j}]")
        a_filt = (";" + ";".join(parts) + ";" + "".join(labs)
                  + f"amix=inputs={len(srcs)}:duration=first:dropout_transition=0:normalize=0[a]")
        amap = "[a]"

    cmd = ["ffmpeg", "-y", *inputs, "-t", f"{scene_dur:.2f}",
           "-filter_complex", filt + a_filt,
           "-map", "[v]", "-map", amap,
           *X264_SEG, "-r", str(FPS), "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
           "-shortest", vp]
    subprocess.run(cmd, check=True, capture_output=True)
    for f in tmp:
        if os.path.exists(f):
            try: os.remove(f)
            except OSError: pass
    return vp, scene_dur


# ---------- CARD (bìa đầu / cuối) — đồ hoạ như title phim ----------
def make_card(kind, title, sub="", out_path=None, dur=3.5, opts=None):
    """1 cảnh đồ hoạ: nền tối điện ảnh + tiêu đề canh giữa + Ken Burns nhẹ + fade. kind=title|end."""
    opts = opts or {}
    col = Image.new("RGB", (1, H))                        # gradient dọc dịu (nhanh: 1 cột rồi kéo ngang)
    cpx = col.load()
    for y in range(H):
        t = y / H; base = 14 + int(12 * (0.5 - abs(t - 0.5)))
        cpx[0, y] = (max(0, base), max(0, base - 2), base + 8)
    im = col.resize((W, H))
    d = ImageDraw.Draw(im); cx = W // 2
    if kind == "title":
        ef = sp.font("viet", 34)
        d.text((cx, H * 0.34), (sub or "PHIM TIẾNG TRUNG").upper(), font=ef,
               fill=(198, 186, 240), anchor="ma")
        tf = sp.font("viet", 78)
        for j, ln in enumerate(sp.wrap_text(d, title, tf, int(W * 0.8))[:2]):
            d.text((cx, H * 0.42 + j * (tf.size + 10)), ln, font=tf, fill=(248, 246, 255), anchor="ma")
        d.line([(cx - 90, H * 0.60), (cx + 90, H * 0.60)], fill=(150, 130, 220), width=3)
    else:
        zf = sp.font("zh", 120)
        d.text((cx, H * 0.34), "完", font=zf, fill=(240, 236, 250), anchor="ma")
        tf = sp.font("viet", 66)
        d.text((cx, H * 0.52), title or "HẾT", font=tf, fill=(248, 246, 255), anchor="ma")
        sf = sp.font("viet", 36)
        d.text((cx, H * 0.63), sub or "Cảm ơn đã xem · Đăng ký kênh nhé!", font=sf,
               fill=(198, 186, 240), anchor="ma")
    png = os.path.join(FILM, f"_card_{kind}.png"); im.save(png)
    out_path = out_path or os.path.join(FILM, f"_cardvid_{kind}.mp4")
    frames = int(dur * FPS)
    fade = (f"fade=t=in:st=0:d=0.6,fade=t=out:st={max(0,dur-0.6):.2f}:d=0.6,format=yuv420p")
    if _HAVE_CV2:                                     # zoom cham subpixel (muot), roi fade
        kbv = _kb_video(png, frames, zoom_in=True,
                        out_path=os.path.join(FILM, f"_cardkb_{kind}.mp4"),
                        zoom=min(0.012 * dur, 0.08))
        subprocess.run(["ffmpeg", "-y", "-i", kbv,
                        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{dur}",
                        "-vf", fade, "-map", "0:v", "-map", "1:a",
                        *X264_SEG, "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "44100", "-ac", "2",
                        "-shortest", out_path], check=True, capture_output=True)
        try: os.remove(kbv)
        except OSError: pass
    else:                                             # fallback zoompan
        # (b6) smoothstep thay tuyen tinh -> khop nhip voi duong cv2
        _ze = f"(3*pow(on/{frames},2)-2*pow(on/{frames},3))"
        zexpr = f"1.0+{min(0.012 * dur, 0.08):.4f}*{_ze}"
        vf = (f"scale={W*2}:{H*2},zoompan=z='{zexpr}':d={frames}:x='iw/2-(iw/zoom/2)':"
              f"y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS}," + fade)
        subprocess.run(["ffmpeg", "-y", "-loop", "1", "-i", png,
                        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{dur}",
                        "-vf", vf, "-map", "0:v", "-map", "1:a",
                        *X264_SEG, "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "44100", "-ac", "2",
                        "-shortest", out_path], check=True, capture_output=True)
    try: os.remove(png)
    except OSError: pass
    return out_path, dur


# ---------- THUMBNAIL có chữ tiêu đề (CTR) ----------
def make_title_thumb(video_path, title, header, out_jpg, bg_image=None):
    """Rút 1 khung 'đắt' rồi phủ tiêu đề lớn (serif) + eyebrow -> thumbnail bắt mắt.
    bg_image: nếu có -> dùng ảnh nền SẠCH (không dính phụ đề); không -> lấy khung từ video."""
    frame = None
    if bg_image and os.path.exists(bg_image) and not _is_video(bg_image):
        src = bg_image
    else:
        t = max(0.5, _dur(video_path) * 0.62)             # khung ~cao trào
        frame = out_jpg + ".f.jpg"
        subprocess.run(["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", video_path,
                        "-frames:v", "1", "-q:v", "2", frame], check=True, capture_output=True)
        src = frame
    im = Image.open(src).convert("RGB").resize((1280, 720), Image.LANCZOS)
    ov = Image.new("RGBA", (1280, 720), (0, 0, 0, 0)); od = ImageDraw.Draw(ov)
    for yy in range(360, 720):                             # scrim tối dần lên từ đáy
        a = int(210 * ((yy - 360) / 360) ** 1.3)
        od.line([(0, yy), (1280, yy)], fill=(0, 0, 0, a))
    im = Image.alpha_composite(im.convert("RGBA"), ov)
    d = ImageDraw.Draw(im); cx = 640
    ef = sp.font("viet", 34)
    d.text((cx, 470), (header or "PHIM TIẾNG TRUNG").upper(), font=ef, anchor="ma",
           fill=(240, 224, 180), stroke_width=2, stroke_fill=(0, 0, 0, 200))
    # tiêu đề lớn, tự xuống dòng, viền đậm
    tf = sp.font("viet", 74)
    lines = sp.wrap_text(d, title, tf, 1160)[:2]
    y = 700 - len(lines) * (tf.size + 8)
    for ln in lines:
        d.text((cx, y), ln, font=tf, anchor="ma", fill=(255, 255, 255),
               stroke_width=5, stroke_fill=(0, 0, 0, 230)); y += tf.size + 8
    d.rounded_rectangle([cx - 70, 456, cx + 70, 460], radius=2, fill=(220, 180, 90))
    im.convert("RGB").save(out_jpg, quality=90)
    if frame and os.path.exists(frame):
        try: os.remove(frame)
        except OSError: pass
    return out_jpg


# ---------- GHEP PHIM ----------
def make_film(scenes, opts, out_path):
    """Noi cac canh -> tap phim. opts: voice, azure, sub_pinyin, rate, music_file, music_vol,
    kenburns, transition('none'|'fade'), grade, title_card, end_card, film_title, film_header."""
    # NANG CAP DIEN ANH: co cv2 -> chuyen canh bake theo beat (plan_transitions), join = cut
    # -> timing SRT/chapters/nhac BAT BIEN. Thieu cv2 -> giu duong xfade cu.
    if _HAVE_CV2 and (opts.get("transition") or "fade") != "none":
        plan_transitions(scenes, opts)
        opts = dict(opts, transition="none")
    seg_videos, durs = [], []
    if opts.get("title_card") and opts.get("film_title"):
        cp, cd = make_card("title", opts["film_title"], opts.get("film_header", ""), dur=3.5, opts=opts)
        seg_videos.append(cp); durs.append(cd)
    for i, sc in enumerate(scenes):
        vp, d = make_scene(sc, opts, i)
        seg_videos.append(vp); durs.append(d)
    if opts.get("end_card"):
        cp, cd = make_card("end", "HẾT", "", dur=3.0, opts=opts)
        seg_videos.append(cp); durs.append(cd)
    return _concat_and_music(seg_videos, opts, out_path, sum(durs))


def _grade_simple(letterbox=False):
    """Grade TỰ NHIÊN, sạch (không ám màu giả): chỉ nhẹ tương phản + độ nét + vignette rất mờ."""
    ch = "eq=contrast=1.04:saturation=1.05:gamma=0.99,vignette=PI/8"
    if letterbox:
        ch += "," + _letterbox_filter()
    return ch

def _grade_rich(inlab, outlab, letterbox=False):
    """Filter_complex: grade tự nhiên (đã bỏ bloom/teal-orange cho đỡ 'phèn')."""
    return f"{inlab}{_grade_simple(letterbox)}{outlab}"

def _grade_chain():
    return _grade_simple()


def _join_video(seg_videos, opts):
    """Nối clip cảnh -> 1 video (không tiếng nền). Có chuyển cảnh mờ + grade. Tra path narr."""
    narr = os.path.join(FILM, "_film_narr.mp4")
    trans = (opts.get("transition") or "fade").lower()
    grade = bool(opts.get("grade", True))
    lb = bool(opts.get("letterbox"))
    n = len(seg_videos)
    # CHUYEN CANH MO (dissolve) — xfade/acrossfade chuoi
    if trans in ("fade", "dissolve") and n >= 2:
        try:
            durs = [max(0.1, _dur(v)) for v in seg_videos]
            TD = 0.75                                       # dissolve dài hơn -> mượt, đỡ 'cắt phựt'
            inp = []
            for v in seg_videos:
                inp += ["-i", v]
            fc, curv, cura, off = [], "[0:v]", "[0:a]", durs[0] - TD
            for k in range(1, n):
                ov = f"[vx{k}]" if k < n - 1 else "[vj]"
                oa = f"[ax{k}]" if k < n - 1 else "[aj]"
                # (c11) fadeblack = dip-to-black (dong bo phong cach voi duong cv2);
                # TD=0.75 GIU NGUYEN — app.py:2192 tinh chapter theo dung so nay
                fc.append(f"{curv}[{k}:v]xfade=transition=fadeblack:duration={TD}:offset={off:.3f}{ov}")
                fc.append(f"{cura}[{k}:a]acrossfade=d={TD}{oa}")
                curv, cura = ov, oa
                off += durs[k] - TD
            vmap = "[vj]"
            if grade:
                fc.append(_grade_rich("[vj]", "[vg]", lb)); vmap = "[vg]"   # bloom+teal-orange+grain(+letterbox)
            elif lb:
                fc.append(f"[vj]{_letterbox_filter()}[vg]"); vmap = "[vg]"
            subprocess.run(["ffmpeg", "-y", *inp, "-filter_complex", ";".join(fc),
                            "-map", vmap, "-map", "[aj]",
                            *X264, "-pix_fmt", "yuv420p", "-r", str(FPS),
                            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2", narr],
                           check=True, capture_output=True)
            return narr
        except subprocess.CalledProcessError:
            # KHONG nuot cam: roi ve noi thang lam timing khac voi du tinh cua app (TD=0.75)
            print("[FILM] ⚠ xfade loi -> noi thang (khong overlap); "
                  "SRT/chapters tinh theo overlap se lech!")
    # NỐI THẲNG (cut) hoặc fallback
    lst = os.path.join(FILM, "_concat.txt")
    with open(lst, "w") as f:
        for v in seg_videos:
            f.write(f"file '{v.replace(os.sep,'/')}'\n")
    _vfchain = _grade_simple(lb) if grade else (_letterbox_filter() if lb else "")
    vf = ["-vf", _vfchain] if _vfchain else []
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                    "-vsync", "cfr", "-r", str(FPS), *vf, *X264, "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2", narr],
                   check=True, capture_output=True)
    try: os.remove(lst)
    except OSError: pass
    return narr


def _add_roomtone(narr):
    """Tron 'room tone' (nhieu nau rat nho) duoi toan phim -> im lang khong bi 'chet' so."""
    out = os.path.join(FILM, "_film_rt.mp4")
    fc = ("[1:a]volume=0.012,lowpass=f=500[rt];"
          "[0:a][rt]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]")
    subprocess.run(["ffmpeg", "-y", "-i", narr,
                    "-f", "lavfi", "-i", "anoisesrc=r=44100:color=brown:seed=7",
                    "-filter_complex", fc, "-map", "0:v", "-map", "[a]",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", out],
                   check=True, capture_output=True)
    os.replace(out, narr)
    return narr


def _concat_and_music(seg_videos, opts, out_path, total):
    """Noi cac clip canh (da dung) -> chuyen canh + grade + roomtone + nhac (ducking) -> out_path."""
    narr = _join_video(seg_videos, opts)
    if opts.get("roomtone", True):
        try:
            narr = _add_roomtone(narr)
        except subprocess.CalledProcessError:
            pass                                          # loi -> bo qua, khong chan phim
    total = _dur(narr) or total                           # do dai THAT (fix: max() giu so phong dai
                                                          # khi xfade rut ngan -> nhac cut phut khong fade)
    music = (opts.get("music_file") or "").strip()
    if music and os.path.exists(music):
        vol = float(opts.get("music_vol", 0.14))
        duck = bool(opts.get("duck", True))
        if duck:
            # DUCKING: nhac tu dong nho lai khi co loi doc (sidechain tu chinh tieng phim)
            fc = (f"[0:a]asplit=2[voice][sc];"
                  f"[1:a]volume={vol},afade=t=in:st=0:d=2,afade=t=out:st={max(0,total-3):.2f}:d=3[mv];"
                  f"[mv][sc]sidechaincompress=threshold=0.02:ratio=8:attack=15:release=350[mduck];"
                  f"[voice][mduck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]")
        else:
            fc = (f"[1:a]volume={vol},afade=t=in:st=0:d=2,afade=t=out:st={max(0,total-3):.2f}:d=3[m];"
                  f"[0:a][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]")
        try:
            subprocess.run(["ffmpeg", "-y", "-i", narr, "-stream_loop", "-1", "-i", music,
                            "-filter_complex", fc, "-map", "0:v", "-map", "[a]",
                            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", out_path],
                           check=True, capture_output=True)
        except subprocess.CalledProcessError:             # ducking loi -> tron thuong
            fc = (f"[1:a]volume={vol},afade=t=in:st=0:d=2,afade=t=out:st={max(0,total-3):.2f}:d=3[m];"
                  f"[0:a][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]")
            try:
                subprocess.run(["ffmpeg", "-y", "-i", narr, "-stream_loop", "-1", "-i", music,
                                "-filter_complex", fc, "-map", "0:v", "-map", "[a]",
                                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", out_path],
                               check=True, capture_output=True)
            except subprocess.CalledProcessError as e:
                # capture_output nuot het stderr -> UI chi thay cau lenh, khong thay ly do.
                # Dua 6 dong cuoi cua ffmpeg ra ngoai de con biet duong ma sua.
                err = (e.stderr or b"").decode("utf-8", "ignore").strip().splitlines()
                raise RuntimeError("Trộn nhạc nền lỗi:\n" + "\n".join(err[-6:] or ["(ffmpeg không nói gì)"]))
    else:
        shutil.move(narr, out_path)           # os.replace loi khi out_path khac o dia (WinError 17)
    for v in seg_videos:
        try: os.remove(v)
        except OSError: pass
    if os.path.exists(narr) and narr != out_path:
        try: os.remove(narr)
        except OSError: pass
    return out_path, round(total, 2)
