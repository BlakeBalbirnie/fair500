#!/usr/bin/env python3
"""Focused re-audit: confirm ratio x median ~= CEO pay for EVERY company after
the fixes. Fast-failing fetch so it can't hang. Reports remaining inconsistencies
(should be only the known false-flags) and how many couldn't be checked."""
import json, re, html, time, os, urllib.request, pipeline
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data"))

UA = "Fair500 research blakebalbirnie@gmail.com"
def get(url, maxbytes=None):
    for a in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=18) as r:
                return r.read(maxbytes) if maxbytes else r.read()
        except Exception:
            if a == 1: raise
            time.sleep(0.6)

def proxy_text(cik):
    sub = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik}.json").decode())["filings"]["recent"]
    u = pipeline.find_form_url(cik, sub, "DEF 14A")
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", get(u).decode("utf-8", "ignore")))) if u else None

def window(t):
    pos = None
    for m in pipeline._RATIO.finditer(t):
        if pipeline._GATE.search(t[max(0, m.start()-280): m.end()+40]): pos = m.start(); break
    if pos is None:
        for m in pipeline._TIMES.finditer(t):
            if "median" in t[max(0, m.start()-60): m.end()+110].lower(): pos = m.start(); break
    if pos is None:
        m = re.search(r"median[- ]?(?:compensated |paid )?(?:employee|associate|of the annual)", t, re.I)
        pos = m.start() if m else None
    return t[max(0, pos-850): pos+850] if pos is not None else None

def ceo(win):
    vals = [int(x.replace(",", "")) for x in re.findall(r"\$\s?([\d,]{7,})", win)]
    vals = [v for v in vals if 900_000 <= v <= 600_000_000]
    return max(vals) if vals else None

d = json.load(open("data.json"))
bad, unchecked, unverifiable_list = [], 0, []
n = 0
for r in d:
    if not (r.get("ratio") and r.get("median_pay") and r.get("proxy_url")): continue
    n += 1
    try:
        t = proxy_text(r["cik"]); w = window(t) if t else None; c = ceo(w) if w else None
        if not c: unchecked += 1; unverifiable_list.append(r['ticker'])
        else:
            imp = c / r["median_pay"]
            if abs(imp - r["ratio"]) / r["ratio"] > 0.15:
                bad.append((r["ticker"], r["ratio"], r["median_pay"], c, round(imp)))
        time.sleep(0.1)
    except Exception as e:
        unchecked += 1; unverifiable_list.append(r['ticker'])
    if n % 40 == 0:
        print(f"  … {n} checked · {len(bad)} inconsistent", flush=True)
print(f"\nRE-AUDIT COMPLETE: checked {n}, {len(bad)} inconsistent, {unchecked} unverifiable")
for x in bad:
    print(f"  {x[0]}: stored ratio {x[1]}, median {x[2]}, CEO {x[3]} -> implied {x[4]}")
json.dump(bad, open("reaudit_bad.json", "w"), indent=1)
json.dump(unverifiable_list, open("reaudit_unverifiable.json", "w"), indent=1)
print("unverifiable tickers:", unverifiable_list)
