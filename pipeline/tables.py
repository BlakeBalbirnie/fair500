#!/usr/bin/env python3
"""Data-driven table/stat fragments injected into hand-written content pages.

Content files contain placeholders like {{SECTOR_TABLE:Technology}}; this module
expands them from data/web_data.json so the numbers in the prose pages can never
drift from the dataset behind the map.
"""
import json, os, re, statistics as st, collections

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SECTOR_SLUG = {
    "Technology": "technology", "Financials": "financials", "Health Care": "health-care",
    "Industrials": "industrials", "Consumer Discretionary": "consumer-discretionary",
    "Consumer Staples": "consumer-staples", "Energy": "energy", "Utilities": "utilities",
    "Real Estate": "real-estate", "Materials": "materials",
    "Communication Services": "communication-services",
}
SLUG_SECTOR = {v: k for k, v in SECTOR_SLUG.items()}

_rows = None


def rows():
    global _rows
    if _rows is None:
        _rows = json.load(open(os.path.join(ROOT, "data", "web_data.json")))
    return _rows


def sector(name):
    return [r for r in rows() if r["sec"] == name]


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def usd(v, dp=0):
    return "$" + format(round(v, dp), f",.{dp}f") if v is not None else "n/a"


def bn(v):
    if v is None:
        return "n/a"
    return ("&minus;$" if v < 0 else "$") + f"{abs(v):,.1f}B"


def ppw(r):
    if not r.get("emp") or r.get("loss") or r["p"] <= 0:
        return None
    return r["p"] * 1e9 / r["emp"]


def fmt_int(v):
    return "{:,}".format(v) if v is not None else "n/a"


def co_cell(r):
    return f'<td class="co">{esc(r["n"])}<span class="tk">{esc(r["t"])}</span></td>'


def _table(caption, headers, body_rows):
    th = "".join(f"<th>{h}</th>" for h in headers)
    return (f'<div class="tbl-scroll"><table><caption>{caption}</caption>'
            f"<thead><tr>{th}</tr></thead><tbody>{''.join(body_rows)}</tbody></table></div>")


def sector_table(name):
    g = sorted(sector(name), key=lambda r: -(r["r"] or 0))
    out = []
    for r in g:
        ratio = "{:,}:1".format(r["r"]) if r.get("r") else "n/a"
        med = usd(r["med"]) if r.get("med") else "n/a"
        cp = "$%.1fM" % (r["cp"] / 1e6) if r.get("cp") else "n/a"
        emp = "{:,}".format(r["emp"]) if r.get("emp") else "n/a"
        out.append(
            f'<tr>{co_cell(r)}<td class="num">{ratio}</td><td class="num">{med}</td>'
            f'<td class="num">{cp}</td><td class="num">{bn(r["p"])}</td>'
            f'<td class="num">{emp}</td></tr>')
    return _table(
        f"Every {esc(name)} company in the S&amp;P 500 covered by Fair500 ({len(g)}), "
        f"ranked by CEO-to-worker pay ratio. Scroll sideways for more columns.",
        ["Company", "Pay ratio", "Median worker pay", "CEO pay (3-yr avg)", "Profit (3-yr avg)", "Employees"],
        out)


def sector_stats(name):
    g = sector(name)
    ratios = [r["r"] for r in g if r.get("r")]
    meds = [r["med"] for r in g if r.get("med")]
    pw = [x for x in (ppw(r) for r in g) if x]
    boxes = [
        (f"{len(g)}", "companies covered"),
        (f"{st.median(ratios):,.0f}:1", "median CEO-to-worker pay ratio"),
        (usd(st.median(meds)), "median worker pay (sector midpoint)"),
        (usd(st.median(pw)), "profit per employee (midpoint)"),
    ]
    return '<div class="stats">' + "".join(
        f'<div class="stat-box"><div class="v">{v}</div><div class="k">{k}</div></div>'
        for v, k in boxes) + "</div>"


def sector_tiles():
    counts = collections.Counter(r["sec"] for r in rows())
    out = []
    for name in sorted(counts, key=lambda n: -counts[n]):
        g = sector(name)
        ratios = [r["r"] for r in g if r.get("r")]
        meds = [r["med"] for r in g if r.get("med")]
        out.append(
            f'<a class="tile" href="/sectors/{SECTOR_SLUG[name]}.html">'
            f'<h3>{esc(name)}</h3>'
            f'<p>{counts[name]} companies &middot; median worker pay {usd(st.median(meds))}</p>'
            f'<p class="stat">Median pay ratio <b>{st.median(ratios):,.0f}:1</b></p></a>')
    return '<div class="grid two">' + "".join(out) + "</div>"


