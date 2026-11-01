import io
import runpy
import shutil
import sys
import urllib.request
from datetime import date
from pathlib import Path

from app import create_app

ROOT = Path(__file__).resolve().parent.parent


def test_seed_demo_works_with_the_sample_data(tmp_path, monkeypatch):
    shutil.copytree(ROOT / "data", tmp_path / "data", ignore=shutil.ignore_patterns("board.db*"))
    c = create_app(tmp_path, today_func=lambda: date(2026, 11, 2)).test_client()

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(req):
        r = c.open(req.full_url.replace("http://seed.test", ""), method=req.get_method(), data=req.data, content_type="application/json")
        assert r.status_code < 400, (req.get_method(), req.full_url, r.get_data(as_text=True))
        return Response(r.get_data())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(sys, "argv", ["seed_demo.py", "http://seed.test"])
    runpy.run_path(str(ROOT / "tests" / "seed_demo.py"))
    b = c.get("/api/board").get_json()
    assert b["warnings"] == []
    assert [(r["company"], r["leader"], r["work"], r["construction"]) for r in b["schedule"]] == [
        ("1班", "佐藤", "組み立て作業", "配管工事"),
        ("見本電機", "田中", "配線工事", "電気工事"),
    ]
    assert [(r["work"], r["construction"]) for r in b["holiday_rows"] if r["person"]] == [("配線工事", "電気工事"), ("清掃", "塗装工事")]
