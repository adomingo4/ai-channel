"""Step 4: put narration and visuals together.

Makes out/long.mp4 (1920x1080) and out/short_<n>.mp4 (1080x1920, with large burned-in
captions), levels the audio for YouTube, and works out chapter timestamps.
"""
import json
import re

from common import OUT, ROOT, cfg, read_out, run, save

FONT = "Inter"


XF = 0.4   # length of the transition between scenes (seconds)
TRANSITIONS = ["smoothleft", "fade", "smoothup", "fade", "slideleft", "fade"]


def pick_music(seed):
    """Optional: any .mp3/.m4a/.wav you put in the music/ folder (e.g. from the YouTube Audio Library)."""
    folder = ROOT / "music"
    tracks = sorted(p for p in folder.glob("*") if p.suffix.lower() in (".mp3", ".m4a", ".wav", ".ogg")) if folder.exists() else []
    return tracks[seed % len(tracks)] if tracks else None


def edit(scenes, out_path, kind, config, captions=None, seed=0):
    """Join scene clips with smooth transitions, lay the narration on top, add music and the progress bar."""
    n = len(scenes)
    durs = [sc["seconds"] + sc["pad"] for sc in scenes]
    total = sum(durs)
    inputs, fc = [], []
    for sc in scenes:
        inputs += ["-i", sc["clip"]]
    for sc in scenes:
        inputs += ["-i", sc["audio"]]
    # video: each clip runs XF longer than its scene, and blends into the next one
    last, offset = "0:v", 0.0
    for k in range(1, n):
        offset += durs[k - 1]
        fc.append(f"[{last}][{k}:v]xfade=transition={TRANSITIONS[(k + seed) % len(TRANSITIONS)]}:"
                  f"duration={XF}:offset={offset:.3f}[x{k}]")
        last = f"x{k}"
    post = ["format=yuv420p"]
    if kind == "long":
        accent = config["brand"]["accent"].lstrip("#")
        post.insert(0, f"drawbox=x=0:y=ih-6:w='iw*t/{total:.3f}':h=6:color=0x{accent}@0.9:t=fill")
    if captions:
        post.insert(0, f"ass={captions}")
    fc.append(f"[{last}]{','.join(post)}[v]")
    # audio: every scene's narration padded to its scene length, back to back
    for i in range(n):
        fc.append(f"[{n + i}:a]aresample=48000,aformat=channel_layouts=stereo,apad=whole_dur={durs[i]:.3f}[a{i}]")
    fc.append("".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[voice]")
    music = pick_music(seed)
    if music:
        inputs += ["-stream_loop", "-1", "-i", str(music)]
        fc.append(f"[{2 * n}:a]aresample=48000,aformat=channel_layouts=stereo,volume=0.12,"
                  f"afade=t=out:st={max(0, total - 2.5):.3f}:d=2.5[mus]")
        fc.append("[voice]asplit=2[v1][v2]")
        fc.append("[mus][v2]sidechaincompress=threshold=0.02:ratio=6:attack=15:release=450[duck]")
        fc.append("[v1][duck]amix=inputs=2:duration=first:normalize=0[mix]")
        fc.append("[mix]loudnorm=I=-14:TP=-1.5:LRA=11[a]")
        print(f"  music: {music.name}")
    else:
        fc.append("[voice]loudnorm=I=-14:TP=-1.5:LRA=11[a]")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs, "-filter_complex", ";".join(fc),
         "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", "30",
         "-ar", "48000", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out_path)])


