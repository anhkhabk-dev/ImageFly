---
name: video-tu-anh
description: Làm video từ ảnh và clip video có sẵn (slideshow có nhạc và hiệu ứng, hoặc có lời đọc tiếng Việt), khung 9:16 hoặc 16:9, xuất MP4; tiếng gốc của clip luôn bị bỏ, chỉ trộn giọng đọc và nhạc mới. Dùng khi người dùng gõ "/video-tu-anh", đưa thư mục ảnh hoặc clip và nói "làm video từ ảnh", "slideshow", "ghép ảnh thành video", "ghép clip", "video có nhạc từ ảnh", "thêm giọng đọc cho ảnh".
---

# Video từ ảnh (ImageFly)

`ROOT` là thư mục gốc của ImageFly: Claude Code dùng `${CLAUDE_PLUGIN_ROOT}`; agent khác (Antigravity...) dùng thư mục đã clone repo. Mọi bước chạy bằng một lệnh:

```bash
python "$ROOT/tools/imagefly.py" <lệnh> ...
```

Lệnh tự dùng môi trường Python của ImageFly (`~/.imagefly/venv`, hoặc `~/.motionfly/venv` nếu máy đã có). Dự án nằm ở `videos/<slug>/` trong thư mục đang làm việc. Lần đầu trong phiên chạy `... doctor`; chưa `SAN SANG` thì làm theo skill `anh-cai-dat`.

## Bước 1. Hiểu yêu cầu (hỏi khi thiếu, mỗi lần một câu, có phương án đề xuất)

| Cần biết | Mặc định |
|---|---|
| Thư mục ảnh | bắt buộc |
| Chế độ: `slideshow` (chỉ ảnh, nhạc, hiệu ứng), `voiceover` (có lời đọc) hay MV ca nhạc (có file bài hát, Bước 3c) | slideshow |
| Khung hình `9:16` hay `16:9` | 9:16, và khung 9:16 mặc định **phủ kín** (`fit: cover`) |
| Tiêu đề hiện đầu video | không |
| Nhạc: file của người dùng, hoặc `synth:calm|inspiring|upbeat|tech`, hoặc `none` | synth:inspiring |
| Màu hình `look`: natural, warm, cool, cinematic, vivid, bw | natural |

Khung hình: **không hỏi, không tự chọn 16:9.** Người dùng không nói gì về khung hình thì dùng 9:16 (phủ kín); chỉ dùng 16:9 khi họ nêu rõ (hoặc nói nơi đăng là YouTube, TV, trang web).

Người dùng nói "tự làm hết" thì bỏ các cổng duyệt, chỉ báo cáo cuối.

## Bước 2. Tạo dự án và xem ảnh

```bash
python "$ROOT/tools/imagefly.py" new <slug> --images "<thư mục ảnh>" --aspect 9:16 --mode slideshow --title "..." --look warm
```

Lệnh xoay ảnh theo EXIF, giảm cỡ, in danh sách `i01...` (kích thước, dọc hay ngang). Thứ tự mặc định theo tên file; `--order date` theo ngày chụp. **Mở xem ảnh** (Read từng ảnh hoặc ghép tờ ảnh bằng ffmpeg) để hiểu nội dung, rồi chỉnh `videos/<slug>/images.json` khi cần:

- `"skip": true` bỏ ảnh; đổi thứ tự bằng cách sắp lại các phần tử.
- **Clip video:** thư viện có thể trộn ảnh và video (`.mp4 .mov .m4v .mkv .webm .avi .mts .3gp`). Khi nạp, clip được chuẩn hóa (H.264 30 fps, tối đa 1920 cạnh dài, tự xoay đúng chiều) và **bỏ hết tiếng gốc** (`-an`), để tiếng trong video chỉ còn giọng đọc và nhạc mới. Không bao giờ dùng tiếng của clip. Clip dùng chung `fit`, `focus`, `effect`, `transition`, `caption` như ảnh. Riêng clip:
  - `"trim_start": giây`: điểm bắt đầu lấy trong clip.
  - `"len": giây`: số giây dùng (slideshow mặc định `clip_s` = 4 giây trong `brief.json`, tự cắt trùng nhịp nhạc). Chế độ có lời: clip phát suốt thời lượng của cảnh.
  - Clip ngắn hơn cảnh thì giữ khung hình cuối đến hết cảnh (`plan` in lưu ý).
  - Clip dọc trong video ngang (và ngược lại) tự đặt giữa trên nền mờ, như ảnh. `sweep` dùng được cho clip rộng trong khung dọc.
