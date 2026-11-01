import json
import os
from pathlib import Path

import pytest

from config import clean_admin_settings, load_config, save_admin_settings


def write_cfg(tmp_path, data):
    p = tmp_path / "config.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


# ---- telop の設定 ----
def test_telop_defaults(tmp_path):
    cfg = load_config(tmp_path / "config.json")
    assert cfg["telop"] == {"speed": 100, "folder": "telop"}
    assert cfg["_warnings"] == []


def test_telop_valid_values(tmp_path):
    cfg = load_config(write_cfg(tmp_path, {"telop": {"speed": 20, "folder": "D:/お知らせ"}}))
    assert cfg["telop"] == {"speed": 20, "folder": "D:/お知らせ"}
    assert cfg["_warnings"] == []
    assert load_config(write_cfg(tmp_path, {"telop": {"speed": 500}}))["telop"]["speed"] == 500


def test_telop_wrong_shape_falls_back(tmp_path):
    for bad in [None, "表示", 5, [1], True]:
        cfg = load_config(write_cfg(tmp_path, {"telop": bad}))
        assert cfg["telop"] == {"speed": 100, "folder": "telop"}, bad
        assert any("telop" in w for w in cfg["_warnings"]), bad


def test_telop_items_are_checked_one_by_one(tmp_path):
    for bad in [19, 501, 0, -1, 100.5, "100", None, True, [100], float("nan")]:
        cfg = load_config(write_cfg(tmp_path, {"telop": {"folder": "x", "speed": bad}}))
        assert cfg["telop"]["speed"] == 100, bad
        assert cfg["telop"]["folder"] == "x", bad  # 正しい項目は生きる
        assert cfg["_warnings"] == ["config.json の telop.speed が正しくありません（100を使います）"], bad
    # 表示・非表示の設定は無い（常に表示）。enabled を書いても無視され、警告も出ない
    cfg = load_config(write_cfg(tmp_path, {"telop": {"enabled": False, "speed": 50}}))
    assert cfg["telop"] == {"speed": 50, "folder": "telop"} and cfg["_warnings"] == []
    for bad in ["", "  ", 5, None, "a" * 261, "x\0y"]:
        cfg = load_config(write_cfg(tmp_path, {"telop": {"folder": bad}}))
        assert cfg["telop"]["folder"] == "telop", bad
        assert any("telop.folder" in w for w in cfg["_warnings"]), bad


# ---- 管理画面からの保存（検証と書き込み） ----
GOOD = {
    "documents": {"buttons": [{"label": " 手順書 ", "folder": " D:\\文書 "}, {"label": "図面", "folder": "//server/share/x"}]},
    "telop": {"speed": 250},
}


def test_clean_admin_settings_accepts_and_trims():
    assert clean_admin_settings(GOOD) == {
        "documents": {"buttons": [{"label": "手順書", "folder": "D:\\文書"}, {"label": "図面", "folder": "//server/share/x"}]},
        "telop": {"speed": 250},
    }


def _bad_cases():
    ok = {"label": "a", "folder": "b"}

    def doc(buttons):
        return {"documents": {"buttons": buttons}, "telop": {"speed": 100}}

    def tel(**kw):
        return {"documents": GOOD["documents"], "telop": {"speed": 100, **kw}}

    return [
        None, [], "x", {}, {"documents": GOOD["documents"]}, {"telop": GOOD["telop"]},
        {"documents": None, "telop": GOOD["telop"]}, {"documents": {}, "telop": GOOD["telop"]},
        doc("x"), doc([]), doc([ok] * 6), doc([5]), doc([None]), doc([{"label": "a"}]), doc([{"folder": "b"}]),
        doc([{"label": "", "folder": "b"}]), doc([{"label": "a", "folder": "  "}]), doc([{"label": 1, "folder": "b"}]),
        doc([{"label": "a", "folder": None}]), doc([{"label": "x" * 101, "folder": "b"}]),
        doc([{"label": "a", "folder": "y" * 261}]), doc([{"label": "a", "folder": "b\0"}]), doc([ok, {"label": "a"}]),
        {"documents": GOOD["documents"], "telop": None}, {"documents": GOOD["documents"], "telop": {}},
        tel(speed=19), tel(speed=501), tel(speed=100.5), tel(speed="100"), tel(speed=True), tel(speed=None),
    ]


@pytest.mark.parametrize("bad", _bad_cases())
def test_clean_admin_settings_rejects_with_japanese_reason(bad):
    with pytest.raises(ValueError) as e:
        clean_admin_settings(bad)
    assert str(e.value) and any(ord(ch) > 127 for ch in str(e.value))


