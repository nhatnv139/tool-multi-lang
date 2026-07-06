# -*- coding: utf-8 -*-
"""Buoc 2: sinh thong tin SEO YouTube + PHU DE (.srt) tu noi dung video + thoi luong that.
   - timestamp chuong tu thoi luong segment that
   - phu de 3 track: zh-Hans (chu Han), zh-Latn (pinyin), vi (tieng Viet)
   - transcript co pinyin, comment ghim tu vung
   Tat ca field cho phep user sua tren web."""
import re
from pypinyin import pinyin as _pyin, Style

# ---------- tien ich ----------
def mmss(sec):
    sec = int(round(sec or 0))
    return f"{sec // 60:02d}:{sec % 60:02d}"

def _srt_time(sec):
    sec = max(0.0, float(sec or 0))
    h = int(sec // 3600); m = int((sec % 3600) // 60); s = int(sec % 60)
    ms = int(round((sec - int(sec)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def has_hanzi(s):
    return any("一" <= c <= "鿿" for c in (s or ""))

_PUNC_MAP = {"，": ",", "。": ".", "！": "!", "？": "?", "、": ",",
             "；": ";", "：": ":", "“": '"', "”": '"', "（": "(", "）": ")"}
def pinyin_of(hanzi):
    if not hanzi:
        return ""
    out = []
    for grp in _pyin(hanzi, style=Style.TONE, errors=lambda x: [[c] for c in x]):
        out.append(grp[0])
    s = " ".join(out)
    # gom dau cau: ' ，' -> ', ' (pinyin doc gon, dep)
    s = re.sub(r"\s*([，。！？、；：“”（）])\s*",
               lambda m: _PUNC_MAP.get(m.group(1), m.group(1)) + " ", s)
    return re.sub(r"\s{2,}", " ", s).strip(" ")

def split_title(title):
    """Tach (chu Han, nghia Viet) — TU NHAN DIEN phan nao la Han du thu tu the nao.
       '我的一天 (Một ngày của tôi)' hay 'Một ngày của tôi (我的一天)' deu dung."""
    title = (title or "").strip()
    a = b = None
    m = re.match(r"^(.*?)[\(（](.+?)[\)）]\s*$", title)
    if m:
        a, b = m.group(1).strip(), m.group(2).strip()
    else:
        for sep in ("|", "—", "-"):
            if sep in title:
                a, b = [x.strip() for x in title.split(sep, 1)]
                break
    if a is not None:
        if has_hanzi(a) and not has_hanzi(b):
            return a, b
        if has_hanzi(b) and not has_hanzi(a):
            return b, a          # Viet truoc, Han trong ngoac -> dao lai cho dung
        return a, b
    han = "".join(c for c in title if "一" <= c <= "鿿")
    lat = "".join(c for c in title if not ("一" <= c <= "鿿")).strip()
    return (han or title), (lat or "")


# ---------- chapters thong minh (timestamp that) ----------
# tu khoa noi dung -> nhan chuong (quet theo thu tu cau, lan dau xuat hien moi tao chuong)
_SCENE_KEYWORDS = [
    ("早上", "Morning"), ("早晨", "Morning"), ("清晨", "Morning"),
    ("起床", "Waking up"), ("早饭", "Breakfast"), ("早餐", "Breakfast"),
    ("上班", "Going to work"), ("公司", "At the office"), ("上午", "Late morning"),
    ("中午", "Noon"), ("午饭", "Lunch"), ("午餐", "Lunch"),
    ("下午", "Afternoon"), ("下班", "Leaving work"),
    ("回家", "Going home"), ("晚上", "Evening"), ("做饭", "Cooking"), ("晚饭", "Dinner"),
    ("睡觉", "Bedtime"), ("睡前", "Before bed"),
]

def build_chapters(seg_meta):
    """[(mmss,label)] tu thoi luong that. Uu tien section -> tu khoa noi dung -> chia deu.
       Luon co 00:00, >=3 chuong cho YouTube."""
    if not seg_meta:
        return [("00:00", "Start")]
    chapters = []
    # 1) segment 'section' lam moc
    for s in seg_meta:
        t, lbl = s["type"], (s.get("label") or "").strip()
        if t in ("title", "objectives") and not chapters:
            chapters.append((0.0, "Intro"))
        elif t == "section" and lbl:
            chapters.append((s["start"], lbl.capitalize()))
        elif t == "practice_q":
            chapters.append((s["start"], "Practice"))

    # 2) khong co section -> quet tu khoa noi dung (sang/trua/chieu/toi...)
    if len(chapters) < 3:
        used = set()
        kw_ch = []
        for s in seg_meta:
            han = s.get("hanzi", "")
            for kw, label in _SCENE_KEYWORDS:
                if kw in han and label not in used:
                    used.add(label)
                    kw_ch.append((s["start"], label))
                    break
        if len(kw_ch) >= 2:
            chapters = kw_ch
            if chapters[0][0] > 0:
                chapters.insert(0, (0.0, "Intro"))

    # 3) van it -> chia deu theo thoi gian
    if len(chapters) < 3:
        total = seg_meta[-1]["end"]
        parts = 4 if total >= 180 else 3
        chapters = [(0.0, "Intro")]
        for k in range(1, parts):
            target = total * k / parts
            seg = min(seg_meta, key=lambda s: abs(s["start"] - target))
            chapters.append((seg["start"], f"Part {k + 1}"))

    if not chapters or chapters[0][0] > 0:
        chapters.insert(0, (0.0, "Intro"))
    # khu trung mmss
    seen, out = set(), []
    for t, lbl in sorted(chapters, key=lambda x: x[0]):
        k = mmss(t)
        if k in seen:
            continue
        seen.add(k); out.append((k, lbl))
    return out

def chapters_text(seg_meta):
    return "\n".join(f"{t} {lbl}" for t, lbl in build_chapters(seg_meta))


# ---------- PHU DE (.srt) ----------
def build_srt(seg_meta, kind="hanzi"):
    """Tao chuoi SRT. kind: 'hanzi' | 'pinyin' | 'viet'."""
    cues = []
    n = 1
    for s in seg_meta:
        han = s.get("hanzi", "")
        if not han:
            continue
        if kind == "hanzi":
            text = han
        elif kind == "pinyin":
            text = pinyin_of(han)
        else:
            text = s.get("viet", "")
        if not text:
            continue
        cues.append(f"{n}\n{_srt_time(s['start'])} --> {_srt_time(s['end'])}\n{text}\n")
        n += 1
    return "\n".join(cues)


# ---------- transcript (co pinyin) ----------
def transcript_text(seg_meta):
    lines = []
    for s in seg_meta:
        han = s.get("hanzi", "")
        if not han:
            continue
        py = pinyin_of(han)
        viet = s.get("viet", "")
        lines.append(f"{han} | {py} | {viet}" if viet else f"{han} | {py}")
    return "\n".join(lines)


# ---------- comment ghim (tu vung trong tam) ----------
def pinned_comment(seg_meta, han_title, hsk):
    """Tach tu bang jieba, lay tu 2+ ky tu xuat hien nhieu nhat lam tu vung."""
    text = "".join(s.get("hanzi", "") for s in seg_meta)
    words = []
    try:
        import jieba
        from collections import Counter
        toks = [w for w in jieba.cut(text) if len(w) >= 2 and has_hanzi(w)]
        common = [w for w, _ in Counter(toks).most_common(14)]
        words = common
    except Exception:
        words = []
    lines = [f"📌 KEY VOCABULARY — {han_title} (HSK{hsk})",
             "Save this and listen again! 👇", ""]
    for w in words:
        lines.append(f"{w}  {pinyin_of(w)}  – ")
    lines.append("")
    lines.append("💬 How many words do you remember? Comment below! 加油 💪")
    return "\n".join(lines)


# ---------- tags ----------
DEFAULT_TAGS = [
    "learn chinese", "chinese listening practice", "mandarin listening",
    "chinese for beginners", "HSK", "comprehensible input chinese",
    "slow chinese", "chinese podcast", "learn mandarin", "chinese pinyin",
    "chinese story", "中文听力", "慢速中文", "中文播客",
]


# ---------- tao toan bo metadata ----------
def generate(ctx):
    seg_meta = ctx.get("_seg_meta") or []
    han_title, viet_title = split_title(ctx.get("title", ""))
    hsk = str(ctx.get("hsk", "") or "HSK1").replace("HSK", "").strip() or "1"
    # chi hien so tap khi user chu dong dat (lesson_parser mac dinh id=1 cho moi bai)
    ep = ctx.get("episode")
    ep_sfx = f" #{ep}" if ep else ""
    channel = ctx.get("channel", "Học Tiếng Trung")

    # Kenh tieng Anh: tieu de dung @title (tieng Anh) lam chinh, chu Han la diem nhan.
    en_title = (ctx.get("title", "") or "").strip()
    han = han_title if has_hanzi(han_title) else (ctx.get("hanzi_title", "") or "")
    titles = [
        f"{en_title} | Learn Chinese Listening HSK{hsk}{ep_sfx} (Hanzi + Pinyin + English CC)",
        f"{en_title} | Chinese Listening Practice HSK{hsk}{ep_sfx} — Comprehensible Input",
        f"{en_title} | Slow Chinese Story HSK{hsk}{ep_sfx} with Pinyin & English",
        f"{en_title} | Improve Your Chinese Listening HSK{hsk}{ep_sfx}",
    ]

    ch_txt = chapters_text(seg_meta)
    tr_txt = transcript_text(seg_meta)
    hashtags = ["#LearnChinese", "#ChineseListening", f"#HSK{hsk}",
                "#Mandarin", "#ComprehensibleInput"]
    next_ep = (int(ep) + 1) if ep and str(ep).isdigit() else None
    next_ep_txt = f"#{next_ep}" if next_ep else "coming tomorrow"
    doc_link = (ctx.get("doc_link") or "").strip()
    doc_block = (f"📄 FREE STUDY GUIDE (Hanzi + Pinyin + English):\n{doc_link}\n\n"
                 if doc_link else "")
    description = f"""🎧 Chinese Listening Practice HSK{hsk} | {en_title}
A "comprehensible input" podcast: slow, natural Chinese with 中文 + Pinyin + English subtitles (CC). Even if you can't read Hanzi yet, you can follow along.

━━━━━━━━━━━━━━━━━━━━
Studying Chinese for ages but still can't catch what people say?
Memorize hundreds of words, then forget them in days? Hanzi still looks like a puzzle?

The fix isn't more memorizing — it's LISTENING to lots of Chinese you can (mostly) understand, the way a child picks up their first language.

No memorizing. No dictionary. No pressure. Just listen every day.

📌 CHAPTERS
{ch_txt}

📚 HOW TO LISTEN
1. Round 1 — read all 3 lines (Hanzi + Pinyin + English), just get the gist.
2. Round 2 — hide the English, follow the Pinyin.
3. Round 3 — look only at the Hanzi and listen again. You'll be surprised how much you catch.
👉 Re-listening (while cooking or commuting) matters more than always starting new episodes.

{doc_block}💜 If this episode helped, share it with a friend who's also learning Chinese.
💬 Comment and tell me — roughly what % did you understand?
🔔 Subscribe for a new listening episode every day.

━━━━━━━━━━━━━━━━━━━━
🎧 {channel} — Train your ears with Chinese, every day. 听中文，练听力。
▶️ Series: Daily Chinese Listening · Next episode {next_ep_txt}

{' '.join(hashtags)}"""

    tags = DEFAULT_TAGS.copy()
    if han_title:
        tags.insert(0, han_title)
        tags.insert(1, f"{han_title} pinyin")
    tags = tags[:20]

    return {
        "title": titles[0],
        "titles": titles,
        "description": description,
        "tags": tags,
        "hashtags": hashtags,
        "chapters": [{"time": t, "label": l} for t, l in build_chapters(seg_meta)],
        "transcript": tr_txt,
        "pinned_comment": pinned_comment(seg_meta, han_title, hsk),
        "srt_hanzi": build_srt(seg_meta, "hanzi"),
        "srt_pinyin": build_srt(seg_meta, "pinyin"),
        "srt_viet": build_srt(seg_meta, "viet"),
        "thumbnail_text": han_title,
        "privacy": "public",
        "category": "27",
        "total_dur": ctx.get("_total_dur", seg_meta[-1]["end"] if seg_meta else 0),
        "channel": channel,
    }