- `"focus": [x, y]` (0 đến 1) điểm nhấn: zoom và cắt hướng về đó (ví dụ người đang hàn ở góc phải dưới: `[0.8, 0.7]`).
- `"focus_to": [x]` (0 đến 1): điểm nhấn thứ hai. Khi ảnh rộng hơn khung nhiều (ảnh ngang trong khung dọc) và `fit` là `cover`, camera tự **quét ngang** (`sweep`) từ `focus` sang `focus_to`, ví dụ ảnh chụp đôi: quét từ mặt người này sang mặt người kia. Xem ảnh, đặt `focus` đúng vào mặt người (x tính theo chiều rộng ảnh gốc), rồi kiểm tra khung hình đầu, giữa, cuối của từng cảnh trước khi giao.
- **Khung 9:16 mặc định phủ kín** (`new` ghi `fit: cover` vào `brief.json`): ảnh ngang bị cắt còn khoảng 40% chiều rộng, nên **bắt buộc đặt `focus` (và `focus_to` cho ảnh quét) vào chủ thể của từng ảnh** rồi kiểm khung hình đầu, giữa, cuối. Người dùng muốn ảnh nguyên khổ giữa nền mờ thì đặt `fit: "auto"` trong `brief.json`. Khung 16:9 vẫn mặc định `auto`.
- `"fit": "cover" | "contain"` cho riêng ảnh này (ghi đè `fit` trong brief). `fit` trong `brief.json`: `cover` (phủ kín, mặc định cho khung 9:16 do `new` ghi), `contain` (nguyên khổ giữa nền mờ), `auto` (tự chọn: phủ kín nếu tỉ lệ ảnh gần khung, ngược lại nguyên khổ trên nền mờ; mặc định cho khung 16:9). Clip video theo cùng quy tắc.
- `"effect"`: `zoom-in`, `zoom-out`, `push-focus`, `pan-left`, `pan-right`, `pan-up`, `pan-down`, `drift`, `none`.
- `"transition"`: `fade`, `slide`, `slideup`, `zoom`, `wipe`.
- `"caption"`: chú thích ngắn hiện dưới ảnh (chế độ slideshow).
- `"beats"`: số nhịp nhạc ảnh này kéo dài (mặc định `shot_beats` trong brief).

Cài đặt chung ở `brief.json`: `look`, `transition` (`mix` xoay vòng), `fit` (`auto` tự chọn phủ kín hay đặt giữa trên nền mờ), `music`, `shot_beats`, `shot_s`, `duration_s`, `burn_captions`, `voice`.

Ảnh tỉ lệ lệch nhiều so với khung được đặt giữa trên nền mờ của chính ảnh đó (không cắt mất nội dung); lệch ít thì phủ kín và quét máy quay (pan).

## Tiêu đề động

Có `title` trong `brief.json` thì tiêu đề **in hoa**, hiện to giữa khung lúc mở đầu (từng chữ bật lên, kèm `subtitle` nếu có), rồi thu nhỏ bay về một góc. Hai chế độ (`title_mode`):
- `fixed` (mặc định): ở yên một góc suốt video. `title_corner` chọn góc (`top-left`, `top-right`, `bottom-left`, `bottom-right`); bỏ trống thì tự chọn góc xa mọi điểm nhấn `focus` nhất để không che chủ thể ở ảnh nào.
- `roam`: đổi góc và đổi màu theo thời gian (`move`: chữ gợn sóng, `pop`: nảy lên), mỗi lần đổi chọn góc xa chủ thể của ảnh đang hiện.

