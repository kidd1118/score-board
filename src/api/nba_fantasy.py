"""Daily fantasy mini-game.

Pick one player for each of PG, SG, SF, PF, C and a sixth man from the teams
playing on a given (US) date. Each player's fantasy points come from that
day's box score:

    points x2, rebounds x3, assists x4, steals x5, blocks x5, turnovers x-2

A player locks when his game starts: he can no longer be picked, and if he is
already in the lineup he can no longer be swapped out.

Lineups are stored in a JSON file (single user), keyed by date.
"""
import json
import os
import threading
from pathlib import Path

from nba_api.live.nba.endpoints import boxscore
from nba_api.stats.endpoints import leaguedashplayerstats, playerindex

import nba_games
from cache import cached

REQUEST_TIMEOUT = 15

SLOTS = ["PG", "SG", "SF", "PF", "C", "6TH"]
# Position letter a player needs for each slot (None = anyone).
SLOT_POSITION = {"PG": "G", "SG": "G", "SF": "F", "PF": "F", "C": "C", "6TH": None}
SCORING = {"pts": 2, "reb": 3, "ast": 4, "stl": 5, "blk": 5, "tov": -2}

SCHEDULED, LIVE, FINAL = 1, 2, 3
PLAYERS_TTL = 6 * 60 * 60
LIVE_BOX_TTL = 15
FINAL_BOX_TTL = 6 * 60 * 60

DATA_FILE = Path(os.environ.get("FANTASY_DATA_FILE", Path(__file__).parent / "data" / "fantasy.json"))
_store_lock = threading.Lock()


class LineupError(ValueError):
    """A lineup change that breaks the game rules."""


# ---------- scoring ----------

def fantasy_points(stats):
    return sum(stats.get(key, 0) * weight for key, weight in SCORING.items())


def eligible_slots(position):
    letters = set((position or "").split("-"))
    return [slot for slot in SLOTS if SLOT_POSITION[slot] is None or SLOT_POSITION[slot] in letters]


# ---------- storage ----------

def _load():
    if not DATA_FILE.exists():
        return {}
    return json.loads(DATA_FILE.read_text())


def _save(data):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = DATA_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    tmp.replace(DATA_FILE)


# ---------- NBA data ----------

def _fetch_players():
    index = playerindex.PlayerIndex(active_nullable=1, timeout=REQUEST_TIMEOUT).get_normalized_dict()["PlayerIndex"]
    averages = leaguedashplayerstats.LeagueDashPlayerStats(
        per_mode_detailed="PerGame", timeout=REQUEST_TIMEOUT
    ).get_normalized_dict()["LeagueDashPlayerStats"]
    avg_by_id = {a["PLAYER_ID"]: a for a in averages}
    players = []
    for p in index:
        if not p.get("TEAM_ID"):
            continue
        a = avg_by_id.get(p["PERSON_ID"], {})
        avg = {key: a.get(key.upper()) or 0 for key in SCORING}
        players.append({
            "id": p["PERSON_ID"],
            "name": f"{p.get('PLAYER_FIRST_NAME', '')} {p.get('PLAYER_LAST_NAME', '')}".strip(),
            "teamId": p["TEAM_ID"],
            "team": p.get("TEAM_ABBREVIATION"),
            "position": p.get("POSITION") or "",
            "gp": a.get("GP") or 0,
            "min": a.get("MIN") or 0,
            "avg": avg,
            "avgPoints": round(fantasy_points(avg), 1),
        })
    return players


def _players():
    return cached("fantasy-players", lambda _: PLAYERS_TTL, _fetch_players)


def _fetch_box(game_id):
    game = boxscore.BoxScore(game_id, timeout=REQUEST_TIMEOUT).get_dict()["game"]
    stats = {}
    for side in ("homeTeam", "awayTeam"):
        for p in game[side].get("players", []):
            s = p.get("statistics", {})
            stats[p["personId"]] = {
                "played": p.get("played") == "1",
                "pts": s.get("points", 0),
                "reb": s.get("reboundsTotal", 0),
                "ast": s.get("assists", 0),
                "stl": s.get("steals", 0),
                "blk": s.get("blocks", 0),
                "tov": s.get("turnovers", 0),
            }
    return {"status": game.get("gameStatus"), "players": stats}


def _box(game_id):
    return cached(
        ("box", game_id),
        lambda box: FINAL_BOX_TTL if box["status"] == FINAL else LIVE_BOX_TTL,
        lambda: _fetch_box(game_id),
    )


def _game_view(game, team_id):
    home = game["home"].get("id") == team_id
    opponent = game["away"] if home else game["home"]
    return {
        "id": game["id"],
        "status": game["status"],
        "statusText": game["statusText"],
        "startTimeUTC": game["startTimeUTC"],
        "home": home,
        "opponent": opponent.get("tricode"),
    }


