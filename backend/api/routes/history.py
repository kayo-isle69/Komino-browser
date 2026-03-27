"""
api/routes/history.py
─────────────────────
Handles visit history and bookmarks for KominoBrowser.

Tables
──────
  visits    (id, url, title, visited_at, visit_count)
  bookmarks (id, url, title, saved_at)

Endpoints
─────────
  POST   /history            — log a visit or increment visit_count
  GET    /history            — last 50 visits, grouped by date
  POST   /bookmarks          — save a URL
  GET    /bookmarks          — list all bookmarks
  DELETE /bookmarks/{id}     — remove a bookmark

visit_count is the Phase-4 crawl-priority signal:
  high visit_count → crawler indexes that page first.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, HttpUrl

# ── Config ────────────────────────────────────────────────────────────────────

DB_PATH = Path(__file__).resolve().parents[2] / "search" / "index.db"

router = APIRouter(prefix="", tags=["history", "bookmarks"])


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db_ctx() -> Generator[sqlite3.Connection, None, None]:
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_tables() -> None:
    """Create tables if they don't exist. Called at startup."""
    with db_ctx() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS visits (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                url         TEXT    NOT NULL,
                title       TEXT    NOT NULL DEFAULT '',
                visited_at  TEXT    NOT NULL,
                visit_count INTEGER NOT NULL DEFAULT 1,
                UNIQUE(url)
            );

            CREATE TABLE IF NOT EXISTS bookmarks (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                url      TEXT NOT NULL UNIQUE,
                title    TEXT NOT NULL DEFAULT '',
                saved_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_visits_visited_at
                ON visits(visited_at DESC);

            CREATE INDEX IF NOT EXISTS idx_visits_visit_count
                ON visits(visit_count DESC);
        """)


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class VisitIn(BaseModel):
    url: str
    title: str = ""


class BookmarkIn(BaseModel):
    url: str
    title: str = ""


# ── Endpoints — History ───────────────────────────────────────────────────────

@router.post("/history", status_code=status.HTTP_200_OK)
def log_visit(payload: VisitIn) -> dict:
    """
    Log a page visit.
    If the URL has been visited before, increment visit_count and update
    visited_at. Otherwise create a new row with visit_count = 1.
    """
    now = datetime.now(timezone.utc).isoformat()

    with db_ctx() as conn:
        existing = conn.execute(
            "SELECT id, visit_count FROM visits WHERE url = ?",
            (payload.url,),
        ).fetchone()

        if existing:
            conn.execute(
                """
                UPDATE visits
                   SET visit_count = visit_count + 1,
                       visited_at  = ?,
                       title       = CASE WHEN ? != '' THEN ? ELSE title END
                 WHERE id = ?
                """,
                (now, payload.title, payload.title, existing["id"]),
            )
            visit_count = existing["visit_count"] + 1
            row_id = existing["id"]
        else:
            cur = conn.execute(
                "INSERT INTO visits (url, title, visited_at, visit_count) VALUES (?, ?, ?, 1)",
                (payload.url, payload.title, now),
            )
            visit_count = 1
            row_id = cur.lastrowid

    return {
        "id": row_id,
        "url": payload.url,
        "title": payload.title,
        "visited_at": now,
        "visit_count": visit_count,
    }


@router.get("/history")
def get_history() -> dict:
    """
    Return the 50 most recent visits, grouped by calendar date (UTC).

    Response shape:
    {
        "grouped": {
            "2025-03-26": [ {id, url, title, visited_at, visit_count}, ... ],
            "2025-03-25": [ ... ],
        },
        "total": 50
    }
    """
    with db_ctx() as conn:
        rows = conn.execute(
            """
            SELECT id, url, title, visited_at, visit_count
              FROM visits
             ORDER BY visited_at DESC
             LIMIT 50
            """
        ).fetchall()

    grouped: dict[str, list] = {}
    for row in rows:
        # visited_at is a full ISO string; take the date part for grouping
        date_key = row["visited_at"][:10]
        grouped.setdefault(date_key, []).append(dict(row))

    return {"grouped": grouped, "total": len(rows)}


# ── Endpoints — Bookmarks ─────────────────────────────────────────────────────

@router.post("/bookmarks", status_code=status.HTTP_201_CREATED)
def add_bookmark(payload: BookmarkIn) -> dict:
    """
    Save a URL as a bookmark.
    Returns 409 if the URL is already bookmarked.
    """
    now = datetime.now(timezone.utc).isoformat()

    with db_ctx() as conn:
        existing = conn.execute(
            "SELECT id FROM bookmarks WHERE url = ?", (payload.url,)
        ).fetchone()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="URL already bookmarked.",
            )

        cur = conn.execute(
            "INSERT INTO bookmarks (url, title, saved_at) VALUES (?, ?, ?)",
            (payload.url, payload.title, now),
        )

    return {
        "id": cur.lastrowid,
        "url": payload.url,
        "title": payload.title,
        "saved_at": now,
    }


@router.get("/bookmarks")
def list_bookmarks() -> dict:
    """Return all bookmarks ordered by most recently saved."""
    with db_ctx() as conn:
        rows = conn.execute(
            "SELECT id, url, title, saved_at FROM bookmarks ORDER BY saved_at DESC"
        ).fetchall()

    return {"bookmarks": [dict(r) for r in rows], "total": len(rows)}


@router.delete("/bookmarks/{bookmark_id}", status_code=status.HTTP_200_OK)
def delete_bookmark(bookmark_id: int) -> dict:
    """Remove a bookmark by id. Returns 404 if not found."""
    with db_ctx() as conn:
        existing = conn.execute(
            "SELECT id FROM bookmarks WHERE id = ?", (bookmark_id,)
        ).fetchone()

        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Bookmark {bookmark_id} not found.",
            )

        conn.execute("DELETE FROM bookmarks WHERE id = ?", (bookmark_id,))

    return {"deleted": True, "id": bookmark_id}


# ── Startup hook (call from api/main.py) ──────────────────────────────────────

def setup_history_tables() -> None:
    """Import and call this from your FastAPI lifespan/startup handler."""
    init_tables()
