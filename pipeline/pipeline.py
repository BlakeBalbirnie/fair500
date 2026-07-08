#!/usr/bin/env python3
"""
Fair500 data pipeline.

For every company in sp500.json (ticker, name, sector, CIK — from the Wikipedia
S&P 500 constituent list), pull from SEC EDGAR:
  - Revenue + net income for the last 3 fiscal years (XBRL companyconcept API)
  - CEO-to-median-worker pay ratio + median worker pay (latest DEF 14A proxy)
  - Employee headcount (latest 10-K)

and derive net margin, avg profit, profit-per-employee, and worker's-share.
Writes data.json for the front-end.

Robustness for the 500-company run: retries on transient errors, checkpoints
every CHECKPOINT_EVERY companies, and resumes (skips already-complete records)
if restarted. Each record carries "complete": False when any field is missing —
that is the manual-review queue.

Politeness: SEC asks for a descriptive User-Agent and <=10 req/s. We stay well under.
"""

import json
import re
import html
import time
import urllib.request
from pathlib import Path

UA = "Fair500 research blakebalbirnie@gmail.com"
HERE = Path(__file__).parent
OUT = HERE / "data.json"
CONSTITUENTS = HERE / "sp500.json"     # [{ticker, name, sector, cik}] from Wikipedia
CHECKPOINT_EVERY = 20                   # flush partial data.json this often
TENK_MAX_BYTES = 6_000_000             # Human Capital lives early in Item 1; cap the (often huge) 10-K read

REVENUE_TAGS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
    "RevenuesNetOfInterestExpense",   # banks/broker-dealers report total net revenues here
]
NET_INCOME_TAGS = ["NetIncomeLoss", "ProfitLoss"]


def get(url, maxbytes=None, tries=3):
    """Fetch bytes with retry/backoff. maxbytes caps the read (for giant 10-Ks)."""
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read(maxbytes) if maxbytes else r.read()
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(1.5 * (attempt + 1))


def get_json(url):
    return json.loads(get(url))


def load_constituents():
    return json.loads(CONSTITUENTS.read_text())


def fetch_submissions(cik):
    """Recent-filings block; fetched once per company and reused for proxy + 10-K."""
    return get_json(f"https://data.sec.gov/submissions/CIK{cik}.json")["filings"]["recent"]


def find_form_url(cik, recent, form):
    for f, acc, doc in zip(recent["form"], recent["accessionNumber"], recent["primaryDocument"]):
        if f == form:
            return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{doc}"
    return None


def _duration_days(x):
    try:
        from datetime import date
        return (date.fromisoformat(x["end"]) - date.fromisoformat(x["start"])).days
    except Exception:
        return 0


def annual_series(cik, tags):
    """Return {fiscal_year: value} of 10-K FULL-YEAR figures.

    We do NOT rely on the XBRL 'frame' field (sparse, biased to old periods, drops
    recent years). Instead take every 10-K annual (fp='FY') fact spanning ~a full
    year, keyed by fiscal-year-end year, keeping the most recently filed value.
    Tags are merged since companies switch revenue tags across eras.
    """
    by_year = {}   # year -> (filed_date, value)
    for tag in tags:
        url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json"
        try:
            d = get_json(url)
        except Exception:
            continue
        for x in d.get("units", {}).get("USD", []):
            if x.get("form") not in ("10-K", "10-K/A") or x.get("fp") != "FY":
                continue
            if not (330 <= _duration_days(x) <= 400):
                continue
            year = int(x["end"][:4])
            filed = x.get("filed", "")
            if year not in by_year or filed > by_year[year][0]:
                by_year[year] = (filed, x["val"])
    return {y: v for y, (f, v) in by_year.items()}


