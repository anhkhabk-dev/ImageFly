---
name: anh-cai-dat
description: Kiểm tra và cài đặt mọi thứ ImageFly cần (Node.js, ffmpeg, HyperFrames, môi trường Python, tùy chọn giọng đọc VieNeu và Whisper). Dùng khi người dùng mới cài ImageFly, gõ "/anh-cai-dat", "kiểm tra máy làm video", hoặc khi một bước báo thiếu công cụ.
---

# Cài đặt ImageFly

`ROOT` là thư mục gốc ImageFly (Claude Code: `${CLAUDE_PLUGIN_ROOT}`; agent khác: thư mục repo đã clone).

## Bước 1. Kiểm tra

```bash
python "$ROOT/tools/imagefly.py" doctor
```

Đọc bảng. Dòng `THIẾU` ở nhóm bắt buộc (Node.js 22+, ffmpeg, ffprobe, ffmpeg loudnorm/afade, HyperFrames) thì báo người dùng tự cài kèm link trong cột ghi chú. Không tự cài phần mềm hệ thống.

## Bước 2. Cài phần Python

Thiếu "Môi trường Python": hỏi người dùng xác nhận một câu rồi chạy (nhẹ, chỉ numpy, scipy, soundfile, pillow):

```bash
python "$ROOT/tools/setup/doctor.py" --install
```

Chỉ khi người dùng muốn video có lời đọc (hoặc dòng "Giọng đọc" báo chưa cài): hỏi xác nhận (tải khoảng 2 đến 3 GB: gói `vieneu`, `faster-whisper`, model Whisper large-v3-turbo) rồi chạy nền:

```bash
python "$ROOT/tools/setup/doctor.py" --install --voice
```

Venv đặt ở `~/.imagefly/venv`. Nếu máy đã có `~/.motionfly/venv` (plugin MotionFly) thì dùng luôn, bỏ qua cài đặt.

## Kết thúc

Chạy lại bước 1. Thấy `SAN SANG` thì báo người dùng gõ `/video-tu-anh` kèm thư mục ảnh. Máy không có card NVIDIA vẫn chạy: giọng dùng CPU, nhạc dùng file người dùng hoặc nhạc tổng hợp bằng code.
