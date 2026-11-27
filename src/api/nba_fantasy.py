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

Data is stored in SQLite (see store.py).
"""
import datetime as dt
import json
import re
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from nba_api.live.nba.endpoints import boxscore
from nba_api.stats.endpoints import boxscoretraditionalv3, leaguedashplayerstats, playergamelogs, playerindex

import nba_games
import nba_injuries
import store
from cache import ERROR_BACKOFF, cached, with_retry
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
LIVE_BOX_TTL = 30  # matches the page's refresh, so each refresh asks NBA at most once
FINAL_BOX_TTL = 6 * 60 * 60
TOP_PLAYERS = 10
RECENT_GAMES = 5
GAME_LOG_TTL = 60 * 60

NAME_MAX = 20


class LineupError(ValueError):
    """A request that breaks the game rules (bad lineup, bad name)."""


class NameTaken(LineupError):
    """Someone already registered that name."""


class GameNotFound(LookupError):
    """No game with that id on that date."""


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
# store.load() returns everything in this shape:
# {
#   "users":   {key: {"name": display name, "token": secret | null}},
#   "lineups": {date: {key: {"slots": {...}, "finalTotal": n | null, "scoringVersion", "pickPoints"}}}
# }
# `key` is the case-folded name, so "Leo" and "leo" are the same player.

_load = store.load
user_key = store.user_key


# ---------- players (people playing the game) ----------


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
    with store.writing() as conn:
        existing = store.get_user(conn, key)
        if existing and existing.get("token"):
            raise NameTaken(f"「{existing['name']}」已經有人使用")
        # An unclaimed player (lineups saved before multiplayer) keeps its name.
        name = existing["name"] if existing else name
        store.put_user(conn, key, name, token)
    return {"name": name, "token": token}


def rename(key, new_name):
    """Change a player's nickname, keeping their token and every saved lineup. Returns {name}."""
    new_name = _clean_name(new_name)
    new_key = user_key(new_name)
    with store.writing() as conn:
        if store.get_user(conn, key) is None:
            raise LineupError("找不到這位玩家")
        # Changing only capitalization or spacing keeps the same key.
        if new_key != key:
            taken = store.get_user(conn, new_key)
            if taken:
                raise NameTaken(f"「{taken['name']}」已經有人使用")
        # The lineups follow the new key through the foreign key.
        store.rename_user(conn, key, new_key, new_name)
    return {"name": new_name}


def user_for_token(token):
    """The player key a token belongs to, or None."""
    if not token:
        return None
    users = _load()["users"]
    for key, user in users.items():
        if user.get("token") and secrets.compare_digest(user["token"], token):
            return key
    return None


def find_user(name):
    """(key, display name) for a player name, or None."""
    key = user_key(name)
    with store.reading() as conn:
        user = store.get_user(conn, key)
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


def _players(force=False):
    return cached("fantasy-players", lambda _: PLAYERS_TTL, _fetch_players, force)


def _season_for(date):
    """'2026-11-24' -> '2026-27'. A season starts in October and ends by June."""
    year, month = int(date[:4]), int(date[5:7])
    start = year if month >= 7 else year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def _fetch_game_logs(season):
    """{player id: [(date, fantasy points), ...] oldest first} for every regular-season game."""
    rows = playergamelogs.PlayerGameLogs(
        season_nullable=season, season_type_nullable="Regular Season", timeout=REQUEST_TIMEOUT
    ).get_normalized_dict()["PlayerGameLogs"]
    logs = {}
    for r in rows:
        g = lambda k: r.get(k) or 0
        points = fantasy_points(scoring_stats(
            g("FGM"), g("FGA"), g("FG3M"), g("FTM"), g("FTA"),
            reb=g("REB"), ast=g("AST"), stl=g("STL"), blk=g("BLK"), tov=g("TOV"), pf=g("PF"),
        ))
        logs.setdefault(r["PLAYER_ID"], []).append((r["GAME_DATE"][:10], points))
    for games in logs.values():
        games.sort()
    return logs


