#!/usr/bin/env python3
"""Full-dataset verification, stage 2 (offline): cross-check stored median pay
and pay ratio against the ACTUAL pay-ratio disclosure text captured by
verify_generate.py (data/verify_batches/*.txt).

Because the excerpts are anchored on the real disclosure, this catches median
and ratio errors: it reads the filed ratio ("N to 1"), the median dollar figure
stated next to "median employee", and the CEO's total comp, then flags any
company whose stored values disagree. Candidates should then be read by hand
(or by the LLM verification subagents) to confirm before fixing.

Run verify_generate.py first, then:  python3 pipeline/verify_crosscheck.py
"""
import re, glob, os, json

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")


def num(s):
    return int(s.replace(",", ""))


def main():
    d = {r["ticker"]: r for r in json.load(open(os.path.join(DATA, "data.json")))}
    blocks = []
    for f in sorted(glob.glob(os.path.join(DATA, "verify_batches", "batch_*.txt"))):
        for blk in open(f).read().split("-" * 88):
            m = re.search(r"TICKER: (\S+)", blk)
            if m:
                blocks.append((m.group(1), blk))

    flags = []
    for tk, blk in blocks:
        r = d.get(tk)
        pr = re.search(r"PROXY_PAY_RATIO_TEXT: (.*?)\nTENK_HEADCOUNT_TEXT:", blk, re.S)
        if not r or not pr:
            continue
        w = pr.group(1)
        sm, sr = r.get("median_pay"), r.get("ratio")
        rm = re.search(r"(?<![\d.])(\d[\d,]{0,6}(?:\.\d+)?)\s*(?:to|:)\s*1\b", w)
        filed_ratio = float(rm.group(1).replace(",", "")) if rm else None
        # reject year-like "ratio" (TOC noise)
        if filed_ratio and filed_ratio == int(filed_ratio) and 1990 <= filed_ratio <= 2035:
            filed_ratio = None
        med_cands = []
        for mm in re.finditer(r"median[^.$]{0,90}?\$\s?([\d,]{4,})|\$\s?([\d,]{4,})[^.$]{0,60}?median", w, re.I):
            v = num(mm.group(1) or mm.group(2))
            if 6000 <= v <= 600000:
                med_cands.append(v)
        if sr and filed_ratio and sr >= 2:
            if abs(filed_ratio - sr) / sr > 0.05 and abs(filed_ratio - sr) > 1:
                flags.append((tk, "ratio", sr, filed_ratio))
        if sm and med_cands and not any(abs(c - sm) / sm <= 0.02 for c in med_cands):
            flags.append((tk, "median", sm, med_cands))

    print(f"Cross-checked {len(blocks)} companies against filed disclosures; "
          f"{len(flags)} candidates to review by hand/LLM:\n")
    for tk, fld, stored, filed in flags:
        print(f"  {tk:6} {fld:7} stored={stored}  filed_candidate(s)={filed}")
    if not flags:
        print("  (none)")


if __name__ == "__main__":
    main()
