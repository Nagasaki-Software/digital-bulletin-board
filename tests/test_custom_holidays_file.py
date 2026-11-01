import json
import os
from datetime import date

import pytest

import masters as m
from app import create_app
from config import DEFAULTS, MAX_PATH, clean_admin_settings, load_config

DOCS = {"buttons": [{"label": "文書", "folder": "documents/doc1"}]}
# equipment-inspection の data/custom_holidays.csv と同じ形: BOM・CRLF・Excel の日付（2026/12/29, 2026-1-5）
CRLF = "\ufeffdate,name\r\n2026-11-05,創立記念日\r\n2026/11/06,工場メンテ\r\n2027-1-5,新年休業\r\n".encode("utf-8")


def make(tmp_path, config=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    if config is not None:
        (tmp_path / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=1), encoding="utf-8")
    return create_app(tmp_path, today_func=lambda: date(2026, 11, 2)).test_client()


def post(c, **extra):
    return c.post("/api/admin-settings", json={"documents": DOCS, "telop": {"speed": 100}, **extra})


def mine(warnings):
    """会社の休日ファイルに関する警告だけ（空の一時フォルダでは、他のマスターCSVが無い警告も出るので除く）。"""
    return [w for w in warnings if "休日" in w or "custom_holidays" in w]


def labels(c):
    return [w["label"] for w in c.get("/api/board").get_json()["week_holidays"]]


def rev(c):
    return c.get("/api/rev").get_json()["rev"]


def shared_file(tmp_path, data=CRLF):
    p = tmp_path / "shared" / "custom_holidays.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


@pytest.fixture(autouse=True)
def _no_holiday_stat_cache(monkeypatch):
    monkeypatch.setattr(m, "HOLIDAY_STAT_TTL", 0)  # 以下の多くは、ファイルを直したらすぐ画面に出ることを確かめる。キャッシュの試験は下で時計つきで行う


def test_default_key():
    assert DEFAULTS["custom_holidays_file"] == "data/custom_holidays.csv"
    assert load_config("nonexistent.json")["custom_holidays_file"] == "data/custom_holidays.csv"


# ---- masters ----
def test_crlf_excel_file_is_read(tmp_path):
    p = shared_file(tmp_path)
    custom, warns = m.load_custom_holidays(tmp_path, p)
    assert warns == []
    assert custom == {"2026-11-05": "創立記念日", "2026-11-06": "工場メンテ", "2027-01-05": "新年休業"}


def test_masters_uses_the_given_file_and_signature_follows_its_mtime_and_size(tmp_path):
    p = shared_file(tmp_path)
    mm = m.Masters(tmp_path / "data", holidays_source=lambda: (p, None))
    assert mm.load_all()["custom_holidays"]["2026-11-05"] == "創立記念日"
    before = mm.signature()
    st = p.stat()
    p.write_bytes(CRLF + "2026-11-07,追加\r\n".encode("utf-8"))
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))  # 更新日時が同じでも、大きさで変わる
    assert mm.signature() != before
    mid = mm.signature()
    later = p.stat().st_mtime + 10
    os.utime(p, (later, later))
    assert mm.signature() != mid
    assert mm.signature() == mm.signature()


def test_masters_default_file_stays_in_data_dir(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "custom_holidays.csv").write_bytes(CRLF)
    mm = m.Masters(tmp_path / "data")
    assert mm.load_all()["custom_holidays"]["2026-11-06"] == "工場メンテ"
    assert mine(mm.load_all()["warnings"]) == []


def test_missing_configured_file_gives_exactly_one_clear_warning(tmp_path):
    p = tmp_path / "nowhere" / "custom_holidays.csv"
    mm = m.Masters(tmp_path / "data", holidays_source=lambda: (p, "D:/共有/custom_holidays.csv"))
    d = mm.load_all()
    assert d["custom_holidays"] == {}
    assert mine(d["warnings"]) == ["会社の休日ファイル（D:/共有/custom_holidays.csv）が見つかりません"]
    assert mine(mm.load_all()["warnings"]) == mine(d["warnings"])  # 呼ぶたびに増えない
    assert mm.signature()  # 落ちない
    assert not p.exists() and not p.parent.exists()  # 読むだけ。作らない


