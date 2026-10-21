"""Talk to the script-writing model: Gemini (free tier) or Claude (paid API)."""
import os
import re
import time

import requests

GEMINI = "https://generativelanguage.googleapis.com/v1beta"


def _gemini_key():
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise SystemExit("Missing secret GEMINI_API_KEY")
    return key


def pick_gemini_model(config):
    """'auto' = the newest Flash model this key can use (free tier friendly)."""
    wanted = config.get("gemini_model", "auto")
    if wanted and wanted != "auto":
        return wanted
    r = requests.get(f"{GEMINI}/models", params={"pageSize": 200},
                     headers={"x-goog-api-key": _gemini_key()}, timeout=60)
    r.raise_for_status()
    best = None
    for m in r.json().get("models", []):
        name = m["name"].split("/")[-1]
        if "generateContent" not in m.get("supportedGenerationMethods", []):
            continue
        if "flash" not in name or any(x in name for x in ("lite", "image", "tts", "live", "audio", "thinking", "exp")):
            continue
        v = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
        if not v:
            continue
        score = (float(v.group(1)), "preview" not in name, -len(name))
        if best is None or score > best[0]:
            best = (score, name)
    if not best:
        raise SystemExit("No Gemini Flash model available for this key")
    print(f"Using Gemini model {best[1]}")
    return best[1]


def gemini(system, user, config):
    model = pick_gemini_model(config)
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 16384},
    }
    for attempt in range(6):
        r = requests.post(f"{GEMINI}/models/{model}:generateContent", json=body, timeout=300,
                          headers={"x-goog-api-key": _gemini_key()})
        if r.status_code == 200:
            data = r.json()
            parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts)
            if text.strip():
                return text
            print("Empty answer from Gemini, retrying")
        elif r.status_code in (429, 500, 503):
            wait = 30 * (attempt + 1)
            print(f"Gemini busy or rate-limited ({r.status_code}), waiting {wait}s")
            time.sleep(wait)
            continue
        else:
            raise SystemExit(f"Gemini error {r.status_code}: {r.text[:400]}")
    raise SystemExit("Gemini kept failing; run it again later")


def claude(system, user, config):
    import anthropic

    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": user}]
    tools = [{"type": config["web_search_tool"], "name": "web_search", "max_uses": config.get("max_searches", 8)}]
    for _ in range(6):
        resp = client.messages.create(model=config["claude_model"], max_tokens=16000,
                                      system=system, tools=tools, messages=messages)
        if resp.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": resp.content})
            continue
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    raise RuntimeError("Claude did not finish after several continuations")


def call(system, user, config):
    if config.get("script_provider", "gemini") == "claude":
        return claude(system, user, config)
    return gemini(system, user, config)
