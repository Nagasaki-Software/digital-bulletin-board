import logging
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def write_masters(data_dir, companies=None, constructions=None, bom=True):
    """登録リストを新しい置き方（1ファイル1項目のフォルダ）で書く。None のフォルダは作らない（フォルダが無い場合の試験用）。
    companies: {会社名: [(責任者, 内線, 外線), ...]} → data/companies/<会社名>.csv（空のリストは見出し行だけ）
    constructions: {工事件名: [作業内容, ...]} → data/constructions/<工事件名>.csv"""
    data_dir = Path(data_dir)
    encoding = "utf-8-sig" if bom else "utf-8"
    for folder, items, header, row in (
        ("companies", companies, "責任者,内線,外線", lambda r: ",".join(r)),
        ("constructions", constructions, "作業内容", lambda r: r),
    ):
        if items is None:
            continue
        (data_dir / folder).mkdir(parents=True, exist_ok=True)
        for name, rows in items.items():
            text = "\n".join([header] + [row(r) for r in rows]) + "\n"
            (data_dir / folder / f"{name}.csv").write_text(text, encoding=encoding, newline="")


@pytest.fixture(autouse=True)
def _scan_cache_off(monkeypatch):
    # 登録フォルダの一覧は本番では約2秒キャッシュするが、ファイルを直したらすぐ rev に出ることを確かめる試験が多いので、通常は切る。
    # キャッシュ自体の試験は test_masters_folders.py で、時計つきで行う
    import masters

    monkeypatch.setattr(masters, "SCAN_TTL", 0)


@pytest.fixture(autouse=True)
def _close_app_log():
    # create_app が開いた logs/app.log を、テストごとに閉じる（開いたままだと Windows で一時フォルダを消せない）
    yield
    import app

    app.close_logging()


@pytest.fixture
def busy_sockets():
    """127.0.0.1 の空きポートを実際に待ち受けて塞ぐ。"""
    socks = []

    def hold():
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        s.listen(128)
        socks.append(s)
        return s.getsockname()[1]

    yield hold
    for s in socks:
        s.close()


class _Catch(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)

    @property
    def text(self):
        return "\n".join(r.getMessage() for r in self.records)


@pytest.fixture
def app_caplog():
    """アプリのロガーは root に流さない（waitress の重複表示を防ぐ）ので、caplog ではなく、アプリのロガーに直接つないで記録する。"""
    lg = logging.getLogger("digital_bulletin_board")
    handler = _Catch()
    lg.addHandler(handler)
    yield handler
    lg.removeHandler(handler)
