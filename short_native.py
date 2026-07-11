# -*- coding: utf-8 -*-
"""Sinh YouTube Short DOC (9:16, 1080x1920) NATIVE tu 1 cau/tu dat trong bai —
KHONG crop video ngang. Bo cuc toi uu giu chan:
  - hook tren cung (curiosity)  · chu Han KHONG LO o giua
  - pinyin to mau theo thanh dieu ngay tren cau
  - nghia Viet duoi  · doc 2 lan (nghe chu dong) · frame tinh -> LOOP lien mach

Audio: TRICH thang tu video dai bang meta.json -> dung giong goc, khong re-synth.
CLI: python3 short_native.py output/video.mp4 [--at 05:00]
"""
import os, sys, json, re, argparse, subprocess, hashlib
from PIL import Image, ImageDraw, ImageFilter
from pypinyin import pinyin as _py, Style as _PyStyle

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import style_pastel as sp
from seo import split_title

SW, SH = 1080, 1920
# ---- Palette v2: "mực đêm + vàng kim" (nền tối sang, tương phản cao — chuẩn short view cao) ----
BG_TOP   = (24, 20, 18)            # đầu gradient (mực nâu đen)
BG_BOT   = (52, 40, 28)            # cuối gradient (nâu ấm)
GOLD     = (222, 184, 122)         # vàng kim — viền, hook, điểm nhấn
IVORY    = (248, 243, 232)         # chữ Hán chính (ngà sáng)
AMBER    = (255, 205, 110)         # nghĩa Việt (hổ phách sáng, nổi trên nền tối)
SEAL_RED = (196, 48, 40)           # triện đỏ + pill CTA
FOOT_TXT = (255, 244, 230)
MUTED    = (168, 156, 140)
# pinyin tô thanh điệu — bản SÁNG cho nền tối (1 đỏ · 2 cam · 3 xanh lá · 4 xanh dương · 0 xám)
TONE_BRIGHT = {1: (255, 106, 106), 2: (255, 178, 72), 3: (126, 217, 118),
               4: (108, 168, 255), 0: (200, 196, 190)}
# giu ten cu de code cu khong vo
PAPER, INK, VIET, HOOK, BORDER, FOOT, PC = BG_TOP, IVORY, AMBER, GOLD, GOLD, MUTED, MUTED

# ---- Ngon ngu chu co dinh tren video (hook/nut/quiz) — theo lua chon nguoi dung ----
UI_LANG = "vi"                            # "vi" | "en"; make_*() dat theo tham so lang
_STRINGS = {
    "vi": {
        "cta_save":   "Lưu lại để học mỗi ngày",
        "cta_answer": "Ghi đáp án của bạn ở bình luận",
        "quiz_q":     "Câu này nghĩa là gì?",
        "quiz_ans":   "Đáp án",
        "quiz_guess": "Đoán nghĩa trước khi lộ đáp án",
        "hook_vocab": "Từ này rất hay dùng",
        "hook_sent":  "Câu này ai cũng cần",
    },
    "en": {
        "cta_save":   "Save it & learn daily",
        "cta_answer": "Drop your answer in the comments",
        "quiz_q":     "What does this mean?",
        "quiz_ans":   "Answer",
        "quiz_guess": "Guess before the answer shows",
        "hook_vocab": "You'll use this word a lot",
        "hook_sent":  "Everyone needs this line",
    },
}

def _t(key):
    """Tra chuoi UI theo UI_LANG hien tai (fallback tieng Viet)."""
    lang = UI_LANG if UI_LANG in _STRINGS else "vi"
    return _STRINGS[lang].get(key, _STRINGS["vi"][key])

# ky tu rieng cua tieng Viet (dau + chu dac biet) -> phan biet Viet/Anh cho dong nghia
_VN_CHARS = set("ăâđêôơưÀÁẢÃẠẰẮẲẴẶẦẤẨẪẬÈÉẺẼẸỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌỒỐỔỖỘỜỚỞỠỢÙÚỦŨỤỪỨỬỮỰỲÝỶỸỴàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ")

def _detect_lang(text):
    """Doan ngon ngu dong nghia: co ky tu tieng Viet -> 'vi', khong co -> 'en'."""
    for ch in (text or ""):
        if ch in _VN_CHARS:
            return "vi"
    return "en"

def _set_lang(lang, viet_sample=""):
    """lang='auto' -> tu doan theo dong nghia (viet_sample). 'vi'/'en' -> dung nguyen."""
    global UI_LANG
    if lang == "auto":
        UI_LANG = _detect_lang(viet_sample)
    else:
        UI_LANG = lang if lang in _STRINGS else "vi"


