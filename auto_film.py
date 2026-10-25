# -*- coding: utf-8 -*-
"""auto_film.py — DUNG PHIM HANG LOAT, KHONG CAN BAM TAY.

Doc thang cac thu muc bai trong D:\\content\\...\\<so>-<ten-bai>\\ (moi bai co
content-film.md + cac anh 01.jpg..NN.jpg), roi lam DUNG NHUNG VIEC ma truoc day
phai ngoi click tren trang /film:
    1. POST /film/parse   -> tach canh
    2. gan anh cho tung canh (anh co san theo thu tu; thieu thi goi /film/ai_bg sinh bu)
    3. POST /film/make    -> dung phim
    4. poll /progress/<id> den khi xong
    5. chep mp4 + thumbnail + SEO/SRT ve ngay thu muc bai

Chay lien tuc nhieu bai: xong bai nay tu sang bai ke tiep. Bai nao co video roi
thi bo qua (tru khi --force) -> dut dien chay lai khong mat cong.

Vi du:
    python auto_film.py --bai 7,8,9
    python auto_film.py --bai 8 --voice vieneu:"Thai Son"
    python auto_film.py --tat-ca --dry-run
    python auto_film.py D:\\content\\...\\08-ba-lao-an-xin-cua-chua
"""
import os, sys, re, json, time, glob, shutil, argparse, subprocess
import urllib.request, urllib.error

_HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = "http://127.0.0.1:5001"
OUT = os.path.join(_HERE, "output")

# Thu muc goc chua 17 bai truyen xua (doi duoc bang --goc)
GOC_MAC_DINH = r"D:\content\12-truyen-xua-nhan-qua__chuyen-que-xua\12-truyen-xua-nhan-qua__chuyen-que-xua"


def ten_nhan_vat(content):
    """Ten nhan vat khai o dong '@voices Ten=giong, Ten2=giong' ([] neu khong khai)."""
    m = re.search(r"^@voices\s+(.+)$", content, re.M)
    return [p.split("=", 1)[0].strip() for p in m.group(1).split(",") if "=" in p] if m else []


