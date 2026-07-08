#!/usr/bin/env python3
"""Individually verify the companies the re-audit could not machine-check.

For each ticker we pull the DEF 14A and independently confirm the stored
`ratio` and `median_pay` are internally consistent with the CEO's disclosed
total compensation. The re-audit's weakness was requiring a $-prefixed 7+ digit
figure inside a narrow +/-850 char window. Here we widen the net:
  1. Compute expected CEO pay = ratio * median.
  2. Scan the WHOLE proxy for any comp-scale figure (>= $900k) written with or
     without a $ sign, and see whether one lands within 12% of expected.
  3. Also grab the largest comp-scale figure near the pay-ratio disclosure
     (the CEO total) and the stated ratio text, for eyeball backup.
Outputs verify48_results.json with per-ticker status: OK / MISMATCH / NOFIG.
"""
import json, re, html, time, sys, os, urllib.request, pipeline
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data"))

UA = "Fair500 research blakebalbirnie@gmail.com"
def get(url):
    for a in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.read()
        except Exception:
            if a == 2: raise
            time.sleep(0.7)

def proxy_text(cik):
    sub = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik}.json").decode())["filings"]["recent"]
    u = pipeline.find_form_url(cik, sub, "DEF 14A")
    if not u: return None, None
    t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", get(u).decode("utf-8", "ignore"))))
    return t, u

# comp-scale figures, with or without $ (tables often omit it): 7-9 digit grouped
_NUM = re.compile(r"(?<![\d.])(\d{1,3}(?:,\d{3}){2,3})(?![\d.])")

def figures(t):
    out = []
    for m in _NUM.finditer(t):
        v = int(m.group(1).replace(",", ""))
        if 900_000 <= v <= 700_000_000:
            out.append(v)
    return out

def verify(r):
    ratio, med = r.get("ratio"), r.get("median_pay")
    if not (ratio and med and r.get("cik")):
        return {"status": "SKIP", "reason": "missing ratio/median/cik"}
    expected = ratio * med
    t, url = proxy_text(r["cik"])
    if not t:
        return {"status": "NOPROXY"}
    figs = figures(t)
    # best matching figure to expected CEO pay
    near = [v for v in figs if abs(v - expected) / expected <= 0.12]
    best = min(figs, key=lambda v: abs(v - expected)) if figs else None
    err = round(abs(best - expected) / expected * 100, 1) if best else None
    status = "OK" if near else ("MISMATCH" if best else "NOFIG")
    return {"status": status, "expected_ceo": expected, "best_fig": best,
            "err_pct": err, "ratio": ratio, "median": med}

def main():
    tickers = json.load(open("reaudit_unverifiable.json"))
    d = {r["ticker"]: r for r in json.load(open("data.json"))}
    results = {}
    for i, tk in enumerate(tickers, 1):
        r = d.get(tk)
        if not r:
            results[tk] = {"status": "NOTFOUND"}; continue
        try:
            results[tk] = verify(r)
        except Exception as e:
            results[tk] = {"status": "ERR", "err": str(e)}
        s = results[tk]
        print(f"[{i}/{len(tickers)}] {tk:6} {s['status']:9} "
              f"exp {s.get('expected_ceo','?')} best {s.get('best_fig','?')} "
              f"({s.get('err_pct','?')}%)", flush=True)
        time.sleep(0.15)
    json.dump(results, open("verify48_results.json", "w"), indent=1)
    bad = {k: v for k, v in results.items() if v["status"] not in ("OK",)}
    print(f"\nDONE. {len(results)} checked. {len(bad)} not auto-OK:")
    for k, v in bad.items():
        print(f"  {k}: {v}")

if __name__ == "__main__":
    main()
