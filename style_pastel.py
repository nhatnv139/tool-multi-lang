# -*- coding: utf-8 -*-
"""Bo render kieu PASTEL (giong kenh hoc tieng Trung): pinyin tren tung chu Han.
   Dung cho moi loai slide: title, objectives, section, vocab, sentence,
   dialogue, practice_q, practice_a, outro."""
import sys, os
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pypinyin import pinyin, Style
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

W, H = 1920, 1080
# ---------- THEME MAU ----------
THEMES = {
    "pink":     dict(BG=(255,235,237), INK=(60,56,58),  PINYIN=(150,140,142),
                     VIET=(170,55,70),  HEADER=(90,80,82), LINE=(210,175,180),
                     BADGE=(244,162,97), GOLD=(224,122,95), SOFT=(120,105,108)),
    "mint":     dict(BG=(223,240,242), INK=(48,60,62),  PINYIN=(120,140,142),
                     VIET=(40,110,120), HEADER=(70,95,98), LINE=(170,200,202),
                     BADGE=(95,170,175), GOLD=(70,150,158), SOFT=(110,130,132)),
    "cream":    dict(BG=(250,243,228), INK=(70,60,48),  PINYIN=(160,148,128),
                     VIET=(168,96,40),  HEADER=(100,88,68), LINE=(214,198,168),
                     BADGE=(212,160,80), GOLD=(190,135,60), SOFT=(140,128,108)),
    "lavender": dict(BG=(238,232,247), INK=(58,52,68),  PINYIN=(150,142,162),
                     VIET=(110,70,160), HEADER=(92,82,108), LINE=(202,190,222),
                     BADGE=(150,120,210), GOLD=(130,100,190), SOFT=(126,118,140)),
    "sky":      dict(BG=(228,238,250), INK=(50,58,72),  PINYIN=(132,144,162),
                     VIET=(40,90,170),  HEADER=(74,88,112), LINE=(184,200,226),
                     BADGE=(86,140,220), GOLD=(60,120,200), SOFT=(116,128,148)),
    # "none": khong phu mau len anh nen — giu nguyen anh; chu tong XANH NAVY hai hoa
    "none":     dict(BG=(245,247,250), INK=(33,62,100),  PINYIN=(92,122,158),
                     VIET=(24,74,98),   HEADER=(56,78,112), LINE=(168,186,210),
                     BADGE=(86,134,180), GOLD=(60,116,170), SOFT=(96,116,148)),
}
# mau hien hanh (mac dinh hong) — apply_theme() doi bo nay
BG, INK, PINYIN, VIET, HEADER, LINE, BADGE, GOLD, SOFT = (
    THEMES["pink"]["BG"], THEMES["pink"]["INK"], THEMES["pink"]["PINYIN"],
    THEMES["pink"]["VIET"], THEMES["pink"]["HEADER"], THEMES["pink"]["LINE"],
    THEMES["pink"]["BADGE"], THEMES["pink"]["GOLD"], THEMES["pink"]["SOFT"])

# Lop phu mo len anh nen (mau theme + do dam) — apply_theme() dat lai
VEIL_RGBA = THEMES["pink"]["BG"] + (170,)

def apply_theme(name):
    global BG, INK, PINYIN, VIET, HEADER, LINE, BADGE, GOLD, SOFT, VEIL_RGBA
    t = THEMES.get(name, THEMES["pink"])
    BG, INK, PINYIN, VIET = t["BG"], t["INK"], t["PINYIN"], t["VIET"]
    HEADER, LINE, BADGE = t["HEADER"], t["LINE"], t["BADGE"]
    GOLD, SOFT = t["GOLD"], t["SOFT"]
    # "none": GIU NGUYEN anh, khong phu lop nao (alpha 0 -> _prep_bg tra ve anh goc)
    VEIL_RGBA = (255, 255, 255, 0) if name == "none" else (BG + (170,))
    # nen anh sang/nhieu chi tiet -> bat quang sang sau chu cho ro net (khong lam mo anh)
    global TEXT_GLOW
    TEXT_GLOW = (name == "none")

_HERE = os.path.dirname(os.path.abspath(__file__))
# Kaiti (thu phap) duoc copy san vao assets/fonts; du phong STHeiti/Songti neu thieu
_KAITI = os.path.join(_HERE, "assets", "fonts", "Kaiti.ttc")
_AVENIR = "/System/Library/Fonts/Avenir Next.ttc"   # .ttc nhieu weight (xem index ben duoi)

def _pick_font(*candidates):
    """Tra ve font dau tien ton tai (cross-platform Windows/macOS/Linux)."""
    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[-1]

def _spec(win_path, mac_path, mac_index=0, *fallbacks):
    """Tra ve (path, index). Uu tien Windows (index 0) -> macOS (index chi dinh) -> du phong."""
    if os.path.exists(win_path):
        return (win_path, 0)
    if os.path.exists(mac_path):
        return (mac_path, mac_index)
    for fb in fallbacks:
        if os.path.exists(fb):
            return (fb, 0)
    return (mac_path, mac_index)

# Tieng Viet + Latin: Lexend (variable font) — chon weight bang ten instance.
_LEXEND = os.path.join(_HERE, "assets", "fonts", "Lexend.ttf")
_AV_IDX = {"Regular": 7, "Medium": 5, "SemiBold": 2, "Bold": 0}   # map khi du phong Avenir
def _latin(weight):
    """(path, None, weight) cho Lexend variable; du phong Avenir/Arial neu thieu Lexend."""
    if os.path.exists(_LEXEND):
        return (_LEXEND, None, weight)
    if os.path.exists(_AVENIR):
        return (_AVENIR, _AV_IDX.get(weight, 7))
    win = "C:/Windows/Fonts/arialbd.ttf" if weight in ("Bold", "SemiBold") else "C:/Windows/Fonts/arial.ttf"
    return (win, 0)

