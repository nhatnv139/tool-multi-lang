---
name: film-particles
description: Bật/tinh chỉnh lớp hạt bay (đom đóm / bụi sáng) procedural khi build video film. Dùng khi build film muốn thêm sinh khí đêm/hoàng hôn, hoặc user chê video "chết"/tĩnh/thiếu sinh khí dù camera đã chuyển động.
---

# Film Particles — đom đóm / bụi nắng overlay (YC2)

Lớp hạt sáng procedural trong `film.py` (repo `~/project/tool-multi-lang`), không cần asset
ngoài: hạt có glow gaussian, trôi chậm lên trên + dao động sin ngang + nhấp nháy alpha
(đom đóm). Bắt chước lớp đốm sáng của video mẫu "Chuyện Quê Xưa".

> **Cập nhật 2026-09-04** — ba thứ đã đổi, số cũ bên dưới không còn đúng:
> 1. Các num độ đậm tách ra thành hằng `FLY_*` ở đầu `film.py`, **chỉ áp cho lớp đom đóm**
>    (`blink=True`); lớp bụi giữ số cũ, không thì bụi nắng ban ngày nổi thành đốm trắng.
> 2. `auto` **không còn đoán ngày/đêm bằng độ sáng ảnh** — nó đọc lời tả `@bg`.
> 3. Kịch bản đè được bằng `@fx` viết thẳng trong `content.md`.

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

| Preset | Màu (BGR) | Alpha | Số hạt | Auto chọn khi |
|---|---|---|---|---|
| `warm` | 70,195,255 vàng ấm | 1.00 | 46–66 | `@bg` nói ĐÊM, không phải đèn dầu, ảnh tông ấm |
| `green` | 120,240,200 vàng-xanh | 1.00 | 46–66 | `@bg` nói ĐÊM, không phải đèn dầu, ảnh tông lạnh |
| `dust` | 235,240,245 trắng mờ | 0.30 | 34–52 | còn lại (ban ngày) |
| `dust` đậm | như trên | 0.42 | 30–44 | ĐÊM nhưng là đặc tả dưới đèn dầu (`P-VANG`) |

**Luật auto** (`_p_canh_dem` + `_p_den_dau`):

- `@bg` có `night` `moonlit` `starlit` `dusk` `lantern` `oil-lamp`… mà không có `morning`
  `daylight` `sunlit`… → **đêm**. Ngược lại → **ngày**. Không đoán được → coi là ngày:
  đom đóm là hiệu ứng mạnh, chỉ thả khi kịch bản nói rõ.
- Đêm **nhưng** `@bg` có chữ ký đèn dầu (`single oil-lamp flame`, `lamplight`) → đặc tả
  trong nhà → **bụi trong quầng đèn**, không phải đom đóm.

⛔ **Đừng quay lại đo độ sáng pixel.** Đã thử ngưỡng V<150: tranh tông trầm nên 19/20 ảnh
bài 17 bị coi là đêm, đom đóm bay giữa cánh đồng buổi sáng. Ảnh cảnh đêm (V=110,7) còn
sáng hơn ảnh ban ngày (V=72,5) — pixel không tách được ngày/đêm cho loại tranh này.

## Opts

| Khóa | Mặc định | Ý nghĩa |
|---|---|---|
| `opts["particles"]` | `"auto"` | `none` \| `firefly` \| `dust` \| `smoke` \| `mist` \| `leaves` \| `auto` — cả phim. |
| `scene["particles"]` | — | Ghi đè từng cảnh. Trang `/film` lấy từ dòng `@fx` trong kịch bản. |

**`@fx` — cách dùng thật cho kênh Chuyện Quê Xưa.** Viết trong `content.md` ngay dưới `@bg`:

```
@fx bui        <!-- trong chuồng trâu, không phải ngoài trời -->
```

Nhận `domdom` · `bui` · `khoi` · `may` · `la` · `none`, ghép bằng `+`. `expand_bg.py` mang
nó sang `content-film.md`; chú thích cùng dòng được bóc. Cần vì prompt `@bg` bung từ `@set`
nên cảnh trong nhà vẫn dính đầy chữ ngoài trời — không luật từ khoá nào đoán đúng hết.

Chỉ có ở đường cv2 (`_kb_video`); lỗi phân tích ảnh → bỏ hạt cảnh đó, không chặn phim.

## Lệnh build mẫu

```bash
cd ~/project/tool-multi-lang && .venv/bin/python app.py     # trang /film, cổng 5001
```

⛔ **`python3 app.py` là mất sạch hạt bay** — xem Troubleshooting bên dưới.

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

- **Không thấy hạt**: gần như luôn là `film._HAVE_CV2 == False` → nhánh zoompan BỎ QUA hạt
  (by design), **không log gì cả**. Nguyên nhân hay gặp nhất không phải thiếu thư viện mà là
  **chạy sai trình thông dịch**: `python3` hệ thống không có cv2, `.venv/bin/python` mới có.
  Mất theo cả chuyển động máy quay và dip-to-black. Kiểm:
  `.venv/bin/python -c "import film; print(film._HAVE_CV2)"` phải in `True`.
  Đánh đổi khi bật: nhánh cv2 vẽ từng frame bằng Python nên chậm ~2×.
- **Cảnh sáng "không có hạt"**: dust alpha 0.30 rất nhẹ — đúng thiết kế, đừng vặn lên.
- **Đom đóm mờ quá**: vặn `FLY_*` ở đầu `film.py`. Num ăn thua nhất là `FLY_BLINK_MIN`
  (độ sáng GIỮA hai lần nháy) — số cũ 0,06 làm hạt tắt hẳn nên chỉ 7–11/33 con nhìn thấy
  được tại một thời điểm; giờ 0,22, đom đóm vẫn âm ỉ như ngoài đời.
- **Thả sai cảnh** (đom đóm trong nhà, hoặc giữa ban ngày): ép `@fx` cho shot đó.
- **Hạt "nhảy" giữa 2 lần render**: chỉ xảy ra nếu ai đó đổi seed khỏi chỉ số cảnh —
  giữ nguyên `_particle_field(i, ...)`, KHÔNG dùng random không seed.
- **Hạt đè lên chữ**: không thể — phụ đề overlay ở bước ffmpeg SAU khi hạt đã vẽ vào
  bg; nếu thấy đè là do sửa thứ tự filter trong `make_scene`.
