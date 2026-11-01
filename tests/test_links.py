import json
import re
from datetime import date
from pathlib import Path

import pytest

from app import create_app
from config import clean_admin_settings, load_config

DOCS = {"buttons": [{"label": "文書", "folder": "documents/doc1"}]}
NAME = re.compile(r"config_\d{8}_\d{6}(_\d+)?\.json")
LAN = {"REMOTE_ADDR": "192.168.1.20"}
INSPECTION = {"label": "設備点検システム", "url": "http://localhost:5000/"}
OTHER = {"label": "Web2", "url": "https://example.com/a?b=1#c"}
DEFAULT_LINKS = {"items": [], "max_stay_seconds": 300}


def write_cfg(tmp_path, data):
    tmp_path.mkdir(parents=True, exist_ok=True)
    p = tmp_path / "config.json"
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def make(tmp_path, config=None, **kw):
    tmp_path.mkdir(parents=True, exist_ok=True)
    if config is not None:
        write_cfg(tmp_path, config)
    return create_app(tmp_path, today_func=lambda: date(2026, 11, 2), **kw)


def client(tmp_path, config=None):
    return make(tmp_path, config).test_client()


def body(links=None, **extra):
    b = {"documents": dict(DOCS), "telop": {"speed": 100}, **extra}
    if links is not None:
        b["links"] = links
    return b


def cfg_bytes(tmp_path):
    p = tmp_path / "config.json"
    return p.read_bytes() if p.exists() else None


def tree(tmp_path):
    return sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if "logs" not in p.parts and p.name != "admin_key.txt")


def saved(tmp_path):
    return json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))


# ---- config.json の読み込み ----

def test_default_is_no_links_and_300_seconds_without_warning(tmp_path):
    cfg = load_config(tmp_path / "config.json")
    assert cfg["links"] == DEFAULT_LINKS
    assert cfg["_warnings"] == []


def test_valid_links_are_loaded_and_label_is_stripped(tmp_path):
    items = [{"label": "  設備点検システム ", "url": "http://localhost:5000/"}, {"label": "Web2", "url": "HTTPS://Example.com/a?b=1#c"}]
    cfg = load_config(write_cfg(tmp_path, {"links": {"items": items, "max_stay_seconds": 120}}))
    assert cfg["links"] == {"items": [INSPECTION, {"label": "Web2", "url": "HTTPS://Example.com/a?b=1#c"}], "max_stay_seconds": 120}
    assert cfg["_warnings"] == []


def test_at_most_two_links_extra_ones_are_dropped_with_warning(tmp_path):
    items = [{"label": f"L{i}", "url": f"http://host{i}/"} for i in range(3)]
    cfg = load_config(write_cfg(tmp_path, {"links": {"items": items}}))
    assert [i["label"] for i in cfg["links"]["items"]] == ["L0", "L1"]
    assert len(cfg["_warnings"]) == 1 and "links" in cfg["_warnings"][0] and "2" in cfg["_warnings"][0]


BAD_URLS = [
    "javascript:alert(1)", "JavaScript:alert(1)", "file:///c:/x", "ftp://a/b", "data:text/html,x", "vbscript:x",
    "//host/x", "/relative", "relative/path", "host:5000/", "example.com", "http://", "https://", "http:///x", "http://:80/",
    "http:example.com", "http:\\\\host\\x", "http://a b/", "http://a\tb/", "http://a\nb/", "http://a\x00b/", "http://a\x7fb/",
    "http://a\u3000b/", " http://x/", "http://x/ ", "\nhttp://x/", "http://x:99999/", "http://[::1/",
    "https://" + "a" * 494, "", None, 5, True, ["http://x/"], {"a": 1},
]


@pytest.mark.parametrize("bad", BAD_URLS, ids=[repr(b)[:30] for b in BAD_URLS])
def test_bad_url_item_is_skipped_with_warning_and_neighbours_kept(tmp_path, bad):
    items = [{"label": "悪い", "url": bad}, INSPECTION]
    cfg = load_config(write_cfg(tmp_path, {"links": {"items": items}}))
    assert cfg["links"]["items"] == [INSPECTION]
    assert len(cfg["_warnings"]) == 1 and "links" in cfg["_warnings"][0] and "1番目" in cfg["_warnings"][0]


