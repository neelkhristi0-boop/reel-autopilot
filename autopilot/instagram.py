"""Posts reels and reads view counts through Instagram's official Graph API."""
import os
import time
from datetime import datetime, timedelta, timezone

import requests

from .common import env

V = "v21.0"
G = f"https://graph.facebook.com/{V}"
_accounts = None


class NeedsInput(Exception):
    """Something only the owner can fix (missing token, page not linked...)."""


def _get(path, token, **params):
    r = requests.get(f"{G}/{path}", params={**params, "access_token": token}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"Instagram API {r.status_code}: {r.text[:300]}")
    return r.json()


def _post(path, token, **data):
    r = requests.post(f"{G}/{path}", data={**data, "access_token": token}, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"Instagram API {r.status_code}: {r.text[:300]}")
    return r.json()


def accounts():
    """{instagram_username: {id, token}} for every page the Meta token can manage."""
    global _accounts
    if _accounts is not None:
        return _accounts
    token = env("META_TOKEN")
    if not token:
        raise NeedsInput("Add the META_TOKEN secret (Meta access token)")
    out, url, params = {}, f"{G}/me/accounts", {"fields": "name,access_token,instagram_business_account{id,username}", "limit": 100, "access_token": token}
    while url:
        r = requests.get(url, params=params, timeout=60)
        if r.status_code != 200:
            raise NeedsInput(f"META_TOKEN was rejected ({r.status_code}): {r.text[:200]}")
        j = r.json()
        for p in j.get("data", []):
            ig = p.get("instagram_business_account")
            if ig:
                out[ig["username"].lower()] = {"id": ig["id"], "token": p["access_token"]}
        url, params = j.get("paging", {}).get("next"), None
    _accounts = out
    return out


def account(page):
    handle = (page.get("instagram") or "").lstrip("@").lower()
    if not handle:
        raise NeedsInput("Add the Instagram handle in pages.yaml")
    acc = accounts().get(handle)
    if not acc:
        raise NeedsInput(f"@{handle} is not linked: make it a Business/Creator account, connect it to a Facebook Page, and give the token access to that Page")
    return acc


def post_reel(page, mp4, caption):
    acc = account(page)
    ig, token = acc["id"], acc["token"]
    size = os.path.getsize(mp4)
    c = _post(f"{ig}/media", token, media_type="REELS", upload_type="resumable", caption=caption, share_to_feed="true")
    cid = c["id"]
    uri = c.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{V}/{cid}"
    with open(mp4, "rb") as f:
        r = requests.post(uri, data=f, timeout=600, headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)})
    if r.status_code != 200:
        raise RuntimeError(f"upload failed {r.status_code}: {r.text[:300]}")
    for _ in range(60):  # Instagram processes the video; up to 10 minutes
        s = _get(cid, token, fields="status_code,status")
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram rejected the video: {s.get('status')}")
        time.sleep(10)
    else:
        raise RuntimeError("Instagram took too long to process the video")
    media_id = _post(f"{ig}/media_publish", token, creation_id=cid)["id"]
    link = _get(media_id, token, fields="permalink").get("permalink", "")
    return media_id, link


def _views(media_id, token):
    for metric in ("views", "plays"):
        try:
            d = _get(f"{media_id}/insights", token, metric=metric)["data"]
            return int(d[0]["values"][0]["value"])
        except Exception:
            continue
    return None


def page_stats(page):
    """Followers plus views of reels from the last 7 days vs the 7 days before."""
    acc = account(page)
    ig, token = acc["id"], acc["token"]
    info = _get(ig, token, fields="followers_count,media_count,username")
    media = _get(f"{ig}/media", token, limit=60, fields="id,timestamp,media_product_type,permalink,like_count,comments_count").get("data", [])
    now = datetime.now(timezone.utc)
    week, prev, reels, per_media = 0, 0, 0, {}
    for m in media:
        ts = datetime.strptime(m["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
        age = now - ts
        if m.get("media_product_type") != "REELS" or age > timedelta(days=14):
            continue
        v = _views(m["id"], token) or 0
        per_media[m["id"]] = {"views": v, "likes": m.get("like_count", 0), "comments": m.get("comments_count", 0)}
        if age <= timedelta(days=7):
            week += v
            reels += 1
        else:
            prev += v
    return {"followers": info.get("followers_count"), "views7": week, "prev7": prev, "reels7": reels, "media": per_media}
