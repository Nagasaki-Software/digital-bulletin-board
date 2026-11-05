import os
import re
import shutil
from pathlib import Path

import pytest

import masters as m

ROOT = Path(__file__).resolve().parent.parent
DECODE_HINT = "CSV UTF-8（コンマ区切り）"


def put(path, text, encoding="utf-8-sig"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding=encoding, newline="")


def company(tmp_path, name, text, encoding="utf-8-sig"):
    put(tmp_path / "companies" / f"{name}.csv", text, encoding)


def construction(tmp_path, name, text, encoding="utf-8-sig"):
    put(tmp_path / "constructions" / f"{name}.csv", text, encoding)


def load(tmp_path):
    put(tmp_path / "genres.csv", "name\n溶接作業\n")  # 登録フォルダ以外の警告（genres.csv が無い）を出さないため
    return m.Masters(tmp_path).load_all()


# ---- 会社（data/companies/*.csv） ----
def test_company_names_are_the_file_names_in_natural_order(tmp_path):
    for name in ["10班", "2班", "見本電機", "abc", "1班", "B", "Abd", "班10", "班2"]:
        company(tmp_path, name, "責任者\n")
    data = load(tmp_path)
    # 数字は数として比べ（1,2,10）、数字で始まる名前が先。英字は大文字小文字を区別せず、残りは名前順
    assert data["companies"] == ["1班", "2班", "10班", "abc", "Abd", "B", "班2", "班10", "見本電機"]
    assert [w for w in data["warnings"] if "companies" in w] == []


def test_leaders_keep_the_output_shape_and_order(tmp_path):
    company(tmp_path, "2班", "責任者,内線,外線\n高橋,1240,\n")
    company(tmp_path, "1班", "責任者,内線,外線\n佐藤,1234,\n鈴木,1235,03-0000-0000\n")
    data = load(tmp_path)
    assert data["companies"] == ["1班", "2班"]
    assert data["leaders"] == [
        {"company": "1班", "leader_name": "佐藤", "ext": "1234", "outside": ""},
        {"company": "1班", "leader_name": "鈴木", "ext": "1235", "outside": "03-0000-0000"},
        {"company": "2班", "leader_name": "高橋", "ext": "1240", "outside": ""},
    ]


def test_ignored_names_in_the_companies_folder(tmp_path):
    company(tmp_path, "1班", "責任者\n佐藤\n")
    for bad in ["~$1班.csv", ".hidden.csv", "_雛形.csv", "memo.txt", "メモ", "x.csv.bak", "名簿.xlsx"]:
        put(tmp_path / "companies" / bad, "責任者\n誰か\n")
    (tmp_path / "companies" / "フォルダ.csv").mkdir()  # 名前が .csv でもフォルダは使わない
    (tmp_path / "companies" / "sub").mkdir()
    put(tmp_path / "companies" / "sub" / "中.csv", "責任者\n誰か\n")
    put(tmp_path / "companies" / "大文字.CSV", "責任者\n山本\n")  # 拡張子は大文字でもよい
    data = load(tmp_path)
    assert data["companies"] == ["1班", "大文字"]
    assert [l["leader_name"] for l in data["leaders"]] == ["佐藤", "山本"]
    assert not [w for w in data["warnings"] if "companies" in w]


@pytest.mark.parametrize(
    "raw",
    [
        "﻿責任者,内線,外線\r\n佐藤,1234,03-0000-0001\r\n".encode("utf-8"),  # BOM + CRLF（Excel）
        "責任者,内線,外線\n佐藤,1234,03-0000-0001\n".encode("utf-8"),  # BOM なし + LF
        "leader_name,ext,outside\n佐藤,1234,03-0000-0001\n".encode("utf-8"),  # 英語の見出し（旧）
        "outside,責任者,ext\n03-0000-0001,佐藤,1234\n".encode("utf-8"),  # 列の順番は自由。日本語と英語の混在も可
        "内線,外線,責任者\n1234,03-0000-0001,佐藤\n".encode("utf-8"),
        " 責任者 , 内線 ,　外線　\n 佐藤 , 1234 , 03-0000-0001 \n".encode("utf-8"),  # 見出しも値も前後の空白は除く
        "責任者,内線,外線,備考\n佐藤,1234,03-0000-0001,メモ\n".encode("utf-8"),  # 知らない列は無視
    ],
)
def test_company_file_header_and_encoding_variants(tmp_path, raw):
    (tmp_path / "companies").mkdir()
    (tmp_path / "companies" / "1班.csv").write_bytes(raw)
    data = load(tmp_path)
    assert data["leaders"] == [{"company": "1班", "leader_name": "佐藤", "ext": "1234", "outside": "03-0000-0001"}]
    assert [w for w in data["warnings"] if "companies" in w or "1班" in w] == []


