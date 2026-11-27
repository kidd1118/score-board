"""SQLite storage for the daily fantasy game.

Tables:

    users   (key, name, token)                 key = case-folded nickname
    lineups (date, user_key, slots, final_total, scoring_version, pick_points)

`slots` and `pick_points` are JSON. Renaming a player changes `users.key`, and
the foreign key carries it over to every lineup.

Every write runs in its own transaction (`BEGIN IMMEDIATE`), so several server
processes (the dev backend and scripts/serve.sh) can share one database file
without overwriting each other's changes.

On first use, an existing fantasy.json (the old storage) is imported once and
renamed to fantasy.json.imported.
"""
import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DB_FILE = Path(os.environ.get("FANTASY_DB_FILE", DATA_DIR / "fantasy.db"))
JSON_FILE = Path(os.environ.get("FANTASY_DATA_FILE", DATA_DIR / "fantasy.json"))
BACKUP_DIR = Path(os.environ.get("FANTASY_BACKUP_DIR", DATA_DIR / "backups"))
BACKUPS_KEPT = 14

# Single-player JSON files ({date: lineup}) belonged to this nickname.
LEGACY_NAME = "玩家1"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    key   TEXT PRIMARY KEY,
    name  TEXT NOT NULL,
    token TEXT UNIQUE
);
CREATE TABLE IF NOT EXISTS lineups (
    date            TEXT NOT NULL,
    user_key        TEXT NOT NULL REFERENCES users(key) ON UPDATE CASCADE ON DELETE CASCADE,
    slots           TEXT NOT NULL,
    final_total     REAL,
    scoring_version INTEGER,
    pick_points     TEXT,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (date, user_key)
);
CREATE INDEX IF NOT EXISTS lineups_user ON lineups(user_key);
"""

_ready = False
_init_lock = threading.Lock()


def user_key(name):
    return " ".join(name.split()).casefold()


def _connect():
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Autocommit mode: transactions are opened explicitly below.
    conn = sqlite3.connect(DB_FILE, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def _ensure_ready():
    global _ready
    if _ready:
        return
    with _init_lock:
        if _ready:
            return
        conn = _connect()
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(SCHEMA)
            conn.execute("BEGIN IMMEDIATE")
            try:
                _import_json(conn)
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()
        _ready = True


def _import_json(conn):
    """Copy the old fantasy.json into an empty database, then rename the file."""
    if not JSON_FILE.exists():
        return
    if conn.execute("SELECT EXISTS(SELECT 1 FROM users) OR EXISTS(SELECT 1 FROM lineups)").fetchone()[0]:
        return  # another process already imported it
    data = json.loads(JSON_FILE.read_text())
    if "lineups" not in data:
        key = user_key(LEGACY_NAME)
        data = {
            "users": {key: {"name": LEGACY_NAME, "token": None}} if data else {},
            "lineups": {date: {key: entry} for date, entry in data.items()},
        }
    users = dict(data.get("users", {}))
    for entries in data.get("lineups", {}).values():
        for key in entries:
            users.setdefault(key, {"name": key, "token": None})
    conn.executemany(
        "INSERT INTO users (key, name, token) VALUES (?, ?, ?)",
        [(key, u.get("name", key), u.get("token")) for key, u in users.items()],
    )
    conn.executemany(
        "INSERT INTO lineups (date, user_key, slots, final_total, scoring_version, pick_points)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        [
            (
                date, key, json.dumps(e.get("slots", {}), ensure_ascii=False),
                e.get("finalTotal"), e.get("scoringVersion"),
                json.dumps(e["pickPoints"], ensure_ascii=False) if e.get("pickPoints") is not None else None,
            )
            for date, entries in data.get("lineups", {}).items()
            for key, e in entries.items()
        ],
    )
    JSON_FILE.rename(JSON_FILE.with_name(JSON_FILE.name + ".imported"))


@contextmanager
def reading():
    _ensure_ready()
    conn = _connect()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def writing():
    """A write transaction; other writers wait until it commits."""
    _ensure_ready()
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()


def _entry(row):
    total = row["final_total"]
    if total is not None and float(total).is_integer():
        total = int(total)  # same numbers the API returned before SQLite
    entry = {"slots": json.loads(row["slots"]), "finalTotal": total}
    if row["scoring_version"] is not None:
        entry["scoringVersion"] = row["scoring_version"]
    if row["pick_points"] is not None:
        entry["pickPoints"] = json.loads(row["pick_points"])
    return entry


def load(conn=None):
    """Everything as {"users": {key: {name, token}}, "lineups": {date: {key: entry}}}."""
    if conn is None:
        with reading() as conn:
            return load(conn)
    data = {"users": {}, "lineups": {}}
    for row in conn.execute("SELECT key, name, token FROM users"):
        data["users"][row["key"]] = {"name": row["name"], "token": row["token"]}
    for row in conn.execute("SELECT * FROM lineups ORDER BY date, rowid"):
        data["lineups"].setdefault(row["date"], {})[row["user_key"]] = _entry(row)
    return data


def get_user(conn, key):
    row = conn.execute("SELECT key, name, token FROM users WHERE key = ?", (key,)).fetchone()
    return {"name": row["name"], "token": row["token"]} if row else None


def get_entry(conn, date, key):
    row = conn.execute("SELECT * FROM lineups WHERE date = ? AND user_key = ?", (date, key)).fetchone()
    return _entry(row) if row else None


def put_user(conn, key, name, token):
    conn.execute(
        "INSERT INTO users (key, name, token) VALUES (?, ?, ?)"
        " ON CONFLICT(key) DO UPDATE SET name = excluded.name, token = excluded.token",
        (key, name, token),
    )


def rename_user(conn, key, new_key, new_name):
    conn.execute("UPDATE users SET key = ?, name = ? WHERE key = ?", (new_key, new_name, key))


def put_lineup(conn, date, key, slots):
    """Save a lineup's picks; it counts as unsettled again."""
    conn.execute(
        "INSERT INTO lineups (date, user_key, slots) VALUES (?, ?, ?)"
        " ON CONFLICT(date, user_key) DO UPDATE SET slots = excluded.slots, final_total = NULL,"
        " scoring_version = NULL, pick_points = NULL, updated_at = datetime('now')",
        (date, key, json.dumps(slots, ensure_ascii=False)),
    )


