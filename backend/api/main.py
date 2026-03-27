"""
KominoSearch — FastAPI Backend v0.4
Now with: ad blocking, URL cleaning, debouncing, HTTPS enforcement
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from search.ddg_client import ddg_search, ddg_news
from search.indexer import log_search, log_visit, get_recent_searches, get_visit_history
from search.ranker import rank_and_merge
from search.tor_manager import tor
from search.adblocker import clean_url, filter_results, is_blocked

from api.routes.browse import router as browse_router

app = FastAPI(title="KominoSearch", version="0.4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

app.include_router(browse_router)

class VisitPayload(BaseModel):
    url: str
    title: str = ""

class TimerPayload(BaseModel):
    seconds: int

# ── Search ────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"status": "KominoSearch running", "version": "0.4.0",
            "stay_hidden": tor.is_running()}

@app.get("/search")
async def search(
    q: str = Query(..., min_length=1),
    count: int = Query(10, ge=1, le=20),
    region: str = Query("wt-wt"),
    safe: str = Query("moderate"),
    private: bool = Query(False),
    fresh: bool = Query(False),
    timelimit: Optional[str] = Query(None),
):
    if not private:
        log_search(q)
    use_tor = tor.is_running()
    ddg_error = None
    ddg_results = []

    try:
        ddg_results = ddg_search(q, count=count, region=region,
                                  safesearch=safe, timelimit=timelimit,
                                  use_tor=use_tor)
    except Exception as e:
        ddg_error = str(e)

    # Filter ads + clean URLs before ranking
    ddg_results = filter_results(ddg_results)

    merged = ddg_results if fresh else rank_and_merge(q, ddg_results)

    return {
        "query": q,
        "results": merged,
        "total": len(merged),
        "private_mode": private,
        "routed_via_tor": use_tor,
        "ddg_error": ddg_error,
    }

@app.get("/search/news")
async def search_news(
    q: str = Query(..., min_length=1),
    count: int = Query(5, ge=1, le=15),
    region: str = Query("wt-wt"),
    timelimit: str = Query("w"),
    private: bool = Query(False),
):
    if not private:
        log_search(f"[news] {q}")
    use_tor = tor.is_running()
    try:
        results = ddg_news(q, count=count, region=region,
                           timelimit=timelimit, use_tor=use_tor)
        results = filter_results(results)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"query": q, "results": results, "total": len(results),
            "routed_via_tor": use_tor}

# ── URL cleaner endpoint ──────────────────────────────────────────────────────

@app.get("/clean")
async def clean(url: str = Query(...)):
    """
    Clean any URL — debounce, strip tracking params, HTTPS upgrade, check block.
    Use this before navigating to any link.
    """
    return clean_url(url)

@app.get("/blocked")
async def check_blocked(url: str = Query(...)):
    """Check if a URL is blocked by the ad/tracker filter lists."""
    return {"url": url, "blocked": is_blocked(url)}

# ── Visit + History ───────────────────────────────────────────────────────────

@app.post("/visit")
async def record_visit(payload: VisitPayload, private: bool = Query(False)):
    # Clean the URL before logging
    cleaned = clean_url(payload.url)
    if cleaned["blocked"]:
        return {"status": "blocked", "url": payload.url}
    if not private:
        log_visit(url=cleaned["clean"], title=payload.title)
    return {"status": "logged" if not private else "skipped"}

@app.get("/history/searches")
async def search_history(limit: int = Query(20)):
    return {"history": get_recent_searches(limit)}

@app.get("/history/visits")
async def visit_history(limit: int = Query(50)):
    return {"history": get_visit_history(limit)}

@app.delete("/history/searches")
async def clear_searches():
    import sqlite3
    from search.indexer import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM search_history")
    conn.commit(); conn.close()
    return {"status": "cleared"}

@app.delete("/history/visits")
async def clear_visits():
    import sqlite3
    from search.indexer import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM visit_history")
    conn.commit(); conn.close()
    return {"status": "cleared"}

# ── Stay Hidden ───────────────────────────────────────────────────────────────

@app.post("/hidden/start")
async def hidden_start():
    return tor.start()

@app.post("/hidden/stop")
async def hidden_stop():
    return tor.stop()

@app.post("/hidden/rotate")
async def hidden_rotate():
    if not tor.is_running():
        raise HTTPException(400, "Tor not running. Call /hidden/start first.")
    return tor.rotate_now()

@app.post("/hidden/timer")
async def hidden_timer(payload: TimerPayload):
    if not tor.is_running():
        raise HTTPException(400, "Tor not running. Call /hidden/start first.")
    return tor.set_timer(payload.seconds)

@app.get("/hidden/status")
async def hidden_status():
    return tor.status()

# ── Bookmarks ─────────────────────────────────────────────────────────────────

import sqlite3
from pathlib import Path

BM_DB = Path("search/index.db")

def _bm_conn():
    conn = sqlite3.connect(BM_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bookmarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL DEFAULT '',
            saved_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn

class BookmarkIn(BaseModel):
    url: str
    title: str = ""

@app.post("/bookmarks", status_code=201)
def add_bookmark(payload: BookmarkIn):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    conn = _bm_conn()
    try:
        cur = conn.execute(
            "INSERT INTO bookmarks (url, title, saved_at) VALUES (?,?,?)",
            (payload.url, payload.title, now)
        )
        conn.commit()
        return {"id": cur.lastrowid, "url": payload.url, "title": payload.title, "saved_at": now}
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Already bookmarked.")
    finally:
        conn.close()

@app.get("/bookmarks")
def list_bookmarks():
    conn = _bm_conn()
    rows = conn.execute("SELECT * FROM bookmarks ORDER BY saved_at DESC").fetchall()
    conn.close()
    return {"bookmarks": [dict(r) for r in rows], "total": len(rows)}

@app.delete("/bookmarks/{bookmark_id}")
def delete_bookmark(bookmark_id: int):
    conn = _bm_conn()
    exists = conn.execute("SELECT id FROM bookmarks WHERE id=?", (bookmark_id,)).fetchone()
    if not exists:
        conn.close()
        raise HTTPException(404, "Bookmark not found.")
    conn.execute("DELETE FROM bookmarks WHERE id=?", (bookmark_id,))
    conn.commit()
    conn.close()
    return {"deleted": True, "id": bookmark_id}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
