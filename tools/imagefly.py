"""ImageFly: ảnh có sẵn -> video (slideshow hoặc có lời đọc), 9:16 hoặc 16:9.

Lệnh (chạy từ thư mục đang làm việc; dự án nằm ở videos/<slug>/):

  new <slug> --images DIR [--mode slideshow|voiceover] [--aspect 9:16|16:9] [--title ...]
        tạo dự án, chuẩn hóa ảnh (xoay theo EXIF, giảm cỡ), ghi brief.json và images.json
  ingest <du-an> --images DIR     nạp lại ảnh (ghi đè assets/ và images.json)
  voice <du-an>                   script.json -> voice.wav, words.json (chế độ voiceover)
  music <du-an>                   nhạc nền: file người dùng hoặc nhạc tổng hợp (brief.music)
  plan <du-an>                    chia cảnh, chọn hiệu ứng và chuyển cảnh -> shots.json, timeline.json
  compose <du-an>                 viết compositions/<shot>.html và index.html
  mix <du-an>                     trộn âm -> mix.wav (-14 LUFS)
  render <du-an> [--name N]       kiểm tra, render, ghép âm -> renders/<N>.mp4
  build <du-an>                   chạy tất cả theo thứ tự (voice nếu cần) rồi render
  doctor                          kiểm tra máy

Mọi quyết định (thứ tự ảnh, hiệu ứng, thời lượng, chú thích) nằm trong brief.json và
images.json: sửa file rồi chạy lại plan, compose, render.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
NPX = "npx.cmd" if os.name == "nt" else "npx"
HYPERFRAMES = "hyperframes@0.8.145"
SIZES = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}
FPS = 30
OVERLAP = 0.6      # giây chuyển cảnh chồng lên cảnh trước
TAIL = 1.0         # giữ cảnh cuối và mờ dần
MAX_EDGE = 2560

DEFAULT_BRIEF = {
    "title": "",
    "subtitle": "",
    "mode": "slideshow",          # slideshow | voiceover
    "aspect": "9:16",             # 9:16 | 16:9 | 1:1
    "look": "natural",            # natural | warm | cool | cinematic | vivid | bw
    "transition": "mix",          # mix | fade | slide | slideup | zoom | wipe
    "fit": "auto",                # auto | cover | contain
    # nhạc: synth:<calm|inspiring|upbeat|tech> | score (soạn từ music/score.json) | đường dẫn file |
    #       danh sách file (nối, mờ chồng 2 giây) | none
    "music": "synth:inspiring",
    "music_start_s": 0,           # bắt đầu lấy nhạc từ giây thứ mấy của file (chọn đoạn hay nhất)
    "music_db": -14,              # nhạc so với giọng khi giọng đang đọc (dB); nhạc tự hạ xuống mức này
    "duck_db": 6,                 # nhạc to thêm bao nhiêu dB lúc giọng nghỉ (nhạc hồi lại giữa các câu)
    "solo_music_gain_db": 0,      # chỉnh thêm cho slideshow không lời
    # hiệu ứng âm thanh ở chỗ chuyển cảnh và tiêu đề đổi góc. "auto": bật, trừ khi người dùng đưa file nhạc
    # (khi đó chỉ dùng âm thanh người dùng cấp, không thêm âm thanh agent tạo). true/false để ép.
    "sfx": "auto",
    "sfx_db": 0,                  # chỉnh mức sfx (dB), âm để nhỏ đi
    "title_upper": True,          # tiêu đề in hoa
    "title_mode": "fixed",        # fixed: ở yên một góc | roam: đổi góc theo thời gian
    "title_corner": None,         # fixed: top-left | top-right | bottom-left | bottom-right (mặc định tự chọn góc xa chủ thể nhất)
    "title_colors": None,         # danh sách màu tiêu đề theo thời gian (mặc định theo look)
    "title_plan": None,           # [{"t": 3.0, "pos": "top-right", "color": "#FFD23F", "hop": "pop"}] ghi đè tự động
    "title_intro_s": 3.0,         # giây tiêu đề to giữa khung trước khi bay về góc
    "title_hop_s": 3.0,           # tối thiểu bao nhiêu giây giữa hai lần đổi góc
    "shot_beats": 4,              # slideshow: số nhịp mỗi ảnh (nếu biết BPM)
    "shot_s": None,               # slideshow: ép số giây mỗi ảnh
    "clip_s": 4.0,                # slideshow: tối đa bao nhiêu giây lấy từ mỗi clip video (riêng từng clip: "len")
    "duration_s": None,           # slideshow: tổng thời lượng mong muốn
    "burn_captions": True,        # voiceover: in phụ đề lên hình
    "voice": "Ngọc Huyền",
}

MOOD_BPM = {"calm": 84, "inspiring": 96, "upbeat": 112, "tech": 104}

LOOKS = {
    "natural": {"filter": "none", "vignette": 0.28, "tint": ""},
    "warm": {"filter": "saturate(1.12) contrast(1.05) sepia(0.14)", "vignette": 0.30, "tint": "rgba(255,170,80,0.10)"},
    "cool": {"filter": "saturate(1.05) contrast(1.05) hue-rotate(-8deg) brightness(1.02)", "vignette": 0.30,
             "tint": "rgba(70,130,255,0.09)"},
    "cinematic": {"filter": "contrast(1.14) saturate(0.9) brightness(0.96)", "vignette": 0.50,
                  "tint": "rgba(0,70,90,0.12)"},
    "vivid": {"filter": "saturate(1.32) contrast(1.08)", "vignette": 0.22, "tint": ""},
    "bw": {"filter": "grayscale(1) contrast(1.12)", "vignette": 0.45, "tint": ""},
}


# ---------- tiện ích ----------

def venv_python() -> Path | None:
    sub = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    for home in (".imagefly", ".motionfly"):
        p = Path.home() / home / "venv" / sub
        if p.exists():
            return p
    return None


def py() -> str:
    v = venv_python()
    return str(v) if v else sys.executable


def run(cmd: list[str], cwd: Path | None = None, log: Path | None = None) -> int:
    env = {**os.environ, "PYTHONUTF8": "1", "HF_HUB_DISABLE_PROGRESS_BARS": "1"}
    if log:
        with open(log, "w", encoding="utf-8") as f:
            return subprocess.run(cmd, cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT).returncode
    return subprocess.run(cmd, cwd=cwd, env=env).returncode


def jload(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def jsave(p: Path, obj) -> None:
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def need(p: Path, hint: str) -> Path:
    if not p.exists():
        raise SystemExit(f"Thiếu {p.name}: {hint}")
    return p


def brief_of(project: Path) -> dict:
    b = {**DEFAULT_BRIEF, **jload(need(project / "brief.json", "chạy lệnh new trước"))}
    if b["aspect"] not in SIZES:
        raise SystemExit(f"aspect phải là một trong {list(SIZES)}")
    return b


# ---------- nạp ảnh ----------

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mts", ".3gp"}


def probe_video(path: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height:format=duration", "-of", "json", str(path)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    d = json.loads(r.stdout or "{}")
    st = (d.get("streams") or [{}])[0]
    if not st.get("width"):
        raise SystemExit(f"Không đọc được video: {path.name}")
    return {"w": int(st["width"]), "h": int(st["height"]), "dur": float(d["format"]["duration"])}


def ingest_video(project: Path, f: Path, iid: str) -> dict:
    """Chuẩn hóa clip: bỏ tiếng (-an) để chỉ trộn giọng đọc và nhạc mới, H.264 30 fps, khóa hình mỗi giây,
    tối đa 1920 cạnh dài, tự xoay đúng chiều. Lấy khung giữa làm poster, khung cuối giữ hình khi clip hết, nền mờ."""
    from PIL import Image, ImageFilter

    out = project / "assets" / f"{iid}.mp4"
    code = run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(f), "-an", "-vf",
                "scale=1920:1920:force_original_aspect_ratio=decrease:force_divisible_by=2,fps=30,format=yuv420p",
                "-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-g", "30", "-keyint_min", "30",
                "-movflags", "+faststart", str(out)])
    if code or not out.exists():
        raise SystemExit(f"Không chuẩn hóa được clip: {f.name}")
    info = probe_video(out)
    poster, last = project / "assets" / f"{iid}.jpg", project / "assets" / f"{iid}_last.jpg"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{info['dur'] / 2:.2f}", "-i", str(out),
         "-frames:v", "1", "-q:v", "3", str(poster)])
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-sseof", "-0.2", "-i", str(out),
         "-update", "1", "-frames:v", "1", "-q:v", "3", str(last)])
    with Image.open(poster) as im:
        bg = im.convert("RGB")
        bg.thumbnail((540, 540))
        bg.filter(ImageFilter.GaussianBlur(10)).save(project / "assets" / "bg" / f"{iid}.jpg", quality=80)
    return {"id": iid, "type": "video", "source": str(f), "file": f"assets/{iid}.mp4", "poster": f"assets/{iid}.jpg",
            "last": f"assets/{iid}_last.jpg", "bg": f"assets/bg/{iid}.jpg", "w": info["w"], "h": info["h"],
            "dur": round(info["dur"], 2)}


def ingest(project: Path, images_dir: Path, order: str = "name") -> list[dict]:
    from PIL import Image, ImageFilter, ImageOps

    files = [f for f in images_dir.iterdir() if f.suffix.lower() in IMAGE_EXTS | VIDEO_EXTS]
    if not files:
        raise SystemExit(f"Không có ảnh hoặc video trong {images_dir}")

    def date_key(f: Path):
        if f.suffix.lower() in VIDEO_EXTS:
            return (time.strftime("%Y:%m:%d %H:%M:%S", time.localtime(f.stat().st_mtime)), f.name)
        try:
            with Image.open(f) as im:
                ex = im.getexif()
                return (ex.get(36867) or ex.get(306) or "", f.name)
        except OSError:
            return ("", f.name)

    files.sort(key=date_key if order == "date" else (lambda f: f.name.lower()))
    (project / "assets" / "bg").mkdir(parents=True, exist_ok=True)
    out = []
    for i, f in enumerate(files, 1):
        iid = f"i{i:02d}"
        if f.suffix.lower() in VIDEO_EXTS:
            out.append(ingest_video(project, f, iid))
            continue
        with Image.open(f) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            if max(im.size) > MAX_EDGE:
                k = MAX_EDGE / max(im.size)
                im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
            im.save(project / "assets" / f"{iid}.jpg", quality=90, optimize=True)
            bg = im.copy()
            bg.thumbnail((540, 540))
            bg.filter(ImageFilter.GaussianBlur(10)).save(project / "assets" / "bg" / f"{iid}.jpg", quality=80)
            out.append({"id": iid, "type": "image", "source": str(f), "file": f"assets/{iid}.jpg",
                        "bg": f"assets/bg/{iid}.jpg", "w": im.width, "h": im.height})
    jsave(project / "images.json", out)
    return out


# ---------- chia cảnh ----------

def bpm_of(project: Path, brief: dict) -> float | None:
    meta = project / "music" / "beats.json"
    if meta.exists():
        return float(jload(meta).get("bpm") or 0) or None
    m = str(brief["music"])
    if m.startswith("synth:"):
        return MOOD_BPM.get(m.split(":", 1)[1], 96)
    if m == "score" or m.startswith("score:"):
        sp = Path(m.split(":", 1)[1]).expanduser() if ":" in m else project / "music" / "score.json"
        if sp.exists():
            return float(jload(sp).get("bpm") or 0) or None
    return None


def is_wide(im: dict, W: int, H: int) -> bool:
    """Ảnh rộng hơn khung nhiều (ví dụ ảnh ngang trong khung dọc): phủ kín thì chỉ thấy một dải ảnh."""
    return im["w"] / im["h"] > (W / H) * 1.05


def choose_fit(brief: dict, im: dict, W: int, H: int) -> str:
    if im.get("fit") in ("cover", "contain"):
        return im["fit"]
    if brief["fit"] in ("cover", "contain"):
        return brief["fit"]
    r = (im["w"] / im["h"]) / (W / H)
    crop = 1 - min(r, 1 / r)
    return "cover" if crop <= 0.30 else "contain"


def choose_effect(i: int, im: dict, fit: str, W: int, H: int) -> str:
    img_taller = (im["w"] / im["h"]) < (W / H)
    sign = i % 2
    if fit == "contain":
        return ["zoom-in", "drift", "zoom-out", "push-focus"][i % 4]
    seq = ["zoom-in", ("pan-up" if sign else "pan-down") if img_taller else ("pan-left" if sign else "pan-right"),
           "zoom-out", "drift", "push-focus",
           ("pan-down" if sign else "pan-up") if img_taller else ("pan-right" if sign else "pan-left")]
    return seq[i % len(seq)]


TRANSITIONS = ["fade", "slide", "zoom", "wipe", "slideup"]


def choose_transition(brief: dict, i: int) -> str:
    if i == 0:
        return "fade"
    t = brief["transition"]
    return TRANSITIONS[(i - 1) % len(TRANSITIONS)] if t == "mix" else t


def resolve_image(imgs: list[dict], ref: str) -> dict:
    for im in imgs:
        if ref in (im["id"], Path(im["source"]).name, Path(im["source"]).stem, im["file"]):
            return im
    raise SystemExit(f"Không tìm thấy ảnh '{ref}' trong images.json (dùng id như i03 hoặc tên file)")


PALETTES = {
    "natural": ["#FFD23F", "#4CC9F0", "#FF5D8F", "#7CFFB2"],
    "warm": ["#FFC857", "#FF7B54", "#FFE29A", "#FF5D8F"],
    "cool": ["#7DF9FF", "#8AB4FF", "#C3A6FF", "#FFFFFF"],
    "cinematic": ["#F2B138", "#3FD0C9", "#FFFFFF", "#E8553D"],
    "vivid": ["#FFEB3B", "#00E5FF", "#FF4081", "#76FF03"],
    "bw": ["#FFFFFF", "#D9D9D9", "#BFBFBF", "#FFFFFF"],
}
CORNER_XY = {"top-left": (0.1, 0.12), "top-right": (0.9, 0.12), "bottom-left": (0.1, 0.88), "bottom-right": (0.9, 0.88)}
CORNERS = list(CORNER_XY)


def corner_css(pos: str, W: int, H: int, caps_on: bool, s: float) -> dict:
    """Vị trí góc (chỉ dùng transform: x, y theo px, xPercent/yPercent theo cỡ của chính tiêu đề, s là tỉ lệ thu nhỏ).
    Chừa vùng an toàn: đỉnh và đáy của khung dọc hay bị giao diện mạng xã hội che."""
    portrait = H > W
    top = 0.10 if portrait else 0.08
    bottom = (0.78 if caps_on else 0.84) if portrait else (0.86 if caps_on else 0.90)
    v, h = pos.split("-")
    return {"x": round(W * (0.06 if h == "left" else 0.94)), "xPercent": 0 if h == "left" else -round(s * 100, 1),
            "y": round(H * (top if v == "top" else bottom)), "yPercent": 0 if v == "top" else -round(s * 100, 1)}


def plan_title(brief: dict, shots: list[dict], total: float, W: int, H: int, caps_on: bool) -> list[dict]:
    """Tiêu đề to giữa khung lúc mở đầu, sau đó bay về một góc và đổi góc theo thời gian.
    Góc được chọn xa điểm nhấn (focus) của ảnh đang hiện để không che chủ thể; màu xoay theo bảng màu của look."""
    if not brief["title"]:
        return []
    pal = brief["title_colors"] or PALETTES[brief["look"]]
    if brief["title_plan"]:
        segs = []
        for i, e in enumerate(sorted(brief["title_plan"], key=lambda e: e["t"])):
            if e["pos"] not in CORNERS:
                raise SystemExit(f"title_plan.pos phải là một trong {CORNERS}")
            segs.append({"t": float(e["t"]), "pos": e["pos"], "color": e.get("color", pal[i % len(pal)]),
                         "hop": e.get("hop", "move")})
        return segs
    intro = min(float(brief["title_intro_s"]), max(1.5, total * 0.3))
    if brief["title_mode"] == "fixed":
        pos = brief["title_corner"]
        if pos is None:   # góc xa mọi điểm nhấn nhất, để không che chủ thể ở ảnh nào
            pos = max(CORNERS, key=lambda c: min((CORNER_XY[c][0] - s["focus"][0]) ** 2
                                                 + (CORNER_XY[c][1] - s["focus"][1]) ** 2 for s in shots))
        elif pos not in CORNERS:
            raise SystemExit(f"title_corner phải là một trong {CORNERS}")
        return [{"t": round(intro, 3), "pos": pos, "color": pal[0], "hop": "pop"}]
    if brief["title_mode"] != "roam":
        raise SystemExit("title_mode phải là fixed hoặc roam")
    times = [intro]
    for s in shots:
        if s["start"] >= times[-1] + float(brief["title_hop_s"]) and s["start"] < total - 1.5:
            times.append(s["start"])
    segs, prev = [], None
    for k, t in enumerate(times):
        cur = [s for s in shots if s["start"] <= t + 0.2][-1]
        fx, fy = cur["focus"]
        cands = [c for c in CORNERS if c != prev] or CORNERS
        pos = max(cands, key=lambda c: (CORNER_XY[c][0] - fx) ** 2 + (CORNER_XY[c][1] - fy) ** 2)
        segs.append({"t": round(t, 3), "pos": pos, "color": pal[k % len(pal)], "hop": ["move", "pop"][k % 2]})
        prev = pos
    return segs


def plan(project: Path) -> dict:
    sys.path.insert(0, str(TOOLS))
    brief = brief_of(project)
    imgs = [im for im in jload(need(project / "images.json", "chạy ingest trước")) if not im.get("skip")]
    W, H = SIZES[brief["aspect"]]
    shots: list[dict] = []
    words = None

    if brief["mode"] == "slideshow":
        n = len(imgs)
        bpm = bpm_of(project, brief)
        base = brief["shot_s"] or (brief["shot_beats"] * 60 / bpm if bpm else 3.0)
        if brief["duration_s"]:
            base = min(8.0, max(1.5, (brief["duration_s"] - TAIL) / n))
        t = 0.0
        beat_s = 60 / bpm if bpm else None
        for im in imgs:
            if im.get("type") == "video":
                avail = im["dur"] - im.get("trim_start", 0)
                length = min(avail, im.get("len") or brief["clip_s"])
                if beat_s and not im.get("len") and length > beat_s:   # cắt clip trùng nhịp nhạc
                    length = math.floor(length / beat_s) * beat_s
            else:
                length = base * (im.get("beats", brief["shot_beats"]) / brief["shot_beats"]) if "beats" in im else base
            shots.append({"img": im, "start": round(t, 3)})
            t += length
        total = round(t + TAIL, 3)
        captions: list[dict] = []
        scene_spans = None
    else:
        from timeline import captions as make_caps, find_kw, scene_spans as spans_fn
        script = jload(need(project / "script.json", "viết script.json (mỗi cảnh có say và images)"))
        words = jload(need(project / "words.json", "chạy lệnh voice trước"))
        total = words["total"]
        spans = {s["id"]: s for s in spans_fn(words["scenes"], [s["id"] for s in script["scenes"]], total)}
        used = set()
        for sc in script["scenes"]:
            refs = sc.get("images") or ([sc["image"]] if sc.get("image") else [])
            if not refs:
                raise SystemExit(f"Cảnh {sc['id']} chưa gán ảnh (khóa images hoặc image trong script.json)")
            sp = spans[sc["id"]]
            sw = [w for w in words["words"] if w["scene"] == sc["id"]]
            k = len(refs)
            for j, ref in enumerate(refs):
                entry = ref if isinstance(ref, dict) else {"img": ref}
                im = resolve_image(imgs, entry["img"])
                used.add(im["id"])
                if j == 0:
                    st = sp["start"]
                elif entry.get("kw"):
                    tk = find_kw(sw, entry["kw"], entry.get("nth", 1))
                    if tk is None:
                        raise SystemExit(f"KW miss: {sc['id']} \"{entry['kw']}\" không có trong lời đọc")
                    st = max(sp["start"], tk - 0.1)
                else:
                    st = sp["start"] + (sp["end"] - sp["start"]) * j / k
                shots.append({"img": im, "start": round(st, 3)})
        unused = [im["id"] for im in imgs if im["id"] not in used]
        if unused:
            print(f"Lưu ý: ảnh chưa dùng trong script.json: {', '.join(unused)}")
        captions = make_caps(words["segments"], words["words"],
                             34 if H > W else 44)
        scene_spans = True

    last_fit_cover = None
    out = []
    for i, s in enumerate(shots):
        im = s["img"]
        fit = choose_fit(brief, im, W, H)
        nxt = shots[i + 1]["start"] if i + 1 < len(shots) else total
        is_video = im.get("type") == "video"
        vstart = im.get("trim_start", 0) if is_video else 0
        end = round(min(total, nxt + (OVERLAP if i + 1 < len(shots) else 0)), 3)
        if is_video and im["dur"] - vstart < end - s["start"] - 0.05:
            print(f"Lưu ý: clip {im['id']} chỉ còn {im['dur'] - vstart:.1f}s, cảnh dài {end - s['start']:.1f}s: "
                  "giữ khung hình cuối đến hết cảnh")
        out.append({
            "id": f"s{i + 1:02d}", "img": im["id"], "type": "video" if is_video else "image",
            "file": im["file"], "bg": im["bg"], "w": im["w"], "h": im["h"],
            "last": im.get("last"), "vstart": vstart, "vdur": round(im["dur"] - vstart, 3) if is_video else None,
            "start": s["start"], "end": end,
            "fit": fit,
            # phủ kín ảnh rộng trong khung hẹp: camera quét ngang giữa các điểm nhấn (focus, focus_to)
            "effect": im.get("effect") or ("sweep" if fit == "cover" and is_wide(im, W, H)
                                           else choose_effect(i, im, fit, W, H)),
            "transition": im.get("transition") or choose_transition(brief, i),
            "focus": im.get("focus", [0.5, 0.5]), "focus_to": im.get("focus_to"), "caption": im.get("caption", ""),
        })
    caps_on = bool(captions) and brief["burn_captions"]
    tplan = plan_title(brief, out, total, W, H, caps_on)
    jsave(project / "shots.json", {"total": total, "width": W, "height": H, "shots": out, "title_plan": tplan})
    for t in tplan:
        print(f"  tiêu đề {t['t']:>5.2f}s -> {t['pos']:<12} {t['color']} {t['hop']}")

    tl = {"fps": FPS, "width": W, "height": H, "duration": total, "style": "imagefly",
          "scenes": [{"id": s["id"], "start": s["start"], "end": s["end"], "anchors": {}} for s in out],
          "captions": captions, "burn_captions": bool(captions) and brief["burn_captions"],
          "words": words["words"] if words else []}
    jsave(project / "timeline.json", tl)
    jsave(project / "storyboard.json", {"title": brief["title"] or project.name, "aspect": brief["aspect"],
                                        "style": "imagefly", "scenes": [{"id": s["id"], "visual": s["img"]} for s in out]})
    print(f"PLAN {len(out)} cảnh, {total}s, {brief['aspect']} ({W}x{H}), chế độ {brief['mode']}")
    for s in out:
        kind = "clip" if s["type"] == "video" else "anh "
        print(f"  {s['id']} {s['img']} {kind} {s['start']:>6.2f}s-{s['end']:>6.2f}s {s['fit']:<7} {s['effect']:<10} {s['transition']}")
    return {"total": total, "shots": out}


# ---------- dựng composition ----------

SHOT_HTML = r"""<!doctype html>
<html>
  <head>
    <meta charset="UTF-8" />
    <!-- Cảnh __SID__ do ImageFly sinh tự động từ shots.json; sửa shots.json/images.json rồi chạy lại compose. -->
  </head>
  <body>
    <template>
      <style>
        @font-face { font-family: "Be Vietnam Pro"; src: url("fonts/BeVietnamPro-Medium.ttf"); font-weight: 500; }
        @font-face { font-family: "Be Vietnam Pro"; src: url("fonts/BeVietnamPro-Bold.ttf"); font-weight: 700; }
        @font-face { font-family: "Be Vietnam Pro"; src: url("fonts/BeVietnamPro-ExtraBold.ttf"); font-weight: 800; }
        #__SID__-root { position: absolute; inset: 0; overflow: hidden; font-family: "Be Vietnam Pro", sans-serif; }
        #__SID__-stage { position: absolute; inset: 0; overflow: hidden; }
        #__SID__-bgwrap, #__SID__-cam { position: absolute; inset: 0; will-change: transform; }
        #__SID__-bgwrap img { position: absolute; inset: -4%; width: 108%; height: 108%; object-fit: cover; filter: __FILTER__ brightness(0.62); }
        #__SID__-media { position: absolute; inset: 0; }
        #__SID__-media img, #__SID__-media video { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: __FIT__;
          object-position: __OPOS__; filter: __FILTER__; }
        #__SID__-media .shadow { filter: __FILTER__ drop-shadow(0 18px 40px rgba(0,0,0,0.55)); }
        #__SID__-grade { position: absolute; inset: 0; pointer-events: none; background: __GRADE__; }
        #__SID__-cap { position: absolute; left: 7%; right: 7%; bottom: __CAP_BOTTOM__; text-align: center; color: #fff; opacity: 0;
          font-size: __CAP__px; font-weight: 700; line-height: 1.25; text-shadow: 0 3px 18px rgba(0,0,0,0.8); }
      </style>

      <div id="__SID__-root" data-composition-id="__SID__" data-width="__W__" data-height="__H__">
        <div id="__SID__-stage">
          __BG__
          <div id="__SID__-cam"><div id="__SID__-media" __MEDIASTYLE__>__MEDIA__</div></div>
          <div id="__SID__-grade"></div>
          __CAPTION__
        </div>
      </div>

      <script>
        (() => {
          const cfg = __CFG__;
          const tl = gsap.timeline({ paused: true });
          const id = cfg.sid, D = cfg.dur, T = cfg.ov;
          const cam = "#" + id + "-cam", bgw = "#" + id + "-bgwrap", stage = "#" + id + "-stage";
          tl.fromTo(cam, cfg.cam.from, { ...cfg.cam.to, duration: D, ease: "none" }, 0);
          if (cfg.sweep) tl.fromTo("#" + id + "-media", { x: cfg.sweep.x0 }, { x: cfg.sweep.x1, duration: D, ease: "none" }, 0);
          if (cfg.hasBg) tl.fromTo(bgw, cfg.bgcam.from, { ...cfg.bgcam.to, duration: D, ease: "none" }, 0);
          const tin = {
            fade: () => tl.fromTo(stage, { opacity: 0 }, { opacity: 1, duration: T, ease: "power1.inOut" }, 0),
            slide: () => tl.fromTo(stage, { xPercent: 100 }, { xPercent: 0, duration: T, ease: "power3.inOut" }, 0),
            slideup: () => tl.fromTo(stage, { yPercent: 100 }, { yPercent: 0, duration: T, ease: "power3.inOut" }, 0),
            zoom: () => tl.fromTo(stage, { scale: 1.4, opacity: 0 }, { scale: 1, opacity: 1, duration: T, ease: "power2.out" }, 0),
            wipe: () => tl.fromTo(stage, { clipPath: "inset(0% 100% 0% 0%)" }, { clipPath: "inset(0% 0% 0% 0%)", duration: T, ease: "power2.inOut" }, 0),
          };
          (tin[cfg.tin] || tin.fade)();
          if (cfg.first) tl.fromTo(stage, { opacity: 0 }, { opacity: 1, duration: 0.8, ease: "power1.out" }, 0);
          if (cfg.last) tl.to(stage, { opacity: 0, duration: 0.9, ease: "power1.in" }, Math.max(0, D - 0.9));
          if (cfg.caption) {
            const c = "#" + id + "-cap";
            tl.fromTo(c, { y: 20, opacity: 0 }, { y: 0, opacity: 1, duration: 0.5, ease: "power2.out" }, 0.7);
            tl.to(c, { opacity: 0, duration: 0.4 }, Math.max(1.2, D - T - 0.5));
          }
          window.__timelines[id] = tl;
        })();
      </script>
    </template>
  </body>
