# -*- coding: utf-8 -*-
"""Helper VieNeu-TTS v3 Turbo — chay bang .venv-vieneu (Python 3.11).

Duoc generate.synth_vieneu() goi qua subprocess:
    echo "noi dung" | .venv-vieneu/bin/python vieneu_tts.py --voice "Thanh Bình" --out out.wav

Model tai tu cache HuggingFace (~/.cache/huggingface), chay offline tren CPU (ONNX).
Giong preset xem: vieneu/assets/voices_v3_turbo.json (14 giong Bac/Trung/Nam).
"""
import sys, os, re, json, argparse

_HERE = os.path.dirname(os.path.abspath(__file__))
_CLONES = os.path.join(_HERE, "voice_clones.json")


def _clone_ref(name):
    """Tra duong dan file mau am thanh cua giong CLONE 'name' (hoac None neu khong co).
    Giong clone khong nam trong preset cua VieNeu -> phai add_voice truoc khi infer,
    neu khong se loi: Voice '...' not found."""
    try:
        with open(_CLONES, encoding="utf-8") as f:
            cfg = json.load(f).get("voices") or {}
    except (OSError, ValueError):
        return None
    item = cfg.get(name)
    if not item:
        return None
    ref = item.get("ref") if isinstance(item, dict) else str(item)
    if not ref:
        return None
    ref = ref if os.path.isabs(ref) else os.path.join(_HERE, ref)
    return ref if os.path.exists(ref) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", required=True, help="Ten giong preset, vd 'Thanh Bình'")
    ap.add_argument("--out", required=True, help="File wav dau ra (48 kHz)")
    # Phim ke chuyen: style 'doc_truyen' + temperature thap -> ngu dieu on dinh giua
    # cac lan goi (moi canh 1 request; temp 0.8 mac dinh lam giong "nhay" tung canh).
    # 'doc_truyen' doc deu va nhanh; 'tu_nhien' len xuong nhieu hon (do: F0 std 79 vs 73,
    # dai dong 16.4 vs 13.9 dB tren cung mot cau) -> mac dinh ke chuyen dung 'tu_nhien'.
    ap.add_argument("--style", default="tu_nhien", help="tu_nhien | tin_tuc | doc_truyen")
    # CAM XUC — thu vien mac dinh EP CUNG <|emotion_0|> ("natural") cho MOI cau, do la
    # ly do giong clone doc phang du mau doc co cam xuc. Checkpoint co 8 token 0..7:
    #   0 natural · 1 [cười] · 2 [thở dài] · 3 [hắng giọng] · 4..7 khong tai lieu.
    # Do thuc te: 4 = nhan nha manh nhat (dai dong 20.1 dB, hon mac dinh 6 dB) -> mac dinh 4.
    # Van co the ghi thang <|emotion_k|> hoac [thở dài] giua text de doi theo tung cau.
    ap.add_argument("--emotion", default="4",
                    help="0..7 hoac rong = de thu vien tu quyet (0 = phang)")
    # temperature 0.6 (cu) lam ngu dieu det, doc nhu robot; 0.9 + top_p 0.96 thi
    # THI THOANG NGONG (sampling chon nham am o duoi phan phoi). 0.85/0.92/30 la diem
    # can bang: van len xuong (da co emotion_4 lo phan dien cam) ma bot han tieng ngong.
    ap.add_argument("--temperature", type=float, default=0.85)
    ap.add_argument("--top-p", type=float, default=0.92, dest="top_p")
    ap.add_argument("--top-k", type=int, default=30, dest="top_k")
    # NGAT NGHI — 2 gat that su co tac dung (khac 'silence_p' cua infer: no bi bo qua
    # khi thu vien tu tinh silence theo ranh gioi chunk):
    #  --max-chars: nguong cat chunk. Mac dinh thu vien 256 -> ca doan van thanh 1 chunk
    #    -> KHONG co ranh gioi -> KHONG co khoang nghi nao. Ha xuong ~90 de cat theo cau.
    ap.add_argument("--max-chars", type=int, default=90, dest="max_chars")
    #  --gap: nhan he so bang nghi cua thu vien (goc rat ngan: doan .35s, cau .18s,
    #    trong cau .04s). 2.5 -> .88 / .45 / .10, nghe moi ra nhip ke chuyen.
    ap.add_argument("--gap", type=float, default=2.5, dest="gap")
    ap.add_argument("--denoise", default="0", help="1 = loc on mau clone (mau sach thi de 0)")
    a = ap.parse_args()

    text = sys.stdin.buffer.read().decode("utf-8").strip()
    if not text:
        sys.exit("vieneu_tts: khong co noi dung (stdin rong)")

    from vieneu import Vieneu
    import soundfile as sf
    import numpy as np

    tts = Vieneu()                      # v3turbo, CPU ONNX

    # Giong CLONE (khai trong voice_clones.json) phai enroll truoc, khong co san preset.
    ref = _clone_ref(a.voice)
    if ref:
        # denoise=False: mau clone thuong da sach (xuat tu TTS/thu phong), chay denoiser
        # chi lam meo chat giong -> clone kem giong hon.
        tts.add_voice(a.voice, ref, style=a.style, save=False,
                      denoise=str(a.denoise).strip() in ("1", "true", "yes"))
    elif a.voice not in getattr(tts, "_preset_voices", {}):
        sys.exit(f"vieneu_tts: khong co giong '{a.voice}'. Neu day la giong clone, "
                 f"bo file mau vao assets/voice_clones/ va khai trong voice_clones.json. "
                 f"Giong preset san co: {list(getattr(tts, '_preset_voices', {}))}")

    # NOI RONG KHOANG NGHI: gaps_to_silence() doc bang V3_GAP_SILENCE luc goi -> nhan
    # he so vao bang la moi khe noi giua cac chunk dai ra that su.
    if a.gap and a.gap != 1.0:
        try:
            from vieneu_utils import core_utils as _cu
            for k in list(_cu.V3_GAP_SILENCE):
                _cu.V3_GAP_SILENCE[k] = round(_cu.V3_GAP_SILENCE[k] * a.gap, 3)
        except Exception:
            pass

    # Het cau -> xuong dong: ranh gioi "para" (nghi dai nhat) thay vi "sentence".
    text = re.sub(r"(?<=[.!?…])\s+", "\n", text)

    # Tag cam xuc noi dong (checkpoint v3 Turbo ho tro): [cười] · [thở dài] · [hắng giọng]
    # -> cu de nguyen trong text, phonemizer tu doi thanh <|emotion_k|>.
    # Con day la SAC THAI CHUNG cua ca doan: chen <|emotion_k|> vao dau text.
    # Chi chen khi text chua tu khai bao token nao (viet tay trong kich ban thi uu tien).
    emo = (a.emotion or "").strip()
    if emo and "<|emotion_" not in text:
        text = f"<|emotion_{emo}|> {text}"
    wav = tts.infer(text, voice=a.voice, style=a.style,
                    temperature=a.temperature, top_p=a.top_p, top_k=a.top_k,
                    max_chars=a.max_chars)
    if isinstance(wav, tuple):          # (sr, data) hoac (data, sr) tuy phien ban
        x, y = wav
        sr, data = (x, y) if isinstance(x, int) else (y, x)
    else:
        sr, data = 48000, wav
    sf.write(a.out, np.asarray(data), sr)
    print(f"vieneu_tts OK: {a.out}")

if __name__ == "__main__":
    main()
