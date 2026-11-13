import json
import logging
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import app as app_mod
from app import create_app


def free_port():
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


# ---- ポートの探索（待ち受けのソケットを自分で bind して持ち続ける） ----

def test_bind_port_gives_bound_socket_for_unused_and_none_for_listening(busy_sockets):
    port = busy_sockets()
    assert app_mod.bind_port(port, "127.0.0.1") is None
    assert app_mod.bind_port(port, "0.0.0.0") is None
    free = free_port()
    s = app_mod.bind_port(free, "127.0.0.1")
    try:
        assert s is not None and s.getsockname() == ("127.0.0.1", free)
    finally:
        s.close()


@pytest.mark.skipif(not hasattr(socket, "SO_EXCLUSIVEADDRUSE"), reason="Windows のみ")
def test_two_binds_to_the_same_port_never_both_succeed():
    free = free_port()
    first = app_mod.bind_port(free, "127.0.0.1")
    try:
        assert first is not None
        assert app_mod.bind_port(free, "127.0.0.1") is None  # 先に取った方が持っている間、2つ目は取れない
        assert app_mod.bind_port(free, "0.0.0.0") is None
    finally:
        first.close()


def test_connectable_port_counts_as_busy_even_if_bind_would_succeed(monkeypatch):
    class FakeSocket:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def bind(self, addr):
            pass  # Windows で起きる「bind は通るが実は使用中」を再現

        def setsockopt(self, *a):
            pass

        def close(self):
            pass

        def settimeout(self, t):
            pass

        def connect_ex(self, addr):
            return 0  # つながる = 誰かが待ち受けている

    monkeypatch.setattr(app_mod.socket, "socket", FakeSocket)
    assert app_mod.bind_port(5100, "0.0.0.0") is None


def test_preferred_free_port_is_used(monkeypatch):
    monkeypatch.setattr(app_mod, "bind_port", lambda port, host: f"sock{port}")
    assert app_mod.find_available_socket(5100, "0.0.0.0") == (5100, "sock5100")


def test_busy_preferred_moves_to_next(monkeypatch):
    monkeypatch.setattr(app_mod, "bind_port", lambda port, host: f"sock{port}" if port >= 5102 else None)
    assert app_mod.find_available_socket(5100, "0.0.0.0") == (5102, "sock5102")


def test_tries_ten_ports_then_gives_up(monkeypatch):
    seen = []
    monkeypatch.setattr(app_mod, "bind_port", lambda port, host: seen.append(port))
    assert app_mod.find_available_socket(5100, "0.0.0.0") == (None, None)
    assert seen == list(range(5100, 5110))


def test_last_of_ten_is_still_used(monkeypatch):
    monkeypatch.setattr(app_mod, "bind_port", lambda port, host: "s" if port == 5109 else None)
    assert app_mod.find_available_socket(5100, "0.0.0.0") == (5109, "s")


def test_find_with_real_busy_port_returns_next(busy_sockets):
    busy = busy_sockets()
    port, sock = app_mod.find_available_socket(busy, "127.0.0.1")
    try:
        assert port is not None and busy < port < busy + 10 and sock.getsockname()[1] == port
    finally:
        sock.close()


def test_find_all_busy_returns_none(busy_sockets):
    busy = busy_sockets()
    assert app_mod.find_available_socket(busy, "127.0.0.1", tries=1) == (None, None)


def test_waitress_accepts_the_prebound_socket(tmp_path):
    from waitress.server import create_server

    port, sock = app_mod.find_available_socket(free_port(), "127.0.0.1")
    app = create_app(tmp_path)
    server = create_server(app, sockets=[sock], threads=4, _start=False)  # 待ち受けは始めない（受け取れる形かだけ確かめる）
    try:
        assert int(server.effective_port) == port
    finally:
        server.close()
        sock.close()


# ---- すでに起動している同じアプリを見つける ----

class _Health(BaseHTTPRequestHandler):
    payload = b'{"status": "ok", "version": "0.1.0", "app": "digital-bulletin-board"}'

    def do_GET(self):
        if self.path != "/api/health":
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, *a):
        pass


@pytest.fixture
def fake_instance():
    """127.0.0.1 の空きポートで /api/health に答える小さなサーバー（テストの中のスレッド）。"""
    servers = []

    def start(payload=None):
        handler = type("H", (_Health,), {"payload": payload} if payload is not None else {})
        srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
        return srv.server_address[1]

    yield start
    for s in servers:
        s.shutdown()
        s.server_close()


