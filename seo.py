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
    ("早上", "Buổi sáng"), ("早晨", "Buổi sáng"), ("清晨", "Buổi sáng"),
    ("起床", "Thức dậy"), ("早饭", "Bữa sáng"), ("早餐", "Bữa sáng"),
    ("上班", "Đi làm"), ("公司", "Ở công ty"), ("上午", "Buổi sáng (làm việc)"),
    ("中午", "Buổi trưa"), ("午饭", "Bữa trưa"), ("午餐", "Bữa trưa"),
    ("下午", "Buổi chiều"), ("下班", "Tan làm"),
    ("回家", "Về nhà"), ("晚上", "Buổi tối"), ("做饭", "Nấu cơm"), ("晚饭", "Bữa tối"),
    ("睡觉", "Đi ngủ"), ("睡前", "Trước khi ngủ"),
]

def build_chapters(seg_meta):
    """[(mmss,label)] tu thoi luong that. Uu tien section -> tu khoa noi dung -> chia deu.
       Luon co 00:00, >=3 chuong cho YouTube."""
    if not seg_meta:
        return [("00:00", "Bắt đầu")]
    chapters = []
    # 1) segment 'section' lam moc
    for s in seg_meta:
        t, lbl = s["type"], (s.get("label") or "").strip()
        if t in ("title", "objectives") and not chapters:
            chapters.append((0.0, "Mở đầu"))
        elif t == "section" and lbl:
            chapters.append((s["start"], lbl.capitalize()))
        elif t == "practice_q":
            chapters.append((s["start"], "Luyện tập"))

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
                chapters.insert(0, (0.0, "Mở đầu"))

    # 3) van it -> chia deu theo thoi gian
    if len(chapters) < 3:
        total = seg_meta[-1]["end"]
        parts = 4 if total >= 180 else 3
        chapters = [(0.0, "Mở đầu")]
        for k in range(1, parts):
            target = total * k / parts
            seg = min(seg_meta, key=lambda s: abs(s["start"] - target))
            chapters.append((seg["start"], f"Phần {k + 1}"))

    if not chapters or chapters[0][0] > 0:
        chapters.insert(0, (0.0, "Mở đầu"))
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
    lines = [f"📌 TỪ VỰNG TRỌNG TÂM — {han_title} (HSK{hsk})",
             "Lưu lại rồi nghe lại video nhé! 👇", ""]
    for w in words:
        lines.append(f"{w}  {pinyin_of(w)}  – ")
    lines.append("")
    lines.append("💬 Bạn nhớ được mấy từ rồi? Comment nhé! 加油 💪")
    return "\n".join(lines)


# ---------- tags ----------
DEFAULT_TAGS = [
    "luyện nghe tiếng Trung", "học tiếng Trung cho người Việt",
    "tiếng Trung cho người mới", "học tiếng Trung từ đầu",
    "nghe hiểu tiếng Trung", "tieng trung cho nguoi moi",
    "học tiếng Trung qua câu chuyện", "chinese podcast cho người Việt",
    "慢速中文", "中文播客", "learn chinese for beginners",
    "chinese listening practice", "comprehensible input chinese",
]


# ---------- tao toan bo metadata ----------
def generate(ctx):
    seg_meta = ctx.get("_seg_meta") or []
    han_title, viet_title = split_title(ctx.get("title", ""))
    hsk = str(ctx.get("hsk", "") or "HSK1").replace("HSK", "").strip() or "1"
    ep = ctx.get("episode") or ctx.get("id") or 1
    channel = ctx.get("channel", "Học Tiếng Trung")

    base = f"{han_title} {viet_title}".strip()
    titles = [
        f"{base} | Luyện nghe tiếng Trung HSK{hsk} #{ep} (phụ đề Việt + pinyin)",
        f"{han_title} | Học tiếng Trung cho người Việt HSK{hsk} #{ep} — Nghe hiểu cơ bản",
        f"{viet_title} {han_title} | Tiếng Trung cho người mới HSK{hsk} #{ep} + pinyin",
        f"{han_title} {viet_title} | Luyện nghe tiếng Trung HSK{hsk} có phụ đề #{ep}",
    ]

    ch_txt = chapters_text(seg_meta)
    tr_txt = transcript_text(seg_meta)
    hashtags = ["#luyennghetiengtrung", f"#HSK{hsk}", "#tiengtrungchonguoiviet"]
    next_ep = (int(ep) + 1) if str(ep).isdigit() else ep
    # thay transcript bang link Google Drive (tai lieu day du) neu co
    doc_link = (ctx.get("doc_link") or "").strip()
    if doc_link:
        doc_section = ("📄 TÀI LIỆU BÀI HỌC (chữ Hán + pinyin + nghĩa Việt) — "
                       f"xem & tải tại:\n{doc_link}")
    else:
        doc_section = "📄 Tài liệu bài học đầy đủ: (đang cập nhật)"
    description = f"""🎧 Luyện nghe tiếng Trung HSK{hsk} cho người Việt mới bắt đầu — "{han_title} / {viet_title}", đọc chậm, có chữ Hán + pinyin + nghĩa tiếng Việt + phụ đề CC.
👉 Bạn chỉ cần NGHE và NHÌN CHỮ — phương pháp "nghe hiểu" (comprehensible input).

━━━━━━━━━━━━━━━━━━━━
📖 TRONG TẬP NÀY
• Trình độ: HSK{hsk} (người mới bắt đầu)
• Giọng kể chậm, ngắt câu rõ + nhạc nền nhẹ
• Trên màn hình: 中文 (chữ Hán) + pinyin + nghĩa tiếng Việt
• 📑 Phụ đề CC: chữ Hán / pinyin / tiếng Việt (bật nút CC để chọn)

⏱️ NỘI DUNG
{ch_txt}

📚 CÁCH HỌC HIỆU QUẢ
1. Nghe lần 1: chỉ nghe, không nhìn chữ.
2. Nghe lần 2: nhìn pinyin + nghĩa Việt.
3. Nghe lần 3: nói nhẩm theo (shadowing).
4. Học từ vựng ở bình luận ghim 📌 rồi nghe lại.

{' '.join(hashtags)}

━━━━━━━━━━━━━━━━━━━━
🔔 Đăng ký kênh để học tiếng Trung mỗi tuần!

━━━━━━━━━━━━━━━━━━━━
{doc_section}

━━━━━━━━━━━━━━━━━━━━
💬 Hãy kể cho mình nghe ở phần bình luận nhé! 👍 Like + Đăng ký để xem tập tiếp theo #{next_ep}."""

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
