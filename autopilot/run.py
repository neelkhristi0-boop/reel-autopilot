"""Reel Autopilot: research -> script -> voice -> render -> post -> stats, for every page that is due.

  python -m autopilot.run --check        cheap: refresh stats, say whether a reel is due
  python -m autopilot.run                make and post every due reel
  python -m autopilot.run --dry-run      make but do not post
  python -m autopilot.run --page ID --force   make one now for that page
"""
import argparse
import os
import shutil
import traceback
from datetime import datetime, timedelta

from . import clips, instagram, research, script, voice
from .common import COMPOSER, OUT, env, iso, load_config, load_state, now_utc, save_state
from .render import render

LATE = timedelta(hours=5)  # a slot missed by more than this is skipped, not posted late


def due_slots(cfg, state, only=None, force=False):
    now = now_utc().astimezone(cfg["tz"])
    done = {r["slot"] for r in state["reels"]}
    out = []
    for page in cfg["pages"]:
        if only and page["id"] != only:
            continue
        if not page.get("enabled") and not (force and only):
            continue
        if force:
            out.append((page, f"{page['id']}|{now:%Y-%m-%d}|manual-{now:%H%M%S}"))
            continue
        for hhmm in page.get("times", []):
            h, m = map(int, hhmm.split(":"))
            at = now.replace(hour=h, minute=m, second=0, microsecond=0)
            slot = f"{page['id']}|{now:%Y-%m-%d}|{hhmm}"
            if at <= now < at + LATE and slot not in done:
                out.append((page, slot))
                break  # one reel per page per run
    return out


def plan(cfg, state):
    """Upcoming slots for the dashboard's 'Planned' column, and what each page still needs."""
    now = now_utc().astimezone(cfg["tz"])
    done = {r["slot"] for r in state["reels"]}
    upcoming = []
    for page in cfg["pages"]:
        ps = state["pages"].setdefault(page["id"], {})
        ps.update({"name": page["name"], "instagram": page.get("instagram", ""), "enabled": bool(page.get("enabled")),
                   "times": page.get("times", []), "accent": page.get("accent", "#3b82f6"),
                   "mode": page.get("mode", "explainer"), "target": page.get("target_views")})
        needs = []
        if not page.get("instagram"):
            needs.append("Instagram handle in pages.yaml")
        if not page.get("enabled"):
            needs.append("Set enabled: true in pages.yaml")
        if page.get("mode") == "clips" and not page.get("drive_folder"):
            needs.append("Google Drive folder link (drive_folder) in pages.yaml")
        ps["needs"] = needs
        if not page.get("enabled"):
            continue
        for day in (0, 1):
            for hhmm in page.get("times", []):
                h, m = map(int, hhmm.split(":"))
                at = (now + timedelta(days=day)).replace(hour=h, minute=m, second=0, microsecond=0)
                slot = f"{page['id']}|{at:%Y-%m-%d}|{hhmm}"
                if at > now - LATE and slot not in done:
                    upcoming.append({"page": page["id"], "at": iso(at.astimezone(now_utc().tzinfo))})
    state["planned"] = sorted(upcoming, key=lambda x: x["at"])[:12]
    missing = [k for k in ("GEMINI_API_KEY", "META_TOKEN") if not env(k)]
    state["needs"] = [f"Add the {k} secret in the GitHub repo settings" for k in missing]


def refresh_stats(cfg, state):
    for page in cfg["pages"]:
        if not page.get("enabled"):
            continue
        ps = state["pages"].setdefault(page["id"], {})
        try:
            s = instagram.page_stats(page)
            media = s.pop("media")
            ps.update(s)
            ps["error"] = ""
            for r in state["reels"]:
                if r.get("media_id") in media:
                    r.update(media[r["media_id"]])
        except instagram.NeedsInput as e:
            ps.setdefault("needs", []).append(str(e))
        except Exception as e:
            ps["error"] = str(e)[:300]
    state["stats_at"] = iso()


