"""Daily fantasy mini-game.

Pick one player for each of PG, SG, SF, PF, C and a sixth man from the teams
playing on a given (US) date. Each player's fantasy points come from that
day's box score:

    points x2, rebounds x3, assists x4, steals x5, blocks x5, turnovers x-2

The six players' real salaries (salaries.json) may total at most SALARY_CAP.

A player locks when their game starts: they can no longer be picked, and if they are
already in the lineup they can no longer be swapped out.

Several people can play. Each registers a nickname and gets a secret token
(kept by the browser) that is required to change their own lineup. Anyone can
see the leaderboards and other lineups, but a pick stays hidden from others
until that player's game starts, so lineups can't be copied.

Data is stored in a JSON file.
"""
import json
import os
import secrets
import threading
from pathlib import Path

from nba_api.live.nba.endpoints import boxscore
from nba_api.stats.endpoints import leaguedashplayerstats, playerindex

import nba_games
import nba_injuries
from cache import cached
from names import name_key

REQUEST_TIMEOUT = 15

SLOTS = ["PG", "SG", "SF", "PF", "C", "6TH"]
# Position letter a player needs for each slot (None = anyone).
SLOT_POSITION = {"PG": "G", "SG": "G", "SF": "F", "PF": "F", "C": "C", "6TH": None}
SCORING = {
    "fg2m": 2,   # made two-pointers
    "fg3m": 3,   # made three-pointers
    "ftm": 1,    # made free throws
    "reb": 3,
    "ast": 4,
    "stl": 5,
    "blk": 5,
    "tov": -2,
    "pf": -2,    # personal fouls
    "miss": -1,  # missed field goals and free throws
}
# Bump when SCORING changes so settled totals saved under the old rules are recomputed.
SCORING_VERSION = 3

# Total salary a lineup may carry, using players' real salaries (salaries.json).
SALARY_CAP = 148_465_000
SALARY_FILE = Path(__file__).parent / "salaries.json"
# Players missing from salaries.json (mostly two-way and 10-day contracts) count
# as the 2026-27 rookie minimum.
UNLISTED_SALARY = 1_357_763
# Basketball-Reference team codes that differ from the NBA's.
BBREF_TEAMS = {"BRK": "BKN", "CHO": "CHA", "PHO": "PHX"}

SCHEDULED, LIVE, FINAL = 1, 2, 3
PLAYERS_TTL = 6 * 60 * 60
LIVE_BOX_TTL = 15
FINAL_BOX_TTL = 6 * 60 * 60

NAME_MAX = 20
LEGACY_NAME = "玩家1"  # owner of lineups saved before the game was multiplayer

DATA_FILE = Path(os.environ.get("FANTASY_DATA_FILE", Path(__file__).parent / "data" / "fantasy.json"))
_store_lock = threading.Lock()


class LineupError(ValueError):
    """A request that breaks the game rules (bad lineup, bad name)."""


class NameTaken(LineupError):
    """Someone already registered that name."""


# ---------- scoring ----------

def fantasy_points(stats):
    """A player's points never go below 0, however bad the night."""
    return max(0, round(sum(stats.get(key, 0) * weight for key, weight in SCORING.items()), 1))


def scoring_stats(fgm, fga, fg3m, ftm, fta, **counts):
    """Turn shooting makes/attempts plus counting stats into the SCORING keys."""
    return {
        "pts": 2 * (fgm - fg3m) + 3 * fg3m + ftm,
        "fg2m": fgm - fg3m,
        "fg3m": fg3m,
        "ftm": ftm,
        "miss": (fga - fgm) + (fta - ftm),
        **counts,
    }


def eligible_slots(position):
    letters = set((position or "").split("-"))
    return [slot for slot in SLOTS if SLOT_POSITION[slot] is None or SLOT_POSITION[slot] in letters]


# ---------- storage ----------
#
# {
#   "users":   {key: {"name": display name, "token": secret | null}},
#   "lineups": {date: {key: {"slots": {...}, "finalTotal": n | null}}}
# }
# `key` is the case-folded name, so "Leo" and "leo" are the same player.

def _empty():
    return {"users": {}, "lineups": {}}


def _load():
    if not DATA_FILE.exists():
        return _empty()
    data = json.loads(DATA_FILE.read_text())
    if "lineups" not in data:
        # Single-player format ({date: lineup}): hand those lineups to an unclaimed
        # player; the first person to register that name takes it over.
        key = user_key(LEGACY_NAME)
        migrated = _empty()
        if data:
            migrated["users"][key] = {"name": LEGACY_NAME, "token": None}
            migrated["lineups"] = {date: {key: entry} for date, entry in data.items()}
        return migrated
    return data


def _save(data):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = DATA_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    tmp.replace(DATA_FILE)


