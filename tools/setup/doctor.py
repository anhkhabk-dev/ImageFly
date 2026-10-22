"""Kiểm tra (và cài) mọi thứ ImageFly cần.

  python doctor.py                  kiểm tra, in bảng và việc cần làm
  python doctor.py --install        tạo ~/.imagefly/venv, cài gói Python cho slideshow (nhẹ)
  python doctor.py --install --voice  cài thêm giọng đọc VieNeu và Whisper (khoảng 2 đến 3 GB)

Chạy được bằng Python 3.10+ bất kỳ, chỉ dùng thư viện chuẩn.
Nếu máy đã có ~/.motionfly/venv (từ plugin MotionFly) thì dùng luôn, không cần cài lại.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

HOME = Path.home() / ".imagefly"
SUB = "Scripts/python.exe" if os.name == "nt" else "bin/python"
VENV = HOME / "venv"
PY = VENV / SUB
if not PY.exists() and (Path.home() / ".motionfly" / "venv" / SUB).exists():
    PY = Path.home() / ".motionfly" / "venv" / SUB
HYPERFRAMES = "hyperframes@0.8.145"
BASE_PACKAGES = ["soundfile", "numpy", "scipy", "pillow"]
VOICE_PACKAGES = ["vieneu==3.8.3", "faster-whisper"]
HERE = Path(__file__).resolve().parent
NPX = "npx.cmd" if os.name == "nt" else "npx"

rows: list[tuple[str, str, str]] = []


def run(cmd: list[str], timeout: int = 600) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                           env={**os.environ, "PYTHONUTF8": "1"})
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)


def row(name: str, ok: bool | None, note: str) -> bool:
    rows.append((name, "có" if ok else ("tùy chọn" if ok is None else "THIẾU"), note))
    return bool(ok)


def check_tools() -> bool:
    good = True
    code, out = run(["node", "--version"])
    major = int(out.lstrip("v").split(".")[0]) if code == 0 and out.startswith("v") else 0
    good &= row("Node.js 22+", major >= 22, out if code == 0 else "cài tại https://nodejs.org")
    for tool in ("ffmpeg", "ffprobe"):
        good &= row(tool, shutil.which(tool) is not None,
                    shutil.which(tool) or "cài tại https://ffmpeg.org/download.html rồi thêm vào PATH")
    if shutil.which("ffmpeg"):
        _, filters = run(["ffmpeg", "-hide_banner", "-filters"])
        need = [f for f in ("loudnorm", "aresample", "afade") if f" {f} " not in filters]
        good &= row("ffmpeg loudnorm/afade", not need, "có" if not need else f"bản ffmpeg thiếu {need}; cài bản đầy đủ")
    code, out = run([NPX, "-y", HYPERFRAMES, "--version"], timeout=300)
    good &= row("HyperFrames", code == 0, out.splitlines()[-1] if code == 0 else "cần Node.js; lỗi: " + out[-200:])
    return good


def check_venv() -> bool:
    if not PY.exists():
        return row("Môi trường Python", False, f"chưa có {VENV}; chạy lại với --install")
    code, out = run([str(PY), "-c", "import soundfile, numpy, scipy, PIL; print('ok')"])
    return row("Môi trường Python", code == 0, str(PY) if code == 0 else out[-300:])


TTS_PROBE = "from vieneu import Vieneu; t=Vieneu(); print('VOICES=%d' % len(t.list_preset_voices()))"


def check_voice() -> None:
    code, out = run([str(PY), "-c", "import vieneu, faster_whisper"])
    if code != 0:
        row("Giọng đọc (chỉ cần khi làm video có lời)", None, "chưa cài: chạy --install --voice")
        return
    code, out = run([str(PY), "-c", TTS_PROBE])
    if code != 0 and "External data path" in out:
        run([str(PY), str(HERE / "fix_hf_symlinks.py")])
        code, out = run([str(PY), "-c", TTS_PROBE])
    n = next((ln.split("=")[1] for ln in out.splitlines() if ln.startswith("VOICES=")), "?")
    row("Giọng VieNeu + Whisper", code == 0, f"{n} giọng có sẵn" if code == 0 else out[-300:])


def install(voice: bool) -> None:
    global PY
    HOME.mkdir(parents=True, exist_ok=True)
    if not PY.exists():
        PY = VENV / SUB
        if shutil.which("uv"):
            run(["uv", "venv", str(VENV), "--python", "3.12"])
        else:
            run([sys.executable, "-m", "venv", str(VENV)])
    pkgs = BASE_PACKAGES + (VOICE_PACKAGES if voice else [])
    if shutil.which("uv"):
        code, out = run(["uv", "pip", "install", "--python", str(PY), *pkgs], timeout=1800)
    else:
        code, out = run([str(PY), "-m", "pip", "install", *pkgs], timeout=1800)
    print(out[-600:])
    if voice:
        print("Tải model VieNeu (lần đầu vài trăm MB)...")
        run([str(PY), "-c", TTS_PROBE], timeout=1800)
        print("Tải model Whisper large-v3-turbo (khoảng 1,6 GB)...")
        run([str(PY), "-c", "from faster_whisper import WhisperModel; WhisperModel('large-v3-turbo', device='cpu', "
                            "compute_type='int8')"], timeout=3600)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--voice", action="store_true", help="cùng --install: cài cả giọng đọc")
    a = ap.parse_args()
    print(f"ImageFly doctor | {platform.system()} {platform.release()} | Python {platform.python_version()}")
    if a.install:
        install(a.voice)
        rows.clear()
    ok = check_tools()
    ok &= check_venv()
    if PY.exists():
        check_voice()
    w = max(len(r[0]) for r in rows)
    for name, state, note in rows:
        print(f"{name:<{w}}  {state:<8}  {note}")
    print("SAN SANG" if ok else "CHUA DU: xử lý các dòng THIẾU ở trên (hoặc chạy --install)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
