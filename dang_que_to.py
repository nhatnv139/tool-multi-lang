# -*- coding: utf-8 -*-
"""Dang 1 bai chu de 12 len kenh Chuyen Que To (hen gio).

    python dang_que_to.py <thu-muc-bai> 2026-10-25T04:00:00Z

Lay: tieu de = khoi ``` dau tien trong title.md; mo ta = muc "PHAN DAN VAO O MO TA" trong
mo-ta.md + muc luc theo canh (tu .seo.json); the = khoi ``` trong muc TAG; thumbnail
<ten>.thumb.jpg; phu de <ten>.srt_viet.srt. Ghi ket qua vao <thu-muc>/dang.json.
"""
import json
import os
import re
import sys

import youtube_upload as yt

CID = "UC1mvnvcjt5yFJKjLCvy_7Ng"   # Chuyen Que To


def doc(p):
    return open(p, encoding="utf-8").read()


def muc_luc(seo_path):
    """'0:58 1.2 · W · mở' -> 1 chuong / canh, ten canh viet hoa chu dau."""
    if not os.path.exists(seo_path):
        return ""
    ch = json.load(open(seo_path, encoding="utf-8")).get("chapters") or ""
    ra, da = [], set()
    for ln in ch.splitlines():
        m = re.match(r"^(\d+:\d+(?::\d+)?)\s+(\d+)\.\d+\s*·\s*[A-Z]\s*·\s*(.+)$", ln.strip())
        if not m or m.group(2) in da:
            continue
        da.add(m.group(2))
        ten = m.group(3).strip()
        ten = "mở đầu" if ten.lower() == "mở" else ten
        ra.append(f"{'0:00' if not ra else m.group(1)} {ten[:1].upper() + ten[1:]}")
    return "\n".join(ra) if len(ra) >= 3 else ""


def main():
    d, gio = os.path.abspath(sys.argv[1]), sys.argv[2]
    ten = os.path.basename(d)
    if os.path.exists(os.path.join(d, "dang.json")):
        raise SystemExit(f"{ten}: da dang roi (dang.json)")
    tt = doc(os.path.join(d, "title.md"))
    title = re.search(r"```\s*\n(.+?)\n```", tt, re.S).group(1).strip()
    mt = doc(os.path.join(d, "mo-ta.md"))
    than = re.search(r"##\s*PHẦN DÁN VÀO Ô MÔ TẢ\s*\n(.+?)\n##\s*TAG", mt, re.S).group(1).strip()
    tags = re.search(r"##\s*TAG.*?```\s*\n(.+?)\n```", mt, re.S).group(1).strip()
    ml = muc_luc(os.path.join(d, ten + ".seo.json"))
    if ml:   # muc luc chen truoc dong hashtag
        p = than.rsplit("\n\n", 1)
        than = p[0] + "\n\n" + ml + "\n\n" + p[1] if len(p) == 2 else than + "\n\n" + ml
    assert len(title) <= 100, title
    print(ten, "|", title, "|", gio)
    r = yt.upload(CID, os.path.join(d, ten + ".mp4"), title, than, tags, publish_at=gio)
    print("  video:", r["url"])
    ket = {"id": r["id"], "url": r["url"], "title": title, "publish_at": gio}
    for buoc, f in (("thumb", lambda: yt.set_thumbnail(CID, r["id"], os.path.join(d, ten + ".thumb.jpg"))),
                    ("srt", lambda: yt.upload_caption(CID, r["id"], doc(os.path.join(d, ten + ".srt_viet.srt")),
                                                      "vi", "Tiếng Việt"))):
        try:
            f(); ket[buoc] = "ok"
        except Exception as e:
            ket[buoc] = f"loi: {e}"
        print(f"  {buoc}: {ket[buoc]}")
    json.dump(ket, open(os.path.join(d, "dang.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
