# -*- coding: utf-8 -*-
"""
Tu dong tao video bai hoc tieng Trung (HSK) tu file JSON.
- Tu sinh background gradient (PIL)
- Render slide chu Han + Pinyin + nghia tieng Viet
- Giong doc AI (edge-tts) - tieng Trung + tieng Viet
- Ghep slide + audio dong bo bang FFmpeg
Cach dung:  python generate.py data/lesson01.json
"""
import os, sys, json, subprocess, shutil, asyncio, time
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import edge_tts
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import style_pastel                       # bo render kieu pastel (pinyin tren chu)
render_slide = style_pastel.render_slide  # dung render moi thay cho ban do cu

ANIM_TYPES = {"vocab", "sentence", "practice_a", "dialogue"}   # cac loai chu hien dan

# ---------- CAU HINH ----------
W, H = 1920, 1080
FPS = 25
PAD = 0.8                      # giay im lang them sau moi doan
# Chat luong hinh x264: CRF 18 (gan lossless voi slide tinh) — YouTube nen it bi nat chu
X264 = ["-c:v", "libx264", "-crf", "18", "-preset", "medium"]
# Chuan hoa am luong final theo chuan YouTube (-14 LUFS)
LOUDNORM = "loudnorm=I=-14:TP=-1.5:LRA=11"

# ---------- CAM XUC GIONG DOC (tu nhan dien theo noi dung cau) ----------
# dr: lech toc do (%); pitch: lech cao do (edge/azure); az: (style, styledegree) Azure;
# el: (delta stability, delta style) ElevenLabs; gm: goi y giong cho Gemini
EMO_CONF = {
    "excited": dict(dr=+9,  pitch="+16Hz", az=("excited", "1.3"),  el=(-0.22, +0.28),
                    gm="hào hứng, phấn khích, tràn đầy năng lượng"),
    "happy":   dict(dr=+5,  pitch="+10Hz", az=("cheerful", "1.2"), el=(-0.12, +0.18),
                    gm="vui tươi, rạng rỡ, như đang mỉm cười khi nói"),
    "sad":     dict(dr=-13, pitch="-9Hz",  az=("sad", "1.3"),      el=(+0.10, +0.12),
                    gm="buồn man mác, chậm rãi, lắng đọng"),
    "gentle":  dict(dr=-7,  pitch="-2Hz",  az=("gentle", "1.2"),   el=(+0.06, +0.06),
                    gm="dịu dàng, vỗ về, thủ thỉ tâm tình"),
    # --- bộ cảm xúc cho PHIM (đặt tay qua tag {emo} trong kịch bản) ---
    "tender":  dict(dr=-8,  pitch="-3Hz",  az=("affectionate", "1.6"), el=(+0.04, +0.10),
                    gm="âu yếm, trìu mến, nghẹn ngào yêu thương"),
    "calm":    dict(dr=-6,  pitch="-2Hz",  az=("calm", "1.1"),        el=(+0.04, +0.04),
                    gm="điềm tĩnh, nhẹ nhàng, sâu lắng"),
    "hopeful": dict(dr=-2,  pitch="+2Hz",  az=("hopeful", "1.3"),     el=(-0.04, +0.10),
                    gm="hi vọng, ấm áp, hướng về phía trước"),
    "lyrical": dict(dr=-6,  pitch="-2Hz",  az=("lyrical", "1.3"),     el=(+0.04, +0.08),
                    gm="tự sự, trữ tình, như đang kể chuyện xúc động"),
    "sorrow":  dict(dr=-15, pitch="-11Hz", az=("sad", "1.7"),        el=(+0.14, +0.14),
                    gm="đau xót, nghẹn ngào, chực trào nước mắt"),
}

def emo_by_name(name):
    """Lay emo dict theo TEN (dat tay trong kich ban phim), None neu khong co."""
    c = EMO_CONF.get((name or "").strip().lower())
    return dict(name=name.strip().lower(), **c) if c else None
import re as _re
_EMO_PAT = [   # uu tien tu tren xuong: buon > diu dang > phan khich > vui
    ("sad",     _re.compile(r"难过|伤心|哭|可惜|遗憾|唉|孤单|寂寞|想念|失望|心疼|分手|离开了|再见了|痛")),
    ("gentle",  _re.compile(r"别担心|没关系|放心|慢慢来|休息|辛苦了|晚安|别怕|没事的|加油")),
    ("excited", _re.compile(r"太好了|太棒了|棒极了|好厉害|哇[!！，]|恭喜|了不起|真的吗[?？]|中奖")),
    ("happy",   _re.compile(r"哈哈|开心|高兴|真好|真不错|喜欢|笑了|愉快|幸福|好玩|有意思")),
]

def detect_emotion(text):
    """Nhan dien cam xuc cau tieng Trung don gian theo tu khoa. None = trung tinh."""
    if not text:
        return None
    for name, pat in _EMO_PAT:
        if pat.search(text):
            return dict(name=name, **EMO_CONF[name])
    return None

def _seg_emo(ctx, text):
    """Cam xuc cho 1 cau (None neu nguoi dung tat emotion_auto)."""
    if not ctx.get("emotion_auto", True):
        return None
    return detect_emotion(text)

def _emo_rate(rate, emo):
    """Cong lech toc do cam xuc vao rate goc: '-8%' + dr(+5) -> '-3%'."""
    if not emo:
        return rate
    try:
        pct = int(str(rate).replace("%", ""))
    except ValueError:
        pct = -8
    return f"{pct + int(emo.get('dr', 0))}%"
def _pick_font(*candidates):
    """Tra ve font dau tien ton tai (cross-platform Windows/macOS/Linux)."""
    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[-1]   # fallback: de Pillow bao loi ro rang

FONTS = {
    # zh dam / thuong: YaHei (Win) -> Hiragino Sans GB / PingFang (macOS)
    "zh_bold":   _pick_font("C:/Windows/Fonts/msyhbd.ttc",
                            "/System/Library/Fonts/Hiragino Sans GB.ttc",
                            "/System/Library/Fonts/PingFang.ttc"),
    "zh":        _pick_font("C:/Windows/Fonts/msyh.ttc",
                            "/System/Library/Fonts/Hiragino Sans GB.ttc",
                            "/System/Library/Fonts/PingFang.ttc"),
    "lat_bold":  _pick_font("C:/Windows/Fonts/arialbd.ttf",
                            "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    "lat":       _pick_font("C:/Windows/Fonts/arial.ttf",
                            "/System/Library/Fonts/Supplemental/Arial.ttf"),
}
VOICE_ZH = "zh-CN-XiaoxiaoNeural"
VOICE_VI = "vi-VN-HoaiMyNeural"
# Mau (theme do - vang Trung Hoa)
C_TOP    = (138, 16, 16)       # do dam
C_BOT    = (58, 5, 5)          # do tham
C_GOLD   = (255, 209, 102)
C_WHITE  = (255, 255, 255)
C_PINYIN = (255, 224, 130)
C_VIET   = (180, 220, 255)

ROOT = os.path.dirname(os.path.abspath(__file__))
TMP  = os.path.join(ROOT, "assets")
SLIDES = os.path.join(TMP, "slides")
AUDIO  = os.path.join(TMP, "audio")
OUT    = os.path.join(ROOT, "output")
for d in (SLIDES, AUDIO, OUT):
    os.makedirs(d, exist_ok=True)

_font_cache = {}
def font(key, size):
    k = (key, size)
    if k not in _font_cache:
        _font_cache[k] = ImageFont.truetype(FONTS[key], size)
    return _font_cache[k]

# ---------- BACKGROUND ----------
_base_bg = None
def make_bg(hanzi_watermark=""):
    """Gradient doc + thanh vang (cache 1 lan vi moi slide giong nhau)."""
    global _base_bg
    if _base_bg is None:
        # gradient doc: tao cot 1px roi keo gian ra full width
        col = Image.new("RGB", (1, H))
        cpx = col.load()
        for y in range(H):
            t = y / H
            cpx[0, y] = (int(C_TOP[0]+(C_BOT[0]-C_TOP[0])*t),
                         int(C_TOP[1]+(C_BOT[1]-C_TOP[1])*t),
                         int(C_TOP[2]+(C_BOT[2]-C_TOP[2])*t))
        base = col.resize((W, H))
        dd = ImageDraw.Draw(base, "RGBA")
        dd.rectangle([0, 96, W, 100], fill=C_GOLD + (180,))
        dd.rectangle([0, H-100, W, H-96], fill=C_GOLD + (180,))
        _base_bg = base
    bg = _base_bg.copy()
    return bg, ImageDraw.Draw(bg, "RGBA")

def draw_chrome(d, header, footer):
    d.text((70, 48), header, font=font("lat_bold", 34), fill=C_GOLD)
    fb = font("lat", 30)
    bb = d.textbbox((0,0), footer, font=fb)
    d.text((W - (bb[2]-bb[0]) - 70, H-72), footer, font=fb, fill=(255,255,255,160))

