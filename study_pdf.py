# -*- coding: utf-8 -*-
"""study_pdf.py — Xuất NỘI DUNG BÀI ĐỌC thành PDF 'Study Guide' đẹp (Hán + pinyin tô thanh điệu + nghĩa).
Convert HTML -> PDF bằng Chrome headless (full CSS, chữ Hán/pinyin/Việt sắc nét)."""
import os, re, subprocess, html as _html, tempfile, shutil
from pypinyin import pinyin as _pin, Style as _PS

_HERE = os.path.dirname(os.path.abspath(__file__))
_CHROME = next((p for p in [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("google-chrome") or "", shutil.which("chromium") or ""] if p and os.path.exists(p)), None)

# màu thanh điệu (đồng bộ với video): 1 đỏ · 2 cam · 3 lục · 4 lam · nhẹ xám
_TONE = {1: "#e0564e", 2: "#d98a2b", 3: "#3f9d55", 4: "#3f74c0", 0: "#8a8a8a"}
_TONEMARK = {1: "āēīōūǖ", 2: "áéíóúǘ", 3: "ǎěǐǒǔǚ", 4: "àèìòùǜ"}

def _tone_of(syl):
    for ch in syl:
        for t, marks in _TONEMARK.items():
            if ch in marks:
                return t
    return 0

def _pinyin_html(hz):
    """Pinyin tô màu thanh điệu (mỗi âm tiết 1 màu) cho câu Hán."""
    out = []
    for seg in _pin(hz, style=_PS.TONE, errors=lambda x: [c for c in x]):
        syl = seg[0]
        if re.search(r"[一-鿿]", "".join(seg)) or not syl.strip():
            out.append(_html.escape(syl)); continue
        col = _TONE[_tone_of(syl)]
        out.append(f'<span style="color:{col}">{_html.escape(syl)}</span>')
    return " ".join(o for o in out if o.strip())


def _parse(content):
    """content.md -> (meta, blocks). block = ('sec', label) | ('card', hz, vi) | ('vocab', text)."""
    meta = {"title": "", "header": "", "hanzi": ""}
    blocks, in_appendix = [], False
    for raw in (content or "").splitlines():
        line = raw.rstrip()
        s = line.strip()
        if not s:
            continue
        if re.match(r"^-{3,}$", s):
            in_appendix = True
            blocks.append(("sec", "📚 Từ vựng & mẫu câu")); continue
        if s.startswith("@"):
            k, _, v = s[1:].partition(" ")
            k = k.lower().strip()
            if k in meta:
                meta[k] = v.strip()
            continue
        if s.startswith("#"):
            lab = s.lstrip("#").strip()
            if lab:
                blocks.append(("sec", lab))
            continue
        if in_appendix:
            blocks.append(("vocab", s.lstrip("-* ").strip())); continue
        # câu 'Hán | nghĩa' — bỏ tag {emo} nếu có
        hz, _, vi = line.partition("|")
        hz = re.sub(r"^\s*\{[a-zA-Z]+\}\s*", "", hz).strip()
        vi = vi.strip()
        if hz:
            blocks.append(("card", hz, vi))
    return meta, blocks


_CSS = """
:root{ --accent:#c0602e; --accent2:#e0a05a; --han:#241f1c; --eng:#4a4038;
       --card:#fbf8f4; --line:#ece1d5; --sub:#9a8c7d; --bg:#ffffff; }
*{ box-sizing:border-box; }
@page{ size:A4; margin:16mm 14mm 18mm;
  @bottom-center{ content:"Học tiếng Trung mỗi ngày  ·  " counter(page) " / " counter(pages);
                  font-family:sans-serif; font-size:9px; color:#b7a897; } }
html,body{ margin:0; background:var(--bg); }
body{ font-family:"PingFang SC","Hiragino Sans GB","Noto Sans SC",
      -apple-system,"Segoe UI",Roboto,Arial,sans-serif; color:var(--eng); }
.wrap{ max-width:820px; margin:0 auto; padding:6px 6px 30px; }
/* ---- COVER ---- */
.cover{ text-align:center; padding:20px 10px 8px; border-bottom:2px solid var(--accent);
        margin-bottom:26px; }
.cover .kick{ letter-spacing:3px; text-transform:uppercase; color:var(--accent);
        font-size:12px; font-weight:700; margin-bottom:12px; }
.cover .hz{ font-size:40px; font-weight:800; color:var(--han); letter-spacing:2px; margin:2px 0 6px; }
.cover h1{ font-size:30px; font-weight:800; color:var(--accent); margin:6px 0 8px; line-height:1.25; }
.cover .sub{ color:var(--sub); font-size:14px; margin:0; }
.cover .band{ height:6px; width:120px; margin:16px auto 0; border-radius:6px;
        background:linear-gradient(90deg,var(--accent),var(--accent2)); }
/* ---- SECTION ---- */
.sec{ display:flex; align-items:center; gap:10px; margin:26px 0 12px; break-after:avoid; }
.sec .t{ color:var(--accent); font-size:17px; font-weight:800; white-space:nowrap; }
.sec .l{ flex:1; height:1px; background:var(--line); }
/* ---- CARD (mỗi câu) ---- */
.card{ background:var(--card); border:1px solid var(--line); border-left:4px solid var(--accent);
       border-radius:10px; padding:13px 18px; margin:0 0 11px; break-inside:avoid; }
.card .han{ color:var(--han); font-size:20px; font-weight:700; line-height:1.6; margin:0 0 5px; }
.card .py{ font-size:14px; line-height:1.5; margin:0 0 7px; font-style:normal; letter-spacing:.3px; }
.card .eng{ color:var(--eng); font-size:14.5px; line-height:1.55; margin:0; }
/* ---- VOCAB ---- */
.vocab{ background:#fff6ec; border:1px solid #f0d9bf; border-radius:8px;
        padding:8px 14px; margin:0 0 8px; font-size:14.5px; color:#6b4a2b; break-inside:avoid; }
.vocab b{ color:var(--accent); }
.foot{ text-align:center; color:var(--sub); font-size:12px; margin-top:26px;
       padding-top:14px; border-top:1px solid var(--line); }
@media print{ .card,.vocab{ box-shadow:none; } }
"""

