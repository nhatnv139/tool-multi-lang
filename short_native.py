# -*- coding: utf-8 -*-
"""Sinh YouTube Short DOC (9:16, 1080x1920) NATIVE tu 1 cau/tu dat trong bai —
KHONG crop video ngang. Bo cuc toi uu giu chan:
  - hook tren cung (curiosity)  · chu Han KHONG LO o giua
  - pinyin to mau theo thanh dieu ngay tren cau
  - nghia Viet duoi  · doc 2 lan (nghe chu dong) · frame tinh -> LOOP lien mach

Audio: TRICH thang tu video dai bang meta.json -> dung giong goc, khong re-synth.
CLI: python3 short_native.py output/video.mp4 [--at 05:00]
"""
import os, sys, json, re, argparse, subprocess, hashlib, math
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
PY_MONO = None                            # None = pinyin tô thanh điệu; (r,g,b) = pinyin 1 màu

_PY_COLORS = {"white": (246, 246, 240), "gold": (255, 212, 120), "cyan": (150, 222, 236),
              "green": (150, 226, 150), "amber": (255, 196, 96), "grey": (200, 196, 190)}
def _parse_color(v):
    """v: 'tone'/None -> None (tô thanh điệu); tên/hex -> (r,g,b)."""
    if not v or str(v).lower() in ("tone", "auto", ""):
        return None
    v = str(v).strip().lower()
    if v in _PY_COLORS:
        return _PY_COLORS[v]
    if v.startswith("#") and len(v) == 7:
        try:
            return tuple(int(v[i:i+2], 16) for i in (1, 3, 5))
        except ValueError:
            pass
    return None
_STRINGS = {
    "vi": {
        "cta_save":   "Lưu lại để học mỗi ngày",
        "cta_answer": "Ghi đáp án của bạn ở bình luận",
        "quiz_q":     "Câu này nghĩa là gì?",
        "quiz_ans":   "Đáp án",
        "quiz_guess": "Đoán nghĩa trước khi lộ đáp án",
        "hook_vocab": "Từ này rất hay dùng",
        "hook_sent":  "Câu này ai cũng cần",
        "lbl_vocab":  "TỪ MỚI HÔM NAY",
        "lbl_pattern":"MẪU CÂU HAY DÙNG",
        "lbl_example":"Ví dụ",
        # --- SEO title/desc/hashtag (theo ngôn ngữ dòng nghĩa) ---
        "brand":      "Tiếng Trung mỗi ngày",
        "t_quiz":     "{hz} nghĩa là gì? Đoán thử!",
        "t_meaning":  "{hz} nghĩa là gì?",
        "t_vocab":    "{word} = {mean} | Từ mới tiếng Trung",
        "t_pattern":  "{pat} | Mẫu câu tiếng Trung",
        "t_combine":  "{n} câu tiếng Trung: {topic}",
        "t_combine_plain": "{n} câu tiếng Trung ai cũng cần",
        "d_quiz":     "Đố bạn: {hz} nghĩa là gì?\n{py}\nĐáp án: {vi}",
        "tags_quiz":  "#hoctiengtrung #dovuitiengtrung #shorts #tiengtrung #chinese",
        "tags_vocab": "#hoctiengtrung #tuvungtiengtrung #tumoi #shorts #tiengtrung",
        "tags_patt":  "#hoctiengtrung #maucau #ngucaptiengtrung #shorts #tiengtrung",
        "tags_def":   "#hoctiengtrung #tiengtrung #shorts #chinese #learnchinese",
    },
    "en": {
        "cta_save":   "Save it & learn daily",
        "cta_answer": "Drop your answer in the comments",
        "quiz_q":     "What does this mean?",
        "quiz_ans":   "Answer",
        "quiz_guess": "Guess before the answer shows",
        "hook_vocab": "You'll use this word a lot",
        "hook_sent":  "Everyone needs this line",
        "lbl_vocab":  "WORD OF THE DAY",
        "lbl_pattern":"USEFUL SENTENCE PATTERN",
        "lbl_example":"Example",
        "brand":      "Learn Chinese Daily",
        "t_quiz":     "What does {hz} mean? Can you guess?",
        "t_meaning":  "What does {hz} mean?",
        "t_vocab":    "{word} = {mean} | Chinese Word of the Day",
        "t_pattern":  "{pat} | Useful Chinese Sentence Pattern",
        "t_combine":  "{n} Chinese Sentences: {topic}",
        "t_combine_plain": "{n} Chinese Sentences You Should Know",
        "d_quiz":     "Quiz: what does {hz} mean?\n{py}\nAnswer: {vi}",
        "tags_quiz":  "#LearnChinese #ChineseQuiz #Shorts #Chinese #Mandarin",
        "tags_vocab": "#LearnChinese #ChineseVocab #WordOfTheDay #Shorts #Chinese",
        "tags_patt":  "#LearnChinese #ChineseGrammar #SentencePattern #Shorts #Chinese",
        "tags_def":   "#LearnChinese #Chinese #Shorts #Mandarin #HSK",
    },
}

def _t(key):
    """Tra chuoi UI theo UI_LANG hien tai (fallback tieng Viet)."""
    lang = UI_LANG if UI_LANG in _STRINGS else "vi"
    return _STRINGS[lang].get(key, _STRINGS["vi"][key])

def _tf(key, **kw):
    """Nhu _t nhung format placeholder ({hz},{vi}...)."""
    return _t(key).format(**kw)

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


# ---------- HE THONG SKIN (nhieu phong cach) ----------
# Moi skin: bg gradient, mau nhan(accent), chu chinh(main), nghia(meaning), trien/CTA(seal),
# phu(muted), tone pinyin (sang cho nen toi / dam cho nen sang), decor (kieu ve nen+vien).
_SEAL_TXT = (250, 245, 236)                 # chu tren trien: LUON sang (do nen do)
_TONE_DARK = {1: (255, 106, 106), 2: (255, 178, 72), 3: (126, 217, 118),
              4: (108, 168, 255), 0: (200, 196, 190)}       # cho nen TOI
_TONE_LIGHT = {1: (206, 40, 44), 2: (200, 120, 26), 3: (40, 140, 74),
               4: (36, 100, 190), 0: (120, 120, 125)}       # cho nen SANG

