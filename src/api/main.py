import datetime as dt

from fastapi import FastAPI, HTTPException
from typing import Dict, Optional, Union

from pydantic import BaseModel
import nba_teams
import nba_players
import nba_games
import nba_fantasy

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Hello World"}

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
        raise HTTPException(status_code=502, detail=f"NBA API request failed: {e}")

@app.get("/team/{team_id}/profile")
def get_team_profile(team_id: int):
    try:
        profile = nba_teams.get_team_profile(team_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"NBA API request failed: {e}")
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
        raise HTTPException(status_code=502, detail=f"NBA API request failed: {e}")
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
        raise HTTPException(status_code=502, detail=f"NBA API request failed: {e}")


def _check_date(date: str) -> str:
    try:
        return dt.date.fromisoformat(date).isoformat()
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")


class LineupIn(BaseModel):
    # slot (PG, SG, SF, PF, C, 6TH) -> player id, or null to leave empty
    slots: Dict[str, Optional[int]]


# must be declared before /fantasy/{date}
@app.get("/fantasy/history")
def get_fantasy_history():
    try:
        return nba_fantasy.get_history()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"NBA API request failed: {e}")

@app.get("/fantasy/{date}/pool")
def get_fantasy_pool(date: str):
    date = _check_date(date)
    try:
        return nba_fantasy.get_pool(date)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"NBA API request failed: {e}")

@app.get("/fantasy/{date}")
def get_fantasy_lineup(date: str):
    date = _check_date(date)
    try:
        return nba_fantasy.get_lineup(date)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"NBA API request failed: {e}")

@app.put("/fantasy/{date}")
def save_fantasy_lineup(date: str, lineup: LineupIn):
    date = _check_date(date)
    try:
        return nba_fantasy.save_lineup(date, lineup.slots)
    except nba_fantasy.LineupError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"NBA API request failed: {e}")