def center_blocks(d, blocks, gap=26, top=None):
    """blocks = [(text, font_key, size, color), ...] xep doc, can giua."""
    sizes = []
    for text, fk, sz, col in blocks:
        bb = d.textbbox((0,0), text, font=font(fk, sz))
        sizes.append((bb[2]-bb[0], bb[3]-bb[1], bb[1]))
    total_h = sum(s[1] for s in sizes) + gap*(len(blocks)-1)
    y = (H - total_h)//2 if top is None else top
    for (text, fk, sz, col), (tw, th, oy) in zip(blocks, sizes):
        d.text(((W-tw)//2, y - oy), text, font=font(fk, sz), fill=col)
        y += th + gap

# ---------- RENDER TUNG LOAI SLIDE ----------
def _old_render_slide_RED(seg, ctx, path):   # GIU LAI THAM KHAO, khong dung nua
    bg, d = make_bg("")
    header = f'{ctx["hsk"]} · BÀI {int(ctx["id"])} — {ctx["title"]}'
    draw_chrome(d, header, "Tự học tiếng Trung mỗi ngày")
    t = seg["type"]

    if t == "title":
        center_blocks(d, [
            (f'{ctx["hsk"]}  ·  BÀI {int(ctx["id"])}', "lat_bold", 70, C_GOLD),
            (ctx["title"], "lat_bold", 96, C_WHITE),
            (ctx["hanzi_title"], "zh_bold", 300, C_GOLD),
        ], gap=40)

    elif t == "objectives":
        blocks = [("HÔM NAY BẠN SẼ HỌC", "lat_bold", 78, C_GOLD)]
        for ln in seg["lines"]:
            blocks.append(("•  " + ln, "lat_bold", 64, C_WHITE))
        center_blocks(d, blocks, gap=34)

    elif t == "section":
        lbl, fk, sz = seg["label"], "lat_bold", 130
        bb = d.textbbox((0,0), lbl, font=font(fk, sz))
        tw = bb[2]-bb[0]
        d.text(((W-tw)//2 - bb[0], (H-sz)//2), lbl, font=font(fk, sz), fill=C_WHITE)
        cx = W//2
        d.rectangle([cx-tw//2, (H+sz)//2 + 36, cx+tw//2, (H+sz)//2 + 46], fill=C_GOLD)

    elif t in ("vocab", "practice_a"):
        center_blocks(d, [
            (seg["hanzi"],  "zh_bold",  300, C_WHITE),
            (seg["pinyin"], "lat_bold", 92,  C_PINYIN),
            (seg["viet"],   "lat",      78,  C_VIET),
        ], gap=44)

    elif t == "sentence":
        center_blocks(d, [
            (seg["hanzi"],  "zh_bold",  170, C_WHITE),
            (seg["pinyin"], "lat_bold", 80,  C_PINYIN),
            ("→ " + seg["viet"], "lat", 70,  C_VIET),
        ], gap=40)

    elif t == "dialogue":
        rows = seg["rows"]
        # tinh chieu cao: moi luot = 2 dong
        line_zh, line_lat = 66, 46
        gap_turn = 30
        total = len(rows)*(line_zh+line_lat+8) + gap_turn*(len(rows)-1)
        y = (H - total)//2 + 40
        for r in rows:
            zh = f'{r["sp"]}：{r["hanzi"]}'
            d.text((230, y), zh, font=font("zh_bold", line_zh), fill=C_WHITE)
            y += line_zh + 8
            sub = f'{r["pinyin"]}   ({r["viet"]})'
            d.text((300, y), sub, font=font("lat", line_lat), fill=C_PINYIN)
            y += line_lat + gap_turn

    elif t == "practice_q":
        center_blocks(d, [
            ("LUYỆN TẬP", "lat_bold", 80, C_GOLD),
            (seg["question"], "lat_bold", 70, C_WHITE),
            ("Bạn thử trả lời nhé...", "lat", 56, C_VIET),
        ], gap=46)

    elif t == "outro":
        n = int(ctx["id"])
        center_blocks(d, [
            (f"Hôm nay bạn đã học xong Bài {n}!", "lat_bold", 76, C_WHITE),
            (f"LIKE và SUBSCRIBE để học tiếp Bài {n+1}", "lat_bold", 60, C_GOLD),
            ("再见!", "zh_bold", 160, C_WHITE),
        ], gap=44)

    bg.save(path)

# ---------- TTS ----------
def tts_for(seg, ctx):
    """Tra ve (text, voice). None neu khong can doc.
       Giong tieng Trung lay tu ctx['voice_zh'], tieng Viet ctx['voice_vi']."""
    vz = seg.get("_voice") or ctx.get("voice_zh", VOICE_ZH)   # _voice: giong rieng tung luot (podcast)
    vv = ctx.get("voice_vi", VOICE_VI)
    t = seg["type"]
    if t == "title":
        topic = ctx.get("topic", ctx["title"].lower())
        return (f'Chào mừng bạn đến với bài {int(ctx["id"])}, tự học tiếng Trung cho người mới. '
                f'Hôm nay chúng ta học {topic}.', vv)
    if t == "objectives":
        return ("Hôm nay bạn sẽ học: " + "; ".join(seg["lines"]), vv)
    if t == "section":
        return (None, None)
    if t in ("vocab", "practice_a"):
        return (f'{seg["hanzi"]}。{seg["hanzi"]}。', vz)
    if t == "sentence":
        return (seg["hanzi"], vz)
    if t == "dialogue":
        return ("。".join(r["hanzi"] for r in seg["rows"]), vz)
    if t == "practice_q":
        return (seg["question"], vv)
    if t == "outro":
        num = {1:"một",2:"hai",3:"ba",4:"bốn",5:"năm",6:"sáu",7:"bảy",8:"tám"}
        n = int(ctx["id"])
        return (f'Hôm nay bạn đã học xong bài {num.get(n,n)}! '
                f'Nhớ đăng ký kênh để học tiếp bài {num.get(n+1,n+1)}. Tạm biệt!', vv)
    return (None, None)

import hashlib, urllib.request, urllib.parse, urllib.error, base64
TTS_CACHE = os.path.join(TMP, "tts_cache")
os.makedirs(TTS_CACHE, exist_ok=True)

# ---------- AI MASCOT (Pollinations.ai - mien phi, khong can key) ----------
AI_CACHE = os.path.join(TMP, "ai_img")
os.makedirs(AI_CACHE, exist_ok=True)

def ai_mascot_image(prompt):
    """Tao hinh hoat hinh de thuong theo chu de, tach nen trang. Tra ve path PNG.
       Co cache theo prompt. Nem loi neu khong tai duoc (de fallback emoji)."""
    key = hashlib.md5(prompt.encode("utf-8")).hexdigest()
    out = os.path.join(AI_CACHE, key + ".png")
    if os.path.exists(out):
        return out
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt)
           + "?width=512&height=512&nologo=true")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    data = urllib.request.urlopen(req, timeout=120).read()
    raw = os.path.join(AI_CACHE, key + ".jpg")
    with open(raw, "wb") as f:
        f.write(data)
    # tach nen: flood-fill tu 4 goc (xu ly ca nen hoi am/gradient, khong thung nhan vat)
    from PIL import ImageDraw
    rgb = Image.open(raw).convert("RGB")
    w, h = rgb.size
    KEY = (255, 0, 255)
    for corner in [(0, 0), (w-1, 0), (0, h-1), (w-1, h-1)]:
        ImageDraw.floodfill(rgb, corner, KEY, thresh=42)
    out_data = [(r, g, b, 0) if (r, g, b) == KEY else (r, g, b, 255)
                for (r, g, b) in rgb.getdata()]
    im = Image.new("RGBA", rgb.size)
    im.putdata(out_data)
    im.save(out)
    return out

def setup_mascot(ctx):
    """Neu bat AI mascot: tao hinh theo chu de, gan vao ctx['_mascot_img']."""
    if not ctx.get("ai_mascot"):
        return
    base = ctx.get("image_prompt") or (
        f"adorable cute cartoon character mascot representing '{ctx.get('title','')}', "
        f"dynamic lively expressive pose, full body")
    prompt = (base + ", kawaii chibi style, soft pastel colors, clean modern flat "
              "illustration, cute big eyes, die-cut sticker, centered, "
              "plain solid pure white background, no shadow, high quality, detailed")
    try:
        ctx["_mascot_img"] = ai_mascot_image(prompt)
    except Exception as e:
        print("  (AI mascot loi, dung emoji thay the):", e)
        ctx["_mascot_img"] = None
def _tts_key(text, voice, rate, expressive=0, engine=""):
    return hashlib.md5(
        f"{voice}|{rate}|{expressive}|{engine}|{text}".encode("utf-8")
    ).hexdigest()

def _ssml_escape(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def synth_azure(text, voice, path, key, region, rate="-8%", mood=None, emo=None):
    """Azure TTS (giong HD/Multilingual tu nhien hon). Ghi mp3 ra path.
       mood -> mstts:express-as style; emo (tu detect_emotion) -> style + do manh +
       cao do theo cam xuc cau. HTTP 400 -> fallback SSML thuong."""
    print(f"[DEBUG-TTS] synth_azure text={text!r} len={len(text or '')} "
          f"key_len={len(key or '')} region={region!r}")
    # Ha tong ngay trong ten giong: 'vi-VN-NamMinhNeural@-4st' -> giong nam TRAM ke chuyen.
    # Truoc day chi edge doc duoc cu phap '@', azure thi nhet ca '@-4st' vao name -> 400.
    voice, base_pitch = _edge_pitch_split(voice)
    pitch = _pitch_add(base_pitch, emo["pitch"] if emo else None)
    pitch_attr = f' pitch="{pitch}"' if pitch else ""
    inner = (f'<prosody rate="{_norm_rate(rate)}"{pitch_attr}>{_ssml_escape(text)}</prosody>')
    # style: cam xuc cau (emo) > mood video > narration-relaxed
    if emo:
        style, degree = emo["az"]
    else:
        style = {"calm": "calm", "sad": "sad", "warm": "chat", "gentle": "gentle",
                 "story": "narration-relaxed", "night": "narration-relaxed"}.get(
            mood, "narration-relaxed")
        degree = None
    deg_attr = f' styledegree="{degree}"' if degree else ""
    ssml_x = (f'<speak version="1.0" '
              f'xmlns="http://www.w3.org/2001/10/synthesis" '
              f'xmlns:mstts="https://www.w3.org/2001/mstts" '
              f'xml:lang="zh-CN"><voice name="{voice}">'
              f'<mstts:express-as style="{style}"{deg_attr}>{inner}</mstts:express-as>'
              f'</voice></speak>')
    ssml_plain = (f'<speak version="1.0" '
                  f'xmlns="http://www.w3.org/2001/10/synthesis" '
                  f'xml:lang="zh-CN"><voice name="{voice}">'
                  f'{inner}</voice></speak>')
    url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
        "User-Agent": "chinese-youtube",
    }

    def _post(ssml):
        req = urllib.request.Request(url, data=ssml.encode("utf-8"),
                                     headers=headers, method="POST")
        return urllib.request.urlopen(req, timeout=60).read()

    print(f"[DEBUG-TTS] synth_azure goi voice={voice!r} region={region!r} url={url!r}")
    # MAI-Voice-2 KHONG ho tro mstts:express-as (tra 502) -> dung thang SSML thuong
    _no_style = "MAI-Voice" in (voice or "")
    try:
        data = _post(ssml_plain if _no_style else ssml_x)
    except urllib.error.HTTPError as e:
        if e.code in (400, 500, 502, 503):   # giong/style khong ho tro express-as -> SSML thuong
            data = _post(ssml_plain)
        else:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:300]
            except Exception:
                pass
            print(f"[DEBUG-TTS] synth_azure HTTPError {e.code}: {detail or e.reason}")
            raise RuntimeError(f"Azure TTS loi {e.code}: {detail or e.reason}")
    except urllib.error.URLError as e:
        print(f"[DEBUG-TTS] synth_azure URLError: {e.reason}")
        raise RuntimeError(f"Azure TTS khong ket noi duoc: {e.reason}")
    print(f"[DEBUG-TTS] synth_azure nhan duoc {len(data) if data else 0} bytes")
    if not data:
        raise RuntimeError("Azure TTS tra ve audio rong")
    with open(path, "wb") as f:
        f.write(data)
    # Azure DragonHD (giong "sieu that") BO QUA prosody rate -> tu chinh toc do bang atempo
    # de slider "Toc do doc" van co tac dung.
    if "Dragon" in (voice or ""):
        _atempo(path, _rate_factor(rate))

ELEVEN_MODEL = "eleven_multilingual_v2"   # da ngon ngu: 1 giong doc ca Trung + Viet
_eleven_model_override = None             # build() dat theo lua chon nguoi dung
_expressive = 60                          # 0..100, build() dat theo ctx (do bieu cam)

def _rate_to_eleven_speed(rate):
    """edge rate (vd -8%) -> ElevenLabs speed (0.7..1.2; 1.0 = binh thuong)."""
    try:
        pct = int(str(rate).replace("%", ""))
    except ValueError:
        pct = -8
    return max(0.7, min(1.2, round(1.0 + pct / 100.0, 2)))

def _eleven_breaks(text, expressive):
    """ElevenLabs: chen <break> SAU dau lang (… hoac em/en dash) cho ngat nghi tu nhien.
       Chi danh cho engine eleven (SSML-like break tag). An toan: khong co dau lang -> tra nguyen."""
    try:
        if not text:
            return text
        t = text
        # chuan hoa "..." / "。。。" -> "…" ; "……" giu nguyen (2 ky tu lang lien tiep cung ok)
        t = t.replace("。。。", "…").replace("...", "…")
        if not any(ch in t for ch in ("…", "—", "–")):
            return t
        x = round(0.30 + 0.0040 * max(0, min(100, int(expressive))), 2)
        x = min(0.70, x)
        brk = f'<break time="{x}s"/>'
        out = []
        for ch in t:
            out.append(ch)
            if ch in ("…", "—", "–"):
                out.append(brk)
        return "".join(out)
    except Exception:
        return text

def _reflective_bonus(seg_text, expressive):
    """Khoang lang phan tu (dam chieu) SAU cau cam xuc -> cong vao pad per-segment (moi engine)."""
    try:
        if not seg_text:
            return 0.0
        t = seg_text.strip()
        if not t:
            return 0.0
        # uu tien: ket thuc bang … — ? ! -> beat sau hon; chi 。/. -> nho
        deep = t.endswith(('…', '—', '–', '?', '？', '!', '！'))
        ends_reflective = t.endswith(
            ('…', '—', '–', '?', '？', '!', '！', '。', '.')
        ) and any(c in t for c in '…—–?？!！')
        if not (deep or ends_reflective):
            return 0.0
        base = 0.45 if deep else 0.15
        e = max(0, min(100, int(expressive))) / 100.0
        return round(base * (0.4 + 0.6 * e), 2)   # cap tu nhien ~<=0.45
    except Exception:
        return 0.0

def synth_eleven(text, voice_id, path, key, rate="-8%", model=None, emo=None):
    """ElevenLabs TTS (tra phi, chat luong cao). Ghi mp3 ra path.
       voice_id lay tu ElevenLabs (Voice Lab / Voices). 1 giong da ngu noi ca Trung+Viet.
       model: None -> lua chon nguoi dung; emo -> day cam xuc manh hon cho cau nay."""
    model = model or _eleven_model_override or ELEVEN_MODEL
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    # thong so dong theo do bieu cam (_expressive 0..100)
    try:
        e = max(0, min(100, int(_expressive))) / 100.0
    except Exception:
        e = 0.6
    stability = round(0.60 - 0.35 * e, 3)   # 0.60 (tinh) -> 0.25 (cam xuc)
    style = round(0.55 * e, 3)              # 0.0 -> 0.55
    if emo:   # cau co cam xuc ro -> noi long stability / tang style
        stability = round(max(0.05, min(0.95, stability + emo["el"][0])), 3)
        style = round(max(0.0, min(0.9, style + emo["el"][1])), 3)
    payload = {
        "text": text,
        "model_id": model,
        "voice_settings": {
            "stability": stability, "similarity_boost": 0.8,
            "style": style, "use_speaker_boost": True,
            "speed": _rate_to_eleven_speed(rate),
        },
    }
    headers = {"xi-api-key": key, "Content-Type": "application/json",
               "Accept": "audio/mpeg"}

    def _post(body):
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                     headers=headers, method="POST")
        return urllib.request.urlopen(req, timeout=120).read()

    print(f"[DEBUG-TTS] synth_eleven goi voice_id={voice_id!r} model={model!r} url={url!r}")
    try:
        data = _post(payload)
    except urllib.error.HTTPError as e:
        # mot so model cu khong nhan "speed" -> thu lai bo speed di
        if e.code in (400, 422):
            payload["voice_settings"].pop("speed", None)
            data = _post(payload)
        else:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:300]
            except Exception:
                pass
            print(f"[DEBUG-TTS] synth_eleven HTTPError {e.code}: {detail or e.reason}")
            raise RuntimeError(f"ElevenLabs loi {e.code}: {detail or e.reason}")
    except urllib.error.URLError as e:
        print(f"[DEBUG-TTS] synth_eleven URLError: {e.reason}")
        raise RuntimeError(f"ElevenLabs khong ket noi duoc: {e.reason}")
    print(f"[DEBUG-TTS] synth_eleven nhan duoc {len(data) if data else 0} bytes")
    if not data:
        raise RuntimeError("ElevenLabs tra ve audio rong")
    with open(path, "wb") as f:
        f.write(data)

# ---- Google Gemini TTS (AI Studio "Generate speech") ----
GEMINI_MODEL = "gemini-3.1-flash-tts-preview"   # giong AI Studio, da ngu (Trung + Viet)

def _rate_to_atempo(rate):
    """edge rate (vd -8%) -> ffmpeg atempo (0.5..2.0; giu cao do). -8% -> 0.92."""
    try:
        pct = int(str(rate).replace("%", ""))
    except ValueError:
        pct = -8
    return max(0.5, min(2.0, round(1.0 + pct / 100.0, 2)))

def synth_gemini(text, voice, path, key, rate="-8%", model=GEMINI_MODEL, emo=None):
    """Gemini TTS (Google AI Studio). Tra ve PCM 16-bit/24kHz/mono base64 -> mp3.
       voice = ten giong prebuilt (Kore, Puck, Zephyr...). emo -> chi dan cam xuc cau."""
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent")
    # PREPEND chi dan phong cach (Gemini doc noi dung theo phong cach, khong doc chi dan)
    try:
        ex = max(0, min(100, int(_expressive)))
        if ex < 33:
            tone = "tram am, nhe nhang, thong tha"
        elif ex <= 66:
            tone = "am ap, truyen cam, doi luc ngam nghi lang lai"
        else:
            tone = "giau cam xuc, luc lang dong dam chieu luc tha thiet, nhan nha co chieu sau"
        if emo:
            tone = tone + f"; rieng cau nay doc voi cam xuc {emo['gm']}"
        directive = (
            f"Doc doan sau bang giong ke chuyen {tone}, ngat nghi tu nhien giua cac y. "
            f"Chi doc noi dung ben duoi, KHONG doc dong huong dan nay:\n\n"
        )
        text_send = directive + text
    except Exception:
        text_send = text
    payload = {
        "contents": [{"parts": [{"text": text_send}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}
            },
        },
    }
    headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers=headers, method="POST")
    try:
        raw = urllib.request.urlopen(req, timeout=120).read()
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        raise RuntimeError(f"Gemini TTS loi {e.code}: {detail or e.reason}")
    resp = json.loads(raw)
    try:
        b64 = resp["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
    except (KeyError, IndexError):
        raise RuntimeError(f"Gemini TTS khong tra ve audio: {str(resp)[:300]}")
    pcm = base64.b64decode(b64)
    if not pcm:
        raise RuntimeError("Gemini TTS tra ve audio rong")
    # PCM raw (s16le, 24kHz, mono) -> mp3 qua ffmpeg, chinh toc do bang atempo
    cmd = ["ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", "pipe:0",
           "-filter:a", f"atempo={_rate_to_atempo(rate)}",
           "-c:a", "libmp3lame", "-q:a", "2", path]
    subprocess.run(cmd, input=pcm, check=True, capture_output=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        raise RuntimeError("Gemini TTS ghi ra file audio rong")

def _rate_to_speed(rate):
    """edge rate (vd -10%) -> ChatTTS speed token 0-9 (cang nho cang cham)."""
    try:
        pct = int(str(rate).replace("%", ""))
    except ValueError:
        pct = -8
    return {-20: 2, -10: 3, -8: 3, 0: 5}.get(pct, max(0, min(9, 5 + pct // 10)))

def _norm_rate(rate):
    """edge-tts bat buoc rate co dau (+/-). '0%' -> '+0%', '8%' -> '+8%'."""
    r = str(rate or "+0%").strip()
    if not r:
        return "+0%"
    return r if r[0] in "+-" else "+" + r

def _rate_factor(rate):
    """'-20%' -> 0.80, '+20%' -> 1.20, '-8%' -> 0.92 (he so toc do cho atempo)."""
    try:
        return 1.0 + int(str(rate).replace("%", "").replace("+", "")) / 100.0
    except Exception:
        return 1.0

def _atempo(path, factor):
    """Doi toc do audio (giu cao do) bang ffmpeg. Dung khi engine BO QUA rate (Azure DragonHD)."""
    factor = max(0.5, min(2.0, factor))
    if abs(factor - 1.0) < 0.01:
        return
    tmp = path + ".at.mp3"
    subprocess.run(["ffmpeg", "-y", "-i", path, "-filter:a", f"atempo={factor:.3f}",
                    "-c:a", "libmp3lame", "-q:a", "4", tmp], check=True, capture_output=True)
    os.replace(tmp, path)

def _is_empty_tts(text):
    """Con ky tu doc duoc khong? (bo khoang trang + dau cau thuan). Cau rong -> edge bao
       'No audio received' -> can chan truoc."""
    return not _re.sub(r"[\s\W_]+", "", text or "", flags=_re.UNICODE)

def _silence_mp3(path, dur=0.35):
    """Tao mp3 im lang ngan (dung khi cau rong de khong lam rot ca job)."""
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                    "-t", str(dur), "-q:a", "9", path], check=True, capture_output=True)

_TTS_TRIES = 4                      # edge-tts hay bi Microsoft throttle khi goi lien tiep (video nhieu slide)
def _edge_retry(fn, what="edge-tts"):
    """Chay fn() voi retry + backoff. Nem loi ro rang neu that bai sau _TTS_TRIES lan."""
    last = None
    for i in range(_TTS_TRIES):
        try:
            return fn()
        except Exception as e:
            last = e
            if i < _TTS_TRIES - 1:
                time.sleep(1.2 * (i + 1))      # nghi tang dan de vuot throttle
    raise RuntimeError(f"{what} that bai sau {_TTS_TRIES} lan (co the bi Microsoft chan tam "
                       f"thoi do goi lien tiep): {last}")

def _edge_pitch_split(voice):
    """Tach pitch nhung trong ten giong: 'vi-VN-NamMinhNeural@-20Hz' -> (giong, '-20Hz').
       Cho phep che bien the TRAM hon tu 2 giong Viet it oi cua edge (khong co giong moi)."""
    if voice and "@" in voice:
        v, p = voice.split("@", 1)
        return v, p
    return voice, None

def _pitch_add(base, extra):
    """Cong pitch nen (tu ten giong) voi pitch cam xuc: '-20Hz' + '-9Hz' -> '-29Hz'."""
    if not base:
        return extra
    if not extra:
        return base
    unit = "st" if "st" in base.lower() else "Hz"      # azure nhan ca 'st' (nua cung)
    try:
        s = (int(base.lower().replace("hz", "").replace("st", ""))
             + int(extra.lower().replace("hz", "").replace("st", "")))
        return f"{s:+d}{unit}"
    except ValueError:
        return base

def _synth_edge(text, voice, path, rate="-8%", pitch=None):
    """Sinh giong bang edge-tts (mien phi, can internet). pitch: vd '+10Hz' (cam xuc).
       Co retry + chong cau rong."""
    if _is_empty_tts(text):
        _silence_mp3(path); return
    voice, base_pitch = _edge_pitch_split(voice)
    pitch = _pitch_add(base_pitch, pitch)
    cmd = [sys.executable, "-m", "edge_tts", "--voice", voice,
           "--text", text, f"--rate={_norm_rate(rate)}", "--write-media", path]
    if pitch:
        cmd.insert(-2, f"--pitch={pitch}")
    def _run():
        subprocess.run(cmd, check=True, capture_output=True)
        if not (os.path.exists(path) and os.path.getsize(path) > 0):
            raise RuntimeError("edge-tts tra ve file rong")
    _edge_retry(_run)

def _edge_voice(voice):
    """Tra ve giong edge hop le; vname kieu 'local' (ChatTTS) -> giong Trung mac dinh."""
    return voice if (voice and "-" in voice and "Neural" in voice) else VOICE_ZH

# ---------- VieNeu-TTS local (tieng Viet, offline, free) ----------
# Dispatch theo TIEN TO ten giong ("vieneu:Thanh Bình") -> khong can them tham so
# vao synth()/synth_timed() va moi call site (film.py, short_native.py...) tu chay.
_VIENEU_VENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv-vieneu")
VIENEU_PY = (os.path.join(_VIENEU_VENV, "Scripts", "python.exe") if os.name == "nt"
             else os.path.join(_VIENEU_VENV, "bin", "python"))
VIENEU_HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vieneu_tts.py")

def _is_vieneu(voice):
    return isinstance(voice, str) and voice.startswith("vieneu:")

def synth_vieneu(text, voice, path, rate="-8%", emotion=None):
    """VieNeu v3 Turbo qua .venv-vieneu (Python 3.11, ONNX CPU). voice = ten preset
       ('Thanh Bình'...), them ':style' tuy chon ('Thái Sơn:tu_nhien') de doi style;
       mac dinh helper dung 'tu_nhien' + emotion 4 (nhan nha nhat) cho ke chuyen.
       emotion: '0'..'7' de ep sac thai ca doan; None = de helper dung mac dinh.
       Muon doi sac thai TUNG CAU thi viet thang <|emotion_k|> / [thở dài] trong text.
       Helper ghi wav 48k -> ffmpeg mp3 24k + atempo theo rate."""
    if not os.path.exists(VIENEU_PY):
        raise RuntimeError("Chua cai VieNeu. Chay trong thu muc du an: "
                           "python -m venv .venv-vieneu roi "
                           f"\"{VIENEU_PY}\" -m pip install vieneu soundfile")
    style = None
    if ":" in voice:
        voice, style = voice.split(":", 1)
    w = path + ".vieneu.wav"
    cmd = [VIENEU_PY, VIENEU_HELPER, "--voice", voice, "--out", w]
    if style:
        cmd += ["--style", style]
    if emotion not in (None, ""):
        cmd += ["--emotion", str(emotion)]
    r = subprocess.run(cmd, input=text.encode("utf-8"), timeout=600, capture_output=True)
    if r.returncode != 0:
        # Doi loi thanh cau nguoi dung doc duoc — truoc day chi nem nguyen dong lenh
        # subprocess ra UI, khong biet la do giong khong ton tai hay do model loi.
        err = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        msg = next((l for l in reversed(err) if l.strip()), "") if err else ""
        raise RuntimeError(f"Giọng VieNeu '{voice}' chạy lỗi: {msg or 'không rõ nguyên nhân'}")
    try:
        pct = float(str(rate).replace("%", "").replace("+", ""))
    except Exception:
        pct = 0.0
    tempo = max(0.5, min(2.0, 1.0 + pct / 100.0))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", w,
                    "-af", f"atempo={tempo}", "-ar", "24000", "-ac", "1",
                    "-b:a", "96k", path], check=True)
    os.remove(w)

def synth_fpt(text, voice, path, key, rate="-8%"):
    """FPT.AI Voicemaker TTS (free 100k ky tu/thang, giong thuan Viet: banmai/leminh/...).
       API tra ve LINK mp3 lam async -> phai poll toi khi CDN co file that."""
    try:
        pct = float(str(rate).replace("%", "").replace("+", ""))
    except Exception:
        pct = 0.0
    speed = str(int(max(-3, min(3, round(pct / 10)))))     # -8% ~ cham nhe -> speed -1
    req = urllib.request.Request(
        "https://api.fpt.ai/hmi/tts/v5", data=text.encode("utf-8"),
        headers={"api-key": key, "voice": voice, "speed": speed})
    j = json.loads(urllib.request.urlopen(req, timeout=60).read())
    if j.get("error"):
        raise RuntimeError(f"FPT TTS loi: {j}")
    url = j.get("async") or j.get("data") or ""
    if not url:
        raise RuntimeError(f"FPT TTS khong tra link mp3: {j}")
    for _ in range(30):
        try:
            data = urllib.request.urlopen(url, timeout=30).read()
            if len(data) > 1000:               # CDN tra trang loi/rong khi file chua san sang
                with open(path, "wb") as f:
                    f.write(data)
                return
        except Exception:
            pass
        time.sleep(1.0)
    raise RuntimeError("FPT TTS: mp3 chua san sang sau 30s: " + url)


# ---------- Vbee TTS (vbee.vn — thuan Viet, giong ke chuyen "Anh Khoi"...) ----------
# Dispatch theo TIEN TO "vbee:<voice_code>" (nhu VieNeu) -> khong can them tham so
# vao synth()/synth_timed() va call site. Can vbee_config.json {"token","app_id"}.
VBEE_CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vbee_config.json")

def _is_vbee(voice):
    return isinstance(voice, str) and voice.startswith("vbee:")

def _load_vbee():
    try:
        d = json.load(open(VBEE_CFG, encoding="utf-8"))
        return d.get("token", ""), d.get("app_id", "")
    except Exception:
        return "", ""

def synth_vbee(text, voice_code, path, rate="-8%"):
    """Vbee TTS (vbee.vn, tra phi theo ky tu). POST /api/v1/tts (async)
       -> poll GET /api/v1/tts/{request_id} toi khi SUCCESS -> tai audio_link ve."""
    token, app_id = _load_vbee()
    if not (token and app_id):
        raise RuntimeError("Chua luu Vbee token/app_id (o 'Giong xin' trang phim).")
    try:
        pct = float(str(rate).replace("%", "").replace("+", ""))
    except Exception:
        pct = 0.0
    speed = max(0.8, min(1.2, round(1.0 + pct / 100.0, 2)))    # -10% -> 0.9
    payload = {"app_id": app_id, "response_type": "direct",
               "input_text": text, "voice_code": voice_code,
               "audio_type": "mp3", "bitrate": 128, "speed_rate": str(speed)}
    req = urllib.request.Request(
        "https://vbee.vn/api/v1/tts", data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + token,
                 "Content-Type": "application/json"})
    try:
        j = json.loads(urllib.request.urlopen(req, timeout=60).read())
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        raise RuntimeError(f"Vbee TTS loi {e.code}: {detail or e.reason}")
    res = j.get("result") or {}
    rid = res.get("request_id") or res.get("id") or ""
    link = res.get("audio_link") or ""
    for _ in range(60):
        if link:
            try:
                data = urllib.request.urlopen(link, timeout=30).read()
                if len(data) > 1000:           # CDN tra trang rong khi chua san sang
                    with open(path, "wb") as f:
                        f.write(data)
                    return
            except Exception:
                pass
        elif rid:
            q = urllib.request.Request("https://vbee.vn/api/v1/tts/" + str(rid),
                                       headers={"Authorization": "Bearer " + token})
            try:
                rr = (json.loads(urllib.request.urlopen(q, timeout=30).read())
                      .get("result") or {})
                st = (rr.get("status") or "").upper()
                if st == "SUCCESS":
                    link = rr.get("audio_link") or ""
                elif st in ("FAILURE", "ERROR", "FAILED"):
                    raise RuntimeError(f"Vbee TTS bao loi: {rr}")
            except urllib.error.HTTPError as e:
                raise RuntimeError(f"Vbee TTS poll loi {e.code}")
        else:
            raise RuntimeError(f"Vbee TTS khong tra request_id/audio_link: {j}")
        time.sleep(1.0)
    raise RuntimeError("Vbee TTS: qua 60s chua co audio")


