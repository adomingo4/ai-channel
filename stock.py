"""Free stock footage from Pixabay (or Pexels): free API key, free for commercial use.

get_clip(query, kind, seconds) returns a local .mp4 that fits the frame, or a moving
gradient made locally when there's no key, no match, or Pexels can't be reached.
"""
import hashlib
import os
import random

import requests

from common import MOCK, OUT, run

API = "https://api.pexels.com"
_used = set()


PIXABAY = "https://pixabay.com/api"


def _pixabay_key():
    return os.environ.get("PIXABAY_API_KEY", "").strip()


def _pexels_key():
    return os.environ.get("PEXELS_API_KEY", "").strip()


def _key():
    return _pixabay_key() or _pexels_key()


def _download(url, path):
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)


def _search_pixabay(query, kind):
    r = requests.get(f"{PIXABAY}/videos/", timeout=60, params={
        "key": _pixabay_key(), "q": query[:100], "video_type": "film", "safesearch": "true", "per_page": 20})
    r.raise_for_status()
    out, seen = [], []
    for v in r.json().get("hits", []):
        vids = v.get("videos", {})
        # Full HD is plenty; vertical Shorts are cropped from the middle of the frame
        pick = next((vids[k] for k in ("medium", "large", "small") if vids.get(k, {}).get("url")), None)
        if pick:
            (seen if v["id"] in _used else out).append((v["id"], pick["url"], v.get("duration", 0)))
    return out + seen   # unused clips first; reuse one only if nothing else matches


def _search_video(query, kind):
    if _pixabay_key():
        return _search_pixabay(query, kind)
    orient = "landscape" if kind == "long" else "portrait"
    r = requests.get(f"{API}/videos/search", headers={"Authorization": _pexels_key()}, timeout=60,
                     params={"query": query, "orientation": orient, "size": "medium", "per_page": 20})
    r.raise_for_status()
    want_w = 1920 if kind == "long" else 1080
    best = []
    for v in r.json().get("videos", []):
        if v["id"] in _used:
            continue
        files = [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4" and f.get("width")]
        if not files:
            continue
        # the smallest file that is still at least full-HD wide (or the largest available)
        files.sort(key=lambda f: f["width"])
        pick = next((f for f in files if f["width"] >= want_w), files[-1])
        best.append((v["id"], pick["link"], v.get("duration", 0)))
    return best


def _gradient(kind, seconds, path, seed):
    """No stock available: a slow, moving colour gradient in the channel's palette."""
    w, h = (1920, 1080) if kind == "long" else (1080, 1920)
    rnd = random.Random(seed)
    palettes = [("0x1B2A6B", "0x0F1222", "0x3B1F5C"), ("0x0F3D4A", "0x0F1222", "0x1B2A6B"),
                ("0x3B1F5C", "0x0F1222", "0x5A2340"), ("0x123B2E", "0x0F1222", "0x1B2A6B")]
    c0, c1, c2 = rnd.choice(palettes)
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", f"gradients=s={w}x{h}:c0={c0}:c1={c1}:c2={c2}:nb_colors=3:speed=0.008:seed={seed}:r=30",
         "-t", f"{seconds:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
         str(path)])
    return path


def get_clip(query, kind, seconds, name):
    """A background clip for one scene, already cut to `seconds` and sized to the frame."""
    folder = OUT / "stock"
    folder.mkdir(parents=True, exist_ok=True)
    seed = int(hashlib.md5(f"{query}{name}".encode()).hexdigest()[:6], 16)
    out = folder / f"{name}.mp4"
    w, h = (1920, 1080) if kind == "long" else (1080, 1920)
    src = None
    if _key() and query:
        try:
            for vid, link, dur in _search_video(query, kind):
                raw = folder / f"stock_{vid}.mp4"
                if not raw.exists():
                    _download(link, raw)
                _used.add(vid)
                src = raw
                break
            if not src:
                print(f"  ! no stock video for '{query}', using a gradient")
        except Exception as e:
            print(f"  ! stock footage unavailable ({str(e)[:80]}), using a gradient")
    if not src:
        test = os.environ.get("TEST_STOCK_DIR")  # local testing stand-in for Pexels
        if test and os.path.isdir(test):
            files = sorted(f for f in os.listdir(test) if f.endswith(".mp4"))
            if files:
                src = os.path.join(test, files[seed % len(files)])
    if not src:
        return _gradient(kind, seconds, out, seed % 10000)
    # fill the frame, loop if the clip is short, slow it slightly for a calmer feel
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-stream_loop", "-1", "-i", str(src),
         "-vf", f"setpts=1.15*PTS,scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps=30,format=yuv420p",
         "-t", f"{seconds:.2f}", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", str(out)])
    return out


def get_photo(query, path):
    """A landscape stock photo for the thumbnail, or None."""
    if not _key() or not query:
        return None
    try:
        if _pixabay_key():
            r = requests.get(f"{PIXABAY}/", timeout=60, params={
                "key": _pixabay_key(), "q": query[:100], "image_type": "photo", "orientation": "horizontal",
                "safesearch": "true", "per_page": 5})
            r.raise_for_status()
            hits = r.json().get("hits", [])
            if hits:
                _download(hits[0]["largeImageURL"], path)
                return path
            return None
        r = requests.get(f"{API}/v1/search", headers={"Authorization": _pexels_key()}, timeout=60,
                         params={"query": query, "orientation": "landscape", "per_page": 5})
        r.raise_for_status()
        photos = r.json().get("photos", [])
        if photos:
            _download(photos[0]["src"]["large2x"], path)
            return path
    except Exception as e:
        print(f"  ! stock photo unavailable ({str(e)[:80]})")
    return None
