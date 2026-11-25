"""Player availability: Out, Doubtful, Questionable, Probable, GTD.

Two sources, merged per player:

1. The NBA's official injury report (a PDF republished every 15 minutes on
   game days). It is authoritative and has the full scale (Out / Doubtful /
   Questionable / Probable / Available), but only covers today's and
   sometimes tomorrow's games.
2. ESPN's injury feed, used for players the official report doesn't cover
   (other dates, teams that haven't submitted yet). It only knows Out and
   day-to-day, which we show as GTD.

Everything here is best effort: if a source can't be fetched or parsed, the
game still works, just without those statuses.
"""
import datetime as dt
import io
import json
import re
import urllib.request

from nba_api.stats.static import teams as static_teams
from pypdf import PdfReader

from cache import cached, with_retry
from names import name_key

INDEX_URL = "https://official.nba.com/nba-injury-report-2025-26-season/"
ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
TTL = 10 * 60
REQUEST_TIMEOUT = 20

# Status codes the frontend understands, most severe first.
STATUSES = {
    "OFS": "Out for season",
    "OUT": "Out",
    "DOUBTFUL": "Doubtful",
    "GTD": "GTD",
    "QUESTIONABLE": "Questionable",
    "PROBABLE": "Probable",
}
OFFICIAL_STATUS = {
    "Out": "OUT",
    "Doubtful": "DOUBTFUL",
    "Questionable": "QUESTIONABLE",
    "Probable": "PROBABLE",
    "Available": None,
}
ESPN_TEAMS = {"GS": "GSW", "NY": "NYK", "SA": "SAS", "NO": "NOP", "UTAH": "UTA", "WSH": "WAS"}

REPORT_LINK = re.compile(r"https://ak-static\.cms\.nba\.com/referee/injury/Injury-Report_(\d{4}-\d{2}-\d{2})_(\d{2})_?(\d{2})?(AM|PM)\.pdf")
PAGE_HEADER = re.compile(r"Injury Report: \S+ \S+ [AP]M Page \d+ of \d+")
COLUMN_HEADER = "Game Date Game Time Matchup Team Player Name Current Status Reason"


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as res:
        return res.read()


# ---------- official NBA injury report ----------

def _latest_report_url():
    page = _get(INDEX_URL).decode("utf-8", "replace")

    def published(match):
        date, hour, minute, half = match.groups()
        hour = int(hour) % 12 + (12 if half == "PM" else 0)
        return dt.datetime.fromisoformat(date).replace(hour=hour, minute=int(minute or 0))

    links = list(REPORT_LINK.finditer(page))
    if not links:
        raise ValueError("no injury report links found")
    latest = max(links, key=published)
    return latest.group(0), published(latest).isoformat()


def _team_names():
    names = {t["full_name"]: t["abbreviation"] for t in static_teams.get_teams()}
    names["LA Clippers"] = "LAC"
    return names


def parse_report(text):
    """Report text -> [{date, team, name, status, reason}] (status None = available)."""
    text = " ".join(text.split())
    text = PAGE_HEADER.sub(" ", text).replace(COLUMN_HEADER, " ")
    # Line wrapping splits hyphenated words: "Karl- Anthony", "Two- Way".
    text = re.sub(r"(\w)- (\w)", r"\1-\2", " ".join(text.split()))

    team_names = _team_names()
    markers = re.compile(
        r"(?P<date>\b\d{2}/\d{2}/\d{4}\b)"
        r"|(?P<time>\b\d{2}:\d{2} \(ET\))"
        r"|(?P<matchup>\b[A-Z]{2,3}@[A-Z]{2,3}\b)"
        r"|(?P<team>" + "|".join(re.escape(n) for n in sorted(team_names, key=len, reverse=True)) + r")"
        r"|(?P<player>(?P<last>[^\s,]+(?: (?:Jr\.|Sr\.|II|III|IV|V))?), (?P<first>\S+(?: \S+)?) "
        r"(?P<status>Out|Questionable|Doubtful|Probable|Available)\b)"
        r"|(?P<missing>NOT YET SUBMITTED)"
    )

    rows, date, team = [], None, None
    found = list(markers.finditer(text))
    for i, m in enumerate(found):
        if m.group("date"):
            month, day, year = m.group("date").split("/")
            date = f"{year}-{month}-{day}"
        elif m.group("team"):
            team = team_names[m.group("team")]
        elif m.group("player") and date and team:
            end = found[i + 1].start() if i + 1 < len(found) else len(text)
            reason = text[m.end():end].strip()
            reason = re.sub(r"^Injury/Illness\s*-\s*", "", reason)
            rows.append({
                "date": date,
                "team": team,
                "name": f"{m.group('first')} {m.group('last')}",
                "status": OFFICIAL_STATUS[m.group("status")],
                "reason": reason,
            })
    return rows


