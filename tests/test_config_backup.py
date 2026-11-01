import json
import logging
import os
import re
from datetime import datetime
from datetime import date

import pytest

import config as config_mod
from app import create_app
from config import clean_admin_settings, save_admin_settings

NAME = re.compile(r"config_\d{8}_\d{6}(_\d+)?\.json")


def body(speed=250):
    return {
        "documents": {"buttons": [{"label": "手順書", "folder": "docs/new1"}]},
        "telop": {"speed": speed},
    }


def save(path, speed=250):
    save_admin_settings(path, clean_admin_settings(body(speed)))


def write_cfg(tmp_path, speed=100):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"company_name": "元の会社", "telop": {"speed": speed}}, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def backups(tmp_path):
    d = tmp_path / "backups"
    return sorted(d.iterdir()) if d.is_dir() else []


def speed_of(path):
    return json.loads(path.read_text(encoding="utf-8"))["telop"]["speed"]


def fake_clock(monkeypatch, start):
    """config.py の datetime.now() を、こちらで決めた時刻にする。state[0] を書き換えれば時刻が動く。"""
    state = [start]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return state[0]

    monkeypatch.setattr(config_mod, "datetime", Clock)
    return state


def test_backup_is_created_before_overwrite_with_same_content(tmp_path):
    p = write_cfg(tmp_path)
    before = p.read_bytes()
    save(p)
    found = backups(tmp_path)
    assert len(found) == 1 and NAME.fullmatch(found[0].name)
    assert found[0].read_bytes() == before  # 書き換える前の中身そのまま
    assert p.read_bytes() != before  # 本体は新しい設定になっている
    assert speed_of(p) == 250


def test_backup_name_uses_current_time(tmp_path, monkeypatch):
    fake_clock(monkeypatch, datetime(2026, 11, 1, 9, 5, 7))
    save(write_cfg(tmp_path))
    assert [f.name for f in backups(tmp_path)] == ["config_20261101_090507.json"]


def test_only_newest_five_backups_are_kept(tmp_path, monkeypatch):
    clock = fake_clock(monkeypatch, datetime(2026, 11, 1, 9, 0, 0))
    p = write_cfg(tmp_path, speed=100)
    for i in range(1, 9):  # 8回保存。バックアップの中身は「保存前の速度」= 100, 21, 22, ...
        clock[0] = datetime(2026, 11, 1, 9, 0, i)
        save(p, speed=20 + i)
    found = backups(tmp_path)
    assert len(found) == 5
    assert [speed_of(f) for f in found] == [23, 24, 25, 26, 27]  # 新しい5件


def test_same_second_saves_do_not_collide_and_numeric_order_is_respected(tmp_path, monkeypatch):
    fake_clock(monkeypatch, datetime(2026, 11, 1, 9, 0, 0))  # 時刻が動かない = 全部同じ秒
    p = write_cfg(tmp_path, speed=100)
    save(p, speed=21)
    save(p, speed=22)
    names = sorted(f.name for f in backups(tmp_path))
    assert names == ["config_20261101_090000.json", "config_20261101_090000_1.json"]
    assert speed_of(tmp_path / "backups" / "config_20261101_090000.json") == 100
    assert speed_of(tmp_path / "backups" / "config_20261101_090000_1.json") == 21
    for i in range(3, 13):  # _10, _11 まで増やす（文字の並びでは _10 が _2 より前になる）
        save(p, speed=20 + i)
    found = backups(tmp_path)
    assert len(found) == 5
    assert sorted(speed_of(f) for f in found) == [27, 28, 29, 30, 31]  # 最後の5回分（保存前の速度）


def test_prune_leaves_files_that_are_not_ours(tmp_path, monkeypatch):
    clock = fake_clock(monkeypatch, datetime(2026, 11, 1, 9, 0, 0))
    p = write_cfg(tmp_path)
    (tmp_path / "backups").mkdir()
    (tmp_path / "backups" / "メモ.txt").write_text("残す", encoding="utf-8")
    (tmp_path / "backups" / "config_manual.json").write_text("{}", encoding="utf-8")
    for i in range(1, 9):
        clock[0] = datetime(2026, 11, 1, 9, 0, i)
        save(p, speed=20 + i)
    names = sorted(f.name for f in backups(tmp_path))
    assert "メモ.txt" in names and "config_manual.json" in names
    assert len([n for n in names if NAME.fullmatch(n)]) == 5


def test_first_save_makes_no_backup(tmp_path):
    p = tmp_path / "config.json"
    save(p)
    assert p.exists()
    assert not (tmp_path / "backups").exists()


@pytest.mark.parametrize("content", ["{ broken", "[1, 2]", "null", ""])
def test_refused_save_makes_no_backup(tmp_path, content):
    p = tmp_path / "config.json"
    p.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        save(p)
    assert not (tmp_path / "backups").exists()


def test_validation_error_makes_no_backup(tmp_path):
    p = write_cfg(tmp_path)
    c = create_app(tmp_path, today_func=lambda: date(2026, 11, 2)).test_client()
    bad = body(speed=5)  # 速度の範囲外
    assert c.post("/api/admin-settings", json=bad).status_code == 400
    assert not (tmp_path / "backups").exists()
    assert speed_of(p) == 100


