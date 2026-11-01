import logging
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


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