def build_html(content, channel="Học tiếng Trung mỗi ngày", level="HSK · Luyện nghe", link=""):
    meta, blocks = _parse(content)
    title = meta.get("title") or "Bài đọc tiếng Trung"
    header = meta.get("header") or f"{channel} · {level}"
    hz_title = meta.get("hanzi", "")
    parts = [f'<!doctype html><html lang="vi"><head><meta charset="utf-8">',
             f'<title>{_html.escape(title)}</title><style>{_CSS}</style></head><body><div class="wrap">']
    parts.append('<div class="cover">'
                 f'<div class="kick">{_html.escape(header)}</div>'
                 + (f'<div class="hz">{_html.escape(hz_title)}</div>' if hz_title else "")
                 + f'<h1>{_html.escape(title)}</h1>'
                 f'<p class="sub">Hán tự · Pinyin (tô thanh điệu) · Nghĩa — bản học kèm video</p>'
                 '<div class="band"></div></div>')
    for b in blocks:
        if b[0] == "sec":
            parts.append(f'<div class="sec"><span class="t">{_html.escape(b[1])}</span><span class="l"></span></div>')
        elif b[0] == "vocab":
            txt = _html.escape(b[1])
            txt = re.sub(r"^([^—\-(（]+)", r"<b>\1</b>", txt)     # tô đậm từ đứng đầu
            parts.append(f'<div class="vocab">{txt}</div>')
        else:
            hz, vi = b[1], b[2]
            parts.append('<div class="card">'
                         f'<p class="han">{_html.escape(hz)}</p>'
                         f'<p class="py">{_pinyin_html(hz)}</p>'
                         + (f'<p class="eng">{_html.escape(vi)}</p>' if vi else "")
                         + '</div>')
    foot = "Tài liệu học kèm video — chúc bạn học vui!"
    if link:
        foot += f'<br>▶ {_html.escape(link)}'
    parts.append(f'<div class="foot">{foot}</div></div></body></html>')
    return "".join(parts)


def build_pdf(content, out_pdf, channel="Học tiếng Trung mỗi ngày", level="HSK · Luyện nghe", link=""):
    """Tạo PDF từ content. Trả out_pdf. Cần Chrome (headless print-to-pdf)."""
    if not _CHROME:
        raise RuntimeError("Không tìm thấy Google Chrome để tạo PDF.")
    html_str = build_html(content, channel=channel, level=level, link=link)
    tmp = tempfile.mkdtemp(prefix="studypdf_")
    hpath = os.path.join(tmp, "guide.html")
    with open(hpath, "w", encoding="utf-8") as f:
        f.write(html_str)
    subprocess.run([_CHROME, "--headless", "--disable-gpu", "--no-sandbox",
                    "--no-pdf-header-footer", f"--print-to-pdf={out_pdf}",
                    "file://" + hpath], check=True, capture_output=True, timeout=60)
    try:
        shutil.rmtree(tmp)
    except OSError:
        pass
    return out_pdf


if __name__ == "__main__":
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else ""
    txt = open(src, encoding="utf-8").read() if src and os.path.exists(src) else "@title Demo\n你好世界。 | Xin chào thế giới."
    print(build_pdf(txt, "/tmp/study_demo.pdf"))
