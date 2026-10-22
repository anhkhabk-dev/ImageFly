"""Hiệu ứng âm thanh (SFX) tổng hợp bằng code, đặt đúng chỗ chuyển cảnh và chỗ tiêu đề đổi góc.

Không dùng file của bên thứ ba: mỗi âm là tổng hợp từ nhiễu, sóng sin và bộ lọc nên không dính bản quyền.
Cùng shots.json thì ra cùng sfx.wav (hạt giống cố định).

  whoosh   tiếng gió quét, dùng cho slide, slideup (ảnh trượt vào)
  swish    quét nhanh, sáng, dùng cho wipe
  impact   tiếng trầm nhẹ kèm gió dâng, dùng cho zoom
  swell    hơi thở mềm, dùng cho fade
  ping     hai nốt chuông ngắn, dùng khi tiêu đề đổi góc
  sparkle  lấp lánh dâng lên, dùng cho phần mở đầu tiêu đề

Usage: python sfx.py <project_dir>      (đọc shots.json, ghi sfx.wav và sfx.json)
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

SR = 48000
KIND = {"slide": "whoosh", "slideup": "whoosh", "wipe": "swish", "zoom": "impact", "fade": "swell"}


def _t(n: int) -> np.ndarray:
    return np.arange(n) / SR


def _sweep_noise(n: int, f0: float, f1: float, rng: np.random.Generator, q: float = 0.35) -> np.ndarray:
    """Nhiễu qua bộ lọc thông thấp một cực có tần số cắt chạy từ f0 đến f1 (hình gió quét)."""
    noise = rng.standard_normal(n).astype(np.float64)
    fc = np.exp(np.linspace(math.log(f0), math.log(f1), n))
    a = 1 - np.exp(-2 * math.pi * fc / SR)
    out = np.empty(n)
    y = 0.0
    z = 0.0
    for i in range(n):          # hai tầng lọc cho dốc hơn
        y += a[i] * (noise[i] - y)
        z += a[i] * (y - z)
        out[i] = z
    out -= np.concatenate([[0.0], out[:-1]]) * q   # bớt phần trầm
    return out.astype(np.float32)


def _norm(x: np.ndarray, peak: float) -> np.ndarray:
    m = float(np.abs(x).max()) or 1.0
    return (x * (peak / m)).astype(np.float32)


def whoosh(rng, dur: float = 0.8, rising: bool = True) -> np.ndarray:
    n = int(dur * SR)
    x = _sweep_noise(n, 250, 5200, rng) if rising else _sweep_noise(n, 5200, 250, rng)
    t = np.linspace(0, 1, n)
    env = np.sin(math.pi * t ** 0.8) ** 2
    return _norm(x * env, 0.5)


def swish(rng, dur: float = 0.45) -> np.ndarray:
    n = int(dur * SR)
    x = _sweep_noise(n, 1500, 9000, rng, q=0.6)
    t = np.linspace(0, 1, n)
    return _norm(x * (np.sin(math.pi * t) ** 1.5), 0.4)


def impact(rng, dur: float = 0.9) -> np.ndarray:
    n = int(dur * SR)
    t = _t(n)
    freq = 38 + 90 * np.exp(-t / 0.07)
    boom = np.sin(2 * math.pi * np.cumsum(freq) / SR) * np.exp(-t / 0.28)
    air = _sweep_noise(n, 400, 3500, rng) * np.exp(-t / 0.25) * 0.5
    return _norm(boom + air, 0.6)


def swell(rng, dur: float = 0.9) -> np.ndarray:
    n = int(dur * SR)
    x = _sweep_noise(n, 300, 1600, rng)
    t = np.linspace(0, 1, n)
    return _norm(x * np.sin(math.pi * t) ** 2, 0.22)


def ping(dur: float = 0.7) -> np.ndarray:
    n = int(dur * SR)
    t = _t(n)
    x = np.zeros(n)
    for f, g, d in ((1318.5, 1.0, 0.0), (1975.5, 0.55, 0.09)):
        k = int(d * SR)
        tt = t[: n - k]
        x[k:] += g * np.sin(2 * math.pi * f * tt) * np.exp(-tt / 0.16)
    x[:200] *= np.linspace(0, 1, 200)
    return _norm(x, 0.38)


def sparkle(rng, dur: float = 1.3) -> np.ndarray:
    n = int(dur * SR)
    out = np.zeros(n)
    for i in range(14):
        start = int((i / 14) ** 1.4 * dur * 0.8 * SR)
        f = 1400 * (1.18 ** (i % 9)) * (1 + rng.uniform(-0.01, 0.01))
        m = min(n - start, int(0.28 * SR))
        tt = _t(m)
        out[start:start + m] += np.sin(2 * math.pi * f * tt) * np.exp(-tt / 0.07) * (0.5 + 0.5 * i / 14)
    return _norm(out, 0.3)


def stereo(x: np.ndarray, pan: float) -> np.ndarray:
    l, r = math.sqrt(0.5 * (1 - pan)), math.sqrt(0.5 * (1 + pan))
    return np.stack([x * l, x * r], axis=1)


def build(project: Path) -> dict:
    sh = json.loads((project / "shots.json").read_text(encoding="utf-8"))
    total = sh["total"]
    rng = np.random.default_rng(7)
    n = int((total + 1.0) * SR)
    out = np.zeros((n, 2), dtype=np.float32)
    events = []

    def put(sig: np.ndarray, at: float, pan: float, kind: str) -> None:
        i = max(0, int(at * SR))
        s = stereo(sig, pan)
        j = min(n, i + len(s))
        out[i:j] += s[: j - i]
        events.append({"t": round(at, 3), "kind": kind})

    for i, s in enumerate(sh["shots"]):
        if i == 0:
            continue
        kind = KIND.get(s["transition"], "swell")
        at = s["start"] + 0.05
        pan = 0.0
        if kind == "whoosh":
            sig = whoosh(rng, 0.85, rising=(s["transition"] == "slide"))
            at = s["start"] - 0.1
            pan = 0.35 if s["transition"] == "slide" else 0.0
        elif kind == "swish":
            sig, pan = swish(rng), -0.3
        elif kind == "impact":
            sig = impact(rng)
            at = s["start"] + 0.12
        else:
            sig = swell(rng)
        put(sig, at, pan, kind)
    plan = sh.get("title_plan") or []
    if plan:
        put(sparkle(rng), 0.3, 0.0, "sparkle")
        for k, seg in enumerate(plan):
            put(ping(), seg["t"] + 0.55, (-0.4 if "left" in seg["pos"] else 0.4), "ping")
    peak = float(np.abs(out).max())
    if peak > 0.9:
        out *= 0.9 / peak
    import soundfile as sf
    sf.write(project / "sfx.wav", out[: int(total * SR) + 1], SR, subtype="FLOAT")
    (project / "sfx.json").write_text(json.dumps(events, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"events": len(events)}


if __name__ == "__main__":
    r = build(Path(sys.argv[1]).resolve())
    print(f"SFXDONE {r['events']} hiệu ứng")
