import json
from datetime import date

import pytest

from app import create_app
from config import clean_admin_settings, load_config

BASE = {"documents": {"buttons": [{"label": "a", "folder": "documents/x"}]}, "telop": {"speed": 100}}


def make(tmp_path, config=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    if config is not None:
        (tmp_path / "config.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return create_app(tmp_path, today_func=lambda: date(2026, 11, 2)).test_client()


def test_defaults_are_returned_and_board_gets_idle_seconds(tmp_path):
    c = make(tmp_path)
    got = c.get("/api/admin-settings").get_json()
    assert got["whiteboard_save_folder"] == "whiteboard"
    assert got["whiteboard_pdf_folder"] == "whiteboard_pdfs"
    assert got["whiteboard_idle_seconds"] == 180
    assert c.get("/api/board").get_json()["settings"]["whiteboard_idle_seconds"] == 180


def test_pdf_folder_is_made_at_startup_but_save_folder_is_not(tmp_path):
    make(tmp_path)
    assert (tmp_path / "whiteboard_pdfs").is_dir()
    assert not (tmp_path / "whiteboard").exists()  # 保存先は、最初に保存するときに作る（ネットワークの場所を起動時に触らない）


def test_post_saves_the_three_values(tmp_path):
    c = make(tmp_path)
    body = {**BASE, "whiteboard_save_folder": "//server/share/ホワイト", "whiteboard_pdf_folder": "D:/背景", "whiteboard_idle_seconds": 90}
    r = c.post("/api/admin-settings", json=body)
    assert r.status_code == 200, r.get_json()
    got = c.get("/api/admin-settings").get_json()
    assert (got["whiteboard_save_folder"], got["whiteboard_pdf_folder"], got["whiteboard_idle_seconds"]) == ("//server/share/ホワイト", "D:/背景", 90)
    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert saved["whiteboard_idle_seconds"] == 90


def test_empty_folder_means_default_and_missing_keys_keep_current(tmp_path):
    c = make(tmp_path, {"whiteboard_save_folder": "mine", "whiteboard_idle_seconds": 60})
    clean = clean_admin_settings({**BASE, "whiteboard_save_folder": "  ", "whiteboard_pdf_folder": ""})
    assert clean["whiteboard_save_folder"] == "whiteboard" and clean["whiteboard_pdf_folder"] == "whiteboard_pdfs"
    assert "whiteboard_idle_seconds" not in clean_admin_settings(BASE)  # 古い画面は送らない → いまのまま
    assert c.post("/api/admin-settings", json=BASE).status_code == 200
    assert c.get("/api/admin-settings").get_json()["whiteboard_save_folder"] == "mine"


@pytest.mark.parametrize("bad", [29, 3601, 0, -5, 90.5, "90", None, True, [90]])
def test_idle_seconds_must_be_30_to_3600(bad):
    with pytest.raises(ValueError, match="30〜3600"):
        clean_admin_settings({**BASE, "whiteboard_idle_seconds": bad})


@pytest.mark.parametrize("ok", [30, 180, 3600])
def test_idle_seconds_edges_are_accepted(ok):
    assert clean_admin_settings({**BASE, "whiteboard_idle_seconds": ok})["whiteboard_idle_seconds"] == ok


@pytest.mark.parametrize("key", ["whiteboard_save_folder", "whiteboard_pdf_folder"])
def test_folders_reject_parent_marks_non_text_and_long_paths(key):
    for bad in ("a/../b", "..", 5, ["x"], "x" * 261):
        with pytest.raises(ValueError):
            clean_admin_settings({**BASE, key: bad})
    assert clean_admin_settings({**BASE, key: "x" * 260})[key] == "x" * 260


def test_bad_values_in_config_json_fall_back_with_a_warning(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"whiteboard_idle_seconds": 5, "whiteboard_save_folder": 3}), encoding="utf-8")
    cfg = load_config(p)
    assert cfg["whiteboard_idle_seconds"] == 180 and cfg["whiteboard_save_folder"] == "whiteboard"
    assert any("whiteboard_idle_seconds" in w for w in cfg["_warnings"])
