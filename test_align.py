"""Checks that scene cuts land in the right place even when the reader drifts from the script.
Builds a fake 'transcript' from known scene timings, then skips, swaps and adds words."""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import align  # noqa: E402

random.seed(7)
scenes = [
    "If you manage projects and you're stuck choosing between Notion and ClickUp, this gives you a straight answer.",
    "Here's the pricing page. Notion Plus is $12 a month and ClickUp Unlimited is $7 a month as of October.",
    "Let's compare the plans side by side, row by row, so you can follow along.",
    "Three things matter most. Task tracking, linked documents, and reporting.",
    "Setup takes four steps. Create the space, add tasks, invite the team, pick a view.",
    "So which one? Docs first, Notion. Tasks first, ClickUp. Links are in the description.",
]
truth, ends, words, t = [], [], [], 0.0
for s in scenes:
    toks = s.split()
    speak = len(toks) / 2.6
    truth.append(t)
    for i, w in enumerate(toks):
        r = random.random()
        if r < 0.08:
            continue                         # skipped word
        if r < 0.12:
            w = "twelve" if "$" in w else w.upper()[::-1]   # misheard / changed word
        start = t + i * speak / len(toks)
        words.append({"w": w, "start": start, "end": start + 0.3})
        if random.random() < 0.05:
            words.append({"w": "um", "start": start + 0.31, "end": start + 0.38})  # ad-lib
    ends.append(t + speak - speak / len(toks) + 0.3)   # end of the scene's last spoken word
    t += speak + random.uniform(0.4, 1.6)   # natural pause between scenes
duration = t

silences = [(ends[i], truth[i + 1]) for i in range(len(scenes) - 1)]
parts = align.split_points(scenes, words, duration, silences)
bad = 0
for i, ((s, e, ws), true_start) in enumerate(zip(parts, truth)):
    pause = (ends[i - 1], true_start) if i else (0.0, true_start)
    inside = i == 0 or pause[0] - 0.05 <= s <= pause[1] + 0.05
    bad += not inside
    print(f"scene {i}: cut at {s:6.2f}s, pause runs {pause[0]:6.2f}-{pause[1]:6.2f}s  {'ok' if inside else 'MISSED'}  ({len(ws)} words)")
assert bad == 0, f"{bad} cut(s) landed outside the pause"
assert all(parts[i][0] < parts[i + 1][0] for i in range(len(parts) - 1))
print("OK")
