# Ghi nguồn (NOTICE)

ImageFly dựa trên [MotionFly](https://github.com/andyluu98/MotionFly) (MIT, © andyluu98) và các dự án mã nguồn mở dưới đây. Phần chép về giữ giấy phép gốc; văn bản giấy phép nằm trong `vendor/licenses/`.

## Chép từ MotionFly (MIT)

| Trong repo | Nguồn trong MotionFly | Đã sửa gì |
|---|---|---|
| `tools/assemble.py` | `tools/assemble.py` | Mỗi cảnh một track riêng (chuyển cảnh chồng nhau), phụ đề in lên hình chỉ khi `burn_captions`, track phụ đề và âm thanh đổi số |
| `tools/timeline.py` | `tools/timeline.py` | Không sửa (dùng lại phần cắt phụ đề và tìm từ khóa) |
| `tools/audio/mix.py` | `tools/audio/mix.py` | Thêm `music_only` (slideshow không lời), bỏ `-shortest` khi ghép, bớt thông báo phụ đề |
| `tools/music/synth.py` | `tools/music/synth.py` | Không sửa |
| `tools/voice/voice.py`, `pron.py` | `tools/voice/` | `pron.py` đọc `~/.imagefly/pron.json` trước |
| `tools/setup/doctor.py`, `fix_hf_symlinks.py` | `tools/setup/` | Viết lại cho ImageFly (cài nhẹ cho slideshow, cài giọng riêng bằng `--voice`) |

## Chép từ nơi khác

| Trong repo | Nguồn | Giấy phép |
|---|---|---|
| `vendor/bestagentkits/fit-beat-grid.py` | [bestagentkits/motion-video-skill](https://github.com/bestagentkits/motion-video-skill) commit a73702b | MIT |
| `templates/fonts/BeVietnamPro-*.ttf` | [google/fonts](https://github.com/google/fonts/tree/main/ofl/bevietnampro) | SIL OFL 1.1 |
| `templates/fonts/JetBrainsMono-Variable.ttf` | [google/fonts](https://github.com/google/fonts/tree/main/ofl/jetbrainsmono) | SIL OFL 1.1 |

## Phụ thuộc cài khi chạy (không chép vào repo)

| Phụ thuộc | Vai trò | Giấy phép |
|---|---|---|
| [HyperFrames](https://github.com/heygen-com/hyperframes) 0.8.145 (npx) | Dựng HTML thành MP4, kiểm tra | Apache-2.0 |
| [GSAP](https://gsap.com) 3.14.2 (CDN) | Chuyển động trong composition | Giấy phép GSAP (miễn phí) |
| [VieNeu-TTS](https://github.com/pnnbao97/VieNeu-TTS) 3.8.3 (pip `vieneu`) | Giọng đọc tiếng Việt (tùy chọn) | Apache-2.0 |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Chấm phát âm, mốc từng từ (tùy chọn) | MIT |
| numpy, scipy, soundfile, Pillow | Xử lý âm thanh, ảnh | BSD, MIT-CMU |
| ffmpeg (người dùng tự cài) | Đọc ghi âm thanh, video | LGPL/GPL tùy bản |

Repo không đóng gói nhạc hay ảnh của bên thứ ba. Ảnh và nhạc người dùng đưa vào thuộc về người dùng.
