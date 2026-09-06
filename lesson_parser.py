# -*- coding: utf-8 -*-
"""Parse noi dung dang text (de gui tu ChatGPT) thanh ctx + segments.

Dinh dang:
    @title CHÀO HỎI
    @hanzi 你好              (tuy chon - chu Han o slide tieu de)
    @topic cách chào hỏi     (tuy chon - cau gioi thieu trong intro)
    @hsk HSK1                (tuy chon)
    @objectives Cách chào; Cách cảm ơn; Tạm biệt   (tuy chon, ngan cach ;)

    # TỪ VỰNG
    你好 | Xin chào
    谢谢 | Cảm ơn

    # MẪU CÂU
    你好吗？ | Bạn khỏe không?

    # HỘI THOẠI
    A: 你好！ | Xin chào!
    B: 你好！ | Xin chào!

    # LUYỆN TẬP
    ? "Cảm ơn" nói thế nào?      (tuy chon - cau hoi)
    谢谢 | Cảm ơn                 (dap an)
"""
import re

def generate_la_ssml(t):
    import generate as _g
    return _g.la_ssml(t)

def generate_strip_ssml(t):
    import generate as _g
    return _g._strip_ssml(t)

def _section_type(name):
    u = name.upper()
    if "VỰNG" in u or "VOCAB" in u or "TỪ" in u:        return "vocab"
    if "HỘI" in u or "THOẠI" in u or "DIALOG" in u:     return "dialogue"
    if "LUYỆN" in u or "PRACTICE" in u or "TẬP" in u:   return "practice"
    if "MẪU" in u or "CÂU" in u or "SENTENCE" in u:     return "sentence"
    return "sentence"

def _split_item(line):
    """'hanzi | viet' -> (hanzi, viet)."""
    if "|" in line:
        a, b = line.split("|", 1)
        return a.strip(), b.strip()
    return line.strip(), ""

# ---------- TU NHAN DIEN NGUOI NOI (auto speaker detection) ----------
# nhan = tu Latin (A, Host) HOAC 1-6 chu Han (王雨, 记者) + dau ':' / '：'
_SPK_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 ]{0,14}|[一-鿿]{1,6})\s*[:：]")
_TIME_RE = re.compile(r"^\s*\d{1,2}[:：]\d{2}")
_HR_RE = re.compile(r"^-{3,}$")   # ranh gioi phu luc: '---' hoac nhieu hon (----, -----)
_NON_SPEAKER = {"时间", "时长", "时候", "正文", "介绍", "目录", "日期", "地点",
                "time", "date", "url", "link", "note", "ghi chú",
                # LIEN TU / TU DAN trong van ke — dung truoc dau ':' nhung KHONG phai ten
                # nguoi noi: "而是：...", "记住：...", "第一行：...", "规则很简单：..."
                "而是", "但是", "可是", "所以", "因为", "然后", "记住", "注意", "结果",
                "比如", "例如", "其实", "于是", "后来", "首先", "接着", "最后", "总之",
                "第一行", "第二行", "第三行", "第一步", "第二步", "第三步",
                "第一", "第二", "第三", "问题", "答案", "规则", "方法", "原因", "结论"}
# Phan biet MENH DE tuong thuat ("陈师傅说：", "心里却想着：", "我又问他：") voi NHAN
# nguoi noi that ("小明:", "记者:", "A:"). Menh de tuong thuat = chu ngu + dong tu noi/nghi
# [+ tan ngu/tro tu]; nhan nguoi noi = danh tu rieng ngan.
_NARR_VERB1 = "说问答喊叫道想笑应叹哭写回"      # dong tu noi/nghi 1 chu (写: '纸条上写着...'; 回: '朋友回：...')
_NARR_VERB2 = ("补充", "解释", "回答", "回应", "插话", "嘟囔", "咕哝", "嘀咕",
               "告诉", "表示", "提醒", "强调", "反问", "追问", "感叹",
               "点头", "摇头", "摆手", "耸肩",
               "回复", "安慰", "惊讶", "吃惊", "沉默", "犹豫", "叹气")  # dong tu noi/hanh dong 2 chu
_NARR_TAIL = "我你他她它们咱俺着了过道"           # tan ngu (dai tu)/tro tu bam sau dong tu:
                                                 # 问[我], 告诉[你], 想[着], 说[过/道]...

