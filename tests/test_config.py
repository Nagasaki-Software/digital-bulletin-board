import json

from config import load_config


def test_defaults_when_file_missing(tmp_path):
    cfg = load_config(tmp_path / "config.json")
    assert cfg["accident_seconds"] == 15
    assert cfg["edit_lock_seconds"] == 60
    assert cfg["default_theme"] == "light"
    assert cfg["standby"] == {"start": "18:00", "end": "07:30", "wake_idle_seconds": 300}
    assert [b["label"] for b in cfg["documents"]["buttons"]] == ["文書1", "文書2", "文書3"]


def test_partial_override_keeps_other_defaults(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(
        json.dumps({"standby": {"start": "19:00"}, "company_name": "テスト(株)"}, ensure_ascii=False),
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg["company_name"] == "テスト(株)"
    assert cfg["standby"] == {"start": "19:00", "end": "07:30", "wake_idle_seconds": 300}


def test_bom_is_accepted(tmp_path):
    p = tmp_path / "config.json"
    p.write_text('{"accident_seconds": 30}', encoding="utf-8-sig")
    assert load_config(p)["accident_seconds"] == 30


def test_broken_json_falls_back_to_defaults(tmp_path, capsys):
    p = tmp_path / "config.json"
    p.write_text("{ broken", encoding="utf-8")
    cfg = load_config(p)
    assert cfg["accident_seconds"] == 15
    assert "config.json" in capsys.readouterr().err


def test_buttons_limited_to_five(tmp_path):
    p = tmp_path / "config.json"
    buttons = [{"label": f"文書{i}", "folder": f"documents/d{i}"} for i in range(7)]
    p.write_text(json.dumps({"documents": {"buttons": buttons}}, ensure_ascii=False), encoding="utf-8")
    assert len(load_config(p)["documents"]["buttons"]) == 5


def write_cfg(tmp_path, data):
    p = tmp_path / "config.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


DEFAULT_LABELS = ["文書1", "文書2", "文書3"]


def test_default_has_no_warnings_and_edit_button_off(tmp_path):
    cfg = load_config(tmp_path / "config.json")
    assert cfg["_warnings"] == []
    assert cfg["default_edit_button"] == "off"


def test_valid_edit_button_and_bad_edit_button(tmp_path):
    assert load_config(write_cfg(tmp_path, {"default_edit_button": "on"}))["default_edit_button"] == "on"
    for bad in ["yes", True, 1, None, ["on"]]:
        cfg = load_config(write_cfg(tmp_path, {"default_edit_button": bad}))
        assert cfg["default_edit_button"] == "off", bad
        assert any("default_edit_button" in w for w in cfg["_warnings"]), bad


def test_documents_wrong_shape_falls_back(tmp_path):
    for bad in [None, "文書", 5, [1]]:
        cfg = load_config(write_cfg(tmp_path, {"documents": bad}))
        assert [b["label"] for b in cfg["documents"]["buttons"]] == DEFAULT_LABELS, bad
        assert cfg["documents"]["idle_return_seconds"] == 120
        assert any("documents" in w for w in cfg["_warnings"]), bad


def test_buttons_wrong_shape_or_items(tmp_path):
    for bad in ["文書1", None, 7, {"label": "a", "folder": "b"}, []]:
        cfg = load_config(write_cfg(tmp_path, {"documents": {"buttons": bad}}))
        assert [b["label"] for b in cfg["documents"]["buttons"]] == DEFAULT_LABELS, bad
        assert any("buttons" in w for w in cfg["_warnings"]), bad
    items = [
        {"label": "良い", "folder": "documents/x"},
        {"label": "フォルダ無し"},
        {"folder": "documents/y"},
        {"label": "", "folder": "documents/z"},
        {"label": "数字", "folder": 5},
        "文字列",
        None,
        {"label": " 空白付き ", "folder": " documents/w "},
    ]
    cfg = load_config(write_cfg(tmp_path, {"documents": {"buttons": items}}))
    assert cfg["documents"]["buttons"] == [
        {"label": "良い", "folder": "documents/x"},
        {"label": "空白付き", "folder": "documents/w"},
    ]
    assert len(cfg["_warnings"]) == 6


def test_all_buttons_invalid_uses_defaults(tmp_path):
    cfg = load_config(write_cfg(tmp_path, {"documents": {"buttons": [{"label": "a"}, 3]}}))
    assert [b["label"] for b in cfg["documents"]["buttons"]] == DEFAULT_LABELS
    assert cfg["_warnings"]


def test_bad_seconds_use_defaults(tmp_path):
    for bad in ["abc", "15", 0, -3, 0.5, None, True, [5], {"a": 1}, 10**9, float("nan"), float("inf")]:
        cfg = load_config(
            write_cfg(
                tmp_path,
                {
                    "accident_seconds": bad,
                    "edit_lock_seconds": bad,
                    "documents": {"idle_return_seconds": bad},
                    "standby": {"wake_idle_seconds": bad},
                },
            )
        )
        assert cfg["accident_seconds"] == 15, bad
        assert cfg["edit_lock_seconds"] == 60, bad
        assert cfg["documents"]["idle_return_seconds"] == 120, bad
        assert cfg["standby"]["wake_idle_seconds"] == 300, bad
        for key in ["accident_seconds", "edit_lock_seconds", "idle_return_seconds", "wake_idle_seconds"]:
            assert any(key in w for w in cfg["_warnings"]), (bad, key)


def test_good_seconds_accepted_including_decimal(tmp_path):
    cfg = load_config(write_cfg(tmp_path, {"accident_seconds": 7.5, "edit_lock_seconds": 1}))
    assert cfg["accident_seconds"] == 7.5 and cfg["edit_lock_seconds"] == 1
    assert cfg["_warnings"] == []


def test_standby_wrong_shape(tmp_path):
    for bad in [None, "18:00", 5, ["18:00"]]:
        cfg = load_config(write_cfg(tmp_path, {"standby": bad}))
        assert cfg["standby"] == {"start": "18:00", "end": "07:30", "wake_idle_seconds": 300}, bad
        assert any("standby" in w for w in cfg["_warnings"]), bad
    cfg = load_config(write_cfg(tmp_path, {"standby": {"start": "25:00", "end": 7, "wake_idle_seconds": 60}}))
    assert cfg["standby"] == {"start": "18:00", "end": "07:30", "wake_idle_seconds": 60}
    assert len(cfg["_warnings"]) == 2


def test_bad_strings_use_defaults(tmp_path):
    for bad in [None, 5, "", "   ", ["a"], {"a": 1}]:
        cfg = load_config(write_cfg(tmp_path, {"company_name": bad, "accident_folder": bad}))
        assert cfg["company_name"] == "サンプル工業(株)", bad
        assert cfg["accident_folder"] == "accident_cases", bad
    for bad in ["blue", "", None, 3, "DARK"]:
        cfg = load_config(write_cfg(tmp_path, {"default_theme": bad}))
        assert cfg["default_theme"] == "light", bad
        assert any("default_theme" in w for w in cfg["_warnings"]), bad
    assert load_config(write_cfg(tmp_path, {"default_theme": "dark"}))["default_theme"] == "dark"


def test_wrong_top_level_and_broken_json_give_warning(tmp_path):
    for text in ["[]", '"x"', "null", "{ broken", "[" * 100000]:
        p = tmp_path / "config.json"
        p.write_text(text, encoding="utf-8")
        cfg = load_config(p)
        assert cfg["accident_seconds"] == 15, text[:10]
        assert cfg["_warnings"] and "config.json" in cfg["_warnings"][0], text[:10]


def test_warning_text_is_japanese_with_default(tmp_path):
    cfg = load_config(write_cfg(tmp_path, {"accident_seconds": "abc"}))
    assert cfg["_warnings"] == ["config.json の accident_seconds が正しくありません（15秒を使います）"]
