"""Weekly step B: build every episode whose recordings have arrived.

Looks in episodes/*/ for a script.json with a video recording and no built.json yet,
then runs voice -> visuals -> assemble -> upload for it and saves built.json.
    EPISODE=episodes/2026-10-29-notion-vs-clickup python scripts/build_ready.py   # just one
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from common import OUT, ROOT, cfg, save, summary
from voice import find_recording

STEPS = ["voice.py", "visuals.py", "assemble.py", "upload.py"]


def ready(folder, config):
    if not (folder / "script.json").exists() or (folder / "built.json").exists():
        return False, []
    if config.get("voice_mode", "recorded") != "recorded":
        return True, []
    script = json.loads((folder / "script.json").read_text(encoding="utf-8"))
    needed = ["video"] + [f"short{n + 1}" for n in range(len(script["shorts"]))]
    missing = [n for n in needed if not find_recording(folder, n)]
    # wait until every file is in, unless you start the build by hand for this episode
    forced = bool(os.environ.get("EPISODE", "").strip())
    return ("video" not in missing) and (not missing or forced), missing


def build(folder):
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    shutil.copy(folder / "script.json", OUT / "script.json")
    env = {**os.environ, "EPISODE": str(folder)}
    for step in STEPS:
        print(f"\n=== {folder.name}: {step}")
        subprocess.run([sys.executable, str(ROOT / "scripts" / step)], check=True, env=env)
    result = json.loads((OUT / "uploaded.json").read_text(encoding="utf-8"))
    if not result.get("mock"):
        save(folder / "built.json", result)
    # keep a copy of this episode's videos for the run's downloadable files
    keep = ROOT / "finished" / folder.name
    keep.mkdir(parents=True, exist_ok=True)
    for f in list(OUT.glob("*.mp4")) + [OUT / "thumbnail.png"]:
        if f.exists() and not f.name.endswith("_joined.mp4"):
            shutil.copy(f, keep / f.name)


def main():
    config = cfg()
    only = os.environ.get("EPISODE", "").strip()
    folders = [ROOT / only] if only else sorted((ROOT / "episodes").glob("*/"))
    built, waiting = [], []
    for folder in folders:
        ok, missing = ready(folder, config)
        if ok:
            build(folder)
            built.append(folder.name)
            if missing:
                waiting.append(f"{folder.name}: built without {', '.join(missing)}")
        elif missing:
            waiting.append(f"{folder.name}: waiting for {', '.join(missing)}")
    lines = ["## Build results"]
    lines += [f"- Built {b}" for b in built] or ["- Nothing new to build"]
    lines += [f"- {w}" for w in waiting]
    summary("\n".join(lines))


if __name__ == "__main__":
    main()