# ---------- players (people playing the game) ----------

def user_key(name):
    return " ".join(name.split()).casefold()


def _clean_name(name):
    """Collapse whitespace and enforce the nickname rules."""
    name = " ".join((name or "").split())
    if not name:
        raise LineupError("請輸入暱稱")
    if len(name) > NAME_MAX:
        raise LineupError(f"暱稱最多 {NAME_MAX} 個字")
    if any(not ch.isprintable() for ch in name):
        raise LineupError("暱稱不能包含特殊字元")
    return name


def register(name):
    """Create a player and return {name, token}. The token is the only credential."""
    name = _clean_name(name)
    key = user_key(name)
    token = secrets.token_urlsafe(18)
    with _store_lock:
        data = _load()
        existing = data["users"].get(key)
        if existing and existing.get("token"):
            raise NameTaken(f"「{existing['name']}」已經有人使用")
        data["users"][key] = {"name": existing["name"] if existing else name, "token": token}
        _save(data)
    return {"name": data["users"][key]["name"], "token": token}


def rename(key, new_name):
    """Change a player's nickname, keeping their token and every saved lineup. Returns {name}."""
    new_name = _clean_name(new_name)
    new_key = user_key(new_name)
    with _store_lock:
        data = _load()
        user = data["users"].get(key)
        if user is None:
            raise LineupError("找不到這位玩家")
        # Changing only capitalization or spacing keeps the same key.
        if new_key != key:
            if new_key in data["users"]:
                raise NameTaken(f"「{data['users'][new_key]['name']}」已經有人使用")
            data["users"][new_key] = data["users"].pop(key)
            for entries in data["lineups"].values():
                if key in entries:
                    entries[new_key] = entries.pop(key)
        data["users"][new_key]["name"] = new_name
        _save(data)
    return {"name": new_name}


def user_for_token(token):
    """The player key a token belongs to, or None."""
    if not token:
        return None
    with _store_lock:
        users = _load()["users"]
    for key, user in users.items():
        if user.get("token") and secrets.compare_digest(user["token"], token):
            return key
    return None


def find_user(name):
    """(key, display name) for a player name, or None."""
    key = user_key(name)
    with _store_lock:
        user = _load()["users"].get(key)
    return (key, user["name"]) if user else None


# ---------- NBA data ----------

# ---------- salaries ----------

def _load_salaries():
    """(rows, season) where rows are (name key, team, salary)."""
    data = json.loads(SALARY_FILE.read_text())
    rows = [(name_key(p["name"]), BBREF_TEAMS.get(p["team"], p["team"]), p["salary"]) for p in data["players"]]
    return rows, data.get("season")


def _salary_for(rows, name, team):
    """(salary, listed) for a player on `team`."""
    key = name_key(name)
    same_name = [(t, salary) for k, t, salary in rows if k == key]
    if same_name:
        # Waived players also carry dead money from old teams; prefer the current team's contract.
        current = [salary for t, salary in same_name if t == team]
        return (current[0] if current else max(salary for _, salary in same_name)), True
    # Nicknames ("Ron" vs "Ronald"): same team, same last name, one first name a prefix of the other.
    first, last = key.split()[0], key.split()[-1]
    similar = [
        salary for k, t, salary in rows
        if t == team and k.split()[-1] == last and (k.startswith(first) or first.startswith(k.split()[0]))
    ]
    if len(similar) == 1:
        return similar[0], True
    return UNLISTED_SALARY, False


def salary_info():
    return {"cap": SALARY_CAP, "season": _load_salaries()[1], "unlisted": UNLISTED_SALARY}


def _fetch_players():
    index = playerindex.PlayerIndex(active_nullable=1, timeout=REQUEST_TIMEOUT).get_normalized_dict()["PlayerIndex"]
    averages = leaguedashplayerstats.LeagueDashPlayerStats(
        per_mode_detailed="PerGame", timeout=REQUEST_TIMEOUT
    ).get_normalized_dict()["LeagueDashPlayerStats"]
    avg_by_id = {a["PLAYER_ID"]: a for a in averages}
    salaries, _ = _load_salaries()
    players = []
    for p in index:
        if not p.get("TEAM_ID"):
            continue
        a = avg_by_id.get(p["PERSON_ID"], {})
        g = lambda k: a.get(k) or 0
        raw = scoring_stats(
            g("FGM"), g("FGA"), g("FG3M"), g("FTM"), g("FTA"),
            reb=g("REB"), ast=g("AST"), stl=g("STL"), blk=g("BLK"), tov=g("TOV"), pf=g("PF"),
        )
        avg = {k: round(v, 1) for k, v in raw.items()}
        name = f"{p.get('PLAYER_FIRST_NAME', '')} {p.get('PLAYER_LAST_NAME', '')}".strip()
        salary, listed = _salary_for(salaries, name, p.get("TEAM_ABBREVIATION"))
        players.append({
            "id": p["PERSON_ID"],
            "name": name,
            "salary": salary,
            "salaryListed": listed,
            "teamId": p["TEAM_ID"],
            "team": p.get("TEAM_ABBREVIATION"),
            "position": p.get("POSITION") or "",
            "gp": a.get("GP") or 0,
            "min": a.get("MIN") or 0,
            "avg": avg,
            "avgPoints": fantasy_points(raw),
        })
    return players


