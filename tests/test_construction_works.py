import os
import shutil
from datetime import date
from pathlib import Path

import pytest

import masters as m
from app import create_app
from conftest import write_masters

ROOT = Path(__file__).resolve().parent.parent

GENRES = "name\n溶接作業\n"
COMPANIES = {"1班": [("佐藤", "1234", "")], "見本電機": []}
# 配管工事: 組み立て作業だけ / 電気工事: 配線工事・組み立て作業 / 塗装工事: 登録なし（何でも選べる）
# 清掃工事は、作業内容の全体に「清掃」を入れるための工事件名（作業内容の全体 = 組み立て作業・配線工事・清掃）
MAP = {"配管工事": ["組み立て作業"], "電気工事": ["配線工事", "組み立て作業"], "塗装工事": [], "清掃工事": ["清掃"]}


def write(path, text, bom=True):
    path.write_text(text, encoding="utf-8-sig" if bom else "utf-8", newline="")


def masters_dir(tmp_path, constructions=MAP):
    write_masters(tmp_path, COMPANIES, constructions)
    write(tmp_path / "genres.csv", GENRES)
    return m.Masters(tmp_path)


def work_file(tmp_path, name):
    return tmp_path / "constructions" / f"{name}.csv"


# ---- CSV の読み込み ----
def test_constructions_without_works_mean_no_restriction_and_no_warning(tmp_path):
    data = masters_dir(tmp_path, {"配管工事": [], "電気工事": []}).load_all()
    assert data["constructions"] == ["配管工事", "電気工事"]
    assert data["construction_works"] == {}
    assert data["warnings"] == []


def test_loads_works_in_row_order_with_bom_and_crlf(tmp_path):
    mm = masters_dir(tmp_path, {"電気工事": [], "配管工事": []})
    work_file(tmp_path, "電気工事").write_bytes("﻿作業内容\r\n配線工事\r\n組み立て作業\r\n".encode("utf-8"))
    work_file(tmp_path, "配管工事").write_bytes("作業内容\r\n組み立て作業\r\n".encode("utf-8"))
    data = mm.load_all()
    assert data["construction_works"] == {"配管工事": ["組み立て作業"], "電気工事": ["配線工事", "組み立て作業"]}
    assert list(data["construction_works"]) == ["配管工事", "電気工事"]  # 工事件名のファイル名の順
    assert data["warnings"] == []


def test_blank_rows_are_skipped_silently_and_duplicates_with_one_warning(tmp_path):
    mm = masters_dir(tmp_path, {"配管工事": []})
    write(work_file(tmp_path, "配管工事"), "作業内容\n\n組み立て作業\n,\n組み立て作業\n  \n")
    data = mm.load_all()
    assert data["construction_works"] == {"配管工事": ["組み立て作業"]}
    assert len(data["warnings"]) == 1 and "配管工事.csv" in data["warnings"][0] and "組み立て作業" in data["warnings"][0]


def test_construction_with_only_a_header_is_listed_but_unrestricted(tmp_path):
    data = masters_dir(tmp_path, {"電気工事": [], "配管工事": ["清掃"]}).load_all()
    assert data["constructions"] == ["配管工事", "電気工事"]
    assert data["construction_works"] == {"配管工事": ["清掃"]}
    assert data["warnings"] == []


def test_missing_column_or_bad_encoding_warns_and_the_construction_is_skipped(tmp_path):
    mm = masters_dir(tmp_path, {"電気工事": ["配線工事"]})
    write(work_file(tmp_path, "配管工事"), "construction\n配管工事\n")
    data = mm.load_all()
    assert data["constructions"] == ["電気工事"]
    assert data["construction_works"] == {"電気工事": ["配線工事"]}
    assert len(data["warnings"]) == 1 and "配管工事.csv" in data["warnings"][0]
    work_file(tmp_path, "配管工事").write_bytes("作業内容\n清掃\n".encode("cp932"))
    data = mm.load_all()
    assert data["constructions"] == ["電気工事"]
    assert len(data["warnings"]) == 1 and "配管工事.csv" in data["warnings"][0]


