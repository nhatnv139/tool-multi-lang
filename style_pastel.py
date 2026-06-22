# -*- coding: utf-8 -*-
"""Bo render kieu PASTEL (giong kenh hoc tieng Trung): pinyin tren tung chu Han.
   Dung cho moi loai slide: title, objectives, section, vocab, sentence,
   dialogue, practice_q, practice_a, outro."""
import sys, os
from PIL import Image, ImageDraw, ImageFont
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
}
# mau hien hanh (mac dinh hong) — apply_theme() doi bo nay
BG, INK, PINYIN, VIET, HEADER, LINE, BADGE, GOLD, SOFT = (
    THEMES["pink"]["BG"], THEMES["pink"]["INK"], THEMES["pink"]["PINYIN"],
    THEMES["pink"]["VIET"], THEMES["pink"]["HEADER"], THEMES["pink"]["LINE"],
    THEMES["pink"]["BADGE"], THEMES["pink"]["GOLD"], THEMES["pink"]["SOFT"])

def apply_theme(name):
    global BG, INK, PINYIN, VIET, HEADER, LINE, BADGE, GOLD, SOFT
    t = THEMES.get(name, THEMES["pink"])
    BG, INK, PINYIN, VIET = t["BG"], t["INK"], t["PINYIN"], t["VIET"]
    HEADER, LINE, BADGE = t["HEADER"], t["LINE"], t["BADGE"]
    GOLD, SOFT = t["GOLD"], t["SOFT"]

F = {
    "zh":     "C:/Windows/Fonts/simsun.ttc",
    "pinyin": "C:/Windows/Fonts/arial.ttf",
    "viet":   "C:/Windows/Fonts/timesbi.ttf",
    "head":   "C:/Windows/Fonts/timesbi.ttf",
    "badge":  "C:/Windows/Fonts/arialbd.ttf",
    "sans":   "C:/Windows/Fonts/arial.ttf",
    "sansb":  "C:/Windows/Fonts/arialbd.ttf",
}
EMOJI = "C:/Windows/Fonts/seguiemj.ttf"
MASCOTS = ["🐼", "🐱", "🐰", "🐻", "🐯", "🐨", "🦊", "🐧"]
_fc = {}
def font(k, s):
    key = (k, s)
    if key not in _fc:
        _fc[key] = ImageFont.truetype(F[k], s)
    return _fc[key]

_ec = {}
def emoji_font(s):
    if s not in _ec:
        _ec[s] = ImageFont.truetype(EMOJI, s)
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
    k = (path, tuple(BG))
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
    veil = Image.new("RGBA", (W, H), BG + (170,))     # mang mo mau theme ~67%
    out = Image.alpha_composite(src.convert("RGBA"), veil).convert("RGB")
    _bg_cache[k] = out
    return out.copy()

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
    tw = text_w(d, header.upper(), hf)
    d.text(((W-tw)//2, 58), header.upper(), font=hf, fill=HEADER)
    cy = 84
    d.line([(W-tw)//2-180, cy, (W-tw)//2-40, cy], fill=LINE, width=3)
    d.line([(W+tw)//2+40, cy, (W+tw)//2+180, cy], fill=LINE, width=3)
    # badge HSK goc duoi phai
    bt = ctx.get("hsk", "HSK1")
    bf = font("badge", 38)
    bw = text_w(d, bt, bf)
    d.rounded_rectangle([W-bw-150, H-95, W-60, H-35], radius=30, fill=BADGE)
    d.text((W-bw-105, H-88), bt, font=bf, fill=(255, 255, 255))
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
        # watermark kenh (cạnh mascot)
        d.text((345, H-92), ctx.get("channel", "Học Tiếng Trung"),
               font=font("sansb", 30), fill=(190, 150, 158))
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

# ---------- DISPATCH ----------
def render_slide(seg, ctx, path, t_now=BIG, reveal_t=None,
                 show_viet=True, n_visible=BIG):
    """t_now/reveal_t: hieu ung chu hien dan (vocab/sentence/practice_a).
       n_visible: so dong hoi thoai da hien (dialogue)."""
    apply_theme(ctx.get("theme", "pink"))
    t = seg["type"]

    if t == "title":
        im, d = base_slide(ctx, header=f'CHINESE · {ctx["hsk"]}')
        h = py_hanzi(d, ctx["hanzi_title"], W//2, 0, zh_size=230, py_size=64, draw=False)
        top = (H-h)//2 - 70
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
        top = (H - (h + vgap + 70))//2 - 20
        py_hanzi(d, seg["hanzi"], W//2, top, zh_size=zh, py_size=py,
                 reveal_t=reveal_t, t_now=t_now)
        if show_viet:
            tw = text_w(d, seg["viet"], vf)
            d.text(((W-tw)//2, top+h+vgap), seg["viet"], font=vf, fill=VIET)

    elif t == "sentence":
        im, d = base_slide(ctx)
        zh, py, vgap = 140, 48, 36
        h = py_hanzi(d, seg["hanzi"], W//2, 0, zh_size=zh, py_size=py, draw=False)
        vf = font("viet", 60)
        top = (H - (h + vgap + 60))//2 - 20
        py_hanzi(d, seg["hanzi"], W//2, top, zh_size=zh, py_size=py,
                 reveal_t=reveal_t, t_now=t_now)
        if show_viet:
            tw = text_w(d, seg["viet"], vf)
            d.text(((W-tw)//2, top+h+vgap), seg["viet"], font=vf, fill=VIET)

    elif t == "dialogue":
        im, d = base_slide(ctx)
        rows = seg["rows"]
        zh_s, py_s, vi_s = 52, 24, 30
        gap_py, gap_vi, gap_turn = 8, 4, 20
        turn_h = py_s + gap_py + zh_s + gap_vi + vi_s + gap_turn
        total = turn_h * len(rows)
        y = (H - total)//2 + 8        # vua khung, khong dung header
        vf = font("viet", vi_s)
        lf = font("sansb", 46)
        for ri, r in enumerate(rows):
            if ri >= n_visible:        # dong chua toi luot -> chua hien
                y += turn_h; continue
            d.text((175, y + py_s), r["sp"] + ".", font=lf, fill=BADGE)
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
