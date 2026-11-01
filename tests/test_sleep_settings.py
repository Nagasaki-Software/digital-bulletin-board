import json
import re
from datetime import date

import pytest

from app import create_app
from config import clean_admin_settings, load_config

DOCS = {"buttons": [{"label": "文書", "folder": "documents/doc1"}]}
NAME = re.compile(r"config_\d{8}_\d{6}(_\d+)?\.json")


def make(tmp_path, config=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    if config is not None:
        (tmp_path / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=1), encoding="utf-8")
    return create_app(tmp_path, today_func=lambda: date(2026, 11, 2)).test_client()


def body(**extra):
    b = {"documents": dict(DOCS), "telop": {"speed": 100}}
    for key, value in extra.items():
        if key == "idle_return_seconds":
            b["documents"]["idle_return_seconds"] = value
        else:
            b[key] = value
    return b


def cfg_bytes(tmp_path):
    p = tmp_path / "config.json"
    return p.read_bytes() if p.exists() else None


def tree(tmp_path):
    return sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if "logs" not in p.parts)


ALL = {
    "standby": {"start": "17:30", "end": "6:45", "wake_idle_seconds": 90},
    "accident_seconds": 25,
    "idle_return_seconds": 77,
    "edit_lock_seconds": 33,
}


def test_defaults_sleep_end_is_0800_and_get_returns_new_fields(tmp_path):
    cfg = load_config(tmp_path / "config.json")
    assert cfg["standby"] == {"start": "18:00", "end": "08:00", "wake_idle_seconds": 300}
    got = make(tmp_path).get("/api/admin-settings").get_json()
    assert got["standby"] == {"start": "18:00", "end": "08:00", "wake_idle_seconds": 300}
    assert got["accident_seconds"] == 15
    assert got["edit_lock_seconds"] == 60
    assert got["documents"]["idle_return_seconds"] == 120
    assert len(got["documents"]["buttons"]) == 3  # 従来の形は変えない
    assert got["telop"] == {"speed": 100, "folder": "telop"}
    assert got["company_name"] == "サンプル工業(株)"
    assert make(tmp_path / "b").get("/api/board").get_json()["settings"]["standby"]["end"] == "08:00"


def test_get_returns_configured_values_normalized(tmp_path):
    c = make(tmp_path, {"standby": {"start": "7:05", "end": "9:00", "wake_idle_seconds": 12}, "accident_seconds": 8.5,
                        "edit_lock_seconds": 5, "documents": {"idle_return_seconds": 40}})
    got = c.get("/api/admin-settings").get_json()
    assert got["standby"] == {"start": "07:05", "end": "09:00", "wake_idle_seconds": 12}
    assert got["accident_seconds"] == 8.5 and got["edit_lock_seconds"] == 5
    assert got["documents"]["idle_return_seconds"] == 40


def test_post_saves_normalizes_and_applies_without_restart(tmp_path):
    c = make(tmp_path)
    rev = c.get("/api/rev").get_json()["rev"]
    r = c.post("/api/admin-settings", json=body(**ALL))
    assert r.status_code == 200 and r.get_json() == {"ok": True}
    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert saved["standby"] == {"start": "17:30", "end": "06:45", "wake_idle_seconds": 90}  # "6:45" は "06:45" で保存
    assert saved["accident_seconds"] == 25 and saved["edit_lock_seconds"] == 33
    assert saved["documents"]["idle_return_seconds"] == 77
    assert not (tmp_path / "config.json").read_bytes().startswith(b"\xef\xbb\xbf")
    # 次の /api/board（画面の次の取得）から新しい値
    s = c.get("/api/board").get_json()["settings"]
    assert s["standby"] == {"start": "17:30", "end": "06:45", "wake_idle_seconds": 90}
    assert s["accident_seconds"] == 25 and s["edit_lock_seconds"] == 33 and s["documents_idle_seconds"] == 77
    assert c.get("/api/rev").get_json()["rev"] != rev  # 画面が取り直すきっかけ
    got = c.get("/api/admin-settings").get_json()
    assert got["standby"] == saved["standby"] and got["accident_seconds"] == 25
    assert got["documents"]["idle_return_seconds"] == 77 and got["edit_lock_seconds"] == 33


