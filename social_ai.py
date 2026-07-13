# -*- coding: utf-8 -*-
"""Sinh nội dung MXH bằng Claude (Anthropic) — TÁI CHẾ nội dung bài học thành bài đăng.

   Video YouTube = hội thoại; bài Facebook = từ vựng + cấu trúc ngữ pháp + link...
   => mỗi kênh × nền tảng có 1 "content profile" (kiểu nội dung) riêng.

   - API key đọc từ social_secrets/anthropic.json {api_key, model} (gitignore).
   - Prompt caching cho system prompt (ổn định theo content_style) -> rẻ khi đăng nhiều bài cùng kiểu.
"""
import os, json

ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(ROOT, "social_secrets", "anthropic.json")
DEFAULT_MODEL = "claude-opus-4-8"

# Các "kiểu nội dung" (content profile) cho bài đăng MXH
CONTENT_STYLES = {
    "video_promo":  "Giới thiệu video + link (không dùng AI — dùng template)",
    "vocab_grammar": "Từ vựng + cấu trúc ngữ pháp rút từ bài học (AI)",
    "summary_tips":  "Tóm tắt bài học + mẹo học (AI)",
    "custom":        "Prompt tự do của bạn (AI)",
}
AI_STYLES = ("vocab_grammar", "summary_tips", "custom")

# Hướng dẫn riêng từng kiểu (system prompt — ổn định -> được cache)
_STYLE_PROMPTS = {
    "vocab_grammar": (
        "Nhiệm vụ: từ transcript một bài học/hội thoại tiếng Trung, soạn một bài đăng "
        "Facebook dạng 'TỪ VỰNG + NGỮ PHÁP' cho người Việt học tiếng Trung.\n"
        "Cấu trúc bài đăng:\n"
        "1) 1-2 câu hook nêu chủ đề bài học.\n"
        "2) 📚 TỪ VỰNG TRỌNG TÂM: 5-8 từ, mỗi dòng: 汉字 (pinyin) — nghĩa Việt.\n"
        "3) 🔑 CẤU TRÚC NGỮ PHÁP: 2-3 mẫu câu/điểm ngữ pháp xuất hiện trong bài, "
        "mỗi mẫu có 1 ví dụ ngắn (汉字 + pinyin + nghĩa).\n"
        "4) CTA mời xem video đầy đủ + đăng ký kênh.\n"
        "Giọng văn thân thiện, dùng emoji vừa phải, KHÔNG bịa từ/ngữ pháp không có trong bài."
    ),
    "summary_tips": (
        "Nhiệm vụ: từ transcript bài học tiếng Trung, soạn bài đăng Facebook gồm: "
        "1) tóm tắt nội dung bài học 2-3 câu, 2) 3 mẹo học/nghe hiểu rút ra từ bài, "
        "3) CTA xem video + đăng ký kênh. Thân thiện, emoji vừa phải, tiếng Việt."
    ),
}

_BASE_SYSTEM = (
    "Bạn là người viết nội dung mạng xã hội cho kênh học tiếng Trung dành cho người Việt. "
    "Luôn trả lời bằng tiếng Việt (giữ nguyên 汉字 và pinyin khi cần). "
    "CHỈ xuất ra nội dung bài đăng cuối cùng — không thêm lời dẫn, không giải thích, "
    "không markdown thừa. Bám sát transcript, không bịa thông tin."
)


def is_configured():
    if not os.path.exists(CONFIG):
        return False
    try:
        return bool(json.load(open(CONFIG, encoding="utf-8")).get("api_key"))
    except Exception:
        return False


def _cfg():
    if os.path.exists(CONFIG):
        return json.load(open(CONFIG, encoding="utf-8"))
    return {}


def setup_hint():
    return ('Đặt <code>social_secrets/anthropic.json</code> dạng '
            '<code>{"api_key": "sk-ant-...", "model": "claude-opus-4-8"}</code> để bật sinh nội dung bằng AI.')


def _system_for(style, custom_prompt, platform, limit):
    style_block = (custom_prompt.strip() if style == "custom" and custom_prompt.strip()
                   else _STYLE_PROMPTS.get(style, _STYLE_PROMPTS["vocab_grammar"]))
    plat_note = (f"\nNền tảng: {platform}. Độ dài tối đa ~{limit} ký tự "
                 "(ưu tiên ngắn gọn, xuống dòng rõ ràng).")
    return _BASE_SYSTEM + "\n\n" + style_block + plat_note


def generate(transcript, platform, style="vocab_grammar", custom_prompt="",
             yt_url="", channel_name="", lang="zh", limit=2000, hashtags=None):
    """Gọi Claude sinh caption. Trả về chuỗi caption, hoặc raise nếu lỗi."""
    import anthropic
    cfg = _cfg()
    api_key = cfg.get("api_key")
    if not api_key:
        raise RuntimeError("Chưa cấu hình Anthropic API key.")
    model = cfg.get("model") or DEFAULT_MODEL
    client = anthropic.Anthropic(api_key=api_key)

    system = _system_for(style, custom_prompt, platform, limit)
    tags = " ".join(hashtags or [])
    user = (f"Tên kênh: {channel_name}\n"
            f"Link video: {yt_url or '(đính kèm sau)'}\n"
            f"Hashtag gợi ý (chèn ở cuối nếu hợp): {tags}\n\n"
            f"TRANSCRIPT BÀI HỌC:\n{(transcript or '').strip()[:8000]}\n\n"
            f"Hãy soạn bài đăng theo đúng yêu cầu. Kết thúc bằng link video nếu có.")

    resp = client.messages.create(
        model=model,
        max_tokens=1500,
        thinking={"type": "disabled"},   # caption ngắn, không cần suy luận dài
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    if yt_url and yt_url not in text:
        text += f"\n▶️ {yt_url}"
    return text
