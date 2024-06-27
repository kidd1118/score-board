from nba_api.stats.static import players

def get_players():
    return players.get_players()

def get_player(name):
    return players.find_players_by_full_name(name)