def test_url_length_limit_is_500(tmp_path):
    ok = "http://a.com/" + "x" * (500 - len("http://a.com/"))
    assert len(ok) == 500
    cfg = load_config(write_cfg(tmp_path, {"links": {"items": [{"label": "長い", "url": ok}, {"label": "超過", "url": ok + "x"}]}}))
    assert cfg["links"]["items"] == [{"label": "長い", "url": ok}]
    assert len(cfg["_warnings"]) == 1


def test_non_ascii_host_and_ip_and_port_urls_are_fine(tmp_path):
    urls = ["http://サーバーPC:5000/", "http://192.168.0.5:5000/", "http://[::1]:5000/x", "https://a.b.c/"]
    cfg = load_config(write_cfg(tmp_path, {"links": {"items": [{"label": "A", "url": u} for u in urls[:2]]}}))
    assert [i["url"] for i in cfg["links"]["items"]] == urls[:2]
    cfg = load_config(write_cfg(tmp_path / "b", {"links": {"items": [{"label": "A", "url": u} for u in urls[2:]]}}))
    assert [i["url"] for i in cfg["links"]["items"]] == urls[2:]


@pytest.mark.parametrize("bad", ["", "   ", "x" * 101, None, 5, True, ["a"]])
def test_bad_label_item_is_skipped_with_warning(tmp_path, bad):
    cfg = load_config(write_cfg(tmp_path, {"links": {"items": [{"label": bad, "url": "http://a/"}, INSPECTION]}}))
    assert cfg["links"]["items"] == [INSPECTION]
    assert len(cfg["_warnings"]) == 1 and "links" in cfg["_warnings"][0]


def test_label_of_100_chars_is_ok(tmp_path):
    cfg = load_config(write_cfg(tmp_path, {"links": {"items": [{"label": "あ" * 100, "url": "http://a/"}]}}))
    assert cfg["links"]["items"] == [{"label": "あ" * 100, "url": "http://a/"}]


def test_item_missing_keys_or_not_an_object_is_skipped(tmp_path):
    items = [{"label": "url無し"}, {"url": "http://a/"}, "http://a/", 3, None, INSPECTION]
    cfg = load_config(write_cfg(tmp_path, {"links": {"items": items}}))
    assert cfg["links"]["items"] == [INSPECTION]
    assert len(cfg["_warnings"]) == 5


@pytest.mark.parametrize("bad", [{}, "x", 5, None, True])
def test_items_wrong_shape_falls_back_to_none_with_warning(tmp_path, bad):
    cfg = load_config(write_cfg(tmp_path, {"links": {"items": bad}}))
    assert cfg["links"]["items"] == []
    assert any("links" in w for w in cfg["_warnings"])


def test_empty_items_list_is_fine(tmp_path):
    cfg = load_config(write_cfg(tmp_path, {"links": {"items": []}}))
    assert cfg["links"] == DEFAULT_LINKS and cfg["_warnings"] == []


@pytest.mark.parametrize("bad", ["x", 5, None, [], True])
def test_links_wrong_shape_falls_back_to_default(tmp_path, bad):
    cfg = load_config(write_cfg(tmp_path, {"links": bad}))
    assert cfg["links"] == DEFAULT_LINKS
    assert any("links" in w for w in cfg["_warnings"])


@pytest.mark.parametrize("good", [60, 300, 3600])
def test_stay_in_range_is_accepted(tmp_path, good):
    cfg = load_config(write_cfg(tmp_path, {"links": {"max_stay_seconds": good}}))
    assert cfg["links"]["max_stay_seconds"] == good and cfg["_warnings"] == []


