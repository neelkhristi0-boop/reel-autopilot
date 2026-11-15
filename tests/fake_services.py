"""Stand-ins for Google News, Gemini and the Instagram Graph API, shaped like the real replies.
They let the whole pipeline run with no keys. They prove our code, not the real services."""
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from autopilot.script import SAMPLE

LOG = {"uploads": [], "published": [], "captions": [], "prompts": [], "polls": 0}
RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>Indian startup raises funds after turnaround - Example Times</title><link>https://example.com/a</link><description>Summary one</description><source url="https://example.com">Example Times</source></item>
<item><title>Founder explains the one decision that saved the company - Example Daily</title><link>https://example.com/b</link><description>Summary two</description><source url="https://example.com">Example Daily</source></item>
</channel></rss>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, code=200, ctype="application/json"):
        body = obj.encode() if isinstance(obj, str) else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        path = u.path
        if path.startswith("/rss/"):
            return self._send(RSS, ctype="application/rss+xml")
        if q.get("access_token", [""])[0] not in ("USER_TOKEN", "PAGE_TOKEN"):
            return self._send({"error": {"message": "Invalid OAuth access token"}}, 400)
        if path.endswith("/me/accounts"):
            return self._send({"data": [
                {"name": "FB Page", "access_token": "PAGE_TOKEN", "instagram_business_account": {"id": "1789", "username": "test_page"}},
                {"name": "No IG page", "access_token": "X"}]})
        if path.endswith("/1789/media"):
            return self._send({"data": [{"id": m, "timestamp": "2026-11-14T04:05:00+0000", "media_product_type": "REELS",
                                         "permalink": f"https://instagram.com/reel/{m}/", "like_count": 12, "comments_count": 3} for m in LOG["published"]]})
        if path.endswith("/1789"):
            return self._send({"followers_count": 1234, "media_count": 9, "username": "test_page"})
        if path.endswith("/insights"):
            if q.get("metric") == ["views"]:
                return self._send({"data": [{"name": "views", "values": [{"value": 4321}]}]})
            return self._send({"error": {"message": "bad metric"}}, 400)
        m = re.search(r"/(CID\d+)$", path)
        if m:
            LOG["polls"] += 1
            return self._send({"status_code": "FINISHED" if LOG["polls"] % 2 == 0 else "IN_PROGRESS", "id": m.group(1)})
        m = re.search(r"/(MEDIA\d+)$", path)
        if m:
            return self._send({"permalink": f"https://instagram.com/reel/{m.group(1)}/", "id": m.group(1)})
        self._send({"error": {"message": f"unknown GET {path}"}}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if ":generateContent" in u.path:
            if self.headers.get("x-goog-api-key") != "GEMINI_KEY":
                return self._send({"error": {"message": "API key not valid"}}, 400)
            prompt = json.loads(raw)["contents"][0]["parts"][0]["text"]
            LOG["prompts"].append(prompt)
            if "single best short clip" in prompt:
                reply = {"start": 6.1, "end": 30.0, "title": "The tolerance trap", "caption": "Did you know this?\nWhat do you think?", "hashtags": ["#cnc", "clips"]}
            else:
                reply = SAMPLE
            text = "Here is the reel:\n```json\n" + json.dumps(reply) + "\n```"  # models often wrap the JSON
            return self._send({"candidates": [{"content": {"parts": [{"text": text}]}}]})
        if u.path.startswith("/upload/"):
            ok = (self.headers.get("Authorization") == "OAuth PAGE_TOKEN" and self.headers.get("offset") == "0"
                  and int(self.headers.get("file_size", -1)) == len(raw))
            LOG["uploads"].append({"bytes": len(raw), "ok": ok, "mp4": raw[4:8] == b"ftyp"})
            return self._send({"success": True} if ok else {"error": "bad upload headers"}, 200 if ok else 400)
        form = parse_qs(raw.decode())
        if form.get("access_token") != ["PAGE_TOKEN"]:
            return self._send({"error": {"message": "Invalid OAuth access token"}}, 400)
        if u.path.endswith("/1789/media"):
            if form.get("media_type") != ["REELS"] or form.get("upload_type") != ["resumable"]:
                return self._send({"error": {"message": "bad container fields"}}, 400)
            LOG["captions"].append(form["caption"][0])
            cid = f"CID{len(LOG['captions'])}"
            return self._send({"id": cid, "uri": f"http://127.0.0.1:{self.server.server_port}/upload/{cid}"})
        if u.path.endswith("/1789/media_publish"):
            mid = "MEDIA" + form["creation_id"][0][3:]
            LOG["published"].append(mid)
            return self._send({"id": mid})
        self._send({"error": {"message": f"unknown POST {u.path}"}}, 404)


def start():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}"
