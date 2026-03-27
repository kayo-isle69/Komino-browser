"""
search/ranker.py
Simple TF-IDF-style ranker. Merges live results with visit frequency
from local history. High visit_count URLs float to the top.
"""
import math
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "index.db"


def _get_visit_counts(urls: list[str]) -> dict[str, int]:
    """Return {url: visit_count} for any urls already in history."""
    if not urls:
        return {}
    try:
        conn = sqlite3.connect(DB_PATH)
        placeholders = ",".join("?" * len(urls))
        rows = conn.execute(
            f"SELECT url, visit_count FROM visit_history WHERE url IN ({placeholders})",
            urls,
        ).fetchall()
        conn.close()
        return {r[0]: r[1] for r in rows}
    except Exception:
        return {}


def _score(result: dict, query: str, visit_counts: dict) -> float:
    """Higher = better. Combines keyword overlap + visit frequency boost."""
    terms = set(query.lower().split())
    text  = (result.get("title", "") + " " + result.get("description", "")).lower()
    
    # keyword hit ratio
    hits = sum(1 for t in terms if t in text)
    kw_score = hits / max(len(terms), 1)
    
    # visit boost (log scale so one viral page doesn't dominate)
    vc = visit_counts.get(result.get("url", ""), 0)
    visit_boost = math.log1p(vc) * 0.3
    
    return kw_score + visit_boost


def rank_and_merge(query: str, results: list[dict]) -> list[dict]:
    if not results:
        return []
    urls = [r.get("url", "") for r in results]
    visit_counts = _get_visit_counts(urls)
    scored = [(r, _score(r, query, visit_counts)) for r in results]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [r for r, _ in scored]