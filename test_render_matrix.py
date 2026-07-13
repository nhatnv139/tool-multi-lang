# -*- coding: utf-8 -*-
"""Autotest ma tran render podcast v2: moi bien the x mode x size px x edge case.
   Chi test RENDER (khong TTS) -> nhanh, quet duoc nhieu case."""
import sys, os, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
import style_podcast, style_pastel

OUTD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ref", "matrix")
os.makedirs(OUTD, exist_ok=True)
BG = "/Users/nhatnv/project/tool-multi-lang/uploads/bg_1782793711602.png"

SEGS = {
    "normal":   {"type": "sentence", "hanzi": "学语言，最重要的是每天都听一点。",
                 "viet": "Học ngôn ngữ, quan trọng nhất là mỗi ngày đều nghe một chút.",
                 "_sp": "小雨", "_idx": 3, "_n": 9},
    "long":     {"type": "sentence", "hanzi": "如果你每天早上坐地铁的时候都能听十分钟中文播客，你的听力一定会越来越好。",
                 "viet": "Nếu mỗi sáng ngồi tàu điện bạn đều nghe được mười phút podcast tiếng Trung thì khả năng nghe của bạn chắc chắn sẽ ngày càng tốt.",
                 "_idx": 4, "_n": 9},
    "short":    {"type": "vocab", "hanzi": "你好", "viet": "Xin chào", "_idx": 1, "_n": 9},
    "hideviet": {"type": "sentence", "hanzi": "我们明天见。", "viet": "Hẹn mai gặp lại.",
                 "_hide_viet": True, "_idx": 5, "_n": 9},
    "noviet":   {"type": "practice_a", "hanzi": "谢谢", "viet": "", "_idx": 6, "_n": 9},
    "latin_sp": {"type": "sentence", "hanzi": "OK，没问题！", "viet": "OK, không vấn đề!",
                 "_sp": "Host", "_idx": 7, "_n": 9},
    "no_hanzi": {"type": "sentence", "hanzi": "Bonjour!", "viet": "Xin chào (tiếng Pháp)",
                 "_idx": 8, "_n": 9},
}
PX_CASES = {
    "auto":  {},
    "tiny":  {"zh_px": 30, "py_px": 20, "vi_px": 20},     # case gay bug 'ws'
    "huge":  {"zh_px": 200, "py_px": 90, "vi_px": 90},
    "mixed": {"zh_px": 120, "py_px": None, "vi_px": 40},
}
VARIANTS = list(style_podcast.VARIANTS.keys()) + ["classic"]
MODES = ["", "ruby", "line"]

def base_ctx(v, bg=True):
    return {"podcast_layout": True, "podcast_variant": v, "channel": "Lạc Học Đường",
            "id": 1, "title": "Mỗi ngày nghe một chút", "hsk": "HSK2",
            "seal_text": "乐学", "bg_image": (BG if bg else ""), "tone_colors": True,
            "panel_alpha": 150, "_speaker_colors": {"小雨": (40, 96, 196), "Host": (1, 2, 3)}}

fails = []
n = 0
# 1) MA TRAN CHINH: variant x pinyin_mode (seg normal)
for v in VARIANTS:
    for m in MODES:
        n += 1
        ctx = base_ctx(v); ctx["pinyin_mode"] = m
        try:
            style_pastel.render_slide(dict(SEGS["normal"]), ctx, f"{OUTD}/m_{v}_{m or 'auto'}.png")
        except Exception as e:
            fails.append((f"variant={v} mode={m}", e)); traceback.print_exc()

# 2) SIZE PX x vai variant dai dien (ca panel & free & classic)
for v in ["inkwash", "daily", "night", "classic"]:
    for pname, px in PX_CASES.items():
        for m in ["", "ruby", "line"]:
            n += 1
            ctx = base_ctx(v); ctx.update(px); ctx["pinyin_mode"] = m
            try:
                style_pastel.render_slide(dict(SEGS["normal"]), ctx, f"{OUTD}/px_{v}_{pname}_{m or 'auto'}.png")
            except Exception as e:
                fails.append((f"px variant={v} {pname} mode={m}", e)); traceback.print_exc()

# 3) EDGE SEGMENTS tren moi variant (mode auto)
for v in VARIANTS:
    for sname, seg in SEGS.items():
        n += 1
        try:
            style_pastel.render_slide(dict(seg), base_ctx(v), f"{OUTD}/s_{v}_{sname}.png")
        except Exception as e:
            fails.append((f"seg variant={v} seg={sname}", e)); traceback.print_exc()

# 4) SECTION + khong bg + alpha 0 + seal khong CJK + tat frame/progress
extra = [
    ("section",    lambda v: style_pastel.render_slide({"type": "section", "label": "HỘI THOẠI"},
                                                       base_ctx(v), f"{OUTD}/x_sec_{v}.png")),
    ("nobg",       lambda v: style_pastel.render_slide(dict(SEGS["normal"]), base_ctx(v, bg=False),
                                                       f"{OUTD}/x_nobg_{v}.png")),
]
for v in VARIANTS:
    for xname, fn in extra:
        n += 1
        try:
            fn(v)
        except Exception as e:
            fails.append((f"{xname} variant={v}", e)); traceback.print_exc()

for v in ["inkwash", "daily"]:
    for patch, name in [({"panel_alpha": 0}, "alpha0"),
                        ({"seal_text": "", "channel": "Hoc Tieng Trung"}, "sealfallback"),
                        ({"podcast_frame": False}, "noframe"),
                        ({"show_progress": False}, "noprog"),
                        ({"tone_colors": False}, "notone"),
                        ({"pinyin_top": False}, "pybottom"),
                        ({"bottom_bar": True, "bar_left": "Học 中文 mỗi ngày",
                          "bar_badge": "PODCAST", "bar_bg": "#14161e"}, "botbar"),
                        ({"bottom_bar": True, "bar_left": "", "bar_badge": "",
                          "bar_bg": ""}, "botbar_empty"),
                        ({"zh_color": "#8b1a1a", "py_color": "#7a4fc0",
                          "vi_color": "#d2691e", "panel_color": "#fff3d6"}, "colors"),
                        ({"zh_color": "xx", "py_color": "#zz9", "panel_color": 5}, "badcolors")]:
        n += 1
        ctx = base_ctx(v); ctx.update(patch)
        try:
            style_pastel.render_slide(dict(SEGS["normal"]), ctx, f"{OUTD}/x_{name}_{v}.png")
        except Exception as e:
            fails.append((f"{name} variant={v}", e)); traceback.print_exc()

# 5) waveform conf cho moi variant + moi lua chon
import generate
for v in VARIANTS:
    for wf in ["auto", "top", "mid", "off", ""]:
        n += 1
        try:
            r = generate._waveform_conf({"podcast_layout": True, "podcast_variant": v, "waveform": wf})
            assert r is None or (r[0] in ("top", "mid") and r[1].startswith("0x")), r
        except Exception as e:
            fails.append((f"waveconf variant={v} wf={wf}", e))
n += 1
try:
    assert generate._waveform_conf({"podcast_layout": False, "waveform": "top"}) is None
except Exception as e:
    fails.append(("waveconf no-podcast", e))

print(f"\n===== {n} case, {len(fails)} FAIL =====")
for name, e in fails:
    print("FAIL:", name, "->", type(e).__name__, e)
sys.exit(1 if fails else 0)