</html>
"""


def camera(effect: str, focus: list[float]) -> dict:
    fx, fy = focus
    org = f"{fx * 100:.0f}% {fy * 100:.0f}%"
    z0, z1, pan = 1.0, 1.16, 4.5
    base = {"transformOrigin": org}
    table = {
        "zoom-in": ({"scale": 1.0}, {"scale": 1.16}),
        "zoom-out": ({"scale": 1.16}, {"scale": 1.0}),
        "push-focus": ({"scale": 1.0}, {"scale": 1.3}),
        "pan-left": ({"scale": 1.16, "xPercent": pan}, {"scale": 1.16, "xPercent": -pan}),
        "pan-right": ({"scale": 1.16, "xPercent": -pan}, {"scale": 1.16, "xPercent": pan}),
        "pan-up": ({"scale": 1.16, "yPercent": pan}, {"scale": 1.16, "yPercent": -pan}),
        "pan-down": ({"scale": 1.16, "yPercent": -pan}, {"scale": 1.16, "yPercent": pan}),
        "drift": ({"scale": 1.08, "xPercent": -2, "yPercent": 2}, {"scale": 1.17, "xPercent": 2, "yPercent": -2}),
        "none": ({"scale": 1.0}, {"scale": 1.0}),
    }
    if effect not in table:
        raise SystemExit(f"Hiệu ứng '{effect}' không có. Chọn: {', '.join(table)}")
    a, b = table[effect]
    return {"from": {**base, **a}, "to": b}


def parallax_bg(cam: dict) -> dict:
    """Nền mờ chuyển động ngược nhẹ so với ảnh chính để tạo chiều sâu."""
    f, t = cam["from"], cam["to"]
    inv = lambda d: {**{k: v for k, v in d.items() if k == "scale"}, "scale": 1 + (d["scale"] - 1) * 0.35,
                     **({"xPercent": -d["xPercent"] * 0.6} if "xPercent" in d else {}),
                     **({"yPercent": -d["yPercent"] * 0.6} if "yPercent" in d else {})}
    return {"from": inv(f), "to": inv(t)}


TITLE_HTML = r"""<!doctype html>
<html>
  <head>
    <meta charset="UTF-8" />
    <!-- Tiêu đề chạy suốt video: to giữa khung lúc mở đầu, rồi đổi góc theo title_plan trong shots.json. -->
  </head>
  <body>
    <template>
      <style>
        @font-face { font-family: "Be Vietnam Pro"; src: url("fonts/BeVietnamPro-Bold.ttf"); font-weight: 700; }
        @font-face { font-family: "Be Vietnam Pro"; src: url("fonts/BeVietnamPro-Medium.ttf"); font-weight: 500; }
        @font-face { font-family: "Be Vietnam Pro"; src: url("fonts/BeVietnamPro-ExtraBold.ttf"); font-weight: 800; }
        #_title-root { position: absolute; inset: 0; overflow: hidden; font-family: "Be Vietnam Pro", sans-serif; }
        #ttl { position: absolute; left: 0; top: 0; display: flex; gap: 18px; align-items: stretch; max-width: 88%;
          padding: 12px 22px 12px 16px; border-radius: 14px; background: rgba(0,0,0,0); transform-origin: 0 0; }
        #ttl-bar { width: 8px; border-radius: 4px; background: __C0__; flex: none; }
        #ttl-in { display: flex; flex-direction: column; justify-content: center; }
        #ttl-text { font-size: __BIG__px; font-weight: 800; letter-spacing: 0.06em; line-height: 1.1; color: __C0__;
          text-shadow: 0 3px 22px rgba(0,0,0,0.75), 0 0 30px __GLOW__; }
        #ttl-text .w { display: inline-block; white-space: nowrap; margin-right: 0.3em; }
        #ttl-text .ch { display: inline-block; }
        #ttl-sub { position: absolute; left: 42px; top: 100%; margin-top: 6px; width: max-content; max-width: 100%;
          font-size: 40px; font-weight: 500; color: #fff; letter-spacing: 0.04em;
          text-shadow: 0 2px 14px rgba(0,0,0,0.8); }
      </style>

      <div id="_title-root" data-composition-id="_title" data-width="__W__" data-height="__H__">
        <div id="ttl" data-layout-allow-overflow><div id="ttl-bar"></div><div id="ttl-in" data-layout-allow-overflow><div id="ttl-text" data-layout-allow-overflow>__TEXT__</div></div>__SUB__</div>
      </div>

      <script>
        (() => {
          const cfg = __CFG__;
          const tl = gsap.timeline({ paused: true });
          const el = "#ttl", txt = "#ttl-text", bar = "#ttl-bar", inn = "#ttl-in", sub = "#ttl-sub";
          tl.set(el, { x: cfg.W / 2, y: cfg.H / 2, xPercent: -50, yPercent: -50, scale: 1 }, 0);
          tl.fromTo(".ch", { y: 70, opacity: 0, rotateX: -80 },
            { y: 0, opacity: 1, rotateX: 0, duration: 0.7, ease: "back.out(1.8)", stagger: 0.035 }, 0.3);
          tl.fromTo(bar, { scaleY: 0, transformOrigin: "50% 0%" }, { scaleY: 1, duration: 0.6, ease: "power3.out" }, 0.6);
          if (cfg.hasSub) tl.fromTo(sub, { opacity: 0, y: 18 }, { opacity: 1, y: 0, duration: 0.6 }, 1.1);
          cfg.segs.forEach((seg, i) => {
            const p = cfg.pos[seg.pos], at = seg.t;
            tl.to(el, { x: p.x, y: p.y, xPercent: p.xPercent, yPercent: p.yPercent, scale: cfg.s,
              backgroundColor: "rgba(8,10,14,0.7)", duration: 0.9, ease: "power3.inOut" }, at);
            tl.to(txt, { color: seg.color, duration: 0.9 }, at);
            tl.to(bar, { backgroundColor: seg.color, duration: 0.9 }, at);
            if (i === 0 && cfg.hasSub) tl.to(sub, { opacity: 0, duration: 0.5 }, at);
            if (seg.hop === "pop") {
              tl.fromTo(inn, { scale: 1.2 }, { scale: 1, duration: 0.6, ease: "back.out(2.4)" }, at + 0.75);
            } else {
              tl.to(".ch", { y: -9, duration: 0.2, stagger: 0.025, yoyo: true, repeat: 1, ease: "sine.inOut" }, at + 0.8);
            }
          });
          tl.to(el, { opacity: 0, duration: 0.8, ease: "power1.in" }, Math.max(0, cfg.total - 1.0));
          window.__timelines["_title"] = tl;
        })();
      </script>
    </template>
  </body>
