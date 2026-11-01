import json
from datetime import date

import pytest

from app import create_app
from config import clean_admin_settings

DOCS = {"buttons": [{"label": "文書", "folder": "documents/doc1"}]}


def make(tmp_path, config=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    if config is not None:
        (tmp_path / "config.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return create_app(tmp_path, today_func=lambda: date(2026, 11, 2)).test_client()


def post(c, **extra):
    return c.post("/api/admin-settings", json={"documents": DOCS, "telop": {"speed": 100}, **extra})


def test_get_returns_current_company_name(tmp_path):
    assert make(tmp_path).get("/api/admin-settings").get_json()["company_name"] == "サンプル工業(株)"
    c = make(tmp_path / "o", {"company_name": "東京製作所(株)"})
    assert c.get("/api/admin-settings").get_json()["company_name"] == "東京製作所(株)"


def test_post_saves_trimmed_name_and_applies_immediately(tmp_path):
    c = make(tmp_path, {"standby": {"start": "19:00"}, "accident_seconds": 20, "documents": {"idle_return_seconds": 33}})
    rev = c.get("/api/rev").get_json()["rev"]
    assert c.get("/api/board").get_json()["company_name"] == "サンプル工業(株)"
    r = post(c, company_name="  ○○工業(株)\u3000")
    assert r.status_code == 200
    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert saved["company_name"] == "○○工業(株)"
    assert saved["standby"] == {"start": "19:00"} and saved["accident_seconds"] == 20
    assert saved["documents"]["idle_return_seconds"] == 33
    assert c.get("/api/board").get_json()["company_name"] == "○○工業(株)"
    assert c.get("/api/admin-settings").get_json()["company_name"] == "○○工業(株)"
    assert c.get("/api/rev").get_json()["rev"] != rev


def test_post_without_company_name_keeps_the_current_one(tmp_path):
    c = make(tmp_path, {"company_name": "そのまま(株)"})
    assert post(c).status_code == 200
    assert c.get("/api/board").get_json()["company_name"] == "そのまま(株)"
    assert json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))["company_name"] == "そのまま(株)"


def test_100_chars_ok(tmp_path):
    c = make(tmp_path)
    assert post(c, company_name="あ" * 100).status_code == 200
    assert c.get("/api/board").get_json()["company_name"] == "あ" * 100


@pytest.mark.parametrize(
    "bad",
    ["", "   ", "\u3000", "あ" * 101, "a\nb", "a\tb", "a\x00b", "a\x7fb", "a\u200bb", "a\u202eb", 5, None, True, ["a"], {"a": 1}],
)
def test_invalid_company_name_is_400_and_saves_nothing(tmp_path, bad):
    c = make(tmp_path, {"company_name": "元の会社", "accident_seconds": 20})
    before = (tmp_path / "config.json").read_bytes()
    names_before = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    rev = c.get("/api/rev").get_json()["rev"]
    r = post(c, company_name=bad)
    assert r.status_code == 400
    assert r.get_json()["error"].startswith("会社名")
    assert (tmp_path / "config.json").read_bytes() == before
    assert sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")) == names_before
    assert c.get("/api/rev").get_json()["rev"] == rev
    assert c.get("/api/board").get_json()["company_name"] == "元の会社"


def test_clean_keeps_key_only_when_sent():
    base = {"documents": DOCS, "telop": {"speed": 100}}
    assert "company_name" not in clean_admin_settings(base)
    assert clean_admin_settings({**base, "company_name": " 甲 "})["company_name"] == "甲"


def test_static_input_and_wiring(tmp_path):
    c = make(tmp_path)
    html = c.get("/").get_data(as_text=True)
    settings = html[html.index('id="settings"'):html.index('id="standby"')]
    inp = 'id="company-input" type="text" maxlength="100" placeholder="例: ○○工業(株)"'
    assert inp in settings and "会社名（右上に表示）" in settings
    assert settings.index("全端末共通") < settings.index('id="company-input"') < settings.index("文書掲示")
    js = c.get("/js/admin-settings.js").get_data(as_text=True)
    assert 'company-input").value = s.company_name' in js
    assert 'const company = $("company-input").value.trim()' in js and "company_name: company" in js