def synth(text, voice, path, rate="-8%", azure=None, chattts=False, eleven=None,
          gemini=None, emo=None, fpt=None):
    """Giong doc co cache. chattts -> ChatTTS local; eleven=key -> ElevenLabs;
       gemini=key -> Gemini TTS; azure=(key,region) -> Azure; con lai -> edge-tts.
       emo (detect_emotion): doc bieu cam theo cam xuc cau — doi toc do/cao do/style.
       ChatTTS loi -> fallback edge."""
    eng = "vn3" if _is_vieneu(voice) else \
          "vb" if _is_vbee(voice) else \
          ("ct-" + str(chattts)) if chattts else \
          ("fp" if fpt else
           ("gm" if gemini else ("el" if eleven else ("az" if azure else "ed"))))
    if emo:
        eng = eng + "~" + emo["name"]          # cache rieng theo cam xuc
    rate = _emo_rate(rate, emo)
    # ElevenLabs: chen <break> trong cau (chi engine nay) -> text khac -> key khac
    text_el = _eleven_breaks(text, _expressive) if eleven else text
    key_text = text_el if eleven else text
    c = os.path.join(TTS_CACHE,
                     _tts_key(eng + key_text, voice, rate, _expressive, eng) + ".mp3")
    print(f"[DEBUG-TTS] synth() eng={eng!r} voice={voice!r} chattts={bool(chattts)} "
          f"gemini={bool(gemini)} eleven={bool(eleven)} azure={bool(azure)} "
          f"cache_hit={os.path.exists(c) and os.path.getsize(c) > 0} -> path={path!r}")
    if not (os.path.exists(c) and os.path.getsize(c) > 0):
        if _is_empty_tts(text):
            print(f"[DEBUG-TTS] synth() cau rong (chi dau cau) -> ghi im lang: {text!r}")
            _silence_mp3(c)
        elif _is_vieneu(voice):
            synth_vieneu(text, voice.split(":", 1)[1], c, rate)
        elif _is_vbee(voice):
            synth_vbee(text, voice.split(":", 1)[1], c, rate)
        elif chattts:
            try:
                import chattts_engine
                style = chattts if isinstance(chattts, str) else "warm"
                p = chattts_engine.STYLES.get(style, chattts_engine.STYLES["warm"])
                chattts_engine.synth_chattts(text, c, speed=_rate_to_speed(rate), **p)
            except Exception as e:
                print(f"[ChatTTS khong dung duoc -> chuyen sang edge-tts] {e}")
                _synth_edge(text, _edge_voice(voice), c, rate,
                            pitch=emo["pitch"] if emo else None)
        elif fpt:
            try:
                synth_fpt(text, voice, c, fpt, rate)
            except Exception as e:
                ev = ("vi-VN-NamMinhNeural"
                      if voice.lower() in ("leminh", "minhquang", "giahuy")
                      else "vi-VN-HoaiMyNeural")
                print(f"[FPT TTS loi (het quota?) -> chuyen sang edge {ev}] {e}")
                _synth_edge(text, ev, c, rate, pitch=emo["pitch"] if emo else None)
        elif gemini:
            synth_gemini(text, voice, c, gemini, rate, emo=emo)
        elif eleven:
            synth_eleven(text_el, voice, c, eleven, rate, emo=emo)
        elif azure:
            synth_azure(text, voice, c, azure[0], azure[1], rate, emo=emo)
        else:
            _synth_edge(text, voice, c, rate, pitch=emo["pitch"] if emo else None)
    shutil.copyfile(c, path)

