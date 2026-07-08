# Fair500

**[fair500.com](https://fair500.com)** — an interactive map of how much profit each
S&P 500 company makes, and how much of it reaches the people who work there.

Every company is plotted by total profit (3-year average net income, log scale) against
a **fairness score** built from two lenses:

- **CEO pay gap** — the disclosed CEO-to-median-worker pay ratio.
- **Worker pay vs. profit** — median worker pay measured against profit-per-employee.

Bubble size is median worker pay; color is the fairness score. All figures come from
public **SEC EDGAR** filings (XBRL financials) and **DEF 14A** proxy statements
(the §953(b) pay-ratio disclosure).

## Layout

```
index.html          The site — a single self-contained file (data inlined, no build needed to view)
og-image.png        Social/share preview card
robots.txt          Crawler directives
sitemap.xml         Sitemap for search engines
ads.txt             Google AdSense authorization
CNAME               Custom domain for GitHub Pages (fair500.com)

data/
  data.json         Master dataset — 500 constituents, all extracted fields (source of truth)
  web_data.json     Derived site dataset (filtered + short keys), inlined into index.html
  sp500.json        S&P 500 constituent list (ticker, name, sector, CIK)

pipeline/
  pipeline.py       SEC extraction library (XBRL financials, pay ratio, median pay, headcount)
  build_site.py     Builds web_data.json from data.json and re-inlines the DATA blob into index.html
  audit.py          Full data audit (ratio x median vs. CEO pay, headcount & staleness checks)
  reaudit.py        Fast consistency re-check across all companies
  verify48.py       Cross-checks companies whose CEO pay couldn't be auto-extracted
  reprocess_median.py  High-precision median-pay re-extraction
```

## Updating the data

1. Edit or re-pull figures into `data/data.json` (the master).
2. Rebuild the site set and re-inline it:
   ```bash
   python3 pipeline/build_site.py
   ```
   This regenerates `data/web_data.json` and updates the `const DATA = [...]` blob in
   `index.html`. Nothing else is needed — `index.html` is fully self-contained.

**Site inclusion rule** (enforced by `build_site.py`): profit > 0, at least one fairness
input present (ratio or median), and — when both are present — estimated CEO pay
(ratio × median) ≥ $100,000. The last rule drops founder-CEOs who take a ~$0 salary,
whose disclosed comp misrepresents their real equity-based wealth.

## Local preview

Serve the folder and open `index.html` — e.g. `python3 -m http.server` — or just open the
file directly in a browser.

## Data sources

- **SEC EDGAR** — XBRL company financials (`data.sec.gov`)
- **DEF 14A proxy statements** — CEO pay ratio, median employee compensation (Dodd-Frank §953(b))