</html>
"""


def write_title(project: Path, brief: dict, sh: dict) -> None:
    f = project / "compositions" / "_title.html"
    segs = sh.get("title_plan") or []
    if not brief["title"] or not segs:
        f.unlink(missing_ok=True)
        return
    W, H = sh["width"], sh["height"]
    portrait = H > W
    caps_on = bool(jload(project / "timeline.json")["captions"]) and brief["burn_captions"]
    text = brief["title"].upper() if brief["title_upper"] else brief["title"]
    words = "".join('<span class="w" data-layout-allow-overflow>'
                    + "".join(f'<span class="ch" data-layout-allow-overflow>{esc(c)}</span>' for c in w) + "</span>"
                    for w in text.split())
    sub = f'<div id="ttl-sub">{esc(brief["subtitle"])}</div>' if brief["subtitle"] else ""
    c0 = segs[0]["color"]
    big, small = (76, 40) if portrait else (104, 38)
    s = round(small / big, 3)
    cfg = {"segs": segs, "total": sh["total"], "hasSub": bool(sub), "W": W, "H": H, "s": s,
           "pos": {c: corner_css(c, W, H, caps_on, s) for c in CORNERS}}
    html = (TITLE_HTML.replace("__CFG__", json.dumps(cfg, ensure_ascii=False)).replace("__TEXT__", words)
            .replace("__SUB__", sub).replace("__C0__", c0).replace("__GLOW__", c0 + "99")
            .replace("__BIG__", str(big)).replace("__W__", str(W)).replace("__H__", str(H)))
    f.write_text(html, encoding="utf-8")


def compose(project: Path) -> None:
    brief = brief_of(project)
    sh = jload(need(project / "shots.json", "chạy plan trước"))
    W, H = sh["width"], sh["height"]
    look = LOOKS.get(brief["look"])
    if not look:
        raise SystemExit(f"look '{brief['look']}' không có. Chọn: {', '.join(LOOKS)}")
    portrait = H > W
    comp = project / "compositions"
    comp.mkdir(exist_ok=True)
    grade = f"radial-gradient(ellipse at center, rgba(0,0,0,0) 55%, rgba(0,0,0,{look['vignette']}) 100%)"
    if look["tint"]:
        grade = f"{grade}, {look['tint']}"
    for i, s in enumerate(sh["shots"]):
        sid = s["id"]
        sweep, media_style = None, ""
        if s["effect"] == "sweep":
            # ảnh giữ nguyên chiều cao khung, rộng hơn khung; trượt cửa sổ nhìn từ điểm nhấn này sang điểm nhấn kia (px, chỉ dùng transform)
            img_w = H * s["w"] / s["h"]
            half = W / img_w / 2
            c0 = min(max(s["focus"][0], half), 1 - half)
            to = s.get("focus_to")
            c1 = min(max(to[0] if to else c0 + (0.03 if i % 2 == 0 else -0.03), half), 1 - half)
            sweep = {"x0": round(-(c0 * img_w - W / 2)), "x1": round(-(c1 * img_w - W / 2))}
            media_style = f'style="left:0; right:auto; width:{img_w:.1f}px;"'
            cam = {"from": {"scale": 1.0, "transformOrigin": "50% 50%"}, "to": {"scale": 1.08}}
        else:
            cam = camera(s["effect"], s["focus"])
        hasbg = s["fit"] == "contain"
        cap_html = f'<div id="{sid}-cap">{esc(s["caption"])}</div>' if s["caption"] else ""
        cfg = {"sid": sid, "dur": round(s["end"] - s["start"], 3), "ov": OVERLAP, "cam": cam,
               "bgcam": parallax_bg(cam), "hasBg": hasbg, "tin": s["transition"], "first": i == 0,
               "last": i == len(sh["shots"]) - 1, "caption": bool(s["caption"]), "sweep": sweep}
        fx, fy = s["focus"]
        cls = ' class="shadow"' if hasbg else ""
        if s.get("type") == "video":
            # clip đã bỏ tiếng từ lúc nạp; khung cuối nằm dưới để hình không biến mất khi clip hết trước cảnh;
            # data-media-start cắt điểm vào; thời lượng không quá phần clip còn lại
            vdur = round(min(s["end"] - s["start"], s["vdur"]), 3)
            media = (f'<img{cls} src="{s["last"]}" />'
                     f'<video id="{sid}-vid"{cls} src="{s["file"]}" muted playsinline data-start="0" '
                     f'data-duration="{vdur}" data-media-start="{s["vstart"]}"></video>')
        else:
            media = f'<img id="{sid}-img"{cls} src="{s["file"]}" />'
        html = (SHOT_HTML
                .replace("__CFG__", json.dumps(cfg, ensure_ascii=False))
                .replace("__BG__", f'<div id="{sid}-bgwrap"><img src="{s["bg"]}" /></div>' if hasbg else "")
                .replace("__CAPTION__", cap_html)
                .replace("__MEDIA__", media).replace("__MEDIASTYLE__", media_style)
                .replace("__FIT__", s["fit"])
                .replace("__OPOS__", f"{fx * 100:.0f}% {fy * 100:.0f}%")
                .replace("__FILTER__", look["filter"] if look["filter"] != "none" else "")
                .replace("__GRADE__", grade)
                .replace("__CAP_BOTTOM__", "13%" if portrait else "9%")
                .replace("__CAP__", "44" if portrait else "42")
                .replace("__SID__", sid).replace("__W__", str(W)).replace("__H__", str(H)))
        (comp / f"{sid}.html").write_text(html, encoding="utf-8")
    write_title(project, brief, sh)
    theme = project / "theme.css"
    theme.write_text(":root {\n  --bg: #000000;\n  --ink: #ffffff;\n  --accent: #f2b138;\n"
                     "  --cap-bg: rgba(8, 10, 14, 0.62);\n  --cap-ink: #ffffff;\n}\n", encoding="utf-8")
    audio = (project / "mix.wav").exists()
    code = run([py(), str(TOOLS / "assemble.py"), str(project)] + ([] if audio else ["--no-audio"]))
    if code:
        raise SystemExit("assemble lỗi")
    print(f"COMPOSE {len(sh['shots'])} cảnh -> compositions/, index.html")


def esc(t: str) -> str:
    return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ---------- âm thanh ----------

def music(project: Path) -> None:
    brief = brief_of(project)
    total = jload(need(project / "shots.json", "chạy plan trước"))["total"]
    m = brief["music"]
    out = project / "music"
    out.mkdir(exist_ok=True)
    for stale in (out / "bgm.wav", out / "beats.json"):   # không để nhạc cũ lọt vào bản mới
        stale.unlink(missing_ok=True)
    if not m or m == "none":
        print("MUSIC none (không nhạc)")
        return
    dur = total + 1
    if isinstance(m, str) and m.startswith("synth:"):
        code = run([py(), str(TOOLS / "music" / "synth.py"), str(project), "--duration", str(dur),
                    "--mood", m.split(":", 1)[1]])
    elif isinstance(m, str) and (m == "score" or m.startswith("score:")):
        cmd = [py(), str(TOOLS / "music" / "score.py"), str(project), "--duration", str(dur)]
        if ":" in m:
            cmd += ["--score", str(Path(m.split(":", 1)[1]).expanduser())]
        code = run(cmd)
    else:
        files = [Path(x).expanduser() for x in (m if isinstance(m, list) else [m])]
        for src in files:
            if not src.exists():
                raise SystemExit(f"Không thấy file nhạc: {src}")
        ss = ["-ss", str(brief["music_start_s"])] if brief["music_start_s"] else []
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
        for k, src in enumerate(files):
            cmd += (ss if k == 0 else []) + ["-i", str(src)]
        if len(files) > 1:   # nối các bài, mờ chồng 2 giây
            chain, last = "", "[0]"
            for k in range(1, len(files)):
                chain += f"{last}[{k}]acrossfade=d=2[a{k}];"
                last = f"[a{k}]"
            cmd += ["-filter_complex", chain.rstrip(";"), "-map", last]
        code = run(cmd + ["-t", str(dur + 5), "-ar", "48000", "-ac", "2", str(out / "bgm.wav")])
        bpm = subprocess.run([py(), str(ROOT / "vendor" / "bestagentkits" / "fit-beat-grid.py"), str(out / "bgm.wav"),
                              "--min-bpm", "70", "--max-bpm", "140"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace").stdout
        mt = re.search(r"BPM\D+([\d.]+)", bpm)
        mb = re.search(r"BEAT0\D+([\d.]+)", bpm)
        if mt:
            jsave(out / "beats.json", {"bpm": float(mt.group(1)), "beat0": float(mb.group(1)) if mb else 0.0,
                                       "source": "fit-beat-grid"})
            print(f"Đã đo nhịp: {mt.group(1)} BPM (chạy plan lại để cắt ảnh theo nhịp)")
    if code:
        raise SystemExit("Tạo nhạc lỗi")


def user_audio(brief: dict) -> bool:
    """True khi music là file (hoặc danh sách file) do người dùng cấp, không phải nhạc agent tạo."""
    m = brief["music"]
    return isinstance(m, list) or (isinstance(m, str) and m not in ("", "none", "score")
                                   and not m.startswith(("synth:", "score:")))


def sfx_on(brief: dict) -> bool:
    return (not user_audio(brief)) if brief["sfx"] == "auto" else bool(brief["sfx"])


def mix(project: Path) -> None:
    brief = brief_of(project)
    sfx = project / "sfx.wav"
    sfx.unlink(missing_ok=True)
    (project / "sfx.json").unlink(missing_ok=True)
    if user_audio(brief) and brief["sfx"] == "auto":
        print("Có file âm thanh người dùng cấp: chỉ dùng file đó, bỏ nhạc tổng hợp và hiệu ứng âm thanh do agent tạo")
    if sfx_on(brief):
        if run([py(), str(TOOLS / "audio" / "sfx.py"), str(project)]):
            raise SystemExit("Tạo hiệu ứng âm thanh lỗi")
    if not (project / "music" / "bgm.wav").exists() and not (project / "voice.wav").exists() and not sfx.exists():
        (project / "mix.wav").unlink(missing_ok=True)
        print("MIX bỏ qua: không có nhạc, giọng và sfx (video không tiếng)")
        return
    cmd = [py(), str(TOOLS / "audio" / "mix.py"), "mix", str(project), "--music-db", str(brief["music_db"]),
           "--duck-db", str(brief["duck_db"]), "--solo-gain-db", str(brief["solo_music_gain_db"]), "--sfx-db", str(brief["sfx_db"])]
    if run(cmd):
        raise SystemExit("Trộn âm lỗi")


# ---------- render ----------

def render(project: Path, name: str | None) -> None:
    brief = brief_of(project)
    name = name or re.sub(r"[^\w-]+", "-", brief["title"] or project.name, flags=re.UNICODE).strip("-").lower() or "video"
    (project / "renders").mkdir(exist_ok=True)
    has_audio = (project / "mix.wav").exists()
    run([py(), str(TOOLS / "assemble.py"), str(project), "--no-audio"])
    chk = subprocess.run([NPX, "-y", HYPERFRAMES, "check"], cwd=project, capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    (project / "renders").joinpath("check.log").write_text(chk.stdout + chk.stderr, encoding="utf-8")
    print((chk.stdout + chk.stderr).strip().splitlines()[-1] if (chk.stdout + chk.stderr).strip() else "check: (không có đầu ra)")
    if chk.returncode:
        raise SystemExit("hyperframes check lỗi, xem renders/check.log")
    raw = project / "renders" / "raw.mp4"
    print("Đang render (khoảng 2 giây máy cho mỗi giây video)...")
    code = run([NPX, "-y", HYPERFRAMES, "render", "--output", str(raw)], cwd=project, log=project / "renders" / "render.log")
    if code or not raw.exists():
        raise SystemExit("Render lỗi, xem renders/render.log")
    final = project / "renders" / f"{name}.mp4"
    if (project / "timeline.json").exists() and jload(project / "timeline.json")["captions"]:
        run([py(), str(TOOLS / "audio" / "mix.py"), "srt", str(project)])
    if has_audio:
        if run([py(), str(TOOLS / "audio" / "mix.py"), "final", str(project), "--video", str(raw), "--name", name]):
            raise SystemExit("Ghép âm lỗi")
    else:
        shutil.copy2(raw, final)
        print(f"FINAL {final} (không tiếng)")
    if has_audio:   # trả index.html về bản có tiếng để xem trước
        run([py(), str(TOOLS / "assemble.py"), str(project)])


def voice(project: Path) -> None:
    need(project / "script.json", "viết script.json (title, voice, scenes[{id, say, images}])")
    code = run([py(), str(TOOLS / "voice" / "voice.py"), str(project)], log=project / "voice.log")
    log = (project / "voice.log").read_text(encoding="utf-8", errors="replace")
    print(log[-1500:])
    if code or "VOICEDONE" not in log:
        raise SystemExit("Sinh giọng lỗi, xem voice.log")


def build(project: Path, name: str | None) -> None:
    brief = brief_of(project)
    if brief["mode"] == "voiceover" and not (project / "words.json").exists():
        voice(project)
    plan(project)
    music(project)
    mix(project)
    compose(project)
    render(project, name)


# ---------- dự án mới ----------

def slugify(s: str) -> str:
    s = re.sub(r"[^\w\s-]", "", s.lower(), flags=re.UNICODE)
    return re.sub(r"[-\s]+", "-", s).strip("-") or "video"


def new(slug: str, images: Path, args) -> Path:
    project = Path("videos") / slugify(slug)
    project = project.resolve()
    if (project / "brief.json").exists():
        raise SystemExit(f"{project} đã có. Dùng tên khác hoặc chạy ingest để nạp lại ảnh.")
    project.mkdir(parents=True, exist_ok=True)
    brief = {**DEFAULT_BRIEF, "title": args.title or "", "mode": args.mode, "aspect": args.aspect,
             "look": args.look, "music": args.music}
    jsave(project / "brief.json", brief)
    imgs = ingest(project, images, args.order)
    n_clip = sum(1 for im in imgs if im.get("type") == "video")
    print(f"NEW {project}\n  {len(imgs) - n_clip} ảnh, {n_clip} clip video (clip đã bỏ tiếng):")
    for im in imgs:
        kind = f"clip {im['dur']:.1f}s" if im.get("type") == "video" else "ảnh"
        print(f"  {im['id']} {kind:<10} {im['w']}x{im['h']} {'dọc' if im['h'] > im['w'] else 'ngang'}  {Path(im['source']).name}")
    return project


def main() -> None:
    v = venv_python()
    if v and Path(sys.executable).resolve() != v.resolve() and not os.environ.get("IMAGEFLY_NOREEXEC"):
        sys.exit(subprocess.run([str(v), __file__, *sys.argv[1:]],
                                env={**os.environ, "IMAGEFLY_NOREEXEC": "1", "PYTHONUTF8": "1"}).returncode)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    n = sp.add_parser("new")
    n.add_argument("slug")
    n.add_argument("--images", required=True)
    n.add_argument("--mode", choices=["slideshow", "voiceover"], default="slideshow")
    n.add_argument("--aspect", choices=list(SIZES), default="9:16")
    n.add_argument("--title", default="")
    n.add_argument("--look", choices=list(LOOKS), default="natural")
    n.add_argument("--music", default="synth:inspiring")
    n.add_argument("--order", choices=["name", "date"], default="name")
    g = sp.add_parser("ingest")
    g.add_argument("project")
    g.add_argument("--images", required=True)
    g.add_argument("--order", choices=["name", "date"], default="name")
    for c in ("voice", "music", "plan", "compose", "mix"):
        sp.add_parser(c).add_argument("project")
    for c in ("render", "build"):
        r = sp.add_parser(c)
        r.add_argument("project")
        r.add_argument("--name")
    sp.add_parser("doctor")
    a = ap.parse_args()
    if a.cmd == "doctor":
        sys.exit(run([sys.executable, str(TOOLS / "setup" / "doctor.py")]))
    if a.cmd == "new":
        new(a.slug, Path(a.images).expanduser().resolve(), a)
        return
    project = Path(a.project).resolve()
    if a.cmd == "ingest":
        print(f"INGEST {len(ingest(project, Path(a.images).expanduser().resolve(), a.order))} ảnh")
    elif a.cmd == "voice":
        voice(project)
    elif a.cmd == "music":
        music(project)
    elif a.cmd == "plan":
        plan(project)
    elif a.cmd == "compose":
        compose(project)
    elif a.cmd == "mix":
        mix(project)
    elif a.cmd == "render":
        render(project, a.name)
    elif a.cmd == "build":
        build(project, a.name)


if __name__ == "__main__":
    main()
