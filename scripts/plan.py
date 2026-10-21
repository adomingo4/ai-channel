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

VISUAL_TYPES = {"title", "web", "table", "bullets", "steps", "verdict", "outro"}


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
  "title": "YouTube title, max 70 characters, specific and honest, no clickbait lies",
  "description_intro": "2-3 sentence YouTube description opening",
  "tags": ["8-15 search tags"],
  "tools": ["exact tool names featured, matching the affiliate list where possible"],
  "thumbnail": {"headline": "2-5 punchy words", "tools": ["1-3 tool names shown as labels"]},
  "scenes": [
    {"chapter": "short chapter label", "narration": "spoken text", "visual": VISUAL}
  ],
  "shorts": [
    {"title": "max 70 characters", "scenes": [{"narration": "spoken text", "visual": VISUAL}]}
  ],
  "facts_to_check": [{"claim": "a price, limit or feature claim used in narration", "source": "https://..."}],
  "sources": ["https://... pages you relied on"]
}

VISUAL is ONE of:
  {"type": "title", "heading": "max 8 words", "sub": "max 12 words"}
  {"type": "web", "url": "https://public page on the tool's own site (home, pricing, features, a docs page). No login pages.", "label": "what the page is, max 6 words"}
  {"type": "table", "heading": "max 8 words", "columns": ["", "Tool A", "Tool B"], "rows": [["Row label", "value", "value"]]}
  {"type": "bullets", "heading": "max 8 words", "items": ["max 9 words each, 2-5 items"]}
  {"type": "steps", "heading": "max 8 words", "items": ["numbered steps, max 10 words each, 2-5 items"]}
  {"type": "verdict", "heading": "max 8 words", "items": ["Pick X if ...", "Pick Y if ..."]}
  {"type": "outro", "heading": "max 8 words", "sub": "max 12 words"}"""


def build_prompt(topic, config, n_shorts):
    today = dt.date.today()
    lo, hi = config["long_video_minutes"]
    s_lo, s_hi = config["short_seconds"]
    words = (int(lo * 150), int(hi * 150))
    s_words = (int(s_lo * 2.4), int(s_hi * 2.4))
    if topic:
        topic_text = (f'Topic id: {topic["id"]}\nType: {topic["type"]}\nWorking title: {topic["title"]}\n'
                      f'Tools: {", ".join(topic.get("tools", [])) or "choose the right ones"}')
    else:
        topic_text = ("No topic was given. Use web search to find a timely, high-interest topic for this "
                      "audience: a comparison of two or three popular AI or productivity tools, or practical "
                      "tips for one tool. Prefer tools that run affiliate programs.")
    system = f"""You write scripts for the YouTube channel "{config['channel_name']}" ({config['channel_tagline']}).
The narrator speaks in the first person and is {config['presenter']}. Audience: {config['audience']}.
Today is {today:%d %B %Y}.

Research first. Use web search to confirm current plans, prices, free tiers, limits and notable recent changes, preferring each tool's own website. Never invent a price, number or feature. If you cannot confirm something, leave it out. Mention prices with "as of {today:%B %Y}" once in the video.

Voice and style:
- Spoken, conversational English. Short sentences. Contractions. Easy to read aloud in one take: no tongue-twisters, no long lists of numbers in one sentence.
- Never invent personal experience ("I've used it for two years", "my team switched last month"). Base opinions on the research and say so naturally ("from what I've seen", "based on their plans").
- Write numbers and prices the way they are spoken: "$12 a month", not "$12/mo"; "version 4", not "v4".
- Open with a hook in the first two sentences that says exactly what the viewer gets. Never "in today's video" or "welcome back".
- Be genuinely useful and honest: real pros and cons, who each tool is for, and a clear verdict. Opinions in first person ("I'd pick..."), based on the research.
- No hype words: game-changer, revolutionary, unleash, supercharge, insane, mind-blowing.
- Only mention links once, at the end: "links to everything are in the description".

Long video: 8 to 14 scenes, {words[0]} to {words[1]} words of narration in total, 25 to 90 words per scene. Give scenes a "chapter" label; neighbouring scenes may share one; use at least 4 different chapters, the first one "Intro". At least 40% of scenes must use a "web" visual showing the real tool. Finish with a verdict scene and an outro scene.

Shorts: write exactly {n_shorts}. Each stands alone, {s_words[0]} to {s_words[1]} words, 2 to 4 scenes, the first sentence is the hook, the last sentence points to the full video on the channel. Tables in Shorts: at most 3 columns and 3 rows.

Each scene has exactly one visual that matches what the narration is saying at that moment.

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
    if not 6 <= len(scenes) <= 16:
        problems.append(f"long video has {len(scenes)} scenes, needs 8-14")
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