def _games_by_team(date):
    by_team = {}
    for g in nba_games.get_games(date)["games"]:
        for side in ("home", "away"):
            team_id = g[side].get("id")
            if team_id:
                by_team[team_id] = g
    return by_team


# ---------- API ----------

def get_pool(date):
    """Players whose team plays on `date`, best average fantasy points first."""
    by_team = _games_by_team(date)
    pool = []
    for p in _players():
        game = by_team.get(p["teamId"])
        if not game:
            continue
        pool.append({
            **p,
            "slots": eligible_slots(p["position"]),
            "game": _game_view(game, p["teamId"]),
            "locked": game["status"] != SCHEDULED,
        })
    pool.sort(key=lambda p: p["avgPoints"], reverse=True)
    return {"date": date, "games": len({p["game"]["id"] for p in pool}), "players": pool}


def _slot_view(slot, pick, games_by_id):
    if not pick:
        return {"slot": slot, "player": None, "game": None, "stats": None, "points": 0, "locked": False}
    game = games_by_id.get(pick["gameId"])
    view = {
        "slot": slot,
        "player": {k: pick[k] for k in ("id", "name", "team", "position")},
        "game": _game_view(game, pick["teamId"]) if game else None,
        "stats": None,
        "points": 0,
        "locked": bool(game) and game["status"] != SCHEDULED,
    }
    if game and game["status"] != SCHEDULED:
        stats = _box(game["id"])["players"].get(pick["id"])
        if stats:
            view["stats"] = stats
            view["points"] = fantasy_points(stats)
        else:
            view["stats"] = {"played": False, **{k: 0 for k in SCORING}}
    return view


def get_lineup(date):
    with _store_lock:
        entry = _load().get(date, {})
    picks = entry.get("slots", {})
    games_by_id = {g["id"]: g for g in nba_games.get_games(date)["games"]} if picks else {}
    slots = [_slot_view(slot, picks.get(slot), games_by_id) for slot in SLOTS]
    total = sum(s["points"] for s in slots)

    picked_games = [s["game"] for s in slots if s["game"]]
    final = bool(picked_games) and all(g["status"] == FINAL for g in picked_games)
    if final and entry.get("finalTotal") != total:
        with _store_lock:
            data = _load()
            if date in data:
                data[date]["finalTotal"] = total
                _save(data)

    return {"date": date, "slots": slots, "total": total, "final": final, "scoring": SCORING}


def save_lineup(date, picks):
    """Replace the lineup for `date`. `picks` maps slot -> player id (or None)."""
    unknown = set(picks) - set(SLOTS)
    if unknown:
        raise LineupError(f"未知的位置：{', '.join(sorted(unknown))}")
    chosen = [pid for pid in picks.values() if pid]
    if len(chosen) != len(set(chosen)):
        raise LineupError("同一位球員只能選一次")

    by_team = _games_by_team(date)
    pool = {p["id"]: p for p in get_pool(date)["players"]}

    with _store_lock:
        data = _load()
        current = data.get(date, {}).get("slots", {})
        new_slots = {}
        for slot in SLOTS:
            new_id = picks.get(slot)
            old = current.get(slot)
            if old and old["id"] == new_id:
                new_slots[slot] = old
                continue
            if old:
                old_game = next((g for g in by_team.values() if g["id"] == old["gameId"]), None)
                if old_game and old_game["status"] != SCHEDULED:
                    raise LineupError(f"{old['name']} 的比賽已經開始，不能換下")
            if not new_id:
                continue
            player = pool.get(new_id)
            if not player:
                raise LineupError("這位球員當天沒有比賽")
            if player["locked"]:
                raise LineupError(f"{player['name']} 的比賽已經開始，不能選")
            if slot not in player["slots"]:
                raise LineupError(f"{player['name']}（{player['position']}）不能打 {slot}")
            new_slots[slot] = {
                "id": player["id"],
                "name": player["name"],
                "team": player["team"],
                "teamId": player["teamId"],
                "position": player["position"],
                "gameId": player["game"]["id"],
            }
        if new_slots:
            data[date] = {"slots": new_slots, "finalTotal": None}
        else:
            data.pop(date, None)
        _save(data)
    return get_lineup(date)


def get_history():
    """Every date with a saved lineup, newest first, with its total."""
    with _store_lock:
        data = _load()
    history = []
    for date in sorted(data, reverse=True):
        entry = data[date]
        total = entry.get("finalTotal")
        if total is None:
            total = get_lineup(date)["total"]
        history.append({
            "date": date,
            "players": len(entry.get("slots", {})),
            "total": total,
            "final": entry.get("finalTotal") is not None,
        })
    return {"history": history}
