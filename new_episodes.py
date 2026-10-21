"""Weekly step A: write this week's scripts and ask you to record them.

For each video it creates episodes/<date>-<topic>/ with:
  script.json   everything the build needs
  RECORD.md     the text to read, file by file
and opens a GitHub issue (GitHub emails it to you) with the same text and upload steps.
"""
import datetime as dt
import json
import os
import subprocess

from common import MOCK, ROOT, cfg, load, save, summary
from plan import pick_topic, write_script


def record_sheet(script, folder):
    lines = [f"# Record: {script['title']}", "",
             "Read each part in one take, at a relaxed pace. Leave a short breath where you see a blank line.",
             "If you stumble, stop and record that file again; small slips are fine.", ""]
    files = [("video", "Full video", script["scenes"])]
    for n, sh in enumerate(script["shorts"], 1):
        files.append((f"short{n}", f"Short {n}: {sh['title']}", sh["scenes"]))
    for name, label, scenes in files:
        words = sum(len(s["narration"].split()) for s in scenes)
        lines += [f"## {label}", f"Save as **{name}.m4a** (or .mp3 / .wav), about {round(words / 150, 1)} min", ""]
        for s in scenes:
            lines += [s["narration"].strip(), ""]
    lines += ["---", "### When you're done",
              f"1. Open the folder `{folder}` in your repository on github.com.",
              "2. Click **Add file > Upload files** and drop in your recordings with the names above.",
              "3. Click **Commit changes**. The video and Shorts build by themselves and appear in "
              "YouTube Studio as private about 15 minutes later.", "",
              "### Facts to double-check while you read",
              *[f"- {f['claim']} ({f['source']})" for f in script.get("facts_to_check", [])]]
    return "\n".join(lines) + "\n"


def open_issue(title, body):
    if MOCK or not os.environ.get("GITHUB_ACTIONS"):
        print(f"(would open issue: {title})")
        return
    try:
        subprocess.run(["gh", "issue", "create", "--title", title, "--body", body[:60000]], check=True)
    except Exception as e:
        print(f"Could not open the issue ({e}); the script is still saved in the episode folder.")


def main():
    config = cfg()
    count = int(os.environ.get("VIDEOS") or config.get("videos_per_week", 2))
    shorts = config.get("shorts_per_video", [1])
    today = dt.date.today().isoformat()
    chosen, made = [], []
    for i in range(count):
        topic = pick_topic(exclude=chosen)
        n_shorts = int(shorts[i] if i < len(shorts) else shorts[-1])
        script = write_script(topic, n_shorts, config)
        tid = script.get("topic_id") or (topic or {}).get("id") or f"auto-{i}"
        chosen.append(tid)
        folder = ROOT / "episodes" / f"{today}-{tid}"
        if MOCK:
            folder = ROOT / "episodes" / f"{today}-mock-{i + 1}"
        folder.mkdir(parents=True, exist_ok=True)
        save(folder / "script.json", script)
        rel = folder.relative_to(ROOT).as_posix()
        sheet = record_sheet(script, rel)
        (folder / "RECORD.md").write_text(sheet, encoding="utf-8")
        open_issue(f"Record: {script['title']}", sheet)
        made.append((script["title"], rel))
        if not MOCK:
            used = load("state/used.json")
            if tid not in used["used"]:
                used["used"].append(tid)
                save(ROOT / "state" / "used.json", used)
    summary("## Scripts ready to record\n" + "\n".join(f"- {t} (`{f}`)" for t, f in made))


if __name__ == "__main__":
    main()
