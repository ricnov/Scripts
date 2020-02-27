import simplejson as json
import pandas as pd
import requests
from bs4 import BeautifulSoup as bs

url = "https://www.sofascore.com/football///json"
r = requests.get(url)
soup = bs(r.content, 'lxml')
json_object = json.loads(r.content)

headers = ['Tournament', 'Home Team', 'Home Score', 'Away Team', 'Away Score', 'Status', 'Start Date']
consolidated = []
for tournament in json_object['sportItem']['tournaments']:
    rows = []
    for event in tournament["events"]:
        row = []
        row.append(tournament["tournament"]["name"])
        row.append(event["homeTeam"]["name"])
        if "current" in event["homeScore"].keys():
            row.append(event["homeScore"]["current"])
        else:
            row.append(-1)
        row.append(event["awayTeam"]["name"])
        if "current" in event["awayScore"].keys():
            row.append(event["awayScore"]["current"])
        else:
            row.append(-1)
        row.append(event["status"]["type"])
        row.append(event["formatedStartDate"])
        rows.append(row)
    df = pd.DataFrame(rows, columns=headers)
    consolidated.append(df)

pd.concat(consolidated).to_csv(r'Path.csv', sep=',', encoding='utf-8-sig',
                               index=False)
