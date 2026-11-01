import mimetypes
import socket
import threading
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

import accident as acc
import masters as mst
import telop
from board_db import HOLIDAY_FIELDS, SCHEDULE_FIELDS, BoardDB
from config import clean_admin_settings, load_config, save_admin_settings

PORT = 5100
APP_VERSION = "0.1.0"  # 画面と /api/health に出す。版数の出どころはここだけ

mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("text/javascript", ".js")


def _resolve(base, p):
    p = Path(p)
    return p if p.is_absolute() else base / p


def _dir_signature(path):
    try:
        return str(Path(path).stat().st_mtime_ns)
    except OSError:
        return "-"


def create_app(base_dir=None, today_func=date.today):
    base = Path(base_dir) if base_dir else Path(__file__).resolve().parent
    config_path = base / "config.json"
    data_dir = base / "data"
    data_dir.mkdir(exist_ok=True)
    db = BoardDB(data_dir / "board.db")
    masters = mst.Masters(data_dir)

    def build_runtime(gen):
        """config.json を読み直し、フォルダの場所などをひとまとめにして返す（フォルダはまだ作らない）。"""
        cfg = load_config(config_path)
        doc_buttons = cfg["documents"]["buttons"]
        return SimpleNamespace(
            cfg=cfg, gen=gen, problems=[], warnings=list(cfg["_warnings"]),
            accident_dir=_resolve(base, cfg["accident_folder"]),
            doc_buttons=doc_buttons, doc_dirs=[_resolve(base, b["folder"]) for b in doc_buttons],
            telop_dir=_resolve(base, cfg["telop"]["folder"]),
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
    live = {"rt": build_runtime(0)}
    ensure_folders(live["rt"])
    save_lock = threading.Lock()

    def rt():
        return live["rt"]

    app = Flask(__name__, static_folder=str(Path(__file__).resolve().parent / "static"), static_url_path="")
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    app.json.ensure_ascii = False

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

    def json_body():
        body = request.get_json(silent=True)
        return body if isinstance(body, dict) else None

    def prepare():
        d = today_func().isoformat()
        db.ensure_day(d)
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
        return jsonify({"status": "ok", "version": APP_VERSION})

    @app.get("/api/telop")
    def api_telop():
        return jsonify({"items": telop.read_items(rt().telop_dir)})

    # ---- 全端末共通の設定（文書ボタン・お知らせ） ----
    @app.get("/api/admin-settings")
    def api_get_admin_settings():
        cfg = rt().cfg
        return jsonify(
            {
                "documents": {"buttons": [{"label": b["label"], "folder": b["folder"]} for b in cfg["documents"]["buttons"]]},
                "telop": {"speed": cfg["telop"]["speed"], "folder": cfg["telop"]["folder"]},
                "company_name": cfg["company_name"],
            }
        )

    @app.post("/api/admin-settings")
    def api_post_admin_settings():
        try:
            clean = clean_admin_settings(json_body())
        except ValueError as e:
            return bad(str(e))
        with save_lock:
            try:
                save_admin_settings(config_path, clean)
            except ValueError as e:  # config.json に書き間違いがある（利用者の設定を消さないよう保存しない）
                return bad(str(e))
            except OSError as e:
                return bad(f"設定ファイルを読めない、または保存できませんでした（{e.strerror or e}）", 500)
            live["rt"] = new = build_runtime(rt().gen + 1)
        ensure_folders(new)
        warnings = [f"{what}のフォルダを作れませんでした: {folder}" for what, folder, _e in new.problems if what != "災害事例"]
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
                "masters": {k: m[k] for k in ("companies", "leaders", "works", "constructions", "genres", "times")},
                "doc_buttons": [{"index": i, "label": b["label"]} for i, b in enumerate(cur.doc_buttons)],
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
        error = validate(masters.load_all(), fields, company)
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
        if db.get_holiday_row(row_id) is None:
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
        error = validate(m, fields_to_check, None)
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


if __name__ == "__main__":
    from waitress import serve

    print("デジタル掲示板を起動します")
    print(f"  このPCで開く: http://localhost:{PORT}")
    print(f"  他のPCで開く: http://{_lan_address()}:{PORT}")
    print("  終了するときは Ctrl + C を押してください")
    serve(create_app(), host="0.0.0.0", port=PORT, threads=4)
