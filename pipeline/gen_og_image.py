#!/usr/bin/env python3
"""Regenerate the social link-preview image (og-image.png, 1200x630).

The card plots the REAL site data (profitable companies, positioned exactly
as the live chart scores them: fairness on Y, log profit on X, coloured by
the combined fairness score, sized by median pay) plus the wordmark, a
"wide gap -> fair" legend, and the footer. It deliberately shows NO company
count, so it never needs updating as companies are added.

Run from the repo root:  python3 pipeline/gen_og_image.py
Requires a headless Chrome/Chromium for the HTML->PNG render (falls back to
writing og.html with instructions if none is found). Needs Pillow.
"""
import json, math, os, subprocess, tempfile, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def pct(items, key, higher_good):
    vals = sorted(((r[key], r) for r in items if r.get(key) is not None), key=lambda x: x[0])
    n = len(vals)
    out = {}
    for rank, (v, r) in enumerate(vals):
        p = rank / (n - 1) * 100 if n > 1 else 100
        out[r["t"]] = round(p if higher_good else 100 - p)
    return out


def score_color(s):
    c1, c2, c3 = (214, 69, 69), (224, 169, 46), (31, 157, 85)
    t = s / 100
    a, b, k = (c1, c2, t * 2) if t < 0.5 else (c2, c3, (t - 0.5) * 2)
    return "rgb(%d,%d,%d)" % tuple(round(a[j] + (b[j] - a[j]) * k) for j in range(3))


def build_html():
    rows = json.load(open(os.path.join(ROOT, "data", "web_data.json")))
    for r in rows:
        p, emp, med = r.get("p"), r.get("emp"), r.get("med")
        r["ppe"] = (p * 1e9 / emp) if (p and emp) else None
        r["share"] = (med / r["ppe"]) if (med and r["ppe"] and not r.get("loss")) else None
    sGap = pct(rows, "r", False)
    sVal = pct([r for r in rows if r["share"] is not None], "share", True)
    for r in rows:
        g, v = sGap.get(r["t"]), sVal.get(r["t"])
        r["score"] = round((g + v) / 2) if (g is not None and v is not None) else \
            (g if r.get("loss") and g is not None else (g if g is not None else v))

    pts = [r for r in rows if r.get("p", 0) and r["p"] > 0 and r.get("score") is not None]
    ps = [r["p"] for r in pts]
    minP, maxP = min(ps) * 0.8, max(ps) * 1.25
    meds = [r["med"] for r in pts if r.get("med")]
    minMed, maxMed = min(meds), max(meds)
    CX0, CX1, CY0, CY1 = 96, 1104, 322, 520

    def xlog(v): return CX0 + (math.log(v) - math.log(minP)) / (math.log(maxP) - math.log(minP)) * (CX1 - CX0)
    def yscore(s): return CY1 - (s / 100) * (CY1 - CY0)
    def rad(m): return 4 + 15 * math.sqrt(max(0, (m - minMed) / (maxMed - minMed))) if m else 4

    pts.sort(key=lambda r: -(r.get("med") or 0))
    circles = "\n".join(
        f'<circle cx="{xlog(r["p"]):.1f}" cy="{yscore(r["score"]):.1f}" r="{rad(r.get("med")):.1f}" '
        f'fill="{score_color(r["score"])}" fill-opacity="0.62" stroke="rgba(20,24,31,.10)" stroke-width="0.6"/>'
        for r in pts)

    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1200px;height:630px}}
body{{font-family:"Helvetica Neue",Helvetica,Arial,sans-serif;background:#fff;color:#14181f;position:relative;overflow:hidden}}
.topbar{{position:absolute;top:0;left:0;right:0;height:6px;background:#2f6df6}}
.wrap{{position:absolute;inset:0;padding:52px 60px 40px}}
h1{{font-size:82px;font-weight:800;letter-spacing:-.03em;line-height:.9}}
h1 span{{color:#2f6df6}}
.sub{{margin-top:20px;font-size:29px;line-height:1.32;color:#5b6472;max-width:1000px}}
.card{{position:absolute;left:60px;right:60px;top:292px;height:250px;background:#f7f8fa;border:1px solid #e3e7ee;border-radius:20px;box-shadow:0 1px 3px rgba(20,24,31,.06),0 10px 30px rgba(20,24,31,.05)}}
.axlbl{{fill:#8a93a2;font-size:17px;font-weight:600}}
.legend{{position:absolute;right:26px;top:18px;display:flex;align-items:center;gap:9px;font-size:15px;color:#8a93a2;font-weight:600}}
.grad{{width:120px;height:9px;border-radius:5px;background:linear-gradient(90deg,#d64545,#e0a92e,#1f9d55)}}
.foot{{position:absolute;left:60px;right:60px;bottom:34px;display:flex;justify-content:space-between;align-items:baseline}}
.foot .site{{color:#2f6df6;font-size:27px;font-weight:800;letter-spacing:-.01em}}
.foot .src{{color:#8a93a2;font-size:22px;font-weight:500}}
</style></head><body>
<div class="topbar"></div>
<div class="wrap"><h1>Fair<span>500</span></h1>
  <div class="sub">How much money each S&amp;P&nbsp;500 company makes,<br>and how much of it reaches the people who work there.</div></div>
<div class="card">
  <div class="legend"><span>Wide gap</span><span class="grad"></span><span>Fair</span></div>
  <svg viewBox="0 0 1080 250" width="1080" height="250" style="position:absolute;left:0;top:0">
    <text class="axlbl" x="26" y="34">fairer</text>
    <text class="axlbl" x="26" y="212">less fair</text>
    <text class="axlbl" x="1054" y="230" text-anchor="end">more total profit  &#8594;</text></svg>
  <svg viewBox="0 0 1200 630" width="1200" height="630" style="position:absolute;left:-60px;top:-292px">{circles}</svg>
</div>
<div class="foot"><span class="site">fair500.com</span><span class="src">Built from SEC EDGAR filings</span></div>
</body></html>'''


def find_chrome():
    for c in ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "/Applications/Chromium.app/Contents/MacOS/Chromium",
              shutil.which("google-chrome"), shutil.which("chromium"), shutil.which("chromium-browser")]:
        if c and os.path.exists(c):
            return c
    return None


def main():
    html = build_html()
    tmp = tempfile.mkdtemp()
    htmlpath = os.path.join(tmp, "og.html")
    open(htmlpath, "w").write(html)
    chrome = find_chrome()
    if not chrome:
        dest = os.path.join(ROOT, "og.html")
        shutil.copy(htmlpath, dest)
        print(f"No headless Chrome found. Wrote {dest}; open it and export a 1200x630 PNG to og-image.png.")
        return
    raw = os.path.join(tmp, "og_2x.png")
    subprocess.run([chrome, "--headless", "--disable-gpu", "--hide-scrollbars",
                    "--force-device-scale-factor=2", "--window-size=1200,630",
                    "--default-background-color=FFFFFFFF", f"--screenshot={raw}",
                    f"file://{htmlpath}"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    from PIL import Image
    im = Image.open(raw).convert("RGB").resize((1200, 630), Image.LANCZOS)
    out = os.path.join(ROOT, "og-image.png")
    im.save(out, optimize=True)
    print(f"Wrote {out} ({os.path.getsize(out)} bytes) from live web_data.json.")


if __name__ == "__main__":
    main()