def rank_table(kind, n):
    n = int(n)
    rs = rows()
    if kind == "widest":
        g = sorted([r for r in rs if r.get("r")], key=lambda r: -r["r"])[:n]
        cap = f"The {n} widest CEO-to-worker pay ratios in the S&amp;P 500."
        cols = ["#", "Company", "Sector", "Pay ratio", "Median worker pay", "CEO pay (3-yr avg)"]
        body = [f'<tr><td class="num">{i}</td>{co_cell(r)}<td>{esc(r["sec"])}</td>'
                f'<td class="num">{r["r"]:,}:1</td><td class="num">{usd(r["med"])}</td>'
                f'<td class="num">${r["cp"]/1e6:.1f}M</td></tr>'
                for i, r in enumerate(g, 1)]
    elif kind == "fairest":
        g = sorted([r for r in rs if r.get("r") and r["r"] >= 20], key=lambda r: r["r"])[:n]
        cap = (f"The {n} narrowest CEO-to-worker pay ratios, excluding companies whose "
               f"chief executive is paid a nominal salary.")
        cols = ["#", "Company", "Sector", "Pay ratio", "Median worker pay", "CEO pay (3-yr avg)"]
        body = [f'<tr><td class="num">{i}</td>{co_cell(r)}<td>{esc(r["sec"])}</td>'
                f'<td class="num">{r["r"]:,}:1</td><td class="num">{usd(r["med"])}</td>'
                f'<td class="num">${r["cp"]/1e6:.1f}M</td></tr>'
                for i, r in enumerate(g, 1)]
    elif kind == "ppw":
        g = sorted([r for r in rs if ppw(r)], key=lambda r: -ppw(r))[:n]
        cap = f"The {n} highest profits per employee in the S&amp;P 500 (3-year average net income &divide; headcount)."
        cols = ["#", "Company", "Sector", "Profit per employee", "Median worker pay", "Employees"]
        body = [f'<tr><td class="num">{i}</td>{co_cell(r)}<td>{esc(r["sec"])}</td>'
                f'<td class="num">{usd(ppw(r))}</td><td class="num">{usd(r["med"]) if r.get("med") else "n/a"}</td>'
                f'<td class="num">{fmt_int(r.get("emp"))}</td></tr>'
                for i, r in enumerate(g, 1)]
    elif kind == "lowmed":
        g = sorted([r for r in rs if r.get("med")], key=lambda r: r["med"])[:n]
        cap = f"The {n} lowest disclosed median worker pay figures in the S&amp;P 500."
        cols = ["#", "Company", "Sector", "Median worker pay", "Pay ratio", "Employees"]
        body = [f'<tr><td class="num">{i}</td>{co_cell(r)}<td>{esc(r["sec"])}</td>'
                f'<td class="num">{usd(r["med"])}</td>'
                f'<td class="num">{(str(r["r"])+":1") if r.get("r") else "n/a"}</td>'
                f'<td class="num">{fmt_int(r.get("emp"))}</td></tr>'
                for i, r in enumerate(g, 1)]
    elif kind == "highmed":
        g = sorted([r for r in rs if r.get("med")], key=lambda r: -r["med"])[:n]
        cap = f"The {n} highest disclosed median worker pay figures in the S&amp;P 500."
        cols = ["#", "Company", "Sector", "Median worker pay", "Pay ratio", "Employees"]
        body = [f'<tr><td class="num">{i}</td>{co_cell(r)}<td>{esc(r["sec"])}</td>'
                f'<td class="num">{usd(r["med"])}</td>'
                f'<td class="num">{(str(r["r"])+":1") if r.get("r") else "n/a"}</td>'
                f'<td class="num">{fmt_int(r.get("emp"))}</td></tr>'
                for i, r in enumerate(g, 1)]
    else:
        raise ValueError(kind)
    return _table(cap, cols, body)


def stat(expr):
    """Inline single figures, e.g. {{STAT:count}}."""
    rs = rows()
    ratios = [r["r"] for r in rs if r.get("r")]
    meds = [r["med"] for r in rs if r.get("med")]
    return {
        "count": f"{len(rs)}",
        "median_ratio": f"{st.median(ratios):,.0f}",
        "median_pay": usd(st.median(meds)),
        "max_ratio": f"{max(ratios):,}",
        "n_ratios": f"{len(ratios)}",
    }[expr]


PH = re.compile(r"\{\{([A-Z_]+)(?::([^}]+))?\}\}")


def expand(html):
    def sub(m):
        kind, arg = m.group(1), m.group(2)
        if kind == "SECTOR_TABLE":
            return sector_table(SLUG_SECTOR.get(arg, arg))
        if kind == "SECTOR_STATS":
            return sector_stats(SLUG_SECTOR.get(arg, arg))
        if kind == "SECTOR_TILES":
            return sector_tiles()
        if kind == "RANK_TABLE":
            k, n = arg.split(":")
            return rank_table(k, n)
        if kind == "STAT":
            return stat(arg)
        raise ValueError(f"unknown placeholder {kind}")
    return PH.sub(sub, html)