def test_other_keys_are_preserved(tmp_path):
    original = {
        "company_name": "テスト(株)",
        "default_theme": "dark",
        "default_edit_button": "on",
        "accident_folder": "事例",
        "telop": {"speed": 100, "folder": "お知らせ", "memo": 1},
        "standby": {"start": "19:00", "end": "07:00", "wake_idle_seconds": 10, "memo": "残す"},
        "documents": {"buttons": [{"label": "旧", "folder": "old"}], "idle_return_seconds": 45, "memo": 2},
        "memo": "手書き",
    }
    c = make(tmp_path, original)
    assert c.post("/api/admin-settings", json=body(standby={"end": "08:30"}, accident_seconds=20)).status_code == 200
    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert saved["standby"] == {"start": "19:00", "end": "08:30", "wake_idle_seconds": 10, "memo": "残す"}
    assert saved["accident_seconds"] == 20
    assert saved["documents"]["idle_return_seconds"] == 45 and saved["documents"]["memo"] == 2
    assert saved["documents"]["buttons"] == DOCS["buttons"]
    assert saved["telop"] == {"speed": 100, "folder": "お知らせ", "memo": 1}
    for key in ("company_name", "default_theme", "default_edit_button", "accident_folder", "memo"):
        assert saved[key] == original[key], key


def test_omitted_fields_keep_current_values_old_clients_still_work(tmp_path):
    original = {"standby": {"start": "19:00", "end": "07:00", "wake_idle_seconds": 10}, "accident_seconds": 20,
                "edit_lock_seconds": 30, "documents": {"idle_return_seconds": 45}}
    c = make(tmp_path, original)
    assert c.post("/api/admin-settings", json=body()).status_code == 200  # 古い画面: 新しい項目を送らない
    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    for key in ("standby", "accident_seconds", "edit_lock_seconds"):
        assert saved[key] == original[key], key
    assert saved["documents"]["idle_return_seconds"] == 45
    got = c.get("/api/admin-settings").get_json()
    assert got["standby"] == original["standby"] and got["accident_seconds"] == 20
    # 一部だけ送ると、その項目だけ変わる
    assert c.post("/api/admin-settings", json=body(standby={"start": "20:15"})).status_code == 200
    assert c.get("/api/admin-settings").get_json()["standby"] == {"start": "20:15", "end": "07:00", "wake_idle_seconds": 10}


def test_start_equal_to_end_is_allowed_never_sleeps(tmp_path):
    c = make(tmp_path)
    assert c.post("/api/admin-settings", json=body(standby={"start": "12:00", "end": "12:00"})).status_code == 200
    assert c.get("/api/board").get_json()["settings"]["standby"]["start"] == "12:00"
    assert c.get("/api/board").get_json()["settings"]["standby"]["end"] == "12:00"


def test_boundary_values_are_accepted(tmp_path):
    c = make(tmp_path)
    r = c.post("/api/admin-settings", json=body(standby={"start": "00:00", "end": "23:59", "wake_idle_seconds": 1},
                                                  accident_seconds=86400, edit_lock_seconds=1, idle_return_seconds=7.5))
    assert r.status_code == 200
    got = c.get("/api/admin-settings").get_json()
    assert got["standby"] == {"start": "00:00", "end": "23:59", "wake_idle_seconds": 1}
    assert got["accident_seconds"] == 86400 and got["documents"]["idle_return_seconds"] == 7.5


BAD_TIMES = ["24:00", "25:00", "12:60", "12:5", "abc", "", "  ", "8", "8:0", "08:00:00", "８:００", "-1:00", "1800", 800, None, True, ["8:00"], {"a": 1}, 8.0]
BAD_SECONDS = [0, 0.5, -1, 86401, 1e9, "60", "", None, True, False, [60], {"a": 1}]


