#!/usr/bin/env python3
"""Stage 1 of LLM-based verification: fetch each company's filings and isolate
the RELEVANT sections, so an LLM can read them and extract the fields in context
(the step regex gets wrong). Locating a section is reliable; understanding the
numbers inside it is what we hand to the LLM.

For each ticker it writes, to data/llm_excerpts.txt:
  - the CEO Pay Ratio disclosure from the DEF 14A (median pay, ratio, CEO comp)
  - the employee-count / human-capital passage from the 10-K
  - the currently stored values, for side-by-side comparison

Run:  python3 pipeline/llm_excerpts.py
"""
import json, re, html, time, os, urllib.request
import pipeline

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
UA = "Fair500 research blakebalbirnie@gmail.com"

SAMPLE = ["PAYX", "ADP", "ELV", "FITB", "URI", "LITE",      # controls we just fixed/verified
          "JPM", "BAC", "WFC",                                # banks
          "AMT", "O", "PLD",                                  # REITs
          "MET", "PGR",                                       # insurers
          "WMT", "COST", "MCD",                               # retail (low medians)
          "AAPL", "MSFT", "NVDA", "AVGO",                     # tech / mega-grant
          "CAT", "GE", "TXN", "KO"]                           # industrials / staples


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read()


def clean(url):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", get(url).decode("utf-8", "ignore"))))


def forms(cik):
    sub = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik}.json").decode())["filings"]["recent"]
    return sub


def pay_ratio_excerpt(t):
    """~900 chars around the CEO pay ratio disclosure."""
    for pat in [r"CEO\s+Pay\s+Ratio", r"Pay\s+Ratio\s+Disclosure", r"Ratio of[^.]{0,30}Median",
                r"pay\s+ratio", r"median\s+(?:employee|associate)[^.]{0,40}(?:total\s+)?(?:annual\s+)?compensation"]:
        m = re.search(pat, t, re.I)
        if m:
            return t[max(0, m.start() - 120): m.start() + 900]
    return None


def headcount_excerpt(t):
    """passage around the human-capital / employee-count statement."""
    for pat in [r"Human\s+Capital", r"(?:As of[^.]{0,40})?(?:we\s+)?employ(?:ed)?\s+approximately",
                r"our\s+(?:total\s+)?workforce", r"our\s+employee\s+population", r"team\s+of\s+associates"]:
        m = re.search(pat, t, re.I)
        if m:
            return t[max(0, m.start() - 60): m.start() + 600]
    return None


def main():
    d = {r["ticker"]: r for r in json.load(open(os.path.join(DATA, "data.json")))}
    out = []
    for tk in SAMPLE:
        r = d.get(tk)
        if not r:
            out.append(f"\n{'='*100}\n{tk}: NOT IN DATASET\n"); continue
        cik = r["cik"]
        try:
            sub = forms(cik)
            proxy_u = r.get("proxy_url") or pipeline.find_form_url(cik, sub, "DEF 14A")
            tenk_u = pipeline.find_form_url(cik, sub, "10-K")
            pr = pay_ratio_excerpt(clean(proxy_u)) if proxy_u else None
            hc = headcount_excerpt(clean(tenk_u)) if tenk_u else None
        except Exception as e:
            out.append(f"\n{'='*100}\n{tk}: FETCH ERROR {e}\n"); continue
        out.append(f"\n{'='*100}\n{tk}  ({r['name']})")
        out.append(f"STORED: median_pay=${r.get('median_pay')}, ratio={r.get('ratio')}, "
                    f"employees={r.get('employees')}, implied_CEO=${(r.get('ratio') or 0)*(r.get('median_pay') or 0):,}")
        out.append(f"PROXY  {proxy_u}")
        out.append(f"  PAY-RATIO EXCERPT: {pr.strip() if pr else '[not located]'}")
        out.append(f"10-K   {tenk_u}")
        out.append(f"  HEADCOUNT EXCERPT: {hc.strip() if hc else '[not located]'}")
        time.sleep(0.2)
    path = os.path.join(DATA, "llm_excerpts.txt")
    open(path, "w").write("\n".join(out))
    print(f"Wrote {len(SAMPLE)} companies' excerpts to {os.path.relpath(path)}")


if __name__ == "__main__":
    main()
