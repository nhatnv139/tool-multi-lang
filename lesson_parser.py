# -*- coding: utf-8 -*-
"""Parse noi dung dang text (de gui tu ChatGPT) thanh ctx + segments.

Dinh dang:
    @title CHÀO HỎI
    @hanzi 你好              (tuy chon - chu Han o slide tieu de)
    @topic cách chào hỏi     (tuy chon - cau gioi thieu trong intro)
    @hsk HSK1                (tuy chon)
    @objectives Cách chào; Cách cảm ơn; Tạm biệt   (tuy chon, ngan cach ;)

    # TỪ VỰNG
    你好 | Xin chào
    谢谢 | Cảm ơn

    # MẪU CÂU
    你好吗？ | Bạn khỏe không?

    # HỘI THOẠI
    A: 你好！ | Xin chào!
    B: 你好！ | Xin chào!

    # LUYỆN TẬP
    ? "Cảm ơn" nói thế nào?      (tuy chon - cau hoi)
    谢谢 | Cảm ơn                 (dap an)
"""
import re

def _section_type(name):
    u = name.upper()
    if "VỰNG" in u or "VOCAB" in u or "TỪ" in u:        return "vocab"
    if "HỘI" in u or "THOẠI" in u or "DIALOG" in u:     return "dialogue"
    if "LUYỆN" in u or "PRACTICE" in u or "TẬP" in u:   return "practice"
    if "MẪU" in u or "CÂU" in u or "SENTENCE" in u:     return "sentence"
    return "sentence"

def _split_item(line):
    """'hanzi | viet' -> (hanzi, viet)."""
    if "|" in line:
        a, b = line.split("|", 1)
        return a.strip(), b.strip()
    return line.strip(), ""

def parse_lesson(text):
    """Tra ve ctx dict: title, hanzi_title, topic, hsk, segments[...]."""
    meta = {"title": "BÀI HỌC", "hanzi_title": "", "topic": "", "hsk": "HSK1",
            "objectives": [], "image_prompt": "", "header": "", "hsk_explicit": False}
    sections = []           # [(label, type, [items])]
    cur = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("@"):
            key, _, val = line[1:].partition(" ")
            key, val = key.strip().lower(), val.strip()
            if key == "objectives":
                meta["objectives"] = [s.strip() for s in val.split(";") if s.strip()]
            elif key == "title":       meta["title"] = val
            elif key == "hanzi":       meta["hanzi_title"] = val
            elif key == "topic":       meta["topic"] = val
            elif key == "hsk":         meta["hsk"] = val; meta["hsk_explicit"] = True
            elif key == "image":       meta["image_prompt"] = val
            elif key == "header":      meta["header"] = val
            continue
        if line.startswith("#"):
            label = line.lstrip("#").strip()
            cur = {"label": label, "type": _section_type(label),
                   "items": [], "explicit": True}
            sections.append(cur)
            continue
        if cur is None:                # dong le (khong co #) -> cau, KHONG divider
            cur = {"label": "", "type": "sentence", "items": [], "explicit": False}
            sections.append(cur)
        cur["items"].append(line)

    # ---- dung segments ----
    segs = [{"type": "title"}]
    if meta["objectives"]:
        segs.append({"type": "objectives", "lines": meta["objectives"]})

    for sec in sections:
        if not sec["items"]:
            continue
        if sec.get("explicit"):        # chi them divider khi co dong '#'
            segs.append({"type": "section", "label": sec["label"].upper()})
        st = sec["type"]
        if st == "dialogue":
            rows = []
            for it in sec["items"]:
                sp = ""
                body = it
                head = it.split("|", 1)[0]          # chi xet phan truoc dau '|'
                # nhan nguoi noi: 'A:' / 'B：' / '小明:' ... (ho tro ca ':' va '：')
                m = re.match(r"^\s*([A-Za-z0-9一-鿿]{1,12})\s*[:：]\s*", head)
                if m:
                    sp = m.group(1).strip()
                    body = it[m.end():]            # phan con lai: 'hanzi | viet'
                hz, vi = _split_item(body)
                rows.append({"sp": sp or "A", "hanzi": hz, "pinyin": "", "viet": vi})
            segs.append({"type": "dialogue", "rows": rows})
        elif st == "practice":
            for it in sec["items"]:
                if it.startswith("?"):
                    segs.append({"type": "practice_q", "question": it[1:].strip()})
                else:
                    hz, vi = _split_item(it)
                    segs.append({"type": "practice_a", "hanzi": hz, "pinyin": "", "viet": vi})
        else:                                       # vocab / sentence
            for it in sec["items"]:
                hz, vi = _split_item(it)
                segs.append({"type": st, "hanzi": hz, "pinyin": "", "viet": vi})

    segs.append({"type": "outro"})

    # hanzi_title mac dinh: lay tu vung dau tien
    if not meta["hanzi_title"]:
        for s in segs:
            if s.get("type") in ("vocab", "sentence") and s.get("hanzi"):
                meta["hanzi_title"] = s["hanzi"][:2]
                break
        if not meta["hanzi_title"]:
            meta["hanzi_title"] = "学习"
    if not meta["topic"]:
        meta["topic"] = meta["title"].lower()

    return {
        "id": 1, "hsk": meta["hsk"], "title": meta["title"],
        "topic": meta["topic"], "hanzi_title": meta["hanzi_title"],
        "image_prompt": meta["image_prompt"], "header": meta["header"],
        "hsk_explicit": meta["hsk_explicit"],
        "segments": segs,
    }

if __name__ == "__main__":
    sample = """@title CHÀO HỎI
@hanzi 你好

# TỪ VỰNG
你好 | Xin chào
谢谢 | Cảm ơn

# MẪU CÂU
你好吗？ | Bạn khỏe không?

# HỘI THOẠI
A: 你好！ | Xin chào!
B: 我很好，谢谢！ | Tôi khỏe, cảm ơn!

# LUYỆN TẬP
? "Cảm ơn" nói thế nào?
谢谢 | Cảm ơn
"""
    import json
    print(json.dumps(parse_lesson(sample), ensure_ascii=False, indent=2))
