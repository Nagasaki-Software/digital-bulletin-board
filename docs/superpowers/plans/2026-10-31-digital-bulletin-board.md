# デジタル掲示板 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 工場のホワイトボードの代わりに、70インチのタッチモニタ（と社内LANの他のPC）で「本日の作業予定・連絡事項・今週の休日出勤予定・災害事例の自動再生・文書閲覧」を表示・入力できるWebアプリを作る。

**Architecture:** Flask + waitress が1台のPCで動き、画面は1枚のHTML（ES modules）。保存は SQLite（`data/board.db`）、選択肢は Excel で編集する CSV（`data/*.csv`）、設定は `config.json`。画面は3秒ごとに軽量なリビジョン確認を行い、変更があれば全体を再取得して描き直す。

**Tech Stack:** Python 3.14（`.venv`）、Flask、waitress、jpholiday、pytest（以上4つが追加パッケージ）、標準ライブラリの sqlite3、素のJavaScript（ES modules、node の `node:test` で純粋関数のみテスト）、PDF.js（equipment-inspection からコピー）。

**Spec:** `docs/superpowers/specs/2026-10-31-digital-bulletin-board-design.md`

## Global Constraints

- アプリの場所は `<アプリのフォルダ>`（`dev/apps/digital-bulletin-board`）。**以降のコマンドはすべてこのフォルダで実行する。**
- ポートは **5100 固定**、待ち受けは `0.0.0.0`。ログイン認証は付けない。
- CSV は必ず `encoding="utf-8-sig"` で読み書きする。`open()` には必ず `encoding` を明示する（省略すると cp932 になる）。
- フォントはメイリオ優先（`"Meiryo","メイリオ",sans-serif`）。
- 新しいパッケージのインストールは、`package-security-scan` スキルでスキャンし、ユーザーの承認を得てから行う（Task 1）。承認なしに `pip install` しない。
- **コミットはユーザーが明示的に依頼したときだけ**行う。この計画には commit の手順を入れていない（`git init` のみ Task 1 で行う）。
- 削除系コマンド（rm, del 等）は実行しない。削除が必要なときは対象と理由を示して承認を得る。
- 既存ファイルを上書きする前は確認する（この計画で作るファイルは新規。Task 7 以降で `board.js` などを編集するのは、この計画が作ったファイルのみ）。
- 1ファイルが1000行を超えたら、完了報告時に分割を提案する。
- 画面を変えたら、実際にブラウザで開いて確認する。実行できなかったものは「未検証」と報告する。
- 画面の編集操作（行の追加・削除・▲▼・赤字スイッチ・欄のタップ）は、すべて `isEditable()` が真のときだけ有効（`.edit-only` クラスで非表示にする）。
- 配色は CSS 変数で、明るい（デザイン案A）と暗い（デザイン案B）の2種類。端末ごとの選択はブラウザの `localStorage`（キー `dbb.theme`）に保存し、無ければ `config.json` の `default_theme`（既定 `light`）に従う。
- 連絡事項は、最初は空の3行。常に3行分の高さで表示し、4行目以降は枠の中でスクロール。4行以上のときだけ行を削除でき、3行未満にはならない。
- 作業ジャンルは `data/genres.csv` だけで増減・改名する（画面からは変えない）。多いときは折り返す。

## Review Focus

仕様が黙っているが、使う人が必ず出会う入力。各行の確認は、右側の Task のテストが担う。

1. **全行を削除した日の翌日**は、直近の「行がある日」から引き継ぐ。**同じ日に全行を削除したあとの再アクセスでは再コピーしない**（Task 3 `test_delete_all_then_no_recopy`）
2. **CSV が壊れている・Shift-JIS で保存された・列が足りない・無い**ときも、掲示は止めず、画面の警告欄に出す（Task 2 `test_read_csv_*`、Task 5 `test_broken_csv_gives_warning_not_error`）
3. **日付の境目**: 日曜は前の月曜と同じ週／月曜 0時で休日出勤が空欄／0時を過ぎたら新しい日（Task 2 `test_week_range`、Task 5 `test_monday_resets_holiday_rows`）
4. **夜勤（終了が開始より前）の就業予定**は拒否せず保存する。待機の時刻設定が日付をまたぐ（18:00〜07:30）場合も正しく判定する（Task 5 `test_overnight_time_is_accepted`、Task 9 `timeutil.test.mjs`）
5. **ファイル名に `_` が無い／ジャンル未登録／PDF以外／日本語名／数字入りの並び**（「事例10」は「事例2」のあと）でも、再生リストが壊れない（Task 4 `test_*`、Task 5 `test_accident_playlist`）
6. **連絡事項が4行以上になっても、3行未満にはならない**。行を足して消しても位置がずれない（Task 3 `test_notice_add_update_delete_compacts` `test_notices_cannot_go_below_three`、Task 5 `test_notices_cannot_be_deleted_below_three`）

---

## ファイル構成

| ファイル | 役割 | 作る Task |
|---|---|---|
| `config.py` | `config.json` の読み込み（既定値とのマージ） | 1 |
| `masters.py` | CSV 読み込み、時刻の候補、休日判定、週の範囲、日付表示 | 2 |
| `board_db.py` | SQLite の読み書き（前日の引き継ぎ・行の詰め・並べ替え・リビジョン） | 3 |
| `accident.py` | 災害事例PDFのファイル名→ジャンル判定、再生リスト、PDF一覧 | 4 |
| `app.py` | Flask のURL（API と静的ファイル）、起動 | 5 |
| `static/board.html` `static/board.css` | 画面の骨組みと見た目 | 6 |
| `static/js/api.js` `timeutil.mjs` `theme.js` `picker.js` `board.js` | 通信、時刻・連絡先の純粋関数（node でテスト）、配色の切り替え、選択パネル、画面の描画と入力 | 6 |
| `static/js/accident.js` `static/pdfjs/` | 災害事例の自動再生、PDF.js | 7 |
| `static/js/documents.js` | 文書ボタンと閲覧 | 8 |
| `static/js/lock.js` `standby.js` | 編集ロック・設定メニュー（編集ボタン・配色）、待機画面 | 9 |
| `起動.bat` `初回セットアップ.bat` `README.md` `THIRD_PARTY_NOTICES.md` | 起動・配布 | 10 |
| `data/*.csv`（サンプル）、`tests/` | 架空のサンプルデータ、テスト | 1〜 |

---

### Task 1: プロジェクトの土台と設定の読み込み

**Files:**
- Create: `.gitignore`, `requirements.txt`, `config.py`, `tests/conftest.py`, `tests/test_config.py`
- Create: `data/companies.csv`, `data/leaders.csv`, `data/works.csv`, `data/genres.csv`, `data/custom_holidays.csv`

**Interfaces:**
- Produces: `config.load_config(path) -> dict`（キー: `company_name`, `default_theme`, `accident_folder`, `accident_seconds`, `documents{buttons[], idle_return_seconds}`, `edit_lock_seconds`, `standby{start,end,wake_idle_seconds}`）

- [ ] **Step 1: git init と除外設定**

```bash
cd <アプリのフォルダ> && git init
```

`.gitignore`:

```
.venv/
.browser/
.claude/
__pycache__/
.pytest_cache/
config.json
data/board.db
data/board.db-wal
data/board.db-shm
accident_cases/
documents/
```

`requirements.txt`:

```
flask
waitress
jpholiday
pytest
```

- [ ] **Step 2: パッケージの安全確認とユーザーの承認（インストール前に必ず止まる）**

`package-security-scan` スキルで `flask` `waitress` `jpholiday` `pytest` をスキャンする。次を日本語でユーザーに伝え、**承認を得てから**次に進む。

> 1. インストールするもの: flask（Webサーバーの部品）、waitress（本番用サーバー）、jpholiday（祝日判定）、pytest（テスト）
> 2. 理由: 画面の配信、LANでの公開、休日出勤の祝日表示、自動テスト
> 3. 範囲: このアプリのフォルダの `.venv` の中だけ（PC全体には入りません）

- [ ] **Step 3: 仮想環境の作成とインストール（承認後）**

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m pytest --version
```

Expected: `pytest 8.x` などのバージョンが表示される。

- [ ] **Step 4: 失敗するテストを書く**

`tests/conftest.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

`tests/test_config.py`:

```python
import json

from config import load_config


def test_defaults_when_file_missing(tmp_path):
    cfg = load_config(tmp_path / "config.json")
    assert cfg["accident_seconds"] == 15
    assert cfg["edit_lock_seconds"] == 60
    assert cfg["default_theme"] == "light"
    assert cfg["standby"] == {"start": "18:00", "end": "07:30", "wake_idle_seconds": 300}
    assert [b["label"] for b in cfg["documents"]["buttons"]] == ["文書1", "文書2", "文書3"]


def test_partial_override_keeps_other_defaults(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(
        json.dumps({"standby": {"start": "19:00"}, "company_name": "テスト(株)"}, ensure_ascii=False),
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg["company_name"] == "テスト(株)"
    assert cfg["standby"] == {"start": "19:00", "end": "07:30", "wake_idle_seconds": 300}


def test_bom_is_accepted(tmp_path):
    p = tmp_path / "config.json"
    p.write_text('{"accident_seconds": 30}', encoding="utf-8-sig")
    assert load_config(p)["accident_seconds"] == 30


def test_broken_json_falls_back_to_defaults(tmp_path, capsys):
    p = tmp_path / "config.json"
    p.write_text("{ broken", encoding="utf-8")
    cfg = load_config(p)
    assert cfg["accident_seconds"] == 15
    assert "config.json" in capsys.readouterr().err


def test_buttons_limited_to_five(tmp_path):
    p = tmp_path / "config.json"
    buttons = [{"label": f"文書{i}", "folder": f"documents/d{i}"} for i in range(7)]
    p.write_text(json.dumps({"documents": {"buttons": buttons}}, ensure_ascii=False), encoding="utf-8")
    assert len(load_config(p)["documents"]["buttons"]) == 5
```

- [ ] **Step 5: 失敗を確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'config'`）

- [ ] **Step 6: `config.py` を書く**

```python
import copy
import json
import sys
from pathlib import Path

DEFAULTS = {
    "company_name": "サンプル工業(株)",
    "default_theme": "light",
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
    "standby": {"start": "18:00", "end": "07:30", "wake_idle_seconds": 300},
}


def _merge(base, over):
    out = dict(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path):
    cfg = copy.deepcopy(DEFAULTS)
    path = Path(path)
    if path.exists():
        try:
            with open(path, encoding="utf-8-sig") as f:
                user = json.load(f)
            if not isinstance(user, dict):
                raise ValueError("設定がオブジェクトではありません")
            cfg = _merge(cfg, user)
        except (OSError, ValueError) as e:
            print(f"[警告] {path.name} を読めないため既定の設定で起動します: {e}", file=sys.stderr)
            cfg = copy.deepcopy(DEFAULTS)
    cfg["documents"]["buttons"] = cfg["documents"]["buttons"][:5]
    return cfg
```

- [ ] **Step 7: テストが通ることを確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py -q`
Expected: `5 passed`

- [ ] **Step 8: 架空のサンプルCSVを作る（UTF-8 BOM付きで保存）**

次の内容を、Python で `encoding="utf-8-sig"` を指定して書き出す（エディタで作るときは「BOM付きUTF-8」で保存）。

```bash
.venv/Scripts/python.exe - <<'EOF'
from pathlib import Path
files = {
    "companies.csv": "name\n1班\n2班\n見本電機\nサンプル建設\n山田\n",
    "leaders.csv": "company,leader_name,ext,outside\n1班,佐藤,1234,\n1班,鈴木,1235,\n2班,高橋,1240,\n見本電機,田中,,03-0000-0001\n見本電機,小林,2345,03-0000-0002\nサンプル建設,伊藤,3456,\n",
    "works.csv": "name\n組み立て作業\n配線工事\nメンテナンス作業\n溶接作業\n高所作業\n搬入作業\n清掃\n",
    "genres.csv": "name\n溶接作業\n高所作業\n電気配線\nその他\n",
    "custom_holidays.csv": "date,name\n2026-12-29,年末休業\n",
}
d = Path("data"); d.mkdir(exist_ok=True)
for name, text in files.items():
    (d / name).write_text(text, encoding="utf-8-sig", newline="\n")
print("ok")
EOF
```

Expected: `ok`。`data/` に5つのCSVができる。

---

### Task 2: 登録リスト・休日・週の判定（`masters.py`）

**Files:**
- Create: `masters.py`, `tests/test_masters.py`

**Interfaces:**
- Produces:
  - `read_csv(path, columns, required=True) -> (rows: list[dict], warning: str | None)`
  - `default_times() -> list[str]`（`"6:00"` … `"22:00"` の30分刻み33個）
  - `class Masters(data_dir)`: `.load_all() -> dict`（キー `companies: list[str]`, `leaders: list[{company,leader_name,ext,outside}]`, `works`, `genres`, `times: list[str]`, `custom_holidays: dict[str,str]`, `warnings: list[str]`）、`.signature() -> str`
  - `holiday_info(d: date, custom: dict) -> {"kind": "" | "saturday" | "holiday", "name": str}`
  - `date_label(d, name) -> str`（例 `11/3(火・文化の日)`）、`day_title(d) -> str`（例 `2026年11月2日（月）`）
  - `week_range(today) -> (monday, sunday)`、`week_holidays(today, custom) -> list[{date,label,kind}]`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_masters.py`:

```python
from datetime import date

import masters as m


def write(path, text):
    path.write_text(text, encoding="utf-8-sig")


def test_read_csv_ok_skips_blank_rows(tmp_path):
    p = tmp_path / "a.csv"
    write(p, "name\n1班\n\n見本電機\n")
    rows, warn = m.read_csv(p, ["name"])
    assert [r["name"] for r in rows] == ["1班", "見本電機"]
    assert warn is None


def test_read_csv_missing_file_warns(tmp_path):
    rows, warn = m.read_csv(tmp_path / "x.csv", ["name"])
    assert rows == []
    assert "x.csv" in warn


def test_read_csv_optional_missing_file_is_silent(tmp_path):
    assert m.read_csv(tmp_path / "x.csv", ["name"], required=False) == ([], None)


def test_read_csv_missing_column_warns(tmp_path):
    p = tmp_path / "a.csv"
    write(p, "title\nabc\n")
    rows, warn = m.read_csv(p, ["name"])
    assert rows == []
    assert "name" in warn


def test_read_csv_shift_jis_file_warns_instead_of_crashing(tmp_path):
    p = tmp_path / "a.csv"
    p.write_bytes("name\n山田\n".encode("cp932"))
    rows, warn = m.read_csv(p, ["name"])
    assert rows == []
    assert "a.csv" in warn


def test_default_times():
    times = m.default_times()
    assert times[0] == "6:00" and times[1] == "6:30" and times[-1] == "22:00"
    assert len(times) == 33


def test_load_all_and_times_file_created(tmp_path):
    write(tmp_path / "companies.csv", "name\n1班\n見本電機\n")
    write(tmp_path / "leaders.csv", "company,leader_name,ext,outside\n1班,佐藤,1234,\n")
    write(tmp_path / "works.csv", "name\n配線工事\n")
    write(tmp_path / "genres.csv", "name\n溶接作業\n")
    data = m.Masters(tmp_path).load_all()
    assert data["companies"] == ["1班", "見本電機"]
    assert data["leaders"] == [{"company": "1班", "leader_name": "佐藤", "ext": "1234", "outside": ""}]
    assert data["works"] == ["配線工事"]
    assert data["genres"] == ["溶接作業"]
    assert data["times"][0] == "6:00"
    assert data["warnings"] == []
    assert (tmp_path / "times.csv").exists()


def test_signature_changes_when_a_file_changes(tmp_path):
    mm = m.Masters(tmp_path)
    before = mm.signature()
    write(tmp_path / "works.csv", "name\n清掃\n")
    assert mm.signature() != before


def test_custom_holidays_skips_bad_dates(tmp_path):
    write(tmp_path / "custom_holidays.csv", "date,name\n2026-12-29,年末休業\nあした,誤り\n")
    custom, warns = m.load_custom_holidays(tmp_path)
    assert custom == {"2026-12-29": "年末休業"}
    assert len(warns) == 1


def test_holiday_info():
    custom = {"2026-11-09": "創立記念日", "2026-11-14": "会社記念日"}
    assert m.holiday_info(date(2026, 11, 3), custom) == {"kind": "holiday", "name": "文化の日"}
    assert m.holiday_info(date(2026, 11, 7), custom) == {"kind": "saturday", "name": ""}
    assert m.holiday_info(date(2026, 11, 8), custom) == {"kind": "holiday", "name": ""}
    assert m.holiday_info(date(2026, 11, 9), custom) == {"kind": "holiday", "name": "創立記念日"}
    assert m.holiday_info(date(2026, 11, 10), custom) == {"kind": "", "name": ""}


def test_saturday_company_holiday_is_red():
    assert m.holiday_info(date(2026, 11, 14), {"2026-11-14": "会社記念日"}) == {
        "kind": "holiday",
        "name": "会社記念日",
    }


