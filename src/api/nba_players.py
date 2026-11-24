from nba_api.stats.endpoints import commonplayerinfo, playercareerstats
from nba_api.stats.static import players

REQUEST_TIMEOUT = 15

STAT_KEYS = [
    "GP", "GS", "MIN", "PTS", "REB", "AST", "STL", "BLK", "TOV",
    "FG_PCT", "FG3_PCT", "FT_PCT",
]


def get_players(active=None):
    all_players = players.get_players()
    if active is None:
        return all_players
    return [p for p in all_players if p["is_active"] == active]


def get_player(name):
    return players.find_players_by_full_name(name)


def _stat_row(row):
    return {key.lower(): row.get(key) for key in STAT_KEYS}


def get_player_profile(player_id: int):
    if players.find_player_by_id(player_id) is None:
        return None
    info = commonplayerinfo.CommonPlayerInfo(
        player_id=player_id, timeout=REQUEST_TIMEOUT
    ).get_normalized_dict()
    career = playercareerstats.PlayerCareerStats(
        player_id=player_id, per_mode36="PerGame", timeout=REQUEST_TIMEOUT
    ).get_normalized_dict()

    rows = info.get("CommonPlayerInfo") or []
    if not rows:
        return None
    p = rows[0]

    seasons = [
        {"season": r["SEASON_ID"], "team": r.get("TEAM_ABBREVIATION"), "age": r.get("PLAYER_AGE"), **_stat_row(r)}
        for r in career.get("SeasonTotalsRegularSeason", [])
    ]
    totals = career.get("CareerTotalsRegularSeason") or []

    return {
        "id": p.get("PERSON_ID"),
        "name": p.get("DISPLAY_FIRST_LAST"),
        "team": {
            "id": p.get("TEAM_ID"),
            "tricode": p.get("TEAM_ABBREVIATION"),
            "city": p.get("TEAM_CITY"),
            "name": p.get("TEAM_NAME"),
        },
        "jersey": p.get("JERSEY"),
        "position": p.get("POSITION"),
        "height": p.get("HEIGHT"),
        "weight": p.get("WEIGHT"),
        "birthdate": (p.get("BIRTHDATE") or "")[:10] or None,
        "country": p.get("COUNTRY"),
        "school": p.get("SCHOOL"),
        "experience": p.get("SEASON_EXP"),
        "fromYear": p.get("FROM_YEAR"),
        "toYear": p.get("TO_YEAR"),
        "draft": {
            "year": p.get("DRAFT_YEAR"),
            "round": p.get("DRAFT_ROUND"),
            "number": p.get("DRAFT_NUMBER"),
        },
        "active": p.get("ROSTERSTATUS") == "Active",
        "career": _stat_row(totals[0]) if totals else None,
        "seasons": seasons,
    }
