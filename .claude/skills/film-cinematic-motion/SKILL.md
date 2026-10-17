---
name: film-cinematic-motion
description: Bật/tinh chỉnh camera đẩy vào nhân vật + dip-to-black chuẩn "Chuyện Quê Xưa" khi build video film. Dùng khi build film, render truyện, hoặc user phàn nàn chuyển cảnh giật/không mượt.
---

# Film Cinematic Motion — camera nhắm nhân vật + dip-to-black

Nâng cấp trong `film.py` (repo `D:\dev\tool-multi-lang`): Ken Burns subpixel hướng về
nhân vật + chuyển cảnh dip-to-black theo số đo video mẫu "Chuyện Quê Xưa".
**Timing toàn cục BẤT BIẾN**: chuyển cảnh được bake vào frame cuối của cảnh trước
(không thêm/bớt frame) → SRT, chapters, mốc nhạc không lệch.

## Cơ chế

1. **Detect nhân vật nhiều tầng** (`find_subject_center`, cache theo path — deterministic):
   - `lbpcascade_animeface` (mặt anime, conf ~0.7) →
   - Haar frontal/profile (mặt người thật, conf ~0.5) →
   - YuNet DNN (chỉ khi cv2 5.x hết cascade) →
   - Saliency Hou-Zhang tự viết bằng numpy FFT (opencv-python KHÔNG có `cv2.saliency`) + prior nửa trên + snap rule-of-thirds →
   - Fallback heuristic `(0.5W, 0.42H)`, conf=0 (camera về zoom tâm cũ, không hại).
   `conf` giảm biên độ kéo về nhân vật: detect yếu → gần như zoom tâm, sai không hại.
2. **Chu kỳ 5 kiểu chuyển động** (`_MOTIONS`, chọn theo chỉ số cảnh `idx % 5`):
   `push` (đẩy vào nhân vật ~10%/cảnh) → `pan_r` → `pan_l` (pan thuần ~8% bề ngang) →
   `pushpan` (đẩy + trượt) → `pull` (mở từ cận nhân vật về toàn cảnh).
   Zoom + pan cùng easing smoothstep, warpAffine subpixel → mượt tuyệt đối, không giật nấc.
   Tâm crop luôn qua `_clamp_center` ở 2 đầu quỹ đạo → **không bao giờ lộ viền đen**.
3. **Dip-to-black ~0.5s đối xứng**: ra 0.25s (bake cuối cảnh trước, gamma-correct `^1.6`)
   + vào 0.25s (`head_black` đầu cảnh sau). `always_fade` bật → mọi mối CUT thành dip
   (video mẫu 100% dip). Beat trong JSON vẫn được tôn trọng: đổi phân đoạn → zoom-blend,
   vào ket/timejump → dissolve chậm (xem `plan_transitions`).
4. Cảnh đầu fade-in 0.8s từ đen; cảnh cuối fade-out (khớp end card).

## Bảng opts mới (truyền vào `film.make_film(scenes, opts, out)`)

| Khóa | Mặc định | Ý nghĩa |
|---|---|---|
| `focus_subject` | `True` | Detect nhân vật → zoom/pan hướng về mặt. `False` = zoom tâm cũ. |
| `zoom_amt` | `None` (=0.10) | Biên độ zoom/cảnh, cap 0.12 (ảnh nguồn 720p, zoom sâu lộ nét). |
| `dip_dur` | `0.5` | Tổng thời gian dip (ra dur/2 + vào dur/2). Video mẫu ~0.45s. |
| `always_fade` | `True` | Mọi mối CUT (cùng beat/twist/climax) → dip-to-black. |
| `scene["focus"]` | — | `[x, y]` tỷ lệ 0–1 trong JSON phân cảnh: ép tay tâm nhân vật, bỏ qua detect (conf=0.95). |
| `scene["trans"]` | — | Ép tay kiểu chuyển TRƯỚC cảnh đó: `cut` \| `black` \| `blend`. |
| env `FILM_FADE_FOCUS=1` | tắt | Dip dùng mask radial quanh nhân vật (nhân vật tắt sau cùng). |

