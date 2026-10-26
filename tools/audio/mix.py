"""Audio finishing for a project.

  mix      voice.wav + music/bgm.wav + words.json -> mix.wav
           voice chain (high-pass, presence EQ, gentle compression, limiter, from the
           CES kit); music ducked by an envelope built from the word timings
           (attack 0.2 s, release 0.5 s); final two-pass loudnorm to -14 LUFS, TP -1.5.
           Levels follow bestagentkits/motion-video-skill's lesson: music about 6 dB
           under the voice while speaking, close to it in pauses (10 dB reads as "no music").
  srt      timeline.json captions -> phude.srt
  final    rendered video + mix.wav + phude.srt -> renders/<name>.mp4 (and <name>-nhe.mp4
           under 27 MiB when the main file is larger)
  measure  print integrated loudness and true peak of a file

Usage: python mix.py <cmd> <project_dir> [--name NAME] [--video PATH] [--music-db -6]
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

SR = 48000
LITE_BYTES = 27 * 1024 * 1024


# ---------- pure helpers ----------

def speech_mask(words: list[dict], total: float, fps: int = 100, bridge: float = 0.35) -> list[float]:
    """1.0 where someone is talking (gaps under `bridge` s are bridged), else 0.0."""
    n = int(total * fps) + 1
    mask = [0.0] * n
    spans = sorted((w["start"], w["end"]) for w in words)
    merged: list[list[float]] = []
    for a, b in spans:
        if merged and a - merged[-1][1] < bridge:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    for a, b in merged:
        for i in range(max(0, int(a * fps)), min(n, int(b * fps) + 1)):
            mask[i] = 1.0
    return mask


def smooth(mask: list[float], fps: int = 100, attack: float = 0.2, release: float = 0.5) -> list[float]:
    """Envelope that rises over `attack` s before speech and falls over `release` s after."""
    up, down = 1.0 / max(1, attack * fps), 1.0 / max(1, release * fps)
    fwd = mask[:]
    for i in range(1, len(fwd)):
        fwd[i] = max(mask[i], fwd[i - 1] - down)
    out = fwd[:]
    for i in range(len(out) - 2, -1, -1):
        out[i] = max(fwd[i], out[i + 1] - up)
    return out


def srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(caps: list[dict]) -> str:
    return "".join(f"{i}\n{srt_time(c['start'])} --> {srt_time(c['end'])}\n{c['text']}\n\n"
                   for i, c in enumerate(caps, 1))


# ---------- ffmpeg steps ----------

def ff(*args: str) -> str:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-y", *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode:
        raise SystemExit(r.stderr[-2000:])
    return r.stderr


def loudness(path: Path) -> dict:
    err = ff("-i", str(path), "-vn", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-")
    return json.loads(err[err.rindex("{"): err.rindex("}") + 1])


def _block_gain(level, attack_ms: float, release_ms: float, block_ms: float = 1.0):
    """One-pole attack/release smoothing over 1 ms blocks (fast enough in pure Python)."""
    import numpy as np
    a = np.exp(-block_ms / attack_ms)
    r = np.exp(-block_ms / release_ms)
    out = np.empty_like(level)
    prev = level[0]
    for i, v in enumerate(level):
        coef = a if v > prev else r
        prev = coef * prev + (1 - coef) * v
        out[i] = prev
    return out


def voice_chain(x, sr: int = SR):
    """High-pass 80 Hz, +2 dB presence at 3 kHz, 2.5:1 compression above -20 dBFS,
    limiter at 0.95. Done in numpy/scipy so minimal ffmpeg builds work (the CES kit
    used ffmpeg highpass/equalizer/acompressor/alimiter for the same chain)."""
    import numpy as np
    from scipy.signal import butter, lfilter, sosfilt

    x = sosfilt(butter(2, 80, "highpass", fs=sr, output="sos"), x)
    A, w0, q = 10 ** (2 / 40), 2 * np.pi * 3000 / sr, 1.0
    al = np.sin(w0) / (2 * q)
    b = [1 + al * A, -2 * np.cos(w0), 1 - al * A]
    a = [1 + al / A, -2 * np.cos(w0), 1 - al / A]
    x = lfilter(b, a, x)
    blk = sr // 1000
    n = len(x) // blk * blk
    blocks = x[:n].reshape(-1, blk)
    lvl_db = 20 * np.log10(np.sqrt((blocks ** 2).mean(axis=1)) + 1e-9)
    over = np.maximum(0, lvl_db + 20)
    gain_db = _block_gain(-over * (1 - 1 / 2.5), 8, 160) + 2
    peak = np.abs(blocks).max(axis=1) * 10 ** (gain_db / 20)
    lim = _block_gain(np.minimum(1, 0.95 / np.maximum(peak, 1e-9)), 1, 60)
    g = np.repeat(10 ** (gain_db / 20) * lim, blk)
    g = np.concatenate([g, np.full(len(x) - n, g[-1] if n else 1.0)])
    return np.clip(x * g, -0.99, 0.99).astype(np.float32)


def rms_db(x, mask=None) -> float:
    import numpy as np
    sel = x if mask is None else x[mask]
    return float(20 * np.log10(np.sqrt(np.mean(sel ** 2)) + 1e-9)) if len(sel) else -120.0


def add_sfx(project: Path, base, offset_db: float, sfx_db: float):
    """Cộng sfx.wav (nếu có) vào bản trộn; mức chỉnh theo RMS của phần nền cộng offset_db và sfx_db."""
    import numpy as np
    import soundfile as sf

    p = project / "sfx.wav"
    if not p.exists():
        return base
    s, _ = sf.read(p, dtype="float32")
    if s.ndim == 1:
        s = np.stack([s, s], axis=1)
    s = s[: len(base)]
    if len(s) < len(base):
        s = np.concatenate([s, np.zeros((len(base) - len(s), 2), dtype=np.float32)])
    active = np.abs(s).max(axis=1) > 1e-3
    if not active.any():
        return base
    ref = rms_db(base.mean(axis=1)) + offset_db if offset_db > -100 else -22.0   # -100: không có nền, mức tuyệt đối
    gain = 10 ** ((ref + sfx_db - rms_db(s.mean(axis=1), active)) / 20)
    return base + s * gain


def mix(project: Path, music_db: float, duck_db: float, sfx_db: float = 0.0) -> None:
    import numpy as np
    import soundfile as sf

    words = json.loads((project / "words.json").read_text(encoding="utf-8"))
    tmp = project / "audio"
    tmp.mkdir(exist_ok=True)
    voice, sr = sf.read(project / "voice.wav", dtype="float32")
    if voice.ndim > 1:
        voice = voice.mean(axis=1)
    if sr != SR:
        raise SystemExit(f"voice.wav phải {SR} Hz (đang {sr})")
    voice = voice_chain(voice)
    n = len(voice)
    music_path = project / "music" / "bgm.wav"
    if music_path.exists():
        ff("-i", str(music_path), "-af", f"aresample={SR}", "-ac", "2", str(tmp / "bgm48.wav"))
        music, _ = sf.read(tmp / "bgm48.wav", dtype="float32")
        if len(music) < n:
            music = np.concatenate([music, np.zeros((n - len(music), 2), dtype=np.float32)])
        music = music[:n]
        env = smooth(speech_mask(words["words"], n / SR))
        idx = np.minimum((np.arange(n) / SR * 100).astype(int), len(env) - 1)
        duck = np.asarray(env, dtype=np.float32)[idx]
        talking = duck > 0.5
        v_db = rms_db(voice, talking) if talking.any() else rms_db(voice)
        m_db = rms_db(music.mean(axis=1))
        base = 10 ** ((v_db + music_db + duck_db - m_db) / 20)   # level in pauses
        gain = base * 10 ** (-duck_db * duck / 20)                # minus duck while talking
        g_talk, g_pause = float(gain[talking].mean()), float(gain[~talking].mean()) if (~talking).any() else float(gain.mean())
        print(f"DUCK nhạc {music_db:+.0f} dB so với giọng khi có giọng; lúc nghỉ {music_db + duck_db:+.0f} dB "
              f"(đo thực tế: nhạc hạ {20 * np.log10(g_pause / g_talk):.1f} dB khi có giọng)")
        out = music * gain[:, None] + voice[:, None]
    else:
        out = np.repeat(voice[:, None], 2, axis=1)
    out = add_sfx(project, out, -8.0, sfx_db)
    sf.write(tmp / "premix.wav", out, SR, subtype="FLOAT")
    m = loudness(tmp / "premix.wav")
    ff("-i", str(tmp / "premix.wav"), "-af",
       f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
       f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true",
       "-ar", str(SR), str(project / "mix.wav"))
    final = loudness(project / "mix.wav")
    print(f"MIXDONE I={final['input_i']} LUFS TP={final['input_tp']} dBTP")


def music_only(project: Path, total: float, gain_db: float, sfx_db: float = 0.0) -> None:
    """Slideshow không lời: nhạc lặp/cắt đúng độ dài, mờ vào 1 s, mờ ra 2 s, cộng sfx, chuẩn -14 LUFS."""
    import numpy as np
    import soundfile as sf

    tmp = project / "audio"
    tmp.mkdir(exist_ok=True)
    fade_out = max(0.0, total - 2.0)
    bgm = project / "music" / "bgm.wav"
    if bgm.exists():
        ff("-stream_loop", "-1", "-i", str(bgm), "-t", f"{total:.3f}", "-af",
           f"aresample={SR},afade=t=in:d=1,afade=t=out:st={fade_out:.3f}:d=2,volume={gain_db}dB",
           "-ac", "2", str(tmp / "music_cut.wav"))
        base, _ = sf.read(tmp / "music_cut.wav", dtype="float32")
    else:   # không nhạc: chỉ có sfx
        base = np.zeros((int(total * SR), 2), dtype=np.float32)
    mixed = add_sfx(project, base, -2.0 if bgm.exists() else -200.0, sfx_db)
    sf.write(tmp / "premix.wav", mixed, SR, subtype="FLOAT")
    m = loudness(tmp / "premix.wav")
    ff("-i", str(tmp / "premix.wav"), "-af",
       f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
       f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true",
       "-ar", str(SR), str(project / "mix.wav"))
    final = loudness(project / "mix.wav")
    print(f"MIXDONE (chỉ nhạc) I={final['input_i']} LUFS TP={final['input_tp']} dBTP")


def write_srt(project: Path) -> None:
    tl = json.loads((project / "timeline.json").read_text(encoding="utf-8"))
    (project / "phude.srt").write_text(to_srt(tl["captions"]), encoding="utf-8")
    print(f"SRTDONE {len(tl['captions'])} dòng")


def final(project: Path, video: Path, name: str) -> None:
    out_dir = project / "renders"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{name}.mp4"
    srt = project / "phude.srt"
    base = ["-i", str(video), "-i", str(project / "mix.wav")]
    tail = ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)]
    try:
        if not srt.exists():
            raise SystemExit("no srt")
        ff(*base, "-i", str(srt), "-map", "0:v", "-map", "1:a", "-map", "2:s", "-c:s", "mov_text",
           "-metadata:s:s:0", "language=vie", *tail)
    except SystemExit:
        # Minimal ffmpeg builds have no srt demuxer; captions are burned in anyway and phude.srt ships beside.
        ff(*base, "-map", "0:v", "-map", "1:a", *tail)
        if srt.exists():
            print("Lưu ý: không nhúng được phụ đề mềm (ffmpeg thiếu srt); phude.srt giao kèm.")
    print(f"FINAL {out} {out.stat().st_size / 1e6:.1f} MB")
    no_lite = False
    try:
        no_lite = bool(json.loads((Path(project) / "brief.json").read_text(encoding="utf-8")).get("no_lite"))
    except Exception:
        pass
    if out.stat().st_size > LITE_BYTES and not no_lite:
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                    str(out)], capture_output=True, text=True).stdout.strip() or 60)
        kbps = max(300, int(LITE_BYTES * 8 / dur / 1000) - 220)
        lite = out_dir / f"{name}-nhe.mp4"
        ff("-i", str(out), "-map", "0", "-c:v", "libx264", "-b:v", f"{kbps}k", "-maxrate", f"{kbps}k",
           "-bufsize", f"{kbps * 2}k", "-c:a", "copy", "-c:s", "copy", "-movflags", "+faststart", str(lite))
        print(f"LITE {lite} {lite.stat().st_size / 1e6:.1f} MB")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["mix", "srt", "final", "measure"])
    ap.add_argument("project")
    ap.add_argument("--name", default="video")
    ap.add_argument("--video")
    ap.add_argument("--music-db", type=float, default=-6.0, help="music vs voice while talking (dB)")
    ap.add_argument("--duck-db", type=float, default=5.0, help="extra music level in pauses (dB)")
    ap.add_argument("--solo-gain-db", type=float, default=0.0, help="chỉ nhạc (slideshow): chỉnh mức trước khi chuẩn hóa")
    ap.add_argument("--sfx-db", type=float, default=0.0, help="chỉnh mức hiệu ứng âm thanh (dB), 0 là mặc định")
    a = ap.parse_args()
    p = Path(a.project).resolve()
    if a.cmd == "mix":
        if (p / "voice.wav").exists():
            mix(p, a.music_db, a.duck_db, a.sfx_db)
        else:
            music_only(p, json.loads((p / "shots.json").read_text(encoding="utf-8"))["total"], a.solo_gain_db,
                       a.sfx_db)
    elif a.cmd == "srt":
        write_srt(p)
    elif a.cmd == "final":
        final(p, Path(a.video).resolve(), a.name)
    else:
        m = loudness(p if p.is_file() else p / "mix.wav")
        print(f"I={m['input_i']} LUFS TP={m['input_tp']} dBTP LRA={m['input_lra']}")


if __name__ == "__main__":
    main()
