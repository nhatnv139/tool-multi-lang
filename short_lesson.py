# -*- coding: utf-8 -*-
"""Bo Short day hoc cho MOT video dai — thiet ke chot 2026-09-13:

  1 Short TU MOI   : 6 tu vung cua tap, moi tu mot khung (Han to + pinyin + nghia), doc lap lai.
  1 Short NGU PHAP : 2-3 mau cau, moi mau = khung vi du gon + khung CAU THAT trong bai (highlight).
  2-3 Short DOAN HAY: doan van dat nhat cua bai (uu tien dinh -30%/-20% trong ban SSML + diep khuc).

Tu vung + mau cau nguoi viet da soan trong `mo-ta.md` (muc "TU VUNG TRONG TAP NAY",
"Mau cau dang nho") — khong tu bia. Thu muc bai tu tim theo ten video trong ~/content.
"""
import glob, io, os, re

HAN = r"[一-鿿]"
GOC_NOI_DUNG = os.path.expanduser("~/content")


# ================================================================ mo-ta.md
def doc_bai_hoc(mo_ta):
    """mo-ta.md -> {'tu': [{han,pinyin,nghia}], 'mau': [{mau,nghia,vd_han,vd_viet}], 'cau': {...}}"""
    s = mo_ta or ""
    tu, mau = [], []
    for m in re.finditer(r"^-\s*(%s+)\s*\(([^)]+)\)\s*[—–-]\s*(.+?)\s*$" % HAN, s, re.M):
        tu.append({"han": m.group(1), "pinyin": m.group(2).strip(), "nghia": m.group(3).strip()})
    for m in re.finditer(r"^-\s*([^\n]*…[^\n]*?)\s*[—–]\s*(.+?)\s*$", s, re.M):
        mauc, giai = m.group(1).strip(), m.group(2).strip()
        vd_h = vd_v = ""
        g = re.search(r"[（(]\s*(%s[^—–)]*)\s*[—–]\s*([^)）]+)[)）]" % HAN, giai)
        if g:
            vd_h, vd_v = g.group(1).strip(), g.group(2).strip()
            giai = giai[:g.start()].strip().rstrip(".")
        mau.append({"mau": mauc, "nghia": giai, "vd_han": vd_h, "vd_viet": vd_v})
    cau = None
    k = s.find("Câu để mang về")
    if k >= 0:
        dong = [x.strip() for x in s[k:].split("\n")[1:] if x.strip()][:2]
        if dong and re.search(HAN, dong[0]):
            cau = {"han": dong[0], "viet": dong[1] if len(dong) > 1 else ""}
    return {"tu": tu, "mau": mau, "cau": cau}


# ================================================================ content(-ssml).md
def _boc(hz):
    """Boc SSML + marker nhip (* // ~ [ ]) khoi ve Han -> chu sach de hien thi/doc."""
    hz = re.sub(r"<[^>]+>", "", hz)
    hz = re.sub(r"/{2,4}\s*$", "", hz.strip())
    return hz.strip("*[] ").strip()

def _cac_dong(content):
    """[(hz_sach, viet, muc_manh)] — muc_manh: 30/20 theo prosody, 5 neu la diep khuc *…*."""
    ra = []
    for l in (content or "").split("\n"):
        raw = l.rstrip()
        if " | " not in raw or raw.lstrip().startswith("@") or raw.startswith("#"):
            ra.append(None); continue                      # giu vi tri de tach kho theo dong trong
        h, v = raw.split(" | ", 1)
        manh = 30 if 'rate="-30%"' in h else 20 if 'rate="-20%"' in h else 0
        hs = _boc(h)
        if h.strip().startswith("*") or "*" in h[:60]:
            manh = max(manh, 5)
        if re.search(HAN, hs):
            ra.append((hs, v.strip(), manh))
        else:
            ra.append(None)
    return ra

def _n_han(s):
    return len(re.findall(HAN, s or ""))


# ================================================================ vi du cho tu / mau
def _khop_theo_thu_tu(h, manh):
    """Cac manh cua mau cau phai xuat hien THEO THU TU, khong chong lan."""
    pos = 0
    for f in manh:
        f = f.strip("，,。 ")
        if not f:
            continue
        i = h.find(f, pos)
        if i < 0:
            return None
        pos = i + len(f)
    return True

