import json
import threading
from datetime import date
from pathlib import Path
from urllib.parse import quote

import pytest

import config as config_mod
from app import create_app

GOOD = {
    "documents": {"buttons": [{"label": "手順書", "folder": "docs/new1"}, {"label": "図面", "folder": "docs/new2"}]},
    "telop": {"speed": 250},
}


def make(tmp_path, config=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    if config is not None:
        (tmp_path / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=1), encoding="utf-8")
    return create_app(tmp_path, today_func=lambda: date(2026, 11, 2)).test_client()


NEW_GET = {
    "manager_title": "",
    "manager_name": "",
    "manager_phone": "",
    "standby": {"start": "18:00", "end": "08:00", "wake_idle_seconds": 300},
    "accident_seconds": 15,
    "edit_lock_seconds": 60,
    "custom_holidays_file": "data/custom_holidays.csv",
    "whiteboard_save_folder": "whiteboard",
    "whiteboard_pdf_folder": "whiteboard_pdfs",
    "whiteboard_idle_seconds": 180,
    "links": {"items": [], "max_stay_seconds": 300},
}


def cfg_bytes(tmp_path):
    p = tmp_path / "config.json"
    return p.read_bytes() if p.exists() else None


def test_get_returns_raw_configured_values(tmp_path):
    r = make(tmp_path).get("/api/admin-settings")
    assert r.status_code == 200
    assert r.get_json() == {
        "documents": {
            "buttons": [
                {"label": "文書1", "folder": "documents/doc1"},
                {"label": "文書2", "folder": "documents/doc2"},
                {"label": "文書3", "folder": "documents/doc3"},
            ],
            "idle_return_seconds": 120,
        },
        "telop": {"speed": 100, "folder": "telop"},
        "company_name": "サンプル工業(株)",
        **NEW_GET,
    }
    cfg = {"documents": {"buttons": [{"label": "A", "folder": "D:/文書"}]}, "telop": {"speed": 40, "folder": "x"}}
    got = make(tmp_path / "o", cfg).get("/api/admin-settings").get_json()
    assert got == {
        "documents": {"buttons": [{"label": "A", "folder": "D:/文書"}], "idle_return_seconds": 120},
        "telop": {"speed": 40, "folder": "x"},
        "company_name": "サンプル工業(株)",
        **NEW_GET,
    }


def test_post_happy_path_saves_and_applies_without_restart(tmp_path):
    c = make(tmp_path)
    old_rev = c.get("/api/rev").get_json()["rev"]
    r = c.post("/api/admin-settings", json=GOOD)
    assert r.status_code == 200 and r.get_json() == {"ok": True}
    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert saved["documents"]["buttons"] == GOOD["documents"]["buttons"]
    assert saved["telop"] == {"speed": 250}
    assert c.get("/api/admin-settings").get_json() == {
        "documents": {**GOOD["documents"], "idle_return_seconds": 120},
        "telop": {"speed": 250, "folder": "telop"},
        "company_name": "サンプル工業(株)",
        **NEW_GET,
    }
    # フォルダが作られ、次のリクエストから新しいフォルダが使われる
    assert (tmp_path / "docs" / "new1").is_dir() and (tmp_path / "docs" / "new2").is_dir()
    (tmp_path / "docs" / "new1" / "手順.pdf").write_bytes(b"%PDF-1.4")
    b = c.get("/api/board").get_json()
    assert b["doc_buttons"] == [{"index": 0, "label": "手順書"}, {"index": 1, "label": "図面"}]
    assert b["settings"]["telop"] == {"speed": 250}
    assert c.get("/api/documents/0/files").get_json() == ["手順.pdf"]
    assert c.get("/api/documents/0/pdf/" + quote("手順.pdf")).status_code == 200
    assert c.get("/api/documents/2/files").status_code == 404
    assert c.get("/api/rev").get_json()["rev"] != old_rev


def test_rev_changes_on_every_post_even_with_same_values(tmp_path):
    c = make(tmp_path)
    c.post("/api/admin-settings", json=GOOD)
    r1 = c.get("/api/rev").get_json()["rev"]
    c.post("/api/admin-settings", json=GOOD)
    assert c.get("/api/rev").get_json()["rev"] != r1


