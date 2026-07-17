# -*- coding: utf-8 -*-
"""Layout PODCAST v2 — bien the tham my Trung Hoa (thuy mac / quoc phong).
   Nang cap so voi render_podcast_main (style_pastel):
   - Render SIEU LAY MAU 2x roi thu nho LANCZOS -> chu Han sac net ro ret o 1080p.
   - Nhieu BIEN THE layout chon qua ctx['podcast_variant']:
       inkwash  : giay xuyen chi + vien kep + goc L + trien do (mac dinh)
       scroll   : cuon thu ngang co truc go 2 dau
       album    : trang sach co (kinh tuyen do nhat 2 ben)
       minimal  : dien anh toi gian — chi scrim gradient duoi, khong khung
       night    : da thoai — panel muc den, chu nga vang (cho truyen dem)
   - An trien do (con dau) khac ten kenh: ctx['seal_text'] (2-4 chu Han).
   - Do bong mem cho chu Han -> noi khoi tren nen tranh.
   - Texture giay nhe (noise) tren panel -> chat giay that.
   Giu nguyen signature render(seg, ctx, path, reveal_t, t_now) nhu render_podcast_main.
"""
import os
from PIL import Image, ImageDraw, ImageFilter

import style_pastel as SP     # dung lai font/flatten/tone/wrap cua bo pastel

W, H = 1920, 1080
S = 2                          # he so sieu lay mau (2x)
BIG = 1e9

# ---------- BANG BIEN THE ----------
# box: (x0,y0,x1,y1) toa do 1x. dark: panel toi -> chu sang.
VARIANTS = {
    "inkwash": dict(
        box=(24, 482, W - 24, 1046), dark=False,
        panel=(255, 253, 246), alpha=165,
        ink=(44, 40, 38), pinyin=(122, 116, 108), viet=(38, 110, 78),
        border=(172, 122, 72), frame="double", corners=True,
        seal=True, rollers=False, redrules=False, scrim=False,
        divider="dot", texture=True),
    "scroll": dict(
        box=(96, 470, W - 96, 1050), dark=False,
        panel=(250, 244, 230), alpha=210,
        ink=(52, 42, 34), pinyin=(128, 116, 100), viet=(146, 84, 30),
        border=(120, 82, 46), frame="single", corners=False,
        seal=True, rollers=True, redrules=False, scrim=False,
        divider="brush", texture=True),
    "album": dict(
        box=(150, 460, W - 150, 1052), dark=False,
        panel=(248, 241, 224), alpha=228,
        ink=(50, 44, 40), pinyin=(130, 108, 92), viet=(60, 84, 130),
        border=(178, 88, 66), frame="single", corners=False,
        seal=True, rollers=False, redrules=True, scrim=False,
        divider="dot", texture=True),
    "minimal": dict(
        box=(120, 520, W - 120, 1040), dark=True,
        panel=(16, 16, 22), alpha=0,
        ink=(250, 248, 244), pinyin=(196, 200, 210), viet=(255, 214, 130),
        border=(210, 180, 120), frame="none", corners=False,
        seal=False, rollers=False, redrules=False, scrim=True,
        divider="line", texture=False),
    "night": dict(
        box=(60, 492, W - 60, 1044), dark=True,
        panel=(20, 22, 32), alpha=200,
        ink=(240, 234, 216), pinyin=(150, 156, 172), viet=(232, 190, 100),
        border=(150, 128, 84), frame="double", corners=True,
        seal=True, rollers=False, redrules=False, scrim=False,
        divider="dot", texture=False),
    # ---- NHOM "FREE" (khong khung/panel — chu ve TRUC TIEP tren tranh, kieu Chinese Daily):
    # ruby=True: pinyin tren TUNG chu Han. halo: quang sang sau chu de doc ro tren tranh.
    "daily": dict(
        free=True, anchor="mid", dark=False,
        ink=(46, 40, 36), pinyin=(96, 88, 78), viet=(178, 44, 38),
        border=(172, 122, 72), seal=True, halo=(255, 255, 255),
        ruby=True, viet_style="band", dashes=True, wave="top"),
    "flat": dict(
        free=True, anchor="top", dark=True,
        ink=(245, 243, 238), pinyin=(205, 205, 215), viet=(235, 205, 120),
        border=(150, 128, 84), seal=False, halo=(12, 10, 28),
        ruby=True, viet_style="inline", dashes=False, wave="top",
        bgfill=(76, 68, 128)),
    "clean": dict(
        free=True, anchor="bottom", dark=False,
        ink=(34, 34, 38), pinyin=(90, 94, 102), viet=(112, 118, 128),
        border=(184, 184, 192), seal=False, halo=(255, 255, 255),
        ruby=True, viet_style="inline", dashes=False, wave="top", band=True),
    "top": dict(
        free=True, anchor="top", dark=False,
        ink=(50, 40, 32), pinyin=(110, 96, 80), viet=(196, 98, 28),
        border=(172, 122, 72), seal=True, halo=(255, 250, 240),
        ruby=True, viet_style="inline", dashes=False, wave="mid"),
    # ---- DOT 3: bien the le hoi / hien dai (nhieu mau, "xinh" hon) ----
    "lantern": dict(   # den long do-vang (le hoi, Tet)
        box=(70, 470, W - 70, 1048), dark=True,
        panel=(148, 26, 24), alpha=240,
        ink=(255, 244, 214), pinyin=(255, 200, 130), viet=(255, 224, 150),
        border=(222, 178, 76), frame="double", corners=True,
        seal=True, rollers=False, redrules=False, scrim=False,
        divider="dot", texture=True, meander=True, wave="top"),
    "porcelain": dict(  # su Thanh Hoa (xanh-trang co dien, sang trong)
        box=(80, 468, W - 80, 1050), dark=False,
        panel=(250, 252, 254), alpha=242,
        ink=(28, 46, 92), pinyin=(108, 128, 170), viet=(30, 84, 160),
        border=(46, 84, 160), frame="double", corners=False,
        seal=True, rollers=False, redrules=False, scrim=False,
        divider="dot", texture=False, meander=True, wave="top"),
    "board": dict(      # bang phan hoc duong (chalkboard am cung)
        box=(56, 462, W - 56, 1052), dark=True,
        panel=(38, 70, 58), alpha=248,
        ink=(248, 249, 244), pinyin=(255, 224, 130), viet=(255, 190, 200),
        border=(235, 238, 230), frame="chalk", corners=False,
        seal=False, rollers=False, redrules=False, scrim=False,
        divider="line", texture=True, texture_col=(235, 238, 230), wave="top"),
    "card": dict(       # the hoc hien dai (kieu the tu vung xiaohongshu)
        box=(130, 470, W - 130, 1040), dark=False,
        panel=(255, 255, 255), alpha=255,
        ink=(42, 46, 56), pinyin=(122, 108, 210), viet=(235, 87, 87),
        border=(235, 87, 87), frame="none", corners=False,
        seal=False, rollers=False, redrules=False, scrim=False,
        divider="line", texture=False, accentbar=True, shadow=True, wave="top"),
    "song": dict(       # Tong van (宋韵) — xanh tra tram + kim, sang trong ban dem
        box=(90, 470, W - 90, 1048), dark=True,
        panel=(43, 65, 75), alpha=246,
        ink=(242, 230, 200), pinyin=(158, 203, 191), viet=(196, 206, 202),
        border=(212, 175, 106), frame="double", corners=True,
        seal=True, rollers=False, redrules=False, scrim=False,
        divider="dot", texture=False, bgfill=(34, 52, 60), wave="top"),
    "bamboo": dict(     # the tre (竹简) — bo thanh tre co thu
        box=(170, 466, W - 170, 1046), dark=False,
        panel=(211, 183, 135), alpha=255,
        ink=(47, 32, 19), pinyin=(122, 59, 46), viet=(92, 64, 51),
        border=(90, 63, 42), frame="none", corners=False,
        seal=True, rollers=False, redrules=False, scrim=False,
        divider="brush", texture=True, slats=True, bgfill=(62, 47, 35), wave="top"),
    "paper": dict(      # vo ke o (study-with-me) — giay ke + highlight + bang washi
        box=(120, 466, W - 120, 1042), dark=False,
        panel=(251, 248, 241), alpha=255,
        ink=(55, 53, 47), pinyin=(192, 90, 69), viet=(122, 116, 106),
        border=(210, 200, 182), frame="none", corners=False,
        seal=False, rollers=False, redrules=False, scrim=False,
        divider="line", texture=False, grid=True, washi=True,
        highlight=(255, 224, 138), shadow=True, wave="top"),
}

