# Reel Autopilot

Makes and posts Instagram reels for several pages by itself, on GitHub's servers. No computer needs to be on.

Every 30 minutes GitHub wakes it up. If a page has a reel due, it:

1. **Researches** what is trending for that page (Google News and Google Trends feeds, plus the page's evergreen list)
2. **Writes** a 35–50 second script and picks a scene for each sentence (Gemini, with search to check facts)
3. **Speaks** it and records when each word is said (Edge neural voices, free)
4. **Draws** the reel, 1080x1920, captions following every word (Word Reel engine on Remotion)
5. **Posts** it through Instagram's official API
6. **Tracks** views and followers, shown on the dashboard

## One-time setup

### 1. Two secrets
Repo → Settings → Secrets and variables → Actions → New repository secret.

| Name | What it is | Where to get it |
|---|---|---|
| `GEMINI_API_KEY` | Writes the scripts (free tier) | https://aistudio.google.com/apikey |
| `META_TOKEN` | Lets it post to your Instagram pages | Steps below |

### 2. The Meta token
Each Instagram page must be a **Business or Creator** account and be **connected to a Facebook Page**.

1. Go to https://developers.facebook.com → My Apps → Create app → type **Business**.
2. In the app, add the **Instagram** product (Instagram Graph API).
3. Best option, never expires: https://business.facebook.com/settings → Users → **System users** → Add (Admin) →
   assign your Facebook Pages and the app to it → **Generate token** with these permissions:
   `instagram_basic`, `instagram_content_publish`, `instagram_manage_insights`, `pages_show_list`, `pages_read_engagement`, `business_management`.
4. Quicker option, expires after 60 days: Tools → Graph API Explorer → pick your app → add the same permissions →
   Generate Access Token → then extend it in Tools → Access Token Debugger → "Extend Access Token".
5. Save the token as the `META_TOKEN` secret. One token covers every page it has access to.

### 3. Dashboard
Repo → Settings → Pages → Source: **Deploy from a branch** → Branch `main`, folder `/docs`.
The dashboard is then at `https://<your-username>.github.io/<repo-name>/`.

### 4. First test
Actions → Reel Autopilot → Run workflow → mode **test**, pick a page.
It makes one reel without posting. Download it from the run's "Artifacts" and watch it.
When you are happy, do nothing more: the schedule posts by itself.

## Changing things

Everything is in `pages.yaml`: pages, posting times (India time), niche, voice, colour, evergreen topics.
To add a page, copy a block, fill in the Instagram handle, set `enabled: true`.

Voices: any Edge voice name, e.g. `en-IN-PrabhatNeural`, `en-IN-NeerjaNeural`, `en-US-GuyNeural`, `hi-IN-MadhurNeural`, `hi-IN-SwaraNeural`.

## Limits to know

- Instagram allows about 50 API posts per account per day; this is far below that.
- Facts are checked by the script model with search, but nobody reviews a reel before it posts.
  Use **test** mode for a new page until you trust its output.
- If the Edge voice service is unreachable it falls back to a plainer Google voice for that reel.
- Scheduled runs can start 5–20 minutes late; that is normal for GitHub.
