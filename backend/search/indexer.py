"""
search/indexer.py
─────────────────
The caching brain between Brave Search API and your local FTS5 index.

Flow
────
  /search route calls query_cache(query)
      ├── HIT  (< 24 h old) → return cached results immediately, never touch Brave
      └── MISS → caller fetches from Brave → calls cache_results(query, results)
                 → next call for same query will be a HIT

Tables managed here
───────────────────
  search_cache  — stores raw Brave results keyed by normalised query
  search_index  — FTS5 table for full-text search over cached page content

The FTS5 table is the Phase-4 seed: once you have your own crawler, you
point it at search_index to find pages worth fetching in full.
"""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Generator

# ── Config ────────────────────────────────────────────────────────────────────

DB_PATH = Path(__file__).resolve().parent / "index.db"

# Results older than this are considered stale; Brave will be called again.
CACHE_TTL = timedelta(hours=24)


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def db_ctx() -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_indexer_tables() -> None:
    """Create FTS5 and cache tables. Call from api/main.py startup."""
    with db_ctx() as conn:
        conn.executescript("""
            -- Raw Brave result cache, keyed by normalised query string
            CREATE TABLE IF NOT EXISTS search_cache (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                query_key    TEXT NOT NULL UNIQUE,
                results_json TEXT NOT NULL,
                cached_at    TEXT NOT NULL
            );

            -- FTS5 full-text index over cached page snippets
            -- Used by the Phase-4 crawler to pick crawl targets
            CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(
                url,
                title,
                snippet,
                query_term,
                content='',        -- contentless; we only store FTS data
                tokenize='porter unicode61'
            );

            -- Shadow table: tracks which (url, query_term) pairs are in search_index.
            -- FTS5 virtual tables can't have UNIQUE constraints, so we guard here instead.
            CREATE TABLE IF NOT EXISTS fts_seen (
                url        TEXT NOT NULL,
                query_term TEXT NOT NULL,
                PRIMARY KEY (url, query_term)
            );

            CREATE INDEX IF NOT EXISTS idx_cache_query
                ON search_cache(query_key);

            CREATE INDEX IF NOT EXISTS idx_cache_cached_at
                ON search_cache(cached_at DESC);
        """)


# ── Query normalisation ───────────────────────────────────────────────────────

def _normalise(query: str) -> str:
    """
    Lowercase, collapse whitespace, strip punctuation.
    Ensures 'Python  Tutorial' and 'python tutorial' share the same cache slot.
    """
    q = query.lower().strip()
    q = re.sub(r"[^\w\s]", "", q)
    q = re.sub(r"\s+", " ", q)
    return q


# ── Public API ────────────────────────────────────────────────────────────────

def query_cache(query: str) -> list[dict[str, Any]] | None:
    """
    Check whether a recent result set exists for *query*.

    Returns
    ───────
    list[dict]   — cached results if found and fresh (< 24 h old)
    None         — cache miss; caller must fetch from Brave
    """
    key = _normalise(query)
    cutoff = (datetime.now(timezone.utc) - CACHE_TTL).isoformat()

    with db_ctx() as conn:
        row = conn.execute(
            """
            SELECT results_json, cached_at
              FROM search_cache
             WHERE query_key = ?
               AND cached_at > ?
            """,
            (key, cutoff),
        ).fetchone()

    if row is None:
        return None

    return json.loads(row["results_json"])