SEAL_RED = (186, 48, 38)

# tone-color pinyin: ban SANG (nen giay) & ban DEM (panel toi, mau tuoi sang hon)
TONE_LIGHT = {1: (208, 38, 46), 2: (224, 142, 30), 3: (46, 139, 76),
              4: (40, 96, 196), 0: (122, 116, 108)}
TONE_DARK  = {1: (255, 118, 108), 2: (255, 186, 92), 3: (118, 214, 148),
              4: (128, 176, 255), 0: (170, 176, 190)}

# mau chip nguoi noi (sang / toi)
CHIP_LIGHT = [(40, 96, 196), (192, 57, 110), (203, 118, 20), (46, 139, 76), (120, 80, 180)]
CHIP_DARK  = [(96, 150, 245), (238, 116, 166), (243, 176, 84), (108, 200, 140), (172, 136, 232)]


def _cfg(ctx):
    v = str(ctx.get("podcast_variant") or "inkwash")
    cfg = VARIANTS.get(v, VARIANTS["inkwash"])
    # nguoi dung tu chon mau: chu tung dong (zh/py/vi_color) + nen panel (panel_color)
    over = {}
    for ck, key in (("ink", "zh_color"), ("pinyin", "py_color"), ("viet", "vi_color")):
        c = SP.hex2rgb(ctx.get(key))
        if c:
            over[ck] = c
    pc = SP.hex2rgb(ctx.get("panel_color"))
    if pc:
        over["panel"] = pc      # lop nen chu (panel variants)
        over["bgfill"] = pc     # nen phang khi KHONG co anh nen (free/flat/song...)
    if over:
        cfg = dict(cfg); cfg.update(over)   # copy — KHONG sua bang VARIANTS goc
    return cfg


# ---------- NEN ----------
_bg_cache = {}
def _cover_bg_2x(path):
    """Anh nen nguoi dung -> phu kin SWxSH (2x), cache."""
    k = path
    if k in _bg_cache:
        return _bg_cache[k].copy()
    src = Image.open(path).convert("RGB")
    tw, th = W * S, H * S
    sr, tr = src.width / src.height, tw / th
    if sr > tr:
        src = src.resize((int(th * sr), th), Image.LANCZOS)
    else:
        src = src.resize((tw, int(tw / sr)), Image.LANCZOS)
    x, y = (src.width - tw) // 2, (src.height - th) // 2
    out = src.crop((x, y, x + tw, y + th))
    _bg_cache[k] = out
    return out.copy()