def tim_vi_du(khoa, dong, bo_qua=(), dai_toi_da=16):
    """Cau chua `khoa`; uu tien cau TRON VEN (ket 。！？) ngan nhat. Tra (hz_highlight, viet)."""
    if "…" in khoa or "..." in khoa:
        manh = [x for x in re.split(r"…+|\.{3}", khoa) if re.search(HAN, x or "")]
        hop = lambda h: _khop_theo_thu_tu(h, manh)
    else:
        manh = [khoa]
        hop = lambda h: khoa in h
    ung = [(h, v) for d in dong if d for h, v, _ in [d]
           if hop(h) and h not in bo_qua]
    if not ung:
        return None
    def diem(hv):
        h = hv[0]
        return (0 if h.rstrip().endswith(("。", "！", "？")) else 1,
                0 if _n_han(h) <= dai_toi_da else 1, _n_han(h))
    h, v = min(ung, key=diem)
    hl = h
    for f in manh:                                          # danh dau [tu] de highlight
        f = f.strip("，,。 ")
        if f and ("[" + f + "]") not in hl:
            hl = hl.replace(f, "[" + f + "]", 1)
    return hl, v, h


# ================================================================ doan hay
def doan_hay(content, n=3):
    """3 HAT GIONG doan hay: dong dinh cam xuc cua 3 kho khac nhau.
    Cua so THAT do `lam_short_clip` noi rong theo MOC THOI GIAN cho du 20-30s —
    vi cat theo so chu ra doan 6-18s, nghe khong hieu gi. (sua 2026-09-13)"""
    dong = _cac_dong(content)
    kho, hien = [], []
    for d in dong:
        if d is None:
            if hien: kho.append(hien); hien = []
        else:
            hien.append(d)
    if hien: kho.append(hien)

    ung = []
    for k in kho:
        if len(k) < 2:                       # kho mot dong khong lam duoc doan
            continue
        tam = max(range(len(k)), key=lambda i: k[i][2])
        m = k[tam][2]
        if m == 0 and len(kho) > 6:
            continue
        ung.append((m, -len(k), k[tam]))
    ung.sort(key=lambda x: (-x[0], x[1]))
    ra, da = [], set()
    for m, _, (h, v, _) in ung:
        if h in da:
            continue
        da.add(h)
        ra.append({"lines": [(h, v, "")], "nhan": h})
        if len(ra) >= n:
            break
    return ra


# ================================================================ bo short cua mot bai
def lam_bo_short(mo_ta, content, ten_bai=""):
    """-> list spec: {'ma','loai','nhan','lines','reads','tieu_de','mo_ta'}"""
    bh = doc_bai_hoc(mo_ta)
    dong = _cac_dong(content)
    duoi = (" | " + ten_bai) if ten_bai else ""
    ra = []
    def _them(x):
        x["ten_bai"] = ten_bai; ra.append(x); return x

    if bh["tu"]:
        # note de RONG: renderer tu ve pinyin to thanh dieu, ghi them la trung 2 lan
        lines = [(t["han"], t["nghia"], "") for t in bh["tu"]]
        _them({"ma": "tumoi", "loai": "tu", "reads": 2, "hook": "6 TỪ TRONG TẬP NÀY",
                   "nhan": "Từ mới: " + " · ".join(t["han"] for t in bh["tu"]),
                   "lines": lines,
                   "tieu_de": "%d từ tiếng Trung trong 1 phút: %s%s #Shorts" % (
                       len(lines), " ".join(t["han"] for t in bh["tu"][:4]), duoi),
                   "mo_ta": "Từ vựng trong tập:\n" + "\n".join(
                       "%s (%s) — %s" % (t["han"], t["pinyin"], t["nghia"]) for t in bh["tu"])})

    if bh["mau"]:
        lines, mota, da = [], [], set()
        for m in bh["mau"]:
            if m["vd_han"]:
                lines.append((m["vd_han"], m["vd_viet"] or m["nghia"], m["mau"]))
            vd = tim_vi_du(m["mau"], dong, bo_qua=da)
            if vd:
                da.add(vd[2]); lines.append((vd[0], vd[1], m["mau"] if not m["vd_han"] else "ví dụ trong bài"))
            mota.append("%s — %s" % (m["mau"], m["nghia"]))
        if lines:
            _them({"ma": "nguphap", "loai": "mau", "reads": 2, "hook": "MẪU CÂU NÓI NHƯ NGƯỜI BẢN XỨ",
                       "nhan": "Ngữ pháp: " + " · ".join(m["mau"] for m in bh["mau"]),
                       "lines": lines,
                       "tieu_de": "Mẫu câu %s — nói như người bản xứ%s #Shorts" % (bh["mau"][0]["mau"], duoi),
                       "mo_ta": "Mẫu câu trong tập:\n" + "\n".join(mota)})

    for i, d in enumerate(doan_hay(content, n=3), 1):
        _them({"ma": "doan%d" % i, "loai": "doan", "reads": 1, "hook": "ĐOẠN NÀY ĐÁNG NGHE HAI LẦN",
                   "nhan": "Đoạn hay: " + d["nhan"][:24],
                   "lines": d["lines"],
                   "tieu_de": "%s — %s%s #Shorts" % (d["lines"][0][0][:18], d["lines"][0][1][:36], duoi),
                   "mo_ta": "\n".join("%s — %s" % (h, v) for h, v, _ in d["lines"])})
    return ra


