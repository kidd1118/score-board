from nba_api.stats.static import teams

def get_teams():
    return teams.get_teams()

def get_team(team_name):
    nba_teams = teams.get_teams()
    # Select the dictionary for the Celtics, which contains their team ID
    celtics = [team for team in nba_teams if team['abbreviation'] == team_name.upper()][0]
    celtics_id = celtics['id']

    print(celtics_id)   
    return celtics