def synth_timed(text, voice, path, rate="-8%", azure=None, chattts=False, eleven=None,
                gemini=None, emo=None):
    """Ghi mp3 + tra ve list (start,end) cac cau. Co cache. emo: doc bieu cam theo cau.
       chattts/azure/eleven/gemini: khong co moc cau -> [] (fallback rai deu chu)."""
    eng = "vn3" if _is_vieneu(voice) else \
          "vb" if _is_vbee(voice) else \
          ("ct-" + str(chattts)) if chattts else \
          ("gm" if gemini else ("el" if eleven else ("az" if azure else "ed")))
    if emo:
        eng = eng + "~" + emo["name"]          # cache rieng theo cam xuc
    rate = _emo_rate(rate, emo)
    # ElevenLabs: chen <break> trong cau (chi engine nay) -> text khac -> key khac
    text_el = _eleven_breaks(text, _expressive) if eleven else text
    key_text = text_el if eleven else text
    key = _tts_key(eng + key_text, voice, rate, _expressive, eng)
    c = os.path.join(TTS_CACHE, key + ".mp3")
    cj = os.path.join(TTS_CACHE, key + ".sents.json")
    if os.path.exists(c) and os.path.getsize(c) > 0 and os.path.exists(cj):
        shutil.copyfile(c, path)
        return json.load(open(cj, encoding="utf-8"))

    pitch = emo["pitch"] if emo else None
    if _is_empty_tts(text):
        print(f"[DEBUG-TTS] synth_timed() cau rong (chi dau cau) -> ghi im lang: {text!r}")
        _silence_mp3(c)
        json.dump([], open(cj, "w", encoding="utf-8"))
        shutil.copyfile(c, path)
        return []
    if chattts or azure or eleven or gemini or _is_vieneu(voice) or _is_vbee(voice):
        # khong co moc cau -> [] (rai deu chu)
        if _is_vieneu(voice):
            synth_vieneu(text, voice.split(":", 1)[1], c, rate)
        elif _is_vbee(voice):
            synth_vbee(text, voice.split(":", 1)[1], c, rate)
        elif chattts:
            try:
                import chattts_engine
                style = chattts if isinstance(chattts, str) else "warm"
                p = chattts_engine.STYLES.get(style, chattts_engine.STYLES["warm"])
                chattts_engine.synth_chattts(text, c, speed=_rate_to_speed(rate), **p)
            except Exception as e:
                print(f"[ChatTTS khong dung duoc -> chuyen sang edge-tts] {e}")
                # edge co moc cau -> ghi binh thuong va tra ve moc that
                sents = _synth_edge_timed(text, _edge_voice(voice), c, rate, pitch=pitch)
                json.dump(sents, open(cj, "w", encoding="utf-8"))
                shutil.copyfile(c, path)
                return sents
        elif gemini:
            synth_gemini(text, voice, c, gemini, rate, emo=emo)
        elif eleven:
            synth_eleven(text_el, voice, c, eleven, rate, emo=emo)
        else:
            synth_azure(text, voice, c, azure[0], azure[1], rate, emo=emo)
        json.dump([], open(cj, "w", encoding="utf-8"))
        shutil.copyfile(c, path)
        return []

    sents = _synth_edge_timed(text, voice, c, rate, pitch=pitch)
    json.dump(sents, open(cj, "w", encoding="utf-8"))
    shutil.copyfile(c, path)
    return sents

