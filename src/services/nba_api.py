# import numpy as np

# arr = np.array([1, 2, 3])

# print(arr)

# print(np.__name__)  # 模組名稱
# print(np.__package__)  # 套件名稱
# print(np.__file__)  # 模組的檔名及路徑

from nba_api.stats.static import teams

nba_teams = teams.get_teams()
# Select the dictionary for the Celtics, which contains their team ID
celtics = [team for team in nba_teams if team['abbreviation'] == 'BOS'][0]
celtics_id = celtics['id']

# from nba_api.live.nba.endpoints import scoreboard

# # Today's Score Board
# games = scoreboard.ScoreBoard()

# # json
# games.get_json()

# # dictionary
# games.get_dict()