def test_post_preserves_other_keys_and_idle_return_seconds(tmp_path):
    original = {
        "company_name": "テスト(株)",
        "accident_seconds": 20,
        "documents": {"buttons": [{"label": "旧", "folder": "old"}], "idle_return_seconds": 45},
        "telop": {"speed": 100, "folder": "お知らせ"},
        "standby": {"start": "19:00"},
    }
    c = make(tmp_path, original)
    assert c.post("/api/admin-settings", json=GOOD).status_code == 200
    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert saved["company_name"] == "テスト(株)" and saved["accident_seconds"] == 20
    assert saved["standby"] == {"start": "19:00"}
    assert saved["documents"]["idle_return_seconds"] == 45
    assert saved["telop"]["folder"] == "お知らせ" and saved["telop"]["speed"] == 250
    b = c.get("/api/board").get_json()
    assert b["company_name"] == "テスト(株)" and b["settings"]["documents_idle_seconds"] == 45


def test_post_when_config_missing_creates_it(tmp_path):
    c = make(tmp_path)
    assert not (tmp_path / "config.json").exists()
    assert c.post("/api/admin-settings", json=GOOD).status_code == 200
    assert json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))["telop"]["speed"] == 250
    assert not (tmp_path / "config.json").read_bytes().startswith(b"\xef\xbb\xbf")
    assert [f.name for f in tmp_path.iterdir() if f.name.startswith("config")] == ["config.json"]


@pytest.mark.parametrize("content", ["{ broken", "[1, 2]", "null", ""])
def test_post_refuses_hand_broken_config_and_keeps_it(tmp_path, content):
    c = make(tmp_path)
    (tmp_path / "config.json").write_text(content, encoding="utf-8")
    before = cfg_bytes(tmp_path)
    rev = c.get("/api/rev").get_json()["rev"]
    r = c.post("/api/admin-settings", json=GOOD)
    assert r.status_code == 400
    assert r.get_json() == {"error": "config.json に書き間違いがあります。直してから保存してください"}
    assert cfg_bytes(tmp_path) == before
    assert [f.name for f in tmp_path.iterdir() if f.name.startswith("config")] == ["config.json"]
    assert not (tmp_path / "docs").exists()  # フォルダも作らない
    assert c.get("/api/rev").get_json()["rev"] == rev


def test_post_with_unreadable_config_is_500_and_keeps_it(tmp_path, monkeypatch):
    c = make(tmp_path, {"company_name": "元", "standby": {"start": "19:00"}})
    before = cfg_bytes(tmp_path)
    real_open = open

    def locked(file, *a, **k):
        if str(file).endswith("config.json"):
            raise PermissionError(13, "Permission denied")
        return real_open(file, *a, **k)

    monkeypatch.setattr("builtins.open", locked)
    r = c.post("/api/admin-settings", json=GOOD)
    monkeypatch.undo()
    assert r.status_code == 500 and "設定ファイル" in r.get_json()["error"]
    assert cfg_bytes(tmp_path) == before


@pytest.mark.parametrize(
    "folder", ["../outside", "a/../../outside", "..\\outside", "docs\\..\\..\\x", "..", "//server/share/../x", "bad\0name"]
)
def test_post_with_parent_or_nul_path_is_400_and_saves_nothing(tmp_path, folder):
    c = make(tmp_path, {"company_name": "元のまま"})
    before = cfg_bytes(tmp_path)
    names_before = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    rev = c.get("/api/rev").get_json()["rev"]
    body = {"documents": {"buttons": [{"label": "a", "folder": folder}]}, "telop": {"speed": 100}}
    r = c.post("/api/admin-settings", json=body)
    assert r.status_code == 400
    assert any(ord(ch) > 127 for ch in r.get_json()["error"])
    assert cfg_bytes(tmp_path) == before
    assert sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")) == names_before
    assert not (tmp_path.parent / "outside").exists()
    assert c.get("/api/rev").get_json()["rev"] == rev
    assert len(c.get("/api/board").get_json()["doc_buttons"]) == 3


