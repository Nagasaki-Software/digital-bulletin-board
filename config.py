import copy
import json
import math
import os
import re
import sys
import unicodedata
from pathlib import Path

DEFAULTS = {
    "company_name": "サンプル工業(株)",
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
    "standby": {"start": "18:00", "end": "07:30", "wake_idle_seconds": 300},
}

MAX_BUTTONS = 5
MAX_SECONDS = 86400
MAX_TEXT = 100
MAX_PATH = 260  # フォルダの場所（ネットワークの共有などは長くなる）
BROKEN_CONFIG_MESSAGE = "config.json に書き間違いがあります。直してから保存してください"
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


def _path(v):
    return _text(v, MAX_PATH)


def _speed(v):
    return v if isinstance(v, int) and not isinstance(v, bool) and MIN_SPEED <= v <= MAX_SPEED else _BAD


def _choice(*allowed):
    return lambda v: v if isinstance(v, str) and v in allowed else _BAD


def _hhmm(v):
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", v) if isinstance(v, str) else None
    return v if m and int(m[1]) <= 23 and int(m[2]) <= 59 else _BAD


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
    take(user, "default_theme", "default_theme", _choice("light", "dark"), cfg)
    take(user, "default_edit_button", "default_edit_button", _choice("on", "off"), cfg)
    take(user, "accident_folder", "accident_folder", _path, cfg)
    take(user, "accident_seconds", "accident_seconds", _seconds, cfg, "秒")
    take(user, "edit_lock_seconds", "edit_lock_seconds", _seconds, cfg, "秒")

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
            warnings.append(f"{path.name} の standby が正しくありません（既定の待機時間帯を使います）")
        else:
            take(sb, "start", "standby.start", _hhmm, cfg["standby"])
            take(sb, "end", "standby.end", _hhmm, cfg["standby"])
            take(sb, "wake_idle_seconds", "wake_idle_seconds", _seconds, cfg["standby"], "秒")

    cfg["_warnings"] = warnings
    return cfg


def _clean_buttons(raw, name, warnings):
    if not isinstance(raw, list):
        warnings.append(f"{name} の documents.buttons が正しくありません（既定の文書ボタンを使います）")
        return None
    buttons = []
    for i, item in enumerate(raw, 1):
        label = _text(item.get("label")) if isinstance(item, dict) else _BAD
        folder = _path(item.get("folder")) if isinstance(item, dict) else _BAD
        if label is _BAD or folder is _BAD:
            warnings.append(f"{name} の documents.buttons の{i}番目に label と folder が揃っていません（この項目は使いません）")
        else:
            buttons.append({"label": label, "folder": folder})
    if not buttons:
        warnings.append(f"{name} の documents.buttons に使える項目がありません（既定の文書ボタンを使います）")
        return None
    return buttons[:MAX_BUTTONS]


def _company_name(v):
    if not isinstance(v, str):
        raise ValueError("会社名は文字で入力してください")
    v = v.strip()
    if not v:
        raise ValueError("会社名を入力してください")
    if len(v) > MAX_TEXT:
        raise ValueError(f"会社名は{MAX_TEXT}文字以内で入力してください")
    if any(unicodedata.category(ch).startswith("C") for ch in v):
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
    return clean


def save_admin_settings(path, clean):
    """config.json の documents.buttons・telop.speed / telop.folder・company_name だけを書き換える（他の項目は残す）。"""
    path = Path(path)
    # ファイルが無いときだけ空から始める。書き間違い・読めない場合は、利用者の他の設定を消さないよう保存しない
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}
    except (ValueError, RecursionError):
        raise ValueError(BROKEN_CONFIG_MESSAGE) from None
    if not isinstance(data, dict):
        raise ValueError(BROKEN_CONFIG_MESSAGE)
    for key in ("documents", "telop"):
        if not isinstance(data.get(key), dict):
            data[key] = {}
    data["documents"]["buttons"] = clean["documents"]["buttons"]
    data["telop"]["speed"] = clean["telop"]["speed"]
    if "company_name" in clean:
        data["company_name"] = clean["company_name"]
    if "folder" in clean["telop"]:
        data["telop"]["folder"] = clean["telop"]["folder"]
    # 同じフォルダの一時ファイルに書いてから置き換える（途中で止まっても元のファイルは壊れない）
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
