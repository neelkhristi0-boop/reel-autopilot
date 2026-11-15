"""Voice first: speaks each beat, records when every word is said, joins it into one track."""
import asyncio
import json
import os
import subprocess
from pathlib import Path

GAP = 0.14  # breath between beats, seconds


def _dur(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def _spread(text, start, end):
    """No word timings from the voice engine: share the time out by word length."""
    ws = text.split()
    total = sum(len(w) + 2 for w in ws) or 1
    t, out = start, []
    for w in ws:
        d = (end - start) * (len(w) + 2) / total
        out.append({"word": w, "start": round(t, 3), "end": round(t + d, 3)})
        t += d
    return out


async def _edge(text, voice, mp3):
    import edge_tts
    words = []
    com = edge_tts.Communicate(text, voice, boundary="WordBoundary", rate=os.environ.get("VOICE_RATE", "+6%"))
    with open(mp3, "wb") as f:
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                s = chunk["offset"] / 1e7
                words.append({"word": chunk["text"], "start": s, "end": s + chunk["duration"] / 1e7})
    return words


def _speak(text, voice, mp3):
    """Returns word timings relative to this clip (may be empty)."""
    if os.environ.get("AUTOPILOT_FAKE_VOICE"):  # tests only: silence at speaking pace
        secs = max(1.0, len(text.split()) / 2.7)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", str(secs), str(mp3)], check=True)
        return []
    for attempt in range(3):
        try:
            words = asyncio.run(_edge(text, voice, mp3))
            if Path(mp3).stat().st_size > 1000:
                return words
        except Exception as e:
            print(f"  edge voice attempt {attempt + 1} failed: {e}")
    from gtts import gTTS  # fallback voice, no word timings
    lang = "hi" if voice.startswith("hi-") else "en"
    gTTS(text, lang=lang, tld="co.in").save(str(mp3))
    return []


def make(beats, voice, workdir, out_audio):
    """beats: [{say, key, scene}] -> (words, render_beats, duration). Writes out_audio (mp3)."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    words, rbeats, wavs, t = [], [], [], 0.0
    silence = workdir / "gap.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", str(GAP), str(silence)], check=True)
    for i, b in enumerate(beats):
        mp3, wav = workdir / f"b{i}.mp3", workdir / f"b{i}.wav"
        timed = _speak(b["say"], voice, mp3)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mp3), "-ar", "44100", "-ac", "1", str(wav)], check=True)
        d = _dur(wav)
        rbeats.append({"start": len(words), "scene": b["scene"], "key": b.get("key", "")})
        if timed:
            words += [{"word": w["word"], "start": round(t + w["start"], 3), "end": round(t + min(w["end"], d), 3)} for w in timed]
        else:
            words += _spread(b["say"], t + 0.05, t + d - 0.1)
        wavs += [wav, silence]
        t += d + GAP
    lst = workdir / "list.txt"
    lst.write_text("".join(f"file '{w.resolve()}'\n" for w in wavs), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-b:a", "160k", str(out_audio)], check=True)
    (workdir / "words.json").write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
    return words, rbeats, round(t + 0.5, 2)