def test_ext_and_outside_columns_are_optional(tmp_path):
    company(tmp_path, "1班", "責任者\n佐藤\n")
    company(tmp_path, "2班", "責任者,外線\n高橋,03-0000-0002\n")
    company(tmp_path, "3班", "leader_name,ext\n鈴木,1235\n")
    data = load(tmp_path)
    assert data["leaders"] == [
        {"company": "1班", "leader_name": "佐藤", "ext": "", "outside": ""},
        {"company": "2班", "leader_name": "高橋", "ext": "", "outside": "03-0000-0002"},
        {"company": "3班", "leader_name": "鈴木", "ext": "1235", "outside": ""},
    ]
    assert [w for w in data["warnings"] if ".csv" in w] == []


def test_header_only_file_is_a_company_without_leaders(tmp_path):
    company(tmp_path, "山田", "責任者,内線,外線\n")
    company(tmp_path, "見本", "責任者,内線,外線")  # 末尾の改行なし
    data = load(tmp_path)
    assert data["companies"] == ["山田", "見本"]
    assert data["leaders"] == []
    assert [w for w in data["warnings"] if ".csv" in w] == []


def test_rows_without_a_leader_name_and_short_rows(tmp_path):
    company(tmp_path, "1班", "責任者,内線,外線\n\n,1234,03-0000-0001\n  ,,\n佐藤\n鈴木,1235\n")
    data = load(tmp_path)
    assert data["leaders"] == [
        {"company": "1班", "leader_name": "佐藤", "ext": "", "outside": ""},
        {"company": "1班", "leader_name": "鈴木", "ext": "1235", "outside": ""},
    ]
    assert [w for w in data["warnings"] if ".csv" in w] == []  # 責任者が空の行は、黙って飛ばす


def test_empty_file_and_missing_leader_column_warn_and_are_skipped(tmp_path):
    company(tmp_path, "1班", "責任者\n佐藤\n")
    (tmp_path / "companies" / "空.csv").write_bytes(b"")
    company(tmp_path, "列なし", "名前,内線\n佐藤,1234\n")
    data = load(tmp_path)
    assert data["companies"] == ["1班"]
    warns = [w for w in data["warnings"] if ".csv" in w]
    assert len(warns) == 2
    assert any("空.csv" in w for w in warns)
    assert any("列なし.csv" in w and "責任者" in w for w in warns)


def test_non_utf8_file_is_skipped_with_one_warning(tmp_path):
    company(tmp_path, "1班", "責任者\n佐藤\n")
    company(tmp_path, "2班", "責任者\n山田\n", "cp932")
    data = load(tmp_path)
    assert data["companies"] == ["1班"]
    assert data["leaders"] == [{"company": "1班", "leader_name": "佐藤", "ext": "", "outside": ""}]
    warns = [w for w in data["warnings"] if ".csv" in w]
    assert len(warns) == 1
    assert "2班.csv を読めません" in warns[0] and DECODE_HINT in warns[0] and "codec" not in warns[0]


def test_duplicate_leader_in_one_company_keeps_the_first_with_one_combined_warning(tmp_path):
    company(tmp_path, "1班", "責任者,内線\n佐藤,1111\n鈴木,1235\n佐藤,9999\n")
    company(tmp_path, "2班", "責任者,内線\n高橋,1240\n高橋,1241\n")
    company(tmp_path, "3班", "責任者,内線\n佐藤,3333\n")  # 別の会社に同じ名前があるのは重複ではない
    data = load(tmp_path)
    assert [(l["company"], l["leader_name"], l["ext"]) for l in data["leaders"]] == [
        ("1班", "佐藤", "1111"),
        ("1班", "鈴木", "1235"),
        ("2班", "高橋", "1240"),
        ("3班", "佐藤", "3333"),
    ]
    warns = [w for w in data["warnings"] if "companies" in w]
    assert len(warns) == 1
    assert "1班.csv" in warns[0] and "佐藤" in warns[0]  # 最初の例


