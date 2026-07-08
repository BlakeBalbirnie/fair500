#!/usr/bin/env python3
"""Comprehensive data audit. The proxy states CEO pay, median pay, and the ratio,
and by definition ratio = CEO_pay / median_pay. We independently pull the CEO's
pay from the disclosure and check ratio x median ~= CEO_pay for every company;
any contaminated median or wrong ratio fails the arithmetic. Also flags implausible
headcount (via profit/employee) and stale financials. Flagged records get their
pay-ratio snippet dumped so the exact figures can be read and corrected."""
import json, re, html, time, os, pipeline
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data"))

d = json.load(open("data.json"))


def clean(cik):
    recent = pipeline.fetch_submissions(cik)
    u = pipeline.find_form_url(cik, recent, "DEF 14A")
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", pipeline.get(u).decode("utf-8", "ignore")))) if u else None


def ratio_window(t):
    pos = None
    for m in pipeline._RATIO.finditer(t):
        if pipeline._GATE.search(t[max(0, m.start() - 280): m.end() + 40]):
            pos = m.start(); break
    if pos is None:
        for m in pipeline._TIMES.finditer(t):
            if "median" in t[max(0, m.start() - 60): m.end() + 110].lower():
                pos = m.start(); break
    if pos is None:   # fallback: anchor on the median-employee phrase itself
        m = re.search(r"median[- ]?(?:compensated |paid )?(?:employee|associate|of the annual)", t, re.I)
        pos = m.start() if m else None
    return (t[max(0, pos - 850): pos + 850], pos) if pos is not None else (None, None)


def ceo_pay(win):
    """Largest dollar figure in the pay-ratio window (the CEO's total comp)."""
    vals = [int(x.replace(",", "")) for x in re.findall(r"\$\s?([\d,]{7,})", win)]
    vals = [v for v in vals if 900_000 <= v <= 600_000_000]
    return max(vals) if vals else None


flags = []
for i, r in enumerate(d, 1):
    tk = r["ticker"]
    issues = []
    # financials recency
    if r.get("years") and max(r["years"]) < 2024:
        issues.append(f"stale years {r['years']}")
    # headcount plausibility via profit/employee
    if r.get("employees") and r.get("avg_net_income"):
        ppe = r["avg_net_income"] / r["employees"]
        if ppe > 6_000_000 or ppe < 1_500:
            issues.append(f"ppe ${ppe:,.0f} (headcount {r['employees']:,}?)")
    # ratio x median vs CEO pay (the core check) — needs proxy
    snippet = ""
    if r.get("ratio") and r.get("median_pay") and r.get("proxy_url"):
        try:
            t = clean(r["cik"])
            win, _ = ratio_window(t) if t else (None, None)
            c = ceo_pay(win) if win else None
            if c:
                implied = c / r["median_pay"]
                if abs(implied - r["ratio"]) / r["ratio"] > 0.15:
                    issues.append(f"ratio {r['ratio']} but CEO ${c:,}/median ${r['median_pay']:,} = {implied:.0f}")
                    snippet = win[:600]
            time.sleep(0.12)
        except Exception as e:
            issues.append(f"ERR {e}")
    if issues:
        flags.append({"ticker": tk, "name": r["name"], "median": r.get("median_pay"),
                      "ratio": r.get("ratio"), "issues": issues, "snippet": snippet})
    if i % 60 == 0:
        print(f"  … audited {i}/{len(d)} · {len(flags)} flagged")

json.dump(flags, open("audit_flags.json", "w"), indent=1)
print(f"\nDone. {len(flags)} records flagged (of {len(d)}). See audit_flags.json")
for f in flags:
    print(f"  {f['ticker']:6} {' | '.join(f['issues'])[:110]}")
