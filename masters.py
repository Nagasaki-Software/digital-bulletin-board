import csv
import time
from datetime import date, timedelta
from pathlib import Path

import jpholiday

WEEKDAYS = "月火水木金土日"

FILES = {
    "companies": ("companies.csv", ["name"]),
    "leaders": ("leaders.csv", ["company", "leader_name", "ext", "outside"]),
    "works": ("works.csv", ["name"]),
    "constructions": ("constructions.csv", ["name"]),
    "genres": ("genres.csv", ["name"]),
    "times": ("times.csv", ["time"]),
}
CUSTOM_HOLIDAYS = "custom_holidays.csv"
HOLIDAY_STAT_TTL = 10  # 会社の休日ファイルの更新確認の間隔（秒）。共有フォルダが応答しなくても、3秒ごとの確認を止めないため
_clock = time.monotonic


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
        return [], f"{path.name} を読めません。Excelで『CSV UTF-8（コンマ区切り）』として保存し直してください"
    except (OSError, csv.Error) as e:
        return [], f"{path.name} を読めません（{e}）"
    if missing:
        return [], f"{path.name} に列がありません: {', '.join(missing)}"
    return rows, None


def default_times():
    return [f"{h}:{mi:02d}" for h in range(6, 22) for mi in (0, 30)] + ["22:00"]


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


class Masters:
    def __init__(self, data_dir, holidays_source=None):
        """holidays_source: 呼ぶたびに（会社の休日ファイルの場所, 無いときの警告に出す名前）を返す。
        名前が None なら、ファイルが無くても警告しない。省略時は data_dir の custom_holidays.csv。"""
        self.holidays_source = holidays_source
        self._holiday_stamp = None  # (場所, 次に確かめる時刻, 値)
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        times = self.dir / FILES["times"][0]
        if not times.exists():
            with open(times, "w", encoding="utf-8-sig", newline="") as f:
                f.write("time\n" + "\n".join(default_times()) + "\n")

    def load_all(self):
        warnings = []
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
            "companies": [r["name"] for r in loaded["companies"]],
            "leaders": loaded["leaders"],
            "works": [r["name"] for r in loaded["works"]],
            "constructions": [r["name"] for r in loaded["constructions"]],
            "genres": [r["name"] for r in loaded["genres"]],
            "times": [r["time"] for r in loaded["times"]],
            "custom_holidays": custom,
            "warnings": warnings,
        }

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


def date_label(d, name):
    w = WEEKDAYS[d.weekday()]
    return f"{d.month}/{d.day}({w}・{name})" if name else f"{d.month}/{d.day}({w})"


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
            out.append({"date": d.isoformat(), "label": date_label(d, info["name"]), "kind": info["kind"]})
    return out
