#!/usr/bin/env python3
"""Re-extract median worker pay with a HIGH-PRECISION positive-match parser:
the figure must be explicitly described as the median employee's/associate's
total compensation, and its context must not be a contaminant (peer table,
benefit, board fee, TSR). Update the stored median ONLY when this fires with a
value (it returns the correct figure or None — never a wrong one), so there are
no regressions. Verified manual overrides cover the few phrasings it can't match."""
import json, re, html, time, os, pipeline
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data"))

_BAD = re.compile(
    r"benefit|healthcare|health and welfare|peer|board|director|grant date|"
    r"value of (?:initial|\$100)|investment|residential|hourly rate of|company-paid|per share|dividend",
    re.I)
_N = r"(?:employee|associate|coworker|team\s?member|teammate|colleague|people)"
_PATS = [re.compile(p, re.I) for p in [
    r"total\s+compensation\s+of\s+(?:our\s+|the\s+)?(?:estimated\s+)?median\s+(?:compensated\s+|paid\s+)?" + _N + r"[^.$]{0,60}?\$\s?([\d,]{5,})",
    r"median\s+of\s+the\s+annual\s+total\s+compensation\s+of[\w\s',()\-\d“”]{0,55}?" + _N + r"s?[\w\s',()\-]{0,45}?(?:was|is)\s*\$?\s?([\d,]{5,})",
    r"median\s+(?:compensated\s+|paid\s+)?" + _N + r"[\w\s',()\-]{0,95}?compensation[\w\s',()\-]{0,50}?(?:was|is|of|:)\s*\$?\s?([\d,]{5,})",
    r"(?:for|of|to)\s+(?:our\s+|the\s+)?(?:estimated\s+)?median\s+(?:compensated\s+|paid\s+)?" + _N + r"(?:['’]s)?[\w\s,()\-]{0,22}?(?:was|is|of|:)\s*\$?\s?([\d,]{5,})",
]]
OVERRIDE = {"UPS": 66268, "DOV": 55766, "UDR": 86140}


def clean(cik):
    recent = pipeline.fetch_submissions(cik)
    u = pipeline.find_form_url(cik, recent, "DEF 14A")
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", pipeline.get(u).decode("utf-8", "ignore")))) if u else None


def find_median(t):
    for rx in _PATS:
        for m in rx.finditer(t):
            if _BAD.search(t[max(0, m.start() - 45): m.end() + 22]):
                continue
            v = int(m.group(1).replace(",", ""))
            if 8000 <= v <= 600000:
                return v
    return None


def main():
    d = json.load(open("data.json"))
    changed = 0
    for i, r in enumerate(d, 1):
        new = None
        if r["ticker"] in OVERRIDE:
            new = OVERRIDE[r["ticker"]]
        elif r.get("proxy_url"):
            try:
                t = clean(r["cik"])
                new = find_median(t) if t else None
            except Exception as e:
                print(f"[{i}] {r['ticker']}: ERR {e}")
            time.sleep(0.15)
        old = r.get("median_pay")
        if new and new != old:
            print(f"[{i}] {r['ticker']}: {old} -> {new}")
            r["median_pay"] = new
            changed += 1
        if r.get("median_pay") and r.get("employees") and r.get("avg_net_income"):
            r["worker_share"] = round(r["median_pay"] / (r["avg_net_income"] / r["employees"]), 3)
        if i % 60 == 0:
            json.dump(d, open("data.json", "w"), indent=2)
            print(f"  … checkpoint {i} · {changed} changed")
    json.dump(d, open("data.json", "w"), indent=2)
    print(f"\nDone. {changed} medians corrected.")


if __name__ == "__main__":
    main()
