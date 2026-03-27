"""
api/routes/browse.py
────────────────────
Single endpoint: GET /browse?url=<target>

What it does
────────────
  1. Validates and cleans the URL (strips tracking params)
  2. Fetches the page with httpx (async, timeout-safe)
  3. Extracts title + main text content via lxml — no CSS, no scripts
  4. Returns JSON { url, title, content, fetched_at }

This is what the React shell renders when the user navigates directly
to a URL rather than searching. The content is clean prose — think
reader mode — so the UI doesn't need to deal with raw HTML.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx
from fastapi import APIRouter, HTTPException, Query, status
from lxml import etree, html as lhtml

# ── Config ────────────────────────────────────────────────────────────────────

# Query parameters that are purely tracking noise — strip them.
_TRACKING_PARAMS: frozenset[str] = frozenset({
    # UTM
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_reader", "utm_name",
    # Facebook / Meta
    "fbclid", "fb_action_ids", "fb_action_types", "fb_source",
    # Google
    "gclid", "gclsrc", "dclid", "gbraid", "wbraid",
    # Microsoft / Bing
    "msclkid",
    # Twitter / X
    "twclid",
    # HubSpot / Marketo / Pardot
    "hsa_acc", "hsa_cam", "hsa_grp", "hsa_ad", "hsa_src", "hsa_tgt",
    "hsa_kw", "hsa_mt", "hsa_net", "hsa_ver",
    "_hsenc", "_hsmi", "mkt_tok",
    # Amazon
    "ref", "pf_rd_r", "pf_rd_m", "pf_rd_p", "pf_rd_s", "pf_rd_t", "pf_rd_i",
    # Miscellaneous
    "mc_cid", "mc_eid", "sc_cid", "ncid", "icid", "yclid",
})

# Tags whose entire subtree we discard before extracting text.
_NOISE_TAGS: frozenset[str] = frozenset({
    "script", "style", "noscript", "iframe", "object", "embed",
    "form", "input", "button", "select", "textarea",
    "nav", "header", "footer", "aside",
    "svg", "canvas", "figure",
    "ad", "advertisement",
    "ul", "ol", "li", "menu", "menuitem",
})

_FETCH_TIMEOUT = 15.0   # seconds
_MAX_CONTENT_CHARS = 50_000  # trim very long pages for the JSON response

HEADERS = {
    "User-Agent": (
        "KominoBrowser/0.1 (self-hosted; +https://github.com/you/komino-browser)"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

router = APIRouter(prefix="", tags=["browse"])


# ── URL cleaning ──────────────────────────────────────────────────────────────

def clean_url(raw: str) -> str:
    """
    Strip known tracking query parameters and normalise the URL.

    Steps:
      - Parse URL components
      - Remove tracking params from query string
      - Rebuild without fragment (fragments are client-side only)
    """
    parsed = urlparse(raw)

    # Scheme must be http or https
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme!r}")

    # Filter query params
    qs = parse_qs(parsed.query, keep_blank_values=True)
    filtered = {k: v for k, v in qs.items() if k.lower() not in _TRACKING_PARAMS}
    clean_query = urlencode(filtered, doseq=True)

    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        clean_query,
        "",          # drop fragment
    ))


# ── Content extraction ────────────────────────────────────────────────────────

def _remove_noise(tree: lhtml.HtmlElement) -> None:
    """In-place removal of noisy subtrees from the parsed HTML tree."""
    for tag in _NOISE_TAGS:
        for el in tree.findall(f".//{tag}"):
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)

    # Also remove elements with common ad/tracking class names
    noise_pattern = re.compile(
        r"(ad|ads|advert|banner|cookie|gdpr|popup|modal|overlay|"
        r"newsletter|subscribe|sidebar|widget|social|share|comment)",
        re.IGNORECASE,
    )
    for el in tree.iter():
        cls = el.get("class", "") + " " + el.get("id", "")
        if noise_pattern.search(cls):
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)


def extract_title(tree: lhtml.HtmlElement) -> str:
    """Return the page <title> text, or empty string if absent."""
    title_el = tree.find(".//title")
    if title_el is not None and title_el.text:
        return title_el.text.strip()

    # Fallback: first <h1>
    h1 = tree.find(".//h1")
    if h1 is not None:
        return (h1.text_content() or "").strip()

    return ""


def extract_content(tree: lhtml.HtmlElement) -> str:
    """
    Pull readable text content from the page.

    Strategy:
      - Try <main>, <article>, [role=main] first (semantic content regions)
      - Fall back to <body>
      - Collapse whitespace, trim to _MAX_CONTENT_CHARS
    """
    # Priority containers (reader-mode heuristic)
    candidates = (
        tree.find(".//main")
        or tree.find(".//*[@role='main']")
        or tree.find(".//article")
        or tree.find(".//body")
        or tree
    )

    _remove_noise(candidates)

    raw = candidates.text_content()
    # Collapse runs of whitespace / blank lines
    lines = [ln.strip() for ln in raw.splitlines()]
    lines = [ln for ln in lines if ln]
    text = "\n".join(lines)

    return text[:_MAX_CONTENT_CHARS]


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.get("/browse")
async def browse(
    url: str = Query(..., description="The URL to fetch and parse"),
) -> dict:
    """
    Fetch a URL, strip trackers, and return clean prose content.

    Response
    ────────
    {
        "url":        "<cleaned url>",
        "title":      "<page title>",
        "content":    "<plain text of main content>",
        "fetched_at": "<ISO 8601 UTC timestamp>"
    }
    """
    # 1. Validate and clean
    try:
        url_clean = clean_url(url.strip())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    # 2. Fetch
    try:
        async with httpx.AsyncClient(
            headers=HEADERS,
            follow_redirects=True,
            timeout=_FETCH_TIMEOUT,
            verify=False,
        ) as client:
            response = await client.get(url_clean)
            response.raise_for_status()
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Request to {url_clean!r} timed out after {_FETCH_TIMEOUT}s.",
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Remote server returned {exc.response.status_code}.",
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Network error fetching URL: {exc}",
        )

    # 3. Guard: only parse HTML
    content_type = response.headers.get("content-type", "")
    if "html" not in content_type and "xml" not in content_type:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Expected HTML, got content-type: {content_type!r}",
        )

    # 4. Parse + extract
    try:
        tree = lhtml.fromstring(response.content)
    except etree.ParserError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse HTML: {exc}",
        )

    title   = extract_title(tree)
    content = extract_content(tree)

    return {
        "url":        url_clean,
        "title":      title,
        "content":    content,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