def test_week_range_is_monday_to_sunday():
    assert m.week_range(date(2026, 11, 2)) == (date(2026, 11, 2), date(2026, 11, 8))
    assert m.week_range(date(2026, 11, 8)) == (date(2026, 11, 2), date(2026, 11, 8))
    assert m.week_range(date(2026, 11, 9)) == (date(2026, 11, 9), date(2026, 11, 15))


def test_week_holidays_labels():
    result = m.week_holidays(date(2026, 11, 4), {})
    assert [w["label"] for w in result] == ["11/3(火・文化の日)", "11/7(土)", "11/8(日)"]
    assert [w["kind"] for w in result] == ["holiday", "saturday", "holiday"]
    assert result[0]["date"] == "2026-11-03"


def test_day_title():
    assert m.day_title(date(2026, 11, 2)) == "2026年11月2日（月）"
```

- [ ] **Step 2: 失敗を確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/test_masters.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'masters'`）

- [ ] **Step 3: `masters.py` を書く**

```python
import csv
from datetime import date, timedelta
from pathlib import Path

import jpholiday

WEEKDAYS = "月火水木金土日"

FILES = {
    "companies": ("companies.csv", ["name"]),
    "leaders": ("leaders.csv", ["company", "leader_name", "ext", "outside"]),
    "works": ("works.csv", ["name"]),
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
            rows = []
            for raw in reader:
                row = {c: (raw.get(c) or "").strip() for c in columns}
                if any(row.values()):
                    rows.append(row)
            missing = [c for c in columns if c not in (reader.fieldnames or [])]
    except (OSError, UnicodeDecodeError, csv.Error) as e:
        return [], f"{path.name} を読めません（{e}）"
    if missing:
        return [], f"{path.name} に列がありません: {', '.join(missing)}"
    return rows, None


def default_times():
    return [f"{h}:{mi:02d}" for h in range(6, 22) for mi in (0, 30)] + ["22:00"]


def load_custom_holidays(data_dir):
    rows, warn = read_csv(Path(data_dir) / CUSTOM_HOLIDAYS, ["date", "name"], required=False)
    warnings = [warn] if warn else []
    out = {}
    for r in rows:
        try:
            date.fromisoformat(r["date"])
        except ValueError:
            warnings.append(f"{CUSTOM_HOLIDAYS} の日付が正しくありません: {r['date']}")
            continue
        out[r["date"]] = r["name"]
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
            "genres": [r["name"] for r in loaded["genres"]],
            "times": [r["time"] for r in loaded["times"]],
            "custom_holidays": custom,
            "warnings": warnings,
        }

    def signature(self):
        names = [f for f, _ in FILES.values()] + [CUSTOM_HOLIDAYS]
        parts = []
        for name in names:
            p = self.dir / name
            parts.append(str(p.stat().st_mtime_ns) if p.exists() else "-")
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
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/test_masters.py -q`
Expected: `14 passed`

---

### Task 3: データベース（`board_db.py`）

**Files:**
- Create: `board_db.py`, `tests/test_board_db.py`

**Interfaces:**
- Produces: `class BoardDB(path)`（日付は `"YYYY-MM-DD"` の文字列）
  - `get_rev() -> int` / `ensure_day(d)`（その日の初回に、直近の行がある日から作業予定を、直近のチェックがある日から作業ジャンルをコピー。連絡事項は空の3行を作る。1日1回）
  - `list_notices(d) -> [{"id","date","position","text","red":bool}]`（`ensure_day` のあとは常に3件以上）/ `add_notice(d) -> int` / `update_notice(id, fields) -> bool`（`fields` は `text` `red`）/ `delete_notice(id) -> bool`（残りが3行未満になるときは `ValueError`。下の行を詰める）
  - `list_schedule(d) -> list[dict]`（`id, date, position, company, leader, work, start_time, end_time`）/ `get_schedule_row(id) -> dict|None` / `add_schedule_row(d) -> int` / `update_schedule_row(id, fields) -> bool`（許可外の列は `ValueError`）/ `delete_schedule_row(id) -> bool`（下の行を詰める）/ `move_schedule_row(id, direction: "up"|"down") -> bool`
  - `list_holiday_rows(start, end) -> list[dict]`（`id, date, person, work, start_time, end_time`、日付順→id順）/ `get_holiday_row(id)` / `add_holiday_row(d) -> int` / `update_holiday_row(id, fields) -> bool` / `delete_holiday_row(id) -> bool`
  - `get_checked_genres(d) -> list[str]` / `set_genre(d, genre, checked)`
- 定数: `SCHEDULE_FIELDS = ("company","leader","work","start_time","end_time")`、`HOLIDAY_FIELDS = ("date","person","work","start_time","end_time")`、`NOTICE_FIELDS = ("text","red")`、`MIN_NOTICES = 3`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_board_db.py`:

```python
import pytest

from board_db import BoardDB

D1, D2 = "2026-11-02", "2026-11-03"
MONDAY_AFTER = "2026-11-09"


@pytest.fixture
def db(tmp_path):
    return BoardDB(tmp_path / "board.db")


def add_rows(db, d, names):
    db.ensure_day(d)
    for n in names:
        rid = db.add_schedule_row(d)
        db.update_schedule_row(rid, {"company": n})


def companies(db, d):
    return [r["company"] for r in db.list_schedule(d)]


def test_carry_over_copies_previous_rows(db):
    add_rows(db, D1, ["1班", "見本電機"])
    db.ensure_day(D2)
    assert companies(db, D2) == ["1班", "見本電機"]
    assert companies(db, D1) == ["1班", "見本電機"]


def test_carry_over_is_independent_copy(db):
    add_rows(db, D1, ["1班"])
    db.ensure_day(D2)
    row = db.list_schedule(D2)[0]
    db.update_schedule_row(row["id"], {"company": "2班"})
    assert companies(db, D1) == ["1班"]


def test_carry_over_across_weekend_uses_latest_day_with_rows(db):
    add_rows(db, D1, ["1班", "2班"])
    db.ensure_day(MONDAY_AFTER)
    assert companies(db, MONDAY_AFTER) == ["1班", "2班"]


def test_ensure_day_twice_does_not_duplicate(db):
    add_rows(db, D1, ["1班"])
    db.ensure_day(D2)
    db.ensure_day(D2)
    assert companies(db, D2) == ["1班"]


def test_delete_all_then_no_recopy(db):
    add_rows(db, D1, ["1班", "2班"])
    db.ensure_day(D2)
    for r in db.list_schedule(D2):
        db.delete_schedule_row(r["id"])
    db.ensure_day(D2)
    assert db.list_schedule(D2) == []


def test_no_previous_day_starts_empty(db):
    db.ensure_day(D1)
    assert db.list_schedule(D1) == []


def test_delete_compacts_positions(db):
    add_rows(db, D1, ["A", "B", "C"])
    rows = db.list_schedule(D1)
    assert db.delete_schedule_row(rows[1]["id"]) is True
    after = db.list_schedule(D1)
    assert [(r["company"], r["position"]) for r in after] == [("A", 1), ("C", 2)]
    new_id = db.add_schedule_row(D1)
    assert db.get_schedule_row(new_id)["position"] == 3


def test_delete_missing_row_returns_false(db):
    assert db.delete_schedule_row(999) is False


def test_move_up_and_down(db):
    add_rows(db, D1, ["A", "B", "C"])
    ids = {r["company"]: r["id"] for r in db.list_schedule(D1)}
    assert db.move_schedule_row(ids["C"], "up") is True
    assert companies(db, D1) == ["A", "C", "B"]
    assert db.move_schedule_row(ids["A"], "up") is False
    assert db.move_schedule_row(ids["B"], "down") is False
    assert db.move_schedule_row(ids["A"], "down") is True
    assert companies(db, D1) == ["C", "A", "B"]


def test_update_rejects_unknown_field_and_missing_row(db):
    add_rows(db, D1, ["A"])
    rid = db.list_schedule(D1)[0]["id"]
    with pytest.raises(ValueError):
        db.update_schedule_row(rid, {"position": 9})
    assert db.update_schedule_row(999, {"company": "X"}) is False


def test_notices_start_with_three_empty_rows(db):
    db.ensure_day(D1)
    rows = db.list_notices(D1)
    assert [r["position"] for r in rows] == [1, 2, 3]
    assert all(r["text"] == "" and r["red"] is False for r in rows)


def test_notice_add_update_delete_compacts(db):
    db.ensure_day(D1)
    new_id = db.add_notice(D1)
    assert [r["position"] for r in db.list_notices(D1)] == [1, 2, 3, 4]
    assert db.update_notice(new_id, {"text": "避難訓練", "red": True}) is True
    rows = db.list_notices(D1)
    assert (rows[3]["text"], rows[3]["red"]) == ("避難訓練", True)
    assert db.delete_notice(rows[1]["id"]) is True
    after = db.list_notices(D1)
    assert [r["position"] for r in after] == [1, 2, 3]
    assert after[2]["text"] == "避難訓練"


def test_notices_cannot_go_below_three(db):
    db.ensure_day(D1)
    rows = db.list_notices(D1)
    with pytest.raises(ValueError):
        db.delete_notice(rows[0]["id"])
    assert len(db.list_notices(D1)) == 3
    assert db.delete_notice(999) is False


def test_notices_are_not_carried_over(db):
    db.ensure_day(D1)
    db.update_notice(db.list_notices(D1)[0]["id"], {"text": "昨日の連絡"})
    db.ensure_day(D2)
    assert [r["text"] for r in db.list_notices(D2)] == ["", "", ""]


def test_genres_toggle_and_carry_over(db):
    db.ensure_day(D1)
    db.set_genre(D1, "溶接作業", True)
    db.set_genre(D1, "高所作業", True)
    db.set_genre(D1, "高所作業", False)
    assert db.get_checked_genres(D1) == ["溶接作業"]
    db.ensure_day(D2)
    assert db.get_checked_genres(D2) == ["溶接作業"]
    db.set_genre(D2, "溶接作業", False)
    assert db.get_checked_genres(D1) == ["溶接作業"]


def test_holiday_rows_filtered_by_range_and_sorted(db):
    for d in ["2026-11-07", "2026-11-03", "2026-10-31"]:
        db.add_holiday_row(d)
    rows = db.list_holiday_rows("2026-11-02", "2026-11-08")
    assert [r["date"] for r in rows] == ["2026-11-03", "2026-11-07"]


def test_holiday_row_update_and_delete(db):
    rid = db.add_holiday_row("2026-11-07")
    assert db.update_holiday_row(rid, {"person": "山田", "work": "清掃"}) is True
    assert db.get_holiday_row(rid)["person"] == "山田"
    assert db.delete_holiday_row(rid) is True
    assert db.get_holiday_row(rid) is None


def test_rev_increases_on_every_write(db):
    r0 = db.get_rev()
    db.ensure_day(D1)
    r1 = db.get_rev()
    rid = db.add_schedule_row(D1)
    r2 = db.get_rev()
    db.update_schedule_row(rid, {"company": "A"})
    r3 = db.get_rev()
    assert r0 < r1 < r2 < r3
    db.ensure_day(D1)
    assert db.get_rev() == r3
```

- [ ] **Step 2: 失敗を確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/test_board_db.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'board_db'`）

- [ ] **Step 3: `board_db.py` を書く**

```python
import sqlite3
from contextlib import contextmanager

SCHEDULE_FIELDS = ("company", "leader", "work", "start_time", "end_time")
HOLIDAY_FIELDS = ("date", "person", "work", "start_time", "end_time")
NOTICE_FIELDS = ("text", "red")
MIN_NOTICES = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value INTEGER NOT NULL);
INSERT OR IGNORE INTO meta(key, value) VALUES ('rev', 0);
CREATE TABLE IF NOT EXISTS days(
    date TEXT PRIMARY KEY,
    schedule_initialized INTEGER NOT NULL DEFAULT 0,
    genres_initialized INTEGER NOT NULL DEFAULT 0,
    notices_initialized INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS notice_rows(
    id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, position INTEGER NOT NULL,
    text TEXT NOT NULL DEFAULT '', red INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS schedule_rows(
    id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, position INTEGER NOT NULL,
    company TEXT NOT NULL DEFAULT '', leader TEXT NOT NULL DEFAULT '',
    work TEXT NOT NULL DEFAULT '', start_time TEXT NOT NULL DEFAULT '',
    end_time TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS holiday_rows(
    id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL,
    person TEXT NOT NULL DEFAULT '', work TEXT NOT NULL DEFAULT '',
    start_time TEXT NOT NULL DEFAULT '', end_time TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS checked_genres(
    date TEXT NOT NULL, genre TEXT NOT NULL, PRIMARY KEY(date, genre));
"""


class BoardDB:
    def __init__(self, path):
        self.path = str(path)
        with self._tx() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _tx(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _bump(c):
        c.execute("UPDATE meta SET value = value + 1 WHERE key = 'rev'")

    def get_rev(self):
        with self._tx() as c:
            return c.execute("SELECT value FROM meta WHERE key = 'rev'").fetchone()["value"]

    # ---- 日付の初期化（前日の引き継ぎ） ----
    def ensure_day(self, d):
        with self._tx() as c:
            c.execute("INSERT OR IGNORE INTO days(date) VALUES (?)", (d,))
            flags = c.execute(
                "SELECT schedule_initialized AS s, genres_initialized AS g, notices_initialized AS n "
                "FROM days WHERE date = ?",
                (d,),
            ).fetchone()
            changed = False
            if not flags["s"]:
                prev = c.execute("SELECT MAX(date) AS m FROM schedule_rows WHERE date < ?", (d,)).fetchone()["m"]
                if prev:
                    c.execute(
                        "INSERT INTO schedule_rows(date, position, company, leader, work, start_time, end_time) "
                        "SELECT ?, position, company, leader, work, start_time, end_time "
                        "FROM schedule_rows WHERE date = ? ORDER BY position",
                        (d, prev),
                    )
                c.execute("UPDATE days SET schedule_initialized = 1 WHERE date = ?", (d,))
                changed = True
            if not flags["g"]:
                prev = c.execute("SELECT MAX(date) AS m FROM checked_genres WHERE date < ?", (d,)).fetchone()["m"]
                if prev:
                    c.execute(
                        "INSERT INTO checked_genres(date, genre) SELECT ?, genre FROM checked_genres WHERE date = ?",
                        (d, prev),
                    )
                c.execute("UPDATE days SET genres_initialized = 1 WHERE date = ?", (d,))
                changed = True
            if not flags["n"]:
                c.executemany(
                    "INSERT INTO notice_rows(date, position) VALUES (?, ?)",
                    [(d, i) for i in range(1, MIN_NOTICES + 1)],
                )
                c.execute("UPDATE days SET notices_initialized = 1 WHERE date = ?", (d,))
                changed = True
            if changed:
                self._bump(c)

    # ---- 連絡事項 ----
    def list_notices(self, d):
        with self._tx() as c:
            rows = c.execute("SELECT * FROM notice_rows WHERE date = ? ORDER BY position", (d,)).fetchall()
        return [{**dict(r), "red": bool(r["red"])} for r in rows]

    def add_notice(self, d):
        with self._tx() as c:
            pos = c.execute(
                "SELECT COALESCE(MAX(position), 0) + 1 AS p FROM notice_rows WHERE date = ?", (d,)
            ).fetchone()["p"]
            cur = c.execute("INSERT INTO notice_rows(date, position) VALUES (?, ?)", (d, pos))
            self._bump(c)
            return cur.lastrowid

    def update_notice(self, row_id, fields):
        return self._update("notice_rows", NOTICE_FIELDS, row_id, fields)

    def delete_notice(self, row_id):
        with self._tx() as c:
            row = c.execute("SELECT date, position FROM notice_rows WHERE id = ?", (row_id,)).fetchone()
            if not row:
                return False
            count = c.execute("SELECT COUNT(*) AS n FROM notice_rows WHERE date = ?", (row["date"],)).fetchone()["n"]
            if count <= MIN_NOTICES:
                raise ValueError("連絡事項は3行より少なくできません")
            c.execute("DELETE FROM notice_rows WHERE id = ?", (row_id,))
            c.execute(
                "UPDATE notice_rows SET position = position - 1 WHERE date = ? AND position > ?",
                (row["date"], row["position"]),
            )
            self._bump(c)
            return True

    # ---- 共通 ----
    def _update(self, table, allowed, row_id, fields):
        bad = [k for k in fields if k not in allowed]
        if bad:
            raise ValueError(f"更新できない列: {bad}")
        if not fields:
            return False
        sets = ", ".join(f"{k} = ?" for k in fields)
        with self._tx() as c:
            cur = c.execute(f"UPDATE {table} SET {sets} WHERE id = ?", (*fields.values(), row_id))
            if cur.rowcount:
                self._bump(c)
            return cur.rowcount > 0

    def _get(self, table, row_id):
        with self._tx() as c:
            r = c.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
        return dict(r) if r else None

    # ---- 本日の作業予定 ----
    def list_schedule(self, d):
        with self._tx() as c:
            rows = c.execute("SELECT * FROM schedule_rows WHERE date = ? ORDER BY position", (d,)).fetchall()
        return [dict(r) for r in rows]

    def get_schedule_row(self, row_id):
        return self._get("schedule_rows", row_id)

    def add_schedule_row(self, d):
        with self._tx() as c:
            pos = c.execute(
                "SELECT COALESCE(MAX(position), 0) + 1 AS p FROM schedule_rows WHERE date = ?", (d,)
            ).fetchone()["p"]
            cur = c.execute("INSERT INTO schedule_rows(date, position) VALUES (?, ?)", (d, pos))
            self._bump(c)
            return cur.lastrowid

    def update_schedule_row(self, row_id, fields):
        return self._update("schedule_rows", SCHEDULE_FIELDS, row_id, fields)

    def delete_schedule_row(self, row_id):
        with self._tx() as c:
            row = c.execute("SELECT date, position FROM schedule_rows WHERE id = ?", (row_id,)).fetchone()
            if not row:
                return False
            c.execute("DELETE FROM schedule_rows WHERE id = ?", (row_id,))
            c.execute(
                "UPDATE schedule_rows SET position = position - 1 WHERE date = ? AND position > ?",
                (row["date"], row["position"]),
            )
            self._bump(c)
            return True

    def move_schedule_row(self, row_id, direction):
        if direction not in ("up", "down"):
            raise ValueError("direction は up / down")
        with self._tx() as c:
            row = c.execute("SELECT date, position FROM schedule_rows WHERE id = ?", (row_id,)).fetchone()
            if not row:
                return False
            target = row["position"] + (-1 if direction == "up" else 1)
            other = c.execute(
                "SELECT id FROM schedule_rows WHERE date = ? AND position = ?", (row["date"], target)
            ).fetchone()
            if not other:
                return False
            c.execute("UPDATE schedule_rows SET position = ? WHERE id = ?", (target, row_id))
            c.execute("UPDATE schedule_rows SET position = ? WHERE id = ?", (row["position"], other["id"]))
            self._bump(c)
            return True

    # ---- 休日出勤予定 ----
    def list_holiday_rows(self, start, end):
        with self._tx() as c:
            rows = c.execute(
                "SELECT * FROM holiday_rows WHERE date >= ? AND date <= ? ORDER BY date, id", (start, end)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_holiday_row(self, row_id):
        return self._get("holiday_rows", row_id)

    def add_holiday_row(self, d):
        with self._tx() as c:
            cur = c.execute("INSERT INTO holiday_rows(date) VALUES (?)", (d,))
            self._bump(c)
            return cur.lastrowid

    def update_holiday_row(self, row_id, fields):
        return self._update("holiday_rows", HOLIDAY_FIELDS, row_id, fields)

    def delete_holiday_row(self, row_id):
        with self._tx() as c:
            cur = c.execute("DELETE FROM holiday_rows WHERE id = ?", (row_id,))
            if cur.rowcount:
                self._bump(c)
            return cur.rowcount > 0

    # ---- 作業ジャンル ----
    def get_checked_genres(self, d):
        with self._tx() as c:
            rows = c.execute("SELECT genre FROM checked_genres WHERE date = ? ORDER BY genre", (d,)).fetchall()
        return [r["genre"] for r in rows]

    def set_genre(self, d, genre, checked):
        with self._tx() as c:
            if checked:
                c.execute("INSERT OR IGNORE INTO checked_genres(date, genre) VALUES (?, ?)", (d, genre))
            else:
                c.execute("DELETE FROM checked_genres WHERE date = ? AND genre = ?", (d, genre))
            self._bump(c)
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/test_board_db.py -q`
Expected: `18 passed`