Kết quả nằm ở `title_plan` trong `shots.json` (in ra khi chạy `plan`).

Agent được quyền tự thiết kế: ghi `brief.json` các khóa `title_plan` (danh sách `{"t": giây, "pos": "top-left|top-right|bottom-left|bottom-right", "color": "#RRGGBB", "hop": "move|pop"}`), `title_colors` (bảng màu), `title_intro_s`, `title_hop_s`, `title_upper: false` (không in hoa). `title_corner_text`: chữ riêng hiện ở góc sau phần mở đầu (ví dụ tiêu đề lúc mở là "ĐẨY NHANH TIẾN ĐỘ" + `subtitle` cỡ 45, về góc đổi thành "SIÊU DỰ ÁN LẤN BIỂN CẦN GIỜ"); bỏ trống thì góc giữ tiêu đề chính. `no_lite: true`: chỉ xuất bản chính, không sinh `-nhe.mp4`. `title_line2`: dòng nhỏ màu trắng dưới tiêu đề, hiện khi tiêu đề đã về góc (ví dụ số điện thoại, tên fanpage). Khung dọc dùng cỡ chữ tiêu đề nhỏ hơn để tiêu đề nằm trọn một dòng. Chữ phải đọc được trên mọi ảnh: không đặt màu quá tối, giữ nền mờ phía sau (đã có sẵn khi ở góc).

Khung hình đầu tiên (giây 0) hiện ngay ảnh đầu, không mờ từ nền đen, nên ảnh đại diện của file MP4 không bị đen: **chọn ảnh đẹp nhất làm ảnh đầu tiên** (sắp lại `images.json`). Nhạc nền mặc định `music_db: -11` (nhạc so với giọng khi giọng đọc), mức đã chốt là hợp lý.

## Nhạc nền (brief.music)

| Giá trị | Nghĩa |
|---|---|
| `synth:calm|inspiring|upbeat|tech` | nhạc tổng hợp bằng code theo tâm trạng |
| `score` hoặc `score:<đường dẫn>` | soạn từ bản nhạc `music/score.json` (giai điệu, hợp âm, nhịp, nhạc cụ) |
| `<đường dẫn file>` | file nhạc người dùng đã chuẩn bị; `music_start_s` chọn đoạn bắt đầu (ví dụ vào thẳng đoạn điệp khúc) |
| `["a.mp3", "b.mp3"]` | nhiều bài nối nhau, mờ chồng 2 giây |
| `none` | không nhạc |

Người dùng yêu cầu **nhạc theo giai điệu hoặc bài hát cụ thể**:
- Giai điệu **thuộc phạm vi công cộng hoặc dân gian** (Ode to Joy, Au Clair de la Lune, Bắc Kim Thang...) hoặc người dùng đưa nốt/hợp âm: viết `music/score.json` theo mô tả ở đầu `tools/music/score.py` rồi đặt `music: "score"`. Cho nghe thử (`music` rồi `mix`) và chỉnh nhịp, nhạc cụ, hợp âm theo góp ý.
- Bài hát **còn bản quyền** (nhạc thương mại): không tái tạo giai điệu hay lời. Đề xuất: (1) người dùng đưa file nhạc đã có (hoặc đã mua giấy phép), (2) soạn một bản **gốc theo phong cách/tâm trạng** tương tự (không sao chép giai điệu), (3) người dùng tạo nhạc bằng công cụ AI nhạc (Suno, Udio...) theo mô tả rồi đưa file vào. Không tự tải nhạc từ web.
- Nhạc tổng hợp bằng code nghe đơn giản (không phải thu âm thật); nói rõ điều này với người dùng.

## Hiệu ứng âm thanh (sfx)

**Người dùng đưa file âm thanh (`music` là file hoặc danh sách file) thì chỉ dùng file đó**: tự bỏ nhạc tổng hợp và hiệu ứng âm thanh do agent tạo (`sfx: "auto"`). Chỉ khi người dùng nói rõ muốn thêm sfx lên trên file của họ thì đặt `sfx: true`. Chế độ có lời đọc vẫn giữ giọng đọc vì người dùng đã yêu cầu.

