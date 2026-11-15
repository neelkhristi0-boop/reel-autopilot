"""End-to-end test: runs the real pipeline (real voice, real render) against stand-in services.

    python tests/test_e2e.py        needs ffmpeg, node and `npm ci` in composer/

Set VOICE_ENGINE=piper where the Edge voice service is blocked."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
tmp = Path(tempfile.mkdtemp())
os.environ.update({"STATE_FILE": str(tmp / "state.json"), "PAGES_FILE": str(tmp / "pages.yaml"), "TRANSCRIPT_DIR": str(tmp / "tr"),
                   "GEMINI_API_KEY": "GEMINI_KEY", "META_TOKEN": "USER_TOKEN", "POLL_SECONDS": "0.1", "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"})
(tmp / "src").mkdir()
from datetime import datetime, timedelta  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

NOW = (datetime.now(ZoneInfo("Asia/Kolkata")) - timedelta(minutes=2)).strftime("%H:%M")  # a slot that is due right now
(tmp / "pages.yaml").write_text(f"""
timezone: Asia/Kolkata
pages:
  - {{id: explain, name: Test Explainer, instagram: test_page, enabled: true, language: English, voice: en-IN-PrabhatNeural,
     accent: "#f59e0b", times: ["{NOW}"], niche: business stories, news_queries: [startup], news_region: IN, target_views: 100000}}
  - {{id: clip, name: Test Clips, instagram: test_page, enabled: true, mode: clips, drive_folder: "{tmp / 'src'}", clip_seconds: [15, 40],
     accent: "#22c55e", times: ["{NOW}"], niche: machining talk}}
  - {{id: unlinked, name: Not Linked, instagram: someone_else, enabled: true, language: English, times: ["{NOW}"], niche: x, news_queries: []}}
