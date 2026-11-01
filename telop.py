import hashlib
from pathlib import Path

from accident import natural_key

MAX_ITEMS = 200  # 全体で流す件数の上限
MAX_CHARS = 500  # 1件の文字数の上限（超えた分は切る）
MAX_FILE_BYTES = 1024 * 1024  # これより大きいファイルは読まない


def _txt_files(folder):
    folder = Path(folder)
    if not folder.is_dir():
        return []
    files = [p for p in folder.iterdir() if p.suffix.lower() == ".txt" and p.is_file()]
    return sorted(files, key=lambda p: natural_key(p.name))


def _decode(raw):
    # UTF-16（BOM付き）・メモ帳の UTF-8（BOM付き）・Shift-JIS のどれでも読む。どれでもなければ読めない文字だけ置き換える
    encodings = ("utf-8-sig", "cp932")
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        encodings = ("utf-16",) + encodings
    for enc in encodings:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="replace")


def read_items(folder):
    """フォルダ内の *.txt を名前順に読み、空でない行を1件ずつ返す。読めないファイルは飛ばす。"""
    items = []
    for path in _txt_files(folder):
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            text = _decode(path.read_bytes())
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if line:
                items.append(line[:MAX_CHARS])
                if len(items) >= MAX_ITEMS:
                    return items
    return items


def signature(folder):
    """*.txt の（名前・更新時刻・大きさ）。編集・追加・削除で変わる。"""
    parts = []
    for path in _txt_files(folder):
        try:
            st = path.stat()
        except OSError:
            continue
        parts.append(f"{path.name}/{st.st_mtime_ns}/{st.st_size}")
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16] if parts else "-"
