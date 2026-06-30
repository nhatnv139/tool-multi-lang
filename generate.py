# -*- coding: utf-8 -*-
"""
Tu dong tao video bai hoc tieng Trung (HSK) tu file JSON.
- Tu sinh background gradient (PIL)
- Render slide chu Han + Pinyin + nghia tieng Viet
- Giong doc AI (edge-tts) - tieng Trung + tieng Viet
- Ghep slide + audio dong bo bang FFmpeg
Cach dung:  python generate.py data/lesson01.json
"""
import os, sys, json, subprocess, shutil, asyncio
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import edge_tts
from PIL import Image, ImageDraw, ImageFont
import style_pastel                       # bo render kieu pastel (pinyin tren chu)
render_slide = style_pastel.render_slide  # dung render moi thay cho ban do cu

ANIM_TYPES = {"vocab", "sentence", "practice_a", "dialogue"}   # cac loai chu hien dan

# ---------- CAU HINH ----------
W, H = 1920, 1080
FPS = 25
PAD = 0.8                      # giay im lang them sau moi doan
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
    vz = ctx.get("voice_zh", VOICE_ZH)
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
def _tts_key(text, voice, rate):
    return hashlib.md5(f"{voice}|{rate}|{text}".encode("utf-8")).hexdigest()

def _ssml_escape(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def synth_azure(text, voice, path, key, region, rate="-8%"):
    """Azure TTS (giong HD/Multilingual tu nhien hon). Ghi mp3 ra path."""
    ssml = (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xml:lang="zh-CN"><voice name="{voice}">'
            f'<prosody rate="{_norm_rate(rate)}">{_ssml_escape(text)}</prosody></voice></speak>')
    url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
        "User-Agent": "chinese-youtube",
    }
    req = urllib.request.Request(url, data=ssml.encode("utf-8"),
                                 headers=headers, method="POST")
    data = urllib.request.urlopen(req, timeout=60).read()
    with open(path, "wb") as f:
        f.write(data)

ELEVEN_MODEL = "eleven_multilingual_v2"   # da ngon ngu: 1 giong doc ca Trung + Viet

def _rate_to_eleven_speed(rate):
    """edge rate (vd -8%) -> ElevenLabs speed (0.7..1.2; 1.0 = binh thuong)."""
    try:
        pct = int(str(rate).replace("%", ""))
    except ValueError:
        pct = -8
    return max(0.7, min(1.2, round(1.0 + pct / 100.0, 2)))

def synth_eleven(text, voice_id, path, key, rate="-8%", model=ELEVEN_MODEL):
    """ElevenLabs TTS (tra phi, chat luong cao). Ghi mp3 ra path.
       voice_id lay tu ElevenLabs (Voice Lab / Voices). 1 giong da ngu noi ca Trung+Viet."""
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    payload = {
        "text": text,
        "model_id": model,
        "voice_settings": {
            "stability": 0.5, "similarity_boost": 0.75,
            "style": 0.0, "use_speaker_boost": True,
            "speed": _rate_to_eleven_speed(rate),
        },
    }
    headers = {"xi-api-key": key, "Content-Type": "application/json",
               "Accept": "audio/mpeg"}

    def _post(body):
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                     headers=headers, method="POST")
        return urllib.request.urlopen(req, timeout=120).read()

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
            raise RuntimeError(f"ElevenLabs loi {e.code}: {detail or e.reason}")
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

