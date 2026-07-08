#!/usr/bin/env python3
"""Re-extract employee counts for companies whose stored headcount is wrong
(mostly a filing YEAR mis-parsed as the count). Pulls each 10-K's human-capital
section and surfaces the total employee-count statement WITH the sentence it
came from, so each number is verifiable before it is applied.

Prints candidates; writes nothing. Apply confirmed values separately.
"""
import json, re, html, time, os, sys, urllib.request
import pipeline

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
UA = "Fair500 research blakebalbirnie@gmail.com"

TARGETS = ["MO","AEE","ADM","EIX","EMR","EXC","GEHC","DOC","HLT","HST","IEX","IDXX",
           "JBL","J","MNST","NDAQ","NTAP","PANW","PLD","PEG","REG","ROK","ROST","TPL",
           "URI","VTR","VRSN","VICI","WELL","XEL","CAT","T","CEG","PRU"]

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read()

def clean(url):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", get(url).decode("utf-8", "ignore"))))

# total-headcount statements, most specific first
PATS = [
    r"(?:we|the company|the bancorp|our workforce)[^.]{0,40}?(?:had|employed|was|consisted of|totaled)[^.]{0,40}?approximately ([\d,]{4,}) (?:full-time |full time )?(?:equivalent )?(?:employees|associates|people|individuals|persons|teammates)",
    r"approximately ([\d,]{4,}) (?:full-time |full time )?(?:equivalent )?(?:employees|associates|people|individuals|persons|teammates)",
    r"(?:had|employed|of) ([\d,]{4,}) (?:full-time |full time )?(?:equivalent )?(?:employees|associates|people|individuals|persons)",
    r"workforce (?:of|was) approximately ([\d,]{4,})",
]

def extract(t):
    cands = []
    for pat in PATS:
        for m in re.finditer(pat, t, re.I):
            n = int(m.group(1).replace(",", ""))
            if 50 <= n <= 3_000_000:
                sent = t[max(0, m.start()-70): m.end()+40]
                cands.append((n, sent.strip()))
        if cands:
            break
    return cands

def main():
    d = {r["ticker"]: r for r in json.load(open(os.path.join(DATA, "data.json")))}
    for tk in TARGETS:
        r = d[tk]
        try:
            sub = json.loads(get(f"https://data.sec.gov/submissions/CIK{r['cik']}.json").decode())["filings"]["recent"]
            u = pipeline.find_form_url(r["cik"], sub, "10-K")
            t = clean(u)
        except Exception as e:
            print(f"{tk:6} stored={r['employees']}  ERROR {e}"); continue
        cands = extract(t)
        print(f"\n{tk:6} stored={r['employees']}")
        for n, sent in cands[:2]:
            print(f"   -> {n:>9,}  «{sent[:150]}»")
        if not cands:
            print("   -> [no total-headcount statement matched]")
        time.sleep(0.2)

if __name__ == "__main__":
    main()
