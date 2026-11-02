import copy
import json
import logging
import math
import os
import re
import shutil
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

logger = logging.getLogger("digital_bulletin_board.config")  # 出力先は app.py の setup_logging が決める

DEFAULTS = {
    "company_name": "サンプル工業(株)",
    "manager_title": "",
    "manager_name": "",
    "manager_phone": "",
    "default_theme": "light",
    "default_edit_button": "off",
    "accident_folder": "accident_cases",
    "accident_seconds": 15,
    "documents": {
        "buttons": [
            {"label": "文書1", "folder": "documents/doc1"},
            {"label": "文書2", "folder": "documents/doc2"},
            {"label": "文書3", "folder": "documents/doc3"},
        ],
        "idle_return_seconds": 120,
    },
    "edit_lock_seconds": 60,
    "telop": {"speed": 100, "folder": "telop"},
    "links": {"items": [], "max_stay_seconds": 300},
    "standby": {"start": "18:00", "end": "08:00", "wake_idle_seconds": 300},
    "custom_holidays_file": "data/custom_holidays.csv",
    "whiteboard_save_folder": "whiteboard",
    "whiteboard_pdf_folder": "whiteboard_pdfs",
    "whiteboard_idle_seconds": 180,
    "server": {"host": "0.0.0.0", "port": 5100},  # 起動時に1回だけ読む（変えたら再起動）
}

MAX_BUTTONS = 5
MIN_PORT = 1024
MAX_PORT = 65526  # 起動時に空きを探して +9 まで使うため、65535 までに収まる上限
MAX_SECONDS = 86400
MAX_TEXT = 100
MAX_LINKS = 2
MAX_URL = 500
MIN_STAY = 60
MAX_STAY = 3600
MIN_WB_IDLE = 30
MAX_WB_IDLE = 3600
MAX_PATH = 260  # フォルダの場所（ネットワークの共有などは長くなる）
BROKEN_CONFIG_MESSAGE = "config.json に書き間違いがあります。直してから保存してください"
BACKUP_KEEP = 5
_BACKUP_NAME = re.compile(r"config_(\d{8}_\d{6})(?:_(\d+))?\.json")
MIN_SPEED = 20
MAX_SPEED = 500
_BAD = object()


def _seconds(v):
    try:
        ok = isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
    except OverflowError:
        return _BAD
    return v if ok and 1 <= v <= MAX_SECONDS else _BAD


def _text(v, limit=MAX_TEXT):
    if not isinstance(v, str):
        return _BAD
    v = v.strip()
    return v if v and len(v) <= limit and "\0" not in v else _BAD


def _optional_text(v, limit=MAX_TEXT):
    """空欄も正しい文字（全体責任者・電話番号用）。"""
    if not isinstance(v, str):
        return _BAD
    v = v.strip()
    return v if len(v) <= limit and "\0" not in v else _BAD


def _has_control(v):
    return any(unicodedata.category(ch).startswith("C") for ch in v)


def _bad_chars(v):
    """文字列で、前後の空白を除いた中に制御文字（改行・タブ・NUL など）があるか。"""
    return isinstance(v, str) and _has_control(v.strip())


def _label(v):
    """ボタンの名前。_text の決まりに加えて、改行・タブ・制御文字を含まない（会社名と同じ決まり）。"""
    v = _text(v)
    return _BAD if v is not _BAD and _has_control(v) else v


def _host(v):
    """待ち受けのホスト。IPv6 のアドレス（「:」を含むもの）は扱わない。"""
    v = _text(v)
    return _BAD if v is not _BAD and ":" in v else v


def _path(v):
    return _text(v, MAX_PATH)


def _speed(v):
    return v if isinstance(v, int) and not isinstance(v, bool) and MIN_SPEED <= v <= MAX_SPEED else _BAD


def _port(v):
    return v if isinstance(v, int) and not isinstance(v, bool) and MIN_PORT <= v <= MAX_PORT else _BAD


def _stay(v):
    return v if isinstance(v, int) and not isinstance(v, bool) and MIN_STAY <= v <= MAX_STAY else _BAD