# ---------- PACING: nghi sau dau phay (ENGINE-AGNOSTIC) ----------
def _concat_audio(files, out):
    """Ghep nhieu file audio -> 1 mp3. Chuan hoa 24kHz mono truoc khi concat (an toan moi engine)."""
    ins = []
    for f in files:
        ins += ["-i", f]
    n = len(files)
    pre = "".join(f"[{i}:a]aresample=24000,aformat=channel_layouts=mono[a{i}];" for i in range(n))
    graph = pre + "".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[a]"
    subprocess.run(["ffmpeg", "-y", *ins, "-filter_complex", graph,
                    "-map", "[a]", "-c:a", "libmp3lame", "-q:a", "4", out],
                   check=True, capture_output=True)

_PACE_SPLIT = _re.compile(r"(?<=[，、；：,;:])")   # tach NGAY SAU dau ngat trong cau

def synth_paced(text, voice, path, rate="-8%", comma_pause=0.0,
                azure=None, chattts=False, eleven=None, gemini=None, emo=None):
    """Synth 1 cau + chen im lang 'comma_pause' (giay) sau moi dau phay/cham-phay.
       Chay cho MOI engine (tach cau -> synth tung khuc qua synth() -> ghep + im lang).
       comma_pause<=0 hoac cau khong co dau phay -> synth_timed binh thuong."""
    kw = dict(azure=azure, chattts=chattts, eleven=eleven, gemini=gemini, emo=emo)
    chunks = [c for c in _PACE_SPLIT.split(text) if c and c.strip()]
    if comma_pause <= 0 or len(chunks) <= 1:
        return synth_timed(text, voice, path, rate=rate, **kw)
    parts = []
    last = len(chunks) - 1
    for idx, ch in enumerate(chunks):
        cf = f"{path}.c{idx}.mp3"
        # bo dau ngat o CUOI khuc (tru khuc cuoi) -> engine khoi tu them nghi ->
        # thoi luong nghi DUNG bang comma_pause (khong bi cong them nghi tu nhien cua giong)
        ct = ch if idx == last else ch.rstrip("，、；：,;: ")
        synth(ct or ch, voice, cf, rate=rate, **kw)    # dispatch engine + cache
        parts.append(cf)
        if idx < last:
            sf = f"{path}.s{idx}.mp3"
            _silence_mp3(sf, comma_pause)
            parts.append(sf)
    _concat_audio(parts, path)
    for p in parts:
        try:
            os.remove(p)
        except Exception:
            pass
    return []          # cau hien tinh (ca cau) -> khong can moc tung tu

def _synth_edge_timed(text, voice, out_mp3, rate="-8%", pitch=None):
    """edge-tts -> ghi out_mp3 + tra ve list (start,end) cac cau/tu. Co retry + chong cau rong."""
    if _is_empty_tts(text):
        _silence_mp3(out_mp3); return []
    ev, base_pitch = _edge_pitch_split(voice)
    pitch = _pitch_add(base_pitch, pitch)
    async def go():
        kw = {"rate": _norm_rate(rate)}
        if pitch:
            kw["pitch"] = pitch
        comm = edge_tts.Communicate(text, ev, **kw)
        sents = []
        with open(out_mp3, "wb") as f:
            async for ch in comm.stream():
                if ch["type"] == "audio":
                    f.write(ch["data"])
                elif ch["type"] in ("SentenceBoundary", "WordBoundary"):
                    sents.append([ch["offset"]/1e7, (ch["offset"]+ch["duration"])/1e7])
        if not (os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 0):
            raise RuntimeError("edge-tts khong nhan duoc audio")
        return sents
    return _edge_retry(lambda: asyncio.run(go()))

def dur_of(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True, check=True)
    return float(out.stdout.strip())

# ---------- NHAC NEN ----------
MUSIC_DIR = os.path.join(TMP, "music")
os.makedirs(MUSIC_DIR, exist_ok=True)
MUSIC_VOL = 0.5           # am luong nhac nen (0-1), nho de khong at giong doc

# Cac mau arpeggio piano theo tam trang (tan so notes, Hz)
MOODS = {
    "calm":  [261.63, 329.63, 392.00, 493.88, 392.00, 329.63,   # C E G B (Do truong)
              293.66, 392.00, 440.00, 392.00],
    "happy": [392.00, 493.88, 587.33, 783.99, 587.33, 493.88,   # G B D G (Sol truong)
              440.00, 587.33, 659.25, 587.33],
    "sad":   [220.00, 261.63, 329.63, 440.00, 329.63, 261.63,   # A C E A (La thu)
              246.94, 329.63, 392.00, 329.63],
    "hope":  [293.66, 369.99, 440.00, 587.33, 440.00, 369.99,   # D F# A D (Re truong)
              329.63, 440.00, 493.88, 440.00],
    "box":   [523.25, 659.25, 783.99, 1046.50, 783.99, 659.25,  # hop am cao - music box
              587.33, 783.99, 880.00, 783.99],
    "deep":  [130.81, 164.81, 196.00, 261.63, 196.00, 164.81,   # tram, sau lang
              146.83, 196.00, 220.00, 196.00],
}

def get_music(mood="calm"):
    """Uu tien file mp3 nguoi dung bo vao assets/music/; neu khong co thi
       tu sinh nhac piano-ish (arpeggio not gay tieng buong) theo tam trang."""
    user = [f for f in glob_mp3(MUSIC_DIR) if not os.path.basename(f).startswith("_")]
    if user:
        return user[0]
    out = os.path.join(MUSIC_DIR, f"_piano_{mood}.mp3")
    if os.path.exists(out):
        return out
    print(f"  (sinh nhac piano '{mood}'...)")
    freqs = MOODS.get(mood, MOODS["calm"])
    note_dur = 0.62
    notes = []
    for i, fr in enumerate(freqs):
        nw = os.path.join(MUSIC_DIR, f"_n{i}.wav")
        # not piano-ish: sin co bồi âm + bao bien suy giam (pluck)
        expr = (f"(0.6*sin(2*PI*{fr}*t)+0.2*sin(2*PI*{2*fr}*t)"
                f"+0.1*sin(2*PI*{3*fr}*t))*exp(-3.4*t)")
        subprocess.run(["ffmpeg","-y","-f","lavfi","-i",
                        f"aevalsrc={expr}:d={note_dur}:s=44100",
                        "-ac","1",nw], check=True, capture_output=True)
        notes.append(nw)
    lst = os.path.join(MUSIC_DIR, "_notes.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for nw in notes:
            f.write(f"file '{nw.replace(os.sep,'/')}'\n")
    pattern = os.path.join(MUSIC_DIR, "_pat.wav")
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",lst,
                    "-c","copy",pattern], check=True, capture_output=True)
    # them vang + am am, xuat mp3 (mix_music se lap lai)
    subprocess.run(["ffmpeg","-y","-i",pattern,
                    "-af","aecho=0.8:0.85:90:0.32,lowpass=f=2600,"
                          "areverse,afade=t=in:st=0:d=0.03,areverse,volume=2.2",
                    "-ac","2",out], check=True, capture_output=True)
    for nw in notes:
        try: os.remove(nw)
        except OSError: pass
    return out

def glob_mp3(d):
    import glob as _g
    return sorted(_g.glob(os.path.join(d, "*.mp3")))

def make_standalone_mascot(ctx):
    """Tao 1 PNG nen trong cua mascot (de overlay chuyen dong). None neu tat."""
    if ctx.get("mascot") == "none":
        return None
    H_ = 270
    img = ctx.get("_mascot_img")
    if img and os.path.exists(img):                      # hinh AI
        im = Image.open(img).convert("RGBA")
        im = im.resize((int(im.width * H_ / im.height), H_))
        p = os.path.join(AI_CACHE, "_overlay_ai.png")
        im.save(p)
        return p
    # emoji -> PNG nen trong
    e = ctx.get("mascot") or style_pastel.MASCOTS[(int(ctx.get("id", 1)) - 1)
                                                  % len(style_pastel.MASCOTS)]
    canvas = Image.new("RGBA", (330, 300), (0, 0, 0, 0))
    dd = ImageDraw.Draw(canvas)
    ef = style_pastel.emoji_font(150)
    dd.text((18, 95), e, font=ef, embedded_color=True)
    dd.text((178, 58), "🎵", font=style_pastel.emoji_font(54),
            embedded_color=True)
    dd.text((168, 205), "🎧", font=style_pastel.emoji_font(50),
            embedded_color=True)
    p = os.path.join(AI_CACHE, "_overlay_emoji.png")
    canvas.save(p)
    return p

# ---------- HIEU UNG CANH HOA ROI (overlay dong, cache 1 lan) ----------
FX_DIR = os.path.join(TMP, "fx")
FX_KINDS = {
    # c1/c2: 2 tong mau; shape: petal (elip xoay) / circle / bokeh (tron mo);
    # dir: down (roi) / up (bay len); n: so hat; size/al: khoang random
    "sakura": dict(c1=(255, 194, 210), c2=(250, 160, 185), shape="petal", dir="down",
                   n=26, size=(7, 15), al=(150, 220)),      # hoa anh dao hong
    "ginkgo": dict(c1=(242, 205, 92), c2=(222, 172, 60), shape="petal", dir="down",
                   n=26, size=(7, 15), al=(150, 220)),      # la ngan hanh vang
    "maple":  dict(c1=(214, 96, 60), c2=(178, 64, 44), shape="petal", dir="down",
                   n=24, size=(8, 16), al=(150, 215)),      # la phong do
    "snow":   dict(c1=(250, 252, 255), c2=(225, 232, 245), shape="circle", dir="down",
                   n=38, size=(2.5, 6), al=(130, 220)),     # tuyet roi (truyen dem)
    "dust":   dict(c1=(244, 214, 140), c2=(228, 188, 108), shape="circle", dir="up",
                   n=44, size=(1.5, 3.5), al=(60, 150)),    # bui vang lap lanh bay len
    "bokeh":  dict(c1=(255, 250, 240), c2=(255, 236, 208), shape="bokeh", dir="up",
                   n=14, size=(18, 55), al=(16, 38)),       # dom sang bokeh mo
}

