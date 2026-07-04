# QUY CHUẨN VIẾT BÀI — series 7 ngày × 5 kênh (video ≥ 20 phút)

Mỗi bài là 1 file `dayN.txt` dán thẳng vào app (tool-multi-lang). Parser là `lesson_parser.py`.

## Format bắt buộc

```
@title 中文标题 (Tiêu đề tiếng Việt)
@hanzi 二字                  ← 2-4 chữ Hán đại diện bài (hiện slide mở đầu)
@topic mô tả ngắn tiếng Việt
@hsk HSK2                    ← ĐÚNG trình độ thật của nội dung, không dán bừa
@image <english prompt for AI illustration, cute warm style>
@objectives Mục tiêu 1; Mục tiêu 2; Mục tiêu 3

# TỪ VỰNG
你好 | Xin chào              ← mỗi dòng 1 từ, KHÔNG gộp

# MẪU CÂU  (hoặc # CHUYỆN KỂ, # PHẦN 1... — đều render dạng câu)
今天天气很好。 | Hôm nay thời tiết rất đẹp.

# HỘI THOẠI
小雨: 你好！ | Xin chào!
阿明: 你好，好久不见！ | Chào cậu, lâu rồi không gặp!

# LUYỆN TẬP
? "Cảm ơn" nói thế nào?
谢谢 | Cảm ơn
```

## Quy tắc CỨNG của parser (vi phạm là hỏng video)

1. **Mỗi dòng câu PHẢI kết thúc bằng dấu câu** (。！？…) trước dấu `|` — dòng không có dấu kết sẽ bị GỘP vào dòng sau.
2. Mỗi dòng đúng 1 cặp `chữ Hán | nghĩa Việt`. Không để dòng chỉ có Hán không có Việt (trừ LUYỆN TẬP câu `?`).
3. Hội thoại: `Tên: hанzi | viet`. Dùng tên chữ Hán để tool tự gán giọng nam/nữ — tên NỮ kết thúc bằng: 雨/丽/娜/婷/芳/玲/静/梅/兰/花/雪/琴/欣/怡/颖/琳; tên NAM kết thúc bằng: 明/强/伟/军/勇/刚/峰/涛/辉/杰/俊/浩/宇/航/鹏/龙/飞/华.
4. Không dùng ký tự `#` hay `@` ở đầu dòng nội dung.
5. Câu chữ Hán dài lý tưởng 10–22 chữ. Câu quá dài (>28 chữ) phải tách đôi.

## Độ dài (mục tiêu video 20–23 phút)

- Mỗi segment đọc ~6.5 giây (Hán + Việt + nghỉ). **20 phút ≈ 180–200 dòng nội dung.**
- Cơ cấu gợi ý bài kể chuyện/tản văn: hook 3 câu + 12–15 từ vựng + truyện phần 1 (~50 câu) + nghe lại chậm 10 câu đắt nhất + truyện phần 2 (~50 câu) + hội thoại/đối đáp (~25 lượt) + luyện tập 10 câu + tổng kết 5 câu.
- Cơ cấu bài hội thoại HSK thấp: 15 từ vựng + 20 mẫu câu + hội thoại 1 (~25 lượt) + nghe lại từng câu + hội thoại 2 mở rộng (~25 lượt) + luyện tập 15 câu + ôn từ vựng lặp lại cuối bài.
- **Lặp lại có chủ đích là TÍNH NĂNG** (người học cần nghe lại): mỗi bài chọn 8–12 "câu vàng" xuất hiện 2 lần ở 2 đoạn khác nhau.

## Chất lượng nội dung (để "review tốt")

1. **Hook 3 câu đầu** phải chạm đúng nỗi đau/tò mò của người xem, KHÔNG mở đầu kiểu "hôm nay chúng ta học...".
2. Tiếng Trung phải TỰ NHIÊN như người bản xứ viết, đúng trình độ khai báo ở @hsk:
   - HSK1-2: chỉ dùng từ trong ~300 từ cơ bản, câu ngắn 5–10 chữ.
   - HSK3: ~600 từ, câu 8–15 chữ.
   - HSK4: câu 10–22 chữ, được dùng thành ngữ đơn giản.
3. Nghĩa Việt dịch THOÁT, tự nhiên như người Việt nói, không dịch word-by-word.
4. Có mạch 7 ngày: cuối mỗi bài nhá hàng bài hôm sau (2 câu), nhân vật/bối cảnh xuyên suốt.
5. Không nội dung nhạy cảm, không thương hiệu thật, không tên người thật.

## Mỗi kênh kèm 1 file CHANNEL.md gồm

- Tên kênh đề xuất + tagline + mô tả kênh (about) + định vị khác biệt.
- Bảng 7 ngày: tiêu đề YouTube (hook Việt đứng TRƯỚC, chữ Hán sau, ≤90 ký tự, KHÔNG gắn "#1"),
  text thumbnail (tiếng Việt ≤6 từ, đánh vào cảm xúc), image_prompt thumbnail,
  giờ đăng đề xuất, 3 câu "đắt" nhất để cắt Shorts (ghi rõ nội dung câu).
- Giọng đọc khuyến nghị cho kênh (từ pool: zh-CN-XiaoxiaoNeural nữ ấm, zh-CN-XiaoyiNeural nữ trẻ, zh-CN-YunxiNeural nam trẻ ấm, zh-CN-YunjianNeural nam trầm; vi-VN-HoaiMyNeural nữ / vi-VN-NamMinhNeural nam).
