"""Shared paths, config and the state file the dashboard reads."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = Path(os.environ.get("STATE_FILE") or ROOT / "docs" / "data" / "state.json")  # env overrides are for the tests
OUT = ROOT / "out"
COMPOSER = ROOT / "composer"


def load_config():
    cfg = yaml.safe_load(Path(os.environ.get("PAGES_FILE") or ROOT / "pages.yaml").read_text(encoding="utf-8"))
    cfg["tz"] = ZoneInfo(cfg.get("timezone", "Asia/Kolkata"))
    return cfg


def now_utc():
    return datetime.now(timezone.utc)


def iso(dt=None):
    return (dt or now_utc()).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"pages": {}, "reels": [], "updated": None, "stats_at": None}


def save_state(state):
    state["updated"] = iso()
    old = iso(now_utc() - timedelta(days=2))
    state["reels"] = [r for r in state["reels"] if not (r["status"] == "made" and r["created"] < old)][-400:]  # drop old test reels
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")


def env(name, default=""):
    return (os.environ.get(name) or default).strip()
