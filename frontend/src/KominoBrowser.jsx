import { useState, useEffect, useRef, useCallback } from "react";

const API = "http://127.0.0.1:8000";

// ── Tiny helpers ──────────────────────────────────────────────────────────────
const isURL = (s) => /^https?:\/\//i.test(s) || /^[\w-]+\.\w{2,}/.test(s);
const toURL  = (s) => /^https?:\/\//i.test(s) ? s : `https://${s}`;
const fmt    = (iso) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
const fmtDate = (d) => {
  const today = new Date().toISOString().slice(0, 10);
  const yest  = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
  if (d === today) return "Today";
  if (d === yest)  return "Yesterday";
  return d;
};

// ── Icons (inline SVG) ────────────────────────────────────────────────────────
const Icon = ({ d, size = 16, stroke = "currentColor", fill = "none" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={fill}
    stroke={stroke} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
    <path d={d} />
  </svg>
);
const SearchIcon   = () => <Icon d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z" />;
const GlobeIcon    = () => <Icon d="M12 2a10 10 0 1 0 0 20A10 10 0 0 0 12 2zM2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />;
const ClockIcon    = () => <Icon d="M12 2a10 10 0 1 0 0 20A10 10 0 0 0 12 2zm0 5v5l3 3" />;
const BookmarkIcon = (p) => <Icon d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" fill={p.filled ? "currentColor" : "none"} />;
const PlusIcon     = () => <Icon d="M12 5v14M5 12h14" />;
const XIcon        = () => <Icon d="M18 6 6 18M6 6l12 12" />;
const ChevronIcon  = ({ dir = "right" }) => <Icon d={dir === "right" ? "M9 18l6-6-6-6" : "M15 18l-6-6 6-6"} />;
const SpinnerIcon  = () => (
  <svg width={18} height={18} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
    <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"
      style={{ animation: "spin 1s linear infinite", transformOrigin: "center" }} />
  </svg>
);

// ── Styles (injected once) ────────────────────────────────────────────────────
const STYLES = `
  @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:       #080810;
    --surface:  #0f0f1a;
    --card:     #13131f;
    --border:   #1c1c2e;
    --border2:  #252538;
    --accent:   #7c6aff;
    --accent2:  #00e5c0;
    --warn:     #ffaa44;
    --text:     #e2e2f0;
    --muted:    #5a5a78;
    --muted2:   #3a3a55;
    --red:      #ff5f6d;
    --font:     'Syne', sans-serif;
    --mono:     'JetBrains Mono', monospace;
  }

  body { background: var(--bg); color: var(--text); font-family: var(--font); overflow: hidden; height: 100vh; }

  @keyframes spin { to { transform: rotate(360deg); } }
  @keyframes fadeUp { from { opacity:0; transform:translateY(10px); } to { opacity:1; transform:translateY(0); } }
  @keyframes slideIn { from { transform:translateX(-100%); opacity:0; } to { transform:translateX(0); opacity:1; } }
  @keyframes pulse { 0%,100%{opacity:.4} 50%{opacity:1} }
  @keyframes shimmer { 0%{background-position:-200% 0} 100%{background-position:200% 0} }

  .kb-root {
    display: grid;
    grid-template-rows: 52px 1fr;
    height: 100vh;
    position: relative;
  }

  /* ── TOP BAR ── */
  .kb-topbar {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 0 14px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    position: relative;
    z-index: 30;
  }

  .kb-logo {
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 500;
    color: var(--accent2);
    letter-spacing: .12em;
    white-space: nowrap;
    user-select: none;
  }

  .kb-bar-wrap {
    flex: 1;
    position: relative;
  }

  .kb-bar {
    width: 100%;
    background: var(--card);
    border: 1px solid var(--border2);
    border-radius: 8px;
    padding: 0 14px 0 38px;
    height: 34px;
    color: var(--text);
    font-family: var(--mono);
    font-size: 12px;
    outline: none;
    transition: border-color .2s, box-shadow .2s;
  }
  .kb-bar:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(124,106,255,.15);
  }
  .kb-bar-icon {
    position: absolute;
    left: 11px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--muted);
    pointer-events: none;
    display: flex;
  }

  .kb-icon-btn {
    background: none;
    border: none;
    color: var(--muted);
    cursor: pointer;
    padding: 6px;
    border-radius: 6px;
    display: flex;
    align-items: center;
    transition: color .15s, background .15s;
    flex-shrink: 0;
  }
  .kb-icon-btn:hover { color: var(--text); background: var(--border); }
  .kb-icon-btn.active { color: var(--accent2); }

  /* ── TABS ── */
  .kb-tabs {
    display: flex;
    align-items: center;
    gap: 4px;
    overflow-x: auto;
    flex: 1;
    scrollbar-width: none;
  }
  .kb-tabs::-webkit-scrollbar { display: none; }

  .kb-tab {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 11px;
    font-family: var(--mono);
    cursor: pointer;
    white-space: nowrap;
    max-width: 140px;
    background: none;
    border: 1px solid transparent;
    color: var(--muted);
    transition: all .15s;
    user-select: none;
  }
  .kb-tab.active {
    background: var(--border);
    border-color: var(--border2);
    color: var(--text);
  }
  .kb-tab:hover:not(.active) { color: var(--text); background: var(--muted2); }
  .kb-tab-title { overflow: hidden; text-overflow: ellipsis; flex: 1; }
  .kb-tab-close {
    opacity: 0;
    display: flex;
    padding: 1px;
    border-radius: 3px;
    transition: opacity .15s, background .15s;
    flex-shrink: 0;
  }
  .kb-tab:hover .kb-tab-close { opacity: 1; }
  .kb-tab-close:hover { background: var(--muted2); }

  .kb-tab-new {
    background: none;
    border: 1px dashed var(--muted2);
    border-radius: 6px;
    color: var(--muted);
    cursor: pointer;
    padding: 3px 7px;
    font-size: 11px;
    display: flex;
    align-items: center;
    transition: all .15s;
    flex-shrink: 0;
  }
  .kb-tab-new:hover { border-color: var(--accent); color: var(--accent); }

  /* ── MAIN CONTENT ── */
  .kb-body {
    display: flex;
    overflow: hidden;
    position: relative;
  }

  /* ── DRAWER ── */
  .kb-drawer {
    width: 300px;
    background: var(--surface);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    animation: slideIn .25s ease;
    overflow: hidden;
    flex-shrink: 0;
  }

  .kb-drawer-head {
    padding: 14px 16px 10px;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .kb-drawer-head h2 {
    font-size: 11px;
    font-family: var(--mono);
    color: var(--accent2);
    letter-spacing: .15em;
    text-transform: uppercase;
  }

  .kb-drawer-tabs {
    display: flex;
    border-bottom: 1px solid var(--border);
  }
  .kb-dtab {
    flex: 1;
    padding: 8px;
    font-size: 11px;
    font-family: var(--mono);
    text-align: center;
    cursor: pointer;
    color: var(--muted);
    border: none;
    background: none;
    border-bottom: 2px solid transparent;
    transition: all .15s;
  }
  .kb-dtab.active { color: var(--accent); border-bottom-color: var(--accent); }

  .kb-drawer-scroll {
    flex: 1;
    overflow-y: auto;
    scrollbar-width: thin;
    scrollbar-color: var(--muted2) transparent;
    padding: 8px 0;
  }

  .kb-date-group { padding: 10px 16px 4px; }
  .kb-date-label {
    font-size: 10px;
    font-family: var(--mono);
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: .12em;
  }

  .kb-hist-item {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    padding: 8px 16px;
    cursor: pointer;
    transition: background .12s;
    border-left: 2px solid transparent;
  }
  .kb-hist-item:hover { background: var(--card); border-left-color: var(--accent); }
  .kb-hist-dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    background: var(--accent2);
    margin-top: 5px;
    flex-shrink: 0;
    opacity: .5;
  }
  .kb-hist-info { flex: 1; min-width: 0; }
  .kb-hist-title {
    font-size: 12px;
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .kb-hist-url {
    font-size: 10px;
    font-family: var(--mono);
    color: var(--muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    margin-top: 1px;
  }
  .kb-hist-meta {
    font-size: 10px;
    font-family: var(--mono);
    color: var(--muted2);
    display: flex;
    align-items: center;
    gap: 4px;
    margin-top: 2px;
  }
  .kb-visit-badge {
    background: var(--muted2);
    border-radius: 3px;
    padding: 1px 4px;
    color: var(--muted);
    font-size: 9px;
  }

  .kb-bm-item {
    display: flex;
    align-items: center;
    padding: 8px 16px;
    gap: 8px;
    cursor: pointer;
    transition: background .12s;
  }
  .kb-bm-item:hover { background: var(--card); }
  .kb-bm-icon { color: var(--warn); flex-shrink: 0; }
  .kb-bm-info { flex: 1; min-width: 0; }
  .kb-bm-title { font-size: 12px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .kb-bm-url { font-size: 10px; font-family: var(--mono); color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .kb-bm-del {
    background: none; border: none; color: var(--muted2);
    cursor: pointer; padding: 3px; border-radius: 4px;
    display: flex; opacity: 0; transition: opacity .15s, color .15s;
  }
  .kb-bm-item:hover .kb-bm-del { opacity: 1; }
  .kb-bm-del:hover { color: var(--red); }

  .kb-empty {
    padding: 32px 16px;
    text-align: center;
    color: var(--muted);
    font-size: 12px;
    font-family: var(--mono);
  }

  /* ── CONTENT AREA ── */
  .kb-content {
    flex: 1;
    overflow-y: auto;
    scrollbar-width: thin;
    scrollbar-color: var(--muted2) transparent;
    position: relative;
  }

  /* ── HOME / SEARCH RESULTS ── */
  .kb-home {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: calc(100vh - 52px);
    padding: 40px 20px;
    animation: fadeUp .4s ease;
  }
  .kb-home-logo {
    font-family: var(--mono);
    font-size: 13px;
    font-weight: 500;
    color: var(--accent2);
    letter-spacing: .2em;
    margin-bottom: 6px;
    opacity: .7;
  }
  .kb-home-title {
    font-size: clamp(2rem, 6vw, 3.5rem);
    font-weight: 800;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 8px;
    text-align: center;
  }
  .kb-home-sub {
    font-size: 13px;
    color: var(--muted);
    margin-bottom: 40px;
    font-family: var(--mono);
  }
  .kb-home-search {
    width: 100%;
    max-width: 540px;
    position: relative;
  }
  .kb-home-input {
    width: 100%;
    background: var(--surface);
    border: 1px solid var(--border2);
    border-radius: 12px;
    padding: 14px 20px 14px 50px;
    color: var(--text);
    font-family: var(--mono);
    font-size: 14px;
    outline: none;
    transition: border-color .2s, box-shadow .2s;
  }
  .kb-home-input:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 4px rgba(124,106,255,.12);
  }
  .kb-home-search-icon {
    position: absolute;
    left: 16px; top: 50%;
    transform: translateY(-50%);
    color: var(--muted);
    display: flex;
  }
  .kb-home-btn {
    position: absolute;
    right: 8px; top: 50%;
    transform: translateY(-50%);
    background: var(--accent);
    border: none;
    color: white;
    padding: 6px 14px;
    border-radius: 8px;
    font-family: var(--mono);
    font-size: 12px;
    cursor: pointer;
    transition: opacity .15s;
  }
  .kb-home-btn:hover { opacity: .85; }

  /* ── RESULTS ── */
  .kb-results {
    padding: 20px;
    max-width: 780px;
    margin: 0 auto;
    animation: fadeUp .3s ease;
  }
  .kb-results-meta {
    font-size: 11px;
    font-family: var(--mono);
    color: var(--muted);
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .kb-source-badge {
    font-size: 9px;
    padding: 2px 6px;
    border-radius: 4px;
    font-family: var(--mono);
  }
  .kb-source-badge.brave { background: rgba(255,170,68,.12); color: var(--warn); border: 1px solid rgba(255,170,68,.2); }
  .kb-source-badge.cache { background: rgba(0,229,192,.12); color: var(--accent2); border: 1px solid rgba(0,229,192,.2); }
  .kb-source-badge.local { background: rgba(124,106,255,.12); color: var(--accent); border: 1px solid rgba(124,106,255,.2); }

  .kb-result-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 10px;
    cursor: pointer;
    transition: border-color .2s, transform .15s;
    position: relative;
    overflow: hidden;
    animation: fadeUp .3s ease both;
  }
  .kb-result-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 3px; height: 100%;
    background: linear-gradient(to bottom, var(--accent), var(--accent2));
    opacity: 0;
    transition: opacity .2s;
  }
  .kb-result-card:hover { border-color: var(--accent); transform: translateX(2px); }
  .kb-result-card:hover::before { opacity: 1; }

  .kb-result-src {
    font-size: 10px;
    font-family: var(--mono);
    color: var(--accent2);
    margin-bottom: 4px;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .kb-result-src-dot { width: 5px; height: 5px; border-radius: 50%; background: var(--accent2); }
  .kb-result-title {
    font-size: 15px;
    font-weight: 700;
    color: var(--text);
    margin-bottom: 6px;
    line-height: 1.3;
  }
  .kb-result-title:hover { color: var(--accent); }
  .kb-result-desc { font-size: 12px; color: var(--muted); line-height: 1.6; }
  .kb-result-actions {
    display: flex;
    gap: 8px;
    margin-top: 10px;
    opacity: 0;
    transition: opacity .15s;
  }
  .kb-result-card:hover .kb-result-actions { opacity: 1; }
  .kb-result-action {
    font-size: 10px;
    font-family: var(--mono);
    padding: 3px 8px;
    border-radius: 4px;
    border: 1px solid var(--border2);
    background: var(--surface);
    color: var(--muted);
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 4px;
    transition: all .15s;
  }
  .kb-result-action:hover { border-color: var(--accent); color: var(--accent); }

  /* ── READER VIEW ── */
  .kb-reader {
    padding: 40px 20px;
    max-width: 680px;
    margin: 0 auto;
    animation: fadeUp .3s ease;
  }
  .kb-reader-url {
    font-size: 10px;
    font-family: var(--mono);
    color: var(--accent2);
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .kb-reader-title {
    font-size: clamp(1.4rem, 3vw, 2rem);
    font-weight: 800;
    line-height: 1.2;
    margin-bottom: 24px;
    color: var(--text);
  }
  .kb-reader-content {
    font-size: 14px;
    line-height: 1.85;
    color: #c0c0d8;
    white-space: pre-wrap;
    font-family: var(--font);
  }
  .kb-reader-meta {
    font-size: 10px;
    font-family: var(--mono);
    color: var(--muted);
    margin-bottom: 28px;
    padding-bottom: 20px;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 12px;
  }

  /* ── LOADING SKELETON ── */
  .kb-skeleton {
    height: 90px;
    background: linear-gradient(90deg, var(--card) 25%, var(--border) 50%, var(--card) 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite;
    border-radius: 12px;
    margin-bottom: 10px;
  }

  /* ── ERROR / TOAST ── */
  .kb-toast {
    position: fixed;
    bottom: 20px; right: 20px;
    background: var(--surface);
    border: 1px solid var(--red);
    color: var(--red);
    padding: 10px 16px;
    border-radius: 8px;
    font-size: 12px;
    font-family: var(--mono);
    z-index: 100;
    animation: fadeUp .2s ease;
  }

  /* ── LOADING indicator in bar ── */
  .kb-loading-bar {
    position: absolute;
    bottom: 0; left: 0;
    height: 2px;
    background: linear-gradient(90deg, var(--accent), var(--accent2));
    animation: shimmer 1.2s infinite;
    background-size: 200% 100%;
  }
`;

let tabCounter = 1;
const makeTab = (url = "", title = "New Tab") => ({
  id: ++tabCounter, url, title, view: "home", results: [], reader: null
});

// ── Main Component ─────────────────────────────────────────────────────────────
export default function KominoBrowser() {
  const [tabs, setTabs]             = useState([makeTab()]);
  const [activeTabId, setActiveTabId] = useState(tabs[0].id);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTab, setDrawerTab]   = useState("history"); // "history" | "bookmarks"
  const [history, setHistory]       = useState({ grouped: {}, total: 0 });
  const [bookmarks, setBookmarks]   = useState([]);
  const [loading, setLoading]       = useState(false);
  const [toast, setToast]           = useState(null);
  const [barValue, setBarValue]     = useState("");
  const barRef = useRef(null);

  const activeTab = tabs.find(t => t.id === activeTabId) || tabs[0];

  // sync bar with active tab url
  useEffect(() => { setBarValue(activeTab.url || ""); }, [activeTabId]);

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  };

  const updateTab = useCallback((id, patch) => {
    setTabs(prev => prev.map(t => t.id === id ? { ...t, ...patch } : t));
  }, []);

  const fetchHistory = async () => {
    try {
      const r = await fetch(`${API}/history`);
      const d = await r.json();
      setHistory(d);
    } catch { /* silent */ }
  };

  const fetchBookmarks = async () => {
    try {
      const r = await fetch(`${API}/bookmarks`);
      const d = await r.json();
      setBookmarks(d.bookmarks || []);
    } catch { /* silent */ }
  };

  useEffect(() => {
    if (drawerOpen) {
      fetchHistory();
      fetchBookmarks();
    }
  }, [drawerOpen]);

  // ── Search ──
  const doSearch = async (query, tabId = activeTabId) => {
    setLoading(true);
    updateTab(tabId, { view: "results", results: [], url: query, title: query });
    try {
      const r = await fetch(`${API}/search?q=${encodeURIComponent(query)}`);
      const d = await r.json();
      const results = d.results || [];
      const source  = d.source || "brave";
      updateTab(tabId, { results, source, title: `"${query}"` });
      // log to history
      fetch(`${API}/history`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: `search:${query}`, title: query }),
      }).catch(() => {});
    } catch (e) {
      showToast("Search failed — is the backend running?");
    }
    setLoading(false);
  };

  // ── Browse ──
  const doBrowse = async (rawUrl, tabId = activeTabId) => {
    const url = toURL(rawUrl);
    setLoading(true);
    updateTab(tabId, { view: "reader", reader: null, url, title: url });
    try {
      const r = await fetch(`${API}/browse?url=${encodeURIComponent(url)}`);
      if (!r.ok) throw new Error(r.statusText);
      const d = await r.json();
      updateTab(tabId, { reader: d, title: d.title || url });
      // log to history
      fetch(`${API}/history`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: d.url, title: d.title }),
      }).catch(() => {});
    } catch (e) {
      showToast(`Could not load page: ${e.message}`);
      updateTab(tabId, { view: "home" });
    }
    setLoading(false);
  };

  // ── Submit bar ──
  const handleSubmit = (e) => {
    e?.preventDefault?.();
    const v = barValue.trim();
    if (!v) return;
    if (isURL(v)) doBrowse(v);
    else doSearch(v);
  };

  // ── Bookmark toggle ──
  const addBookmark = async (url, title) => {
    try {
      await fetch(`${API}/bookmarks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, title }),
      });
      fetchBookmarks();
    } catch { showToast("Bookmark failed."); }
  };

  const delBookmark = async (id) => {
    await fetch(`${API}/bookmarks/${id}`, { method: "DELETE" });
    fetchBookmarks();
  };

  const isBookmarked = bookmarks.some(b => b.url === activeTab.url);

  // ── Tab management ──
  const addTab = () => {
    const t = makeTab();
    setTabs(prev => [...prev, t]);
    setActiveTabId(t.id);
    setBarValue("");
  };

  const closeTab = (id) => {
    if (tabs.length === 1) { setTabs([makeTab()]); return; }
    const idx = tabs.findIndex(t => t.id === id);
    const next = tabs[idx === 0 ? 1 : idx - 1];
    setTabs(prev => prev.filter(t => t.id !== id));
    if (activeTabId === id) setActiveTabId(next.id);
  };

  const selectTab = (id) => {
    setActiveTabId(id);
    const t = tabs.find(t => t.id === id);
    setBarValue(t?.url || "");
  };

  return (
    <>
      <style>{STYLES}</style>
      <div className="kb-root">

        {/* TOP BAR */}
        <div className="kb-topbar">
          <span className="kb-logo">K://</span>

          {/* Tabs */}
          <div className="kb-tabs">
            {tabs.map(tab => (
              <div
                key={tab.id}
                className={`kb-tab ${tab.id === activeTabId ? "active" : ""}`}
                onClick={() => selectTab(tab.id)}
              >
                <span className="kb-tab-title">{tab.title}</span>
                <span className="kb-tab-close" onClick={e => { e.stopPropagation(); closeTab(tab.id); }}>
                  <XIcon />
                </span>
              </div>
            ))}
            <button className="kb-tab-new" onClick={addTab}><PlusIcon /></button>
          </div>

          {/* Address bar */}
          <div className="kb-bar-wrap" style={{ maxWidth: 420 }}>
            <span className="kb-bar-icon">
              {loading ? <SpinnerIcon /> : isURL(barValue) ? <GlobeIcon /> : <SearchIcon />}
            </span>
            <input
              ref={barRef}
              className="kb-bar"
              value={barValue}
              onChange={e => setBarValue(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleSubmit()}
              placeholder="Search or enter URL…"
              spellCheck={false}
            />
            {loading && <div className="kb-loading-bar" style={{ width: "60%" }} />}
          </div>

          {/* Actions */}
          <button
            className={`kb-icon-btn ${isBookmarked ? "active" : ""}`}
            title="Bookmark"
            onClick={() => activeTab.url && addBookmark(activeTab.url, activeTab.title)}
          >
            <BookmarkIcon filled={isBookmarked} />
          </button>
          <button
            className={`kb-icon-btn ${drawerOpen ? "active" : ""}`}
            onClick={() => setDrawerOpen(o => !o)}
            title="History & Bookmarks"
          >
            <ClockIcon />
          </button>
        </div>

        {/* BODY */}
        <div className="kb-body">

          {/* DRAWER */}
          {drawerOpen && (
            <div className="kb-drawer">
              <div className="kb-drawer-head">
                <h2>{drawerTab === "history" ? "History" : "Bookmarks"}</h2>
                <button className="kb-icon-btn" onClick={() => setDrawerOpen(false)}><ChevronIcon dir="left" /></button>
              </div>
              <div className="kb-drawer-tabs">
                <button className={`kb-dtab ${drawerTab === "history" ? "active" : ""}`} onClick={() => { setDrawerTab("history"); fetchHistory(); }}>History</button>
                <button className={`kb-dtab ${drawerTab === "bookmarks" ? "active" : ""}`} onClick={() => { setDrawerTab("bookmarks"); fetchBookmarks(); }}>Bookmarks</button>
              </div>
              <div className="kb-drawer-scroll">
                {drawerTab === "history" && (
                  Object.keys(history.grouped).length === 0
                    ? <div className="kb-empty">No history yet.<br/>Start browsing.</div>
                    : Object.entries(history.grouped).map(([date, items]) => (
                      <div key={date}>
                        <div className="kb-date-group">
                          <div className="kb-date-label">{fmtDate(date)}</div>
                        </div>
                        {items.map(item => (
                          <div key={item.id} className="kb-hist-item"
                            onClick={() => { isURL(item.url) ? doBrowse(item.url) : doSearch(item.url.replace("search:", "")); setDrawerOpen(false); }}>
                            <div className="kb-hist-dot" />
                            <div className="kb-hist-info">
                              <div className="kb-hist-title">{item.title || item.url}</div>
                              <div className="kb-hist-url">{item.url}</div>
                              <div className="kb-hist-meta">
                                {fmt(item.visited_at)}
                                {item.visit_count > 1 && <span className="kb-visit-badge">×{item.visit_count}</span>}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    ))
                )}
                {drawerTab === "bookmarks" && (
                  bookmarks.length === 0
                    ? <div className="kb-empty">No bookmarks yet.<br/>Click ★ to save a page.</div>
                    : bookmarks.map(bm => (
                      <div key={bm.id} className="kb-bm-item"
                        onClick={() => { doBrowse(bm.url); setDrawerOpen(false); }}>
                        <span className="kb-bm-icon"><BookmarkIcon filled /></span>
                        <div className="kb-bm-info">
                          <div className="kb-bm-title">{bm.title || bm.url}</div>
                          <div className="kb-bm-url">{bm.url}</div>
                        </div>
                        <button className="kb-bm-del" onClick={e => { e.stopPropagation(); delBookmark(bm.id); }}>
                          <XIcon />
                        </button>
                      </div>
                    ))
                )}
              </div>
            </div>
          )}

          {/* CONTENT */}
          <div className="kb-content">

            {/* HOME */}
            {activeTab.view === "home" && (
              <div className="kb-home">
                <div className="kb-home-logo">komino_dev</div>
                <div className="kb-home-title">KominoBrowser</div>
                <div className="kb-home-sub">// private · self-hosted · yours</div>
                <div className="kb-home-search">
                  <span className="kb-home-search-icon"><SearchIcon /></span>
                  <input
                    className="kb-home-input"
                    placeholder="Search the web or enter a URL…"
                    autoFocus
                    value={barValue}
                    onChange={e => setBarValue(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && handleSubmit()}
                  />
                  <button className="kb-home-btn" onClick={handleSubmit}>Go</button>
                </div>
              </div>
            )}

            {/* RESULTS */}
            {activeTab.view === "results" && (
              <div className="kb-results">
                <div className="kb-results-meta">
                  {activeTab.results.length} results for "{activeTab.url}"
                  {activeTab.source && (
                    <span className={`kb-source-badge ${activeTab.source}`}>
                      {activeTab.source === "local_cache" ? "cached" : activeTab.source}
                    </span>
                  )}
                </div>
                {loading && [1,2,3].map(i => <div key={i} className="kb-skeleton" style={{ animationDelay: `${i * .1}s` }} />)}
                {activeTab.results.map((r, i) => (
                  <div
                    key={i}
                    className="kb-result-card"
                    style={{ animationDelay: `${i * 0.04}s` }}
                    onClick={() => doBrowse(r.url)}
                  >
                    <div className="kb-result-src">
                      <div className="kb-result-src-dot" />
                      {new URL(r.url).hostname}
                    </div>
                    <div className="kb-result-title">{r.title}</div>
                    <div className="kb-result-desc">{r.description || r.snippet || ""}</div>
                    <div className="kb-result-actions">
                      <button className="kb-result-action" onClick={e => { e.stopPropagation(); addBookmark(r.url, r.title); }}>
                        <BookmarkIcon /> Save
                      </button>
                      <button className="kb-result-action" onClick={e => { e.stopPropagation(); navigator.clipboard?.writeText(r.url); }}>
                        Copy URL
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* READER */}
            {activeTab.view === "reader" && (
              <div className="kb-reader">
                {loading && [1,2,3].map(i => <div key={i} className="kb-skeleton" style={{ height: 20, marginBottom: 12, animationDelay: `${i*.1}s` }} />)}
                {activeTab.reader && (
                  <>
                    <div className="kb-reader-url">
                      <GlobeIcon />
                      {activeTab.reader.url}
                    </div>
                    <div className="kb-reader-title">{activeTab.reader.title}</div>
                    <div className="kb-reader-meta">
                      <span>Fetched {new Date(activeTab.reader.fetched_at).toLocaleString()}</span>
                      <button className="kb-result-action" onClick={() => addBookmark(activeTab.reader.url, activeTab.reader.title)}>
                        <BookmarkIcon /> Bookmark
                      </button>
                    </div>
                    <div className="kb-reader-content">{activeTab.reader.content}</div>
                  </>
                )}
              </div>
            )}

          </div>
        </div>

        {toast && <div className="kb-toast">{toast}</div>}
      </div>
    </>
  );
}