def synth_gemini(text, voice, path, key, rate="-8%", model=GEMINI_MODEL):
    """Gemini TTS (Google AI Studio). Tra ve PCM 16-bit/24kHz/mono base64 -> mp3.
       voice = ten giong prebuilt (Kore, Puck, Zephyr...). 1 giong doc ca Trung + Viet."""
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent")
    payload = {
        "contents": [{"parts": [{"text": text}]}],
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
    # PCM raw (s16le, 24kHz, mono) -> mp3 qua ffmpeg, chinh toc do bang atempo
    cmd = ["ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", "pipe:0",
           "-filter:a", f"atempo={_rate_to_atempo(rate)}",
           "-c:a", "libmp3lame", "-q:a", "2", path]
    subprocess.run(cmd, input=pcm, check=True, capture_output=True)

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

def _synth_edge(text, voice, path, rate="-8%"):
    """Sinh giong bang edge-tts (mien phi, can internet)."""
    cmd = [sys.executable, "-m", "edge_tts", "--voice", voice,
           "--text", text, f"--rate={_norm_rate(rate)}", "--write-media", path]
    subprocess.run(cmd, check=True, capture_output=True)

def _edge_voice(voice):
    """Tra ve giong edge hop le; vname kieu 'local' (ChatTTS) -> giong Trung mac dinh."""
    return voice if (voice and "-" in voice and "Neural" in voice) else VOICE_ZH

def synth(text, voice, path, rate="-8%", azure=None, chattts=False, eleven=None,
          gemini=None):
    """Giong doc co cache. chattts -> ChatTTS local; eleven=key -> ElevenLabs;
       gemini=key -> Gemini TTS; azure=(key,region) -> Azure; con lai -> edge-tts.
       ChatTTS loi -> fallback edge."""
    eng = ("ct-" + str(chattts)) if chattts else \
          ("gm" if gemini else ("el" if eleven else ("az" if azure else "ed")))
    c = os.path.join(TTS_CACHE, _tts_key(eng + text, voice, rate) + ".mp3")
    if not os.path.exists(c):
        if chattts:
            try:
                import chattts_engine
                style = chattts if isinstance(chattts, str) else "warm"
                p = chattts_engine.STYLES.get(style, chattts_engine.STYLES["warm"])
                chattts_engine.synth_chattts(text, c, speed=_rate_to_speed(rate), **p)
            except Exception as e:
                print(f"[ChatTTS khong dung duoc -> chuyen sang edge-tts] {e}")
                _synth_edge(text, _edge_voice(voice), c, rate)
        elif gemini:
            synth_gemini(text, voice, c, gemini, rate)
        elif eleven:
            synth_eleven(text, voice, c, eleven, rate)
        elif azure:
            synth_azure(text, voice, c, azure[0], azure[1], rate)
        else:
            _synth_edge(text, voice, c, rate)
    shutil.copyfile(c, path)

def synth_timed(text, voice, path, rate="-8%", azure=None, chattts=False, eleven=None,
                gemini=None):
    """Ghi mp3 + tra ve list (start,end) cac cau. Co cache.
       chattts/azure/eleven/gemini: khong co moc cau -> [] (fallback rai deu chu)."""
    eng = ("ct-" + str(chattts)) if chattts else \
          ("gm" if gemini else ("el" if eleven else ("az" if azure else "ed")))
    key = _tts_key(eng + text, voice, rate)
    c = os.path.join(TTS_CACHE, key + ".mp3")
    cj = os.path.join(TTS_CACHE, key + ".sents.json")
    if os.path.exists(c) and os.path.exists(cj):
        shutil.copyfile(c, path)
        return json.load(open(cj, encoding="utf-8"))

    if chattts or azure or eleven or gemini:  # khong co moc cau -> [] (rai deu chu)
        if chattts:
            try:
                import chattts_engine
                style = chattts if isinstance(chattts, str) else "warm"
                p = chattts_engine.STYLES.get(style, chattts_engine.STYLES["warm"])
                chattts_engine.synth_chattts(text, c, speed=_rate_to_speed(rate), **p)
            except Exception as e:
                print(f"[ChatTTS khong dung duoc -> chuyen sang edge-tts] {e}")
                # edge co moc cau -> ghi binh thuong va tra ve moc that
                sents = _synth_edge_timed(text, _edge_voice(voice), c, rate)
                json.dump(sents, open(cj, "w", encoding="utf-8"))
                shutil.copyfile(c, path)
                return sents
        elif gemini:
            synth_gemini(text, voice, c, gemini, rate)
        elif eleven:
            synth_eleven(text, voice, c, eleven, rate)
        else:
            synth_azure(text, voice, c, azure[0], azure[1], rate)
        json.dump([], open(cj, "w", encoding="utf-8"))
        shutil.copyfile(c, path)
        return []

    sents = _synth_edge_timed(text, voice, c, rate)
    json.dump(sents, open(cj, "w", encoding="utf-8"))
    shutil.copyfile(c, path)
    return sents

def _synth_edge_timed(text, voice, out_mp3, rate="-8%"):
    """edge-tts -> ghi out_mp3 + tra ve list (start,end) cac cau/tu."""
    async def go():
        comm = edge_tts.Communicate(text, voice, rate=_norm_rate(rate))
        sents = []
        with open(out_mp3, "wb") as f:
            async for ch in comm.stream():
                if ch["type"] == "audio":
                    f.write(ch["data"])
                elif ch["type"] in ("SentenceBoundary", "WordBoundary"):
                    sents.append([ch["offset"]/1e7, (ch["offset"]+ch["duration"])/1e7])
        return sents
    return asyncio.run(go())

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

def compose_final(narr, ctx, final):
    """Ghep buoc cuoi: overlay mascot bong benh + tron nhac (tuy chon)."""
    mascot = ctx.get("_mascot_png")
    music_on = ctx.get("music", True)
    vol = ctx.get("music_vol", MUSIC_VOL)
    vdur = dur_of(narr)
    inputs = ["-i", narr]
    parts, idx = [], 1
    vmap, amap = "0:v", "0:a"
    if mascot:
        inputs += ["-i", mascot]; mi = idx; idx += 1
        # bong benh: len xuong 13px moi ~2.6s
        parts.append(f"[0:v][{mi}:v]overlay=x=42:"
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
                     "dropout_transition=0:normalize=0[a]")
        amap = "[a]"
    cmd = ["ffmpeg", "-y", *inputs]
    if parts:
        cmd += ["-filter_complex", ";".join(parts)]
    vcodec = (["-c:v", "libx264", "-r", str(FPS), "-pix_fmt", "yuv420p"]
              if mascot else ["-c:v", "copy"])
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
    base = ["-c:v", "libx264", "-r", str(FPS), "-pix_fmt", "yuv420p",
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
                        "-c:v", "libx264", "-r", str(FPS), "-pix_fmt", "yuv420p",
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
def make_static_segment(seg, ctx, i):
    """Slide tinh: 1 hinh + audio, co fade."""
    sp = os.path.join(SLIDES, f"s{i:02d}.png")
    render_slide(seg, ctx, sp)
    text, voice = tts_for(seg, ctx)
    if text:
        ap = os.path.join(AUDIO, f"a{i:02d}.mp3")
        synth(text, voice, ap, rate=ctx.get("rate", "-8%"),
              azure=ctx.get("_azure"), chattts=ctx.get("_chattts", False),
              eleven=ctx.get("_eleven"), gemini=ctx.get("_gemini"))
        adur = dur_of(ap)
    else:
        ap, adur = None, 1.6
    pad = ctx.get("pad", PAD)
    seg_total = adur + pad
    vp = os.path.join(AUDIO, f"v{i:02d}.mp4")
    vf = (f"scale={W}:{H},format=yuv420p,"
          f"fade=t=in:st=0:d=0.35:c=0xFFEBED,"
          f"fade=t=out:st={seg_total-0.35:.2f}:d=0.35:c=0xFFEBED")
    if ap:
        cmd = ["ffmpeg","-y","-loop","1","-i",sp,"-i",ap,
               "-t",f"{seg_total:.2f}","-vf",vf,
               "-af",f"aresample=44100,apad=pad_dur={pad}",
               "-c:v","libx264","-r",str(FPS),"-pix_fmt","yuv420p",
               "-c:a","aac","-b:a","192k","-ar","44100","-ac","2",vp]
    else:
        cmd = ["ffmpeg","-y","-loop","1","-i",sp,
               "-f","lavfi","-i","anullsrc=r=44100:cl=stereo",
               "-t",f"{seg_total:.2f}","-vf",vf,
               "-c:v","libx264","-r",str(FPS),"-pix_fmt","yuv420p",
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
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",lst,"-i",ap,
                    "-t",f"{total:.2f}","-vf",f"scale={W}:{H},format=yuv420p",
                    "-af",f"aresample=44100,apad=pad_dur={pad}",
                    "-map","0:v","-map","1:a",
                    "-c:v","libx264","-r",str(FPS),"-pix_fmt","yuv420p",
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

def synth_dialogue(rows, ctx, out_mp3, vmap):
    """Doc hoi thoai NHIEU GIONG: moi nguoi noi mot voice rieng (A, B, C, D...).
       vmap: dict {nguoi_noi: voice}. Dung CUNG engine voi giong chinh (edge/azure/eleven).
       Tra ve (starts, total): starts[k] = thoi diem bat dau dong k (de canh hien chu)."""
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
        synth(r["hanzi"], v, rp, rate=rate, azure=azure,
              chattts=chattts, eleven=eleven, gemini=gemini)  # co cache theo (giong,text)
        d = dur_of(rp)
        starts.append(t)
        parts.append(rp)
        t += d + DIALOGUE_GAP
    # ghep cac luot lai, chen khoang lang DIALOGUE_GAP sau moi luot
    inputs, filt = [], []
    for k, rp in enumerate(parts):
        inputs += ["-i", rp]
        filt.append(f"[{k}:a]aresample=44100,apad=pad_dur={DIALOGUE_GAP}[a{k}]")
    concat_in = "".join(f"[a{k}]" for k in range(len(parts)))
    filt.append(f"{concat_in}concat=n={len(parts)}:v=0:a=1[out]")
    subprocess.run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filt),
                    "-map", "[out]", "-c:a", "libmp3lame", "-q:a", "2", out_mp3],
                   check=True, capture_output=True)
    return starts, dur_of(out_mp3)

