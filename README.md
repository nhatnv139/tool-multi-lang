# 🇨🇳 Chinese YouTube — Tự động tạo & đăng video bài học tiếng Trung (HSK)

Pipeline tự sinh **video bài học tiếng Trung**: nền pastel + pinyin-trên-chữ +
chữ chạy theo giọng + nhạc nền + mascot, tự ghép & xuất. Có **app web** để dùng dễ,
kèm **SEO tự động + đăng thẳng lên YouTube nhiều kênh** (kèm phụ đề & ảnh bìa).

---

## 📋 Yêu cầu hệ thống

| Thành phần | Bản tối thiểu | Ghi chú |
|-----------|---------------|---------|
| **Python** | 3.11+ | macOS dùng lệnh `python3`; Windows dùng `python` |
| **FFmpeg** | bản mới | phải nằm trong PATH (ghép video/âm thanh) |
| **Internet** | — | edge-tts (giọng đọc MS) + hình AI Pollinations + YouTube API |

Kiểm tra nhanh:
```bash
python3 --version      # >= 3.11
ffmpeg -version        # phải ra version
```
Cài FFmpeg nếu thiếu: macOS `brew install ffmpeg` · Windows `choco install ffmpeg` · Linux `sudo apt install ffmpeg`.

---

## ⚙️ Cài đặt (làm 1 lần)

```bash
# 1. Vào thư mục dự án
cd tool-video-lang

# 2. (Khuyến nghị) tạo virtualenv riêng
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 3. Cài thư viện
pip install -r requirements.txt
```

> Không dùng venv cũng được — khi đó cài thẳng: `pip install -r requirements.txt`.

---

## 🚀 Chạy app web (cách dùng chính)

```bash
python3 app.py
```
Mở trình duyệt: **http://127.0.0.1:5000**

### Quy trình 2 bước trên giao diện

