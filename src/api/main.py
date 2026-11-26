import datetime as dt
import os
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from typing import Dict, Optional, Union

from pydantic import BaseModel
import nba_teams
import nba_players
import nba_games
import nba_fantasy
from cache import describe

app = FastAPI()

# `npm run build` output. When it exists the backend also serves the site itself,
# so the whole app runs on one port (see scripts/serve.sh).
BUILD_DIR = Path(os.environ.get("FRONTEND_BUILD_DIR", Path(__file__).resolve().parents[2] / "build"))

@app.get("/items/{item_id}")
def read_item(item_id: int, q: Union[str, None] = None):
    return {"item_id": item_id, "q": q}

@app.get("/team/")
def get_teams():
    return nba_teams.get_teams()

# must be declared before /team/{name}, or "standings" is treated as a team name
@app.get("/team/standings")
def get_standings():
    try:
        return nba_teams.get_standings()
    except Exception as e:
        raise HTTPException(status_code=502, detail=describe(e))

@app.get("/team/{team_id}/profile")
def get_team_profile(team_id: int):
    try:
        profile = nba_teams.get_team_profile(team_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=describe(e))
    if profile is None:
        raise HTTPException(status_code=404, detail="team not found")
    return profile

# team name: BOS
@app.get("/team/{name}")
def get_team(name: str):
    team = nba_teams.get_team(name)
    if team is None:
        raise HTTPException(status_code=404, detail="team not found")
    return team

# active: true = current players only, false = retired only, omit = all
@app.get("/player/")
def get_players(active: Union[bool, None] = None):
    players = nba_players.get_players(active)
    return {"players": players}

@app.get("/player/{player_id}/profile")
def get_player_profile(player_id: int):
    try:
        profile = nba_players.get_player_profile(player_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=describe(e))
    if profile is None:
        raise HTTPException(status_code=404, detail="player not found")
    return profile

@app.get("/player/{name}")
def get_player(name: str):
    players = nba_players.get_player(name)
    return {"players": players}

# date format: YYYY-MM-DD; omit for today's live scoreboard
@app.get("/games/")
def get_games(date: Union[str, None] = None):
    if date:
        try:
            date = dt.date.fromisoformat(date).isoformat()
        except ValueError:
            raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    try:
        return nba_games.get_games(date)
    except Exception as e:
        raise HTTPException(status_code=502, detail=describe(e))


def _check_date(date: str) -> str:
    try:
        return dt.date.fromisoformat(date).isoformat()
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")


class LineupIn(BaseModel):
    # slot (PG, SG, SF, PF, C, 6TH) -> player id, or null to leave empty
    slots: Dict[str, Optional[int]]


class UserIn(BaseModel):
    name: str


def _nba(fetch):
    """Run an NBA-backed call; rule violations become 400, NBA failures 502."""
    try:
        return fetch()
    except nba_fantasy.NameTaken as e:
        raise HTTPException(status_code=409, detail=str(e))
    except nba_fantasy.LineupError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=describe(e))


def _fantasy_user(name: str):
    found = nba_fantasy.find_user(name)
    if found is None:
        raise HTTPException(status_code=404, detail="找不到這位玩家")
    return found[0]


def _signed_in(token: Optional[str]):
    key = nba_fantasy.user_for_token(token)
    if key is None:
        raise HTTPException(status_code=401, detail="請先加入遊戲（金鑰無效或已失效）")
    return key


# Fantasy routes without a date must be declared before /fantasy/{date}/...
@app.post("/fantasy/users")
def register_fantasy_user(user: UserIn):
    return _nba(lambda: nba_fantasy.register(user.name))

@app.get("/fantasy/me")
def get_fantasy_me(x_fantasy_token: Optional[str] = Header(None)):
    key = _signed_in(x_fantasy_token)
    return {"name": nba_fantasy.find_user_name(key)}

@app.patch("/fantasy/me")
def rename_fantasy_me(user: UserIn, x_fantasy_token: Optional[str] = Header(None)):
    key = _signed_in(x_fantasy_token)
    return _nba(lambda: nba_fantasy.rename(key, user.name))

@app.get("/fantasy/salary")
def get_fantasy_salary():
    return nba_fantasy.salary_info()

@app.get("/fantasy/leaderboard")
def get_fantasy_leaderboard():
    return _nba(nba_fantasy.get_leaderboard)

@app.get("/fantasy/history/{name}")
def get_fantasy_history(name: str):
    key = _fantasy_user(name)
    return _nba(lambda: nba_fantasy.get_history(key))

@app.get("/fantasy/{date}/pool")
def get_fantasy_pool(date: str):
    date = _check_date(date)
    return _nba(lambda: nba_fantasy.get_pool(date))

@app.get("/fantasy/{date}/leaderboard")
def get_fantasy_daily_leaderboard(date: str):
    date = _check_date(date)
    return _nba(lambda: nba_fantasy.get_daily_leaderboard(date))

@app.get("/fantasy/{date}/top")
def get_fantasy_top_players(date: str):
    date = _check_date(date)
    return _nba(lambda: nba_fantasy.get_top_players(date))

# Anyone can look; picks whose game hasn't started are only shown to their owner.
@app.get("/fantasy/{date}/lineup/{name}")
def get_fantasy_lineup(date: str, name: str, x_fantasy_token: Optional[str] = Header(None)):
    date = _check_date(date)
    key = _fantasy_user(name)
    reveal = nba_fantasy.user_for_token(x_fantasy_token) == key
    return _nba(lambda: nba_fantasy.get_lineup(date, key, reveal))

@app.put("/fantasy/{date}/lineup")
def save_fantasy_lineup(date: str, lineup: LineupIn, x_fantasy_token: Optional[str] = Header(None)):
    date = _check_date(date)
    key = _signed_in(x_fantasy_token)
    return _nba(lambda: nba_fantasy.save_lineup(date, key, lineup.slots))



# Declared last so every API route above wins over a file with the same path.
if (BUILD_DIR / "index.html").exists():
    app.mount("/", StaticFiles(directory=BUILD_DIR, html=True), name="frontend")
else:
    @app.get("/")
    def root():
        return {"message": "Frontend not built; run `npm run build` to serve the site from here."}
