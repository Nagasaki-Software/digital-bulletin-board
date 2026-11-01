import json
import logging
from datetime import date

import app as app_mod
from app import create_app

GOOD = {
    "documents": {"buttons": [{"label": "手順書", "folder": "docs/new1"}]},
    "telop": {"speed": 250},
}
NO_KEY = "管理者キーが必要です（サーバーPCの黒い窓、または admin_key.txt に書かれています）"
LAN = {"REMOTE_ADDR": "192.168.1.20"}


def make_app(tmp_path, config=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    if config is not None:
        (tmp_path / "config.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return create_app(tmp_path, today_func=lambda: date(2026, 11, 2))


def key_of(tmp_path):
    return (tmp_path / "admin_key.txt").read_text(encoding="utf-8").strip()


def cfg_bytes(tmp_path):
    p = tmp_path / "config.json"
    return p.read_bytes() if p.exists() else None


def no_backups(tmp_path):
    return not (tmp_path / "backups").exists() or not list((tmp_path / "backups").iterdir())


# ---- 鍵ファイル ----

def test_key_file_is_generated_with_enough_length(tmp_path):
    make_app(tmp_path)
    key = key_of(tmp_path)
    assert len(key) >= 16 and key.isascii() and " " not in key


def test_key_is_stable_across_create_app_calls(tmp_path):
    make_app(tmp_path)
    first = key_of(tmp_path)
    make_app(tmp_path)
    make_app(tmp_path)
    assert key_of(tmp_path) == first


def test_empty_or_blank_key_file_is_regenerated(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "admin_key.txt").write_text("  \n", encoding="utf-8")
    make_app(tmp_path)
    assert len(key_of(tmp_path)) >= 16


def test_unreadable_key_file_is_regenerated(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "admin_key.txt").write_bytes(b"\xff\xfe\x00\x81\x82\xff")  # utf-8 として読めない
    make_app(tmp_path)
    assert len(key_of(tmp_path)) >= 16


def test_existing_key_is_used_as_is(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "admin_key.txt").write_text("my-own-secret-key-123\r\n", encoding="utf-8")
    c = make_app(tmp_path).test_client()
    r = c.post("/api/admin-settings", json=GOOD, headers={"X-Admin-Key": "my-own-secret-key-123"}, environ_overrides=LAN)
    assert r.status_code == 200


def test_write_failure_keeps_in_memory_key_and_warns(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "admin_key.txt").mkdir()  # ファイルとして読み書きできない
    app = make_app(tmp_path)
    key = app.config["ADMIN_KEY"]
    assert len(key) >= 16
    c = app.test_client()
    assert c.post("/api/admin-settings", json=GOOD, headers={"X-Admin-Key": key}, environ_overrides=LAN).status_code == 200
    log = (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")
    assert "admin_key.txt" in log and key not in log


def test_load_admin_key_helper(tmp_path):
    p = tmp_path / "admin_key.txt"
    k1 = app_mod.load_admin_key(p)
    assert p.read_text(encoding="utf-8").strip() == k1
    assert app_mod.load_admin_key(p) == k1


# ---- 保存の許可 ----

def test_loopback_needs_no_key(tmp_path):
    c = make_app(tmp_path).test_client()
    for addr in ("127.0.0.1", "::1"):
        r = c.post("/api/admin-settings", json=GOOD, environ_overrides={"REMOTE_ADDR": addr})
        assert r.status_code == 200, addr


def test_default_test_client_is_loopback(tmp_path):
    assert make_app(tmp_path).test_client().post("/api/admin-settings", json=GOOD).status_code == 200


def test_other_address_without_key_is_403_and_nothing_saved(tmp_path):
    c = make_app(tmp_path, {"company_name": "元の会社"}).test_client()
    before = cfg_bytes(tmp_path)
    r = c.post("/api/admin-settings", json=GOOD, environ_overrides=LAN)
    assert r.status_code == 403
    assert r.get_json() == {"error": NO_KEY}
    assert r.content_type == "application/json; charset=utf-8"
    assert cfg_bytes(tmp_path) == before and no_backups(tmp_path)
    assert not (tmp_path / "config.json.tmp").exists()


def test_other_address_without_any_config_file_creates_none(tmp_path):
    c = make_app(tmp_path).test_client()
    assert c.post("/api/admin-settings", json=GOOD, environ_overrides=LAN).status_code == 403
    assert not (tmp_path / "config.json").exists()


def test_empty_key_header_counts_as_missing(tmp_path):
    c = make_app(tmp_path).test_client()
    r = c.post("/api/admin-settings", json=GOOD, headers={"X-Admin-Key": ""}, environ_overrides=LAN)
    assert r.status_code == 403 and r.get_json() == {"error": NO_KEY}


def test_wrong_key_is_403_and_nothing_saved(tmp_path):
    c = make_app(tmp_path, {"company_name": "元の会社"}).test_client()
    before = cfg_bytes(tmp_path)
    for bad in ("wrong", key_of(tmp_path)[:-1], key_of(tmp_path) + "x", "日本語キー"):
        r = c.post("/api/admin-settings", json=GOOD, headers={"X-Admin-Key": bad}, environ_overrides=LAN)
        assert r.status_code == 403, bad
        assert r.get_json() == {"error": "管理者キーが違います"}
    assert cfg_bytes(tmp_path) == before and no_backups(tmp_path)


def test_key_is_checked_before_the_body(tmp_path):
    c = make_app(tmp_path).test_client()
    # 本文が壊れていても、キーが無ければ中身については何も答えない
    r = c.post("/api/admin-settings", data="これはJSONではない", content_type="application/json", environ_overrides=LAN)
    assert r.status_code == 403 and r.get_json() == {"error": NO_KEY}
    r = c.post("/api/admin-settings", json={"bad": 1}, headers={"X-Admin-Key": "wrong"}, environ_overrides=LAN)
    assert r.status_code == 403 and r.get_json() == {"error": "管理者キーが違います"}


def test_right_key_saves_and_validation_still_applies(tmp_path):
    c = make_app(tmp_path).test_client()
    headers = {"X-Admin-Key": key_of(tmp_path)}
    r = c.post("/api/admin-settings", json=GOOD, headers=headers, environ_overrides=LAN)
    assert r.status_code == 200
    assert json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))["telop"]["speed"] == 250
    r = c.post("/api/admin-settings", json={"bad": 1}, headers=headers, environ_overrides=LAN)
    assert r.status_code == 400


def test_get_and_other_routes_stay_open(tmp_path):
    c = make_app(tmp_path).test_client()
    for path in ("/api/admin-settings", "/api/board", "/api/health", "/api/rev", "/api/telop", "/"):
        assert c.get(path, environ_overrides=LAN).status_code == 200, path
    assert c.post("/api/notices", environ_overrides=LAN).status_code == 200


# ---- 鍵を外に出さない ----

def test_key_never_appears_in_responses_or_log(tmp_path):
    app = make_app(tmp_path)
    c = app.test_client()
    key = key_of(tmp_path)
    c.post("/api/admin-settings", json=GOOD, environ_overrides=LAN)
    c.post("/api/admin-settings", json=GOOD, headers={"X-Admin-Key": key[:-1]}, environ_overrides=LAN)
    c.post("/api/admin-settings", json=GOOD, headers={"X-Admin-Key": key}, environ_overrides=LAN)
    for path in ("/api/board", "/api/admin-settings", "/api/health", "/api/rev", "/"):
        assert key not in c.get(path, environ_overrides=LAN).get_data(as_text=True), path
    for h in logging.getLogger(app_mod.LOGGER_NAME).handlers:
        h.flush()
    assert key not in (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")
    assert key not in (tmp_path / "config.json").read_text(encoding="utf-8")


# ---- 画面 ----

def test_ui_has_hidden_admin_key_password_row_at_top_of_shared_section(tmp_path):
    html = make_app(tmp_path).test_client().get("/").get_data(as_text=True)
    settings = html[html.index('id="settings"'):html.index('id="standby"')]
    shared = settings[settings.index("全端末共通"):]
    start = shared.index('id="admin-key-row"')
    row = shared[start:]
    row = row[:row.index("</div>")]
    assert "hidden" in shared[start:start + 80]
    assert 'id="admin-key"' in row and 'type="password"' in row
    assert 'placeholder="別のPCから設定を変えるときだけ入力"' in row and "管理者キー" in row
    assert shared.index('id="admin-key"') < shared.index('id="company-input"')


def test_js_sends_key_header_and_remembers_it_per_tab(tmp_path):
    c = make_app(tmp_path).test_client()
    js = c.get("/js/admin-settings.js").get_data(as_text=True)
    for needle in ["X-Admin-Key", "sessionStorage", "admin-key", "admin-key-row", "location.hostname", "localhost", "127.0.0.1", "[::1]", "403"]:
        assert needle in js, needle
    assert "try" in js[js.index("sessionStorage") - 200:]
    assert "headers" in c.get("/js/api.js").get_data(as_text=True)


def test_hidden_field_line_is_really_hidden_in_css(tmp_path):
    css = make_app(tmp_path).test_client().get("/board.css").get_data(as_text=True)
    assert ".field-line[hidden]" in css


# ---- 修正: 鍵ファイルの書き方 ----

def tmp_leftovers(tmp_path):
    return sorted(p.name for p in tmp_path.iterdir() if "admin_key" in p.name and p.name != "admin_key.txt")


def test_key_file_is_created_whole_and_leaves_no_temp_file_behind(tmp_path):
    p = tmp_path / "admin_key.txt"
    key = app_mod.load_admin_key(p)
    assert p.read_bytes() == (key + "\n").encode("utf-8")
    assert tmp_leftovers(tmp_path) == []


def test_key_created_by_someone_else_meanwhile_is_read_not_overwritten(tmp_path, monkeypatch):
    p = tmp_path / "admin_key.txt"

    def lost_race(src, dst):
        p.write_text("winner-key-from-other-process\n", encoding="utf-8")  # 確かめたあと・置く前に、別の起動が作った
        raise FileExistsError(dst)

    monkeypatch.setattr(app_mod.os, "link", lost_race)
    assert app_mod.load_admin_key(p) == "winner-key-from-other-process"
    assert p.read_text(encoding="utf-8") == "winner-key-from-other-process\n"
    assert tmp_leftovers(tmp_path) == []


def test_key_is_still_created_where_hard_links_are_not_available(tmp_path, monkeypatch):
    def no_links(src, dst):
        raise PermissionError("リンクを作れない場所")

    monkeypatch.setattr(app_mod.os, "link", no_links)
    p = tmp_path / "admin_key.txt"
    key = app_mod.load_admin_key(p)
    assert len(key) >= 16 and p.read_text(encoding="utf-8").strip() == key and tmp_leftovers(tmp_path) == []


def test_failed_replace_cleans_up_and_keeps_in_memory_key(tmp_path, monkeypatch, app_caplog):
    def denied(src, dst):
        raise PermissionError("denied")

    monkeypatch.setattr(app_mod.os, "link", denied)
    monkeypatch.setattr(app_mod.os, "replace", denied)
    p = tmp_path / "admin_key.txt"
    key = app_mod.load_admin_key(p)
    assert len(key) >= 16 and not p.exists() and tmp_leftovers(tmp_path) == []
    assert "admin_key.txt" in app_caplog.text and key not in app_caplog.text


def test_cp932_key_file_is_regenerated_with_a_warning_and_the_log_has_no_key(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "admin_key.txt").write_bytes("管理者キー\r\n".encode("cp932"))  # メモ帳などで Shift-JIS 保存された
    app = make_app(tmp_path)
    key = key_of(tmp_path)
    assert len(key) >= 16 and key.isascii() and key == app.config["ADMIN_KEY"]
    for h in logging.getLogger(app_mod.LOGGER_NAME).handlers:
        h.flush()
    log = (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")
    assert "admin_key.txt" in log and "作り直します" in log and key not in log
    assert tmp_leftovers(tmp_path) == []


# ---- 修正: 管理者キー不要の条件は「接続元が自分自身」かつ「Host が localhost 系」 ----

def test_loopback_with_a_foreign_host_header_needs_the_key(tmp_path):
    c = make_app(tmp_path, {"company_name": "元の会社"}).test_client()
    before = cfg_bytes(tmp_path)
    for host in ("evil.example", "evil.example:5100", "localhost.evil.example", "192.168.1.5:5100", "127.0.0.1.evil.example", "", "[::1"):
        r = c.post("/api/admin-settings", json=GOOD, headers={"Host": host}, environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
        assert r.status_code == 403, host
        assert r.get_json() == {"error": NO_KEY}
    assert cfg_bytes(tmp_path) == before and no_backups(tmp_path)


def test_loopback_with_a_foreign_host_and_the_right_key_is_accepted(tmp_path):
    c = make_app(tmp_path).test_client()
    r = c.post("/api/admin-settings", json=GOOD, headers={"Host": "evil.example", "X-Admin-Key": key_of(tmp_path)},
               environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert r.status_code == 200


def test_loopback_with_localhost_style_hosts_needs_no_key(tmp_path):
    c = make_app(tmp_path).test_client()
    for host, addr in (("localhost", "127.0.0.1"), ("localhost:5100", "127.0.0.1"), ("LOCALHOST:5100", "127.0.0.1"),
                       ("127.0.0.1", "127.0.0.1"), ("127.0.0.1:5101", "127.0.0.1"), ("[::1]", "::1"), ("[::1]:5100", "::1"),
                       ("localhost", "::1")):
        r = c.post("/api/admin-settings", json=GOOD, headers={"Host": host}, environ_overrides={"REMOTE_ADDR": addr})
        assert r.status_code == 200, host


def test_localhost_host_from_another_pc_still_needs_the_key(tmp_path):
    c = make_app(tmp_path).test_client()
    r = c.post("/api/admin-settings", json=GOOD, headers={"Host": "localhost:5100"}, environ_overrides=LAN)
    assert r.status_code == 403


# ---- 修正: 画面（管理者キー欄） ----

def test_js_shows_key_row_after_any_403_refills_from_session_and_checks_ascii(tmp_path):
    js = make_app(tmp_path).test_client().get("/js/admin-settings.js").get_data(as_text=True)
    assert "isAsciiKey" in js and "管理者キーは半角英数字です" in js
    load = js[js.index("async function load()"):js.index("// 入力を確かめて送る内容にする")]
    assert "rememberedKey()" in load  # 設定を開くたびに、このタブで覚えているキーを入れ直す
    save = js[js.index("settings-save"):]
    assert "e.status === 403 && isRemote" not in js and "e.status === 403" in save
    assert 'admin-key-row").hidden = false' in js.replace("\n", "")  # localhost でも 403 のあとは欄を出す
    assert js.index("isAsciiKey(key)") < js.index('api("POST"')  # 送る前に確かめる（TypeError にしない）
