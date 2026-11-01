import re
from datetime import date

import app as app_module
from app import APP_VERSION, create_app


def client(tmp_path):
    return create_app(tmp_path, today_func=lambda: date(2026, 11, 2)).test_client()


def test_app_version_is_semver_and_0_1_0():
    assert re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", APP_VERSION)
    assert APP_VERSION == "0.1.0"


def test_health_returns_version_and_is_cheap(tmp_path):
    c = client(tmp_path)
    rev = c.get("/api/rev").get_json()["rev"]
    r = c.get("/api/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok", "version": APP_VERSION}
    assert "charset=utf-8" in r.headers["Content-Type"].lower()
    for _ in range(3):
        assert c.get("/api/health").status_code == 200
    assert c.get("/api/rev").get_json()["rev"] == rev
    assert not (tmp_path / "config.json").exists()  # 設定には触れない


def test_health_does_not_touch_db_or_masters(tmp_path, monkeypatch):
    c = client(tmp_path)

    def boom(*a, **k):
        raise AssertionError("health must not read the DB or CSVs")

    monkeypatch.setattr(app_module.mst.Masters, "load_all", boom)
    monkeypatch.setattr(app_module.BoardDB, "ensure_day", boom)
    monkeypatch.setattr(app_module.BoardDB, "get_rev", boom)
    assert c.get("/api/health").get_json()["status"] == "ok"


def test_version_has_one_source_and_overlay_shows_it_from_health(tmp_path):
    c = client(tmp_path)
    html = c.get("/").get_data(as_text=True)
    settings = html[html.index('id="settings"'):html.index('id="standby"')]
    assert 'id="app-version-line"' in settings and 'id="app-version"' in settings
    line = settings[settings.index('id="app-version-line"'):]
    assert "hidden" in line[:80] and "バージョン" in line and "0.1.0" not in settings  # 画面に版数を直書きしない
    js = c.get("/js/admin-settings.js").get_data(as_text=True)
    assert "/api/health" in js and "0.1.0" not in js
    assert settings.index("閉じる") < settings.index("バージョン")  # 一番下に出す