def test_missing_companies_folder_gives_empty_list_and_one_warning(tmp_path):
    data = load(tmp_path)
    assert data["companies"] == [] and data["leaders"] == []
    assert [w for w in data["warnings"] if "data/companies" in w] == ["data/companies フォルダがありません"]


def test_old_companies_file_next_to_the_folder_is_ignored(tmp_path):
    put(tmp_path / "companies.csv", "name\n旧会社\n")
    put(tmp_path / "leaders.csv", "company,leader_name,ext,outside\n旧会社,旧人,1,\n")
    company(tmp_path, "1班", "責任者\n佐藤\n")
    data = load(tmp_path)
    assert data["companies"] == ["1班"]
    assert [l["leader_name"] for l in data["leaders"]] == ["佐藤"]


# ---- 工事件名（data/constructions/*.csv） ----
def test_construction_names_are_the_file_names_in_natural_order(tmp_path):
    for name in ["10工区", "2工区", "配管工事", "1工区", "Ab", "aC"]:
        construction(tmp_path, name, "作業内容\n")
    data = load(tmp_path)
    assert data["constructions"] == ["1工区", "2工区", "10工区", "Ab", "aC", "配管工事"]


def test_works_of_a_construction_and_the_union(tmp_path):
    construction(tmp_path, "電気工事", "作業内容\n配線工事\nメンテナンス作業\n")
    construction(tmp_path, "配管工事", "作業内容\r\n組み立て作業\r\n搬入作業\r\nメンテナンス作業\r\n")
    construction(tmp_path, "足場工事", "name\n高所作業\n搬入作業\n")  # 英語の見出し（旧）でもよい
    data = load(tmp_path)
    assert data["constructions"] == ["足場工事", "配管工事", "電気工事"]
    assert data["construction_works"] == {
        "足場工事": ["高所作業", "搬入作業"],
        "配管工事": ["組み立て作業", "搬入作業", "メンテナンス作業"],
        "電気工事": ["配線工事", "メンテナンス作業"],
    }
    # 作業内容の全体 = 工事件名のファイルの順、行の順に並べ、重なりは最初の1つだけ
    assert data["works"] == ["高所作業", "搬入作業", "組み立て作業", "メンテナンス作業", "配線工事"]
    assert list(data["construction_works"]) == ["足場工事", "配管工事", "電気工事"]
    assert [w for w in data["warnings"] if ".csv" in w] == []


def test_construction_without_works_is_listed_but_has_no_entry(tmp_path):
    construction(tmp_path, "塗装工事", "作業内容\n")
    construction(tmp_path, "電気工事", "作業内容\n配線工事\n")
    data = load(tmp_path)
    assert data["constructions"] == ["塗装工事", "電気工事"]
    assert data["construction_works"] == {"電気工事": ["配線工事"]}
    assert data["works"] == ["配線工事"]
    assert [w for w in data["warnings"] if ".csv" in w] == []


def test_construction_file_variants_and_blank_rows(tmp_path):
    construction(tmp_path, "A", "作業内容\r\n 清掃 \r\n\r\n  \r\n搬入作業\r\n")
    put(tmp_path / "constructions" / "B.csv", "作業内容,備考\n配線工事,メモ\n", "utf-8")  # BOM なし・知らない列
    data = load(tmp_path)
    assert data["construction_works"] == {"A": ["清掃", "搬入作業"], "B": ["配線工事"]}
    assert [w for w in data["warnings"] if ".csv" in w] == []


def test_ignored_names_in_the_constructions_folder(tmp_path):
    construction(tmp_path, "配管工事", "作業内容\n清掃\n")
    for bad in ["~$配管工事.csv", ".x.csv", "_雛形.csv", "memo.txt", "メモ"]:
        put(tmp_path / "constructions" / bad, "作業内容\n誰か\n")
    (tmp_path / "constructions" / "dir.csv").mkdir()
    data = load(tmp_path)
    assert data["constructions"] == ["配管工事"]
    assert data["works"] == ["清掃"]