def test_slow_folder_creation_does_not_hold_the_save_lock(tmp_path, monkeypatch):
    c = make(tmp_path)
    entered, release = threading.Event(), threading.Event()
    real_mkdir = Path.mkdir

    def slow_mkdir(self, *a, **k):
        if self.name == "slow":
            entered.set()
            release.wait(5)  # ネットワークの場所への接続待ちを真似る
        return real_mkdir(self, *a, **k)

    monkeypatch.setattr(Path, "mkdir", slow_mkdir)
    slow = {"documents": {"buttons": [{"label": "遅い", "folder": "docs/slow"}]}, "telop": {"speed": 100}}
    fast = {"documents": {"buttons": [{"label": "速い", "folder": "docs/fast"}]}, "telop": {"speed": 100}}
    first = []
    t1 = threading.Thread(target=lambda: first.append(c.post("/api/admin-settings", json=slow).status_code))
    t1.start()
    assert entered.wait(5)
    second = []
    t2 = threading.Thread(target=lambda: second.append(c.post("/api/admin-settings", json=fast).status_code))
    t2.start()
    t2.join(2)
    finished_while_first_is_blocked = not t2.is_alive()
    release.set()
    t1.join(5)
    t2.join(5)
    assert finished_while_first_is_blocked, "2回目の保存が1回目のフォルダ作成を待ってしまった"
    assert first == [200] and second == [200]
    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert saved["documents"]["buttons"][0]["label"] == "速い"
    assert c.get("/api/board").get_json()["doc_buttons"] == [{"index": 0, "label": "速い"}]


def _invalid_bodies():
    ok_btn = {"label": "a", "folder": "b"}

    def b(buttons=None, **tel):
        return {"documents": {"buttons": buttons if buttons is not None else [ok_btn]}, "telop": {"speed": 100, **tel}}

    return [
        b(buttons=[]), b(buttons=[ok_btn] * 6), b(buttons="x"), b(buttons=[{"label": "a"}]),
        b(buttons=[{"label": "", "folder": "b"}]), b(buttons=[{"label": "a", "folder": " "}]),
        b(buttons=[{"label": "x" * 101, "folder": "b"}]), b(buttons=[{"label": "a", "folder": "y" * 261}]),
        b(buttons=[{"label": 5, "folder": "b"}]), b(buttons=[7]),
        b(speed=19), b(speed=501), b(speed="100"), b(speed=1.5), b(speed=True),
        {"documents": {"buttons": [ok_btn]}}, {"telop": {"speed": 100}}, {}, {"documents": 1, "telop": 2},
    ]


@pytest.mark.parametrize("body", _invalid_bodies())
@pytest.mark.parametrize("preexisting", [False, True])
def test_invalid_posts_are_400_and_save_nothing(tmp_path, body, preexisting):
    c = make(tmp_path, {"company_name": "元のまま", "documents": {"idle_return_seconds": 9}} if preexisting else None)
    before = cfg_bytes(tmp_path)
    names_before = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    rev = c.get("/api/rev").get_json()["rev"]
    r = c.post("/api/admin-settings", json=body)
    assert r.status_code == 400
    msg = r.get_json()["error"]
    assert msg and any(ord(ch) > 127 for ch in msg)
    assert cfg_bytes(tmp_path) == before
    assert sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")) == names_before
    assert c.get("/api/rev").get_json()["rev"] == rev
    assert len(c.get("/api/board").get_json()["doc_buttons"]) == 3


def test_non_json_bodies_are_400(tmp_path):
    c = make(tmp_path)
    assert c.post("/api/admin-settings", data="not json", content_type="application/json").status_code == 400
    assert c.post("/api/admin-settings", json=[1, 2]).status_code == 400
    assert c.post("/api/admin-settings").status_code == 400
    assert not (tmp_path / "config.json").exists()


def test_unmakeable_folder_still_saves_with_warning(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("ファイル", encoding="utf-8")
    c = make(tmp_path)
    body = {
        "documents": {"buttons": [{"label": "ダメ", "folder": "blocker/sub"}, {"label": "良い", "folder": "docs/ok"}]},
        "telop": {"speed": 100},
    }
    r = c.post("/api/admin-settings", json=body)
    assert r.status_code == 200
    j = r.get_json()
    assert j["ok"] is True and len(j["warnings"]) == 1 and "ダメ" in j["warnings"][0] and "作れませんでした" in j["warnings"][0]
    assert json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))["documents"]["buttons"][0]["folder"] == "blocker/sub"
    assert c.get("/api/documents/0/files").get_json() == []
    assert (tmp_path / "docs" / "ok").is_dir()


