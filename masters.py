import csv
import hashlib
import os
import re
import time
from datetime import date, timedelta
from pathlib import Path

import jpholiday

WEEKDAYS = "月火水木金土日"

FILES = {
    "genres": ("genres.csv", ["name"]),
    "times": ("times.csv", ["time"]),
}
CUSTOM_HOLIDAYS = "custom_holidays.csv"
# 会社・工事件名は「1ファイル = 1項目」のフォルダ。ファイル名（.csv を除く）が会社名・工事件名になる。
# 列は (取り込み後の名前, 見出しの書き方...)。最初の列だけが必須
COMPANY_COLUMNS = [("leader_name", "責任者", "leader_name"), ("ext", "内線", "ext"), ("outside", "外線", "outside")]
CONSTRUCTION_COLUMNS = [("work", "作業内容", "name")]
HOLIDAY_STAT_TTL = 10  # 会社の休日ファイルの更新確認の間隔（秒）。共有フォルダが応答しなくても、3秒ごとの確認を止めないため
SCAN_TTL = 2  # 会社・工事件名のフォルダの一覧を調べ直す間隔（秒）。3秒ごとに全画面が確認するので、毎回は走査しない
_clock = time.monotonic


def decode_warning(name):
    return f"{name} を読めません。Excelで『CSV UTF-8（コンマ区切り）』として保存し直してください"


def read_csv(path, columns, required=True):
    """(行のリスト, 警告文)。読めないときは空のリストと警告を返す（例外にしない）。"""
    path = Path(path)
    if not path.exists():
        return [], (f"{path.name} が見つかりません" if required else None)
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                reader.fieldnames = [h.strip() for h in reader.fieldnames]
            rows = []
            for raw in reader:
                row = {c: (raw.get(c) or "").strip() for c in columns}
                if any(row.values()):
                    rows.append(row)
            missing = [c for c in columns if c not in (reader.fieldnames or [])]
    except UnicodeDecodeError:
        return [], decode_warning(path.name)
    except (OSError, csv.Error) as e:
        return [], f"{path.name} を読めません（{e}）"
    if missing:
        return [], f"{path.name} に列がありません: {', '.join(missing)}"
    return rows, None


def natural_key(name):
    """1班, 2班, 10班 の順になる並べ替えのキー。数字は数として、文字は大文字小文字を区別せずに比べる。"""
    parts = re.split(r"([0-9]+)", name)
    chunks = [(0, int(p), "") if p.isascii() and p.isdigit() else (1, 0, p.casefold()) for p in parts if p]
    return chunks, name


def list_csv_files(data_dir, folder):
    """(使うファイルのパスの一覧（自然順）, 警告文)。使うのは拡張子が .csv の普通のファイルだけ。
    Excel の一時ファイル（~$）、隠しファイル（.）、雛形・メモ（_）、フォルダは使わない。"""
    root = Path(data_dir) / folder
    try:
        with os.scandir(root) as it:
            entries = list(it)
    except (FileNotFoundError, NotADirectoryError):
        return [], f"data/{folder} フォルダがありません"
    except OSError as e:
        return [], f"data/{folder} フォルダを読めません（{e}）"
    files = [
        Path(e.path)
        for e in entries
        if e.name.lower().endswith(".csv") and not e.name.startswith(("~$", ".", "_")) and e.is_file()
    ]
    return sorted(files, key=lambda p: natural_key(p.stem)), None


def read_item_file(path, columns):
    """1項目のファイルを読む。(行のリスト, 警告文)。行は {取り込み後の名前: 値}。最初の列が空の行は黙って飛ばす。
    読めない・空・必須の列が無いファイルは、警告を返してその項目ごと使わない（行は None）。"""
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            table = [r for r in csv.reader(f) if any(c.strip() for c in r)]
    except UnicodeDecodeError:
        return None, decode_warning(path.name)
    except (OSError, csv.Error) as e:
        return None, f"{path.name} を読めません（{e}）"
    if not table:
        return None, f"{path.name} が空です。1行目に見出し（{columns[0][1]}）が必要です"
    header = [h.strip() for h in table[0]]
    index = {}
    for key, *aliases in columns:
        index[key] = next((header.index(a) for a in aliases if a in header), None)
    first = columns[0]
    if index[first[0]] is None:
        return None, f"{path.name} に列がありません: {first[1]}"
    rows = []
    for raw in table[1:]:
        row = {k: (raw[i].strip() if i is not None and i < len(raw) else "") for k, i in index.items()}
        if row[first[0]]:
            rows.append(row)
    return rows, None