@pytest.mark.parametrize("bad", [0, 59, 3601, -1, 10**9, 300.5, 300.0, "300", "", None, True, False, [300], {"a": 1}])
def test_stay_out_of_range_falls_back_to_300_with_warning(tmp_path, bad):
    cfg = load_config(write_cfg(tmp_path, {"links": {"max_stay_seconds": bad, "items": [INSPECTION]}}))
    assert cfg["links"]["max_stay_seconds"] == 300
    assert cfg["links"]["items"] == [INSPECTION]  # 他の項目は生きる
    assert len(cfg["_warnings"]) == 1 and "max_stay_seconds" in cfg["_warnings"][0]


# ---- 管理画面の保存 ----

def test_get_admin_settings_returns_links_default_and_configured(tmp_path):
    assert client(tmp_path).get("/api/admin-settings").get_json()["links"] == DEFAULT_LINKS
    c = client(tmp_path / "b", {"links": {"items": [INSPECTION], "max_stay_seconds": 90}})
    assert c.get("/api/admin-settings").get_json()["links"] == {"items": [INSPECTION], "max_stay_seconds": 90}


def test_post_saves_and_applies_without_restart(tmp_path):
    c = client(tmp_path)
    rev = c.get("/api/rev").get_json()["rev"]
    links = {"items": [{"label": " 設備点検システム ", "url": "http://localhost:5000/"}, OTHER], "max_stay_seconds": 180}
    r = c.post("/api/admin-settings", json=body(links))
    assert r.status_code == 200 and r.get_json() == {"ok": True}
    assert saved(tmp_path)["links"] == {"items": [INSPECTION, OTHER], "max_stay_seconds": 180}
    assert c.get("/api/rev").get_json()["rev"] != rev
    assert c.get("/api/board").get_json()["links"] == {"items": [INSPECTION, OTHER], "max_stay_seconds": 180}
    assert c.get("/api/admin-settings").get_json()["links"] == {"items": [INSPECTION, OTHER], "max_stay_seconds": 180}


def test_blank_rows_are_unused(tmp_path):
    c = client(tmp_path)
    blank = {"label": "", "url": ""}
    assert c.post("/api/admin-settings", json=body({"items": [blank, OTHER], "max_stay_seconds": 300})).status_code == 200
    assert saved(tmp_path)["links"]["items"] == [OTHER]
    assert c.post("/api/admin-settings", json=body({"items": [{"label": "  ", "url": " "}, blank], "max_stay_seconds": 300})).status_code == 200
    assert saved(tmp_path)["links"]["items"] == []
    assert c.get("/api/board").get_json()["links"]["items"] == []


def test_an_empty_items_list_clears_the_links(tmp_path):
    c = client(tmp_path, {"links": {"items": [INSPECTION]}})
    assert c.post("/api/admin-settings", json=body({"items": []})).status_code == 200
    assert c.get("/api/board").get_json()["links"]["items"] == []


@pytest.mark.parametrize(
    "row,which",
    [({"label": "名前だけ", "url": ""}, 2), ({"label": "名前だけ", "url": "  "}, 2), ({"label": "", "url": "http://a/"}, 2), ({"label": " ", "url": "http://a/"}, 2)],
)
def test_partial_row_is_400_naming_the_row_and_saves_nothing(tmp_path, row, which):
    c = client(tmp_path, {"company_name": "元のまま"})
    before, names, rev = cfg_bytes(tmp_path), tree(tmp_path), c.get("/api/rev").get_json()["rev"]
    r = c.post("/api/admin-settings", json=body({"items": [INSPECTION, row], "max_stay_seconds": 300}))
    assert r.status_code == 400
    assert f"リンクボタン {which}" in r.get_json()["error"]
    assert cfg_bytes(tmp_path) == before and tree(tmp_path) == names
    assert c.get("/api/rev").get_json()["rev"] == rev


def test_partial_first_row_names_row_1(tmp_path):
    c = client(tmp_path)
    r = c.post("/api/admin-settings", json=body({"items": [{"label": "A", "url": ""}, OTHER]}))
    assert r.status_code == 400 and "リンクボタン 1" in r.get_json()["error"]


