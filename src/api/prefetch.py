"""Keep today's NBA data warm in the background.

Without this, NBA data is fetched when someone opens a page and the cached
copy has expired, so traffic to NBA grows with the number of visitors and open
tabs, and the top-players board fires many box score requests at once.

Here one background thread refreshes, one request at a time:

- the live board (today's games) every LIVE_INTERVAL seconds while a game is
  live, otherwise every IDLE_INTERVAL seconds
- the box score of every live game on each of those rounds; finished games once
- players and season averages, game logs and the injury report when their
  cache runs out

The page-facing cache lifetimes are raised while it runs, so visitors are
served from memory instead of triggering requests themselves. It also backs up
the fantasy database once a day.

Set NBA_PREFETCH=0 to turn it off.
"""
import logging
import os
import threading
import time

import nba_fantasy
import nba_games
import nba_injuries
import store
from cache import describe, is_cached

LIVE_INTERVAL = 15
IDLE_INTERVAL = 60
PAUSE = 1.0  # between box score requests, so NBA sees a trickle, not a burst
BACKUP_INTERVAL = 24 * 60 * 60
# While the prefetcher keeps things fresh, a visitor only fetches if it falls behind.
WARM_TTL = 90

log = logging.getLogger("prefetch")

_thread = None
_stop = threading.Event()
_status = {
    "enabled": False,
    "lastRound": None,
    "lastError": None,
    "liveGames": 0,
    "boxScores": 0,
    "rounds": 0,
}


def enabled():
    return os.environ.get("NBA_PREFETCH", "1") not in ("0", "false", "no")


def status():
    return dict(_status)


def _refresh_round():
    """One pass over today's data. Returns how many games are live."""
    board = nba_games.get_games(force=True)
    date = board["date"]
    games = board["games"]
    live = [g for g in games if g["status"] == nba_fantasy.LIVE]
    boxes = 0
    for game in games:
        if _stop.is_set():
            break
        if game["status"] == nba_fantasy.SCHEDULED:
            continue
        # Finished games keep their box score for hours; refetch only once it expires.
        if game["status"] == nba_fantasy.FINAL and is_cached(nba_fantasy._box_key(game)):
            continue
        nba_fantasy._box(game, force=True)
        boxes += 1
        _stop.wait(PAUSE)

    # These refetch only when their own cache has run out.
    nba_fantasy._players()
    nba_fantasy._game_logs(date)
    if any(g["status"] == nba_fantasy.SCHEDULED for g in games):
        nba_injuries.statuses_for(date)

    _status.update(liveGames=len(live), boxScores=boxes)
    return len(live)


def _backup_if_due():
    if time.time() - store.last_backup_time() >= BACKUP_INTERVAL:
        path = store.backup()
        log.info("fantasy database backed up to %s", path)


def _run():
    while not _stop.is_set():
        live = 0
        try:
            live = _refresh_round()
            _status["lastError"] = None
        except Exception as e:  # keep going; the cache serves the last good data
            _status["lastError"] = describe(e)
            log.warning("prefetch round failed: %s", describe(e))
        _status["lastRound"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        _status["rounds"] += 1
        try:
            _backup_if_due()
        except Exception as e:
            log.warning("fantasy database backup failed: %s", e)
        _stop.wait(LIVE_INTERVAL if live else IDLE_INTERVAL)


def start():
    global _thread
    if not enabled() or (_thread and _thread.is_alive()):
        return
    nba_games.LIVE_TTL = WARM_TTL
    nba_games.UNFINISHED_DAY_TTL = WARM_TTL
    nba_fantasy.LIVE_BOX_TTL = WARM_TTL
    _stop.clear()
    _status["enabled"] = True
    _thread = threading.Thread(target=_run, name="nba-prefetch", daemon=True)
    _thread.start()


def stop():
    _stop.set()
    if _thread:
        _thread.join(timeout=5)
