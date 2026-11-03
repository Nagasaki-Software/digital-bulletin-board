import base64
import json
import re
from datetime import date

from app import create_app
from test_whiteboard import fake_jpeg


def make(tmp_path, config=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    if config is not None:
        (tmp_path / "config.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return create_app(tmp_path, today_func=lambda: date(2026, 11, 2)).test_client()


def payload(**extra):
    return {"image": base64.b64encode(fake_jpeg()).decode(), **extra}


def test_pdf_list_and_file_only_from_the_folder(tmp_path):
    c = make(tmp_path)
    assert c.get("/api/whiteboard/pdfs").get_json() == []
    folder = tmp_path / "whiteboard_pdfs"
    (folder / "10_ひな形.pdf").write_bytes(b"%PDF-1.4 ten")
    (folder / "2_ひな形.pdf").write_bytes(b"%PDF-1.4 two")
    (folder / "memo.txt").write_text("x", encoding="utf-8")
    (folder / "sub").mkdir()
    (folder / "sub" / "x.pdf").write_bytes(b"%PDF-1.4 sub")
    assert c.get("/api/whiteboard/pdfs").get_json() == ["2_ひな形.pdf", "10_ひな形.pdf"]
    assert c.get("/api/whiteboard/pdf/2_ひな形.pdf").data == b"%PDF-1.4 two"
    for name in ("sub/x.pdf", "../config.json", "..%5Cconfig.json", "memo.txt", "none.pdf"):
        assert c.get("/api/whiteboard/pdf/" + name).status_code == 404, name


def test_save_writes_pdf_into_the_configured_folder(tmp_path):
    out = tmp_path / "出力"
    c = make(tmp_path, {"whiteboard_save_folder": str(out)})
    r = c.post("/api/whiteboard/save", json=payload())
    assert r.status_code == 200
    name = r.get_json()["name"]
    assert re.fullmatch(r"\d{4}-\d\d-\d\d_\d\d-\d\d-\d\d\.pdf", name)
    assert (out / name).read_bytes().startswith(b"%PDF-1.4")
    auto = c.post("/api/whiteboard/save", json=payload(auto=True)).get_json()["name"]
    assert auto.endswith("_自動保存.pdf") and (out / auto).is_file()


def test_save_default_folder_is_relative_to_the_app(tmp_path):
    c = make(tmp_path)
    name = c.post("/api/whiteboard/save", json=payload()).get_json()["name"]
    assert (tmp_path / "whiteboard" / name).is_file()


def test_save_rejects_bad_images_without_making_the_folder(tmp_path):
    c = make(tmp_path)
    for body in (None, {}, {"image": ""}, {"image": "***"}, {"image": base64.b64encode(b"hello").decode()}, payload(auto="yes"), []):
        r = c.post("/api/whiteboard/save", json=body)
        assert r.status_code == 400, body
        assert "error" in r.get_json()
    assert not (tmp_path / "whiteboard").exists()


def test_save_reports_a_write_failure_and_keeps_the_app_alive(tmp_path):
    blocker = tmp_path / "ふさがれた場所"
    blocker.write_text("x", encoding="utf-8")  # フォルダの場所に同名のファイルがある
    c = make(tmp_path, {"whiteboard_save_folder": str(blocker)})
    r = c.post("/api/whiteboard/save", json=payload())
    assert r.status_code == 500
    assert r.get_json()["error"].startswith("保存先に書き込めませんでした")
    assert c.get("/api/health").status_code == 200


def test_too_large_body_is_413_json(tmp_path):
    c = make(tmp_path)
    r = c.post("/api/whiteboard/save", data=b'{"image": "' + b"A" * (121 * 1024 * 1024) + b'"}', content_type="application/json")
    assert r.status_code == 413
    assert "error" in r.get_json()
    assert not (tmp_path / "whiteboard").exists()


def test_images_listed_and_served_only_from_background_folder(tmp_path):
    c = make(tmp_path)
    assert c.get("/api/whiteboard/images").get_json() == []
    folder = tmp_path / "whiteboard_pdfs"
    (folder / "10_現場.JPG").write_bytes(b"jpg10")
    (folder / "2_現場.png").write_bytes(b"png2")
    (folder / "a.jpeg").write_bytes(b"jpeg")
    (folder / "b.pdf").write_bytes(b"%PDF")
    (folder / "c.txt").write_text("x", encoding="utf-8")
    assert c.get("/api/whiteboard/images").get_json() == ["2_現場.png", "10_現場.JPG", "a.jpeg"]
    assert c.get("/api/whiteboard/image/2_現場.png").data == b"png2"
    for name in ("b.pdf", "c.txt", "../config.json", "none.png"):
        assert c.get("/api/whiteboard/image/" + name).status_code == 404, name


def test_saved_pdfs_newest_first_and_served_from_save_folder(tmp_path):
    out = tmp_path / "出力"
    c = make(tmp_path, {"whiteboard_save_folder": str(out)})
    assert c.get("/api/whiteboard/saved").get_json() == []
    out.mkdir()
    (out / "2026-11-02_09-00-00.pdf").write_bytes(b"%PDF old")
    (out / "2026-11-03_08-00-00_自動保存.pdf").write_bytes(b"%PDF new")
    (out / "memo.txt").write_text("x", encoding="utf-8")
    assert c.get("/api/whiteboard/saved").get_json() == ["2026-11-03_08-00-00_自動保存.pdf", "2026-11-02_09-00-00.pdf"]
    assert c.get("/api/whiteboard/saved/2026-11-02_09-00-00.pdf").data == b"%PDF old"
    for name in ("memo.txt", "../config.json", "none.pdf"):
        assert c.get("/api/whiteboard/saved/" + name).status_code == 404, name


def test_save_many_pages_into_one_pdf(tmp_path):
    c = make(tmp_path)
    img = base64.b64encode(fake_jpeg()).decode()
    r = c.post("/api/whiteboard/save", json={"images": [img, img, img]})
    assert r.status_code == 200
    assert (tmp_path / "whiteboard" / r.get_json()["name"]).read_bytes().count(b"/Type /Page ") == 3
    for bad_body in ({"images": []}, {"images": "x"}, {"images": [img, "***"]}, {"images": [img] * 51}):
        assert c.post("/api/whiteboard/save", json=bad_body).status_code == 400, bad_body


def test_schedule_days_marks_saturdays_sundays_and_holidays(tmp_path):
    c = make(tmp_path)
    (tmp_path / "data" / "custom_holidays.csv").write_text("date,name\n2026-11-05,創立記念日\n", encoding="utf-8-sig")
    days = c.get("/api/whiteboard/schedule-days?start=2026-10-30&end=2026-11-05").get_json()
    assert days == [
        {"date": "2026-10-30", "kind": ""},
        {"date": "2026-10-31", "kind": "saturday"},
        {"date": "2026-11-01", "kind": "holiday"},  # 日曜
        {"date": "2026-11-02", "kind": ""},
        {"date": "2026-11-03", "kind": "holiday"},  # 文化の日
        {"date": "2026-11-04", "kind": ""},
        {"date": "2026-11-05", "kind": "holiday"},  # 会社の休日
    ]


def test_schedule_days_rejects_bad_ranges(tmp_path):
    c = make(tmp_path)
    assert len(c.get("/api/whiteboard/schedule-days?start=2026-11-01&end=2027-01-01").get_json()) == 62
    for q in ("start=2026-11-02&end=2026-11-01", "start=2026-11-01&end=2027-01-02", "start=x&end=2026-11-01", "start=2026-11-01", ""):
        r = c.get("/api/whiteboard/schedule-days?" + q)
        assert r.status_code == 400, q
        assert r.get_json()["error"]