def _mmss(s):
    m = re.match(r"^(\d{1,2}):(\d{2})$", s.strip())
    if not m:
        raise ValueError(f"moc thoi gian sai: {s} (dung mm:ss)")
    return int(m.group(1)) * 60 + int(m.group(2))


def load_meta(video):
    p = video + ".meta.json"
    if not os.path.exists(p):
        raise SystemExit(f"khong thay {p} — can meta de chon cau + trich audio")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


_END_PUNCT = "。，！？；：、…．,.!?\"'“”‘’《》()（）"

def _strip_punct(s):
    """Bo dau cau 2 dau -> chu Han hien thi sach (audio van doc nguyen)."""
    return s.strip().strip(_END_PUNCT).strip()


def _n_hanzi(s):
    return len([c for c in s if "一" <= c <= "鿿"])


def _score(seg):
    """Cau NGAN, thuc dung lam Short: 3-12 chu Han, co nghia Viet, khong muc luc.
    Dinh diem ~7 chu -> chu Han to nhat, punchy nhat."""
    if seg.get("type") not in ("sentence", "vocab", "dialogue", "practice_a"):
        return -1
    n = _n_hanzi(seg.get("hanzi", ""))
    if not (3 <= n <= 12):
        return -1
    sc = 10 - abs(n - 7) * 0.7
    if seg.get("viet"):
        sc += 3
    if seg.get("type") == "vocab":
        sc += 1
    return sc


def extract_candidates(content, n=5):
    """Parse content.md -> chon N cau 'dat' nhat lam Short.
    Uu tien cau ngan-vua (5-14 chu Han) co nghia; neu bai toan cau dai -> lay cau ngan nhat.
    Tra ve list [{'hanzi':..., 'viet':...}] (da loai trung, sap theo diem giam dan)."""
    import lesson_parser
    ctx = lesson_parser.parse_lesson(content or "")
    scored = []
    for s in ctx.get("segments", []):
        if s.get("type") not in ("sentence", "vocab", "practice_a"):
            continue
        h = (s.get("hanzi") or "").strip()
        v = (s.get("viet") or "").strip()
        if not _strip_punct(h) or not v:
            continue
        nn = _n_hanzi(h)
        if nn < 3:
            continue
        sc = 10 - abs(nn - 8) * 0.6      # dinh diem ~8 chu (punchy nhung du y)
        if 5 <= nn <= 14:
            sc += 2                       # thuong cau do dai ly tuong cho Short
        if s.get("type") == "vocab":
            sc += 1
        scored.append((sc, nn, h, v))
    scored.sort(key=lambda x: -x[0])
    seen, out = set(), []
    for sc, nn, h, v in scored:
        if h in seen:
            continue
        seen.add(h)
        out.append({"hanzi": h, "viet": v})
        if len(out) >= max(1, n):
            break
    return out


def pick_sentence(segs, at=None):
    cand = [s for s in segs if s.get("hanzi") and s.get("end", 0) > s.get("start", 0)]
    if not cand:
        raise SystemExit("meta khong co cau nao")
    if at is not None:
        return min(cand, key=lambda s: abs(s.get("start", 0) - at))
    best = max(cand, key=_score)
    if _score(best) < 0:              # khong cau nao du ngan -> lay cau ngan nhat co nghia
        best = min(cand, key=lambda s: _n_hanzi(s.get("hanzi", "")) + (0 if s.get("viet") else 100))
    return best


def pinyin_str(hanzi):
    """Chuoi pinyin co dau thanh (cho mo ta/tieu de)."""
    return " ".join(p[0] for p in _py(hanzi, style=_PyStyle.TONE,
                                      errors=lambda x: [c for c in x]))


# ---------- Render frame doc ----------
import math


def _wrap_hanzi(d, text, zf, max_w, gap):
    """Chia deu chu Han thanh so dong it nhat sao cho moi dong vua max_w."""
    chars = list(text)

    def w(chs):
        return sum(sp.text_w(d, c, zf) + gap for c in chs) - gap if chs else 0

    if w(chars) <= max_w:
        return [text]
    for nlines in range(2, 6):
        size = math.ceil(len(chars) / nlines)
        chunks = [chars[i:i + size] for i in range(0, len(chars), size)]
        if all(w(c) <= max_w for c in chunks):
            return ["".join(c) for c in chunks]
    return ["".join(chars)]


