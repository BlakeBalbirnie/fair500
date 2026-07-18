#!/usr/bin/env python3
"""Build Fair500's content pages (articles, sector pages, about/contact/methodology).

Each source file in content/ is a hand-written HTML fragment prefixed with a JSON
metadata block:

    <!--META
    {"path": "articles/ceo-pay-ratio-explained.html",
     "title": "...", "desc": "...", "type": "article",
     "published": "2026-07-18", "standfirst": "..."}
    -->
    <p>body html...</p>

The builder only supplies the shell — <head>, nav, footer, schema. The prose in
content/ is written by hand; nothing here generates sentences.

Run:  python3 pipeline/build_pages.py
"""
import json, os, re, datetime, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tables

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CONTENT = os.path.join(ROOT, "content")
SITE = "https://fair500.com"

# privacy.html is hand-maintained, not built from content/; bump this when it changes
# so the sitemap does not tell crawlers to skip a page that actually moved.
PRIVACY_MODIFIED = "2026-07-18"

NAV = [
    ("/", "The map"),
    ("/sectors/", "Sectors"),
    ("/articles/", "Analysis"),
    ("/methodology.html", "Methodology"),
    ("/about.html", "About"),
]

ADS = ('<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js'
       '?client=ca-pub-7286721892267178" crossorigin="anonymous"></script>')

FAVICON = ("data:image/svg+xml,%3Csvg%20xmlns%3D%27http%3A//www.w3.org/2000/svg%27%20viewBox%3D%270%200%20100%20100%27%3E"
           "%3Crect%20width%3D%27100%27%20height%3D%27100%27%20rx%3D%2722%27%20fill%3D%27%232f6df6%27/%3E"
           "%3Crect%20x%3D%2722%27%20y%3D%2754%27%20width%3D%2713%27%20height%3D%2726%27%20rx%3D%272%27%20fill%3D%27%23fff%27/%3E"
           "%3Crect%20x%3D%2743%27%20y%3D%2740%27%20width%3D%2713%27%20height%3D%2740%27%20rx%3D%272%27%20fill%3D%27%23fff%27/%3E"
           "%3Crect%20x%3D%2764%27%20y%3D%2726%27%20width%3D%2713%27%20height%3D%2754%27%20rx%3D%272%27%20fill%3D%27%23fff%27/%3E%3C/svg%3E")

# Theme toggle, shared with index.html's behaviour (localStorage key "f500-theme").
THEME_JS = """<script>
(function(){var k='f500-theme',s=localStorage.getItem(k);if(s)document.documentElement.setAttribute('data-theme',s);
document.addEventListener('DOMContentLoaded',function(){var b=document.getElementById('themeToggle');if(!b)return;
var d=function(){var t=document.documentElement.getAttribute('data-theme');
return t?t:(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light')};
b.textContent=d()==='dark'?'☀':'☾';
b.onclick=function(){var n=d()==='dark'?'light':'dark';
document.documentElement.setAttribute('data-theme',n);localStorage.setItem(k,n);b.textContent=n==='dark'?'☀':'☾'}})})();
</script>"""


def canonical_path(path):
    """URL form used in canonical, og:url and the sitemap.

    Directory index pages are linked as /articles/ everywhere on the site, so
    they must canonicalise to that form rather than /articles/index.html, or
    the two spellings compete as duplicates.
    """
    if path == "index.html":
        return ""
    if path.endswith("/index.html"):
        return path[: -len("index.html")]
    return path


def depth_prefix(path):
    """Relative prefix back to site root, e.g. 'articles/x.html' -> '../'."""
    return "../" * path.count("/")


def nav_html(path):
    cur = "/" + path
    if path.endswith("index.html"):
        cur = "/" + path[: -len("index.html")]
    out = []
    for href, label in NAV:
        on = " class=\"on\"" if href == cur else ""
        out.append(f'<a href="{href}"{on}>{label}</a>')
    return "".join(out)


def schema_for(meta):
    url = f"{SITE}/{canonical_path(meta['path'])}"
    if meta["type"] == "article":
        node = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": meta["title"],
            "description": meta["desc"],
            "url": url,
            "datePublished": meta["published"],
            "dateModified": meta.get("modified", meta["published"]),
            "author": {"@type": "Organization", "name": "Fair500", "url": SITE + "/"},
            "publisher": {"@type": "Organization", "name": "Fair500", "url": SITE + "/"},
            "isBasedOn": "https://www.sec.gov/edgar",
            "mainEntityOfPage": {"@type": "WebPage", "@id": url},
        }
    else:
        node = {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": meta["title"],
            "description": meta["desc"],
            "url": url,
            "isPartOf": {"@type": "WebSite", "name": "Fair500", "url": SITE + "/"},
        }
    if meta.get("faq"):
        node = [node, {
            "@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": q,
                            "acceptedAnswer": {"@type": "Answer", "text": a}}
                           for q, a in meta["faq"]],
        }]
    return json.dumps(node, indent=1)


SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title_tag}</title>
<meta name="description" content="{desc}">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta name="author" content="Fair500">
<meta name="theme-color" content="#2f6df6">
<link rel="canonical" href="{url}">
<link rel="icon" type="image/svg+xml" href="{favicon}">
<meta property="og:type" content="{ogtype}">
<meta property="og:site_name" content="Fair500">
<meta property="og:title" content="{title_esc}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{site}/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title_esc}">
<meta name="twitter:description" content="{desc}">
<meta name="twitter:image" content="{site}/og-image.png">
<script type="application/ld+json">
{schema}
</script>
<link rel="stylesheet" href="{pfx}assets/site.css">
{theme_js}
{ads}
</head>
<body>
<div class="topbar"><div class="topbar-in">
  <a class="brand" href="/">Fair<span>500</span></a>
  <nav class="nav">{nav}</nav>
  <button class="theme-btn" id="themeToggle" aria-label="Toggle light or dark mode" title="Toggle light/dark">&#9790;</button>
</div></div>

<div class="wrap{wide}">
{crumb}
<h1>{title_esc}</h1>
{standfirst}
{byline}
{body}
</div>

<footer class="site"><div class="in{wide}">
  <nav>
    <a href="/">The map</a><a href="/sectors/">Sectors</a><a href="/articles/">Analysis</a>
    <a href="/methodology.html">Methodology</a><a href="/about.html">About</a>
    <a href="/contact.html">Contact</a><a href="/privacy.html">Privacy</a>
  </nav>
  <p><b>Fair500</b> &middot; Built from public <a href="https://www.sec.gov/edgar" rel="nofollow">SEC EDGAR</a> filings &middot;
     CEO pay-ratio and median-worker-pay data from DEF 14A proxy statements.</p>
  <p>Data last updated July 2026 &middot; Not affiliated with the U.S. Securities and Exchange Commission or any company listed.
     Nothing here is investment advice.</p>
</div></footer>
</body>
</html>
"""


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def build_page(meta, body):
    path = meta["path"]
    title_tag = meta.get("title_tag") or f"{meta['title']} · Fair500"
    crumb = ""
    if meta.get("crumb"):
        crumb = f'<p class="crumb">{meta["crumb"]}</p>'
    standfirst = f'<p class="standfirst">{meta["standfirst"]}</p>' if meta.get("standfirst") else ""
    byline = ""
    if meta["type"] == "article":
        d = datetime.date.fromisoformat(meta["published"]).strftime("%-d %B %Y")
        byline = (f'<p class="byline">By the Fair500 editors &middot; Published {d} &middot; '
                  f'All figures from SEC filings &middot; '
                  f'<a href="/methodology.html">How these numbers are built</a></p>')
    return SHELL.format(
        title_tag=esc(title_tag), title_esc=esc(meta["title"]), desc=esc(meta["desc"]),
        url=f"{SITE}/{canonical_path(path)}", site=SITE, favicon=FAVICON,
        ogtype="article" if meta["type"] == "article" else "website",
        schema=schema_for(meta), pfx=depth_prefix(path), theme_js=THEME_JS, ads=ADS,
        nav=nav_html(path), crumb=crumb, standfirst=standfirst, byline=byline,
        body=body.strip(), wide=" wide" if meta.get("wide") else "",
    )


META_RE = re.compile(r"^<!--META\s*(\{.*?\})\s*-->\s*", re.S)


def main():
    built = []
    for dirpath, _, files in os.walk(CONTENT):
        for f in sorted(files):
            if not f.endswith(".html"):
                continue
            # expand data placeholders across the whole file so they work in
            # metadata (titles, descriptions, standfirsts) as well as the body
            src = tables.expand(open(os.path.join(dirpath, f)).read())
            m = META_RE.match(src)
            assert m, f"{f}: missing <!--META ... --> block"
            meta = json.loads(m.group(1))
            body = src[m.end():]
            out = os.path.join(ROOT, meta["path"])
            os.makedirs(os.path.dirname(out), exist_ok=True)
            open(out, "w").write(build_page(meta, body))
            built.append((meta["path"], meta.get("published")))

    # regenerate sitemap: homepage + privacy + every built page
    today = datetime.date.today().isoformat()
    urls = [("", "1.0", "monthly", today), ("privacy.html", "0.3", "yearly", PRIVACY_MODIFIED)]
    for p, pub in sorted(built):
        pri = "0.9" if p.endswith("index.html") else "0.8"
        urls.append((canonical_path(p), pri, "monthly", pub or today))
    body = "\n".join(
        f"  <url>\n    <loc>{SITE}/{u}</loc>\n    <lastmod>{lm}</lastmod>\n"
        f"    <changefreq>{cf}</changefreq>\n    <priority>{pr}</priority>\n  </url>"
        for u, pr, cf, lm in urls)
    open(os.path.join(ROOT, "sitemap.xml"), "w").write(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + body + "\n</urlset>\n")

    print(f"Built {len(built)} content pages; sitemap lists {len(urls)} URLs.")
    for p, _ in sorted(built):
        print("  ", p)


if __name__ == "__main__":
    main()