# dong tu "noi" de nhan biet 1 dong LA nhan vat X dang noi ("老赵笑着说：...")
_SAY_VERBS = "说问道喊叫答"
def _parse_voices(val):
    """'@voices 老赵=nam, 小美=nữ' hoac '老赵=zh-CN-YunjianNeural'
       -> {ten: spec}. spec = 'nam'/'nu'/gioi tinh HOAC ma giong edge cu the."""
    out = {}
    for part in re.split(r"[,;]", val or ""):
        if "=" in part:
            n, v = part.split("=", 1)
            n, v = n.strip(), v.strip()
            if n and v:
                out[n] = v
    return out

def _tag_speaker_by_names(hanzi, names):
    """Neu dong LA 1 nhan vat da khai bao (@voices) dang noi -> tra ve ten do; nguoc lai None.
       CHI khop cac ten da khai (tin cay, khong doan mo). VD 'X + (trong vai chu) + noi:' hoac
       ca dong nam trong ngoac kep (loi thoai)."""
    if not names or not hanzi:
        return None
    for name in names:
        if hanzi.startswith(name):
            # 'X...说/问/道：'  (co dong tu noi trong ~6 ky tu dau)
            if re.match(rf"^{re.escape(name)}.{{0,6}}[{_SAY_VERBS}]", hanzi):
                return name
    return None

def _is_narration_label(sp):
    """True neu 'sp' la mot menh de tuong thuat (nen bo qua), khong phai nhan nguoi noi.
       NEO dong tu vao CUOI nhan (sau khi bo tan ngu/tro tu) de tranh chan nham ten
       rieng co chu dong tu o giua/dau: '李道明', '问天', '阿道' -> van la nhan hop le."""
    # nhan bat dau bang dai tu nhan xung (我你他她它咱俺) -> KHONG bao gio la ten nguoi noi
    # that ('小明','记者','A'), ma la menh de tuong thuat: '我很惊讶', '她大笑起来', '他转过身'...
    # (dong tu co the o GIUA nhu '大笑起来' nen khong the chi neo o cuoi).
    if sp[0] in "我你他她它咱俺":
        return True
    # TEN NGUOI NOI THAT luon NGAN: '小明', '记者', '王师傅', '炒锅师傅' (toi da 4 chu).
    # Dai hon -> chac chan la menh de tuong thuat: '老马安慰自己', '刘主任很吃惊'.
    if len(sp) > 4:
        return True
    # TRO TU / PHO TU khong bao gio nam trong ten rieng -> co mat = menh de tuong thuat:
    # '阿强愣了一下', '大伟低着头', '小婷很惊讶', '翻译的意思是'.
    if any(ch in sp for ch in "了着过很的都又也就还才把被"):
        return True
    s = sp
    while len(s) > 1 and s[-1] in _NARR_TAIL:   # bo '他'/'着'/'了'/'道' o cuoi
        s = s[:-1]
    if s and s[-1] in _NARR_VERB1:              # ket thuc bang dong tu noi 1 chu
        return True
    if s.endswith(_NARR_VERB2):                 # ket thuc bang dong tu noi 2 chu
        return True
    return False

def parse_speaker(line):
    """(speaker, rest) neu dong co nhan nguoi noi hop le; nguoc lai (None, line).
       Bo qua timestamp (00:12), nhan toan so, tu khoa metadata (时间...),
       va menh de tuong thuat ket thuc bang dong tu noi/nghi ("...说：", "...又问他：")."""
    head = line.split("|", 1)[0]
    if _TIME_RE.match(head):
        return None, line
    m = _SPK_RE.match(head)
    if not m:
        return None, line
    sp = m.group(1).strip()
    if not sp or sp.isdigit() or sp.lower() in _NON_SPEAKER or sp in _NON_SPEAKER:
        return None, line
    if _is_narration_label(sp):
        return None, line
    return sp, line[m.end():].strip()

_TERMINAL = "。！？.!?…—"
# ---- NHIP THO (breath) ----
# Dong ket bang dau PHAY ma van la mot cap 'hanzi | dich' hoan chinh => tac gia CO Y
# ngat de lay hoi giua mot cau dai, KHONG phai dong bi xuong dong nham. Khong gop.
_BREATH_END = "，,、；;"
_PAD_BREATH = 0.18    # cung mot hoi -> chi hop rat nhe
_PAD_SHORT  = 0.32    # cau <=7 chu Han -> nhip don, khong nghi dai
_PAD_STOP   = 0.55    # het cau (。.)
_PAD_EMO    = 0.80    # cau hoi / cam than
_PAD_LONG   = 0.72    # cau dai -> nghi sau hon mot chut cho ngam

