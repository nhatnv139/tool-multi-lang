# -*- coding: utf-8 -*-
"""Bước 2+3 của quy trình: sinh MỘT audio liền mạch cho cả đoạn hội thoại,
và lấy TIMELINE chính xác từng câu — không dùng WhisperX.

Vì sao không WhisperX: audio do chính mình sinh ra, Azure biết chính xác từng chữ
phát lúc nào. WhisperX là nghe lại rồi đoán ngược — nặng vài GB, thêm sai số ASR.

Đo ngày 2026-09-15 trên key dự án:
  - giọng Neural thường  -> <bookmark> bắn đủ 3/3, tái lập y hệt từng byte
  - giọng Dragon HD      -> bookmark 0/3, phải lùi về WordBoundary + text_offset
  - text_offset đánh chỉ số vào CHUỖI SSML, KHÔNG phải văn bản thuần
  - SDK cũng chập chờn: có lần trả 1,8s/7 sự kiện thay vì 10,7s/38 -> phải chốt chặn
"""
import os, re, time

NS = ('<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
      'xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="zh-CN">')


def _esc(t):
    """Escape & và < KHÔNG thuộc thẻ SSML hợp lệ."""
    import generate as g
    return g._ssml_escape_giu_the(t)


# Khoảng nghỉ TRƯỚC mỗi câu, suy từ vai trò của câu trong mạch thoại.
# Nói chuyện thật thì nhịp nghỉ KHÔNG đều: cướp lời thì gần như không nghỉ,
# nghĩ một lúc mới đáp thì nghỉ lâu. Nghỉ đều tăm tắp là giọng máy. (2026-09-16)
_NGHI = [
    (("chen ngang", "cướp lời", "đáp ngay", "nói tiếp", "nói liền", "vừa làm vừa"), 60),
    (("một tiếng", "cụt", "gật", "đáp gọn", "reo", "bật cười", "trêu"),            140),
    (("hỏi lại", "vặn", "nhắc lại", "khen", "hưởng ứng"),                          260),
    (("ngượng", "lí nhí", "đuối", "bỏ lửng", "nghĩ", "ngập ngừng", "do dự"),       520),
    (("chuyển cảnh", "đổi chuyện", "quay lại chuyện", "chốt"),                     620),
]
_NGHI_MAC_DINH = 300

# Azure TU nghi san ~0,64s giua hai cau — cong break vao la thanh ~0,95s, nghe nhu may.
# Cach chua: ha NEN xuong 60ms bang mstts:silence roi CONG THEM theo tung cau.
# Do that 2026-09-16: silence 100ms -> quang lang 0,14s · 200ms -> 0,25s · 350ms -> 0,40s
NEN_MS = 60                      # quang lang toi thieu giua hai cau
_TRU = 100                       # quang lang thuc te ~ NEN + break + 40ms


def _break_thuc(ms_mong_muon):
    """Doi 'quang lang mong muon' -> so ms can chen them, da tru phan Azure tu nghi."""
    return max(0, int(ms_mong_muon) - _TRU)


def nghi_truoc(ghi_chu):
    """Ghi chú -> số mili giây nghỉ trước câu đó.
    Ưu tiên chỉ định TAY: ghi `nghỉ 480` trong cột ghi chú thì lấy đúng 480ms.
    Không có thì mới suy theo từ khoá."""
    import re as _re
    g = (ghi_chu or "").lower()
    m = _re.search(r"nghỉ\s*(\d{2,4})", g)
    if m:
        return max(0, min(1500, int(m.group(1))))
    for khoa, ms in _NGHI:
        if any(k in g for k in khoa):
            return ms
    return _NGHI_MAC_DINH


