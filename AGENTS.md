# ImageFly: hướng dẫn cho agent (Antigravity, Codex, Cursor, Gemini CLI...)

ImageFly biến thư mục ảnh thành video MP4 (slideshow hoặc có lời đọc tiếng Việt), khung 9:16 hoặc 16:9.
Lõi là một CLI Python độc lập với agent: `python tools/imagefly.py <lệnh>`.

Cách làm việc: đọc `skills/video-tu-anh/SKILL.md` và làm theo đúng từng bước (đặt `ROOT` là thư mục repo này). Cài máy lần đầu: `skills/anh-cai-dat/SKILL.md`.

Tóm tắt lệnh (chạy từ thư mục làm việc; dự án nằm ở `videos/<slug>/`):

```bash
python tools/imagefly.py doctor
python tools/imagefly.py new <slug> --images "<thư mục ảnh>" --aspect 9:16 --mode slideshow --title "..."
# xem ảnh, chỉnh videos/<slug>/images.json và brief.json nếu cần
python tools/imagefly.py build videos/<slug> --name <ten-file>
```

Chế độ có lời: viết `videos/<slug>/script.json` (xem SKILL.md) rồi chạy `build` (tự sinh giọng).

Quy tắc: không bịa số liệu hay thông tin không có trong ảnh hoặc yêu cầu của người dùng; không xóa hay sửa ảnh gốc; không tải nhạc/ảnh từ web đóng gói vào repo; không `git push` khi người dùng chưa đồng ý.

Agent không có sub-agent song song vẫn chạy bình thường: ImageFly không cần sub-agent (mọi cảnh được sinh tự động từ `shots.json`).

Đăng ký skill: Claude Code cài qua plugin (`/plugin marketplace add anhkhabk-dev/ImageFly`, `/plugin install imagefly@imagefly`). Antigravity và agent khác: clone repo, rồi chép hoặc liên kết `skills/video-tu-anh` và `skills/anh-cai-dat` vào thư mục skills của agent đó (kiểm tra tài liệu của agent về đường dẫn), hoặc chỉ cần để agent đọc file này.