def _wb_idle(v):
    return v if isinstance(v, int) and not isinstance(v, bool) and MIN_WB_IDLE <= v <= MAX_WB_IDLE else _BAD


def _url(v):
    """http:// か https:// のアドレスだけ。空白・制御文字・長すぎるもの・ホストが無いもの・ユーザー名:パスワード@ 付きは使えない（前後の空白も不可）。"""
    if not isinstance(v, str) or not v or len(v) > MAX_URL or not re.match(r"https?://", v, re.IGNORECASE):
        return _BAD
    if any(ch.isspace() or unicodedata.category(ch).startswith("C") for ch in v):
        return _BAD
    try:
        parts = urlsplit(v)
        parts.port  # 範囲外のポートはここで ValueError
    except ValueError:
        return _BAD
    if "@" in parts.netloc:  # ユーザー名:パスワード@ 付きのアドレスは使わない（パスワードが設定や画面に残るため）
        return _BAD
    return v if parts.hostname else _BAD


def _choice(*allowed):
    return lambda v: v if isinstance(v, str) and v in allowed else _BAD


def _hhmm(v):
    """H:MM / HH:MM（半角・00:00〜23:59）を HH:MM にそろえる。"""
    m = re.fullmatch(r"([0-9]{1,2}):([0-9]{2})", v) if isinstance(v, str) else None
    return f"{int(m[1]):02d}:{m[2]}" if m and int(m[1]) <= 23 and int(m[2]) <= 59 else _BAD


def _file_path(v):
    """ファイルの場所。フォルダの場所と同じ決まり（長さ・NUL）に加えて「..」を含まない。"""
    v = _path(v)
    return _BAD if v is not _BAD and ".." in re.split(r"[\\/]+", v) else v


def _read_user_config(path, warnings):
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8-sig") as f:
            user = json.load(f)
        if not isinstance(user, dict):
            raise ValueError("設定がオブジェクトではありません")
        return user
    except (OSError, ValueError, RecursionError) as e:
        print(f"[警告] {path.name} を読めないため既定の設定で起動します: {e}", file=sys.stderr)
        warnings.append(f"{path.name} を読めないため、既定の設定で起動しました")
        return {}