def dung_ssml(dong, giong_vai, giong_mac_dinh, rate=None):
    """dong: [(hz_co_the, vai)] hoặc [(hz, vai, ghi_chu)] -> (ssml, [ten_moc]).
    Gộp các câu LIÊN TIẾP cùng vai vào một <voice> để ngữ điệu chảy liền,
    và chèn khoảng nghỉ KHÔNG ĐỀU giữa các câu theo `ghi_chu`."""
    ra, moc = [NS], []
    cur, dem = None, 0
    for mux in dong:
        hz, vai = mux[0], mux[1]
        ghi = mux[2] if len(mux) > 2 else ""
        g = giong_vai.get(vai) or giong_mac_dinh
        g = g.split(":", 1)[1] if g.startswith(("azure:", "edge:")) else g
        if g != cur:
            if cur is not None: ra.append("</voice>")
            ra.append('<voice name="%s">' % g)
            ra.append('<mstts:silence type="Sentenceboundary-exact" value="%dms"/>' % NEN_MS)
            cur = g
        ten = "c%d" % dem
        if dem:                                   # câu đầu không cần nghỉ trước
            _b = _break_thuc(nghi_truoc(ghi))
            if _b:
                ra.append('<break time="%dms"/>' % _b)
        dem += 1
        moc.append(ten)
        than = _esc(re.sub(r"[\[\]]", "", hz))
        if rate:
            than = '<prosody rate="%s">%s</prosody>' % (rate, than)
        ra.append('<bookmark mark="%s"/>%s' % (ten, than))
    if cur is not None: ra.append("</voice>")
    ra.append("</speak>")
    return "".join(ra), moc


def sinh_lien_mach(ssml, moc_ten, key, region, ra_mp3, lan_toi_da=3):
    """Một lần gọi -> một audio liền mạch + timeline.
    Trả về (thoi_luong, {ten_moc: giay}). Ném lỗi nếu 3 lần đều bị cắt."""
    import azure.cognitiveservices.speech as sp
    loi_cuoi = ""
    for lan in range(lan_toi_da):
        cf = sp.SpeechConfig(subscription=key, region=region)
        cf.set_speech_synthesis_output_format(
            sp.SpeechSynthesisOutputFormat.Audio24Khz48KBitRateMonoMp3)
        syn = sp.SpeechSynthesizer(speech_config=cf,
              audio_config=sp.audio.AudioOutputConfig(filename=ra_mp3))
        bm, wb = {}, []
        syn.bookmark_reached.connect(lambda e: bm.__setitem__(e.text, e.audio_offset / 1e7))
        syn.synthesis_word_boundary.connect(
            lambda e: wb.append((e.audio_offset / 1e7, e.text_offset)))
        r = syn.speak_ssml_async(ssml).get()
        if r.reason != sp.ResultReason.SynthesizingAudioCompleted:
            loi_cuoi = getattr(getattr(r, "cancellation_details", None), "error_details", "") or str(r.reason)
            time.sleep(1.2); continue
        dur = r.audio_duration.total_seconds()
        if len(bm) >= len(moc_ten):                      # giong co bookmark -> chuan nhat
            return dur, {k: bm[k] for k in moc_ten if k in bm}
        # lui ve WordBoundary: text_offset danh chi so vao CHUOI SSML
        if wb:
            vt = {t: ssml.index('<bookmark mark="%s"/>' % t) for t in moc_ten}
            het = max(o for _, o in wb)
            if het >= vt[moc_ten[-1]]:                   # chot chan: khong bi cat giua chung
                ra = {}
                for t in moc_ten:
                    sau = [g for g, o in wb if o >= vt[t]]
                    ra[t] = sau[0] if sau else dur
                return dur, ra
            loi_cuoi = "bản bị cắt (%d sự kiện, không tới câu cuối)" % len(wb)
        time.sleep(1.2)
    raise RuntimeError("Azure không trả về bản đầy đủ sau %d lần: %s" % (lan_toi_da, loi_cuoi[:120]))


def khoang(moc, ten, tong):
    """{ten: giay} -> [(bat_dau, ket_thuc)] theo đúng thứ tự câu."""
    t = [moc[k] for k in ten]
    return [(t[i], t[i + 1] if i + 1 < len(t) else tong) for i in range(len(t))]