def learn(page, state):
    """The daily lesson: which of this page's reels won and lost, fed back into the next script or clip choice."""
    done = [r for r in state["reels"] if r["page"] == page["id"] and r["status"] == "posted" and r.get("views") is not None]
    if len(done) < 4:
        return ""
    done.sort(key=lambda r: r["views"], reverse=True)
    line = lambda r: f'- {r["views"]} views: "{r.get("hook") or r.get("title")}" ({r.get("seconds", "?")}s)'
    return "WINNERS:\n" + "\n".join(line(r) for r in done[:5]) + "\nLOSERS:\n" + "\n".join(line(r) for r in done[-3:])


def make_one(page, slot, state, dry_run):
    rid = slot.replace("|", "_").replace(":", "")
    rec = {"id": rid, "slot": slot, "page": page["id"], "status": "researching", "created": iso(), "title": "", "error": ""}
    state["reels"].append(rec)
    try:
        if not dry_run:
            instagram.account(page)  # fail fast, before any rendering, if the page cannot be posted to
        learned = learn(page, state)
        if page.get("mode") == "clips":
            print(f"[{page['id']}] clipping")
            mp4, caption, rec["hook"] = clips.make(page, rec, state, learned)
        else:
            print(f"[{page['id']}] researching")
            items = research.gather(page)
            history = [r["topic"] for r in state["reels"] if r["page"] == page["id"] and r.get("topic")]
            rec["status"] = "scripting"
            s = script.write(page, items, history, learned)
            rec.update({"title": s["title"], "topic": s["topic"], "sources": s["sources"], "trending_items": len(items), "hook": s["beats"][0]["say"]})
            print(f"[{page['id']}] topic: {s['topic']} ({len(items)} trending items read)")
            rec["status"] = "voicing"
            words, beats, duration = voice.make(s["beats"], page.get("voice", "en-IN-PrabhatNeural"), OUT / f"{rid}_work", COMPOSER / "public" / "voice.mp3")
            rec.update({"status": "rendering", "seconds": duration, "voice": "+".join(sorted(voice.used))})
            handle = "@" + page["instagram"] if page.get("instagram") else page["name"]
            mp4 = render(rid, words, beats, duration, page.get("accent", "#3b82f6"), handle)
            shutil.rmtree(OUT / f"{rid}_work", ignore_errors=True)
            caption = s["caption"] + "\n\n" + " ".join("#" + h for h in s["hashtags"])
        (OUT / f"{rid}.txt").write_text(caption, encoding="utf-8")
        if dry_run:
            rec["status"] = "made"
            print(f"[{page['id']}] made {mp4} (not posted)")
            return
        rec["status"] = "posting"
        rec["media_id"], rec["permalink"] = instagram.post_reel(page, mp4, caption)
        rec.update({"status": "posted", "posted": iso()})
        print(f"[{page['id']}] posted {rec['permalink']}")
    except instagram.NeedsInput as e:
        rec.update({"status": "needs_input", "error": str(e)})
        print(f"[{page['id']}] needs input: {e}")
    except Exception as e:
        traceback.print_exc()
        rec.update({"status": "failed", "error": f"{rec['status']}: {str(e)[:300]}"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--page")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    cfg, state = load_config(), load_state()
    if a.summary:  # shown on the GitHub run page
        print("| Page | Reel | Status | Voice | Note |\n|---|---|---|---|---|")
        for r in state["reels"][-8:]:
            print(f"| {r['page']} | {r.get('title', '')} | {r['status']} | {r.get('voice', '')} | {r.get('permalink') or r.get('error', '')} |")
        return
    slots = due_slots(cfg, state, a.page, a.force)
    if a.check:
        last = state.get("stats_at")
        stale = not last or now_utc() - datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=now_utc().tzinfo) > timedelta(hours=3)
        plan(cfg, state)
        if stale and env("META_TOKEN"):
            refresh_stats(cfg, state)
        save_state(state)
        print(f"due: {[s for _, s in slots]}")
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                f.write(f"due={'true' if slots else 'false'}\n")
        return
    if not env("GEMINI_API_KEY") and not env("AUTOPILOT_SELFTEST"):
        raise SystemExit("GEMINI_API_KEY is not set: add it as a repository secret")
    for page, slot in slots:
        make_one(page, slot, state, a.dry_run)
        plan(cfg, state)
        save_state(state)
    plan(cfg, state)
    save_state(state)


if __name__ == "__main__":
    main()