def test_save_keeps_unrelated_keys_and_writes_atomically(tmp_path):
    p = tmp_path / "config.json"
    original = {
        "company_name": "テスト(株)",
        "accident_seconds": 20,
        "documents": {"buttons": [{"label": "旧", "folder": "old"}], "idle_return_seconds": 33, "memo": "残す"},
        "telop": {"speed": 100, "folder": "D:/お知らせ", "enabled": False},
        "my_note": {"a": [1, 2]},
    }
    p.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8-sig")
    save_admin_settings(p, clean_admin_settings(GOOD))
    raw = p.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    saved = json.loads(raw.decode("utf-8"))
    assert saved["company_name"] == "テスト(株)" and saved["accident_seconds"] == 20 and saved["my_note"] == {"a": [1, 2]}
    assert saved["documents"]["idle_return_seconds"] == 33 and saved["documents"]["memo"] == "残す"
    assert saved["documents"]["buttons"][0] == {"label": "手順書", "folder": "D:\\文書"}
    assert saved["telop"] == {"speed": 250, "folder": "D:/お知らせ", "enabled": False}
    assert "手順書" in raw.decode("utf-8")  # ensure_ascii=False
    assert [f.name for f in tmp_path.iterdir()] == ["config.json"]  # 一時ファイルが残らない


def test_save_starts_from_empty_when_file_is_missing(tmp_path):
    p = tmp_path / "config.json"
    save_admin_settings(p, clean_admin_settings(GOOD))
    saved = json.loads(p.read_text(encoding="utf-8"))
    assert set(saved) == {"documents", "telop"}
    assert saved["telop"] == {"speed": 250}
    assert len(saved["documents"]["buttons"]) == 2


@pytest.mark.parametrize("content", ["{ broken", "[1, 2]", "null", '"text"', "", b"\xff\xfe\x00", b"\xef\xbb\xbf{ \"a\": "])
def test_save_refuses_broken_config_and_leaves_it_untouched(tmp_path, content):
    p = tmp_path / "config.json"
    if isinstance(content, str):
        p.write_text(content, encoding="utf-8")
    else:
        p.write_bytes(content)
    before = p.read_bytes()
    with pytest.raises(ValueError) as e:
        save_admin_settings(p, clean_admin_settings(GOOD))
    assert str(e.value) == "config.json に書き間違いがあります。直してから保存してください"
    assert p.read_bytes() == before
    assert [f.name for f in tmp_path.iterdir()] == ["config.json"]


def test_save_does_not_swallow_unreadable_config(tmp_path, monkeypatch):
    # 読めない（権限・他のプログラムが使用中など）ときも、空から作り直さず OSError のまま失敗する
    p = tmp_path / "config.json"
    p.write_text('{"company_name": "元"}', encoding="utf-8")
    before = p.read_bytes()
    real_open = open

    def locked(file, *a, **k):
        if Path(file).name == "config.json":
            raise PermissionError("locked")
        return real_open(file, *a, **k)

    monkeypatch.setattr("builtins.open", locked)
    with pytest.raises(PermissionError):
        save_admin_settings(p, clean_admin_settings(GOOD))
    monkeypatch.undo()
    assert p.read_bytes() == before
    assert [f.name for f in tmp_path.iterdir()] == ["config.json"]


@pytest.mark.parametrize(
    "folder",
    ["..", "../x", "a/../b", "a/..", "..\\x", "a\\..\\b", "a/..\\b", "//server/share/../x", "D:\\文書\\..\\..\\Windows", "a//../b"],
)
def test_folder_with_parent_segment_is_rejected(folder):
    body = {"documents": {"buttons": [{"label": "a", "folder": folder}]}, "telop": {"speed": 100}}
    with pytest.raises(ValueError) as e:
        clean_admin_settings(body)
    assert "..」" in str(e.value) and "フォルダパス 1 " in str(e.value)


@pytest.mark.parametrize("folder", ["a..b", "..x", "x..", "...", "documents/v1..2", "//server/share/x", "D:\\文書", "D:/文書", ".hidden/x"])
def test_folder_names_merely_containing_dots_are_allowed(folder):
    body = {"documents": {"buttons": [{"label": "a", "folder": folder}]}, "telop": {"speed": 100}}
    assert clean_admin_settings(body)["documents"]["buttons"][0]["folder"] == folder


def test_save_failure_leaves_original_and_no_temp(tmp_path, monkeypatch):
    p = tmp_path / "config.json"
    p.write_text('{"company_name": "元"}', encoding="utf-8")
    before = p.read_bytes()

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        save_admin_settings(p, clean_admin_settings(GOOD))
    assert p.read_bytes() == before
    assert [f.name for f in tmp_path.iterdir()] == ["config.json"]


def test_blank_row_messages_name_the_row():
    def body(buttons):
        return {"documents": {"buttons": buttons}, "telop": {"speed": 100}}

    ok = {"label": "a", "folder": "b"}
    with pytest.raises(ValueError, match="ラベル 2 を入力"):
        clean_admin_settings(body([ok, {"label": " ", "folder": "x"}]))
    with pytest.raises(ValueError, match="フォルダパス 3 を入力"):
        clean_admin_settings(body([ok, ok, {"label": "c", "folder": ""}]))


def test_clean_telop_folder_blank_default_and_absent():
    def body(**telop):
        return {"documents": GOOD["documents"], "telop": {"speed": 100, **telop}}

    assert "folder" not in clean_admin_settings(body())["telop"]  # 送られなければ現状のまま
    assert clean_admin_settings(body(folder=""))["telop"]["folder"] == "telop"
    assert clean_admin_settings(body(folder="  D:/共有/サイネージ "))["telop"]["folder"] == "D:/共有/サイネージ"
    assert clean_admin_settings(body(folder="//server/share/x"))["telop"]["folder"] == "//server/share/x"
