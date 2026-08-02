# -*- coding: utf-8 -*-
"""retone.py — Chỉnh tone (pitch) audio của video ĐÃ render, không đổi tốc độ, giữ nguyên hình.

Giống voice effect CapCut áp lên clip có sẵn. Video stream được copy (không re-encode)
nên chạy rất nhanh; chỉ audio được xử lý lại.

LƯU Ý: nhạc nền đã mix chung 1 track với giọng đọc -> pitch dịch cả nhạc.
Dịch nhẹ (±1..3 semitone) nghe vẫn tự nhiên; muốn chỉ đổi giọng thì đổi
"voice": "...@-20Hz" trong JSON rồi render lại.

Dùng:
    python retone.py input.mp4 -2            # trầm xuống 2 semitone -> input.tone-2.mp4
    python retone.py input.mp4 +3 -o out.mp4 # cao lên 3 semitone
"""
import os, subprocess, sys


def retone(inp, semitones, out=None):
    f = 2 ** (semitones / 12.0)              # semitone -> hệ số tần số
    sr = 44100
    if out is None:
        root, ext = os.path.splitext(inp)
        out = f"{root}.tone{semitones:+g}{ext}"
    # asetrate đổi pitch nhưng làm nhanh/chậm theo -> atempo bù lại đúng tốc độ gốc
    af = f"asetrate={sr}*{f:.6f},aresample={sr},atempo={1/f:.6f}"
    cmd = ["ffmpeg", "-y", "-i", inp, "-vcodec", "copy",
           "-af", af, "-c:a", "aac", "-b:a", "192k", out]
    subprocess.run(cmd, check=True, capture_output=True)
    return out


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    inp, st = sys.argv[1], float(sys.argv[2])
    out = None
    if "-o" in sys.argv:
        out = sys.argv[sys.argv.index("-o") + 1]
    print("->", retone(inp, st, out))