def test_signature_changes_when_a_construction_file_appears_or_is_edited(tmp_path):
    mm = masters_dir(tmp_path, {"配管工事": ["組み立て作業"]})
    none = mm.signature()
    p = work_file(tmp_path, "電気工事")
    write(p, "作業内容\n清掃\n")
    created = mm.signature()
    assert created != none
    st = p.stat()
    write(p, "作業内容\n清掃\n配線工事\n")  # 更新日時が同じでも、大きさが変われば気づく
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert mm.signature() != created


def test_sample_data_in_the_repo_loads_without_warnings(tmp_path):
    shutil.copytree(ROOT / "data" / "constructions", tmp_path / "constructions")
    for name in ("配管工事", "電気工事", "塗装工事", "足場工事", "設備据付工事"):
        raw = (tmp_path / "constructions" / f"{name}.csv").read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw
        assert raw[3:].startswith("作業内容\n".encode("utf-8"))
    write_masters(tmp_path, COMPANIES)
    write(tmp_path / "genres.csv", GENRES)
    data = m.Masters(tmp_path).load_all()
    assert data["warnings"] == []
    assert data["construction_works"] == {
        "配管工事": ["組み立て作業", "搬入作業", "メンテナンス作業"],
        "電気工事": ["配線工事", "メンテナンス作業"],
        "塗装工事": ["メンテナンス作業", "清掃"],
        "足場工事": ["高所作業", "搬入作業", "組み立て作業"],
        "設備据付工事": ["溶接作業", "組み立て作業", "搬入作業", "高所作業"],
    }
    assert set(data["construction_works"]) == set(data["constructions"])


