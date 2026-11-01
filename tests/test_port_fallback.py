import json
import re
import socket
from datetime import date
from pathlib import Path

import pytest

import app as app_mod
from app import create_app
from config import load_config


def make(tmp_path, config=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    if config is not None:
        (tmp_path / "config.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return create_app(tmp_path, today_func=lambda: date(2026, 11, 2)).test_client()


# ---- 設定 server.host / server.port ----

def test_server_defaults(tmp_path):
    cfg = load_config(tmp_path / "config.json")
    assert cfg["server"] == {"host": "0.0.0.0", "port": 5100}
    assert cfg["_warnings"] == []


def test_server_values_are_read(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"server": {"host": "127.0.0.1", "port": 6200}}), encoding="utf-8")
    cfg = load_config(p)
    assert cfg["server"] == {"host": "127.0.0.1", "port": 6200}
    assert cfg["_warnings"] == []


@pytest.mark.parametrize("bad", [1023, 65527, 0, -1, 5100.5, "5100", None, True, [5100]])
def test_bad_port_falls_back_with_japanese_warning(tmp_path, bad):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"server": {"port": bad, "host": "127.0.0.1"}}), encoding="utf-8")
    cfg = load_config(p)
    assert cfg["server"] == {"host": "127.0.0.1", "port": 5100}  # 他の項目は生きる
    (w,) = cfg["_warnings"]
    assert "server.port" in w and "正しくありません" in w and "5100" in w


@pytest.mark.parametrize("port", [1024, 65526])
def test_port_range_edges_are_accepted(tmp_path, port):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"server": {"port": port}}), encoding="utf-8")
    assert load_config(p)["server"]["port"] == port


@pytest.mark.parametrize("bad", ["", "   ", 5, None, "x" * 101, "a\0b", ["0.0.0.0"], "::1", "[::1]", "fe80::1", "127.0.0.1:5100"])
def test_bad_host_falls_back_with_japanese_warning(tmp_path, bad):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"server": {"host": bad, "port": 6200}}), encoding="utf-8")
    cfg = load_config(p)
    assert cfg["server"] == {"host": "0.0.0.0", "port": 6200}
    (w,) = cfg["_warnings"]
    assert "server.host" in w and "正しくありません" in w and "0.0.0.0" in w


def test_server_not_an_object_uses_defaults(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"server": 5}), encoding="utf-8")
    cfg = load_config(p)
    assert cfg["server"] == {"host": "0.0.0.0", "port": 5100}
    (w,) = cfg["_warnings"]
    assert "server" in w and "正しくありません" in w


def test_saving_admin_settings_keeps_server_section(tmp_path):
    c = make(tmp_path, {"server": {"host": "127.0.0.1", "port": 6200}})
    body = {"documents": {"buttons": [{"label": "A", "folder": "docs/a"}]}, "telop": {"speed": 100}}
    assert c.post("/api/admin-settings", json=body).status_code == 200
    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert saved["server"] == {"host": "127.0.0.1", "port": 6200}


# ---- server_port.txt / health ----

def test_write_port_file_is_number_and_newline_utf8(tmp_path):
    path = tmp_path / "server_port.txt"
    assert app_mod.write_port_file(path, 5101) is True
    assert path.read_bytes() == b"5101\n"


def test_write_port_file_failure_returns_false_and_does_not_raise(tmp_path):
    (tmp_path / "server_port.txt").mkdir()  # ファイルとして書けない
    assert app_mod.write_port_file(tmp_path / "server_port.txt", 5101) is False


def test_port_file_name_constant():
    assert app_mod.PORT_FILE == "server_port.txt"


def test_health_has_app_marker_status_and_version(tmp_path):
    r = make(tmp_path).get("/api/health")
    assert r.get_json() == {"status": "ok", "version": app_mod.APP_VERSION, "app": "digital-bulletin-board"}


def test_start_line_in_log_shows_given_port(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    create_app(tmp_path, port=5103)
    text = (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")
    assert "ポート 5103" in text


# ---- 起動.bat（静的チェック。実行はしない） ----

BAT_PATH = Path(app_mod.__file__).resolve().parent / "起動.bat"


def bat_bytes():
    return BAT_PATH.read_bytes()


def bat_text():
    return bat_bytes().decode("cp932")  # 厳密に読めること


def test_bat_is_cp932_roundtrip_and_crlf_only():
    raw = bat_bytes()
    assert bat_text().encode("cp932") == raw
    assert b"\r" not in raw.replace(b"\r\n", b"")
    assert raw.count(b"\n") == raw.count(b"\r\n") and raw.endswith(b"\r\n")


def test_bat_reads_port_file_and_checks_health_marker():
    t = bat_text()
    assert "server_port.txt" in t and "findstr" in t
    assert "digital-bulletin-board" in t and "/api/health" in t
    assert "set /p" in t and "localhost:%PORT%" in t
    assert "5100" in t  # 既定の番号（ファイルが無いとき）
    assert "curl.exe -s --max-time 2 http://localhost:%PORT%/api/health" in t  # 応答しない相手で止まらない
    assert "localhost:5100" not in t  # 番号を固定した待ち受け・ブラウザ起動は残さない
    assert t.count('start "" "%EDGE%" http://localhost:%PORT%') == 1
    assert t.count('start "" http://localhost:%PORT%') == 1


def test_bat_keeps_existing_messages():
    t = bat_text()
    for msg in ["[エラー] .venv が見つかりません。", "先に「初回セットアップ.bat」をダブルクリックしてください。",
                "デジタル掲示板を起動します。この黒い窓は閉じないでください。",
                "終了するときは、この窓で Ctrl + C を押してください。"]:
        assert msg in t, msg


def test_bat_has_no_half_width_parens_inside_blocks_or_echo():
    opens = closes = 0
    for line in bat_text().splitlines():
        s = line.replace("%ProgramFiles(x86)%", "")
        if re.fullmatch(r"if .* \(", s):
            opens += 1
            continue
        if s == ")":
            closes += 1
            continue
        assert "(" not in s and ")" not in s, line
    assert opens == closes


def test_bat_labels_and_gotos_resolve():
    t = bat_text()
    labels = re.findall(r"^:([A-Za-z0-9_]+)\s*$", t, re.M)
    assert len(labels) == len(set(labels))
    for target in re.findall(r"goto\s+:([A-Za-z0-9_]+)", t, re.I):
        assert target in labels, target
    assert {"openbrowser", "waitloop", "ready", "fallback"} <= set(labels)


def test_gitignore_lists_runtime_files():
    lines = (BAT_PATH.parent / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "server_port.txt" in lines and "admin_key.txt" in lines
