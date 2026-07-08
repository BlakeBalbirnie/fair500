#!/usr/bin/env python3
"""Comprehensive plausibility sweep over the whole dataset.

Every data error we have found produces an implausible RATIO between fields:
a client count stored as headcount makes revenue-per-employee absurdly low;
a partial revenue line makes margin exceed 100%; a contaminated median breaks
the arithmetic of ratio x median = CEO pay. This script recomputes those
relationships for every company and flags outliers, ranked by how many checks
they fail, so a human can review the short list instead of all 462 rows.

Pure offline checks on the stored data (no network) — fast. For the arithmetic
consistency check against the actual proxy, see audit.py / reaudit.py.

Run:  python3 pipeline/validate.py
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data", "data.json")


def avg_revenue(r):
    """3-yr avg revenue: prefer the stored revenue series over common years,
    else fall back to profit / margin."""
    rev, yrs = r.get("revenue"), r.get("years") or []
    if rev:
        common = [y for y in yrs if str(y) in rev]
        if common:
            return sum(rev[str(y)] for y in common) / len(common)
    ni, m = r.get("avg_net_income"), r.get("margin_3yr")
    if ni and m:
        return ni / (m / 100)
    return None


def checks(r):
    """Return a list of (severity, message) plausibility flags for one company."""
    out = []
    emp = r.get("employees")
    ni = r.get("avg_net_income")
    med = r.get("median_pay")
    ratio = r.get("ratio")
    m = r.get("margin_3yr")
    rev = avg_revenue(r)

    # --- headcount sanity via revenue- and profit-per-employee ---
    if emp and rev:
        rpe = rev / emp
        if rpe < 45_000:
            out.append(("HIGH", f"revenue/employee ${rpe:,.0f} — headcount likely too high ({emp:,})"))
        elif rpe > 25_000_000:
            out.append(("MED", f"revenue/employee ${rpe:,.0f} — headcount may be too low ({emp:,})"))
    if emp and ni and ni > 0:
        ppe = ni / emp
        if ppe < 1_500:
            out.append(("MED", f"profit/employee ${ppe:,.0f} — headcount may be too high"))
        elif ppe > 6_000_000:
            out.append(("MED", f"profit/employee ${ppe:,.0f} — headcount may be too low"))

    # --- margin sanity ---
    if m is not None:
        if m >= 100:
            out.append(("HIGH", f"margin {m}% — profit exceeds revenue (bad revenue tag?)"))
        elif m > 70:
            out.append(("MED", f"margin {m}% — unusually high, verify revenue"))

    # --- median worker pay sanity (human range) ---
    if med is not None:
        if med < 12_000:
            out.append(("HIGH", f"median pay ${med:,} — implausibly low"))
        elif med > 450_000:
            out.append(("HIGH", f"median pay ${med:,} — implausibly high"))

    # --- pay ratio sanity ---
    if ratio is not None:
        if ratio < 2:
            out.append(("LOW", f"pay ratio {ratio} — very low (founder/low-comp CEO?)"))
        elif ratio > 2000:
            out.append(("MED", f"pay ratio {ratio} — extreme, verify"))

    # --- implied CEO pay sanity ---
    if ratio and med:
        ceo = ratio * med
        if ceo > 120_000_000:
            out.append(("MED", f"implied CEO pay ${ceo/1e6:.0f}M — extreme, verify mega-grant"))

    # --- staleness ---
    yrs = r.get("years")
    if yrs and max(yrs) < 2024:
        out.append(("HIGH", f"stale financials — latest year {max(yrs)}"))

    # --- completeness: a plotted company missing a core field ---
    if ni and ni > 0:
        if not ratio and not med:
            pass  # partial rows are allowed (no fairness input) — handled by build_site
    return out


def main():
    data = json.load(open(DATA))
    rank = {"HIGH": 3, "MED": 2, "LOW": 1}
    flagged = []
    for r in data:
        fl = checks(r)
        if fl:
            score = sum(rank[s] for s, _ in fl)
            flagged.append((score, r["ticker"], r["name"], fl))
    flagged.sort(reverse=True)

    print(f"Validated {len(data)} companies · {len(flagged)} flagged (ranked by suspicion)\n")
    for score, tk, name, fl in flagged:
        print(f"[{score}] {tk:6} {name[:26]:26}")
        for sev, msg in fl:
            print(f"        {sev:4} {msg}")
    # machine-readable
    json.dump([{"ticker": tk, "name": nm, "score": sc,
                "flags": [{"sev": s, "msg": m} for s, m in fl]}
               for sc, tk, nm, fl in flagged],
              open(os.path.join(os.path.dirname(HERE), "data", "validation_flags.json"), "w"), indent=1)
    print(f"\nHIGH-severity flags: {sum(1 for _,_,_,fl in flagged if any(s=='HIGH' for s,_ in fl))}")


if __name__ == "__main__":
    main()
