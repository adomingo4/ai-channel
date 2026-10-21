"""Line up a recording with the script's scenes.

transcribe() turns your recording into words with timestamps (free, local Whisper).
split_points() matches those words to the script, so each scene gets the stretch of
audio where you read it, even if you skip, repeat or add a few words.
"""
import re
from difflib import SequenceMatcher

_MODEL = None


def norm(token):
    t = token.lower().replace("’", "'")
    t = re.sub(r"[^a-z0-9$%']", "", t)
    return t.strip("'")


def transcribe(path, model_name="small.en"):
    """Returns [{'w','start','end'}], or None if Whisper isn't available."""
    global _MODEL
    try:
        from faster_whisper import WhisperModel
        if _MODEL is None:
            _MODEL = WhisperModel(model_name, device="cpu", compute_type="int8")
        segments, _ = _MODEL.transcribe(str(path), language="en", word_timestamps=True,
                                        vad_filter=True, beam_size=5)
        words = []
        for seg in segments:
            for w in seg.words or []:
                words.append({"w": w.word.strip(), "start": float(w.start), "end": float(w.end)})
        return words
    except Exception as e:
        print(f"  ! Whisper not available ({str(e)[:100]}); spacing scenes by word count instead")
        return None


def even_words(scene_texts, duration):
    """Fallback: pretend the words were spread evenly over the recording."""
    words = [w for t in scene_texts for w in t.split()]
    step = duration / max(len(words), 1)
    return [{"w": w, "start": i * step, "end": (i + 0.85) * step} for i, w in enumerate(words)]


def find_silences(path, noise_db=-35, min_len=0.2):
    """Quiet stretches in the recording, from ffmpeg's silence detector: [(start, end)]."""
    import subprocess
    out = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
                          f"silencedetect=noise={noise_db}dB:d={min_len}", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", out)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
    return list(zip(starts, ends))


def split_by_silence(scene_texts, duration, silences):
    """No transcript: estimate each boundary by word count, then move it to the
    nearest clear pause in the audio."""
    counts = [max(1, len(t.split())) for t in scene_texts]
    lead = silences[0][1] if silences and silences[0][0] <= 0.05 else 0.0
    tail = silences[-1][0] if silences and silences[-1][1] >= duration - 0.05 else duration
    speech = tail - lead
    pauses = [(s, e) for s, e in silences if e - s >= 0.3 and s > lead and e < tail]
    bounds, used = [max(0.0, lead - 0.25)], set()
    total = sum(counts)
    for i in range(1, len(scene_texts)):
        est = lead + speech * sum(counts[:i]) / total
        options = [(abs((s + e) / 2 - est), k) for k, (s, e) in enumerate(pauses)
                   if k not in used and (s + e) / 2 > bounds[-1] + 0.8]
        if options:
            _, k = min(options)
            used.add(k)
            bounds.append((pauses[k][0] + pauses[k][1]) / 2)
        else:
            bounds.append(max(est, bounds[-1] + 0.8))
    bounds.append(min(duration, tail + 0.4))
    return [(round(bounds[i], 3), round(bounds[i + 1], 3), []) for i in range(len(scene_texts))]


def split_points(scene_texts, asr, duration, silences=None):
    """Returns [(start, end, [words relative to start]) per scene]."""
    s_tokens, s_scene = [], []
    for si, text in enumerate(scene_texts):
        for tok in text.split():
            t = norm(tok)
            if t:
                s_tokens.append(t)
                s_scene.append(si)
    asr = [w for w in asr if norm(w["w"])]
    a_tokens = [norm(w["w"]) for w in asr]
    if not asr and silences:
        return split_by_silence(scene_texts, duration, silences)
    if not asr:
        asr = even_words(scene_texts, duration)
        a_tokens = [norm(w["w"]) for w in asr]

    match = {}
    for blk in SequenceMatcher(None, s_tokens, a_tokens, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            match[blk.a + k] = blk.b + k

    n = len(scene_texts)
    first_tok = [s_scene.index(si) if si in s_scene else None for si in range(n)]
    starts_idx = [0] + [None] * (n - 1)          # index into asr where each scene begins

    def silence_before(ai):
        return asr[ai]["start"] - asr[ai - 1]["end"] if 0 < ai < len(asr) else 0.0

    for si in range(1, n):
        ft = first_tok[si]
        if ft is None:
            continue
        last = (first_tok[si + 1] if si + 1 < n and first_tok[si + 1] is not None else len(s_tokens))
        # the last spoken word we know belongs to an earlier scene: never cut before it
        earlier = [match[k] for k in range(0, ft) if k in match]
        floor = (max(earlier) + 1) if earlier else 1
        for k in range(ft, last):
            if k in match:
                hi = match[k]
                est = hi - (k - ft)              # step back over opening words we didn't match
                lo = max(floor, est - 3)
                if lo > hi:
                    lo = hi
                # cut where the speaker actually paused, near the expected spot
                starts_idx[si] = max(range(lo, hi + 1), key=lambda ai: (silence_before(ai), -abs(ai - est)))
                break

    def gap_time(ai):
        if ai <= 0:
            return max(0.0, asr[0]["start"] - 0.2)
        if ai >= len(asr):
            return duration
        a, b = asr[ai - 1]["end"], asr[ai]["start"]
        # best: the longest real silence in the audio between those two words
        # (works even if the transcript missed a word at either side)
        quiet = [(s, e) for s, e in (silences or []) if e > a - 0.05 and s < b + 0.05]
        if quiet:
            s, e = max(quiet, key=lambda x: x[1] - x[0])
            return (max(s, a - 0.05) + min(e, b + 0.05)) / 2
        return (a + b) / 2

    times = [gap_time(i) if i is not None else None for i in starts_idx]
    times[0] = max(0.0, asr[0]["start"] - 0.25)
    end_time = min(duration, asr[-1]["end"] + 0.4)

    # fill scenes that matched nothing, by word count between known neighbours
    counts = [max(1, len(t.split())) for t in scene_texts]
    known = [i for i, t in enumerate(times) if t is not None]
    for i in range(n):
        if times[i] is None:
            lo = max(k for k in known if k < i)
            hi_list = [k for k in known if k > i]
            hi, hi_t = (hi_list[0], times[hi_list[0]]) if hi_list else (n, end_time)
            span = sum(counts[lo:hi])
            times[i] = times[lo] + (hi_t - times[lo]) * sum(counts[lo:i]) / span

    # keep scenes in order and at least 0.8 s long
    for i in range(1, n):
        if times[i] < times[i - 1] + 0.8:
            times[i] = times[i - 1] + 0.8
    bounds = times + [max(end_time, times[-1] + 0.8)]

    result = []
    for i in range(n):
        s, e = bounds[i], bounds[i + 1]
        ws = [{"w": w["w"], "start": round(w["start"] - s, 3), "end": round(min(w["end"], e) - s, 3)}
              for w in asr if s <= w["start"] < e]
        result.append((round(s, 3), round(e, 3), ws))
    return result
