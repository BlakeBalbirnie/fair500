#!/usr/bin/env python3
"""Verify hand-written figures in content/ against data/web_data.json.

The prose pages are written by hand and quote a lot of specific numbers. This
checks the ones that are mechanically checkable:

  * hand-written table rows tagged with <span class="tk">TICKER</span>
  * prose of the form "<Company> ... NNN:1"
  * prose of the form "<Company> ... median of $NN,NNN"

Run:  python3 pipeline/check_content.py
Exits non-zero if any claim contradicts the dataset.
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CONTENT = os.path.join(ROOT, "content")

rows = json.load(open(os.path.join(ROOT, "data", "web_data.json")))
by_ticker = {r["t"]: r for r in rows}

# name -> record, including a few short forms used in prose
by_name = {}
for r in rows:
    by_name[r["n"].lower()] = r
    short = re.sub(r"[,.]? (Inc|Corp|Corporation|Company|Co|plc|Ltd|Group|& Co)\.?$", "",
                   r["n"], flags=re.I)
    by_name.setdefault(short.lower(), r)
EXTRA = {
    "alphabet": "GOOGL", "meta": "META", "google": "GOOGL", "amazon": "AMZN",
    "walmart": "WMT", "coca-cola": "KO", "mcdonald's": "MCD", "starbucks": "SBUX",
    "disney": "DIS", "walt disney": "DIS", "exxonmobil": "XOM", "chevron": "CVX",
    "nvidia": "NVDA", "broadcom": "AVGO", "intel": "INTC", "tesla": "TSLA",
    "netflix": "NFLX", "verizon": "VZ", "comcast": "CMCSA", "charter": "CHTR",
    "welltower": "WELL", "fiserv": "FISV", "citigroup": "C", "wells fargo": "WFC",
    "jpmorgan chase": "JPM", "berkshire hathaway": "BRK.B", "blackstone": "BX",
    "kkr": "KKR", "apollo": "APO", "coinbase": "COIN", "robinhood": "HOOD",
    "unitedhealth": "UNH", "hca": "HCA", "align technology": "ALGN",
    "thermo fisher": "TMO", "veeva": "VEEV", "regeneron": "REGN", "vertex": "VRTX",
    "biogen": "BIIB", "moderna": "MRNA", "incyte": "INCY", "gilead": "GILD",
    "zoetis": "ZTS", "becton dickinson": "BDX", "baxter": "BAX", "solventum": "SOLV",
    "carrier": "CARR", "carrier global": "CARR", "ge aerospace": "GE",
    "howmet": "HWM", "howmet aerospace": "HWM", "vertiv": "VRT", "otis": "OTIS",
    "otis worldwide": "OTIS", "trane": "TT", "trane technologies": "TT",
    "axon": "AXON", "axon enterprise": "AXON", "copart": "CPRT", "fastenal": "FAST",
    "norfolk southern": "NSC", "csx": "CSX", "union pacific": "UNP", "eaton": "ETN",
    "uber": "UBER", "paccar": "PCAR", "caterpillar": "CAT", "deere": "DE",
    "boeing": "BA", "ross stores": "ROST", "aptiv": "APTV", "ulta beauty": "ULTA",
    "tjx": "TJX", "yum! brands": "YUM", "chipotle": "CMG", "carnival": "CCL",
    "royal caribbean": "RCL", "airbnb": "ABNB", "doordash": "DASH", "nvr": "NVR",
    "pultegroup": "PHM", "d.r. horton": "DHI", "dollar tree": "DLTR",
    "dollar general": "DG", "casey's": "CASY", "tyson": "TSN", "tyson foods": "TSN",
    "pepsico": "PEP", "altria": "MO", "hershey": "HSY", "kroger": "KR",
    "church & dwight": "CHD", "kenvue": "KVUE", "molson coors": "TAP",
    "hormel": "HRL", "j.m. smucker": "SJM", "mondelez": "MDLZ",
    "philip morris": "PM", "estée lauder": "EL", "darden": "DRI",
    "baker hughes": "BKR", "halliburton": "HAL", "schlumberger": "SLB",
    "phillips 66": "PSX", "valero": "VLO", "targa": "TRGP", "expand energy": "EXE",
    "texas pacific land": "TPL", "williams companies": "WMB", "devon": "DVN",
    "devon energy": "DVN", "apa": "APA", "apa corporation": "APA",
    "diamondback": "FANG", "diamondback energy": "FANG", "eog": "EOG",
    "eog resources": "EOG", "conocophillips": "COP", "occidental": "OXY",
    "pinnacle west": "PNW", "dte": "DTE", "dte energy": "DTE",
    "alliant": "LNT", "alliant energy": "LNT", "american water works": "AWK",
    "cms energy": "CMS", "evergy": "EVRG", "american electric power": "AEP",
    "aes": "AES", "southern company": "SO", "nrg": "NRG", "sempra": "SRE",
    "nextera": "NEE", "nextera energy": "NEE", "duke energy": "DUK",
    "centerpoint": "CNP", "edison international": "EIX", "constellation energy": "CEG",
    "vici properties": "VICI", "host hotels": "HST", "realty income": "O",
    "prologis": "PLD", "federal realty": "FRT", "cbre": "CBRE", "cbre group": "CBRE",
    "iron mountain": "IRM", "public storage": "PSA", "extra space storage": "EXR",
    "simon property group": "SPG", "costar": "CSGP", "mid-america": "MAA",
    "essex": "ESS", "regency centers": "REG", "alexandria real estate": "ARE",
    "crown castle": "CCI", "avery dennison": "AVY", "linde": "LIN", "ecolab": "ECL",
    "ppg": "PPG", "ppg industries": "PPG", "smurfit westrock": "SW",
    "sherwin-williams": "SHW", "ball corporation": "BALL", "cf industries": "CF",
    "freeport-mcmoran": "FCX", "steel dynamics": "STLD", "vulcan materials": "VMC",
    "nucor": "NUE", "newmont": "NEM", "martin marietta": "MLM", "albemarle": "ALB",
    "dow": "DOW", "international paper": "IP", "crh": "CRH",
    "live nation": "LYV", "warner bros. discovery": "WBD", "omnicom": "OMC",
    "tko group": "TKO", "t-mobile": "TMUS", "take-two": "TTWO",
    "take-two interactive": "TTWO", "echostar": "ECHO", "trade desk": "TTD",
    "at&t": "T", "fox corporation": "FOXA", "western digital": "WDC",
    "lumentum": "LITE", "jabil": "JBL", "flex": "FLEX", "on semiconductor": "ON",
    "amphenol": "APH", "seagate": "STX", "coherent": "COHR", "palantir": "PLTR",
    "dell": "DELL", "oracle": "ORCL", "teledyne": "TDY", "arista": "ANET",
    "verisign": "VRSN", "applovin": "APP", "apple": "AAPL", "microsoft": "MSFT",
    "intuit": "INTU", "adobe": "ADBE", "palo alto networks": "PANW",
    "supermicro": "SMCI", "crowdstrike": "CRWD", "american express": "AXP",
    "bny mellon": "BNY", "state street": "STT", "factset": "FDS",
    "s&p global": "SPGI", "blackrock": "BLK", "cme group": "CME",
    "everest group": "EG", "erie indemnity": "ERIE", "block": "XYZ",
    "lilly": "LLY", "eli lilly": "LLY", "bristol myers squibb": "BMY",
    "bio-techne": "TECH", "centene": "CNC", "viatris": "VTRS", "kraft heinz": "KHC",
    "monster beverage": "MNST", "brown–forman": "BF.B", "lululemon": "LULU",
    "williams-sonoma": "WSM", "builders firstsource": "BLDR", "wabtec": "WAB",
    "international flavors & fragrances": "IFF", "amcor": "AMCR",
    "fidelity national information services": "FIS", "corpay": "CPAY",
    "jack henry": "JKHY", "cboe global markets": "CBOE", "xcel energy": "XEL",
    "camden property trust": "CPT", "lowe's": "LOW", "home depot": "HD",
    "procter & gamble": "PG", "johnson & johnson": "JNJ", "merck": "MRK",
    "abbott": "ABT", "sysco": "SYY", "archer daniels midland": "ADM",
    "ebay": "EBAY", "expedia": "EXPE", "hasbro": "HAS", "deckers": "DECK",
    "o’reilly automotive": "ORLY", "microchip technology": "MCHP",
    "marathon petroleum": "MPC", "kinder morgan": "KMI", "eqt": "EQT",
    "eqt corporation": "EQT", "pg&e": "PCG", "entergy": "ETR",
    "consolidated edison": "ED", "atmos energy": "ATO", "wabash": None,
}
for k, v in EXTRA.items():
    if v and v in by_ticker:
        by_name.setdefault(k, by_ticker[v])

problems = []


def money(s):
    return int(s.replace(",", "").replace("$", ""))


PERYEAR = re.compile(r"<!--PER-YEAR-->")


def check_tables(path, src):
    """Hand-written rows: <td class="co">Name<span class="tk">TK</span></td> + cells."""
    peryear = bool(PERYEAR.search(src))
    for m in re.finditer(r'<td class="co">([^<]+)<span class="tk">([A-Z.\-]+)</span></td>'
                         r'((?:<td[^>]*>[^<]*</td>)+)', src):
        name, tk, cells = m.group(1).strip(), m.group(2), m.group(3)
        r = by_ticker.get(tk)
        if not r:
            problems.append(f"{path}: unknown ticker {tk} (for '{name}')")
            continue
        dn = r["n"].replace("&amp;", "&").lower()
        cn = name.replace("&amp;", "&").lower()
        if not (dn == cn or dn.startswith(cn)):
            problems.append(f"{path}: {tk} labelled '{name}' but dataset says '{r['n']}'")
        vals = re.findall(r"<td[^>]*>([^<]*)</td>", cells)
        for v in vals:
            v = v.strip().replace("&nbsp;", "")
            if re.fullmatch(r"[\d,]+:1", v):
                claimed = int(v.split(":")[0].replace(",", ""))
                if r.get("r") != claimed:
                    problems.append(f"{path}: {tk} ratio {claimed}:1, dataset {r.get('r')}:1")
            elif re.fullmatch(r"\$[\d,]+", v):
                c = money(v)
                # could be median pay, profit-per-employee, or headcount-ish
                ppw = (r["p"] * 1e9 / r["emp"]) if r.get("emp") and r["p"] > 0 else None
                ok = (r.get("med") == c
                      or (ppw and abs(ppw - c) <= max(2, ppw * 0.005)))
                if not ok:
                    problems.append(
                        f"{path}: {tk} ${c:,} matches neither median "
                        f"({r.get('med')}) nor profit/employee "
                        f"({int(ppw) if ppw else None})")
            elif re.fullmatch(r"\$[\d.]+M", v):
                if peryear:
                    continue
                c = float(v[1:-1]) * 1e6
                if not r.get("cp") or abs(r["cp"] - c) > 60_000:
                    problems.append(f"{path}: {tk} CEO pay {v}, dataset "
                                    f"${(r.get('cp') or 0)/1e6:.1f}M")


NAME_RE = None


def check_prose(path, src):
    """'<Company> ... NNN:1' and '<Company> ... median of $NN,NNN' within 140 chars."""
    text = re.sub(r"<[^>]+>", " ", src)
    text = re.sub(r"\s+", " ", text)
    names = sorted(by_name, key=len, reverse=True)
    pat = re.compile("(" + "|".join(re.escape(n) for n in names) + ")"
                     r"(.{0,140}?)(?:(\d[\d,]*):1|median of (\$[\d,]+))",
                     re.I)
    for m in pat.finditer(text):
        nm, gap, ratio, med = m.group(1), m.group(2), m.group(3), m.group(4)
        # if another company name appears in the gap, the figure belongs to it
        if re.search("|".join(re.escape(n) for n in names), gap, re.I):
            continue
        r = by_name.get(nm.lower())
        if not r:
            continue
        if ratio:
            c = int(ratio.replace(",", ""))
            # single-year / hypothetical figures are flagged in the prose itself
            if re.search(r"would (be|exceed|sit|produce)|on the (peak|grant) year|"
                         r"single-year|single year", gap, re.I):
                continue
            if r.get("r") != c:
                problems.append(f"{path}: prose '{nm} ... {c}:1' but dataset "
                                f"{r.get('r')}:1")
        if med:
            c = money(med)
            if r.get("med") != c:
                problems.append(f"{path}: prose '{nm} ... median of {med}' but dataset "
                                f"${(r.get('med') or 0):,}")


for dirpath, _, files in os.walk(CONTENT):
    for f in sorted(files):
        if not f.endswith(".html"):
            continue
        p = os.path.relpath(os.path.join(dirpath, f), ROOT)
        src = open(os.path.join(dirpath, f)).read()
        check_tables(p, src)
        check_prose(p, src)

if problems:
    print(f"{len(problems)} problem(s):\n")
    for p in problems:
        print("  ✗", p)
    sys.exit(1)
print("All checkable figures in content/ agree with the dataset.")