def delete_lineup(conn, date, key):
    conn.execute("DELETE FROM lineups WHERE date = ? AND user_key = ?", (date, key))


def settle(date, key, total, scoring_version, pick_points):
    with writing() as conn:
        conn.execute(
            "UPDATE lineups SET final_total = ?, scoring_version = ?, pick_points = ?, updated_at = datetime('now')"
            " WHERE date = ? AND user_key = ?",
            (total, scoring_version, json.dumps(pick_points, ensure_ascii=False), date, key),
        )


def backup(target=None):
    """Copy the database (consistent even while it's in use) and keep the newest BACKUPS_KEPT copies."""
    _ensure_ready()
    if target is None:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        target = BACKUP_DIR / f"fantasy-{time.strftime('%Y%m%d-%H%M%S')}.db"
    source = _connect()
    try:
        dest = sqlite3.connect(target)
        try:
            source.backup(dest)
        finally:
            dest.close()
    finally:
        source.close()
    if target.parent == BACKUP_DIR:
        for old in sorted(BACKUP_DIR.glob("fantasy-*.db"))[:-BACKUPS_KEPT]:
            old.unlink()
    return target


def last_backup_time():
    """Unix time of the newest automatic backup, or 0."""
    copies = sorted(BACKUP_DIR.glob("fantasy-*.db")) if BACKUP_DIR.exists() else []
    return copies[-1].stat().st_mtime if copies else 0