Các opts nền tảng phải bật cùng: `kenburns=True`, `transition="fade"` (có cv2 sẽ tự
ép `transition="none"` sau khi `plan_transitions` bake dip vào từng cảnh).

## Lệnh build mẫu

```bash
# Qua build_film_story.py (JSON phân cảnh trong data/)
D:\dev\tool-multi-lang\venv\Scripts\python.exe build_film_story.py data/film_xxx.json
# thử nhanh 4 cảnh đầu:
... build_film_story.py data/film_xxx.json --scenes 4 --music none
```

Qua web UI: Flask chạy port 5001 (`python app.py`), tab Film — job web inline lại
đúng chuỗi `plan_transitions()` → `make_scene()` → `_concat_and_music()` nên cùng
hành vi. **Sau khi cài/đổi cv2 phải restart Flask** thì `_HAVE_CV2` mới cập nhật.

## Checklist QA sau khi render

1. **Tổng thời lượng bất biến**: `ffprobe -show_entries format=duration out.mp4`
   phải bằng tổng dur các cảnh (±0.2s). Lệch = có bug thêm/bớt frame.
2. **Đo dip YAVG**:
   ```
   ffprobe -f lavfi -i "movie=out.mp4,signalstats" \
     -show_entries frame=pts_time -show_entries frame_tags=lavfi.signalstats.YAVG -of csv=p=0
   ```
   Tại mỗi mối nối YAVG phải tụt xuống sàn đen (~12–16 tùy range encode — so với frame 0
   vốn đen tuyệt đối) rồi bật lại trong ~0.5s. Không có đáy = dip không ăn.
3. **Kiểm viền đen**: trích frame đầu/giữa/cuối mỗi cảnh
   (`ffmpeg -ss T -i out.mp4 -vframes 1 f.jpg`) — mép khung không được có dải đen
   ngoài 2 thanh letterbox 138px trên/dưới; nhân vật phải nằm trong vùng an toàn.
4. **Camera nhắm nhân vật**: cùng các frame đó, khung phải dịch/zoom về phía nhân vật
   theo chu kỳ push/pan/pull; in `film.subject_of(img)` để đối chiếu tọa độ detect.
5. Tốc độ tham chiếu: ~0.8x realtime (19s render / 24s video, 4 cảnh 1080p30, máy dev).

## Troubleshooting

- **Thiếu cv2** (`film._HAVE_CV2 == False`): rơi về `zoompan` của ffmpeg — crop pixel
  nguyên nên zoom giật nấc, chuyển cảnh thành chuỗi xfade `fadeblack` (TD=0.75, rút ngắn
  tổng thời lượng — app.py bù trừ). Cài: `pip install opencv-python` rồi **restart Flask**.
- **cv2 phải < 5**: venv đang ghim `opencv-python 4.14.0` — cv2 5.x bỏ
  `CascadeClassifier` nên animeface/Haar chết, chỉ còn YuNet (yếu hơn với anime).
  Nếu lỡ lên 5.x: `pip install "opencv-python<5"`.
- **Model animeface**: tự tải về `assets/film/models/lbpcascade_animeface.xml`
  (kèm `face_detection_yunet_2023mar.onnx`). Không mạng → tải tay từ
  `github.com/nagadomi/lbpcascade_animeface`, đặt đúng thư mục đó.
- **Camera không nhắm đúng người** (ảnh đông người / saliency lệch): ép tay
  `"focus": [x, y]` trong JSON phân cảnh — thắng mọi tầng detect.
- **Ra file khác ổ đĩa (C: vs D:)**: đã fix `shutil.move` trong `_concat_and_music`
  (trước dùng `os.replace` → WinError 17).
- **Xuất hiện "đen 2 lần" quanh title card**: card fade 0.6s đã khớp `_head_black=0.8`
  của cảnh 1 — nếu chỉnh `dip_dur` lớn hãy soát lại `make_card`.