# Duong cong nghi lien tuc thay cho _PAD_SHORT/_PAD_STOP/_PAD_LONG (van giu 3 hang
# so tren de tuong thich va de so sanh). n = so chu Han (tieng khac quy doi).
#   n=4 -> 0.32   n=12 -> 0.47   n=18 -> 0.58   n=26 -> 0.73
_PAD_C0  = 0.24
_PAD_K   = 0.019
_PAD_MIN = 0.26
_PAD_MAX = 0.82
# ---- KY TU NGAT NGHI do NGUOI VIET dat trong content.md (xem SKILL tan-van / giong-van) ----
# Tat ca deu bi BOC KHOI CHU truoc khi ve phu de va truoc khi goi TTS -> may KHONG doc chung.
_PAD_HANG   = 1.00    # het cau bang '……' -> treo lung, de nguoi nghe tu dien not
_PAD_DASH   = 0.45    # het cau bang '——'  -> ngat nhan giua mach van
_LANG_SLASH = 1.20    # '//' cuoi ve  -> lang them 1,2s (khong hien tren phu de)
_LANG_TILDE = 2.50    # dong chi co '~' -> lang 2,5s cho nhac troi len
_NHAN_DR    = -8      # dong danh dau '*' -> doc cham hon 8%, nghi sau dai hon
_NHAN_PAD   = 1.40

def _ends_breath(s):
    """Da 'dong' cau HOAC la mot nhip lay hoi co chu y.
       Dong dang 'hanzi | dich' -> XET VE HAN (don vi cau that), khong xet ve dich:
       ve dich hay ket bang ',' ':' '-' ma cau Han da tron ven -> khong duoc gop."""
    # rsplit: item da bi GOP se co nhieu dau '|' -> phai lay cum Han CUOI CUNG,
    # neu khong se gop day chuyen (mot dong ket bang ':' nuot sach phan con lai cua bai).
    head = s.rsplit(" | ", 1)[0] if " | " in s else s
    if _ends_terminal(head):
        return True
    # BOC SSML: dong gan the ket bang '</prosody>' / '</mstts:express-as>' chu khong
    # phai '，'. Khong boc thi ky tu cuoi la '>' -> khong khop _BREATH_END -> parser
    # tuong cau chua ngat va NUOT DONG KE TIEP. (bai 61 mat 4 dong, 2026-09-06)
    head = generate_strip_ssml(head)
    h = head.rstrip().rstrip("\"'”’」』）) ")
    return bool(h) and h[-1] in _BREATH_END

def breath_pad(hanzi):
    """Nghi bao lau sau cau nay — theo dau cau va do dai, thay cho PAD co dinh 0.8s."""
    # Boc SSML truoc: neu khong, ky tu cuoi luon la '>' nen MOI cau gan the deu
    # roi xuong nhanh mac dinh, va so chu Han dem ca ten the -> nghi sai.
    t = generate_strip_ssml(hanzi or "")
    t = t.rstrip().rstrip("\"'”’」』）) ")
    if not t:
        return None
    if t[-1] in _BREATH_END:
        return _PAD_BREATH
    if t[-1] == "…":                     # '……' hoac '...' -> treo lung
        return _PAD_HANG
    if t[-1] == "—":                     # '——' -> ngat nhan
        return _PAD_DASH
    if t[-1] in "？！?!":
        return _PAD_EMO
    # DAI NGAN: dem chu Han voi tieng Trung, dem TU voi cac thu tieng khac.
    # Truoc day chi dem chu Han -> bai TIENG VIET co 0 chu Han nen MOI dong deu bi
    # coi la "cau ngan" -> lai ve mot muc nghi duy nhat, dung cai loi minh dinh chua.
    n_cjk = sum(1 for c in t if _is_cjk_char(c))
    n_unit = n_cjk if n_cjk else len(t.split())
    if not n_cjk:
        n_unit = int(round(n_unit * 22 / 16.0))   # quy ve thang do chu Han

    # DO DAI -> NGHI, LIEN TUC chu khong con 3 BAC.
    # Do 2026-08-23 tren 7 bai moi (46-52): bang 3 bac lam 75-89% moi cau nghi
    # DUNG MOT CON SO 0.55s, ~19 lan/phut, cach nhau deu 3,2s. Tai nghe ra
    # may danh nhip, khong phai nguoi doc. Do lech chuan gan nhu khong doi khi
    # sua - cai phai sua la TY LE LAP LAI cua mot gia tri duy nhat.
    pad = _PAD_C0 + _PAD_K * n_unit
    pad = max(_PAD_MIN, min(_PAD_MAX, pad))

    # Rung nhe, TAT DINH theo noi dung cau (cung mot cau luon ra cung mot so ->
    # render lai khong lech). Chi de pha the trung nhau, khong doi cam giac nhip.
    import hashlib as _hl
    jit = (int(_hl.md5(t.encode("utf-8")).hexdigest()[:4], 16) % 13 - 6) / 100.0
    return round(max(_PAD_MIN - 0.06, pad + jit), 3)
