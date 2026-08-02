---
name: film-multi-shot
description: Nhiều ảnh cho 1 cảnh/beat (multi-shot per beat) khi build video film. Dùng khi cảnh dài >15s cần đổi ảnh theo tình tiết (chủ đạo / cận cảnh / quang cảnh) thay vì 1 ảnh đứng 30–90s, hoặc user chê "một ảnh trơ suốt cảnh".
---

# Film Multi-Shot — nhiều ảnh cho 1 cảnh (YC3)

`build_film_story.py` sinh 1–4 ảnh/cảnh (chủ đạo + phụ), `film.make_scene` đổi ảnh theo
nhóm câu trong cảnh như video mẫu "Chuyện Quê Xưa" (thay ảnh mỗi ~5–10s). **Timing tổng +
SRT BẤT BIẾN**: chỉ đổi NGUỒN ẢNH của từng group, tổng frame làm tròn TÍCH LŨY nên không
thêm/bớt frame nào.

## Cơ chế

1. **Schema JSON**: cảnh có thể khai `"shots"` = list ≤3 prompt PHỤ (ưu tiên tuyệt đối):
   ```json
   {"id": 3, "beat": "than_bai", "prompt": "Nhan, a thin kind Vietnamese man..., village at dusk",
    "shots": ["close-up of the incense bowl on the wooden altar",
              "wide shot of the village road at dusk, no people"],
    "subs": [{"vi": "..."}, {"vi": "...", "cut": true}, {"vi": "..."}]}
   ```
2. **Auto-derive rule-based** (`derive_shot_prompts`, KHÔNG gọi AI) khi JSON không có
   `"shots"`: shot 2 = `close-up detail shot, shallow depth of field, ` + **NGUYÊN VĂN
   toàn bộ prompt gốc** (character sheet nằm giữa prompt — cắt cụm sẽ vẽ lệch nhân vật);
   shot 3 = wide establishing `no people` (lọc bỏ các vế tả người bằng `_PERSON_WORDS`);
   shot 4 = extreme close-up vật thể ý nghĩa (giữ nguyên prompt).
3. **Luật số ảnh theo độ dài** (`_auto_shot_count`, est = `dur` hoặc số câu × 4s):
   **<15s → 1 ảnh, 15–35s → 2 ảnh, >35s → 3 ảnh** (ép tay tối đa 4).
4. **Phân bổ ảnh** (`_clip_alloc`): ảnh CHỦ ĐẠO (index 0, có nhân vật) MỞ và CHỐT cảnh,
   ảnh phụ xen giữa (`[0, phụ..., 0]`; 2 group → `[0,1]`); nhiều group hơn ảnh → lặp
   vòng ảnh phụ.
5. **Chia group theo nhịp lời thoại** (`_multi_groups`): sub có `"cut": true` → mở group
   mới ĐÚNG câu đó (marker kịch bản được tôn trọng); không có marker → chia cân bằng,
   nhịp đổi ảnh ~6.5s (mẫu 5–10s).
6. **Trong film.py**: `scene["clips"]` ≥2 ảnh tồn tại + ≥1 câu + `film_mode` + cv2 →
   `use_multi` (thắng nhánh fake-coverage `use_shots`). Mỗi group đi trọn đường YC1
   (subject-focused Ken Burns, motion đổi theo `idx = g + i` chu kỳ 5) + hạt YC2 trôi
   liên tục. **Giữa các group: CUT THẲNG (không dip)** — dip-to-black chỉ ở RANH GIỚI
   CẢNH (trans bake vào group cuối, head_black vào group đầu). `scene["focus"]` ép tay
   chỉ áp cho ảnh chủ đạo; ảnh phụ tự detect riêng.
7. **Cache ảnh phụ**: `assets/film/aibg/{slug}_scene{id}_s{k}_{hash8}.jpg`
   (`hash8 = md5(prompt_phụ + "|" + id)[:8]`) — đổi prompt không dính ảnh cũ, 2 phim
   khác nhau không đạp file nhau; ảnh chủ đạo giữ cache hash cũ của `ai_scene_bg`.