def test_duplicate_work_in_one_construction_keeps_the_first_with_one_combined_warning(tmp_path):
    construction(tmp_path, "配管工事", "作業内容\n清掃\n搬入作業\n清掃\n")
    construction(tmp_path, "電気工事", "作業内容\n配線工事\n配線工事\n")
    data = load(tmp_path)
    assert data["construction_works"] == {"配管工事": ["清掃", "搬入作業"], "電気工事": ["配線工事"]}
    warns = [w for w in data["warnings"] if "constructions" in w]
    assert len(warns) == 1 and "配管工事.csv" in warns[0] and "清掃" in warns[0]


def test_same_work_in_two_constructions_is_not_a_duplicate(tmp_path):
    construction(tmp_path, "配管工事", "作業内容\n清掃\n")
    construction(tmp_path, "電気工事", "作業内容\n清掃\n")
    data = load(tmp_path)
    assert data["works"] == ["清掃"]
    assert [w for w in data["warnings"] if "constructions" in w] == []


def test_construction_empty_missing_column_and_non_utf8_warn_and_are_skipped(tmp_path):
    construction(tmp_path, "電気工事", "作業内容\n配線工事\n")
    (tmp_path / "constructions" / "空.csv").write_bytes(b"")
    construction(tmp_path, "列なし", "名前,備考\n清掃,x\n")
    construction(tmp_path, "文字コード", "作業内容\n清掃\n", "cp932")
    data = load(tmp_path)
    assert data["constructions"] == ["電気工事"]
    assert data["works"] == ["配線工事"]
    warns = [w for w in data["warnings"] if ".csv" in w]
    assert len(warns) == 3
    assert any("空.csv" in w for w in warns)
    assert any("列なし.csv" in w and "作業内容" in w for w in warns)
    assert any("文字コード.csv を読めません" in w and DECODE_HINT in w and "codec" not in w for w in warns)


def test_missing_constructions_folder_gives_empty_lists_and_one_warning(tmp_path):
    data = load(tmp_path)
    assert data["constructions"] == [] and data["works"] == [] and data["construction_works"] == {}
    assert [w for w in data["warnings"] if "data/constructions" in w] == ["data/constructions フォルダがありません"]


def test_old_files_are_ignored_and_never_warned_about(tmp_path):
    put(tmp_path / "works.csv", "name\n旧作業\n")
    put(tmp_path / "constructions.csv", "name\n旧工事\n")
    put(tmp_path / "construction_works.csv", "construction,work\n旧工事,旧作業\n")
    construction(tmp_path, "配管工事", "作業内容\n清掃\n")
    company(tmp_path, "1班", "責任者\n")
    data = load(tmp_path)
    assert data["constructions"] == ["配管工事"] and data["works"] == ["清掃"] and data["construction_works"] == {"配管工事": ["清掃"]}
    assert [w for w in data["warnings"] if "works.csv" in w or "constructions.csv" in w or "companies.csv" in w] == []


def test_load_all_keeps_its_keys(tmp_path):
    data = load(tmp_path)
    assert set(data) == {"companies", "leaders", "works", "constructions", "construction_works", "genres", "times", "equipment", "custom_holidays", "warnings"}


# ---- signature ----
def folder_files(tmp_path):
    company(tmp_path, "1班", "責任者\n佐藤\n")
    construction(tmp_path, "配管工事", "作業内容\n清掃\n")


def bump(p, seconds=10):
    later = p.stat().st_mtime + seconds
    os.utime(p, (later, later))


def test_signature_changes_when_a_company_file_is_added_removed_renamed_or_edited(tmp_path):
    folder_files(tmp_path)
    mm = m.Masters(tmp_path)
    s0 = mm.signature()
    company(tmp_path, "2班", "責任者\n高橋\n")
    s1 = mm.signature()
    assert s1 != s0
    p = tmp_path / "companies" / "2班.csv"
    p.rename(tmp_path / "companies" / "3班.csv")
    s2 = mm.signature()
    assert s2 != s1
    company(tmp_path, "3班", "責任者\n高橋\n鈴木\n")
    s3 = mm.signature()
    assert s3 != s2
    (tmp_path / "companies" / "3班.csv").unlink()
    assert mm.signature() == s0


