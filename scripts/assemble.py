"""Step 4: put narration and visuals together.

Makes out/long.mp4 (1920x1080) and out/short_<n>.mp4 (1080x1920, with large burned-in
captions), levels the audio for YouTube, and works out chapter timestamps.
"""
import json
import re

from common import OUT, cfg, read_out, run, save

FONT = "Inter"


def mux_scene(sc, out_path):
    dur = sc["seconds"] + sc["pad"]
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-i", sc["clip"], "-i", sc["audio"],
         "-filter_complex", "[1:a]aresample=48000,aformat=channel_layouts=stereo,apad[a]",
         "-map", "0:v", "-map", "[a]", "-t", f"{dur:.3f}",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(out_path)])


def concat(parts, out_path, captions=None):
    listfile = out_path.with_suffix(".txt")
    listfile.write_text("".join(f"file '{p.resolve()}'\n" for p in parts))
    joined = out_path.with_name(out_path.stem + "_joined.mp4")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
         "-i", str(listfile), "-c", "copy", str(joined)])
    vcodec = ["-c:v", "copy"]
    vf = []
    if captions:
        vf = ["-vf", f"ass={captions}"]
        vcodec = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(joined), *vf, *vcodec,
         "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000", "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", str(out_path)])
    listfile.unlink()
    joined.unlink()


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
    work = OUT / "av"
    work.mkdir(parents=True, exist_ok=True)

    parts = []
    for i, sc in enumerate(timeline["long"]):
        p = work / f"long_{i:02d}.mp4"
        mux_scene(sc, p)
        parts.append(p)
    concat(parts, OUT / "long.mp4")
    marks = chapters(timeline["long"])

    for short in timeline["shorts"]:
        n = short.get("index", timeline["shorts"].index(short))
        parts = []
        for i, sc in enumerate(short["scenes"]):
            p = work / f"short{n}_{i:02d}.mp4"
            mux_scene(sc, p)
            parts.append(p)
        ass = OUT / f"short_{n}.ass"
        caption_file(short["scenes"], ass, config["brand"])
        concat(parts, OUT / f"short_{n}.mp4", captions=ass)

    save(OUT / "chapters.json", marks)
    print("Chapters:", json.dumps(marks))


if __name__ == "__main__":
    main()
