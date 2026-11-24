from concurrent.futures import ThreadPoolExecutor

from nba_api.stats.endpoints import (
    commonteamroster,
    leaguegamefinder,
    leaguestandingsv3,
    teaminfocommon,
)
from nba_api.stats.library.parameters import Season
from nba_api.stats.static import teams

REQUEST_TIMEOUT = 15


def get_teams():
    return teams.get_teams()


def get_team(team_name):
    """Look up a team by abbreviation, e.g. BOS."""
    matches = [t for t in teams.get_teams() if t['abbreviation'] == team_name.upper()]
    return matches[0] if matches else None


def get_standings(season=Season.default):
    rows = leaguestandingsv3.LeagueStandingsV3(
        season=season, timeout=REQUEST_TIMEOUT
    ).get_normalized_dict()["Standings"]
    tricodes = {t["id"]: t["abbreviation"] for t in teams.get_teams()}
    standings = [
        {
            "id": r["TeamID"],
            "tricode": tricodes.get(r["TeamID"]),
            "city": r.get("TeamCity"),
            "name": r.get("TeamName"),
            "conference": r.get("Conference"),
            "division": r.get("Division"),
            "rank": r.get("PlayoffRank"),
            "wins": r.get("WINS"),
            "losses": r.get("LOSSES"),
            "pct": r.get("WinPCT"),
            "gamesBack": r.get("ConferenceGamesBack"),
            "home": (r.get("HOME") or "").strip(),
            "road": (r.get("ROAD") or "").strip(),
            "last10": (r.get("L10") or "").strip(),
            "streak": (r.get("strCurrentStreak") or "").strip(),
            "ppg": r.get("PointsPG"),
            "oppPpg": r.get("OppPointsPG"),
            "diff": r.get("DiffPointsPG"),
            "clinch": (r.get("ClinchIndicator") or "").strip(" -") or None,
        }
        for r in rows
    ]
    standings.sort(key=lambda t: (t["conference"] or "", t["rank"] or 99))
    return {"season": season, "teams": standings}


def _team_info(team_id, season):
    data = teaminfocommon.TeamInfoCommon(
        team_id=team_id, season_nullable=season, timeout=REQUEST_TIMEOUT
    ).get_normalized_dict()
    info = (data.get("TeamInfoCommon") or [{}])[0]
    ranks = (data.get("TeamSeasonRanks") or [{}])[0]
    return info, ranks


def _roster(team_id, season):
    data = commonteamroster.CommonTeamRoster(
        team_id=team_id, season=season, timeout=REQUEST_TIMEOUT
    ).get_normalized_dict()
    players = [
        {
            "id": p.get("PLAYER_ID"),
            "name": p.get("PLAYER"),
            "number": p.get("NUM"),
            "position": p.get("POSITION"),
            "height": p.get("HEIGHT"),
            "weight": p.get("WEIGHT"),
            "age": p.get("AGE"),
            "experience": p.get("EXP"),
            "school": p.get("SCHOOL"),
        }
        for p in data.get("CommonTeamRoster", [])
    ]
    coach = next(
        (c.get("COACH_NAME") for c in data.get("Coaches", []) if c.get("COACH_TYPE") == "Head Coach"),
        None,
    )
    return players, coach


def _games(team_id, season):
    rows = leaguegamefinder.LeagueGameFinder(
        team_id_nullable=team_id,
        season_nullable=season,
        season_type_nullable="Regular Season",
        league_id_nullable="00",
        timeout=REQUEST_TIMEOUT,
    ).get_normalized_dict()["LeagueGameFinderResults"]
    games = []
    for g in rows:
        matchup = g.get("MATCHUP") or ""
        pts, margin = g.get("PTS"), g.get("PLUS_MINUS")
        games.append({
            "id": g.get("GAME_ID"),
            "date": g.get("GAME_DATE"),
            "opponent": matchup.split(" ")[-1],
            "home": "vs." in matchup,
            "result": g.get("WL"),
            "pts": pts,
            "oppPts": round(pts - margin) if pts is not None and margin is not None else None,
            "margin": round(margin) if margin is not None else None,
        })
    games.sort(key=lambda g: g["date"] or "")
    return games


def get_team_profile(team_id: int, season=Season.default):
    team = teams.find_team_name_by_id(team_id)
    if team is None:
        return None

    with ThreadPoolExecutor(max_workers=3) as pool:
        info_f = pool.submit(_team_info, team_id, season)
        roster_f = pool.submit(_roster, team_id, season)
        games_f = pool.submit(_games, team_id, season)
        (info, ranks), (roster, coach), games = info_f.result(), roster_f.result(), games_f.result()

    def rank(value_key, rank_key):
        return {"value": ranks.get(value_key), "rank": ranks.get(rank_key)}

    return {
        "id": team_id,
        "season": season,
        "tricode": team["abbreviation"],
        "city": team["city"],
        "name": team["nickname"],
        "conference": info.get("TEAM_CONFERENCE"),
        "division": info.get("TEAM_DIVISION"),
        "wins": info.get("W"),
        "losses": info.get("L"),
        "pct": info.get("PCT"),
        "confRank": info.get("CONF_RANK"),
        "divRank": info.get("DIV_RANK"),
        "founded": team.get("year_founded"),
        "coach": coach,
        "ranks": {
            "pts": rank("PTS_PG", "PTS_RANK"),
            "reb": rank("REB_PG", "REB_RANK"),
            "ast": rank("AST_PG", "AST_RANK"),
            "oppPts": rank("OPP_PTS_PG", "OPP_PTS_RANK"),
        },
        "games": games,
        "roster": roster,
    }