def load_config(path):
    """設定を読み、間違った項目は既定値に戻す。戻り値の "_warnings" に日本語の警告文が入る。"""
    path = Path(path)
    warnings = []
    user = _read_user_config(path, warnings)
    cfg = copy.deepcopy(DEFAULTS)

    def take(src, key, label, check, target, unit=""):
        if key not in src:
            return
        value = check(src[key])
        if value is _BAD:
            warnings.append(f"{path.name} の {label} が正しくありません（{target[key]}{unit}を使います）")
        else:
            target[key] = value

    take(user, "company_name", "company_name", _text, cfg)
    take(user, "manager_title", "manager_title", _optional_text, cfg)
    take(user, "manager_name", "manager_name", _optional_text, cfg)
    take(user, "manager_phone", "manager_phone", _optional_text, cfg)
    take(user, "default_theme", "default_theme", _choice("light", "dark"), cfg)
    take(user, "default_edit_button", "default_edit_button", _choice("on", "off"), cfg)
    take(user, "accident_folder", "accident_folder", _path, cfg)
    take(user, "accident_seconds", "accident_seconds", _seconds, cfg, "秒")
    take(user, "edit_lock_seconds", "edit_lock_seconds", _seconds, cfg, "秒")
    take(user, "custom_holidays_file", "custom_holidays_file", _file_path, cfg)
    take(user, "whiteboard_save_folder", "whiteboard_save_folder", _path, cfg)
    take(user, "whiteboard_pdf_folder", "whiteboard_pdf_folder", _path, cfg)
    take(user, "whiteboard_idle_seconds", "whiteboard_idle_seconds", _wb_idle, cfg, "秒")

    if "documents" in user:
        docs = user["documents"]
        if not isinstance(docs, dict):
            warnings.append(f"{path.name} の documents が正しくありません（既定の文書ボタンを使います）")
        else:
            take(docs, "idle_return_seconds", "idle_return_seconds", _seconds, cfg["documents"], "秒")
            if "buttons" in docs:
                buttons = _clean_buttons(docs["buttons"], path.name, warnings)
                if buttons:
                    cfg["documents"]["buttons"] = buttons

    if "links" in user:
        ln = user["links"]
        if not isinstance(ln, dict):
            warnings.append(f"{path.name} の links が正しくありません（リンクボタンは使いません）")
        else:
            take(ln, "max_stay_seconds", "links.max_stay_seconds", _stay, cfg["links"], "秒")
            if "items" in ln:
                cfg["links"]["items"] = _clean_links(ln["items"], path.name, warnings)

    if "telop" in user:
        tp = user["telop"]
        if not isinstance(tp, dict):
            warnings.append(f"{path.name} の telop が正しくありません（既定のお知らせ設定を使います）")
        else:
            take(tp, "speed", "telop.speed", _speed, cfg["telop"])
            take(tp, "folder", "telop.folder", _path, cfg["telop"])

    if "standby" in user:
        sb = user["standby"]
        if not isinstance(sb, dict):
            warnings.append(f"{path.name} の standby が正しくありません（既定のスリープ時間帯を使います）")
        else:
            take(sb, "start", "standby.start", _hhmm, cfg["standby"])
            take(sb, "end", "standby.end", _hhmm, cfg["standby"])
            take(sb, "wake_idle_seconds", "wake_idle_seconds", _seconds, cfg["standby"], "秒")

    if "server" in user:
        sv = user["server"]
        if not isinstance(sv, dict):
            warnings.append(f"{path.name} の server が正しくありません（既定のホスト・ポートを使います）")
        else:
            take(sv, "host", "server.host", _host, cfg["server"])
            take(sv, "port", "server.port", _port, cfg["server"])

    cfg["_warnings"] = warnings
    return cfg


def _clean_buttons(raw, name, warnings):
    if not isinstance(raw, list):
        warnings.append(f"{name} の documents.buttons が正しくありません（既定の文書ボタンを使います）")
        return None
    buttons = []
    for i, item in enumerate(raw, 1):
        label = _label(item.get("label")) if isinstance(item, dict) else _BAD
        folder = _path(item.get("folder")) if isinstance(item, dict) else _BAD
        if label is _BAD or folder is _BAD:
            warnings.append(f"{name} の documents.buttons の{i}番目に label と folder が揃っていません（この項目は使いません）")
        else:
            buttons.append({"label": label, "folder": folder})
    if not buttons:
        warnings.append(f"{name} の documents.buttons に使える項目がありません（既定の文書ボタンを使います）")
        return None
    return buttons[:MAX_BUTTONS]


def _clean_links(raw, name, warnings):
    if not isinstance(raw, list):
        warnings.append(f"{name} の links.items が正しくありません（リンクボタンは使いません）")
        return []
    items = []
    for i, item in enumerate(raw, 1):
        label = _label(item.get("label")) if isinstance(item, dict) else _BAD
        url = _url(item.get("url")) if isinstance(item, dict) else _BAD
        if label is _BAD or url is _BAD:
            warnings.append(f"{name} の links.items の{i}番目の label か url が正しくありません（この項目は使いません。url は http:// か https:// で始めます）")
        else:
            items.append({"label": label, "url": url})
    if len(items) > MAX_LINKS:
        warnings.append(f"{name} の links.items は {MAX_LINKS} 個までです（先頭の {MAX_LINKS} 個を使います）")
    return items[:MAX_LINKS]


def _manager_field(v, label):
    if not isinstance(v, str):
        raise ValueError(f"{label}は文字で入力してください")
    v = v.strip()
    if len(v) > MAX_TEXT:
        raise ValueError(f"{label}は{MAX_TEXT}文字以内で入力してください")
    if _has_control(v):
        raise ValueError(f"{label}に使えない文字（改行・制御文字など）が含まれています")
    return v