def test_write_failure_is_500_and_config_unchanged(tmp_path, monkeypatch):
    c = make(tmp_path, {"company_name": "元"})
    before = cfg_bytes(tmp_path)

    def boom(*a, **k):
        raise OSError("read-only")

    monkeypatch.setattr(config_mod.os, "replace", boom)
    r = c.post("/api/admin-settings", json=GOOD)
    assert r.status_code == 500 and r.get_json()["error"]
    assert cfg_bytes(tmp_path) == before
    assert len(c.get("/api/board").get_json()["doc_buttons"]) == 3


def test_concurrent_saves_leave_valid_json(tmp_path):
    c = make(tmp_path)
    results = []

    def go(i):
        body = {"documents": {"buttons": [{"label": f"B{i}", "folder": f"docs/t{i}"}]}, "telop": {"speed": 20 + i}}
        results.append(c.post("/api/admin-settings", json=body).status_code)

    threads = [threading.Thread(target=go, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == [200] * 8
    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    i = saved["telop"]["speed"] - 20
    assert saved["documents"]["buttons"] == [{"label": f"B{i}", "folder": f"docs/t{i}"}]
    assert c.get("/api/admin-settings").get_json()["telop"]["speed"] == saved["telop"]["speed"]
    assert [f.name for f in tmp_path.iterdir() if f.name.startswith("config")] == ["config.json"]


# ---- テロップフォルダ（equipment-inspection と共通にできる） ----
def post_telop(c, **telop):
    return c.post(
        "/api/admin-settings",
        json={"documents": GOOD["documents"], "telop": {"speed": 100, **telop}},
    )


def test_get_and_post_telop_folder_applies_without_restart(tmp_path):
    c = make(tmp_path, {"company_name": "元", "telop": {"speed": 60, "folder": "old", "memo": 1}})
    (tmp_path / "old" / "a.txt").write_text("古い", encoding="utf-8")
    assert c.get("/api/telop").get_json() == {"items": ["古い"]}
    assert c.get("/api/admin-settings").get_json()["telop"] == {"speed": 60, "folder": "old"}
    rev = c.get("/api/rev").get_json()["rev"]
    new = tmp_path / "shared" / "signage"
    new.mkdir(parents=True)
    (new / "n.txt").write_text("共有の1行目\n\"重要\"2行目", encoding="utf-8")
    (new / "doc.pdf").write_bytes(b"%PDF-1.4")  # PDF など txt 以外は無視される
    r = post_telop(c, folder=" shared/signage ")
    assert r.status_code == 200 and r.get_json() == {"ok": True}
    assert c.get("/api/telop").get_json() == {"items": ["共有の1行目", '"重要"2行目']}
    assert c.get("/api/rev").get_json()["rev"] != rev
    assert c.get("/api/admin-settings").get_json()["telop"] == {"speed": 100, "folder": "shared/signage"}
    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert saved["telop"] == {"speed": 100, "folder": "shared/signage", "memo": 1}
    assert saved["company_name"] == "元"
    b = c.get("/api/board").get_json()["settings"]["telop"]
    assert b == {"speed": 100}  # 画面にはフォルダの場所を渡さない
    # 古いフォルダは触らない（消さない）
    assert (tmp_path / "old" / "a.txt").exists()


def test_telop_folder_absolute_and_unc_are_accepted(tmp_path):
    c = make(tmp_path)
    absolute = str(tmp_path / "abs")
    assert post_telop(c, folder=absolute).status_code == 200
    assert (tmp_path / "abs").is_dir()
    assert c.get("/api/admin-settings").get_json()["telop"]["folder"] == absolute


@pytest.mark.parametrize("blank", ["", "   ", "　"])
def test_blank_telop_folder_means_default_telop(tmp_path, blank):
    c = make(tmp_path, {"telop": {"folder": "elsewhere"}})
    assert post_telop(c, folder=blank).status_code == 200
    assert c.get("/api/admin-settings").get_json()["telop"]["folder"] == "telop"
    assert json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))["telop"]["folder"] == "telop"
    (tmp_path / "telop" / "x.txt").write_text("既定", encoding="utf-8")
    assert c.get("/api/telop").get_json() == {"items": ["既定"]}


