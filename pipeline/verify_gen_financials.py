#!/usr/bin/env python3
"""Full LLM financial verification, stage 1: for every site company, assemble
the stored net income / revenue / margin, the candidate XBRL concept values,
and the actual income-statement text excerpt — so an LLM can read the statement,
pick the correct total revenue and net income ATTRIBUTABLE TO THE PARENT, and
compare to stored.

Writes data/fin_batches/batch_XX.txt (BATCH_SIZE companies each).
Run: python3 pipeline/verify_gen_financials.py
"""
import json, re, html, os, time, urllib.request
from datetime import date
import pipeline

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
OUTDIR = os.path.join(DATA, "fin_batches")
UA = "Fair500 research blakebalbirnie@gmail.com"
BATCH_SIZE = 42

NI_CONCEPTS = ["NetIncomeLoss", "ProfitLoss", "NetIncomeLossAttributableToParent",
               "NetIncomeLossAvailableToCommonStockholdersBasic"]
REV_CONCEPTS = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax",
                "InterestAndDividendIncomeOperating", "InterestIncomeExpenseNet",
                "NoninterestIncome", "RegulatedAndUnregulatedOperatingRevenue"]


def get(url):
    for a in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.read()
        except Exception:
            if a == 1:
                return None
            time.sleep(0.5)


def getj(url):
    b = get(url)
    return json.loads(b) if b else None


def clean(b):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", b.decode("utf-8", "ignore"))))


def dur(x):
    try:
        s = [int(v) for v in x["start"][:10].split("-")]
        e = [int(v) for v in x["end"][:10].split("-")]
        return (date(*e) - date(*s)).days
    except Exception:
        return 0


def annual(cik, tag, yrs):
    dd = getj(f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json")
    if not dd:
        return {}
    by = {}
    for x in dd.get("units", {}).get("USD", []):
        if 330 <= dur(x) <= 400:
            y = int(x["end"][:4]); f = x.get("filed", "")
            if y in yrs and (y not in by or f > by[y][0]):
                by[y] = (f, x["val"])
    return {y: round(v / 1e6) for y, (f, v) in by.items()}


def income_stmt(t, yrs):
    y = [str(x) for x in sorted(yrs, reverse=True)]
    yhdr = re.compile(r"\b" + y[0] + r"\b[\s,and]{0,8}" + y[1] + r"\b[\s,and]{0,8}" + y[2] + r"\b")
    revkw = re.compile(r"revenue|net sales|net operating revenue|premiums|interest income|total sales", re.I)
    anc = re.compile(r"CONSOLIDATED STATEMENTS? OF (?:OPERATIONS|INCOME|EARNINGS)"
                     r"|Consolidated Statements? of (?:Operations|Income|Earnings)")
    footnote = re.compile(r"^\s*(related to|within|ventures|as described|in Note|equal to|and (?:is|within)|reflect)", re.I)
    best, bestscore = None, -1
    for m in anc.finditer(t):
        head = t[m.end():m.end() + 400]
        if footnote.match(head):  # skip references/footnotes, not the actual statement
            continue
        score = 0
        if re.search(r"millions|thousands", head, re.I): score += 2
        if yhdr.search(head): score += 2
        rm = revkw.search(head)
        if rm and re.search(r"\$?\s?[\d,]{3,}", head[rm.start():rm.start() + 60]): score += 3
        if score > bestscore:
            bestscore, best = score, t[m.start():m.start() + 3200]
    return best if bestscore >= 4 else "[income statement not cleanly located]"


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    web = {r["t"] for r in json.load(open(os.path.join(DATA, "web_data.json")))}
    d = [r for r in json.load(open(os.path.join(DATA, "data.json"))) if r["ticker"] in web]
    batch, bn, done = [], 0, 0
    for r in d:
        cik, yrs = r["cik"], set(r["years"])
        try:
            ni = {c: annual(cik, c, yrs) for c in NI_CONCEPTS}
            rev = {c: annual(cik, c, yrs) for c in REV_CONCEPTS}
            sub = getj(f"https://data.sec.gov/submissions/CIK{cik}.json")["filings"]["recent"]
            u = pipeline.find_form_url(cik, sub, "10-K")
            stmt = income_stmt(clean(get(u)), r["years"]) if u else "[no 10-K]"
        except Exception as e:
            ni, rev, stmt = {}, {}, f"[ERROR {e}]"
        ni = {k: v for k, v in ni.items() if v}
        rev = {k: v for k, v in rev.items() if v}
        block = (f"TICKER: {r['ticker']}  ({r['name']}) | fiscal years {r['years']} | ($ in millions)\n"
                 f"STORED: net_income={ {k: round(v/1e6) for k,v in (r.get('net_income') or {}).items()} } "
                 f"avg={round(r['avg_net_income']/1e6)} | revenue={ {k: round(v/1e6) for k,v in (r.get('revenue') or {}).items()} } "
                 f"| margin={r.get('margin_3yr')}%\n"
                 f"XBRL net-income concepts: {ni}\n"
                 f"XBRL revenue concepts: {rev}\n"
                 f"INCOME_STATEMENT: {stmt}\n" + "-" * 90)
        batch.append(block); done += 1
        if len(batch) == BATCH_SIZE:
            open(os.path.join(OUTDIR, f"batch_{bn:02d}.txt"), "w").write("\n".join(batch)); bn += 1; batch = []
        if done % 20 == 0:
            print(f"  … {done}/{len(d)}", flush=True)
        time.sleep(0.05)
    if batch:
        open(os.path.join(OUTDIR, f"batch_{bn:02d}.txt"), "w").write("\n".join(batch)); bn += 1
    print(f"Done. {done} companies across {bn} batches in {os.path.relpath(OUTDIR)}")


if __name__ == "__main__":
    main()
