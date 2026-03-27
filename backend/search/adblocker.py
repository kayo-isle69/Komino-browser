"""
search/adblocker.py
URL cleaning, tracker stripping, ad domain blocking, result filtering.
"""
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
import re

# ── Tracking params to strip ──────────────────────────────────────────────────
_TRACKING = frozenset({
    "utm_source","utm_medium","utm_campaign","utm_term","utm_content",
    "utm_id","utm_reader","utm_name",
    "fbclid","fb_action_ids","fb_action_types","fb_source",
    "gclid","gclsrc","dclid","gbraid","wbraid","msclkid","twclid",
    "hsa_acc","hsa_cam","hsa_grp","hsa_ad","hsa_src","hsa_tgt",
    "hsa_kw","hsa_mt","hsa_net","hsa_ver","_hsenc","_hsmi","mkt_tok",
    "ref","pf_rd_r","pf_rd_m","pf_rd_p","pf_rd_s","pf_rd_t","pf_rd_i",
    "mc_cid","mc_eid","sc_cid","ncid","icid","yclid",
})

# ── Blocked ad/tracker domains ────────────────────────────────────────────────
_BLOCKED_DOMAINS = frozenset({
    "doubleclick.net","googleadservices.com","googlesyndication.com",
    "google-analytics.com","analytics.google.com","adservice.google.com",
    "facebook.com/tr","connect.facebook.net","ads.twitter.com",
    "static.ads-twitter.com","amazon-adsystem.com","media.net",
    "outbrain.com","taboola.com","revcontent.com","zergnet.com",
    "adnxs.com","rubiconproject.com","pubmatic.com","openx.net",
    "criteo.com","moatads.com","scorecardresearch.com","quantserve.com",
    "chartbeat.com","newrelic.com","hotjar.com","fullstory.com",
    "mouseflow.com","clarity.ms",
})

_AD_PATH_PATTERN = re.compile(
    r"/(ads?|advert|banner|track|pixel|beacon|analytics|telemetry)/",
    re.IGNORECASE,
)


def is_blocked(url: str) -> bool:
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        host = parsed.netloc.lower().lstrip("www.")
        if any(host == d or host.endswith(f".{d}") for d in _BLOCKED_DOMAINS):
            return True
        if _AD_PATH_PATTERN.search(parsed.path):
            return True
    except Exception:
        pass
    return False


def clean_url(url: str) -> dict:
    """Strip tracking params, upgrade to HTTPS, check block status."""
    try:
        raw = url.strip()
        if not raw.startswith(("http://", "https://")):
            raw = "https://" + raw

        parsed = urlparse(raw)

        # HTTPS upgrade
        scheme = "https" if parsed.scheme == "http" else parsed.scheme

        # Strip tracking params
        qs = parse_qs(parsed.query, keep_blank_values=True)
        filtered = {k: v for k, v in qs.items() if k.lower() not in _TRACKING}
        clean_query = urlencode(filtered, doseq=True)

        clean = urlunparse((scheme, parsed.netloc, parsed.path,
                            parsed.params, clean_query, ""))
        blocked = is_blocked(clean)

        return {"original": url, "clean": clean, "blocked": blocked,
                "actions": ["https_upgrade" if parsed.scheme == "http" else None,
                            "tracking_stripped" if clean_query != parsed.query else None]}
    except Exception as e:
        return {"original": url, "clean": url, "blocked": False, "error": str(e)}


def filter_results(results: list[dict]) -> list[dict]:
    """Remove blocked URLs from a result list and clean the rest."""
    clean = []
    for r in results:
        url = r.get("url", "")
        if not url or is_blocked(url):
            continue
        cleaned = clean_url(url)
        r["url"] = cleaned["clean"]
        clean.append(r)
    return clean