# -*- coding: utf-8 -*-
"""build_film_story.py — Dung PHIM KE CHUYEN tu file phan canh JSON.

Luong: doc data/film_*.json -> sinh anh nen tung canh (Pollinations) -> film.make_film().
Moi canh 3 cau -> film.py tu cat 3 CO CANH (toan/trung/can) tu 1 anh => ~10s/canh.

Dung:
    python build_film_story.py data/film_dem_bao_tren_deo.json
    python build_film_story.py data/film_dem_bao_tren_deo.json --scenes 6   # thu 6 canh dau
"""
import os, sys, json, time, argparse

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import film
import generate


def prewarm_tts(scenes_in, voice, rate, gap=1.0):
    """Nap san cache TTS, GIAN NHIP giua cac lan goi.

    edge-tts bi Microsoft chan khi goi lien tiep; _edge_retry trong generate.py chi nghi
    toi da ~3.6s nen van vo. Goi truoc voi khoang nghi co dinh -> make_film() chi an cache,
    khong con cham mang => khong bi throttle giua chung khi dang ghep phim.
    """
    lines = []
    for sc in scenes_in:
        for s in sc["subs"]:
            t = (s.get("tts") or s.get("hz") or s.get("vi") or "").strip()
            if t:
                lines.append((t, s.get("voice") or voice, s.get("emo")))

    print(f"Nap cache TTS: {len(lines)} cau (gian {gap}s/cau, ~{len(lines)*gap/60:.1f} phut)")
    done = fail = 0
    for n, (text, vc, emo) in enumerate(lines, 1):
        tmp = os.path.join(film.FILM, "_warm.mp3")
        for attempt in range(3):
            try:
                generate.synth(text, film._clean_voice(vc), tmp, rate=rate, emo=emo)
                done += 1
                break
            except Exception as e:
                if attempt == 2:
                    fail += 1
                    print(f"  [!] cau {n} that bai: {str(e)[:80]}")
                else:
                    time.sleep(5 * (attempt + 1))     # nghi dai han _edge_retry
        if n % 25 == 0:
            print(f"  ...{n}/{len(lines)}")
        time.sleep(gap)
    print(f"Cache TTS: {done} ok, {fail} loi")
    return fail


def build(json_path, limit=None, out_path=None, music="warm", gap=1.0):
    with open(json_path, encoding="utf-8") as f:
        doc = json.load(f)

    style = doc.get("style", "")
    scenes_in = doc["scenes"]
    if limit:
        scenes_in = scenes_in[:limit]

    print(f"Phim  : {doc['title']}")
    print(f"Canh  : {len(scenes_in)}" + (f" (gioi han tu {len(doc['scenes'])})" if limit else ""))
    print("-" * 60)

    # 1) sinh anh nen tung canh
    scenes = []
    for n, sc in enumerate(scenes_in, 1):
        prompt = sc["prompt"].strip().rstrip(",")
        if style:
            prompt = f"{prompt}, {style}"
        t0 = time.time()
        img = film.ai_scene_bg(prompt, seed=sc.get("id", n))
        print(f"[{n:02d}/{len(scenes_in)}] {sc.get('beat',''):<12} {time.time()-t0:5.1f}s  {os.path.basename(img)}")
        # PHIM TIENG VIET: bat buoc dua chu vao truong 'vi', KHONG phai 'hz'.
        # render_subtitle() ve 'hz' theo duong Han tu (font zh = SimSun) -> mat sach
        # cac ky tu rieng cua tieng Viet (O do o e a...). Truong 'vi' dung font
        # Arial Unicode -> hien du dau. 'tts' giu nguyen chu de doc.
        subs = []
        for s in sc["subs"]:
            txt = (s.get("hz") or s.get("vi") or "").strip()
            s2 = {k: v for k, v in s.items() if k not in ("hz", "vi", "tts")}
            s2["vi"] = txt
            s2["tts"] = s.get("tts") or txt
            subs.append(s2)

        scenes.append({
            "clip": img,
            "narrate": True,
            "subs": subs,
        })

    # 1b) nap san cache TTS (chong throttle edge-tts)
    prewarm_tts(scenes_in, doc.get("voice", "vi-VN-NamMinhNeural"), doc.get("rate", "-8%"), gap=gap)

    # 2) nhac nen sinh bang DSP (khong dinh ban quyen)
    music_file = film.make_music_bed(music) if music else None

    opts = {
        "voice": doc.get("voice", "vi-VN-NamMinhNeural"),
        "rate": doc.get("rate", "-8%"),
        "sub_pinyin": False,          # phim tieng Viet -> khong hien pinyin
        "film_mode": True,            # bat fake coverage (3 co canh / anh)
        "kenburns": True,
        "transition": "fade",
        "grade": True,
        "letterbox": True,
        "music_file": music_file,
        "music_vol": 0.16,
        "title_card": True,
        "end_card": True,
        "film_title": doc["title"],
        "film_header": doc.get("header", ""),
    }

    out = out_path or os.path.join(_HERE, "output", "film_" + os.path.splitext(os.path.basename(json_path))[0] + ".mp4")
    os.makedirs(os.path.dirname(out), exist_ok=True)

    print("-" * 60)
    print("Dang ghep phim...")
    t0 = time.time()
    res = film.make_film(scenes, opts, out)
    print(f"XONG sau {time.time()-t0:.0f}s -> {res}")
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("json", help="file phan canh, vd data/film_dem_bao_tren_deo.json")
    ap.add_argument("--scenes", type=int, default=None, help="chi dung N canh dau (de thu nhanh)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--music", default="warm", help="warm | none")
    ap.add_argument("--gap", type=float, default=1.0, help="giay nghi giua cac lan goi edge-tts")
    a = ap.parse_args()
    build(a.json, limit=a.scenes, out_path=a.out,
          music=(None if a.music == "none" else a.music), gap=a.gap)
