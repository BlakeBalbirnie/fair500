#!/usr/bin/env python3
"""Full LLM-verification pass, stage 1: for every company on the site, fetch the
ACTUAL CEO pay-ratio disclosure (median $, ratio, CEO total comp) and the
headcount statement, and write them in batches for an LLM to read and check.

Improvement over the prototype: anchors on the real disclosure (the ratio
statement that sits near a dollar median), not the table-of-contents entry.

Writes data/verify_batches/batch_XX.txt  (BATCH_SIZE companies each).
Run:  python3 pipeline/verify_generate.py
"""
import json, re, html, time, os, urllib.request
import pipeline

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
OUTDIR = os.path.join(DATA, "verify_batches")
UA = "Fair500 research blakebalbirnie@gmail.com"
BATCH_SIZE = 42


def get(url):
    for a in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception:
            if a == 1:
                raise
            time.sleep(0.6)


def clean(url):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", get(url).decode("utf-8", "ignore"))))


def ratio_window(t):
    """~900 chars around the actual pay-ratio disclosure (reuses the audit anchors)."""
    pos = None
    for m in pipeline._RATIO.finditer(t):
        if pipeline._GATE.search(t[max(0, m.start() - 280): m.end() + 40]):
            pos = m.start(); break
    if pos is None:
        for m in pipeline._TIMES.finditer(t):
            if "median" in t[max(0, m.start() - 60): m.end() + 110].lower():
                pos = m.start(); break
    if pos is None:
        m = re.search(r"median[- ]?(?:compensated |paid )?(?:employee|associate|of the annual)", t, re.I)
        pos = m.start() if m else None
    return t[max(0, pos - 700): pos + 700] if pos is not None else None


def head_window(t):
    for pat in [r"(?:we|the company|the bancorp|our (?:global )?(?:employee population|workforce|team))"
                r"[^.]{0,60}?(?:had|employed|was|consisted of|comprised|of)[^.]{0,40}?"
                r"(?:approximately |about )?[\d,]{3,}\s*(?:full-time |global )?"
                r"(?:employees|associates|people|individuals|persons|teammates|colleagues|partners)",
                r"(?:approximately |about )[\d,]{3,}\s*(?:full-time )?(?:employees|associates|people|colleagues|partners)",
                r"[Tt]otal (?:[Ee]mployees|[Ww]orkforce)\s+[\d,]{3,}"]:
        m = re.search(pat, t, re.I)
        if m:
            return t[max(0, m.start() - 60): m.start() + 320]
    return None


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    d = {r["ticker"]: r for r in json.load(open(os.path.join(DATA, "data.json")))}
    web = json.load(open(os.path.join(DATA, "web_data.json")))
    tickers = [r["t"] for r in web]

    batch, bn = [], 0
    done = 0
    for tk in tickers:
        r = d[tk]
        try:
            proxy = clean(r["proxy_url"]) if r.get("proxy_url") else ""
            rw = ratio_window(proxy) if proxy else None
            sub = json.loads(get(f"https://data.sec.gov/submissions/CIK{r['cik']}.json").decode())["filings"]["recent"]
            tenk = pipeline.find_form_url(r["cik"], sub, "10-K")
            hw = head_window(clean(tenk)) if tenk else None
        except Exception as e:
            rw, hw = f"[FETCH ERROR {e}]", None
        block = (f"TICKER: {tk}  ({r['name']})\n"
                 f"STORED -> median_pay: {r.get('median_pay')} | pay_ratio: {r.get('ratio')} | "
                 f"employees: {r.get('employees')} | implied_CEO_pay(ratio*median): "
                 f"{(r.get('ratio') or 0)*(r.get('median_pay') or 0)}\n"
                 f"PROXY_PAY_RATIO_TEXT: {rw or '[not located]'}\n"
                 f"TENK_HEADCOUNT_TEXT: {hw or '[not located]'}\n"
                 + "-" * 88)
        batch.append(block)
        done += 1
        if len(batch) == BATCH_SIZE:
            open(os.path.join(OUTDIR, f"batch_{bn:02d}.txt"), "w").write("\n".join(batch))
            bn += 1; batch = []
        if done % 20 == 0:
            print(f"  … {done}/{len(tickers)} fetched", flush=True)
        time.sleep(0.12)
    if batch:
        open(os.path.join(OUTDIR, f"batch_{bn:02d}.txt"), "w").write("\n".join(batch))
        bn += 1
    print(f"Done. {done} companies across {bn} batch files in {os.path.relpath(OUTDIR)}")


if __name__ == "__main__":
    main()
