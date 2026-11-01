import sqlite3
from contextlib import contextmanager

SCHEDULE_FIELDS = ("company", "leader", "work", "start_time", "end_time", "construction")
HOLIDAY_FIELDS = ("date", "person", "work", "start_time", "end_time", "construction")
NOTICE_FIELDS = ("text", "red")
MIN_NOTICES = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value INTEGER NOT NULL);
INSERT OR IGNORE INTO meta(key, value) VALUES ('rev', 0);
CREATE TABLE IF NOT EXISTS days(
    date TEXT PRIMARY KEY,
    schedule_initialized INTEGER NOT NULL DEFAULT 0,
    genres_initialized INTEGER NOT NULL DEFAULT 0,
    notices_initialized INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS notice_rows(
    id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, position INTEGER NOT NULL,
    text TEXT NOT NULL DEFAULT '', red INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS schedule_rows(
    id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, position INTEGER NOT NULL,
    company TEXT NOT NULL DEFAULT '', leader TEXT NOT NULL DEFAULT '',
    work TEXT NOT NULL DEFAULT '', start_time TEXT NOT NULL DEFAULT '',
    end_time TEXT NOT NULL DEFAULT '', construction TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS holiday_rows(
    id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL,
    person TEXT NOT NULL DEFAULT '', work TEXT NOT NULL DEFAULT '',
    start_time TEXT NOT NULL DEFAULT '', end_time TEXT NOT NULL DEFAULT '',
    construction TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS holiday_seeded(date TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS checked_genres(
    date TEXT NOT NULL, genre TEXT NOT NULL, PRIMARY KEY(date, genre));
"""


class BoardDB:
    def __init__(self, path):
        self.path = str(path)
        with self._tx(write=False) as c:
            c.executescript(SCHEMA)
        self._migrate()

    def _migrate(self):
        # 古い board.db に「工事件名」列を足す。毎回の起動で実行しても安全（列があれば何もしない）。
        # 書き込みロックを取ってから確認するので、同時に起動しても二重には足されない
        with self._tx() as c:
            for table in ("schedule_rows", "holiday_rows"):
                cols = [r["name"] for r in c.execute(f"PRAGMA table_info({table})")]
                if "construction" not in cols:
                    c.execute(f"ALTER TABLE {table} ADD COLUMN construction TEXT NOT NULL DEFAULT ''")

    @contextmanager
    def _tx(self, write=True):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            if write:
                # 読み取り→書き込みの間に他のリクエストが割り込まないよう、最初に書き込みロックを取る
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _bump(c):
        c.execute("UPDATE meta SET value = value + 1 WHERE key = 'rev'")

    def get_rev(self):
        with self._tx(write=False) as c:
            return c.execute("SELECT value FROM meta WHERE key = 'rev'").fetchone()["value"]

    # ---- 日付の初期化（前日の引き継ぎ） ----
    def ensure_day(self, d):
        with self._tx() as c:
            c.execute("INSERT OR IGNORE INTO days(date) VALUES (?)", (d,))
            flags = c.execute(
                "SELECT schedule_initialized AS s, genres_initialized AS g, notices_initialized AS n "
                "FROM days WHERE date = ?",
                (d,),
            ).fetchone()
            changed = False
            if not flags["s"]:
                prev = c.execute("SELECT MAX(date) AS m FROM schedule_rows WHERE date < ?", (d,)).fetchone()["m"]
                if prev:
                    c.execute(
                        "INSERT INTO schedule_rows(date, position, company, leader, work, start_time, end_time, construction) "
                        "SELECT ?, position, company, leader, work, start_time, end_time, construction "
                        "FROM schedule_rows WHERE date = ? ORDER BY position",
                        (d, prev),
                    )
                c.execute("UPDATE days SET schedule_initialized = 1 WHERE date = ?", (d,))
                changed = True
            if not flags["g"]:
                prev = c.execute("SELECT MAX(date) AS m FROM checked_genres WHERE date < ?", (d,)).fetchone()["m"]
                if prev:
                    c.execute(
                        "INSERT INTO checked_genres(date, genre) SELECT ?, genre FROM checked_genres WHERE date = ?",
                        (d, prev),
                    )
                c.execute("UPDATE days SET genres_initialized = 1 WHERE date = ?", (d,))
                changed = True
            if not flags["n"]:
                c.executemany(
                    "INSERT INTO notice_rows(date, position) VALUES (?, ?)",
                    [(d, i) for i in range(1, MIN_NOTICES + 1)],
                )
                c.execute("UPDATE days SET notices_initialized = 1 WHERE date = ?", (d,))
                changed = True
            if changed:
                self._bump(c)

    # ---- 連絡事項 ----
    def list_notices(self, d):
        with self._tx(write=False) as c:
            rows = c.execute("SELECT * FROM notice_rows WHERE date = ? ORDER BY position", (d,)).fetchall()
        return [{**dict(r), "red": bool(r["red"])} for r in rows]

    def add_notice(self, d):
        with self._tx() as c:
            pos = c.execute(
                "SELECT COALESCE(MAX(position), 0) + 1 AS p FROM notice_rows WHERE date = ?", (d,)
            ).fetchone()["p"]
            cur = c.execute("INSERT INTO notice_rows(date, position) VALUES (?, ?)", (d, pos))
            self._bump(c)
            return cur.lastrowid

    def update_notice(self, row_id, fields):
        return self._update("notice_rows", NOTICE_FIELDS, row_id, fields)

    def delete_notice(self, row_id):
        with self._tx() as c:
            row = c.execute("SELECT date, position FROM notice_rows WHERE id = ?", (row_id,)).fetchone()
            if not row:
                return False
            count = c.execute("SELECT COUNT(*) AS n FROM notice_rows WHERE date = ?", (row["date"],)).fetchone()["n"]
            if count <= MIN_NOTICES:
                raise ValueError("連絡事項は3行より少なくできません")
            c.execute("DELETE FROM notice_rows WHERE id = ?", (row_id,))
            c.execute(
                "UPDATE notice_rows SET position = position - 1 WHERE date = ? AND position > ?",
                (row["date"], row["position"]),
            )
            self._bump(c)
            return True

    # ---- 共通 ----
    def _update(self, table, allowed, row_id, fields):
        bad = [k for k in fields if k not in allowed]
        if bad:
            raise ValueError(f"更新できない列: {bad}")
        if not fields:
            return False
        sets = ", ".join(f"{k} = ?" for k in fields)
        with self._tx() as c:
            cur = c.execute(f"UPDATE {table} SET {sets} WHERE id = ?", (*fields.values(), row_id))
            if cur.rowcount:
                self._bump(c)
            return cur.rowcount > 0

    def _get(self, table, row_id):
        with self._tx(write=False) as c:
            r = c.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
        return dict(r) if r else None

    # ---- 本日の作業予定 ----
    def list_schedule(self, d):
        with self._tx(write=False) as c:
            rows = c.execute("SELECT * FROM schedule_rows WHERE date = ? ORDER BY position", (d,)).fetchall()
        return [dict(r) for r in rows]

    def get_schedule_row(self, row_id):
        return self._get("schedule_rows", row_id)

    def add_schedule_row(self, d):
        with self._tx() as c:
            pos = c.execute(
                "SELECT COALESCE(MAX(position), 0) + 1 AS p FROM schedule_rows WHERE date = ?", (d,)
            ).fetchone()["p"]
            cur = c.execute("INSERT INTO schedule_rows(date, position) VALUES (?, ?)", (d, pos))
            self._bump(c)
            return cur.lastrowid

    def update_schedule_row(self, row_id, fields):
        return self._update("schedule_rows", SCHEDULE_FIELDS, row_id, fields)

    def delete_schedule_row(self, row_id):
        with self._tx() as c:
            row = c.execute("SELECT date, position FROM schedule_rows WHERE id = ?", (row_id,)).fetchone()
            if not row:
                return False
            c.execute("DELETE FROM schedule_rows WHERE id = ?", (row_id,))
            c.execute(
                "UPDATE schedule_rows SET position = position - 1 WHERE date = ? AND position > ?",
                (row["date"], row["position"]),
            )
            self._bump(c)
            return True

    def move_schedule_row(self, row_id, direction):
        if direction not in ("up", "down"):
            raise ValueError("direction は up / down")
        with self._tx() as c:
            row = c.execute("SELECT date, position FROM schedule_rows WHERE id = ?", (row_id,)).fetchone()
            if not row:
                return False
            target = row["position"] + (-1 if direction == "up" else 1)
            other = c.execute(
                "SELECT id FROM schedule_rows WHERE date = ? AND position = ?", (row["date"], target)
            ).fetchone()
            if not other:
                return False
            c.execute("UPDATE schedule_rows SET position = ? WHERE id = ?", (target, row_id))
            c.execute("UPDATE schedule_rows SET position = ? WHERE id = ?", (row["position"], other["id"]))
            self._bump(c)
            return True

    # ---- 休日出勤予定 ----
    def list_holiday_rows(self, start, end):
        with self._tx(write=False) as c:
            rows = c.execute(
                "SELECT * FROM holiday_rows WHERE date >= ? AND date <= ? ORDER BY date, id", (start, end)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_holiday_row(self, row_id):
        return self._get("holiday_rows", row_id)

    def add_holiday_row(self, d):
        with self._tx() as c:
            cur = c.execute("INSERT INTO holiday_rows(date) VALUES (?)", (d,))
            self._bump(c)
            return cur.lastrowid

    def update_holiday_row(self, row_id, fields):
        return self._update("holiday_rows", HOLIDAY_FIELDS, row_id, fields)

    def delete_holiday_row(self, row_id):
        with self._tx() as c:
            cur = c.execute("DELETE FROM holiday_rows WHERE id = ?", (row_id,))
            if cur.rowcount:
                self._bump(c)
            return cur.rowcount > 0

    def seed_holidays(self, dates):
        # 休日1日につき、空の行を1回だけ作る。一度作った日付は holiday_seeded に残すので、利用者が消した行は戻らない
        # すでにその日の行がある日付（この仕組みより前の board.db）には足さない
        with self._tx() as c:
            changed = False
            for d in dates:
                if c.execute("INSERT OR IGNORE INTO holiday_seeded(date) VALUES (?)", (d,)).rowcount:
                    if not c.execute("SELECT 1 FROM holiday_rows WHERE date = ?", (d,)).fetchone():
                        c.execute("INSERT INTO holiday_rows(date) VALUES (?)", (d,))
                    changed = True
            if changed:
                self._bump(c)
            return changed

    # ---- 作業ジャンル ----
    def get_checked_genres(self, d):
        with self._tx(write=False) as c:
            rows = c.execute("SELECT genre FROM checked_genres WHERE date = ? ORDER BY genre", (d,)).fetchall()
        return [r["genre"] for r in rows]

    def set_genre(self, d, genre, checked):
        with self._tx() as c:
            if checked:
                c.execute("INSERT OR IGNORE INTO checked_genres(date, genre) VALUES (?, ?)", (d, genre))
            else:
                c.execute("DELETE FROM checked_genres WHERE date = ? AND genre = ?", (d, genre))
            self._bump(c)
