"""MV ca nhạc: cắt ảnh theo lời bài hát.

  lyrics <du-an> [--audio FILE]   nhận lời bằng Whisper -> lyrics.json (mốc giây từng câu)
  mv <du-an>                      mv.json (danh sách mốc cắt) -> images.json + brief.json, rồi chạy plan

mv.json:
  {"lead": 0.3,                   # chuyển cảnh bắt đầu sớm bấy nhiêu giây so với mốc lời
   "cuts": [{"end": 14.8, "img": "i10", "effect": "zoom-in", "transition": "fade"}, ...]}
  "end" là giây kết thúc cảnh trong bài (cảnh cuối: "end" = độ dài bài trừ 1 giây đuôi).
  Ảnh dùng lại nhiều lần được nhân bản thành id mới (bản sao dùng chung file ảnh).
"""

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Whisper hay "nghe ra" câu quảng cáo ở đoạn nhạc không lời: loại bỏ
HALLUCINATION = re.compile(r"subscribe|đăng ký kênh|ghiền mì|cảm ơn các bạn đã (xem|theo dõi)", re.I)


def jload(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def jsave(p: Path, obj) -> None:
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def audio_of(project: Path, arg: str | None) -> Path:
    if arg:
        return Path(arg).expanduser().resolve()
    m = jload(project / "brief.json").get("music")
    first = m[0] if isinstance(m, list) and m else m
    if not isinstance(first, str) or first.startswith(("synth:", "score")) or first == "none":
        raise SystemExit("brief.music chưa là file nhạc: truyền --audio <file.mp3>")
    return Path(first).expanduser().resolve()


def lyrics(project: Path, audio_arg: str | None) -> None:
    """Whisper không VAD (VAD hay cắt mất cả bài có nhạc nền), đọc mảng âm thanh trực tiếp
    vì PyAV mới không nhận tham số metadata_errors của faster-whisper."""
    import numpy as np
    from faster_whisper import WhisperModel
    audio = audio_of(project, audio_arg)
    if not audio.exists():
        raise SystemExit(f"Không thấy file nhạc: {audio}")
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(audio), "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True).stdout
    wav = np.frombuffer(raw, dtype=np.float32)
    model = WhisperModel("medium", device="cpu", compute_type="int8")
    segs, _ = model.transcribe(wav, language="vi", vad_filter=False, beam_size=5,
                               condition_on_previous_text=False, no_speech_threshold=0.9)
    out = [{"start": round(s.start, 1), "end": round(s.end, 1), "text": s.text.strip()} for s in segs]
    kept = [o for o in out if not HALLUCINATION.search(o["text"])]
    jsave(project / "lyrics.json", kept)
    print(f"LYRICS {len(kept)} câu (bỏ {len(out) - len(kept)} câu nghi nhận nhầm) -> lyrics.json, bài dài {len(wav) / 16000:.1f}s")
    for o in kept:
        print(f"  {o['start']:7.1f} {o['end']:7.1f}  {o['text']}")
    print("Lời do Whisper nhận, có thể sai chính tả: chỉ dùng để xác định ý và mốc câu, đối chiếu khoảng trống để tìm đoạn nhạc không lời.")


def apply(project: Path) -> None:
    mvp = project / "mv.json"
    if not mvp.exists():
        raise SystemExit("Thiếu mv.json (danh sách mốc cắt), xem đầu tools/mv.py")
    mv = jload(mvp)
    cuts = mv["cuts"]
    lead = float(mv.get("lead", 0.3))
    imgs = [x for x in jload(project / "images.json") if not x.get("copy")]
    base = {x["id"]: x for x in imgs}
    stamp = time.strftime("%Y%m%d-%H%M")
    (project / "_backup").mkdir(exist_ok=True)
    for f in ("images.json", "brief.json"):
        shutil.copy2(project / f, project / "_backup" / f"{Path(f).stem}_{stamp}.json")
    out, used, nid, t0 = [], set(), len(imgs) + 1, 0.0
    for k, c in enumerate(cuts):
        if c["img"] not in base:
            raise SystemExit(f"mv.json: không có ảnh {c['img']} trong images.json")
        e = float(c["end"]) - (lead if k < len(cuts) - 1 else 0.0)
        if e <= t0:
            raise SystemExit(f"mv.json: mốc end={c['end']} của cảnh {k + 1} không lớn hơn cảnh trước")
        y = copy.deepcopy(base[c["img"]])
        if c["img"] in used:
            y["id"], y["copy"] = f"i{nid:02d}", True
            nid += 1
        used.add(c["img"])
        y["beats"] = round(e - t0, 3)       # shot_s=1, shot_beats=1: beats chính là số giây của cảnh
        for key in ("effect", "transition", "focus", "focus_to", "fit"):
            if key in c:
                y[key] = c[key]
        t0 = e
        out.append(y)
    jsave(project / "images.json", out)
    b = jload(project / "brief.json")
    b.update(shot_s=1.0, shot_beats=1, duration_s=None)
    jsave(project / "brief.json", b)
    print(f"MV {len(out)} cảnh từ {len(base)} ảnh, tổng {t0:.1f}s (+1s đuôi). Đã sao lưu images.json, brief.json vào _backup/")


if __name__ == "__main__":
    cmd, proj = sys.argv[1], Path(sys.argv[2]).resolve()
    if cmd == "lyrics":
        lyrics(proj, sys.argv[sys.argv.index("--audio") + 1] if "--audio" in sys.argv else None)
    else:
        apply(proj)
