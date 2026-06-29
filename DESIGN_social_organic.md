# Thiết kế: Đăng video YouTube → tự động lan toả sang kênh mạng xã hội (organic marketing đa nền tảng, đa ngôn ngữ)

Tài liệu này tổng hợp toàn bộ khảo sát code, nghiên cứu API và hai bản thiết kế thành một bản đặc tả thực thi được ngay. Mọi đường dẫn là tuyệt đối, mọi chữ ký hàm bám sát code thật (`youtube_upload.py`, `seo.py`, `youtube.html`, `app.py`).

---

## 1. Tổng quan & mục tiêu tính năng

### 1.1 Bối cảnh
Tool Flask hiện sinh video học ngôn ngữ → tạo SEO → upload YouTube. Đã có sẵn:
- Multi-channel YouTube OAuth (token lưu `yt_tokens/<channel_id>.json` + `.name`).
- Trang 2 (`templates/youtube.html`) cho phép chọn 1 kênh YT trong nhiều kênh đã kết nối để đăng.

### 1.2 Mục tiêu mới
1. Khi đăng lên YouTube, chọn 1 kênh YT (select đã có).
2. **Mỗi kênh YouTube có riêng một bộ kênh mạng xã hội** (Facebook, X/Twitter, TikTok, Instagram) chỉ phục vụ kênh YT đó → chạy organic marketing.
3. Khi đăng video YT xong, **tự động lan toả bài sang các kênh MXH của đúng kênh YT đó**, với **nội dung chuẩn SEO theo ngôn ngữ / chủ đề / hướng nội dung** của video.

### 1.3 Nguyên tắc thiết kế cốt lõi
- **Khóa định danh tự nhiên = `yt_channel_id`** (vd `UCb6YtnCkhEG8wUMAtd8lrnw`). MXH map 1-1 theo kênh YT vì `list_channels()` đã key theo `cid`.
- **Mỗi platform = 1 adapter** cùng contract `connect / list / _creds_for / post` như `youtube_upload.py`, nhưng token schema tự do per-platform.
- **Native upload thắng organic reach** (research FB/IG): mặc định upload video native, không đăng link YouTube (link bị giảm 70-80% reach). Có cờ `mode: "native" | "link"` để fallback.
- **Đăng MXH là async + best-effort**: không bao giờ làm fail luồng YT. Mỗi platform có status/error/retry riêng.
- **Đăng nền (background thread) + polling tiến trình** vì IG/TikTok/FB-native là async (phải poll status).

---

## 2. Hiện trạng code (tái sử dụng được gì)

### 2.1 Từ `youtube_upload.py` — pattern token đa kênh (tái dùng nguyên xi)
- Thư mục `yt_tokens/`, mỗi kênh = 2 file cùng tên `<channel_id>`:
  - `<channel_id>.json` — credentials OAuth (`creds.to_json()`).
  - `<channel_id>.name` — text thuần chứa tên kênh (liệt kê nhanh không gọi API).
- `channel_id` lấy từ `channels().list(mine=True)` → khóa định danh tự nhiên.
- Liệt kê = `glob("*.json")`, strip ext, đọc kèm `.name`.
- Auto-refresh khi hết hạn rồi ghi đè file json.
- `client_secret.json` ở ROOT dùng chung; `is_configured()` chỉ kiểm tra file này tồn tại.

**Chữ ký các hàm hiện có:**

| Hàm | Chữ ký | Trả về |
|---|---|---|
| `is_configured` | `()` | bool |
| `connect` | `()` | `{id, title}` (OAuth blocking, ghi 2 file) |
| `list_channels` | `()` | `[{id, title}]` |
| `_creds_for` | `(channel_id)` | `Credentials` (auto-refresh) |
| `upload` | `(channel_id, video_path, title, description, tags, privacy, category)` | `{id, url}` |
| `upload_caption` | `(channel_id, video_id, srt_text, lang, name)` | caption_id / None |
| `post_comment` | `(channel_id, video_id, text)` | comment_id / None |
| `set_thumbnail` | `(channel_id, video_id, image_path)` | True / None |

→ **Pattern này áp dụng 100% cho 4 nền tảng MXH** (chỉ khác refresh-flow và token schema per-platform).

### 2.2 Từ `seo.py` — nguồn caption (tái dùng dữ liệu thô + helper thuần)
`seo.generate(ctx)` đã trả về dict đầy đủ, lưu trong `job["seo"]`:
- `title` / `titles` (4 biến thể), `description`, `tags` (≤20), `hashtags` (5), `chapters`, `transcript`, `pinned_comment`, `srt_hanzi/srt_pinyin/srt_viet`, `thumbnail_text`, `total_dur`, `channel`.

**Tái dùng trực tiếp cho caption MXH** (không cần gọi lại `generate`):
- `job["seo"]` đã sinh sẵn → nguồn caption.
- `split_title()` (seo.py:38) → tách Hán + nghĩa Việt cho hook.
- `build_chapters()` / `chapters` → bullet tóm tắt cho FB/IG.
- `pinned_comment` (từ vựng jieba) → trích "từ trọng tâm" → hashtag từ vựng.
- `hashtags` → base hashtag, cắt theo platform.
- Helper thuần ngôn ngữ-độc lập: `mmss`, `_srt_time`, `build_srt`.