def boc_dau_nhip(item):
    """Boc ky tu ngat nghi cua nguoi viet ra khoi cau.

    '*' bat ky dau trong dong  -> ca dong doc cham hon (nhan), nghi sau dai hon
    '//' cuoi ve Han/ve dich   -> lang them 1,2s

    Tra ve (dong da sach, nhan, lang_them). Vi boc NGAY LUC PARSE nen ca phu de
    lan van ban dua cho TTS deu khong con ky tu nay -> may khong bao gio doc chung.
    """
    lang_them = 0.0
    s = item
    nhan = "*" in s
    if nhan:
        s = s.replace("*", "")

    def _boc(v):
        nonlocal lang_them
        v = v.rstrip()
        while v.endswith("//"):
            lang_them += _LANG_SLASH
            v = v[:-2].rstrip()
        return v

    if "|" in s:
        hz, vi = s.split("|", 1)
        s = _boc(hz).rstrip() + " | " + _boc(vi).strip()
    else:
        s = _boc(s)
    return s.strip(), nhan, lang_them


_DAU_NGHI_RE = re.compile(r"^/{2,4}$")

def boc_dau_nhip_van_ban(text, giu_dau_nghi=False):
    """Boc ky tu ngat nghi khoi CA VAN BAN, giu nguyen cau truc dong.

    Dung cho cac duong KHONG di qua parse_lesson — PDF ban chu (study_pdf),
    trang /short, trang /film. Neu khong boc thi '*' va '//' hien nguyen trong
    PDF va bi TTS doc thanh tieng (do duoc: '*是累。*' dai 3,12s so voi 1,78s).

    giu_dau_nghi=True: dong CHI GOM 2-4 dau '/' la LENH NGHI cua kich ban phim
    (NHIP-NGAT-NGHI-V3.md: '//' 0,8s · '///' 1,5s · '////' 2,4s), khong phai chu.
    Truoc day _boc() an luon duoi cua no: '//' va '////' bi xoa sach con '///'
    teo thanh '/' roi bi doc len — ca he thong ngat nghi cua kich ban khong bao
    gio den duoc video. Trang /film truyen True; cac duong khac giu nguyen nhu cu.
    """
    out = []
    for raw in (text or "").splitlines():
        s = raw.strip()
        if s in ("~", "～", "~~", "~~~"):     # dong lang cho nhac troi -> khong phai chu
            continue
        if giu_dau_nghi and _DAU_NGHI_RE.match(s):
            out.append(s)                    # lenh nghi -> chuyen thang cho film.py
            continue
        if not s or s.startswith(("@", "#", "<!--")):
            out.append(raw)
            continue
        out.append(boc_dau_nhip(s)[0])
    return "\n".join(out)


def _ghi_dau_nhip(sec, idx, nhan, lang_them):
    """Nho lai dau nhip cua dong thu idx trong section (dong bi gop thi don vao item truoc)."""
    if nhan:
        sec.setdefault("nhan", set()).add(idx)
    if lang_them:
        lt = sec.setdefault("lang_them", {})
        lt[idx] = lt.get(idx, 0.0) + lang_them


def _is_cjk_char(ch):
    o = ord(ch)
    return ("一" <= ch <= "鿿") or 0x3000 <= o <= 0x303F or 0xFF00 <= o <= 0xFFEF