def _game_logs(date, force=False):
    season = _season_for(date)
    return cached(("game-logs", season), lambda _: GAME_LOG_TTL, lambda: _fetch_game_logs(season), force)


def _recent(logs, player_id, date):
    """The player's last RECENT_GAMES games before `date`: {"games": [points, ...] oldest first, "avg"}."""
    games = [points for day, points in logs.get(player_id, []) if day < date][-RECENT_GAMES:]
    if not games:
        return None
    return {"games": games, "avg": round(sum(games) / len(games), 1)}


def _pick_salary(pick):
    """Salary saved with a pick; picks made before the salary cap use today's salary."""
    if pick.get("salary") is not None:
        return pick["salary"]
    player = next((p for p in _players() if p["id"] == pick["id"]), None)
    return player["salary"] if player else UNLISTED_SALARY


def _money(amount):
    return f"${amount:,}"


def _minutes(value):
    """'PT25M30.00S' (live) or '25:30' (stats) -> '25:30'."""
    m = re.match(r"PT(\d+)M(\d+)", value or "")
    if m:
        return f"{int(m.group(1))}:{m.group(2)}"
    return value or ""


def _box_players(teams, played):
    """Stats and names from either box score source; both use the same field names."""
    stats = {}
    people = {}
    for team in teams:
        for p in team.get("players", []):
            s = p.get("statistics", {})
            people[p["personId"]] = {
                "name": p.get("name") or f"{p.get('firstName', '')} {p.get('familyName', '')}".strip(),
                "team": team.get("teamTricode"),
                "position": p.get("position") or "",
                # The live feed flags starters; the stats feed only gives starters a position.
                "starter": p.get("starter") == "1" if "starter" in p else bool(p.get("position")),
            }
            stats[p["personId"]] = {
                "played": played(p),
                "min": _minutes(s.get("minutes")),
                "fgm": s.get("fieldGoalsMade", 0),
                "fga": s.get("fieldGoalsAttempted", 0),
                "fg3a": s.get("threePointersAttempted", 0),
                "fta": s.get("freeThrowsAttempted", 0),
                "pm": int(s.get("plusMinusPoints") or 0),
                **scoring_stats(
                    s.get("fieldGoalsMade", 0), s.get("fieldGoalsAttempted", 0),
                    s.get("threePointersMade", 0),
                    s.get("freeThrowsMade", 0), s.get("freeThrowsAttempted", 0),
                    reb=s.get("reboundsTotal", 0), ast=s.get("assists", 0), stl=s.get("steals", 0),
                    blk=s.get("blocks", 0), tov=s.get("turnovers", 0), pf=s.get("foulsPersonal", 0),
                ),
            }
    return stats, people


def _fetch_live_box(game_id):
    game = boxscore.BoxScore(game_id, timeout=REQUEST_TIMEOUT).get_dict()["game"]
    stats, people = _box_players([game["homeTeam"], game["awayTeam"]], lambda p: p.get("played") == "1")
    return {"status": game.get("gameStatus"), "players": stats, "people": people}


def _fetch_stats_box(game_id, status):
    box = boxscoretraditionalv3.BoxScoreTraditionalV3(
        game_id=game_id, timeout=REQUEST_TIMEOUT
    ).get_dict()["boxScoreTraditional"]
    played = lambda p: (p.get("statistics", {}).get("minutes") or "0:00") not in ("0:00", "00:00")
    stats, people = _box_players([box["homeTeam"], box["awayTeam"]], played)
    return {"status": status, "players": stats, "people": people}


_cdn_down_until = 0.0


def _fetch_box(game):
    """Live box score from cdn.nba.com, or the stats API's when the CDN refuses us.

    After a CDN failure, skip it for ERROR_BACKOFF seconds instead of trying every game.
    """
    global _cdn_down_until
    if time.monotonic() >= _cdn_down_until:
        try:
            return with_retry(lambda: _fetch_live_box(game["id"]))
        except Exception:
            _cdn_down_until = time.monotonic() + ERROR_BACKOFF
    return _fetch_stats_box(game["id"], game["status"])