def test_backup_failure_does_not_block_save_and_warns(tmp_path, monkeypatch, app_caplog):
    p = write_cfg(tmp_path)

    def denied(*a, **k):
        raise PermissionError("denied")

    monkeypatch.setattr(config_mod.shutil, "copyfile", denied)
    save(p)
    assert speed_of(p) == 250  # 保存は成功
    assert any("バックアップ" in r.getMessage() and r.levelno == logging.WARNING for r in app_caplog.records)


def test_backup_folder_unusable_does_not_block_save(tmp_path, app_caplog):
    p = write_cfg(tmp_path)
    (tmp_path / "backups").write_text("ファイルがフォルダの場所にある", encoding="utf-8")
    save(p)
    assert speed_of(p) == 250
    assert any("バックアップ" in r.getMessage() for r in app_caplog.records)


def test_backup_does_not_log_file_content(tmp_path, app_caplog):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"company_name": "秘密のしるしXYZ", "telop": {"speed": 100}}, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "backups").write_text("x", encoding="utf-8")  # 失敗させて警告を出させる
    save(p)
    assert app_caplog.records and "秘密のしるしXYZ" not in app_caplog.text


def test_backup_via_http_save(tmp_path):
    p = write_cfg(tmp_path)
    before = p.read_bytes()
    c = create_app(tmp_path, today_func=lambda: date(2026, 11, 2)).test_client()
    assert c.post("/api/admin-settings", json=body()).status_code == 200
    found = backups(tmp_path)
    assert len(found) == 1 and found[0].read_bytes() == before


# ---- 変わらない保存は、控えを増やさない ----

def test_identical_saves_do_not_push_out_the_real_change_point_backup(tmp_path, monkeypatch):
    clock = fake_clock(monkeypatch, datetime(2026, 11, 1, 9, 0, 0))
    p = write_cfg(tmp_path, speed=100)
    original = p.read_bytes()
    save(p, speed=250)  # 本当の変更: 元の中身がバックアップになる
    (first,) = backups(tmp_path)
    assert first.read_bytes() == original
    for i in range(1, 7):  # 同じ内容の保存を6回
        clock[0] = datetime(2026, 11, 1, 9, 0, i)
        save(p, speed=250)
    assert [f.name for f in backups(tmp_path)] == [first.name]
    assert first.read_bytes() == original  # 元の設定は残っている
    assert speed_of(p) == 250


def test_identical_save_does_not_even_rewrite_the_file(tmp_path):
    p = write_cfg(tmp_path, speed=100)
    save(p, speed=250)
    st = p.stat()
    before = p.read_bytes()
    save(p, speed=250)
    assert p.read_bytes() == before and p.stat().st_mtime_ns == st.st_mtime_ns
    assert not (tmp_path / "config.json.tmp").exists()


def test_save_that_equals_a_hand_formatted_file_is_also_a_no_op(tmp_path):
    p = tmp_path / "config.json"
    p.write_text('{"documents":{"buttons":[{"label":"手順書","folder":"docs/new1"}]},"telop":{"speed":250}}', encoding="utf-8")
    before = p.read_bytes()
    save(p, speed=250)
    assert p.read_bytes() == before and not (tmp_path / "backups").exists()


def test_a_real_change_after_no_ops_still_backs_up(tmp_path, monkeypatch):
    clock = fake_clock(monkeypatch, datetime(2026, 11, 1, 9, 0, 0))
    p = write_cfg(tmp_path, speed=100)
    save(p, speed=250)
    save(p, speed=250)
    clock[0] = datetime(2026, 11, 1, 9, 0, 5)
    save(p, speed=300)
    assert [speed_of(f) for f in backups(tmp_path)] == [100, 250]


def test_no_op_save_through_http_keeps_backups_and_still_answers_ok(tmp_path):
    write_cfg(tmp_path)
    c = create_app(tmp_path, today_func=lambda: date(2026, 11, 2)).test_client()
    assert c.post("/api/admin-settings", json=body()).status_code == 200
    (first,) = backups(tmp_path)
    for _ in range(6):
        assert c.post("/api/admin-settings", json=body()).status_code == 200
    assert backups(tmp_path) == [first]


def test_prune_sorts_by_file_time_and_never_deletes_the_file_just_made(tmp_path, monkeypatch):
    """時計が戻った（名前が新しいのに古いファイルがある）ときも、いま作った控えを消さない。"""
    clock = fake_clock(monkeypatch, datetime(2026, 11, 1, 9, 0, 0))
    p = write_cfg(tmp_path, speed=100)
    folder = tmp_path / "backups"
    folder.mkdir()
    for i in range(5):  # 名前だけ未来の日付（時計が進んでいた頃の控え）。更新日時は古い
        f = folder / f"config_20991231_00000{i}.json"
        f.write_text(json.dumps({"telop": {"speed": 900 + i}}), encoding="utf-8")
        os.utime(f, (1_000_000 + i, 1_000_000 + i))
    save(p, speed=250)
    found = backups(tmp_path)
    assert len(found) == 5
    made = [f for f in found if speed_of(f) == 100]
    assert len(made) == 1  # いま作った控え（元の速度 100）は残っている
    assert sorted(speed_of(f) for f in found if speed_of(f) != 100) == [901, 902, 903, 904]  # いちばん古い更新日時の1件が消えた
    clock[0] = datetime(2026, 11, 1, 9, 0, 1)
    save(p, speed=260)
    assert any(speed_of(f) == 250 for f in backups(tmp_path))
