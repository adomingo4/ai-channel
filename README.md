# Techtenoris: tech trends channel (free trial version)

You read the scripts; everything else is automatic and costs nothing.

## How a week works

| When (Doha time) | What happens | Your time |
| --- | --- | --- |
| **Thursday 18:17** | The week's 2 scripts (1 video + 2 Shorts, 1 video + 1 Short) are researched and written. GitHub emails you a "Record:" message for each. | – |
| **Friday or Saturday** | You read each script into your phone and upload the recordings. | ~20 min |
| **15 minutes after each upload** | Your audio is matched to the scenes, cleaned up and levelled; websites are captured; the video, Shorts and thumbnail are edited and uploaded to YouTube as **private**. | – |
| **During the week** | You watch each one in YouTube Studio, tick the fact checklist, and publish or schedule it. | ~5 min each |

## What it costs: $0
- **Scripts:** Google Gemini API, free tier (with Google Search to check prices and features).
- **Voice:** you.
- **Speech matching:** Whisper, free and open source, runs on GitHub.
- **Footage:** Pixabay stock videos and photos, free for commercial use.
- **Music (optional):** tracks you add from the YouTube Audio Library or Pixabay Music.
- **Running it:** GitHub Actions, free for private repositories up to 2,000 minutes a month (this uses about 70).
- **YouTube** and **affiliate programs:** free.

Note: on Gemini's free tier, Google may use what you send it to improve its products.
That's fine here, because the scripts become public videos anyway.

---

## Setup (about 40 minutes, once)

### 1. Create the YouTube channel
YouTube > profile picture > **Settings > Add or manage your channels > Create a channel**.
Name it **Techtenoris** (already set in `config.json`).

### 2. Get a free Gemini API key
1. Go to **aistudio.google.com** and sign in with your Google account.
2. Click **Get API key > Create API key**. No card is needed.
3. Copy the key.

### 2b. Get a free Pixabay key (for stock footage)
1. Sign up at **pixabay.com** (free).
2. Open **pixabay.com/api/docs/** while logged in. Your key is shown in the **Parameters** table, next to `key`.
3. Copy it. Without it, videos use moving colour backgrounds instead of footage.

### 3. Connect YouTube
Reuse the Google Cloud project and `client_secret.json` from Colourinda.
1. Run `python scripts/get_token.py client_secret.json` in this folder.
2. When Google asks which account or channel, choose the **new channel**, not Colourinda.
3. Copy the three values it prints.

### 4. Put it on GitHub
1. Create a new **private** repository, e.g. `ai-channel`.
2. Upload everything in this folder **except** `client_secret.json`.
   Check that `.github/workflows/` holds `scripts.yml` and `build.yml`; if the folder didn't
   upload, create each file with **Add file > Create new file** and paste the contents.
3. **Settings > Secrets and variables > Actions**, add 5 secrets:
   `GEMINI_API_KEY`, `PIXABAY_API_KEY`, `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`.
4. **Settings > Notifications** (your account settings): make sure **Issues** emails are on,
   so the weekly "Record:" messages reach you.

### 5. Free test (nothing uploaded)
**Actions > Build videos > Run workflow**, type `true` in the test box. It writes a sample
episode, reads it with a robot voice, runs the real speech matching, and edits everything.
When it's green (about 15 minutes), download **finished-videos** at the bottom of the run.

### 6. Start for real
**Actions > Weekly scripts > Run workflow** (or wait for Thursday). Each "Record:" email
tells you exactly what to read and how to name the files.

---

## Background music (optional)
Drop calm instrumental tracks into the `music` folder (see `music/README.txt`). Each video
uses one, quietly under your voice, dipping whenever you speak. Leave it empty for no music.

## Recording tips
- Use your phone's voice recorder in a quiet room with soft furnishings (curtains,
  sofa, carpet). Hold the phone about 20 cm from your mouth. Turn on airplane mode.
- **One file per item:** `video.m4a`, `short1.m4a`, `short2.m4a` (.mp3 and .wav work too).
- Read naturally. Small changes of wording are fine: the matching follows what you
  actually say, and the Shorts captions show your real words.
- Pause for a breath between paragraphs. The cuts between scenes happen in those pauses.
- If you stumble badly, trim it in the recorder app or record that file again.
  A repeated sentence would stay in the video.

## Uploading recordings
1. On github.com, open your repository > `episodes` > the episode's folder.
2. **Add file > Upload files**, drop in **all** the files for that episode at once,
   then **Commit changes**.
3. The build starts by itself. If you upload only some files, it waits for the rest.
   To build without a missing Short, go to **Actions > Build videos > Run workflow**
   and type the episode folder.

## Reviewing
Open the finished run in **Actions** for links to each video in YouTube Studio and the
list of prices and claims to double-check against their sources.

---

## Affiliate programs (payment to a Qatari bank account)
1. Join the programs for the tools you feature: ElevenLabs, Jasper, Synthesia,
   Writesonic, Surfer, Pictory, Murf, Semrush, Notion, monday.com and others.
2. Before relying on a program, open its payout settings and confirm an option works
   from Qatar: Impact.com (international bank wire or PayPal), PartnerStack (PayPal or
   Stripe), or programs that pay into Payoneer.
3. Paste each approved link into `affiliates.json`. Tools without a link get their normal
   website, so you can start before any approvals come through.
4. The affiliate disclosure is added to every description automatically.

## Changing things
| To change | Edit |
| --- | --- |
| Channel name, audience, colours | `config.json` |
| Upcoming topics and their order | `topics.json` (formats: `trends`, `explainer`, `versus`; when it runs out, it suggests topics itself) |
| Videos per week, Shorts per video, length | `config.json` |
| Script day and time | the `cron` line in `.github/workflows/scripts.yml` (UTC; Doha is UTC+3) |

## Upgrading later (paid, fully automatic)
When the channel earns, two switches in `config.json` make it hands-off:
`voice_mode: "elevenlabs"` (your voice clone) and `script_provider: "claude"`.

## If something fails
Open the failed run, click the red step and read the last lines:
- **Missing secret GEMINI_API_KEY**: add the secret (step 4).
- **Gemini 429 / busy**: the free tier is rate-limited. Run **Weekly scripts** again later.
- **No video recording**: the file must be named `video` (any audio extension).
- **invalid_grant**: redo the YouTube sign-in (step 3) and update `YT_REFRESH_TOKEN`.