def _company_name(v):
    if not isinstance(v, str):
        raise ValueError("会社名は文字で入力してください")
    v = v.strip()
    if not v:
        raise ValueError("会社名を入力してください")
    if len(v) > MAX_TEXT:
        raise ValueError(f"会社名は{MAX_TEXT}文字以内で入力してください")
    if _has_control(v):
        raise ValueError("会社名に使えない文字（改行・制御文字など）が含まれています")
    return v


def clean_admin_settings(body):
    """管理画面から届いた設定を1項目ずつ確かめ、整えた値を返す。正しくなければ日本語の理由つきの ValueError。"""
    if not isinstance(body, dict):
        raise ValueError("設定の形が正しくありません")
    docs, tp = body.get("documents"), body.get("telop")
    if not isinstance(docs, dict) or not isinstance(tp, dict):
        raise ValueError("設定の形が正しくありません（documents と telop が必要です）")
    raw = docs.get("buttons")
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_BUTTONS:
        raise ValueError(f"文書ボタンの数は 1〜{MAX_BUTTONS} にしてください")
    buttons = []
    for i, item in enumerate(raw, 1):
        label = _text(item.get("label")) if isinstance(item, dict) else _BAD
        folder = _path(item.get("folder")) if isinstance(item, dict) else _BAD
        if _bad_chars(item.get("label") if isinstance(item, dict) else None):
            raise ValueError(f"ラベル {i} に使えない文字（改行・制御文字など）が含まれています")
        if label is _BAD:
            raise ValueError(f"ラベル {i} を入力してください（{MAX_TEXT}文字以内）")
        if folder is _BAD:
            raise ValueError(f"フォルダパス {i} を入力してください（{MAX_PATH}文字以内）")
        if ".." in re.split(r"[\\/]+", folder):
            raise ValueError(f"フォルダパス {i} に「..」は使えません")
        buttons.append({"label": label, "folder": folder})
    speed = _speed(tp.get("speed"))
    if speed is _BAD:
        raise ValueError(f"お知らせの速度は {MIN_SPEED}〜{MAX_SPEED} の整数にしてください")
    telop = {"speed": speed}
    if "folder" in tp:  # 送られてこなければ、いまの設定のまま
        folder = tp["folder"]
        if not isinstance(folder, str):
            raise ValueError("テロップフォルダは文字で入力してください")
        folder = folder.strip() or DEFAULTS["telop"]["folder"]  # 空欄は既定の telop フォルダ
        if _path(folder) is _BAD:
            raise ValueError(f"テロップフォルダを正しく入力してください（{MAX_PATH}文字以内）")
        if ".." in re.split(r"[\\/]+", folder):
            raise ValueError("テロップフォルダに「..」は使えません")
        telop["folder"] = folder
    clean = {"documents": {"buttons": buttons}, "telop": telop}
    if "company_name" in body:  # 送られなければ、いまの会社名のまま
        clean["company_name"] = _company_name(body["company_name"])
    for key, label in (("manager_title", "役職"), ("manager_name", "氏名"), ("manager_phone", "電話番号")):
        if key in body:  # 送られなければ、いまのまま（古い画面でも使える）
            clean[key] = _manager_field(body[key], label)
    # 以下は送られてきた項目だけを確かめる（送られなければ、いまの設定のまま。古い画面でも使える）
    if "idle_return_seconds" in docs:
        clean["documents"]["idle_return_seconds"] = _admin_seconds(docs["idle_return_seconds"], "文書の操作なし戻り（秒）")
    for key, label in (("accident_seconds", "災害事例の表示秒数"), ("edit_lock_seconds", "編集の自動終了（秒）")):
        if key in body:
            clean[key] = _admin_seconds(body[key], label)
    if "standby" in body:
        sb = body["standby"]
        if not isinstance(sb, dict):
            raise ValueError("スリープの設定の形が正しくありません")
        standby = {}
        for key, label in (("start", "スリープ開始"), ("end", "スリープ終了")):
            if key in sb:
                standby[key] = _hhmm(sb[key])
                if standby[key] is _BAD:
                    raise ValueError(f"{label}は 18:00 のような時刻（00:00〜23:59）で入力してください")
        if "wake_idle_seconds" in sb:
            standby["wake_idle_seconds"] = _admin_seconds(sb["wake_idle_seconds"], "操作なしでスリープに戻る（秒）")
        clean["standby"] = standby
    if "custom_holidays_file" in body:
        path = body["custom_holidays_file"]
        if not isinstance(path, str):
            raise ValueError("会社の休日ファイルは文字で入力してください")
        path = path.strip() or DEFAULTS["custom_holidays_file"]  # 空欄は既定の場所
        if _path(path) is _BAD:
            raise ValueError(f"会社の休日ファイルを正しく入力してください（{MAX_PATH}文字以内）")
        if _file_path(path) is _BAD:
            raise ValueError("会社の休日ファイルに「..」は使えません")
        clean["custom_holidays_file"] = path
    for key, label in (("whiteboard_save_folder", "ホワイトボードの保存フォルダ"), ("whiteboard_pdf_folder", "ホワイトボードの背景用PDFフォルダ")):
        if key in body:
            clean[key] = _admin_folder(body[key], label, DEFAULTS[key])
    if "whiteboard_idle_seconds" in body:
        n = _wb_idle(body["whiteboard_idle_seconds"])
        if n is _BAD:
            raise ValueError(f"ホワイトボードの操作なし戻り（秒）は {MIN_WB_IDLE}〜{MAX_WB_IDLE} の整数で入力してください")
        clean["whiteboard_idle_seconds"] = n
    if "links" in body:
        clean["links"] = _admin_links(body["links"])
    return clean


