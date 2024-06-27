from fastapi import FastAPI
from typing import Union
import nba_teams
import nba_players

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

# team name: BOS
@app.get("/team/{name}")
def get_team(name: str):
    team = nba_teams.get_team(name)
    return team

@app.get("/player/")
def get_players():
    players = nba_players.get_players()
    return {"players": players}
    
@app.get("/player/{name}")
def get_player(name: str):
    players = nba_players.get_player(name)
    return {"players": players}