**Phần hardcode tiếng Trung/HSK cần tách** (lõi zh-specific): `pinyin_of`, `split_title`, jieba, `_SCENE_KEYWORDS`, `DEFAULT_TAGS`, template `titles/description/hashtags`. Các phần này **chỉ kích hoạt khi `lang=="zh"`**; ngôn ngữ khác bỏ pinyin, dùng `title` thẳng.

### 2.3 Từ `youtube.html` + `app.py` — UI & route pattern
- Card pattern `.card`, toggle `.switch` (mẫu `capToggle` / `setThumb`).
- Fetch pattern của `loadChannels()` (`youtube.html:162-178`).
- `connectChannel()` mở tab OAuth + `setTimeout(loadChannels, 4000)`.
- `doUpload()` POST JSON body → render kết quả `.ok`/`.err`.
- Route mẫu: `GET /yt/channels`, `GET /yt/connect` (blocking OAuth), `POST /yt/upload` (luồng upload + captions + thumbnail + comment, mỗi bước `try/except` độc lập).

**Điểm cần lưu ý:** `select#channel` (`youtube.html:72`) hiện **không có `onchange`** — bắt buộc thêm để vùng MXH cập nhật theo kênh YT đang chọn.

---

## 3. Làm rõ yêu cầu & xử lý mâu thuẫn "3 vs 4 nền tảng"

Người dùng nói "3 kênh MXH" nhưng liệt kê 4 (FB, X, TikTok, IG).

**Quyết định: hỗ trợ cả 4, bật/tắt độc lập per-channel qua `enabled`.**

- UI hiện **4 dòng** (FB, X, TikTok, IG), mỗi dòng 1 toggle bật/tắt → người dùng tự quyết 3 hay 4. Không hardcode con số.
- `fanout()` chỉ đăng platform `enabled && connected`. Tắt 1 nền tảng = bỏ qua hoàn toàn, không lỗi.
- Toggle lưu persistent per kênh YT (kênh A bật IG, kênh B tắt IG được).
- **Default đề xuất: FB ✅, X ✅, IG ✅, TikTok ❌** — vì TikTok unaudited bị ép `SELF_ONLY` (private), không phục vụ organic public. Như vậy "mặc định 3 nền tảng hoạt động" khớp lời người dùng nói "3 kênh", mà vẫn để sẵn nền tảng thứ 4 khi qua audit.

---

## 4. Kiến trúc tổng thể (sơ đồ luồng)

```
[Trang 1: tạo video] ──POST /generate──► job_id ──GET /progress──► done
        │  bấm "→ Đăng YouTube" (/youtube/<job_id>)
        ▼
[Trang 2 mở]
   loadChannels() ──GET /yt/channels──► đổ select kênh YT
   select.onchange (auto-fire kênh đầu) ──► loadSocial(cid)
        │
        ▼
   loadSocial(cid) ──GET /social/links/<cid>──► render 4 dòng platform (enabled/connected/warn)
        └─ song song ──GET /social/caption/<job_id>──► đổ caption 4 nền tảng vào textarea
        │
        │ (nếu chưa kết nối) bấm [Kết nối]
        ▼
   ──window.open('/social/connect/<cid>/<platform>')──► OAuth tab (blocking, ghi token)
        setTimeout(loadSocial(cid), 4000) → dòng chuyển ● đã kết nối, toggle bật được
        │
        │ user bật/tắt platform + sửa caption + chọn native/link
        ▼
[Bấm "🚀 Đăng YouTube + lan toả MXH"]  doUpload():
        │
   (a) POST /yt/upload ──► đợi {url, id}   [YouTube PHẢI xong TRƯỚC]
        │   (vì caption mọi nền tảng cần youtu.be/<id> thật; FB/IG native cần file đã có)
        │
   (b) POST /social/post ──► {task_id}  (đăng nền, async)
        │
        ▼
┌──────────────── BACKEND: social_orchestrator.fanout ────────────────┐
│ - đọc index.json → lọc platform enabled && connected && override     │
│ - mỗi platform CHẠY SONG SONG (ThreadPoolExecutor max_workers=4):     │
│     a. caption = social_seo.caption(job["seo"], platform, lang, url)  │
│     b. media = native(video_path) | link(yt_url) theo mode            │
│     c. adapter.post(cid, caption, media, opts)                        │
│     d. retry x2 (backoff 5s/15s) nếu lỗi tạm; permanent → không retry │
│     e. async platform (TikTok/IG) poll status tới DONE/FAILED         │
│ - fault isolation: 1 nền tảng lỗi KHÔNG kéo nền khác                  │
└──────────────────────────────────────────────────────────────────────┘
        │
        ▼
   pollSocial(task_id) ──GET /social/status/<task_id>──► cập nhật 4 dòng mỗi 2s
        ✅ url / ❌ lỗi+gợi ý / ⏳ đang đăng / ⛔ đã tắt  → done:true
```

**Per-platform state machine** (mỗi nền tảng độc lập):
```
PENDING ──post()──► RUNNING ──┬─ ok ───────────────► DONE {post_url}
                              ├─ async(TikTok/IG) ──► poll status ──► DONE | FAILED
                              └─ lỗi tạm (429/5xx) ─► RETRY (x2) ───► DONE | FAILED
lỗi vĩnh viễn (auth/permission/audit) ──────────────► FAILED {error, hint} (KHÔNG retry)
```

---

## 5. Data model & cách lưu mapping 1 YT → N MXH

### 5.1 Cấu trúc thư mục (song song `yt_tokens/`)