def make_petals_fx(kind="sakura"):
    """Sinh video overlay canh hoa roi (VP9 co alpha, 8s loop, 960x540 -> scale len).
       Cache theo kind — chi ton cong 1 lan dau."""
    import math, random
    os.makedirs(FX_DIR, exist_ok=True)
    out = os.path.join(FX_DIR, f"petals_{kind}.webm")
    if os.path.exists(out):
        return out
    print(f"  (sinh hieu ung '{kind}' lan dau — se cache lai...)")
    FW, FH, NFRAME = 960, 540, 200          # 8s @ 25fps, loop khep kin
    conf = FX_KINDS.get(kind, FX_KINDS["sakura"])
    rng = random.Random(42)
    sgn = -1 if conf["dir"] == "up" else 1
    petals = []
    for i in range(conf["n"]):
        petals.append(dict(
            x=rng.uniform(0, FW), y=rng.uniform(0, FH),
            vy=sgn * rng.uniform(28, 62) / 25.0,          # px/frame (am = bay len)
            ax=rng.uniform(18, 46), spd=rng.uniform(0.4, 1.1),
            size=rng.uniform(*conf["size"]), ph=rng.uniform(0, 6.28),
            col=conf["c1"] if i % 3 else conf["c2"], al=rng.randint(*conf["al"])))
    tmpd = os.path.join(FX_DIR, f"_frames_{kind}")
    os.makedirs(tmpd, exist_ok=True)
    shape = conf["shape"]
    for f in range(NFRAME):
        im = Image.new("RGBA", (FW, FH), (0, 0, 0, 0))
        t = f / NFRAME * 2 * math.pi                     # pha khep kin de loop muot
        for p in petals:
            y = (p["y"] + p["vy"] * f) % (FH + 30) - 15
            x = (p["x"] + p["ax"] * math.sin(t * p["spd"] * 2 + p["ph"])) % (FW + 20) - 10
            sz = p["size"]
            box = int(max(6, sz * 3))
            pet = Image.new("RGBA", (box, box), (0, 0, 0, 0))
            pd = ImageDraw.Draw(pet)
            cxp = cyp = box / 2
            if shape == "petal":       # elip xoay canh hoa/la
                wob = 0.55 + 0.45 * math.sin(t * 3 * p["spd"] + p["ph"])
                rw, rh = sz, max(2.5, sz * wob)
                pd.ellipse([cxp - rw, cyp - rh, cxp + rw, cyp + rh],
                           fill=p["col"] + (p["al"],))
                pet = pet.rotate(math.degrees(math.sin(t * p["spd"] + p["ph"])) * 0.6,
                                 resample=Image.BILINEAR)
            else:                      # circle / bokeh: hat tron (bokeh se blur)
                # lap lanh nhe theo thoi gian (dust/snow)
                tw = 0.75 + 0.25 * math.sin(t * 4 * p["spd"] + p["ph"] * 2)
                a = int(p["al"] * (tw if shape == "circle" else 1.0))
                pd.ellipse([cxp - sz, cyp - sz, cxp + sz, cyp + sz],
                           fill=p["col"] + (max(8, a),))
                if shape == "bokeh":
                    pet = pet.filter(ImageFilter.GaussianBlur(max(2, sz / 3)))
            im.alpha_composite(pet, (int(x - cxp), int(y - cyp)))
        im.save(os.path.join(tmpd, f"f{f:03d}.png"))
    subprocess.run(["ffmpeg", "-y", "-framerate", str(FPS),
                    "-i", os.path.join(tmpd, "f%03d.png"),
                    "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "600k",
                    "-auto-alt-ref", "0", out], check=True, capture_output=True)
    shutil.rmtree(tmpd, ignore_errors=True)
    return out


def _waveform_conf(ctx):
    """Song am giong noi (visualizer). Tra ve (pos, color) hoac None.
       ctx['waveform']: 'auto' (theo bien the) / 'top' / 'mid' / 'off'."""
    if not ctx.get("podcast_layout"):
        return None
    wf = (ctx.get("waveform") or "auto")
    dark = False
    try:
        import style_podcast
        vcfg = style_podcast.VARIANTS.get(ctx.get("podcast_variant") or "inkwash", {})
        dark = bool(vcfg.get("dark"))
        if wf == "auto":
            wf = vcfg.get("wave", "off")
    except Exception:
        if wf == "auto":
            wf = "off"
    if wf not in ("top", "mid"):
        return None
    color = "0xFFF2DC" if dark else "0x8B1A1A"
    return (wf, color)


def compose_final(narr, ctx, final):
    """Ghep buoc cuoi: overlay mascot bong benh + song am giong noi + tron nhac."""
    mascot = ctx.get("_mascot_png")
    music_on = ctx.get("music", True)
    vol = ctx.get("music_vol", MUSIC_VOL)
    vdur = dur_of(narr)
    inputs = ["-i", narr]
    parts, idx = [], 1
    vmap, amap = "0:v", "0:a"
    # canh hoa / la roi (overlay dong toan video — video "sinh dong" ma van tinh)
    fx = (ctx.get("fx") or "").strip()
    if fx in FX_KINDS:
        try:
            fxf = make_petals_fx(fx)
            inputs += ["-stream_loop", "-1", "-c:v", "libvpx-vp9", "-i", fxf]
            fi = idx; idx += 1
            parts.append(f"[{fi}:v]scale={W}:{H}[fxs]")
            parts.append(f"[{vmap}][fxs]overlay=shortest=1[vfx]")
            vmap = "[vfx]"
        except Exception as e:
            print("  [fx] loi, bo qua hieu ung roi:", e)
    wave = _waveform_conf(ctx)
    if wave:
        pos, color = wave
        ww, wh = 640, 110
        wy = 40 if pos == "top" else int(H * 0.42)
        # showwaves tu GIONG DOC (0:a — chua tron nhac) -> song nhay theo tieng noi.
        # volume boost truoc showwaves: bien do noi ro (khong anh huong am thanh video)
        # colors: du CA 2 KENH stereo; KHONG dung alpha @x (bug ffmpeg cline -> lech mau xanh)
        parts.append(f"[0:a]volume=2.4,showwaves=s={ww}x{wh}:mode=cline:rate={FPS}:"
                     f"scale=sqrt:colors={color}|{color},format=rgba[wv]")
        src = vmap if vmap.startswith("[") else f"[{vmap}]"
        parts.append(f"{src}[wv]overlay=x=(W-w)/2:y={wy}[vw]")
        vmap = "[vw]"
    if mascot:
        inputs += ["-i", mascot]; mi = idx; idx += 1
        # bong benh: len xuong 13px moi ~2.6s
        src = vmap if vmap.startswith("[") else f"[{vmap}]"
        parts.append(f"{src}[{mi}:v]overlay=x=42:"
                     f"y='H-h-40+13*sin(2*PI*t/2.6)':eval=frame[v]")
        vmap = "[v]"
    if music_on:
        mf = ctx.get("music_file")
        # chi dung file nhac neu THUC SU co audio (tranh upload nham anh PNG -> crash)
        if mf and os.path.exists(mf) and _has_audio(mf):
            music = mf
        else:
            if mf and not _has_audio(mf):
                print(f"  [nhac] '{os.path.basename(mf)}' khong phai file am thanh -> dung piano")
            music = get_music(ctx.get("mood", "calm"))
        inputs += ["-stream_loop", "-1", "-i", music]; mu = idx; idx += 1
        parts.append(f"[{mu}:a]volume={vol},afade=t=in:st=0:d=2,"
                     f"afade=t=out:st={vdur-3:.2f}:d=3[mm]")
        parts.append("[0:a][mm]amix=inputs=2:duration=first:"
                     "dropout_transition=0:normalize=0[amix]")
        # chuan hoa am luong ve -14 LUFS (chuan YouTube) -> moi video to deu nhau
        parts.append(f"[amix]{LOUDNORM}[a]")
        amap = "[a]"
    elif ctx.get("loudnorm", True):
        parts.append(f"[0:a]{LOUDNORM}[a]")
        amap = "[a]"
    cmd = ["ffmpeg", "-y", *inputs]
    if parts:
        cmd += ["-filter_complex", ";".join(parts)]
    vcodec = ([*X264, "-r", str(FPS), "-pix_fmt", "yuv420p"]
              if (mascot or wave or vmap != "0:v") else ["-c:v", "copy"])
    cmd += ["-map", vmap, "-map", amap, *vcodec,
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2", final]
    subprocess.run(cmd, check=True, capture_output=True)

BRAND_INTRO = os.path.join(ROOT, "brand", "intro.mp4")
BRAND_OUTRO = os.path.join(ROOT, "brand", "outro.mp4")

def _has_audio(path):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a",
                              "-show_entries", "stream=index", "-of", "csv=p=0", path],
                             capture_output=True, text=True)
        return bool(out.stdout.strip())
    except Exception:
        return False

def _normalize_clip(src, dst):
    """Chuan hoa clip ve dung dinh dang video chinh (1920x1080, 25fps, aac stereo 44100).
       Them audio im lang neu clip khong co tieng."""
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
          f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0x000000,setsar=1,fps={FPS},format=yuv420p")
    base = [*X264, "-r", str(FPS), "-pix_fmt", "yuv420p",
            "-video_track_timescale", "12800",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2"]
    if _has_audio(src):
        cmd = ["ffmpeg", "-y", "-i", src, "-vf", vf, "-map", "0:v:0", "-map", "0:a:0",
               *base, dst]
    else:
        cmd = ["ffmpeg", "-y", "-i", src,
               "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
               "-vf", vf, "-map", "0:v:0", "-map", "1:a:0", "-shortest", *base, dst]
    subprocess.run(cmd, check=True, capture_output=True)

def attach_intro_outro(final, ctx):
    """Ghep brand/intro.mp4 vao dau + brand/outro.mp4 vao cuoi (neu co). Tra ve path video moi."""
    # ton trong bat/tat rieng tung cai (use_intro / use_outro)
    intro = BRAND_INTRO if (os.path.exists(BRAND_INTRO) and ctx.get("use_intro", True)) else None
    outro = BRAND_OUTRO if (os.path.exists(BRAND_OUTRO) and ctx.get("use_outro", True)) else None
    if not ctx.get("intro_outro", True) or not (intro or outro):
        return final, 0.0
    parts = []
    intro_dur = 0.0
    if intro:
        ni = os.path.join(AUDIO, "_intro_norm.mp4"); _normalize_clip(intro, ni)
        parts.append(ni); intro_dur = dur_of(ni)
    parts.append(final)
    if outro:
        no = os.path.join(AUDIO, "_outro_norm.mp4"); _normalize_clip(outro, no); parts.append(no)
    lst = os.path.join(AUDIO, "_concat_brand.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for p in parts:
            f.write(f"file '{p.replace(os.sep,'/')}'\n")
    out = final.replace(".mp4", "_brand.mp4")
    try:    # nhanh: noi truc tiep (cung dinh dang)
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                        "-c", "copy", out], check=True, capture_output=True)
    except subprocess.CalledProcessError:   # du phong: re-encode neu copy loi
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                        *X264, "-r", str(FPS), "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2", out],
                       check=True, capture_output=True)
    os.replace(out, final)   # ghi de len final
    return final, intro_dur

def mix_music(narr_mp4, out_mp4, vol=None, mood="calm"):
    music = get_music(mood)
    if vol is None:
        vol = MUSIC_VOL
    vdur = dur_of(narr_mp4)
    fc = (f"[1:a]volume={vol},afade=t=in:st=0:d=2,"
          f"afade=t=out:st={vdur-3:.2f}:d=3[m];"
          f"[0:a][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]")
    subprocess.run(["ffmpeg","-y","-i",narr_mp4,"-stream_loop","-1","-i",music,
                    "-filter_complex",fc,"-map","0:v","-map","[a]",
                    "-c:v","copy","-c:a","aac","-b:a","192k",out_mp4],
                   check=True, capture_output=True)

# ---------- SEGMENT (TINH / DONG) ----------
_BG_VIDEO_EXT = (".mp4", ".mov", ".webm", ".mkv", ".m4v", ".avi")
def _is_bg_video(p):
    return bool(p) and os.path.splitext(p)[1].lower() in _BG_VIDEO_EXT