# ---- API ----
@pytest.fixture
def env(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    masters_dir(data)
    app = create_app(tmp_path, today_func=lambda: date(2026, 11, 2))
    return app.test_client(), tmp_path


def board(c):
    r = c.get("/api/board")
    assert r.status_code == 200
    return r.get_json()


def new_schedule(c, **fields):
    rid = c.post("/api/schedule").get_json()["id"]
    if fields:
        assert c.patch(f"/api/schedule/{rid}", json=fields).status_code == 200
    return rid


def schedule_row(c, rid):
    return next(r for r in board(c)["schedule"] if r["id"] == rid)


def new_holiday(c, **fields):
    rid = board(c)["holiday_rows"][0]["id"]  # 最初から用意されている休日の行
    if fields:
        assert c.patch(f"/api/holiday-rows/{rid}", json=fields).status_code == 200
    return rid


def holiday_row(c, rid):
    return next(r for r in board(c)["holiday_rows"] if r["id"] == rid)


TABLES = {
    "schedule": ("/api/schedule", new_schedule, schedule_row),
    "holiday": ("/api/holiday-rows", new_holiday, holiday_row),
}


@pytest.fixture(params=["schedule", "holiday"])
def table(request, env):
    c, _ = env
    url, new, get = TABLES[request.param]
    return c, url, new, get


def test_board_exposes_the_map_and_nothing_else_changes(env, tmp_path):
    c, base = env
    mas = board(c)["masters"]
    assert mas["construction_works"] == {"配管工事": ["組み立て作業"], "電気工事": ["配線工事", "組み立て作業"], "清掃工事": ["清掃"]}
    assert mas["works"] == ["清掃", "組み立て作業", "配線工事"]  # 作業内容の全体 = 各工事件名の作業内容を、ファイルの順に並べて重なりを除いたもの
    assert set(mas) == {"companies", "leaders", "works", "constructions", "genres", "times", "construction_works", "equipment"}
    c2 = create_app(tmp_path / "plain", today_func=lambda: date(2026, 11, 2)).test_client()
    assert board(c2)["masters"]["construction_works"] == {}


def test_duplicate_works_show_one_warning_on_the_board(env):
    c, base = env
    assert board(c)["warnings"] == []
    write(work_file(base / "data", "配管工事"), "作業内容\n組み立て作業\n組み立て作業\n")
    warnings = board(c)["warnings"]
    assert len(warnings) == 1 and "配管工事.csv" in warnings[0] and "組み立て作業" in warnings[0]


def test_rev_changes_when_a_construction_file_is_edited(env):
    c, base = env
    before = c.get("/api/rev").get_json()["rev"]
    p = work_file(base / "data", "塗装工事")
    write(p, "作業内容\n清掃\n")
    assert c.get("/api/rev").get_json()["rev"] != before
    assert board(c)["masters"]["construction_works"]["塗装工事"] == ["清掃"]


def test_allowed_work_is_accepted_and_disallowed_is_rejected(table):
    c, url, new, get = table
    rid = new(c, construction="配管工事")
    assert c.patch(f"{url}/{rid}", json={"work": "組み立て作業"}).status_code == 200
    assert get(c, rid)["work"] == "組み立て作業"
    # 配管工事の選択肢には無いが、手入力として保存する
    assert c.patch(f"{url}/{rid}", json={"work": "配線工事"}).status_code == 200
    assert get(c, rid)["work"] == "配線工事"
    assert c.patch(f"{url}/{rid}", json={"work": ""}).status_code == 200  # 空はいつでも可
    assert get(c, rid)["work"] == ""


def test_unregistered_work_can_be_typed(table):
    c, url, new, get = table
    rid = new(c, construction="配管工事")
    assert c.patch(f"{url}/{rid}", json={"work": "未登録作業"}).status_code == 200
    assert get(c, rid)["work"] == "未登録作業"


def test_unmapped_or_empty_construction_allows_any_registered_work(table):
    c, url, new, get = table
    rid = new(c, construction="塗装工事")  # 対応の行が無い
    for w in ("組み立て作業", "配線工事", "清掃"):
        assert c.patch(f"{url}/{rid}", json={"work": w}).status_code == 200
    assert c.patch(f"{url}/{rid}", json={"construction": ""}).status_code == 200  # 工事件名が空でも何でも可
    for w in ("配線工事", "清掃"):
        assert c.patch(f"{url}/{rid}", json={"work": w}).status_code == 200
    assert get(c, rid)["work"] == "清掃"


def test_work_alone_is_checked_against_the_stored_construction(table):
    c, url, new, get = table
    rid = new(c, construction="電気工事")
    assert c.patch(f"{url}/{rid}", json={"work": "清掃"}).status_code == 200  # 手入力
    assert c.patch(f"{url}/{rid}", json={"work": "配線工事"}).status_code == 200


def test_changing_construction_clears_an_incompatible_work(table):
    c, url, new, get = table
    rid = new(c, construction="塗装工事", work="清掃")
    assert c.patch(f"{url}/{rid}", json={"construction": "配管工事"}).status_code == 200
    assert get(c, rid)["construction"] == "配管工事"
    assert get(c, rid)["work"] == ""  # 配管工事では選べないので、同じ更新で空になる


def test_changing_construction_keeps_a_compatible_work(table):
    c, url, new, get = table
    rid = new(c, construction="配管工事", work="組み立て作業")
    assert c.patch(f"{url}/{rid}", json={"construction": "電気工事"}).status_code == 200
    assert get(c, rid)["work"] == "組み立て作業"
    assert c.patch(f"{url}/{rid}", json={"construction": "塗装工事"}).status_code == 200  # 対応なし: 何でも可
    assert get(c, rid)["work"] == "組み立て作業"


def test_changing_construction_bumps_rev_once_and_other_fields_are_kept(table):
    c, url, new, get = table
    rid = new(c, construction="塗装工事", work="清掃")
    rev = c.get("/api/rev").get_json()["rev"]
    assert c.patch(f"{url}/{rid}", json={"construction": "配管工事", "start_time": "", "end_time": ""}).status_code == 200
    assert c.get("/api/rev").get_json()["rev"] != rev
    assert get(c, rid)["work"] == "" and get(c, rid)["construction"] == "配管工事"


def test_clearing_the_construction_never_clears_the_work(table):
    c, url, new, get = table
    rid = new(c, construction="配管工事", work="組み立て作業")
    assert c.patch(f"{url}/{rid}", json={"construction": ""}).status_code == 200
    assert get(c, rid)["construction"] == "" and get(c, rid)["work"] == "組み立て作業"


def test_same_construction_does_not_clear_a_stored_work(env):
    c, base = env
    rid = new_schedule(c, construction="塗装工事", work="清掃")
    write(work_file(base / "data", "塗装工事"), "作業内容\n組み立て作業\n")  # 後から対応が増えた
    assert c.patch(f"/api/schedule/{rid}", json={"construction": "塗装工事"}).status_code == 200
    assert schedule_row(c, rid)["work"] == "清掃"


def test_request_with_both_fields_is_validated_as_a_pair(table):
    c, url, new, get = table
    rid = new(c, construction="塗装工事", work="清掃")
    # 組み合わせが正しければ、保存してある作業内容が合わなくても通る
    assert c.patch(f"{url}/{rid}", json={"construction": "電気工事", "work": "配線工事"}).status_code == 200
    assert (get(c, rid)["construction"], get(c, rid)["work"]) == ("電気工事", "配線工事")
    # 組み合わせが選択肢に無くても、両方を送ったときは手入力として、そのまま保存する
    assert c.patch(f"{url}/{rid}", json={"construction": "配管工事", "work": "配線工事"}).status_code == 200
    assert (get(c, rid)["construction"], get(c, rid)["work"]) == ("配管工事", "配線工事")
    # 作業内容を空にして工事件名を変えるのも通る
    assert c.patch(f"{url}/{rid}", json={"construction": "配管工事", "work": ""}).status_code == 200
    assert (get(c, rid)["construction"], get(c, rid)["work"]) == ("配管工事", "")


def test_without_registered_works_nothing_is_restricted_or_cleared(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    masters_dir(data, {"配管工事": [], "電気工事": [], "清掃工事": ["組み立て作業", "配線工事", "清掃"]})
    c = create_app(tmp_path, today_func=lambda: date(2026, 11, 2)).test_client()
    rid = new_schedule(c, construction="配管工事", work="清掃")
    assert c.patch(f"/api/schedule/{rid}", json={"construction": "電気工事"}).status_code == 200
    assert schedule_row(c, rid)["work"] == "清掃"
    hid = new_holiday(c, construction="配管工事", work="配線工事")
    assert holiday_row(c, hid)["work"] == "配線工事"


def test_holiday_date_change_with_work_is_unaffected(env):
    c, _ = env
    hid = new_holiday(c, construction="配管工事", work="組み立て作業")
    assert c.patch(f"/api/holiday-rows/{hid}", json={"date": "2026-11-07"}).status_code == 200
    assert holiday_row(c, hid)["work"] == "組み立て作業"


# ---- 画面（JavaScript） ----
def test_board_js_uses_worksfor_for_the_work_picker_in_both_tables(tmp_path):
    js = create_app(tmp_path).test_client().get("/js/board.js").get_data(as_text=True)
    assert 'import { formatRange, formatRangeOrDash, orDash, contactText, visibleHolidayRows, worksFor } from "./timeutil.mjs"' in js
    sched = js[js.index("async function editSchedule"):js.index("async function editHoliday(")]
    hol = js[js.index("async function editHoliday("):js.index("async function editHolidayDate")]
    assert "worksFor(row.construction, m)" in sched and "m.works" not in sched
    assert "worksFor(row.construction, state.masters)" in hol and "state.masters.works" not in hol
    assert "export function worksFor" in create_app(tmp_path).test_client().get("/js/timeutil.mjs").get_data(as_text=True)