BAD_POST_URLS = [u for u in BAD_URLS if isinstance(u, str) and u.strip()] + [None, 5, True]


@pytest.mark.parametrize("bad", BAD_POST_URLS, ids=[repr(b)[:30] for b in BAD_POST_URLS])
@pytest.mark.parametrize("preexisting", [False, True])
def test_invalid_url_is_400_naming_the_row_and_saves_nothing(tmp_path, bad, preexisting):
    c = client(tmp_path, {"company_name": "元のまま", "links": {"items": [INSPECTION]}} if preexisting else None)
    before, names, rev = cfg_bytes(tmp_path), tree(tmp_path), c.get("/api/rev").get_json()["rev"]
    r = c.post("/api/admin-settings", json=body({"items": [{"label": "悪い", "url": bad}]}))
    assert r.status_code == 400
    msg = r.get_json()["error"]
    assert "リンクボタン 1" in msg and any(ord(ch) > 127 for ch in msg)
    assert cfg_bytes(tmp_path) == before and tree(tmp_path) == names
    assert c.get("/api/rev").get_json()["rev"] == rev
    assert c.get("/api/board").get_json()["links"]["items"] == ([INSPECTION] if preexisting else [])


@pytest.mark.parametrize("bad", ["", "x" * 101, None, 5, ["a"]])
def test_bad_label_in_a_row_with_url_is_400(tmp_path, bad):
    c = client(tmp_path)
    before = cfg_bytes(tmp_path)
    r = c.post("/api/admin-settings", json=body({"items": [{"label": bad, "url": "http://a/"}]}))
    assert r.status_code == 400 and "リンクボタン 1" in r.get_json()["error"]
    assert cfg_bytes(tmp_path) == before


def test_three_items_are_rejected_even_if_one_is_blank(tmp_path):
    c = client(tmp_path)
    for third in (OTHER, {"label": "", "url": ""}):
        before = cfg_bytes(tmp_path)
        r = c.post("/api/admin-settings", json=body({"items": [INSPECTION, OTHER, third]}))
        assert r.status_code == 400 and "2" in r.get_json()["error"] and "リンク" in r.get_json()["error"]
        assert cfg_bytes(tmp_path) == before


@pytest.mark.parametrize("bad", [0, 59, 3601, 300.5, "300", "", None, True, [300]])
def test_bad_stay_is_400_naming_the_field_and_saves_nothing(tmp_path, bad):
    c = client(tmp_path, {"company_name": "元"})
    before, names = cfg_bytes(tmp_path), tree(tmp_path)
    r = c.post("/api/admin-settings", json=body({"items": [INSPECTION], "max_stay_seconds": bad}))
    assert r.status_code == 400 and "最大滞在" in r.get_json()["error"]
    assert cfg_bytes(tmp_path) == before and tree(tmp_path) == names


@pytest.mark.parametrize("bad", ["x", 5, None, [], [INSPECTION], True])
def test_links_not_an_object_is_400(tmp_path, bad):
    c = client(tmp_path)
    before = cfg_bytes(tmp_path)
    assert c.post("/api/admin-settings", json={**body(), "links": bad}).status_code == 400
    assert cfg_bytes(tmp_path) == before


@pytest.mark.parametrize("bad", ["x", 5, None, {}, True, INSPECTION])
def test_items_not_a_list_is_400(tmp_path, bad):
    c = client(tmp_path)
    before = cfg_bytes(tmp_path)
    assert c.post("/api/admin-settings", json=body({"items": bad})).status_code == 400
    assert cfg_bytes(tmp_path) == before


def test_items_not_dict_rows_are_400(tmp_path):
    c = client(tmp_path)
    r = c.post("/api/admin-settings", json=body({"items": ["http://a/"]}))
    assert r.status_code == 400 and "リンクボタン 1" in r.get_json()["error"]


