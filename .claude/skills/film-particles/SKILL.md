---
name: film-particles
description: Bật/tinh chỉnh lớp hạt bay (đom đóm / bụi sáng) procedural khi build video film. Dùng khi build film muốn thêm sinh khí đêm/hoàng hôn, hoặc user chê video "chết"/tĩnh/thiếu sinh khí dù camera đã chuyển động.
---

# Film Particles — đom đóm / bụi nắng overlay (YC2)

Lớp hạt sáng procedural trong `film.py` (repo `D:\dev\tool-multi-lang`), không cần asset
ngoài: 10–25 hạt/khung 2–6px có glow gaussian, trôi chậm lên trên + dao động sin ngang +
nhấp nháy alpha (đom đóm). Bắt chước lớp đốm sáng của video mẫu "Chuyện Quê Xưa".

## Cơ chế

1. **Vẽ TRỰC TIẾP trong vòng frame của `_kb_video`, SAU fade/trans/head_black**
   (`_particles_draw`, cộng additive `cv2.add` sprite nhỏ precompute — không blur cả
   frame). Vì vẽ sau fade nên **hạt KHÔNG chìm đen theo dip-to-black** — đúng video mẫu:
   hạt + phụ đề + watermark nằm layer trên, không fade theo cảnh. Phụ đề overlay ở bước
   ffmpeg sau đó → hạt tự nhiên nằm DƯỚI phụ đề.
2. **Deterministic theo seed cảnh**: `_particle_field(seed=i, preset)` dùng
   `np.random.RandomState(i)` (i = chỉ số cảnh) → render lại ra đúng vị trí từng hạt
   (mean|diff| = 0, không phá zoomblend/QA). Trong cảnh nhiều shot/group, `t0` cộng dồn
   qua group → hạt trôi LIÊN TỤC xuyên các cú cut trong cảnh.
3. **Chuyển động**: trôi lên 10–30 px/s (wrap đáy khung, lề M=48px vào/ra êm), sin ngang
   biên độ 10–40px chu kỳ 3–8s, nhấp nháy alpha chu kỳ 1.5–4.5s, pha lệch từng hạt.
4. **Preset tính 1 LẦN/CẢNH theo ảnh chủ đạo** (`clip` = `clips[0]` nếu multi-shot):
   downsample 64×36 → mean HSV. Cảnh nhiều ảnh khác tông chấp nhận 1 preset chung.

## Bảng preset + điều kiện auto

| Preset | Màu (RGB) | Alpha | Số hạt | Auto chọn khi (mean HSV ảnh chủ đạo) |
|---|---|---|---|---|
| `warm` | 255,190,90 vàng ấm | 0.85 | 12–20 | V < 150 VÀ mean R > mean B + 8 (tối + ấm: hoàng hôn, đèn dầu) |
| `green` | 180,220,120 xanh đom đóm | 0.80 | 12–20 | V < 150 VÀ không ấm (tối + lạnh: đêm) |
| `dust` | 245,240,235 trắng mờ | 0.32 | 14–25 | V ≥ 150 (cảnh sáng ngày — bụi nắng, alpha thấp) |

Mode `firefly` = ép nhóm đom đóm nhưng vẫn chọn `warm`/`green` theo tông ấm/lạnh;
mode `dust` = ép bụi nắng; `none` = tắt.

## Opts

| Khóa | Mặc định | Ý nghĩa |
|---|---|---|
| `opts["particles"]` | `"auto"` | `none` \| `firefly` \| `dust` \| `auto` — áp cho cả phim. |
| `scene["particles"]` | — | Ghi đè per-scene trong JSON phân cảnh (vd cảnh trong nhà → `"none"`). |

Chỉ có ở đường cv2 (`_kb_video`); lỗi phân tích ảnh → bỏ hạt cảnh đó, không chặn phim.

## Lệnh build mẫu

```bash
D:\dev\tool-multi-lang\venv\Scripts\python.exe build_film_story.py data/film_xxx.json
# build_film_story.py đã set particles="auto" trong opts; ép tắt 1 cảnh:
#   trong JSON: {"id": 5, "particles": "none", ...}
```

## Checklist QA sau khi render

1. **Hạt nhìn thấy**: trích frame giữa cảnh (`ffmpeg -ss T -i out.mp4 -vframes 1 f.png`)
   — thấy các đốm glow nhỏ; cảnh sáng (dust) mờ hơn nhiều là ĐÚNG (alpha 0.32).
2. **Hạt vẫn sáng lúc dip**: trích frame ngay đáy dip (mối nối cảnh) — nền đen tuyệt đối
   nhưng các hạt vẫn glow (test 2026-08-02: frame t=17.97/25.97 pass).
3. **Preset đúng tông**: in `film._particle_preset(img, "auto")` đối chiếu bảng trên.
4. **Determinism**: render 2 lần → md5 file trùng nhau (test: equal=True).
5. **Overhead**: hạt cộng ~14% thời gian render nhánh cv2 (vẽ additive vùng nhỏ);
   test 3 cảnh 32s 1080p30 vẫn ~1.1–1.2x realtime cả pipeline.

## Troubleshooting

- **Không thấy hạt**: thiếu cv2 (`film._HAVE_CV2 == False`) → fallback zoompan BỎ QUA
  hạt (by design). Cài `opencv-python<5` rồi restart Flask.
- **Cảnh sáng "không có hạt"**: dust alpha 0.32 rất nhẹ — nhìn kỹ vùng trời/đồng; muốn
  rõ hơn ép `scene["particles"]="firefly"` (chỉ nên cho hoàng hôn/đêm).
- **Preset sai tông** (vd cảnh đêm ra vàng ấm): ảnh có nguồn lửa lớn kéo mean R lên —
  ép `scene["particles"]` per-scene.
- **Hạt "nhảy" giữa 2 lần render**: chỉ xảy ra nếu ai đó đổi seed khỏi chỉ số cảnh —
  giữ nguyên `_particle_field(i, ...)`, KHÔNG dùng random không seed.
- **Hạt đè lên chữ**: không thể — phụ đề overlay ở bước ffmpeg SAU khi hạt đã vẽ vào
  bg; nếu thấy đè là do sửa thứ tự filter trong `make_scene`.
