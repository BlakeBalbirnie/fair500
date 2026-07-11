#!/usr/bin/env python3
"""Build the website's data from the master dataset.

Reads   data/data.json      (master: 500 S&P constituents, full fields)
Writes  data/web_data.json   (site set: short keys, filtered & scoreable)
Updates ../index.html        (re-inlines the `const DATA = [...]` blob)

Inclusion rule for the site (see fair500-data-audit memory):
  - 3-year average net income (profit) is present and > 0
  - has at least one fairness input: a CEO-to-median pay ratio OR a median
    worker pay figure (rows with only one are kept as "partial" and scored
    null-safe; e.g. Tesla, which discloses a median but no ratio)
  - excluded only when BOTH ratio and median are present AND estimated CEO pay
    (ratio x median) < $100,000 — below this the disclosed comp is a founder
    taking ~$0 salary and the figure misrepresents their real equity wealth

Run from anywhere:  python3 pipeline/build_site.py
"""
import json, os, re, html as _html

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA_DIR = os.path.join(ROOT, "data")
INDEX = os.path.join(ROOT, "index.html")
MIN_CEO_PAY = 100_000


def build_rows(master):
    rows = []
    for r in master:
        p = r.get("avg_net_income")
        ratio, med = r.get("ratio"), r.get("median_pay")
        if p is None:
            continue
        loss = p <= 0
        if loss:
            # loss-makers plot in the chart's "lost money" band; they can only be
            # scored on the CEO-pay gap (the value score needs positive profit), so
            # they must have BOTH a ratio (for the gap score) and a median (for the
            # bubble). Value/combined fall back to gap in the site JS.
            if not (ratio and med):
                continue
        elif not ratio and not med:          # profitable: need at least one input
            continue
        # founder rule: disclosed comp of a ~$0-salary founder misrepresents them
        if ratio and med and ratio * med < MIN_CEO_PAY:
            continue
        row = {
            "t": r["ticker"], "n": r["name"], "sec": r.get("sector"),
            "m": r.get("margin_3yr"), "r": ratio,
            "p": round(p / 1e9, 3 if loss else 2), "med": med, "emp": r.get("employees"),
            "cp": r.get("ceo_pay"),  # actual CEO total comp from proxy (null -> site estimates)
            "y": r.get("years"), "url": r.get("proxy_url"),
        }
        if loss:
            row["loss"] = 1
        rows.append(row)
    return rows


def main():
    master = json.load(open(os.path.join(DATA_DIR, "data.json")))
    rows = build_rows(master)
    json.dump(rows, open(os.path.join(DATA_DIR, "web_data.json"), "w"), indent=1)

    src = open(INDEX).read()

    # 1) inline the DATA blob
    blob = "const DATA = " + json.dumps(rows, separators=(",", ":")) + ";"
    src, n = re.subn(r"const DATA = \[.*?\];", lambda m: blob, src, count=1, flags=re.S)
    assert n == 1, f"expected exactly one DATA blob, found {n}"

    # 2) regenerate the crawlable A–Z company index between markers
    cos = sorted(rows, key=lambda r: r["t"])
    idx = "\n".join(f'<span><b>{_html.escape(r["t"])}</b> '
                    f'{_html.escape(r["n"])}</span>' for r in cos)
    src, n = re.subn(r"(<!--CO_INDEX_START-->).*?(<!--CO_INDEX_END-->)",
                     lambda m: m.group(1) + "\n" + idx + "\n" + m.group(2),
                     src, count=1, flags=re.S)
    assert n == 1, f"expected exactly one CO_INDEX marker pair, found {n}"

    # 3) keep the company counts in the copy in sync
    src = re.sub(r"For each of \d+ companies", f"For each of {len(rows)} companies", src)
    src = re.sub(r"All \d+ companies covered", f"All {len(rows)} companies covered", src)
    # FAQ coverage count (visible + JSON-LD): "maps N of the 500 companies"
    src = re.sub(r"maps \d+ of the 500 companies", f"maps {len(rows)} of the 500 companies", src)

    open(INDEX, "w").write(src)
    print(f"Built {len(rows)} site rows from {len(master)} master records; "
          f"re-inlined DATA, company index, and counts into {os.path.relpath(INDEX)}.")


if __name__ == "__main__":
    main()