def test_boundary_values_are_accepted(tmp_path):
    c = client(tmp_path)
    ok = "http://a.com/" + "x" * (500 - len("http://a.com/"))
    assert c.post("/api/admin-settings", json=body({"items": [{"label": "あ" * 100, "url": ok}], "max_stay_seconds": 60})).status_code == 200
    assert c.post("/api/admin-settings", json=body({"items": [INSPECTION], "max_stay_seconds": 3600})).status_code == 200
    assert c.get("/api/admin-settings").get_json()["links"]["max_stay_seconds"] == 3600


def test_omitted_links_keep_current_values_old_clients_still_work(tmp_path):
    original = {"links": {"items": [INSPECTION], "max_stay_seconds": 90, "memo": "残す"}}
    c = client(tmp_path, original)
    assert c.post("/api/admin-settings", json=body()).status_code == 200  # 古い画面: links を送らない
    assert saved(tmp_path)["links"] == original["links"]
    # 秒数だけ送ると、そこだけ変わる。items だけ送っても同じ
    assert c.post("/api/admin-settings", json=body({"max_stay_seconds": 120})).status_code == 200
    assert saved(tmp_path)["links"] == {"items": [INSPECTION], "max_stay_seconds": 120, "memo": "残す"}
    assert c.post("/api/admin-settings", json=body({"items": [OTHER]})).status_code == 200
    assert saved(tmp_path)["links"] == {"items": [OTHER], "max_stay_seconds": 120, "memo": "残す"}


def test_other_keys_are_preserved_when_saving_links(tmp_path):
    original = {
        "company_name": "テスト(株)", "default_theme": "dark", "accident_folder": "事例", "memo": "手書き",
        "telop": {"speed": 100, "folder": "お知らせ"}, "standby": {"start": "19:00", "end": "07:00", "wake_idle_seconds": 10},
        "documents": {"buttons": [{"label": "旧", "folder": "old"}], "idle_return_seconds": 45},
        "server": {"host": "0.0.0.0", "port": 5105},
    }
    c = client(tmp_path, original)
    assert c.post("/api/admin-settings", json=body({"items": [INSPECTION], "max_stay_seconds": 100})).status_code == 200
    got = saved(tmp_path)
    for key in ("company_name", "default_theme", "accident_folder", "memo", "standby", "server"):
        assert got[key] == original[key], key
    assert got["documents"]["idle_return_seconds"] == 45 and got["documents"]["buttons"] == DOCS["buttons"]
    assert got["links"] == {"items": [INSPECTION], "max_stay_seconds": 100}


def test_validator_returns_normalized_values_only_for_sent_fields():
    clean = clean_admin_settings(body({"items": [{"label": " A ", "url": "http://a/"}, {"label": "", "url": ""}]}))
    assert clean["links"] == {"items": [{"label": "A", "url": "http://a/"}]}
    assert "links" not in clean_admin_settings(body())
    assert clean_admin_settings(body({"max_stay_seconds": 61}))["links"] == {"max_stay_seconds": 61}


def test_backup_is_created_when_links_are_saved(tmp_path):
    c = client(tmp_path, {"company_name": "元の会社"})
    before = cfg_bytes(tmp_path)
    assert c.post("/api/admin-settings", json=body({"items": [INSPECTION]})).status_code == 200
    found = sorted((tmp_path / "backups").iterdir())
    assert len(found) == 1 and NAME.fullmatch(found[0].name) and found[0].read_bytes() == before