def cache_results(query: str, results: list[dict[str, Any]]) -> None:
    """
    Persist Brave results for *query* into both:
      1. search_cache  — for fast exact-query deduplication
      2. search_index  — FTS5 table for full-text search and crawler seeding

    Designed to be called immediately after a successful Brave API response,
    before the results are returned to the client.
    """
    if not results:
        return

    key = _normalise(query)
    now = datetime.now(timezone.utc).isoformat()
    results_json = json.dumps(results, ensure_ascii=False)

    with db_ctx() as conn:
        # Upsert into search_cache (replace stale entry if query_key exists)
        conn.execute(
            """
            INSERT INTO search_cache (query_key, results_json, cached_at)
                 VALUES (?, ?, ?)
            ON CONFLICT(query_key) DO UPDATE SET
                results_json = excluded.results_json,
                cached_at    = excluded.cached_at
            """,
            (key, results_json, now),
        )

        # Index each result into FTS5 for full-text retrieval
        # Brave results typically contain: url, title, description
        for item in results:
            url     = item.get("url", "")
            title   = item.get("title", "")
            snippet = item.get("description", item.get("snippet", ""))

            if not url:
                continue

            # Only insert into FTS5 if this (url, query_term) pair is new.
            # INSERT OR IGNORE on the shadow table returns rowcount=0 on a dupe.
            inserted = conn.execute(
                "INSERT OR IGNORE INTO fts_seen (url, query_term) VALUES (?, ?)",
                (url, key),
            ).rowcount
            if inserted:
                conn.execute(
                    """
                    INSERT INTO search_index (url, title, snippet, query_term)
                         VALUES (?, ?, ?, ?)
                    """,
                    (url, title, snippet, key),
                )


def search_local_index(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """
    Full-text search over the FTS5 index.

    Useful for offline mode or as an additional result source once the
    Phase-4 crawler has built up a meaningful local index.

    Returns a list of {url, title, snippet, rank} dicts ordered by relevance.
    """
    key = _normalise(query)
    if not key:
        return []

    # FTS5 match syntax: wrap in quotes to handle multi-word queries safely
    fts_query = f'"{key}"'

    with db_ctx() as conn:
        try:
            rows = conn.execute(
                """
                SELECT url, title, snippet, rank
                  FROM search_index
                 WHERE search_index MATCH ?
                 ORDER BY rank
                 LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            # FTS5 MATCH can raise on malformed queries; return empty gracefully
            return []

    return [dict(r) for r in rows]


def evict_stale_cache(older_than: timedelta = timedelta(days=7)) -> int:
    """
    Remove cache entries older than *older_than*.
    Call periodically (e.g. a nightly background task) to keep the DB lean.

    Returns the number of rows deleted.
    """
    cutoff = (datetime.now(timezone.utc) - older_than).isoformat()
    with db_ctx() as conn:
        cur = conn.execute(
            "DELETE FROM search_cache WHERE cached_at < ?", (cutoff,)
        )
    return cur.rowcount


# ── Legacy API (required by main.py) ─────────────────────────────────────────

DB_PATH = Path(__file__).parent / "index.db"

def _legacy_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS search_history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            query      TEXT NOT NULL,
            searched_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS visit_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            url         TEXT NOT NULL,
            title       TEXT NOT NULL DEFAULT '',
            visited_at  TEXT NOT NULL,
            visit_count INTEGER NOT NULL DEFAULT 1,
            UNIQUE(url)
        )
    """)
    conn.commit()
    return conn

def log_search(query: str) -> None:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    conn = _legacy_conn()
    conn.execute("INSERT INTO search_history (query, searched_at) VALUES (?, ?)", (query, now))
    conn.commit(); conn.close()

def log_visit(url: str, title: str = "") -> None:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    conn = _legacy_conn()
    existing = conn.execute("SELECT id, visit_count FROM visit_history WHERE url=?", (url,)).fetchone()
    if existing:
        conn.execute("UPDATE visit_history SET visit_count=visit_count+1, visited_at=?, title=CASE WHEN ?!='' THEN ? ELSE title END WHERE id=?",
                     (now, title, title, existing["id"]))
    else:
        conn.execute("INSERT INTO visit_history (url, title, visited_at) VALUES (?,?,?)", (url, title, now))
    conn.commit(); conn.close()

def get_recent_searches(limit: int = 20) -> list:
    conn = _legacy_conn()
    rows = conn.execute("SELECT query, searched_at FROM search_history ORDER BY searched_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_visit_history(limit: int = 50) -> list:
    conn = _legacy_conn()
    rows = conn.execute("SELECT url, title, visited_at, visit_count FROM visit_history ORDER BY visited_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