Nhạc tổng hợp, nhạc soạn từ `score.json` thì sfx mặc định bật (`sfx: "auto"`, ép bằng `true`/`false`, chỉnh `sfx_db`): `tools/audio/sfx.py` tổng hợp bằng code và đặt đúng thời điểm: tiếng gió quét (slide, slideup), swish (wipe), tiếng trầm nhẹ (zoom), hơi thở mềm (fade), lấp lánh lúc tiêu đề hiện, chuông ngắn mỗi lần tiêu đề đổi góc. Danh sách sự kiện ở `sfx.json`. Không có file bên thứ ba nên không dính bản quyền. Người dùng muốn bỏ hoặc nhỏ đi: `sfx: false` hoặc `sfx_db: -6`.

## Bước 3a. Chế độ slideshow

```bash
python "$ROOT/tools/imagefly.py" build videos/<slug> --name <ten-file>
```

`build` chạy lần lượt: `plan` (chia cảnh theo nhịp nhạc, chọn hiệu ứng, chuyển cảnh), `music`, `mix` (-14 LUFS), `compose` (viết từng cảnh HTML), rồi `render` (kiểm tra HyperFrames, render, ghép âm). Render chạy nền, khoảng 2 giây máy cho mỗi giây video; log ở `renders/render.log`.

## Bước 3b. Chế độ voiceover

1. Viết `videos/<slug>/script.json`:

```json
{"title": "...", "voice": "Ngọc Huyền", "aspect": "9:16",
 "scenes": [
  {"id": "s1", "say": "Câu một. Câu hai.", "images": ["i01", "i02"]},
  {"id": "s2", "say": "Công nhân hàn cấu kiện. Việc kéo dài cả ban đêm.", "images": ["i03", {"img": "i04", "kw": "ban đêm"}]}
 ],
 "pron": {}}
```

   - Mỗi cảnh có `images` (một hoặc nhiều). Nhiều ảnh trong một cảnh: chia đều, hoặc đặt `kw` (từ trong lời đọc, viết đúng chữ) để ảnh đó hiện đúng lúc từ ấy được đọc.
   - Luật lời đọc: văn nói, mỗi câu dưới 25 từ, số viết chữ số, không emoji, `|` tạo khoảng nghỉ. Chỉ viết điều thấy trong ảnh hoặc người dùng cung cấp; số liệu, tên, ngày tháng không có thì không bịa.
   - Giọng: 25 giọng có sẵn; đổi ở `voice`. Từ tiếng Anh/viết tắt đọc sai thì thêm vào `pron` (ví dụ `"MCP": "em xi pi"`).
2. Gửi người dùng bảng cảnh, lời đọc, ảnh gán; chờ duyệt (trừ khi "tự làm hết").
3. `python "$ROOT/tools/imagefly.py" build videos/<slug> --name <ten-file>` (tự sinh giọng, chấm bằng Whisper, nhạc tự hạ khi có lời, phụ đề in lên hình và `phude.srt`).
4. Đọc `voice.log`: câu `WEAK` thật thì viết lại câu (cần chủ ngữ tiếng Việt, tránh câu quá ngắn) hoặc thêm `pron`, rồi chạy lại; chỉ câu sửa được sinh lại.

## Bước 3c. Chế độ MV ca nhạc (ảnh cắt theo lời bài hát)

Dùng khi người dùng đưa **file bài hát (mp3) kèm ảnh** và muốn làm MV. Nhạc là file của họ nên chỉ dùng file đó (không nhạc tổng hợp, không sfx).

