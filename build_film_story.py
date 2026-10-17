# -*- coding: utf-8 -*-
"""build_film_story.py — Dung PHIM KE CHUYEN tu file phan canh JSON.

Luong: doc data/film_*.json -> sinh anh nen tung canh (Pollinations) -> film.make_film().
Moi canh 3 cau -> film.py tu cat 3 CO CANH (toan/trung/can) tu 1 anh => ~10s/canh.

Dung:
    python build_film_story.py data/film_dem_bao_tren_deo.json
    python build_film_story.py data/film_dem_bao_tren_deo.json --scenes 6   # thu 6 canh dau
"""
import os, sys, json, time, argparse, hashlib, re

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import film
import generate


# ---------- YC3: MULTI-SHOT — nhieu anh cho 1 canh (nhu video mau Chuyen Que Xua) ----------
# Tu khoa nhan dien ve (comma segment) mo ta NGUOI trong prompt — de loc ra khoi
# wide establishing shot "no people" (chi giu boi canh).
_PERSON_WORDS = re.compile(
    r"\b(man|woman|men|women|person|people|boy|girl|child|children|kid|baby|elder|"
    r"grandmother|grandfather|mother|father|wife|husband|daughter|son|merchant|"
    r"farmer|seller|doctor|monk|villager|his|her|he|she|face|hair|eyes|mustache|"
    r"shirt|blouse|coat|dress|hat|hand|hands|arm|holding|standing|sitting|kneeling|"
    r"walking|running|crying|smiling|carrying)\b", re.I)


def _auto_shot_count(sc):
    """So ANH cho 1 canh theo do dai UOC TINH: <15s -> 1, 15-35s -> 2, >35s -> 3.
    Uoc tinh = scene['dur'] neu co, khong thi so cau x ~4s (chua co TTS luc nay)."""
    est = float(sc.get("dur") or (len(sc.get("subs") or []) * 4.0))
    if est < 15:
        return 1
    if est <= 35:
        return 2
    return 3


def derive_shot_prompts(prompt, n_extra):
    """Sinh 0-3 prompt PHU rule-based tu prompt chu dao (KHONG goi AI):
      shot 2 = can canh chi tiet; shot 3 = quang canh rong khong nguoi; shot 4 = chi tiet khac.
    QUAN TRONG: shot can canh GIU NGUYEN VAN toan bo prompt goc — character sheet nam
    GIUA prompt (vd 'Nhan, a thin kind Vietnamese man...'), cat cum se mat mo ta nhan vat
    -> anh ve lech nhan vat. Wide shot khong nguoi thi loc bo cac ve ta nguoi."""
    prompt = (prompt or "").strip().rstrip(",")
    outs = []
    if n_extra >= 1:                             # CAN CANH: giu nguyen prompt (character sheet)
        outs.append("close-up detail shot, shallow depth of field, " + prompt)
    if n_extra >= 2:                             # QUANG CANH: chi giu cac ve boi canh
        segs = [s.strip() for s in prompt.split(",") if s.strip()]
        scenery = [s for s in segs if not _PERSON_WORDS.search(s)]
        base = ", ".join(scenery) if scenery else "the same landscape and time of day"
        outs.append("wide establishing shot of the scene, no people, no characters, " + base)
    if n_extra >= 3:                             # CHI TIET PHU: goc khac, van giu nhan vat
        outs.append("extreme close-up of a small meaningful object in the scene, " + prompt)
    return outs[:3]


def gen_scene_clips(sc, n, style, json_path, shots_per_scene="auto", auto_shots=True):
    """Sinh danh sach anh cho 1 canh: [chu dao, phu 1, ...]. 'shots' trong JSON uu tien;
    khong co -> auto-derive theo do dai (auto_shots). Cache theo PATH doc duoc:
    aibg/{ten_phim}_scene{id}_s{k}_{hash8}.jpg (hash prompt -> doi prompt khong dinh anh cu,
    them ten phim de 2 phim khac nhau khong dam file nhau)."""
    prompt = sc["prompt"].strip().rstrip(",")
    if style:
        prompt = f"{prompt}, {style}"
    sid = sc.get("id", n)
    img = film.ai_scene_bg(prompt, seed=sid)     # anh chu dao: giu cache hash nhu cu
    clips = [img]

    shot_prompts = [str(p).strip() for p in (sc.get("shots") or []) if str(p).strip()][:3]
    if not shot_prompts and auto_shots and shots_per_scene != 1:
        if shots_per_scene in (None, "", "auto"):
            n_imgs = _auto_shot_count(sc)
        else:
            n_imgs = max(1, min(4, int(shots_per_scene)))
        shot_prompts = derive_shot_prompts(sc["prompt"], n_imgs - 1)

    slug = os.path.splitext(os.path.basename(json_path))[0]
    for k, sp2 in enumerate(shot_prompts, 1):
        p2 = sp2.strip().rstrip(",")
        if style:
            p2 = f"{p2}, {style}"
        hh = hashlib.md5((p2 + "|" + str(sid)).encode("utf-8")).hexdigest()[:8]
        pth = os.path.join(film._AIBG, f"{slug}_scene{sid}_s{k}_{hh}.jpg")
        clips.append(film.ai_scene_bg(p2, path=pth, seed=sid))
    return clips


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