def _admin_links(raw):
    if not isinstance(raw, dict):
        raise ValueError("リンクボタンの設定の形が正しくありません")
    links = {}
    if "items" in raw:  # 送られなければ、いまのリンクのまま
        rows = raw["items"]
        if not isinstance(rows, list):
            raise ValueError("リンクボタンの設定の形が正しくありません")
        if len(rows) > MAX_LINKS:
            raise ValueError(f"リンクボタンは {MAX_LINKS} つまでです")
        items = []
        for i, row in enumerate(rows, 1):
            if not isinstance(row, dict):
                raise ValueError(f"リンクボタン {i} の形が正しくありません")
            label, url = row.get("label"), row.get("url")
            # 名前もアドレスも空欄の行は「使わない」。片方だけ入っていたらどちらかが足りない
            if all(isinstance(v, str) and not v.strip() for v in (label, url)):
                continue
            if _bad_chars(label):
                raise ValueError(f"リンクボタン {i} の名前に使えない文字（改行・制御文字など）が含まれています")
            label = _text(label)
            if label is _BAD:
                raise ValueError(f"リンクボタン {i} の名前を入力してください（{MAX_TEXT}文字以内。使わないときは名前もアドレスも空にします）")
            if _url(url) is _BAD:
                raise ValueError(f"リンクボタン {i} のアドレスを http:// か https:// で始まる正しい形で入力してください（空白・ユーザー名:パスワード@ なし・{MAX_URL}文字以内。使わないときは名前もアドレスも空にします）")
            items.append({"label": label, "url": url})
        links["items"] = items
    if "max_stay_seconds" in raw:
        stay = _stay(raw["max_stay_seconds"])
        if stay is _BAD:
            raise ValueError(f"リンクの最大滞在（秒）は {MIN_STAY}〜{MAX_STAY} の整数で入力してください")
        links["max_stay_seconds"] = stay
    return links


def _admin_seconds(v, label):
    n = _seconds(v)
    if n is _BAD:
        raise ValueError(f"{label}は 1〜{MAX_SECONDS} の数で入力してください")
    return n


