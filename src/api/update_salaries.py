"""Refresh salaries.json from Basketball-Reference's contracts page.

Run from src/api:  ../../.venv/bin/python update_salaries.py

The fantasy game reads the snapshot instead of scraping on every request, so it
keeps working offline and doesn't hammer the site. Re-run it when salaries change
(new season, trades, signings).
"""
import datetime as dt
import html
import json
import re
import urllib.request
from pathlib import Path

URL = "https://www.basketball-reference.com/contracts/players.html"
OUT = Path(__file__).parent / "salaries.json"

ROW = re.compile(r"<tr\s*>(.*?)</tr>", re.S)
CELL = re.compile(r'data-stat="(\w+)"[^>]*?(?:csk="([^"]*)")?\s*>(.*?)</t[dh]>', re.S)
SEASON = re.compile(r'data-stat="y1"[^>]*>(\d{4}-\d{2})<')
TAG = re.compile(r"<[^>]+>")


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read().decode("utf-8")


def parse(page):
    players = []
    for row in ROW.findall(page):
        cells = {stat: (csk, html.unescape(TAG.sub("", text)).strip()) for stat, csk, text in CELL.findall(row)}
        salary = cells.get("y1", ("", ""))[0]
        if "player" not in cells or not salary.isdigit():
            continue
        players.append({
            "name": cells["player"][1],
            "team": cells.get("team_id", ("", ""))[1],
            "salary": int(salary),
        })
    return players


def main():
    page = fetch()
    season = SEASON.search(page)
    players = parse(page)
    if not players:
        raise SystemExit("no salaries found; the page layout may have changed")
    OUT.write_text(json.dumps({
        "season": season.group(1) if season else None,
        "source": URL,
        "updated": dt.date.today().isoformat(),
        "players": players,
    }, ensure_ascii=False, indent=1))
    print(f"wrote {len(players)} salaries to {OUT.name}")


if __name__ == "__main__":
    main()
