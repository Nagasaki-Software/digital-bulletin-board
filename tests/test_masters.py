import os
from datetime import date

import masters as m


def write(path, text):
    path.write_text(text, encoding="utf-8-sig")


def test_read_csv_ok_skips_blank_rows(tmp_path):
    p = tmp_path / "a.csv"
    write(p, "name\n1班\n\n見本電機\n")
    rows, warn = m.read_csv(p, ["name"])
    assert [r["name"] for r in rows] == ["1班", "見本電機"]
    assert warn is None


def test_read_csv_missing_file_warns(tmp_path):
    rows, warn = m.read_csv(tmp_path / "x.csv", ["name"])
    assert rows == []
    assert "x.csv" in warn


def test_read_csv_optional_missing_file_is_silent(tmp_path):
    assert m.read_csv(tmp_path / "x.csv", ["name"], required=False) == ([], None)


def test_read_csv_missing_column_warns(tmp_path):
    p = tmp_path / "a.csv"
    write(p, "title\nabc\n")
    rows, warn = m.read_csv(p, ["name"])
    assert rows == []
    assert "name" in warn


def test_read_csv_shift_jis_file_warns_instead_of_crashing(tmp_path):
    p = tmp_path / "a.csv"
    p.write_bytes("name\n山田\n".encode("cp932"))
    rows, warn = m.read_csv(p, ["name"])
    assert rows == []
    assert "a.csv を読めません" in warn
    assert "CSV UTF-8（コンマ区切り）" in warn
    assert "codec" not in warn


def test_default_times():
    times = m.default_times()
    assert times[0] == "6:00" and times[1] == "6:30" and times[-1] == "22:00"
    assert len(times) == 33


def test_load_all_and_times_file_created(tmp_path):
    write(tmp_path / "companies.csv", "name\n1班\n見本電機\n")
    write(tmp_path / "leaders.csv", "company,leader_name,ext,outside\n1班,佐藤,1234,\n")
    write(tmp_path / "works.csv", "name\n配線工事\n")
    write(tmp_path / "genres.csv", "name\n溶接作業\n")
    write(tmp_path / "constructions.csv", "name\n配管工事\n")
    data = m.Masters(tmp_path).load_all()
    assert data["companies"] == ["1班", "見本電機"]
    assert data["constructions"] == ["配管工事"]
    assert data["leaders"] == [{"company": "1班", "leader_name": "佐藤", "ext": "1234", "outside": ""}]
    assert data["works"] == ["配線工事"]
    assert data["genres"] == ["溶接作業"]
    assert data["times"][0] == "6:00"
    assert data["warnings"] == []
    assert (tmp_path / "times.csv").exists()


def test_signature_changes_when_a_file_changes(tmp_path):
    mm = m.Masters(tmp_path)
    before = mm.signature()
    write(tmp_path / "works.csv", "name\n清掃\n")
    assert mm.signature() != before


def test_custom_holidays_skips_bad_dates(tmp_path):
    write(tmp_path / "custom_holidays.csv", "date,name\n2026-12-29,年末休業\nあした,誤り\n")
    custom, warns = m.load_custom_holidays(tmp_path)
    assert custom == {"2026-12-29": "年末休業"}
    assert len(warns) == 1


def test_custom_holidays_accepts_excel_date_formats(tmp_path):
    write(tmp_path / "custom_holidays.csv", "date,name\n2026/12/29,年末休業\n2026-1-5,新年休業\n")
    custom, warns = m.load_custom_holidays(tmp_path)
    assert custom == {"2026-12-29": "年末休業", "2026-01-05": "新年休業"}
    assert warns == []


def test_custom_holidays_found_by_holiday_info(tmp_path):
    write(tmp_path / "custom_holidays.csv", "date,name\n2026/12/29,年末休業\n2026-1-5,新年休業\n")
    custom, _ = m.load_custom_holidays(tmp_path)
    assert m.holiday_info(date(2026, 12, 29), custom) == {"kind": "holiday", "name": "年末休業"}
    assert m.holiday_info(date(2026, 1, 5), custom) == {"kind": "holiday", "name": "新年休業"}


