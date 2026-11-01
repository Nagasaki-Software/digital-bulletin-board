from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", ".browser", ".claude", ".superpowers", ".pytest_cache", "__pycache__", "node_modules", "logs", "backups", "data", "telop", "documents", "accident_cases"}
TEXT_SUFFIXES = {".py", ".js", ".mjs", ".html", ".css", ".md", ".txt", ".json"}
RUNTIME_FILES = {"config.json", "admin_key.txt", "server_port.txt"}  # 利用者の環境で作られる。git の管理外
CRLF_FILES = {"起動.bat", "初回セットアップ.bat"}  # .bat だけは CRLF（cp932）。.gitattributes は * -text で変換しない


def text_files():
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT)
        if SKIP_DIRS & set(rel.parts[:-1]) or not p.is_file():
            continue
        if rel.as_posix() in RUNTIME_FILES:
            continue
        if p.suffix in TEXT_SUFFIXES or p.name in (".gitignore", ".gitattributes"):
            yield rel, p


def test_no_text_file_has_crlf_line_endings():
    found = [str(rel) for rel, p in text_files() if b"\r\n" in p.read_bytes()]
    assert found == []  # * -text のため、CRLF のまま保存すると差分が全行になる。LF にそろえる


def test_the_two_bat_files_keep_crlf():
    for name in CRLF_FILES:
        raw = (ROOT / name).read_bytes()
        assert raw.count(b"\r\n") == raw.count(b"\n") > 0, name


def test_the_walk_really_covers_the_source_files():
    names = {rel.as_posix() for rel, _ in text_files()}
    assert {"app.py", "config.py", "masters.py", "static/board.html", "static/js/links.js", "tests/test_line_endings.py"} <= names
