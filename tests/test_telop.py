import json
from datetime import date

import telop
from app import create_app


def make_client(tmp_path, config=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    if config is not None:
        (tmp_path / "config.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return create_app(tmp_path, today_func=lambda: date(2026, 11, 2)).test_client()


def items(c):
    r = c.get("/api/telop")
    assert r.status_code == 200
    assert "charset=utf-8" in r.headers["Content-Type"].lower()
    return r.get_json()["items"]


def test_empty_when_no_files_and_folder_is_created(tmp_path):
    c = make_client(tmp_path)
    assert items(c) == []
    assert (tmp_path / "telop").is_dir()


def test_utf8_bom_cp932_utf8_without_bom_and_blank_lines(tmp_path):
    c = make_client(tmp_path)
    d = tmp_path / "telop"
    (d / "a.txt").write_bytes("﻿今日は晴れ\r\n\r\n  \r\n\"安全\"第一\r\n".encode("utf-8"))
    (d / "b.txt").write_bytes("明日は雨です\n\n来週は休み".encode("cp932"))
    (d / "c.txt").write_bytes("ＵＴＦ８ ｶﾀｶﾅ\n".encode("utf-8"))
    assert items(c) == ["今日は晴れ", "\"安全\"第一", "明日は雨です", "来週は休み", "ＵＴＦ８ ｶﾀｶﾅ"]


def test_files_sorted_by_name_non_txt_and_subfolders_ignored(tmp_path):
    c = make_client(tmp_path)
    d = tmp_path / "telop"
    (d / "10.txt").write_text("十", encoding="utf-8")
    (d / "2.txt").write_text("二", encoding="utf-8")
    (d / "A.TXT").write_text("大文字拡張子", encoding="utf-8")
    (d / "memo.csv").write_text("無視", encoding="utf-8")
    (d / "note.txt.bak").write_text("無視", encoding="utf-8")
    (d / "sub").mkdir()
    (d / "sub" / "x.txt").write_text("無視", encoding="utf-8")
    (d / "dir.txt").mkdir()
    assert items(c) == ["二", "十", "大文字拡張子"]


def test_unreadable_file_is_ignored(tmp_path, monkeypatch):
    c = make_client(tmp_path)
    d = tmp_path / "telop"
    (d / "a.txt").write_text("読める", encoding="utf-8")
    (d / "b.txt").write_text("読めない", encoding="utf-8")
    real = telop.Path.read_bytes

    def flaky(self):
        if self.name == "b.txt":
            raise PermissionError("locked")
        return real(self)

    monkeypatch.setattr(telop.Path, "read_bytes", flaky)
    assert items(c) == ["読める"]


def test_undecodable_bytes_are_replaced_not_fatal(tmp_path):
    c = make_client(tmp_path)
    (tmp_path / "telop" / "bad.txt").write_bytes(b"ok\n\x81\n\xff\xfe\xfd\n")
    got = items(c)
    assert got[0] == "ok" and len(got) >= 2


def test_custom_folder_from_config(tmp_path):
    c = make_client(tmp_path, {"telop": {"folder": "お知らせ置き場"}})
    (tmp_path / "お知らせ置き場" / "x.txt").write_text("カスタム", encoding="utf-8")
    assert items(c) == ["カスタム"]
    assert not (tmp_path / "telop").exists()


def test_rev_changes_when_a_txt_is_edited_added_or_removed(tmp_path):
    c = make_client(tmp_path)
    d = tmp_path / "telop"
    r0 = c.get("/api/rev").get_json()["rev"]
    f = d / "a.txt"
    f.write_text("one", encoding="utf-8")
    r1 = c.get("/api/rev").get_json()["rev"]
    assert r1 != r0
    f.write_text("one two", encoding="utf-8")  # サイズが変わる
    r2 = c.get("/api/rev").get_json()["rev"]
    assert r2 != r1
    assert c.get("/api/rev").get_json()["rev"] == r2  # 変更が無ければ変わらない
    (d / "ignored.csv").write_text("x", encoding="utf-8")
    assert c.get("/api/rev").get_json()["rev"] == r2
    f.unlink()
    assert c.get("/api/rev").get_json()["rev"] != r2


def test_board_exposes_telop_settings_without_folder(tmp_path):
    s = make_client(tmp_path).get("/api/board").get_json()["settings"]
    assert s["telop"] == {"speed": 100}
    c = make_client(tmp_path / "x", {"telop": {"speed": 60, "folder": "秘密のパス"}})
    assert c.get("/api/board").get_json()["settings"]["telop"] == {"speed": 60}


def test_bad_telop_config_warns_and_unreachable_folder_does_not_crash(tmp_path):
    c = make_client(tmp_path, {"telop": {"speed": 5}})
    b = c.get("/api/board").get_json()
    assert b["settings"]["telop"]["speed"] == 100
    assert any("telop.speed" in w for w in b["warnings"])
    (tmp_path / "w").mkdir()
    (tmp_path / "w" / "blocker").write_text("ファイル", encoding="utf-8")  # この下にフォルダは作れない
    c2 = make_client(tmp_path / "w", {"telop": {"folder": "blocker/sub"}})
    b2 = c2.get("/api/board").get_json()
    assert any("お知らせ" in w and "フォルダ" in w for w in b2["warnings"])
    assert c2.get("/api/telop").get_json() == {"items": []}
    assert c2.get("/api/rev").status_code == 200