def test_save_log_names_the_group_without_leaking_urls(tmp_path):
    c = client(tmp_path)
    secret = {"label": "秘密のラベル", "url": "http://secret-host.example/token123"}
    assert c.post("/api/admin-settings", json=body({"items": [secret], "max_stay_seconds": 77})).status_code == 200
    log = (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")
    assert "設定を保存しました" in log and "リンク" in log
    assert "secret-host" not in log and "token123" not in log and "秘密のラベル" not in log


# ---- 管理者キー（従来どおり） ----

def test_admin_key_rules_still_apply_to_links(tmp_path):
    app = make(tmp_path)
    c = app.test_client()
    links = {"items": [INSPECTION], "max_stay_seconds": 100}
    r = c.post("/api/admin-settings", json=body(links), environ_overrides=LAN)
    assert r.status_code == 403 and not (tmp_path / "config.json").exists()
    r = c.post("/api/admin-settings", json=body(links), headers={"X-Admin-Key": "wrong"}, environ_overrides=LAN)
    assert r.status_code == 403 and not (tmp_path / "config.json").exists()
    key = app.config["ADMIN_KEY"]
    r = c.post("/api/admin-settings", json=body(links), headers={"X-Admin-Key": key}, environ_overrides=LAN)
    assert r.status_code == 200
    assert saved(tmp_path)["links"] == {"items": [INSPECTION], "max_stay_seconds": 100}
    # 本体に問題があっても、キーが無ければ中身については答えない（403のまま）
    r = c.post("/api/admin-settings", json=body({"items": [{"label": "A", "url": "javascript:x"}]}), environ_overrides=LAN)
    assert r.status_code == 403
    r = c.post("/api/admin-settings", json=body({"items": [{"label": "A", "url": "javascript:x"}]}), headers={"X-Admin-Key": key}, environ_overrides=LAN)
    assert r.status_code == 400


# ---- /api/board ----

def test_board_exposes_links(tmp_path):
    assert client(tmp_path).get("/api/board").get_json()["links"] == DEFAULT_LINKS
    c = client(tmp_path / "b", {"links": {"items": [INSPECTION, OTHER], "max_stay_seconds": 600}})
    assert c.get("/api/board").get_json()["links"] == {"items": [INSPECTION, OTHER], "max_stay_seconds": 600}


def test_board_hand_edited_bad_links_fall_back_and_warn(tmp_path):
    c = client(tmp_path, {"links": {"items": [{"label": "悪い", "url": "javascript:alert(1)"}, INSPECTION], "max_stay_seconds": 5}})
    j = c.get("/api/board").get_json()
    assert j["links"] == {"items": [INSPECTION], "max_stay_seconds": 300}
    assert any("links" in w for w in j["warnings"])


# ---- 画面（静的な確認） ----

def _get(tmp_path, path):
    return create_app(tmp_path).test_client().get(path).get_data(as_text=True)


def test_html_has_link_row_above_documents_and_the_overlay_with_iframe(tmp_path):
    html = _get(tmp_path, "/")
    assert html.index('id="link-buttons"') < html.index('id="doc-buttons"')
    assert re.search(r'<div id="link-buttons"[^>]*\bhidden\b', html)
    view = html[html.index('id="link-view"'):html.index('id="settings"')]
    assert 'class="overlay"' in html[html.index('id="link-view"'):html.index('id="link-view"') + 60]
    assert "<iframe" in view and 'referrerpolicy="no-referrer"' in view
    assert 'id="link-title"' in view and "掲示板へ戻る" in view and 'id="link-back"' in view
    anchor = re.search(r'<a [^>]*id="link-newtab"[^>]*>', view)
    assert anchor and 'target="_blank"' in anchor[0] and 'rel="noopener noreferrer"' in anchor[0]
    assert "開けないときは別のタブで開く" in view
    assert "src=" not in view  # 設定のURLは JS が確かめてから入れる


def test_settings_has_link_rows_stay_and_hints(tmp_path):
    html = _get(tmp_path, "/")
    settings = html[html.index('id="settings"'):html.index('id="standby"')]
    shared = settings[settings.index("全端末共通"):]
    assert "リンクボタン（最大2つ）" in shared
    assert shared.index("リンクボタン（最大2つ）") < shared.index('id="link-label-0"') < shared.index('id="settings-save"')
    for i in (0, 1):
        assert f'id="link-label-{i}"' in shared and f'id="link-url-{i}"' in shared
    assert 'placeholder="例: 設備点検システム"' in shared
    assert 'placeholder="例: http://サーバーPC名:5000/"' in shared
    assert 'maxlength="100"' in shared[shared.index('id="link-label-0"') - 60:shared.index('id="link-label-0"') + 120]
    assert 'maxlength="500"' in shared[shared.index('id="link-url-0"') - 60:shared.index('id="link-url-0"') + 160]
    assert "最大滞在（秒）" in shared and 'id="link-stay"' in shared
    assert settings.count('id="settings-save"') == 1  # 既存の「保存して適用」で保存する


def test_links_module_is_served_and_wired(tmp_path):
    c = create_app(tmp_path).test_client()
    r = c.get("/js/links.js")
    assert r.status_code == 200 and "javascript" in r.content_type
    links = r.get_data(as_text=True)
    for needle in ["export function isSafeUrl", "export function buildLinkList", "export function clampStay", "about:blank",
                   "textContent", "setAttribute"]:
        assert needle in links, needle
    assert "innerHTML" not in links  # 設定の文字を HTML として入れない
    board = c.get("/js/board.js").get_data(as_text=True)
    assert 'from "./links.js"' in board and "renderLinkButtons(state.links)" in board
    # 開くと災害事例を止め、閉じると再開。スリープに入るときは閉じる（再開はしない）
    assert "pauseAccident" in board[board.index("initLinks("):board.index("initLinks(") + 200]
    assert "resumeAccident" in board[board.index("initLinks("):board.index("initLinks(") + 200]
    assert "closeLink(" in board[board.index("initStandby("):]
    admin = c.get("/js/admin-settings.js").get_data(as_text=True)
    for needle in ["links", "max_stay_seconds", "link-label-", "link-url-", "link-stay", "isSafeUrl"]:
        assert needle in admin, needle
    assert "X-Admin-Key" in admin


def test_css_has_link_row_and_overlay_between_picker_and_sleep(tmp_path):
    css = _get(tmp_path, "/board.css")
    assert "#link-buttons" in css and ".link-btn" in css and "#link-view" in css
    assert re.search(r"#documents,\s*#link-view\s*\{[^}]*z-index:\s*20", css)
    assert "#standby { flex-direction: column; z-index: 30" in css
    assert ".link-btn" in css[css.index("#link-buttons"):] and "text-overflow: ellipsis" in css


# ---- 修正: URL に ユーザー名:パスワード@ は使えない（JS と同じ表） ----

URL_CASES = json.loads((Path(__file__).parent / "link_url_cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("bad", URL_CASES["ng"])
def test_userinfo_url_is_rejected_on_load_and_on_save(tmp_path, bad):
    cfg = load_config(write_cfg(tmp_path, {"links": {"items": [{"label": "悪い", "url": bad}, INSPECTION]}}))
    assert cfg["links"]["items"] == [INSPECTION]
    assert len(cfg["_warnings"]) == 1 and "1番目" in cfg["_warnings"][0]
    with pytest.raises(ValueError):
        clean_admin_settings(body({"items": [{"label": "悪い", "url": bad}]}))


@pytest.mark.parametrize("good", URL_CASES["ok"])
def test_at_sign_outside_the_host_part_is_fine(tmp_path, good):
    cfg = load_config(write_cfg(tmp_path, {"links": {"items": [{"label": "良い", "url": good}]}}))
    assert cfg["links"]["items"] == [{"label": "良い", "url": good}] and cfg["_warnings"] == []
    assert clean_admin_settings(body({"items": [{"label": "良い", "url": good}]}))["links"]["items"] == [{"label": "良い", "url": good}]


# ---- 修正: ラベル（リンク・文書）に改行・タブ・制御文字は使えない ----

BAD_LABELS = ["a\nb", "a\tb", "a\x00b", "a\x1bb", "a​b", "a\x7fb", "a\r\nb"]


@pytest.mark.parametrize("bad", BAD_LABELS, ids=[repr(b) for b in BAD_LABELS])
def test_link_label_with_control_chars_is_skipped_on_load_and_refused_on_save(tmp_path, bad):
    cfg = load_config(write_cfg(tmp_path, {"links": {"items": [{"label": bad, "url": "http://a/"}, INSPECTION]}}))
    assert cfg["links"]["items"] == [INSPECTION]
    assert len(cfg["_warnings"]) == 1 and "links" in cfg["_warnings"][0]
    with pytest.raises(ValueError, match="使えない文字"):
        clean_admin_settings(body({"items": [{"label": bad, "url": "http://a/"}]}))


@pytest.mark.parametrize("bad", BAD_LABELS, ids=[repr(b) for b in BAD_LABELS])
def test_document_label_with_control_chars_is_skipped_on_load_and_refused_on_save(tmp_path, bad):
    good = {"label": "良い", "folder": "documents/doc9"}
    cfg = load_config(write_cfg(tmp_path, {"documents": {"buttons": [{"label": bad, "folder": "documents/x"}, good]}}))
    assert cfg["documents"]["buttons"] == [good]
    assert len(cfg["_warnings"]) == 1 and "documents.buttons" in cfg["_warnings"][0]
    with pytest.raises(ValueError, match="使えない文字"):
        clean_admin_settings({"documents": {"buttons": [{"label": bad, "folder": "documents/x"}]}, "telop": {"speed": 100}})


def test_labels_with_ordinary_symbols_and_surrounding_whitespace_are_still_fine(tmp_path):
    cfg = load_config(write_cfg(tmp_path, {"links": {"items": [{"label": "  点検（A）・B  \n", "url": "http://a/"}]}}))
    assert cfg["links"]["items"] == [{"label": "点検（A）・B", "url": "http://a/"}]


# ---- 修正: 枠（iframe）の権限 / 設定画面の説明 ----

def test_iframe_sandbox_allows_the_page_to_work_but_not_to_navigate_the_board(tmp_path):
    html = _get(tmp_path, "/")
    frame = re.search(r'<iframe id="link-frame"[^>]*>', html)[0]
    m = re.search(r'sandbox="([^"]*)"', frame)
    assert m, frame
    got = m[1].split()
    assert sorted(got) == sorted("allow-scripts allow-forms allow-same-origin allow-popups allow-popups-to-escape-sandbox allow-modals allow-downloads".split())
    assert "allow-top-navigation" not in frame and "allow-top-navigation-by-user-activation" not in frame


def test_link_hint_and_placeholder_do_not_say_localhost(tmp_path):
    html = _get(tmp_path, "/")
    shared = html[html.index('id="settings"'):html.index('id="standby"')]
    shared = shared[shared.index("全端末共通"):]
    hint = ("設備点検システム（equipment-inspection）の画面を開くには、サーバーPCの名前かIPアドレスで書きます"
            "（例: http://サーバーPC名:5000/）。設備点検システム側は、他のPCから開けるように設定しておく必要があります")
    assert hint in shared
    assert shared.count('placeholder="例: http://サーバーPC名:5000/"') == 2
    assert "localhost" not in shared[shared.index("リンクボタン（最大2つ）"):shared.index('id="settings-save"')]


# ---- 修正: 閉じる前の警告（「あと30秒で戻ります」「続ける」） ----

def test_link_overlay_has_the_warning_notice_with_a_continue_button(tmp_path):
    html = _get(tmp_path, "/")
    view = html[html.index('id="link-view"'):html.index('id="settings"')]
    warn = re.search(r'<div id="link-warn"[^>]*>.*?</div>', view, re.S)
    assert warn and re.search(r"\bhidden\b", warn[0][:60])
    assert "あと30秒で戻ります" in warn[0] and 'id="link-continue"' in warn[0] and "続ける" in warn[0]
    assert view.index('id="link-warn"') < view.index('id="link-back"')
    css = _get(tmp_path, "/board.css")
    assert "#link-warn[hidden]" in css


def test_standby_does_not_sleep_over_an_open_link_and_links_exports_isLinkOpen(tmp_path):
    c = create_app(tmp_path).test_client()
    standby = c.get("/js/standby.js").get_data(as_text=True)
    assert 'from "./links.js"' in standby and "isLinkOpen()" in standby
    assert "export function isLinkOpen" in c.get("/js/links.js").get_data(as_text=True)
