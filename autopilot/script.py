"""Writes the reel: picks a topic, writes the voice-over beat by beat, and chooses a scene for each beat."""
import json
import re

import requests

from .common import env

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

PROMPT = """You write short faceless explainer reels for the Instagram page "{name}".

PAGE NICHE: {niche}
LANGUAGE OF THE VOICE-OVER: {language}

TRENDING ITEMS FOUND TODAY (may be empty or irrelevant; ignore any that do not fit the niche):
{items}

EVERGREEN TOPIC IDEAS (use one of these if nothing trending fits):
{evergreen}

ALREADY POSTED (never repeat these topics):
{history}

Pick ONE topic and write one reel. Rules:
- 8 to 11 beats. A beat is one short spoken sentence (6 to 16 words). Total 85 to 130 words (35 to 50 seconds).
- Beat 1 is the hook: a contrast or a question a stranger would stop for. No greeting, no "in this video".
- One idea per beat. Plain words. The last beat is the payoff, not "follow for more".
- Every fact, number, name and date must be true and checkable. Use search to verify. If you are not sure of a number, leave it out.
- No medical, legal or investment advice. No insults, no rumours about real people, nothing hateful or political point-scoring.
- Each beat gets ONE scene shown while it is spoken. Scene text is SHORT on-screen text (not the sentence repeated), in the same language as the voice-over. Vary the scene types; use "number" or "compare" whenever the beat has a number.

Scene types (use exactly these shapes):
{{"type":"title","kicker":"2-3 WORDS","text":"max 5 words"}}
{{"type":"number","value":22,"prefix":"$","suffix":"B","label":"max 7 words"}}       value is a plain number
{{"type":"compare","a":{{"label":"max 3 words","value":10}},"b":{{"label":"max 3 words","value":45}},"unit":"%"}}
{{"type":"list","heading":"2-3 words","items":["max 4 words","max 4 words","max 4 words"]}}   2 to 4 items
{{"type":"statement","text":"max 10 words","highlight":"one or two words from text"}}
{{"type":"timeline","points":[{{"label":"1994","text":"max 5 words"}},{{"label":"2016","text":"max 5 words"}}]}}   2 to 4 points

Reply with ONLY a JSON object, no other text:
{{
 "topic": "the topic in under 10 words",
 "title": "cover title, max 6 words",
 "beats": [{{"say": "spoken sentence", "key": "the one most important word in that sentence, exactly as written", "scene": {{...}}}}],
 "caption": "Instagram caption, 2 to 3 short lines, ends with a question to drive comments",
 "hashtags": ["8 to 12 relevant hashtags without #"],
 "sources": ["URL or publication name for the main facts"]
}}"""


def _call(prompt, search=True):
    model = env("GEMINI_MODEL", "gemini-flash-latest")
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.9}}
    if search:
        body["tools"] = [{"google_search": {}}]
    r = requests.post(API.format(model=model), headers={"x-goog-api-key": env("GEMINI_API_KEY")}, json=body, timeout=180)
    if r.status_code != 200:
        raise RuntimeError(f"Gemini {r.status_code}: {r.text[:300]}")
    cand = r.json()["candidates"][0]
    return "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))


def _json(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON in model reply")
    return json.loads(m.group(0))


def _num(v, default=0.0):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return default


def _s(v, n):
    return str(v or "").strip()[:n]


def clean_scene(scene, say):
    """Force every scene into a shape the renderer accepts; fall back to a statement."""
    fallback = {"type": "statement", "text": _s(say, 90)}
    if not isinstance(scene, dict):
        return fallback
    t = scene.get("type")
    try:
        if t == "title":
            return {"type": t, "kicker": _s(scene.get("kicker"), 28), "text": _s(scene["text"], 48)}
        if t == "number":
            return {"type": t, "value": _num(scene["value"]), "prefix": _s(scene.get("prefix"), 3),
                    "suffix": _s(scene.get("suffix"), 6), "label": _s(scene.get("label"), 60)}
        if t == "compare":
            a, b = scene["a"], scene["b"]
            return {"type": t, "unit": _s(scene.get("unit"), 4),
                    "a": {"label": _s(a["label"], 30), "value": _num(a["value"])},
                    "b": {"label": _s(b["label"], 30), "value": _num(b["value"])}}
        if t == "list":
            items = [_s(i, 50) for i in scene["items"] if str(i).strip()][:4]
            if len(items) >= 2:
                return {"type": t, "heading": _s(scene.get("heading"), 28), "items": items}
        if t == "statement":
            return {"type": t, "text": _s(scene["text"], 110), "highlight": _s(scene.get("highlight"), 30)}
        if t == "timeline":
            pts = [{"label": _s(p["label"], 10), "text": _s(p["text"], 60)} for p in scene["points"]][:4]
            if len(pts) >= 2:
                return {"type": t, "points": pts}
    except (KeyError, TypeError):
        pass
    return fallback


def validate(d):
    beats = []
    for b in d.get("beats", []):
        say = _s(b.get("say"), 240)
        if say:
            beats.append({"say": say, "key": _s(b.get("key"), 30), "scene": clean_scene(b.get("scene"), say)})
    words = sum(len(b["say"].split()) for b in beats)
    if not (5 <= len(beats) <= 14) or not (50 <= words <= 170):
        raise ValueError(f"script out of range: {len(beats)} beats, {words} words")
    tags = [re.sub(r"[^\w]", "", str(h)) for h in d.get("hashtags", [])]
    return {
        "topic": _s(d.get("topic"), 120) or _s(d.get("title"), 120),
        "title": _s(d.get("title"), 80),
        "beats": beats,
        "caption": _s(d.get("caption"), 1200),
        "hashtags": [t for t in tags if t][:15],
        "sources": [_s(s, 200) for s in d.get("sources", [])][:6],
    }


def write(page, items, history):
    prompt = PROMPT.format(
        name=page["name"], niche=" ".join(page["niche"].split()), language=page.get("language", "English"),
        items="\n".join(f"- {i['title']} ({i['source']}) {i['summary']}" for i in items) or "(none)",
        evergreen="\n".join(f"- {t}" for t in page.get("evergreen") or []) or "(none)",
        history="\n".join(f"- {h}" for h in history[-60:]) or "(nothing yet)",
    )
    last = None
    for attempt, search in enumerate([True, True, False]):
        try:
            return validate(_json(_call(prompt, search=search)))
        except Exception as e:
            last = e
            print(f"  script attempt {attempt + 1} failed: {e}")
    raise RuntimeError(f"could not write a script: {last}")
