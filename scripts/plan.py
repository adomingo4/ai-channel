"""Step 1: pick the next topic, research it with Claude + web search, write out/script.json.

    python scripts/plan.py              # real run (needs ANTHROPIC_API_KEY)
    MOCK=1 python scripts/plan.py       # uses tests/sample_script.json, no API call
    TOPIC=notion-vs-clickup python scripts/plan.py   # force a topic id
"""
import datetime as dt
import json
import os
import re
import shutil
import sys

from common import MOCK, OUT, ROOT, cfg, load, save, shorts_for_today, summary

VISUAL_TYPES = {"broll", "rank", "stat", "title", "web", "table", "bullets", "steps", "verdict", "outro"}


def pick_topic(exclude=()):
    forced = os.environ.get("TOPIC", "").strip()
    topics = load("topics.json")["topics"]
    if forced and forced not in exclude:
        for t in topics:
            if t["id"] == forced:
                return t
        return {"id": forced, "type": "auto", "title": forced.replace("-", " "), "tools": []}
    used = set(load("state/used.json")["used"]) | set(exclude)
    for t in topics:
        if t["id"] not in used:
            return t
    return None  # backlog empty: Claude proposes one


SCHEMA = """{
  "topic_id": "kebab-case id",
  "title": "YouTube title, max 70 characters, curiosity-driven but honest (no false claims)",
  "description_intro": "2-3 sentence YouTube description opening",
  "tags": ["8-15 search tags"],
  "tools": ["brands or products named in the video, if any (for the description links)"],
  "thumbnail": {"headline": "2-5 punchy words", "tags": ["1-3 short labels"], "broll": "2-4 word stock photo search"},
  "scenes": [
    {"chapter": "short chapter label", "narration": "spoken text", "broll": "2-4 word stock footage search", "visual": VISUAL}
  ],
  "shorts": [
    {"title": "max 70 characters", "scenes": [{"narration": "spoken text", "broll": "2-4 word stock footage search", "visual": VISUAL}]}
  ],
  "facts_to_check": [{"claim": "every statistic, date, price or forecast used in narration", "source": "https://..."}],
  "sources": ["https://... pages you relied on"]
}

"broll" is the search phrase for free stock footage shown behind the scene. Make it concrete and filmable,
e.g. "smart fridge kitchen", "electric car charging", "robot vacuum floor", "city traffic night".
Avoid brand names and abstract words in broll.

VISUAL is ONE of:
  {"type": "broll", "caption": "max 7 punchy words shown big over full-screen footage"}
  {"type": "rank", "number": 3, "heading": "the trend's name, max 7 words", "sub": "max 10 words"}
  {"type": "stat", "value": "short number like 68% or $1.2T or 2029", "label": "what it means, max 12 words", "source": "short source name"}
  {"type": "title", "heading": "max 8 words", "sub": "max 12 words"}
  {"type": "table", "heading": "max 8 words", "columns": ["", "A", "B"], "rows": [["Row label", "value", "value"]]}
  {"type": "bullets", "heading": "max 8 words", "items": ["max 9 words each, 2-4 items"]}
  {"type": "verdict", "heading": "max 8 words", "items": ["max 10 words each, 2-3 items"]}
  {"type": "web", "url": "https://a public product or company page", "label": "max 6 words"}
  {"type": "outro", "heading": "max 8 words", "sub": "max 12 words"}"""


