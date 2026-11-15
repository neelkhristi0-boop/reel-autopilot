"""Clipping mode: turns long source videos (a Google Drive folder you own) into captioned vertical clips."""
import json
import os
import re
import subprocess
from pathlib import Path

from . import script
from .common import COMPOSER, OUT, ROOT, env
from .instagram import NeedsInput

VIDEO_EXT = (".mp4", ".mov", ".mkv", ".webm", ".m4v")
TRANSCRIPTS = Path(os.environ.get("TRANSCRIPT_DIR") or ROOT / "data" / "transcripts")


def list_sources(folder):
    """[{id, name}] for every video in the Drive folder (or a local folder, used by tests)."""
    if os.path.isdir(folder):
        return [{"id": p.name, "name": p.name, "local": str(p)} for p in sorted(Path(folder).iterdir()) if p.suffix.lower() in VIDEO_EXT]
    import gdown
    files = gdown.download_folder(url=folder, skip_download=True, quiet=True, use_cookies=False)
    if not files:
        raise NeedsInput("The Drive folder is empty or not shared as 'Anyone with the link'")
    return [{"id": f.id, "name": os.path.basename(f.path)} for f in files if f.path.lower().endswith(VIDEO_EXT)]


def fetch(src, dest):
    if src.get("local"):
        return src["local"]
    import gdown
    if not Path(dest).exists():
        gdown.download(id=src["id"], output=str(dest), quiet=True, use_cookies=False)
    return str(dest)


def transcribe(video, key):
    """Word-timed transcript, cached in the repo so each source is transcribed only once."""
    cache = TRANSCRIPTS / (re.sub(r"[^\w.-]", "_", key) + ".json")
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    from faster_whisper import WhisperModel
    wav = OUT / "source.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", video, "-ar", "16000", "-ac", "1", str(wav)], check=True)
    model = WhisperModel(env("WHISPER_MODEL", "small"), device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(wav), word_timestamps=True, vad_filter=True)
    segs = [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip(),
             "words": [{"word": w.word.strip(), "start": round(w.start, 2), "end": round(w.end, 2)} for w in (s.words or [])]}
            for s in segments]
    wav.unlink(missing_ok=True)
    TRANSCRIPTS.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(segs, ensure_ascii=False), encoding="utf-8")
    return segs


def _free(a, b, used):
    return all(b <= u[0] or a >= u[1] for u in used)


def _windows(segs, used, lo, hi):
    """Every window that starts and ends on a sentence boundary, fits the length and is unused."""
    out = []
    for i, s in enumerate(segs):
        for j in range(i, len(segs)):
            d = segs[j]["end"] - s["start"]
            if d > hi:
                break
            if d >= lo and _free(s["start"], segs[j]["end"], used):
                out.append((i, j))
    return out


PICK = """You choose the single best short clip from a long video's transcript for the Instagram page "{name}" ({niche}).

A good clip: starts on a hook (a surprising claim, a question, a strong opinion or the start of a story), makes sense
with no other context, and ends on a complete thought. Length {lo} to {hi} seconds.

WHAT THE NUMBERS SAY ABOUT THIS PAGE:
{learned}

TRANSCRIPT (each line: [start-end seconds] text). Lines marked USED are taken, do not overlap them.
{lines}

Reply with ONLY a JSON object:
{{"start": <start seconds of the first line of the clip>, "end": <end seconds of the last line>,
  "title": "on-screen hook, max 8 words", "caption": "Instagram caption, 2 short lines ending in a question",
  "hashtags": ["8 to 12 hashtags without #"]}}"""


