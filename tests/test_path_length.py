import json
from datetime import date

import pytest

from app import create_app
from config import MAX_PATH, clean_admin_settings, load_config

LONG150 = "共有/" + "d" * 147  # 150文字
assert len(LONG150) == 150


def make(tmp_path, config=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    if config is not None:
        (tmp_path / "config.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return create_app(tmp_path, today_func=lambda: date(2026, 11, 2)).test_client()


def body(doc_folder="documents/x", telop_folder="telop", label="a"):
    return {
        "documents": {"buttons": [{"label": label, "folder": doc_folder}]},
        "telop": {"speed": 100, "folder": telop_folder},
    }


def test_limit_is_260_for_folders_and_100_for_labels():
    assert MAX_PATH == 260
    clean_admin_settings(body("a" * 260, "b" * 260))
    with pytest.raises(ValueError, match="260文字以内"):
        clean_admin_settings(body("a" * 261))
    with pytest.raises(ValueError, match="260文字以内"):
        clean_admin_settings(body(telop_folder="b" * 261))
    clean_admin_settings(body(label="x" * 100))
    with pytest.raises(ValueError, match="100文字以内"):
        clean_admin_settings(body(label="x" * 101))


def test_150_char_paths_are_accepted_via_post(tmp_path):
    c = make(tmp_path)
    r = c.post("/api/admin-settings", json=body(LONG150 + "d", LONG150 + "t"))
    assert r.status_code == 200 and r.get_json() == {"ok": True}
    got = c.get("/api/admin-settings").get_json()
    assert got["documents"]["buttons"][0]["folder"] == LONG150 + "d"
    assert got["telop"]["folder"] == LONG150 + "t"
    assert (tmp_path / (LONG150 + "d")).is_dir() and (tmp_path / (LONG150 + "t")).is_dir()
    assert c.get("/api/documents/0/files").status_code == 200
    assert c.get("/api/telop").status_code == 200


def test_150_char_paths_are_accepted_via_config_json(tmp_path):
    cfg = {
        "accident_folder": LONG150 + "a",
        "documents": {"buttons": [{"label": "長い", "folder": LONG150 + "d"}]},
        "telop": {"folder": LONG150 + "t"},
    }
    (tmp_path).mkdir(exist_ok=True)
    (tmp_path / "config.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    loaded = load_config(tmp_path / "config.json")
    assert loaded["_warnings"] == []
    assert loaded["accident_folder"] == LONG150 + "a"
    assert loaded["telop"]["folder"] == LONG150 + "t"
    c = make(tmp_path)
    b = c.get("/api/board").get_json()
    assert b["doc_buttons"] == [{"index": 0, "label": "長い"}]
    assert not any("config.json" in w for w in b["warnings"])


def test_261_char_paths_in_config_json_fall_back_with_warning(tmp_path):
    cfg = {"accident_folder": "a" * 261, "telop": {"folder": "t" * 261}}
    (tmp_path).mkdir(exist_ok=True)
    (tmp_path / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    loaded = load_config(tmp_path / "config.json")
    assert loaded["accident_folder"] == "accident_cases" and loaded["telop"]["folder"] == "telop"
    assert len(loaded["_warnings"]) == 2


@pytest.mark.parametrize("which", ["document", "telop"])
def test_261_char_path_is_400_and_saves_nothing(tmp_path, which):
    c = make(tmp_path, {"company_name": "元のまま"})
    before = (tmp_path / "config.json").read_bytes()
    names_before = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    rev = c.get("/api/rev").get_json()["rev"]
    b = body(doc_folder="a" * 261) if which == "document" else body(telop_folder="t" * 261)
    r = c.post("/api/admin-settings", json=b)
    assert r.status_code == 400 and "260文字以内" in r.get_json()["error"]
    assert (tmp_path / "config.json").read_bytes() == before
    assert sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")) == names_before
    assert c.get("/api/rev").get_json()["rev"] == rev