def load_item_folder(data_dir, folder, columns, kind):
    """([(項目名, 行のリスト), ...], 警告のリスト)。項目名はファイル名。同じファイルの中で最初の列が重なった行は、最初の1つだけ使い、
    重なりの警告はフォルダごとに1つ（最初の例）。"""
    files, warn = list_csv_files(data_dir, folder)
    warnings = [warn] if warn else []
    items = []
    first_dup = None
    key = columns[0][0]
    for path in files:
        rows, warn = read_item_file(path, columns)
        if warn:
            warnings.append(warn)
            continue
        seen = set()
        kept = []
        for row in rows:
            if row[key] in seen:
                first_dup = first_dup or f"{path.name} の「{row[key]}」"
            else:
                seen.add(row[key])
                kept.append(row)
        items.append((path.stem, kept))
    if first_dup:
        warnings.append(f"data/{folder} に、同じ{kind}が2回書かれたファイルがあります（2回目以降は使いません。最初の例: {first_dup}）")
    return items, warnings


def default_times():
    # 夜勤・徹夜に対応するため24時間分。日勤の時刻が先頭に来るよう、6:00 から 23:30、続けて 0:00 から 5:30 の順
    return [f"{h}:{mi:02d}" for h in [*range(6, 24), *range(0, 6)] for mi in (0, 30)]


def parse_date(text):
    """2026-12-29 / 2026/12/29 / 2026-1-5 を date にする。形式や日付が不正なら ValueError。"""
    parts = text.strip().replace("/", "-").split("-")
    if len(parts) != 3 or len(parts[0]) != 4 or not all(p.isdigit() for p in parts):
        raise ValueError(text)
    return date(*(int(p) for p in parts))


def load_custom_holidays(data_dir, path=None, missing_label=None):
    """会社の休日ファイル（date,name）を読む。path が無ければ data_dir の custom_holidays.csv（無くても静か）。
    missing_label を渡したときだけ、ファイルが無い場合に警告を1つ返す。読むだけで書かない。"""
    path = Path(path) if path else Path(data_dir) / CUSTOM_HOLIDAYS
    rows, warn = read_csv(path, ["date", "name"], required=False)
    if warn is None and missing_label and not path.exists():
        warn = f"会社の休日ファイル（{missing_label}）が見つかりません"
    warnings = [warn] if warn else []
    out = {}
    for r in rows:
        try:
            key = parse_date(r["date"]).isoformat()
        except ValueError:
            warnings.append(f"{path.name} の日付が正しくありません: {r['date']}")
            continue
        out[key] = r["name"]
    return out, warnings


def load_companies(data_dir):
    """(会社名の一覧, 責任者の一覧, 警告のリスト)。会社名は data/companies/ のファイル名。"""
    items, warnings = load_item_folder(data_dir, "companies", COMPANY_COLUMNS, "責任者")
    companies = [name for name, _ in items]
    leaders = [
        {"company": name, "leader_name": r["leader_name"], "ext": r["ext"], "outside": r["outside"]}
        for name, rows in items
        for r in rows
    ]
    return companies, leaders, warnings


def load_constructions(data_dir):
    """(工事件名の一覧, 工事件名 → 選べる作業内容, 作業内容の全体, 警告のリスト)。工事件名は data/constructions/ のファイル名。
    作業内容が1つも無い工事件名は対応表に入れない（どの作業内容でも選べる）。作業内容の全体は、全ファイルの作業内容を並びの順にまとめ、重なりを除いたもの。"""
    items, warnings = load_item_folder(data_dir, "constructions", CONSTRUCTION_COLUMNS, "作業内容")
    constructions = [name for name, _ in items]
    construction_works = {name: [r["work"] for r in rows] for name, rows in items if rows}
    works = list(dict.fromkeys(w for ws in construction_works.values() for w in ws))
    return constructions, construction_works, works, warnings