## Opts / CLI

| Khóa | Mặc định | Ý nghĩa |
|---|---|---|
| `shots_per_scene` (build) | `"auto"` | `auto` = theo luật độ dài; `1..4` = ép số ảnh mọi cảnh. |
| `auto_shots` (build) | `True` | `False` = không tự sinh prompt phụ (JSON không có `"shots"` → 1 ảnh như cũ). |
| CLI `--shots` | `auto` | `python build_film_story.py data/x.json --shots 2` |
| CLI `--no-auto-shots` | tắt | tắt auto-derive. |
| `scene["clips"]` (film.py) | — | List path ảnh trực tiếp (≥2 → bật multi-shot, không cần build_film_story). |
| `subs[k]["cut"]` | — | `true` = ép đổi shot/ảnh tại câu k. |

## Lệnh build mẫu

```bash
D:\dev\tool-multi-lang\venv\Scripts\python.exe build_film_story.py data/film_xxx.json          # auto
... build_film_story.py data/film_xxx.json --shots 1            # tắt multi-shot (1 ảnh/cảnh)
... build_film_story.py data/film_xxx.json --scenes 4 --music none --shots 3   # thử nhanh
```

## Checklist QA sau khi render

1. **Timing bất biến**: `ffprobe -show_entries format=duration` = tổng dur cảnh ±0.2s
   (test 2026-08-02: 3 cảnh 18+8+6 = 32s → đo 32.037s).
2. **Cut thẳng TRONG cảnh — dip chỉ ranh giới cảnh**: đo YAVG (signalstats): tại mốc đổi
   ảnh trong cảnh KHÔNG có đáy đen (test: min 34.5–43.7), tại ranh giới cảnh tụt sàn
   (test: 12.9–13.0, dip ~0.5s).
3. **Đúng thứ tự ảnh**: trích frame từng group — chủ đạo mở cảnh, phụ xen giữa, chủ đạo
   chốt cảnh (cảnh 4 câu/3 ảnh → thứ tự [0,1,2,0], cut tại 4.5/9/13.5s với cảnh 18s).
4. **Nhân vật nhất quán**: ảnh phụ close-up phải cùng nhân vật (auto-derive giữ nguyên
   văn prompt); wide shot KHÔNG có người.
5. **Camera đổi mỗi group**: framing các group khác nhau rõ (chu kỳ push/pan_r/pan_l/
   pushpan/pull theo `g+i`).

## Troubleshooting

- **Không đổi ảnh dù có "clips"**: cần ≥2 path TỒN TẠI + không phải video + ≥1 sub +
  `film_mode=True` + cv2 (`_scene_clips` lọc path chết). Thiếu cv2 → multi-shot tắt,
  dùng ảnh chủ đạo như cũ.
- **Ảnh phụ vẽ sai nhân vật**: prompt phụ trong JSON tự viết bị cắt mất character sheet
  — bắt chước auto-derive: LẶP NGUYÊN VĂN prompt chủ đạo trong prompt phụ.
- **Cắt ảnh sai chỗ so với lời thoại**: đánh dấu `"cut": true` vào câu muốn đổi ảnh —
  thắng luật chia ~6.5s.
- **Muốn 1 cảnh giữ 1 ảnh**: bỏ `"shots"` + build với `--no-auto-shots`, hoặc cảnh đó
  `"shots": []` vẫn bị auto → dùng `--shots 1` cho cả phim, hoặc để cảnh ngắn <15s.
- **Dip xuất hiện GIỮA cảnh**: bug — trans chỉ được bake vào group CUỐI, head_black
  group ĐẦU (xem `use_multi` trong `make_scene`); nếu thấy dip giữa cảnh, soát lại
  `trans_out`/`head_black` truyền vào `_kb_video` của các group giữa.
- **Ảnh phụ không tái sinh sau khi sửa prompt**: cache theo hash8 prompt — sửa prompt
  là ra file mới; muốn ép vẽ lại cùng prompt thì xóa file trong `assets/film/aibg/`.