def test_missing_default_file_is_silent(tmp_path):
    mm = m.Masters(tmp_path / "data", holidays_source=lambda: (tmp_path / "data" / "custom_holidays.csv", None))
    assert mine(mm.load_all()["warnings"]) == []


def test_undecodable_file_warns_with_existing_wording_and_does_not_crash(tmp_path):
    p = shared_file(tmp_path, "date,name\r\n2026-11-05,創立記念日\r\n".encode("cp932"))
    mm = m.Masters(tmp_path / "data", holidays_source=lambda: (p, "shared/custom_holidays.csv"))
    d = mm.load_all()
    assert d["custom_holidays"] == {}
    w = mine(d["warnings"])
    assert len(w) == 1 and "custom_holidays.csv を読めません" in w[0] and "CSV UTF-8" in w[0]


def test_directory_given_as_file_does_not_crash(tmp_path):
    (tmp_path / "adir").mkdir()
    mm = m.Masters(tmp_path / "data", holidays_source=lambda: (tmp_path / "adir", "adir"))
    d = mm.load_all()
    assert d["custom_holidays"] == {} and len([w for w in d["warnings"] if "adir" in w]) == 1


# ---- config.json ----
@pytest.mark.parametrize("bad", ["../x.csv", "a/../b.csv", "a\\..\\b.csv", "..", "x" * 261, "a\0b", "", "  ", 5, None, ["a"], True])
def test_bad_config_value_falls_back_with_warning(tmp_path, bad):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"custom_holidays_file": bad}), encoding="utf-8")
    cfg = load_config(p)
    assert cfg["custom_holidays_file"] == "data/custom_holidays.csv"
    assert cfg["_warnings"] == ["config.json の custom_holidays_file が正しくありません（data/custom_holidays.csvを使います）"]


def test_config_values_accepted(tmp_path):
    for good in ["data/other.csv", "D:/共有/休日.csv", "//server/share/data/custom_holidays.csv", "x" * MAX_PATH, "a..b/c.csv"]:
        p = tmp_path / "config.json"
        p.write_text(json.dumps({"custom_holidays_file": good}), encoding="utf-8")
        cfg = load_config(p)
        assert cfg["custom_holidays_file"] == good and cfg["_warnings"] == []


# ---- app ----
def test_default_location_still_works(tmp_path):
    c = make(tmp_path)
    (tmp_path / "data" / "custom_holidays.csv").write_bytes(CRLF)
    assert "11/5(木・創立記念日)" in labels(c)
    assert c.get("/api/admin-settings").get_json()["custom_holidays_file"] == "data/custom_holidays.csv"


def test_shared_absolute_path_is_used_for_week_holidays_and_edits_refresh_screens(tmp_path):
    p = shared_file(tmp_path)
    c = make(tmp_path / "app", {"custom_holidays_file": str(p)})
    b = c.get("/api/board").get_json()
    assert [w["label"] for w in b["week_holidays"]] == ["11/3(火・文化の日)", "11/5(木・創立記念日)", "11/6(金・工場メンテ)", "11/7(土)", "11/8(日)"]
    assert mine(b["warnings"]) == []
    assert c.post("/api/holiday-rows", json={"date": "2026-11-05"}).status_code == 200  # 共有ファイルの休日を選べる
    r1 = rev(c)
    p.write_bytes(CRLF.replace("創立記念日".encode(), "創立記念".encode()))  # Excel で直した
    assert rev(c) != r1
    assert "11/5(木・創立記念)" in labels(c)
    rows = [r for r in c.get("/api/board").get_json()["holiday_rows"] if r["date"] == "2026-11-05"]
    assert [r["label"] for r in rows] == ["11/5(木・創立記念)"] * 2  # 最初から作られた行と、上で足した行