def _fetch_official():
    url, published = _latest_report_url()
    reader = PdfReader(io.BytesIO(_get(url)))
    text = " ".join(page.extract_text() or "" for page in reader.pages)
    return {"published": published, "url": url, "rows": parse_report(text)}


# ---------- ESPN ----------

def _fetch_espn():
    data = json.loads(_get(ESPN_URL))
    rows = []
    for team in data.get("injuries", []):
        for item in team.get("injuries", []):
            athlete = item.get("athlete", {})
            abbr = athlete.get("team", {}).get("abbreviation", "")
            details = item.get("details") or {}
            fantasy = (details.get("fantasyStatus") or {}).get("abbreviation")
            # ESPN's `status` is the current one; its fantasy flag only adds "out for season".
            if fantasy == "OFS":
                status = "OFS"
            else:
                status = "OUT" if item.get("status") == "Out" else "GTD"
            reason = " ".join(filter(None, [details.get("side"), details.get("type"), details.get("detail")]))
            rows.append({
                "team": ESPN_TEAMS.get(abbr, abbr),
                "name": athlete.get("displayName", ""),
                "status": status,
                "reason": reason or item.get("shortComment", ""),
                "returnDate": details.get("returnDate"),
            })
    return rows


# ---------- merged lookup ----------

FAILED_TTL = 2 * 60


def _safe(key, fetch):
    """Cached fetch that returns None on failure (remembered briefly, so a dead source doesn't slow every request)."""
    def attempt():
        try:
            return with_retry(fetch)
        except Exception:
            return None

    return cached(key, lambda value: TTL if value is not None else FAILED_TTL, attempt)


class Statuses:
    """Status lookup for one game date."""

    def __init__(self, official, espn):
        self.official = official
        self.espn = espn

    def get(self, name, team):
        """{status, label, reason, source} for a player, or None if nothing is reported."""
        # A team on the official report lists everyone who isn't fully available,
        # so for those teams ESPN has nothing to add.
        sources = [("NBA", self.official)] if team in self.official else [("ESPN", self.espn)]
        for source, rows in sources:
            row = _find(rows.get(team, []), name)
            if row is not None:
                if row["status"] is None:  # listed as Available
                    return None
                return {
                    "status": row["status"],
                    "label": STATUSES[row["status"]],
                    "reason": row["reason"],
                    "source": source,
                }
        return None


def _find(rows, name):
    key = name_key(name)
    for row in rows:
        if row["key"] == key:
            return row
    # "Jones Garcia, David" reaches us as "David Garcia"; "Ron" vs "Ronald".
    first, last = key.split()[0], key.split()[-1]
    similar = [
        r for r in rows
        if r["key"].split()[-1] == last and (r["key"].startswith(first) or first.startswith(r["key"].split()[0]))
    ]
    return similar[0] if len(similar) == 1 else None


def _by_team(rows):
    teams = {}
    for row in rows:
        teams.setdefault(row["team"], []).append({**row, "key": name_key(row["name"])})
    return teams


def statuses_for(date):
    """Statuses for players in games on `date` (YYYY-MM-DD, US date)."""
    official = _safe("injuries-official", _fetch_official)
    espn = _safe("injuries-espn", _fetch_espn)
    official_rows = [r for r in (official or {}).get("rows", []) if r["date"] == date]
    # ESPN describes players *now*, so it only says something useful about upcoming games.
    today = dt.date.today().isoformat()
    espn_rows = (espn or []) if date >= (dt.date.fromisoformat(today) - dt.timedelta(days=1)).isoformat() else []
    return Statuses(_by_team(official_rows), _by_team(espn_rows))


def report_info():
    official = _safe("injuries-official", _fetch_official)
    espn = _safe("injuries-espn", _fetch_espn)
    return {
        "official": {"published": official["published"], "url": official["url"]} if official else None,
        "espn": espn is not None,
    }