class Masters:
    def __init__(self, data_dir, holidays_source=None):
        """holidays_source: 呼ぶたびに（会社の休日ファイルの場所, 無いときの警告に出す名前）を返す。
        名前が None なら、ファイルが無くても警告しない。省略時は data_dir の custom_holidays.csv。"""
        self.holidays_source = holidays_source
        self._holiday_stamp = None  # (場所, 次に確かめる時刻, 値)
        self._folders_cache = None  # (次に走査する時刻, 値)
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        times = self.dir / FILES["times"][0]
        if not times.exists():
            with open(times, "w", encoding="utf-8-sig", newline="") as f:
                f.write("time\n" + "\n".join(default_times()) + "\n")

    def load_all(self):
        companies, leaders, warnings = load_companies(self.dir)
        constructions, construction_works, works, construction_warns = load_constructions(self.dir)
        warnings.extend(construction_warns)
        loaded = {}
        for key, (fname, cols) in FILES.items():
            rows, warn = read_csv(self.dir / fname, cols)
            if warn:
                warnings.append(warn)
            loaded[key] = rows
        path, label = self._holidays()
        custom, custom_warns = load_custom_holidays(self.dir, path, label)
        warnings.extend(custom_warns)
        return {
            "companies": companies,
            "leaders": leaders,
            "works": works,
            "constructions": constructions,
            "construction_works": construction_works,
            "genres": [r["name"] for r in loaded["genres"]],
            "times": [r["time"] for r in loaded["times"]],
            "custom_holidays": custom,
            "warnings": warnings,
        }

    def _folders_stamp(self):
        """会社・工事件名のフォルダの、ファイル名・更新日時・大きさ（追加・削除・名前の変更・書き換えで変わる）。
        画面ごとに3秒ごとに呼ばれるので、走査は SCAN_TTL 秒に1回だけ。Excel の上書きで更新日時が同じでも、大きさで気づく。"""
        now = _clock()
        cached = self._folders_cache
        if cached is None or now >= cached[0]:
            lines = []
            for folder in ("companies", "constructions"):
                files, _ = list_csv_files(self.dir, folder)
                for path in files:
                    try:
                        st = path.stat()
                    except OSError:
                        continue
                    lines.append(f"{folder}/{path.name}:{st.st_mtime_ns}:{st.st_size}")
            digest = hashlib.md5("\n".join(lines).encode("utf-8"), usedforsecurity=False).hexdigest()[:12] if lines else "-"
            cached = self._folders_cache = (now + SCAN_TTL, digest)
        return cached[1]

    def _holidays(self):
        return self.holidays_source() if self.holidays_source else (self.dir / CUSTOM_HOLIDAYS, None)

    def signature(self):
        def stamp(path, with_size=False):
            try:
                st = Path(path).stat()
            except (OSError, ValueError):
                return "-"
            return f"{st.st_mtime_ns}-{st.st_size}" if with_size else str(st.st_mtime_ns)

        parts = [stamp(self.dir / f) for f, _ in FILES.values()]
        parts.append(self._folders_stamp())
        # 会社の休日ファイルは別の場所にあることがあり、Excel で上書きされる。更新日時が同じでも気づけるよう、大きさも含める
        # ネットワークの場所だと確認に時間がかかることがあるので、同じ場所への問い合わせは HOLIDAY_STAT_TTL 秒に1回だけ
        holidays = str(self._holidays()[0])
        now = _clock()
        cached = self._holiday_stamp
        if cached is None or cached[0] != holidays or now >= cached[1]:
            cached = self._holiday_stamp = (holidays, now + HOLIDAY_STAT_TTL, stamp(holidays, with_size=True))
        parts.append(cached[2])
        return ".".join(parts)


def holiday_info(d, custom):
    name = jpholiday.is_holiday_name(d) or custom.get(d.isoformat(), "")
    if name or d.weekday() == 6:
        return {"kind": "holiday", "name": name or ""}
    if d.weekday() == 5:
        return {"kind": "saturday", "name": ""}
    return {"kind": "", "name": ""}


def date_label(d):
    return f"{d.month}/{d.day}({WEEKDAYS[d.weekday()]})"


def day_title(d):
    return f"{d.year}年{d.month}月{d.day}日（{WEEKDAYS[d.weekday()]}）"


def week_range(today):
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=6)


def week_holidays(today, custom):
    monday, _ = week_range(today)
    out = []
    for i in range(7):
        d = monday + timedelta(days=i)
        info = holiday_info(d, custom)
        if info["kind"]:
            out.append({"date": d.isoformat(), "label": date_label(d), "kind": info["kind"]})
    return out