# Avenir Next.ttc face index: 0=Bold 1=BoldItalic 2=DemiBold 3=DemiBoldItalic 5=Medium 7=Regular
F = {
    # chu Han: Kaiti (thu phap) tren macOS; SimSun tren Windows
    "zh":     _spec("C:/Windows/Fonts/simsun.ttc", _KAITI, 0,
                    "/System/Library/Fonts/STHeiti Medium.ttc",
                    "/System/Library/Fonts/Supplemental/Songti.ttc",
                    "/System/Library/Fonts/Hiragino Sans GB.ttc"),
    "pinyin": _latin("Regular"),    # pinyin nhe, thanh
    "viet":   _latin("SemiBold"),   # nghia Viet (nhan)
    "head":   _latin("Medium"),     # header tren cung
    "badge":  _latin("Bold"),       # badge HSK
    "sans":   _latin("Regular"),    # van ban thuong
    "sansb":  _latin("SemiBold"),   # van ban dam
}
EMOJI = _pick_font("C:/Windows/Fonts/seguiemj.ttf",
                   "/System/Library/Fonts/Apple Color Emoji.ttc")
# Apple Color Emoji la font bitmap, chi nhan vai size co dinh -> nan ve gan nhat.
_EMOJI_IS_BITMAP = EMOJI.endswith("Apple Color Emoji.ttc")
_EMOJI_STRIKES = (20, 26, 32, 40, 48, 52, 64, 96, 160)
def _emoji_size(s):
    if not _EMOJI_IS_BITMAP:
        return s
    return min(_EMOJI_STRIKES, key=lambda k: abs(k - s))

MASCOTS = ["🐼", "🐱", "🐰", "🐻", "🐯", "🐨", "🦊", "🐧"]
_fc = {}
def font(k, s):
    key = (k, s)
    if key not in _fc:
        spec = F[k]
        if isinstance(spec, tuple) and len(spec) == 3:   # (path, None, weight) - variable font
            f = ImageFont.truetype(spec[0], s)
            try:
                f.set_variation_by_name(spec[2])
            except Exception:
                pass
            _fc[key] = f
        elif isinstance(spec, tuple):                    # (path, face_index) - .ttc
            _fc[key] = ImageFont.truetype(spec[0], s, index=spec[1])
        else:
            _fc[key] = ImageFont.truetype(spec, s)
    return _fc[key]

_ec = {}
def emoji_font(s):
    if s not in _ec:
        _ec[s] = ImageFont.truetype(EMOJI, _emoji_size(s))
    return _ec[s]

_mascot_img_cache = {}
def draw_mascot(im, d, ctx):
    """Mascot góc dưới-trái. Uu tien hinh AI (ctx['_mascot_img']); neu khong thi
       emoji. ctx['mascot']=='none' -> tat."""
    if ctx.get("mascot", "") == "none":
        return
    # 1) hinh AI theo chu de
    img = ctx.get("_mascot_img")
    if img and os.path.exists(img):
        if img not in _mascot_img_cache:
            mi = Image.open(img).convert("RGBA")
            hgt = 260
            mi = mi.resize((int(mi.width * hgt / mi.height), hgt))
            _mascot_img_cache[img] = mi
        mi = _mascot_img_cache[img]
        im.paste(mi, (38, H - mi.height - 26), mi)
        return
    # 2) emoji
    m = ctx.get("mascot", "")
    e = m if m else MASCOTS[(int(ctx.get("id", 1)) - 1) % len(MASCOTS)]
    d.text((48, H-165), e, font=emoji_font(130), embedded_color=True)
    d.text((180, H-185), "🎵", font=emoji_font(46), embedded_color=True)
    d.text((170, H-92), "🎧", font=emoji_font(44), embedded_color=True)

def has_hanzi(ch):
    return '一' <= ch <= '鿿'

def hex2rgb(h):
    """'#rrggbb' -> (r,g,b); sai/rong -> None (dung mau mac dinh)."""
    try:
        h = (h or "").strip().lstrip("#")
        if len(h) != 6:
            return None
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, AttributeError):
        return None

def text_w(d, t, f):
    bb = d.textbbox((0, 0), t, font=f); return bb[2]-bb[0]

BIG = 1e9

def flatten(text):
    """[(ch, pinyin, is_hanzi), ...] theo dung thu tu hien thi."""
    plist = pinyin(text, style=Style.TONE, errors=lambda x: [c for c in x])
    flat, pi = [], 0
    for ch in text:
        h = has_hanzi(ch)
        p = plist[pi][0] if (pi < len(plist) and h) else ""
        flat.append((ch, p, h)); pi += 1
    return flat

