import hmac
import http.client
import json
import logging
import mimetypes
import os
import secrets
import socket
import sys
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote, urlsplit

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException, InternalServerError

import accident as acc
import masters as mst
import telop
from board_db import HOLIDAY_FIELDS, SCHEDULE_FIELDS, BoardDB
from config import DEFAULTS, clean_admin_settings, load_config, save_admin_settings

APP_VERSION = "0.2.0"  # 画面と /api/health に出す。版数の出どころはここだけ
APP_ID = "digital-bulletin-board"  # /api/health に出す。起動.bat が、隣のポートの別アプリと見分けるのに使う
PORT_FILE = "server_port.txt"  # 実際に使っているポート番号。起動.bat が読む
ADMIN_KEY_FILE = "admin_key.txt"
PORT_TRIES = 10  # 設定のポート番号から +9 まで順に空きを探す
LOOPBACK = ("127.0.0.1", "::1")
LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1")  # 管理者キーが要らないのは、接続元が自分自身で、かつ宛先もこの名前のとき

mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("text/javascript", ".js")

LOGGER_NAME = "digital_bulletin_board"
log = logging.getLogger(LOGGER_NAME)
_log_handlers = []  # このアプリが付けたハンドラー（作り直すときに外して閉じる）


def close_logging():
    while _log_handlers:
        h = _log_handlers.pop()
        log.removeHandler(h)
        h.close()  # 開いたままだと、Windows ではログのフォルダを消せなくなる


def setup_logging(log_dir):
    """logs/app.log に書く（1MB × 5世代）。何度呼んでも付くのは1つだけ。ログのフォルダを使えないときは画面（コンソール）だけに出す。"""
    close_logging()
    log.setLevel(logging.INFO)
    log.propagate = False  # waitress が root にもハンドラーを付けるので、流すと警告が画面に二重に出る
    problem = None
    try:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(Path(log_dir) / "app.log", maxBytes=1024 * 1024, backupCount=5, encoding="utf-8")
    except OSError as e:
        problem = e
        handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    log.addHandler(handler)
    _log_handlers.append(handler)
    if problem:
        log.warning("ログフォルダを使えないため、ログは画面（コンソール）だけに出します: %s（%s）", log_dir, problem)


def _read_admin_key(path):
    """キーを返す。ファイルが無い・空なら None。読めない（文字コードなど）ときは OSError / ValueError。"""
    try:
        return path.read_text(encoding="utf-8-sig").strip() or None
    except FileNotFoundError:
        return None


def load_admin_key(path):
    """管理者キーを返す。ファイルが無い・空・読めないときは作り直して保存する（保存できなければ今回の起動だけ有効）。キーはログに書かない。
    保存は一時ファイルに書いてから置く（途中の中身を誰も読まない）。無かったときに作る場合、同時に別の起動が先に作っていたら、そちらを使う。"""
    path = Path(path)
    missing = not path.exists()
    try:
        key = _read_admin_key(path)
        if key:
            return key
    except (OSError, ValueError) as e:
        log.warning("%s を読めないため、管理者キーを作り直します（%s）", ADMIN_KEY_FILE, type(e).__name__)
    key = secrets.token_urlsafe(16)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(key + "\n")
        if not missing:
            os.replace(tmp, path)
        else:
            try:
                os.link(tmp, path)  # 先に誰かが作っていれば FileExistsError（上書きしない）
            except FileExistsError:
                other = _read_admin_key(path)
                if other:
                    return other
                os.replace(tmp, path)
            except OSError:  # ハードリンクを作れない場所。確かめてから置く
                other = _read_admin_key(path) if path.exists() else None
                if other:
                    return other
                os.replace(tmp, path)
    except (OSError, ValueError) as e:
        log.warning("%s に管理者キーを書けませんでした。今回の起動の間だけ有効なキーを使います（%s）", ADMIN_KEY_FILE, type(e).__name__)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
    return key