# Only treat "N to 1" as the pay ratio if the context is clearly the pay-ratio
# disclosure. Gate keeps us off stock splits, vote thresholds, "1 to 1 match".
_GATE = re.compile(r"median|pay ratio|ratio of (?:these|the)", re.I)
# The (?<![\d.]) lookbehind stops us grabbing a digit that follows a decimal
# point: "158.2 to 1" must read as 158.2, not "2 to 1". Decimals are allowed.
_RATIO = re.compile(
    r"(?:(?<![\d.])(\d[\d,]{0,7}(?:\.\d+)?)\s*(?:to|:|-to-)\s*1\b)"   # 533:1 / 158.2 to 1
    r"|(?:(?<![\d.])\b1\s*(?:to|-to-)\s*(\d[\d,]{0,7}(?:\.\d+)?)\b)"  # 1-to-51 (reversed)
)
# "166 times" phrasing (Boeing/Colgate): weaker, so we require 'median' close by.
_TIMES = re.compile(r"(\d[\d,]{1,7})\s*times\b", re.I)
# median worker pay — the figure can sit on either side of the word 'median'
# ("median employee ... $30,520" or "$177,115 for our median employee").
_MEDIAN = re.compile(r"median[^.$]{0,220}?\$\s?([\d,]{4,})", re.I)
_MEDIAN_R = re.compile(r"\$\s?([\d,]{4,})[^.$]{0,80}?median", re.I)


def _find_median(text):
    # Near the ratio there are two comp figures: the CEO's (larger) and the
    # median worker's (smaller). Median pay is always the smaller — so when both
    # land in range (e.g. Berkshire, whose CEO pay is unusually low), take the min.
    vals = []
    for rx in (_MEDIAN, _MEDIAN_R):
        for mm in rx.finditer(text):
            v = int(mm.group(1).replace(",", ""))
            if 8_000 <= v <= 500_000:
                vals.append(v)
    return min(vals) if vals else None


def extract_pay_ratio(proxy_url):
    txt = re.sub(r"<[^>]+>", " ", get(proxy_url).decode("utf-8", errors="ignore"))
    txt = re.sub(r"\s+", " ", html.unescape(txt))
    result = {"ratio": None, "median_pay": None, "confidence": "none"}
    ratio_pos = None

    # Strong: "N to 1 / N:1 / 1-to-N" inside the pay-ratio disclosure context.
    for m in _RATIO.finditer(txt):
        if _GATE.search(txt[max(0, m.start() - 280): m.end() + 40]):
            val = float((m.group(1) or m.group(2)).replace(",", ""))
            # reject year-like integers (e.g. "...in 2025: 1. Executive Summary")
            if val == int(val) and 1990 <= val <= 2035:
                continue
            if 1.5 <= val <= 15000:
                result["ratio"] = int(round(val)); ratio_pos = m.start(); break
    # Weaker: "N times [the median]" — require 'median' very close to avoid
    # "3 times base salary" and similar unrelated multiples.
    if result["ratio"] is None:
        for m in _TIMES.finditer(txt):
            ctx = txt[max(0, m.start() - 60): m.end() + 110].lower()
            if any(k in ctx for k in ("median employee", "median worker", "median associate",
                                      "median of the annual", "median paid")):
                val = float(m.group(1).replace(",", ""))
                if 1.5 <= val <= 15000:
                    result["ratio"] = int(round(val)); ratio_pos = m.start(); break
    if result["ratio"] is not None:
        result["confidence"] = "high"

    # Median worker pay sits in the SAME sentence as the ratio — search there first
    # (avoids the many peer-group "median" mentions elsewhere), then fall back.
    if ratio_pos is not None:
        result["median_pay"] = _find_median(txt[max(0, ratio_pos - 600): ratio_pos + 600])
    if result["median_pay"] is None:
        result["median_pay"] = _find_median(txt)
    return result


# Employee headcount from the 10-K: a number, optional million/thousand, up to 3
# filler words, then a workforce noun. Gated to the Human Capital section, and we
# reject numbers preceded by share/award/IRS boilerplate.
_HEAD = re.compile(
    r"([\d][\d,\.]{2,})\s*(million|thousand)?(?:\s+[\w\-\(\)]+){0,3}?\s+"
    r"(?:employees|associates|team members|people)\b", re.I)
_HEAD_BAD = re.compile(r"i\.?r\.?s|identification|shares|per share|stock|award|\$", re.I)

# Verified manual overrides for genuine parsing stragglers (odd phrasing / no
# Human Capital heading). This is the review queue at work.
_HEAD_OVERRIDE = {"XOM": 57_900, "KO": 65_900}