def py_hanzi(d, text, cx, top, zh_size=130, py_size=44,
             char_gap=14, py_gap=16, max_w=1640, draw=True,
             reveal_t=None, t_now=BIG):
    """Ve chu Han + pinyin tren tung chu. Tra ve chieu cao.
       reveal_t: mang thoi-gian-hien moi chu (cung do dai flat); chi ve chu i
       neu reveal_t[i] <= t_now. None = ve het."""
    flat = flatten(text)
    zf, pf = font("zh", zh_size), font("pinyin", py_size)
    cw = lambda ch: text_w(d, ch, zf)
    # chia dong (giu vi tri co dinh cho moi chu du da hien hay chua)
    lines, cur, curw, gidx = [], [], 0, 0
    for ch, p, h in flat:
        w = cw(ch) + char_gap
        if curw + w > max_w and cur:
            lines.append(cur); cur, curw = [], 0
        cur.append((ch, p, gidx)); curw += w; gidx += 1
    if cur: lines.append(cur)
    line_h = py_size + py_gap + zh_size + 28
    y = top
    for ln in lines:
        total = sum(cw(ch)+char_gap for ch, _, _ in ln) - char_gap
        x = cx - total//2
        for ch, p, idx in ln:
            w = cw(ch)
            shown = draw and (reveal_t is None or reveal_t[idx] <= t_now)
            if shown and p:
                pw = text_w(d, p, pf)
                d.text((x + (w-pw)//2, y), p, font=pf, fill=PINYIN)
            if shown:
                d.text((x, y + py_size + py_gap), ch, font=zf, fill=INK)
            x += w + char_gap
        y += line_h
    return len(lines) * line_h

def fit_zh_size(d, text, max_size, min_size=64, max_w=1640, char_gap=14):
    """Tu chon co chu Han lon nhat (<=max_size) de ca cau vua 1 dong (<=max_w).
       Cau ngan giu max_size; cau dai thu nho dan toi min_size."""
    flat = flatten(text)
    chars = [c for c, _, _ in flat]
    if not chars:
        return max_size
    size = max_size
    while size > min_size:
        zf = font("zh", size)
        total = sum(text_w(d, c, zf) + char_gap for c in chars) - char_gap
        if total <= max_w:
            break
        size -= 4
    return max(min_size, size)

TEXT_GLOW = False
def _apply_glow(im, overlay, color=(255,255,255), radius=14, boost=3.0, layers=4):
    """Phu quang sang mo (halo) tu chu tren 'overlay' xuong 'im' roi ve lai chu net.
       Tao 1 vung sang mem sau chu -> noi ro tren nen sang/nhieu chi tiet, KHONG lam mo ca anh."""
    a = overlay.split()[3].point(lambda p: min(255, int(p * boost)))
    glow = Image.composite(Image.new("RGBA", overlay.size, color + (255,)),
                           Image.new("RGBA", overlay.size, (0, 0, 0, 0)), a)
    glow = glow.filter(ImageFilter.GaussianBlur(radius))
    base = im.convert("RGBA")
    for _ in range(layers):             # chong nhieu lop -> quang dac, ro chu
        base.alpha_composite(glow)
    base.alpha_composite(overlay)       # chu net ben tren
    im.paste(base.convert("RGB"), (0, 0))

def wrap_text(d, text, fnt, max_w):
    """Cat van ban (theo tu) thanh nhieu dong sao cho moi dong <= max_w."""
    words = (text or "").split()
    if not words:
        return []
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if not cur or text_w(d, trial, fnt) <= max_w:
            cur = trial
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines

def draw_viet(d, text, top, fnt, line_gap=10):
    """Ve nghia Viet, canh giua, tu xuong dong neu dai > 90% chieu rong. Tra ve chieu cao."""
    lines = wrap_text(d, text, fnt, int(W * 0.9))
    lh = fnt.size + line_gap
    y = top
    for ln in lines:
        tw = text_w(d, ln, fnt)
        d.text(((W - tw) // 2, y), ln, font=fnt, fill=VIET)
        y += lh
    return max(1, len(lines)) * lh

def char_reveal_times(text, win_start, win_end):
    """Tra ve mang reveal_t (theo flat) — rai deu cac chu Han tren [win_start,win_end].
       Dau cau hien cung chu Han ngay truoc no."""
    flat = flatten(text)
    n = sum(1 for _, _, h in flat if h) or 1
    rt, last, k = [], win_start, 0
    for ch, p, h in flat:
        if h:
            t = win_start + (k / n) * (win_end - win_start)
            rt.append(t); last = t; k += 1
        else:
            rt.append(last)
    return rt

_bg_cache = {}
def _prep_bg(path):
    """Anh nguoi dung tai len -> phu kin 1920x1080 + phu mang mo mau theme
       de chu van doc ro. Co cache."""
    k = (path, tuple(VEIL_RGBA))
    if k in _bg_cache:
        return _bg_cache[k].copy()
    src = Image.open(path).convert("RGB")
    sr, tr = src.width / src.height, W / H
    if sr > tr:
        src = src.resize((int(H * sr), H))
    else:
        src = src.resize((W, int(W / sr)))
    x, y = (src.width - W) // 2, (src.height - H) // 2
    src = src.crop((x, y, x + W, y + H))
    if VEIL_RGBA[3] <= 0:                              # khong phu mau -> giu nguyen anh
        out = src
    else:
        veil = Image.new("RGBA", (W, H), tuple(VEIL_RGBA))
        out = Image.alpha_composite(src.convert("RGBA"), veil).convert("RGB")
    _bg_cache[k] = out
    return out.copy()

_BRAND_LOGO = os.path.join(_HERE, "brand", "logo_tr.png")
_logo_cache = {}
def brand_logo(h):
    """Logo thuong hieu (PNG trong suot) resize theo chieu cao h. None neu khong co file."""
    path = _BRAND_LOGO
    if not os.path.exists(path):
        return None
    key = (path, h)
    if key not in _logo_cache:
        im = Image.open(path).convert("RGBA")
        w = max(1, int(im.width * h / im.height))
        _logo_cache[key] = im.resize((w, h), Image.LANCZOS)
    return _logo_cache[key]

def base_slide(ctx, header=None):
    bgimg = ctx.get("bg_image")
    if bgimg and os.path.exists(bgimg):
        im = _prep_bg(bgimg)
    else:
        im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    if header is None:
        header = ctx.get("header") or f'BÀI {int(ctx["id"])} · {ctx["title"]}'
    hf = font("head", 44)
    # ve tung ky tu: chu Han dung font Han (KHONG tofu), Latin/Viet dung Lexend
    _hchars = [(ch, (font("zh", 44) if _is_cjk(ch) else hf)) for ch in header.upper()]
    tw = sum(text_w(d, ch, f) for ch, f in _hchars)
    _hx = (W - tw) // 2
    for ch, f in _hchars:
        d.text((_hx, 58), ch, font=f, fill=HEADER)
        _hx += text_w(d, ch, f)
    cy = 84
    d.line([(W-tw)//2-180, cy, (W-tw)//2-40, cy], fill=LINE, width=3)
    d.line([(W+tw)//2+40, cy, (W+tw)//2+180, cy], fill=LINE, width=3)
    # badge HSK goc duoi phai — chi hien khi nguoi dung dat @hsk (bai hoc co so)
    if ctx.get("hsk_explicit"):
        bt = ctx.get("hsk", "HSK1")
        bf = font("badge", 38)
        bw = text_w(d, bt, bf)
        d.rounded_rectangle([W-bw-150, H-95, W-60, H-35], radius=30, fill=BADGE)
        d.text((W-bw-105, H-88), bt, font=bf, fill=(255, 255, 255))
    # logo thuong hieu goc TREN-PHAI (nhan dien thuong hieu) — moi slide
    if ctx.get("brand_logo", True):
        lg = brand_logo(150)
        if lg:
            im.paste(lg, (W - lg.width - 45, 35), lg)
    # mascot dễ thương góc dưới-trái (bỏ qua nếu sẽ overlay chuyển động)
    if not ctx.get("_skip_mascot_in_slide"):
        draw_mascot(im, d, ctx)
    # thanh thong tin duoi (FB / Youtube / Zalo) — neu co
    info = ctx.get("infobar", "")
    if info:
        inf = font("sansb", 28)
        tw2 = text_w(d, info, inf)
        d.text(((W - tw2)//2, H - 50), info, font=inf, fill=SOFT)
    else:
        # watermark kenh (cạnh mascot) — theo tong mau theme
        d.text((345, H-92), ctx.get("channel", "Học Tiếng Trung"),
               font=font("sansb", 30), fill=SOFT)
    return im, d

def center_text_block(d, blocks, gap=30, top=None):
    sizes = []
    for t, fk, sz, col in blocks:
        bb = d.textbbox((0, 0), t, font=font(fk, sz))
        sizes.append((bb[2]-bb[0], bb[3]-bb[1], bb[1]))
    total = sum(s[1] for s in sizes) + gap*(len(blocks)-1)
    y = (H-total)//2 if top is None else top
    for (t, fk, sz, col), (tw, th, oy) in zip(blocks, sizes):
        d.text(((W-tw)//2, y-oy), t, font=font(fk, sz), fill=col)
        y += th + gap

# ---------- LAYOUT PODCAST (Chinese Daily style) ----------
# Vung noi dung chinh (khung do): nguoi dung tu lam header (nguoi dan + tranh) o nen.
PODCAST_BOX = (24, 482, W - 24, 1046)        # x0,y0,x1,y1
PC_PINYIN = (105, 110, 115)                  # pinyin xam
PC_VIET   = (38, 110, 78)                    # nghia (xanh la dam, giong mau dich mau)
PC_BORDER = (193, 142, 90)                   # vien panel (nau vang co dien)
PC_CORNER = (193, 142, 90)                   # hoa van goc

# Tone-color (ho tro hoc): pinyin to mau theo thanh dieu
_TONE_MARKS = {
    'āēīōūǖ': 1, 'áéíóúǘ': 2, 'ǎěǐǒǔǚ': 3, 'àèìòùǜ': 4,
}
TONE_COLORS = {1: (208, 38, 46), 2: (224, 142, 30), 3: (46, 139, 76),
               4: (40, 96, 196), 0: (105, 110, 115)}
def _tone_of(syl):
    for ch in syl:
        for marks, t in _TONE_MARKS.items():
            if ch in marks:
                return t
    return 0

def _cover_bg(path):
    """Anh nen nguoi dung -> phu kin 1920x1080 (giu nguyen mau, KHONG veil)."""
    src = Image.open(path).convert("RGB")
    sr, tr = src.width / src.height, W / H
    if sr > tr:
        src = src.resize((int(H * sr), H))
    else:
        src = src.resize((W, int(W / sr)))
    x, y = (src.width - W) // 2, (src.height - H) // 2
    return src.crop((x, y, x + W, y + H))

_CLOSERS = "，。、！？；：）】》」』”’%…"      # dau cau dong: khong de dung dau dong

def _is_cjk(ch):
    """Chu Han hoac dau cau CJK (toan-rong) -> dung font Han; con lai (Latin/Viet) -> font Latin."""
    o = ord(ch)
    return has_hanzi(ch) or 0x3000 <= o <= 0x303F or 0xFF00 <= o <= 0xFFEF

def _charfont(ch, size):
    """Font cho 1 ky tu: CJK -> Kaiti; Latin/Viet -> Lexend (co dau tieng Viet, KHONG tofu)."""
    return font("zh", size) if _is_cjk(ch) else font("viet", int(size * 0.86))

def _hanzi_wrap_lines(d, text, size, max_w, char_gap=8):
    """Chia thanh cac dong <= max_w (dung font dung cho tung ky tu); dau cau dong khong dung dau dong."""
    cw = lambda ch: text_w(d, ch, _charfont(ch, size))
    lines, cur, curw, gi = [], [], 0, 0
    for ch, p, h in flatten(text):
        w = cw(ch) + char_gap
        if curw + w > max_w and cur and ch not in _CLOSERS:
            lines.append(cur); cur, curw = [], 0
        cur.append((ch, gi)); curw += w; gi += 1
    if cur:
        lines.append(cur)
    return lines

def _fit_hanzi_box(d, text, max_w, max_h, hi=132, lo=72, line_gap=22):
    """Chon co chu Han LON NHAT sao cho ngat dong vua chieu cao max_h (chu to, 2-3 dong)."""
    size = hi
    while size > lo:
        n = len(_hanzi_wrap_lines(d, text, size, max_w))
        if n * (size + line_gap) <= max_h:
            return size
        size -= 4
    return lo

def _draw_hanzi_wrapped(d, text, cx, top, size, max_w,
                        char_gap=8, line_gap=22, reveal_t=None, t_now=BIG, color=INK):
    """Ve chu Han to (KHONG pinyin tren chu), tu xuong dong, canh giua. Tra ve chieu cao."""
    lines = _hanzi_wrap_lines(d, text, size, max_w, char_gap)
    cw = lambda ch: text_w(d, ch, _charfont(ch, size))
    lh = size + line_gap
    y = top
    for ln in lines:
        total = sum(cw(ch) + char_gap for ch, _ in ln) - char_gap
        x = cx - total // 2
        for ch, idx in ln:
            if reveal_t is None or reveal_t[idx] <= t_now:
                # canh chan day chu Han va chu Latin (Latin nho hon -> ha xuong chut)
                f = _charfont(ch, size)
                oy = 0 if _is_cjk(ch) else int(size * 0.12)
                d.text((x, y + oy), ch, font=f, fill=color)
            x += cw(ch) + char_gap
        y += lh
    return len(lines) * lh

def _draw_pinyin_line(d, text, cx, y, max_w, size=46, gap=10, tone=False, neutral=None):
    """Ve dong pinyin ca cau, canh giua. Dau cau (，。"") ve bang font Han de KHONG bi tofu.
       tone=True: to mau tung am tiet theo thanh dieu. neutral: mau khi KHONG to thanh dieu."""
    neutral = neutral or PC_PINYIN
    toks = []
    for ch, p, h in flatten(text):
        if ch.strip() == "":
            continue
        if h and p:
            toks.append((p, False))            # am tiet pinyin -> font Latin
        else:
            toks.append((ch, _is_cjk(ch)))     # dau cau CJK -> font Han; Latin/Viet -> font Latin
    while size > 26:
        pf = font("pinyin", size); zf = font("zh", int(size * 0.92))
        ws = [(t, isc, text_w(d, t, zf if isc else pf)) for t, isc in toks]
        total = sum(w for *_, w in ws) + gap * (max(0, len(ws) - 1))
        if total <= max_w:
            break
        size -= 2
    x = cx - total // 2
    for t, isc, w in ws:
        f = zf if isc else pf
        col = neutral if (isc or not tone) else TONE_COLORS[_tone_of(t)]
        d.text((x, y), t, font=f, fill=col)
        x += w + gap
    return size + 12

def _ornament_corners(d, box, size=34, inset=18, color=PC_CORNER, w=3):
    """Ve 4 goc trang tri kieu khung co dien (L-bracket) cho panel."""
    x0, y0, x1, y1 = box
    x0 += inset; y0 += inset; x1 -= inset; y1 -= inset
    for (cx, cy, sx, sy) in [(x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)]:
        d.line([(cx, cy), (cx + sx * size, cy)], fill=color, width=w)
        d.line([(cx, cy), (cx, cy + sy * size)], fill=color, width=w)

def render_podcast_main(seg, ctx, path, reveal_t=None, t_now=BIG):
    """Layout podcast (Chinese Daily): chi ve KHOI NOI DUNG CHINH (Han to + pinyin + Viet)
       trong khung do + lop nen mo de chu ro. Nen (nguoi dan + tranh) lay tu ctx['bg_image']."""
    bgimg = ctx.get("bg_image")
    if bgimg and os.path.exists(bgimg):
        im = _cover_bg(bgimg)                 # nen nguoi dung (nguoi dan + tranh)
    else:
        im = Image.new("RGB", (W, H), BG)     # chua upload -> dung nen pastel theo theme
    im = im.convert("RGBA")
    # lop nen mo (readability) — mep MO DAN (feather) de hoa vao tranh, khong co vet doc
    alpha = int(ctx.get("panel_alpha", 150))
    x0, y0, x1, y1 = PODCAST_BOX
    if alpha > 0:
        mask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(mask).rounded_rectangle([x0, y0, x1, y1], radius=26, fill=alpha)
        mask = mask.filter(ImageFilter.GaussianBlur(16))     # mo mep -> khong vet cung
        panel_c = hex2rgb(ctx.get("panel_color")) or (255, 253, 248)
        white = Image.new("RGBA", (W, H), tuple(panel_c) + (255,))
        im = Image.composite(white, im, mask)
    # vien co dien + goc trang tri (net sac)
    if ctx.get("podcast_frame", True):
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        od.rounded_rectangle([x0, y0, x1, y1], radius=26, outline=PC_BORDER + (210,), width=3)
        od.rounded_rectangle([x0 + 10, y0 + 10, x1 - 10, y1 - 10],
                             radius=20, outline=PC_BORDER + (110,), width=2)
        im = Image.alpha_composite(im, ov)
    im = im.convert("RGB")
    d = ImageDraw.Draw(im)
    if ctx.get("podcast_frame", True):
        _ornament_corners(d, PODCAST_BOX, color=PC_CORNER)

    text = seg.get("hanzi", "")
    viet = seg.get("viet", "")
    x0, y0, x1, y1 = PODCAST_BOX
    cx = W // 2
    box_w = x1 - x0
    max_w = int(box_w * 0.90)
    # mau tuy chinh tung dong (nguoi dung chon trong app; rong = mac dinh)
    ink_c = hex2rgb(ctx.get("zh_color")) or INK
    py_c = hex2rgb(ctx.get("py_color")) or PC_PINYIN
    vi_c = hex2rgb(ctx.get("vi_color")) or PC_VIET

    # --- chip ten nguoi noi (hoi thoai nhieu giong) ---
    sp = seg.get("_sp")
    spcol = (ctx.get("_speaker_colors") or {}).get(sp) if sp else None
    chip_h = 58 if spcol else 0

    gap1, gap2 = 40, 30
    # --- uoc luong chieu cao pinyin + viet de chua khong gian cho chu Han ---
    pf = font("pinyin", 46)
    pin_h = 46 + 12
    vf = font("viet", 56)
    vwraps = wrap_text(d, viet, vf, int(box_w * 0.88)) if viet else []
    vie_h = len(vwraps) * (56 + 12)
    reserved = chip_h + (gap1 + pin_h) + (gap2 + vie_h if vie_h else 0) + 40
    # --- chu Han TO, ngat dong vua khung con lai ---
    zsize = _fit_hanzi_box(d, text, max_w, (y1 - y0) - reserved, hi=132, lo=78)
    han_h = len(_hanzi_wrap_lines(d, text, zsize, max_w)) * (zsize + 22)

    total = chip_h + han_h + (gap1 + pin_h) + (gap2 + vie_h if vie_h else 0)
    y = y0 + ((y1 - y0) - total) // 2

    # --- ve ---
    if spcol:
        label = str(sp)
        has_cjk = any(has_hanzi(c) for c in label)
        cf = font("zh", 32) if has_cjk else font("badge", 32)   # ten Han -> font Han (khong tofu)
        lw = text_w(d, label, cf)
        cw2 = lw + 56
        d.rounded_rectangle([cx - cw2 // 2, y, cx + cw2 // 2, y + 46], radius=23, fill=spcol)
        d.text((cx - lw // 2, y + (2 if has_cjk else 6)), label, font=cf, fill=(255, 255, 255))
        y += chip_h
    tone = bool(ctx.get("tone_colors", True))
    y += _draw_hanzi_wrapped(d, text, cx, y, zsize, max_w, reveal_t=reveal_t, t_now=t_now,
                             color=ink_c)
    y += gap1
    y += _draw_pinyin_line(d, text, cx, y, int(box_w * 0.94), tone=tone, neutral=py_c)
    if vie_h:
        # gach trang tri mảnh + cham ngoc giua Han/pinyin va nghia Viet
        dy = y + gap2 // 2
        d.line([(cx - 70, dy), (cx - 14, dy)], fill=PC_BORDER, width=2)
        d.line([(cx + 14, dy), (cx + 70, dy)], fill=PC_BORDER, width=2)
        d.ellipse([cx - 4, dy - 4, cx + 4, dy + 4], fill=PC_BORDER)
        y += gap2 + 8
        for ln in vwraps:
            tw = text_w(d, ln, vf)
            d.text((cx - tw // 2, y), ln, font=vf, fill=vi_c); y += 56 + 12

    im.save(path)
    return im

# ---------- DISPATCH ----------
def render_slide(seg, ctx, path, t_now=BIG, reveal_t=None,
                 show_viet=True, n_visible=BIG):
    """t_now/reveal_t: hieu ung chu hien dan (vocab/sentence/practice_a).
       n_visible: so dong hoi thoai da hien (dialogue)."""
    apply_theme(ctx.get("theme", "pink"))
    t = seg["type"]
    # Layout podcast: chi ve khoi noi dung chinh (Han+pinyin+Viet) tren nen nguoi dung
    if ctx.get("podcast_layout") and t in ("sentence", "vocab", "practice_a"):
        # v2 (bien the tham my Trung Hoa, render 2x): mac dinh; "classic" = ban cu
        if (ctx.get("podcast_variant") or "inkwash") == "classic":
            render_podcast_main(seg, ctx, path, reveal_t=reveal_t, t_now=t_now)
        else:
            import style_podcast
            style_podcast.render(seg, ctx, path, reveal_t=reveal_t, t_now=t_now)
        return
    # The chuyen muc trong podcast layout: dong bo tham my voi bien the da chon
    if ctx.get("podcast_layout") and t == "section" \
            and (ctx.get("podcast_variant") or "inkwash") != "classic":
        import style_podcast
        style_podcast.render_section(seg, ctx, path)
        return

    if t == "title":
        # header: uu tien @header nguoi dung; neu khong moi dung mac dinh "CHINESE · HSK"
        im, d = base_slide(ctx, header=(ctx.get("header") or f'CHINESE · {ctx["hsk"]}'))
        h = py_hanzi(d, ctx["hanzi_title"], W//2, 0, zh_size=230, py_size=64, draw=False)
        top = (H-h)//2 - 70
        # chi hien dong "HSK · BÀI n" khi nguoi dung THUC SU dat @hsk (bai hoc co so)
        if ctx.get("hsk_explicit"):
            center_text_block(d, [(f'{ctx["hsk"]}  ·  BÀI {int(ctx["id"])}', "sansb", 56, GOLD)],
                              top=top-90)
        py_hanzi(d, ctx["hanzi_title"], W//2, top, zh_size=230, py_size=64)
        vf = font("viet", 76); tw = text_w(d, ctx["title"], vf)
        d.text(((W-tw)//2, top+h+30), ctx["title"], font=vf, fill=VIET)

    elif t == "objectives":
        im, d = base_slide(ctx)
        blocks = [("HÔM NAY BẠN SẼ HỌC", "sansb", 72, GOLD)]
        for ln in seg["lines"]:
            blocks.append(("•  " + ln, "viet", 60, INK))
        center_text_block(d, blocks, gap=34)

    elif t == "section":
        im, d = base_slide(ctx)
        lbl = seg["label"]; lf = font("viet", 128)
        tw = text_w(d, lbl, lf)
        d.text(((W-tw)//2, (H-128)//2 - 10), lbl, font=lf, fill=VIET)
        cx = W//2
        d.rounded_rectangle([cx-tw//2, (H+128)//2+30, cx+tw//2, (H+128)//2+40],
                            radius=5, fill=BADGE)

    elif t in ("vocab", "practice_a"):
        im, d = base_slide(ctx)
        zh, py, vgap = 240, 66, 40
        h = py_hanzi(d, seg["hanzi"], W//2, 0, zh_size=zh, py_size=py, draw=False)
        vf = font("viet", 70)
        vh = len(wrap_text(d, seg.get("viet", ""), vf, int(W*0.9))) * (vf.size+10) if show_viet else 0
        top = (H - (h + vgap + vh))//2 - 20
        td, ov = d, None
        if TEXT_GLOW:
            ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); td = ImageDraw.Draw(ov)
        py_hanzi(td, seg["hanzi"], W//2, top, zh_size=zh, py_size=py,
                 reveal_t=reveal_t, t_now=t_now)
        if show_viet:
            draw_viet(td, seg["viet"], top+h+vgap, vf)
        if ov is not None:
            _apply_glow(im, ov)

    elif t == "sentence":
        im, d = base_slide(ctx)
        # co DONG NHAT toan bai (tinh san trong build) -> khong nhay chu;
        # neu render le (khong qua build) thi tu co theo cau
        zh = ctx.get("zh_size") or fit_zh_size(d, seg["hanzi"], 118)
        py, vgap = max(38, int(zh * 0.46)), 36
        h = py_hanzi(d, seg["hanzi"], W//2, 0, zh_size=zh, py_size=py, draw=False)
        vf = font("viet", 60)
        vh = len(wrap_text(d, seg.get("viet", ""), vf, int(W*0.9))) * (vf.size+10) if show_viet else 0
        top = (H - (h + vgap + vh))//2 - 20
        td, ov = d, None
        if TEXT_GLOW:
            ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); td = ImageDraw.Draw(ov)
        py_hanzi(td, seg["hanzi"], W//2, top, zh_size=zh, py_size=py,
                 reveal_t=reveal_t, t_now=t_now)
        if show_viet:
            draw_viet(td, seg["viet"], top+h+vgap, vf)
        if ov is not None:
            _apply_glow(im, ov)

    elif t == "dialogue":
        im, d = base_slide(ctx)
        rows = seg["rows"]
        zh_s, py_s, vi_s = 52, 24, 30
        gap_py, gap_vi, gap_turn = 8, 4, 20
        turn_h = py_s + gap_py + zh_s + gap_vi + vi_s + gap_turn
        total = turn_h * len(rows)
        y = (H - total)//2 + 8        # vua khung, khong dung header
        vf = font("viet", vi_s)
        for ri, r in enumerate(rows):
            if ri >= n_visible:        # dong chua toi luot -> chua hien
                y += turn_h; continue
            sp_lbl = str(r.get("sp", ""))
            # nhan ten: ten Han -> font Han (khong tofu); A/B/Host -> font Latin
            lf = font("zh", 42) if any(has_hanzi(c) for c in sp_lbl) else font("sansb", 46)
            d.text((175, y + py_s), sp_lbl + " :", font=lf, fill=BADGE)
            py_hanzi(d, r["hanzi"], W//2 + 40, y, zh_size=zh_s, py_size=py_s,
                     char_gap=8, py_gap=gap_py)
            sub = r["viet"]
            tw = text_w(d, sub, vf)
            d.text((W//2 + 40 - tw//2, y + py_s + gap_py + zh_s + gap_vi),
                   sub, font=vf, fill=VIET)
            y += turn_h

    elif t == "practice_q":
        im, d = base_slide(ctx)
        center_text_block(d, [
            ("LUYỆN TẬP", "sansb", 76, GOLD),
            (seg["question"], "viet", 66, INK),
            ("Bạn thử trả lời nhé...", "viet", 50, SOFT),
        ], gap=44)

    elif t == "outro":
        im, d = base_slide(ctx, header=f'CẢM ƠN BẠN ĐÃ XEM')
        n = int(ctx["id"])
        h = py_hanzi(d, "再见", W//2, 0, zh_size=180, py_size=52, draw=False)
        top = (H-h)//2 + 40
        center_text_block(d, [
            (f"Bạn đã học xong Bài {n}!", "viet", 72, INK),
            (f"LIKE & SUBSCRIBE để học tiếp Bài {n+1}", "sansb", 50, GOLD),
        ], top=top-200)
        py_hanzi(d, "再见", W//2, top, zh_size=180, py_size=52)
    else:
        im, d = base_slide(ctx)

    im.save(path)

# ---------- THUMBNAIL (anh bia YouTube 1280x720) ----------
def _thumb_blob(size, color, alpha):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0)); dd = ImageDraw.Draw(im)
    dd.ellipse([0, 0, size, size], fill=color + (alpha,))
    return im.filter(ImageFilter.GaussianBlur(size // 5))

_AI_THUMB_CACHE = os.path.join(_HERE, "assets", "ai_thumb")

def _ai_thumb_bg(prompt, tw, th):
    """Tai nen AI 16:9 tu Pollinations (cache theo prompt). Nem loi neu fail."""
    import hashlib, urllib.request, urllib.parse
    os.makedirs(_AI_THUMB_CACHE, exist_ok=True)
    key = hashlib.md5(f"{prompt}|{tw}x{th}".encode("utf-8")).hexdigest()
    out = os.path.join(_AI_THUMB_CACHE, key + ".jpg")
    if not os.path.exists(out):
        url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt)
               + f"?width={tw}&height={th}&nologo=true")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=120).read()
        with open(out, "wb") as f:
            f.write(data)
    im = Image.open(out).convert("RGB")
    if im.size != (tw, th):
        im = im.resize((tw, th), Image.LANCZOS)
    return im

def _outline_text(d, xy, text, fnt, fill, outline=(20, 20, 24), w=4):
    x, y = xy
    for dx in range(-w, w + 1, max(1, w // 2)):
        for dy in range(-w, w + 1, max(1, w // 2)):
            if dx or dy:
                d.text((x + dx, y + dy), text, font=fnt, fill=outline)
    d.text((x, y), text, font=fnt, fill=fill)

def make_thumbnail_ai(ctx, path):
    """Anh bia v2: nen AI theo chu de + hook TIENG VIET LON (nguoi xem chua doc duoc
       chu Han -> hook Viet phai la thu to nhat), chu Han nho lam trang tri,
       badge ngay/series de nhan dien binge-watch."""
    from seo import split_title
    TW, TH = 1280, 720
    han, viet = split_title(ctx.get("title", ""))
    hook = (ctx.get("thumb_hook") or viet or ctx.get("title", "")).strip()
    prompt = (ctx.get("thumb_prompt") or ctx.get("image_prompt") or "").strip()
    if not prompt:
        raise ValueError("khong co image_prompt cho nen AI")
    full_prompt = (prompt + ", beautiful cinematic illustration, warm cozy light, "
                   "soft colors, chinese aesthetic, no text, no words, no letters")
    im = _ai_thumb_bg(full_prompt, TW, TH)
    # lop toi gradient ben trai -> chu noi tren moi loai nen
    ov = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    for x in range(TW):
        a = int(190 * max(0.0, 1.0 - x / (TW * 0.72)))
        od.line([(x, 0), (x, TH)], fill=(15, 15, 22, a))
    for y in range(TH - 220, TH):                       # them dai toi duoi day
        a = int(150 * (y - (TH - 220)) / 220)
        od.line([(0, y), (TW, y)], fill=(15, 15, 22, a))
    im = Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")
    d = ImageDraw.Draw(im)
    # badge ngay/series (vd "NGÀY 3/7") — goc tren trai, vang noi bat
    badge = (ctx.get("thumb_badge") or "").strip()
    if badge:
        bf = font("badge", 40)
        bw = text_w(d, badge, bf)
        d.rounded_rectangle([46, 42, 46 + bw + 56, 42 + 66], radius=16, fill=(255, 200, 40))
        d.text((74, 54), badge, font=bf, fill=(40, 30, 10))
    # hook tieng Viet — thu TO NHAT tren anh
    hf = font("viet", 104)
    lines = wrap_text(d, hook, hf, int(TW * 0.62))
    if len(lines) > 3:
        hf = font("viet", 84)
        lines = wrap_text(d, hook, hf, int(TW * 0.62))
    y = max(150, (TH - len(lines) * (hf.size + 18) - 90) // 2)
    for ln in lines:
        _outline_text(d, (64, y), ln, hf, fill=(255, 255, 255), w=5)
        y += hf.size + 18
    # chu Han nho ben duoi (trang tri + tin hieu "hoc tieng Trung")
    if han:
        zf = font("zh", 54)
        _outline_text(d, (66, y + 14), han, zf, fill=(255, 210, 90), w=3)
    # tagline kenh duoi day
    d.text((66, TH - 58), (ctx.get("channel", "") + "  ·  Luyện nghe tiếng Trung có phụ đề").strip(" ·"),
           font=font("sansb", 28), fill=(235, 235, 235))
    lg = brand_logo(120)
    if lg:
        im.paste(lg, (TW - lg.width - 40, TH - lg.height - 34), lg)
    im.save(path, "JPEG", quality=92)
    return path

def make_thumbnail(ctx, path):
    """Uu tien anh bia AI (hook Viet lon); loi/thieu prompt -> fallback ban pastel."""
    if ctx.get("thumb_ai", True):
        try:
            return make_thumbnail_ai(ctx, path)
        except Exception as e:
            print("  [thumbnail AI] loi, dung ban pastel:", e)
    return make_thumbnail_pastel(ctx, path)

def make_thumbnail_pastel(ctx, path):
    """Anh bia dep: nen gradient am + dom trang tri + cau Viet (cam) + chu Han + pinyin + logo."""
    from seo import split_title, pinyin_of
    TW, TH = 1280, 720
    ORANGE = (232, 98, 46); NAVY = (30, 58, 98); GRAY = (138, 130, 122)
    han, viet = split_title(ctx.get("title", ""))
    viet = (viet or ctx.get("title", "")).strip()
    # nen gradient kem -> dao nhe
    im = Image.new("RGB", (TW, TH)); px = im.load()
    for y in range(TH):
        f = y / TH
        c = (int(253 - 6*f), int(248 - 12*f), int(240 - 18*f))
        for x in range(TW):
            px[x, y] = c
    d = ImageDraw.Draw(im)
    # vien tren + duoi mau cam
    d.rectangle([0, 0, TW, 10], fill=ORANGE)
    d.rectangle([0, TH-12, TW, TH], fill=ORANGE)
    # badge PODCAST
    bf = font("badge", 34); bt = "PODCAST"; bw = text_w(d, bt, bf)
    d.rounded_rectangle([52, 46, 52+bw+98, 46+60], radius=30, fill=ORANGE)
    d.text((118, 56), bt, font=bf, fill=(255, 255, 255))
    ef = emoji_font(40); d.text((70, 54), "🎙️", font=ef, embedded_color=True)
    # logo goc tren phai
    lg = brand_logo(158)
    if lg: im.paste(lg, (TW-lg.width-46, 34), lg)
    # khoi text can giua theo chieu doc
    vf = font("viet", 82); vlines = wrap_text(d, viet, vf, TW-180)
    if len(vlines) > 2:
        vf = font("viet", 62); vlines = wrap_text(d, viet, vf, TW-150)
    zf = font("zh", 76)
    if han and text_w(d, han, zf) > TW-150:
        zf = font("zh", 58)
    pf = font("pinyin", 36)
    block_h = len(vlines)*(vf.size+14) + (40 + zf.size + 12 + pf.size if han else 0)
    y = max(170, (TH - block_h)//2 + 8)
    # cau tieng Viet (cam, dam) — co bong nhe cho noi
    for ln in vlines:
        tw = text_w(d, ln, vf)
        d.text(((TW-tw)//2+2, y+2), ln, font=vf, fill=(210, 180, 150))  # bong
        d.text(((TW-tw)//2, y), ln, font=vf, fill=ORANGE)
        y += vf.size + 14
    if han:
        y += 26
        # gach ngan trang tri giua Viet va Han
        d.rounded_rectangle([TW//2-46, y-18, TW//2+46, y-13], radius=3, fill=(228, 196, 150))
        tw = text_w(d, han, zf); d.text(((TW-tw)//2, y), han, font=zf, fill=NAVY)
        py = pinyin_of(han); ptw = text_w(d, py, pf)
        d.text(((TW-ptw)//2, y+zf.size+10), py, font=pf, fill=GRAY)
    # tagline duoi (emoji ve rieng vi Lexend khong co emoji)
    d.text((104, TH-62), ctx.get("channel", "Lạc Học Đường") + " · Luyện nghe tiếng Trung mỗi ngày",
           font=font("sansb", 30), fill=NAVY)
    d.text((56, TH-66), "🎧", font=emoji_font(36), embedded_color=True)
    im.save(path, "JPEG", quality=92)
    return path

if __name__ == "__main__":
    ctx = {"id": "01", "hsk": "HSK1", "title": "CHÀO HỎI",
           "hanzi_title": "你好", "channel": "Học Tiếng Trung"}
    for seg, name in [
        ({"type": "title"}, "title"),
        ({"type": "vocab", "hanzi": "你好", "pinyin": "nǐ hǎo", "viet": "Xin chào"}, "vocab"),
        ({"type": "sentence", "hanzi": "我很好，谢谢！", "pinyin": "", "viet": "Tôi khỏe, cảm ơn!"}, "sentence"),
        ({"type": "dialogue", "rows": [
            {"sp": "A", "hanzi": "你好吗？", "pinyin": "", "viet": "Bạn khỏe không?"},
            {"sp": "B", "hanzi": "我很好，谢谢！", "pinyin": "", "viet": "Tôi khỏe, cảm ơn!"},
            {"sp": "A", "hanzi": "再见！", "pinyin": "", "viet": "Tạm biệt!"},
        ]}, "dialogue"),
        ({"type": "outro"}, "outro"),
    ]:
        render_slide(seg, ctx, f"ref/_p_{name}.png")
    print("done")