def pick(page, segs, used, learned=""):
    lo, hi = page.get("clip_seconds", [20, 45])
    wins = _windows(segs, used, lo, hi)
    if not wins:
        return None
    if env("GEMINI_API_KEY"):
        lines = "\n".join(f"[{s['start']}-{s['end']}] {s['text']}" + ("" if _free(s["start"], s["end"], used) else "  USED") for s in segs)
        prompt = PICK.format(name=page["name"], niche=" ".join(page["niche"].split()), lo=lo, hi=hi, lines=lines[:60000], learned=learned or "(no data yet)")
        for attempt in range(2):
            try:
                d = script._json(script._call(prompt, search=False))
                i = min(range(len(segs)), key=lambda k: abs(segs[k]["start"] - float(d["start"])))
                j = min(range(len(segs)), key=lambda k: abs(segs[k]["end"] - float(d["end"])))
                if (i, j) not in wins:  # snap the model's choice to the nearest valid window
                    i, j = min(wins, key=lambda w: abs(w[0] - i) + abs(w[1] - j))
                tags = [re.sub(r"[^\w]", "", str(h)) for h in d.get("hashtags", [])]
                return {"i": i, "j": j, "title": str(d.get("title", ""))[:70], "caption": str(d.get("caption", ""))[:1200], "hashtags": [t for t in tags if t][:15]}
            except Exception as e:
                print(f"  clip pick attempt {attempt + 1} failed: {e}")
    # no key or the model failed: densest speech wins
    i, j = max(wins, key=lambda w: sum(len(s["text"].split()) for s in segs[w[0]:w[1] + 1]) / (segs[w[1]]["end"] - segs[w[0]]["start"]))
    first = segs[i]["text"]
    return {"i": i, "j": j, "title": " ".join(first.split()[:7]), "caption": first, "hashtags": []}


def cut(video, start, end, out):
    """Cuts [start, end] and fits it to 1080x1920. Landscape sources sit on a blurred copy of themselves."""
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:stream_side_data=rotation",
                            "-of", "json", video], capture_output=True, text=True, check=True)
    st = json.loads(probe.stdout)["streams"][0]
    w, h = st["width"], st["height"]
    if any(abs(int(sd.get("rotation", 0))) in (90, 270) for sd in st.get("side_data_list", [])):
        w, h = h, w
    if w / h > 0.7:  # not already vertical
        vf = ("split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:4,eq=brightness=-0.25[bg];"
              "[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=30,format=yuv420p")
    else:
        vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,format=yuv420p"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.2f}", "-i", video, "-t", f"{end - start:.2f}", "-filter_complex", f"[0:v]{vf}[v]",
                    "-map", "[v]", "-map", "0:a:0?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k", str(out)], check=True)


def make(page, rec, state, learned=""):
    """Returns (mp4, caption, hook). Raises NeedsInput when there is nothing left to clip."""
    folder = page.get("drive_folder")
    if not folder:
        raise NeedsInput("Add drive_folder (Google Drive folder link with your source videos) in pages.yaml")
    book = state.setdefault("sources", {}).setdefault(page["id"], {})
    OUT.mkdir(exist_ok=True)
    for src in list_sources(folder):
        entry = book.setdefault(src["id"], {"name": src["name"], "used": [], "done": False})
        if entry["done"]:
            continue
        rec["status"] = "downloading"
        video = fetch(src, OUT / ("source" + Path(src["name"]).suffix))
        rec["status"] = "transcribing"
        segs = [s for s in transcribe(video, src["id"]) if s["words"]]
        choice = pick(page, segs, entry["used"], learned)
        if not choice:
            entry["done"] = True
            continue
        a, b = segs[choice["i"]]["start"], segs[choice["j"]]["end"]
        start, end = max(0, a - 0.15), b + 0.25
        rec.update({"title": choice["title"], "topic": f"{src['name']} {a:.0f}-{b:.0f}s", "seconds": round(end - start, 1), "status": "rendering"})
        cut(video, start, end, COMPOSER / "public" / "clip.mp4")
        words = [{"word": w["word"], "start": round(w["start"] - start, 2), "end": round(w["end"] - start, 2)}
                 for s in segs[choice["i"]:choice["j"] + 1] for w in s["words"]]
        props = {"video": "clip.mp4", "words": words, "title": choice["title"], "accent": page.get("accent", "#3b82f6"),
                 "handle": "@" + page["instagram"] if page.get("instagram") else page["name"], "duration": round(end - start, 2)}
        (COMPOSER / "props.json").write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
        mp4 = OUT / f"{rec['id']}.mp4"
        cmd = ["npx", "remotion", "render", "src/index.ts", "Clip", str(mp4), "--props=props.json", "--crf=20", "--pixel-format=yuv420p", "--log=error"]
        if os.environ.get("REMOTION_BROWSER"):
            cmd.append(f"--browser-executable={os.environ['REMOTION_BROWSER']}")
        subprocess.run(cmd, cwd=COMPOSER, check=True)
        entry["used"].append([a, b])
        caption = choice["caption"] + ("\n\n" + " ".join("#" + t for t in choice["hashtags"]) if choice["hashtags"] else "")
        return mp4, caption, segs[choice["i"]]["text"]
    raise NeedsInput("Every source video is fully clipped: add new videos to the Drive folder")
