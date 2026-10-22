"""Soạn nhạc từ bản nhạc viết tay (score.json): giai điệu, hợp âm, nhịp, kiểu trình bày.

Agent (hoặc người dùng) viết music/score.json, công cụ này dựng thành music/bgm.wav (48 kHz stereo).
Cùng score.json thì ra cùng file. Giai điệu và hợp âm lặp lại cho đủ độ dài video.

score.json:
{
  "title": "Tên bản",
  "bpm": 92,
  "style": "ballad",            // ballad | pop | lofi | cinematic | folk | upbeat | none (chỉ giai điệu)
  "lead": "piano",              // piano | flute | pluck | bell | pad
  "melody": [["E4", 1], ["G4", 1], ["A4", 2], ["R", 1], ["G4", 1]],   // [tên nốt, số phách]; R là nghỉ
  "chords": [["C", 4], ["Am", 4], ["F", 4], ["G", 4]],               // [hợp âm, số phách]
  "bass": true,
  "drums": "soft",              // none | soft | pop | lofi
  "melody_octave_shift": 0,
  "loop": true
}

Tên nốt: C4, F#3, Bb4 (C4 là Đô giữa). Hợp âm: C, Am, G7, Fmaj7, Dm7, Bb, Esus4, Cdim.
Giai điệu có bản quyền (bài hát thương mại) không nên tái tạo: viết giai điệu gốc, giai điệu dân gian
hay phạm vi công cộng, hoặc giai điệu do người dùng tự cung cấp (xem skills/video-tu-anh/SKILL.md).

Usage: python score.py <project_dir> --duration 60 [--score path/to/score.json]
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from synth import SR, bass as bass_note, env, hat, kick, pad_note  # noqa: E402

NOTE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def midi(name: str) -> int | None:
    n = name.strip()
    if n.upper() in ("R", "-", ""):
        return None
    m = re.fullmatch(r"([A-Ga-g])([#b]?)(-?\d)", n)
    if not m:
        raise SystemExit(f"Tên nốt không hợp lệ: '{name}' (ví dụ C4, F#3, Bb4, R)")
    pc = NOTE[m.group(1).upper()] + (1 if m.group(2) == "#" else -1 if m.group(2) == "b" else 0)
    return 12 * (int(m.group(3)) + 1) + pc


def hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


QUAL = {"": (0, 4, 7), "m": (0, 3, 7), "7": (0, 4, 7, 10), "maj7": (0, 4, 7, 11), "m7": (0, 3, 7, 10),
        "sus4": (0, 5, 7), "sus2": (0, 2, 7), "dim": (0, 3, 6), "aug": (0, 4, 8), "6": (0, 4, 7, 9),
        "m6": (0, 3, 7, 9), "add9": (0, 4, 7, 14), "9": (0, 4, 7, 10, 14)}


def chord_notes(name: str, octave: int = 3) -> tuple[int, list[int]]:
    m = re.fullmatch(r"([A-G])([#b]?)(.*)", name.strip())
    if not m or m.group(3) not in QUAL:
        raise SystemExit(f"Hợp âm không hợp lệ: '{name}' (ví dụ C, Am, G7, Fmaj7, Dm7, Bb, Esus4)")
    root = 12 * (octave + 1) + NOTE[m.group(1)] + (1 if m.group(2) == "#" else -1 if m.group(2) == "b" else 0)
    return root, [root + i for i in QUAL[m.group(3)]]


# ---------- nhạc cụ ----------

def piano(f: float, n: int) -> np.ndarray:
    t = np.arange(n) / SR
    tone = sum(a * np.sin(2 * math.pi * f * k * t) * np.exp(-t / (0.9 / k ** 0.6))
               for k, a in ((1, 1.0), (2, 0.5), (3, 0.28), (4, 0.14), (5, 0.07)))
    return (tone * env(n, 0.004, 0.15)).astype(np.float32) * 0.16


def flute(f: float, n: int) -> np.ndarray:
    t = np.arange(n) / SR
    vib = 1 + 0.004 * np.sin(2 * math.pi * 5.2 * t) * np.minimum(1, t / 0.3)
    ph = 2 * math.pi * np.cumsum(f * vib) / SR
    tone = np.sin(ph) + 0.18 * np.sin(2 * ph) + 0.05 * np.sin(3 * ph)
    return (tone * env(n, 0.06, 0.12)).astype(np.float32) * 0.14


def bell(f: float, n: int) -> np.ndarray:
    t = np.arange(n) / SR
    tone = (np.sin(2 * math.pi * f * t) + 0.6 * np.sin(2 * math.pi * f * 2.76 * t) * np.exp(-t / 0.3)
            + 0.3 * np.sin(2 * math.pi * f * 5.4 * t) * np.exp(-t / 0.15)) * np.exp(-t / 0.9)
    return (tone * env(n, 0.002, 0.1)).astype(np.float32) * 0.12


def pluck_lead(f: float, n: int) -> np.ndarray:
    t = np.arange(n) / SR
    tone = np.sin(2 * math.pi * f * t) + 0.4 * np.sin(4 * math.pi * f * t) + 0.15 * np.sin(6 * math.pi * f * t)
    return (tone * np.exp(-t / 0.35) * env(n, 0.004, 0.08)).astype(np.float32) * 0.15


def pad_lead(f: float, n: int) -> np.ndarray:
    rng = np.random.default_rng(3)
    return pad_note(f, n, rng) * 2.0


LEADS = {"piano": piano, "flute": flute, "bell": bell, "pluck": pluck_lead, "pad": pad_lead}

STYLES = {
    #            chord voicing, drums default, chord rhythm (beat offsets within a bar of 4)
    "ballad":    {"comp": "arp", "drums": "none", "pad": True},
    "pop":       {"comp": "strum", "drums": "pop", "pad": True},
    "lofi":      {"comp": "strum", "drums": "lofi", "pad": False},
    "cinematic": {"comp": "pad", "drums": "none", "pad": True},
    "folk":      {"comp": "arp", "drums": "none", "pad": False},
    "upbeat":    {"comp": "strum", "drums": "pop", "pad": True},
    "none":      {"comp": "none", "drums": "none", "pad": False},
}


def render(score: dict, duration: float) -> tuple[np.ndarray, dict]:
    bpm = float(score.get("bpm", 90))
    beat = 60.0 / bpm
    style = STYLES.get(score.get("style", "ballad"))
    if style is None:
        raise SystemExit(f"style phải là một trong {sorted(STYLES)}")
    lead = LEADS.get(score.get("lead", "piano"))
    if lead is None:
        raise SystemExit(f"lead phải là một trong {sorted(LEADS)}")
    shift = int(score.get("melody_octave_shift", 0)) * 12
    drums = score.get("drums", style["drums"])
    rng = np.random.default_rng(11)

    mel = [(midi(n), float(b)) for n, b in score.get("melody", [])]
    chords = [(c, float(b)) for c, b in score.get("chords", [])]
    mel_beats = sum(b for _, b in mel)
    chord_beats = sum(b for _, b in chords)
    total = int((duration + 2) * SR)
    L = np.zeros(total, dtype=np.float32)
    R = np.zeros(total, dtype=np.float32)

    def add(sig: np.ndarray, start: float, pan: float = 0.0) -> None:
        i = int(start * SR)
        if i >= total:
            return
        j = min(total, i + len(sig))
        L[i:j] += sig[: j - i] * (1 - max(0, pan))
        R[i:j] += sig[: j - i] * (1 + min(0, pan))

    end_beats = (duration + 2) / beat
    # giai điệu
    if mel:   # giai điệu và hợp âm lặp riêng theo độ dài của từng phần
        t = 0.0
        while t < end_beats and mel_beats > 0:
            pos = t
            for m, b in mel:
                if pos >= end_beats:
                    break
                if m is not None:
                    n = int((b * beat + 0.35) * SR)
                    add(lead(hz(m + shift), n), pos * beat, 0.1)
                pos += b
            t += mel_beats
            if not score.get("loop", True):
                break
    # hợp âm và bass
    if chords:
        t = 0.0
        while t < end_beats:
            pos = t
            for name, b in chords:
                if pos >= end_beats:
                    break
                root, notes = chord_notes(name, 3)
                if style["pad"]:
                    n = int((b * beat + 0.5) * SR)
                    for m in notes:
                        add(pad_note(hz(m + 12), n, rng) * 0.8, pos * beat)
                comp = style["comp"]
                if comp in ("arp", "strum"):
                    step = 0.5 if comp == "arp" else 1.0
                    k = 0
                    x = 0.0
                    while x < b:
                        m = notes[k % len(notes)] + (12 if comp == "arp" and (k // len(notes)) % 2 else 0)
                        add(piano(hz(m + 12), int(0.9 * SR)) * (0.8 if comp == "arp" else 0.7),
                            (pos + x) * beat, -0.25 if k % 2 else 0.25)
                        x += step
                        k += 1
                if score.get("bass", True) and comp != "none":
                    x = 0.0
                    while x < b:
                        add(bass_note(hz(root - 12), int(min(b - x, 2) * beat * SR)), (pos + x) * beat)
                        x += 2.0 if comp in ("pad", "arp") else 1.0
                pos += b
            t += chord_beats if chord_beats else 4
    # trống
    if drums != "none":
        bars = int(end_beats // 4) + 1
        for b in range(bars):
            t0 = b * 4
            for q in range(4):
                if drums in ("pop",) or q % 2 == 0:
                    add(kick(int(0.4 * SR)) * (0.8 if drums == "soft" else 1.0), (t0 + q) * beat)
                add(hat(int(0.1 * SR), rng) * (1.4 if drums == "lofi" else 1.0), (t0 + q + 0.5) * beat)
    n = int(duration * SR)
    out = np.stack([L[:n], R[:n]], axis=1)
    fade = min(n, int(2.0 * SR))
    out[-fade:] *= np.linspace(1, 0, fade)[:, None]
    fin = min(n, int(0.6 * SR))
    out[:fin] *= np.linspace(0, 1, fin)[:, None]
    out *= 0.89 / (np.abs(out).max() or 1.0)
    return out, {"bpm": bpm, "beat0": 0.0, "style": score.get("style", "ballad"), "source": "score.py",
                 "title": score.get("title", "")}


def main() -> None:
    import soundfile as sf

    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--duration", type=float, required=True)
    ap.add_argument("--score")
    a = ap.parse_args()
    proj = Path(a.project).resolve()
    sp = Path(a.score) if a.score else proj / "music" / "score.json"
    if not sp.exists():
        raise SystemExit(f"Thiếu {sp}: viết score.json (xem mô tả đầu file score.py)")
    audio, meta = render(json.loads(sp.read_text(encoding="utf-8")), a.duration)
    out = proj / "music"
    out.mkdir(parents=True, exist_ok=True)
    sf.write(out / "bgm.wav", audio, SR, subtype="PCM_16")
    (out / "beats.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"MUSICDONE {out / 'bgm.wav'} bpm={meta['bpm']} style={meta['style']}")


if __name__ == "__main__":
    main()