```
tool-multi-lang/
├── client_secret.json                      # YT (đã có) — dùng chung
├── yt_tokens/                               # YT (đã có)
│   ├── <yt_channel_id>.json
│   └── <yt_channel_id>.name
├── social_secrets/                          # MỚI: app credentials per-platform (KHÔNG per-channel)
│   ├── facebook.json                        # {app_id, app_secret} (dùng chung cho IG)
│   ├── x.json                               # {api_key, api_secret}  (OAuth1 app keys)
│   └── tiktok.json                          # {client_key, client_secret}
└── social_tokens/                           # MỚI: token + mapping per YT channel
    └── <yt_channel_id>/
        ├── index.json                       # trạng thái 4 nền tảng (nguồn sự thật cho UI)
        ├── facebook.json                    # page token + page_id
        ├── x.json                           # oauth1 access token/secret
        ├── tiktok.json                      # open_id + access/refresh token + expiry
        └── instagram.json                   # ig_user_id + long-lived token
```

> Lý do tách thư mục per-channel thay vì 1 file phẳng: token mỗi platform có schema/secret riêng, refresh độc lập, dễ xóa/cấp lại từng cái. `index.json` là lớp tóm tắt cho UI (khỏi đọc 4 file).

### 5.2 `index.json` — schema (nguồn sự thật cho UI)

```json
{
  "yt_channel_id": "UCb6YtnCkhEG8wUMAtd8lrnw",
  "yt_channel_name": "Tố Nhật",
  "lang": "zh",
  "topic_hint": "HSK1 luyện nghe",
  "updated_at": "2026-06-29T10:00:00Z",
  "platforms": {
    "facebook":  { "enabled": true,  "connected": true,  "name": "Page Học Tiếng Trung", "account_id": "1029384756", "mode": "native" },
    "x":         { "enabled": true,  "connected": true,  "name": "@hoctiengtrung",         "account_id": "1552...",     "mode": "link"   },
    "tiktok":    { "enabled": false, "connected": false, "name": "",                       "account_id": "",            "mode": "native", "note": "unaudited -> chỉ đăng private" },
    "instagram": { "enabled": true,  "connected": true,  "name": "@hoctiengtrung_official","account_id": "178...",      "mode": "native" }
  }
}
```

- `enabled` = cờ bật/tắt (giải quyết "3 vs 4"). `connected` = đã có token hợp lệ chưa.
- `mode`: `"native"` (upload file) hoặc `"link"` (đăng link YT — chỉ FB/X dùng).
- `lang` / `topic_hint`: lấy từ `job["seo"]`/`ctx` lúc generate, dùng sinh caption đúng ngôn ngữ; kế thừa từ kênh, override per-channel được.

### 5.3 Token schema per-platform

**facebook.json** (Page token never-expiring qua long-lived user token):
```json
{
  "page_id": "1029384756",
  "page_name": "Page Học Tiếng Trung",
  "page_access_token": "EAAB...long_lived_never_expiring",
  "user_token_expiry": "2026-08-28T00:00:00Z",
  "scopes": ["pages_manage_posts","pages_read_engagement","pages_show_list","publish_video"]
}
```

**x.json** (OAuth 1.0a User Context — đơn giản nhất cho self-post, token không hết hạn):
```json
{
  "user_id": "1552...", "screen_name": "hoctiengtrung",
  "api_key": "...", "api_secret": "...",
  "access_token": "...", "access_token_secret": "...",
  "premium": false
}
```

**tiktok.json** (OAuth2, access 24h + refresh):
```json
{
  "open_id": "_000...", "display_name": "Học Tiếng Trung",
  "access_token": "act....", "refresh_token": "rft....",
  "expires_at": "2026-06-30T10:00:00Z", "audited": false
}
```

**instagram.json** (IG Business + Page, long-lived 60 ngày):
```json
{
  "ig_user_id": "178...", "username": "hoctiengtrung_official",
  "linked_page_id": "1029384756",
  "access_token": "EAAB...long_lived", "expires_at": "2026-08-28T00:00:00Z"
}
```

### 5.4 Bảo mật & refresh token

| Platform | Loại token | Refresh | Hết hạn | Hành động khi gần hết hạn |
|---|---|---|---|---|
| Facebook | Page token long-lived | Không cần (never-expiring nếu lấy từ long-lived user token) | user_token ~60 ngày | Re-OAuth user. Cảnh báo UI khi `user_token_expiry` < 7 ngày |
| X | OAuth1 access | Không cần | Không | — |
| TikTok | OAuth2 access | `grant_type=refresh_token` (không cần consent lại) | access 24h | `_creds_for` tự refresh nếu `now > expires_at`, ghi đè |
| Instagram | Long-lived 60 ngày | `GET ?grant_type=ig_refresh_token` | 60 ngày | Refresh khi còn < 7 ngày |

**Thực dụng (đúng phong cách tool local):**
- App secrets tách khỏi token; thêm `social_secrets/` + `social_tokens/` vào `.gitignore` (giống `client_secret.json` + `yt_tokens/`).
- `os.chmod(path, 0o600)` khi ghi token.
- Không log token; UI chỉ trả `name/connected/enabled`, không trả token.
- `_creds_for(channel_id)` mỗi platform: **đọc file → refresh nếu hết hạn → ghi đè (chmod 600) → trả token**.

---

## 6. Module/code đề xuất

### 6.1 File mới cần tạo