def _ends_terminal(s):
    """Dong da 'dong' chua? (ket thuc bang dau cau, bo qua ngoac/nhay cuoi).

    BOC THE SSML TRUOC KHI XET: dong co the ket thuc bang '</prosody>' /
    '</mstts:express-as>' chu khong phai '。'. Khong boc thi parser tuong cau chua
    xong va NUOT DONG KE TIEP vao — bai 61 mat 21 dong vi loi nay (2026-09-06).
    """
    s = generate_strip_ssml(s)
    s = s.rstrip().rstrip("\"'”’」』）) ")
    return bool(s) and s[-1] in _TERMINAL

def _smart_join(a, b):
    """Noi 2 manh: Han giap Han -> khong space; con lai -> 1 dau cach."""
    a, b = a.rstrip(), b.lstrip()
    if a and b and _is_cjk_char(a[-1]) and _is_cjk_char(b[0]):
        return a + b
    return a + " " + b

def detect_speakers(text):
    """Tra ve danh sach nguoi noi theo thu tu xuat hien ([] neu doc thoai/khong ro).
       Chi coi la hoi thoai khi co >=2 nguoi noi khac nhau."""
    order = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if _HR_RE.match(line):           # het phan noi dung chinh -> bo qua phu luc
            break
        if not line or line[0] in "@#":
            continue
        sp, _ = parse_speaker(line)
        if sp and sp not in order:
            order.append(sp)
    return order if len(order) >= 2 else []

# doan gioi tinh tu ten -> chon giong nam/nu
_FEM_HAN = set("雨丽娜婷芳燕玲莉娟静秀红梅兰珍春花雪琴霞凤蕾欣怡颖琳云悦佳慧洁妍柔萍嫣媛璐妮")
_MALE_HAN = set("明强伟军磊勇刚峰涛斌波辉杰俊浩宇航昊鹏龙飞建国华")
_FEM_EN = {"sarah", "emma", "anna", "mary", "lisa", "aria", "rachel", "linda", "lan", "hoa"}
_NEUTRAL = {"记者", "主持人", "主播", "专家", "host", "guest", "mc", "khách", "người dẫn"}

def guess_gender(name):
    """'F' / 'M' / None (trung tinh)."""
    if not name:
        return None
    low = name.lower()
    if name in _NEUTRAL or low in _NEUTRAL:
        return None
    if name[-1] in _FEM_HAN:
        return "F"
    if name[-1] in _MALE_HAN:
        return "M"
    if low in _FEM_EN:
        return "F"
    return None

# pool giong MS (edge/azure dung chung ten) — nam/nu
VOICES_F = ["zh-CN-XiaoxiaoNeural", "zh-CN-XiaoyiNeural", "zh-CN-XiaomengNeural"]
VOICES_M = ["zh-CN-YunjianNeural", "zh-CN-YunxiNeural", "zh-CN-YunyangNeural"]

def assign_speaker_voices(speakers):
    """{speaker: voice} — doan gioi tinh; nguoi trung tinh (nhan vai: 司机/售票员/路人...)
       duoc BU cho CAN BANG voi gioi da biet (vd da co 1 nu -> nguoi trung tinh thanh nam),
       nen hoi thoai 2 nguoi luon ra 1 nam + 1 nu thay vi 2 giong cung gioi.
       Moi nguoi 1 giong on dinh, xoay vong khi thieu."""
    genders = {sp: guess_gender(sp) for sp in speakers}
    known_f = sum(1 for g in genders.values() if g == "F")
    known_m = sum(1 for g in genders.values() if g == "M")
    fi = mi = 0
    vmap = {}
    for sp in speakers:
        g = genders[sp]
        if g is None:                       # trung tinh -> bu cho can bang
            if known_f > known_m:
                g = "M"; known_m += 1
            elif known_m > known_f:
                g = "F"; known_f += 1
            else:                           # dang hoa -> luan phien on dinh
                g = "F" if (fi + mi) % 2 == 0 else "M"
                if g == "F": known_f += 1
                else: known_m += 1
        if g == "F":
            vmap[sp] = VOICES_F[fi % len(VOICES_F)]; fi += 1
        else:
            vmap[sp] = VOICES_M[mi % len(VOICES_M)]; mi += 1
    return vmap

