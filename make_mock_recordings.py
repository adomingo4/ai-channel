"""Test helper: fake your recordings with a robot voice (espeak-ng), so the build can be
tested end to end without you recording anything.
    python tests/make_mock_recordings.py episodes/<folder>
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def say(text, path):
    if shutil.which("espeak-ng"):
        subprocess.run(["espeak-ng", "-v", "en-us", "-s", "165", "-w", str(path), text], check=True)
    else:  # no test voice installed: silence of a similar length
        secs = max(2, len(text.split()) / 2.5)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                        "-i", "anullsrc=r=22050:cl=mono", "-t", str(secs), str(path)], check=True)


def record(scenes, out_path):
    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        for i, s in enumerate(scenes):
            p = Path(tmp) / f"{i}.wav"
            say(s["narration"], p)
            parts.append(p)
        pause = Path(tmp) / "pause.wav"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                        "-i", "anullsrc=r=22050:cl=mono", "-t", "0.6", str(pause)], check=True)
        lst = Path(tmp) / "list.txt"
        lst.write_text("".join(f"file '{p}'\nfile '{pause}'\n" for p in parts))
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
                        "-i", str(lst), "-c:a", "aac", "-b:a", "96k", str(out_path)], check=True)


folder = Path(sys.argv[1])
script = json.loads((folder / "script.json").read_text(encoding="utf-8"))
record(script["scenes"], folder / "video.m4a")
for n, sh in enumerate(script["shorts"], 1):
    record(sh["scenes"], folder / f"short{n}.m4a")
print(f"Fake recordings written to {folder}")