---

### Task 4: 災害事例のファイル判定（`accident.py`）

**Files:**
- Create: `accident.py`, `tests/test_accident.py`

**Interfaces:**
- Produces:
  - `natural_key(name) -> list`（「事例2」が「事例10」より前になる並べ替えキー）
  - `file_genres(filename, known: list[str]) -> list[str]`（ファイル名の先頭〜最初の `_` までを `＋`/`+` で分け、`known` にあるものだけ返す）
  - `playlist(folder, genre_order: list[str], checked: set[str]) -> list[str]`（ファイル名のリスト。ジャンル順→自然順）
  - `list_pdfs(folder) -> list[str]`（文書ボタンでも使う）

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_accident.py`:

```python
import accident as acc

GENRES = ["溶接作業", "高所作業", "電気配線", "その他"]


def test_file_genres_single_and_multi():
    assert acc.file_genres("溶接作業_事例A.pdf", GENRES) == ["溶接作業"]
    assert acc.file_genres("溶接作業＋高所作業_事例A.pdf", GENRES) == ["溶接作業", "高所作業"]
    assert acc.file_genres("溶接作業+電気配線_事例A.pdf", GENRES) == ["溶接作業", "電気配線"]


def test_file_genres_ignores_unknown_and_missing_underscore():
    assert acc.file_genres("不明_事例.pdf", GENRES) == []
    assert acc.file_genres("溶接作業.pdf", GENRES) == []
    assert acc.file_genres("溶接作業＋不明_事例.pdf", GENRES) == ["溶接作業"]


def test_natural_key_orders_numbers():
    names = ["溶接作業_事例10.pdf", "溶接作業_事例2.pdf", "溶接作業_事例1.pdf"]
    assert sorted(names, key=acc.natural_key) == [
        "溶接作業_事例1.pdf",
        "溶接作業_事例2.pdf",
        "溶接作業_事例10.pdf",
    ]


def make_files(folder, names):
    for n in names:
        (folder / n).write_bytes(b"%PDF-1.4")


def test_playlist_order_and_filtering(tmp_path):
    make_files(
        tmp_path,
        [
            "高所作業_b.pdf",
            "溶接作業_事例10.pdf",
            "溶接作業_事例2.pdf",
            "電気配線_c.pdf",
            "不明_x.pdf",
            "memo.txt",
            "溶接作業＋高所作業_both.pdf",
        ],
    )
    result = acc.playlist(tmp_path, GENRES, {"溶接作業", "高所作業"})
    assert result == [
        "溶接作業_事例2.pdf",
        "溶接作業_事例10.pdf",
        "溶接作業＋高所作業_both.pdf",
        "高所作業_b.pdf",
    ]


def test_playlist_does_not_duplicate_multi_genre_file(tmp_path):
    make_files(tmp_path, ["溶接作業＋高所作業_both.pdf"])
    assert acc.playlist(tmp_path, GENRES, {"溶接作業", "高所作業"}) == ["溶接作業＋高所作業_both.pdf"]


def test_playlist_nothing_checked_or_missing_folder(tmp_path):
    make_files(tmp_path, ["溶接作業_a.pdf"])
    assert acc.playlist(tmp_path, GENRES, set()) == []
    assert acc.playlist(tmp_path / "nothing", GENRES, {"溶接作業"}) == []


def test_pdf_extension_is_case_insensitive(tmp_path):
    make_files(tmp_path, ["溶接作業_a.PDF"])
    assert acc.playlist(tmp_path, GENRES, {"溶接作業"}) == ["溶接作業_a.PDF"]


def test_list_pdfs(tmp_path):
    make_files(tmp_path, ["b.pdf", "a10.pdf", "a2.pdf", "note.txt"])
    assert acc.list_pdfs(tmp_path) == ["a2.pdf", "a10.pdf", "b.pdf"]
    assert acc.list_pdfs(tmp_path / "none") == []
```

- [ ] **Step 2: 失敗を確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/test_accident.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'accident'`）

- [ ] **Step 3: `accident.py` を書く**

```python
import re
from pathlib import Path


def natural_key(name):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", name)]


def file_genres(filename, known):
    stem = Path(filename).stem
    if "_" not in stem:
        return []
    head = stem.split("_", 1)[0]
    names = [n.strip() for n in re.split(r"[＋+]", head)]
    return [n for n in names if n in known]


def _pdfs(folder):
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return [p.name for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"]


def list_pdfs(folder):
    return sorted(_pdfs(folder), key=natural_key)


def playlist(folder, genre_order, checked):
    items = []
    for name in _pdfs(folder):
        hits = [genre_order.index(g) for g in file_genres(name, genre_order) if g in checked]
        if hits:
            items.append((min(hits), natural_key(name), name))
    return [name for _, _, name in sorted(items)]
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/test_accident.py -q`
Expected: `8 passed`

---

### Task 5: Webサーバーと API（`app.py`）

**Files:**
- Create: `app.py`, `tests/test_api.py`

**Interfaces:**
- Consumes: Task 1〜4 の関数すべて
- Produces: `create_app(base_dir=None, today_func=date.today) -> Flask`。URL は次のとおり（JSON、日本語は UTF-8）。
  - `GET /` → `static/board.html`
  - `GET /api/rev` → `{"rev": str, "today": "YYYY-MM-DD"}`
  - `GET /api/board` → `{today, date_label, company_name, settings{accident_seconds, edit_lock_seconds, documents_idle_seconds, default_theme, standby{start,end,wake_idle_seconds}}, notices[{id,position,text,red}], schedule[{id,position,company,leader,work,start_time,end_time,ext,outside}], holiday_rows[{id,date,person,work,start_time,end_time,label,kind}], week_holidays[{date,label,kind}], checked_genres[], accident[{name,url}], masters{companies,leaders,works,genres,times}, doc_buttons[{index,label}], warnings[]}`
  - `POST /api/notices` → `{id}`（連絡事項の行を1つ足す）/ `PATCH /api/notices/<id>` `{text?, red?}` / `DELETE /api/notices/<id>`（残りが3行未満になるときは 400）
  - `POST /api/schedule` → `{id}` / `PATCH /api/schedule/<id>` `{company?,leader?,work?,start_time?,end_time?}` / `DELETE /api/schedule/<id>` / `POST /api/schedule/<id>/move` `{direction}`
  - `POST /api/holiday-rows` `{date}` → `{id}` / `PATCH /api/holiday-rows/<id>` `{date?,person?,work?,start_time?,end_time?}` / `DELETE /api/holiday-rows/<id>`
  - `POST /api/genres/toggle` `{name, checked}`
  - `GET /api/accident/file/<name>` / `GET /api/documents/<idx>/files` → `[name]` / `GET /api/documents/<idx>/pdf/<name>`
  - エラーは `{"error": "..."}` と 400/404

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_api.py`:

```python
import time
from datetime import date
from urllib.parse import quote

import pytest

from app import create_app

COMPANIES = "name\n1班\n見本電機\n山田\n"
LEADERS = (
    "company,leader_name,ext,outside\n"
    "1班,佐藤,1234,\n1班,鈴木,1235,\n見本電機,田中,,03-0000-0001\n"
)
WORKS = "name\n組み立て作業\n配線工事\n"
GENRES = "name\n溶接作業\n高所作業\n電気配線\nその他\n"