def test_find_running_instance_sees_our_app_within_ten_ports(fake_instance):
    port = fake_instance()
    assert app_mod.find_running_instance(port) == port
    assert app_mod.find_running_instance(port - 9) == port
    assert app_mod.find_running_instance(port - 10) is None  # 範囲の外


@pytest.mark.parametrize("payload", [b'{"status": "ok"}', b'{"app": "other-app"}', b"<html>hello</html>", b"[1, 2]", b"null", b""])
def test_find_running_instance_ignores_other_apps_and_odd_replies(fake_instance, payload):
    port = fake_instance(payload)
    assert app_mod.find_running_instance(port) is None


def test_find_running_instance_gives_up_on_a_port_that_never_answers(busy_sockets):
    port = busy_sockets()  # つながるが返事をしない
    assert app_mod.find_running_instance(port, tries=1, timeout=0.2) is None


def test_find_running_instance_with_nothing_running():
    assert app_mod.find_running_instance(free_port(), tries=3, timeout=0.2) is None


# ---- main() ----

def write_cfg(tmp_path, port, host="127.0.0.1", **extra):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "config.json").write_text(json.dumps({"server": {"host": host, "port": port}, **extra}), encoding="utf-8")


def no_serve(*a, **k):
    pytest.fail("サーバーを起動してはいけない")


