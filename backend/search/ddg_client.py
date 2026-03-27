"""
KominoSearch — DDG client
Routes through Tor SOCKS5 when Stay Hidden is active.
"""

import re
import ssl
import httpx
from urllib.parse import unquote

# SSL bypass for Termux
ssl._create_default_https_context = ssl._create_unverified_context

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

_AD = re.compile(
    r"duckduckgo\.com/y\.js|duckduckgo\.com/l/\?|doubleclick\.net|googlesyndication\.com",
    re.I
)

def _get_proxy(use_tor=False):
    if use_tor:
        return "socks5://127.0.0.1:9050"
    return None

def _unwrap(url):
    if "duckduckgo.com/l/?" in url:
        m = re.search(r"uddg=([^&]+)", url)
        if m:
            return unquote(m.group(1))
    return url

def _parse_html(html):
    results = []
    for block in re.findall(
        r'<div class="result[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>', html, re.S
    ):
        title_m = re.search(
            r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S
        )
        desc_m = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', block, re.S)
        if not title_m:
            continue
        url   = _unwrap(title_m.group(1))
        title = re.sub(r"<[^>]+>", "", title_m.group(2)).strip()
        desc  = re.sub(r"<[^>]+>", "", desc_m.group(1)).strip() if desc_m else ""
        if url and not _AD.search(url):
            results.append({"title": title, "url": url, "description": desc, "source": "ddg"})
    return results

def ddg_search(query, count=10, region="wt-wt", safesearch="moderate",
               timelimit=None, use_tor=False):
    params = {"q": query, "kl": region, "kp": "-1"}
    if timelimit:
        params["df"] = timelimit
    proxy = _get_proxy(use_tor)
    try:
        with httpx.Client(verify=False, follow_redirects=True,
                          proxy=proxy, timeout=15) as client:
            r = client.get("https://html.duckduckgo.com/html/",
                           params=params, headers=HEADERS)
            r.raise_for_status()
            return _parse_html(r.text)[:count]
    except Exception as e:
        raise RuntimeError(f"DDG request failed: {e}")

def ddg_news(query, count=5, region="wt-wt", timelimit="w", use_tor=False):
    params = {"q": query, "kl": region, "iar": "news", "ia": "news"}
    proxy = _get_proxy(use_tor)
    try:
        with httpx.Client(verify=False, follow_redirects=True,
                          proxy=proxy, timeout=15) as client:
            r = client.get("https://html.duckduckgo.com/html/",
                           params=params, headers=HEADERS)
            r.raise_for_status()
            results = _parse_html(r.text)[:count]
            for res in results:
                res["source"] = "ddg_news"
            return results
    except Exception as e:
        raise RuntimeError(f"DDG News failed: {e}")