def parse_lesson(text):
    """Tra ve ctx dict: title, hanzi_title, topic, hsk, segments[...]."""
    meta = {"title": "BÀI HỌC", "hanzi_title": "", "topic": "", "hsk": "HSK1",
            "objectives": [], "image_prompt": "", "header": "", "hsk_explicit": False,
            "voices": {}}
    sections = []           # [(label, type, [items])]
    cur = None

    for raw in text.splitlines():
        line = raw.strip()
        if _HR_RE.match(line):          # het phan noi dung chinh -> bo qua phu luc
            break
        if not line:
            # DONG TRONG = ranh gioi doan -> danh dau cau cuoi cua doan hien tai (nghi dai hon)
            if cur and cur.get("items"):
                cur.setdefault("para_ends", set()).add(len(cur["items"]) - 1)
            continue
        if line in ("~", "～", "~~", "~~~"):
            # DONG CHI CO '~' = khoang lang de nhac troi len. Khong tao cau, chi keo dai
            # khoang nghi cua cau ngay truoc no.
            if cur and cur.get("items"):
                lt = cur.setdefault("lang_them", {})
                lt[len(cur["items"]) - 1] = lt.get(len(cur["items"]) - 1, 0.0) + _LANG_TILDE
            continue
        if line.startswith("@"):
            key, _, val = line[1:].partition(" ")
            key, val = key.strip().lower(), val.strip()
            if key == "objectives":
                meta["objectives"] = [s.strip() for s in val.split(";") if s.strip()]
            elif key == "title":       meta["title"] = val
            elif key == "hanzi":       meta["hanzi_title"] = val
            elif key == "topic":       meta["topic"] = val
            elif key == "hsk":         meta["hsk"] = val; meta["hsk_explicit"] = True
            elif key == "image":       meta["image_prompt"] = val
            elif key == "header":      meta["header"] = val
            elif key == "voices":      meta["voices"] = _parse_voices(val)
            continue
        if line.startswith("#"):
            label = line.lstrip("#").strip()
            cur = {"label": label, "type": _section_type(label),
                   "items": [], "explicit": True}
            sections.append(cur)
            continue
        if cur is None:                # dong le (khong co #) -> cau, KHONG divider
            cur = {"label": "", "type": "sentence", "items": [], "explicit": False}
            sections.append(cur)
        # BOC KY TU NGAT NGHI ngay tu day (truoc khi gop dong): neu boc muon, dong ket
        # bang '*' hay '//' bi coi la CHUA dong cau -> nuot luon dong sau.
        line, _nhan, _lt = boc_dau_nhip(line)
        # GOP DONG NOI TIEP: dong bi xuong dong giua luot/cau (khong co nhan nguoi noi)
        # -> noi vao item truoc. Khong gop trong vocab (moi dong = 1 tu).
        if cur["items"]:
            sp, _ = parse_speaker(line)
            if sp is None:
                prev = cur["items"][-1]
                # Noi tiep CHI khi item truoc CHUA ket thuc bang dau cau.
                # (cu: "prev co nhan nguoi noi" cung gop -> mot dong bi nhan nham la nhan
                #  nguoi noi se NUOT toan bo cac dong sau no, vi sau khi gop prev VAN con
                #  nhan do -> vong lap gop vo tan. Mot bai 96 dong tung bi rut con 9 muc,
                #  ca doan don thanh MOT phu de tran man hinh.)
                if cur["type"] != "vocab" and not _ends_breath(prev):
                    cur["items"][-1] = _smart_join(prev, line)
                    _ghi_dau_nhip(cur, len(cur["items"]) - 1, _nhan, _lt)
                    continue
        cur["items"].append(line)
        _ghi_dau_nhip(cur, len(cur["items"]) - 1, _nhan, _lt)

    # ---- tu nhan dien hoi thoai: section nao co >=2 nguoi noi -> doi sang dialogue ----
    for sec in sections:
        if sec["type"] != "dialogue":
            sps = []
            for it in sec["items"]:
                sp, _ = parse_speaker(it)
                if sp and sp not in sps:
                    sps.append(sp)
            if len(sps) >= 2:
                sec["type"] = "dialogue"

    # ---- dung segments ----
    segs = [{"type": "title"}]
    if meta["objectives"]:
        segs.append({"type": "objectives", "lines": meta["objectives"]})

    for sec in sections:
        if not sec["items"]:
            continue
        if sec.get("explicit"):        # chi them divider khi co dong '#'
            segs.append({"type": "section", "label": sec["label"].upper()})
        st = sec["type"]
        if st == "dialogue":
            rows = []
            for it in sec["items"]:
                sp = ""
                body = it
                head = it.split("|", 1)[0]          # chi xet phan truoc dau '|'
                # nhan nguoi noi: 'A:' / 'B：' / '小明:' ... (ho tro ca ':' va '：')
                m = re.match(r"^\s*([A-Za-z0-9一-鿿]{1,12})\s*[:：]\s*", head)
                if m:
                    sp = m.group(1).strip()
                    body = it[m.end():]            # phan con lai: 'hanzi | viet'
                hz, vi = _split_item(body)
                row = {"sp": sp or "A", "hanzi": hz, "pinyin": "", "viet": vi}
                if generate_la_ssml(hz):        # the SSML viet tay -> doc co the, hien khong the
                    row["tts"], row["hanzi"] = hz, generate_strip_ssml(hz)
                rows.append(row)
            segs.append({"type": "dialogue", "rows": rows})
        elif st == "practice":
            for it in sec["items"]:
                if it.startswith("?"):
                    segs.append({"type": "practice_q", "question": it[1:].strip()})
                else:
                    hz, vi = _split_item(it)
                    segs.append({"type": "practice_a", "hanzi": hz, "pinyin": "", "viet": vi})
        else:                                       # vocab / sentence
            pends = sec.get("para_ends", set())
            langs = sec.get("lang_them", {})
            nhans = sec.get("nhan", set())
            for idx, it in enumerate(sec["items"]):
                nhan = idx in nhans                  # '*' — da boc khoi chu tu luc doc dong
                hz, vi = _split_item(it)
                s2 = {"type": st, "hanzi": hz, "pinyin": "", "viet": vi}
                if generate_la_ssml(hz):        # the SSML viet tay (xem generate.la_ssml)
                    s2["tts"], s2["hanzi"] = hz, generate_strip_ssml(hz)
                    hz = s2["hanzi"]            # pad/nhip do tren chu sach
                bp = breath_pad(hz)                  # nhip tho theo dau cau
                if bp is not None:
                    s2["_pad"] = bp
                    # generate.py tinh lai pad tu hanzi; giu ban goc de khong phai doan lai
                    s2["_pad_raw"] = bp * (_NHAN_PAD if nhan else 1.0)
                if nhan:
                    s2["_nhan"] = True               # doc cham hon, tach khoi block-tts
                extra = float(langs.get(idx, 0.0))
                if extra:
                    s2["_lang_them"] = round(extra, 2)
                if idx in pends:
                    s2["_para_end"] = True           # cau ket doan -> nghi dai (para_gap)
                segs.append(s2)

    segs.append({"type": "outro"})

    # ---- GAN NGUOI NOI theo @voices (khai bao tay -> tin cay, khong doan mo) ----
    # dong nao LA nhan vat da khai dang noi -> danh dau _sp = ten do -> app gan giong rieng.
    vnames = list(meta.get("voices") or {})
    if vnames:
        for s in segs:
            if s.get("type") in ("sentence", "vocab") and s.get("hanzi"):
                who = _tag_speaker_by_names(s["hanzi"], vnames)
                if who:
                    s["_sp"] = who

    # hanzi_title mac dinh: lay tu vung dau tien
    if not meta["hanzi_title"]:
        for s in segs:
            if s.get("type") in ("vocab", "sentence") and s.get("hanzi"):
                meta["hanzi_title"] = s["hanzi"][:2]
                break
        if not meta["hanzi_title"]:
            meta["hanzi_title"] = "学习"
    if not meta["topic"]:
        meta["topic"] = meta["title"].lower()

    return {
        "id": 1, "hsk": meta["hsk"], "title": meta["title"],
        "topic": meta["topic"], "hanzi_title": meta["hanzi_title"],
        "image_prompt": meta["image_prompt"], "header": meta["header"],
        "hsk_explicit": meta["hsk_explicit"], "voices": meta.get("voices", {}),
        "segments": segs,
    }

if __name__ == "__main__":
    sample = """@title CHÀO HỎI
@hanzi 你好

# TỪ VỰNG
你好 | Xin chào
谢谢 | Cảm ơn

# MẪU CÂU
你好吗？ | Bạn khỏe không?

# HỘI THOẠI
A: 你好！ | Xin chào!
B: 我很好，谢谢！ | Tôi khỏe, cảm ơn!

# LUYỆN TẬP
? "Cảm ơn" nói thế nào?
谢谢 | Cảm ơn
"""
    import json
    print(json.dumps(parse_lesson(sample), ensure_ascii=False, indent=2))
