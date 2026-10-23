# -*- coding: utf-8 -*-
"""do_nhip_doc.py — do do MUOT cua loi doc trong mot video/audio phim.

Tach giong ra (bo nhac nen bang loc bang tan giong), tim cac khoang lang bang
ffmpeg silencedetect, roi in:
  - so khoang nghi, phan bo do dai (bao nhieu cho > 1s = "bi ngat")
  - toc do am tiet/phut tren thoi gian NOI that (khong tinh lang)
Dung de so ban 'doc lien' voi ban 'vai tro' (cat tung cau).

    python do_nhip_doc.py video.mp4 [--script content-film.md]
"""
import re, sys, subprocess, argparse


def khoang_lang(path, nguong_db=-34, toi_thieu=0.25):
    # giong nam 100-4000Hz; nhac nen da bi duck nen nguong -34dB tach duoc cho lang
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-vn",
                        "-af", f"highpass=f=120,lowpass=f=4000,silencedetect=n={nguong_db}dB:d={toi_thieu}",
                        "-f", "null", "-"], capture_output=True, text=True, errors="replace")
    ss = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ds = [float(x) for x in re.findall(r"silence_duration: ([\d.]+)", r.stderr)]
    dur = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    tong = int(dur.group(1)) * 3600 + int(dur.group(2)) * 60 + float(dur.group(3)) if dur else 0
    return list(zip(ss, ds)), tong


def am_tiet(script):
    n = 0
    for ln in open(script, encoding="utf-8"):
        s = ln.strip()
        if not s or s.startswith(("#", "@", "//", "---")):
            continue
        n += len(re.findall(r"\w+", s))
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--script", default="")
    a = ap.parse_args()
    gaps, tong = khoang_lang(a.path)
    # bo khoang lang dau/cuoi phim (bia, fade)
    gaps = [g for g in gaps if g[0] > 1.0 and g[0] + g[1] < tong - 1.0]
    d = sorted(g[1] for g in gaps)
    lang = sum(d)
    print(f"Dai {tong:.1f}s · {len(d)} khoang nghi · tong lang {lang:.1f}s ({lang / max(tong, 1) * 100:.0f}%)")
    if d:
        bins = [(0.25, 0.5), (0.5, 0.8), (0.8, 1.2), (1.2, 2.0), (2.0, 99)]
        for lo, hi in bins:
            k = sum(1 for x in d if lo <= x < hi)
            print(f"  {lo:>4}-{hi if hi < 99 else '…':<4}s : {k:3d} {'#' * k}")
        print(f"  trung vi {d[len(d) // 2]:.2f}s · dai nhat {d[-1]:.2f}s")
    if a.script:
        n = am_tiet(a.script)
        noi = tong - lang
        print(f"{n} am tiet · {n / (tong / 60):.0f} a/p tren ca phim · {n / (noi / 60):.0f} a/p luc dang noi")


if __name__ == "__main__":
    main()
