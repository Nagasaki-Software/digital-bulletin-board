import json
import logging
import re
import shutil
from datetime import date
from logging.handlers import RotatingFileHandler

import app as app_mod
from app import create_app

GOOD = {
    "documents": {"buttons": [{"label": "秘密ラベルAAA", "folder": "docs/new1"}]},
    "telop": {"speed": 250, "folder": "お知らせ置き場"},
    "company_name": "秘密会社名BBB",
}


def make_app(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    return create_app(tmp_path, today_func=lambda: date(2026, 11, 2))


def log_lines(tmp_path):
    p = tmp_path / "logs" / "app.log"
    return p.read_text(encoding="utf-8").splitlines() if p.exists() else []


def our_handlers():
    # pytest は、root に流さないロガーにも自前の記録用ハンドラーをつなぐ。それは数に入れない
    return [h for h in logging.getLogger(app_mod.LOGGER_NAME).handlers if type(h).__name__ != "LogCaptureHandler"]


def test_log_file_is_created_under_base_dir_with_start_line(tmp_path):
    make_app(tmp_path)
    lines = log_lines(tmp_path)
    assert (tmp_path / "logs" / "app.log").is_file()
    start = [ln for ln in lines if "起動します" in ln]
    assert len(start) == 1
    assert app_mod.APP_VERSION in start[0] and "ポート 5100" in start[0] and "ホスト 0.0.0.0" in start[0]
    # 形式: 2026-11-01 09:00:00,123 [INFO] メッセージ
    assert re.match(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3} \[INFO\] ", start[0])


def test_handler_settings_match_sibling_app(tmp_path):
    make_app(tmp_path)
    (h,) = our_handlers()
    assert isinstance(h, RotatingFileHandler)
    assert h.maxBytes == 1024 * 1024 and h.backupCount == 5
    assert (h.encoding or "").lower().replace("-", "") == "utf8"


def test_settings_save_is_logged_without_free_text(tmp_path):
    c = make_app(tmp_path).test_client()
    assert c.post("/api/admin-settings", json=GOOD).status_code == 200
    text = "\n".join(log_lines(tmp_path))
    saved = [ln for ln in log_lines(tmp_path) if "設定を保存" in ln]
    assert len(saved) == 1
    for group in ("文書ボタン", "テロップ速度", "テロップフォルダ", "会社名"):
        assert group in saved[0]
    assert "docs/new1" in saved[0] and "お知らせ置き場" in saved[0]  # フォルダの場所は書いてよい
    assert "秘密ラベルAAA" not in text and "秘密会社名BBB" not in text


def test_unchanged_save_says_no_change(tmp_path):
    c = make_app(tmp_path).test_client()
    c.post("/api/admin-settings", json=GOOD)
    c.post("/api/admin-settings", json=GOOD)
    saved = [ln for ln in log_lines(tmp_path) if "設定を保存" in ln]
    assert len(saved) == 2 and "変更なし" in saved[1]


def test_refused_saves_are_logged_with_reason(tmp_path):
    c = make_app(tmp_path).test_client()
    bad = json.loads(json.dumps(GOOD))
    bad["telop"]["speed"] = 5
    assert c.post("/api/admin-settings", json=bad).status_code == 400
    (tmp_path / "config.json").write_text("{ broken", encoding="utf-8")
    assert c.post("/api/admin-settings", json=GOOD).status_code == 400
    refused = [ln for ln in log_lines(tmp_path) if "拒否" in ln]
    assert len(refused) == 2
    assert "[WARNING]" in refused[0] and "速度" in refused[0]
    assert "書き間違い" in refused[1]
    assert not any("設定を保存" in ln for ln in log_lines(tmp_path))
    assert "秘密会社名BBB" not in "\n".join(log_lines(tmp_path))


def test_backup_warning_reaches_log_file(tmp_path):
    c = make_app(tmp_path).test_client()
    (tmp_path / "config.json").write_text('{"company_name": "元"}', encoding="utf-8")
    (tmp_path / "backups").write_text("x", encoding="utf-8")
    assert c.post("/api/admin-settings", json=GOOD).status_code == 200
    assert any("[WARNING]" in ln and "バックアップ" in ln for ln in log_lines(tmp_path))


def test_startup_warnings_are_logged_once_not_per_poll(tmp_path):
    (tmp_path / "config.json").write_text('{"telop": {"speed": 5}}', encoding="utf-8")
    c = make_app(tmp_path).test_client()
    warned = [ln for ln in log_lines(tmp_path) if "[WARNING]" in ln and "telop.speed" in ln]
    assert len(warned) == 1
    for _ in range(3):
        c.get("/api/board")
        c.get("/api/rev")
    assert len([ln for ln in log_lines(tmp_path) if "telop.speed" in ln]) == 1


def test_csv_warnings_are_logged_at_startup(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "custom_holidays.csv").write_text("date,name\nあいう,休み\n", encoding="utf-8-sig")
    make_app(tmp_path)
    assert any("[WARNING]" in ln and "custom_holidays" in ln for ln in log_lines(tmp_path))


def test_polling_adds_no_log_lines(tmp_path):
    c = make_app(tmp_path).test_client()
    n = len(log_lines(tmp_path))
    for _ in range(10):
        assert c.get("/api/rev").status_code == 200
    c.get("/api/health")
    c.get("/api/board")
    c.get("/api/telop")
    c.get("/api/admin-settings")
    c.get("/")
    c.get("/no-such-file")
    assert len(log_lines(tmp_path)) == n


def test_unhandled_exception_is_logged_with_traceback_and_response_stays_json(tmp_path):
    app = make_app(tmp_path)

    @app.get("/api/boom")
    def boom():
        raise ZeroDivisionError("ここで落ちる")

    @app.get("/boom-page")
    def boom_page():
        raise RuntimeError("画面側で落ちる")

    c = app.test_client()
    r = c.get("/api/boom")
    assert r.status_code == 500
    assert r.get_json() == {"error": "サーバーでエラーが起きました"}
    assert "charset=utf-8" in r.headers["Content-Type"].lower()
    r2 = c.get("/boom-page")
    assert r2.status_code == 500 and r2.mimetype == "text/html"
    text = "\n".join(log_lines(tmp_path))
    assert "[ERROR]" in text and "Traceback" in text
    assert "ZeroDivisionError: ここで落ちる" in text and "RuntimeError: 画面側で落ちる" in text
    assert "/api/boom" in text


def test_http_errors_like_404_are_not_logged_as_errors(tmp_path):
    c = make_app(tmp_path).test_client()
    c.get("/api/nothing")
    c.post("/api/board")
    assert not any("[ERROR]" in ln for ln in log_lines(tmp_path))


def test_repeated_create_app_does_not_duplicate_handlers(tmp_path):
    for _ in range(5):
        make_app(tmp_path)
    assert len(our_handlers()) == 1
    for i in range(3):
        make_app(tmp_path / f"other{i}")
    assert len(our_handlers()) == 1
    # 起動の行は、そのフォルダにつき1回ずつ（重複ハンドラーなら2行以上になる）
    assert len([ln for ln in log_lines(tmp_path) if "起動します" in ln]) == 5


def test_old_log_file_handle_is_released_so_folder_can_be_removed(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    make_app(a)
    make_app(b)
    shutil.rmtree(a)  # 古いハンドラーが開いたままだと、Windows ではここで失敗する
    assert not a.exists()


def test_unwritable_log_folder_falls_back_to_console(tmp_path, capsys, caplog):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "logs").write_text("ファイルがフォルダの場所にある", encoding="utf-8")
    c = make_app(tmp_path).test_client()  # 落ちない
    assert c.get("/api/health").status_code == 200
    assert (tmp_path / "logs").is_file()
    assert len(our_handlers()) == 1 and not isinstance(our_handlers()[0], logging.FileHandler)
    c.get("/api/board")
    err = capsys.readouterr().err
    assert err.count("ログフォルダ") == 1  # 警告は1回だけ


def test_fallback_then_writable_again_uses_file(tmp_path):
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "logs").write_text("x", encoding="utf-8")
    make_app(bad)
    good = tmp_path / "good"
    make_app(good)
    assert len(our_handlers()) == 1 and isinstance(our_handlers()[0], RotatingFileHandler)
    assert (good / "logs" / "app.log").is_file()