def test_post_without_telop_folder_keeps_the_current_one(tmp_path):
    c = make(tmp_path, {"telop": {"folder": "keepme"}})
    assert c.post("/api/admin-settings", json=GOOD).status_code == 200
    assert c.get("/api/admin-settings").get_json()["telop"]["folder"] == "keepme"


@pytest.mark.parametrize(
    "folder", ["..", "../x", "a/../b", "a\\..\\b", "//server/share/../x", "bad\0name", "x" * 261, 5, None, ["a"], {"a": 1}, True]
)
def test_invalid_telop_folder_is_400_and_saves_nothing(tmp_path, folder):
    c = make(tmp_path, {"company_name": "元のまま", "telop": {"folder": "keep"}})
    before = cfg_bytes(tmp_path)
    names_before = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    rev = c.get("/api/rev").get_json()["rev"]
    r = post_telop(c, folder=folder)
    assert r.status_code == 400
    assert "テロップフォルダ" in r.get_json()["error"]
    assert cfg_bytes(tmp_path) == before
    assert sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")) == names_before
    assert c.get("/api/rev").get_json()["rev"] == rev
    assert c.get("/api/admin-settings").get_json()["telop"]["folder"] == "keep"


def test_unmakeable_telop_folder_saves_with_warning(tmp_path):
    (tmp_path / "blocker").write_text("ファイル", encoding="utf-8")
    c = make(tmp_path)
    r = post_telop(c, folder="blocker/sub")
    assert r.status_code == 200
    j = r.get_json()
    assert j["ok"] is True and len(j["warnings"]) == 1 and "お知らせ" in j["warnings"][0] and "作れませんでした" in j["warnings"][0]
    assert c.get("/api/admin-settings").get_json()["telop"]["folder"] == "blocker/sub"
    assert c.get("/api/telop").get_json() == {"items": []}
def test_manager_title_name_and_phone_are_saved_trimmed_and_shown_on_board(tmp_path):
    c = make(tmp_path)
    body = {**GOOD, "manager_title": " 工場長 ", "manager_name": "  山田 太郎 ", "manager_phone": "内線 1234 / 外線 03-0000-0000"}
    assert c.post("/api/admin-settings", json=body).status_code == 200
    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert saved["manager_title"] == "工場長" and saved["manager_name"] == "山田 太郎" and saved["manager_phone"] == "内線 1234 / 外線 03-0000-0000"
    for got in (c.get("/api/board").get_json(), c.get("/api/admin-settings").get_json()):
        assert got["manager_title"] == "工場長" and got["manager_name"] == "山田 太郎" and got["manager_phone"] == "内線 1234 / 外線 03-0000-0000"


def test_manager_fields_can_be_cleared_and_are_kept_when_not_sent(tmp_path):
    c = make(tmp_path, {"manager_title": "工場長", "manager_name": "山田", "manager_phone": "1234"})
    assert c.post("/api/admin-settings", json=GOOD).status_code == 200  # 送らなければ、いまのまま
    b = c.get("/api/board").get_json()
    assert (b["manager_title"], b["manager_name"], b["manager_phone"]) == ("工場長", "山田", "1234")
    assert c.post("/api/admin-settings", json={**GOOD, "manager_title": "", "manager_name": "", "manager_phone": ""}).status_code == 200
    b = c.get("/api/board").get_json()
    assert (b["manager_title"], b["manager_name"], b["manager_phone"]) == ("", "", "")


@pytest.mark.parametrize("key,bad", [("manager_title", "a" * 101), ("manager_name", "a" * 101), ("manager_phone", "1\n2"), ("manager_title", "工\n場"), ("manager_name", 5), ("manager_phone", None)])
def test_manager_fields_reject_bad_values(tmp_path, key, bad):
    c = make(tmp_path)
    before = cfg_bytes(tmp_path)
    r = c.post("/api/admin-settings", json={**GOOD, key: bad})
    assert r.status_code == 400
    assert cfg_bytes(tmp_path) == before
