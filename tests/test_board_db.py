import sqlite3
import threading

import pytest

from board_db import BoardDB

D1, D2 = "2026-11-02", "2026-11-03"
MONDAY_AFTER = "2026-11-09"


@pytest.fixture
def db(tmp_path):
    return BoardDB(tmp_path / "board.db")


def add_rows(db, d, names):
    db.ensure_day(d)
    for n in names:
        rid = db.add_schedule_row(d)
        db.update_schedule_row(rid, {"company": n})


def companies(db, d):
    return [r["company"] for r in db.list_schedule(d)]


def test_carry_over_copies_previous_rows(db):
    add_rows(db, D1, ["1班", "見本電機"])
    db.ensure_day(D2)
    assert companies(db, D2) == ["1班", "見本電機"]
    assert companies(db, D1) == ["1班", "見本電機"]


def test_carry_over_is_independent_copy(db):
    add_rows(db, D1, ["1班"])
    db.ensure_day(D2)
    row = db.list_schedule(D2)[0]
    db.update_schedule_row(row["id"], {"company": "2班"})
    assert companies(db, D1) == ["1班"]


def test_carry_over_across_weekend_uses_latest_day_with_rows(db):
    add_rows(db, D1, ["1班", "2班"])
    db.ensure_day(MONDAY_AFTER)
    assert companies(db, MONDAY_AFTER) == ["1班", "2班"]


def test_ensure_day_twice_does_not_duplicate(db):
    add_rows(db, D1, ["1班"])
    db.ensure_day(D2)
    db.ensure_day(D2)
    assert companies(db, D2) == ["1班"]


def test_carry_over_copies_construction(db):
    add_rows(db, D1, ["1班"])
    db.update_schedule_row(db.list_schedule(D1)[0]["id"], {"construction": "配管工事"})
    db.ensure_day(D2)
    row = db.list_schedule(D2)[0]
    assert (row["company"], row["construction"]) == ("1班", "配管工事")


def test_new_rows_have_empty_construction(db):
    db.ensure_day(D1)
    sid = db.add_schedule_row(D1)
    hid = db.add_holiday_row("2026-11-07")
    assert db.get_schedule_row(sid)["construction"] == ""
    assert db.get_holiday_row(hid)["construction"] == ""


def test_construction_is_updatable_on_both_tables(db):
    db.ensure_day(D1)
    sid = db.add_schedule_row(D1)
    hid = db.add_holiday_row("2026-11-07")
    assert db.update_schedule_row(sid, {"construction": "電気工事"}) is True
    assert db.update_holiday_row(hid, {"construction": "塗装工事"}) is True
    assert db.get_schedule_row(sid)["construction"] == "電気工事"
    assert db.get_holiday_row(hid)["construction"] == "塗装工事"
    assert db.list_schedule(D1)[0]["construction"] == "電気工事"
    assert db.list_holiday_rows("2026-11-02", "2026-11-08")[0]["construction"] == "塗装工事"


OLD_SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value INTEGER NOT NULL);
INSERT INTO meta(key, value) VALUES ('rev', 5);
CREATE TABLE days(
    date TEXT PRIMARY KEY,
    schedule_initialized INTEGER NOT NULL DEFAULT 0,
    genres_initialized INTEGER NOT NULL DEFAULT 0,
    notices_initialized INTEGER NOT NULL DEFAULT 0);
CREATE TABLE notice_rows(
    id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, position INTEGER NOT NULL,
    text TEXT NOT NULL DEFAULT '', red INTEGER NOT NULL DEFAULT 0);
CREATE TABLE schedule_rows(
    id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, position INTEGER NOT NULL,
    company TEXT NOT NULL DEFAULT '', leader TEXT NOT NULL DEFAULT '',
    work TEXT NOT NULL DEFAULT '', start_time TEXT NOT NULL DEFAULT '',
    end_time TEXT NOT NULL DEFAULT '');
