"""Step 5: upload the video and Shorts to YouTube as PRIVATE, then leave a review checklist.

Needs YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN.
    python scripts/upload.py --dry-run   # print titles and descriptions only
"""
import argparse
import json
import os
import sys
import time

from common import MOCK, OUT, ROOT, cfg, load, read_out, save, summary


def link_for(tool, affiliates):
    for name, info in affiliates.items():
        if name.lower() == tool.lower():
            return info.get("link") or info.get("site")
    return None


def tool_lines(tools, affiliates):
    lines = []
    for t in tools:
        url = link_for(t, affiliates)
        if url:
            lines.append(f"{t}: {url}")
    return lines


def long_description(script, marks, config, affiliates):
    parts = [script["description_intro"].strip()]
    if marks:
        parts.append("Chapters\n" + "\n".join(f"{m['time']} {m['title']}" for m in marks))
    links = tool_lines(script.get("tools", []), affiliates)
    if links:
        parts.append("Tools in this video\n" + "\n".join(links))
    parts.append(config["affiliate_disclosure"])
    sources = script.get("sources", [])[:6]
    if sources:
        parts.append("Sources\n" + "\n".join(sources))
    if config.get("voice_mode") == "elevenlabs":
        parts.append("Narrated with an AI clone of my own voice.")
    return "\n\n".join(parts)[:4900]


def short_description(short, script, long_id, config, affiliates):
    parts = [f"Full comparison: https://youtu.be/{long_id}" if long_id else script["title"]]
    links = tool_lines(script.get("tools", []), affiliates)
    if links:
        parts.append("\n".join(links))
    parts.append("Some links are affiliate links.")
    return "\n\n".join(parts)


def tags_fit(tags):
    out, total = [], 0
    for t in tags:
        t = t.replace("<", "").replace(">", "").strip()
        if t and total + len(t) + 1 <= 480:
            out.append(t)
            total += len(t) + 1
    return out


def client():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"):
        if not os.environ.get(k):
            sys.exit(f"Missing secret {k}")
    creds = Credentials(None, refresh_token=os.environ["YT_REFRESH_TOKEN"],
                        client_id=os.environ["YT_CLIENT_ID"],
                        client_secret=os.environ["YT_CLIENT_SECRET"],
                        token_uri="https://oauth2.googleapis.com/token",
                        scopes=["https://www.googleapis.com/auth/youtube.upload"])
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload(yt, path, body, thumb=None):
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    def go(b):
        media = MediaFileUpload(str(path), mimetype="video/mp4", chunksize=16 * 1024 * 1024, resumable=True)
        req = yt.videos().insert(part="snippet,status", body=b, media_body=media)
        resp, tries = None, 0
        while resp is None:
            try:
                _, resp = req.next_chunk()
            except HttpError as e:
                if e.resp.status in (500, 502, 503, 504) and tries < 5:
                    tries += 1
                    time.sleep(2 ** tries)
                    continue
                raise
        return resp["id"]

    try:
        vid = go(body)
    except HttpError as e:
        if e.resp.status == 400 and "containsSyntheticMedia" in body["status"]:
            body["status"].pop("containsSyntheticMedia")  # older API: tick the box in Studio instead
            vid = go(body)
        else:
            raise
    if thumb:
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(thumb))).execute()
        except HttpError as e:
            print(f"Thumbnail not set ({e.resp.status}); verify the channel at youtube.com/verify")
    return vid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    config = cfg()
    affiliates = load("affiliates.json")["tools"]
    script = read_out("script.json")
    marks = read_out("chapters.json")
    made_shorts = [s.get("index", i) for i, s in enumerate(read_out("timeline.json")["shorts"])]
    status = {"privacyStatus": config["privacy"], "selfDeclaredMadeForKids": False,
              "containsSyntheticMedia": bool(config.get("ai_disclosure"))}

    long_body = {"snippet": {"title": script["title"][:100],
                             "description": long_description(script, marks, config, affiliates),
                             "tags": tags_fit(script.get("tags", [])),
                             "categoryId": config["category_id"],
                             "defaultLanguage": config["default_language"],
                             "defaultAudioLanguage": config["default_language"]},
                 "status": dict(status)}

    if args.dry_run or MOCK:
        print(json.dumps(long_body, indent=2, ensure_ascii=False))
        for n in made_shorts:
            sh = script["shorts"][n]
            print(f"\nShort {n + 1}: {sh['title']}\n{short_description(sh, script, 'VIDEO_ID', config, affiliates)}")
        print("\nDry run: nothing uploaded.")
        save(OUT / "uploaded.json", {"mock": True, "video": "MOCK", "shorts": ["MOCK"] * len(made_shorts)})
        return

    yt = client()
    long_id = upload(yt, OUT / "long.mp4", long_body, OUT / "thumbnail.png")
    results = [("Video", script["title"], long_id)]
    for n in made_shorts:
        sh = script["shorts"][n]
        title = sh["title"][:90]
        if "#shorts" not in title.lower():
            title = f"{title} #shorts"
        body = {"snippet": {"title": title[:100],
                            "description": short_description(sh, script, long_id, config, affiliates),
                            "tags": tags_fit(script.get("tags", [])[:8]),
                            "categoryId": config["category_id"],
                            "defaultLanguage": config["default_language"],
                            "defaultAudioLanguage": config["default_language"]},
                "status": dict(status)}
        results.append((f"Short {n + 1}", title, upload(yt, OUT / f"short_{n}.mp4", body)))

    save(OUT / "uploaded.json", {"video": long_id, "shorts": [r[2] for r in results[1:]],
                                 "titles": [r[1] for r in results]})

    rows = "\n".join(f"| {k} | {t} | [watch](https://youtu.be/{v}) · [edit in Studio](https://studio.youtube.com/video/{v}/edit) |"
                     for k, t, v in results)
    facts = "\n".join(f"- [ ] {f['claim']} ([source]({f['source']}))" for f in script.get("facts_to_check", []))
    summary(f"""## Ready for review (all uploaded as {config['privacy']})

| | Title | Links |
|---|---|---|
{rows}

### Check before publishing
{facts or '- [ ] Watch the video once'}
- [ ] Voice sounds right and nothing is mispronounced
- [ ] Affiliate links in the description work
""")


if __name__ == "__main__":
    main()