def make_static_segment(seg, ctx, i):
    """Slide tinh: 1 hinh + audio, co fade. Neu ctx['_bg_video'] -> overlay chu len VIDEO nen dong."""
    sp = os.path.join(SLIDES, f"s{i:02d}.png")
    render_slide(seg, ctx, sp)
    text, voice = tts_for(seg, ctx)
    if text:
        ap = os.path.join(AUDIO, f"a{i:02d}.mp3")
        synth(text, voice, ap, rate=seg.get("_rate") or ctx.get("rate", "-8%"),
              azure=ctx.get("_azure"), chattts=ctx.get("_chattts", False),
              eleven=ctx.get("_eleven"), gemini=ctx.get("_gemini"),
              emo=_seg_emo(ctx, seg.get("hanzi", "")))
        adur = dur_of(ap)
    else:
        ap, adur = None, 1.6
    pad = seg.get("_pad", ctx.get("pad", PAD))
    # "dam chieu": them khoang lang phan tu sau cau cam xuc (moi engine)
    try:
        pad = pad + _reflective_bonus(text, _expressive)
    except Exception:
        pass
    seg_total = adur + pad
    vp = os.path.join(AUDIO, f"v{i:02d}.mp4")
    bgv = ctx.get("_bg_video")
    if bgv and os.path.exists(bgv):
        # NEN VIDEO DONG: loop video phu kin WxH -> overlay lop chu (PNG trong suot) len tren.
        # -ss theo moc thoi gian (mod thoi luong video) -> bg CHAY LIEN TUC xuyen cac cau, KHONG restart.
        # KHONG fade den giua cau (tranh "nhay den"); bg noi lien mach nen cat cung van muot.
        try:
            _bd = dur_of(bgv)
        except Exception:
            _bd = 0
        _off = round((ctx.get("_seg_start", 0.0) % _bd), 3) if _bd and _bd > 0.5 else 0
        vfc = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
               f"crop={W}:{H},fps={FPS},format=yuv420p[bgv];"
               f"[bgv][1:v]overlay=0:0:format=auto[v]")
        _bg_in = ["-stream_loop","-1","-ss",str(_off),"-i",bgv]
        if ap:
            cmd = ["ffmpeg","-y",*_bg_in,"-loop","1","-i",sp,"-i",ap,
                   "-t",f"{seg_total:.2f}",
                   "-filter_complex",vfc + f";[2:a]aresample=44100,apad=pad_dur={pad}[a]",
                   "-map","[v]","-map","[a]",
                   *X264,"-r",str(FPS),"-pix_fmt","yuv420p",
                   "-c:a","aac","-b:a","192k","-ar","44100","-ac","2",vp]
        else:
            cmd = ["ffmpeg","-y",*_bg_in,"-loop","1","-i",sp,
                   "-f","lavfi","-i","anullsrc=r=44100:cl=stereo",
                   "-t",f"{seg_total:.2f}","-filter_complex",vfc,
                   "-map","[v]","-map","2:a",
                   *X264,"-r",str(FPS),"-pix_fmt","yuv420p",
                   "-c:a","aac","-b:a","192k","-ar","44100","-ac","2",vp]
        subprocess.run(cmd, check=True, capture_output=True)
        return vp, seg_total
    vf = (f"scale={W}:{H},format=yuv420p,"
          f"fade=t=in:st=0:d=0.35:c=0xFFEBED,"
          f"fade=t=out:st={seg_total-0.35:.2f}:d=0.35:c=0xFFEBED")
    if ap:
        cmd = ["ffmpeg","-y","-loop","1","-i",sp,"-i",ap,
               "-t",f"{seg_total:.2f}","-vf",vf,
               "-af",f"aresample=44100,apad=pad_dur={pad}",
               *X264,"-r",str(FPS),"-pix_fmt","yuv420p",
               "-c:a","aac","-b:a","192k","-ar","44100","-ac","2",vp]
    else:
        cmd = ["ffmpeg","-y","-loop","1","-i",sp,
               "-f","lavfi","-i","anullsrc=r=44100:cl=stereo",
               "-t",f"{seg_total:.2f}","-vf",vf,
               *X264,"-r",str(FPS),"-pix_fmt","yuv420p",
               "-c:a","aac","-b:a","192k","-ar","44100","-ac","2",vp]
    subprocess.run(cmd, check=True, capture_output=True)
    return vp, seg_total

def _encode_states(states, ap, total, vp, pad=PAD):
    """states = [(png, start_time)] tang dan (bat dau 0) -> video chu hien dan."""
    lst = os.path.join(AUDIO, "_states.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for k, (png, st) in enumerate(states):
            nxt = states[k+1][1] if k+1 < len(states) else total
            dur = max(nxt - st, 0.04)
            f.write(f"file '{png.replace(os.sep,'/')}'\n")
            f.write(f"duration {dur:.3f}\n")
        f.write(f"file '{states[-1][0].replace(os.sep,'/')}'\n")   # lap file cuoi
    # fps={FPS} ÉP ảnh thành khung CFR ĐỦ thời lượng (sửa lỗi ffmpeg chỉ sinh 1 frame khi
    # 1 ảnh duration >= -t -> truoc day slide chi hien 1/25s roi chay truoc tieng).
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",lst,"-i",ap,
                    "-t",f"{total:.2f}","-vf",f"scale={W}:{H},format=yuv420p,fps={FPS}",
                    "-af",f"aresample=44100,apad=pad_dur={pad}",
                    "-map","0:v","-map","1:a","-fps_mode","cfr",
                    *X264,"-r",str(FPS),"-pix_fmt","yuv420p",
                    "-c:a","aac","-b:a","192k","-ar","44100","-ac","2",vp],
                   check=True, capture_output=True)

DIALOGUE_GAP = 0.35      # khoang nghi giua 2 luot noi (giay)

def dialogue_voice_map(rows, ctx):
    """Tra ve dict {nguoi_noi: voice}. Map theo nhan ('A','B','小明'...) tu _dialogue_map;
       nguoi nao khong gan thi dung giong chinh (voice_zh). Hop voi MOI engine."""
    default_v = ctx.get("voice_zh", VOICE_ZH)
    by_label = ctx.get("_dialogue_map") or {}            # {sp: voice (edge name / voice_id)}
    speakers = []                                        # gom theo thu tu xuat hien
    for r in rows:
        sp = r.get("sp", "")
        if sp not in speakers:
            speakers.append(sp)
    return {sp: (by_label.get(sp) or default_v) for sp in speakers}

def _gap_wav():
    """File im lang DIALOGUE_GAP giay (PCM 44100 stereo) — sinh 1 lan."""
    p = os.path.join(AUDIO, f"_gap_{int(DIALOGUE_GAP*1000)}.wav")
    if not os.path.exists(p):
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi",
                        "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
                        "-t", f"{DIALOGUE_GAP}", "-c:a", "pcm_s16le", p],
                       check=True, capture_output=True)
    return p