**Bước 1 — Tạo video**
1. Dán nội dung (xem [Định dạng nội dung](#-định-dạng-nội-dung-dán-vào-app)) + chọn giọng đọc.
2. Tuỳ chọn: màu nền, tốc độ, nhạc, mascot, tên kênh, thanh info (FB/YouTube/Zalo),
   **🎨 Hình minh hoạ AI theo chủ đề** (miễn phí qua Pollinations.ai, cần internet).
3. Bấm **Tạo video** → theo dõi tiến độ → video ra ở `output/`.

**Bước 2 — Đăng YouTube** (sau khi video xong, bấm **Next → Đăng YouTube**)
1. App tự sinh **SEO**: tiêu đề, mô tả (có timestamp tự động), tags, comment từ vựng, phụ đề SRT (Hán/Pinyin/Việt).
2. Chọn kênh trong dropdown (hoặc **+ Kết nối kênh mới**).
3. Bấm **🚀 Đăng lên YouTube** → tool tự: upload video (mặc định *public*) +
   gắn 3 track phụ đề (CC) + đặt ảnh bìa + đăng comment từ vựng.

> **Lần đầu cần cấu hình OAuth** (`client_secret.json`). Xem **[YOUTUBE_SETUP.md](YOUTUBE_SETUP.md)** — làm 1 lần duy nhất.

### 🎙️ Chọn giọng đọc (4 mức)

| Engine | Phí | Chất lượng | Cần gì |
|--------|-----|-----------|--------|
| **edge-tts** | Free | Tốt | Chỉ cần internet (mặc định) |
| **ChatTTS (local)** | Free | Tự nhiên | Chạy trên máy, hơi chậm |
| **Azure** | Free F0 | Rất tự nhiên | Key + Region (portal.azure.com) |
| **ElevenLabs** 💎 | Trả phí | Cao nhất | API key (elevenlabs.io) |

**Dùng ElevenLabs (trả phí):**
1. Vào https://elevenlabs.io → đăng nhập → avatar góc phải → **API Keys → Create** → copy key.
2. (Tuỳ chọn) Vào **Voices** chọn/clone 1 giọng → bấm nút **ID** để copy `voice_id`.
3. Trên app: dropdown giọng chọn nhóm **💎 ElevenLabs**, dán **API key** vào ô "Giọng cao cấp (ElevenLabs)".
   - Muốn dùng giọng riêng → dán `voice_id` vào ô bên cạnh (để trống thì dùng giọng đã chọn).
4. Key được lưu vào `eleven_config.json` (đã .gitignore — không commit), lần sau khỏi nhập.

> Dùng model `eleven_multilingual_v2`: **1 giọng đọc được cả tiếng Trung lẫn tiếng Việt**.
> Tốc độ đọc (thanh trượt) tự map sang `speed` 0.7–1.2 của ElevenLabs.

---

## 📝 Định dạng nội dung (dán vào app)

```
@title CHÀO HỎI
@hanzi 你好                 (tuỳ chọn)
@image cute panda waving   (tuỳ chọn - mô tả hình AI, tiếng Anh)

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
```
App tự sinh pinyin + intro/outro. Bạn chỉ gõ chữ Hán + nghĩa Việt
(bảo ChatGPT xuất đúng mẫu này là nhanh nhất).

---

## 🖥️ (Nâng cao) Chạy pipeline trực tiếp bằng dòng lệnh

Dành cho khi muốn render từ file JSON trong `data/` (không qua web).

Render 1 bài:
```bash
python3 generate.py data/lesson01.json
```

Render tất cả bài trong `data/`:
```bash
python3 build_all.py
```
Video ra ở `output/HSK1_BaiXX_*.mp4` (1080p, có tiếng).

### Thêm bài mới
Copy 1 file trong `data/`, đổi nội dung. Mỗi bài gồm các "segment":

| type | Ý nghĩa | Trường cần |
|------|---------|-----------|
| `title` | Slide mở đầu | (dùng title/hanzi_title của bài) |
| `objectives` | Mục tiêu bài | `lines: [...]` |
| `section` | Slide phân mục | `label` |
| `vocab` | Từ vựng | `hanzi`, `pinyin`, `viet` |
| `sentence` | Mẫu câu | `hanzi`, `pinyin`, `viet` |
| `dialogue` | Hội thoại | `rows: [{sp,hanzi,pinyin,viet}]` |
| `practice_q` | Câu hỏi luyện tập | `question` |
| `practice_a` | Đáp án | `hanzi`, `pinyin`, `viet` |
| `outro` | Slide kết (tự ghi số bài) | — |

Header bài cần: `id`, `hsk`, `title`, `topic`, `hanzi_title`.

---

## 📁 Cấu trúc dự án

```
tool-video-lang/
├── app.py              # App web Flask (cổng 5000) — điểm vào chính
├── generate.py         # Render 1 bài (slide → audio → ghép video)
├── build_all.py        # Render tất cả bài trong data/
├── style_pastel.py     # Toàn bộ logic vẽ slide (theme pastel)
├── lesson_parser.py    # Parse nội dung text dán vào app
├── seo.py              # Sinh SEO: tiêu đề/mô tả/tags/timestamp/phụ đề SRT
├── youtube_upload.py   # OAuth + upload video/caption/thumbnail/comment
├── chattts_engine.py   # (tuỳ chọn) engine TTS thay thế
├── templates/          # index.html, youtube.html
├── data/               # Nội dung mỗi bài (lesson01.json, ...)
├── assets/             # File tạm khi render (png/mp3) — tự sinh, gitignore
├── output/             # Video .mp4 thành phẩm    ← gitignore
├── uploads/            # Nội dung người dùng tải lên — gitignore
├── brand/              # Logo/banner + clip intro/outro
├── client_secret.json  # 🔒 Bí mật OAuth — KHÔNG commit (xem YOUTUBE_SETUP.md)
├── yt_tokens/          # 🔒 Token kênh đã kết nối — KHÔNG commit
├── requirements.txt    # Thư viện Python
├── README.md
└── YOUTUBE_SETUP.md    # Hướng dẫn bật đăng YouTube (làm 1 lần)
```

---

## 🎨 Tùy chỉnh nhanh (trong `generate.py`)
- `VOICE_ZH`, `VOICE_VI` — đổi giọng đọc
- `C_TOP`, `C_BOT`, `C_GOLD` — đổi màu nền/theme
- `PAD` — khoảng lặng sau mỗi slide
- `synth(..., rate="-8%")` — tốc độ đọc (chậm hơn cho người mới)

Giao diện theo style **pastel**: nền hồng `(255,235,237)`, **pinyin đặt trên từng chữ Hán**,
chữ Hán serif, nghĩa Việt đậm nghiêng đỏ mận, header + badge HSK.

---

## 🩺 Xử lý sự cố thường gặp

| Triệu chứng | Cách xử lý |
|-------------|-----------|
| `ffmpeg: command not found` | Cài FFmpeg và đảm bảo nằm trong PATH |
| Trang đăng YouTube báo "Chưa có client_secret.json" | Làm theo [YOUTUBE_SETUP.md](YOUTUBE_SETUP.md) |
| Google cảnh báo "app chưa xác minh" | **Advanced → Go to ... (unsafe)** — an toàn vì là app của chính bạn |
| Hết quota upload | ~6 video/ngày (mỗi upload tốn 1600/10.000 đơn vị) — đợi sang ngày |
| Đặt thumbnail lỗi | Kênh phải bật custom thumbnail (cần xác minh số điện thoại) |
| Giọng đọc/hình AI không ra | Cần internet (edge-tts & Pollinations gọi mạng) |

---

## 📺 Mẹo vận hành kênh
- Tiêu đề mẫu: `[HSK1] Bài X: ... | Tự học tiếng Trung cho người mới`
- Gom video vào Playlist theo HSK1 / HSK2 / HSK3.
- Cắt 1 từ vựng thành Short/TikTok để kéo view.