def make_anim_segment(seg, ctx, i):
    """Slide chu hien dan tung chu / tung dong theo giong doc."""
    t = seg["type"]
    ap = os.path.join(AUDIO, f"a{i:02d}.mp3")
    pad = ctx.get("pad", PAD)
    vp = os.path.join(AUDIO, f"v{i:02d}.mp4")
    states = []

    # Hoi thoai nhieu giong (MOI engine: edge/azure/eleven) khi co gan giong theo nguoi noi
    has_dlg_cfg = bool(ctx.get("_dialogue_map"))
    if t == "dialogue" and has_dlg_cfg:
        rows = seg["rows"]; n = len(rows)
        vmap = dialogue_voice_map(rows, ctx)
        starts, adur = synth_dialogue(rows, ctx, ap, vmap)
        total = adur + pad
        times = [0.0] + list(starts)
        for k in range(n + 1):
            png = os.path.join(SLIDES, f"s{i:02d}_{k:02d}.png")
            render_slide(seg, ctx, png, n_visible=k)
            states.append((png, times[k] if k < len(times) else times[-1]))
        _encode_states(states, ap, total, vp, pad=pad)
        return vp, total

    text, voice = tts_for(seg, ctx)
    sents = synth_timed(text, voice, ap, rate=ctx.get("rate", "-8%"),
                        azure=ctx.get("_azure"), chattts=ctx.get("_chattts", False),
                        eleven=ctx.get("_eleven"), gemini=ctx.get("_gemini"))
    adur = dur_of(ap)
    total = adur + pad

    if t == "dialogue":
        rows = seg["rows"]; n = len(rows)
        starts = [s[0] for s in sents][:n]
        if len(starts) < n:                      # thieu moc -> rai deu
            end = sents[-1][1] if sents else adur
            starts = [end * k / n for k in range(n)]
        times = [0.0] + list(starts)             # state k hien k dong
        for k in range(n + 1):
            png = os.path.join(SLIDES, f"s{i:02d}_{k:02d}.png")
            render_slide(seg, ctx, png, n_visible=k)
            states.append((png, times[k] if k < len(times) else times[-1]))
    else:
        # Hien CA CAU chu Trung NGAY tu dau (khong chay tung chu theo giong doc),
        # giong nhu dong tieng Viet -> chi can 1 state tinh cho ca doan.
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

    seg_videos = []
    seg_meta = []          # [{index,type,dur,start,end,hanzi,viet,label}] cho timestamp YouTube
    _clock = 0.0
    for i, seg in enumerate(segs):
        if seg["type"] in ANIM_TYPES:
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
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",concat_txt,
                    "-c","copy",narr], check=True, capture_output=True)
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