SKINS = {
    "ink": dict(label="Mực đêm vàng kim", light=False, glow=True, glow_col=(255, 210, 140), decor="ink",
                bg=[(24, 20, 18), (52, 40, 28)], accent=(222, 184, 122), main=(248, 243, 232),
                meaning=(255, 205, 110), seal=(196, 48, 40), muted=(168, 156, 140), tone=_TONE_DARK),
    "cute": dict(label="Sáng dễ thương", light=True, glow=False, decor="cute",
                 bg=[(246, 250, 238), (236, 245, 226)], accent=(107, 163, 74), main=(58, 74, 56),
                 meaning=(223, 118, 58), seal=(226, 92, 76), muted=(122, 134, 112), tone=_TONE_LIGHT),
    "paper": dict(label="Giấy cổ thư pháp", light=True, glow=False, decor="paper",
                  bg=[(245, 237, 221), (232, 219, 195)], accent=(150, 60, 40), main=(52, 42, 34),
                  meaning=(150, 60, 40), seal=(168, 50, 40), muted=(132, 116, 96), tone=_TONE_LIGHT),
    "white": dict(label="Minimalist trắng", light=True, glow=False, decor="white",
                  bg=[(252, 252, 250), (245, 245, 243)], accent=(228, 88, 78), main=(28, 28, 30),
                  meaning=(228, 88, 78), seal=(228, 88, 78), muted=(150, 150, 155), tone=_TONE_LIGHT),
    "gradient": dict(label="Gradient hiện đại", light=False, glow=True, glow_col=(255, 250, 214), decor="gradient",
                     bg=[(96, 66, 190), (206, 84, 146)], accent=(255, 232, 128), main=(255, 255, 255),
                     meaning=(255, 236, 156), seal=(255, 92, 112), muted=(232, 222, 244), tone=_TONE_DARK),
    "sakura": dict(label="Anh đào hồng", light=True, glow=False, decor="sakura",
                   bg=[(255, 244, 246), (250, 226, 232)], accent=(214, 96, 130), main=(74, 44, 54),
                   meaning=(202, 78, 118), seal=(216, 84, 112), muted=(178, 138, 150), tone=_TONE_LIGHT),
    "night": dict(label="Đêm sao lấp lánh", light=False, glow=True, glow_col=(150, 190, 255), decor="night",
                  bg=[(18, 22, 46), (44, 36, 78)], accent=(255, 214, 130), main=(240, 244, 255),
                  meaning=(255, 224, 150), seal=(232, 96, 122), muted=(162, 170, 205), tone=_TONE_DARK),
    "ocean": dict(label="Biển ngọc bích", light=False, glow=True, glow_col=(180, 255, 240), decor="ocean",
                  bg=[(12, 92, 108), (26, 152, 150)], accent=(255, 240, 178), main=(255, 255, 255),
                  meaning=(226, 255, 242), seal=(255, 112, 96), muted=(198, 228, 226), tone=_TONE_DARK),
    "sunset": dict(label="Hoàng hôn ấm", light=False, glow=True, glow_col=(255, 224, 156), decor="sunset",
                   bg=[(250, 146, 84), (194, 72, 116)], accent=(255, 246, 206), main=(255, 255, 255),
                   meaning=(255, 240, 194), seal=(176, 44, 72), muted=(255, 224, 212), tone=_TONE_DARK),
    "bamboo": dict(label="Trúc xanh thuỷ mặc", light=True, glow=False, decor="bamboo",
                   bg=[(238, 244, 234), (220, 233, 214)], accent=(66, 122, 84), main=(38, 58, 44),
                   meaning=(64, 116, 78), seal=(176, 62, 50), muted=(120, 148, 124), tone=_TONE_LIGHT),
    "royal": dict(label="Cung đình đỏ vàng", light=False, glow=True, glow_col=(255, 218, 150), decor="royal",
                  bg=[(122, 20, 24), (70, 12, 16)], accent=(240, 202, 112), main=(255, 246, 226),
                  meaning=(250, 214, 132), seal=(220, 66, 50), muted=(214, 162, 130), tone=_TONE_DARK),
    "chalk": dict(label="Bảng phấn lớp học", light=False, glow=False, decor="chalk",
                  bg=[(40, 56, 50), (30, 44, 40)], accent=(255, 240, 182), main=(246, 246, 238),
                  meaning=(200, 238, 202), seal=(228, 130, 120), muted=(172, 188, 178), tone=_TONE_DARK),
    "notebook": dict(label="Vở kẻ ngang học trò", light=True, glow=False, decor="notebook",
                     bg=[(253, 251, 243), (248, 245, 234)], accent=(64, 110, 190), main=(40, 46, 66),
                     meaning=(210, 76, 66), seal=(226, 98, 88), muted=(128, 132, 148), tone=_TONE_LIGHT),
    "grid": dict(label="Giấy ô ly caro", light=True, glow=False, decor="grid",
                 bg=[(250, 252, 255), (240, 246, 253)], accent=(58, 120, 196), main=(36, 48, 72),
                 meaning=(214, 84, 72), seal=(230, 104, 92), muted=(130, 140, 158), tone=_TONE_LIGHT),
    "comic": dict(label="Comic pop-art", light=True, glow=False, decor="comic",
                  bg=[(255, 247, 222), (255, 235, 188)], accent=(228, 60, 68), main=(30, 30, 38),
                  meaning=(228, 60, 68), seal=(42, 96, 200), muted=(146, 134, 116), tone=_TONE_LIGHT),
    "candy": dict(label="Kẹo ngọt pastel", light=True, glow=False, decor="candy",
                  bg=[(255, 242, 248), (243, 231, 255)], accent=(236, 118, 170), main=(92, 72, 112),
                  meaning=(150, 108, 210), seal=(236, 118, 170), muted=(180, 162, 192), tone=_TONE_LIGHT),
    "memphis": dict(label="Memphis 80s", light=True, glow=False, decor="memphis",
                    bg=[(250, 248, 244), (242, 238, 230)], accent=(255, 88, 118), main=(38, 38, 46),
                    meaning=(36, 164, 196), seal=(255, 88, 118), muted=(152, 148, 142), tone=_TONE_LIGHT),
    "kawaii": dict(label="Kawaii mây cầu vồng", light=True, glow=False, decor="kawaii",
                   bg=[(255, 247, 250), (236, 246, 255)], accent=(255, 136, 172), main=(92, 80, 104),
                   meaning=(150, 118, 210), seal=(255, 136, 172), muted=(188, 172, 198), tone=_TONE_LIGHT),
    "neon": dict(label="Neon synthwave", light=False, glow=True, glow_col=(0, 255, 220), decor="neon",
                 bg=[(18, 16, 36), (34, 20, 52)], accent=(0, 232, 204), main=(240, 244, 255),
                 meaning=(255, 118, 210), seal=(255, 88, 150), muted=(150, 150, 196), tone=_TONE_DARK),
}
CUR_SKIN = "ink"

def _apply_skin(name):
    """Dat bang mau global theo skin (cac ham render dung GOLD/IVORY/AMBER/... nhu cu)."""
    global CUR_SKIN, BG_TOP, BG_BOT, GOLD, IVORY, AMBER, SEAL_RED, MUTED, TONE_BRIGHT, PY_MONO
    PY_MONO = None                        # reset: mỗi short tự đặt lại (chống rò rỉ giữa các format)
    CUR_SKIN = name if name in SKINS else "ink"
    s = SKINS[CUR_SKIN]
    BG_TOP, BG_BOT = s["bg"]
    GOLD, IVORY, AMBER = s["accent"], s["main"], s["meaning"]
    SEAL_RED, MUTED, TONE_BRIGHT = s["seal"], s["muted"], s["tone"]


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