@pytest.fixture
def env(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    for name, text in [
        ("companies.csv", COMPANIES),
        ("leaders.csv", LEADERS),
        ("works.csv", WORKS),
        ("genres.csv", GENRES),
    ]:
        (data / name).write_text(text, encoding="utf-8-sig")
    clock = {"today": date(2026, 11, 2)}
    app = create_app(tmp_path, today_func=lambda: clock["today"])
    return app.test_client(), clock, tmp_path


def board(c):
    r = c.get("/api/board")
    assert r.status_code == 200
    return r.get_json()


def add_row(c, **fields):
    rid = c.post("/api/schedule").get_json()["id"]
    if fields:
        assert c.patch(f"/api/schedule/{rid}", json=fields).status_code == 200
    return rid


def test_board_basics(env):
    c, _, _ = env
    b = board(c)
    assert b["today"] == "2026-11-02"
    assert b["date_label"] == "2026年11月2日（月）"
    assert b["company_name"] == "サンプル工業(株)"
    assert b["schedule"] == [] and b["holiday_rows"] == []
    assert [n["position"] for n in b["notices"]] == [1, 2, 3]
    assert b["masters"]["genres"] == ["溶接作業", "高所作業", "電気配線", "その他"]
    assert b["doc_buttons"] == [
        {"index": 0, "label": "文書1"},
        {"index": 1, "label": "文書2"},
        {"index": 2, "label": "文書3"},
    ]
    assert b["settings"]["accident_seconds"] == 15
    assert b["settings"]["default_theme"] == "light"
    assert b["warnings"] == []


def test_schedule_add_patch_and_contact(env):
    c, _, _ = env
    add_row(c, company="1班", leader="佐藤", work="組み立て作業", start_time="9:00", end_time="15:00")
    add_row(c, company="見本電機", leader="田中")
    rows = board(c)["schedule"]
    assert (rows[0]["ext"], rows[0]["outside"]) == ("1234", "")
    assert (rows[1]["ext"], rows[1]["outside"]) == ("", "03-0000-0001")
    assert rows[0]["start_time"] == "9:00"


def test_changing_company_clears_leader(env):
    c, _, _ = env
    rid = add_row(c, company="1班", leader="佐藤")
    assert c.patch(f"/api/schedule/{rid}", json={"company": "見本電機"}).status_code == 200
    assert board(c)["schedule"][0]["leader"] == ""


def test_leader_must_belong_to_company(env):
    c, _, _ = env
    rid = add_row(c, company="1班")
    r = c.patch(f"/api/schedule/{rid}", json={"leader": "田中"})
    assert r.status_code == 400
    assert board(c)["schedule"][0]["leader"] == ""


def test_values_must_be_registered(env):
    c, _, _ = env
    rid = add_row(c)
    assert c.patch(f"/api/schedule/{rid}", json={"company": "未登録会社"}).status_code == 400
    assert c.patch(f"/api/schedule/{rid}", json={"work": "未登録作業"}).status_code == 400
    assert c.patch(f"/api/schedule/{rid}", json={"start_time": "25:00"}).status_code == 400
    assert c.patch(f"/api/schedule/{rid}", json={"company": 5}).status_code == 400
    assert c.patch(f"/api/schedule/{rid}", json={"company": ""}).status_code == 200


def test_overnight_time_is_accepted(env):
    c, _, _ = env
    rid = add_row(c)
    r = c.patch(f"/api/schedule/{rid}", json={"start_time": "22:00", "end_time": "6:00"})
    assert r.status_code == 200


def test_patch_and_delete_missing_row_return_404(env):
    c, _, _ = env
    assert c.patch("/api/schedule/999", json={"company": "1班"}).status_code == 404
    assert c.delete("/api/schedule/999").status_code == 404
    assert c.post("/api/schedule/999/move", json={"direction": "up"}).status_code == 404


def test_delete_compacts_and_move(env):
    c, _, _ = env
    add_row(c, company="1班")
    add_row(c, company="見本電機")
    add_row(c, company="山田")
    rows = board(c)["schedule"]
    assert c.post(f"/api/schedule/{rows[2]['id']}/move", json={"direction": "up"}).status_code == 200
    assert [r["company"] for r in board(c)["schedule"]] == ["1班", "山田", "見本電機"]
    assert c.delete(f"/api/schedule/{rows[0]['id']}").status_code == 200
    after = board(c)["schedule"]
    assert [r["company"] for r in after] == ["山田", "見本電機"]
    assert [r["position"] for r in after] == [1, 2]


def test_move_at_edge_is_noop_200(env):
    c, _, _ = env
    rid = add_row(c, company="1班")
    r = c.post(f"/api/schedule/{rid}/move", json={"direction": "up"})
    assert r.status_code == 200


def test_carry_over_next_day(env):
    c, clock, _ = env
    first = add_row(c, company="1班")
    clock["today"] = date(2026, 11, 3)
    rows = board(c)["schedule"]
    assert [r["company"] for r in rows] == ["1班"]
    assert rows[0]["id"] != first


def test_notices_add_patch_delete(env):
    c, _, _ = env
    new_id = c.post("/api/notices").get_json()["id"]
    assert c.patch(f"/api/notices/{new_id}", json={"text": "避難訓練", "red": True}).status_code == 200
    notices = board(c)["notices"]
    assert len(notices) == 4
    assert (notices[3]["text"], notices[3]["red"]) == ("避難訓練", True)
    assert c.delete(f"/api/notices/{notices[0]['id']}").status_code == 200
    after = board(c)["notices"]
    assert [n["position"] for n in after] == [1, 2, 3]
    assert after[2]["text"] == "避難訓練"


def test_notices_cannot_be_deleted_below_three(env):
    c, _, _ = env
    first = board(c)["notices"][0]["id"]
    assert c.delete(f"/api/notices/{first}").status_code == 400
    assert c.delete("/api/notices/999").status_code == 404
    assert c.patch("/api/notices/999", json={"text": "x"}).status_code == 404
    assert c.patch(f"/api/notices/{first}", json={"text": 5}).status_code == 400
    assert c.patch(f"/api/notices/{first}", json={}).status_code == 400
    assert len(board(c)["notices"]) == 3


def test_holiday_rows_only_on_this_weeks_holidays(env):
    c, _, _ = env
    assert c.post("/api/holiday-rows", json={"date": "2026-11-04"}).status_code == 400
    assert c.post("/api/holiday-rows", json={"date": "2026-11-09"}).status_code == 400
    r = c.post("/api/holiday-rows", json={"date": "2026-11-07"})
    assert r.status_code == 200
    rid = r.get_json()["id"]
    assert c.patch(f"/api/holiday-rows/{rid}", json={"person": "山田", "work": "配線工事"}).status_code == 200
    assert c.patch(f"/api/holiday-rows/{rid}", json={"date": "2026-11-04"}).status_code == 400
    assert c.patch(f"/api/holiday-rows/{rid}", json={"date": "2026-11-03"}).status_code == 200
    b = board(c)
    assert [w["label"] for w in b["week_holidays"]] == ["11/3(火・文化の日)", "11/7(土)", "11/8(日)"]
    row = b["holiday_rows"][0]
    assert (row["label"], row["kind"], row["person"]) == ("11/3(火・文化の日)", "holiday", "山田")


def test_holiday_rows_sorted_by_date(env):
    c, _, _ = env
    c.post("/api/holiday-rows", json={"date": "2026-11-07"})
    c.post("/api/holiday-rows", json={"date": "2026-11-03"})
    assert [r["date"] for r in board(c)["holiday_rows"]] == ["2026-11-03", "2026-11-07"]


def test_monday_resets_holiday_rows(env):
    c, clock, _ = env
    c.post("/api/holiday-rows", json={"date": "2026-11-07"})
    assert len(board(c)["holiday_rows"]) == 1
    clock["today"] = date(2026, 11, 9)
    b = board(c)
    assert b["holiday_rows"] == []
    assert [w["date"] for w in b["week_holidays"]] == ["2026-11-14", "2026-11-15"]


def test_company_holiday_can_be_chosen(env):
    c, _, base = env
    (base / "data" / "custom_holidays.csv").write_text("date,name\n2026-11-05,創立記念日\n", encoding="utf-8-sig")
    labels = [w["label"] for w in board(c)["week_holidays"]]
    assert "11/5(木・創立記念日)" in labels
    assert c.post("/api/holiday-rows", json={"date": "2026-11-05"}).status_code == 200


def test_genre_toggle_must_be_registered(env):
    c, _, _ = env
    assert c.post("/api/genres/toggle", json={"name": "未登録", "checked": True}).status_code == 400
    assert c.post("/api/genres/toggle", json={"name": "溶接作業", "checked": True}).status_code == 200
    assert board(c)["checked_genres"] == ["溶接作業"]
    c.post("/api/genres/toggle", json={"name": "溶接作業", "checked": False})
    assert board(c)["checked_genres"] == []


def test_accident_playlist(env):
    c, _, base = env
    folder = base / "accident_cases"
    for n in ["溶接作業_b.pdf", "溶接作業_a.pdf", "高所作業_x.pdf", "不明_y.pdf", "memo.txt"]:
        (folder / n).write_bytes(b"%PDF-1.4")
    assert board(c)["accident"] == []
    c.post("/api/genres/toggle", json={"name": "溶接作業", "checked": True})
    b = board(c)
    assert [a["name"] for a in b["accident"]] == ["溶接作業_a.pdf", "溶接作業_b.pdf"]
    assert b["accident"][0]["url"] == "/api/accident/file/" + quote("溶接作業_a.pdf")
    assert c.get(b["accident"][0]["url"]).status_code == 200
    assert c.get("/api/accident/file/" + quote("存在しない.pdf")).status_code == 404


def test_documents(env):
    c, _, base = env
    folder = base / "documents" / "doc1"
    (folder / "手順書2.pdf").write_bytes(b"%PDF-1.4")
    (folder / "手順書10.pdf").write_bytes(b"%PDF-1.4")
    assert c.get("/api/documents/0/files").get_json() == ["手順書2.pdf", "手順書10.pdf"]
    assert c.get("/api/documents/1/files").get_json() == []
    assert c.get("/api/documents/9/files").status_code == 404
    assert c.get("/api/documents/0/pdf/" + quote("手順書2.pdf")).status_code == 200
    assert c.get("/api/documents/0/pdf/..%2F..%2Fconfig.json").status_code == 404


def test_broken_csv_gives_warning_not_error(env):
    c, _, base = env
    (base / "data" / "works.csv").write_bytes("name\n組み立て作業\n".encode("cp932"))
    b = board(c)
    assert b["masters"]["works"] == []
    assert any("works.csv" in w for w in b["warnings"])


def test_rev_changes_on_write_and_on_csv_edit(env):
    c, _, base = env
    r0 = c.get("/api/rev").get_json()["rev"]
    add_row(c)
    r1 = c.get("/api/rev").get_json()["rev"]
    assert r1 != r0
    time.sleep(0.02)
    (base / "data" / "works.csv").write_text("name\n清掃\n", encoding="utf-8-sig")
    assert c.get("/api/rev").get_json()["rev"] != r1
    assert c.get("/api/rev").get_json()["today"] == "2026-11-02"
```

- [ ] **Step 2: 失敗を確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'app'`）

- [ ] **Step 3: `app.py` を書く**

```python
import mimetypes
import socket
from datetime import date
from pathlib import Path
from urllib.parse import quote

from flask import Flask, jsonify, request, send_from_directory

import accident as acc
import masters as mst
from board_db import HOLIDAY_FIELDS, SCHEDULE_FIELDS, BoardDB
from config import load_config

PORT = 5100

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
    cfg = load_config(base / "config.json")
    data_dir = base / "data"
    data_dir.mkdir(exist_ok=True)
    db = BoardDB(data_dir / "board.db")
    masters = mst.Masters(data_dir)
    accident_dir = _resolve(base, cfg["accident_folder"])
    accident_dir.mkdir(parents=True, exist_ok=True)
    doc_buttons = cfg["documents"]["buttons"]
    doc_dirs = [_resolve(base, b["folder"]) for b in doc_buttons]
    for d in doc_dirs:
        d.mkdir(parents=True, exist_ok=True)

    app = Flask(__name__, static_folder=str(Path(__file__).resolve().parent / "static"), static_url_path="")
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

    def bad(message, code=400):
        return jsonify({"error": message}), code

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

    # ---- 画面 ----
    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "board.html")

    @app.get("/api/rev")
    def api_rev():
        rev = f"{db.get_rev()}:{masters.signature()}:{_dir_signature(accident_dir)}"
        return jsonify({"rev": rev, "today": today_func().isoformat()})

    @app.get("/api/board")
    def api_board():
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

        checked = db.get_checked_genres(d)
        names = acc.playlist(accident_dir, m["genres"], set(checked))
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
                    "standby": cfg["standby"],
                },
                "notices": db.list_notices(d),
                "schedule": schedule,
                "holiday_rows": holiday_rows,
                "week_holidays": week_holidays(m),
                "checked_genres": checked,
                "accident": [{"name": n, "url": "/api/accident/file/" + quote(n)} for n in names],
                "masters": {k: m[k] for k in ("companies", "leaders", "works", "genres", "times")},
                "doc_buttons": [{"index": i, "label": b["label"]} for i, b in enumerate(doc_buttons)],
                "warnings": m["warnings"],
            }
        )

    # ---- 連絡事項 ----
    @app.post("/api/notices")
    def api_add_notice():
        return jsonify({"id": db.add_notice(prepare())})

    @app.patch("/api/notices/<int:row_id>")
    def api_patch_notice(row_id):
        prepare()
        body = request.get_json(silent=True) or {}
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
        fields = clean_fields(request.get_json(silent=True) or {}, SCHEDULE_FIELDS)
        if fields is None:
            return bad("値が文字列ではありません")
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
        direction = (request.get_json(silent=True) or {}).get("direction")
        if direction not in ("up", "down"):
            return bad("direction は up / down")
        db.move_schedule_row(row_id, direction)
        return jsonify({"ok": True})

    # ---- 休日出勤予定 ----
    @app.post("/api/holiday-rows")
    def api_add_holiday():
        prepare()
        date_str = (request.get_json(silent=True) or {}).get("date", "")
        if date_str not in {w["date"] for w in week_holidays(masters.load_all())}:
            return bad("今週の休日ではありません")
        return jsonify({"id": db.add_holiday_row(date_str)})

    @app.patch("/api/holiday-rows/<int:row_id>")
    def api_patch_holiday(row_id):
        prepare()
        if db.get_holiday_row(row_id) is None:
            return bad("行が見つかりません", 404)
        fields = clean_fields(request.get_json(silent=True) or {}, HOLIDAY_FIELDS)
        if fields is None:
            return bad("値が文字列ではありません")
        m = masters.load_all()
        if "date" in fields:
            if fields["date"] not in {w["date"] for w in week_holidays(m)}:
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
        body = request.get_json(silent=True) or {}
        name = body.get("name")
        if name not in masters.load_all()["genres"]:
            return bad("登録されていないジャンルです")
        db.set_genre(d, name, bool(body.get("checked")))
        return jsonify({"ok": True})

    # ---- ファイル配信 ----
    @app.get("/api/accident/file/<path:name>")
    def api_accident_file(name):
        return send_from_directory(accident_dir, name)

    def doc_dir(idx):
        return doc_dirs[idx] if 0 <= idx < len(doc_dirs) else None

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
        return send_from_directory(folder, name)

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
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `.venv/Scripts/python.exe -m pytest tests -q`
Expected: `66 passed`（config 5 + masters 14 + board_db 18 + accident 8 + api 21）

---

### Task 6: 画面の骨組みと、表示・入力（災害事例・文書・編集ロック・待機は後の Task）

**Files:**
- Create: `static/board.html`, `static/board.css`, `static/js/api.js`, `static/js/timeutil.mjs`, `static/js/theme.js`, `static/js/picker.js`, `static/js/board.js`
- Create: `tests/test_static.py`, `tests/js/timeutil.test.mjs`, `tests/seed_demo.py`, `.claude/launch.json`

**Interfaces:**
- Consumes: Task 5 の API すべて
- Produces（後の Task が使う）:
  - `static/js/timeutil.mjs`: `formatRange(start, end) -> string`、`contactText(ext, outside) -> string`
  - `static/js/picker.js`: `pickOption({title, options, current, allowClear}) -> Promise<string | "" | undefined>`（選んだ値／クリア＝空文字／閉じる＝undefined。`options` は文字列、または `{value,label}`）、`inputText({title, value, flagLabel, flag}) -> Promise<{text, flag} | undefined>`、`confirmBox(message, okLabel) -> Promise<boolean>`、`alertBox(message) -> Promise<void>`
  - `static/js/board.js`: `isEditable()`（いまは常に true）、`renderParts()`（空。Task 7〜9 で中身を足す）。HTML には文書・設定・待機の覆い（`#documents` `#settings` `#standby`）が最初から入っている
  - `static/js/theme.js`: `initTheme()`、`setDefaultTheme(t)`、`getTheme()`、`setTheme(t)`（`t` は `"light"` か `"dark"`。`<html data-theme>` を切り替える。端末の選択は `localStorage` の `dbb.theme`）

- [ ] **Step 1: 失敗するテストを書く（静的ファイル・JSの純粋関数）**

`tests/test_static.py`:

```python
from app import create_app


def test_index_and_assets_are_served(tmp_path):
    c = create_app(tmp_path).test_client()
    r = c.get("/")
    assert r.status_code == 200
    assert "デジタル掲示板" in r.get_data(as_text=True)
    for path in ["/board.css", "/js/board.js", "/js/api.js", "/js/picker.js", "/js/timeutil.mjs", "/js/theme.js"]:
        assert c.get(path).status_code == 200, path
    assert "javascript" in c.get("/js/timeutil.mjs").content_type
```

`tests/js/timeutil.test.mjs`:

```js
import test from "node:test";
import assert from "node:assert/strict";
import { formatRange, contactText } from "../../static/js/timeutil.mjs";

test("formatRange", () => {
  assert.equal(formatRange("9:00", "15:00"), "9:00～15:00");
  assert.equal(formatRange("9:00", ""), "9:00～");
  assert.equal(formatRange("", "15:00"), "～15:00");
  assert.equal(formatRange("", ""), "");
});

test("contactText", () => {
  assert.equal(contactText("1234", ""), "内線 1234");
  assert.equal(contactText("", "03-0000-0001"), "外線 03-0000-0001");
  assert.equal(contactText("1234", "03-0000-0001"), "内線 1234 / 外線 03-0000-0001");
  assert.equal(contactText("", ""), "");
});
```

- [ ] **Step 2: 失敗を確認する**

Run: `.venv/Scripts/python.exe -m pytest tests/test_static.py -q` と `node --test "tests/js/*.test.mjs"`
Expected: どちらも FAIL（`board.html` が無い／`timeutil.mjs` が無い）。`node` が使えない場合は `node --version` を確認し、Node.js が無ければ JS のテストは「未検証」として Task 9 の実機確認で代える（その旨を報告する）。

- [ ] **Step 3: `static/js/timeutil.mjs` と `static/js/api.js` と `static/js/theme.js` を書く**

`static/js/timeutil.mjs`:

```js
export function formatRange(start, end) {
  if (!start && !end) return "";
  return `${start}～${end}`;
}

export function contactText(ext, outside) {
  const parts = [];
  if (ext) parts.push("内線 " + ext);
  if (outside) parts.push("外線 " + outside);
  return parts.join(" / ");
}
```

`static/js/api.js`:

```js
export async function api(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let message = res.statusText;
    try {
      message = (await res.json()).error || message;
    } catch (_) {}
    throw new Error(message);
  }
  return res.json();
}
```

`static/js/theme.js`（端末ごとの配色。保存できない環境でも、そのページの間は切り替わる）:

```js
const KEY = "dbb.theme";
let defaultTheme = "light";

function read() {
  try {
    const v = localStorage.getItem(KEY);
    return v === "dark" || v === "light" ? v : null;
  } catch (_) {
    return null;
  }
}

let chosen = read();

function apply() {
  document.documentElement.dataset.theme = chosen || defaultTheme;
}

export function getTheme() {
  return chosen || defaultTheme;
}

export function setTheme(t) {
  chosen = t === "dark" ? "dark" : "light";
  try {
    localStorage.setItem(KEY, chosen);
  } catch (_) {}
  apply();
}

// 端末で選んでいなければ、サーバーの既定（config.json の default_theme）に従う
export function setDefaultTheme(t) {
  defaultTheme = t === "dark" ? "dark" : "light";
  apply();
}

export function initTheme() {
  apply();
}
```

- [ ] **Step 4: `static/board.html` を書く**

```html
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>デジタル掲示板</title>
  <link rel="stylesheet" href="/board.css">
</head>
<body class="locked">
  <div id="board">
    <header>
      <div id="date-title"></div>
      <div id="top-right">
        <button id="btn-edit" class="head-btn edit-btn" type="button" hidden>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/></svg>
          <span id="btn-edit-label">編集</span>
        </button>
        <button id="btn-gear" class="head-btn" type="button" aria-label="設定">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>
        </button>
        <span id="company-name"></span>
      </div>
    </header>
    <div id="warnings" hidden></div>
    <main>
      <section id="left">
        <h2>連絡事項</h2>
        <div id="notices"></div>
        <button id="btn-add-notice" class="add-btn edit-only" type="button">＋ 連絡事項を追加</button>
        <h2>本日の作業予定</h2>
        <div class="table-wrap" id="schedule-wrap">
          <table id="schedule">
            <thead><tr>
              <th class="c-company">所属・会社名</th><th class="c-leader">責任者</th>
              <th class="c-work">作業内容</th><th class="c-time">就業予定</th>
              <th class="c-act edit-only"></th>
            </tr></thead>
            <tbody></tbody>
          </table>
        </div>
        <button id="btn-add-schedule" class="add-btn edit-only" type="button">＋ 行を追加</button>
      </section>
      <section id="right">
        <div id="accident-frame">
          <canvas id="accident-canvas" hidden></canvas>
          <div id="accident-msg"></div>
          <div id="accident-tag" hidden></div>
          <div id="accident-count" hidden></div>
          <div id="accident-bar" hidden><div id="accident-bar-fill"></div></div>
        </div>
        <h2>作業ジャンル</h2>
        <div id="genres"></div>
        <h2>今週の休日出勤予定</h2>
        <div class="table-wrap" id="holiday-wrap">
          <table id="holidays">
            <thead><tr>
              <th class="c-date">日付</th><th class="c-person">氏名・会社名</th>
              <th class="c-work">作業内容</th><th class="c-time">就業予定</th>
              <th class="c-act edit-only"></th>
            </tr></thead>
            <tbody></tbody>
          </table>
        </div>
        <button id="btn-add-holiday" class="add-btn edit-only" type="button">＋ 行を追加</button>
        <div id="doc-buttons"></div>
      </section>
    </main>
  </div>

  <div id="picker" class="overlay" hidden></div>

  <div id="documents" class="overlay" hidden>
    <div class="docs-head">
      <div id="docs-title"></div>
      <div class="docs-head-actions">
        <button id="docs-back" class="opt" type="button" hidden>一覧へ</button>
        <button id="docs-close" class="opt" type="button">閉じる</button>
      </div>
    </div>
    <div id="doc-list"></div>
    <div id="doc-viewer" hidden>
      <div class="viewer-bar">
        <button id="doc-prev" class="opt" type="button">◀</button>
        <span id="doc-page"></span>
        <button id="doc-next" class="opt" type="button">▶</button>
        <button id="doc-zoom-out" class="opt" type="button">－</button>
        <button id="doc-zoom-in" class="opt" type="button">＋</button>
      </div>
      <div id="doc-canvas-wrap"><canvas id="doc-canvas"></canvas></div>
    </div>
  </div>

  <div id="settings" class="overlay" hidden>
    <div class="panel">
      <h3>設定（この端末だけ）</h3>
      <p class="setting-title">編集ボタン</p>
      <label class="radio"><input type="radio" name="edit-button" value="on"> あり（普段は閲覧のみ。「編集」を押すと入力できる）</label>
      <label class="radio"><input type="radio" name="edit-button" value="off"> なし（常に入力できる）</label>
      <p class="setting-title">配色</p>
      <label class="radio"><input type="radio" name="theme" value="light"> 明るい</label>
      <label class="radio"><input type="radio" name="theme" value="dark"> 暗い</label>
      <div class="panel-actions"><button id="settings-close" class="opt" type="button">閉じる</button></div>
    </div>
  </div>

  <div id="standby" class="overlay" hidden>
    <div id="standby-clock"></div>
    <div id="standby-date"></div>
  </div>

  <script type="module" src="/js/board.js"></script>
</body>
</html>
```

- [ ] **Step 5: `static/board.css` を書く**

```css
:root, :root[data-theme="light"] {
  --bg: #EEF2F7; --text: #0F172A; --muted: #475569; --card: #FFFFFF; --border: #CBD5E1;
  --row-alt: #F1F5F9; --row-line: #E2E8F0;
  --head-blue: #1D4ED8; --head-blue-text: #FFFFFF; --head-orange: #C2410C; --head-orange-text: #FFFFFF;
  --red: #B91C1C; --red-bg: #FEF2F2; --sat: #1D4ED8; --accent: #1D4ED8; --accent-text: #FFFFFF;
  --chip-on-bg: #DBEAFE; --chip-on-border: #1D4ED8; --chip-on-text: #1E3A8A;
  --chip-off-bg: #FFFFFF; --chip-off-border: #94A3B8; --chip-off-text: #334155;
  --btn-bg: #FFFFFF; --btn-border: #CBD5E1; --btn-text: #475569;
  --paper: #FFFFFF; --paper-muted: #475569; --bar-track: #E2E8F0;
  --check-text: #FFFFFF; --overlay: rgba(15, 23, 42, .55);
}
:root[data-theme="dark"] {
  --bg: #0A1020; --text: #F8FAFC; --muted: #A9B6CC; --card: #111A2E; --border: #2A3A5C;
  --row-alt: #16223A; --row-line: #2A3A5C;
  --head-blue: #2563EB; --head-blue-text: #FFFFFF; --head-orange: #F59E0B; --head-orange-text: #1A1203;
  --red: #FF8F8F; --red-bg: #2A1420; --sat: #7DB2FF; --accent: #2563EB; --accent-text: #FFFFFF;
  --chip-on-bg: #1E3A8A; --chip-on-border: #60A5FA; --chip-on-text: #EAF2FF;
  --chip-off-bg: #111A2E; --chip-off-border: #3B4B6E; --chip-off-text: #C0CBE0;
  --btn-bg: #111A2E; --btn-border: #3B4B6E; --btn-text: #A9B6CC;
  --paper: #F1F5F9; --paper-muted: #475569; --bar-track: #CBD5E1;
  --check-text: #0A1020; --overlay: rgba(0, 0, 0, .7);
}

* { box-sizing: border-box; }
html { font-size: calc(100vw / 120); }
body { margin: 0; font-family: "Meiryo", "メイリオ", "Yu Gothic UI", sans-serif; font-size: 1rem; color: var(--text);
       background: var(--bg); user-select: none; -webkit-user-select: none; overflow: hidden; }
button { font-family: inherit; color: inherit; }

#board { height: 100vh; padding: 2rem 2.5rem; display: flex; flex-direction: column; gap: 1.25rem; }
header { display: flex; justify-content: space-between; align-items: center; height: 5.25rem; flex: none; }
#date-title { font-size: 3.6rem; font-weight: 700; letter-spacing: .02em; }
#date-title .wd { color: var(--sat); }
#top-right { display: flex; align-items: center; gap: 1rem; }
#company-name { margin-left: 1.25rem; font-size: 2.75rem; font-weight: 700; }
.head-btn { display: flex; align-items: center; justify-content: center; gap: .6rem; height: 3.5rem; min-width: 3.5rem;
            padding: 0 1rem; font-size: 1.75rem; font-weight: 700; border: 2px solid var(--btn-border);
            border-radius: .9rem; background: var(--btn-bg); color: var(--btn-text); }
.head-btn svg { width: 1.75rem; height: 1.75rem; }
.head-btn[hidden] { display: none; }
.edit-btn { padding: 0 1.5rem; color: var(--accent); border-color: var(--accent); }
#warnings { flex: none; padding: .3rem 1rem; font-size: 1.1rem; background: #FFF3CD; color: #7A5B00; border-radius: .5rem; }
#warnings[hidden] { display: none; }
main { flex: 1; min-height: 0; display: grid; grid-template-columns: 1128fr 680fr; gap: 3rem; }
section { display: flex; flex-direction: column; min-height: 0; }
h2 { margin: .9rem 0 .5rem; font-size: 1.75rem; font-weight: 700; color: var(--muted); flex: none; }
section > h2:first-child { margin-top: 0; }

#notices { flex: none; max-height: calc(10.5rem + 6px); overflow-y: auto; background: var(--card);
           border: 2px solid var(--border); border-radius: 1rem; }
.notice-line { display: flex; align-items: center; gap: .9rem; min-height: 3.5rem; padding: .2rem 1.5rem;
               font-size: 2rem; border-top: 1px solid var(--row-line); }
.notice-line:first-child { border-top: none; }
.notice-line.red { color: var(--red); background: var(--red-bg); font-weight: 700; }
.notice-line svg { width: 1.9rem; height: 1.9rem; flex: none; }
.notice-text { flex: 1; min-width: 0; overflow-wrap: anywhere; }

.table-wrap { flex: 1; min-height: 8rem; overflow-y: auto; background: var(--card); border: 2px solid var(--border);
              border-radius: 1rem; }
table { width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 2rem; }
th { position: sticky; top: 0; z-index: 1; height: 3.5rem; padding: 0 1.25rem; text-align: left; font-size: 1.625rem;
     font-weight: 700; color: var(--head-blue-text); background: var(--head-blue); }
#holidays th { height: 3rem; font-size: 1.375rem; color: var(--head-orange-text); background: var(--head-orange); }
th.c-time { text-align: center; }
td { height: 5.125rem; padding: 0 1.25rem; text-align: left; vertical-align: middle; border-top: 1px solid var(--row-line);
     overflow-wrap: anywhere; }
#holidays td { height: 4rem; font-size: 1.4375rem; }
td.b { font-weight: 700; }
td.c { text-align: center; }
td.sat { color: var(--sat); }
td.red { color: var(--red); }
tbody tr:nth-child(even) td { background: var(--row-alt); }
.contact { margin-top: .1rem; font-size: 1.25rem; font-weight: 400; color: var(--muted); }
#schedule .c-company { width: 21%; } #schedule .c-leader { width: 19%; } #schedule .c-work { width: 26%; }
#schedule .c-time { width: 21%; } #schedule .c-act { width: 13%; }
#holidays .c-date { width: 29%; } #holidays .c-person { width: 19%; } #holidays .c-work { width: 23%; }
#holidays .c-time { width: 17%; } #holidays .c-act { width: 12%; }

.add-btn { flex: none; margin-top: .5rem; min-height: 3rem; font-size: 1.25rem; color: var(--muted);
           border: 2px dashed var(--btn-border); background: var(--card); border-radius: .75rem; }
.act-btn { min-width: 2.6rem; min-height: 2.6rem; margin: 0 .1rem; font-size: 1.1rem; background: var(--btn-bg);
           color: var(--btn-text); border: 1px solid var(--btn-border); border-radius: .4rem; }
.act-btn:disabled { opacity: .35; }
.locked .edit-only { display: none !important; }

#accident-frame { position: relative; width: 100%; aspect-ratio: 297 / 210; flex: none; overflow: hidden;
                  display: flex; align-items: center; justify-content: center; background: var(--paper);
                  border: 2px solid var(--border); border-radius: 1rem; }
#accident-canvas { max-width: 100%; max-height: 100%; }
#accident-msg { padding: 2rem; font-size: 1.75rem; color: var(--paper-muted); text-align: center; }
#accident-msg[hidden], #accident-tag[hidden], #accident-count[hidden], #accident-bar[hidden],
#accident-canvas[hidden] { display: none; }
#accident-tag { position: absolute; left: 1.25rem; top: 1.25rem; padding: .35rem 1.1rem; font-size: 1.5rem;
                font-weight: 700; color: var(--accent-text); background: var(--accent); border-radius: 1.5rem; }
#accident-count { position: absolute; right: 1.25rem; bottom: 1.1rem; padding: .1rem .6rem; font-size: 1.5rem;
                  font-weight: 700; color: var(--paper-muted); background: rgba(255, 255, 255, .85); border-radius: .5rem; }
#accident-bar { position: absolute; left: 0; right: 0; bottom: 0; height: .5rem; background: var(--bar-track); }
#accident-bar-fill { width: 0; height: 100%; background: var(--accent); }

#genres { display: flex; flex-wrap: wrap; gap: .5rem; flex: none; max-height: 7.25rem; overflow-y: auto; }
.genre { display: flex; align-items: center; gap: .5rem; height: 3.5rem; padding: 0 .75rem; font-size: 1.625rem;
         font-weight: 700; white-space: nowrap; color: var(--chip-off-text); background: var(--chip-off-bg);
         border: 2px solid var(--chip-off-border); border-radius: .75rem; }
.genre::before { content: ""; width: 1.5rem; height: 1.5rem; background: var(--chip-off-bg);
                 border: 2px solid var(--chip-off-border); border-radius: .4rem; }
.genre.on { color: var(--chip-on-text); background: var(--chip-on-bg); border-color: var(--chip-on-border); }
.genre.on::before { content: "✔"; display: flex; align-items: center; justify-content: center; font-size: 1rem;
                    color: var(--check-text); background: var(--chip-on-border); border-color: var(--chip-on-border); }

#doc-buttons { display: flex; gap: 1rem; margin-top: .9rem; flex: none; }
.doc-btn { flex: 1; display: flex; align-items: center; justify-content: center; gap: .75rem; height: 4.25rem;
           font-size: 1.875rem; font-weight: 700; color: var(--accent-text); background: var(--accent); border: none;
           border-radius: 2.125rem; }
.doc-btn svg { width: 1.75rem; height: 1.75rem; }

.overlay { position: fixed; inset: 0; display: flex; align-items: center; justify-content: center; z-index: 10;
           background: var(--overlay); }
.overlay[hidden] { display: none; }
.panel { display: flex; flex-direction: column; min-width: 30rem; max-width: 80vw; max-height: 85vh; padding: 1.5rem 2rem;
         font-size: 1.4rem; color: var(--text); background: var(--card); border: 2px solid var(--border); border-radius: 1rem; }
.panel h3 { margin: 0 0 1rem; font-size: 1.8rem; font-weight: 700; }
.options { display: grid; grid-template-columns: repeat(auto-fill, minmax(14rem, 1fr)); gap: .8rem; overflow-y: auto; }
.opt { min-height: 4rem; padding: 0 1rem; font-size: 1.5rem; color: var(--text); background: var(--btn-bg);
       border: 2px solid var(--btn-border); border-radius: .6rem; }
.opt.current { color: var(--chip-on-text); background: var(--chip-on-bg); border-color: var(--chip-on-border); }
.panel-actions { display: flex; gap: 1rem; justify-content: flex-end; margin-top: 1rem; }
.panel input[type=text] { width: 100%; padding: .6rem; font-size: 1.6rem; color: #0F172A; background: #FFFFFF;
                          user-select: text; -webkit-user-select: text; }
.radio { display: block; margin: .6rem 0; font-size: 1.4rem; }
.setting-title { margin: 1rem 0 .2rem; font-weight: 700; color: var(--muted); }

#documents { flex-direction: column; align-items: stretch; justify-content: flex-start; z-index: 20; background: var(--bg); }
.docs-head { display: flex; justify-content: space-between; align-items: center; flex: none; padding: 1rem 2rem;
             font-size: 1.8rem; background: var(--card); border-bottom: 2px solid var(--border); }
.docs-head-actions { display: flex; gap: 1rem; }
#doc-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(24rem, 1fr)); gap: 1rem; align-content: start;
            padding: 2rem; overflow-y: auto; font-size: 1.6rem; }
#doc-list[hidden], #doc-viewer[hidden] { display: none; }
.doc-item { min-height: 5rem; }
#doc-viewer { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.viewer-bar { display: flex; gap: 1rem; align-items: center; flex: none; padding: .6rem 2rem; font-size: 1.4rem;
              background: var(--card); }
#doc-canvas-wrap { flex: 1; overflow: auto; text-align: center; background: #777777; touch-action: pan-x pan-y; }

#standby { flex-direction: column; z-index: 30; color: #FFFFFF; background: #000000; }
#standby-clock { font-size: 12rem; line-height: 1.1; }
#standby-date { font-size: 3rem; }
```

- [ ] **Step 6: `static/js/picker.js` を書く**

```js
const overlay = document.getElementById("picker");

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function btn(text, cls, onClick) {
  const b = el("button", cls, text);
  b.type = "button";
  b.addEventListener("click", onClick);
  return b;
}

function open(build) {
  return new Promise(resolve => {
    overlay.innerHTML = "";
    const panel = el("div", "panel");
    overlay.appendChild(panel);
    const close = value => {
      overlay.hidden = true;
      overlay.innerHTML = "";
      resolve(value);
    };
    build(panel, close);
    overlay.hidden = false;
  });
}

export function pickOption({ title, options, current = "", allowClear = true }) {
  return open((panel, close) => {
    panel.appendChild(el("h3", "", title));
    const grid = el("div", "options");
    for (const o of options) {
      const value = typeof o === "string" ? o : o.value;
      const label = typeof o === "string" ? o : o.label;
      grid.appendChild(btn(label, "opt" + (value === current ? " current" : ""), () => close(value)));
    }
    panel.appendChild(grid);
    const actions = el("div", "panel-actions");
    if (allowClear) actions.appendChild(btn("クリア", "opt", () => close("")));
    actions.appendChild(btn("閉じる", "opt", () => close(undefined)));
    panel.appendChild(actions);
  });
}

export function inputText({ title, value = "", flagLabel = "", flag = false }) {
  return open((panel, close) => {
    panel.appendChild(el("h3", "", title));
    const input = el("input");
    input.type = "text";
    input.value = value;
    panel.appendChild(input);
    let check = null;
    if (flagLabel) {
      const label = el("label", "radio");
      check = el("input");
      check.type = "checkbox";
      check.checked = flag;
      label.append(check, document.createTextNode(" " + flagLabel));
      panel.appendChild(label);
    }
    const submit = () => close({ text: input.value.trim(), flag: check ? check.checked : false });
    const actions = el("div", "panel-actions");
    actions.appendChild(btn("キャンセル", "opt", () => close(undefined)));
    actions.appendChild(btn("決定", "opt current", submit));
    panel.appendChild(actions);
    input.addEventListener("keydown", e => {
      if (e.key === "Enter") submit();
    });
    setTimeout(() => input.focus(), 0);
  });
}

export function confirmBox(message, okLabel = "はい") {
  return open((panel, close) => {
    panel.appendChild(el("h3", "", message));
    const actions = el("div", "panel-actions");
    actions.appendChild(btn("やめる", "opt", () => close(false)));
    actions.appendChild(btn(okLabel, "opt current", () => close(true)));
    panel.appendChild(actions);
  });
}

export function alertBox(message) {
  return open((panel, close) => {
    panel.appendChild(el("h3", "", message));
    const actions = el("div", "panel-actions");
    actions.appendChild(btn("閉じる", "opt current", () => close()));
    panel.appendChild(actions);
  });
}
```

- [ ] **Step 7: `static/js/board.js` を書く**

```js
import { api } from "./api.js";
import { pickOption, inputText, confirmBox, alertBox } from "./picker.js";
import { formatRange, contactText } from "./timeutil.mjs";
import { initTheme, setDefaultTheme } from "./theme.js";

const MIN_SCHEDULE_ROWS = 7;
const MIN_HOLIDAY_ROWS = 2;
const POLL_MS = 3000;
const ALERT_ICON =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>';

const $ = id => document.getElementById(id);
let state = null;
let lastRev = null;
let lastToday = null;

// 編集できるか（Task 9 で編集ロックに置き換える）
function isEditable() {
  return true;
}

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function td(text, { cls = "", onClick = null } = {}) {
  const e = el("td", cls, text);
  if (onClick) {
    e.addEventListener("click", () => {
      if (isEditable()) onClick();
    });
  }
  return e;
}

function actBtn(label, onClick, disabled = false, extraCls = "") {
  const b = el("button", "act-btn" + (extraCls ? " " + extraCls : ""), label);
  b.type = "button";
  b.disabled = disabled;
  b.addEventListener("click", onClick);
  return b;
}

function fillerRow() {
  const tr = el("tr");
  for (let i = 0; i < 5; i++) tr.appendChild(td("", { cls: i === 4 ? "edit-only" : "" }));
  return tr;
}

function keepScroll(id, fn) {
  const box = $(id);
  const top = box.scrollTop;
  fn();
  box.scrollTop = top;
}

function dateClass(kind) {
  return kind === "saturday" ? "sat" : kind === "holiday" ? "red" : "";
}

function setWarnings(list) {
  const box = $("warnings");
  box.hidden = list.length === 0;
  box.textContent = list.join(" / ");
}

// ---- 描画 ----
function renderHeader() {
  const title = $("date-title");
  title.textContent = "";
  const m = state.date_label.match(/^(.*日)(（.）)$/);
  if (m) title.append(m[1], el("span", "wd", m[2]));
  else title.textContent = state.date_label;
  $("company-name").textContent = state.company_name;
}

function renderNotices() {
  const box = $("notices");
  const top = box.scrollTop;
  box.innerHTML = "";
  const removable = state.notices.length > 3;
  for (const n of state.notices) {
    const line = el("div", "notice-line" + (n.red ? " red" : ""));
    if (n.red) line.insertAdjacentHTML("beforeend", ALERT_ICON);
    line.appendChild(el("span", "notice-text", n.text));
    if (removable) {
      line.appendChild(actBtn("✕", e => {
        e.stopPropagation();
        removeRow(`/api/notices/${n.id}`);
      }, false, "edit-only"));
    }
    line.addEventListener("click", () => {
      if (isEditable()) editNotice(n);
    });
    box.appendChild(line);
  }
  box.scrollTop = top;
}

function renderSchedule() {
  keepScroll("schedule-wrap", () => {
    const body = document.querySelector("#schedule tbody");
    body.innerHTML = "";
    const rows = state.schedule;
    rows.forEach((r, i) => {
      const tr = el("tr");
      tr.appendChild(td(r.company, { cls: "b", onClick: () => editSchedule(r, "company") }));
      const leader = td(r.leader, { cls: "b", onClick: () => editSchedule(r, "leader") });
      const contact = r.leader ? contactText(r.ext, r.outside) : "";
      if (contact) leader.appendChild(el("div", "contact", contact));
      tr.appendChild(leader);
      tr.appendChild(td(r.work, { onClick: () => editSchedule(r, "work") }));
      tr.appendChild(td(formatRange(r.start_time, r.end_time), { cls: "b c", onClick: () => editTimes(`/api/schedule/${r.id}`, r) }));
      const act = td("", { cls: "edit-only" });
      act.append(
        actBtn("▲", () => save("POST", `/api/schedule/${r.id}/move`, { direction: "up" }), i === 0),
        actBtn("▼", () => save("POST", `/api/schedule/${r.id}/move`, { direction: "down" }), i === rows.length - 1),
        actBtn("✕", () => removeRow(`/api/schedule/${r.id}`))
      );
      tr.appendChild(act);
      body.appendChild(tr);
    });
    for (let i = rows.length; i < MIN_SCHEDULE_ROWS; i++) body.appendChild(fillerRow());
  });
}

function renderHolidays() {
  keepScroll("holiday-wrap", () => {
    const body = document.querySelector("#holidays tbody");
    body.innerHTML = "";
    for (const r of state.holiday_rows) {
      const tr = el("tr");
      tr.appendChild(td(r.label, { cls: ("b " + dateClass(r.kind)).trim(), onClick: () => editHolidayDate(r) }));
      tr.appendChild(td(r.person, { cls: "b", onClick: () => editHoliday(r, "person") }));
      tr.appendChild(td(r.work, { onClick: () => editHoliday(r, "work") }));
      tr.appendChild(td(formatRange(r.start_time, r.end_time), { cls: "c", onClick: () => editTimes(`/api/holiday-rows/${r.id}`, r) }));
      const act = td("", { cls: "edit-only" });
      act.appendChild(actBtn("✕", () => removeRow(`/api/holiday-rows/${r.id}`)));
      tr.appendChild(act);
      body.appendChild(tr);
    }
    for (let i = state.holiday_rows.length; i < MIN_HOLIDAY_ROWS; i++) body.appendChild(fillerRow());
  });
}

function renderGenres() {
  const box = $("genres");
  box.innerHTML = "";
  for (const g of state.masters.genres) {
    const on = state.checked_genres.includes(g);
    const b = el("button", "genre" + (on ? " on" : ""), g);
    b.type = "button";
    b.addEventListener("click", () => {
      if (isEditable()) save("POST", "/api/genres/toggle", { name: g, checked: !on });
    });
    box.appendChild(b);
  }
}

// 災害事例・文書ボタン・編集ロック・待機画面の更新（Task 7〜9 で中身を足す）
function renderParts() {}

function render() {
  setDefaultTheme(state.settings.default_theme);
  renderHeader();
  renderNotices();
  renderSchedule();
  renderGenres();
  renderHolidays();
  renderParts();
  setWarnings(state.warnings);
}

// ---- 保存と更新 ----
async function refresh() {
  state = await api("GET", "/api/board");
  lastToday = state.today;
  render();
}

async function save(method, url, body) {
  try {
    await api(method, url, body);
  } catch (e) {
    await alertBox("保存できませんでした: " + e.message);
  }
  try {
    await refresh();
  } catch (_) {}
}

async function removeRow(url) {
  if (await confirmBox("この行を削除しますか？", "削除する")) await save("DELETE", url);
}

async function poll() {
  try {
    const r = await api("GET", "/api/rev");
    if (r.rev !== lastRev || r.today !== lastToday) {
      await refresh();
      lastRev = r.rev;
    } else {
      setWarnings(state ? state.warnings : []);
    }
  } catch (_) {
    setWarnings(["サーバーに接続できません。再接続しています…"]);
  }
  setTimeout(poll, POLL_MS);
}

// ---- 入力 ----
async function editNotice(n) {
  const r = await inputText({ title: `連絡事項 ${n.position}行目`, value: n.text, flagLabel: "赤字で表示する", flag: n.red });
  if (!r) return;
  await save("PATCH", `/api/notices/${n.id}`, { text: r.text, red: r.flag });
}

async function editSchedule(row, field) {
  const m = state.masters;
  let options;
  let title;
  if (field === "company") {
    options = m.companies;
    title = "所属・会社名";
  } else if (field === "leader") {
    if (!row.company) {
      await alertBox("先に所属・会社名を選んでください");
      return;
    }
    options = m.leaders.filter(l => l.company === row.company).map(l => l.leader_name);
    if (!options.length) {
      await alertBox("この会社の責任者は登録されていません");
      return;
    }
    title = "責任者";
  } else {
    options = m.works;
    title = "作業内容";
  }
  const v = await pickOption({ title, options, current: row[field] });
  if (v === undefined) return;
  await save("PATCH", `/api/schedule/${row.id}`, { [field]: v });
}

async function editHoliday(row, field) {
  const options = field === "person" ? state.masters.companies : state.masters.works;
  const v = await pickOption({ title: field === "person" ? "氏名・会社名" : "作業内容", options, current: row[field] });
  if (v === undefined) return;
  await save("PATCH", `/api/holiday-rows/${row.id}`, { [field]: v });
}

async function editHolidayDate(row) {
  const options = state.week_holidays.map(w => ({ value: w.date, label: w.label }));
  const v = await pickOption({ title: "日付", options, current: row.date, allowClear: false });
  if (!v) return;
  await save("PATCH", `/api/holiday-rows/${row.id}`, { date: v });
}

async function editTimes(url, row) {
  const times = state.masters.times;
  const start = await pickOption({ title: "開始時刻", options: times, current: row.start_time });
  if (start === undefined) return;
  if (start === "") {
    await save("PATCH", url, { start_time: "", end_time: "" });
    return;
  }
  const end = await pickOption({ title: "終了時刻", options: times, current: row.end_time });
  if (end === undefined) return;
  await save("PATCH", url, { start_time: start, end_time: end });
}

async function addHoliday() {
  if (!state.week_holidays.length) {
    await alertBox("今週は休日がありません。会社の休日は data/custom_holidays.csv に登録します。");
    return;
  }
  const options = state.week_holidays.map(w => ({ value: w.date, label: w.label }));
  const date = await pickOption({ title: "休日出勤の日付", options, allowClear: false });
  if (!date) return;
  await save("POST", "/api/holiday-rows", { date });
}

initTheme();
$("btn-add-notice").addEventListener("click", async () => {
  await save("POST", "/api/notices");
  const box = $("notices");
  box.scrollTop = box.scrollHeight;
});
$("btn-add-schedule").addEventListener("click", () => save("POST", "/api/schedule"));
$("btn-add-holiday").addEventListener("click", addHoliday);
poll();
```

- [ ] **Step 8: 検証用の補助ファイルを作る**

`tests/seed_demo.py`（起動中のサーバーに、画面案と同じ見本データを入れる。確認用。pytest の対象ではない）:

```python
import json
import sys
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5100"


def call(method, path, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(BASE + path, method=method, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read().decode("utf-8"))


rows = [
    ("1班", "佐藤", "組み立て作業", "9:00", "15:00"),
    ("見本電機", "田中", "配線工事", "8:00", "18:00"),
]
for company, leader, work, start, end in rows:
    rid = call("POST", "/api/schedule")["id"]
    call("PATCH", f"/api/schedule/{rid}", {"company": company, "leader": leader, "work": work, "start_time": start, "end_time": end})

first_notice = call("GET", "/api/board")["notices"][0]["id"]
call("PATCH", f"/api/notices/{first_notice}", {"text": "本日15時から避難訓練があります", "red": True})
for g in ("溶接作業", "高所作業"):
    call("POST", "/api/genres/toggle", {"name": g, "checked": True})
for w in call("GET", "/api/board")["week_holidays"][:2]:
    rid = call("POST", "/api/holiday-rows", {"date": w["date"]})["id"]
    call("PATCH", f"/api/holiday-rows/{rid}", {"person": "1班", "work": "組み立て作業", "start_time": "8:00", "end_time": "17:00"})
print("見本データを入れました")
```

`.claude/launch.json`:

```json
{
  "version": "0.0.1",
  "configurations": [
    {
      "name": "digital-bulletin-board",
      "runtimeExecutable": ".venv\\Scripts\\python.exe",
      "runtimeArgs": ["app.py"],
      "port": 5100
    }
  ]
}
```

- [ ] **Step 9: 自動テストが通ることを確認する**

Run: `.venv/Scripts/python.exe -m pytest tests -q` と `node --test "tests/js/*.test.mjs"`
Expected: `67 passed`、node は `pass 2`。

- [ ] **Step 10: 実際にブラウザで確認する（必須。画面は目で確かめる）**

`preview_start`（名前 `digital-bulletin-board`）でサーバーを起動し、`.venv/Scripts/python.exe tests/seed_demo.py` で見本データを入れる。ブラウザ枠を `resize_window` で 1920×1080 にして確認する。

1. 画面案と並べ、配置（左: 日付・連絡事項・作業予定、右: 枠・ジャンル・休日出勤・ボタン領域）が同じこと。災害事例の枠は「作業ジャンルを選ぶと…」ではなく空（Task 7 まで未接続）でよい。
2. 連絡事項は最初3行。タップ → 文字入力と「赤字」チェック → 決定で、赤字で表示される。「＋ 連絡事項を追加」で4行目以降が増え、**3行分の高さのまま、枠の中だけがスクロールする**。✕は4行以上のときだけ出て、3行未満にはならない。
3. 作業予定: 会社をタップ → 候補が出る。**責任者は、会社を選ぶまで「先に会社を選んでください」と出て、選んだ後はその会社の人だけが並ぶ。会社を変えると責任者が空になる。** 責任者の名前の下に「内線 1234」などが小さく出る。就業予定は開始→終了の順に2回選ぶ。
4. ▲▼で行が入れ替わる。✕は確認が出てから消え、**途中の行を消すと下の行が上に詰まる**。
5. 行を10行まで追加し、**表の中だけが縦にスクロールし、見出しが固定されたまま**であること。ページ全体はスクロールしない。
6. 休日出勤: 「＋ 行を追加」で今週の休日だけが選べる（例 `11/3(火・文化の日)`）。土曜は青、日曜・祝日は赤。日付順に並ぶ。
7. もう1つブラウザのタブで同じ画面を開き、片方で入力すると、もう片方が約3〜5秒で変わる。
8. **配色**: `javascript_tool` で `document.documentElement.dataset.theme = "dark"` と `"light"` を切り替え、どちらでも文字が読め、暗いときに白い箱や読めない文字が残っていないこと。作業ジャンルを `data/genres.csv` で10個に増やすと、チェックの枠が折り返し、2行を超えたら枠の中でスクロールすること（確認後は元に戻す）。
9. `read_console_messages` にエラーが出ていない。

見本データ（`data/board.db`）は、確認用として残る。最終報告で「削除してよいか」を尋ねる（Task 10）。

---

### Task 7: 災害事例の自動再生

**Files:**
- Create: `static/js/accident.js`, `tests/make_sample_pdfs.py`
- Copy: `static/pdfjs/`（equipment-inspection の `static/pdfjs/` をそのままコピー）
- Modify: `static/js/board.js`（取り込みと `renderParts()`）

**Interfaces:**
- Consumes: `/api/board` の `accident[{name,url}]`、`checked_genres`、`settings.accident_seconds`
- Produces: `setPlaylist(files, emptyMessage)`、`setSeconds(n)`、`pause()`、`resume()`

- [ ] **Step 1: PDF.js をコピーする（新規インストールではない）**

```bash
cp -r <equipment-inspection のフォルダ>/static/pdfjs static/pdfjs
ls static/pdfjs
```

Expected: `LICENSE` `cmaps` `pdf.min.js` `pdf.mjs` `pdf.worker.min.js` `pdf.worker.mjs` が並ぶ。

- [ ] **Step 2: 見本のPDFを作る道具を書く**

`tests/make_sample_pdfs.py`（外部部品なしで、複数ページのPDFを書き出す。文字は英数字のみ）:

```python
import sys
from pathlib import Path


def make_pdf(texts, width=842, height=595):
    objs = [None, None, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for text in texts:
        content = f"BT /F1 56 Tf 60 {height // 2} Td ({text}) Tj ET".encode("latin-1")
        page_id = len(objs) + 1
        content_id = len(objs) + 2
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] /Contents {content_id} 0 R "
            f"/Resources << /Font << /F1 3 0 R >> >> >>".encode()
        )
        objs.append(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
        kids.append(f"{page_id} 0 R")
    objs[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>".encode()
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


if __name__ == "__main__":
    accident = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("accident_cases")
    docs = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("documents/doc1")
    accident.mkdir(parents=True, exist_ok=True)
    docs.mkdir(parents=True, exist_ok=True)
    samples = {
        "溶接作業_サンプル1.pdf": ["WELDING SAMPLE 1"],
        "溶接作業_サンプル2.pdf": ["WELDING SAMPLE 2 P1", "WELDING SAMPLE 2 P2"],
        "高所作業_サンプル1.pdf": ["HIGH PLACE SAMPLE 1"],
        "電気配線_サンプル1.pdf": ["WIRING SAMPLE 1"],
        "溶接作業＋高所作業_サンプル複合.pdf": ["WELDING AND HIGH PLACE"],
        "その他_サンプル1.pdf": ["OTHER SAMPLE 1"],
    }
    for name, texts in samples.items():
        (accident / name).write_bytes(make_pdf(texts))
    (docs / "手順書サンプル.pdf").write_bytes(make_pdf(["MANUAL SAMPLE P1", "MANUAL SAMPLE P2"], 595, 842))
    print("見本PDFを作りました:", accident, docs)
```

```bash
.venv/Scripts/python.exe tests/make_sample_pdfs.py
```

Expected: `見本PDFを作りました: accident_cases documents\doc1`（同名のファイルが既にある場合は上書きされるので、先に中身を確認する）。

- [ ] **Step 3: `static/js/accident.js` を書く**

```js
import * as pdfjsLib from "/pdfjs/pdf.mjs";

pdfjsLib.GlobalWorkerOptions.workerSrc = "/pdfjs/pdf.worker.mjs";

const frame = document.getElementById("accident-frame");
const canvas = document.getElementById("accident-canvas");
const msg = document.getElementById("accident-msg");
const tag = document.getElementById("accident-tag");
const count = document.getElementById("accident-count");
const bar = document.getElementById("accident-bar");
const barFill = document.getElementById("accident-bar-fill");

let list = [];
let listKey = null;
let seconds = 15;
let fileIdx = 0;
let pageNum = 1;
let doc = null;
let timer = null;
let paused = false;
let token = 0;
let renderTask = null;

export function setSeconds(s) {
  seconds = s;
}

export function pause() {
  paused = true;
  clearTimeout(timer);
  barFill.style.transition = "none";
  barFill.style.width = "0";
}

export function resume() {
  paused = false;
  if (list.length) show();
}

function dropDoc() {
  if (doc) {
    doc.destroy();
    doc = null;
  }
}

export function setPlaylist(files, emptyMessage) {
  const key = JSON.stringify(files.map(f => f.name)) + "|" + emptyMessage;
  if (key === listKey) return;
  listKey = key;
  list = files;
  fileIdx = 0;
  pageNum = 1;
  dropDoc();
  clearTimeout(timer);
  token++;
  if (!files.length) {
    canvas.hidden = true;
    tag.hidden = true;
    count.hidden = true;
    bar.hidden = true;
    msg.hidden = false;
    msg.textContent = emptyMessage;
    return;
  }
  canvas.hidden = false;
  tag.hidden = false;
  count.hidden = false;
  bar.hidden = false;
  msg.hidden = true;
  if (!paused) show();
}

async function show() {
  clearTimeout(timer);
  const my = ++token;
  try {
    if (!doc) {
      const loaded = await pdfjsLib.getDocument({
        url: list[fileIdx].url,
        cMapUrl: "/pdfjs/cmaps/",
        cMapPacked: true,
      }).promise;
      if (my !== token) {
        loaded.destroy();
        return;
      }
      doc = loaded;
    }
    pageNum = Math.min(Math.max(pageNum, 1), doc.numPages);
    const page = await doc.getPage(pageNum);
    if (my !== token) return;
    const base = page.getViewport({ scale: 1 });
    const scale = Math.min(frame.clientWidth / base.width, frame.clientHeight / base.height);
    const vp = page.getViewport({ scale });
    const dpr = window.devicePixelRatio || 1;
    canvas.width = vp.width * dpr;
    canvas.height = vp.height * dpr;
    canvas.style.width = vp.width + "px";
    canvas.style.height = vp.height + "px";
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (renderTask) renderTask.cancel();
    renderTask = page.render({ canvasContext: ctx, viewport: vp });
    await renderTask.promise;
    if (my === token) updateOverlay();
  } catch (e) {
    if (my !== token || (e && e.name === "RenderingCancelledException")) return;
    console.error("災害事例の表示に失敗しました", e);
    dropDoc();
    timer = setTimeout(() => step(1), 3000);
    return;
  }
  if (my === token && !paused) {
    restartBar();
    timer = setTimeout(() => step(1), seconds * 1000);
  }
}

// 枠の左上にジャンル名、右下に「何件目／全部で何件」、下に次へ進むまでの進み具合を出す
function updateOverlay() {
  const f = list[fileIdx];
  tag.textContent = f.name.split("_")[0];
  count.textContent = `${fileIdx + 1} / ${list.length}`;
}

function restartBar() {
  barFill.style.transition = "none";
  barFill.style.width = "0";
  void barFill.offsetWidth;
  barFill.style.transition = `width ${seconds}s linear`;
  barFill.style.width = "100%";
}

function step(dir) {
  if (!list.length) return;
  if (dir > 0) {
    if (doc && pageNum < doc.numPages) {
      pageNum++;
    } else {
      const next = (fileIdx + 1) % list.length;
      if (next !== fileIdx) dropDoc();
      fileIdx = next;
      pageNum = 1;
    }
  } else if (pageNum > 1) {
    pageNum--;
  } else {
    const prev = (fileIdx - 1 + list.length) % list.length;
    if (prev !== fileIdx) dropDoc();
    fileIdx = prev;
    pageNum = Number.MAX_SAFE_INTEGER;
  }
  show();
}

let down = null;
frame.addEventListener("pointerdown", e => {
  down = { x: e.clientX };
});
frame.addEventListener("pointerup", e => {
  if (!down) return;
  const dx = e.clientX - down.x;
  down = null;
  if (Math.abs(dx) > 60) {
    step(dx < 0 ? 1 : -1);
  } else {
    const r = frame.getBoundingClientRect();
    step(e.clientX > r.left + r.width / 2 ? 1 : -1);
  }
});

let resizeTimer = null;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    if (list.length && !paused) show();
  }, 300);
});
```

- [ ] **Step 4: `board.js` につなぐ**

`static/js/board.js` の取り込み行の直後に追加する。

old:
```js
import { formatRange, contactText } from "./timeutil.mjs";
```
new:
```js
import { formatRange, contactText } from "./timeutil.mjs";
import { setPlaylist, setSeconds, pause as pauseAccident, resume as resumeAccident } from "./accident.js";
```

`renderParts()` を置き換える。

old:
```js
function renderParts() {}
```
new:
```js
function renderParts() {
  setSeconds(state.settings.accident_seconds);
  setPlaylist(
    state.accident,
    state.checked_genres.length ? "該当する災害事例がありません" : "作業ジャンルを選ぶと災害事例が表示されます"
  );
}
```

（`pauseAccident` `resumeAccident` は Task 9 で使う。いまは未使用でよい。）

- [ ] **Step 5: 実際にブラウザで確認する**

サーバーを再読み込みして（`static` は毎回読み直される）確認する。

1. ジャンルが何もチェックされていないとき、枠に「作業ジャンルを選ぶと災害事例が表示されます」。
2. 「溶接作業」をチェックすると、`溶接作業_サンプル1.pdf` が枠に収まって表示され、約15秒ごとに次へ進む（サンプル2は2ページ→両方出る）。複合ファイルは1回だけ出る。「その他」だけチェックすると `その他_サンプル1.pdf`。
3. 枠の右半分をタップすると次、左半分で前、左右にスワイプしても切り替わる。
4. チェックを全部外すと、メッセージに戻る。該当ファイルが無いジャンル（フォルダを空にして試す必要はなく、`電気配線` を外してから確認）で「該当する災害事例がありません」が出ること。
5. 枠の縦横比が A4横（297:210）で、縦向きPDF（`documents/doc1/手順書サンプル.pdf` は縦。災害事例に入れて試してもよい）は左右に余白が出ること。
6. 枠の左上にジャンル名（複合ファイルは `溶接作業＋高所作業`）、右下に `1 / 5` のような件数、下に次へ進むまでの進み具合の線が出ること。待機画面（Task 9）で再生が止まると、線は0に戻ること。
7. `read_console_messages` にエラーが無いこと。

---

### Task 8: 文書ボタンと閲覧

**Files:**
- Create: `static/js/documents.js`
- Modify: `static/js/board.js`

**Interfaces:**
- Consumes: `/api/board` の `doc_buttons[{index,label}]`、`settings.documents_idle_seconds`、`/api/documents/<idx>/files`、`/api/documents/<idx>/pdf/<name>`
- Produces: `renderDocButtons(buttons, idleSeconds)`、`closeDocuments()`

- [ ] **Step 1: `static/js/documents.js` を書く**

```js
import * as pdfjsLib from "/pdfjs/pdf.mjs";
import { api } from "./api.js";

pdfjsLib.GlobalWorkerOptions.workerSrc = "/pdfjs/pdf.worker.mjs";

const $ = id => document.getElementById(id);
const DOC_ICON =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M16 13H8"/><path d="M16 17H8"/></svg>';
let idleSeconds = 120;
let idleTimer = null;
let doc = null;
let pageNum = 1;
let zoom = 1;
let rendering = false;
let pending = false;
let currentIndex = 0;
let currentLabel = "";

function resetIdle() {
  clearTimeout(idleTimer);
  idleTimer = setTimeout(closeDocuments, idleSeconds * 1000);
}

function dropDoc() {
  if (doc) {
    doc.destroy();
    doc = null;
  }
}

export function closeDocuments() {
  clearTimeout(idleTimer);
  $("documents").hidden = true;
  dropDoc();
}

export function renderDocButtons(buttons, idle) {
  idleSeconds = idle;
  const box = $("doc-buttons");
  const key = JSON.stringify(buttons);
  if (box.dataset.key === key) return;
  box.dataset.key = key;
  box.innerHTML = "";
  for (const b of buttons) {
    const e = document.createElement("button");
    e.type = "button";
    e.className = "doc-btn";
    e.insertAdjacentHTML("beforeend", DOC_ICON);
    e.appendChild(document.createTextNode(b.label));
    e.addEventListener("click", () => openFolder(b.index, b.label));
    box.appendChild(e);
  }
}

async function openFolder(index, label) {
  currentIndex = index;
  currentLabel = label;
  dropDoc();
  $("documents").hidden = false;
  $("docs-title").textContent = label;
  $("docs-back").hidden = true;
  $("doc-viewer").hidden = true;
  const list = $("doc-list");
  list.hidden = false;
  list.innerHTML = "";
  resetIdle();
  let files = [];
  try {
    files = await api("GET", `/api/documents/${index}/files`);
  } catch (_) {}
  if (!files.length) {
    list.textContent = "文書がありません";
    return;
  }
  for (const name of files) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "opt doc-item";
    b.textContent = name.replace(/\.pdf$/i, "");
    b.addEventListener("click", () => openFile(name));
    list.appendChild(b);
  }
}

async function openFile(name) {
  $("doc-list").hidden = true;
  $("doc-viewer").hidden = false;
  $("docs-back").hidden = false;
  $("docs-title").textContent = name.replace(/\.pdf$/i, "");
  zoom = 1;
  pageNum = 1;
  dropDoc();
  resetIdle();
  try {
    doc = await pdfjsLib.getDocument({
      url: `/api/documents/${currentIndex}/pdf/${encodeURIComponent(name)}`,
      cMapUrl: "/pdfjs/cmaps/",
      cMapPacked: true,
    }).promise;
    await renderPage();
  } catch (e) {
    console.error("文書の表示に失敗しました", e);
    $("doc-page").textContent = "表示できません";
  }
}

async function renderPage() {
  if (!doc) return;
  if (rendering) {
    pending = true;
    return;
  }
  rendering = true;
  try {
    const p = await doc.getPage(pageNum);
    const wrap = $("doc-canvas-wrap");
    const base = p.getViewport({ scale: 1 });
    const fit = Math.min(wrap.clientWidth / base.width, wrap.clientHeight / base.height) * 0.97;
    const vp = p.getViewport({ scale: fit * zoom });
    const dpr = window.devicePixelRatio || 1;
    const c = $("doc-canvas");
    c.width = vp.width * dpr;
    c.height = vp.height * dpr;
    c.style.width = vp.width + "px";
    c.style.height = vp.height + "px";
    const ctx = c.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    await p.render({ canvasContext: ctx, viewport: vp }).promise;
    $("doc-page").textContent = `${pageNum} / ${doc.numPages}`;
  } finally {
    rendering = false;
    if (pending) {
      pending = false;
      renderPage();
    }
  }
}

function clampZoom(z) {
  return Math.min(5, Math.max(0.5, z));
}

$("docs-close").addEventListener("click", closeDocuments);
$("docs-back").addEventListener("click", () => openFolder(currentIndex, currentLabel));
$("doc-prev").addEventListener("click", () => {
  if (doc && pageNum > 1) {
    pageNum--;
    renderPage();
  }
});
$("doc-next").addEventListener("click", () => {
  if (doc && pageNum < doc.numPages) {
    pageNum++;
    renderPage();
  }
});
$("doc-zoom-in").addEventListener("click", () => {
  zoom = clampZoom(zoom * 1.25);
  renderPage();
});
$("doc-zoom-out").addEventListener("click", () => {
  zoom = clampZoom(zoom / 1.25);
  renderPage();
});

// ピンチ（2本指）とホイールでの拡大縮小
const wrap = $("doc-canvas-wrap");
let pinch = null;
const dist = t => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
wrap.addEventListener("touchstart", e => {
  if (e.touches.length === 2) pinch = { d: dist(e.touches), z: zoom };
}, { passive: true });
wrap.addEventListener("touchmove", e => {
  if (pinch && e.touches.length === 2) {
    zoom = clampZoom(pinch.z * (dist(e.touches) / pinch.d));
    renderPage();
  }
}, { passive: true });
wrap.addEventListener("touchend", e => {
  if (e.touches.length < 2) pinch = null;
}, { passive: true });
wrap.addEventListener("wheel", e => {
  if (e.ctrlKey) {
    e.preventDefault();
    zoom = clampZoom(zoom * (e.deltaY < 0 ? 1.1 : 1 / 1.1));
    renderPage();
  }
}, { passive: false });

// 何か操作するたびに「一定時間操作なしで戻る」を数え直す
for (const ev of ["pointerdown", "wheel", "scroll"]) {
  $("documents").addEventListener(ev, resetIdle, { capture: true, passive: true });
}
```

- [ ] **Step 2: `board.js` につなぐ**

old:
```js
import { setPlaylist, setSeconds, pause as pauseAccident, resume as resumeAccident } from "./accident.js";
```
new:
```js
import { setPlaylist, setSeconds, pause as pauseAccident, resume as resumeAccident } from "./accident.js";
import { renderDocButtons } from "./documents.js";
```

old:
```js
    state.checked_genres.length ? "該当する災害事例がありません" : "作業ジャンルを選ぶと災害事例が表示されます"
  );
}
```
new:
```js
    state.checked_genres.length ? "該当する災害事例がありません" : "作業ジャンルを選ぶと災害事例が表示されます"
  );
  renderDocButtons(state.doc_buttons, state.settings.documents_idle_seconds);
}
```

- [ ] **Step 3: 実際にブラウザで確認する**

1. 右下に「文書1・文書2・文書3」が出る。文書1を押すと `手順書サンプル` の一覧、文書2・3は「文書がありません」。
2. 一覧から開くと、縦向きPDFが枠に収まって出る。◀▶でページが変わる。＋－で拡大縮小でき、拡大時は文書の中だけがスクロールする。「一覧へ」「閉じる」で戻れる。
3. 開いたまま操作せずにいると、設定の `idle_return_seconds`（既定120秒）で掲示板に戻る。（待つのは長いので、`config.json` を一時的に作って `{"documents": {"idle_return_seconds": 10}}` にして確認し、確認後は `config.json` を最終報告の削除確認に入れる。）
4. ピンチ操作（2本指）は、実機のタッチパネルでないと確認できない。確認できなければ「未検証」と報告する。
5. `read_console_messages` にエラーが無いこと。

---

### Task 9: 編集ロック・設定メニュー・待機画面

**Files:**
- Create: `static/js/lock.js`, `static/js/standby.js`, `tests/js/standby.test.mjs`
- Modify: `static/js/timeutil.mjs`（時刻の関数を追加）、`static/js/board.js`

**Interfaces:**
- Consumes: `/api/board` の `settings.edit_lock_seconds`、`settings.standby{start,end,wake_idle_seconds}`、HTML の `#btn-edit` `#btn-gear` `#settings` `#standby`、`accident.js` の `pause`/`resume`
- Produces: `lock.js` の `isEditable()`、`initLock()`、`setLockSeconds(n)`。`standby.js` の `initStandby(onShow, onHide)`、`setStandbyConfig(cfg)`。`timeutil.mjs` の `toMinutes(hhmm)`、`isStandbyTime(nowMinutes, start, end)`

- [ ] **Step 1: 失敗するテストを書く**

`tests/js/standby.test.mjs`:

```js
import test from "node:test";
import assert from "node:assert/strict";
import { isStandbyTime, toMinutes } from "../../static/js/timeutil.mjs";

const at = (h, m) => h * 60 + m;

test("toMinutes", () => {
  assert.equal(toMinutes("07:30"), 450);
  assert.equal(toMinutes("18:00"), 1080);
});

test("standby across midnight (18:00 - 07:30)", () => {
  assert.equal(isStandbyTime(at(18, 0), "18:00", "07:30"), true);
  assert.equal(isStandbyTime(at(23, 59), "18:00", "07:30"), true);
  assert.equal(isStandbyTime(at(0, 0), "18:00", "07:30"), true);
  assert.equal(isStandbyTime(at(7, 29), "18:00", "07:30"), true);
  assert.equal(isStandbyTime(at(7, 30), "18:00", "07:30"), false);
  assert.equal(isStandbyTime(at(12, 0), "18:00", "07:30"), false);
  assert.equal(isStandbyTime(at(17, 59), "18:00", "07:30"), false);
});

test("standby within one day", () => {
  assert.equal(isStandbyTime(at(13, 0), "12:00", "14:00"), true);
  assert.equal(isStandbyTime(at(14, 0), "12:00", "14:00"), false);
  assert.equal(isStandbyTime(at(11, 59), "12:00", "14:00"), false);
});

test("start equal to end means never standby", () => {
  assert.equal(isStandbyTime(at(12, 0), "12:00", "12:00"), false);
});
```

Run: `node --test "tests/js/*.test.mjs"`
Expected: FAIL（`isStandbyTime` が無い）

- [ ] **Step 2: `timeutil.mjs` に追加する**

old:
```js
  return parts.join(" / ");
}
```
new:
```js
  return parts.join(" / ");
}

export function toMinutes(hhmm) {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
}

// start〜end が日付をまたぐとき（18:00〜07:30）も正しく判定する
export function isStandbyTime(nowMinutes, start, end) {
  const s = toMinutes(start);
  const e = toMinutes(end);
  if (s === e) return false;
  return s < e ? nowMinutes >= s && nowMinutes < e : nowMinutes >= s || nowMinutes < e;
}
```

Run: `node --test "tests/js/*.test.mjs"`
Expected: すべて pass

- [ ] **Step 3: `static/js/lock.js` を書く**

```js
import { setTheme, getTheme } from "./theme.js";

const KEY = "dbb.editButton";
const $ = id => document.getElementById(id);

let mode = "off";
let editing = false;
let timer = null;
let lockSeconds = 60;

function readMode() {
  try {
    return localStorage.getItem(KEY) === "on" ? "on" : "off";
  } catch (_) {
    return "off";
  }
}

function writeMode(m) {
  try {
    localStorage.setItem(KEY, m);
  } catch (_) {}
}

export function isEditable() {
  return mode === "off" || editing;
}

export function setLockSeconds(s) {
  lockSeconds = s;
}

function apply() {
  clearTimeout(timer);
  document.body.classList.toggle("locked", !isEditable());
  const b = $("btn-edit");
  b.hidden = mode !== "on";
  $("btn-edit-label").textContent = editing ? "完了" : "編集";
  if (editing) {
    timer = setTimeout(() => {
      editing = false;
      apply();
    }, lockSeconds * 1000);
  }
}

function openSettings() {
  for (const r of document.querySelectorAll('input[name="edit-button"]')) r.checked = r.value === mode;
  for (const r of document.querySelectorAll('input[name="theme"]')) r.checked = r.value === getTheme();
  $("settings").hidden = false;
}

export function initLock() {
  mode = readMode();
  $("btn-edit").addEventListener("click", () => {
    editing = !editing;
    apply();
  });
  // 編集中に画面を触るたびに、自動で閲覧に戻るまでの時間を数え直す
  document.addEventListener("pointerdown", () => {
    if (editing) apply();
  }, true);
  $("btn-gear").addEventListener("click", openSettings);
  $("settings-close").addEventListener("click", () => {
    $("settings").hidden = true;
  });
  for (const r of document.querySelectorAll('input[name="edit-button"]')) {
    r.addEventListener("change", () => {
      mode = r.value;
      writeMode(mode);
      editing = false;
      apply();
    });
  }
  for (const r of document.querySelectorAll('input[name="theme"]')) {
    r.addEventListener("change", () => setTheme(r.value));
  }
  apply();
}
```

- [ ] **Step 4: `static/js/standby.js` を書く**

```js
import { isStandbyTime } from "./timeutil.mjs";

let cfg = { start: "18:00", end: "07:30", wake_idle_seconds: 300 };
let lastActivity = -Infinity;
let shown = false;
let onShow = () => {};
let onHide = () => {};
const $ = id => document.getElementById(id);

export function setStandbyConfig(c) {
  cfg = c;
}

function updateClock() {
  const n = new Date();
  $("standby-clock").textContent = n.getHours() + ":" + String(n.getMinutes()).padStart(2, "0");
  $("standby-date").textContent = `${n.getMonth() + 1}月${n.getDate()}日`;
}

function showStandby() {
  shown = true;
  $("standby").hidden = false;
  updateClock();
  onShow();
}

function hideStandby() {
  shown = false;
  $("standby").hidden = true;
  lastActivity = Date.now();
  onHide();
}

function tick() {
  const n = new Date();
  const inTime = isStandbyTime(n.getHours() * 60 + n.getMinutes(), cfg.start, cfg.end);
  if (shown) {
    if (!inTime) hideStandby();
    else updateClock();
    return;
  }
  if (inTime && Date.now() - lastActivity > cfg.wake_idle_seconds * 1000) showStandby();
}

export function initStandby(show, hide) {
  onShow = show;
  onHide = hide;
  document.addEventListener("pointerdown", () => {
    lastActivity = Date.now();
  }, true);
  $("standby").addEventListener("pointerdown", () => {
    if (shown) hideStandby();
  });
  setInterval(tick, 5000);
  tick();
}
```

- [ ] **Step 5: `board.js` につなぐ**

取り込み行を足す。

old:
```js
import { renderDocButtons } from "./documents.js";
```
new:
```js
import { renderDocButtons } from "./documents.js";
import { isEditable, initLock, setLockSeconds } from "./lock.js";
import { initStandby, setStandbyConfig } from "./standby.js";
```

仮の `isEditable` を消す（`lock.js` のものを使う）。

old:
```js
// 編集できるか（Task 9 で編集ロックに置き換える）
function isEditable() {
  return true;
}

```
new: （空にする）

`renderParts()` に足す。

old:
```js
  renderDocButtons(state.doc_buttons, state.settings.documents_idle_seconds);
}
```
new:
```js
  renderDocButtons(state.doc_buttons, state.settings.documents_idle_seconds);
  setLockSeconds(state.settings.edit_lock_seconds);
  setStandbyConfig(state.settings.standby);
}
```

起動処理に足す。

old:
```js
$("btn-add-holiday").addEventListener("click", addHoliday);
poll();
```
new:
```js
$("btn-add-holiday").addEventListener("click", addHoliday);
initLock();
initStandby(pauseAccident, resumeAccident);
poll();
```

- [ ] **Step 6: 実際にブラウザで確認する**

1. 初期状態（設定「なし」）: 編集ボタンは出ず、常に入力できる。
2. 歯車 → 設定メニュー → 「あり」を選んで閉じる。**普段は「連絡事項・表・ジャンルをタップしても何も起きない」ことと、`＋ 行を追加`・▲▼✕が消えていること。**「編集」を押すと入力でき、ボタンが「完了」に変わる。「完了」で閲覧に戻る。
3. `config.json` を一時的に作り（`{"edit_lock_seconds": 8}`）、サーバーを再起動して、編集中に8秒触らないと自動で閲覧に戻ること。触り続けると戻らないこと。
4. 別のタブ（同じブラウザ）で設定を変えても、**もう1つ別のブラウザ（プライベートウィンドウなど）には影響しない**こと（端末ごとの設定）。ブラウザを再読み込みしても設定が残ること。
5. 待機画面: `config.json` を `{"standby": {"start": "<いまの2分前>", "end": "<いまの30分後>", "wake_idle_seconds": 10}}`（時刻は HH:MM）にしてサーバーを再起動する。**5秒以内（最大10秒）に時計だけの画面になる**こと。触ると掲示板に戻り、10秒操作しないと再び待機になること。災害事例の再生が待機中は止まり、戻ると再開すること。
6. 連絡事項の「赤字」スイッチ: 連絡事項を赤字にすると赤い太字、外すと黒に戻る。
7. 配色: 歯車 → 設定メニューの「配色」を「暗い」にすると全体が暗い配色になり、「明るい」で戻ること。ブラウザを再読み込みしても、その端末の選択が残ること。別のブラウザ（プライベートウィンドウなど）には影響しないこと。災害事例の枠は、どちらの配色でも白い紙の色のままであること。
8. `read_console_messages` にエラーが無いこと。

試験用の `config.json` は、最終報告で削除の承認を求める（Task 10）。

---

### Task 10: 起動用のファイルと説明書、最終確認

**Files:**
- Create: `起動.bat`, `初回セットアップ.bat`, `README.md`, `THIRD_PARTY_NOTICES.md`

- [ ] **Step 1: `.bat` を作る（Shift-JIS で保存する）**

日本語Windowsの `.bat` は Shift-JIS（cp932）で保存する。次のスクリプトで書き出す。

```bash
.venv/Scripts/python.exe - <<'EOF'
start_bat = r'''@echo off
cd /d "%~dp0"

if "%~1"=="openbrowser" goto :openbrowser

if not exist ".venv\Scripts\python.exe" (
    echo [エラー] .venv が見つかりません。
    echo 先に「初回セットアップ.bat」をダブルクリックしてください。
    pause
    exit /b 1
)
echo デジタル掲示板を起動します。この黒い窓は閉じないでください。
echo 終了するときは、この窓で Ctrl + C を押してください。
echo.
start /min "" "%~f0" openbrowser
".venv\Scripts\python.exe" app.py
pause
exit /b 0

:openbrowser
timeout /t 3 /nobreak >nul
set "EDGE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" set "EDGE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" goto :fallback
start "" "%EDGE%" --kiosk http://localhost:5100 --edge-kiosk-type=fullscreen --user-data-dir="%~dp0.browser" --no-first-run --no-default-browser-check
exit /b 0

:fallback
start "" http://localhost:5100
exit /b 0
'''
setup_bat = r'''@echo off
cd /d "%~dp0"
echo ============================================
echo  デジタル掲示板 初回セットアップ
echo ============================================
echo.

set "PYCMD="
where py >nul 2>nul && set "PYCMD=py -3"
if not defined PYCMD (
    where python >nul 2>nul && set "PYCMD=python"
)
if not defined PYCMD (
    echo [エラー] Python が見つかりません。
    echo https://www.python.org/ から Python 3.10 以降をインストールしてください。
    echo インストール時は「Add Python to PATH」に必ずチェックを入れてください。
    pause
    exit /b 1
)

echo Python を確認しました。実行環境を作成します...
%PYCMD% -m venv .venv
if errorlevel 1 (
    echo [エラー] 実行環境の作成に失敗しました。
    pause
    exit /b 1
)

echo 必要な部品をインストールします。インターネット接続が必要です...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [エラー] 部品のインストールに失敗しました。
    echo インターネット接続を確認して、もう一度実行してください。
    pause
    exit /b 1
)

echo.
echo ============================================
echo  セットアップが完了しました。
echo  次回からは「起動.bat」をダブルクリックしてください。
echo ============================================
pause
'''
for name, text in (("起動.bat", start_bat), ("初回セットアップ.bat", setup_bat)):
    with open(name, "w", encoding="cp932", newline="\r\n") as f:
        f.write(text)
print("ok")
EOF
```

Expected: `ok`。（既に同名のファイルがある場合は、先に上書きの確認を取る。）

- [ ] **Step 2: `.bat` を実際に実行して確認する（必須）**

- `起動.bat`: ダブルクリック相当（`cmd /c 起動.bat`）で実行し、黒い窓に「デジタル掲示板を起動します」と出ること、数秒後に Edge が**全画面（キオスク）**で掲示板を開くこと、`curl http://localhost:5100/api/rev` が JSON を返すことを確認する。Edge は `Alt + F4` で閉じ、黒い窓は `Ctrl + C` で止める。**Edge の全画面がユーザーの画面を占有するので、実行前に一言伝える。**
- `初回セットアップ.bat`: いまのフォルダでは `.venv` が既にあるので実行しない。**ユーザーの承認を得て**、アプリのフォルダを scratchpad にコピー（`.venv` `.git` `data/board.db*` `.browser` を除く）してから、そのコピーで実行し、`.venv` ができて `起動.bat` が動くところまで確認する。承認が得られなければ「未検証」と報告する。

- [ ] **Step 3: `README.md` と `THIRD_PARTY_NOTICES.md` を書く**

`README.md`:

```markdown
# デジタル掲示板

工場などの「本日の作業内容」ホワイトボードの代わりに、大型のタッチモニタ（と社内LANの他のPC）で、本日の作業予定・連絡事項・今週の休日出勤予定・災害事例の自動再生・文書閲覧を行うWebアプリです。

## 使い方

1. `初回セットアップ.bat` をダブルクリック（最初の1回だけ。インターネット接続が必要）
2. `起動.bat` をダブルクリック。Edge が全画面で開きます
3. 他のPCからは、起動時の黒い窓に出る「他のPCで開く」のアドレスをブラウザに入力します（ポートは 5100 固定）

## 画面の操作

- 欄をタップすると、登録済みの候補から選べます。連絡事項だけは自由に入力でき、常に3行分の高さで表示し、増えたら枠の中でスクロールします（編集中の「＋ 連絡事項を追加」で増やせます。4行以上のときだけ✕で消せます）
- 歯車ボタンで、その端末の「編集ボタン あり／なし」を切り替えます。「あり」にすると、普段は閲覧のみで、「編集」を押したときだけ入力できます（誤操作防止。暗証番号はありません）。「配色」（明るい／暗い）も、同じ歯車から端末ごとに選べます
- 本日の作業予定は、前日の内容を引き継いで始まります。▲▼で並べ替え、✕で削除すると下の行が上に詰まります
- 今週の休日出勤予定は、月曜〜日曜の週ごとに、月曜になると空欄になります。日付は今週の休日（土日・祝日・会社の休日）から選びます
- 作業ジャンルをチェックすると、そのジャンルの災害事例PDFが順に自動再生されます
- 右下のボタンで、フォルダに入れた文書（PDF）を閲覧できます
- 夜間（既定 18:00〜翌7:30）は時計だけの待機画面になります。触ると戻ります

## 選択肢の登録（Excelで編集）

`data` フォルダのCSVを、Excel や メモ帳で編集します。保存すると、画面は数秒で反映されます。文字コードは **UTF-8（BOM付き）** で保存してください（Excelの「CSV UTF-8」）。

| ファイル | 列 | 内容 |
|---|---|---|
| `companies.csv` | `name` | 所属・会社名／氏名（休日出勤の氏名・会社名にも使います） |
| `leaders.csv` | `company,leader_name,ext,outside` | 責任者。会社名ごとに登録し、内線（`ext`）・外線（`outside`）はどちらか一方でも構いません |
| `works.csv` | `name` | 作業内容 |
| `genres.csv` | `name` | 作業ジャンル（並び順もこの順）。追加・名前の変更もここで行います。名前を変えたら、災害事例PDFのファイル名の先頭も同じに直してください |
| `times.csv` | `time` | 就業予定の時刻の候補（無ければ 6:00〜22:00 の30分刻みで自動作成） |
| `custom_holidays.csv` | `date,name` | 会社の休日（例 `2026-12-29,年末休業`）。祝日は自動で判定します |

## 災害事例と文書

- 災害事例のPDFは `accident_cases` フォルダに入れます。**ファイル名の先頭が作業ジャンル名**です。例: `溶接作業_事例A.pdf`。複数のジャンルに当てはまる事例は `＋` でつなぎます（`溶接作業＋高所作業_事例A.pdf`）。`data/genres.csv` に無いジャンル名のファイルは再生されません
- 文書ボタンのPDFは、設定で指定したフォルダ（既定 `documents/doc1`〜`doc3`）に入れます

## 設定（config.json）

無ければ既定で動きます。変えたい項目だけ書いて、サーバーを再起動します。

| 項目 | 既定 | 内容 |
|---|---|---|
| `company_name` | サンプル工業(株) | 画面右上の会社名 |
| `default_theme` | light | 配色の初期値（`light` か `dark`）。端末ごとに選んだ配色が優先されます |
| `accident_folder` | accident_cases | 災害事例PDFのフォルダ |
| `accident_seconds` | 15 | 災害事例1枚の表示秒数 |
| `documents.buttons` | 文書1〜3 | 文書ボタン（最大5つ。`label` と `folder`） |
| `documents.idle_return_seconds` | 120 | 文書閲覧で操作が無いと掲示板へ戻る秒数 |
| `edit_lock_seconds` | 60 | 編集ボタンで編集中、操作が無いと閲覧へ戻る秒数 |
| `standby.start` / `standby.end` | 18:00 / 07:30 | 待機画面の時間 |
| `standby.wake_idle_seconds` | 300 | 待機画面から戻したあと、操作が無いと再び待機する秒数 |

## 注意

- ログイン認証はありません。社内LANの中だけで使ってください
- 他のPCから開くには、サーバーPCのファイアウォールで 5100 番の受け付けが必要な場合があります
```

`THIRD_PARTY_NOTICES.md`:

```markdown
# 同梱しているソフトウェアのライセンス

| 名前 | 場所 | 作者 | ライセンス |
|---|---|---|---|
| PDF.js | `static/pdfjs/`（`cmaps/` を除く） | Mozilla Foundation | Apache License 2.0（`static/pdfjs/LICENSE`） |
| PDF.js 同梱の文字データ（CMap） | `static/pdfjs/cmaps/` | Adobe Systems Incorporated | BSD 3-Clause（`static/pdfjs/cmaps/LICENSE`） |

PDF.js の各ファイルの先頭にある著作権表示は、変更せずに残しています。

## 初回セットアップで入る部品

`初回セットアップ.bat` が、インターネット（PyPI）からダウンロードします。このリポジトリには含まれていません。

| 部品 | ライセンス |
|---|---|
| Flask | BSD-3-Clause |
| waitress | ZPL 2.1 |
| jpholiday | MIT |
| pytest | MIT |

（各部品のライセンスは、配布元の表示が正です。上の表は確認した時点の表示を写したものです。）
```

- [ ] **Step 4: 全体の最終確認**

1. `.venv/Scripts/python.exe -m pytest tests -q` → `67 passed`、`node --test "tests/js/*.test.mjs"` → すべて pass
2. サーバーを起動し、Task 6〜9 の画面確認のうち、**1920×1080 と 3840×2160（`resize_window` の custom）** で表示が崩れないこと（文字の切れ・はみ出し・縦スクロールの出現が無いこと）を確かめる。実機モニタの解像度は未確認なので、実機で確認が必要と報告する。
3. 2つのブラウザで同時に別の行を編集し、互いの内容が消えないこと。
4. サーバーを止めて再起動しても、入力済みの内容が残ること。

- [ ] **Step 5: 完了報告**

次を「完了／未完了／未確認」に分けて報告する（`.claude/launch.json` 以外の一時ファイルは、削除してよいか対象名と理由を示して承認を求める）。

- 完了: 全 Task のテスト結果、ブラウザで確認できた項目
- 未確認（実機で確認が必要）: Windows のタッチキーボードの表示、70インチモニタの解像度、ピンチ・スワイプのタッチ操作、`起動.bat` の自動起動（PC起動時）
- 確認用に残ったもの（削除の承認を求める）: `data/board.db`（見本データ入り）、`config.json`（試験用）、`accident_cases/` と `documents/doc1/` の見本PDF
- ユーザーの判断が要るもの: コミットしてよいか（まだ1回もコミットしていません）、実装中に見つかった想定との違い