# ================================================================ tim thu muc bai theo ten
def tim_thu_muc(ten):
    """Ten bai (tu @title / ten video) -> thu muc trong ~/content, so khop @title."""
    ten = (ten or "").replace("_", " ").strip().lower()
    if not ten:
        return None
    ung = []                                   # (do_dai_title, thu_muc)
    for f in glob.glob(os.path.join(GOC_NOI_DUNG, "*", "*", "content.md")):
        try:
            dau = io.open(f, encoding="utf-8").read(400)
        except Exception:
            continue
        m = re.search(r"^@title (.+)$", dau, re.M)
        if not m:
            continue
        t = m.group(1).strip().lower()
        if t == ten:
            return os.path.dirname(f)          # khop chinh xac -> lay ngay
        # ten video co the co duoi (timestamp/SEO): title phai la DAU chuoi va du dai
        if len(t) >= 10 and ten.startswith(t):
            ung.append((len(t), os.path.dirname(f)))
    return max(ung)[1] if ung else None

def bo_short_tu_thu_muc(thu_muc):
    doc = lambda n: io.open(os.path.join(thu_muc, n), encoding="utf-8").read() \
        if os.path.exists(os.path.join(thu_muc, n)) else ""
    ct = doc("content-ssml.md") or doc("content.md")
    ten = ""
    m = re.search(r"^@title (.+)$", ct, re.M)
    if m: ten = m.group(1).strip()
    return lam_bo_short(doc("mo-ta.md"), ct, ten)


# ============================================================ DUNG SHORT KIEU CLIP
# Nguoi dung chot 2026-09-13: Short phai la CLIP THAT cat tu video dai (chu Han/pinyin/nghia
# chay theo loi doc, tieng goc cua bai) — KHONG phai the tinh doc lai bang TTS.
# Lop day hoc (tu moi / mau cau) ve DE LEN clip do.
import json, subprocess, tempfile

SW, SH = 1080, 1920


def _moc_theo_cau(video, lines):
    """Ghep tung dong bai hoc vao mot doan THAT trong video -> [(start, end, dong)]."""
    mp = video + ".meta.json"
    if not os.path.exists(mp):
        raise RuntimeError("thiếu %s — cần meta để cắt đúng câu" % os.path.basename(mp))
    segs = [s for s in json.load(io.open(mp, encoding="utf-8"))["segments"] if s.get("hanzi")]
    chinh = {s["hanzi"].strip(): s for s in segs}
    ra = []
    for h, v, n in lines:
        h2 = re.sub(r"[\[\]]", "", h).strip()
        s = chinh.get(h2) or next((x for x in segs if h2 and h2 in x["hanzi"]), None)
        if s:
            ra.append((float(s["start"]), float(s["end"]), (h, v, n)))
    return ra


