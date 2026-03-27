"""
search/tor_manager.py
Stub Tor manager — keeps the rest of the app working without Tor installed.
Real Tor routing can be wired in later via stem + privoxy.
"""


class TorManager:
    def __init__(self):
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def start(self) -> dict:
        self._running = False   # flip to True when real Tor is wired
        return {"status": "tor_stub", "running": self._running,
                "note": "Tor not configured yet. Privacy via DDG only."}

    def stop(self) -> dict:
        self._running = False
        return {"status": "stopped"}

    def rotate_now(self) -> dict:
        return {"status": "stub", "rotated": False}

    def set_timer(self, seconds: int) -> dict:
        return {"status": "stub", "timer_set": False}

    def status(self) -> dict:
        return {"running": self._running, "mode": "stub"}


tor = TorManager()