1. `new <slug> --images "<thư mục ảnh>" --aspect 9:16 --title "<tên bài>" --look cinematic`, rồi đặt `brief.json` `music` là đường dẫn tuyệt đối file mp3.
2. `python "$ROOT/tools/imagefly.py" lyrics videos/<slug>`: nhận lời bằng Whisper, ghi `lyrics.json` (mốc giây từng câu). Lời có thể sai chính tả, chỉ dùng để hiểu ý và tìm mốc câu; khoảng trống giữa các câu là đoạn nhạc không lời (intro, interlude, outro). Câu quảng cáo "subscribe…" là nhận nhầm, đã tự loại.
3. **Xem từng ảnh** rồi ghép ảnh với ý của từng câu: cô độc, ký ức hạnh phúc, chia ly, hy vọng, kết. Quy tắc ghép:
   - Cắt cảnh đúng ranh giới câu hát; điệp khúc vào bằng chuyển cảnh mạnh hơn (`slideup`, `zoom`), còn lại chủ yếu `fade`.
   - Cận cảnh cảm xúc: `zoom-in` chậm. Cô độc, xa cách, bình minh: `zoom-out`. Đi, níu kéo: `pan-*`, `push-focus`.
   - Ảnh ít hơn số cảnh thì dùng lại, nhưng cách nhau xa và luôn đi với đúng ý của câu; nói rõ với người dùng và đề nghị thêm ảnh.
   - Đoạn không lời dùng ảnh ký ức hoặc ảnh nhạc cụ; cảnh cuối nên về lại ảnh mở đầu cho khép vòng.
4. Viết `videos/<slug>/mv.json`: `{"lead": 0.3, "cuts": [{"end": 14.8, "img": "i10", "effect": "zoom-in", "transition": "fade"}, ...]}`. `end` là giây kết thúc cảnh trong bài; `lead` cho chuyển cảnh bắt đầu sớm một chút để hình đổi cùng lúc câu hát; cảnh cuối có `end` bằng độ dài bài trừ 1 giây (đuôi). Có thể thêm `focus`, `focus_to`, `fit` cho từng cảnh.
5. `python "$ROOT/tools/imagefly.py" mv videos/<slug>`: ghi `images.json` (ảnh dùng lại được nhân bản id mới, `beats` là số giây của cảnh), `brief.json` (`shot_s: 1`, `shot_beats: 1`), sao lưu bản cũ vào `_backup/`, rồi chạy `plan`. Kiểm `total` bằng độ dài bài.
6. `build videos/<slug> --name <ten-file>`; bản sửa đặt tên mới (`-v2`), không ghi đè bản cũ. Kiểm như Bước 4 và báo cho người dùng bảng ảnh-theo-lời.

## Bước 4. Kiểm và giao

- `ffprobe` file trong `renders/`: đúng kích thước (1080x1920 hoặc 1920x1080), 30 fps, có luồng aac, thời lượng bằng `total` trong `shots.json`.
- `python "$ROOT/tools/audio/mix.py" measure <file.mp4>`: I trong -14 ± 0,5 LUFS.
- Trích khung bằng ffmpeg (đầu, giữa các chỗ chuyển cảnh, cuối) và xem lại: chữ tràn mép, ảnh bị cắt mất phần quan trọng (chỉnh `focus` hoặc `fit`), cảnh tối.
- Sửa rồi chạy lại từ bước cần thiết: đổi hiệu ứng/thứ tự → `plan`, `compose`, `render`; đổi nhạc → `music`, `mix`, `compose`, `render`.

Báo cáo cuối: đường dẫn MP4 (và `-nhe.mp4`, `phude.srt` nếu có), độ dài, khung hình, nguồn nhạc, số đo loudness, câu nào đã sửa phát âm, ảnh nào đã bỏ hoặc cắt nhiều.

## Luật

- Không tải nhạc hay ảnh từ web về đóng gói; chỉ dùng file người dùng đưa hoặc nhạc tổng hợp bằng code. Nhạc của người dùng: nhắc họ tự chịu trách nhiệm bản quyền nếu video đăng công khai.
- Ảnh gốc không bị sửa: bản chuẩn hóa nằm ở `assets/` của dự án.
- Không xóa file của người dùng; dọn `videos/<slug>/` chỉ khi người dùng yêu cầu.