def test_signature_changes_when_a_construction_file_is_added_removed_renamed_or_edited(tmp_path):
    folder_files(tmp_path)
    mm = m.Masters(tmp_path)
    s0 = mm.signature()
    construction(tmp_path, "電気工事", "作業内容\n配線工事\n")
    s1 = mm.signature()
    assert s1 != s0
    (tmp_path / "constructions" / "電気工事.csv").rename(tmp_path / "constructions" / "電気.csv")
    s2 = mm.signature()
    assert s2 != s1
    construction(tmp_path, "電気", "作業内容\n配線工事\n清掃\n")
    assert mm.signature() != s2
    (tmp_path / "constructions" / "電気.csv").unlink()
    assert mm.signature() == s0


def test_signature_notices_an_edit_with_the_same_mtime_or_the_same_size(tmp_path):
    folder_files(tmp_path)
    mm = m.Masters(tmp_path)
    p = tmp_path / "companies" / "1班.csv"
    st = p.stat()
    s0 = mm.signature()
    company(tmp_path, "1班", "責任者\n佐藤\n鈴木\n")  # 大きさが変わる。更新日時は元に戻す（Excel の上書きなど）
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))
    s1 = mm.signature()
    assert s1 != s0
    company(tmp_path, "1班", "責任者\n鈴木\n佐藤\n")  # 大きさは同じ。更新日時だけ変わる
    bump(p)
    assert mm.signature() != s1


def test_signature_ignores_files_that_are_not_used(tmp_path):
    folder_files(tmp_path)
    mm = m.Masters(tmp_path)
    s0 = mm.signature()
    put(tmp_path / "companies" / "~$1班.csv", "x")
    put(tmp_path / "companies" / "_雛形.csv", "x")
    put(tmp_path / "constructions" / "memo.txt", "x")
    (tmp_path / "constructions" / "dir.csv").mkdir()
    assert mm.signature() == s0


def test_signature_of_missing_folders_is_stable_and_changes_when_they_appear(tmp_path):
    mm = m.Masters(tmp_path)
    s0 = mm.signature()
    assert mm.signature() == s0
    company(tmp_path, "1班", "責任者\n")
    assert mm.signature() != s0


def test_signature_stays_short(tmp_path):
    for i in range(300):
        company(tmp_path, f"会社{i}", "責任者\n")
    assert len(m.Masters(tmp_path).signature()) < 200  # 3秒ごとに全画面が送り返す文字列なので、ファイル名を並べない


# ---- 一覧の確認は約2秒に1回 ----
@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(m, "_clock", lambda: now[0])
    monkeypatch.setattr(m, "SCAN_TTL", 2)
    return now


@pytest.fixture
def scans(monkeypatch):
    """登録フォルダを走査した回数。"""
    calls = []
    real = m.os.scandir

    def spy(path=".", *a, **k):
        if Path(path).name in ("companies", "constructions"):
            calls.append(Path(path).name)
        return real(path, *a, **k)

    monkeypatch.setattr(m.os, "scandir", spy)
    return calls


def test_default_scan_interval_is_two_seconds():
    # conftest が試験中は 0 にしているので、本番の値はソースで確かめる
    assert re.search(r"^SCAN_TTL = 2\b", Path(m.__file__).read_text(encoding="utf-8"), re.M)


def test_folder_listing_is_scanned_once_per_two_seconds(tmp_path, clock, scans):
    folder_files(tmp_path)
    mm = m.Masters(tmp_path)
    first = mm.signature()
    n = len(scans)
    assert n == 2  # 会社と工事件名のフォルダを1回ずつ
    for _ in range(4):  # 3秒ごとの確認が複数の画面から続いても、2秒たつまでは走査しない
        clock[0] += 0.4
        assert mm.signature() == first
    assert len(scans) == n
    company(tmp_path, "2班", "責任者\n")
    clock[0] = 1000.0 + 1.9
    assert mm.signature() == first  # まだキャッシュの中
    clock[0] = 1000.0 + 2.0
    assert mm.signature() != first  # 2秒たったので、追加に気づく
    assert len(scans) == n + 2