def test_missing_configured_file_shows_one_banner_warning_and_falls_back_to_jpholiday(tmp_path):
    missing = str(tmp_path / "gone" / "custom_holidays.csv")
    c = make(tmp_path / "app", {"custom_holidays_file": missing})
    for _ in range(3):
        b = c.get("/api/board").get_json()
        assert mine(b["warnings"]) == [f"会社の休日ファイル（{missing}）が見つかりません"]
    assert labels(c) == ["11/3(火・文化の日)", "11/7(土)", "11/8(日)"]
    assert c.get("/api/rev").status_code == 200
    assert not (tmp_path / "gone").exists()


def test_the_app_never_writes_the_holiday_file(tmp_path):
    p = shared_file(tmp_path)
    st = p.stat()
    c = make(tmp_path / "app", {"custom_holidays_file": str(p)})
    c.get("/api/board")
    c.get("/api/rev")
    post(c, custom_holidays_file=str(p))
    assert p.read_bytes() == CRLF and p.stat().st_mtime_ns == st.st_mtime_ns
    assert sorted(f.name for f in p.parent.iterdir()) == ["custom_holidays.csv"]


def test_post_changes_file_without_restart(tmp_path):
    p = shared_file(tmp_path)
    c = make(tmp_path / "app")
    assert "11/5(木・創立記念日)" not in labels(c)
    r0 = rev(c)
    res = post(c, custom_holidays_file=f"  {p}  ")
    assert res.status_code == 200 and res.get_json() == {"ok": True}
    assert rev(c) != r0
    assert "11/5(木・創立記念日)" in labels(c)
    assert c.get("/api/admin-settings").get_json()["custom_holidays_file"] == str(p)
    saved = json.loads((tmp_path / "app" / "config.json").read_text(encoding="utf-8"))
    assert saved["custom_holidays_file"] == str(p)
    # 元の場所（data/）に戻す: 空欄 = 既定
    assert post(c, custom_holidays_file="").status_code == 200
    assert c.get("/api/admin-settings").get_json()["custom_holidays_file"] == "data/custom_holidays.csv"
    assert "11/5(木・創立記念日)" not in labels(c)


def test_post_relative_path_is_from_the_app_folder_and_missing_file_warns_on_screen(tmp_path):
    c = make(tmp_path)
    assert post(c, custom_holidays_file="shared/休日.csv").status_code == 200
    b = c.get("/api/board").get_json()
    assert mine(b["warnings"]) == ["会社の休日ファイル（shared/休日.csv）が見つかりません"]
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "休日.csv").write_bytes(CRLF)
    assert "11/5(木・創立記念日)" in labels(c)
    assert mine(c.get("/api/board").get_json()["warnings"]) == []


def test_post_without_the_field_keeps_it(tmp_path):
    p = shared_file(tmp_path)
    c = make(tmp_path / "app", {"custom_holidays_file": str(p)})
    assert post(c).status_code == 200
    assert c.get("/api/admin-settings").get_json()["custom_holidays_file"] == str(p)
    assert json.loads((tmp_path / "app" / "config.json").read_text(encoding="utf-8"))["custom_holidays_file"] == str(p)


@pytest.mark.parametrize("bad", ["..", "../x.csv", "a/../b.csv", "a\\..\\b.csv", "//server/share/../x.csv", "bad\0name", "x" * 261, 5, None, ["a"], {"a": 1}, True])
def test_invalid_value_is_400_and_saves_nothing(tmp_path, bad):
    c = make(tmp_path, {"company_name": "元のまま", "custom_holidays_file": "keep.csv"})
    before = (tmp_path / "config.json").read_bytes()
    names = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if "logs" not in p.parts)
    r0 = rev(c)
    res = post(c, custom_holidays_file=bad)
    assert res.status_code == 400
    assert "会社の休日ファイル" in res.get_json()["error"]
    assert (tmp_path / "config.json").read_bytes() == before
    assert sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if "logs" not in p.parts) == names
    assert rev(c) == r0
    assert c.get("/api/admin-settings").get_json()["custom_holidays_file"] == "keep.csv"


