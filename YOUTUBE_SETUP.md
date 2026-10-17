# 🚀 Hướng dẫn bật tính năng "Đăng lên YouTube"

Để tool đăng video thẳng lên YouTube, cần 1 file `client_secret.json` (làm **1 lần duy nhất**),
sau đó mỗi kênh đăng nhập 1 lần.

## Bước 1 — Tạo project & bật API
1. Vào https://console.cloud.google.com → tạo **Project** mới (vd: "tool-multi-lang").
2. Menu **APIs & Services → Library** → tìm **YouTube Data API v3** → **Enable**.

## Bước 2 — Cấu hình màn hình đồng ý (OAuth consent)
Giao diện mới của Google gọi mục này là **Google Auth Platform**; bản cũ là **OAuth consent screen**.
1. **APIs & Services → OAuth consent screen** (hoặc **Google Auth Platform → Branding**).
2. User type: **External** → điền tên app + email liên hệ + email nhà phát triển → Save.
   (Không cần submit xét duyệt.)
3. Mục **Audience → Test users** → **Add users** → thêm **email Google của (các) kênh** sẽ đăng.
   > App để chế độ "Testing" thì chỉ test user mới đăng nhập được — đủ dùng cho cá nhân.
   > Token ở chế độ Testing hết hạn sau ~7 ngày → hết hạn thì bấm "Kết nối kênh mới" lại.

## Bước 3 — Tạo OAuth Client
1. **APIs & Services → Credentials → Create Credentials → OAuth client ID**.
2. Application type: **Desktop app** → Create.
3. Bấm **Download JSON** → đổi tên thành **`client_secret.json`**.
4. Đặt file vào đúng thư mục gốc của tool:

```
D:\dev\tool-multi-lang\client_secret.json
```

Kiểm tra nhanh bằng PowerShell:
```powershell
Test-Path D:\dev\tool-multi-lang\client_secret.json   # phải ra True
```

## Bước 4 — Kết nối kênh
1. Chạy app: `D:\dev\tool-multi-lang\venv\Scripts\python.exe app.py`
   → mở **http://127.0.0.1:5001** (app tự nhảy cổng nếu 5000 bận — xem dòng in ra ở terminal).
2. Tạo 1 video → bấm **Next → Đăng YouTube** (hoặc mở thẳng trang đăng của job đã render).
3. Bấm **"+ Kết nối kênh mới"** → tab mới mở ra → trình duyệt bật cửa sổ đăng nhập Google
   → chọn tài khoản của kênh → **Advanced → Go to … (unsafe)** (app của chính bạn, an toàn)
   → tick đủ quyền → Allow.
4. Hiện "✅ Đã kết nối kênh: …" → đóng tab, quay lại trang đăng, danh sách kênh tự cập nhật.
5. Muốn thêm kênh khác: lặp lại bước 3 với tài khoản Google khác.

Token lưu tại `yt_tokens\<channel_id>.json` (+ `.name` là tên kênh).

---

### Lưu ý
- **Quota miễn phí:** ~6 video/ngày (mỗi upload tốn 1600 / 10.000 đơn vị).
- `client_secret.json` và thư mục `yt_tokens/` đã được **.gitignore** — tuyệt đối không commit.
- Nếu kênh nằm trong **Brand Account**, ở bước chọn tài khoản Google phải chọn đúng
  brand account đó (Google sẽ hỏi "chọn kênh") — không thì token trỏ vào kênh cá nhân.
- Đặt ảnh bìa (thumbnail) lỗi → kênh chưa bật custom thumbnail (cần xác minh số điện thoại).
- Lỗi `access_denied` → email đó chưa nằm trong **Test users** ở Bước 2.