""")

from tests import fake_services  # noqa: E402

srv, base = fake_services.start()
os.environ.update({"GRAPH_BASE": base, "GEMINI_BASE": base, "NEWS_BASE": base})

from autopilot import instagram, research, run, script, voice  # noqa: E402
from autopilot.common import OUT, load_config, load_state, save_state  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)


def probe(path):
    j = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], capture_output=True, text=True).stdout)
    v = next(s for s in j["streams"] if s["codec_type"] == "video")
    a = [s for s in j["streams"] if s["codec_type"] == "audio"]
    loud = subprocess.run(["ffmpeg", "-v", "info", "-i", str(path), "-af", "volumedetect", "-vn", "-f", "null", "-"], capture_output=True, text=True).stderr
    mean = float(loud.split("mean_volume:")[1].split("dB")[0]) if "mean_volume:" in loud else -99
    return v["width"], v["height"], float(j["format"]["duration"]), bool(a), mean


cfg, state = load_config(), load_state()
pages = {p["id"]: p for p in cfg["pages"]}

# 1 research
items = research.gather(pages["explain"])
check("research reads the news feed", len(items) == 2 and items[0]["source"] == "Example Times", f"{len(items)} items")

# 2 scheduler
slots = run.due_slots(cfg, state)
check("scheduler finds a due slot for every enabled page", {p["id"] for p, _ in slots} == {"explain", "clip", "unlinked"})

# 3 explainer reel, start to finish
slot = next(s for p, s in slots if p["id"] == "explain")
run.make_one(pages["explain"], slot, state, dry_run=False)
r = state["reels"][-1]
check("explainer reel is posted", r["status"] == "posted", r.get("error") or r.get("permalink", ""))
mp4 = OUT / f"{r['id']}.mp4"
w, h, d, has_audio, mean = probe(mp4)
check("video is 1080x1920", (w, h) == (1080, 1920), f"{w}x{h}")
check("length is 25-60 s", 25 <= d <= 60, f"{d:.1f}s")
check("video has an audible voice", has_audio and mean > -40, f"mean volume {mean} dB, engine {r.get('voice')}")
up = fake_services.LOG["uploads"][-1]
check("upload sent the whole mp4 with the right headers", up["ok"] and up["mp4"] and up["bytes"] == mp4.stat().st_size, f"{up['bytes']} bytes")
check("caption carries hashtags", "#cnc" in fake_services.LOG["captions"][-1])
check("script prompt includes the trending items", "Example Times" in fake_services.LOG["prompts"][0])
check("same slot is not made twice", slot not in [s for _, s in run.due_slots(cfg, state)])
words = json.loads((ROOT / "composer" / "props.json").read_text())["words"]
check("word timings are in order and inside the video",
      all(a["start"] <= b["start"] for a, b in zip(words, words[1:])) and words[-1]["end"] <= d + 0.1, f"{len(words)} words")

# 4 clipping reel from a local 'Drive' folder: a landscape test video with real speech
text = [b["say"] for b in script.SAMPLE["beats"]] * 2  # about a minute of talk
parts, segs, t = [], [], 0.0
for i, line in enumerate(text):
    wav = tmp / f"s{i}.wav"
    voice._speak(line, "en-IN-PrabhatNeural", wav)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(wav), "-ar", "44100", "-ac", "1", str(tmp / f"n{i}.wav")], check=True)
    dur = voice._dur(tmp / f"n{i}.wav")
    segs.append({"start": round(t, 2), "end": round(t + dur, 2), "text": line, "words": voice._spread(line, t, t + dur)})
    parts.append(f"file '{tmp / f'n{i}.wav'}'\n")
    t += dur
(tmp / "l.txt").write_text("".join(parts))
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=s=1280x720:r=30:d={t:.2f}", "-f", "concat", "-safe", "0", "-i", str(tmp / "l.txt"),
                "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(tmp / "src" / "talk.mp4")], check=True)
(tmp / "tr").mkdir()
# stands in for Whisper, whose model cannot be downloaded in every test environment
(tmp / "tr" / "talk.mp4.json").write_text(json.dumps(segs))
slot = next(s for p, s in slots if p["id"] == "clip")
run.make_one(pages["clip"], slot, state, dry_run=False)
r = state["reels"][-1]
check("clip reel is posted", r["status"] == "posted", r.get("error") or r.get("topic", ""))
w, h, d, has_audio, mean = probe(OUT / f"{r['id']}.mp4")
check("clip is vertical with sound", (w, h) == (1080, 1920) and has_audio and mean > -40, f"{w}x{h}, {d:.1f}s, {mean} dB")
check("clip length is within the limits", 15 <= d <= 41, f"{d:.1f}s")
used = state["sources"]["clip"]["talk.mp4"]["used"]
check("used part of the source is remembered", len(used) == 1, str(used))
run.make_one(pages["clip"], slot + "b", state, dry_run=True)
used = state["sources"]["clip"]["talk.mp4"]["used"]
check("second clip does not overlap the first", len(used) == 2 and (used[1][0] >= used[0][1] or used[1][1] <= used[0][0]), str(used))

# 5 a page whose Instagram is not linked asks for input instead of crashing
slot = next(s for p, s in slots if p["id"] == "unlinked")
run.make_one(pages["unlinked"], slot, state, dry_run=False)
r = state["reels"][-1]
check("unlinked page is reported as needing input", r["status"] == "needs_input" and "not linked" in r["error"], r["error"][:60])

# 6 stats, learning, dashboard data
run.refresh_stats(cfg, state)
run.plan(cfg, state)
save_state(state)
ps = state["pages"]["explain"]
check("stats read followers and views", ps.get("followers") == 1234 and ps.get("views7", 0) >= 4321, f"{ps.get('followers')} followers, {ps.get('views7')} views")
check("posted reels get their own view counts", all(x.get("views") == 4321 for x in state["reels"] if x["status"] == "posted"))
for i in range(4):
    state["reels"].append({"id": f"h{i}", "slot": f"h{i}", "page": "explain", "status": "posted", "created": "2026-11-10T00:00:00Z",
                           "title": f"Old {i}", "hook": f"Hook {i}", "views": 100 * i, "seconds": 40})
lesson = run.learn(pages["explain"], state)
check("learning ranks winners and losers", lesson.index("4321 views") < lesson.index("LOSERS") < lesson.rindex("- 0 views"), lesson.splitlines()[1])
saved = json.loads(Path(os.environ["STATE_FILE"]).read_text())
check("dashboard file is written", {"pages", "reels", "planned", "needs", "updated"} <= set(saved) and saved["pages"]["explain"]["target"] == 100000)

# 7 a wrong token is reported clearly
instagram._accounts = None
os.environ["META_TOKEN"] = "WRONG"
try:
    instagram.accounts()
    check("bad token is rejected", False)
except instagram.NeedsInput as e:
    check("bad token is rejected with a clear message", "rejected" in str(e))

print(f"\n{sum(checks)}/{len(checks)} checks passed")
print("kept:", sorted(str(p) for p in OUT.glob("*.mp4")))
sys.exit(0 if all(checks) else 1)
