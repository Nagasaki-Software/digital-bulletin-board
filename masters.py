import csv
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


def load_custom_holidays(data_dir):
    rows, warn = read_csv(Path(data_dir) / CUSTOM_HOLIDAYS, ["date", "name"], required=False)
    warnings = [warn] if warn else []
    out = {}
    for r in rows:
        try:
            key = parse_date(r["date"]).isoformat()
        except ValueError:
            warnings.append(f"{CUSTOM_HOLIDAYS} の日付が正しくありません: {r['date']}")
            continue
        out[key] = r["name"]
    return out, warnings


class Masters:
    def __init__(self, data_dir):
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
        custom, custom_warns = load_custom_holidays(self.dir)
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

    def signature(self):
        names = [f for f, _ in FILES.values()] + [CUSTOM_HOLIDAYS]
        parts = []
        for name in names:
            try:
                parts.append(str((self.dir / name).stat().st_mtime_ns))
            except OSError:
                parts.append("-")
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