# ---------- Anh nen tuy chon (cover-fit 1080x1920 + toi + mo nhe) ----------
def _prep_bg_short(path):
    """Doc anh nguoi dung tai len -> cover-fit 1080x1920, lam toi + mo nhe de chu doc ro.
    Tra ve im RGB kich thuoc (SW, SH)."""
    src = Image.open(path).convert("RGB")
    sw, sh = src.size
    scale = max(SW / sw, SH / sh)                          # cover: phu kin khung, khong vien
    src = src.resize((max(1, int(sw*scale)), max(1, int(sh*scale))), Image.LANCZOS)
    nw, nh = src.size
    src = src.crop(((nw-SW)//2, (nh-SH)//2, (nw-SW)//2+SW, (nh-SH)//2+SH))  # crop giua
    src = src.filter(ImageFilter.GaussianBlur(6))          # mo nhe -> chu noi hon
    # scrim toi kieu "bang": DAM o TREN (hook) + DUOI (nghia/CTA), NHAT o giua (chu Han chinh
    # co glow rieng, de anh nen van hien). Robust cho moi anh tai len.
    scrim = Image.new("L", (SW, SH), 0)
    ds = ImageDraw.Draw(scrim)
    for yy in range(SH):
        r = yy / SH
        base = 108
        top_extra = int(80 * max(0.0, 1 - r / 0.22))       # +80 dinh -> 0 tai 22% (bao ve hook)
        bot_extra = int(95 * max(0.0, (r - 0.55) / 0.45))  # 0 den 55% -> +95 duoi (nghia/CTA)
        a = min(225, base + top_extra + bot_extra)
        ds.line([(0, yy), (SW, yy)], fill=a)
    black = Image.new("RGB", (SW, SH), (14, 11, 9))
    return Image.composite(black, src, scrim)


# ---------- Nen + vien + trang tri theo SKIN ----------
def _grad_bg(top, bot):
    """Anh RGB gradient doc top->bot, kich thuoc (SW, SH)."""
    im = Image.new("RGB", (SW, SH), top)
    d = ImageDraw.Draw(im)
    for yy in range(SH):
        t = yy / SH
        d.line([(0, yy), (SW, yy)], fill=tuple(int(top[i] + (bot[i]-top[i])*t) for i in range(3)))
    return im

def _border_gold(d, col=None, w=3):
    """Vien kep + 4 goc chi (kieu ink/anh nen)."""
    c = col or GOLD
    d.rectangle([30, 30, SW-30, SH-30], outline=c, width=w)
    d.rectangle([48, 48, SW-48, SH-48], outline=(120, 96, 62), width=1)
    L = 74
    for cx, cy, dx, dy in [(30, 30, 1, 1), (SW-30, 30, -1, 1), (30, SH-30, 1, -1), (SW-30, SH-30, -1, -1)]:
        d.line([(cx, cy), (cx + dx*L, cy)], fill=c, width=7)
        d.line([(cx, cy), (cx, cy + dy*L)], fill=c, width=7)

def _glow_center(im, warm=(86, 66, 44)):
    """Quang sang am o giua (paste in-place)."""
    m = Image.new("L", (SW, SH), 0)
    ImageDraw.Draw(m).ellipse([SW//2-460, SH//2-560, SW//2+460, SH//2+560], fill=52)
    im.paste(Image.new("RGB", (SW, SH), warm), (0, 0), m.filter(ImageFilter.GaussianBlur(180)))

def _watermark(im, ch, col, alpha=16):
    if not ch:
        return
    wm = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    ImageDraw.Draw(wm).text((SW//2, SH//2 - 30), ch, font=sp.font("zh", 760),
                            fill=tuple(col) + (alpha,), anchor="mm")
    im.paste(Image.alpha_composite(im.convert("RGBA"), wm).convert("RGB"), (0, 0))

def _decor_ink(im, d, wm_ch):
    _glow_center(im); _watermark(im, wm_ch, GOLD, 16); _border_gold(d, GOLD)

def _decor_gradient(im, d, wm_ch):
    # bokeh mem + vien trang mong bo goc
    layer = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    for cx, cy, r, a in [(200, 300, 220, 26), (900, 700, 300, 22), (300, 1500, 260, 20),
                         (820, 1250, 180, 24), (560, 950, 120, 30)]:
        ld.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(255, 255, 255, a))
    im.paste(Image.alpha_composite(im.convert("RGBA"),
             layer.filter(ImageFilter.GaussianBlur(40))).convert("RGB"), (0, 0))
    _watermark(im, wm_ch, (255, 255, 255), 14)
    d.rounded_rectangle([34, 34, SW-34, SH-34], radius=40, outline=(255, 255, 255), width=3)

def _decor_white(im, d, wm_ch):
    # toi gian: vien xam nhat bo goc + 1 cham nhan goc tren-trai
    d.rounded_rectangle([36, 36, SW-36, SH-36], radius=44, outline=(224, 224, 226), width=2)
    d.ellipse([70, 70, 122, 122], fill=SEAL_RED)          # cham nhan nho

def _decor_paper(im, d, wm_ch):
    _watermark(im, wm_ch, SEAL_RED, 14)                   # chu Han do rat nhat
    d.rounded_rectangle([34, 34, SW-34, SH-34], radius=18, outline=(150, 60, 40), width=3)
    d.rounded_rectangle([50, 50, SW-50, SH-50], radius=14, outline=(190, 150, 120), width=1)

def _sun(d, cx, cy, r, body=(255, 214, 92), ray=(255, 214, 92), cheek=(245, 170, 150)):
    for k in range(12):                                   # tia nang
        import math as _m
        a = k * (3.14159 / 6)
        x1, y1 = cx + _m.cos(a)*(r+14), cy + _m.sin(a)*(r+14)
        x2, y2 = cx + _m.cos(a)*(r+46), cy + _m.sin(a)*(r+46)
        d.line([(x1, y1), (x2, y2)], fill=ray, width=12)
    d.ellipse([cx-r, cy-r, cx+r, cy+r], fill=body)
    d.ellipse([cx-r*0.45-8, cy+2, cx-r*0.45+22, cy+30], fill=cheek)   # ma hong
    d.ellipse([cx+r*0.45-22, cy+2, cx+r*0.45+8, cy+30], fill=cheek)

def _decor_cute(im, d, wm_ch):
    # doi co bo tron o day (2 lop xanh)
    d.ellipse([-200, SH-360, SW//2+160, SH+240], fill=(196, 224, 150))
    d.ellipse([SW//2-160, SH-300, SW+200, SH+240], fill=(176, 214, 130))
    # hoa nho rai (cham bi + canh)
    for fx, fy, fc in [(150, SH-250, (240, 150, 180)), (SW-190, SH-210, (250, 200, 120)),
                       (SW-120, 900, (240, 150, 180)), (120, 1150, (250, 200, 120))]:
        for dx, dy in [(-16, 0), (16, 0), (0, -16), (0, 16)]:
            d.ellipse([fx+dx-11, fy+dy-11, fx+dx+11, fy+dy+11], fill=fc)
        d.ellipse([fx-9, fy-9, fx+9, fy+9], fill=(255, 240, 170))
    # mat troi goc tren-trai
    _sun(d, 150, 150, 58)
    # vien bo goc xanh
    d.rounded_rectangle([34, 34, SW-34, SH-34], radius=48, outline=(150, 190, 120), width=4)

def _petal(d, cx, cy, r, col, ang=0.0):
    """Canh hoa anh dao 5 canh (mem)."""
    for k in range(5):
        a = ang + k * (2*math.pi/5)
        px, py = cx + math.cos(a)*r, cy + math.sin(a)*r
        d.ellipse([px-r*0.62, py-r*0.62, px+r*0.62, py+r*0.62], fill=col)
    d.ellipse([cx-r*0.5, cy-r*0.5, cx+r*0.5, cy+r*0.5], fill=(255, 250, 250))

def _decor_sakura(im, d, wm_ch):
    _watermark(im, wm_ch, (224, 150, 174), 16)
    # canh hoa rai nhe quanh ria
    for cx, cy, r, a in [(140, 250, 30, 0.3), (SW-170, 360, 24, 1.1), (SW-110, 1120, 34, 0.6),
                         (110, 980, 22, 0.9), (200, SH-260, 28, 0.2), (SW-200, SH-230, 26, 1.4),
                         (SW-130, 720, 18, 0.5), (90, 1450, 20, 0.8)]:
        _petal(d, cx, cy, r, (250, 196, 210), a)
    d.rounded_rectangle([34, 34, SW-34, SH-34], radius=48, outline=(238, 168, 190), width=4)

def _star(d, cx, cy, r, col):
    d.line([(cx-r, cy), (cx+r, cy)], fill=col, width=3)
    d.line([(cx, cy-r), (cx, cy+r)], fill=col, width=3)
    d.ellipse([cx-2, cy-2, cx+2, cy+2], fill=col)

def _decor_night(im, d, wm_ch):
    _glow_center(im, warm=(40, 50, 96))
    _watermark(im, wm_ch, (150, 170, 230), 14)
    # trang khuyet goc tren-phai
    mx, my, mr = SW-190, 240, 76
    d.ellipse([mx-mr, my-mr, mx+mr, my+mr], fill=(255, 232, 168))
    d.ellipse([mx-mr+40, my-mr-6, mx+mr+40, my+mr-6], fill=(SKINS["night"]["bg"][0]))
    # sao lap lanh
    for sx, sy, sr in [(180, 190, 9), (360, 120, 6), (SW-360, 150, 7), (140, 520, 5),
                       (SW-140, 560, 8), (260, 1500, 7), (SW-220, 1400, 6), (120, 1180, 5),
                       (SW-120, 980, 7), (420, 300, 4)]:
        _star(d, sx, sy, sr, (235, 240, 255))
    d.rounded_rectangle([34, 34, SW-34, SH-34], radius=40, outline=(120, 140, 210), width=2)

def _decor_ocean(im, d, wm_ch):
    _watermark(im, wm_ch, (255, 255, 255), 12)
    # song bo day (3 lop sin)
    layer = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    for base, col in [(SH-260, (255, 255, 255, 26)), (SH-170, (255, 255, 255, 34)),
                      (SH-90, (255, 255, 255, 46))]:
        pts = [(x, base + int(28*math.sin(x/90.0))) for x in range(0, SW+1, 12)]
        pts += [(SW, SH), (0, SH)]
        ld.polygon(pts, fill=col)
    im.paste(Image.alpha_composite(im.convert("RGBA"), layer).convert("RGB"), (0, 0))
    # bot khi noi
    d2 = ImageDraw.Draw(im)
    for bx, by, br in [(180, 380, 26), (SW-160, 300, 18), (SW-220, 720, 14), (140, 900, 12)]:
        d2.ellipse([bx-br, by-br, bx+br, by+br], outline=(220, 255, 248), width=3)
    d2.rounded_rectangle([34, 34, SW-34, SH-34], radius=40, outline=(210, 255, 244), width=3)

def _decor_sunset(im, d, wm_ch):
    # dia mat troi lon mo phia sau
    sun = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    ImageDraw.Draw(sun).ellipse([SW//2-300, 560, SW//2+300, 1160], fill=(255, 226, 150, 150))
    im.paste(Image.alpha_composite(im.convert("RGBA"),
             sun.filter(ImageFilter.GaussianBlur(60))).convert("RGB"), (0, 0))
    d2 = ImageDraw.Draw(im)
    _watermark(im, wm_ch, (255, 240, 210), 14)
    # duong chan troi lap lanh
    for gy, ga in [(SH-300, 60), (SH-250, 42), (SH-205, 28)]:
        d2.line([(60, gy), (SW-60, gy)], fill=(255, 236, 200), width=2)
    d2.rounded_rectangle([34, 34, SW-34, SH-34], radius=40, outline=(255, 236, 200), width=3)

def _bamboo_stalk(d, x, col):
    d.line([(x, 60), (x, SH-60)], fill=col, width=14)
    for y in range(180, SH-60, 240):                       # dot truc
        d.line([(x-9, y), (x+9, y)], fill=col, width=6)
        d.line([(x, y), (x+70, y-40)], fill=col, width=8)   # canh
        d.ellipse([x+60, y-70, x+150, y-30], fill=col)       # la
        d.ellipse([x+70, y-46, x+170, y-8], fill=col)

def _decor_bamboo(im, d, wm_ch):
    _watermark(im, wm_ch, (150, 180, 150), 14)
    _bamboo_stalk(d, 96, (176, 204, 172))                   # trai
    _bamboo_stalk(d, SW-108, (168, 198, 164))               # phai
    d.rounded_rectangle([40, 40, SW-40, SH-40], radius=18, outline=(120, 156, 122), width=3)

def _cloud(d, cx, cy, s, col):
    """Van may cung dinh (ru-yi) don gian."""
    for dx in (-1, 1):
        d.arc([cx+dx*s-s, cy-s, cx+dx*s+s, cy+s], 0, 360, fill=col, width=6)
    d.arc([cx-s*1.6, cy-s*0.4, cx+s*1.6, cy+s*1.8], 200, 340, fill=col, width=6)

def _decor_royal(im, d, wm_ch):
    _glow_center(im, warm=(120, 40, 30))
    _watermark(im, wm_ch, (240, 200, 120), 18)
    # van may vang 4 goc
    for cx, cy in [(140, 300), (SW-140, 300), (140, SH-280), (SW-140, SH-280)]:
        _cloud(d, cx, cy, 34, (232, 194, 110))
    d.rectangle([32, 32, SW-32, SH-32], outline=(232, 194, 110), width=4)
    d.rectangle([50, 50, SW-50, SH-50], outline=(200, 150, 80), width=1)
    L = 80
    for cx, cy, dx, dy in [(32, 32, 1, 1), (SW-32, 32, -1, 1), (32, SH-32, 1, -1), (SW-32, SH-32, -1, -1)]:
        d.line([(cx, cy), (cx+dx*L, cy)], fill=(232, 194, 110), width=8)
        d.line([(cx, cy), (cx, cy+dy*L)], fill=(232, 194, 110), width=8)

def _decor_chalk(im, d, wm_ch):
    _watermark(im, wm_ch, (255, 255, 255), 8)
    # vien nét phan dut khuc
    col = (232, 234, 224)
    for x in range(48, SW-48, 34):
        d.line([(x, 48), (x+18, 48)], fill=col, width=3)
        d.line([(x, SH-48), (x+18, SH-48)], fill=col, width=3)
    for y in range(48, SH-48, 34):
        d.line([(48, y), (48, y+18)], fill=col, width=3)
        d.line([(SW-48, y), (SW-48, y+18)], fill=col, width=3)
    # vai net phan trang trang tri goc
    d.arc([70, 120, 190, 210], 10, 170, fill=(210, 235, 210), width=3)

def _washi(d, x, y, w, h, col, skew=18):
    """Bang keo washi cheo (parallelogram) trang tri goc."""
    d.polygon([(x, y), (x+w, y-skew), (x+w, y+h-skew), (x, y+h)], fill=col)

def _pencil(d, x, y, L, col=(245, 196, 90)):
    """But chi nho nam ngang."""
    d.rectangle([x, y-9, x+L, y+9], fill=col)                       # than
    d.polygon([(x+L, y-9), (x+L+22, y), (x+L, y+9)], fill=(240, 214, 178))  # go nhon
    d.polygon([(x+L+14, y-4), (x+L+22, y), (x+L+14, y+4)], fill=(60, 60, 60))  # ruot chi
    d.rectangle([x-14, y-9, x, y+9], fill=(240, 150, 160))         # cuc tay

def _decor_notebook(im, d, wm_ch):
    # giay ke ngang (xanh nhat) + le do doc
    for y in range(232, SH-80, 76):
        d.line([(150, y), (SW-70, y)], fill=(198, 216, 238), width=2)
    d.line([(150, 70), (150, SH-70)], fill=(232, 158, 158), width=3)
    d.line([(156, 70), (156, SH-70)], fill=(244, 196, 196), width=1)
    # gay xoan kim loai ben trai
    for y in range(150, SH-90, 138):
        d.ellipse([44, y-18, 96, y+18], fill=(238, 238, 232), outline=(178, 178, 176), width=3)
        d.arc([56, y-24, 92, y+8], 200, 350, fill=(150, 150, 152), width=6)
    # washi tape 2 goc tren
    _washi(d, 250, 90, 150, 54, (168, 214, 224))
    _washi(d, SW-360, 96, 150, 54, (250, 206, 160))
    # doodle sinh dong rai quanh
    _spark(d, SW-150, 470, 18, (250, 196, 90))
    _star(d, 210, 760, 15, (108, 170, 230))
    _heart(d, SW-160, 1180, 22, (240, 150, 162))
    _spark(d, 205, 1360, 15, (120, 195, 140))
    _star(d, SW-190, 1520, 13, (250, 190, 100))
    _pencil(d, 195, 448, 110)                              # but chi dat tren dong ke (dai trong)
    _watermark(im, wm_ch, (150, 168, 200), 10)

def _decor_grid(im, d, wm_ch):
    # giay o ly caro (2 lop: manh + dam moi 5 o)
    g, G2 = (208, 222, 240), (176, 200, 230)
    step = 54
    for x in range(60, SW-50, step):
        d.line([(x, 150), (x, SH-60)], fill=g, width=1)
    for y in range(150, SH-60, step):
        d.line([(60, y), (SW-60, y)], fill=g, width=1)
    for i, x in enumerate(range(60, SW-50, step)):
        if i % 5 == 0: d.line([(x, 150), (x, SH-60)], fill=G2, width=2)
    for i, y in enumerate(range(150, SH-60, step)):
        if i % 5 == 0: d.line([(60, y), (SW-60, y)], fill=G2, width=2)
    # washi + doodle (tránh vùng pinyin/chữ giữa y~700-1150)
    _washi(d, SW-330, 96, 140, 50, (170, 206, 236))
    _spark(d, 176, 470, 17, (250, 196, 90))
    _heart(d, SW-150, 470, 20, (240, 150, 162))
    _star(d, 190, 1380, 14, (120, 180, 235))
    _spark(d, SW-170, 1400, 15, (140, 200, 150))
    d.rectangle([40, 40, SW-40, SH-40], outline=(150, 178, 214), width=3)
    _watermark(im, wm_ch, (150, 172, 205), 10)

def _halftone(d, x0, y0, x1, y1, col, r=8, gap=30):
    for j, yy in enumerate(range(y0, y1, gap)):
        off = 0 if j % 2 == 0 else gap // 2
        for xx in range(x0 + off, x1, gap):
            d.ellipse([xx-r, yy-r, xx+r, yy+r], fill=col)

def _burst(d, cx, cy, r, col, spikes=12):
    pts = []
    for k in range(spikes*2):
        rr = r if k % 2 == 0 else r*0.55
        a = k*math.pi/spikes
        pts.append((cx+math.cos(a)*rr, cy+math.sin(a)*rr))
    d.polygon(pts, fill=col)

def _decor_comic(im, d, wm_ch):
    _halftone(d, 66, SH-330, 360, SH-80, (255, 196, 70), r=9, gap=34)
    _halftone(d, SW-360, 130, SW-70, 380, (120, 180, 255), r=8, gap=34)
    _burst(d, 150, SH-160, 74, (255, 214, 84)); _burst(d, 150, SH-160, 60, (255, 176, 60))
    _burst(d, SW-150, 470, 58, (255, 120, 150)); _burst(d, SW-150, 470, 46, (255, 160, 180))
    _watermark(im, wm_ch, (0, 0, 0), 7)
    d.rounded_rectangle([32, 32, SW-32, SH-32], radius=30, outline=(26, 26, 32), width=9)

def _sprinkle(d, cx, cy, col, ang):
    dx, dy = math.cos(ang)*13, math.sin(ang)*13
    d.line([(cx-dx, cy-dy), (cx+dx, cy+dy)], fill=col, width=10)

def _decor_candy(im, d, wm_ch):
    cols = [(255, 150, 190), (150, 210, 255), (190, 240, 150), (255, 220, 120), (200, 170, 255)]
    pts = [(150, 300, .5), (SW-160, 380, 1.2), (200, 900, 2.0), (SW-120, 1000, .3), (160, 1400, 1.6),
           (SW-200, 1500, .9), (120, 650, 2.4), (SW-140, 1720, 1.1), (300, 1650, .2), (SW-260, 720, 1.9)]
    for i, (x, y, a) in enumerate(pts):
        _sprinkle(d, x, y, cols[i % len(cols)], a)
    for bx, by, br in [(180, 500, 30), (SW-170, 700, 22), (SW-230, 1300, 18), (150, 1150, 24)]:
        d.ellipse([bx-br, by-br, bx+br, by+br], outline=(255, 178, 210), width=5)
    d.rounded_rectangle([34, 34, SW-34, SH-34], radius=56, outline=(240, 158, 200), width=6)

def _decor_memphis(im, d, wm_ch):
    C1, C2, C3, C4 = (255, 88, 118), (36, 182, 200), (255, 200, 60), (40, 40, 48)
    for x, y, r, c in [(150, 320, 26, C2), (SW-160, 1520, 30, C1), (SW-150, 660, 20, C3)]:
        d.ellipse([x-r, y-r, x+r, y+r], fill=c)
    def tri(cx, cy, s, c):
        d.polygon([(cx, cy-s), (cx-s, cy+s), (cx+s, cy+s)], fill=c)
    tri(SW-150, 340, 26, C3); tri(180, 1560, 24, C1)
    def zig(x, y, c):
        pts = [(x+i*20, y+(11 if i % 2 else -11)) for i in range(6)]
        d.line(pts, fill=c, width=7, joint="curve")
    zig(110, 720, C1); zig(SW-270, 920, C2)
    for x, y, c in [(SW-160, 1150, C4), (200, 1250, C4)]:
        d.line([(x-15, y), (x+15, y)], fill=c, width=7); d.line([(x, y-15), (x, y+15)], fill=c, width=7)
    d.rounded_rectangle([34, 34, SW-34, SH-34], radius=24, outline=C4, width=5)

def _cloud_face(d, cx, cy, s, body=(255, 255, 255), cheek=(255, 182, 202)):
    for ox, oy, r in [(-s*.7, s*.1, s*.55), (s*.7, s*.1, s*.55), (0, -s*.3, s*.72), (0, s*.22, s*.6)]:
        d.ellipse([cx+ox-r, cy+oy-r, cx+ox+r, cy+oy+r], fill=body)
    d.ellipse([cx-s*.34-6, cy-6, cx-s*.34+6, cy+9], fill=(80, 66, 92))
    d.ellipse([cx+s*.34-6, cy-6, cx+s*.34+6, cy+9], fill=(80, 66, 92))
    d.ellipse([cx-s*.52-8, cy+8, cx-s*.52+8, cy+22], fill=cheek)
    d.ellipse([cx+s*.52-8, cy+8, cx+s*.52+8, cy+22], fill=cheek)
    d.arc([cx-13, cy+4, cx+13, cy+24], 20, 160, fill=(80, 66, 92), width=3)

def _rainbow(d, cx, cy, r0, cols):
    for i, c in enumerate(cols):
        rr = r0 + i*13
        d.arc([cx-rr, cy-rr, cx+rr, cy+rr], 180, 360, fill=c, width=9)

def _decor_kawaii(im, d, wm_ch):
    _rainbow(d, SW-170, 300, 34,
             [(255, 120, 140), (255, 180, 110), (255, 226, 120), (150, 216, 150), (130, 190, 240), (182, 150, 232)])
    _cloud_face(d, 172, 320, 66)
    for sx, sy, sr in [(SW-210, 720, 14), (176, 1040, 12), (SW-150, 1460, 15), (250, 1650, 12)]:
        _star(d, sx, sy, sr, (255, 206, 120))
    _heart(d, SW-180, 1150, 20, (255, 150, 182))
    d.rounded_rectangle([34, 34, SW-34, SH-34], radius=52, outline=(255, 180, 206), width=6)

def _decor_neon(im, d, wm_ch):
    _watermark(im, wm_ch, (120, 92, 200), 14)
    hor = (48, 224, 214)
    gy = SH-330
    dd = ImageDraw.Draw(im)
    for i in range(10):
        y = gy + int(3.4*i*i) + 8*i
        if y > SH-44:
            break
        dd.line([(56, y), (SW-56, y)], fill=hor, width=2)
    for vx in range(60, SW-40, 118):
        dd.line([(vx, gy), (int(SW/2 + (vx-SW/2)*2.6), SH-44)], fill=(40, 150, 150), width=1)
    for sx, sy, sr in [(180, 300, 11), (SW-200, 430, 9), (240, 900, 8), (SW-160, 1000, 10), (150, 1250, 7)]:
        _spark(d, sx, sy, sr, (255, 110, 200))
    # vien neon phat sang
    layer = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle([42, 42, SW-42, SH-42], radius=44, outline=(0, 235, 205, 255), width=6)
    im.paste(Image.alpha_composite(im.convert("RGBA"), layer.filter(ImageFilter.GaussianBlur(12))).convert("RGB"), (0, 0))
    ImageDraw.Draw(im).rounded_rectangle([42, 42, SW-42, SH-42], radius=44, outline=(150, 255, 240), width=3)

_DECOR = {"ink": _decor_ink, "gradient": _decor_gradient, "cute": _decor_cute,
          "paper": _decor_paper, "white": _decor_white, "sakura": _decor_sakura,
          "night": _decor_night, "ocean": _decor_ocean, "sunset": _decor_sunset,
          "bamboo": _decor_bamboo, "royal": _decor_royal, "chalk": _decor_chalk,
          "notebook": _decor_notebook, "grid": _decor_grid, "comic": _decor_comic,
          "candy": _decor_candy, "memphis": _decor_memphis, "kawaii": _decor_kawaii,
          "neon": _decor_neon}


def _canvas_v2(watermark_ch=None, bg_image=None):
    """Tra ve (im, draw). Neu co bg_image -> anh nguoi dung (toi+mo) + vien vang; con lai ve theo
    SKIN hien tai (nen gradient + trang tri rieng tung phong cach)."""
    if bg_image and os.path.exists(bg_image):
        im = _prep_bg_short(bg_image)
        d = ImageDraw.Draw(im)
        _border_gold(d, GOLD)
        return im, d
    im = _grad_bg(BG_TOP, BG_BOT)
    d = ImageDraw.Draw(im)
    _DECOR.get(SKINS.get(CUR_SKIN, {}).get("decor", "ink"), _decor_ink)(im, d, watermark_ch)
    return im, ImageDraw.Draw(im)


def _seal(d, text="每日", cx=None, cy=176):
    """Trien do vuong goc tren-phai (2 chu doc). Chu tren trien LUON sang."""
    cx = cx or SW - 128
    s = 116
    d.rounded_rectangle([cx - s//2, cy - s//2, cx + s//2, cy + s//2], radius=14, fill=SEAL_RED)
    f = sp.font("zh", 46)
    chs = list(text[:2])
    yy = cy - (len(chs) * 48) // 2 + 22
    for ch in chs:
        d.text((cx, yy), ch, font=f, fill=_SEAL_TXT, anchor="mm")
        yy += 48


def _glow_text(im, xy, text, font, fill, glow=None, radius=16, anchor=None):
    """Chu chinh: co quang sang (skin toi) HOAC ve phang (skin sang)."""
    if SKINS.get(CUR_SKIN, {}).get("glow", True):
        g = glow or SKINS.get(CUR_SKIN, {}).get("glow_col", (255, 210, 140))
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(layer).text(xy, text, font=font, fill=g + (110,), anchor=anchor)
        layer = layer.filter(ImageFilter.GaussianBlur(radius))
        im.paste(Image.new("RGB", im.size, g), (0, 0), layer)
        ImageDraw.Draw(im).text(xy, text, font=font, fill=fill, anchor=anchor)
    else:
        ImageDraw.Draw(im).text(xy, text, font=font, fill=fill, anchor=anchor)


def _extract_hl(hanzi):
    """Bóc marker [từ] -> (disp sạch, set index chữ Hán được highlight trong disp)."""
    words = re.findall(r"\[([^\]]+)\]", hanzi or "")
    clean = re.sub(r"[\[\]]", "", hanzi or "")
    disp = _strip_punct(clean)
    hl = set()
    for w in words:
        w = _strip_punct(w)
        st = 0
        while w:
            idx = disp.find(w, st)
            if idx < 0:
                break
            for k in range(len(w)):
                hl.add(idx + k)
            st = idx + len(w)
    return disp, hl

def _hl_box(im, x0, y0, x1, y1, col=(255, 206, 92)):
    """Vệt highlighter mềm (bo góc, trong suốt) sau chữ — kiểu bút dạ quang."""
    ov = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    ImageDraw.Draw(ov).rounded_rectangle([x0, y0, x1, y1], radius=12, fill=col + (78,))
    im.paste(Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB"), (0, 0))

def _pinyin_over_hanzi(im, d, zlines, zf, zsize, py_size, gap, cx, y, hl=None):
    """Ve pinyin TREN TUNG CHU HAN. hl: set index chu Han duoc highlight (bút dạ quang).
    Pinyin: PY_MONO (1 mau) neu dat, khong thi to thanh dieu."""
    hl = hl or set()
    pf = sp.font("pinyin", py_size)
    line_h = py_size + 16 + zsize + 28
    ci = 0
    for ln in zlines:
        cells = []
        for ch, p, h in sp.flatten(ln):
            w_ch = sp.text_w(d, ch, zf)
            w_py = sp.text_w(d, p, pf) if p else 0
            cells.append((ch, p, w_ch, w_py, max(w_ch, w_py)))
        total = sum(c[4] for c in cells) + gap * (len(cells) - 1) if cells else 0
        x = cx - total // 2
        boxes = []                                          # gom vùng highlight vẽ trước
        cx2 = x
        for ch, p, w_ch, w_py, cellw in cells:
            if ci in hl and ("一" <= ch <= "鿿"):
                boxes.append((cx2 - 8, y + py_size + 10, cx2 + cellw + 8, y + py_size + 16 + zsize + 6))
            cx2 += cellw + gap; ci += 1
        # nối các ô highlight liền nhau thành 1 vệt dài
        for bx0, by0, bx1, by1 in _merge_boxes(boxes):
            _hl_box(im, bx0, by0, bx1, by1)
        d = ImageDraw.Draw(im)
        ci -= len(cells)                                    # tua lại để vẽ chữ
        for ch, p, w_ch, w_py, cellw in cells:
            if p:
                col = PY_MONO if PY_MONO else TONE_BRIGHT[sp._tone_of(p)]
                d.text((x + (cellw - w_py) // 2, y), p, font=pf, fill=col)
            _glow_text(im, (x + (cellw - w_ch) // 2, y + py_size + 16), ch, zf, IVORY)
            x += cellw + gap; ci += 1
        d = ImageDraw.Draw(im)
        y += line_h
    return line_h * len(zlines)

def _merge_boxes(boxes):
    """Nối các ô highlight sát nhau (cùng dòng) thành 1 vệt liền."""
    if not boxes:
        return []
    boxes = sorted(boxes)
    out = [list(boxes[0])]
    for b in boxes[1:]:
        if b[0] <= out[-1][2] + 24:                         # gần nhau -> gộp
            out[-1][2] = max(out[-1][2], b[2])
        else:
            out.append(list(b))
    return out


def _lighten(col, f=0.22):
    return tuple(min(255, int(c + (255 - c) * f)) for c in col)

def _heart(d, cx, cy, s, col):
    """Trai tim nho (2 thuy tron + tam giac)."""
    r = s * 0.56
    d.ellipse([cx - s, cy - r, cx - s + 2*r, cy + r], fill=col)
    d.ellipse([cx + s - 2*r, cy - r, cx + s, cy + r], fill=col)
    d.polygon([(cx - s + 2, cy + r*0.15), (cx + s - 2, cy + r*0.15), (cx, cy + s*1.18)], fill=col)

def _spark(d, cx, cy, s, col):
    """Tia lap lanh 4 canh (sparkle)."""
    d.polygon([(cx, cy - s), (cx + s*0.28, cy - s*0.28), (cx + s, cy),
               (cx + s*0.28, cy + s*0.28), (cx, cy + s), (cx - s*0.28, cy + s*0.28),
               (cx - s, cy), (cx - s*0.28, cy - s*0.28)], fill=col)

def _pill(im, d, cx, cy, text, fill=None, txt=None, fsize=40, icon=True):
    """Nut CTA sinh dong: do bong noi + icon tim + dai bong nhe phia tren."""
    fill = fill or SEAL_RED
    txt = txt or FOOT_TXT
    f = sp.font("sansb", fsize)
    tw = sp.text_w(d, text, f)
    ic = fsize + 10 if icon else 0
    gap_ic = 16 if icon else 0
    pad, h = 46, fsize + 46
    total = tw + ic + gap_ic
    x0, x1 = cx - total//2 - pad, cx + total//2 + pad
    y0, y1 = cy - h//2, cy + h//2
    # do bong mem
    sh = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([x0, y0 + 12, x1, y1 + 18], radius=h//2, fill=(0, 0, 0, 105))
    im.paste(Image.alpha_composite(im.convert("RGBA"),
             sh.filter(ImageFilter.GaussianBlur(14))).convert("RGB"), (0, 0))
    d = ImageDraw.Draw(im)
    # than nut + dai sang mo phia tren (gloss)
    d.rounded_rectangle([x0, y0, x1, y1], radius=h//2, fill=fill)
    d.rounded_rectangle([x0 + 8, y0 + 6, x1 - 8, y0 + h//2], radius=h//2 - 8, fill=_lighten(fill, 0.16))
    d.rounded_rectangle([x0, y0, x1, y1], radius=h//2, outline=_lighten(fill, 0.34), width=2)
    # icon tim + chu
    tx = cx - total//2 + (ic + gap_ic if icon else 0)
    if icon:
        _heart(d, cx - total//2 + ic//2, cy, ic*0.5, txt)
    d.text((tx, cy - 4), text, font=f, fill=txt, anchor="lm")
    return d


def render_frame(hanzi, viet, hook, path, footer="", note="", bg=None):
    """Frame flashcard v2 — nen toi/anh + vang kim, chu Han glow, pinyin sang, an toan safe-zone.
    hanzi co the chua marker [tu] -> highlight tu do (bút dạ quang)."""
    disp, hl = _extract_hl(hanzi)
    im, d = _canvas_v2(watermark_ch=(disp[0] if disp else None), bg_image=bg)
    _seal(d)

    # hook: chip phat sang + sparkle (sinh dong, trong safe-zone)
    _hook_badge(im, d, hook, y=214, fsize=54)
    d = ImageDraw.Draw(im)

    # khoi giua
    max_w, gap = SW - 170, 16
    zsize = sp.fit_zh_size(d, disp, max_size=250, min_size=110, max_w=max_w, char_gap=gap)
    zf = sp.font("zh", zsize)
    zlines = _wrap_hanzi(d, disp, zf, max_w, gap)
    py_size = max(48, int(zsize * 0.40))
    line_h = py_size + 16 + zsize + 28          # pinyin + chu Han tinh chung 1 dong
    vf = sp.font("viet", 62)
    vlines = sp.wrap_text(d, viet, vf, max_w)[:3] if viet else []
    nf = sp.font("note", 40)     # font phu chu Han -> ghi chu co the chua 我的/这是... khong tofu
    nlines = sp.wrap_text(d, note, nf, max_w)[:2] if note else []
    block_h = len(zlines) * line_h + 42 + len(vlines) * (vf.size + 12) \
              + (len(nlines) * (nf.size + 8) + 26 if nlines else 0)
    y = max(430, (SH - block_h) // 2 - 20)

    y += _pinyin_over_hanzi(im, d, zlines, zf, zsize, py_size, gap, SW // 2, y, hl=hl)
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

    _pill(im, d, SW // 2, SH - 300, footer or _t("cta_save"))
    im.save(path)
    return path


_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002300-\U000023FF"
    "\U00002B00-\U00002BFF\U0001F1E6-\U0001F1FF\U0000FE00-\U0000FE0F\U00002190-\U000021FF]+")

def _strip_emoji(s):
    """Bo emoji/pictograph (font chu khong ve dc -> tofu). Giu CJK/Latin/dau cau."""
    return re.sub(r"\s{2,}", " ", _EMOJI_RE.sub("", s or "")).strip()

def _hook_badge(im, d, text, y=206, fsize=52, accent=None):
    """Nhan tren cung dang CHIP phat sang: tu co chu cho vua 1 dong + chua cho trien goc phai.
    Chip LUON nam gon giua, khong dam vao trien (x1 <= SW-206)."""
    accent = accent or GOLD
    txt = _strip_emoji(text).upper()
    padx, pady, spr = 74, 18, 12
    MAX_CHIP = 660                                          # be rong chip toi da (chua cho trien)
    inner = MAX_CHIP - 2 * padx
    # co font cho text vua 1 dong trong inner (min 30)
    fs = fsize
    while fs > 30 and sp.text_w(d, txt, sp.font("viet", fs)) > inner:
        fs -= 2
    hf = sp.font("viet", fs)
    lines = sp.wrap_text(d, txt, hf, inner)[:2]
    lh = fs + 8
    tw = min(inner, max((sp.text_w(d, ln, hf) for ln in lines), default=0))
    block_h = lh * len(lines)
    x0, x1 = SW//2 - tw//2 - padx, SW//2 + tw//2 + padx
    yt, yb = y - pady, y + block_h + pady - 6
    rad = (yb - yt)//2
    # nen chip tint mo (glow am) — composite 1 lan
    tl = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    ImageDraw.Draw(tl).rounded_rectangle([x0, yt, x1, yb], radius=rad, fill=tuple(accent) + (38,))
    im.paste(Image.alpha_composite(im.convert("RGBA"), tl).convert("RGB"), (0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([x0, yt, x1, yb], radius=rad, outline=accent, width=2)
    cy = (yt + yb)//2
    _spark(d, x0 + 32, cy, spr, accent)
    _spark(d, x1 - 32, cy, spr, accent)
    yy = y
    for ln in lines:
        d.text((SW // 2, yy), ln, font=hf, fill=accent, anchor="ma")
        yy += lh
    return yb + 30

def _label(d, text, y=236, im=None):
    """Nhan tren cung — chip phat sang (fallback gach chan neu thieu im)."""
    if im is not None:
        return _hook_badge(im, d, text, y=y, fsize=50)
    hf = sp.font("viet", 52)
    for ln in sp.wrap_text(d, text.upper(), hf, SW - 200)[:2]:
        d.text((SW // 2, y), ln, font=hf, fill=GOLD, anchor="ma")
        y += hf.size + 8
    d.line([(SW//2 - 70, y + 12), (SW//2 + 70, y + 12)], fill=SEAL_RED, width=6)
    return y + 40


def _small_pinyin_row(im, d, text, cx, y, zh_size, py_size, gap=12):
    """Ve 1 dong 汉字 NHO + pinyin to mau tren tung chu (cho cau vi du). Tra chieu cao."""
    zf, pf = sp.font("zh", zh_size), sp.font("pinyin", py_size)
    cells = []
    for ch, p, h in sp.flatten(text):
        wch = sp.text_w(d, ch, zf); wpy = sp.text_w(d, p, pf) if p else 0
        cells.append((ch, p, wch, wpy, max(wch, wpy)))
    total = sum(c[4] for c in cells) + gap*(len(cells)-1) if cells else 0
    x = cx - total//2
    for ch, p, wch, wpy, cw in cells:
        if p:
            d.text((x + (cw-wpy)//2, y), p, font=pf, fill=TONE_BRIGHT[sp._tone_of(p)])
        d.text((x + (cw-wch)//2, y + py_size + 8), ch, font=zf, fill=IVORY)
        x += cw + gap
    return py_size + 8 + zh_size


def render_vocab_frame(word, meaning, example, path, ex_viet="", footer="", bg=None, label=None):
    """Layout TU MOI: nhan + tu KHONG LO (pinyin tren tung chu) + nghia + o vi du + CTA."""
    w = _strip_punct(word)
    im, d = _canvas_v2(watermark_ch=(w[0] if w else None), bg_image=bg)
    _seal(d, "生词")                                        # trien "tu moi"
    y = _label(d, label or _t("lbl_vocab"), im=im)

    # tu chinh: to het co (1-4 chu) — pinyin tren tung chu + glow
    max_w, gap = SW - 200, 20
    zsize = sp.fit_zh_size(d, w, max_size=340, min_size=150, max_w=max_w, char_gap=gap)
    zf = sp.font("zh", zsize)
    zlines = _wrap_hanzi(d, w, zf, max_w, gap)
    py_size = max(56, int(zsize * 0.34))
    y = max(y + 40, 520)
    y += _pinyin_over_hanzi(im, d, zlines, zf, zsize, py_size, gap, SW // 2, y)
    d = ImageDraw.Draw(im)

    # nghia Viet — ho phach, to
    y += 24
    vf = sp.font("viet", 74)
    for ln in sp.wrap_text(d, meaning, vf, SW - 200)[:2]:
        d.text((SW // 2, y), ln, font=vf, fill=AMBER, anchor="ma")
        y += vf.size + 10

    # o vi du: khung bo tron mo + nhan "Ví dụ" + cau vi du (Han nho + pinyin) + nghia
    if _strip_punct(example):
        y += 46
        box_top = y
        ef = sp.font("sansb", 38)
        d.text((92, y), _t("lbl_example"), font=ef, fill=GOLD)
        y += ef.size + 18
        y += _small_pinyin_row(im, d, _strip_punct(example), SW // 2, y, 74, 34)
        d = ImageDraw.Draw(im)
        if ex_viet.strip():
            y += 16
            evf = sp.font("viet", 46)
            for ln in sp.wrap_text(d, ex_viet.strip(), evf, SW - 200)[:2]:
                d.text((SW // 2, y), ln, font=evf, fill=MUTED, anchor="ma")
                y += evf.size + 8
        # vien o vi du
        d.rounded_rectangle([60, box_top - 26, SW - 60, y + 22], radius=26,
                            outline=(150, 122, 78), width=2)

    _pill(im, d, SW // 2, SH - 300, footer or _t("cta_save"))
    im.save(path)
    return path


def render_pattern_frame(pattern, meaning, examples, path, footer="", bg=None, label=None):
    """Layout MAU CAU: nhan + mau cau (khung) + nghia + 2-3 vi du (Han nho + pinyin -> nghia) + CTA.
    examples: list (han, viet)."""
    im, d = _canvas_v2(watermark_ch=None, bg_image=bg)
    _seal(d, "句型")                                        # trien "mau cau"
    y = _label(d, label or _t("lbl_pattern"), im=im)

    # mau cau (co the lan Latin A/B) trong khung bo tron
    y = max(y + 30, 430)
    pf_sz = sp.fit_zh_size(d, pattern, max_size=170, min_size=90, max_w=SW - 240, char_gap=12)
    # ve tung ky tu: Han dung font zh, Latin (A/B) dung sansb cung co
    pf_zh = sp.font("zh", pf_sz); pf_la = sp.font("sansb", int(pf_sz * 0.9))
    chs = [(c, pf_zh if sp.has_hanzi(c) else pf_la) for c in pattern]
    tw = sum(sp.text_w(d, c, f) for c, f in chs) + 8 * (len(chs) - 1)
    bx = (SW - tw) // 2 - 44; d_box_top = y - 30
    box_fill = (255, 253, 247) if SKINS.get(CUR_SKIN, {}).get("light") else (40, 32, 24)
    d.rounded_rectangle([max(40, bx), d_box_top, min(SW-40, SW-bx), y + pf_sz + 34],
                        radius=28, fill=box_fill, outline=GOLD, width=3)
    x = (SW - tw) // 2
    for c, f in chs:
        col = SEAL_RED if not sp.has_hanzi(c) else IVORY      # A/B (Latin) to do noi bat
        d.text((x, y), c, font=f, fill=col)
        x += sp.text_w(d, c, f) + 8
    y += pf_sz + 60

    # nghia mau cau
    vf = sp.font("viet", 60)
    for ln in sp.wrap_text(d, meaning, vf, SW - 200)[:2]:
        d.text((SW // 2, y), ln, font=vf, fill=AMBER, anchor="ma")
        y += vf.size + 10
    y += 30

    # cac vi du
    for han, viet in examples[:3]:
        if not _strip_punct(han):
            continue
        y += _small_pinyin_row(im, d, _strip_punct(han), SW // 2, y, 66, 32)
        d = ImageDraw.Draw(im)
        if (viet or "").strip():
            y += 12
            evf = sp.font("viet", 44)
            for ln in sp.wrap_text(d, viet.strip(), evf, SW - 200)[:1]:
                d.text((SW // 2, y), ln, font=evf, fill=MUTED, anchor="ma")
                y += evf.size + 6
        y += 34

    _pill(im, d, SW // 2, SH - 300, footer or _t("cta_save"))
    im.save(path)
    return path


# ---------- QUIZ (do nghia): hoi -> dem nguoc -> dap an -> loop ----------
SLOT_H = 250


def render_quiz_frame(hanzi, viet, path, phase, count=None, hook=None, bg=None):
    """phase: 'q' (hoi, an nghia) | 'count' (dem nguoc) | 'reveal' (lo nghia).
    Cung phong cach v2 voi flashcard; pinyin+Han GIU NGUYEN vi tri -> chuyen canh muot + loop."""
    disp = _strip_punct(hanzi)
    im, d = _canvas_v2(watermark_ch=(disp[0] if disp else None), bg_image=bg)
    _seal(d, "考考")                                       # trien "kiem tra"

    # nhan tren dang chip: hoi (vang) / dap an (xanh la sang)
    label = _t("quiz_ans") if phase == "reveal" else (hook or _t("quiz_q"))
    lcol = TONE_BRIGHT[3] if phase == "reveal" else GOLD
    _hook_badge(im, d, label, y=214, fsize=54, accent=lcol)
    d = ImageDraw.Draw(im)

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

    _pill(im, d, SW // 2, SH - 300,
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


def _clean_voice(voice):
    """Bo tien to engine ('azure:'/'edge:'/...) NHUNG giu tên giọng có nhiều dấu ':'
    (vd zh-CN-Xiaoyue:DragonHDOmniLatestNeural). Truoc day .split(':')[-1] lam vo tên HD."""
    v = (voice or "zh-CN-XiaoxiaoNeural").strip()
    for p in ("azure:", "edge:", "eleven:", "gemini:", "chattts:"):
        if v.startswith(p):
            return v[len(p):]
    return v


def make_quiz_from_text(hanzi, viet="", voice="zh-CN-XiaoxiaoNeural", hook=None,
                        out_dir=None, cta=None, rate="-8%", name=None, count_from=3,
                        lang="auto", bg=None, skin="ink", azure=None):
    """Sinh Short QUIZ do nghia: hoi (an nghia) -> dem nguoc -> lo dap an. Tu TTS (edge free)."""
    import generate
    hanzi = (hanzi or "").strip()
    if not _strip_punct(hanzi):
        raise ValueError("cau rong")
    viet = (viet or "").strip()
    _set_lang(lang, viet)                                  # 'auto' -> doan theo dong nghia
    _apply_skin("ink" if bg else skin)                     # anh nen -> palette sang tren nen toi
    voice = _clean_voice(voice)
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
        generate.synth(hanzi, voice, raw, rate=rate, azure=azure)          # edge free
        _to_wav(raw, sent)
        d_sent = _dur(sent)
        # audio: doc cau (khi hoi) + gap + [dem nguoc: im lang] + doc lai cau (khi lo dap an) + tail
        _silence_concat([("clip", sent), ("sil", gap), ("sil", float(count_from)),
                         ("clip", sent), ("sil", tail)], audio)
        render_quiz_frame(hanzi, viet, fq, "q", hook=hook, bg=bg)
        for i, n in enumerate(range(count_from, 0, -1)):
            render_quiz_frame(hanzi, viet, fcs[i], "count", count=n, hook=hook, bg=bg)
        render_quiz_frame(hanzi, viet, fr, "reveal", hook=hook, bg=bg)
        items = ([(fq, d_sent + gap)]
                 + [(fcs[i], 1.0) for i in range(count_from)]
                 + [(fr, d_sent + tail)])
        _compose_frames(items, audio, out)
    finally:
        for f in tmp:
            if os.path.exists(f):
                os.remove(f)

    title = f"{_tf('t_quiz', hz=_strip_punct(hanzi))} | {_t('brand')} #Shorts"
    desc = _tf("d_quiz", hz=hanzi, py=py, vi=viet) + "\n\n" + _t("tags_quiz")
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


def make_short(video, out_dir=None, cta=None, at=None, reads=2, lang="auto", skin="ink"):
    """Sinh 1 Short DOC native tu bai. Tra ve {file,title,desc,hook,start,dur}."""
    video = os.path.abspath(video)
    meta = load_meta(video)
    _han_title, viet_title = split_title(meta.get("title", ""))
    at_sec = float(_mmss(at)) if at else None
    seg = pick_sentence(meta["segments"], at_sec)
    hanzi = seg["hanzi"].strip()
    viet = (seg.get("viet") or "").strip()
    _set_lang(lang, viet)                                  # 'auto' -> doan theo dong nghia
    _apply_skin(skin)
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

    title = f"{_tf('t_meaning', hz=_strip_punct(hanzi))} | {viet[:40]} | {_t('brand')} #Shorts"
    desc = (f"{hanzi}\n{py}\n{viet}\n\n"
            f"🎧 Bài đầy đủ ({viet_title}) có trên kênh!\n"
            "#hoctiengtrung #tuvungtiengtrung #shorts #tiengtrung #chinese")
    return {"file": out, "title": title, "desc": desc, "hook": hook,
            "hanzi": hanzi, "pinyin": py, "viet": viet,
            "start": round(st, 3), "dur": round(_dur(out), 2)}


def make_short_from_text(hanzi, viet="", voice="zh-CN-XiaoxiaoNeural", hook=None,
                         out_dir=None, cta=None, reads=2, rate="-8%", name=None, note="",
                         lang="auto", bg=None, skin="ink", azure=None, py_color=None):
    """Sinh 1 Short DOC native TRUC TIEP tu 1 cau (KHONG can video dai).
    Tu tong hop giong bang generate.synth (edge free mac dinh). Tra ve dict giong make_short."""
    import generate
    hanzi = (hanzi or "").strip()
    if not _strip_punct(hanzi):
        raise ValueError("cau rong")
    viet = (viet or "").strip()
    _set_lang(lang, viet)                                  # 'auto' -> doan theo dong nghia
    _apply_skin("ink" if bg else skin)
    global PY_MONO; PY_MONO = _parse_color(py_color)       # sau _apply_skin (skin reset PY_MONO)
    voice = _clean_voice(voice)   # bo tien to 'edge:' neu co
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
        generate.synth(hanzi, voice, raw, rate=rate, azure=azure)          # edge-tts (khong can key)
        _to_wav(raw, sent)
        _build_audio(sent, audio, reads=reads)
        render_frame(hanzi, viet, hook, frame,
                     footer=cta or _t("cta_save"), note=note, bg=bg)
        _compose(frame, audio, out)
    finally:
        for f in (frame, raw, sent, audio):
            if os.path.exists(f):
                os.remove(f)

    title = f"{_tf('t_meaning', hz=_strip_punct(hanzi))} | {viet[:40]} | {_t('brand')} #Shorts"
    desc = (f"{hanzi}\n{py}\n{viet}\n\n"
            "#hoctiengtrung #tuvungtiengtrung #shorts #tiengtrung #chinese")
    return {"file": out, "title": title, "desc": desc, "hook": hook,
            "hanzi": hanzi, "pinyin": py, "viet": viet, "dur": round(_dur(out), 2)}


def make_vocab_from_text(word, meaning="", example="", ex_viet="", voice="zh-CN-XiaoxiaoNeural",
                         out_dir=None, cta=None, reads=2, rate="-8%", name=None, lang="auto",
                         bg=None, skin="ink", label=None, azure=None):
    """Short TU MOI: tu KHONG LO + pinyin + nghia + o vi du. Audio: doc tu 'reads' lan + vi du 1 lan."""
    import generate
    word = (word or "").strip()
    if not _strip_punct(word):
        raise ValueError("tu rong")
    meaning = (meaning or "").strip(); example = (example or "").strip()
    _set_lang(lang, meaning)
    _apply_skin("ink" if bg else skin)
    voice = _clean_voice(voice)
    py = pinyin_str(word)
    out_dir = out_dir or "."; os.makedirs(out_dir, exist_ok=True)
    base = name or ("vocab_" + hashlib.md5((word + voice).encode("utf-8")).hexdigest()[:10])
    out = os.path.join(out_dir, base + ".mp4")
    frame = os.path.join(out_dir, f"_vf_{base}.png")
    wr = os.path.join(out_dir, f"_vwr_{base}.mp3"); ws = os.path.join(out_dir, f"_vws_{base}.wav")
    er = os.path.join(out_dir, f"_ver_{base}.mp3"); es = os.path.join(out_dir, f"_ves_{base}.wav")
    audio = os.path.join(out_dir, f"_va_{base}.wav")
    tmp = [frame, wr, ws, er, es, audio]
    try:
        generate.synth(word, voice, wr, rate=rate, azure=azure); _to_wav(wr, ws)
        parts = []
        for i in range(max(1, reads)):
            parts += [("clip", ws), ("sil", 0.45)]
        if _strip_punct(example):
            generate.synth(_strip_punct(example), voice, er, rate=rate, azure=azure); _to_wav(er, es)
            parts += [("sil", 0.3), ("clip", es), ("sil", 0.8)]
        else:
            parts += [("sil", 0.5)]
        _silence_concat(parts, audio)
        render_vocab_frame(word, meaning, example, frame, ex_viet=ex_viet,
                           footer=cta or _t("cta_save"), bg=bg, label=label)
        _compose(frame, audio, out)
    finally:
        for f in tmp:
            if os.path.exists(f):
                os.remove(f)
    title = f"{_tf('t_vocab', word=word, mean=meaning[:30])} | {_t('brand')} #Shorts"
    desc = (f"{word}\n{py}\n{meaning}\n" + (f"例：{example}\n" if example else "") +
            "\n" + _t("tags_vocab"))
    return {"file": out, "title": title, "desc": desc, "hook": label or _t("lbl_vocab"),
            "hanzi": word, "pinyin": py, "viet": meaning, "dur": round(_dur(out), 2)}


def make_pattern_from_text(pattern, meaning="", examples=None, voice="zh-CN-XiaoxiaoNeural",
                           out_dir=None, cta=None, rate="-8%", name=None, lang="auto",
                           bg=None, skin="ink", label=None, azure=None):
    """Short MAU CAU: mau cau (khung) + nghia + 2-3 vi du. examples: list (han, viet).
    Audio: doc lan luot cac cau vi du (1 lan/cau)."""
    import generate
    pattern = (pattern or "").strip()
    if not pattern:
        raise ValueError("mau cau rong")
    meaning = (meaning or "").strip()
    examples = [(h.strip(), (v or "").strip()) for h, v in (examples or []) if _strip_punct(h)]
    _set_lang(lang, meaning or (examples[0][1] if examples else ""))
    _apply_skin("ink" if bg else skin)
    voice = _clean_voice(voice)
    out_dir = out_dir or "."; os.makedirs(out_dir, exist_ok=True)
    base = name or ("patt_" + hashlib.md5((pattern + voice).encode("utf-8")).hexdigest()[:10])
    out = os.path.join(out_dir, base + ".mp4")
    frame = os.path.join(out_dir, f"_pf_{base}.png")
    audio = os.path.join(out_dir, f"_pa_{base}.wav")
    tmp = [frame, audio]
    try:
        parts = [("sil", 0.5)]
        for i, (han, _v) in enumerate(examples[:3]):
            r = os.path.join(out_dir, f"_pr_{base}_{i}.mp3"); s = os.path.join(out_dir, f"_ps_{base}_{i}.wav")
            tmp += [r, s]
            generate.synth(_strip_punct(han), voice, r, rate=rate, azure=azure); _to_wav(r, s)
            parts += [("clip", s), ("sil", 0.6)]
        if len(parts) == 1:
            parts += [("sil", 2.0)]
        _silence_concat(parts, audio)
        render_pattern_frame(pattern, meaning, examples, frame, footer=cta or _t("cta_save"), bg=bg, label=label)
        _compose(frame, audio, out)
    finally:
        for f in tmp:
            if os.path.exists(f):
                os.remove(f)
    ex_txt = "\n".join(f"{h}  {v}" for h, v in examples)
    title = f"{_tf('t_pattern', pat=pattern)} | {_t('brand')} #Shorts"
    desc = (f"{pattern}\n{meaning}\n{ex_txt}\n\n"
            + _t("tags_patt"))
    return {"file": out, "title": title, "desc": desc, "hook": label or _t("lbl_pattern"),
            "hanzi": pattern, "pinyin": "", "viet": meaning, "dur": round(_dur(out), 2)}


def make_short_from_lines(lines, voice="zh-CN-XiaoxiaoNeural", hook=None,
                          out_dir=None, cta=None, reads=2, rate="-8%", name=None,
                          lang="auto", bg=None, skin="ink", title=None, azure=None, py_color=None):
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
    _apply_skin("ink" if bg else skin)
    global PY_MONO; PY_MONO = _parse_color(py_color)       # sau _apply_skin (skin reset PY_MONO)
    voice = _clean_voice(voice)

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
            generate.synth(hz, voice, raw, rate=rate, azure=azure)
            _to_wav(raw, sent)
            _build_audio(sent, aud, reads=reads)
            render_frame(hz, vi, hk, frame, footer=cta or _t("cta_save"), note=nt, bg=bg)
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

    # TIÊU ĐỀ: ưu tiên CHỦ ĐỀ (hook, vd "Starting the interview") cho tò mò; không có -> generic
    topic = _strip_emoji(hook or "").strip().rstrip(".…")
    if title:
        pass
    elif topic:
        title = f"{_tf('t_combine', n=len(norm), topic=topic)} | {_t('brand')} #Shorts"
    else:
        title = f"{_tf('t_combine_plain', n=len(norm))} | {_t('brand')} #Shorts"
    desc = "\n".join(f"{h}  {pinyin_str(h)}  {v}" for h, v, _ in norm) + "\n\n" + _t("tags_def")
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