def _admin_folder(v, label, default):
    if not isinstance(v, str):
        raise ValueError(f"{label}は文字で入力してください")
    v = v.strip() or default  # 空欄は既定の場所
    if _path(v) is _BAD:
        raise ValueError(f"{label}を正しく入力してください（{MAX_PATH}文字以内）")
    if ".." in re.split(r"[\\/]+", v):
        raise ValueError(f"{label}に「..」は使えません")
    return v


def _backup_config(path):
    """いまの config.json を backups/config_日時.json に写し、新しい5件だけ残す。失敗しても保存は止めない（警告だけ）。中身は読まない・ログに書かない。"""
    try:
        folder = path.parent / "backups"
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        def name_key(p):
            m = _BACKUP_NAME.fullmatch(p.name)
            return m[1], int(m[2] or 0)  # 番号は数として比べる（文字の並びだと _10 が _2 より前になる）

        def age_key(p):
            # 新しさは更新日時で決める（時計が戻った・進んだときに、名前の日付が新しくても古いファイルを残さない）。同時刻なら名前の順
            try:
                return p.stat().st_mtime_ns, name_key(p)
            except OSError:
                return 0, name_key(p)

        mine = [p for p in folder.iterdir() if _BACKUP_NAME.fullmatch(p.name)]
        same = [name_key(p)[1] for p in mine if name_key(p)[0] == stamp]
        # 同じ秒にもう保存があれば、いちばん大きい番号の次を使う（上書きしない）
        dest = folder / (f"config_{stamp}_{max(same) + 1}.json" if same else f"config_{stamp}.json")
        shutil.copyfile(path, dest)
        # 消すのは、いま作った控えを除く古いものだけ（いま作った控えは必ず残す）
        mine.sort(key=age_key)
        for old in mine[:max(0, len(mine) - (BACKUP_KEEP - 1))]:
            old.unlink()
    except OSError as e:
        logger.warning("config.json のバックアップを作れませんでした（保存は続けます）: %s", e)


def save_admin_settings(path, clean):
    """管理画面から届いた項目だけを config.json に書く（他の項目は残す）。"""
    path = Path(path)
    existed = True
    # ファイルが無いときだけ空から始める。書き間違い・読めない場合は、利用者の他の設定を消さないよう保存しない
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}
        existed = False
    except (ValueError, RecursionError):
        raise ValueError(BROKEN_CONFIG_MESSAGE) from None
    if not isinstance(data, dict):
        raise ValueError(BROKEN_CONFIG_MESSAGE)
    before = copy.deepcopy(data)
    for key in ("documents", "telop"):
        if not isinstance(data.get(key), dict):
            data[key] = {}
    data["documents"]["buttons"] = clean["documents"]["buttons"]
    data["telop"]["speed"] = clean["telop"]["speed"]
    if "company_name" in clean:
        data["company_name"] = clean["company_name"]
    for key in ("manager_title", "manager_name", "manager_phone"):
        if key in clean:
            data[key] = clean[key]
    if "folder" in clean["telop"]:
        data["telop"]["folder"] = clean["telop"]["folder"]
    if "idle_return_seconds" in clean["documents"]:
        data["documents"]["idle_return_seconds"] = clean["documents"]["idle_return_seconds"]
    for key in ("accident_seconds", "edit_lock_seconds", "custom_holidays_file", "whiteboard_save_folder", "whiteboard_pdf_folder", "whiteboard_idle_seconds"):
        if key in clean:
            data[key] = clean[key]
    if clean.get("links"):
        if not isinstance(data.get("links"), dict):
            data["links"] = {}
        data["links"].update(clean["links"])
    if clean.get("standby"):
        if not isinstance(data.get("standby"), dict):
            data["standby"] = {}
        data["standby"].update(clean["standby"])
    # 中身が変わらない保存は、書き直さず控えも作らない（同じ保存の繰り返しで、本当の変更前の控えが押し出されないように）
    if existed and json.dumps(before, sort_keys=True) == json.dumps(data, sort_keys=True):
        return
    # 同じフォルダの一時ファイルに書いてから置き換える（途中で止まっても元のファイルは壊れない）
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        if existed:
            _backup_config(path)  # 置き換える直前に、いまのファイルを控える
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