def bind_port(port, host):
    """そのポートが空いていれば、bind 済みの待ち受け用ソケットを返す（開いたまま。使う側が閉じる）。使用中なら None。
    まず 127.0.0.1 につないでみて、つながれば使用中。Windows では、使用中のポートにも bind が通ってしまうことがあるため。
    （使われていないポートへの接続は Windows だと拒否の返事まで約2秒かかるので、0.3秒で見切る）
    bind は他の起動と共有しない設定（SO_EXCLUSIVEADDRUSE）で行うので、続けて2つ起動しても同じポートを取り合わない。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.3)
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            return None
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
    except OSError:
        s.close()
        return None
    return s


def find_available_socket(preferred, host, tries=PORT_TRIES):
    """preferred から順に tries 個まで調べ、最初に空いていたポートを (ポート番号, bind 済みソケット) で返す。全部使用中なら (None, None)。"""
    for port in range(preferred, preferred + tries):
        sock = bind_port(port, host)
        if sock is not None:
            return port, sock
    return None, None


def _is_our_health(port, timeout):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # 環境のプロキシ設定を通さない
    try:
        with opener.open(f"http://127.0.0.1:{port}/api/health", timeout=timeout) as r:
            body = json.loads(r.read(4096).decode("utf-8"))
    except (OSError, ValueError, http.client.HTTPException):
        return False
    return isinstance(body, dict) and body.get("app") == APP_ID


def find_running_instance(preferred, tries=PORT_TRIES, timeout=0.5):
    """すでにこのアプリが preferred から tries 個のポートのどれかで動いていれば、そのポート番号を返す（無ければ None）。
    /api/health が app: digital-bulletin-board と答えたものだけを、このアプリと見なす。"""
    ports = list(range(preferred, preferred + tries))
    with ThreadPoolExecutor(max_workers=len(ports)) as pool:  # 返事のないポートで待ち時間が積み重ならないよう、いっせいに調べる
        found = list(pool.map(lambda p: _is_our_health(p, timeout), ports))
    return next((p for p, ok in zip(ports, found) if ok), None)


def write_port_file(path, port):
    """使うポート番号だけを書く。書けなくても起動は続ける（起動.bat は既定の番号を使う）。"""
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(f"{port}\n")
        return True
    except OSError as e:
        log.warning("%s を書けませんでした（起動.bat は既定のポートを使います）: %s", PORT_FILE, e)
        return False


def _changed_groups(old, clean):
    """保存で変わる設定の項目名だけを返す（お知らせなどの自由な文字は含めない。フォルダの場所は含める）。"""
    out = []
    new_buttons = clean["documents"]["buttons"]
    if new_buttons != [{"label": b["label"], "folder": b["folder"]} for b in old["documents"]["buttons"]]:
        out.append("文書ボタン（フォルダ: " + ", ".join(b["folder"] for b in new_buttons) + "）")
    if clean["telop"]["speed"] != old["telop"]["speed"]:
        out.append(f"テロップ速度（{clean['telop']['speed']}）")
    if "folder" in clean["telop"] and clean["telop"]["folder"] != old["telop"]["folder"]:
        out.append(f"テロップフォルダ（{clean['telop']['folder']}）")
    if "company_name" in clean and clean["company_name"] != old["company_name"]:
        out.append("会社名")
    for key, label in (("start", "スリープ開始"), ("end", "スリープ終了"), ("wake_idle_seconds", "スリープに戻る秒数")):
        if key in clean.get("standby", {}) and clean["standby"][key] != old["standby"][key]:
            out.append(f"{label}（{clean['standby'][key]}）")
    for key, label in (("accident_seconds", "災害事例の表示秒数"), ("edit_lock_seconds", "編集の自動終了")):
        if key in clean and clean[key] != old[key]:
            out.append(f"{label}（{clean[key]}）")
    idle = clean["documents"].get("idle_return_seconds")
    if idle is not None and idle != old["documents"]["idle_return_seconds"]:
        out.append(f"文書の操作なし戻り（{idle}）")
    if "custom_holidays_file" in clean and clean["custom_holidays_file"] != old["custom_holidays_file"]:
        out.append(f"会社の休日ファイル（{clean['custom_holidays_file']}）")
    links = clean.get("links", {})
    if "items" in links and links["items"] != old["links"]["items"]:
        out.append(f"リンクボタン（{len(links['items'])}件）")  # 名前・アドレスはログに書かない
    if "max_stay_seconds" in links and links["max_stay_seconds"] != old["links"]["max_stay_seconds"]:
        out.append(f"リンクの最大滞在（{links['max_stay_seconds']}）")
    return out


def _resolve(base, p):
    p = Path(p)
    return p if p.is_absolute() else base / p


def _dir_signature(path):
    try:
        return str(Path(path).stat().st_mtime_ns)
    except OSError:
        return "-"


def create_app(base_dir=None, today_func=date.today, port=None, cfg=None, log_ready=False):
    """port は実際に使うポート（ログ用）。省略すると config.json の server.port を書く。
    cfg: 読み込み済みの設定（起動時に1回だけ読むため、main() が渡す）。log_ready: ログの用意が済んでいるとき True。"""
    base = Path(base_dir) if base_dir else Path(__file__).resolve().parent
    config_path = base / "config.json"
    if not log_ready:
        setup_logging(base / "logs")
    admin_key = load_admin_key(base / ADMIN_KEY_FILE)
    data_dir = base / "data"
    data_dir.mkdir(exist_ok=True)
    db = BoardDB(data_dir / "board.db")

    def holidays_source():
        r = live["rt"]
        return r.holidays_file, r.holidays_label

    masters = mst.Masters(data_dir, holidays_source)

    def build_runtime(gen, loaded=None):
        """config.json を読み直し（loaded があればそれを使い）、フォルダの場所などをひとまとめにして返す（フォルダはまだ作らない）。"""
        cfg = loaded or load_config(config_path)
        doc_buttons = cfg["documents"]["buttons"]
        return SimpleNamespace(
            cfg=cfg, gen=gen, problems=[], warnings=list(cfg["_warnings"]),
            accident_dir=_resolve(base, cfg["accident_folder"]),
            doc_buttons=doc_buttons, doc_dirs=[_resolve(base, b["folder"]) for b in doc_buttons],
            telop_dir=_resolve(base, cfg["telop"]["folder"]),
            # 会社の休日ファイル（読むだけ）。既定の場所のときは、無くても警告しない
            holidays_file=_resolve(base, cfg["custom_holidays_file"]),
            holidays_label=None if cfg["custom_holidays_file"] == DEFAULTS["custom_holidays_file"] else cfg["custom_holidays_file"],
        )

    def ensure_folders(r):
        # 時間のかかることがある（ネットワークの場所など）ので、保存の排他（save_lock）の外で呼ぶ。
        # 作れない場所（存在しないドライブなど）でも動きは続ける。中身は空として扱われる
        targets = [(r.accident_dir, "災害事例")]
        targets += [(d, f"文書「{b['label']}」") for b, d in zip(r.doc_buttons, r.doc_dirs)]
        targets.append((r.telop_dir, "お知らせ"))
        for folder, what in targets:
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except (OSError, ValueError) as e:
                r.problems.append((what, folder, e))
                r.warnings.append(f"{what}のフォルダを使えません: {folder}（{e}）")

    # 実行中の設定。保存のたびに丸ごと差し替える（1回の要求の途中で新旧が混ざらないよう、各要求の最初に rt() で取り出す）
    live = {"rt": build_runtime(0, cfg)}
    server_cfg = live["rt"].cfg["server"]
    log.info("デジタル掲示板を起動します（バージョン %s, ホスト %s, ポート %s）", APP_VERSION, server_cfg["host"], port or server_cfg["port"])
    ensure_folders(live["rt"])
    # 起動時の警告は、ここで1回だけ記録する（画面が数秒ごとに読む処理では記録しない）
    for w in live["rt"].warnings + masters.load_all()["warnings"]:
        log.warning("起動時の警告: %s", w)
    save_lock = threading.Lock()

    def rt():
        return live["rt"]

    app = Flask(__name__, static_folder=str(Path(__file__).resolve().parent / "static"), static_url_path="")
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    app.json.ensure_ascii = False
    app.config["ADMIN_KEY"] = admin_key  # 起動時に黒い窓へ出すためだけ。どの API にも載せない

    @app.after_request
    def json_charset(resp):
        if resp.mimetype == "application/json":
            resp.headers["Content-Type"] = "application/json; charset=utf-8"
        return resp

    def bad(message, code=400):
        return jsonify({"error": message}), code

    @app.errorhandler(OverflowError)
    def too_large_id(_e):
        return bad("行が見つかりません", 404)

    api_messages = {
        400: "リクエストが正しくありません",
        404: "見つかりません",
        405: "この操作はできません",
        500: "サーバーでエラーが起きました",
    }

    @app.errorhandler(HTTPException)
    def http_error(e):
        # /api/ のエラーだけ JSON にする（画面のファイルなどは従来どおり）
        if request.path.startswith("/api/"):
            return bad(api_messages.get(e.code, e.name), e.code)
        return e

    @app.errorhandler(Exception)
    def unhandled_error(e):
        log.error("予期しないエラー: %s %s", request.method, request.path, exc_info=e)
        return http_error(InternalServerError())

    def is_local_request():
        """接続元が自分自身で、宛先（Host）も localhost / 127.0.0.1 / ::1 のときだけ True（別の名前で来たものは、中継されたものかもしれない）。"""
        if request.remote_addr not in LOOPBACK:
            return False
        try:
            host = urlsplit("//" + request.headers.get("Host", "")).hostname
        except ValueError:
            return False
        return host in LOOPBACK_HOSTS

    def json_body():
        body = request.get_json(silent=True)
        return body if isinstance(body, dict) else None

    def prepare():
        today = today_func()
        d = today.isoformat()
        db.ensure_day(d)
        # 今週の休日の行を、最初から1日1行ずつ用意しておく（作るのは1回だけ。消した行は戻らない）
        db.seed_holidays([w["date"] for w in mst.week_holidays(today, masters.load_all()["custom_holidays"])])
        return d

    def clean_fields(body, allowed):
        fields = {}
        for key in allowed:
            if key in body:
                if not isinstance(body[key], str):
                    return None
                fields[key] = body[key].strip()
        return fields

    def validate(m, fields, company):
        for key, value in fields.items():
            if value == "":
                continue
            if key in ("company", "person"):
                ok = value in m["companies"]
            elif key == "work":
                ok = value in m["works"]
            elif key == "construction":
                ok = value in m["constructions"]
            elif key in ("start_time", "end_time"):
                ok = value in m["times"]
            elif key == "leader":
                ok = any(l["company"] == company and l["leader_name"] == value for l in m["leaders"])
            else:
                ok = False
            if not ok:
                return f"登録リストにありません: {value}"
        return None

    def apply_work_rule(m, fields, row):
        """作業内容は、その行の工事件名に対応表の登録があるときは、そこから選ぶ（本日の作業予定・休日出勤予定で共通）。
        合わなければ理由を返す。工事件名を変える要求で、保存済みの作業内容が新しい工事件名に合わないときは、同じ更新で空にする。"""
        allowed = m["construction_works"].get(fields.get("construction", row["construction"]))
        if not allowed:
            return None
        if "work" in fields:
            if fields["work"] and fields["work"] not in allowed:
                return f"この工事件名では選べない作業内容です: {fields['work']}"
        elif fields.get("construction", row["construction"]) != row["construction"] and row["work"] not in allowed:
            fields["work"] = ""
        return None

    def week_holidays(m):
        return mst.week_holidays(today_func(), m["custom_holidays"])

    def is_week_holiday(value, m):
        # 今週の休日一覧にある「YYYY-MM-DD」と完全一致するものだけを受け付ける
        return isinstance(value, str) and value in {w["date"] for w in week_holidays(m)}

    # ---- 画面 ----
    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "board.html")

    @app.get("/api/rev")
    def api_rev():
        r = rt()
        rev = ":".join(
            [
                str(db.get_rev()),
                masters.signature(),
                _dir_signature(r.accident_dir),
                telop.signature(r.telop_dir),
                f"{r.gen}-{_dir_signature(config_path)}",
            ]
        )
        return jsonify({"rev": rev, "today": today_func().isoformat()})

    @app.get("/api/health")
    def api_health():
        return jsonify({"status": "ok", "version": APP_VERSION, "app": APP_ID})

    @app.get("/api/telop")
    def api_telop():
        return jsonify({"items": telop.read_items(rt().telop_dir)})

    # ---- 全端末共通の設定（文書ボタン・お知らせ・スリープと時間・会社の休日ファイル・リンクボタン） ----
    @app.get("/api/admin-settings")
    def api_get_admin_settings():
        cfg = rt().cfg
        return jsonify(
            {
                "documents": {
                    "buttons": [{"label": b["label"], "folder": b["folder"]} for b in cfg["documents"]["buttons"]],
                    "idle_return_seconds": cfg["documents"]["idle_return_seconds"],
                },
                "telop": {"speed": cfg["telop"]["speed"], "folder": cfg["telop"]["folder"]},
                "company_name": cfg["company_name"],
                "standby": dict(cfg["standby"]),
                "accident_seconds": cfg["accident_seconds"],
                "edit_lock_seconds": cfg["edit_lock_seconds"],
                "custom_holidays_file": cfg["custom_holidays_file"],
                "links": {"items": [dict(i) for i in cfg["links"]["items"]], "max_stay_seconds": cfg["links"]["max_stay_seconds"]},
            }
        )

    @app.post("/api/admin-settings")
    def api_post_admin_settings():
        # 別のPCから変えるときだけ管理者キーが要る。本文を見る前に確かめる（キーが違うとき、中身については何も答えない）
        if not is_local_request():
            sent = request.headers.get("X-Admin-Key", "")
            if not sent:
                log.warning("設定の保存を拒否しました: 管理者キーがありません（接続元 %s）", request.remote_addr)
                return bad("管理者キーが必要です（サーバーPCの黒い窓、または admin_key.txt に書かれています）", 403)
            if not hmac.compare_digest(sent.encode("utf-8"), admin_key.encode("utf-8")):
                log.warning("設定の保存を拒否しました: 管理者キーが違います（接続元 %s）", request.remote_addr)
                return bad("管理者キーが違います", 403)
        try:
            clean = clean_admin_settings(json_body())
        except ValueError as e:
            log.warning("設定の保存を拒否しました: %s", e)
            return bad(str(e))
        with save_lock:
            changed = _changed_groups(rt().cfg, clean)
            try:
                save_admin_settings(config_path, clean)
            except ValueError as e:  # config.json に書き間違いがある（利用者の設定を消さないよう保存しない）
                log.warning("設定の保存を拒否しました: %s", e)
                return bad(str(e))
            except OSError as e:
                log.error("設定を保存できませんでした: %s", e)
                return bad(f"設定ファイルを読めない、または保存できませんでした（{e.strerror or e}）", 500)
            live["rt"] = new = build_runtime(rt().gen + 1)
        log.info("設定を保存しました（変更: %s）", "、".join(changed) or "変更なし")
        ensure_folders(new)
        warnings = [f"{what}のフォルダを作れませんでした: {folder}" for what, folder, _e in new.problems if what != "災害事例"]
        for w in warnings:
            log.warning("%s", w)
        return jsonify({"ok": True, "warnings": warnings} if warnings else {"ok": True})

    @app.get("/api/board")
    def api_board():
        cur = rt()
        cfg = cur.cfg
        d = prepare()
        today = today_func()
        m = masters.load_all()
        monday, sunday = mst.week_range(today)

        schedule = []
        for r in db.list_schedule(d):
            leader = next(
                (l for l in m["leaders"] if l["company"] == r["company"] and l["leader_name"] == r["leader"]),
                None,
            )
            r["ext"] = leader["ext"] if leader else ""
            r["outside"] = leader["outside"] if leader else ""
            schedule.append(r)

        holiday_rows = []
        for r in db.list_holiday_rows(monday.isoformat(), sunday.isoformat()):
            day = date.fromisoformat(r["date"])
            info = mst.holiday_info(day, m["custom_holidays"])
            r["label"] = mst.date_label(day, info["name"])
            r["kind"] = info["kind"]
            holiday_rows.append(r)

        checked = [g for g in db.get_checked_genres(d) if g in m["genres"]]
        names = acc.playlist(cur.accident_dir, m["genres"], set(checked))
        return jsonify(
            {
                "today": d,
                "date_label": mst.day_title(today),
                "company_name": cfg["company_name"],
                "settings": {
                    "accident_seconds": cfg["accident_seconds"],
                    "edit_lock_seconds": cfg["edit_lock_seconds"],
                    "documents_idle_seconds": cfg["documents"]["idle_return_seconds"],
                    "default_theme": cfg["default_theme"],
                    "default_edit_button": cfg["default_edit_button"],
                    "standby": cfg["standby"],
                    "telop": {"speed": cfg["telop"]["speed"]},
                },
                "notices": db.list_notices(d),
                "schedule": schedule,
                "holiday_rows": holiday_rows,
                "week_holidays": week_holidays(m),
                "checked_genres": checked,
                "accident": [{"name": n, "url": "/api/accident/file/" + quote(n)} for n in names],
                "masters": {k: m[k] for k in ("companies", "leaders", "works", "constructions", "genres", "times", "construction_works")},
                "doc_buttons": [{"index": i, "label": b["label"]} for i, b in enumerate(cur.doc_buttons)],
                "links": {"items": [dict(i) for i in cfg["links"]["items"]], "max_stay_seconds": cfg["links"]["max_stay_seconds"]},
                "warnings": cur.warnings + m["warnings"],
            }
        )

    # ---- 連絡事項 ----
    @app.post("/api/notices")
    def api_add_notice():
        return jsonify({"id": db.add_notice(prepare())})

    @app.patch("/api/notices/<int:row_id>")
    def api_patch_notice(row_id):
        d = prepare()
        if not any(n["id"] == row_id for n in db.list_notices(d)):
            return bad("行が見つかりません", 404)
        body = json_body()
        if body is None:
            return bad("JSONオブジェクトが必要です")
        fields = {}
        if "text" in body:
            if not isinstance(body["text"], str):
                return bad("text は文字列です")
            fields["text"] = body["text"].strip()
        if "red" in body:
            fields["red"] = 1 if body["red"] else 0
        if not fields:
            return bad("更新する項目がありません")
        if not db.update_notice(row_id, fields):
            return bad("行が見つかりません", 404)
        return jsonify({"ok": True})

    @app.delete("/api/notices/<int:row_id>")
    def api_delete_notice(row_id):
        prepare()
        try:
            found = db.delete_notice(row_id)
        except ValueError as e:
            return bad(str(e))
        if not found:
            return bad("行が見つかりません", 404)
        return jsonify({"ok": True})

    # ---- 本日の作業予定 ----
    @app.post("/api/schedule")
    def api_add_schedule():
        return jsonify({"id": db.add_schedule_row(prepare())})

    @app.patch("/api/schedule/<int:row_id>")
    def api_patch_schedule(row_id):
        prepare()
        row = db.get_schedule_row(row_id)
        if row is None:
            return bad("行が見つかりません", 404)
        body = json_body()
        if body is None:
            return bad("JSONオブジェクトが必要です")
        fields = clean_fields(body, SCHEDULE_FIELDS)
        if fields is None:
            return bad("値が文字列ではありません")
        if not fields:
            return bad("更新する項目がありません")
        if "company" in fields and fields["company"] != row["company"] and "leader" not in fields:
            fields["leader"] = ""
        company = fields.get("company", row["company"])
        m = masters.load_all()
        error = validate(m, fields, company) or apply_work_rule(m, fields, row)
        if error:
            return bad(error)
        db.update_schedule_row(row_id, fields)
        return jsonify({"ok": True})

    @app.delete("/api/schedule/<int:row_id>")
    def api_delete_schedule(row_id):
        prepare()
        if not db.delete_schedule_row(row_id):
            return bad("行が見つかりません", 404)
        return jsonify({"ok": True})

    @app.post("/api/schedule/<int:row_id>/move")
    def api_move_schedule(row_id):
        prepare()
        if db.get_schedule_row(row_id) is None:
            return bad("行が見つかりません", 404)
        direction = (json_body() or {}).get("direction")
        if direction not in ("up", "down"):
            return bad("direction は up / down")
        db.move_schedule_row(row_id, direction)
        return jsonify({"ok": True})

    # ---- 休日出勤予定 ----
    @app.post("/api/holiday-rows")
    def api_add_holiday():
        prepare()
        date_str = (json_body() or {}).get("date")
        if not is_week_holiday(date_str, masters.load_all()):
            return bad("今週の休日ではありません")
        return jsonify({"id": db.add_holiday_row(date_str)})

    @app.patch("/api/holiday-rows/<int:row_id>")
    def api_patch_holiday(row_id):
        prepare()
        row = db.get_holiday_row(row_id)
        if row is None:
            return bad("行が見つかりません", 404)
        body = json_body()
        if body is None:
            return bad("JSONオブジェクトが必要です")
        fields = clean_fields(body, HOLIDAY_FIELDS)
        if fields is None:
            return bad("値が文字列ではありません")
        if not fields:
            return bad("更新する項目がありません")
        m = masters.load_all()
        if "date" in fields:
            if not is_week_holiday(fields["date"], m):
                return bad("今週の休日ではありません")
            fields_to_check = {k: v for k, v in fields.items() if k != "date"}
        else:
            fields_to_check = fields
        error = validate(m, fields_to_check, None) or apply_work_rule(m, fields, row)
        if error:
            return bad(error)
        db.update_holiday_row(row_id, fields)
        return jsonify({"ok": True})

    @app.delete("/api/holiday-rows/<int:row_id>")
    def api_delete_holiday(row_id):
        prepare()
        if not db.delete_holiday_row(row_id):
            return bad("行が見つかりません", 404)
        return jsonify({"ok": True})

    # ---- 作業ジャンル ----
    @app.post("/api/genres/toggle")
    def api_toggle_genre():
        d = prepare()
        body = json_body() or {}
        name = body.get("name")
        if not isinstance(name, str) or name not in masters.load_all()["genres"]:
            return bad("登録されていないジャンルです")
        db.set_genre(d, name, bool(body.get("checked")))
        return jsonify({"ok": True})

    # ---- ファイル配信 ----
    def send_listed_pdf(folder, name):
        # 実際のファイル一覧にある名前だけを返す（../ や サブフォルダ指定は一覧に無いので404）
        if name not in acc.list_pdfs(folder):
            return bad("ファイルがありません", 404)
        return send_from_directory(folder, name)

    @app.get("/api/accident/file/<path:name>")
    def api_accident_file(name):
        return send_listed_pdf(rt().accident_dir, name)

    def doc_dir(idx):
        dirs = rt().doc_dirs
        return dirs[idx] if 0 <= idx < len(dirs) else None

    @app.get("/api/documents/<int:idx>/files")
    def api_doc_files(idx):
        folder = doc_dir(idx)
        if folder is None:
            return bad("文書ボタンがありません", 404)
        return jsonify(acc.list_pdfs(folder))

    @app.get("/api/documents/<int:idx>/pdf/<path:name>")
    def api_doc_pdf(idx, name):
        folder = doc_dir(idx)
        if folder is None:
            return bad("文書ボタンがありません", 404)
        return send_listed_pdf(folder, name)

    return app


def _lan_address():
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "サーバーのIPアドレス"


def _port_file_number(path):
    try:
        return int(Path(path).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def main(base=None, serve_func=None):
    """起動の流れ。終了コードを返す（0: 正常 / すでに起動済み、1: 空きポートなし）。serve_func は試験用に差し替えられる。"""
    base = Path(base) if base else Path(__file__).resolve().parent
    setup_logging(base / "logs")
    cfg = load_config(base / "config.json")
    host, preferred = cfg["server"]["host"], cfg["server"]["port"]
    port_file = base / PORT_FILE
    running = find_running_instance(preferred)
    if running is not None:  # 2つ目のサーバーは起動しない。起動.bat は、動いているほうを開く
        print(f"すでに起動しています: http://localhost:{running}")
        log.info("すでに起動しています: http://localhost:%s（2つ目は起動しません）", running)
        if _port_file_number(port_file) != running:
            write_port_file(port_file, running)
        return 0
    port, sock = find_available_socket(preferred, host)
    if port is None:
        msg = f"ポート {preferred}～{preferred + PORT_TRIES - 1} がすべて使用中のため起動できません"
        print(f"エラー: {msg}")
        print("  ほかのアプリを終了するか、config.json の server の port を変えてから、もう一度起動してください")
        log.error(msg)
        return 1
    try:
        if port != preferred:
            msg = f"ポート {preferred} は使用中のため、ポート {port} で起動します"
            print(f"注意: {msg}")
            log.warning(msg)
        write_port_file(port_file, port)  # 起動.bat が開く先を知るため。待ち受けを始める前に書く
        app = create_app(base, port=port, cfg=cfg, log_ready=True)
        print("デジタル掲示板を起動します")
        print(f"  このPCで開く: http://localhost:{port}")
        if host not in ("127.0.0.1", "localhost"):
            print(f"  他のPCで開く: http://{_lan_address()}:{port}")
        print(f"  管理者キー: {app.config['ADMIN_KEY']}（他のPCから全端末共通の設定を変えるときに使います）")
        print("  終了するときは Ctrl + C を押してください")
        if serve_func is None:
            from waitress import serve as serve_func
        try:
            serve_func(app, sockets=[sock], threads=4)  # bind 済みのソケットを渡す（ポートを取ってから起動までの間に横取りされない）
        except Exception:
            log.exception("サーバーが異常終了しました")
            raise
        log.info("デジタル掲示板を終了しました")
        return 0
    finally:
        sock.close()


if __name__ == "__main__":
    sys.exit(main())