| File (tuyệt đối) | Vai trò |
|---|---|
| `/Users/nhatnv/project/tool-multi-lang/social_upload.py` | index.json CRUD + base adapter + 4 adapter (connect/_creds/post) |
| `/Users/nhatnv/project/tool-multi-lang/social_orchestrator.py` | `fanout()` song song + retry + state machine |
| `/Users/nhatnv/project/tool-multi-lang/social_seo.py` | `caption(seo_data, platform, lang, yt_url)` per-platform, tái dùng `seo.py` |
| `social_secrets/<platform>.json` | app credentials per-platform (gitignore) |
| `social_tokens/<yt_channel_id>/{index,facebook,x,tiktok,instagram}.json` | mapping + token per kênh (gitignore, chmod 600) |
| Sửa `/Users/nhatnv/project/tool-multi-lang/app.py` (sau dòng 507) | 6 route `/social/*` + gọi `fanout` trong `/yt/upload` (hoặc `/social/post` riêng) |
| Sửa `/Users/nhatnv/project/tool-multi-lang/templates/youtube.html` | card "Kênh MXH liên kết" + JS `loadSocial/toggle/connectSocial/pollSocial` |

### 6.2 `social_upload.py` — skeleton

```python
# /Users/nhatnv/project/tool-multi-lang/social_upload.py
import os, json, glob, time

ROOT = os.path.dirname(os.path.abspath(__file__))
SECRETS_DIR = os.path.join(ROOT, "social_secrets")
TOKENS_ROOT = os.path.join(ROOT, "social_tokens")
PLATFORMS = ("facebook", "x", "tiktok", "instagram")
os.makedirs(TOKENS_ROOT, exist_ok=True)

# ---------- index.json (mapping YT -> MXH) ----------
def _chan_dir(cid):
    d = os.path.join(TOKENS_ROOT, cid); os.makedirs(d, exist_ok=True); return d
def _index_path(cid): return os.path.join(_chan_dir(cid), "index.json")

def load_index(cid, yt_name="", lang="zh", topic_hint=""):
    p = _index_path(cid)
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    idx = {"yt_channel_id": cid, "yt_channel_name": yt_name,
           "lang": lang, "topic_hint": topic_hint, "updated_at": _now(),
           "platforms": {p_: _default_platform(p_) for p_ in PLATFORMS}}
    save_index(cid, idx); return idx

def save_index(cid, idx):
    idx["updated_at"] = _now()
    _write(_index_path(cid), json.dumps(idx, ensure_ascii=False, indent=2))

def set_enabled(cid, platform, enabled: bool):
    idx = load_index(cid); idx["platforms"][platform]["enabled"] = enabled
    save_index(cid, idx); return idx

def _default_platform(p):
    return {"enabled": p != "tiktok", "connected": False, "name": "",
            "account_id": "", "mode": "link" if p == "x" else "native"}

# ---------- registry ----------
def get_adapter(platform):
    return {"facebook": FacebookAdapter, "x": XAdapter,
            "tiktok": TikTokAdapter, "instagram": InstagramAdapter}[platform]()

# ---------- helpers ----------
def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
def _write(path, text):
    with open(path, "w", encoding="utf-8") as f: f.write(text)
    try: os.chmod(path, 0o600)
    except OSError: pass


# ===================== BASE ADAPTER (contract chung) =====================
class BaseAdapter:
    platform = ""
    def is_configured(self) -> bool: ...            # có social_secrets/<platform>.json?
    def setup_hint(self) -> str: ...                # HTML hướng dẫn tạo app
    def connect(self, cid) -> dict: ...             # OAuth blocking -> ghi <platform>.json + cập nhật index; trả {account_id,name}
    def _creds(self, cid) -> dict: ...              # đọc token, REFRESH nếu hết hạn, ghi đè; trả token dict
    def post(self, cid, caption, media, opts) -> dict:
        """media = {'kind':'native','video_path':...,'thumb':...} hoặc {'kind':'link','url':...}
           Trả {'ok':True,'post_url':...} hoặc {'ok':False,'error':...,'permanent':bool,'hint':...}"""


# ===================== 4 ADAPTER (khác body, giống contract) =====================
class FacebookAdapter(BaseAdapter):
    platform = "facebook"
    # post(): mode=native -> resumable /{page}/videos (3 bước INIT/upload/publish)
    #         mode=link   -> /{page}/feed (message + link). Page token + pages_manage_posts.

class XAdapter(BaseAdapter):
    platform = "x"
    # post(): POST /2/tweets (OAuth1.0a self-post). Link tính 23 ký tự.
    #         native -> chunked /2/media/upload (INIT/APPEND/FINALIZE). >280 -> thread tự cắt.

class TikTokAdapter(BaseAdapter):
    platform = "tiktok"
    # post(): creator_info/query -> video/init (FILE_UPLOAD chunked) -> poll status/fetch.
    #         unaudited -> ép SELF_ONLY; set permanent=False + hint "cần audit để public".

class InstagramAdapter(BaseAdapter):
    platform = "instagram"
    # post(): cần public video_url -> POST /{ig}/media (REELS) -> poll status_code -> media_publish.
```

**Chữ ký 4 adapter (khác body, giống contract):**