def test_load_all_always_reads_the_folders_fresh(tmp_path, clock):
    folder_files(tmp_path)
    mm = m.Masters(tmp_path)
    mm.signature()
    company(tmp_path, "2班", "責任者\n")
    assert mm.load_all()["companies"] == ["1班", "2班"]  # 書き込み後の検証用。キャッシュは signature だけ


def test_other_signature_parts_are_not_delayed_by_the_scan_cache(tmp_path, clock):
    folder_files(tmp_path)
    mm = m.Masters(tmp_path)
    s0 = mm.signature()
    put(tmp_path / "genres.csv", "name\n溶接作業\n")
    assert mm.signature() != s0


# ---- リポジトリ同梱の見本データ ----
def copy_repo_data(tmp_path):
    dst = tmp_path / "data"
    dst.mkdir()
    for f in (ROOT / "data").glob("*.csv"):
        shutil.copy(f, dst / f.name)
    for d in ("companies", "constructions"):
        shutil.copytree(ROOT / "data" / d, dst / d)
    return dst


def test_sample_data_loads_without_warnings(tmp_path):
    data = m.Masters(copy_repo_data(tmp_path)).load_all()
    assert data["warnings"] == []
    assert data["companies"] == ["1班", "2班", "サンプル建設", "山田", "見本電機"]
    assert data["leaders"] == [
        {"company": "1班", "leader_name": "佐藤", "ext": "1234", "outside": ""},
        {"company": "1班", "leader_name": "鈴木", "ext": "1235", "outside": ""},
        {"company": "2班", "leader_name": "高橋", "ext": "1240", "outside": ""},
        {"company": "サンプル建設", "leader_name": "伊藤", "ext": "3456", "outside": ""},
        {"company": "見本電機", "leader_name": "田中", "ext": "", "outside": "03-0000-0001"},
        {"company": "見本電機", "leader_name": "小林", "ext": "2345", "outside": "03-0000-0002"},
    ]
    assert data["constructions"] == ["塗装工事", "設備据付工事", "足場工事", "配管工事", "電気工事"]
    assert data["construction_works"] == {
        "配管工事": ["組み立て作業", "搬入作業", "メンテナンス作業"],
        "電気工事": ["配線工事", "メンテナンス作業"],
        "塗装工事": ["メンテナンス作業", "清掃"],
        "足場工事": ["高所作業", "搬入作業", "組み立て作業"],
        "設備据付工事": ["溶接作業", "組み立て作業", "搬入作業", "高所作業"],
    }
    assert data["works"] == ["メンテナンス作業", "清掃", "溶接作業", "組み立て作業", "搬入作業", "高所作業", "配線工事"]
    assert data["genres"] == ["溶接作業", "高所作業", "電気配線", "その他"]
    assert set(data["construction_works"]) == set(data["constructions"])


def test_sample_files_are_bom_utf8_with_lf_and_templates_are_ignored(tmp_path):
    files = sorted(p for d in ("companies", "constructions") for p in (ROOT / "data" / d).iterdir())
    assert {p.name for p in files if p.parent.name == "companies"} == {"1班.csv", "2班.csv", "見本電機.csv", "サンプル建設.csv", "山田.csv", "_雛形.csv"}
    assert {p.name for p in files if p.parent.name == "constructions"} == {"配管工事.csv", "電気工事.csv", "塗装工事.csv", "足場工事.csv", "設備据付工事.csv", "_雛形.csv"}
    for p in files:
        raw = p.read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw, p
    assert (ROOT / "data" / "companies" / "_雛形.csv").read_text(encoding="utf-8-sig") == "責任者,内線,外線\n（責任者の名前）,（内線）,（外線）\n"
    assert (ROOT / "data" / "constructions" / "_雛形.csv").read_text(encoding="utf-8-sig") == "作業内容\n（作業内容の名前）\n"
    assert (ROOT / "data" / "companies" / "山田.csv").read_text(encoding="utf-8-sig") == "責任者,内線,外線\n"
    assert (ROOT / "data" / "companies" / "1班.csv").read_text(encoding="utf-8-sig") == "責任者,内線,外線\n佐藤,1234,\n鈴木,1235,\n"
