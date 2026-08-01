# -*- coding: utf-8 -*-
"""make_film_thumb.py — Thumbnail kieu kenh ke chuyen: canh cao trao + chu CAM to vien den.

Dung:
    python make_film_thumb.py data/film_nguoi_biet_du_la_phuc.json
    python make_film_thumb.py data/film_x.json --text "TRÚNG SỐ ĐỘC ĐẮC" --sub "Người Biết Đủ Là Phúc"
"""
import os, sys, json, argparse

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import film

# Canh cao trao mac dinh (neu khong truyen --prompt): dung character sheet cua truyen
DEFAULT_PROMPT = (
    "Dramatic scene: Nhan, a thin kind Vietnamese man in his forties with short black hair, "
    "sun-tanned angular face, patched brown ba ba shirt, holding two glowing golden lottery tickets "
    "with shocked wide eyes at night, villagers crowding excitedly behind him, "
    "Phat, a plump arrogant Vietnamese merchant with slicked-back hair, thin mustache, "
    "shiny indigo silk shirt, watching with greedy jealous eyes from the side"
)


def _font(size, bold=True):
    """Font he thong ho tro tieng Viet, uu tien net day cho thumbnail."""
    cands = ["arialbd.ttf", "ariblk.ttf", "tahomabd.ttf", "arial.ttf"] if bold else ["arial.ttf"]
    for name in cands:
        p = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", name)
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _fit_font(draw, text, max_w, start=170, floor=70):
    """Chon co chu lon nhat de text vua chieu ngang."""
    size = start
    while size > floor:
        f = _font(size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 6
    return _font(floor)


def _outline_text(draw, xy, text, font, fill, outline, width):
    x, y = xy
    for dx in range(-width, width + 1, max(1, width // 3)):
        for dy in range(-width, width + 1, max(1, width // 3)):
            if dx or dy:
                draw.text((x + dx, y + dy), text, font=font, fill=outline)
    draw.text((x, y), text, font=font, fill=fill)


def make_thumb(json_path, text=None, sub=None, prompt=None, out=None, seed=777):
    doc = json.load(open(json_path, encoding="utf-8"))
    style = doc.get("style", "")
    p = (prompt or DEFAULT_PROMPT).strip().rstrip(",")
    if style:
        p = f"{p}, {style}"

    print("Sinh anh nen thumbnail...")
    bg = film.ai_scene_bg(p, seed=seed, w=1280, h=720)
    im = Image.open(bg).convert("RGB").resize((1280, 720), Image.LANCZOS)

    # lam toi 1/3 duoi de chu noi
    grad = Image.new("L", (1, 720))
    for y in range(720):
        grad.putpixel((0, y), int(min(160, max(0, (y - 380) / 340 * 160))))
    shadow = Image.new("RGB", (1280, 720), (0, 0, 0))
    im = Image.composite(shadow, im, grad.resize((1280, 720)))

    d = ImageDraw.Draw(im)
    main = (text or "TRÚNG SỐ ĐỘC ĐẮC").upper()
    f_main = _fit_font(d, main, 1180)
    h_main = f_main.size
    y_main = 720 - h_main - 55

    if sub:
        f_sub = _fit_font(d, sub, 1000, start=64, floor=40)
        y_sub = y_main - f_sub.size - 18
        _outline_text(d, (52, y_sub), sub, f_sub, (255, 255, 255), (0, 0, 0), 6)

    # chu chinh 2 mau kieu kenh mau: nua dau CAM, nua sau TRANG
    words = main.split()
    cut = max(1, len(words) // 2)
    part1, part2 = " ".join(words[:cut]) + " ", " ".join(words[cut:])
    x = 50
    _outline_text(d, (x, y_main), part1, f_main, (255, 122, 24), (20, 10, 5), 10)
    x2 = x + d.textlength(part1, font=f_main)
    _outline_text(d, (x2, y_main), part2, f_main, (255, 255, 255), (20, 10, 5), 10)

    out = out or os.path.join(_HERE, "output",
                              "thumb_" + os.path.splitext(os.path.basename(json_path))[0] + ".jpg")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    im = im.filter(ImageFilter.SHARPEN)
    im.save(out, quality=92)
    print("XONG ->", out)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("json")
    ap.add_argument("--text", default=None, help="chu to (mac dinh: TRÚNG SỐ ĐỘC ĐẮC)")
    ap.add_argument("--sub", default=None, help="dong phu nho phia tren")
    ap.add_argument("--prompt", default=None, help="mo ta canh nen (mac dinh: canh cao trao co san)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--seed", type=int, default=777)
    a = ap.parse_args()
    make_thumb(a.json, text=a.text, sub=a.sub, prompt=a.prompt, out=a.out, seed=a.seed)