| Adapter | `post()` gọi | Native | Link | Async? |
|---|---|---|---|---|
| `FacebookAdapter` | `/{page}/videos` (native) / `/{page}/feed` (link) | resumable 3 bước | `message+link` | Không |
| `XAdapter` | `POST /2/tweets` (+ chunked `/2/media/upload` nếu native) | media v2 INIT/APPEND/FINALIZE | text+url (link=23 ký tự) | Không (thread nếu dài) |
| `TikTokAdapter` | `/v2/post/publish/video/init/` → poll `status/fetch` | FILE_UPLOAD chunked | n/a | **Có** (poll) |
| `InstagramAdapter` | `/{ig}/media` (REELS) → poll `status_code` → `/media_publish` | cần public `video_url` | n/a | **Có** (poll) |

### 6.3 `social_orchestrator.py` — fan-out skeleton

```python
# /Users/nhatnv/project/tool-multi-lang/social_orchestrator.py
from concurrent.futures import ThreadPoolExecutor, as_completed
import social_upload as su
import social_seo

def fanout(cid, job, yt_result, opts):
    """Sau khi YT upload xong -> đăng song song lên MXH enabled+connected.
       Trả {platform: {ok, post_url|error, caption}}."""
    idx = su.load_index(cid)
    lang, topic = idx.get("lang", "zh"), idx.get("topic_hint", "")
    targets = [p for p, st in idx["platforms"].items()
               if st["enabled"] and st["connected"]
               and opts.get("platforms_override", {}).get(p, True)]
    results = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_post_one, cid, p, idx, job, yt_result, lang, topic, opts): p
                for p in targets}
        for f in as_completed(futs):
            results[futs[f]] = f.result()
    return results

def _post_one(cid, platform, idx, job, yt_result, lang, topic, opts):
    cap = (opts.get("captions_override", {}).get(platform)
           or social_seo.caption(job.get("seo", {}), platform, lang, yt_result["url"], topic))
    mode = idx["platforms"][platform]["mode"]
    media = ({"kind": "native", "video_path": _abs(job["video"]), "thumb": _abs(job.get("thumb"))}
             if mode == "native" else {"kind": "link", "url": yt_result["url"]})
    ad = su.get_adapter(platform)
    return _with_retry(lambda: ad.post(cid, cap, media, opts), tries=3)

def _with_retry(fn, tries=3):
    import time
    last = None
    for i in range(tries):
        r = fn()
        if r.get("ok") or r.get("permanent"): return r
        last = r; time.sleep([0, 5, 15][min(i, 2)])
    return last or {"ok": False, "error": "unknown"}
```

**Idempotency:** lưu `social_tokens/<cid>/last_post_<job_id>.json` ghi platform đã đăng OK → tránh đăng trùng khi Retry chỉ retry nền tảng FAILED.

---

## 7. Caption SEO per-platform per-language

### 7.1 `social_seo.py` — skeleton

```python
# /Users/nhatnv/project/tool-multi-lang/social_seo.py
import seo  # tái dùng helper thuần (split_title, pinyin_of, build_chapters...)

LIMITS = {
  "facebook":  {"max": 2000, "tags": 5,  "allow_link": True,  "style": "long"},
  "x":         {"max": 270,  "tags": 2,  "allow_link": True,  "style": "short"},  # chừa 23 ký tự cho link
  "tiktok":    {"max": 2200, "tags": 6,  "allow_link": False, "style": "hashtag"},
  "instagram": {"max": 2000, "tags": 12, "allow_link": False, "style": "hashtag"},
}

def caption(seo_data, platform, lang, yt_url, topic_hint=""):
    han, viet = (seo.split_title(seo_data.get("title", "")) if lang == "zh"
                 else (seo_data.get("title", ""), ""))
    cfg = LIMITS[platform]
    hook = _hook(platform, lang, han, viet, topic_hint)     # 1-2 câu mở
    body = _body(platform, lang, seo_data, yt_url, cfg)      # bullet/CTA tùy style
    tags = " ".join(seo_data.get("hashtags", [])[:cfg["tags"]])
    text = "\n".join(x for x in [hook, body, tags] if x).strip()
    if cfg["allow_link"] and platform != "x":               # X đã nhúng link trong body
        text += f"\n▶️ {yt_url}"
    return _truncate(text, cfg["max"])
```

> Lõi zh-specific (`pinyin_of`, `split_title`, jieba) chỉ kích hoạt khi `lang=="zh"`. Mở rộng ngôn ngữ khác = thêm nhánh `lang` trong `_hook/_body`, **không đụng adapter**.

### 7.2 Khác biệt caption FB vs X vs TikTok vs IG

