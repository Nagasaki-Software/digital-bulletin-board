"""古い版のフォルダから、入力した内容・設定・PDF などを、新しい版のフォルダへ写す（データ引き継ぎ.bat から呼ぶ）。

古いフォルダの中身は変えない（読むだけ）。新しいフォルダの見本の会社名・工事件名は「見本データ」フォルダへ移してから写す。
標準ライブラリだけで動く（初回セットアップの前でも使えるように）。
"""
import json
import shutil
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

APP_ID = "digital-bulletin-board"
DEFAULT_PORT = 5100
SAMPLE_DIR = "見本データ"
DB_FILES = ("board.db", "board.db-wal", "board.db-shm")
# いつも写すもの（無ければ飛ばす）。logs は写さない
FIXED = ["config.json", "admin_key.txt", "data", "accident_cases", "documents", "telop", "whiteboard", "whiteboard_pdfs", "backups"]


class MigrateError(Exception):
    pass


def board_is_running(folder):
    """そのフォルダの server_port.txt のポート（無ければ 5100）で、掲示板が返事をするか。"""
    port = DEFAULT_PORT
    try:
        text = (Path(folder) / "server_port.txt").read_text(encoding="utf-8").strip()
        if text.isdigit():
            port = int(text)
    except OSError:
        pass
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as r:
            return json.loads(r.read().decode("utf-8")).get("app") == APP_ID
    except (OSError, ValueError):
        return False


def config_paths(old):
    """古い config.json に書かれたフォルダ・ファイルの場所の一覧（書き間違いで読めなければ空）。"""
    try:
        cfg = json.loads((old / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(cfg, dict):
        return []
    out = [cfg.get(k) for k in ("accident_folder", "whiteboard_save_folder", "whiteboard_pdf_folder",
                                "companies_folder", "constructions_folder", "custom_holidays_file")]
    telop = cfg.get("telop")
    if isinstance(telop, dict):
        out.append(telop.get("folder"))
    docs = cfg.get("documents")
    if isinstance(docs, dict) and isinstance(docs.get("buttons"), list):
        out += [b.get("folder") for b in docs["buttons"] if isinstance(b, dict)]
    return [p.strip() for p in out if isinstance(p, str) and p.strip()]


def _copy(src, dst):
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _count(path):
    return sum(1 for p in path.rglob("*") if p.is_file()) if path.is_dir() else 1


def migrate(old, new, overwrite_db=False, is_running=board_is_running):
    """写した内容を、画面に出す行のリストで返す。写せないときは MigrateError（何も写さない）。"""
    old, new = Path(old), Path(new)
    if not old.is_dir():
        raise MigrateError(f"古いフォルダが見つかりません: {old}")
    if old.resolve() == new.resolve():
        raise MigrateError("古いフォルダに、この新しいフォルダが指定されています。古い版のフォルダを指定してください")
    if not (old / "app.py").is_file() or not (old / "data").is_dir():
        raise MigrateError(f"デジタル掲示板のフォルダではないようです（app.py と data がありません）: {old}")
    if is_running(old):
        raise MigrateError("古い掲示板が動いています。黒い窓で Ctrl + C を押して止めてから、もう一度実行してください")
    if (new / "data" / "board.db").exists() and not overwrite_db:
        raise MigrateError("新しいフォルダには、すでに入力した内容（data\\board.db）があります。新しいフォルダで一度起動したためです")

    report = []
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 新しいフォルダの入力内容を上書きするときは、消さずに見本データへ移しておく
    if (new / "data" / "board.db").exists():
        keep = new / SAMPLE_DIR / f"上書き前のboard_{stamp}"
        keep.mkdir(parents=True, exist_ok=True)
        for name in DB_FILES:
            if (new / "data" / name).exists():
                shutil.move(str(new / "data" / name), str(keep / name))
        report.append(f"新しいフォルダの入力内容は {keep.relative_to(new)} へ移しました")

    # 見本の会社名・工事件名（古いほうに無いファイル）を見本データへ移す。混ざらないように
    for folder in ("companies", "constructions"):
        src_old, src_new = old / "data" / folder, new / "data" / folder
        if not src_old.is_dir() or not src_new.is_dir():
            continue
        moved = 0
        for f in src_new.iterdir():
            if f.is_file() and not (src_old / f.name).exists():
                dst = new / SAMPLE_DIR / folder / f.name
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(f), str(dst))
                moved += 1
        if moved:
            report.append(f"見本の {folder} のファイル {moved} 個を {SAMPLE_DIR}\\{folder} へ移しました")

    # 写すものを決める（設定で変えたフォルダも。ほかのPC・共有の場所は写さない）
    targets, seen = [], set()
    old_root = old.resolve()
    for rel in FIXED + config_paths(old):
        p = Path(rel)
        if p.is_absolute() or p.drive or str(rel).startswith(("\\\\", "//")):
            report.append(f"そのまま使います（写しません）: {rel}")
            continue
        src = (old / p).resolve()
        if src != old_root and old_root not in src.parents:
            report.append(f"アプリのフォルダの外なので写しません: {rel}")
            continue
        key = src.relative_to(old_root)
        if key in seen or any(s in key.parents for s in seen):
            continue
        seen.add(key)
        targets.append(key)

    for key in targets:
        src = old_root / key
        if not src.exists():
            continue
        _copy(src, new / key)
        n = _count(src)
        report.append(f"写しました: {key}" + (f"（ファイル {n} 個）" if src.is_dir() else ""))
    return report


def main(argv):
    new = Path(__file__).resolve().parent
    print("============================================")
    print(" デジタル掲示板 データ引き継ぎ")
    print("============================================")
    print(f"新しい版のフォルダ: {new}")
    print()
    raw = argv[1] if len(argv) > 1 else input("古い版のフォルダの場所を入れて Enter を押してください（フォルダをこの窓へドラッグしても入ります）\n> ")
    old = Path(raw.strip().strip('"'))
    overwrite = False
    while True:
        try:
            report = migrate(old, new, overwrite_db=overwrite)
            break
        except MigrateError as e:
            print()
            print("[止めました] " + str(e))
            if "入力した内容" in str(e) and not overwrite:
                ans = input("古いフォルダの内容で上書きしますか？（新しいフォルダの内容は「見本データ」に残します） y / n > ")
                if ans.strip().lower() == "y":
                    overwrite = True
                    continue
            print("何も写していません。")
            return 1
    print()
    for line in report:
        print("  " + line)
    print()
    print("引き継ぎが終わりました。古いフォルダはそのまま残っています。")
    print("次に「初回セットアップ.bat」、そのあと「起動.bat」を実行してください。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
