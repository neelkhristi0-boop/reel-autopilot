"""Draws the reel with the Remotion composer (1080x1920, 30 fps)."""
import json
import os
import subprocess

from .common import COMPOSER, OUT


def render(reel_id, words, beats, duration, accent, handle):
    OUT.mkdir(exist_ok=True)
    props = {"words": words, "beats": beats, "audio": "voice.mp3", "accent": accent, "handle": handle, "duration": duration}
    (COMPOSER / "props.json").write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    mp4 = OUT / f"{reel_id}.mp4"
    cmd = ["npx", "remotion", "render", "src/index.ts", "Reel", str(mp4), "--props=props.json",
           "--crf=20", "--pixel-format=yuv420p", "--audio-bitrate=160k", "--log=error"]
    if os.environ.get("REMOTION_BROWSER"):
        cmd.append(f"--browser-executable={os.environ['REMOTION_BROWSER']}")
    subprocess.run(cmd, cwd=COMPOSER, check=True)
    cover = OUT / f"{reel_id}.jpg"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "1.2", "-i", str(mp4), "-frames:v", "1", str(cover)], check=False)
    return mp4
