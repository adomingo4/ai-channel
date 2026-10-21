"""Step 3: build a silent video clip for every scene, plus the thumbnail.

Every scene sits on moving stock footage (Pexels, free) chosen from the scene's
"broll" search words. On top of it:
- broll:   the footage full screen with a bold caption
- rank:    "#3" countdown title for trend lists
- stat:    one big number with a short label
- title / outro, bullets / steps / verdict, table: glass panels that slide in,
           lists and tables revealing one row at a time
- web:     a real product page scrolling inside a browser window (used sparingly)
Writes out/clips/<scene>.mp4 and out/thumbnail.png.
"""
import html
import json
from urllib.parse import urlparse

import stock
from common import MOCK, OUT, cfg, read_out, run

FPS = 30
PAD = 0.35
LAST_PAD = 0.9
XF = 0.4      # must match assemble.XF (scene transitions)
SIZES = {"long": (1920, 1080), "short": (1080, 1920)}
ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS)]


def esc(s):
    return html.escape(str(s or ""))


def rgba(hex_color, a):
    h = hex_color.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a})"


# ---------------------------------------------------------------- overlay HTML (transparent)
def page(body, w, h, b, kind):
    s = 1.0 if kind == "long" else 1.08
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:{w}px;height:{h}px;background:transparent;color:{b['text']};
font-family:'{b['font']}','Inter','DejaVu Sans',sans-serif;overflow:hidden}}
.glass{{background:{rgba(b['background'], 0.78)};border:1px solid rgba(255,255,255,.10);border-radius:{int(32*s)}px;
box-shadow:0 30px 90px rgba(0,0,0,.45);padding:{int(64*s)}px {int(72*s)}px}}
.kicker{{font-size:{int(30*s)}px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:{b['accent']}}}
h1{{font-size:{int(76*s)}px;font-weight:800;letter-spacing:-0.02em;line-height:1.07}}
.big h1{{font-size:{int(112*s)}px;text-shadow:0 6px 40px rgba(0,0,0,.55)}}
.sub{{font-size:{int(40*s)}px;color:{b['muted']};margin-top:{int(22*s)}px;font-weight:500;line-height:1.3}}
.big .sub{{color:#E6E8F2;text-shadow:0 4px 24px rgba(0,0,0,.6)}}
.items{{display:flex;flex-direction:column;gap:{int(18*s)}px;margin-top:{int(40*s)}px}}
.item{{display:flex;align-items:center;gap:{int(24*s)}px;background:rgba(255,255,255,.07);border-radius:{int(20*s)}px;
padding:{int(22*s)}px {int(28*s)}px;font-size:{int(38*s)}px;font-weight:600;line-height:1.25}}
.dot{{flex:0 0 auto;width:{int(46*s)}px;height:{int(46*s)}px;border-radius:50%;background:{b['accent']};color:{b['background']};
display:flex;align-items:center;justify-content:center;font-size:{int(24*s)}px;font-weight:900}}
.hidden{{visibility:hidden}}
table{{border-collapse:separate;border-spacing:0 {int(12*s)}px;margin-top:{int(28*s)}px;width:100%;font-size:{int(36*s)}px}}
th{{text-align:left;color:{b['accent']};font-weight:800;padding:0 {int(26*s)}px 6px}}
td{{background:rgba(255,255,255,.07);padding:{int(20*s)}px {int(26*s)}px;font-weight:600;line-height:1.25}}
td:first-child{{border-radius:16px 0 0 16px;color:{b['muted']}}}
td:last-child{{border-radius:0 16px 16px 0}}
.rank{{font-size:{int(230*s)}px;font-weight:900;line-height:.9;color:{b['accent']};text-shadow:0 10px 60px rgba(0,0,0,.5)}}
.stat{{font-size:{int(200*s)}px;font-weight:900;line-height:1;color:{b['accent_2']};letter-spacing:-0.03em}}
.cap{{font-size:{int(84*s)}px;font-weight:900;line-height:1.05;letter-spacing:-0.02em;text-shadow:0 6px 40px rgba(0,0,0,.7)}}
.brand{{position:absolute;right:56px;top:44px;font-size:24px;font-weight:800;letter-spacing:.12em;
text-transform:uppercase;color:rgba(255,255,255,.75);text-shadow:0 2px 12px rgba(0,0,0,.6)}}
</style></head><body>{body}</body></html>"""


SHADE_LONG = "linear-gradient(90deg,rgba(8,10,22,.82) 0%,rgba(8,10,22,.55) 45%,rgba(8,10,22,0) 80%)"
SHADE_SHORT = "linear-gradient(180deg,rgba(8,10,22,.0) 0%,rgba(8,10,22,.70) 30%,rgba(8,10,22,.70) 65%,rgba(8,10,22,0) 100%)"


def overlay_html(v, kind, shown, config):
    """The text layer for a scene. Returns (html, background treatment)."""
    b, (w, h) = config["brand"], SIZES[kind]
    t = v["type"]
    long = kind == "long"
    brand = f'<div class="brand">{esc(config["channel_name"])}</div>' if long else ""
    pad = "padding:120px 140px" if long else "padding:240px 70px 0"
    col = f"position:absolute;inset:0;display:flex;flex-direction:column;{pad};"

    if t == "broll":
        grad = "linear-gradient(180deg,rgba(0,0,0,0) 45%,rgba(0,0,0,.72) 100%)"
        pos = "justify-content:flex-end;padding-bottom:130px" if long else "justify-content:center"
        body = (f'<div style="position:absolute;inset:0;background:{grad}"></div>'
                f'<div style="{col}{pos}"><div class="cap" style="max-width:{1500 if long else 940}px">'
                f'{esc(v.get("caption"))}</div></div>{brand}')
        return page(body, w, h, b, kind), "clear"
    shade = f'<div style="position:absolute;inset:0;background:{SHADE_LONG if long else SHADE_SHORT}"></div>'
    if t == "rank":
        body = (shade + f'<div style="{col}justify-content:center"><div class="rank">#{esc(v.get("number"))}</div>'
                f'<div class="big" style="margin-top:20px;max-width:{1400 if long else 940}px"><h1>{esc(v.get("heading"))}</h1>'
                f'<div class="sub">{esc(v.get("sub"))}</div></div></div>{brand}')
        return page(body, w, h, b, kind), "dim"
    if t in ("title", "outro", "web-fallback"):
        body = (shade + f'<div style="{col}justify-content:center"><div class="big" style="max-width:{1500 if long else 940}px">'
                f'<div class="kicker">{esc(v.get("kicker") or config["channel_name"])}</div>'
                f'<h1 style="margin-top:18px">{esc(v.get("heading"))}</h1><div class="sub">{esc(v.get("sub"))}</div></div></div>{brand}')
        return page(body, w, h, b, kind), "dim"
    if t == "stat":
        body = (f'<div style="{col}justify-content:center;align-items:{"flex-start" if long else "stretch"}">'
                f'<div class="glass" style="max-width:{1300 if long else 940}px"><div class="stat">{esc(v.get("value"))}</div>'
                f'<div class="sub" style="font-size:{46 if long else 50}px;color:#F5F6FA;font-weight:700">{esc(v.get("label"))}</div>'
                f'<div class="sub" style="font-size:26px">{esc(v.get("source"))}</div></div></div>{brand}')
        return page(body, w, h, b, kind), "blur"
    if t in ("bullets", "steps", "verdict"):
        rows = []
        for i, item in enumerate(v.get("items", [])):
            mark = str(i + 1) if t == "steps" else ("&#10003;" if t == "verdict" else "")
            rows.append(f'<div class="item{"" if i < shown else " hidden"}"><div class="dot">{mark}</div><div>{esc(item)}</div></div>')
        body = (f'<div style="{col}justify-content:center"><div class="glass" style="max-width:{1400 if long else 940}px">'
                f'<h1>{esc(v.get("heading"))}</h1><div class="items">{"".join(rows)}</div></div></div>{brand}')
        return page(body, w, h, b, kind), "blur"
    if t == "table":
        head = "".join(f"<th>{esc(c)}</th>" for c in v.get("columns", []))
        rows = "".join(f'<tr{"" if i < shown else " class=hidden"}>' + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>"
                       for i, r in enumerate(v.get("rows", [])))
        body = (f'<div style="{col}justify-content:center"><div class="glass" style="width:{1640 if long else 940}px">'
                f'<h1>{esc(v.get("heading"))}</h1><table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>'
                f'</div></div>{brand}')
        return page(body, w, h, b, kind), "blur"
    return page(f'<div style="{col}justify-content:center"><h1>{esc(v.get("heading"))}</h1></div>', w, h, b, kind), "dim"


def frame_html(domain, label, kind, config):
    b, (w, h) = config["brand"], SIZES[kind]
    win = dict(x=110, y=96, w=1700, h=930, bar=56) if kind == "long" else dict(x=60, y=300, w=960, h=1250, bar=64)
    label_html = ""
    if kind == "short":
        label_html = (f'<div style="position:absolute;left:60px;right:60px;top:110px;font-size:58px;font-weight:800;'
                      f'line-height:1.1;text-shadow:0 4px 24px rgba(0,0,0,.6)">{esc(label)}</div>')
    body = f"""{label_html}
<div style="position:absolute;left:{win['x']}px;top:{win['y']}px;width:{win['w']}px;height:{win['h']}px;
border-radius:22px;overflow:hidden;box-shadow:0 30px 90px rgba(0,0,0,.55)">
<div style="height:{win['bar']}px;background:#E9EBF2;display:flex;align-items:center;gap:12px;padding:0 22px">
<span style="width:16px;height:16px;border-radius:50%;background:#FF6B6B"></span>
<span style="width:16px;height:16px;border-radius:50%;background:#FFC453"></span>
<span style="width:16px;height:16px;border-radius:50%;background:#4ADE80"></span>
<span style="margin-left:18px;flex:1;height:{win['bar'] - 22}px;border-radius:10px;background:#fff;color:#4B5163;
font-size:{int(win['bar'] * .4)}px;display:flex;align-items:center;padding:0 18px;font-weight:600">{esc(domain)}</span>
</div></div>"""
    return page(body, w, h, b, kind), win


# ---------------------------------------------------------------- rendering helpers
def shot(pw_page, html_text, w, h, path):
    pw_page.set_viewport_size({"width": w, "height": h})
    pw_page.set_content(html_text, wait_until="load")
    pw_page.wait_for_timeout(120)
    pw_page.screenshot(path=str(path), omit_background=True)


ACCEPT = ["Accept all", "Accept All", "Accept", "I agree", "Agree", "Allow all", "Got it", "OK"]


def capture_site(browser, url, kind, path):
    if MOCK and not url.startswith("http://127.0.0.1"):
        return False
    vw, scale = (1600, 1) if kind == "long" else (430, 2)
    ctx = browser.new_context(viewport={"width": vw, "height": 900 if kind == "long" else 932},
                              device_scale_factor=scale, locale="en-US",
                              user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                          "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"))
    p = ctx.new_page()
    try:
        resp = p.goto(url, wait_until="domcontentloaded", timeout=45000)
        p.wait_for_timeout(3500)
        for text in ACCEPT:
            try:
                btn = p.get_by_role("button", name=text, exact=True)
                if btn.count():
                    btn.first.click(timeout=1500)
                    p.wait_for_timeout(600)
                    break
            except Exception:
                pass
        p.evaluate("""async () => { for (let y = 0; y < Math.min(document.body.scrollHeight, 7000); y += 700) {
            window.scrollTo(0, y); await new Promise(r => setTimeout(r, 250)); } window.scrollTo(0, 0); }""")
        p.wait_for_timeout(1200)
        title = (p.title() or "").lower()
        text_len = p.evaluate("document.body ? document.body.innerText.length : 0")
        blocked = any(k in title for k in ("just a moment", "access denied", "attention required", "forbidden"))
        if (resp and resp.status >= 400) or blocked or text_len < 300:
            print(f"  ! {url} looks blocked or empty, using footage instead")
            return False
        height = p.evaluate("Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)")
        cap = 6500 if kind == "long" else 2600
        p.screenshot(path=str(path), full_page=True,
                     clip={"x": 0, "y": 0, "width": vw, "height": max(600, min(height, cap))})
        return True
    except Exception as e:
        print(f"  ! could not capture {url}: {str(e)[:120]}")
        return False
    finally:
        ctx.close()


BG = {  # how the footage is treated under each kind of overlay
    "clear": "eq=brightness=-0.02:saturation=1.05",
    "dim": "eq=brightness=-0.16:saturation=0.85,gblur=sigma=2",
    "blur": "eq=brightness=-0.20:saturation=0.75,gblur=sigma=14",
    "web": "eq=brightness=-0.25:saturation=0.6,gblur=sigma=22",
}


def compose(bg_clip, layers, treatment, seconds, out_path, kind):
    """Footage + transparent text layers. layers = [(png, start, end)]; the first slides in."""
    w, h = SIZES[kind]
    zoom = f"scale={int(w * 1.06)}:{int(h * 1.06)},crop={w}:{h}:x='(iw-ow)/2*(1-t/{seconds:.3f})':y='(ih-oh)/2'"
    inputs = ["-i", str(bg_clip)]
    fc = [f"[0:v]{BG[treatment]},{zoom},format=yuv420p[bg]"]
    last = "bg"
    for i, (png, start, end) in enumerate(layers, 1):
        inputs += ["-loop", "1", "-t", f"{seconds:.3f}", "-i", str(png)]
        if i == 1:
            fc.append(f"[{i}:v]format=rgba,fade=t=in:st=0:d=0.45:alpha=1[l{i}]")
            x = "0"
            y = "'if(lt(t,0.45),40*(1-t/0.45),0)'"
        else:
            fc.append(f"[{i}:v]format=rgba[l{i}]")
            x, y = "0", "0"
        fc.append(f"[{last}][l{i}]overlay=x={x}:y={y}:enable='between(t,{start:.3f},{end:.3f})'[v{i}]")
        last = f"v{i}"
    fc.append(f"[{last}]fade=t=in:st=0:d=0.2,format=yuv420p[out]")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs, "-filter_complex", ";".join(fc),
         "-map", "[out]", "-t", f"{seconds:.3f}", *ENC, str(out_path)])


def encode_scroll(bg_clip, frame_png, site_png, win, kind, seconds, out_path):
    view_w, view_h = win["w"], win["h"] - win["bar"]
    hold = min(1.6, seconds * 0.2)
    speed = 90 if kind == "long" else 120
    fc = (f"[0:v]{BG['web']},format=yuv420p[bg];"
          f"[bg][1:v]overlay=0:0[fr];"
          f"[2:v]scale={view_w}:-2,crop={view_w}:{view_h}:0:'min(max(ih-{view_h},0), max(0,(t-{hold:.2f}))*{speed})'[pg];"
          f"[fr][pg]overlay={win['x']}:{win['y'] + win['bar']},fade=t=in:st=0:d=0.2,format=yuv420p[v]")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(bg_clip),
         "-loop", "1", "-t", f"{seconds:.3f}", "-i", str(frame_png), "-loop", "1", "-t", f"{seconds:.3f}", "-i", str(site_png),
         "-filter_complex", fc, "-map", "[v]", "-t", f"{seconds:.3f}", *ENC, str(out_path)])


def broll_query(scene, v):
    q = scene.get("broll") or v.get("heading") or v.get("caption") or v.get("label") or "technology"
    return str(q)[:60]


def scene_clip(pw, browser, scene, kind, seconds, name, config):
    tmp = OUT / "frames"
    tmp.mkdir(parents=True, exist_ok=True)
    clip = OUT / "clips" / f"{name}.mp4"
    clip.parent.mkdir(parents=True, exist_ok=True)
    v = dict(scene["visual"])
    w, h = SIZES[kind]
    bg = stock.get_clip(broll_query(scene, v), kind, seconds + 0.5, name)

    if v["type"] == "web":
        site = tmp / f"{name}_site.png"
        if capture_site(browser, v.get("url", ""), kind, site):
            domain = urlparse(v["url"]).netloc.replace("www.", "")
            frame_text, win = frame_html(domain, v.get("label", ""), kind, config)
            frame = tmp / f"{name}_frame.png"
            shot(pw, frame_text, w, h, frame)
            encode_scroll(bg, frame, site, win, kind, seconds, clip)
            return clip
        v = {"type": "broll", "caption": v.get("label") or ""}

    n = len(v.get("items", v.get("rows", []))) if v["type"] in ("bullets", "steps", "verdict", "table") else 0
    layers = []
    if n:
        lead = min(1.2, seconds * 0.15)
        step = (seconds - lead) / n
        t0 = 0.0
        for k in range(1, n + 1):
            png = tmp / f"{name}_{k}.png"
            html_text, treatment = overlay_html(v, kind, k, config)
            shot(pw, html_text, w, h, png)
            t1 = seconds if k == n else (lead + step * k)
            layers.append((png, t0, t1 + (0 if k == n else 0.04)))
            t0 = t1
    else:
        png = tmp / f"{name}_card.png"
        html_text, treatment = overlay_html(v, kind, 99, config)
        shot(pw, html_text, w, h, png)
        layers.append((png, 0.0, seconds))
    compose(bg, layers, treatment, seconds, clip, kind)
    return clip


def thumbnail(pw, script, config):
    b = config["brand"]
    t = script.get("thumbnail", {})
    photo = stock.get_photo(t.get("broll") or script.get("title"), OUT / "frames" / "thumb_photo.jpg")
    if photo:
        bg = f'url("file://{photo.resolve()}") center/cover'
    else:
        bg = f"linear-gradient(135deg,#1B2A6B 0%,{b['background']} 55%,#3B1F5C 100%)"
    chips = "".join(
        f'<span style="background:{c};color:{b["background"]};padding:12px 26px;border-radius:14px">{esc(x)}</span>'
        for x, c in zip(t.get("tags", t.get("tools", []))[:3], [b["accent"], b["accent_2"], b["good"]]))
    body = f"""<div style="position:absolute;inset:0;background:{bg}"></div>
<div style="position:absolute;inset:0;background:linear-gradient(90deg,rgba(10,12,24,.92) 0%,rgba(10,12,24,.65) 55%,rgba(10,12,24,.15) 100%)"></div>
<div style="position:absolute;inset:0;padding:64px 76px;display:flex;flex-direction:column;justify-content:space-between">
<div style="display:flex;gap:16px;font-size:36px;font-weight:800">{chips}</div>
<div style="font-size:112px;font-weight:900;line-height:.98;letter-spacing:-0.03em;max-width:980px;text-shadow:0 6px 30px rgba(0,0,0,.5)">{esc(t.get('headline', script['title']))}</div>
<div style="font-size:28px;font-weight:800;color:{b['muted']};letter-spacing:.12em;text-transform:uppercase">{esc(config['channel_name'])}</div>
</div>"""
    (OUT / "frames").mkdir(parents=True, exist_ok=True)
    pw.set_viewport_size({"width": 1280, "height": 720})
    pw.set_content(page(body, 1280, 720, b, "long").replace("background:transparent", f"background:{b['background']}"),
                   wait_until="load")
    pw.wait_for_timeout(300)
    pw.screenshot(path=str(OUT / "thumbnail.png"))


def main():
    from playwright.sync_api import sync_playwright

    config = cfg()
    script = read_out("script.json")
    timeline = read_out("timeline.json")
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--allow-file-access-from-files"])
        pw = browser.new_page()
        thumbnail(pw, script, config)
        for i, sc in enumerate(timeline["long"]):
            pad = LAST_PAD if i == len(timeline["long"]) - 1 else PAD
            sc["pad"] = pad
            extra = 0 if i == len(timeline["long"]) - 1 else XF
            sc["clip"] = str(scene_clip(pw, browser, sc, "long", sc["seconds"] + pad + extra, f"long_{i:02d}", config))
            print(f"  long_{i:02d} {sc['visual']['type']}")
        for n, short in enumerate(timeline["shorts"]):
            for i, sc in enumerate(short["scenes"]):
                pad = LAST_PAD if i == len(short["scenes"]) - 1 else 0.2
                sc["pad"] = pad
                extra = 0 if i == len(short["scenes"]) - 1 else XF
                sc["clip"] = str(scene_clip(pw, browser, sc, "short", sc["seconds"] + pad + extra, f"short{n}_{i:02d}", config))
        browser.close()
    (OUT / "timeline.json").write_text(json.dumps(timeline, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