def synth_dialogue(rows, ctx, out_wav, vmap):
    """Doc hoi thoai NHIEU GIONG: moi nguoi noi mot voice rieng (A, B, C, D...).
       vmap: dict {nguoi_noi: voice}. Dung CUNG engine voi giong chinh (edge/azure/eleven).
       Tra ve (starts, total): starts[k] = thoi diem bat dau dong k (de canh hien chu).

       DONG BO CHINH XAC: giai ma tung luot ra WAV (PCM) roi noi bang concat -c copy —
       thoi luong tinh theo SAMPLE, khong con lech tich luy do padding cua mp3
       (truoc day chu luc nhanh luc cham hon tieng)."""
    default_v = ctx.get("voice_zh", VOICE_ZH)
    eleven = ctx.get("_eleven")
    azure = ctx.get("_azure")
    chattts = ctx.get("_chattts", False)
    gemini = ctx.get("_gemini")
    rate = ctx.get("rate", "-8%")
    parts, starts, t = [], [], 0.0
    for k, r in enumerate(rows):
        v = vmap.get(r.get("sp", ""), default_v)
        rp = os.path.join(AUDIO, f"_dlg_{k:02d}.mp3")
        emo = _seg_emo(ctx, r.get("hanzi", ""))    # cam xuc rieng TUNG luot noi
        synth(r["hanzi"], v, rp, rate=rate, azure=azure,
              chattts=chattts, eleven=eleven, gemini=gemini, emo=emo)
        wp = os.path.join(AUDIO, f"_dlg_{k:02d}.wav")
        subprocess.run(["ffmpeg", "-y", "-i", rp, "-ar", "44100", "-ac", "2",
                        "-c:a", "pcm_s16le", wp], check=True, capture_output=True)
        d = dur_of(wp)                              # PCM: chinh xac tuyet doi theo sample
        starts.append(t)
        parts.append(wp)
        t += d + DIALOGUE_GAP
    # noi PCM + khoang lang chuan sau moi luot: concat demuxer -c copy (khong re-encode)
    gap = _gap_wav()
    lst = os.path.join(AUDIO, "_dlg_concat.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for wp in parts:
            f.write(f"file '{wp.replace(os.sep, chr(47))}'\n")
            f.write(f"file '{gap.replace(os.sep, chr(47))}'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                    "-c", "copy", out_wav], check=True, capture_output=True)
    return starts, dur_of(out_wav)

def make_anim_segment(seg, ctx, i):
    """Slide chu hien dan tung chu / tung dong theo giong doc."""
    t = seg["type"]
    ap = os.path.join(AUDIO, f"a{i:02d}.mp3")
    pad = seg.get("_pad", ctx.get("pad", PAD))     # _pad: nhip deu cho tung luot podcast
    vp = os.path.join(AUDIO, f"v{i:02d}.mp4")
    states = []

    # Hoi thoai: LUON doc tung luot rieng (synth_dialogue) -> moc hien chu CHINH XAC theo
    # tung luot, dong bo voi giong doc (du 1 hay nhieu giong). Tranh dung word-boundary lech.
    if t == "dialogue":
        rows = seg["rows"]; n = len(rows)
        vmap = dialogue_voice_map(rows, ctx)
        ap = os.path.join(AUDIO, f"a{i:02d}.wav")   # PCM: dong bo chu-tieng chinh xac
        starts, adur = synth_dialogue(rows, ctx, ap, vmap)
        # "dam chieu": them khoang lang phan tu sau cau cam xuc
        try:
            pad = pad + _reflective_bonus(tts_for(seg, ctx)[0], _expressive)
        except Exception:
            pass
        total = adur + pad
        times = [0.0] + list(starts)
        for k in range(n + 1):
            png = os.path.join(SLIDES, f"s{i:02d}_{k:02d}.png")
            render_slide(seg, ctx, png, n_visible=k)
            states.append((png, times[k] if k < len(times) else times[-1]))
        _encode_states(states, ap, total, vp, pad=pad)
        return vp, total

    text, voice = tts_for(seg, ctx)
    sents = synth_paced(text, voice, ap, rate=seg.get("_rate") or ctx.get("rate", "-8%"),
                        comma_pause=float(ctx.get("comma_pause", 0.0) or 0.0),
                        azure=ctx.get("_azure"), chattts=ctx.get("_chattts", False),
                        eleven=ctx.get("_eleven"), gemini=ctx.get("_gemini"),
                        emo=_seg_emo(ctx, seg.get("hanzi", "")))
    adur = dur_of(ap)
    # "dam chieu": them khoang lang phan tu sau cau cam xuc (moi engine)
    try:
        pad = pad + _reflective_bonus(text, _expressive)
    except Exception:
        pass
    # NGHI GIUA DOAN: cau ket thuc 1 doan (truoc dong trong) -> nghi dai hon (para_gap)
    if seg.get("_para_end"):
        pad = pad + float(ctx.get("para_gap", 0.0) or 0.0)
    total = adur + pad

    # Cau/tu vung: hien CA CAU ngay tu dau (1 state tinh) -> text luon khop voi giong doc.
    png = os.path.join(SLIDES, f"s{i:02d}_00.png")
    render_slide(seg, ctx, png, reveal_t=None, show_viet=True)
    states.append((png, 0.0))

    _encode_states(states, ap, total, vp, pad=pad)
    return vp, total

# ---------- BUILD ----------
def build(lesson, progress=None):
    """lesson: duong dan JSON hoac dict ctx.
       progress: callback(done, total, label) de bao tien do (cho app web)."""
    ctx = json.load(open(lesson, encoding="utf-8")) if isinstance(lesson, str) else lesson
    global _eleven_model_override
    _eleven_model_override = ctx.get("_eleven_model")     # model ElevenLabs nguoi dung chon
    global _expressive
    try:
        _expressive = int(ctx.get("expressive", 60) or 60)
    except Exception:
        _expressive = 60
    segs = ctx["segments"]
    if ctx.get("podcast"):
        # podcast: bo intro/outro + cac doan noi tieng Viet, chi giu noi dung Trung
        segs = [s for s in segs if s["type"] not in
                ("title", "objectives", "outro", "practice_q")]
    # bo slide tieu de mo dau (hanzi + ten bai) tru khi nguoi dung bat lai
    if not ctx.get("show_title", False):
        segs = [s for s in segs if s["type"] != "title"]
    # bo slide ket thuc (再见 / cam on / like-subscribe) tru khi nguoi dung bat lai
    if not ctx.get("show_outro", False):
        segs = [s for s in segs if s["type"] != "outro"]
    # layout podcast: bo mascot + tach hoi thoai thanh tung luot (moi luot = 1 slide khung,
    # doc bang giong nguoi noi do). Tranh roi vao layout hoi thoai cu (header + nhan A.).
    if ctx.get("podcast_layout"):
        ctx["mascot"] = "none"
        dmap = ctx.get("_dialogue_map") or {}
        default_v = ctx.get("voice_zh", VOICE_ZH)
        PALETTE = [(40, 96, 196), (192, 57, 110), (224, 142, 30), (46, 139, 76), (120, 80, 180)]
        order = []
        for s in segs:
            if s.get("type") == "dialogue":
                for r in s.get("rows", []):
                    sp = r.get("sp", "")
                    if sp and sp not in order:
                        order.append(sp)
        ctx["_speaker_colors"] = {sp: PALETTE[i % len(PALETTE)] for i, sp in enumerate(order)}
        turn_gap = float(ctx.get("turn_gap", 0.3))   # khoang nghi NGAN & DEU giua cac luot
        expanded = []
        for s in segs:
            if s.get("type") == "dialogue":
                for r in s.get("rows", []):
                    expanded.append({"type": "sentence", "hanzi": r.get("hanzi", ""),
                                     "pinyin": "", "viet": r.get("viet", ""),
                                     "_voice": dmap.get(r.get("sp", "")) or default_v,
                                     "_sp": r.get("sp", ""), "_pad": turn_gap})
            else:
                # cau le trong podcast cung dung nhip deu (khong de khoang lang 0.8 lung tung)
                s = dict(s); s["_pad"] = turn_gap
                expanded.append(s)
        segs = expanded

        # -- CHE DO "DOAN NGHIA + DOC LAI CHAM" (retention): moi cau 2 pha --
        #    pha 1: an nghia Viet, doc toc do thuong + khoang lang recall
        #    pha 2: hien nghia, doc CHAM lai (rate -17%)
        if ctx.get("repeat_slow"):
            def _slow(rate):
                try:
                    return f"{int(str(rate).replace('%','')) - 17}%"
                except ValueError:
                    return "-25%"
            slow_rate = _slow(ctx.get("rate", "-8%"))
            twice = []
            for s in segs:
                if s.get("type") == "sentence" and s.get("viet"):
                    p1 = dict(s); p1["_hide_viet"] = True; p1["_pad"] = 1.6   # lang de doan
                    p2 = dict(s); p2["_rate"] = slow_rate
                    twice += [p1, p2]
                else:
                    twice.append(s)
            segs = twice

        # -- VONG ON CUOI VIDEO: phat lai toan bo cau, AN nghia Viet (watch time ~x1.5) --
        if ctx.get("replay_loop"):
            replay = [dict(s, _hide_viet=True, _pad=0.5)
                      for s in segs if s.get("type") == "sentence"
                      and not s.get("_hide_viet")]
            if replay:
                segs = segs + [{"type": "section",
                                "label": "Nghe lại — không nhìn nghĩa"}] + replay

        # -- DANH SO CAU (bo dem 12/50 + thanh tien do trong style_podcast) --
        counted = [s for s in segs if s.get("type") in ("sentence", "vocab", "practice_a")]
        for k, s in enumerate(counted, 1):
            s["_idx"], s["_n"] = k, len(counted)
    n = len(segs)
    print(f'>> Bai {ctx.get("id","?")}: {ctx.get("title","")} — {n} doan')

    # Co chu Han DONG NHAT cho moi cau (theo cau DAI NHAT) -> khong nhay chu giua cac slide
    _sent = [s.get("hanzi", "") for s in segs if s.get("type") == "sentence"]
    if _sent and "zh_size" not in ctx:
        _d = ImageDraw.Draw(Image.new("RGB", (W, H)))
        _zf = style_pastel.font("zh", 116)
        longest = max(_sent, key=lambda h: style_pastel.text_w(_d, h, _zf))
        # kep [88,116]: giu chu du to & dong nhat; cau dai bat thuong se xuong dong (cung co)
        # giu cỡ TO & dong nhat (>=100); cau dai se XUONG DONG cung co (khong thu nho)
        fit = style_pastel.fit_zh_size(_d, longest, 118, min_size=100)
        ctx["zh_size"] = max(100, min(118, fit))
        print(f"   Co chu cau (dong nhat): {ctx['zh_size']}px")

    if ctx.get("ai_mascot"):
        if progress:
            progress(0, n + 1, "AI đang vẽ hình minh hoạ theo chủ đề...")
        setup_mascot(ctx)

    # mascot chuyen dong nhe: chuan bi PNG overlay + bo mascot tinh trong slide
    if ctx.get("mascot_motion", True) and ctx.get("mascot") != "none":
        ctx["_mascot_png"] = make_standalone_mascot(ctx)
        if ctx.get("_mascot_png"):
            ctx["_skip_mascot_in_slide"] = True

    # NEN NHIEU NGUON (anh HOAC video dong): chia DEU theo thoi luong (uoc luong = do dai text doc)
    # -> moi doan gan 1 nguon theo moc tich luy, xoay vong THEO THU TU. Nguon = anh (bake) hoac video (overlay).
    _bg_list = list(ctx.get("bg_images") or [])
    if not _bg_list and ctx.get("bg_image"):
        _bg_list = [ctx["bg_image"]]
    _bg_list = [p for p in _bg_list if p and os.path.exists(p)]
    _seg_bg = None
    if _bg_list and ctx.get("bg_by_scene"):
        # THEO PHAN CANH: moi MUC '#' (section) dung 1 nguon theo thu tu (clamp o nguon cuoi)
        _seg_bg, _sec, _started = [], 0, False
        for s in segs:
            if s.get("type") == "section":
                if _started:
                    _sec += 1
                _started = True
            _seg_bg.append(_bg_list[min(len(_bg_list) - 1, _sec)])
        _nsec = _sec + 1 if _started else 1
        _nvid = sum(1 for p in _bg_list if _is_bg_video(p))
        print(f"  [BG] {len(_bg_list)} nguồn ({len(_bg_list)-_nvid} ảnh + {_nvid} video) "
              f"— THEO PHÂN CẢNH ({_nsec} mục '#')")
    elif _bg_list:
        # CHIA DEU theo thoi luong (uoc luong = do dai text doc)
        _weights = []
        for s in segs:
            try:
                _t, _ = tts_for(s, ctx)
            except Exception:
                _t = s.get("hanzi", "")
            _weights.append(max(1, len(_t or "")))
        _tot = sum(_weights) or 1
        _win = _tot / len(_bg_list)
        _seg_bg, _cum = [], 0.0
        for _w in _weights:
            _seg_bg.append(_bg_list[min(len(_bg_list) - 1, int(_cum / _win))])
            _cum += _w
        _nvid = sum(1 for p in _bg_list if _is_bg_video(p))
        print(f"  [BG] {len(_bg_list)} nguồn nền ({len(_bg_list)-_nvid} ảnh + {_nvid} video) "
              f"— chia đều theo thời lượng")

    # AN THE PHAN CANH: van dem muc '#' de doi nen (o tren), nhung KHONG render slide tieu de.
    # Dung cho series dai: moi the la ~1.6s man hinh cam, khong giup gi cho nguoi hoc.
    if ctx.get("hide_section_slides"):
        _keep = [i for i, s in enumerate(segs) if s.get("type") != "section"]
        _nhid = len(segs) - len(_keep)
        if _nhid:
            if _seg_bg:
                _seg_bg = [_seg_bg[i] for i in _keep]
            segs = [segs[i] for i in _keep]
            print(f"  [BG] ẩn {_nhid} thẻ phân cảnh (vẫn giữ mốc đổi nền)")

    seg_videos = []
    seg_meta = []          # [{index,type,dur,start,end,hanzi,viet,label}] cho timestamp YouTube
    _clock = 0.0
    for i, seg in enumerate(segs):
        if _seg_bg:                       # dat nguon nen cho doan nay truoc khi render
            _src = _seg_bg[i]
            if _is_bg_video(_src):        # video dong -> render chu trong suot + overlay
                ctx["_bg_video"] = _src; ctx["_transparent"] = True; ctx["bg_image"] = None
            else:                         # anh tinh -> bake nhu cu
                ctx["_bg_video"] = None;  ctx["_transparent"] = False; ctx["bg_image"] = _src
        ctx["_seg_start"] = _clock            # moc thoi gian -> bg video chay LIEN TUC xuyen cac cau
        # nen VIDEO -> di duong static (overlay chu day du len video; bo hieu ung hien dan v1)
        if seg["type"] in ANIM_TYPES and not ctx.get("_bg_video"):
            vp, seg_total = make_anim_segment(seg, ctx, i)
        else:
            vp, seg_total = make_static_segment(seg, ctx, i)
        seg_videos.append(vp)
        seg_meta.append({
            "index": i, "type": seg["type"],
            "dur": round(seg_total, 3), "start": round(_clock, 3),
            "end": round(_clock + seg_total, 3),
            "hanzi": seg.get("hanzi", ""), "viet": seg.get("viet", ""),
            "label": seg.get("label", ""),
        })
        _clock += seg_total
        print(f"  [{i+1:02d}/{n}] {seg['type']:11s} {seg_total:5.1f}s")
        if progress:
            progress(i + 1, n + 1, f"Dựng slide {i+1}/{n}")

    # noi tat ca
    concat_txt = os.path.join(AUDIO, "concat.txt")
    with open(concat_txt, "w", encoding="utf-8") as f:
        for v in seg_videos:
            f.write(f"file '{v.replace(os.sep,'/')}'\n")
    narr = os.path.join(AUDIO, "_narr.mp4")
    # RE-ENCODE khi noi (khong dung -c copy): ep khung hinh deu (CFR) + dong bo lai audio
    # -> tranh lech tieng-hinh TICH LUY qua nhieu luot (chu chay truoc tieng o luot sau).
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",concat_txt,
                    "-vsync","cfr","-r",str(FPS),
                    *X264,"-pix_fmt","yuv420p",
                    "-af","aresample=async=1:first_pts=0",
                    "-c:a","aac","-b:a","192k","-ar","44100","-ac","2",narr],
                   check=True, capture_output=True)
    if progress:
        progress(n, n + 1, "Trộn nhạc & xuất video")

    out_name = ctx.get("out_name") or \
        f'HSK1_Bai{int(ctx.get("id",1)):02d}_{ctx.get("title","video").replace(" ","")}'
    final = os.path.join(OUT, out_name + ".mp4")
    compose_final(narr, ctx, final)   # overlay mascot bong benh + tron nhac
    # ghep intro/outro thuong hieu (neu co brand/intro.mp4 / outro.mp4)
    final, intro_dur = attach_intro_outro(final, ctx)
    if intro_dur:
        # dich timestamp phu de/chuong theo do dai intro o dau
        for s in seg_meta:
            s["start"] = round(s["start"] + intro_dur, 3)
            s["end"] = round(s["end"] + intro_dur, 3)
        print(f"   + Intro {intro_dur:.1f}s -> da dich timestamp")
    if progress:
        progress(n + 1, n + 1, "Hoàn tất")
    print(f"\n✅ XONG: {final}")
    total_dur = dur_of(final)
    print(f"   Thoi luong: {total_dur:.1f}s")
    # ghi metadata segment (thoi luong that) de Buoc 2 sinh timestamp YouTube
    ctx["_seg_meta"] = seg_meta
    ctx["_total_dur"] = round(total_dur, 3)
    try:
        with open(final + ".meta.json", "w", encoding="utf-8") as f:
            json.dump({"title": ctx.get("title", ""), "hsk": ctx.get("hsk", ""),
                       "total_dur": round(total_dur, 3), "segments": seg_meta},
                      f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("  [meta.json] khong ghi duoc:", e)
    # tao thumbnail (anh bia YouTube)
    try:
        thumb = final[:-4] + ".thumb.jpg"
        style_pastel.make_thumbnail(ctx, thumb)
        print(f"   Thumbnail: {os.path.basename(thumb)}")
    except Exception as e:
        print("  [thumbnail] loi:", e)
    return final

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT,"data","lesson01.json")
    build(path)