CREATE TABLE holiday_rows(
    id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL,
    person TEXT NOT NULL DEFAULT '', work TEXT NOT NULL DEFAULT '',
    start_time TEXT NOT NULL DEFAULT '', end_time TEXT NOT NULL DEFAULT '');
CREATE TABLE checked_genres(
    date TEXT NOT NULL, genre TEXT NOT NULL, PRIMARY KEY(date, genre));
INSERT INTO schedule_rows(date, position, company, work) VALUES ('2026-11-02', 1, '1班', '配線工事');
INSERT INTO holiday_rows(date, person, work) VALUES ('2026-11-07', '山田', '清掃');
"""


def make_old_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(OLD_SCHEMA)
    conn.commit()
    conn.close()


def columns(path, table):
    conn = sqlite3.connect(path)
    try:
        return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    finally:
        conn.close()


def test_old_database_without_construction_is_migrated(tmp_path):
    path = tmp_path / "board.db"
    make_old_db(path)
    assert "construction" not in columns(path, "schedule_rows")
    db = BoardDB(path)
    assert "construction" in columns(path, "schedule_rows")
    assert "construction" in columns(path, "holiday_rows")
    sched = db.list_schedule("2026-11-02")
    assert [(r["company"], r["work"], r["construction"]) for r in sched] == [("1班", "配線工事", "")]
    hol = db.list_holiday_rows("2026-11-02", "2026-11-08")
    assert [(r["person"], r["work"], r["construction"]) for r in hol] == [("山田", "清掃", "")]
    assert db.get_rev() == 5
    db.update_schedule_row(sched[0]["id"], {"construction": "配管工事"})
    assert db.get_schedule_row(sched[0]["id"])["construction"] == "配管工事"


def test_migration_is_safe_to_run_every_start(tmp_path):
    path = tmp_path / "board.db"
    make_old_db(path)
    db = BoardDB(path)
    db.update_schedule_row(db.list_schedule("2026-11-02")[0]["id"], {"construction": "配管工事"})
    db = BoardDB(path)
    BoardDB(path)
    assert columns(path, "schedule_rows").count("construction") == 1
    assert columns(path, "holiday_rows").count("construction") == 1
    assert db.list_schedule("2026-11-02")[0]["construction"] == "配管工事"


def test_concurrent_start_on_old_database_adds_column_once(tmp_path):
    path = tmp_path / "board.db"
    make_old_db(path)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")  # 運用中の board.db は WAL。初回の WAL 切替の競合はここでは扱わない
    conn.close()
    errors = []

    def start():
        try:
            BoardDB(path)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=start) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert columns(path, "schedule_rows").count("construction") == 1
    assert columns(path, "holiday_rows").count("construction") == 1


def test_new_database_has_construction_columns(tmp_path):
    path = tmp_path / "board.db"
    BoardDB(path)
    assert "construction" in columns(path, "schedule_rows")
    assert "construction" in columns(path, "holiday_rows")


def test_delete_all_then_no_recopy(db):
    add_rows(db, D1, ["1班", "2班"])
    db.ensure_day(D2)
    for r in db.list_schedule(D2):
        db.delete_schedule_row(r["id"])
    db.ensure_day(D2)
    assert db.list_schedule(D2) == []


def test_no_previous_day_starts_empty(db):
    db.ensure_day(D1)
    assert db.list_schedule(D1) == []


def test_delete_compacts_positions(db):
    add_rows(db, D1, ["A", "B", "C"])
    rows = db.list_schedule(D1)
    assert db.delete_schedule_row(rows[1]["id"]) is True
    after = db.list_schedule(D1)
    assert [(r["company"], r["position"]) for r in after] == [("A", 1), ("C", 2)]
    new_id = db.add_schedule_row(D1)
    assert db.get_schedule_row(new_id)["position"] == 3


def test_delete_missing_row_returns_false(db):
    assert db.delete_schedule_row(999) is False


def test_move_up_and_down(db):
    add_rows(db, D1, ["A", "B", "C"])
    ids = {r["company"]: r["id"] for r in db.list_schedule(D1)}
    assert db.move_schedule_row(ids["C"], "up") is True
    assert companies(db, D1) == ["A", "C", "B"]
    assert db.move_schedule_row(ids["A"], "up") is False
    assert db.move_schedule_row(ids["B"], "down") is False
    assert db.move_schedule_row(ids["A"], "down") is True
    assert companies(db, D1) == ["C", "A", "B"]


def test_update_rejects_unknown_field_and_missing_row(db):
    add_rows(db, D1, ["A"])
    rid = db.list_schedule(D1)[0]["id"]
    with pytest.raises(ValueError):
        db.update_schedule_row(rid, {"position": 9})
    assert db.update_schedule_row(999, {"company": "X"}) is False


def test_notices_start_with_three_empty_rows(db):
    db.ensure_day(D1)
    rows = db.list_notices(D1)
    assert [r["position"] for r in rows] == [1, 2, 3]
    assert all(r["text"] == "" and r["red"] is False for r in rows)


def test_notice_add_update_delete_compacts(db):
    db.ensure_day(D1)
    new_id = db.add_notice(D1)
    assert [r["position"] for r in db.list_notices(D1)] == [1, 2, 3, 4]
    assert db.update_notice(new_id, {"text": "避難訓練", "red": True}) is True
    rows = db.list_notices(D1)
    assert (rows[3]["text"], rows[3]["red"]) == ("避難訓練", True)
    assert db.delete_notice(rows[1]["id"]) is True
    after = db.list_notices(D1)
    assert [r["position"] for r in after] == [1, 2, 3]
    assert after[2]["text"] == "避難訓練"


def test_notices_cannot_go_below_three(db):
    db.ensure_day(D1)
    rows = db.list_notices(D1)
    with pytest.raises(ValueError):
        db.delete_notice(rows[0]["id"])
    assert len(db.list_notices(D1)) == 3
    assert db.delete_notice(999) is False


def test_notices_are_not_carried_over(db):
    db.ensure_day(D1)
    db.update_notice(db.list_notices(D1)[0]["id"], {"text": "昨日の連絡"})
    db.ensure_day(D2)
    assert [r["text"] for r in db.list_notices(D2)] == ["", "", ""]


def test_genres_toggle_and_carry_over(db):
    db.ensure_day(D1)
    db.set_genre(D1, "溶接作業", True)
    db.set_genre(D1, "高所作業", True)
    db.set_genre(D1, "高所作業", False)
    assert db.get_checked_genres(D1) == ["溶接作業"]
    db.ensure_day(D2)
    assert db.get_checked_genres(D2) == ["溶接作業"]
    db.set_genre(D2, "溶接作業", False)
    assert db.get_checked_genres(D1) == ["溶接作業"]


def test_holiday_rows_filtered_by_range_and_sorted(db):
    for d in ["2026-11-07", "2026-11-03", "2026-10-31"]:
        db.add_holiday_row(d)
    rows = db.list_holiday_rows("2026-11-02", "2026-11-08")
    assert [r["date"] for r in rows] == ["2026-11-03", "2026-11-07"]


def test_holiday_row_update_and_delete(db):
    rid = db.add_holiday_row("2026-11-07")
    assert db.update_holiday_row(rid, {"person": "山田", "work": "清掃"}) is True
    assert db.get_holiday_row(rid)["person"] == "山田"
    assert db.delete_holiday_row(rid) is True
    assert db.get_holiday_row(rid) is None


def test_rev_increases_on_every_write(db):
    r0 = db.get_rev()
    db.ensure_day(D1)
    r1 = db.get_rev()
    rid = db.add_schedule_row(D1)
    r2 = db.get_rev()
    db.update_schedule_row(rid, {"company": "A"})
    r3 = db.get_rev()
    assert r0 < r1 < r2 < r3
    db.ensure_day(D1)
    assert db.get_rev() == r3


# ---- 今週の休日の行を最初から作る ----
WEEK = ("2026-11-03", "2026-11-07", "2026-11-08")
WEEK_START, WEEK_END = "2026-11-02", "2026-11-08"


def week_rows(db):
    return db.list_holiday_rows(WEEK_START, WEEK_END)


def test_seed_holidays_creates_one_empty_row_per_date(db):
    assert db.seed_holidays(WEEK) is True
    rows = week_rows(db)
    assert [r["date"] for r in rows] == list(WEEK)
    for r in rows:
        assert (r["construction"], r["person"], r["work"], r["start_time"], r["end_time"]) == ("", "", "", "", "")


def test_seed_holidays_is_idempotent_and_does_not_bump_rev_again(db):
    r0 = db.get_rev()
    assert db.seed_holidays(WEEK) is True
    r1 = db.get_rev()
    assert r1 > r0
    assert db.seed_holidays(WEEK) is False
    assert db.seed_holidays([]) is False
    assert db.get_rev() == r1
    assert len(week_rows(db)) == 3


def test_deleted_seeded_row_does_not_come_back(db):
    db.seed_holidays(WEEK)
    row = week_rows(db)[1]
    assert db.delete_holiday_row(row["id"]) is True
    assert db.seed_holidays(WEEK) is False
    assert [r["date"] for r in week_rows(db)] == ["2026-11-03", "2026-11-08"]


def test_holiday_added_later_gets_its_row(db):
    db.seed_holidays(WEEK)
    assert db.seed_holidays(WEEK + ("2026-11-05",)) is True
    assert [r["date"] for r in week_rows(db)] == ["2026-11-03", "2026-11-05", "2026-11-07", "2026-11-08"]
    assert db.seed_holidays(WEEK + ("2026-11-05",)) is False


def test_seed_does_not_add_a_row_where_one_already_exists(db):
    # 旧版の board.db には、この仕組みの前に利用者が入れた行がある。その日付には空の行を足さない
    rid = db.add_holiday_row("2026-11-07")
    db.update_holiday_row(rid, {"person": "山田"})
    db.seed_holidays(WEEK)
    rows = week_rows(db)
    assert [r["date"] for r in rows] == ["2026-11-03", "2026-11-07", "2026-11-08"]
    assert rows[1]["person"] == "山田"
    assert db.seed_holidays(WEEK) is False


def test_seeding_survives_reopening_an_existing_database(tmp_path):
    path = tmp_path / "board.db"
    BoardDB(path).seed_holidays(WEEK)
    db = BoardDB(path)
    assert db.seed_holidays(WEEK) is False
    assert len(week_rows(db)) == 3


def test_seed_table_is_added_to_a_database_made_before_this_feature(tmp_path):
    path = tmp_path / "board.db"
    make_old_db(path)
    db = BoardDB(path)
    assert db.seed_holidays(WEEK) is True
    rows = week_rows(db)
    assert sorted(r["date"] for r in rows) == ["2026-11-03", "2026-11-07", "2026-11-08"]
    assert [r["person"] for r in rows if r["date"] == "2026-11-07"] == ["山田"]


def test_concurrent_first_seeding_creates_each_row_once(tmp_path):
    path = tmp_path / "board.db"
    db = BoardDB(path)
    errors, results = [], []

    def seed():
        try:
            results.append(BoardDB(path).seed_holidays(WEEK))
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=seed) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert results.count(True) == 1
    assert [r["date"] for r in week_rows(db)] == list(WEEK)


def test_old_database_gets_holiday_leader_column(tmp_path):
    path = tmp_path / "board.db"
    make_old_db(path)
    db = BoardDB(path)
    db = BoardDB(path)  # 2回目の起動でも列は1つだけ
    assert columns(path, "holiday_rows").count("leader") == 1
    hol = db.list_holiday_rows("2026-11-02", "2026-11-08")
    assert [(r["person"], r["leader"]) for r in hol] == [("山田", "")]
    db.update_holiday_row(hol[0]["id"], {"leader": "佐藤"})
    assert db.get_holiday_row(hol[0]["id"])["leader"] == "佐藤"
