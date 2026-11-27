"""Fetch NBA games and normalize them into one shape for the dashboard.

Today's games come from the live scoreboard (real-time scores, clock, leaders).
Any other date comes from the stats ScoreboardV2 endpoint, which also stands in
for today when the live scoreboard (cdn.nba.com) is unreachable.
"""
import re
from datetime import date as date_cls, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from nba_api.live.nba.endpoints import scoreboard
from nba_api.stats.endpoints import scoreboardv2

from cache import cached

REQUEST_TIMEOUT = 15
EASTERN = ZoneInfo("America/New_York")

# Cache TTLs (seconds). A day whose games are all final never changes.
LIVE_TTL = 15
UNFINISHED_DAY_TTL = 60
FINISHED_DAY_TTL = 6 * 60 * 60


def _day_ttl(result):
    games = result["games"]
    if games and all(g["status"] == 3 for g in games):
        return FINISHED_DAY_TTL
    return UNFINISHED_DAY_TTL


def _eastern_start_utc(game_date, status_text):
    """Scheduled stats games only give '7:30 pm ET'; turn that into a UTC timestamp."""
    m = re.match(r"(\d{1,2}):(\d{2})\s*([ap]m)\s*ET", status_text or "", re.I)
    if not m:
        return None
    hour, minute = int(m.group(1)) % 12, int(m.group(2))
    if m.group(3).lower() == "pm":
        hour += 12
    day = date_cls.fromisoformat(game_date)
    local = datetime(day.year, day.month, day.day, hour, minute, tzinfo=EASTERN)
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_clock(clock):
    """Convert ISO-8601 duration like 'PT05M12.00S' to '5:12'."""
    if not clock:
        return ""
    m = re.match(r"PT(\d+)M(\d+(?:\.\d+)?)S", clock)
    if not m:
        return clock
    minutes, seconds = int(m.group(1)), float(m.group(2))
    if minutes == 0 and seconds < 60 and seconds % 1:
        return f"{seconds:.1f}"
    return f"{minutes}:{int(seconds):02d}"


def _live_team(team):
    return {
        "id": team.get("teamId"),
        "tricode": team.get("teamTricode"),
        "city": team.get("teamCity"),
        "name": team.get("teamName"),
        "record": f"{team.get('wins', 0)}-{team.get('losses', 0)}",
        "score": team.get("score"),
        "periods": [p.get("score") for p in team.get("periods", [])],
    }


def _live_leader(leader):
    if not leader or not leader.get("name"):
        return None
    return {
        "name": leader.get("name"),
        "points": leader.get("points"),
        "rebounds": leader.get("rebounds"),
        "assists": leader.get("assists"),
    }


def _fetch_live_games():
    board = scoreboard.ScoreBoard(timeout=REQUEST_TIMEOUT).get_dict()["scoreboard"]
    games = []
    for g in board.get("games", []):
        leaders = g.get("gameLeaders") or {}
        games.append({
            "id": g.get("gameId"),
            "status": g.get("gameStatus"),
            "statusText": (g.get("gameStatusText") or "").strip(),
            "period": g.get("period"),
            "clock": _parse_clock(g.get("gameClock")),
            "startTimeUTC": g.get("gameTimeUTC"),
            "arena": (g.get("arena") or {}).get("arenaName"),
            "home": _live_team(g.get("homeTeam", {})),
            "away": _live_team(g.get("awayTeam", {})),
            "leaders": {
                "home": _live_leader(leaders.get("homeLeaders")),
                "away": _live_leader(leaders.get("awayLeaders")),
            },
        })
    return {"date": board.get("gameDate"), "source": "live", "games": games}


def _stats_team(line):
    if not line:
        return {}
    periods = [line.get(f"PTS_QTR{i}") for i in range(1, 5)]
    periods += [line.get(f"PTS_OT{i}") for i in range(1, 11) if line.get(f"PTS_OT{i}")]
    return {
        "id": line.get("TEAM_ID"),
        "tricode": line.get("TEAM_ABBREVIATION"),
        "city": line.get("TEAM_CITY_NAME"),
        "name": line.get("TEAM_NAME"),
        "record": line.get("TEAM_WINS_LOSSES"),
        "score": line.get("PTS"),
        "periods": [p for p in periods if p is not None],
    }


def get_live_games(force=False):
    return cached("live", lambda _: LIVE_TTL, _fetch_live_games, force)


def _fetch_games_by_date(game_date: str):
    data = scoreboardv2.ScoreboardV2(
        game_date=game_date, timeout=REQUEST_TIMEOUT
    ).get_normalized_dict()
    lines = {(l["GAME_ID"], l["TEAM_ID"]): l for l in data.get("LineScore", [])}
    games = []
    seen = set()
    for h in sorted(data.get("GameHeader", []), key=lambda h: h.get("GAME_SEQUENCE") or 0):
        gid = h["GAME_ID"]
        # The stats API sometimes repeats a game's header row.
        if gid in seen:
            continue
        seen.add(gid)
        games.append({
            "id": gid,
            "status": h.get("GAME_STATUS_ID"),
            "statusText": (h.get("GAME_STATUS_TEXT") or "").strip(),
            "period": h.get("LIVE_PERIOD"),
            "clock": (h.get("LIVE_PC_TIME") or "").strip(),
            "startTimeUTC": _eastern_start_utc(game_date, h.get("GAME_STATUS_TEXT"))
            if h.get("GAME_STATUS_ID") == 1 else None,
            "arena": h.get("ARENA_NAME"),
            "home": _stats_team(lines.get((gid, h.get("HOME_TEAM_ID")))),
            "away": _stats_team(lines.get((gid, h.get("VISITOR_TEAM_ID")))),
            "leaders": {"home": None, "away": None},
        })
    return {"date": game_date, "source": "stats", "games": games}


def get_games_by_date(game_date: str, force=False):
    return cached(("date", game_date), _day_ttl, lambda: _fetch_games_by_date(game_date), force)


def _board_date():
    """Best guess at the live board's date: the NBA keeps showing last night's games
    into the early morning US Eastern time."""
    return (datetime.now(EASTERN) - timedelta(hours=6)).date().isoformat()


def get_games(game_date: Optional[str] = None, force=False):
    """Games for a date (YYYY-MM-DD, already validated). Uses the live feed for the live board's date."""
    try:
        live = get_live_games(force)
    except Exception:
        live = None
    if live and (not game_date or game_date == live["date"]):
        return live
    return get_games_by_date(game_date or _board_date(), force)