# ---------------------------------------------------------------- HTTP nho gon
def _post(path, payload, timeout=1800):
    req = urllib.request.Request(SERVER + path,
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _get(path, timeout=60):
    with urllib.request.urlopen(SERVER + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def server_song(timeout=3):
    try:
        urllib.request.urlopen(SERVER + "/", timeout=timeout).read(64)
        return True
    except Exception:
        return False


def bat_server():
    """Tu bat app.py bang python trong venv neu server chua chay."""
    py = os.path.join(_HERE, "venv", "Scripts", "python.exe")
    if not os.path.exists(py):
        py = sys.executable
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    log = open(os.path.join(_HERE, "output", "auto_film_server.log"), "ab")
    subprocess.Popen([py, os.path.join(_HERE, "app.py")], cwd=_HERE, env=env,
                     stdout=log, stderr=log, creationflags=flags)
    for _ in range(60):
        if server_song():
            return True
        time.sleep(1)
    return False


# ------------------------------------------------------------- gom thu muc bai
def tim_bai(goc, chon):
    """chon = ['7','08',...] hoac None (lay het). Tra ve danh sach duong dan bai."""
    dirs = sorted(d for d in glob.glob(os.path.join(goc, "*"))
                  if os.path.isdir(d) and os.path.exists(os.path.join(d, "content-film.md")))
    if not chon:
        return dirs
    ra = []
    for c in chon:
        so = str(c).strip().lstrip("0") or "0"
        hit = [d for d in dirs if (os.path.basename(d).split("-", 1)[0].lstrip("0") or "0") == so]
        if not hit:
            print(f"  [!] khong thay bai {c} trong {goc}")
        ra += hit
    return ra


def cat_content(content, n):
    """Giu phan dau (@title/@header) + N canh dau. Server tu parse lai content nen
    muon dung thu N canh thi phai cat chinh content, khong cat moi danh sach clip."""
    lines = content.splitlines(True)
    moc = [i for i, ln in enumerate(lines) if re.match(r"^#\s", ln)]
    if len(moc) <= n:
        return content
    return "".join(lines[:moc[n]])


def anh_cua_bai(folder):
    """Anh nen theo thu tu: 01.jpg, 02.jpg... (jpg/jpeg/png deu nhan)."""
    pats = ("[0-9][0-9].jpg", "[0-9][0-9].jpeg", "[0-9][0-9].png")
    files = []
    for p in pats:
        files += glob.glob(os.path.join(folder, p))
    return sorted(files, key=lambda f: os.path.basename(f).lower())


# --------------------------------------------------------------- dung 1 bai
def sinh_anh_thieu(scenes, clips, folder, backend, style, dung_that=True):
    """Canh nao chua co anh -> goi /film/ai_bg sinh, luu ve chinh thu muc bai
    theo dung ten NN.jpg de lan sau dung lai."""
    thieu = [i for i, c in enumerate(clips) if not c]
    if not thieu:
        return clips, 0
    print(f"  · {len(thieu)} canh chua co anh -> sinh bang {backend}")
    if not dung_that:
        return clips, len(thieu)
    for n, i in enumerate(thieu, 1):
        sc = scenes[i]
        for lan in range(3):
            try:
                j = _post("/film/ai_bg", {"prompt": sc.get("prompt") or "",
                                          "label": sc.get("label") or "",
                                          "subs": sc.get("subs") or [],
                                          "style": style, "seed": i + 1,
                                          "backend": backend}, timeout=600)
                if j.get("error"):
                    raise RuntimeError(j["error"])
                dst = os.path.join(folder, f"{i+1:02d}.jpg")
                shutil.copyfile(j["path"], dst)
                clips[i] = dst
                print(f"    [{n:02d}/{len(thieu)}] canh {i+1:02d} -> {os.path.basename(dst)}"
                      + (f"  ({j.get('note')})" if j.get("note") else ""))
                break
            except Exception as e:
                if lan == 2:
                    print(f"    [!] canh {i+1} sinh anh that bai: {str(e)[:120]}")
                else:
                    time.sleep(5 * (lan + 1))
    return clips, 0


def doi_xong(job_id, nhip=5, han_gio=8):
    """Poll /progress cho den khi done/error/cancelled. In nhan moi khi doi."""
    t0, nhan = time.time(), ""
    while True:
        try:
            j = _get(f"/progress/{job_id}")
        except Exception as e:
            print(f"    [!] mat ket noi server: {str(e)[:80]} — thu lai...")
            time.sleep(nhip)
            continue
        if j.get("note"):
            n = "NOTE: " + j["note"]
            if n != nhan:
                print("    " + n); nhan = n
        lb = j.get("label") or ""
        if lb and lb != nhan:
            phut = (time.time() - t0) / 60
            print(f"    [{phut:5.1f}p] {lb}")
            nhan = lb
        st = j.get("status")
        if st in ("done", "error", "cancelled"):
            return j
        if time.time() - t0 > han_gio * 3600:
            return {"status": "error", "error": f"qua {han_gio} gio chua xong"}
        time.sleep(nhip)


def chep_ket_qua(job, folder, ten):
    """mp4 + thumb + seo/srt tu output/ -> thu muc bai."""
    ra = {}
    src = os.path.join(OUT, job["video"])
    dst = os.path.join(folder, ten + ".mp4")
    shutil.copyfile(src, dst)
    ra["video"] = dst
    if job.get("thumb"):
        t = os.path.join(OUT, job["thumb"])
        if os.path.exists(t):
            shutil.copyfile(t, os.path.join(folder, ten + ".thumb.jpg"))
            ra["thumb"] = os.path.join(folder, ten + ".thumb.jpg")
    seo = job.get("seo") or {}
    if seo:
        # SRT tach ra file rieng cho de dung; phan con lai (mo ta + chapters) vao seo.json
        con = {}
        for k, v in seo.items():
            if k.startswith("srt") and isinstance(v, str) and v.strip():
                p = os.path.join(folder, f"{ten}.{k}.srt")
                with open(p, "w", encoding="utf-8") as f:
                    f.write(v)
            else:
                con[k] = v
        with open(os.path.join(folder, ten + ".seo.json"), "w", encoding="utf-8") as f:
            json.dump(con, f, ensure_ascii=False, indent=1)
    return ra


def dung_bai(folder, opt):
    ten = os.path.basename(folder.rstrip("\\/"))
    if opt.canh:                       # ban thu -> ten khac de khong de len ban day du
        ten += f".thu{opt.canh}canh"
    dich = os.path.join(folder, ten + ".mp4")
    print(f"\n=== {ten} ===")
    if os.path.exists(dich) and not opt.force:
        print(f"  ✓ da co video ({os.path.getsize(dich)/1e6:.0f} MB) -> bo qua (--force de dung lai)")
        return {"bai": ten, "ket": "bo-qua", "video": dich}

    with open(os.path.join(folder, "content-film.md"), encoding="utf-8") as f:
        content = f.read()
    if opt.canh:                                   # chi dung N canh dau (thu nhanh)
        content = cat_content(content, opt.canh)

    j = _post("/film/parse", {"content": content})
    if j.get("error"):
        print("  [!] tach canh loi:", j["error"])
        return {"bai": ten, "ket": "loi", "loi": j["error"]}
    scenes = j["scenes"]

    imgs = anh_cua_bai(folder)
    clips = [imgs[i] if i < len(imgs) else "" for i in range(len(scenes))]
    co = sum(1 for c in clips if c)
    print(f"  · {len(scenes)} canh · {co}/{len(scenes)} canh co anh san"
          + (f" (thua {len(imgs)-len(scenes)} anh, bo qua)" if len(imgs) > len(scenes) else ""))

    clips, con_thieu = sinh_anh_thieu(scenes, clips, folder, opt.backend,
                                      opt.bg_style, dung_that=not opt.dry_run)
    if opt.dry_run:
        print(f"  (dry-run) se dung {len(scenes)} canh, can sinh them {con_thieu} anh")
        return {"bai": ten, "ket": "dry-run", "canh": len(scenes), "thieu": con_thieu}
    if any(not c for c in clips):
        con = [i + 1 for i, c in enumerate(clips) if not c]
        print(f"  [!] con {len(con)} canh khong co anh: {con[:10]}... -> bo qua bai nay")
        return {"bai": ten, "ket": "loi", "loi": f"thieu anh {len(con)} canh"}

    body = {
        "content": content,
        "clips": clips,
        "voice": opt.voice,
        "rate": opt.rate,
        "sub_pinyin": False,                 # phim tieng Viet
        "narrate": True,
        "keep_audio": False,
        # 1 GIONG (25/10, user chot): nhan vat khai @voices van duoc nhan dien (bo nhan
        # 'Ten:' truoc cau thoai) nhung doc bang chinh giong ke. --nhieu-giong de giu giong rieng.
        "char_voices": {} if opt.nhieu_giong else {n: opt.voice for n in ten_nhan_vat(content)},
        "music_file": opt.music_file,
        "music_bed": "" if opt.music_file else opt.music,
        "music_vol": opt.music_vol,
        "voice_vol": opt.voice_vol,
        "nhip_doc": opt.nhip_doc,
        "film_mode": True,
        "particles": opt.particles,
        "scene_sfx": not opt.no_sfx,
        "sfx": ["auto"] * len(scenes),
        "narr": [""] * len(scenes),
        "kenburns": True,
        "transition": "none" if opt.no_transition else "fade",
        "grade": True,
        "letterbox": opt.letterbox,
        "duck": True,
        "title_card": opt.title_card,
        "end_card": opt.end_card,
    }
    t0 = time.time()
    r = _post("/film/make", body)
    if r.get("error"):
        print("  [!]", r["error"])
        return {"bai": ten, "ket": "loi", "loi": r["error"]}
    jid = r["job_id"]
    print(f"  · job {jid} — dang dung, cu de day...")
    job = doi_xong(jid, han_gio=opt.han_gio)
    if job.get("status") != "done":
        print(f"  [!] {job.get('status')}: {str(job.get('error'))[:200]}")
        return {"bai": ten, "ket": "loi", "loi": str(job.get("error") or job.get("status"))}

    ra = chep_ket_qua(job, folder, ten)
    phut = (time.time() - t0) / 60
    print(f"  ✓ XONG sau {phut:.0f} phut · dai {job.get('dur', 0)/60:.1f} phut -> {ra['video']}")
    return {"bai": ten, "ket": "xong", "video": ra["video"],
            "phut_dung": round(phut, 1), "dai_giay": job.get("dur")}


# ------------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description="Dung phim hang loat tu thu muc bai (khong can bam tay)")
    ap.add_argument("folders", nargs="*", help="duong dan thu muc bai (thay cho --bai)")
    ap.add_argument("--goc", default=GOC_MAC_DINH, help="thu muc goc chua cac bai")
    ap.add_argument("--bai", default="", help="danh sach so bai, vd 7,8,9")
    ap.add_argument("--tat-ca", dest="tat_ca", action="store_true", help="chay het moi bai co content-film.md")
    # mac dinh = mac dinh trang /film: Vbee nhattruyenxua (user chot 2026-10-11), toc do -16% + nghi het cau 0.25s (do 2026-10-23: 207 a/p),
    # giong 160%, nhac Erev Shel Shoshanim 0.4
    ap.add_argument("--voice", default="vbee:n_ninhbinh_male_nhattruyenxua_zero_shot_story_vc",
                    help="giong doc (mac dinh nhu tren trang film)")
    ap.add_argument("--rate", default="-16%", help="toc do doc, vd -8%%")
    ap.add_argument("--nhieu-giong", dest="nhieu_giong", action="store_true",
                    help="giu giong rieng cho nhan vat theo @voices (mac dinh: 1 giong ke doc het)")
    ap.add_argument("--voice-vol", dest="voice_vol", type=float, default=1.6)
    ap.add_argument("--nhip-doc", dest="nhip_doc", default="",
                    help="lien (ca canh 1 hoi doc, mac dinh voi Vbee) | vai_tro (cat tung cau)")
    ap.add_argument("--music", default="warm", help="warm | hope | sad | none (khi khong co --music-file)")
    ap.add_argument("--music-file", dest="music_file",
                    default=os.path.join(_HERE, "assets", "film_music", "erev-shel-shoshanim.mp3"))
    ap.add_argument("--music-vol", dest="music_vol", type=float, default=0.4)
    ap.add_argument("--particles", default="auto")
    ap.add_argument("--backend", default="pollinations", help="engine sinh anh khi thieu: pollinations|openai|together|gemini")
    ap.add_argument("--bg-style", dest="bg_style", default="story", help="style anh AI (story = theo @bg co nhan vat)")
    ap.add_argument("--canh", type=int, default=0, help="chi dung N canh dau (thu nhanh)")
    ap.add_argument("--title-card", dest="title_card", action="store_true", help="them bia dau")
    ap.add_argument("--end-card", dest="end_card", action="store_true", help="them card HET")
    ap.add_argument("--letterbox", action="store_true")
    ap.add_argument("--no-sfx", dest="no_sfx", action="store_true")
    ap.add_argument("--no-transition", dest="no_transition", action="store_true")
    ap.add_argument("--force", action="store_true", help="dung lai ca bai da co video")
    ap.add_argument("--dry-run", dest="dry_run", action="store_true", help="chi kiem tra, khong dung")
    ap.add_argument("--han-gio", dest="han_gio", type=float, default=8, help="het gio cho 1 phim")
    opt = ap.parse_args()

    if opt.folders:
        bais = [os.path.abspath(f) for f in opt.folders]
    else:
        chon = [c for c in re.split(r"[,\s]+", opt.bai) if c] if opt.bai else None
        if not chon and not opt.tat_ca:
            ap.error("can --bai 7,8,9 hoac --tat-ca hoac duong dan thu muc")
        bais = tim_bai(opt.goc, chon)
    if not bais:
        print("Khong co bai nao de dung."); return 1

    if not server_song():
        print("Server chua chay -> dang bat app.py ...")
        if not bat_server():
            print("[!] Khong bat duoc server o", SERVER); return 1
        print("Server san sang:", SERVER)

    print(f"Hang doi {len(bais)} bai: " + ", ".join(os.path.basename(b) for b in bais))
    t0, ket = time.time(), []
    for b in bais:
        try:
            ket.append(dung_bai(b, opt))
        except KeyboardInterrupt:
            print("\n[dung tay] thoat."); break
        except Exception as e:
            import traceback; traceback.print_exc()
            ket.append({"bai": os.path.basename(b), "ket": "loi", "loi": str(e)[:200]})

    print("\n" + "=" * 60)
    print(f"TONG KET sau {(time.time()-t0)/60:.0f} phut")
    for k in ket:
        print(f"  {k['ket']:<8} {k['bai']}" + (f"  -> {k.get('video','')}" if k.get("video") else "")
              + (f"  ({k.get('loi')})" if k.get("loi") else ""))
    bao = os.path.join(OUT, "auto_film_ket_qua.json")
    with open(bao, "w", encoding="utf-8") as f:
        json.dump(ket, f, ensure_ascii=False, indent=1)
    print("Bao cao:", bao)
    return 0


if __name__ == "__main__":
    sys.exit(main())