def _players():
    return cached("fantasy-players", lambda _: PLAYERS_TTL, _fetch_players)


def _pick_salary(pick):
    """Salary saved with a pick; picks made before the salary cap use today's salary."""
    if pick.get("salary") is not None:
        return pick["salary"]
    player = next((p for p in _players() if p["id"] == pick["id"]), None)
    return player["salary"] if player else UNLISTED_SALARY


def _money(amount):
    return f"${amount:,}"


def _fetch_box(game_id):
    game = boxscore.BoxScore(game_id, timeout=REQUEST_TIMEOUT).get_dict()["game"]
    stats = {}
    for side in ("homeTeam", "awayTeam"):
        for p in game[side].get("players", []):
            s = p.get("statistics", {})
            stats[p["personId"]] = {
                "played": p.get("played") == "1",
                **scoring_stats(
                    s.get("fieldGoalsMade", 0), s.get("fieldGoalsAttempted", 0),
                    s.get("threePointersMade", 0),
                    s.get("freeThrowsMade", 0), s.get("freeThrowsAttempted", 0),
                    reb=s.get("reboundsTotal", 0), ast=s.get("assists", 0), stl=s.get("steals", 0),
                    blk=s.get("blocks", 0), tov=s.get("turnovers", 0), pf=s.get("foulsPersonal", 0),
                ),
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
    upcoming = any(g["status"] == SCHEDULED for g in by_team.values())
    injuries = nba_injuries.statuses_for(date) if upcoming else None
    pool = []
    for p in _players():
        game = by_team.get(p["teamId"])
        if not game:
            continue
        locked = game["status"] != SCHEDULED
        pool.append({
            **p,
            "slots": eligible_slots(p["position"]),
            "game": _game_view(game, p["teamId"]),
            "locked": locked,
            # Availability only matters before tip-off.
            "injury": injuries.get(p["name"], p["team"]) if injuries and not locked else None,
        })
    pool.sort(key=lambda p: p["avgPoints"], reverse=True)
    return {
        "date": date,
        "games": len({p["game"]["id"] for p in pool}),
        "players": pool,
        "injuryReport": nba_injuries.report_info() if injuries else None,
    }


def _slot_view(slot, pick, games_by_id, reveal, injuries):
    empty = {
        "slot": slot, "player": None, "game": None, "stats": None, "points": 0,
        "locked": False, "hidden": False, "injury": None,
    }
    if not pick:
        return empty
    game = games_by_id.get(pick["gameId"])
    locked = bool(game) and game["status"] != SCHEDULED
    if not reveal and not locked:
        return {**empty, "hidden": True}
    view = {
        **empty,
        "player": {**{k: pick[k] for k in ("id", "name", "team", "position")}, "salary": _pick_salary(pick)},
        "game": _game_view(game, pick["teamId"]) if game else None,
        "locked": locked,
        "injury": injuries.get(pick["name"], pick["team"]) if injuries and not locked else None,
    }
    if locked:
        stats = _box(game["id"])["players"].get(pick["id"])
        if stats:
            view["stats"] = stats
            view["points"] = fantasy_points(stats)
        else:
            view["stats"] = {"played": False, "pts": 0, **{k: 0 for k in SCORING}}
    return view


def get_lineup(date, key, reveal=True):
    """One player's lineup for `date`. With reveal=False, picks whose game hasn't started are hidden."""
    with _store_lock:
        data = _load()
    entry = data["lineups"].get(date, {}).get(key, {})
    picks = entry.get("slots", {})
    games_by_id = {g["id"]: g for g in nba_games.get_games(date)["games"]} if picks else {}
    # Only look up injuries when a visible pick hasn't tipped off yet.
    upcoming = any(
        games_by_id.get(p["gameId"], {}).get("status") == SCHEDULED for p in picks.values()
    )
    injuries = nba_injuries.statuses_for(date) if upcoming and reveal else None
    slots = [_slot_view(slot, picks.get(slot), games_by_id, reveal, injuries) for slot in SLOTS]
    total = round(sum(s["points"] for s in slots), 1)
    salary = sum(_pick_salary(p) for p in picks.values())

    picked_games = [games_by_id.get(p["gameId"]) for p in picks.values()]
    final = bool(picked_games) and all(g and g["status"] == FINAL for g in picked_games)
    if final and (entry.get("finalTotal") != total or entry.get("scoringVersion") != SCORING_VERSION):
        with _store_lock:
            data = _load()
            stored = data["lineups"].get(date, {}).get(key)
            if stored:
                stored["finalTotal"] = total
                stored["scoringVersion"] = SCORING_VERSION
                _save(data)

    user = data["users"].get(key, {})
    return {
        "date": date,
        "player": user.get("name", key),
        "slots": slots,
        "total": total,
        "final": final,
        "scoring": SCORING,
        # Hidden picks count too, so others only learn the total, not who it is.
        "salary": {"used": salary, "cap": SALARY_CAP, "left": SALARY_CAP - salary},
    }


def save_lineup(date, key, picks):
    """Replace `key`'s lineup for `date`. `picks` maps slot -> player id (or None)."""
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
        day = data["lineups"].setdefault(date, {})
        current = day.get(key, {}).get("slots", {})
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
                "salary": player["salary"],
            }
        old_salary = sum(_pick_salary(p) for p in current.values())
        new_salary = sum(_pick_salary(p) for p in new_slots.values())
        # A lineup over the cap (e.g. saved before the cap existed) may still shrink.
        if new_salary > SALARY_CAP and new_salary > old_salary:
            raise LineupError(f"薪資總額 {_money(new_salary)} 超過上限 {_money(SALARY_CAP)}")
        if new_slots:
            day[key] = {"slots": new_slots, "finalTotal": None}
        else:
            day.pop(key, None)
        if not day:
            data["lineups"].pop(date, None)
        _save(data)
    return get_lineup(date, key)


