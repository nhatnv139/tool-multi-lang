# -*- coding: utf-8 -*-
"""film.py — Dựng PHIM: ghép nhiều CẢNH (mỗi cảnh = 1 clip video/ảnh) thành 1 tập.
Mỗi cảnh: giữ TIẾNG gốc của clip (tuỳ chọn) + phụ đề (Hán / pinyin / nghĩa) + (tuỳ chọn) lời dẫn TTS.
Nối các cảnh -> tập phim, thêm nhạc nền. KHÔNG có layout học (phim thuần + phụ đề dưới)."""
import os, re, subprocess, hashlib
from PIL import Image, ImageDraw
import style_pastel as sp
from pypinyin import pinyin as _py, Style as _PyStyle

W, H, FPS = 1920, 1080, 30
_HERE = os.path.dirname(os.path.abspath(__file__))
FILM = os.path.join(_HERE, "assets", "film")
os.makedirs(FILM, exist_ok=True)
X264 = ["-c:v", "libx264", "-preset", "medium", "-crf", "20"]
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
def _shot_crops(img_path, n, i, tmp):
    """1 anh -> n shot (toan canh / trung / can, dao goc trai-phai) nhu phim co nhieu cu may."""
    im = Image.open(img_path).convert("RGB")
    iw, ih = im.size
    base_w = min(iw, ih * W // H)          # cua so 16:9 lon nhat trong anh
    base_h = base_w * H // W
    outs = []
    for k in range(n):
        m = (k + i) % 4
        # oy keo LEN TREN (0.40-0.45): mat nhan vat luon o nua tren anh,
        # crop lech xuong (0.54-0.56 cu) se cat cut dau khi vao trung/can canh.
        if m == 0:   f, ox, oy = 1.00, 0.50, 0.50      # TOAN canh (wide)
        elif m == 1: f, ox, oy = 0.80, 0.40, 0.45      # TRUNG - lech trai, neo vung mat
        elif m == 2: f, ox, oy = 0.80, 0.60, 0.45      # TRUNG - lech phai, neo vung mat
        else:        f, ox, oy = 0.70, 0.50, 0.40      # CAN - giua, neo phan tren
        cw, ch = int(base_w * f), int(base_h * f)
        x0 = max(0, min(iw - cw, int(ox * iw) - cw // 2))
        y0 = max(0, min(ih - ch, int(oy * ih) - ch // 2))
        crop = im.crop((x0, y0, x0 + cw, y0 + ch)).resize((W, H), Image.LANCZOS)
        p = os.path.join(FILM, f"_shot_{i}_{k}.jpg")
        crop.save(p, quality=90)
        outs.append(p); tmp.append(p)
    return outs


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


def _kb_filter(i, frames):
    """Ken Burns TỐI GIẢN: chỉ đẩy-vào / kéo-ra RẤT NHẸ, canh giữa, KHÔNG lia (đỡ chóng mặt/giật).
    Supersample cao (3x) -> zoom mượt, không rung pixel."""
    T = max(2, frames)
    e = f"(3*pow(on/{T},2)-2*pow(on/{T},3))"        # smoothstep 0->1 (ease in-out)
    z = f"1.0+0.05*{e}" if i % 2 == 0 else f"1.05-0.05*{e}"   # ±5% rất nhẹ
    S, SH = W * 3, H * 3
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
    is_vid = _is_video(clip) and os.path.exists(clip)
    is_img = clip and os.path.exists(clip) and not is_vid
    subs = [s for s in (scene.get("subs") or []) if (s.get("hz") or s.get("vi"))]
    narrate = bool(scene.get("narrate"))
    keep = bool(scene.get("keep_audio", True)) and is_vid
    show_py = bool(opts.get("sub_pinyin", True))
    tmp = []

    # 1) TIMELINE (thoi luong tung phu de) + AUDIO track
    scene_audio = None
    if narrate and subs:
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
    # FAKE COVERAGE: anh tinh + >=2 cau -> cat SHOT (toan/trung/can) nhu phim co nhieu cu may.
    # CHUYEN SHOT THEO NOI DUNG, khong phai 1 cau/1 shot (giat lien tuc):
    #   - sub co "cut": true  -> mo shot moi tai cau do (kich ban tu quyet dinh diem chuyen)
    #   - khong danh dau "cut" -> tu gom cac cau lien tiep den ~6.5s roi moi chuyen
    use_shots = (is_img and narrate and len(subs) >= 2 and opts.get("film_mode", True))
    if use_shots:
        has_cut = any(s.get("cut") for s in subs)
        groups = [[0]]
        for k in range(1, len(subs)):
            if has_cut:
                new = bool(subs[k].get("cut"))
            else:
                new = sum(sub_dur[j] for j in groups[-1]) >= 6.5
            groups.append([k]) if new else groups[-1].append(k)
        shot_imgs = _shot_crops(clip, len(groups), i, tmp)
        for p in shot_imgs:
            inputs += ["-loop", "1", "-i", p]
        segs = []
        for g, idxs in enumerate(groups):
            dd = sum(sub_dur[k] for k in idxs)
            fr = max(2, int(dd * FPS))
            # 2.5% (truoc 4%): zoom sau qua lam mat dau nhan vat o shot can
            z = f"1.0+0.025*(on/{fr})" if (g + i) % 2 == 0 else f"1.025-0.025*(on/{fr})"
            fc.append(f"[{g}:v]scale={W*2}:{H*2},zoompan=z='{z}':d={fr}:"
                      f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},"
                      f"trim=end_frame={fr},setpts=PTS-STARTPTS[sh{g}]")
            segs.append(f"[sh{g}]")
        fc.append("".join(segs) + f"concat=n={len(groups)}:v=1:a=0,format=yuv420p[bg]")
        n_bg = len(groups)
    else:
        if is_vid:
            inputs += ["-stream_loop", "-1", "-i", clip]
        elif is_img:
            inputs += ["-loop", "1", "-i", clip]
        else:
            inputs += ["-f", "lavfi", "-i", f"color=c=0x101018:s={W}x{H}:r={FPS}"]
        if is_img and opts.get("kenburns", True):
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
        fd = min(0.35, max(0.15, sub_dur[k] * 0.18))       # phụ đề FADE lên/xuống, không 'pop'
        sf = f"[sf{k}]"
        fc.append(f"[{idx}:v]format=rgba,fade=t=in:st={s0:.2f}:d={fd:.2f}:alpha=1,"
                  f"fade=t=out:st={max(s0, e0-fd):.2f}:d={fd:.2f}:alpha=1{sf}")
        out = f"[v{k}]" if k < len(sub_pngs) - 1 else "[v]"
        fc.append(f"{cur}{sf}overlay=0:0:enable='between(t,{s0:.2f},{e0:.2f})'{out}")
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
           *X264, "-r", str(FPS), "-pix_fmt", "yuv420p",
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
    zexpr = "min(zoom+0.0004,1.08)"
    vf = (f"scale={W*2}:{H*2},zoompan=z='{zexpr}':d={frames}:x='iw/2-(iw/zoom/2)':"
          f"y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},"
          f"fade=t=in:st=0:d=0.6,fade=t=out:st={max(0,dur-0.6):.2f}:d=0.6,format=yuv420p")
    subprocess.run(["ffmpeg", "-y", "-loop", "1", "-i", png,
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{dur}",
                    "-vf", vf, "-map", "0:v", "-map", "1:a",
                    *X264, "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "44100", "-ac", "2",
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
                fc.append(f"{curv}[{k}:v]xfade=transition=fade:duration={TD}:offset={off:.3f}{ov}")
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
            pass                                          # lỗi filter -> rơi về nối thẳng
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
    total = max(total, _dur(narr))                        # xfade rut ngan -> lay dung do dai
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
            subprocess.run(["ffmpeg", "-y", "-i", narr, "-stream_loop", "-1", "-i", music,
                            "-filter_complex", fc, "-map", "0:v", "-map", "[a]",
                            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", out_path],
                           check=True, capture_output=True)
    else:
        os.replace(narr, out_path)
    for v in seg_videos:
        try: os.remove(v)
        except OSError: pass
    if os.path.exists(narr) and narr != out_path:
        try: os.remove(narr)
        except OSError: pass
    return out_path, round(total, 2)
