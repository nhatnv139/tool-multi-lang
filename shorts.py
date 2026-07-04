# -*- coding: utf-8 -*-
"""Cat video ngang (16:9) thanh YouTube Shorts doc (9:16, 1080x1920).

Dung meta.json (timestamp tung cau) de cat DUNG RANH GIOI CAU:
  - chon N doan 25-58s rai deu theo video, uu tien cau co do dai dep
  - nen: chinh frame do phong to + lam mo; giua: frame goc; tren/duoi: hook + CTA
  - moi short kem file .txt goi y tieu de/mo ta/hashtag

Dung:
    python3 shorts.py output/video.mp4                # 3 shorts tu dong
    python3 shorts.py output/video.mp4 --n 5
    python3 shorts.py output/video.mp4 --at 02:15 --at 07:40   # tu chon moc
"""
import os, sys, json, re, argparse, subprocess
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import style_pastel
from seo import split_title

SW, SH = 1080, 1920
TARGET, MIN_D, MAX_D = 38.0, 25.0, 58.0


def _mmss_to_sec(s):
    m = re.match(r"^(\d{1,2}):(\d{2})$", s.strip())
    if not m:
        raise ValueError(f"moc thoi gian sai: {s} (dung mm:ss)")
    return int(m.group(1)) * 60 + int(m.group(2))


def load_meta(video):
    meta_path = video + ".meta.json"
    if not os.path.exists(meta_path):
        raise SystemExit(f"khong thay {meta_path} — can meta de cat dung cau")
    with open(meta_path, encoding="utf-8") as f:
        return json.load(f)


def _score_seg(s):
    """Cau 'dat' de mo dau short: cau ke, do dai vua, khong phai muc luc."""
    han = s.get("hanzi", "")
    if not han or s.get("type") not in ("sentence", "vocab", "dialogue", "practice_a"):
        return -1
    n = len([c for c in han if "一" <= c <= "鿿"])
    if not (6 <= n <= 26):
        return 0
    sc = 10 - abs(n - 14) * 0.4
    if s.get("viet"):
        sc += 2
    return sc


def pick_windows(segs, n, at=None):
    """Tra ve [(start, dur, first_seg)] — moi window gom cau lien tiep 25-58s."""
    segs = [s for s in segs if s.get("hanzi")]
    if not segs:
        raise SystemExit("meta khong co cau nao")

    def grow(i0):
        st = segs[i0]["start"]
        end = st
        for s in segs[i0:]:
            if s["end"] - st > MAX_D:
                break
            end = s["end"]
            if end - st >= TARGET:
                break
        return (st, max(MIN_D, end - st), segs[i0])

    if at:                                   # nguoi dung tu chon moc
        out = []
        for t in at:
            i0 = min(range(len(segs)), key=lambda i: abs(segs[i]["start"] - t))
            out.append(grow(i0))
        return out

    total = segs[-1]["end"]
    out, used = [], []
    for k in range(n):                       # rai deu, moi vung chon cau diem cao nhat
        lo = total * k / n
        hi = total * (k + 1) / n
        cand = [i for i, s in enumerate(segs) if lo <= s["start"] < hi]
        if not cand:
            continue
        best = max(cand, key=lambda i: _score_seg(segs[i]))
        if _score_seg(segs[best]) <= 0:
            best = cand[len(cand) // 2]
        w = grow(best)
        if all(abs(w[0] - u) > MIN_D for u in used):
            used.append(w[0])
            out.append(w)
    return out


def make_overlay(hook, cta, path):
    """PNG 1080x1920 trong suot: hook tren (nen toi mo), CTA duoi."""
    im = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    hf = style_pastel.font("viet", 64)
    lines = style_pastel.wrap_text(d, hook, hf, SW - 120)[:3]
    bh = len(lines) * (hf.size + 12) + 70
    d.rounded_rectangle([30, 90, SW - 30, 90 + bh], radius=28, fill=(15, 15, 22, 175))
    y = 90 + 34
    for ln in lines:
        tw = style_pastel.text_w(d, ln, hf)
        d.text(((SW - tw) // 2, y), ln, font=hf, fill=(255, 255, 255))
        y += hf.size + 12
    cf = style_pastel.font("sansb", 44)
    tw = style_pastel.text_w(d, cta, cf)
    d.rounded_rectangle([(SW - tw) // 2 - 36, SH - 260, (SW + tw) // 2 + 36, SH - 175],
                        radius=24, fill=(255, 200, 40, 235))
    d.text(((SW - tw) // 2, SH - 242), cta, font=cf, fill=(40, 30, 10))
    im.save(path)
    return path


def cut_short(video, start, dur, overlay, out):
    vf = (f"[0:v]scale={SW}:{SH}:force_original_aspect_ratio=increase,"
          f"crop={SW}:{SH},boxblur=22:4[bg];"
          f"[0:v]scale={SW}:-2[fg];"
          f"[bg][fg]overlay=(W-w)/2:(H-h)/2[v1];"
          f"[v1][1:v]overlay=0:0,format=yuv420p[v]")
    subprocess.run(["ffmpeg", "-y", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}",
                    "-i", video, "-i", overlay,
                    "-filter_complex", vf, "-map", "[v]", "-map", "0:a?",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    "-c:a", "aac", "-b:a", "160k", out],
                   check=True, capture_output=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--at", action="append", help="moc mm:ss (lap lai duoc)")
    ap.add_argument("--cta", default="Xem bài đầy đủ 20 phút trên kênh")
    args = ap.parse_args()

    video = os.path.abspath(args.video)
    meta = load_meta(video)
    han_title, viet_title = split_title(meta.get("title", ""))
    at = [float(_mmss_to_sec(t)) for t in args.at] if args.at else None
    wins = pick_windows(meta["segments"], args.n, at)

    out_dir = os.path.join(os.path.dirname(video), "shorts")
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(video))[0][:40]

    made = []
    for i, (st, dur, seg) in enumerate(wins, 1):
        hook = (seg.get("viet") or viet_title or "").strip()
        ovl = os.path.join(out_dir, f"_ovl{i}.png")
        make_overlay(hook, args.cta, ovl)
        out = os.path.join(out_dir, f"{base}_short{i}.mp4")
        print(f"  short {i}: {st:7.1f}s +{dur:.0f}s — {hook[:50]}")
        cut_short(video, st, dur, ovl, out)
        os.remove(ovl)
        # goi y metadata dang kem
        title = f"{hook[:70]} | Tiếng Trung mỗi ngày #Shorts"
        desc = (f"{seg.get('hanzi','')}\n{hook}\n\n"
                f"🎧 Bài đầy đủ ({viet_title}) dài 20 phút có trên kênh!\n"
                "#hoctiengtrung #luyennghetiengtrung #shorts #tiengtrung #chinese")
        with open(out + ".txt", "w", encoding="utf-8") as f:
            f.write(title + "\n\n" + desc + "\n")
        made.append(out)

    print(f"\n✅ {len(made)} shorts -> {out_dir}")
    for m in made:
        print("  -", os.path.basename(m))


if __name__ == "__main__":
    main()
