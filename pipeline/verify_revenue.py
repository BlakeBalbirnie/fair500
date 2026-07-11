#!/usr/bin/env python3
"""Independent revenue verification: for every site company, compare stored
revenue to the most inclusive total-revenue XBRL concept. A partial line item
(e.g. only contract revenue for a REIT, or one segment) stored as total revenue
understates revenue and inflates margin. Flags where stored revenue is
materially below the best total-revenue candidate.

Banks/insurers report revenue oddly (net interest income + noninterest income),
so a low stored value there may be legitimate — those are flagged for a human
look, not auto-fixed.

Writes data/revenue_flags.json. Run: python3 pipeline/verify_revenue.py
"""
import json, os, time, urllib.request
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
UA = "Fair500 research blakebalbirnie@gmail.com"

# most-inclusive first
REV_CONCEPTS = [
    "Revenues",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RegulatedAndUnregulatedOperatingRevenue",
]


def get(url):
    for a in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read())
        except Exception:
            if a == 1:
                return None
            time.sleep(0.5)


def dur(x):
    try:
        s = [int(v) for v in x["start"][:10].split("-")]
        e = [int(v) for v in x["end"][:10].split("-")]
        return (date(*e) - date(*s)).days
    except Exception:
        return 0


def annual(cik, tag):
    dd = get(f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json")
    if not dd:
        return {}
    by = {}
    for x in dd.get("units", {}).get("USD", []):
        if 330 <= dur(x) <= 400:
            y = int(x["end"][:4]); f = x.get("filed", "")
            if y not in by or f > by[y][0]:
                by[y] = (f, x["val"])
    return {y: v for y, (f, v) in by.items()}


def main():
    web = {r["t"] for r in json.load(open(os.path.join(DATA, "web_data.json")))}
    d = [r for r in json.load(open(os.path.join(DATA, "data.json"))) if r["ticker"] in web]
    flags = []
    for i, r in enumerate(d, 1):
        cik, yrs = r["cik"], r["years"]
        rev = r.get("revenue") or {}
        common = [y for y in yrs if str(y) in rev]
        if not common:
            continue
        stored_avg = sum(rev[str(y)] for y in common) / len(common)
        # best total-revenue candidate across concepts
        best = 0
        for c in REV_CONCEPTS:
            s = annual(cik, c)
            vals = [s[y] for y in common if y in s]
            if len(vals) == len(common):
                best = max(best, sum(vals) / len(vals))
        # flag when a materially larger total exists than what is stored
        if best and stored_avg and (best - stored_avg) / best > 0.10:
            flags.append({
                "ticker": r["ticker"], "name": r["name"],
                "stored_rev": round(stored_avg / 1e9, 3),
                "best_total": round(best / 1e9, 3),
                "margin": r.get("margin_3yr"),
            })
        if i % 40 == 0:
            print(f"  … {i}/{len(d)} · {len(flags)} flagged", flush=True)
        time.sleep(0.05)
    json.dump(flags, open(os.path.join(DATA, "revenue_flags.json"), "w"), indent=1)
    print(f"\nDONE. {len(flags)} companies where stored revenue looks partial:")
    for f in sorted(flags, key=lambda x: x["best_total"] - x["stored_rev"], reverse=True):
        print(f"  {f['ticker']:6} stored=${f['stored_rev']}B  best_total=${f['best_total']}B  margin={f['margin']}%")


if __name__ == "__main__":
    main()
