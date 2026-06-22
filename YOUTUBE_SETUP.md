# 🚀 Hướng dẫn bật tính năng "Đăng lên YouTube"

Để tool đăng video thẳng lên YouTube, cần 1 file `client_secret.json` (làm **1 lần duy nhất**).

## Bước 1 — Tạo project & bật API
1. Vào https://console.cloud.google.com → tạo **Project** mới (vd: "tool-video-lang").
2. Menu → **APIs & Services → Library** → tìm **YouTube Data API v3** → **Enable**.

## Bước 2 — Cấu hình màn hình đồng ý (OAuth consent)
1. **APIs & Services → OAuth consent screen** → chọn **External** → Create.
2. Điền tên app, email → Save. (Không cần submit để xét duyệt.)
3. Mục **Test users** → **Add users** → thêm email Google của (các) kênh bạn sẽ đăng.
   > Khi app ở chế độ "Testing", chỉ test users mới đăng nhập được — đủ dùng cho cá nhân.

## Bước 3 — Tạo OAuth Client
1. **APIs & Services → Credentials → Create Credentials → OAuth client ID**.
2. Application type: **Desktop app** → Create.
3. Bấm **Download JSON** → đổi tên thành **`client_secret.json`**.
4. Đặt file vào thư mục tool: `/Users/nhatnv/project/tool-video-lang/client_secret.json`

## Bước 4 — Kết nối kênh
1. Tạo 1 video → bấm **Next → Đăng YouTube** → trang đăng.
2. Bấm **"+ Kết nối kênh mới"** → trình duyệt mở → đăng nhập Google của kênh → cấp quyền.
3. Xong! Kênh hiện trong dropdown. Lặp lại để thêm kênh khác.
4. Từ giờ: chọn kênh → **🚀 Đăng lên YouTube**.

---

### Lưu ý
- **Quota miễn phí:** ~6 video/ngày (mỗi upload tốn 1600 đơn vị / 10.000). Bạn đăng ~3/ngày → thoải mái.
- `client_secret.json` và thư mục `yt_tokens/` đã được **.gitignore** — không bao giờ commit (bí mật).
- Lần đầu Google có thể cảnh báo "app chưa xác minh" → bấm **Advanced → Go to ... (unsafe)** (an toàn vì là app của chính bạn).
