"""Step 2: turn every scene's narration into audio with your ElevenLabs voice clone.

Needs ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID. In MOCK mode it makes silent audio
of the right length instead, so the rest of the pipeline can be tested for free.
Writes out/audio/*.mp3 and out/timeline.json (every scene with its audio length).
"""
import os
import time
from pathlib import Path

import requests

from common import MOCK, OUT, cfg, media_seconds, read_out, run, save

API = "https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128"


def tts(text, path, prev_text, next_text, config):
    if MOCK:
        seconds = max(2.0, len(text.split()) / 2.5)
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
             "-i", "anullsrc=r=44100:cl=mono", "-t", f"{seconds:.2f}", "-q:a", "9", str(path)])
        return
    key = os.environ["ELEVENLABS_API_KEY"]
    voice = os.environ["ELEVENLABS_VOICE_ID"]
    body = {"text": text, "model_id": config["elevenlabs_model"],
            "voice_settings": config["voice_settings"]}
    if prev_text:
        body["previous_text"] = prev_text
    if next_text:
        body["next_text"] = next_text
    for attempt in range(5):
        r = requests.post(API.format(voice=voice), json=body, timeout=180,
                          headers={"xi-api-key": key, "accept": "audio/mpeg"})
        if r.status_code == 200:
            path.write_bytes(r.content)
            return
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(5 * (attempt + 1))
            continue
        raise RuntimeError(f"ElevenLabs error {r.status_code}: {r.text[:300]}")
    raise RuntimeError("ElevenLabs kept failing; try again later")


def voice_list(scenes, prefix, config):
    audio_dir = OUT / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    items = []
    for i, scene in enumerate(scenes):
        path = audio_dir / f"{prefix}_{i:02d}.mp3"
        prev_text = scenes[i - 1]["narration"] if i else ""
        next_text = scenes[i + 1]["narration"] if i + 1 < len(scenes) else ""
        tts(scene["narration"].strip(), path, prev_text, next_text, config)
        items.append({**scene, "audio": str(path), "seconds": round(media_seconds(path), 3)})
        print(f"  {path.name}: {items[-1]['seconds']:.1f}s")
    return items


AUDIO_EXT = (".m4a", ".mp3", ".wav", ".aac", ".ogg", ".opus", ".webm", ".mp4", ".mov", ".flac")


def find_recording(folder, name):
    for f in sorted(folder.iterdir()):
        if f.stem.lower() == name and f.suffix.lower() in AUDIO_EXT:
            return f
    return None


def recorded_list(scenes, recording, prefix, config):
    """Clean up your recording, match it to the script and cut it scene by scene."""
    import align

    audio_dir = OUT / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    clean = audio_dir / f"{prefix}_clean.wav"
    # phone-friendly clean-up: remove rumble and steady background hiss, even out the level
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(recording), "-vn",
         "-af", "highpass=f=80,afftdn=nf=-25,acompressor=threshold=-20dB:ratio=3:attack=5:release=120",
         "-ac", "1", "-ar", "48000", str(clean)])
    duration = media_seconds(clean)
    texts = [s["narration"] for s in scenes]
    words = align.transcribe(clean, config.get("whisper_model", "small.en")) or []
    parts = align.split_points(texts, words, duration, align.find_silences(clean))
    items = []
    for i, (scene, (start, end, ws)) in enumerate(zip(scenes, parts)):
        path = audio_dir / f"{prefix}_{i:02d}.wav"
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(clean),
             "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-af", "afade=t=in:d=0.04", str(path)])
        items.append({**scene, "audio": str(path), "seconds": round(media_seconds(path), 3), "words": ws})
        print(f"  {path.name}: {items[-1]['seconds']:.1f}s")
    return items


def main():
    config = cfg()
    script = read_out("script.json")
    if config.get("voice_mode", "recorded") == "recorded":
        folder = Path(os.environ["EPISODE"])
        video = find_recording(folder, "video")
        if not video:
            raise SystemExit(f"No video recording in {folder}")
        timeline = {"long": recorded_list(script["scenes"], video, "long", config), "shorts": []}
        for n, short in enumerate(script["shorts"]):
            rec = find_recording(folder, f"short{n + 1}")
            if not rec:
                print(f"  ! short{n + 1} not recorded, skipping that Short")
                continue
            timeline["shorts"].append({"title": short["title"], "index": n,
                                       "scenes": recorded_list(short["scenes"], rec, f"short{n}", config)})
    else:
        timeline = {"long": voice_list(script["scenes"], "long", config), "shorts": []}
        for n, short in enumerate(script["shorts"]):
            timeline["shorts"].append({"title": short["title"], "index": n,
                                       "scenes": voice_list(short["scenes"], f"short{n}", config)})
    save(OUT / "timeline.json", timeline)
    total = sum(s["seconds"] for s in timeline["long"])
    print(f"Narration: long video {total / 60:.1f} min, {len(timeline['shorts'])} Shorts")


if __name__ == "__main__":
    main()