# ---------- Canvas v2: nen toi sang trong, tuong phan cao ----------
def _canvas_v2(watermark_ch=None):
    """Nen gradient doc am + quang sang giua + vien vang kep + goc trang tri + watermark Han mo.
    Tra ve (im RGB, draw)."""
    im = Image.new("RGB", (SW, SH), BG_TOP)
    d = ImageDraw.Draw(im)
    for yy in range(SH):                                   # gradient doc
        t = yy / SH
        col = tuple(int(BG_TOP[i] + (BG_BOT[i] - BG_TOP[i]) * t) for i in range(3))
        d.line([(0, yy), (SW, yy)], fill=col)
    glow = Image.new("L", (SW, SH), 0)                     # quang sang am giua man
    ImageDraw.Draw(glow).ellipse([SW//2 - 460, SH//2 - 560, SW//2 + 460, SH//2 + 560], fill=52)
    glow = glow.filter(ImageFilter.GaussianBlur(180))
    im = Image.composite(Image.new("RGB", (SW, SH), (86, 66, 44)), im, glow)
    d = ImageDraw.Draw(im)
    if watermark_ch:                                       # chu Han khong lo mo phia sau
        wm = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
        ImageDraw.Draw(wm).text((SW//2, SH//2 - 30), watermark_ch,
                                font=sp.font("zh", 760), fill=GOLD + (16,), anchor="mm")
        im = Image.alpha_composite(im.convert("RGBA"), wm).convert("RGB")
        d = ImageDraw.Draw(im)
    d.rectangle([30, 30, SW-30, SH-30], outline=GOLD, width=3)      # vien vang kep
    d.rectangle([48, 48, SW-48, SH-48], outline=GOLD + (0,) if False else (120, 96, 62), width=1)
    L = 74
    for cx, cy, dx, dy in [(30, 30, 1, 1), (SW-30, 30, -1, 1), (30, SH-30, 1, -1), (SW-30, SH-30, -1, -1)]:
        d.line([(cx, cy), (cx + dx*L, cy)], fill=GOLD, width=7)      # goc chi vang
        d.line([(cx, cy), (cx, cy + dy*L)], fill=GOLD, width=7)
    return im, d


def _seal(d, text="每日", cx=None, cy=176):
    """Trien do vuong goc tren-phai (2 chu doc)."""
    cx = cx or SW - 128
    s = 116
    d.rounded_rectangle([cx - s//2, cy - s//2, cx + s//2, cy + s//2], radius=14, fill=SEAL_RED)
    f = sp.font("zh", 46)
    chs = list(text[:2])
    yy = cy - (len(chs) * 48) // 2 + 22
    for ch in chs:
        d.text((cx, yy), ch, font=f, fill=IVORY, anchor="mm")
        yy += 48


def _glow_text(im, xy, text, font, fill, glow=(255, 210, 140), radius=16, anchor=None):
    """Ve chu co quang sang mem phia sau (noi khoi tren nen toi)."""
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text(xy, text, font=font, fill=glow + (110,), anchor=anchor)
    layer = layer.filter(ImageFilter.GaussianBlur(radius))
    im.paste(Image.new("RGB", im.size, glow), (0, 0), layer)
    ImageDraw.Draw(im).text(xy, text, font=font, fill=fill, anchor=anchor)


def _pinyin_over_hanzi(im, d, zlines, zf, zsize, py_size, gap, cx, y):
    """Ve pinyin DUNG TREN TUNG CHU HAN (khong phai ca cau don 1 dong).
    Moi chu Han co 1 "o" rong = max(be rong chu Han, be rong am tiet pinyin) de tranh
    chong lan khi pinyin dai hon chu Han. Tra ve tong chieu cao da chiem (cong don y ben ngoai)."""
    pf = sp.font("pinyin", py_size)
    line_h = py_size + 16 + zsize + 28
    for ln in zlines:
        cells = []
        for ch, p, h in sp.flatten(ln):
            w_ch = sp.text_w(d, ch, zf)
            w_py = sp.text_w(d, p, pf) if p else 0
            cells.append((ch, p, w_ch, w_py, max(w_ch, w_py)))
        total = sum(c[4] for c in cells) + gap * (len(cells) - 1) if cells else 0
        x = cx - total // 2
        for ch, p, w_ch, w_py, cellw in cells:
            if p:
                d.text((x + (cellw - w_py) // 2, y), p, font=pf,
                       fill=TONE_BRIGHT[sp._tone_of(p)])
            _glow_text(im, (x + (cellw - w_ch) // 2, y + py_size + 16), ch, zf, IVORY)
            x += cellw + gap
        d = ImageDraw.Draw(im)
        y += line_h
    return line_h * len(zlines)


def _pill(d, cx, cy, text, fill=SEAL_RED, txt=FOOT_TXT, fsize=40):
    f = sp.font("sansb", fsize)
    tw = sp.text_w(d, text, f)
    pad, h = 42, fsize + 44
    d.rounded_rectangle([cx - tw//2 - pad, cy - h//2, cx + tw//2 + pad, cy + h//2],
                        radius=h//2, fill=fill)
    d.text((cx, cy - 4), text, font=f, fill=txt, anchor="mm")


def render_frame(hanzi, viet, hook, path, footer="", note=""):
    """Frame flashcard v2 — nen toi + vang kim, chu Han glow, pinyin sang, an toan safe-zone."""
    disp = _strip_punct(hanzi)
    im, d = _canvas_v2(watermark_ch=(disp[0] if disp else None))
    _seal(d)

    # hook: nhan vang + gach chan ngan (trong safe-zone, y>=220)
    hf = sp.font("viet", 56)
    hy = 236
    for ln in sp.wrap_text(d, hook.upper(), hf, SW - 200)[:2]:
        tw = sp.text_w(d, ln, hf)
        d.text(((SW - tw) // 2, hy), ln, font=hf, fill=GOLD)
        hy += hf.size + 8
    d.line([(SW//2 - 70, hy + 14), (SW//2 + 70, hy + 14)], fill=SEAL_RED, width=6)

    # khoi giua
    max_w, gap = SW - 170, 16
    zsize = sp.fit_zh_size(d, disp, max_size=250, min_size=110, max_w=max_w, char_gap=gap)
    zf = sp.font("zh", zsize)
    zlines = _wrap_hanzi(d, disp, zf, max_w, gap)
    py_size = max(48, int(zsize * 0.40))
    line_h = py_size + 16 + zsize + 28          # pinyin + chu Han tinh chung 1 dong
    vf = sp.font("viet", 62)
    vlines = sp.wrap_text(d, viet, vf, max_w)[:3] if viet else []
    nf = sp.font("sans", 40)
    nlines = sp.wrap_text(d, note, nf, max_w)[:2] if note else []
    block_h = len(zlines) * line_h + 42 + len(vlines) * (vf.size + 12) \
              + (len(nlines) * (nf.size + 8) + 26 if nlines else 0)
    y = max(430, (SH - block_h) // 2 - 20)

    y += _pinyin_over_hanzi(im, d, zlines, zf, zsize, py_size, gap, SW // 2, y)
    d = ImageDraw.Draw(im)
    y += 30
    for ln in vlines:                                       # nghia Viet — ho phach sang
        d.text((SW // 2, y), ln, font=vf, fill=AMBER, anchor="ma")
        y += vf.size + 12
    if nlines:                                              # ghi chu cach dung (tuy chon)
        y += 22
        for ln in nlines:
            d.text((SW // 2, y), ln, font=nf, fill=MUTED, anchor="ma")
            y += nf.size + 8

    _pill(d, SW // 2, SH - 300, footer or _t("cta_save"))
    im.save(path)
    return path


# ---------- QUIZ (do nghia): hoi -> dem nguoc -> dap an -> loop ----------
SLOT_H = 250


def render_quiz_frame(hanzi, viet, path, phase, count=None, hook=None):
    """phase: 'q' (hoi, an nghia) | 'count' (dem nguoc) | 'reveal' (lo nghia).
    Cung phong cach v2 voi flashcard; pinyin+Han GIU NGUYEN vi tri -> chuyen canh muot + loop."""
    disp = _strip_punct(hanzi)
    im, d = _canvas_v2(watermark_ch=(disp[0] if disp else None))
    _seal(d, "考考")                                       # trien "kiem tra"

    # nhan tren: hoi (vang) / dap an (xanh la sang)
    label = _t("quiz_ans").upper() if phase == "reveal" else (hook or _t("quiz_q")).upper()
    lcol = TONE_BRIGHT[3] if phase == "reveal" else GOLD
    hf = sp.font("viet", 56)
    hy = 236
    for ln in sp.wrap_text(d, label, hf, SW - 200)[:2]:
        d.text((SW // 2, hy), ln, font=hf, fill=lcol, anchor="ma")
        hy += hf.size + 8
    d.line([(SW//2 - 70, hy + 14), (SW//2 + 70, hy + 14)], fill=SEAL_RED, width=6)

    max_w, gap = SW - 170, 16
    zsize = sp.fit_zh_size(d, disp, max_size=250, min_size=110, max_w=max_w, char_gap=gap)
    zf = sp.font("zh", zsize)
    zlines = _wrap_hanzi(d, disp, zf, max_w, gap)
    py_size = max(48, int(zsize * 0.40))
    line_h = py_size + 16 + zsize + 28          # pinyin + chu Han tinh chung 1 dong
    block_h = len(zlines) * line_h + 30 + SLOT_H
    y = max(430, (SH - block_h) // 2 + 10)

    y += _pinyin_over_hanzi(im, d, zlines, zf, zsize, py_size, gap, SW // 2, y)
    d = ImageDraw.Draw(im)
    y += 26
    slot_top = y

    if phase == "q":
        d.text((SW // 2, slot_top + 66), _t("quiz_guess"),
               font=sp.font("sansb", 44), fill=MUTED, anchor="ma")
        d.text((SW // 2, slot_top + 130), "? ? ?", font=sp.font("badge", 64),
               fill=GOLD, anchor="ma")
    elif phase == "count":
        r = 96
        cx, cy = SW // 2, slot_top + SLOT_H // 2 - 6
        d.ellipse([cx - r - 10, cy - r - 10, cx + r + 10, cy + r + 10], outline=GOLD, width=5)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=SEAL_RED)
        d.text((cx, cy - 6), str(count), font=sp.font("badge", 124), fill=IVORY, anchor="mm")
    else:  # reveal
        vf = sp.font("viet", 62)
        vy = slot_top + 8
        for ln in (sp.wrap_text(d, viet, vf, max_w)[:3] if viet else []):
            d.text((SW // 2, vy), ln, font=vf, fill=AMBER, anchor="ma")
            vy += vf.size + 12

    _pill(d, SW // 2, SH - 300,
          _t("cta_save") if phase == "reveal" else _t("cta_answer"))
    im.save(path)
    return path


def _silence_concat(parts, out):
    """parts: list ('sil', giay) hoac ('clip', path) -> concat thanh wav 44100 mono."""
    inputs, labels = [], []
    for i, (kind, val) in enumerate(parts):
        if kind == "sil":
            inputs += ["-f", "lavfi", "-t", f"{val:.2f}", "-i", "anullsrc=r=44100:cl=mono"]
        else:
            inputs += ["-i", val]
        labels.append(f"[{i}]")
    fc = "".join(labels) + f"concat=n={len(labels)}:v=0:a=1[a]"
    subprocess.run(["ffmpeg", "-y", *inputs, "-filter_complex", fc,
                    "-map", "[a]", "-ac", "1", "-ar", "44100", out],
                   check=True, capture_output=True)


def _compose_frames(items, audio, out):
    """items: [(png, giay)] -> video (moi anh hien 'giay') + ghep audio. Frame tinh -> loop muot."""
    lst = out + ".concat.txt"
    with open(lst, "w", encoding="utf-8") as f:
        for p, dur in items:
            f.write(f"file '{os.path.abspath(p)}'\nduration {dur:.3f}\n")
        f.write(f"file '{os.path.abspath(items[-1][0])}'\n")   # lap frame cuoi (concat demuxer)
    try:
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                        "-i", audio, "-c:v", "libx264", "-tune", "stillimage",
                        "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                        "-r", "30", "-c:a", "aac", "-b:a", "160k", "-shortest",
                        "-vf", f"scale={SW}:{SH}", out],
                       check=True, capture_output=True)
    finally:
        if os.path.exists(lst):
            os.remove(lst)


def make_quiz_from_text(hanzi, viet="", voice="zh-CN-XiaoxiaoNeural", hook=None,
                        out_dir=None, cta=None, rate="-8%", name=None, count_from=3,
                        lang="auto"):
    """Sinh Short QUIZ do nghia: hoi (an nghia) -> dem nguoc -> lo dap an. Tu TTS (edge free)."""
    import generate
    hanzi = (hanzi or "").strip()
    if not _strip_punct(hanzi):
        raise ValueError("cau rong")
    viet = (viet or "").strip()
    _set_lang(lang, viet)                                  # 'auto' -> doan theo dong nghia
    voice = (voice or "zh-CN-XiaoxiaoNeural").split(":")[-1]
    py = pinyin_str(hanzi)
    out_dir = out_dir or "."
    os.makedirs(out_dir, exist_ok=True)
    base = name or ("quiz_" + hashlib.md5((hanzi + voice).encode("utf-8")).hexdigest()[:10])
    out = os.path.join(out_dir, base + ".mp4")
    raw = os.path.join(out_dir, f"_qr_{base}.mp3")
    sent = os.path.join(out_dir, f"_qs_{base}.wav")
    audio = os.path.join(out_dir, f"_qa_{base}.wav")
    fq = os.path.join(out_dir, f"_qfq_{base}.png")
    fr = os.path.join(out_dir, f"_qfr_{base}.png")
    fcs = [os.path.join(out_dir, f"_qfc{n}_{base}.png") for n in range(count_from, 0, -1)]
    tmp = [raw, sent, audio, fq, fr, *fcs]
    gap, tail = 0.4, 1.0
    try:
        generate.synth(hanzi, voice, raw, rate=rate)          # edge free
        _to_wav(raw, sent)
        d_sent = _dur(sent)
        # audio: doc cau (khi hoi) + gap + [dem nguoc: im lang] + doc lai cau (khi lo dap an) + tail
        _silence_concat([("clip", sent), ("sil", gap), ("sil", float(count_from)),
                         ("clip", sent), ("sil", tail)], audio)
        render_quiz_frame(hanzi, viet, fq, "q", hook=hook)
        for i, n in enumerate(range(count_from, 0, -1)):
            render_quiz_frame(hanzi, viet, fcs[i], "count", count=n, hook=hook)
        render_quiz_frame(hanzi, viet, fr, "reveal", hook=hook)
        items = ([(fq, d_sent + gap)]
                 + [(fcs[i], 1.0) for i in range(count_from)]
                 + [(fr, d_sent + tail)])
        _compose_frames(items, audio, out)
    finally:
        for f in tmp:
            if os.path.exists(f):
                os.remove(f)

    title = f"{_strip_punct(hanzi)} nghĩa là gì? Đoán thử! | Tiếng Trung mỗi ngày #Shorts"
    desc = (f"Đố bạn: {hanzi} nghĩa là gì?\n{py}\nĐáp án: {viet}\n\n"
            "#hoctiengtrung #dovuitiengtrung #shorts #tiengtrung #chinese")
    return {"file": out, "title": title, "desc": desc, "hook": hook or _t("quiz_q"),
            "hanzi": hanzi, "pinyin": py, "viet": viet, "dur": round(_dur(out), 2)}


# ---------- Audio: trich cau tu video + doc 2 lan + loop ----------
def _dur(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "quiet", "-of", "csv=p=0",
         "-show_entries", "format=duration", path]).decode().strip()
    return float(out or 0)


def _extract_audio(video, start, dur, out):
    subprocess.run(["ffmpeg", "-y", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}",
                    "-i", video, "-vn", "-ac", "1", "-ar", "44100",
                    "-c:a", "pcm_s16le", out],
                   check=True, capture_output=True)


def _to_wav(src, out):
    """Chuan hoa audio bat ky -> wav 44100 mono (de concat khong loi sample-rate)."""
    subprocess.run(["ffmpeg", "-y", "-i", src, "-vn", "-ac", "1", "-ar", "44100",
                    "-c:a", "pcm_s16le", out],
                   check=True, capture_output=True)


def _build_audio(sent_wav, out, reads=2, lead=0.7, gap=0.55, tail=0.9):
    """lead-silence + (cau + gap)*reads + tail-silence -> loop-friendly."""
    inputs, labels, idx = [], [], 0

    def sil(t):
        nonlocal idx
        inputs.extend(["-f", "lavfi", "-t", f"{t:.2f}", "-i", "anullsrc=r=44100:cl=mono"])
        labels.append(f"[{idx}]"); idx += 1

    def clip():
        nonlocal idx
        inputs.extend(["-i", sent_wav])
        labels.append(f"[{idx}]"); idx += 1

    sil(lead)
    for i in range(reads):
        clip()
        sil(gap if i < reads - 1 else tail)
    fc = "".join(labels) + f"concat=n={len(labels)}:v=0:a=1[a]"
    subprocess.run(["ffmpeg", "-y", *inputs, "-filter_complex", fc,
                    "-map", "[a]", "-ac", "1", "-ar", "44100", out],
                   check=True, capture_output=True)


def _compose(frame_png, audio_wav, out):
    subprocess.run(["ffmpeg", "-y", "-loop", "1", "-i", frame_png, "-i", audio_wav,
                    "-c:v", "libx264", "-tune", "stillimage", "-preset", "medium",
                    "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30",
                    "-c:a", "aac", "-b:a", "160k", "-shortest",
                    "-vf", f"scale={SW}:{SH}", out],
                   check=True, capture_output=True)


def _hook_for(seg):
    if seg.get("type") == "vocab":
        return _t("hook_vocab")
    return _t("hook_sent")


def make_short(video, out_dir=None, cta=None, at=None, reads=2, lang="auto"):
    """Sinh 1 Short DOC native tu bai. Tra ve {file,title,desc,hook,start,dur}."""
    video = os.path.abspath(video)
    meta = load_meta(video)
    _han_title, viet_title = split_title(meta.get("title", ""))
    at_sec = float(_mmss(at)) if at else None
    seg = pick_sentence(meta["segments"], at_sec)
    hanzi = seg["hanzi"].strip()
    viet = (seg.get("viet") or "").strip()
    _set_lang(lang, viet)                                  # 'auto' -> doan theo dong nghia
    hook = _hook_for(seg)
    py = pinyin_str(hanzi)

    out_dir = out_dir or os.path.dirname(video)
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(video))[0]
    out = os.path.join(out_dir, f"{base}_short.mp4")
    frame = os.path.join(out_dir, f"_sf_{base}.png")
    sent = os.path.join(out_dir, f"_sa_{base}.wav")
    audio = os.path.join(out_dir, f"_saud_{base}.wav")

    st = float(seg.get("start", 0))
    sent_dur = min(6.0, max(0.8, float(seg.get("end", st + 3)) - st))
    try:
        _extract_audio(video, st, sent_dur, sent)
        _build_audio(sent, audio, reads=reads)
        render_frame(hanzi, viet, hook, frame, footer=cta or _t("cta_save"))
        _compose(frame, audio, out)
    finally:
        for f in (frame, sent, audio):
            if os.path.exists(f):
                os.remove(f)

    title = f"{_strip_punct(hanzi)} nghĩa là gì? | {viet[:40]} | Tiếng Trung mỗi ngày #Shorts"
    desc = (f"{hanzi}\n{py}\n{viet}\n\n"
            f"🎧 Bài đầy đủ ({viet_title}) có trên kênh!\n"
            "#hoctiengtrung #tuvungtiengtrung #shorts #tiengtrung #chinese")
    return {"file": out, "title": title, "desc": desc, "hook": hook,
            "hanzi": hanzi, "pinyin": py, "viet": viet,
            "start": round(st, 3), "dur": round(_dur(out), 2)}


def make_short_from_text(hanzi, viet="", voice="zh-CN-XiaoxiaoNeural", hook=None,
                         out_dir=None, cta=None, reads=2, rate="-8%", name=None, note="",
                         lang="auto"):
    """Sinh 1 Short DOC native TRUC TIEP tu 1 cau (KHONG can video dai).
    Tu tong hop giong bang generate.synth (edge free mac dinh). Tra ve dict giong make_short."""
    import generate
    hanzi = (hanzi or "").strip()
    if not _strip_punct(hanzi):
        raise ValueError("cau rong")
    viet = (viet or "").strip()
    _set_lang(lang, viet)                                  # 'auto' -> doan theo dong nghia
    voice = (voice or "zh-CN-XiaoxiaoNeural").split(":")[-1]   # bo tien to 'edge:' neu co
    hook = hook or _hook_for({"type": "sentence"})
    py = pinyin_str(hanzi)

    out_dir = out_dir or "."
    os.makedirs(out_dir, exist_ok=True)
    base = name or ("short_" + hashlib.md5((hanzi + voice).encode("utf-8")).hexdigest()[:10])
    out = os.path.join(out_dir, base + ".mp4")
    frame = os.path.join(out_dir, f"_sf_{base}.png")
    raw = os.path.join(out_dir, f"_sr_{base}.mp3")
    sent = os.path.join(out_dir, f"_sa_{base}.wav")
    audio = os.path.join(out_dir, f"_saud_{base}.wav")
    try:
        generate.synth(hanzi, voice, raw, rate=rate)          # edge-tts (khong can key)
        _to_wav(raw, sent)
        _build_audio(sent, audio, reads=reads)
        render_frame(hanzi, viet, hook, frame,
                     footer=cta or _t("cta_save"), note=note)
        _compose(frame, audio, out)
    finally:
        for f in (frame, raw, sent, audio):
            if os.path.exists(f):
                os.remove(f)

    title = f"{_strip_punct(hanzi)} nghĩa là gì? | {viet[:40]} | Tiếng Trung mỗi ngày #Shorts"
    desc = (f"{hanzi}\n{py}\n{viet}\n\n"
            "#hoctiengtrung #tuvungtiengtrung #shorts #tiengtrung #chinese")
    return {"file": out, "title": title, "desc": desc, "hook": hook,
            "hanzi": hanzi, "pinyin": py, "viet": viet, "dur": round(_dur(out), 2)}


def make_short_from_lines(lines, voice="zh-CN-XiaoxiaoNeural", hook=None,
                          out_dir=None, cta=None, reads=2, rate="-8%", name=None,
                          lang="auto"):
    """GOP nhieu cau thanh 1 Short: cau 1 doc 'reads' lan -> next cau 2 ... -> het.
    lines: list ('汉字','nghia') hoac ('汉字','nghia','ghi chu'). Moi cau 1 khung + audio rieng,
    noi lai thanh 1 video duy nhat (frame tinh, loop muot)."""
    import generate
    norm = []
    for it in lines:
        if isinstance(it, (list, tuple)):
            hz = (it[0] or "").strip()
            vi = (it[1].strip() if len(it) > 1 and it[1] else "")
            nt = (it[2].strip() if len(it) > 2 and it[2] else "")
        else:
            hz, vi, nt = str(it).strip(), "", ""
        if _strip_punct(hz):
            norm.append((hz, vi, nt))
    if not norm:
        raise ValueError("khong co cau nao")
    _set_lang(lang, norm[0][1])
    voice = (voice or "zh-CN-XiaoxiaoNeural").split(":")[-1]

    out_dir = out_dir or "."
    os.makedirs(out_dir, exist_ok=True)
    key = "|".join(h for h, _, _ in norm) + voice
    base = name or ("multi_" + hashlib.md5(key.encode("utf-8")).hexdigest()[:10])
    out = os.path.join(out_dir, base + ".mp4")

    tmp, items, audio_parts = [], [], []
    try:
        for i, (hz, vi, nt) in enumerate(norm):
            hk = hook or _hook_for({"type": "sentence"})
            frame = os.path.join(out_dir, f"_mf_{base}_{i}.png")
            raw   = os.path.join(out_dir, f"_mr_{base}_{i}.mp3")
            sent  = os.path.join(out_dir, f"_ms_{base}_{i}.wav")
            aud   = os.path.join(out_dir, f"_ma_{base}_{i}.wav")
            tmp += [frame, raw, sent, aud]
            generate.synth(hz, voice, raw, rate=rate)
            _to_wav(raw, sent)
            _build_audio(sent, aud, reads=reads)
            render_frame(hz, vi, hk, frame, footer=cta or _t("cta_save"), note=nt)
            items.append((frame, _dur(aud)))
            audio_parts.append(("clip", aud))
        full_a = os.path.join(out_dir, f"_mfull_{base}.wav")
        tmp.append(full_a)
        _silence_concat(audio_parts, full_a)
        _compose_frames(items, full_a, out)
    finally:
        for f in tmp:
            if os.path.exists(f):
                os.remove(f)

    head = _strip_punct(norm[0][0])
    title = f"{head}… | {len(norm)} câu tiếng Trung | Tiếng Trung mỗi ngày #Shorts"
    desc = "\n".join(f"{h}  {pinyin_str(h)}  {v}" for h, v, _ in norm) + \
           "\n\n#hoctiengtrung #tuvungtiengtrung #shorts #tiengtrung #chinese"
    return {"file": out, "title": title, "desc": desc,
            "count": len(norm), "dur": round(_dur(out), 2)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?", help="video dai (.mp4) — de trong neu dung --text")
    ap.add_argument("--at", help="moc mm:ss (chon cau gan moc do)")
    ap.add_argument("--text", help="'汉字 | nghia' — sinh Short truc tiep, khong can video")
    ap.add_argument("--voice", default="zh-CN-XiaoxiaoNeural")
    ap.add_argument("--reads", type=int, default=2)
    args = ap.parse_args()
    if args.text:
        hz, _, vi = args.text.partition("|")
        r = make_short_from_text(hz.strip(), vi.strip(), voice=args.voice, reads=args.reads)
    else:
        r = make_short(os.path.abspath(args.video), at=args.at, reads=args.reads)
    print("OK ->", os.path.basename(r["file"]), f"({r['dur']}s)")
    print("   ", r["hanzi"], "·", r["pinyin"], "·", r["viet"])


if __name__ == "__main__":
    main()