def test_custom_holidays_rejects_invalid_dates_with_warning(tmp_path):
    write(
        tmp_path / "custom_holidays.csv",
        "date,name\n20261229,コンパクト形式\n2026/13/1,存在しない月\n2026/2/30,存在しない日\n",
    )
    custom, warns = m.load_custom_holidays(tmp_path)
    assert custom == {}
    assert len(warns) == 3


def test_read_csv_header_with_spaces_reads(tmp_path):
    p = tmp_path / "a.csv"
    write(p, " name , leader_name \n1班,佐藤\n")
    rows, warn = m.read_csv(p, ["name", "leader_name"])
    assert rows == [{"name": "1班", "leader_name": "佐藤"}]
    assert warn is None


def test_missing_constructions_csv_gives_empty_list_and_warning(tmp_path):
    write(tmp_path / "companies.csv", "name\n1班\n")
    write(tmp_path / "leaders.csv", "company,leader_name,ext,outside\n")
    write(tmp_path / "works.csv", "name\n配線工事\n")
    write(tmp_path / "genres.csv", "name\n溶接作業\n")
    data = m.Masters(tmp_path).load_all()
    assert data["constructions"] == []
    assert data["works"] == ["配線工事"]
    assert data["warnings"] == ["constructions.csv が見つかりません"]


def test_signature_changes_when_constructions_csv_is_edited(tmp_path):
    p = tmp_path / "constructions.csv"
    write(p, "name\n配管工事\n")
    mm = m.Masters(tmp_path)
    before = mm.signature()
    write(p, "name\n配管工事\n電気工事\n")
    later = p.stat().st_mtime + 10
    os.utime(p, (later, later))
    assert mm.signature() != before


def test_signature_changes_when_existing_file_is_modified(tmp_path):
    p = tmp_path / "works.csv"
    write(p, "name\n清掃\n")
    mm = m.Masters(tmp_path)
    before = mm.signature()
    write(p, "name\n清掃\n配線工事\n")
    later = p.stat().st_mtime + 10
    os.utime(p, (later, later))
    assert mm.signature() != before


def test_holiday_info():
    custom = {"2026-11-09": "創立記念日", "2026-11-14": "会社記念日"}
    assert m.holiday_info(date(2026, 11, 3), custom) == {"kind": "holiday", "name": "文化の日"}
    assert m.holiday_info(date(2026, 11, 7), custom) == {"kind": "saturday", "name": ""}
    assert m.holiday_info(date(2026, 11, 8), custom) == {"kind": "holiday", "name": ""}
    assert m.holiday_info(date(2026, 11, 9), custom) == {"kind": "holiday", "name": "創立記念日"}
    assert m.holiday_info(date(2026, 11, 10), custom) == {"kind": "", "name": ""}


def test_saturday_company_holiday_is_red():
    assert m.holiday_info(date(2026, 11, 14), {"2026-11-14": "会社記念日"}) == {
        "kind": "holiday",
        "name": "会社記念日",
    }


def test_week_range_is_monday_to_sunday():
    assert m.week_range(date(2026, 11, 2)) == (date(2026, 11, 2), date(2026, 11, 8))
    assert m.week_range(date(2026, 11, 8)) == (date(2026, 11, 2), date(2026, 11, 8))
    assert m.week_range(date(2026, 11, 9)) == (date(2026, 11, 9), date(2026, 11, 15))


def test_week_holidays_labels():
    result = m.week_holidays(date(2026, 11, 4), {})
    assert [w["label"] for w in result] == ["11/3(火・文化の日)", "11/7(土)", "11/8(日)"]
    assert [w["kind"] for w in result] == ["holiday", "saturday", "holiday"]
    assert result[0]["date"] == "2026-11-03"


def test_day_title():
    assert m.day_title(date(2026, 11, 2)) == "2026年11月2日（月）"