| | Facebook | X (Twitter) | TikTok | Instagram |
|---|---|---|---|---|
| **Độ dài** | dài (~500-2000) | rất ngắn ≤270 (chừa 23 cho link) | trung bình, nặng hashtag | trung bình, ≤30 tag |
| **Hook** | 1-2 câu cảm xúc + emoji | 1 câu giật + 1 hashtag chủ đề | câu CTA + hashtag trend | câu CTA + emoji |
| **Body** | bullet `chapters` + CTA "đăng ký kênh" | 1 lợi ích + link YT | 5-6 hashtag (#hoctiengtrung #fyp) | 10-12 hashtag + line break |
| **Link YT** | `▶️ url` (reach thấp) hoặc native | link cuối (23 ký tự) | KHÔNG clickable → "link ở bio" | KHÔNG clickable → "link ở bio" |
| **Native pref** | native (reach 2-3x) | text+link đơn giản | bắt buộc file | REELS native (cần public URL) |
| **Từ vựng** | trích 3-5 từ từ `pinned_comment` | 1 từ "từ hôm nay" | hashtag từ vựng | "Từ vựng trong bài 👇" + tags |

---

## 8. So sánh độ khó & ràng buộc từng nền tảng

| Tiêu chí | Facebook | X (Twitter) | TikTok | Instagram |
|---|---|---|---|---|
| **Endpoint chính** | `/{page}/feed`, `/{page}/videos` | `POST /2/tweets` + `/2/media/upload` | `/v2/post/publish/video/init/` | `/{ig}/media` → `/media_publish` |
| **Auth** | Page token long-lived | OAuth 1.0a self / OAuth2 PKCE | OAuth2 (access 24h + refresh) | Page-linked long-lived token |
| **App Review** | `pages_manage_posts` (cần review + app Live; Page mình sở hữu = Standard Access test ngay) | Set Read&Write / scopes; không review nhưng cần nạp credit | **Audit ToS bắt buộc để public** (5-10 ngày, dễ reject) | Review riêng mỗi permission (2-4 tuần) |
| **Business Verification** | Chỉ khi đăng cho Page người khác | Không | Không (nhưng audit) | Khuyến nghị |
| **Chi phí** | Miễn phí | **Pay-per-use**: $0.015/post, **$0.20/post có link** (đắt ~13x) | Miễn phí | Miễn phí |
| **Quota** | 4800 × engaged users / 24h | Free legacy ~500 post/tháng; mới phải nạp credit | init 6 req/phút; unaudited cap 5 user/24h | 100 post / 24h |
| **Media** | native resumable 3 bước / link | text-only dễ; media v2 chunked phức tạp | FILE_UPLOAD chunked (né verify domain) | **bắt buộc public URL** (S3/CDN/tunnel) |
| **Giới hạn caption** | text dài, hashtag inline | 280 (25k nếu Premium); link=23 | 2200 ký tự | 2200; ≤30 hashtag, ≤20 mention |
| **Chặn trở số 1** | App Review + app Live | **Chi phí** (link đắt) | **Audit** — chưa duyệt thì mãi private | **App Review + public URL hosting** |
| **Native reach** | 2-3x so với link | n/a | bắt buộc | REELS ưu tiên mạnh |
| **Async (poll)?** | Native: có | Không | **Có** | **Có** |
| **Độ khó code** | Trung bình (native) / Dễ (link) | Dễ (text+link) | Cao (audit + chunked + poll) | Cao (public URL + poll) |

**Tóm tắt ưu tiên triển khai theo độ khó:** Facebook (link) dễ nhất → Facebook (native) → X (text) → Instagram (cần public URL) → TikTok (cần audit). Rào cản thực sự ở TikTok/IG là **quy trình duyệt & hạ tầng**, không phải code.

### 8.1 Vấn đề "public URL" cho native upload (IG bắt buộc)
Tool chạy local. IG `video_url` và TikTok `PULL_FROM_URL` cần URL công khai.
- **TikTok**: dùng `FILE_UPLOAD` chunked (không cần URL public) → ưu tiên, né verify-domain.
- **IG**: bắt buộc public URL. Đề xuất route tạm `GET /public_media/<job_id>/<token>` expose qua ngrok/tunnel, hoặc upload lên bucket tạm. Nếu không có tunnel → đánh dấu IG-native "cần host public", cảnh báo UI. **Đây là blocker hạ tầng, không phải code.**

---

## 9. UI/UX (wireframe) + route Flask mới

### 9.1 Wireframe — Trang 2 mở rộng

Card mới **"Kênh mạng xã hội của <tên kênh>"** chèn **ngay sau card "Kênh đăng"** (sau `youtube.html:77`).

```
┌──────────────────────────────────────────────────────────────┐
│ 📺 Kênh đăng                          [+ Kết nối kênh mới]    │
│ ┌────────────────────────────────────────────────────────┐   │
│ │ Tố Nhật  (UCb6Ytn…)                              ▼     │◄── onchange → loadSocial(cid)
│ └────────────────────────────────────────────────────────┘   │
├──────────────────────────────────────────────────────────────┤
│ 🌐 Kênh mạng xã hội của "Tố Nhật"          (card MỚI)         │
│    Tự đăng bài chuẩn SEO sang các kênh MXH gắn với kênh YT này│
│  ┌───────────────────────────────────────────────────────┐  │
│  │ ⓕ Facebook   ● Page "Tố Nhật CN"      [Quản lý]  [✓]  │◄─ toggle bật/tắt
│  │   caption ▼ (textarea, sửa được)            [Copy]    │  │
│  │   ┌─────────────────────────────────────────────────┐ │  │
│  │   │ 我的一天 — Luyện nghe tiếng Trung HSK1 🎧       │ │  │
│  │   │ Video mới: nghe hiểu "Một ngày của tôi"…       │ │  │
│  │   │ 👉 youtu.be/xxxx   #HọcTiếngTrung #HSK1         │ │  │
│  │   └─────────────────────────────────────────────────┘ │  │
│  │   ◉ Đăng video native (reach cao)  ○ Đăng link YT     │  │
│  ├───────────────────────────────────────────────────────┤  │
│  │ 𝕏 X (Twitter) ○ Chưa kết nối           [Kết nối] [ ]  │◄─ toggle disabled khi chưa connect
│  ├───────────────────────────────────────────────────────┤  │
│  │ ♪ TikTok      ● @tonhat_cn  ⚠ chưa duyệt(private)[✓]  │◄─ cảnh báo audit inline
│  │   caption ▼ … [Copy]                                  │  │
│  ├───────────────────────────────────────────────────────┤  │
│  │ ◎ Instagram   ○ Chưa kết nối           [Kết nối] [ ]  │◄─ nhắc cần public URL
│  └───────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────┤
│ 📝 SEO YouTube (title/desc/privacy/tags) … 📑 CC … 📌 Comment │
├──────────────────────────────────────────────────────────────┤
│         🚀 Đăng lên YouTube + lan toả MXH                     │◄── nút đăng gộp
│  ┌───────────── trạng thái đăng (live, poll 2s) ─────────┐    │
│  │ ✅ YouTube      youtu.be/xxxx ↗                        │    │
│  │ ⏳ Facebook     đang đăng video native…               │    │
│  │ ✅ TikTok       đã đẩy (private — chờ duyệt) ↗         │    │
│  │ ⛔ X            (đã tắt)                               │    │
│  │ ❌ Instagram    lỗi: cần video public URL             │    │
│  └────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

**Mỗi dòng nền tảng (component lặp) gồm 5 phần tử:**
1. Icon + tên nền tảng.
2. Trạng thái kết nối: `● tên-tài-khoản` (xanh) / `○ Chưa kết nối` (xám).
3. Nút `[Kết nối]` (chưa connect) / `[Quản lý]` (đã connect) → mở tab OAuth.
4. Toggle bật/tắt đăng (mẫu `capToggle`/`setThumb`) — **disabled** nếu chưa kết nối.
5. Vùng caption: `<textarea>` sửa được + nút Copy + radio native/link (chỉ hiện khi đã kết nối & bật).

### 9.2 Route Flask mới (thêm sau khối `/yt/*`, sau `app.py:507`)

| Route | Mô tả | Response |
|---|---|---|
| `GET /social/links/<channel_id>` | Trạng thái 4 nền tảng (đọc `index.json`), chỉ trả name/enabled/connected/warn | `{platforms:{facebook:{connected,name,warn},…}}` |
| `POST /social/toggle/<channel_id>/<platform>` | body `{enabled}` → `set_enabled()` | `{ok:true, ...}` |
| `GET /social/connect/<channel_id>/<platform>` | OAuth blocking, mở tab (mẫu `/yt/connect`); ghi token + cập nhật index | HTML "Đã kết nối — đóng tab". 400 chưa cấu hình app, 500 OAuth lỗi |
| `POST /social/disconnect/<channel_id>/<platform>` | xóa file token, set `connected=False` | `{ok:true}` |
| `GET /social/caption/<job_id>` (`?channel_id=&yt_url=`) | sinh 4 caption từ `job["seo"]` | `{facebook:{text,native_ok}, x:{text,len,limit}, tiktok:{text,limit}, instagram:{text,needs_public_url}}` |
| `POST /social/post` | đăng nền song song; trả task_id ngay | `202 {task_id}`; 400 thiếu yt_url/video_id |
| `GET /social/status/<task_id>` | polling tiến trình (mẫu `/progress/<id>`) | `{done, results:{facebook:{state,url,msg},…}}` |
| `POST /social/retry/<job_id>/<channel_id>/<platform>` | đăng lại đúng 1 nền tảng FAILED | `{state,url,msg}` |

`POST /social/post` body:
```json
{
  "job_id": "abc123", "channel_id": "UCb6Ytn…",
  "video_id": "yt_video_id", "yt_url": "https://youtu.be/yt_video_id",
  "platforms": {
    "facebook":  { "on": true,  "caption": "…", "mode": "native" },
    "x":         { "on": false },
    "tiktok":    { "on": true,  "caption": "…" },
    "instagram": { "on": true,  "caption": "…" }
  }
}
```

`GET /social/status/<task_id>` map `state` → UI:

| state | icon | class | text mẫu |
|---|---|---|---|
| `pending` | `•` | muted | chờ đăng |
| `running` | `⏳` | run (cam) | đang đăng video native… |
| `ok` | `✅` | ok (xanh) | `<a>` mở bài ↗ |
| `error` | `❌` | err (đỏ) | lỗi + gợi ý khắc phục |
| `skipped` | `⛔` | skip (xám) | đã tắt |

### 9.3 Điểm sửa cụ thể trong `youtube.html`

| Vị trí | Thay đổi |
|---|---|
| dòng 72 `<select id="channel">` | thêm `onchange="loadSocial(this.value)"` |
| sau dòng 77 | chèn `<div class="card" id="socialCard">` (vùng render `#socialList`) |
| CSS (sau dòng 40) | thêm `.plat-row`, `.dot.on/.off`, `.run`, `.skip`, `.cap-box` |
| dòng 162-178 `loadChannels()` | sau khi đổ select, gọi `loadSocial(sel.value)` cho kênh đầu |
| script (vùng 140-217) | thêm `loadSocial(cid)`, `connectSocial(cid,plat)`, `togglePlat()`, `pollSocial(taskId)` |
| dòng 185-215 `doUpload()` | YT trả `{url,id}` → `POST /social/post` → `pollSocial(task_id)`; đổi nhãn nút "Đăng YouTube + lan toả MXH" |

---

## 10. Lộ trình triển khai theo giai đoạn

### Phase 0 — Hạ tầng nền (1-2 ngày)
- Tạo `social_upload.py` (index.json CRUD + BaseAdapter + registry), `social_orchestrator.py` (fanout + retry), `social_seo.py` (caption skeleton).
- Tạo thư mục `social_secrets/`, `social_tokens/`; thêm vào `.gitignore`; chmod 600.
- Thêm 6 route `/social/*` (chưa cần adapter thật — trả mock để test UI).
- Sửa `youtube.html`: card MXH + JS `loadSocial/toggle/connectSocial/pollSocial` + `onchange` select.
- **Mốc nghiệm thu:** UI render 4 dòng nền tảng, toggle lưu được, caption preview hiển thị (mock).

### Phase 1 — Facebook (nền tảng dễ nhất, 2-3 ngày)
- `FacebookAdapter`: OAuth user → long-lived → Page token; `post()` mode=link (`/{page}/feed`) trước, rồi native (`/{page}/videos` resumable).
- Lý do làm trước: chỉ cần app + `pages_manage_posts` trên Page mình sở hữu (Standard Access, test ngay không cần Business Verification).
- `social_seo.caption()` cho FB hoàn chỉnh (zh + lang-agnostic).
- **Mốc:** đăng thật 1 bài FB native từ video thật, status hiển thị link.

### Phase 2 — X (Twitter) (1-2 ngày)
- `XAdapter`: OAuth 1.0a self-post → `POST /2/tweets` text+link; thread tự cắt nếu >280.
- **Rủi ro:** dev mới cần nạp credit pay-per-use, link post đắt ~13x → để X mặc định `mode` cân nhắc, nhắc chi phí inline. Media v2 chunked để sau (optional).
- **Mốc:** đăng tweet text+link thật.

### Phase 3 — Instagram (3-4 ngày, có blocker hạ tầng)
- `InstagramAdapter`: REELS `/{ig}/media` → poll `status_code` → `/media_publish`.
- **Blocker:** cần IG Business + public URL → dựng route `/public_media` + tunnel (ngrok) hoặc bucket; App Review 2-4 tuần.
- **Mốc:** đăng REELS thật qua public URL (qua tunnel trong dev).

### Phase 4 — TikTok (3-5 ngày + chờ audit, làm cuối)
- `TikTokAdapter`: `creator_info/query` → `video/init` (FILE_UPLOAD chunked) → poll `status/fetch`.
- **Blocker lớn nhất:** unaudited ép private (SELF_ONLY), cap 5 user/24h; audit 5-10 ngày để public → để default tắt, hiển thị `warn`.
- **Mốc:** đăng private thành công khi chưa audit; bật public sau audit.

### Phase 5 — Hoàn thiện (1-2 ngày)
- Retry per-platform (`/social/retry`), idempotency `last_post_<job_id>.json`.
- Cảnh báo token sắp hết hạn (FB/IG < 7 ngày), refresh TikTok/IG.
- Dịch sẵn gợi ý lỗi (IG "cần public URL", TikTok "private vì chưa duyệt", FB "token Page hết hạn", X "vượt 280 / cần nạp credit").

### Rủi ro & khuyến nghị chốt

| Rủi ro | Khuyến nghị |
|---|---|
| TikTok/IG App Review chậm/reject | Ship FB+X trước (Phase 1-2 dùng được ngay); TikTok/IG đánh dấu "beta", default tắt |
| IG cần public URL khi tool chạy local | Dùng ngrok/tunnel trong dev; production cần host file công khai có token bảo vệ |
| X chi phí pay-per-use (link đắt 13x) | Mặc định nhắc chi phí; ưu tiên post không link hoặc cân nhắc bỏ X nếu ngân sách hạn chế |
| Token hết hạn giữa chừng | `_creds_for` auto-refresh + cảnh báo UI < 7 ngày; FB never-expiring page token là lựa chọn an toàn nhất |
| Caption sai ngôn ngữ khi mở rộng | Lõi zh-specific gated theo `lang`; thêm ngôn ngữ = thêm nhánh trong `social_seo._hook/_body`, không đụng adapter |
| Đăng trùng khi Retry | Idempotency file `last_post_<job_id>.json`, chỉ retry platform FAILED |
| 1 nền tảng lỗi kéo cả luồng | Fault isolation: mỗi platform 1 future + try/except độc lập; YT luôn xong trước và không phụ thuộc MXH |

**Khuyến nghị tổng:** Bắt đầu Phase 1 (Facebook) ngay vì rào cản thấp nhất và chứng minh được toàn bộ kiến trúc end-to-end (chọn kênh YT → upload → sinh caption SEO → đăng MXH → poll status). Các nền tảng còn lại cắm vào cùng contract `BaseAdapter` mà không sửa orchestrator/UI — chỉ thêm adapter + nhánh caption.

---

**Tất cả file liên quan:**
- `/Users/nhatnv/project/tool-multi-lang/youtube_upload.py`
- `/Users/nhatnv/project/tool-multi-lang/seo.py`
- `/Users/nhatnv/project/tool-multi-lang/app.py`
- `/Users/nhatnv/project/tool-multi-lang/templates/youtube.html`
- `/Users/nhatnv/project/tool-multi-lang/templates/index.html`
- Module mới: `/Users/nhatnv/project/tool-multi-lang/social_upload.py`, `/Users/nhatnv/project/tool-multi-lang/social_orchestrator.py`, `/Users/nhatnv/project/tool-multi-lang/social_seo.py`