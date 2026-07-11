#!/usr/bin/env python3
"""Independent net-income verification: for every site company, pull the main
US-GAAP net-income concepts and flag where the stored profit may use the wrong
one. `ProfitLoss` includes amounts attributable to noncontrolling interests;
`NetIncomeLoss` is (usually) attributable to the parent; asset managers with
consolidated funds and companies with preferred stock diverge between these.
Where the concepts diverge and the stored value tracks the NCI-inclusive figure,
the profit (and thus the fairness score) is wrong.

Writes data/netincome_flags.json. Run: python3 pipeline/verify_netincome.py
"""
import json, os, time, urllib.request
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
UA = "Fair500 research blakebalbirnie@gmail.com"


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
        nil = annual(cik, "NetIncomeLoss")
        pl = annual(cik, "ProfitLoss")
        parent = annual(cik, "NetIncomeLossAttributableToParent")
        stored = r["avg_net_income"]

        def avg(series):
            vals = [series[y] for y in yrs if y in series]
            return sum(vals) / len(vals) if len(vals) == len(yrs) else None

        a_nil, a_pl, a_par = avg(nil), avg(pl), avg(parent)
        # the "best" = attributable to parent if present, else NetIncomeLoss
        best = a_par if a_par is not None else a_nil
        # flag when concepts materially diverge AND stored differs from 'best'
        cands = [x for x in (a_nil, a_pl, a_par) if x is not None]
        diverge = cands and (max(cands) - min(cands)) / (abs(max(cands, key=abs)) or 1) > 0.10
        wrong = best is not None and abs(stored - best) / (abs(best) or 1) > 0.05
        if diverge and wrong:
            flags.append({
                "ticker": r["ticker"], "name": r["name"], "years": yrs,
                "stored_avg": round(stored / 1e9, 3),
                "NetIncomeLoss": round(a_nil / 1e9, 3) if a_nil is not None else None,
                "ProfitLoss": round(a_pl / 1e9, 3) if a_pl is not None else None,
                "AttribToParent": round(a_par / 1e9, 3) if a_par is not None else None,
            })
        if i % 40 == 0:
            print(f"  … {i}/{len(d)} · {len(flags)} flagged", flush=True)
        time.sleep(0.05)
    json.dump(flags, open(os.path.join(DATA, "netincome_flags.json"), "w"), indent=1)
    print(f"\nDONE. {len(flags)} companies where stored profit may use the wrong net-income concept:")
    for f in flags:
        print(f"  {f['ticker']:6} stored={f['stored_avg']}  NIL={f['NetIncomeLoss']}  "
              f"PL={f['ProfitLoss']}  parent={f['AttribToParent']}")


if __name__ == "__main__":
    main()
