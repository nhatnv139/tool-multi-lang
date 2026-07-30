# -*- coding: utf-8 -*-
"""Helper VieNeu-TTS v3 Turbo — chay bang .venv-vieneu (Python 3.11).

Duoc generate.synth_vieneu() goi qua subprocess:
    echo "noi dung" | .venv-vieneu/bin/python vieneu_tts.py --voice "Thanh Bình" --out out.wav

Model tai tu cache HuggingFace (~/.cache/huggingface), chay offline tren CPU (ONNX).
Giong preset xem: vieneu/assets/voices_v3_turbo.json (14 giong Bac/Trung/Nam).
"""
import sys, argparse

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", required=True, help="Ten giong preset, vd 'Thanh Bình'")
    ap.add_argument("--out", required=True, help="File wav dau ra (48 kHz)")
    a = ap.parse_args()

    text = sys.stdin.buffer.read().decode("utf-8").strip()
    if not text:
        sys.exit("vieneu_tts: khong co noi dung (stdin rong)")

    from vieneu import Vieneu
    import soundfile as sf
    import numpy as np

    tts = Vieneu()                      # v3turbo, CPU ONNX
    wav = tts.infer(text, voice=a.voice)
    if isinstance(wav, tuple):          # (sr, data) hoac (data, sr) tuy phien ban
        x, y = wav
        sr, data = (x, y) if isinstance(x, int) else (y, x)
    else:
        sr, data = 48000, wav
    sf.write(a.out, np.asarray(data), sr)
    print(f"vieneu_tts OK: {a.out}")

if __name__ == "__main__":
    main()
