import json
from datetime import date

import pytest
from urllib.parse import quote

import masters as m
from app import create_app
from config import clean_admin_settings

BASE = {"documents": {"buttons": [{"label": "a", "folder": "documents/x"}]}, "telop": {"speed": 100}}
KEYS = ["accident_folder", "companies_folder", "constructions_folder"]


def make(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    return create_app(tmp_path, today_func=lambda: date(2026, 11, 2)).test_client()


def write_company(folder, name, leader):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.csv").write_text(f"責任者,内線,外線\n{leader},,\n", encoding="utf-8-sig")


def write_construction(folder, name, work):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.csv").write_text(f"作業内容\n{work}\n", encoding="utf-8-sig")


# ---- 設定の受け取り ----
def test_defaults_are_returned(tmp_path):
    got = make(tmp_path).get("/api/admin-settings").get_json()
    assert (got["accident_folder"], got["companies_folder"], got["constructions_folder"]) == (
        "accident_cases", "data/companies", "data/constructions")


def test_post_saves_the_three_folders(tmp_path):
    c = make(tmp_path)
    body = {**BASE, "accident_folder": "//server/share/災害", "companies_folder": "//server/share/会社", "constructions_folder": "D:/工事"}
    r = c.post("/api/admin-settings", json=body)
    assert r.status_code == 200, r.get_json()
    got = c.get("/api/admin-settings").get_json()
    assert [got[k] for k in KEYS] == ["//server/share/災害", "//server/share/会社", "D:/工事"]
    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert [saved[k] for k in KEYS] == ["//server/share/災害", "//server/share/会社", "D:/工事"]


def test_empty_folder_means_default_and_missing_keys_keep_current():
    clean = clean_admin_settings({**BASE, "accident_folder": " ", "companies_folder": "", "constructions_folder": ""})
    assert [clean[k] for k in KEYS] == ["accident_cases", "data/companies", "data/constructions"]
    assert not any(k in clean_admin_settings(BASE) for k in KEYS)  # 古い画面は送らない → いまのまま


@pytest.mark.parametrize("key", KEYS)
def test_folders_reject_parent_marks_non_text_and_long_paths(key):
    for bad in ("a/../b", "..", 5, ["x"], "x" * 261):
        with pytest.raises(ValueError):
            clean_admin_settings({**BASE, key: bad})


# ---- 実際に使う場所が変わる ----
def test_companies_and_constructions_are_read_from_the_set_folders(tmp_path):
    c = make(tmp_path)
    write_company(tmp_path / "shared" / "会社", "共有建設", "木村")
    write_construction(tmp_path / "shared" / "工事", "共有工事", "据付")
    body = {**BASE, "companies_folder": str(tmp_path / "shared" / "会社"), "constructions_folder": str(tmp_path / "shared" / "工事")}
    assert c.post("/api/admin-settings", json=body).status_code == 200
    masters = c.get("/api/board").get_json()["masters"]
    assert masters["companies"] == ["共有建設"]
    assert [l["leader_name"] for l in masters["leaders"]] == ["木村"]
    assert masters["constructions"] == ["共有工事"]
    # 選べるようになった会社は、保存もできる
    rid = c.post("/api/schedule").get_json()["id"]
    assert c.patch(f"/api/schedule/{rid}", json={"company": "共有建設", "leader": "木村"}).status_code == 200


def test_accident_folder_is_read_from_the_set_folder(tmp_path):
    c = make(tmp_path)
    folder = tmp_path / "共有の災害事例"
    folder.mkdir()
    (folder / "転落.pdf").write_bytes(b"%PDF-1.4\n")
    assert c.post("/api/admin-settings", json={**BASE, "accident_folder": str(folder)}).status_code == 200
    # 一覧に載ったファイルだけを渡す仕組みなので、新しいフォルダのファイルが開ければ、そこを読んでいる
    r = c.get("/api/accident/file/" + quote("転落.pdf"))
    assert r.status_code == 200 and r.data.startswith(b"%PDF")


def test_unreachable_accident_folder_is_reported_on_save(tmp_path):
    c = make(tmp_path)
    blocker = tmp_path / "file.txt"
    blocker.write_text("x", encoding="utf-8")
    r = c.post("/api/admin-settings", json={**BASE, "accident_folder": str(blocker / "sub")})
    assert r.status_code == 200
    assert any("災害事例" in w for w in r.get_json()["warnings"])


# ---- つながらないとき ----
def test_unreachable_folder_keeps_the_last_list(tmp_path):
    shared = tmp_path / "shared"
    write_company(shared, "共有建設", "木村")
    mm = m.Masters(tmp_path / "data", folders_source=lambda: {"companies": (shared, "//server/会社"), "constructions": (tmp_path / "data" / "constructions", "data/constructions")})
    assert mm.load_all()["companies"] == ["共有建設"]
    shared.rename(tmp_path / "moved")  # 同じ場所につながらなくなった
    data = mm.load_all()
    assert data["companies"] == ["共有建設"]
    assert any("//server/会社" in w and "前に読めた一覧" in w for w in data["warnings"])


def test_unreachable_from_the_start_is_empty_with_a_warning(tmp_path):
    mm = m.Masters(tmp_path / "data", folders_source=lambda: {"companies": (tmp_path / "gone", "//server/会社"), "constructions": (tmp_path / "gone2", "//server/工事")})
    data = mm.load_all()
    assert data["companies"] == [] and data["constructions"] == []
    assert any("//server/会社" in w for w in data["warnings"])
    assert any("//server/工事" in w for w in data["warnings"])


def test_changing_the_folder_changes_the_signature(tmp_path, monkeypatch):
    a, b = tmp_path / "a", tmp_path / "b"
    write_company(a, "甲", "x")
    write_company(b, "甲", "x")
    where = {"p": a}
    mm = m.Masters(tmp_path / "data", folders_source=lambda: {"companies": (where["p"], "会社"), "constructions": (tmp_path / "data" / "constructions", "data/constructions")})
    first = mm.signature()
    where["p"] = b
    monkeypatch.setattr(m, "_clock", lambda: 10**9)  # 走査の間隔を待たずに確かめる
    assert mm.signature() != first


def test_accident_url_has_a_version_and_is_cached(tmp_path):
    c = make(tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "genres.csv").write_text("name\n溶接作業\n", encoding="utf-8-sig")
    pdf = tmp_path / "accident_cases" / "溶接作業_A.pdf"
    pdf.write_bytes(b"%PDF-1.4\n1")
    c.post("/api/genres/toggle", json={"name": "溶接作業", "checked": True})
    url = c.get("/api/board").get_json()["accident"][0]["url"]
    assert "?v=" in url
    r = c.get(url)
    assert r.status_code == 200 and r.headers.get("Cache-Control") == "max-age=86400"
    pdf.write_bytes(b"%PDF-1.4\n22")  # 同じ名前で差し替えると、url の版が変わる（読み直される）
    assert c.get("/api/board").get_json()["accident"][0]["url"] != url
    # 版の無い url（古い画面）は、これまでどおり毎回確かめる
    assert "max-age=86400" not in c.get(url.split("?")[0]).headers.get("Cache-Control", "")
