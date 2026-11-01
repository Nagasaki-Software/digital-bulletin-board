import time
from datetime import date
from urllib.parse import quote

import pytest

import masters as mst
from app import create_app

COMPANIES = "name\n1班\n見本電機\n山田\n"
LEADERS = (
    "company,leader_name,ext,outside\n"
    "1班,佐藤,1234,\n1班,鈴木,1235,\n見本電機,田中,,03-0000-0001\n"
)
WORKS = "name\n組み立て作業\n配線工事\n"
GENRES = "name\n溶接作業\n高所作業\n電気配線\nその他\n"
CONSTRUCTIONS = "name\n配管工事\n電気工事\n"


@pytest.fixture
def env(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    for name, text in [
        ("companies.csv", COMPANIES),
        ("leaders.csv", LEADERS),
        ("works.csv", WORKS),
        ("genres.csv", GENRES),
        ("constructions.csv", CONSTRUCTIONS),
    ]:
        (data / name).write_text(text, encoding="utf-8-sig")
    clock = {"today": date(2026, 11, 2)}
    app = create_app(tmp_path, today_func=lambda: clock["today"])
    return app.test_client(), clock, tmp_path


def board(c):
    r = c.get("/api/board")
    assert r.status_code == 200
    return r.get_json()


def add_row(c, **fields):
    rid = c.post("/api/schedule").get_json()["id"]
    if fields:
        assert c.patch(f"/api/schedule/{rid}", json=fields).status_code == 200
    return rid


def test_board_basics(env):
    c, _, _ = env
    b = board(c)
    assert b["today"] == "2026-11-02"
    assert b["date_label"] == "2026年11月2日（月）"
    assert b["company_name"] == "サンプル工業(株)"
    assert b["schedule"] == [] and b["holiday_rows"] == []
    assert [n["position"] for n in b["notices"]] == [1, 2, 3]
    assert b["masters"]["genres"] == ["溶接作業", "高所作業", "電気配線", "その他"]
    assert b["doc_buttons"] == [
        {"index": 0, "label": "文書1"},
        {"index": 1, "label": "文書2"},
        {"index": 2, "label": "文書3"},
    ]
    assert b["settings"]["accident_seconds"] == 15
    assert b["settings"]["default_theme"] == "light"
    assert b["warnings"] == []


def test_schedule_add_patch_and_contact(env):
    c, _, _ = env
    add_row(c, company="1班", leader="佐藤", work="組み立て作業", start_time="9:00", end_time="15:00")
    add_row(c, company="見本電機", leader="田中")
    rows = board(c)["schedule"]
    assert (rows[0]["ext"], rows[0]["outside"]) == ("1234", "")
    assert (rows[1]["ext"], rows[1]["outside"]) == ("", "03-0000-0001")
    assert rows[0]["start_time"] == "9:00"


def test_changing_company_clears_leader(env):
    c, _, _ = env
    rid = add_row(c, company="1班", leader="佐藤")
    assert c.patch(f"/api/schedule/{rid}", json={"company": "見本電機"}).status_code == 200
    assert board(c)["schedule"][0]["leader"] == ""


def test_leader_must_belong_to_company(env):
    c, _, _ = env
    rid = add_row(c, company="1班")
    r = c.patch(f"/api/schedule/{rid}", json={"leader": "田中"})
    assert r.status_code == 400
    assert board(c)["schedule"][0]["leader"] == ""


def test_values_must_be_registered(env):
    c, _, _ = env
    rid = add_row(c)
    assert c.patch(f"/api/schedule/{rid}", json={"company": "未登録会社"}).status_code == 400
    assert c.patch(f"/api/schedule/{rid}", json={"work": "未登録作業"}).status_code == 400
    assert c.patch(f"/api/schedule/{rid}", json={"start_time": "25:00"}).status_code == 400
    assert c.patch(f"/api/schedule/{rid}", json={"company": 5}).status_code == 400
    assert c.patch(f"/api/schedule/{rid}", json={"company": ""}).status_code == 200


def test_overnight_time_is_accepted(env):
    c, _, _ = env
    rid = add_row(c)
    r = c.patch(f"/api/schedule/{rid}", json={"start_time": "22:00", "end_time": "6:00"})
    assert r.status_code == 200


def test_patch_and_delete_missing_row_return_404(env):
    c, _, _ = env
    assert c.patch("/api/schedule/999", json={"company": "1班"}).status_code == 404
    assert c.delete("/api/schedule/999").status_code == 404
    assert c.post("/api/schedule/999/move", json={"direction": "up"}).status_code == 404


def test_delete_compacts_and_move(env):
    c, _, _ = env
    add_row(c, company="1班")
    add_row(c, company="見本電機")
    add_row(c, company="山田")
    rows = board(c)["schedule"]
    assert c.post(f"/api/schedule/{rows[2]['id']}/move", json={"direction": "up"}).status_code == 200
    assert [r["company"] for r in board(c)["schedule"]] == ["1班", "山田", "見本電機"]
    assert c.delete(f"/api/schedule/{rows[0]['id']}").status_code == 200
    after = board(c)["schedule"]
    assert [r["company"] for r in after] == ["山田", "見本電機"]
    assert [r["position"] for r in after] == [1, 2]


def test_move_at_edge_is_noop_200(env):
    c, _, _ = env
    rid = add_row(c, company="1班")
    r = c.post(f"/api/schedule/{rid}/move", json={"direction": "up"})
    assert r.status_code == 200


def test_carry_over_next_day(env):
    c, clock, _ = env
    first = add_row(c, company="1班")
    clock["today"] = date(2026, 11, 3)
    rows = board(c)["schedule"]
    assert [r["company"] for r in rows] == ["1班"]
    assert rows[0]["id"] != first


def test_notices_add_patch_delete(env):
    c, _, _ = env
    new_id = c.post("/api/notices").get_json()["id"]
    assert c.patch(f"/api/notices/{new_id}", json={"text": "避難訓練", "red": True}).status_code == 200
    notices = board(c)["notices"]
    assert len(notices) == 4
    assert (notices[3]["text"], notices[3]["red"]) == ("避難訓練", True)
    assert c.delete(f"/api/notices/{notices[0]['id']}").status_code == 200
    after = board(c)["notices"]
    assert [n["position"] for n in after] == [1, 2, 3]
    assert after[2]["text"] == "避難訓練"


def test_notices_cannot_be_deleted_below_three(env):
    c, _, _ = env
    first = board(c)["notices"][0]["id"]
    assert c.delete(f"/api/notices/{first}").status_code == 400
    assert c.delete("/api/notices/999").status_code == 404
    assert c.patch("/api/notices/999", json={"text": "x"}).status_code == 404
    assert c.patch(f"/api/notices/{first}", json={"text": 5}).status_code == 400
    assert c.patch(f"/api/notices/{first}", json={}).status_code == 400
    assert len(board(c)["notices"]) == 3


def test_holiday_rows_only_on_this_weeks_holidays(env):
    c, _, _ = env
    assert c.post("/api/holiday-rows", json={"date": "2026-11-04"}).status_code == 400
    assert c.post("/api/holiday-rows", json={"date": "2026-11-09"}).status_code == 400
    r = c.post("/api/holiday-rows", json={"date": "2026-11-07"})
    assert r.status_code == 200
    rid = r.get_json()["id"]
    assert c.patch(f"/api/holiday-rows/{rid}", json={"person": "山田", "work": "配線工事"}).status_code == 200
    assert c.patch(f"/api/holiday-rows/{rid}", json={"date": "2026-11-04"}).status_code == 400
    assert c.patch(f"/api/holiday-rows/{rid}", json={"date": "2026-11-03"}).status_code == 200
    b = board(c)
    assert [w["label"] for w in b["week_holidays"]] == ["11/3(火・文化の日)", "11/7(土)", "11/8(日)"]
    row = b["holiday_rows"][0]
    assert (row["label"], row["kind"], row["person"]) == ("11/3(火・文化の日)", "holiday", "山田")


def test_holiday_rows_sorted_by_date(env):
    c, _, _ = env
    c.post("/api/holiday-rows", json={"date": "2026-11-07"})
    c.post("/api/holiday-rows", json={"date": "2026-11-03"})
    assert [r["date"] for r in board(c)["holiday_rows"]] == ["2026-11-03", "2026-11-07"]


def test_monday_resets_holiday_rows(env):
    c, clock, _ = env
    c.post("/api/holiday-rows", json={"date": "2026-11-07"})
    assert len(board(c)["holiday_rows"]) == 1
    clock["today"] = date(2026, 11, 9)
    b = board(c)
    assert b["holiday_rows"] == []
    assert [w["date"] for w in b["week_holidays"]] == ["2026-11-14", "2026-11-15"]


def test_company_holiday_can_be_chosen(env):
    c, _, base = env
    (base / "data" / "custom_holidays.csv").write_text("date,name\n2026-11-05,創立記念日\n", encoding="utf-8-sig")
    labels = [w["label"] for w in board(c)["week_holidays"]]
    assert "11/5(木・創立記念日)" in labels
    assert c.post("/api/holiday-rows", json={"date": "2026-11-05"}).status_code == 200


def test_genre_toggle_must_be_registered(env):
    c, _, _ = env
    assert c.post("/api/genres/toggle", json={"name": "未登録", "checked": True}).status_code == 400
    assert c.post("/api/genres/toggle", json={"name": "溶接作業", "checked": True}).status_code == 200
    assert board(c)["checked_genres"] == ["溶接作業"]
    c.post("/api/genres/toggle", json={"name": "溶接作業", "checked": False})
    assert board(c)["checked_genres"] == []


def test_accident_playlist(env):
    c, _, base = env
    folder = base / "accident_cases"
    for n in ["溶接作業_b.pdf", "溶接作業_a.pdf", "高所作業_x.pdf", "不明_y.pdf", "memo.txt"]:
        (folder / n).write_bytes(b"%PDF-1.4")
    assert board(c)["accident"] == []
    c.post("/api/genres/toggle", json={"name": "溶接作業", "checked": True})
    b = board(c)
    assert [a["name"] for a in b["accident"]] == ["溶接作業_a.pdf", "溶接作業_b.pdf"]
    assert b["accident"][0]["url"] == "/api/accident/file/" + quote("溶接作業_a.pdf")
    assert c.get(b["accident"][0]["url"]).status_code == 200
    assert c.get("/api/accident/file/" + quote("存在しない.pdf")).status_code == 404


def test_documents(env):
    c, _, base = env
    folder = base / "documents" / "doc1"
    (folder / "手順書2.pdf").write_bytes(b"%PDF-1.4")
    (folder / "手順書10.pdf").write_bytes(b"%PDF-1.4")
    assert c.get("/api/documents/0/files").get_json() == ["手順書2.pdf", "手順書10.pdf"]
    assert c.get("/api/documents/1/files").get_json() == []
    assert c.get("/api/documents/9/files").status_code == 404
    assert c.get("/api/documents/0/pdf/" + quote("手順書2.pdf")).status_code == 200
    assert c.get("/api/documents/0/pdf/..%2F..%2Fconfig.json").status_code == 404


def test_broken_csv_gives_warning_not_error(env):
    c, _, base = env
    (base / "data" / "works.csv").write_bytes("name\n組み立て作業\n".encode("cp932"))
    b = board(c)
    assert b["masters"]["works"] == []
    assert any("works.csv" in w for w in b["warnings"])


def test_rev_changes_on_write_and_on_csv_edit(env):
    c, _, base = env
    r0 = c.get("/api/rev").get_json()["rev"]
    add_row(c)
    r1 = c.get("/api/rev").get_json()["rev"]
    assert r1 != r0
    time.sleep(0.02)
    (base / "data" / "works.csv").write_text("name\n清掃\n", encoding="utf-8-sig")
    assert c.get("/api/rev").get_json()["rev"] != r1
    assert c.get("/api/rev").get_json()["today"] == "2026-11-02"

# ---- 工事件名 ----
def test_board_exposes_constructions_master_and_row_field(env):
    c, _, _ = env
    add_row(c, company="1班")
    hid = c.post("/api/holiday-rows", json={"date": "2026-11-07"}).get_json()["id"]
    b = board(c)
    assert b["masters"]["constructions"] == ["配管工事", "電気工事"]
    assert b["schedule"][0]["construction"] == ""
    assert b["holiday_rows"][0]["construction"] == ""
    assert c.patch(f"/api/holiday-rows/{hid}", json={"construction": "電気工事"}).status_code == 200
    assert board(c)["holiday_rows"][0]["construction"] == "電気工事"


def test_schedule_construction_must_be_registered(env):
    c, _, _ = env
    rid = add_row(c)
    assert c.patch(f"/api/schedule/{rid}", json={"construction": "配管工事"}).status_code == 200
    assert board(c)["schedule"][0]["construction"] == "配管工事"
    assert c.patch(f"/api/schedule/{rid}", json={"construction": "未登録工事"}).status_code == 400
    assert c.patch(f"/api/schedule/{rid}", json={"construction": 5}).status_code == 400
    assert board(c)["schedule"][0]["construction"] == "配管工事"
    assert c.patch(f"/api/schedule/{rid}", json={"construction": ""}).status_code == 200
    assert board(c)["schedule"][0]["construction"] == ""


def test_holiday_construction_must_be_registered(env):
    c, _, _ = env
    hid = c.post("/api/holiday-rows", json={"date": "2026-11-07"}).get_json()["id"]
    assert c.patch(f"/api/holiday-rows/{hid}", json={"construction": "電気工事"}).status_code == 200
    assert board(c)["holiday_rows"][0]["construction"] == "電気工事"
    assert c.patch(f"/api/holiday-rows/{hid}", json={"construction": "未登録工事"}).status_code == 400
    assert c.patch(f"/api/holiday-rows/{hid}", json={"construction": ["配管工事"]}).status_code == 400
    assert board(c)["holiday_rows"][0]["construction"] == "電気工事"
    assert c.patch(f"/api/holiday-rows/{hid}", json={"construction": ""}).status_code == 200


def test_construction_is_carried_over_next_day(env):
    c, clock, _ = env
    add_row(c, company="1班", construction="配管工事")
    clock["today"] = date(2026, 11, 3)
    assert board(c)["schedule"][0]["construction"] == "配管工事"


def test_rev_changes_when_constructions_csv_is_edited(env):
    c, _, base = env
    r0 = c.get("/api/rev").get_json()["rev"]
    time.sleep(0.02)
    (base / "data" / "constructions.csv").write_text("name\n足場工事\n", encoding="utf-8-sig")
    assert c.get("/api/rev").get_json()["rev"] != r0
    assert board(c)["masters"]["constructions"] == ["足場工事"]


def test_missing_constructions_csv_warns_but_board_works(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    for name, text in [("companies.csv", COMPANIES), ("leaders.csv", LEADERS), ("works.csv", WORKS), ("genres.csv", GENRES)]:
        (data / name).write_text(text, encoding="utf-8-sig")
    c = create_app(tmp_path, today_func=lambda: date(2026, 11, 2)).test_client()
    b = board(c)
    assert b["masters"]["constructions"] == []
    assert any("constructions.csv" in w for w in b["warnings"])
    rid = add_row(c)
    assert c.patch(f"/api/schedule/{rid}", json={"construction": "配管工事"}).status_code == 400


# ---- 追加テスト（レビュー指摘への対応） ----
def test_empty_or_invalid_body_is_400_not_404(env):
    c, _, _ = env
    rid = add_row(c, company="1班")
    assert c.patch(f"/api/schedule/{rid}", json={}).status_code == 400
    assert c.patch(f"/api/schedule/{rid}", json={"unknown": "x"}).status_code == 400
    assert c.patch(f"/api/schedule/{rid}", data="[1]", content_type="application/json").status_code == 400
    assert c.patch(f"/api/schedule/{rid}", data="not json", content_type="application/json").status_code == 400
    assert c.patch("/api/schedule/999", json={}).status_code == 404
    hid = c.post("/api/holiday-rows", json={"date": "2026-11-07"}).get_json()["id"]
    assert c.patch(f"/api/holiday-rows/{hid}", json={}).status_code == 400
    assert c.patch("/api/holiday-rows/999", json={}).status_code == 404
    nid = board(c)["notices"][0]["id"]
    assert c.patch(f"/api/notices/{nid}", data="[1]", content_type="application/json").status_code == 400


def test_holiday_date_must_be_exact_string(env):
    c, _, _ = env
    for bad_date in ["abc", "", 5, None, ["2026-11-07"], "2026/11/07", "2026-11-7"]:
        assert c.post("/api/holiday-rows", json={"date": bad_date}).status_code == 400, bad_date
    assert c.post("/api/holiday-rows", json={}).status_code == 400
    assert c.post("/api/holiday-rows", data="[]", content_type="application/json").status_code == 400
    hid = c.post("/api/holiday-rows", json={"date": "2026-11-07"}).get_json()["id"]
    for bad_date in ["abc", 5, ["2026-11-07"], "2026/11/08"]:
        assert c.patch(f"/api/holiday-rows/{hid}", json={"date": bad_date}).status_code == 400, bad_date
    assert board(c)["holiday_rows"][0]["date"] == "2026-11-07"


def test_first_write_of_a_day_still_carries_over(env):
    c, clock, _ = env
    add_row(c, company="1班")
    c.post("/api/genres/toggle", json={"name": "溶接作業", "checked": True})
    clock["today"] = date(2026, 11, 3)
    # 翌日の最初の操作が書き込みでも、前日の引き継ぎが消えない
    assert c.post("/api/genres/toggle", json={"name": "高所作業", "checked": True}).status_code == 200
    assert board(c)["checked_genres"] == ["溶接作業", "高所作業"]
    clock["today"] = date(2026, 11, 4)
    add_row(c, company="山田")
    assert [r["company"] for r in board(c)["schedule"]] == ["1班", "山田"]


def test_pdf_names_are_checked_against_listing(env):
    c, _, base = env
    (base / "config.json").write_text("{}", encoding="utf-8")
    (base / "accident_cases" / "sub").mkdir()
    (base / "accident_cases" / "sub" / "a.pdf").write_bytes(b"%PDF-1.4")
    (base / "accident_cases" / "溶接作業_a.pdf").write_bytes(b"%PDF-1.4")
    (base / "documents" / "doc1" / "手順書.pdf").write_bytes(b"%PDF-1.4")
    (base / "documents" / "doc1" / "sub").mkdir()
    (base / "documents" / "doc1" / "sub" / "b.pdf").write_bytes(b"%PDF-1.4")
    absolute = quote(str(base / "config.json"), safe="")
    evil = [
        "../config.json",
        "..%2Fconfig.json",
        "%2E%2E%2Fconfig.json",
        "..\\config.json",
        "..%5Cconfig.json",
        "sub/a.pdf",
        "sub%2Fa.pdf",
        absolute,
        "config.json",
        "手順書.pdf",  # 別フォルダのファイル
    ]
    for name in evil:
        assert c.get("/api/accident/file/" + name).status_code == 404, name
    for name in [n for n in evil if n != "手順書.pdf"] + ["溶接作業_a.pdf"]:
        assert c.get("/api/documents/0/pdf/" + name).status_code == 404, name
    assert c.get("/api/accident/file/" + quote("溶接作業_a.pdf")).status_code == 200
    assert c.get("/api/documents/0/pdf/" + quote("手順書.pdf")).status_code == 200


def test_json_is_utf8_and_readable(env):
    c, _, _ = env
    r = c.get("/api/board")
    assert r.headers["Content-Type"].replace(" ", "").lower() == "application/json;charset=utf-8"
    assert "サンプル工業(株)" in r.get_data(as_text=True)
    bad = c.post("/api/genres/toggle", json={"name": "未登録", "checked": True})
    assert "charset=utf-8" in bad.headers["Content-Type"].lower()


# ---- 最終修正: config.json の誤り・エラー形式・その他 ----
import json as _json


def make_client(tmp_path, config):
    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)
    for name, text in [
        ("companies.csv", COMPANIES),
        ("leaders.csv", LEADERS),
        ("works.csv", WORKS),
        ("genres.csv", GENRES),
        ("constructions.csv", CONSTRUCTIONS),
    ]:
        (data / name).write_text(text, encoding="utf-8-sig")
    if config is not None:
        text = config if isinstance(config, str) else _json.dumps(config, ensure_ascii=False)
        (tmp_path / "config.json").write_text(text, encoding="utf-8")
    return create_app(tmp_path, today_func=lambda: date(2026, 11, 2)).test_client()


DEFAULT_DOC_BUTTONS = [{"index": i, "label": f"文書{i + 1}"} for i in range(3)]


@pytest.mark.parametrize(
    "config, key",
    [
        ({"documents": None}, "documents"),
        ({"documents": {"buttons": "文書1"}}, "buttons"),
        ({"documents": {"buttons": [{"label": "名前だけ"}]}}, "buttons"),
        ({"documents": {"buttons": [{"folder": "documents/x"}]}}, "buttons"),
        ({"documents": {"buttons": [5, None]}}, "buttons"),
        ({"documents": {"idle_return_seconds": "abc"}}, "idle_return_seconds"),
        ({"accident_seconds": "abc"}, "accident_seconds"),
        ({"accident_seconds": 0}, "accident_seconds"),
        ({"accident_seconds": -5}, "accident_seconds"),
        ({"edit_lock_seconds": 0}, "edit_lock_seconds"),
        ({"standby": None}, "standby"),
        ({"standby": "18:00"}, "standby"),
        ({"standby": {"wake_idle_seconds": -1}}, "wake_idle_seconds"),
        ({"default_theme": "blue"}, "default_theme"),
        ({"default_theme": 5}, "default_theme"),
        ({"default_edit_button": "maybe"}, "default_edit_button"),
        ({"company_name": 5}, "company_name"),
        ({"company_name": ""}, "company_name"),
        ({"accident_folder": None}, "accident_folder"),
        ("[1, 2]", "config.json"),
        ("{ broken", "config.json"),
    ],
)
def test_wrong_config_does_not_break_startup_or_board(tmp_path, config, key):
    c = make_client(tmp_path, config)
    r = c.get("/api/board")
    assert r.status_code == 200
    b = r.get_json()
    assert any(key in w and "config.json" in w for w in b["warnings"]), b["warnings"]
    s = b["settings"]
    assert s["accident_seconds"] == 15 and s["edit_lock_seconds"] == 60
    assert s["documents_idle_seconds"] == 120
    assert s["default_theme"] == "light" and s["default_edit_button"] == "off"
    assert s["standby"] == {"start": "18:00", "end": "07:30", "wake_idle_seconds": 300}
    assert b["company_name"] == "サンプル工業(株)"
    assert b["doc_buttons"] == DEFAULT_DOC_BUTTONS
    assert c.get("/api/rev").status_code == 200


def test_valid_config_has_no_warnings_and_edit_button_default(tmp_path):
    c = make_client(tmp_path, {"default_edit_button": "on", "accident_seconds": 20})
    b = c.get("/api/board").get_json()
    assert b["warnings"] == []
    assert b["settings"]["default_edit_button"] == "on"
    assert b["settings"]["accident_seconds"] == 20
    assert make_client(tmp_path / "other", None).get("/api/board").get_json()["settings"]["default_edit_button"] == "off"


def test_good_buttons_survive_bad_ones(tmp_path):
    cfg = {"documents": {"buttons": [{"label": "A", "folder": "docs/a"}, {"label": "B"}, {"label": "C", "folder": "docs/c"}]}}
    b = make_client(tmp_path, cfg).get("/api/board").get_json()
    assert b["doc_buttons"] == [{"index": 0, "label": "A"}, {"index": 1, "label": "C"}]
    assert len(b["warnings"]) == 1


def test_unreachable_folders_give_warning_not_crash(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("ファイル", encoding="utf-8")  # この下にフォルダは作れない
    cfg = {
        "accident_folder": "blocker/accident",
        "documents": {"buttons": [{"label": "文書A", "folder": "blocker/docs"}]},
    }
    c = make_client(tmp_path, cfg)
    r = c.get("/api/board")
    assert r.status_code == 200
    b = r.get_json()
    assert b["accident"] == []
    assert b["doc_buttons"] == [{"index": 0, "label": "文書A"}]
    assert sum("フォルダ" in w for w in b["warnings"]) == 2
    assert c.get("/api/documents/0/files").get_json() == []
    assert c.get("/api/accident/file/x.pdf").status_code == 404
    c.post("/api/genres/toggle", json={"name": "溶接作業", "checked": True})
    assert c.get("/api/board").status_code == 200


def test_huge_ids_are_404_json(tmp_path):
    c = make_client(tmp_path, None)
    huge = "9" * 30
    for r in [
        c.patch(f"/api/schedule/{huge}", json={"company": "1班"}),
        c.delete(f"/api/schedule/{huge}"),
        c.post(f"/api/schedule/{huge}/move", json={"direction": "up"}),
        c.patch(f"/api/notices/{huge}", json={"text": "x"}),
        c.delete(f"/api/notices/{huge}"),
        c.patch(f"/api/holiday-rows/{huge}", json={"person": "山田"}),
        c.delete(f"/api/holiday-rows/{huge}"),
        c.get(f"/api/documents/{huge}/files"),
    ]:
        assert r.status_code == 404
        assert "error" in r.get_json()


def test_api_errors_are_json_other_errors_unchanged(tmp_path, monkeypatch):
    c = make_client(tmp_path, None)
    r = c.get("/api/nothing-here")
    assert r.status_code == 404 and "error" in r.get_json()
    assert "charset=utf-8" in r.headers["Content-Type"].lower()
    r = c.post("/api/board")
    assert r.status_code == 405 and "error" in r.get_json()
    r = c.get("/no-such-file.txt")
    assert r.status_code == 404 and r.mimetype == "text/html"

    def boom(self):
        raise RuntimeError("test failure")

    monkeypatch.setattr(mst.Masters, "load_all", boom)
    r = c.get("/api/board")
    assert r.status_code == 500
    assert r.get_json()["error"]


def test_removed_genre_is_not_listed_as_checked(env):
    c, _, base = env
    c.post("/api/genres/toggle", json={"name": "溶接作業", "checked": True})
    c.post("/api/genres/toggle", json={"name": "高所作業", "checked": True})
    assert board(c)["checked_genres"] == ["溶接作業", "高所作業"]
    (base / "data" / "genres.csv").write_text("name\n高所作業\nその他\n", encoding="utf-8-sig")
    assert board(c)["checked_genres"] == ["高所作業"]