def test_main_binds_an_exclusive_socket_writes_port_file_then_serves_it(tmp_path, capsys):
    port = free_port()
    write_cfg(tmp_path, port)
    seen = {}

    def fake_serve(app, **kw):
        seen["app"], seen["kw"] = app, kw
        seen["name"] = kw["sockets"][0].getsockname()
        seen["port_file"] = (tmp_path / "server_port.txt").read_bytes()  # 待ち受けを始める前に書かれている

    assert app_mod.main(tmp_path, serve_func=fake_serve) == 0
    assert set(seen["kw"]) == {"sockets", "threads"} and seen["kw"]["threads"] == 8 and len(seen["kw"]["sockets"]) == 1
    assert seen["name"] == ("127.0.0.1", port)
    assert seen["port_file"] == f"{port}\n".encode()
    assert seen["kw"]["sockets"][0].fileno() == -1  # 終わったら閉じる
    out = capsys.readouterr().out
    assert f"http://localhost:{port}" in out and "管理者キー" in out and seen["app"].config["ADMIN_KEY"] in out
    assert "注意" not in out
    assert "終了しました" in (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")


def test_main_moves_to_the_next_port_when_the_preferred_one_is_busy(tmp_path, capsys, busy_sockets):
    busy = busy_sockets()
    write_cfg(tmp_path, busy)
    got = {}
    assert app_mod.main(tmp_path, serve_func=lambda app, **kw: got.update(port=kw["sockets"][0].getsockname()[1])) == 0
    assert busy < got["port"] < busy + 10
    assert (tmp_path / "server_port.txt").read_text(encoding="utf-8") == f"{got['port']}\n"
    assert f"ポート {busy} は使用中のため、ポート {got['port']} で起動します" in capsys.readouterr().out


def test_main_exits_with_1_when_every_port_is_busy(tmp_path, capsys, monkeypatch):
    write_cfg(tmp_path, 5100)
    monkeypatch.setattr(app_mod, "find_running_instance", lambda *a, **k: None)
    monkeypatch.setattr(app_mod, "find_available_socket", lambda *a, **k: (None, None))
    assert app_mod.main(tmp_path, serve_func=no_serve) == 1
    assert not (tmp_path / "server_port.txt").exists()
    assert "5100～5109 がすべて使用中" in capsys.readouterr().out


def test_serve_crash_is_logged_and_reraised_and_socket_closed(tmp_path):
    write_cfg(tmp_path, free_port())
    socks = []

    def boom(app, **kw):
        socks.extend(kw["sockets"])
        raise RuntimeError("壊れた")

    with pytest.raises(RuntimeError):
        app_mod.main(tmp_path, serve_func=boom)
    assert socks[0].fileno() == -1
    assert "サーバーが異常終了しました" in (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")


def test_second_start_does_not_start_a_second_server(tmp_path, capsys, fake_instance, monkeypatch):
    port = fake_instance()
    write_cfg(tmp_path, port - 3)  # 探す範囲の途中に動いているアプリがいる
    monkeypatch.setattr(app_mod, "create_app", lambda *a, **k: pytest.fail("2つ目のアプリを作ってはいけない"))
    monkeypatch.setattr(app_mod, "find_available_socket", lambda *a, **k: pytest.fail("空きポートを探してはいけない"))
    assert app_mod.main(tmp_path, serve_func=no_serve) == 0
    assert f"すでに起動しています: http://localhost:{port}" in capsys.readouterr().out
    assert (tmp_path / "server_port.txt").read_text(encoding="utf-8") == f"{port}\n"  # 無かったので書く
    assert f"すでに起動しています: http://localhost:{port}" in (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")


def test_second_start_fixes_a_port_file_that_names_another_port(tmp_path, fake_instance):
    port = fake_instance()
    write_cfg(tmp_path, port)
    (tmp_path / "server_port.txt").write_text("5100\n", encoding="utf-8")
    assert app_mod.main(tmp_path, serve_func=no_serve) == 0
    assert (tmp_path / "server_port.txt").read_text(encoding="utf-8") == f"{port}\n"


def test_second_start_leaves_a_correct_port_file_alone(tmp_path, fake_instance):
    port = fake_instance()
    write_cfg(tmp_path, port)
    original = f" {port}\r\n".encode()  # 手で書き換えた形でも、同じ番号なら触らない
    (tmp_path / "server_port.txt").write_bytes(original)
    assert app_mod.main(tmp_path, serve_func=no_serve) == 0
    assert (tmp_path / "server_port.txt").read_bytes() == original


def test_another_app_on_the_port_is_not_mistaken_for_ours(tmp_path, fake_instance):
    port = fake_instance(b'{"status": "ok", "app": "other-app"}')
    write_cfg(tmp_path, port)
    got = {}
    assert app_mod.main(tmp_path, serve_func=lambda app, **kw: got.update(port=kw["sockets"][0].getsockname()[1])) == 0
    assert port < got["port"] < port + 10


# ---- ログ・設定の読み込みは1回だけ ----

def test_main_loads_config_and_sets_up_logging_once(tmp_path, monkeypatch):
    write_cfg(tmp_path, free_port())
    counts = {"log": 0, "cfg": 0}
    real_setup, real_load = app_mod.setup_logging, app_mod.load_config
    monkeypatch.setattr(app_mod, "setup_logging", lambda d: counts.__setitem__("log", counts["log"] + 1) or real_setup(d))
    monkeypatch.setattr(app_mod, "load_config", lambda p: counts.__setitem__("cfg", counts["cfg"] + 1) or real_load(p))
    assert app_mod.main(tmp_path, serve_func=lambda app, **kw: None) == 0
    assert counts == {"log": 1, "cfg": 1}


def test_startup_warning_is_printed_and_logged_once(tmp_path, capsys, monkeypatch):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "config.json").write_text("{ broken", encoding="utf-8")  # 壊れた設定 → 既定の設定で起動する
    real = app_mod.find_available_socket
    monkeypatch.setattr(app_mod, "find_running_instance", lambda *a, **k: None)  # 手元で動いているアプリに影響されない
    monkeypatch.setattr(app_mod, "find_available_socket", lambda preferred, host, tries=10: real(free_port(), host))
    assert app_mod.main(tmp_path, serve_func=lambda app, **kw: None) == 0
    assert capsys.readouterr().err.count("[警告]") == 1
    log = (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")
    assert log.count("起動時の警告: config.json を読めない") == 1


def test_app_logger_does_not_propagate_to_the_root_logger(tmp_path):
    seen = []

    class Catch(logging.Handler):
        def emit(self, record):
            seen.append(record.getMessage())

    root = logging.getLogger()
    handler = Catch(level=logging.DEBUG)
    root.addHandler(handler)  # waitress が basicConfig で付けるハンドラーの代わり
    try:
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "config.json").write_text("{ broken", encoding="utf-8")
        create_app(tmp_path)
        logging.getLogger(app_mod.LOGGER_NAME + ".config").warning("子のロガーも同じ")
    finally:
        root.removeHandler(handler)
    assert logging.getLogger(app_mod.LOGGER_NAME).propagate is False
    assert seen == []
