# -*- coding: utf-8 -*-
"""Form nội dung chuẩn SEO cho từng nền tảng MXH, dựng từ seo_data (job["seo"]).
   Tách bài đăng thành các TRƯỜNG: hook (tiêu đề giật), body (nội dung),
   cta (kêu gọi), hashtags, link — rồi RÁP lại theo chuẩn từng nền tảng.
   Tái dùng dữ liệu seo.py, KHÔNG gọi lại seo.generate. Không dùng AI.
"""
import re

import seo

# giới hạn & cấu hình từng nền tảng (SEO/organic best-practice)
LIMITS = {
    "facebook":  {"max": 2000, "tags": 5,  "allow_link": True},
    "x":         {"max": 270,  "tags": 2,  "allow_link": True},   # chừa ~23 ký tự cho link
    "tiktok":    {"max": 2200, "tags": 6,  "allow_link": False},
    "instagram": {"max": 2200, "tags": 12, "allow_link": False},  # IG ≤30 hashtag
}
DEFAULT_CTA = "🔔 Đăng ký kênh để mỗi ngày có một bài nghe mới!"


def _chapters_bullets(seo_data, limit=4):
    # 'chapters' co HAI dang: bai hoc tra list dict {label:...}, con phim (_film_seo)
    # tra MOT CHUOI "0:00 Mo dau\n1:23 Canh 2...". Chi doc dang dict thi trang dang
    # cua phim no 500 (AttributeError: 'str' object has no attribute 'get').
    ch = seo_data.get("chapters") or []
    if isinstance(ch, str):
        rows = [re.sub(r"^\s*\d+:\d{2}(?::\d{2})?\s*", "", ln).strip()
                for ln in ch.splitlines()]
    else:
        rows = [(c.get("label") if isinstance(c, dict) else str(c) or "").strip()
                for c in ch]
    return "\n".join(f"• {r}" for r in [r for r in rows if r][:limit])


def _truncate(text, n):
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def fields(seo_data, platform, lang="zh", yt_url=""):
    """Trả về các trường soạn bài (để render form). Giá trị là GỢI Ý — user sửa được."""
    seo_data = seo_data or {}
    cfg = LIMITS.get(platform, LIMITS["facebook"])
    title = (seo_data.get("title") or "").strip()
    if lang == "zh":
        han, viet = seo.split_title(seo_data.get("title", ""))
        hook = (f"🎧 {han} — {viet}".strip(" —")) or f"🎧 {title}"
    else:
        hook = f"🎧 {title}"

    bullets = _chapters_bullets(seo_data)
    body = ("Nội dung trong tập:\n" + bullets) if bullets else \
           "Video mới đã lên sóng — bật phụ đề để nghe hiểu theo nhé!"

    all_tags = list(dict.fromkeys(seo_data.get("hashtags") or []))   # khử trùng, giữ thứ tự
    sugg = all_tags[: cfg["tags"]]
    link = yt_url if cfg["allow_link"] else ""

    return {
        "hook": hook,
        "body": body,
        "cta": DEFAULT_CTA,
        "hashtags": sugg,            # đã chọn sẵn theo số tag khuyến nghị của nền tảng
        "all_hashtags": all_tags,    # pool đầy đủ để gợi ý click thêm
        "link": link,
        "allow_link": cfg["allow_link"],
        "limit": cfg["max"],
        "tag_limit": cfg["tags"],
    }


def assemble(f, limit=None):
    """Ráp các trường thành 1 bài đăng hoàn chỉnh chuẩn SEO."""
    f = f or {}
    parts = []
    for k in ("hook", "body", "cta"):
        v = (f.get(k) or "").strip()
        if v:
            parts.append(v)
    link = (f.get("link") or "").strip()
    if link:
        parts.append(f"▶️ Xem full: {link}")
    tags = f.get("hashtags") or []
    if isinstance(tags, str):
        tags = tags.split()
    if tags:
        parts.append(" ".join(t if t.startswith("#") else "#" + t for t in tags))
    text = "\n\n".join(parts)
    return _truncate(text, limit) if limit else text


def caption(seo_data, platform, lang="zh", yt_url="", **_ignore):
    """Bài đăng template hoàn chỉnh (dùng cho đăng nhiều kênh / auto)."""
    cfg = LIMITS.get(platform, LIMITS["facebook"])
    return assemble(fields(seo_data, platform, lang=lang, yt_url=yt_url), limit=cfg["max"])


def all_fields(seo_data, lang="zh", yt_url="",
               platforms=("facebook", "x", "tiktok", "instagram")):
    return {p: fields(seo_data, p, lang=lang, yt_url=yt_url) for p in platforms}
