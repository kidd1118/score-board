"""Fetch NBA games and normalize them into one shape for the dashboard.

Today's games come from the live scoreboard (real-time scores, clock, leaders).
Any other date comes from the stats ScoreboardV2 endpoint.
"""
import re
from datetime import date as date_cls
from typing import Optional

from nba_api.live.nba.endpoints import scoreboard
from nba_api.stats.endpoints import scoreboardv2

REQUEST_TIMEOUT = 15


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


def get_live_games():
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


def get_games_by_date(game_date: str):
    data = scoreboardv2.ScoreboardV2(
        game_date=game_date, timeout=REQUEST_TIMEOUT
    ).get_normalized_dict()
    lines = {(l["GAME_ID"], l["TEAM_ID"]): l for l in data.get("LineScore", [])}
    games = []
    for h in sorted(data.get("GameHeader", []), key=lambda h: h.get("GAME_SEQUENCE") or 0):
        gid = h["GAME_ID"]
        games.append({
            "id": gid,
            "status": h.get("GAME_STATUS_ID"),
            "statusText": (h.get("GAME_STATUS_TEXT") or "").strip(),
            "period": h.get("LIVE_PERIOD"),
            "clock": (h.get("LIVE_PC_TIME") or "").strip(),
            "startTimeUTC": None,
            "arena": h.get("ARENA_NAME"),
            "home": _stats_team(lines.get((gid, h.get("HOME_TEAM_ID")))),
            "away": _stats_team(lines.get((gid, h.get("VISITOR_TEAM_ID")))),
            "leaders": {"home": None, "away": None},
        })
    return {"date": game_date, "source": "stats", "games": games}


def get_games(game_date: Optional[str] = None):
    """Games for a date (YYYY-MM-DD). Uses the live feed when the date is the live board's date."""
    if game_date:
        date_cls.fromisoformat(game_date)  # raises ValueError on bad input
    try:
        live = get_live_games()
    except Exception:
        if not game_date:
            raise
        live = None
    if live and (not game_date or game_date == live["date"]):
        return live
    return get_games_by_date(game_date)
