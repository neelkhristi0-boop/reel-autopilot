"""The 'spider': collects what is trending for a page from free public feeds."""
import re
import urllib.parse

import feedparser

LANG = {"IN": ("en-IN", "IN:en"), "US": ("en-US", "US:en")}


def _clean(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


def gather(page, limit=30):
    """Returns a list of {title, summary, source, link} items, newest first."""
    region = page.get("news_region", "IN")
    hl, ceid = LANG.get(region, LANG["IN"])
    urls = []
    for q in page.get("news_queries") or []:
        urls.append(
            "https://news.google.com/rss/search?q="
            + urllib.parse.quote(q + " when:2d")
            + f"&hl={hl}&gl={region}&ceid={ceid}"
        )
    if page.get("use_trends"):
        urls.append(f"https://trends.google.com/trending/rss?geo={region}")
    items, seen = [], set()
    for url in urls:
        try:
            feed = feedparser.parse(url)
        except Exception as e:  # a dead feed must not stop the run
            print(f"  feed failed: {url} ({e})")
            continue
        for e in feed.entries[:15]:
            title = _clean(e.get("title"))
            key = title.lower()[:60]
            if not title or key in seen:
                continue
            seen.add(key)
            extra = " | ".join(_clean(e.get(k)) for k in ("ht_news_item_title", "summary") if e.get(k))
            items.append({
                "title": title,
                "summary": extra[:300],
                "source": _clean(getattr(e.get("source"), "title", "") if e.get("source") else ""),
                "link": e.get("link", ""),
            })
    return items[:limit]