def build_prompt(topic, config, n_shorts):
    today = dt.date.today()
    lo, hi = config["long_video_minutes"]
    s_lo, s_hi = config["short_seconds"]
    words = (int(lo * 150), int(hi * 150))
    s_words = (int(s_lo * 2.4), int(s_hi * 2.4))
    if topic:
        topic_text = f'Topic id: {topic["id"]}\nFormat: {topic["type"]}\nWorking title: {topic["title"]}'
    else:
        topic_text = ("No topic was given. Use web search to find a timely, high-interest consumer technology "
                      "topic: a trends countdown, a 'what is the future of...' explainer, or a comparison of two "
                      "countries, products or approaches.")
    system = f"""You write scripts for the YouTube channel "{config['channel_name']}" ({config['channel_tagline']}).
The narrator speaks in the first person and is {config['presenter']}. Audience: {config['audience']}.
Today is {today:%d %B %Y}.

Research first. Use web search to find what is genuinely new or coming: real products, launches, pilots, company
announcements, market data and expert forecasts. Prefer reputable sources (company sites, major news, research firms).
Never invent a number, product, date or quote. If you cannot confirm something, leave it out. Every statistic in the
narration goes in facts_to_check with its source. Say "as of {today:%B %Y}" when a fact may change soon.

Formats:
- trends: a countdown of 5 to 7 trends. For each: a "rank" scene naming it, then 1-2 scenes explaining what it is,
  a real example product or company, and what it means for the viewer's daily life.
- explainer: where things are today, what's coming in 2-5 years, what's hype vs real, what it means for the viewer.
- versus: the two sides compared fairly on 3-5 points with a "table" scene, then a balanced conclusion.

Voice and style:
- Spoken, conversational English. Short sentences. Contractions. Easy to read aloud in one take.
- Never invent personal experience. Opinions are clearly marked as opinions ("my bet is...").
- Write numbers the way they're spoken: "68 percent", "1.2 trillion dollars", "by 2030".
- Open with a hook in the first two sentences: a surprising fact or a vivid picture of the near future.
  Never "in today's video" or "welcome back".
- Wonder without hype. No: game-changer, revolutionary, unleash, mind-blowing, insane.
- End with a question for the comments and a reason to subscribe.

Long video: 9 to 16 scenes, {words[0]} to {words[1]} words of narration in total, 20 to 80 words per scene.
Give scenes a "chapter" label (use at least 4, the first one "Intro"). Mix visuals for variety: about a third "broll",
plus "rank", "stat" and "table" where they fit. Use "web" at most twice. Never use the same visual type 3 times in a row.

Shorts: write exactly {n_shorts}. Each stands alone, {s_words[0]} to {s_words[1]} words, 2 to 4 scenes. The first
sentence is a strong hook; the last points to the full video on the channel. Prefer "broll" and "stat" visuals.
Tables in Shorts: at most 3 columns and 3 rows.

Each scene has exactly one visual that matches what the narration says at that moment, and its own "broll" search.

Reply with the JSON only, wrapped in <json></json>, following this schema:
{SCHEMA}"""
    user = f"Write the next video.\n{topic_text}"
    return system, user


def parse(text):
    m = re.search(r"<json>(.*)</json>", text, re.S)
    raw = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    return json.loads(raw)


def validate(script, n_shorts, config):
    problems = []
    scenes = script.get("scenes") or []
    if not 7 <= len(scenes) <= 18:
        problems.append(f"long video has {len(scenes)} scenes, needs 9-16")
    words = sum(len(s.get("narration", "").split()) for s in scenes)
    lo, hi = config["long_video_minutes"]
    if not lo * 150 * 0.8 <= words <= hi * 150 * 1.2:
        problems.append(f"long video narration is {words} words, needs {int(lo*150)}-{int(hi*150)}")
    if len({s.get("chapter") for s in scenes}) < 3:
        problems.append("needs at least 3 different chapters (4 preferred)")
    all_scenes = scenes + [sc for sh in script.get("shorts", []) for sc in sh.get("scenes", [])]
    for s in all_scenes:
        v = s.get("visual", {})
        if v.get("type") not in VISUAL_TYPES:
            problems.append(f"unknown visual type {v.get('type')}")
        if not s.get("broll"):
            s["broll"] = v.get("heading") or v.get("caption") or "technology"
        if v.get("type") == "web" and not str(v.get("url", "")).startswith("http"):
            problems.append(f"web visual without a valid url: {v}")
        if not s.get("narration", "").strip():
            problems.append("a scene has no narration")
    if len(script.get("shorts", [])) != n_shorts:
        problems.append(f"needs exactly {n_shorts} shorts")
    if len(script.get("title", "")) > 100:
        problems.append("title longer than 100 characters")
    return problems


def write_script(topic, n_shorts, config):
    """Research and write one video plus its Shorts. Returns the script dict."""
    if MOCK:
        script = json.loads((ROOT / "tests" / "sample_script.json").read_text(encoding="utf-8"))
        script["shorts"] = script["shorts"][:max(n_shorts, 1)]
        print("MOCK: using tests/sample_script.json")
        return script

    import llm

    system, user = build_prompt(topic, config, n_shorts)
    script, problems = None, []
    for attempt in range(3):
        prompt = user if not problems else (
            user + "\n\nYour previous answer had these problems, fix them:\n- " + "\n- ".join(problems))
        try:
            script = parse(llm.call(system, prompt, config))
        except (json.JSONDecodeError, ValueError) as e:
            problems = [f"the JSON could not be read ({e}); reply with valid JSON only inside <json></json>"]
            continue
        problems = validate(script, n_shorts, config)
        if not problems:
            break
        print("Script problems:", problems)
    if problems:
        sys.exit("Script still invalid after retries: " + "; ".join(problems))
    script["topic_id"] = (topic or {}).get("id") or script.get("topic_id") or "auto"
    script["created"] = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    return script


def main():
    """Single run (used by the fully automatic voice-clone mode)."""
    OUT.mkdir(exist_ok=True)
    config = cfg()
    n_shorts = shorts_for_today(config)
    script = write_script(pick_topic(), n_shorts, config)
    save(OUT / "script.json", script)
    summary(f"### Script: {script['title']}\n{len(script['scenes'])} scenes, "
            f"{len(script['shorts'])} Shorts")


if __name__ == "__main__":
    main()