_paper_cache = {}
def _paper_texture(size, strength=10, color=(120, 100, 70)):
    """Texture giay/phan nhe (noise mo) — RGBA de alpha_composite len panel."""
    k = (size, strength, color)
    if k in _paper_cache:
        return _paper_cache[k]
    n = Image.effect_noise(size, 28).filter(ImageFilter.GaussianBlur(1))
    # noise xam -> lech quanh 128; chuyen thanh alpha rat nhe
    a = n.point(lambda p: max(0, min(strength, abs(p - 128) // 3)))
    tex = Image.new("RGBA", size, tuple(color) + (255,))
    tex.putalpha(a)
    _paper_cache[k] = tex
    return tex


# ---------- TRANG TRI ----------
def _draw_seal(im, d, text, x, y, size):
    """An trien do: o vuong do bo goc, chu Han trang xep doc. (x,y)=goc tren-trai."""
    pad = size // 7
    d.rounded_rectangle([x, y, x + size, y + size * max(1, len(text))],
                        radius=size // 6, fill=SEAL_RED + (235,))
    d.rounded_rectangle([x + pad // 2, y + pad // 2,
                         x + size - pad // 2, y + size * max(1, len(text)) - pad // 2],
                        radius=size // 8, outline=(255, 240, 230, 200), width=max(2, size // 22))
    f = SP.font("zh", size - 2 * pad)
    for i, ch in enumerate(text):
        cw = SP.text_w(d, ch, f)
        d.text((x + (size - cw) // 2, y + i * size + pad), ch, font=f, fill=(255, 245, 238))


def _seal_text(ctx):
    """Chu khac tren trien: ctx['seal_text'] hoac 2 chu CJK dau cua ten kenh; fallback '汉语'."""
    t = (ctx.get("seal_text") or "").strip()
    if not t:
        ch = [c for c in (ctx.get("channel") or "") if SP.has_hanzi(c)]
        t = "".join(ch[:2]) if ch else "汉语"
    return t[:4]


def _corners(d, box, size, inset, color, w):
    x0, y0, x1, y1 = box
    x0 += inset; y0 += inset; x1 -= inset; y1 -= inset
    for (cx, cy, sx, sy) in [(x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)]:
        d.line([(cx, cy), (cx + sx * size, cy)], fill=color, width=w)
        d.line([(cx, cy), (cx, cy + sy * size)], fill=color, width=w)


def _draw_rollers(d, box, color):
    """2 truc go dau cuon thu (scroll): thanh doc dam + num tron o 2 dau."""
    x0, y0, x1, y1 = box
    bar_w = 26 * S
    knob_r = 20 * S
    dark = tuple(max(0, c - 36) for c in color)
    for bx in (x0 - bar_w - 6 * S, x1 + 6 * S):
        d.rounded_rectangle([bx, y0 - 14 * S, bx + bar_w, y1 + 14 * S],
                            radius=bar_w // 2, fill=color + (255,))
        # van go: 2 soc sang mo
        d.rounded_rectangle([bx + bar_w // 3, y0 - 8 * S, bx + bar_w // 3 + 3 * S, y1 + 8 * S],
                            radius=2 * S, fill=(255, 255, 255, 36))
        for by in (y0 - 14 * S, y1 + 14 * S):
            d.ellipse([bx + bar_w // 2 - knob_r, by - knob_r,
                       bx + bar_w // 2 + knob_r, by + knob_r], fill=dark + (255,))
            d.ellipse([bx + bar_w // 2 - knob_r // 2, by - knob_r // 2,
                       bx + bar_w // 2 + knob_r // 2, by + knob_r // 2],
                      fill=tuple(min(255, c + 30) for c in color) + (255,))


def _draw_meander(d, box, color, cell=None, inset=None):
    """Hoa van HOI VAN (回纹 — Greek key) chay doc mep TREN + DUOI panel."""
    cell = cell or 18 * S
    inset = inset if inset is not None else 26 * S
    x0, y0, x1, y1 = box
    w = max(2, 2 * S)
    for ybase, flip in ((y0 + inset, 1), (y1 - inset, -1)):
        x = x0 + 60 * S
        while x + cell * 2 <= x1 - 60 * S:
            c, h = cell, cell // 2 * flip
            # 1 don vi hoi van don gian: nét chữ U vuông lồng nhau
            pts = [(x, ybase), (x + c, ybase), (x + c, ybase - h),
                   (x + c // 2, ybase - h), (x + c // 2, ybase - h // 2),
                   (x + c * 2 - c // 4, ybase - h // 2)]
            d.line(pts, fill=color, width=w, joint="curve")
            x += cell * 2
    return


def _draw_chalk_border(d, box, color):
    """Vien PHAN TAY VE (chalkboard): net dut khong deu + 2 goc xoan nho."""
    import math
    x0, y0, x1, y1 = box
    m = 22 * S
    x0, y0, x1, y1 = x0 + m, y0 + m, x1 - m, y1 - m
    w = 3 * S
    def _seg(a, b, k):
        # net dut "run tay": do dai doan thay doi theo sin de trong tu nhien
        ax, ay = a; bx, by = b
        L = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
        t = 0.0; i = 0
        while t < 1.0:
            dl = (26 + 14 * math.sin(k + i * 1.7)) * S / L
            gp = (12 + 8 * math.cos(k + i * 2.3)) * S / L
            t2 = min(1.0, t + dl)
            jx = int(2 * S * math.sin(k * 3 + i))            # lech nhe cho giong tay ve
            d.line([(ax + (bx - ax) * t + jx, ay + (by - ay) * t),
                    (ax + (bx - ax) * t2 + jx, ay + (by - ay) * t2)],
                   fill=color + (215,), width=w)
            t = t2 + gp; i += 1
    _seg((x0, y0), (x1, y0), 1); _seg((x1, y1), (x0, y1), 2)
    _seg((x0, y1), (x0, y0), 3); _seg((x1, y0), (x1, y1), 4)


def _draw_slats(im, d, box, base):
    """Bo THE TRE (竹简): cac thanh doc xen ke mau + 2 day buoc ngang."""
    import random
    rng = random.Random(7)
    x0, y0, x1, y1 = box
    n = 13
    gap = 6 * S
    sw = ((x1 - x0) - gap * (n - 1)) // n
    for i in range(n):
        sx = x0 + i * (sw + gap)
        dv = rng.randint(-9, 9)
        col = tuple(max(0, min(255, c + dv)) for c in base)
        d.rounded_rectangle([sx, y0, sx + sw, y1], radius=12 * S, fill=col + (255,))
        # van tre: 1 soc sang RAT mo giua thanh (khong xuyen chu)
        d.rounded_rectangle([sx + sw // 2 - S, y0 + 10 * S, sx + sw // 2 + S, y1 - 10 * S],
                            radius=S, fill=(255, 255, 255, 13))
    # 2 day buoc ngang — sat mep tren/duoi de KHONG cat ngang chu
    for ry in (y0 + int((y1 - y0) * 0.055), y1 - int((y1 - y0) * 0.055)):
        d.rectangle([x0 - 8 * S, ry - 5 * S, x1 + 8 * S, ry + 5 * S], fill=(90, 63, 42, 235))
        for i in range(n):
            sx = x0 + i * (sw + gap)
            d.rectangle([sx + sw // 2 - 7 * S, ry - 9 * S, sx + sw // 2 + 7 * S, ry + 9 * S],
                        fill=(70, 48, 32, 255))


def _draw_grid_paper(d, box, line_col):
    """Nen VO KE O: luoi vuong 32px + duong le do ben trai."""
    x0, y0, x1, y1 = box
    step = 32 * S
    x = x0 + step
    while x < x1:
        d.line([(x, y0 + 6 * S), (x, y1 - 6 * S)], fill=line_col + (110,), width=S)
        x += step
    y = y0 + step
    while y < y1:
        d.line([(x0 + 6 * S, y), (x1 - 6 * S, y)], fill=line_col + (110,), width=S)
        y += step
    d.line([(x0 + 90 * S, y0 + 6 * S), (x0 + 90 * S, y1 - 6 * S)],
           fill=(232, 176, 168, 200), width=2 * S)


def _paste_washi(im, x, y):
    """Bang keo WASHI soc cheo hong, xoay nhe — chat 'so tay hoc tap'."""
    tw, th = 220 * S, 34 * S
    tape = Image.new("RGBA", (tw, th), (244, 199, 207, 235))
    td = ImageDraw.Draw(tape)
    for sx in range(-th, tw + th, 22 * S):
        td.line([(sx, th), (sx + th, 0)], fill=(249, 224, 228, 235), width=8 * S)
    tape = tape.rotate(-2.4, expand=True, resample=Image.BICUBIC)
    im.alpha_composite(tape, (x, y))


def _draw_redrules(d, box, color):
    """Kinh tuyen do nhat 2 mep trong (phong sach co / trang kinh)."""
    x0, y0, x1, y1 = box
    m = 34 * S
    for rx in (x0 + m, x1 - m):
        d.line([(rx, y0 + 22 * S), (rx, y1 - 22 * S)], fill=color + (110,), width=2 * S)
    for rx in (x0 + m + 10 * S, x1 - m - 10 * S):
        d.line([(rx, y0 + 22 * S), (rx, y1 - 22 * S)], fill=color + (60,), width=S)


# ---------- CHU ----------
def _shadow_text(d, xy, text, f, fill, dark_bg):
    """Chu co bong mem: bong lech nhe -> chu noi khoi tren nen tranh."""
    x, y = xy
    if dark_bg:
        sh = (0, 0, 0, 130)
    else:
        sh = (92, 74, 58, 60)
    d.text((x + 2 * S, y + 2 * S), text, font=f, fill=sh)
    d.text((x, y), text, font=f, fill=fill)


def _hanzi_lines(d, text, size, max_w, char_gap):
    """Chia dong (gom tu Latin thanh 1 khoi -> khong tach le/cat giua tu)."""
    zf = SP.font("zh", size); lf = SP.font("viet", int(size * 0.86))
    uw = lambda u, h: SP.text_w(d, u, zf if h else lf)
    lines, cur, curw, gi = [], [], 0, 0
    for unit, p, h in SP.group_units(text):
        w = uw(unit, h) + char_gap
        if curw + w > max_w and cur and unit not in SP._CLOSERS:
            lines.append(cur); cur, curw = [], 0
        cur.append((unit, bool(h), gi)); curw += w; gi += 1
    if cur:
        lines.append(cur)
    return lines


def _fit_hanzi(d, text, max_w, max_h, hi, lo, line_gap):
    size = hi
    while size > lo:
        n = len(_hanzi_lines(d, text, size, max_w, 8 * S))
        if n * (size + line_gap) <= max_h:
            return size
        size -= 4 * S
    return lo


def _draw_hanzi(d, text, cx, top, size, max_w, color, dark_bg,
                char_gap=None, line_gap=None, reveal_t=None, t_now=BIG, hl=None):
    char_gap = char_gap if char_gap is not None else 8 * S
    line_gap = line_gap if line_gap is not None else 22 * S
    lines = _hanzi_lines(d, text, size, max_w, char_gap)
    zf = SP.font("zh", size); lf = SP.font("viet", int(size * 0.86))
    uw = lambda u, h: SP.text_w(d, u, zf if h else lf)
    lh = size + line_gap
    y = top
    for ln in lines:
        total = sum(uw(u, h) + char_gap for u, h, _ in ln) - char_gap
        x = cx - total // 2
        if hl:   # vet but da quang sau chu (study style)
            d.rounded_rectangle([x - 14 * S, y + size * 0.06, x + total + 14 * S,
                                 y + size * 1.12], radius=10 * S, fill=tuple(hl) + (160,))
        for unit, h, idx in ln:
            if reveal_t is None or reveal_t[idx] <= t_now:
                f = zf if h else lf
                oy = 0 if h else int(size * 0.12)
                _shadow_text(d, (x, y + oy), unit, f, color, dark_bg)
            x += uw(unit, h) + char_gap
        y += lh
    return len(lines) * lh


def _draw_pinyin(d, text, cx, y, max_w, neutral, tone_map, tone=True, size=None, gap=None):
    size = size or 46 * S
    gap = gap or 10 * S
    toks = []
    for unit, p, h in SP.group_units(text):     # gom tu Latin -> khong giãn rời từng chữ cái
        if h and p:
            toks.append((p, False))
        else:
            toks.append((unit, bool(h)))
    # tinh be rong TRUOC roi moi thu nho dan — size nho san (nguoi dung ep px)
    # cung phai chay it nhat 1 lan, khong duoc de bien chua gan (bug 'ws')
    while True:
        pf = SP.font("pinyin", size); zf = SP.font("zh", int(size * 0.92))
        ws = [(t, isc, SP.text_w(d, t, zf if isc else pf)) for t, isc in toks]
        total = sum(w for *_, w in ws) + gap * (max(0, len(ws) - 1))
        if total <= max_w or size <= 26 * S:
            break
        size -= 2 * S
    x = cx - total // 2
    for t, isc, w in ws:
        f = zf if isc else pf
        col = neutral if (isc or not tone) else tone_map[SP._tone_of(t)]
        d.text((x, y), t, font=f, fill=col)
        x += w + gap
    return size + 12 * S


def _divider(d, cx, dy, style, color):
    if style == "brush":       # net but long: thanh ngang thon 2 dau
        for i in range(-90, 91, 2):
            t = abs(i) / 90.0
            h = max(1, int((1.0 - t * t) * 4 * S))
            d.line([(cx + i * S, dy - h // 2), (cx + i * S, dy + h // 2)], fill=color)
    elif style == "line":
        d.line([(cx - 70 * S, dy), (cx + 70 * S, dy)], fill=color, width=S)
    else:                       # "dot": gach — cham ngoc — gach (nhu ban cu)
        d.line([(cx - 70 * S, dy), (cx - 14 * S, dy)], fill=color, width=2 * S)
        d.line([(cx + 14 * S, dy), (cx + 70 * S, dy)], fill=color, width=2 * S)
        d.ellipse([cx - 4 * S, dy - 4 * S, cx + 4 * S, dy + 4 * S], fill=color)


# ---------- RUBY PINYIN (pinyin tren TUNG chu Han — kieu Chinese Daily) ----------
def _px(ctx, key, default):
    """Cỡ chữ px nguoi dung tu chinh (zh_px/py_px/vi_px); None/0 = tu dong."""
    try:
        v = int(ctx.get(key) or 0)
        return v * S if 20 <= v <= 320 else default
    except (TypeError, ValueError):
        return default


def _ruby_wrap(d, text, zsize, pysize, max_w, col_gap):
    """Chia cot ruby thanh cac dong <= max_w. Moi cot = (ch, py, col_w, wz, wp).
       Be rong cot = max(be rong chu Han, be rong pinyin). Dau cau dong khong dung dau dong."""
    pf = SP.font("pinyin", pysize)
    zf = SP.font("zh", zsize)
    lf = SP.font("viet", int(zsize * 0.86))       # từ Latin (chèn tiếng Anh) -> font Latin, cả từ 1 ô
    cols = []
    for unit, p, h in SP.group_units(text):
        f = zf if h else lf
        wz = SP.text_w(d, unit, f)
        wp = SP.text_w(d, p, pf) if (h and p) else 0
        cols.append((unit, p if h else "", max(wz, wp), wz, wp, bool(h)))
    lines, cur, curw = [], [], 0
    gi = 0
    for col in cols:
        w = col[2] + col_gap
        if curw + w > max_w and cur and col[0] not in SP._CLOSERS:
            lines.append(cur); cur, curw = [], 0
        cur.append(col + (gi,)); curw += w; gi += 1
    if cur:
        lines.append(cur)
    return lines


def _ruby_line_h(zsize, pysize, py_gap, line_gap):
    return pysize + py_gap + zsize + line_gap


def _fit_ruby(d, text, max_w, max_h, hi, lo, pysize_of, py_gap, line_gap, col_gap):
    """Chon co chu Han LON NHAT de khoi ruby (pinyin + Han) vua max_w x max_h."""
    size = hi
    while size > lo:
        ps = pysize_of(size)
        n = len(_ruby_wrap(d, text, size, ps, max_w, col_gap))
        if n * _ruby_line_h(size, ps, py_gap, line_gap) <= max_h:
            return size
        size -= 4 * S
    return lo


def _draw_ruby(d, text, cx, top, zsize, pysize, max_w, ink, py_neutral, tone_map,
               tone=True, dark=False, col_gap=None, py_gap=None, line_gap=None,
               reveal_t=None, t_now=BIG, hl=None):
    """Ve khoi ruby: pinyin (to mau thanh dieu) tren TUNG chu Han, canh giua."""
    col_gap = col_gap if col_gap is not None else 18 * S
    py_gap = py_gap if py_gap is not None else 10 * S
    line_gap = line_gap if line_gap is not None else 26 * S
    pf = SP.font("pinyin", pysize)
    zf = SP.font("zh", zsize)
    lf = SP.font("viet", int(zsize * 0.86))
    lines = _ruby_wrap(d, text, zsize, pysize, max_w, col_gap)
    lh = _ruby_line_h(zsize, pysize, py_gap, line_gap)
    y = top
    for ln in lines:
        total = sum(c[2] + col_gap for c in ln) - col_gap
        x = cx - total // 2
        if hl:   # vet but da quang sau hang chu Han
            d.rounded_rectangle([x - 12 * S, y + pysize + py_gap + zsize * 0.04,
                                 x + total + 12 * S, y + pysize + py_gap + zsize * 1.1],
                                radius=10 * S, fill=tuple(hl) + (160,))
        for unit, py, colw, wz, wp, h, idx in ln:
            if reveal_t is None or reveal_t[idx] <= t_now:
                if py:
                    col = tone_map[SP._tone_of(py)] if tone else py_neutral
                    d.text((x + (colw - wp) // 2, y), py, font=pf, fill=col)
                f = zf if h else lf
                oy = 0 if h else int(zsize * 0.12)
                _shadow_text(d, (x + (colw - wz) // 2, y + pysize + py_gap + oy),
                             unit, f, ink, dark)
            x += colw + col_gap
        y += lh
    return len(lines) * lh


def _glow_behind(im, overlay, halo, radius=None, layers=3):
    """Quang sang mem sau chu (tu alpha cua overlay) -> chu doc ro tren tranh
       ma KHONG can panel. im: RGBA nen; overlay: RGBA chua chu."""
    radius = radius if radius is not None else 9 * S
    a = overlay.split()[3].point(lambda p: min(255, int(p * 2.2)))
    glow = Image.composite(Image.new("RGBA", overlay.size, halo + (255,)),
                           Image.new("RGBA", overlay.size, (0, 0, 0, 0)), a)
    glow = glow.filter(ImageFilter.GaussianBlur(radius))
    for _ in range(layers):
        im.alpha_composite(glow)
    im.alpha_composite(overlay)


def _dashed_line(d, y, color, x0=None, x1=None, dash=14, gap=10, w=2):
    x0 = x0 if x0 is not None else 46 * S
    x1 = x1 if x1 is not None else W * S - 46 * S
    x = x0
    while x < x1:
        d.line([(x, y), (min(x + dash * S, x1), y)], fill=color, width=w * S)
        x += (dash + gap) * S


# ---------- RENDER "FREE" (khong panel — chu truc tiep tren tranh) ----------
def _render_free(seg, ctx, path, cfg, reveal_t=None, t_now=BIG):
    dark = cfg["dark"]
    bgimg = ctx.get("bg_image")
    if bgimg and os.path.exists(bgimg):
        im = _cover_bg_2x(bgimg).convert("RGBA")
    else:
        base = cfg.get("bgfill") or ((18, 20, 28) if dark else SP.BG)
        im = Image.new("RGBA", (W * S, H * S), tuple(base) + (255,))

    # dai gradient trang duoi (clean): chu vung day luon ro tren moi anh
    if cfg.get("band"):
        ov = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        y_from = int(H * S * 0.52)
        for yy in range(y_from, H * S):
            a = int(240 * min(1.0, (yy - y_from) / (H * S * 0.22)))
            od.line([(0, yy), (W * S, yy)], fill=(252, 252, 253, a))
        im = Image.alpha_composite(im, ov)

    text = seg.get("hanzi", "")
    viet = seg.get("viet", "")
    hide_viet = bool(seg.get("_hide_viet"))
    cx = W * S // 2
    max_w = int(W * S * 0.78)          # margin thoáng 2 bên -> câu dài tự thu nhỏ, không sát mép
    tone = bool(ctx.get("tone_colors", True))
    tone_map = TONE_DARK if dark else TONE_LIGHT
    mode = ctx.get("pinyin_mode") or ("ruby" if cfg.get("ruby") else "line")

    # --- co chu: nguoi dung ep px hoac tu dong fit ---
    d0 = ImageDraw.Draw(im)
    py_of = lambda z: _px(ctx, "py_px", max(30 * S, int(z * 0.34)))
    zpx = _px(ctx, "zh_px", None)
    vsz = _px(ctx, "vi_px", 46 * S)
    vf = SP.font("viet", vsz)
    max_h = int(H * S * (0.46 if cfg["anchor"] == "mid" else 0.42))
    if mode == "ruby":
        zsize = zpx or _fit_ruby(d0, text, max_w, max_h, hi=104 * S, lo=56 * S,
                                 pysize_of=py_of, py_gap=10 * S, line_gap=26 * S,
                                 col_gap=18 * S)
        pysize = py_of(zsize)
        n_lines = len(_ruby_wrap(d0, text, zsize, pysize, max_w, 18 * S))
        block_h = n_lines * _ruby_line_h(zsize, pysize, 10 * S, 26 * S)
    else:
        zsize = zpx or _fit_hanzi(d0, text, max_w, max_h, hi=104 * S, lo=56 * S,
                                  line_gap=22 * S)
        pysize = _px(ctx, "py_px", 44 * S)
        n_lines = len(_hanzi_lines(d0, text, zsize, max_w, 8 * S))
        block_h = (pysize + 12 * S) + int(22 * S) + n_lines * (zsize + 22 * S)

    # --- vi tri khoi theo anchor ---
    sp_name = seg.get("_sp")
    chip_h = 58 * S if sp_name else 0
    vwraps = SP.wrap_text(d0, viet, vf, int(W * S * 0.84)) if viet else []
    vie_inline = (cfg["viet_style"] == "inline" and vwraps)
    vie_h = len(vwraps) * (vsz + 10 * S) if vie_inline else 0
    total_h = chip_h + block_h + ((26 * S + vie_h) if vie_h else 0)
    if cfg["anchor"] == "top":
        y = int(H * S * 0.045)
    elif cfg["anchor"] == "bottom":
        y = int(H * S * 0.93) - total_h
    else:  # mid: tam khoi ~58% chieu cao (chua vung tranh phia tren)
        y = int(H * S * 0.56) - total_h // 2

    # --- ve chu len overlay -> glow sau chu ---
    ov = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov, "RGBA")

    if cfg.get("dashes"):
        dcol = tuple(cfg["pinyin"]) + (120,)
        _dashed_line(d, max(y - 40 * S, 30 * S), dcol)
        _dashed_line(d, min(y + total_h + 44 * S, H * S - 120 * S), dcol)

    if sp_name:
        chips = CHIP_DARK if dark else CHIP_LIGHT
        order = list((ctx.get("_speaker_colors") or {}).keys())
        spcol = chips[order.index(sp_name) % len(chips)] if sp_name in order else chips[0]
        label = str(sp_name)
        has_cjk = any(SP.has_hanzi(c) for c in label)
        cf = SP.font("zh", 32 * S) if has_cjk else SP.font("badge", 32 * S)
        lw = SP.text_w(d, label, cf)
        cw2 = lw + 56 * S
        d.rounded_rectangle([cx - cw2 // 2, y, cx + cw2 // 2, y + 46 * S],
                            radius=23 * S, fill=spcol)
        d.text((cx - lw // 2, y + (2 if has_cjk else 6) * S), label,
               font=cf, fill=(255, 255, 255))
        y += chip_h

    if mode == "ruby":
        y += _draw_ruby(d, text, cx, y, zsize, pysize, max_w, cfg["ink"],
                        cfg["pinyin"], tone_map, tone=tone, dark=dark,
                        reveal_t=reveal_t, t_now=t_now)
    else:
        y += _draw_pinyin(d, text, cx, y, int(W * S * 0.9), cfg["pinyin"], tone_map,
                          tone=tone, size=pysize)
        y += int(22 * S)
        y += _draw_hanzi(d, text, cx, y, zsize, max_w, cfg["ink"], dark,
                         reveal_t=reveal_t, t_now=t_now)

    # --- nghia Viet ---
    if vwraps:
        if cfg["viet_style"] == "band":
            vy = H * S - 150 * S - (len(vwraps) - 1) * (vsz + 10 * S)
        else:
            vy = y + 26 * S
        if hide_viet:
            hint = "· · ·  thử đoán nghĩa  · · ·"
            hf = SP.font("sans", 32 * S)
            hw = SP.text_w(d, hint, hf)
            col = (220, 222, 232, 180) if dark else (120, 110, 100, 200)
            d.text((cx - hw // 2, vy + 4 * S), hint, font=hf, fill=col)
        else:
            for ln in vwraps:
                tw = SP.text_w(d, ln, vf)
                _shadow_text(d, (cx - tw // 2, vy), ln, vf, cfg["viet"], dark)
                vy += vsz + 10 * S

    _glow_behind(im, ov, cfg["halo"])
    d = ImageDraw.Draw(im, "RGBA")

    # trien do (goc duoi-trai, nhu kenh mau) + bo dem + tien do
    if cfg.get("seal") and ctx.get("seal", True) and ctx.get("podcast_frame", True):
        st = _seal_text(ctx)
        ssz = 40 * S
        _draw_seal(im, d, st, 40 * S, H * S - 40 * S - ssz * max(1, len(st)), ssz)
    bar_h = _draw_bottom_bar(im, d, ctx)
    if ctx.get("show_progress", True):
        _draw_counter(d, seg, dark)
        _draw_progress(d, seg, off=bar_h)

    if ctx.get("_transparent"):        # giu RGBA -> overlay len video (panel co mau, ria trong suot)
        out = im.resize((W, H), Image.LANCZOS)
    else:
        out = im.convert("RGB").resize((W, H), Image.LANCZOS)
    out.save(path)
    return out


# ---------- BOTTOM BAR (thanh chan kieu Chinese Daily) ----------
def _mixed_w(d, text, size):
    """Be rong chuoi khi ve tron: chu Han dung font Han, Latin/Viet dung font dam."""
    return sum(SP.text_w(d, ch, SP.font("zh" if SP._is_cjk(ch) else "badge", size))
               for ch in text)


def _mixed_text(d, x, y, text, size, fill):
    """Ve chuoi tron Han + Latin/Viet (khong tofu). Tra ve x sau khi ve."""
    for ch in text:
        cjk = SP._is_cjk(ch)
        f = SP.font("zh" if cjk else "badge", size)
        d.text((x, y - (int(size * 0.08) if cjk else 0)), ch, font=f, fill=fill)
        x += SP.text_w(d, ch, f)
    return x


def _luma(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


BAR_H = 64  # chieu cao bottom bar (px 1x)

def _draw_bottom_bar(im, d, ctx):
    """Thanh chan day man hinh: hook TRAI + ten kenh & badge PHAI.
       Mau nen tuy chinh ctx['bar_bg'] ('#rrggbb'); chu tu dong den/trang theo do sang.
       Tra ve chieu cao bar (2x) de day thanh tien do len tren."""
    if not ctx.get("bottom_bar"):
        return 0
    bar_h = BAR_H * S
    bg = SP.hex2rgb(ctx.get("bar_bg")) or (244, 241, 234)
    fg = (34, 32, 30) if _luma(bg) > 140 else (250, 248, 244)
    y0 = H * S - bar_h
    d.rectangle([0, y0, W * S, H * S], fill=tuple(bg) + (255,))
    d.line([(0, y0), (W * S, y0)], fill=(0, 0, 0, 45), width=S)
    ty = y0 + (bar_h - 30 * S) // 2 - 2 * S
    # trai: cau hook (tu dong VIET HOA cho manh)
    left = (ctx.get("bar_left") or "").strip()
    if left:
        _mixed_text(d, 56 * S, ty, left.upper(), 30 * S, fg)
    # phai: badge pill (PODCAST...) roi den ten kenh
    x = W * S - 56 * S
    badge = (ctx.get("bar_badge") or "PODCAST").strip()
    if badge:
        bf30 = 26 * S
        bw = _mixed_w(d, badge, bf30)
        pw = bw + 44 * S
        x -= pw
        d.rounded_rectangle([x, y0 + 12 * S, x + pw, H * S - 12 * S],
                            radius=(bar_h - 24 * S) // 2, fill=(28, 28, 32, 255))
        # cham mic vang ben phai trong pill
        _mixed_text(d, x + 20 * S, y0 + (bar_h - bf30) // 2 - 2 * S, badge, bf30,
                    (255, 255, 255))
        x -= 22 * S
    ch = (ctx.get("channel") or "").strip()
    if ch:
        cw = _mixed_w(d, ch.upper(), 30 * S)
        _mixed_text(d, x - cw, ty, ch.upper(), 30 * S, fg)
    return bar_h


# ---------- BO DEM CAU + THANH TIEN DO ----------
def _draw_counter(d, seg, dark):
    """Pill '12/50' goc tren-phai — nguoi xem biet con bao nhieu cau (retention)."""
    idx, n = seg.get("_idx"), seg.get("_n")
    if not idx or not n:
        return
    label = f"{idx}/{n}"
    f = SP.font("sansb", 30 * S)
    lw = SP.text_w(d, label, f)
    x1, y0 = W * S - 44 * S, 40 * S
    d.rounded_rectangle([x1 - lw - 44 * S, y0, x1, y0 + 52 * S],
                        radius=26 * S, fill=(10, 10, 14, 130))
    d.text((x1 - lw - 22 * S, y0 + 9 * S), label, font=f, fill=(255, 246, 224))


def _draw_progress(d, seg, off=0):
    """Thanh tien do manh (6px) day man hinh — mau vang accent tren track mo.
       off: day len tren (khi co bottom bar)."""
    idx, n = seg.get("_idx"), seg.get("_n")
    if not idx or not n:
        return
    h = 6 * S
    yb = H * S - off
    d.rectangle([0, yb - h, W * S, yb], fill=(255, 255, 255, 34))
    d.rectangle([0, yb - h, int(W * S * idx / n), yb], fill=(227, 179, 65, 235))


# ---------- RENDER CHINH ----------
def render(seg, ctx, path, reveal_t=None, t_now=BIG):
    cfg = _cfg(ctx)
    if cfg.get("free"):        # nhom khong panel (daily/flat/clean/top)
        return _render_free(seg, ctx, path, cfg, reveal_t=reveal_t, t_now=t_now)
    dark = cfg["dark"]

    # 1) nen
    bgimg = ctx.get("bg_image")
    if ctx.get("_transparent"):        # nen VIDEO dong -> canvas trong suot (chi ve panel+chu)
        im = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    elif bgimg and os.path.exists(bgimg):
        im = _cover_bg_2x(bgimg).convert("RGBA")
    else:
        base = tuple(cfg.get("bgfill") or ((18, 20, 28) if dark else SP.BG))
        im = Image.new("RGBA", (W * S, H * S), base + (255,))

    # --- box panel (1x) + tuy chinh chieu cao + tranh de thanh chan ---
    bx0, by0, bx1, by1 = cfg["box"]
    ph = ctx.get("panel_h")            # chieu cao panel nguoi dung chon (px 1x); 0/None = mac dinh
    if ph:
        by0 = by1 - int(ph)            # giu day, keo dinh len/xuong -> cao/thap hon
    if ctx.get("bottom_bar") and not cfg.get("scrim") and not cfg.get("slats"):
        limit = (H - BAR_H) - 12       # dinh thanh chan - le; panel phai ket thuc tren day
        if by1 > limit:
            shift = by1 - limit        # day CA panel len de khong bi thanh chan de
            by0 -= shift; by1 -= shift
    if by0 < 60:                        # chan tren (khong day qua sat mep)
        by0 = 60
    x0, y0, x1, y1 = [c * S for c in (bx0, by0, bx1, by1)]

    # 2) panel / scrim
    alpha = ctx.get("panel_alpha")
    alpha = cfg["alpha"] if alpha is None else int(alpha)
    if ctx.get("_transparent") and alpha > 0:     # nen video -> hop kem DAM hon cho chu ro
        alpha = min(240, max(215, alpha + 70))
    if cfg.get("slats"):
        _draw_slats(im, ImageDraw.Draw(im, "RGBA"), (x0, y0, x1, y1), cfg["panel"])
    elif cfg["scrim"]:
        # gradient toi tu duoi len (dien anh) — khong khung
        ov = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        top_f = y0 - 90 * S
        for yy in range(top_f, H * S):
            a = int(215 * min(1.0, (yy - top_f) / (H * S * 0.30)))
            od.line([(0, yy), (W * S, yy)], fill=(10, 10, 16, a))
        im = Image.alpha_composite(im, ov)
    elif alpha > 0:
        radius = 34 * S if cfg.get("shadow") else 26 * S
        if cfg.get("shadow"):
            # bong do mem duoi the (card hien dai)
            sh = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
            ImageDraw.Draw(sh).rounded_rectangle(
                [x0 + 4 * S, y0 + 14 * S, x1 + 4 * S, y1 + 14 * S],
                radius=radius, fill=(30, 30, 50, 90))
            im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(18 * S)))
        mask = Image.new("L", (W * S, H * S), 0)
        ImageDraw.Draw(mask).rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=alpha)
        blur = 4 * S if cfg.get("shadow") else 16 * S    # card: mep sac; con lai: mep mo
        mask = mask.filter(ImageFilter.GaussianBlur(blur))
        fill = Image.new("RGBA", (W * S, H * S), cfg["panel"] + (255,))
        im = Image.composite(fill, im, mask)
        if cfg["texture"]:
            tex = _paper_texture((x1 - x0, y1 - y0),
                                 color=cfg.get("texture_col", (120, 100, 70)))
            im.alpha_composite(tex, (x0, y0))
        if cfg.get("grid"):
            _draw_grid_paper(ImageDraw.Draw(im, "RGBA"), (x0, y0, x1, y1), (222, 214, 198))

    # 3) khung + trang tri
    ov = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    frame_on = ctx.get("podcast_frame", True)
    if frame_on and cfg["frame"] not in ("none", "chalk"):
        od.rounded_rectangle([x0, y0, x1, y1], radius=26 * S,
                             outline=cfg["border"] + (215,), width=3 * S)
        if cfg["frame"] == "double":
            od.rounded_rectangle([x0 + 10 * S, y0 + 10 * S, x1 - 10 * S, y1 - 10 * S],
                                 radius=20 * S, outline=cfg["border"] + (110,), width=2 * S)
    if frame_on and cfg["frame"] == "chalk":
        _draw_chalk_border(od, (x0, y0, x1, y1), cfg["border"])
    if frame_on and cfg.get("meander"):
        _draw_meander(od, (x0, y0, x1, y1), cfg["border"] + (170,))
    if cfg.get("accentbar"):
        # thanh accent tren dinh the + 3 cham trang tri (card hien dai)
        od.rounded_rectangle([x0, y0, x1, y0 + 16 * S], radius=8 * S,
                             fill=cfg["border"] + (255,))
        for k, cc in enumerate([(235, 87, 87), (250, 176, 64), (72, 190, 140)]):
            cxx = x0 + 46 * S + k * 34 * S
            od.ellipse([cxx - 8 * S, y0 + 40 * S - 8 * S, cxx + 8 * S, y0 + 40 * S + 8 * S],
                       fill=cc + (255,))
    if frame_on and cfg["rollers"]:
        _draw_rollers(od, (x0, y0, x1, y1), cfg["border"])
    if frame_on and cfg["redrules"]:
        _draw_redrules(od, (x0, y0, x1, y1), (196, 84, 64))
    if frame_on and cfg["seal"] and ctx.get("seal", True):
        st = _seal_text(ctx)
        ssz = 46 * S
        _draw_seal(ov, od, st, x1 - ssz - 26 * S, y0 + 24 * S, ssz)
    im = Image.alpha_composite(im, ov)
    if cfg.get("washi"):
        _paste_washi(im, x0 + 30 * S, y0 - 12 * S)
    d = ImageDraw.Draw(im, "RGBA")
    if frame_on and cfg["corners"]:
        _corners(d, (x0, y0, x1, y1), 34 * S, 18 * S, cfg["border"], 3 * S)

    # 4) noi dung
    text = seg.get("hanzi", "")
    viet = seg.get("viet", "")            # van RESERVE cho de bo cuc 2 pha giong het nhau
    hide_viet = bool(seg.get("_hide_viet"))
    pinyin_top = bool(ctx.get("pinyin_top", True))   # pinyin TREN chu Han (chuan kenh lon)
    cx = (x0 + x1) // 2
    box_w = x1 - x0
    max_w = int(box_w * 0.86)          # margin trong panel -> câu dài tự thu nhỏ, không sát viền

    sp_name = seg.get("_sp")
    chips = CHIP_DARK if dark else CHIP_LIGHT
    spcol = None
    if sp_name:
        order = list((ctx.get("_speaker_colors") or {}).keys())
        if sp_name in order:
            spcol = chips[order.index(sp_name) % len(chips)]
        else:
            spcol = chips[0]
    chip_h = 58 * S if spcol else 0

    gap1, gap2 = 40 * S, 30 * S
    ruby_mode = (ctx.get("pinyin_mode") == "ruby")
    vsz = _px(ctx, "vi_px", 56 * S)
    vf = SP.font("viet", vsz)
    vwraps = SP.wrap_text(d, viet, vf, int(box_w * 0.88)) if viet else []
    vie_h = len(vwraps) * (vsz + 12 * S)
    if ruby_mode:
        # khoi ruby (pinyin tren tung chu) — khong co dong pinyin rieng
        avail = (y1 - y0) - (chip_h + (gap2 + vie_h if vie_h else 0) + 40 * S)
        py_of = lambda z: _px(ctx, "py_px", max(28 * S, int(z * 0.34)))
        zsize = _px(ctx, "zh_px", None) or _fit_ruby(d, text, max_w, avail,
                                                     hi=120 * S, lo=64 * S, pysize_of=py_of,
                                                     py_gap=10 * S, line_gap=26 * S, col_gap=16 * S)
        pysize = py_of(zsize)
        blk_h = len(_ruby_wrap(d, text, zsize, pysize, max_w, 16 * S)) * \
            _ruby_line_h(zsize, pysize, 10 * S, 26 * S)
    else:
        pysize = _px(ctx, "py_px", 46 * S)
        pin_h = pysize + 12 * S
        reserved = chip_h + (gap1 + pin_h) + (gap2 + vie_h if vie_h else 0) + 40 * S
        zsize = _px(ctx, "zh_px", None) or _fit_hanzi(d, text, max_w, (y1 - y0) - reserved,
                                                      hi=132 * S, lo=78 * S, line_gap=22 * S)
        blk_h = len(_hanzi_lines(d, text, zsize, max_w, 8 * S)) * (zsize + 22 * S) \
            + gap1 + pin_h

    total = chip_h + blk_h + (gap2 + vie_h if vie_h else 0)
    y = y0 + ((y1 - y0) - total) // 2

    if spcol:
        label = str(sp_name)
        has_cjk = any(SP.has_hanzi(c) for c in label)
        cf = SP.font("zh", 32 * S) if has_cjk else SP.font("badge", 32 * S)
        lw = SP.text_w(d, label, cf)
        cw2 = lw + 56 * S
        if dark:
            d.rounded_rectangle([cx - cw2 // 2, y, cx + cw2 // 2, y + 46 * S],
                                radius=23 * S, fill=(0, 0, 0, 120), outline=spcol, width=2 * S)
            d.text((cx - lw // 2, y + (2 if has_cjk else 6) * S), label, font=cf, fill=spcol)
        else:
            d.rounded_rectangle([cx - cw2 // 2, y, cx + cw2 // 2, y + 46 * S],
                                radius=23 * S, fill=spcol)
            d.text((cx - lw // 2, y + (2 if has_cjk else 6) * S), label,
                   font=cf, fill=(255, 255, 255))
        y += chip_h

    tone = bool(ctx.get("tone_colors", True))
    tone_map = TONE_DARK if dark else TONE_LIGHT
    hl = cfg.get("highlight")
    if ruby_mode:
        y += _draw_ruby(d, text, cx, y, zsize, pysize, max_w, cfg["ink"], cfg["pinyin"],
                        tone_map, tone=tone, dark=dark, col_gap=16 * S,
                        reveal_t=reveal_t, t_now=t_now, hl=hl)
    elif pinyin_top:
        y += _draw_pinyin(d, text, cx, y, int(box_w * 0.94), cfg["pinyin"], tone_map,
                          tone=tone, size=pysize)
        y += int(gap1 * 0.55)
        y += _draw_hanzi(d, text, cx, y, zsize, max_w, cfg["ink"], dark,
                         reveal_t=reveal_t, t_now=t_now, hl=hl)
    else:
        y += _draw_hanzi(d, text, cx, y, zsize, max_w, cfg["ink"], dark,
                         reveal_t=reveal_t, t_now=t_now, hl=hl)
        y += gap1
        y += _draw_pinyin(d, text, cx, y, int(box_w * 0.94), cfg["pinyin"], tone_map,
                          tone=tone, size=pysize)
    if vie_h:
        dy = y + gap2 // 2
        _divider(d, cx, dy, cfg["divider"], cfg["border"])
        y += gap2 + 8 * S
        if hide_viet:
            # pha "doan nghia": giu nguyen bo cuc, chi thay nghia bang goi y nhe
            hint = "· · ·  thử đoán nghĩa  · · ·"
            hf = SP.font("sans", 34 * S)
            hw = SP.text_w(d, hint, hf)
            col = (200, 204, 216, 170) if dark else (128, 116, 100, 190)
            d.text((cx - hw // 2, y + (vie_h - 34 * S) // 2 - 6 * S), hint, font=hf, fill=col)
        else:
            for ln in vwraps:
                tw = SP.text_w(d, ln, vf)
                _shadow_text(d, (cx - tw // 2, y), ln, vf, cfg["viet"], dark)
                y += vsz + 12 * S

    bar_h = _draw_bottom_bar(im, d, ctx)
    if ctx.get("show_progress", True):
        _draw_counter(d, seg, dark)
        _draw_progress(d, seg, off=bar_h)

    if ctx.get("_transparent"):        # giu RGBA -> overlay len video (panel co mau, ria trong suot)
        out = im.resize((W, H), Image.LANCZOS)
    else:
        out = im.convert("RGB").resize((W, H), Image.LANCZOS)
    out.save(path)
    return out


def render_section(seg, ctx, path):
    """The chuyen muc trong podcast layout: nen tranh + nhan lon giua, cung tham my."""
    cfg = _cfg(ctx)
    dark = cfg["dark"]
    # nhom "free" khong co panel/divider rieng -> dung mau mac dinh hop tone
    panel_col = cfg.get("panel") or ((24, 26, 34) if dark else (252, 249, 242))
    div_style = cfg.get("divider", "dot")
    bgimg = ctx.get("bg_image")
    if bgimg and os.path.exists(bgimg):
        im = _cover_bg_2x(bgimg).convert("RGBA")
    else:
        base = (18, 20, 28) if dark else SP.BG
        im = Image.new("RGBA", (W * S, H * S), base + (255,))
    lbl = seg.get("label", "")
    d = ImageDraw.Draw(im, "RGBA")
    lf = SP.font("viet", 108 * S)
    tw = SP.text_w(d, lbl, lf)
    cx, cy = W * S // 2, H * S // 2
    # panel nho quanh nhan
    pw, ph = tw + 220 * S, 108 * S + 150 * S
    mask = Image.new("L", (W * S, H * S), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [cx - pw // 2, cy - ph // 2, cx + pw // 2, cy + ph // 2], radius=24 * S, fill=200)
    mask = mask.filter(ImageFilter.GaussianBlur(14 * S))
    fill = Image.new("RGBA", (W * S, H * S), tuple(panel_col) + (255,))
    im = Image.composite(fill, im, mask)
    d = ImageDraw.Draw(im, "RGBA")
    d.rounded_rectangle([cx - pw // 2, cy - ph // 2, cx + pw // 2, cy + ph // 2],
                        radius=24 * S, outline=cfg["border"] + (200,), width=3 * S)
    ink = cfg["ink"]
    _shadow_text(d, (cx - tw // 2, cy - (108 * S) // 2 - 12 * S), lbl, lf, ink, dark)
    _divider(d, cx, cy + (108 * S) // 2 + 26 * S, div_style, cfg["border"])
    _draw_bottom_bar(im, d, ctx)
    if ctx.get("_transparent"):        # giu RGBA -> overlay len video (panel co mau, ria trong suot)
        out = im.resize((W, H), Image.LANCZOS)
    else:
        out = im.convert("RGB").resize((W, H), Image.LANCZOS)
    out.save(path)
    return out


if __name__ == "__main__":
    # xem thu 5 bien the -> ghi ra ref/
    os.makedirs("ref", exist_ok=True)
    bg = None
    up = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
    if os.path.isdir(up):
        pngs = [os.path.join(up, f) for f in sorted(os.listdir(up))
                if f.lower().endswith((".png", ".jpg", ".jpeg"))]
        bg = pngs[0] if pngs else None
    seg = {"type": "sentence", "hanzi": "学语言，最重要的是每天都听一点。",
           "viet": "Học ngôn ngữ, quan trọng nhất là mỗi ngày đều nghe một chút.",
           "_sp": "小雨", "_idx": 12, "_n": 50}
    for v in VARIANTS:
        ctx = {"podcast_layout": True, "podcast_variant": v, "channel": "Lạc Học Đường",
               "seal_text": "乐学", "bg_image": bg, "tone_colors": True,
               "_speaker_colors": {"小雨": (40, 96, 196)}}
        render(seg, ctx, f"ref/_v_{v}.png")
        print("ok", v)
    # pha "doan nghia" (an Viet) + the chuyen muc
    render(dict(seg, _hide_viet=True), {"podcast_layout": True, "podcast_variant": "inkwash",
           "channel": "Lạc Học Đường", "seal_text": "乐学", "bg_image": bg},
           "ref/_v_recall.png")
    render_section({"type": "section", "label": "Nghe lại — không nhìn nghĩa"},
                   {"podcast_layout": True, "podcast_variant": "inkwash", "bg_image": bg},
                   "ref/_v_section.png")
    # ruby trong panel + size px tuy chinh
    render(seg, {"podcast_layout": True, "podcast_variant": "inkwash", "channel": "Lạc Học Đường",
                 "seal_text": "乐学", "bg_image": bg, "pinyin_mode": "ruby",
                 "_speaker_colors": {"小雨": (40, 96, 196)}}, "ref/_v_inkwash_ruby.png")
    render(seg, {"podcast_layout": True, "podcast_variant": "daily", "bg_image": bg,
                 "zh_px": 120, "py_px": 34, "vi_px": 40, "seal_text": "乐学",
                 "_speaker_colors": {"小雨": (40, 96, 196)}}, "ref/_v_daily_px.png")
    print("ok recall + section + ruby/px")