def test_260_chars_ok_261_rejected_in_validator():
    base = {"documents": DOCS, "telop": {"speed": 100}}
    assert clean_admin_settings({**base, "custom_holidays_file": "a" * 260})["custom_holidays_file"] == "a" * 260
    with pytest.raises(ValueError, match="260文字以内"):
        clean_admin_settings({**base, "custom_holidays_file": "a" * 261})
    assert clean_admin_settings({**base, "custom_holidays_file": "  "})["custom_holidays_file"] == "data/custom_holidays.csv"
    assert "custom_holidays_file" not in clean_admin_settings(base)


# ---- 休日ファイルの更新確認は10秒に1回まで（共有フォルダが応答しなくても、3秒ごとの確認を止めない） ----

@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(m, "_clock", lambda: now[0])
    monkeypatch.setattr(m, "HOLIDAY_STAT_TTL", 10)
    return now


@pytest.fixture
def stat_calls(monkeypatch):
    """Path.stat が呼ばれたパスを記録する。"""
    calls = []
    real = m.Path.stat

    def spy(self, *a, **k):
        calls.append(self)
        return real(self, *a, **k)

    monkeypatch.setattr(m.Path, "stat", spy)
    return calls


def test_holiday_file_is_checked_once_per_ten_seconds(tmp_path, clock, stat_calls):
    p = shared_file(tmp_path)
    mm = m.Masters(tmp_path / "data", holidays_source=lambda: (p, None))
    first = mm.signature()
    n = stat_calls.count(p)
    assert n == 1
    for _ in range(20):  # 3秒ごとの確認が続いても、10秒たつまでは共有フォルダに問い合わせない
        clock[0] += 0.4
        assert mm.signature() == first
    assert stat_calls.count(p) == n
    p.write_bytes(CRLF + "2026-11-07,追加\r\n".encode("utf-8"))
    clock[0] = 1000.0 + 9.9
    assert mm.signature() == first  # まだキャッシュの中
    clock[0] = 1000.0 + 10.0
    assert mm.signature() != first  # 10秒たったので、変更に気づく
    assert stat_calls.count(p) == n + 1


def test_other_master_files_are_not_cached(tmp_path, clock):
    (tmp_path / "data").mkdir()
    p = shared_file(tmp_path)
    mm = m.Masters(tmp_path / "data", holidays_source=lambda: (p, None))
    before = mm.signature()
    (tmp_path / "data" / "companies.csv").write_text("name\nA社\n", encoding="utf-8")
    assert mm.signature() != before  # 会社の一覧などは、いままでどおり毎回見る


def test_changing_the_configured_path_drops_the_cache(tmp_path, clock, stat_calls):
    a = shared_file(tmp_path)
    b = tmp_path / "other" / "custom_holidays.csv"
    b.parent.mkdir()
    b.write_bytes(CRLF + b"2026-11-09,x\r\n")
    current = [a]
    mm = m.Masters(tmp_path / "data", holidays_source=lambda: (current[0], None))
    sig_a = mm.signature()
    current[0] = b
    clock[0] += 1  # 10秒たっていなくても
    sig_b = mm.signature()
    assert sig_b != sig_a and stat_calls.count(b) == 1
    current[0] = a
    assert mm.signature() == sig_a and stat_calls.count(a) == 2  # 戻したときも、古い別の場所の値を使わない


def test_a_missing_file_that_appears_is_noticed_after_the_ten_seconds(tmp_path, clock):
    p = tmp_path / "shared" / "custom_holidays.csv"
    mm = m.Masters(tmp_path / "data", holidays_source=lambda: (p, None))
    before = mm.signature()
    shared_file(tmp_path)
    assert mm.signature() == before
    clock[0] += 10
    assert mm.signature() != before


def test_default_source_without_holidays_source_also_works(tmp_path, clock):
    (tmp_path / "data").mkdir()
    mm = m.Masters(tmp_path / "data")
    assert mm.signature() == mm.signature()
