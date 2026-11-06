from datetime import date, timedelta

import pytest

from app import create_app
from conftest import write_masters

COMPANIES = {"1班": [("佐藤", "1234", ""), ("鈴木", "1235", "")], "見本電機": [("田中", "", "03-0000-0001")]}
EQUIPMENT = "name\nコンプレッサ\nクレーン\n"


@pytest.fixture
def env(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    write_masters(data, COMPANIES, {})
    (data / "equipment.csv").write_text(EQUIPMENT, encoding="utf-8-sig")
    clock = {"today": date(2026, 11, 5)}
    app = create_app(tmp_path, today_func=lambda: clock["today"])
    return app.test_client(), clock, tmp_path


def board(c):
    r = c.get("/api/board")
    assert r.status_code == 200
    return r.get_json()


def test_day_starts_with_two_empty_rows_and_the_equipment_list(env):
    c, _, _ = env
    b = board(c)
    assert [(r["equipment"], r["company"], r["user"], r["start_time"], r["end_time"]) for r in b["equipment"]] == [("", "", "", "", "")] * 2
    assert b["masters"]["equipment"] == ["コンプレッサ", "クレーン"]
    assert board(c)["equipment"] == b["equipment"]  # 何度読んでも増えない


def test_fill_a_row(env):
    c, _, _ = env
    rid = board(c)["equipment"][0]["id"]
    for body in ({"equipment": "クレーン"}, {"company": "1班"}, {"user": "鈴木"}, {"start_time": "9:00", "end_time": "12:00"}):
        assert c.patch(f"/api/equipment/{rid}", json=body).status_code == 200
    r = board(c)["equipment"][0]
    assert (r["equipment"], r["company"], r["user"], r["start_time"], r["end_time"]) == ("クレーン", "1班", "鈴木", "9:00", "12:00")


def test_typed_values_are_saved_but_times_must_be_registered(env):
    c, _, _ = env
    rid = board(c)["equipment"][0]["id"]
    for body in ({"equipment": "ショベル"}, {"company": "無い会社"}, {"user": "山本"}):
        assert c.patch(f"/api/equipment/{rid}", json=body).status_code == 200, body
    r = board(c)["equipment"][0]
    assert (r["equipment"], r["company"], r["user"]) == ("ショベル", "無い会社", "山本")
    assert c.patch(f"/api/equipment/{rid}", json={"equipment": "あ" * 31}).status_code == 400
    assert c.patch(f"/api/equipment/{rid}", json={"start_time": "9:15"}).status_code == 400
    assert c.patch(f"/api/equipment/{rid}", json={"bogus": "x"}).status_code == 400


def test_company_change_clears_user(env):
    c, _, _ = env
    rid = board(c)["equipment"][0]["id"]
    c.patch(f"/api/equipment/{rid}", json={"company": "1班"})
    assert c.patch(f"/api/equipment/{rid}", json={"user": "佐藤"}).status_code == 200
    c.patch(f"/api/equipment/{rid}", json={"company": "見本電機"})
    assert board(c)["equipment"][0]["user"] == ""


def test_add_and_delete_rows(env):
    c, _, _ = env
    first, second = [r["id"] for r in board(c)["equipment"]]
    new = c.post("/api/equipment").get_json()["id"]
    assert [r["id"] for r in board(c)["equipment"]] == [first, second, new]
    assert c.delete(f"/api/equipment/{first}").status_code == 200
    assert [r["id"] for r in board(c)["equipment"]] == [second, new]
    assert c.delete(f"/api/equipment/{first}").status_code == 404
    assert c.patch(f"/api/equipment/{first}", json={"equipment": "クレーン"}).status_code == 404


def test_next_day_clears_the_list(env):
    c, clock, _ = env
    old = board(c)["equipment"]
    c.patch(f"/api/equipment/{old[0]['id']}", json={"equipment": "クレーン"})
    c.post("/api/equipment")
    clock["today"] += timedelta(days=1)
    rows = board(c)["equipment"]
    assert len(rows) == 2 and all(r["equipment"] == "" for r in rows)
    assert not {r["id"] for r in rows} & {r["id"] for r in old}
    assert c.patch(f"/api/equipment/{old[0]['id']}", json={"equipment": "コンプレッサ"}).status_code == 404  # 前の日の行は消えている


def test_first_write_of_a_day_also_starts_fresh(env):
    c, clock, _ = env
    rid = board(c)["equipment"][0]["id"]
    c.patch(f"/api/equipment/{rid}", json={"equipment": "クレーン"})
    clock["today"] += timedelta(days=1)
    c.post("/api/equipment")  # 画面を読む前に追加しても、まず空の2行が用意される
    assert [r["equipment"] for r in board(c)["equipment"]] == ["", "", ""]


def test_missing_equipment_file_is_created_with_samples(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    write_masters(data, COMPANIES, {})
    c = create_app(tmp_path, today_func=lambda: date(2026, 11, 5)).test_client()
    assert (data / "equipment.csv").exists()
    b = board(c)
    assert "コンプレッサ" in b["masters"]["equipment"]
    assert not any("equipment" in w for w in b["warnings"])


def test_rev_changes_when_the_equipment_file_is_edited(env):
    c, _, tmp_path = env
    board(c)
    rev = c.get("/api/rev").get_json()["rev"]
    (tmp_path / "data" / "equipment.csv").write_text(EQUIPMENT + "フォークリフト\n", encoding="utf-8-sig")
    assert c.get("/api/rev").get_json()["rev"] != rev
    assert board(c)["masters"]["equipment"][-1] == "フォークリフト"