def extract_headcount(tenk_url, ticker=None):
    if ticker in _HEAD_OVERRIDE:
        return _HEAD_OVERRIDE[ticker]
    if not tenk_url:
        return None
    txt = re.sub(r"<[^>]+>", " ", get(tenk_url, maxbytes=TENK_MAX_BYTES).decode("utf-8", errors="ignore"))
    txt = re.sub(r"\s+", " ", html.unescape(txt))
    hc = txt.lower().find("human capital")
    pools = [txt[hc:hc + 6000], txt] if hc >= 0 else [txt]
    for pool in pools:
        for m in _HEAD.finditer(pool):
            if _HEAD_BAD.search(pool[max(0, m.start() - 12):m.start()]):
                continue
            num = float(m.group(1).replace(",", ""))
            if m.group(2):
                num *= 1_000_000 if m.group(2).lower() == "million" else 1_000
            if 500 <= num <= 3_000_000:
                return int(num)
    return None


def is_complete(rec):
    return bool(rec.get("margin_3yr") is not None and rec.get("ratio")
                and rec.get("median_pay") and rec.get("employees"))


def process(c):
    """Build one company's record."""
    cik, t = c["cik"], c["ticker"]
    rec = {"ticker": t, "name": c["name"], "sector": c["sector"], "cik": cik}
    rev = annual_series(cik, REVENUE_TAGS)
    ni = annual_series(cik, NET_INCOME_TAGS)
    years = sorted(set(rev) & set(ni))[-3:]
    rec["years"] = years
    rec["revenue"] = {y: rev[y] for y in years}
    rec["net_income"] = {y: ni[y] for y in years}
    if years:
        tot_rev = sum(rev[y] for y in years)
        tot_ni = sum(ni[y] for y in years)
        rec["margin_3yr"] = round(tot_ni / tot_rev * 100, 2) if tot_rev else None
        rec["avg_net_income"] = round(tot_ni / len(years))
    time.sleep(0.15)
    recent = fetch_submissions(cik)
    proxy = find_form_url(cik, recent, "DEF 14A")
    if proxy:
        rec.update(extract_pay_ratio(proxy))
        rec["proxy_url"] = proxy
    else:
        rec["confidence"] = "no proxy"
    time.sleep(0.15)
    rec["employees"] = extract_headcount(find_form_url(cik, recent, "10-K"), t)
    if rec.get("employees") and rec.get("avg_net_income"):
        ppe = rec["avg_net_income"] / rec["employees"]
        rec["profit_per_employee"] = round(ppe)
        if rec.get("median_pay"):
            rec["worker_share"] = round(rec["median_pay"] / ppe, 3)
    rec["complete"] = is_complete(rec)
    return rec


def main():
    companies = load_constituents()
    done = {}
    if OUT.exists():                       # resume: reuse already-complete records
        try:
            for r in json.loads(OUT.read_text()):
                done[r.get("cik")] = r
        except Exception:
            pass

    out, n = [], len(companies)
    for i, c in enumerate(companies, 1):
        prev = done.get(c["cik"])
        if prev and is_complete(prev):
            prev["complete"] = True
            out.append(prev)
            continue
        try:
            rec = process(c)
            flag = "OK" if rec["complete"] else "PARTIAL"
            print(f"[{i}/{n}] {c['ticker']}: margin {rec.get('margin_3yr')}%  ratio {rec.get('ratio')}  "
                  f"med ${rec.get('median_pay')}  emp {rec.get('employees')}  {flag}")
        except Exception as e:
            rec = {"ticker": c["ticker"], "name": c["name"], "sector": c["sector"],
                   "cik": c["cik"], "error": str(e), "complete": False}
            print(f"[{i}/{n}] {c['ticker']}: ERROR {e}")
        out.append(rec)
        if i % CHECKPOINT_EVERY == 0:
            OUT.write_text(json.dumps(out, indent=2))
            ok = sum(1 for r in out if r.get("complete"))
            print(f"  … checkpoint {i}/{n} saved · {ok} complete so far")
        time.sleep(0.2)

    OUT.write_text(json.dumps(out, indent=2))
    ok = sum(1 for r in out if r.get("complete"))
    print(f"\nWrote {OUT}. Complete: {ok}/{n}  ·  needs review: {n - ok}")


if __name__ == "__main__":
    main()
