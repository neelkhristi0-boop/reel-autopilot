"""Finds a real photo for every beat by searching the whole web, then downloads and checks it."""
import io
import re
from urllib.parse import urlparse

import requests
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from .common import env

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
# stock sites stamp a watermark across the picture, which looks worse than no picture
WATERMARKED = ("shutterstock", "alamy", "gettyimages", "istockphoto", "dreamstime", "123rf", "depositphotos", "stock.adobe", "freepik", "vecteezy", "bigstock")


def _ddg(q, n):
    """Whole-web image search (DuckDuckGo, no key)."""
    from ddgs import DDGS
    return [r["image"] for r in DDGS().images(q, max_results=n, size="Large", safesearch="moderate")]


def _commons(q, n):
    r = requests.get(env("COMMONS_BASE", "https://commons.wikimedia.org") + "/w/api.php", headers=UA, timeout=20, params={
        "action": "query", "generator": "search", "gsrsearch": q, "gsrnamespace": 6, "gsrlimit": n,
        "prop": "imageinfo", "iiprop": "url|mime", "iiurlwidth": 1600, "format": "json"})
    pages = (r.json().get("query") or {}).get("pages") or {}
    out = []
    for p in sorted(pages.values(), key=lambda p: p.get("index", 0)):
        ii = (p.get("imageinfo") or [{}])[0]
        if ii.get("mime", "").startswith("image/") and "svg" not in ii.get("mime", ""):
            out.append(ii.get("thumburl") or ii.get("url"))
    return out


def _openverse(q, n):
    r = requests.get("https://api.openverse.org/v1/images/", headers=UA, timeout=20, params={"q": q, "page_size": n})
    return [x["url"] for x in r.json().get("results", [])]


ENGINES = {"web": _ddg, "commons": _commons, "openverse": _openverse}


def search(q, n=10):
    """Image URLs for a query, best first. Engines are tried in order until one returns results."""
    for name in env("IMAGE_ENGINES", "web,commons,openverse").split(","):
        try:
            urls = [u for u in ENGINES[name.strip()](q, n) if u and not any(w in urlparse(u).netloc for w in WATERMARKED)]
            if urls:
                return urls
        except Exception as e:
            print(f"  image search '{name}' failed for '{q}': {str(e)[:120]}")
    return []


def download(url, dest):
    """Saves the image as a JPEG if it is a real, big-enough picture. Returns True on success."""
    try:
        r = requests.get(url, headers=UA, timeout=15, stream=True)
        if r.status_code != 200:
            return False
        data = r.raw.read(12_000_000, decode_content=True)
        im = Image.open(io.BytesIO(data))
        im.load()
        if im.width < 600 or im.height < 400 or im.width / im.height > 3.2 or im.height / im.width > 3.2:
            return False
        im = im.convert("RGB")
        # sharp picture for the photo window, and a pre-blurred dark copy for the background (blurring in the renderer is very slow)
        ImageOps.fit(im, (1080, 920), Image.LANCZOS, centering=(0.5, 0.35)).save(dest, "JPEG", quality=88)
        bg = ImageOps.fit(im, (270, 480), Image.BILINEAR).filter(ImageFilter.GaussianBlur(9))
        ImageEnhance.Brightness(bg).enhance(0.4).save(str(dest).replace(".jpg", "_bg.jpg"), "JPEG", quality=80)
        return True
    except Exception:
        return False


def for_beats(beats, public_dir, prefix="img"):
    """Gives each beat an 'image' file name (inside composer/public) or None. Never raises: a reel without photos still renders."""
    for old in public_dir.glob(f"{prefix}_*.jpg"):
        old.unlink()
    seen, found = set(), 0
    for i, b in enumerate(beats):
        q = re.sub(r"\s+", " ", b.pop("image", "") or "").strip()
        b["image_file"] = None
        if not q:
            continue
        for url in search(q):
            if url in seen:
                continue
            seen.add(url)
            if download(url, public_dir / f"{prefix}_{i}.jpg"):
                b["image_file"] = f"{prefix}_{i}.jpg"
                b["image_url"] = url
                found += 1
                break
    print(f"  photos found for {found} of {len(beats)} beats")
    return found