def _box_key(game):
    return ("box", game["id"])


def _box(game, force=False):
    return cached(
        _box_key(game),
        lambda box: FINAL_BOX_TTL if box["status"] == FINAL else LIVE_BOX_TTL,
        lambda: _fetch_box(game),
        force,
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
    try:
        logs = _game_logs(date)
    except Exception:
        logs = {}  # recent form is a nice-to-have; the pool works without it
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
            "recent": _recent(logs, p["id"], date),
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
        stats = _box(game)["players"].get(pick["id"])
        if stats:
            view["stats"] = stats
            view["points"] = fantasy_points(stats)
        else:
            view["stats"] = {"played": False, "pts": 0, **{k: 0 for k in SCORING}}
    return view


def get_lineup(date, key, reveal=True):
    """One player's lineup for `date`. With reveal=False, picks whose game hasn't started are hidden."""
    with store.reading() as conn:
        entry = store.get_entry(conn, date, key) or {}
        user = store.get_user(conn, key) or {}
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
    pick_points = {s["slot"]: s["points"] for s in slots if s["player"]}
    if final and (
        entry.get("finalTotal") != total
        or entry.get("scoringVersion") != SCORING_VERSION
        or entry.get("pickPoints") != pick_points
    ):
        store.settle(date, key, total, SCORING_VERSION, pick_points)

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

    with store.writing() as conn:
        current = (store.get_entry(conn, date, key) or {}).get("slots", {})
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
            store.put_lineup(conn, date, key, new_slots)
        else:
            store.delete_lineup(conn, date, key)
    return get_lineup(date, key)


# ---------- best lineup ----------

# Players with these statuses are left out of the best lineup.
AUTO_SKIP_INJURIES = {"OUT", "OFS"}


def _prune(candidates, slot_count):
    """Drop players who can never be in a best lineup.

    If `slot_count` other players fit every slot this one fits, cost no more and
    score at least as much, one of them is always free to take this one's place.
    """
    kept = []
    for p in candidates:
        better = 0
        for q in candidates:
            if q is p or not q["fits"] >= p["fits"]:
                continue
            if q["salary"] <= p["salary"] and q["score"] >= p["score"]:
                # Exact twins: only the one with the lower id counts as better.
                if q["salary"] == p["salary"] and q["score"] == p["score"] and q["id"] > p["id"]:
                    continue
                better += 1
                if better >= slot_count:
                    break
        if better < slot_count:
            kept.append(p)
    return kept


def _optimize(candidates, slots, budget):
    """The best {slot: candidate} within `budget`, filling as many of `slots` as possible.

    Each candidate has "id", "salary", "score" and "fits" (the slots it may play).
    Dynamic programming over which slots are filled; for each, only the
    salary/score trade-offs that aren't beaten (Pareto front) are kept.
    """
    index = {slot: i for i, slot in enumerate(slots)}
    pool = _prune([c for c in candidates if c["fits"] & set(slots)], len(slots))
    pool.sort(key=lambda c: -c["score"])
    # mask of filled slots -> [(salary, score, ((slot, candidate), ...))]
    fronts = {0: [(0, 0, ())]}
    for c in pool:
        bits = [(slot, 1 << index[slot]) for slot in c["fits"] if slot in index]
        updates = {}
        for mask, front in fronts.items():
            for slot, bit in bits:
                if mask & bit:
                    continue
                for salary, score, picks in front:
                    if salary + c["salary"] <= budget:
                        updates.setdefault(mask | bit, []).append(
                            (salary + c["salary"], score + c["score"], picks + ((slot, c),))
                        )
        for mask, options in updates.items():
            merged = sorted(fronts.get(mask, []) + options, key=lambda o: (o[0], -o[1]))
            front, best = [], float("-inf")
            for option in merged:
                if option[1] > best:
                    front.append(option)
                    best = option[1]
            fronts[mask] = front
    mask, front = max(fronts.items(), key=lambda kv: (bin(kv[0]).count("1"), kv[1][-1][1]))
    salary, score, picks = front[-1]
    return dict(picks), round(score, 1)


def best_lineup(date, key):
    """Fill every slot whose game hasn't started with the best players by season average.

    Locked picks stay. Players listed Out are skipped. Saves and returns the lineup
    with "projected", the expected total by season averages.
    """
    pool = get_pool(date)["players"]
    with store.reading() as conn:
        current = (store.get_entry(conn, date, key) or {}).get("slots", {})
    games_by_id = {g["id"]: g for g in nba_games.get_games(date)["games"]}
    locked = {
        slot: pick for slot, pick in current.items()
        if games_by_id.get(pick["gameId"], {}).get("status", SCHEDULED) != SCHEDULED
    }
    open_slots = [slot for slot in SLOTS if slot not in locked]
    if not open_slots:
        raise LineupError("所有位置都已鎖定，不能再更換")
    taken = {pick["id"] for pick in locked.values()}
    candidates = [
        {"id": p["id"], "salary": p["salary"], "score": p["avgPoints"], "fits": set(p["slots"])}
        for p in pool
        if not p["locked"] and p["id"] not in taken and p["avgPoints"] > 0
        and (p.get("injury") or {}).get("status") not in AUTO_SKIP_INJURIES
    ]
    if not candidates:
        raise LineupError("這天已經沒有還沒開賽的球員可以選")
    budget = SALARY_CAP - sum(_pick_salary(p) for p in locked.values())
    chosen, projected = _optimize(candidates, open_slots, budget)
    picks = {slot: pick["id"] for slot, pick in locked.items()}
    picks.update({slot: c["id"] for slot, c in chosen.items()})
    lineup = save_lineup(date, key, picks)
    by_id = {p["id"]: p for p in pool}
    projected += sum(by_id[p["id"]]["avgPoints"] for p in locked.values() if p["id"] in by_id)
    return {**lineup, "projected": round(projected, 1)}


def _rank(rows, score):
    """Competition ranking (1, 1, 3) by `score`, rows already sorted best first."""
    previous, rank = None, 0
    for i, row in enumerate(rows, start=1):
        if score(row) != previous:
            rank, previous = i, score(row)
        row["rank"] = rank
    return rows


def _settled(entry):
    """A lineup settled under the current rules (older ones are recomputed once)."""
    return (
        entry.get("finalTotal") is not None
        and entry.get("scoringVersion") == SCORING_VERSION
        and "pickPoints" in entry
    )


def _day_results(date, entries):
    """{key: (total, final, players)} for every lineup on `date`, settling any that just finished."""
    results = {}
    for key, entry in entries.items():
        if _settled(entry):
            results[key] = (entry["finalTotal"], True, len(entry.get("slots", {})))
        else:
            lineup = get_lineup(date, key)
            results[key] = (lineup["total"], lineup["final"], len(entry.get("slots", {})))
    return results


def get_daily_leaderboard(date):
    data = _load()
    results = _day_results(date, data["lineups"].get(date, {}))
    rows = [
        {"player": data["users"].get(key, {}).get("name", key), "total": total, "final": final, "players": players}
        for key, (total, final, players) in results.items()
    ]
    rows.sort(key=lambda r: (-r["total"], r["player"].casefold()))
    return {"date": date, "entries": _rank(rows, lambda r: r["total"])}


PERIODS = ("week", "month")

BADGES = [
    {"id": "champion", "icon": "👑", "name": "單日冠軍", "description": "拿過單日第一（當天至少兩人參加）"},
    {"id": "club300", "icon": "💯", "name": "300 分俱樂部", "description": "單日總積分達到 300 分"},
    {"id": "sniper", "icon": "🎯", "name": "神準", "description": "選中單場 70 分以上的球員"},
    {"id": "streak", "icon": "🔥", "name": "連續 7 天", "description": "連續 7 個比賽日都有組陣容"},
    {"id": "veteran", "icon": "📅", "name": "老玩家", "description": "參加滿 10 天"},
]
CLUB_TOTAL = 300
SNIPER_POINTS = 70
STREAK_DAYS = 7
VETERAN_DAYS = 10


def _period_range(period, date):
    """(first, last) ISO dates of the Monday-Sunday week or the month containing `date`."""
    day = dt.date.fromisoformat(date)
    if period == "week":
        first = day - dt.timedelta(days=day.weekday())
        last = first + dt.timedelta(days=6)
    else:
        first = day.replace(day=1)
        last = (first + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)
    return first.isoformat(), last.isoformat()


def _longest_streak(days, calendar):
    """Longest run of consecutive entries of `calendar` (sorted game days) found in `days`."""
    best = run = 0
    for day in calendar:
        run = run + 1 if day in days else 0
        best = max(best, run)
    return best


def _badges(data, stats):
    """{key: [badge id, ...]} earned over every day, whatever period is shown."""
    calendar = sorted(data["lineups"])
    played = {}
    sniper = set()
    for date, entries in data["lineups"].items():
        for key, entry in entries.items():
            played.setdefault(key, set()).add(date)
            if any(points >= SNIPER_POINTS for points in (entry.get("pickPoints") or {}).values()):
                sniper.add(key)
    earned = {}
    for key, days in played.items():
        s = stats.get(key, {})
        ids = []
        if s.get("wins"):
            ids.append("champion")
        if (s.get("best") or 0) >= CLUB_TOTAL:
            ids.append("club300")
        if key in sniper:
            ids.append("sniper")
        if _longest_streak(days, calendar) >= STREAK_DAYS:
            ids.append("streak")
        if len(days) >= VETERAN_DAYS:
            ids.append("veteran")
        earned[key] = ids
    return earned


def _standings(data, dates):
    """{key: {"days", "total", "best", "wins"}} over the settled lineups of `dates`."""
    stats = {}
    for date in dates:
        results = _day_results(date, data["lineups"][date])
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
    return stats


def get_leaderboard(period=None, date=None):
    """Standings over settled days: total points, days played, average, best day, daily wins.

    `period` "week" or "month" limits it to the week (Monday-Sunday) or month of
    `date`; otherwise every day counts. Badges always count every day.
    """
    data = _load()
    everything = _standings(data, sorted(data["lineups"]))
    if period:
        first, last = _period_range(period, date)
        stats = _standings(data, [d for d in sorted(data["lineups"]) if first <= d <= last])
    else:
        first = last = None
        stats = everything
    # Working out the standings may have just settled days; read their pick points too.
    data = _load()
    badges = _badges(data, everything)
    rows = [
        {
            "player": data["users"].get(key, {}).get("name", key),
            **s,
            "average": round(s["total"] / s["days"], 1),
            "badges": badges.get(key, []),
        }
        for key, s in stats.items()
    ]
    rows.sort(key=lambda r: (-r["total"], -r["average"], r["player"].casefold()))
    return {
        "period": period,
        "from": first,
        "to": last,
        "entries": _rank(rows, lambda r: r["total"]),
        "badges": BADGES,
    }


def _started_boxes(date):
    """(all games, games that have tipped off, their box scores)."""
    games = nba_games.get_games(date)["games"]
    started = [g for g in games if g["status"] != SCHEDULED]
    # The first box alone, so a blocked CDN is noticed once rather than by every thread.
    boxes = [_box(g) for g in started[:1]]
    with ThreadPoolExecutor(max_workers=8) as pool:
        boxes += pool.map(_box, started[1:])
    return games, started, boxes


def _picked_by(date):
    """{player id: [nicknames]} for `date`. Only show it for players whose game has started."""
    data = _load()
    picked_by = {}
    for key, entry in data["lineups"].get(date, {}).items():
        name = data["users"].get(key, {}).get("name", key)
        for pick in entry.get("slots", {}).values():
            picked_by.setdefault(pick["id"], []).append(name)
    return {pid: sorted(names, key=str.casefold) for pid, names in picked_by.items()}


def get_game_leaders(date):
    """Each started game's best fantasy scorer per team, for the game cards."""
    _, started, boxes = _started_boxes(date)
    leaders = {}
    for game, box in zip(started, boxes):
        sides = {}
        for side in ("away", "home"):
            tricode = game[side].get("tricode")
            rows = [
                {"id": pid, "name": box["people"].get(pid, {}).get("name", str(pid)),
                 "points": fantasy_points(stats), "stats": stats}
                for pid, stats in box["players"].items()
                if stats["played"] and box["people"].get(pid, {}).get("team") == tricode
            ]
            sides[side] = max(rows, key=lambda r: r["points"], default=None)
        leaders[game["id"]] = sides
    return {"date": date, "games": leaders}


def get_game_detail(date, game_id):
    """One game's box score with every player's fantasy points and who picked them."""
    game = next((g for g in nba_games.get_games(date)["games"] if g["id"] == game_id), None)
    if game is None:
        raise GameNotFound(game_id)
    teams = {}
    if game["status"] == SCHEDULED:
        for side in ("away", "home"):
            teams[side] = {"tricode": game[side].get("tricode"), "players": [], "bench": []}
        return {"date": date, "game": game, "teams": teams}
    box = _box(game)
    # The game has tipped off, so its picks are locked and public.
    picked_by = _picked_by(date)
    for side in ("away", "home"):
        tricode = game[side].get("tricode")
        players, bench = [], []
        for pid, stats in box["players"].items():
            person = box["people"].get(pid, {})
            if person.get("team") != tricode:
                continue
            if not stats["played"]:
                bench.append(person.get("name", str(pid)))
                continue
            players.append({
                "id": pid,
                "name": person.get("name", str(pid)),
                "position": person.get("position", ""),
                "starter": person.get("starter", False),
                "stats": stats,
                "points": fantasy_points(stats),
                "pickedBy": picked_by.get(pid, []),
            })
        teams[side] = {"tricode": tricode, "players": players, "bench": bench}
    return {"date": date, "game": game, "teams": teams}


def get_top_players(date, limit=TOP_PLAYERS):
    """The day's best fantasy scorers across every game, not just picked players.

    Ties at the cut-off are all kept. Only games that have tipped off count, so
    showing who picked each player never reveals a hidden pick.
    """
    games, started, boxes = _started_boxes(date)
    picked_by = _picked_by(date)

    rows = []
    for game, box in zip(started, boxes):
        for pid, stats in box["players"].items():
            if not stats["played"]:
                continue
            person = box.get("people", {}).get(pid, {})
            rows.append({
                "id": pid,
                "name": person.get("name", str(pid)),
                "team": person.get("team"),
                "position": person.get("position", ""),
                "game": _game_view(game, next(
                    (game[s]["id"] for s in ("home", "away") if game[s].get("tricode") == person.get("team")),
                    None,
                )),
                "stats": stats,
                "points": fantasy_points(stats),
                "pickedBy": picked_by.get(pid, []),
            })
    rows.sort(key=lambda r: (-r["points"], r["name"].casefold()))
    ranked = _rank(rows, lambda r: r["points"])
    return {
        "date": date,
        "games": len(games),
        "started": len(started),
        "live": any(g["status"] == LIVE for g in started),
        "players": [r for r in ranked if r["rank"] <= limit],
    }


def get_history(key):
    """Every date `key` has a lineup, newest first, with total and daily rank."""
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
    with store.reading() as conn:
        user = store.get_user(conn, key)
    return user["name"] if user else key
