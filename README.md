# ImageFly: ảnh có sẵn thành video

Công cụ dòng lệnh chạy trong agent (Claude Code, Antigravity...) biến một thư mục ảnh thành video MP4: quét máy quay (Ken Burns), chuyển cảnh, nhạc nền, tiêu đề, phụ đề, và tùy chọn lời đọc tiếng Việt. Khung **9:16** hoặc **16:9**.

Phát triển từ [MotionFly](https://github.com/andyluu98/MotionFly), thêm đường vào bằng ảnh có sẵn và chế độ slideshow.

```
/video-tu-anh Làm video 9:16 từ thư mục ảnh D:\Anh\CanGio, có nhạc, tiêu đề "Công trường Cần Giờ", tông màu ấm
/video-tu-anh Làm video 16:9 có lời đọc từ ảnh trong D:\Anh\CanGio
```

## Hai chế độ

| Chế độ | Làm gì |
|---|---|
| `slideshow` | Chỉ ảnh, nhạc và hiệu ứng. Mỗi ảnh dài theo nhịp nhạc, chuyển cảnh xoay vòng. |
| `voiceover` | Có lời đọc (VieNeu, chấm phát âm bằng Whisper). Ảnh hiện theo lời, nhạc tự hạ khi có lời, phụ đề in lên hình và xuất `.srt`. |

## Tính năng

- Nạp ảnh tự động: xoay theo EXIF, giảm cỡ, sắp theo tên hoặc ngày chụp; ảnh gốc không bị sửa.
- Ảnh lệch tỉ lệ nhiều so với khung được đặt giữa trên nền mờ của chính nó; lệch ít thì phủ kín và quét máy quay.
- 9 hiệu ứng máy quay: `zoom-in`, `zoom-out`, `push-focus`, `pan-left/right/up/down`, `drift`, `none`; điểm nhấn `focus` cho từng ảnh.
- 5 kiểu chuyển cảnh: `fade`, `slide`, `slideup`, `zoom`, `wipe` (hoặc `mix` xoay vòng).
- 6 tông màu: `natural`, `warm`, `cool`, `cinematic`, `vivid`, `bw`.
- Tiêu đề in hoa, hiệu ứng chữ bật lên, tự bay về góc và đổi góc, đổi màu theo thời gian (góc chọn xa chủ thể trong ảnh); có thể tự thiết kế bằng `title_plan`.
- Nhạc: file của anh (chọn đoạn bắt đầu, nối nhiều bài, tự đo nhịp để cắt ảnh theo nhịp), nhạc tổng hợp bằng code (4 mood), **nhạc soạn từ bản nhạc** `score.json` (giai điệu, hợp âm, nhạc cụ), hoặc không nhạc. Trộn chuẩn -14 LUFS.
- Hiệu ứng âm thanh tổng hợp bằng code đặt đúng chỗ chuyển cảnh và khi tiêu đề đổi góc (gió quét, swish, tiếng trầm, chuông, lấp lánh).
- **Có file âm thanh của anh thì chỉ dùng file đó:** tự bỏ nhạc tổng hợp và hiệu ứng âm thanh do agent tạo (đặt `sfx: true` nếu anh muốn thêm sfx lên trên).
- Chú thích từng ảnh, vùng an toàn cho mỗi khung hình.

**Về nhạc có bản quyền:** ImageFly không tái tạo giai điệu hay lời của bài hát thương mại. Dùng file nhạc anh có quyền sử dụng, bản nhạc phạm vi công cộng, hoặc nhạc gốc soạn theo phong cách.

## Cài đặt

Cần có sẵn: Node.js 22+, Python 3.10+, [ffmpeg](https://ffmpeg.org/download.html) trong PATH. Nên có [uv](https://docs.astral.sh/uv/).

**Claude Code**

```
/plugin marketplace add anhkhabk-dev/ImageFly
/plugin install imagefly@imagefly
/anh-cai-dat
```

**Antigravity và agent khác:** clone repo, để agent đọc `AGENTS.md` (hoặc chép `skills/` vào thư mục skills của agent). Chạy thử:

```bash
python tools/imagefly.py doctor                       # kiểm tra máy
python tools/setup/doctor.py --install [--voice]      # cài phần Python còn thiếu
```

`--install` chỉ cài gói nhẹ cho slideshow; `--voice` tải thêm giọng đọc và Whisper (khoảng 2 đến 3 GB).

## Dùng trực tiếp bằng dòng lệnh

```bash
python tools/imagefly.py new can-gio --images "D:\Anh\CanGio" --aspect 16:9 --title "Công trường Cần Giờ" --look warm
python tools/imagefly.py build videos/can-gio --name can-gio
```

Kết quả ở `videos/can-gio/renders/can-gio.mp4`. Chỉnh `images.json` (thứ tự, `skip`, `focus`, `effect`, `transition`, `caption`, `beats`) và `brief.json` (`look`, `music`, `shot_s`, `duration_s`...) rồi chạy lại `build`. Các lệnh lẻ: `plan`, `music`, `mix`, `compose`, `render`, `voice`.

## Cấu trúc

```
skills/      video-tu-anh (quy trình), anh-cai-dat
tools/       imagefly.py (CLI), assemble.py, timeline.py, audio/mix.py, music/synth.py, voice/, setup/
templates/   font Be Vietnam Pro
vendor/      code chép từ repo khác, giấy phép gốc
AGENTS.md    hướng dẫn cho agent không phải Claude Code
```

## Nguồn và giấy phép

Code: MIT ([LICENSE](LICENSE)). Phần chép từ MotionFly, bestagentkits, Google Fonts giữ giấy phép gốc: xem [NOTICE.md](NOTICE.md). Repo không kèm nhạc hay ảnh của bên thứ ba.
