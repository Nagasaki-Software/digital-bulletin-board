import json
from pathlib import Path

import pytest

import migrate as mg


def make_old(root):
    """古い版のフォルダ（入力済み）。"""
    (root / "data" / "companies").mkdir(parents=True)
    (root / "data" / "constructions").mkdir(parents=True)
    (root / "app.py").write_text("# old", encoding="utf-8")
    (root / "data" / "board.db").write_bytes(b"OLD-DB")
    (root / "data" / "board.db-wal").write_bytes(b"OLD-WAL")
    (root / "data" / "genres.csv").write_text("name\n自社ジャンル\n", encoding="utf-8-sig")
    (root / "data" / "companies" / "自社.csv").write_text("責任者\n木村\n", encoding="utf-8-sig")
    (root / "data" / "constructions" / "自社工事.csv").write_text("作業内容\n据付\n", encoding="utf-8-sig")
    (root / "config.json").write_text(json.dumps({"company_name": "自社", "telop": {"folder": "お知らせ"}}, ensure_ascii=False), encoding="utf-8")
    (root / "admin_key.txt").write_text("KEY", encoding="utf-8")
    for d in ("accident_cases", "documents/doc1", "お知らせ", "whiteboard", "whiteboard_pdfs", "backups"):
        (root / d).mkdir(parents=True)
        (root / d / "a.pdf").write_bytes(b"%PDF")
    (root / "logs").mkdir()
    (root / "logs" / "board.log").write_text("log", encoding="utf-8")
    return root


def make_new(root):
    """新しい版を展開したばかりのフォルダ（見本入り・まだ起動していない）。"""
    (root / "data" / "companies").mkdir(parents=True)
    (root / "data" / "constructions").mkdir(parents=True)
    (root / "app.py").write_text("# new", encoding="utf-8")
    (root / "data" / "genres.csv").write_text("name\n見本ジャンル\n", encoding="utf-8-sig")
    (root / "data" / "equipment.csv").write_text("name\nクレーン\n", encoding="utf-8-sig")
    (root / "data" / "companies" / "見本電機.csv").write_text("責任者\n田中\n", encoding="utf-8-sig")
    (root / "data" / "constructions" / "電気工事.csv").write_text("作業内容\n配線\n", encoding="utf-8-sig")
    return root


@pytest.fixture
def both(tmp_path):
    return make_old(tmp_path / "old"), make_new(tmp_path / "new")


def run(old, new, **kw):
    kw.setdefault("is_running", lambda folder: False)
    return mg.migrate(old, new, **kw)


def test_copies_everything_the_board_needs(both):
    old, new = both
    report = run(old, new)
    assert (new / "data" / "board.db").read_bytes() == b"OLD-DB"
    assert (new / "data" / "board.db-wal").read_bytes() == b"OLD-WAL"
    assert (new / "data" / "genres.csv").read_text(encoding="utf-8-sig") == "name\n自社ジャンル\n"  # 古いほうで上書き
    assert (new / "data" / "equipment.csv").exists()  # 古いほうに無いファイルは新しいほうのまま
    assert json.loads((new / "config.json").read_text(encoding="utf-8"))["company_name"] == "自社"
    assert (new / "admin_key.txt").read_text(encoding="utf-8") == "KEY"
    for d in ("accident_cases", "documents/doc1", "お知らせ", "whiteboard", "whiteboard_pdfs", "backups"):
        assert (new / d / "a.pdf").exists(), d  # 設定で変えたテロップのフォルダ（お知らせ）も
    assert not (new / "logs").exists()  # ログは移さない
    assert any("data" in line for line in report)


def test_sample_companies_and_constructions_are_moved_aside(both):
    old, new = both
    run(old, new)
    assert sorted(p.name for p in (new / "data" / "companies").iterdir()) == ["自社.csv"]
    assert sorted(p.name for p in (new / "data" / "constructions").iterdir()) == ["自社工事.csv"]
    assert (new / "見本データ" / "companies" / "見本電機.csv").exists()
    assert (new / "見本データ" / "constructions" / "電気工事.csv").exists()


def test_old_folder_is_not_changed(both):
    old, new = both
    before = sorted((p.relative_to(old), p.read_bytes() if p.is_file() else None) for p in old.rglob("*"))
    run(old, new)
    after = sorted((p.relative_to(old), p.read_bytes() if p.is_file() else None) for p in old.rglob("*"))
    assert before == after


def test_absolute_folders_in_config_are_left_as_they_are(both, tmp_path):
    old, new = both
    shared = tmp_path / "shared"
    shared.mkdir()
    (old / "config.json").write_text(json.dumps({"accident_folder": str(shared)}), encoding="utf-8")
    report = run(old, new)
    assert any("そのまま" in line and str(shared) in line for line in report)


def test_stops_when_the_old_board_is_running(both):
    old, new = both
    with pytest.raises(mg.MigrateError, match="止めて"):
        run(old, new, is_running=lambda folder: True)
    assert not (new / "data" / "board.db").exists()


def test_stops_when_the_new_folder_already_has_entries(both):
    old, new = both
    (new / "data" / "board.db").write_bytes(b"NEW-DB")
    with pytest.raises(mg.MigrateError, match="入力した内容"):
        run(old, new)
    assert (new / "data" / "board.db").read_bytes() == b"NEW-DB"
    run(old, new, overwrite_db=True)  # 確かめたうえで上書きを選んだとき
    assert (new / "data" / "board.db").read_bytes() == b"OLD-DB"


@pytest.mark.parametrize("case", ["same", "not_app", "missing"])
def test_rejects_wrong_old_folder(both, tmp_path, case):
    old, new = both
    target = {"same": new, "not_app": tmp_path, "missing": tmp_path / "nothing"}[case]
    with pytest.raises(mg.MigrateError):
        run(target, new)


def test_running_twice_is_safe(both):
    old, new = both
    run(old, new)
    run(old, new, overwrite_db=True)
    assert (new / "data" / "board.db").read_bytes() == b"OLD-DB"
    assert (new / "見本データ" / "companies" / "見本電機.csv").exists()
    assert sorted(p.name for p in (new / "data" / "companies").iterdir()) == ["自社.csv"]


def test_folder_outside_old_root_in_config_is_not_copied(both, tmp_path):
    old, new = both
    (old / "config.json").write_text(json.dumps({"telop": {"folder": "../outside"}}), encoding="utf-8")
    (tmp_path / "outside").mkdir()
    run(old, new)
    assert not (tmp_path / "new" / ".." / "outside" / "copied").exists()
    assert not (new.parent / "outside").joinpath("a.pdf").exists()


def test_bat_is_shift_jis_with_crlf():
    raw = (Path(__file__).resolve().parent.parent / "データ引き継ぎ.bat").read_bytes()
    text = raw.decode("cp932")
    assert "\r\n" in text and "\n" not in text.replace("\r\n", "")
    assert "migrate.py" in text and "%~1" in text
