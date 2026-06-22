# -*- coding: utf-8 -*-
"""ChatTTS chay local - giong tieng Trung tu nhien, mien phi, khong can key.
   Load model 1 lan, dung 1 speaker co dinh cho ca video (giong nhat quan).
   API ChatTTS co the doi giua cac phien ban -> code phong thu, test sau khi cai.
"""
import os, wave, subprocess
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
SPK_FILE = os.path.join(ROOT, "assets", "chattts_speaker.txt")

_chat = None
_spk = None

# 3 muc ngu dieu (temperature cao = nhieu cam xuc; oral/break = tu nhien/ngat nghi)
STYLES = {
    "clear": dict(temperature=0.2, oral=1, brk=4),   # ro rang, on dinh
    "warm":  dict(temperature=0.3, oral=2, brk=5),   # truyen cam (mac dinh)
    "story": dict(temperature=0.45, oral=3, brk=6),  # ke chuyen, nhieu cam xuc
}

def _load():
    """Load model + speaker (lazy, 1 lan)."""
    global _chat, _spk
    if _chat is not None:
        return
    import ChatTTS
    c = ChatTTS.Chat()
    # tren Windows trinh tai mac dinh (rvcmd) bi crash -> tai qua huggingface_hub
    ok = False
    try:
        ok = c.load(source="huggingface", compile=False)
    except Exception:
        ok = False
    if not ok:
        from huggingface_hub import snapshot_download
        d = snapshot_download("2Noise/ChatTTS")
        ok = c.load(source="custom", custom_path=d, compile=False)
    if not ok:
        raise RuntimeError("ChatTTS load that bai")
    _chat = c
    # speaker co dinh: luu lai de cac lan/cau deu cung 1 giong
    if os.path.exists(SPK_FILE):
        _spk = open(SPK_FILE, encoding="utf-8").read().strip()
    else:
        _spk = c.sample_random_speaker()
        try:
            if isinstance(_spk, str):
                open(SPK_FILE, "w", encoding="utf-8").write(_spk)
        except Exception:
            pass

_PUNC = {"，": ",", "。": ".", "？": "?", "！": "!", "：": ":", "；": ";",
         "、": ",", "（": "(", "）": ")", "「": "", "」": "", "“": "", "”": "",
         "‘": "", "’": "", "—": ",", "…": "..."}
def _clean_text(t):
    """Chuyen dau cau full-width -> ASCII de ChatTTS giu ngu dieu hoi/cam than."""
    for a, b in _PUNC.items():
        t = t.replace(a, b)
    return t.strip()

def _write_wav(path, wav, sr=24000):
    wav = np.clip(np.asarray(wav).reshape(-1).astype("float32"), -1, 1)
    pcm = (wav * 32767).astype("<i2").tobytes()
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(pcm)

def synth_chattts(text, out_mp3, speed=3, temperature=0.3, oral=2, brk=5):
    """Sinh giong 1 cau -> ghi out_mp3.
       - speaker co dinh + seed: giong on dinh, nhat quan
       - temperature vua: co ngu dieu/cam xuc ma khong loan
       - [oral_N]: tu nhien nhu ke chuyen; [break_N]: ngat nghi theo nghia cau
    """
    _load()
    import ChatTTS, torch
    text = _clean_text(text)
    try:
        torch.manual_seed(2)                 # tai lap -> on dinh, cache nhat quan
        infer_p = ChatTTS.Chat.InferCodeParams(
            spk_emb=_spk, temperature=temperature, top_P=0.7, top_K=20,
            prompt=f"[speed_{speed}]")
        refine_p = ChatTTS.Chat.RefineTextParams(
            prompt=f"[oral_{oral}][laugh_0][break_{brk}]")
        wavs = _chat.infer([text], skip_refine_text=False,
                           params_infer_code=infer_p, params_refine_text=refine_p)
    except Exception:
        wavs = _chat.infer([text])          # fallback API don gian
    tmp = out_mp3 + ".wav"
    _write_wav(tmp, wavs[0])
    subprocess.run(["ffmpeg", "-y", "-i", tmp, out_mp3],
                   check=True, capture_output=True)
    try: os.remove(tmp)
    except OSError: pass

if __name__ == "__main__":
    synth_chattts("你好，今天天气很好。", os.path.join(ROOT, "output", "_chattts_test.mp3"))
    print("done")