def build(json_path, limit=None, out_path=None, music="warm", gap=1.0,
          shots_per_scene="auto", auto_shots=True):
    with open(json_path, encoding="utf-8") as f:
        doc = json.load(f)

    style = doc.get("style", "")
    scenes_in = doc["scenes"]
    if limit:
        scenes_in = scenes_in[:limit]

    print(f"Phim  : {doc['title']}")
    print(f"Canh  : {len(scenes_in)}" + (f" (gioi han tu {len(doc['scenes'])})" if limit else ""))
    print("-" * 60)

    # 1) sinh anh nen tung canh (YC3: 1 canh co the NHIEU anh — chu dao + can canh + quang canh)
    scenes = []
    for n, sc in enumerate(scenes_in, 1):
        t0 = time.time()
        clips = gen_scene_clips(sc, n, style, json_path,
                                shots_per_scene=shots_per_scene, auto_shots=auto_shots)
        img = clips[0]
        _nsh = f" +{len(clips)-1} shot phu" if len(clips) > 1 else ""
        print(f"[{n:02d}/{len(scenes_in)}] {sc.get('beat',''):<12} {time.time()-t0:5.1f}s  "
              f"{os.path.basename(img)}{_nsh}")
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
            # YC3: >=2 anh -> film.make_scene doi anh theo group (multi-shot per beat)
            **({"clips": clips} if len(clips) >= 2 else {}),
            "narrate": True,
            "subs": subs,
            # beat -> film.plan_transitions chon chuyen canh dien anh (cut/blend/dip theo vai tro);
            # "trans" trong JSON ep tay kieu chuyen TRUOC canh do (cut|black|blend)
            "beat": sc.get("beat", ""),
            "trans": sc.get("trans", ""),
            # "focus": [x,y] 0-1 ep tay tam nhan vat (a18) — khong co thi tu detect
            "focus": sc.get("focus"),
        })

    # 1b) nap san cache TTS (chong throttle edge-tts)
    # Giong LOCAL (vieneu:/vbee:) khong bi throttle mang; make_film() lai GOM cau lien tiep
    # thanh 1 run TTS (cache key khac cau le) -> prewarm tung cau chi ton cong vo ich. Bo qua.
    _v = doc.get("voice", "vi-VN-NamMinhNeural")
    _local_voice = isinstance(_v, str) and _v.startswith(("vieneu:", "vbee:"))
    _has_edge_sub = any((s.get("voice") or "").startswith("vi-") or (s.get("voice") or "").startswith("zh-")
                        for sc in scenes_in for s in sc["subs"])
    if not _local_voice or _has_edge_sub:
        prewarm_tts(scenes_in, _v, doc.get("rate", "-8%"), gap=gap)
    else:
        print(f"Bo qua prewarm TTS (giong local {_v}, khong can chong throttle)")

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
        # YC1: camera day vao nhan vat + dip-to-black chuan mau (style Chuyen Que Xua)
        "focus_subject": True,        # detect nhan vat -> zoom/pan huong ve mat
        "zoom_amt": None,             # None = auto (10%/canh, cap 12% vi anh nguon 720p)
        "dip_dur": 0.5,               # tong dip ~0.5s (ra 0.25 + vao 0.25, mau ~0.45s)
        "always_fade": True,          # moi CUT -> dip-to-black (video mau 100% dip)
        # YC2: lop hat bay (dom dom / bui nang) — auto chon preset theo mau anh
        "particles": "auto",          # none|firefly|dust|auto (scene["particles"] ghi de)
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
    ap.add_argument("--shots", default="auto",
                    help="so anh moi canh: auto (theo do dai) | 1..4")
    ap.add_argument("--no-auto-shots", action="store_true",
                    help="tat tu sinh anh phu (JSON khong co 'shots' -> 1 anh nhu cu)")
    a = ap.parse_args()
    build(a.json, limit=a.scenes, out_path=a.out,
          music=(None if a.music == "none" else a.music), gap=a.gap,
          shots_per_scene=(a.shots if a.shots == "auto" else int(a.shots)),
          auto_shots=(not a.no_auto_shots))
