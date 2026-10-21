"""Shared helpers: paths, config, small utilities."""
import datetime as dt
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
MOCK = os.environ.get("MOCK", "").lower() in ("1", "true", "yes")


def load(name):
    with open(ROOT / name, encoding="utf-8") as f:
        return json.load(f)


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def read_out(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def cfg():
    return load("config.json")


def shorts_for_today(config):
    override = os.environ.get("SHORTS", "").strip()
    if override:
        return int(override)
    table = config.get("shorts_per_run")
    if isinstance(table, dict):
        day = dt.datetime.utcnow().strftime("%A")
        return int(table.get(day, table.get("default", 1)))
    return int((config.get("shorts_per_video") or [1])[0])


def run(cmd):
    subprocess.run(cmd, check=True)


def media_seconds(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


def summary(markdown):
    """Append to the GitHub run summary (shown on the run's page)."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(markdown + "\n")
    print(markdown)