def _lop_day(hook, han, py, nghia, cta, path, stt="", ten_bai=""):
    """PNG 1080x1920 trong suot. Khung video that chi chiem dai giua (y 656-1264),
    nen chia ro: DINH = ten bai · tren = hook · DUOI = the day hoc · day = CTA.
    (2026-09-13: truoc do don het len tren, nua duoi bo trong ca nghin pixel.)"""
    from PIL import Image, ImageDraw
    import style_pastel as sp
    im = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    TREN_HET, DUOI_DAU = 646, 1274        # mep khung video that

    y = 46
    if ten_bai:                            # DINH: ten bai — nho, chim, khong gianh cho hook
        tf = sp.font("sansb", 40)
        while sp.text_w(d, ten_bai, tf) > SW - 200 and tf.size > 26:
            tf = sp.font("sansb", tf.size - 2)
        tw = sp.text_w(d, ten_bai, tf)
        d.rounded_rectangle([(SW - tw) // 2 - 30, y, (SW + tw) // 2 + 30, y + tf.size + 30],
                            radius=20, fill=(12, 14, 20, 168))
        d.text(((SW - tw) // 2, y + 15), ten_bai, font=tf, fill=(236, 226, 206))
        y += tf.size + 46

    if hook:
        hf = sp.font("sansb", 56)
        while sp.text_w(d, hook, hf) > SW - 150 and hf.size > 34:
            hf = sp.font("sansb", hf.size - 3)
        dong = sp.wrap_text(d, hook, hf, SW - 150)[:3]
        cao = len(dong) * (hf.size + 12) + 52
        if y + cao > TREN_HET - 12:        # khong bao gio de len khung video
            cao = max(80, TREN_HET - 12 - y)
        d.rounded_rectangle([34, y, SW - 34, y + cao], radius=26, fill=(14, 16, 24, 186))
        yy = y + 26
        for ln in dong:
            d.text(((SW - sp.text_w(d, ln, hf)) // 2, yy), ln, font=hf, fill=(255, 214, 120))
            yy += hf.size + 12

    if han:                                # DUOI: the day hoc — chiem vung trong duoi khung
        zf = sp.font("zh", 150 if len(han) <= 3 else (108 if len(han) <= 6 else 76))
        pf = sp.font("sans", 52)
        nf = sp.font("viet", 58)
        while nghia and len(sp.wrap_text(d, nghia, nf, SW - 170)) > 2 and nf.size > 40:
            nf = sp.font("viet", nf.size - 3)
        nd = sp.wrap_text(d, nghia or "", nf, SW - 170)[:3]
        cao = ((pf.size + 10) if py else 0) + int(zf.size * 1.34) + len(nd) * (nf.size + 10) + 70
        CTA_DAU = SH - 268                 # mep tren nut CTA
        cho = CTA_DAU - 24 - (DUOI_DAU + 24)
        if cao > cho:                      # the cao hon vung trong -> co chu cho vua, KHONG de len CTA
            while cao > cho and zf.size > 64:
                zf = sp.font("zh", zf.size - 6)
                if nf.size > 40: nf = sp.font("viet", nf.size - 2)
                nd = sp.wrap_text(d, nghia or "", nf, SW - 170)[:3]
                cao = ((pf.size + 10) if py else 0) + int(zf.size * 1.34) + len(nd) * (nf.size + 10) + 70
            cao = min(cao, cho)
        y2 = DUOI_DAU + 24
        d.rounded_rectangle([34, y2, SW - 34, y2 + cao], radius=28, fill=(18, 15, 11, 210))
        d.rounded_rectangle([34, y2, 46, y2 + cao], radius=6, fill=(255, 196, 70, 235))
        yy = y2 + 32
        if py:
            d.text(((SW - sp.text_w(d, py, pf)) // 2, yy), py, font=pf, fill=(150, 214, 236))
            yy += pf.size + 10
        d.text(((SW - sp.text_w(d, han, zf)) // 2, yy), han, font=zf, fill=(255, 248, 236))
        yy += int(zf.size * 1.34)
        for ln in nd:
            d.text(((SW - sp.text_w(d, ln, nf)) // 2, yy), ln, font=nf, fill=(255, 205, 110))
            yy += nf.size + 10
        if stt:
            sf = sp.font("sansb", 40)
            d.text((SW - 66 - sp.text_w(d, stt, sf), y2 + 26), stt, font=sf, fill=(200, 184, 152))

    cf = sp.font("sansb", 46)
    tw = sp.text_w(d, cta, cf)
    d.rounded_rectangle([(SW - tw) // 2 - 38, SH - 244, (SW + tw) // 2 + 38, SH - 154],
                        radius=26, fill=(255, 200, 40, 238))
    d.text(((SW - tw) // 2, SH - 225), cta, font=cf, fill=(40, 30, 10))
    im.save(path)
    return path


DOAN_MIN, DOAN_MAX = 20.0, 30.0        # nguoi dung chot: doan hay phai 20-30 giay


def _noi_rong_doan(video, hat):
    """Tu dong dinh, noi rong sang cac cau LIEN TUC hai ben cho du DOAN_MIN giay.
    Tra ve [(start, end, dong)] MOT phan tu -> cat mot lat lien mach, khong ghep."""
    st0, en0, (h, v, ghi) = hat
    segs = [x for x in json.load(io.open(video + ".meta.json", encoding="utf-8"))["segments"]
            if x.get("hanzi")]
    segs.sort(key=lambda x: float(x["start"]))
    i = min(range(len(segs)), key=lambda k: abs(float(segs[k]["start"]) - st0))
    a = b = i
    while float(segs[b]["end"]) - float(segs[a]["start"]) < DOAN_MIN:
        sau   = b + 1 < len(segs)
        truoc = a - 1 >= 0
        if not (sau or truoc):
            break
        # uu tien keo VE SAU (cau tiep noi y), het moi lui ve truoc
        if sau and (float(segs[b + 1]["end"]) - float(segs[a]["start"])) <= DOAN_MAX:
            b += 1
        elif truoc and (float(segs[b]["end"]) - float(segs[a - 1]["start"])) <= DOAN_MAX:
            a -= 1
        else:
            break
    st, en = float(segs[a]["start"]), float(segs[b]["end"])
    if en - st > DOAN_MAX:
        en = st + DOAN_MAX
    return [(st, en, (h, v, ghi))]


def lam_short_clip(video, spec, out_dir, ten_file, cta="Xem bài đầy đủ trên kênh 👆",
                   dem_toi_thieu=2.2):
    """Cat cac doan THAT chua tung dong bai hoc, de lop day hoc len, noi lai thanh 1 Short."""
    import shorts as _sh
    video = os.path.abspath(video)
    moc = _moc_theo_cau(video, spec["lines"])
    if not moc:
        raise RuntimeError("không khớp được câu nào của bài học vào video")
    if spec["loai"] == "doan":
        moc = _noi_rong_doan(video, moc[0])       # 1 lat cat lien tuc, du dai de hieu
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, ten_file + ".mp4")
    tam, phan = [], []
    n = len(moc)
    try:
        for i, (st, en, (h, v, ghi)) in enumerate(moc, 1):
            if spec["loai"] == "doan":
                st = max(0.0, st - 0.30); dur = (en - st) + 0.55   # giu tron lat cat
            else:
                st = max(0.0, st - 0.25); dur = max(dem_toi_thieu, (en - st) + 0.45)
            han = py = ngh = ""
            if spec["loai"] == "tu":
                han, ngh = h, v
                try:
                    import short_native as _sn; py = _sn.pinyin_str(h)
                except Exception: py = ""
            elif spec["loai"] == "mau":
                han, ngh = (ghi or ""), v
            hook = spec.get("hook", "")
            if spec["loai"] == "doan":
                hook, han = (v or spec.get("hook", "")), ""
            ovl = os.path.join(out_dir, "_lo_%s_%d.png" % (ten_file, i))
            cl  = os.path.join(out_dir, "_lc_%s_%d.mp4" % (ten_file, i))
            tam += [ovl, cl]
            _lop_day(hook, han, py, ngh, cta, ovl,
                     stt=("%d/%d" % (i, n)) if n > 1 else "", ten_bai=spec.get("ten_bai", ""))
            _sh.cut_short(video, st, dur, ovl, cl)
            phan.append(cl)
        if len(phan) == 1:
            os.replace(phan[0], out); tam.remove(phan[0])
        else:
            ds = os.path.join(out_dir, "_ll_%s.txt" % ten_file); tam.append(ds)
            io.open(ds, "w", encoding="utf-8").write(
                "".join("file '%s'\n" % os.path.abspath(p) for p in phan))
            subprocess.run(["ffmpeg", "-y", "-v", "quiet", "-f", "concat", "-safe", "0",
                            "-i", ds, "-c", "copy", out], check=True)
    finally:
        for f in tam:
            if os.path.exists(f):
                os.remove(f)
    return {"file": out}