def _rank(rows, score):
    """Competition ranking (1, 1, 3) by `score`, rows already sorted best first."""
    previous, rank = None, 0
    for i, row in enumerate(rows, start=1):
        if score(row) != previous:
            rank, previous = i, score(row)
        row["rank"] = rank
    return rows


def _day_results(date, entries):
    """{key: (total, final, players)} for every lineup on `date`, settling any that just finished."""
    results = {}
    for key, entry in entries.items():
        if entry.get("finalTotal") is not None and entry.get("scoringVersion") == SCORING_VERSION:
            results[key] = (entry["finalTotal"], True, len(entry.get("slots", {})))
        else:
            lineup = get_lineup(date, key)
            results[key] = (lineup["total"], lineup["final"], len(entry.get("slots", {})))
    return results


def get_daily_leaderboard(date):
    with _store_lock:
        data = _load()
    results = _day_results(date, data["lineups"].get(date, {}))
    rows = [
        {"player": data["users"].get(key, {}).get("name", key), "total": total, "final": final, "players": players}
        for key, (total, final, players) in results.items()
    ]
    rows.sort(key=lambda r: (-r["total"], r["player"].casefold()))
    return {"date": date, "entries": _rank(rows, lambda r: r["total"])}


def get_leaderboard():
    """Season standings over settled days: total points, days played, average, best day, daily wins."""
    with _store_lock:
        data = _load()
    stats = {}
    for date, entries in data["lineups"].items():
        results = _day_results(date, entries)
        settled = {key: total for key, (total, final, _) in results.items() if final}
        everyone_settled = len(settled) == len(results)
        best = max(settled.values()) if settled else None
        for key, total in settled.items():
            s = stats.setdefault(key, {"days": 0, "total": 0, "best": None, "wins": 0})
            s["days"] += 1
            s["total"] += total
            s["best"] = total if s["best"] is None else max(s["best"], total)
            if everyone_settled and len(settled) > 1 and total == best:
                s["wins"] += 1
    rows = [
        {
            "player": data["users"].get(key, {}).get("name", key),
            **s,
            "average": round(s["total"] / s["days"], 1),
        }
        for key, s in stats.items()
    ]
    rows.sort(key=lambda r: (-r["total"], -r["average"], r["player"].casefold()))
    return {"entries": _rank(rows, lambda r: r["total"])}


def get_history(key):
    """Every date `key` has a lineup, newest first, with total and daily rank."""
    with _store_lock:
        dates = sorted((d for d, entries in _load()["lineups"].items() if key in entries), reverse=True)
    name = find_user_name(key)
    history = []
    for date in dates:
        board = get_daily_leaderboard(date)["entries"]
        mine = next((r for r in board if r["player"] == name), None)
        if mine:
            history.append({"date": date, **mine, "entrants": len(board)})
    return {"history": history}


def find_user_name(key):
    with _store_lock:
        return _load()["users"].get(key, {}).get("name", key)