def _bad_bodies():
    out = []
    for v in BAD_TIMES:
        out.append(("スリープ開始", body(standby={"start": v})))
        out.append(("スリープ終了", body(standby={"end": v})))
    for v in BAD_SECONDS:
        out.append(("操作なしでスリープに戻る", body(standby={"wake_idle_seconds": v})))
        out.append(("災害事例の表示秒数", body(accident_seconds=v)))
        out.append(("文書の操作なし戻り", body(idle_return_seconds=v)))
        out.append(("編集の自動終了", body(edit_lock_seconds=v)))
    for v in ["18:00", 5, None, ["a"], True]:
        out.append(("スリープ", body(standby=v)))
    return out


@pytest.mark.parametrize("label,bad_body", _bad_bodies())
@pytest.mark.parametrize("preexisting", [False, True])
def test_invalid_values_are_400_naming_the_field_and_save_nothing(tmp_path, label, bad_body, preexisting):
    c = make(tmp_path, {"company_name": "元のまま", "standby": {"start": "19:00"}} if preexisting else None)
    before = cfg_bytes(tmp_path)
    names_before = tree(tmp_path)
    rev = c.get("/api/rev").get_json()["rev"]
    r = c.post("/api/admin-settings", json=bad_body)
    assert r.status_code == 400
    msg = r.get_json()["error"]
    assert label in msg and any(ord(ch) > 127 for ch in msg)
    assert cfg_bytes(tmp_path) == before  # config.json は触らない
    assert tree(tmp_path) == names_before  # バックアップなども作らない
    assert c.get("/api/rev").get_json()["rev"] == rev
    assert c.get("/api/board").get_json()["settings"]["standby"]["start"] == ("19:00" if preexisting else "18:00")


def test_non_finite_numbers_are_rejected_by_the_validator():
    for v in (float("nan"), float("inf"), float("-inf")):
        for extra in ({"accident_seconds": v}, {"edit_lock_seconds": v}, {"standby": {"wake_idle_seconds": v}}):
            with pytest.raises(ValueError):
                clean_admin_settings({"documents": DOCS, "telop": {"speed": 100}, **extra})


def test_validator_returns_normalized_values_only_for_sent_fields():
    clean = clean_admin_settings(body(standby={"start": "7:30"}, accident_seconds=12))
    assert clean["standby"] == {"start": "07:30"}
    assert clean["accident_seconds"] == 12
    assert "edit_lock_seconds" not in clean and "idle_return_seconds" not in clean["documents"]
    plain = clean_admin_settings(body())
    assert "standby" not in plain and "accident_seconds" not in plain


def test_first_invalid_field_wins_over_a_valid_save_even_if_buttons_ok(tmp_path):
    c = make(tmp_path, {"company_name": "元"})
    before = cfg_bytes(tmp_path)
    r = c.post("/api/admin-settings", json=body(standby={"start": "09:00", "end": "99:00"}, accident_seconds=10))
    assert r.status_code == 400
    assert cfg_bytes(tmp_path) == before


def test_config_json_hand_values_are_normalized_on_load_and_bad_ones_fall_back(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"standby": {"start": "7:30", "end": "８:００"}}, ensure_ascii=False), encoding="utf-8")
    cfg = load_config(p)
    assert cfg["standby"]["start"] == "07:30" and cfg["standby"]["end"] == "08:00"  # 全角は使えない → 既定
    assert len(cfg["_warnings"]) == 1 and "standby.end" in cfg["_warnings"][0]


def test_backup_is_created_on_save_with_new_fields(tmp_path):
    c = make(tmp_path, {"company_name": "元の会社", "accident_seconds": 40})
    before = cfg_bytes(tmp_path)
    assert c.post("/api/admin-settings", json=body(**ALL)).status_code == 200
    found = sorted((tmp_path / "backups").iterdir())
    assert len(found) == 1 and NAME.fullmatch(found[0].name)
    assert found[0].read_bytes() == before
    assert json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))["accident_seconds"] == 25


def test_save_writes_log_without_leaking_free_text(tmp_path):
    c = make(tmp_path)
    assert c.post("/api/admin-settings", json=body(**ALL)).status_code == 200
    log = (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")
    assert "設定を保存しました" in log and "スリープ" in log