def ts(seconds):
    s = int(seconds)
    return f"{s // 60}:{s % 60:02d}" if s < 3600 else f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def chapters(scenes):
    """YouTube chapters: start at 0:00, at least 3, each at least 10 seconds long."""
    marks, t = [], 0.0
    for sc in scenes:
        name = sc.get("chapter") or "Part"
        if not marks or marks[-1]["title"] != name:
            marks.append({"start": t, "title": name})
        t += sc["seconds"] + sc["pad"]
    end = t
    merged = []
    for i, m in enumerate(marks):
        nxt = marks[i + 1]["start"] if i + 1 < len(marks) else end
        if merged and nxt - m["start"] < 10:
            continue  # too short: fold into the previous chapter
        merged.append(m)
    merged[0]["start"] = 0.0
    if len(merged) < 3:
        return []
    return [{"time": ts(m["start"]), "title": m["title"]} for m in merged]


def ass_time(t):
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def caption_file(scenes, path, brand):
    """Big, centred captions, three or four words at a time, timed to each scene's audio."""
    accent = brand["accent"].lstrip("#")
    bgr = accent[4:6] + accent[2:4] + accent[0:2]
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{FONT},76,&H00FFFFFF,&H00FFFFFF,&H00141414,&H96000000,-1,0,0,0,100,100,0,0,1,6,0,2,80,80,250,1
Style: Key,{FONT},76,&H00{bgr},&H00FFFFFF,&H00141414,&H96000000,-1,0,0,0,100,100,0,0,1,6,0,2,80,80,250,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events, t = [], 0.0
    for sc in scenes:
        if sc.get("words"):
            # your real words with their real timings (from the recording)
            chunk = []
            for i, w in enumerate(sc["words"]):
                chunk.append(w)
                last = i == len(sc["words"]) - 1
                if len(chunk) >= 4 or (len(chunk) >= 2 and w["w"][-1:] in ".,!?:;") or last:
                    text = " ".join(x["w"] for x in chunk).replace("{", "(").replace("}", ")")
                    style = "Key" if any(ch.isdigit() or ch == "$" for ch in text) else "Cap"
                    end = sc["words"][i + 1]["start"] if not last else min(chunk[-1]["end"] + 0.3, sc["seconds"])
                    events.append(f"Dialogue: 0,{ass_time(t + chunk[0]['start'])},{ass_time(t + max(end, chunk[0]['start'] + 0.3))},"
                                  f"{style},,0,0,0,,{text}")
                    chunk = []
            t += sc["seconds"] + sc["pad"]
            continue
        words = re.sub(r"\s+", " ", sc["narration"]).strip().split(" ")
        chunks, cur = [], []
        for w in words:
            cur.append(w)
            if len(cur) >= 4 or (len(cur) >= 2 and w[-1:] in ".,!?:;"):
                chunks.append(cur)
                cur = []
        if cur:
            chunks.append(cur)
        total_chars = sum(len(" ".join(c)) + 2 for c in chunks)
        start = t
        for c in chunks:
            d = sc["seconds"] * (len(" ".join(c)) + 2) / total_chars
            text = " ".join(c).replace("{", "(").replace("}", ")")
            style = "Key" if any(ch.isdigit() or ch == "$" for ch in text) else "Cap"
            events.append(f"Dialogue: 0,{ass_time(start)},{ass_time(start + d)},{style},,0,0,0,,{text}")
            start += d
        t += sc["seconds"] + sc["pad"]
    path.write_text(head + "\n".join(events) + "\n", encoding="utf-8")


def main():
    config = cfg()
    timeline = read_out("timeline.json")
    seed = sum(map(ord, read_out("script.json").get("title", "")))
    edit(timeline["long"], OUT / "long.mp4", "long", config, seed=seed)
    marks = chapters(timeline["long"])
    for short in timeline["shorts"]:
        n = short.get("index", timeline["shorts"].index(short))
        ass = OUT / f"short_{n}.ass"
        caption_file(short["scenes"], ass, config["brand"])
        edit(short["scenes"], OUT / f"short_{n}.mp4", "short", config, captions=ass, seed=seed + n + 1)
    save(OUT / "chapters.json", marks)
    print("Chapters:", json.dumps(marks))


if __name__ == "__main__":
    main()
