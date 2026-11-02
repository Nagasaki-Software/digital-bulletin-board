# ホワイトボード機能 実装計画

> **実行する人へ:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development（推奨）または superpowers:executing-plans で、タスクごとに進める。手順はチェックボックス（`- [ ]`）で追う。

**Goal:** 掲示板の画面を、タッチで描けるホワイトボードに切り替え、カラーPDFで保存できるようにする（背景PDF・操作なし戻り・自動保存つき）。

**Architecture:** 画面側は新規 `static/js/whiteboard.js`（描画・道具・操作なし監視）と、node でも試せる純粋な部品 `static/js/whiteboard-core.mjs`（描いた記録・元に戻す・図形の計算）。保存は、背景+描画を重ねた画像をJPEGにしてサーバーへ送り、新規 `whiteboard.py` が標準ライブラリだけで1ページのPDFに包んで保存先へ書く。設定3項目は既存の `config.py` / `app.py` / `admin-settings.js` の作りに足す。

**Tech Stack:** Flask（既存）、標準ライブラリの Python、バニラ JS（ES モジュール）、同梱の pdf.js。**新しいライブラリは入れない。**

**Spec:** `docs/superpowers/specs/2026-11-02-whiteboard-design.md`

## Global Constraints

- 新しいパッケージ（pip / npm / CDN）を入れない。
- コミットしない（ユーザーが頼んだときだけ）。版番号は上げない（v0.3.0 の公開は別の依頼）。
- テキストファイルは LF（`tests/test_line_endings.py` が検査する）。Python で `open()` するときは `encoding=` を明示する。
- 画面の文字はメイリオ優先（既存の `body` の指定を継承）。長さの単位は `rem`（`html { font-size: calc(100vw / 180) }` で画面幅に比例する）。
- 保存先に書けないときは、描いたものを消さずにエラーを画面に出す。自動保存で失敗したら戻らず画面に残す。
- 「保存先を試す」ボタンは作らない。複数ページPDFの出力・選択移動・表示側PCへの保存は作らない。
- テスト実行: `.venv/Scripts/python.exe -m pytest -q`（Python）、`node --test tests/js/*.test.mjs`（JS）。作業前の基準は pytest 1049 件・node 55 件が全部通ること。
- 確認用のファイルは scratchpad（セッションの一時フォルダ）に作る。プロジェクトの中に作らない。削除は対象と理由を言って承認を取る。

## Rulings（計画での判断）

- 自動保存は「描いてあって、最後の保存のあとに描き足している」ときだけ行う（手動で保存した直後に放置して、同じ内容の `_自動保存` ができるのを防ぐ）。
- 背景PDFは、画面（描画エリア）にぴったり収まる大きさで中央に置く。保存されるPDFのページの縦横比は、描画エリアと同じ。
- 保存のデータは JSON（base64 の JPEG）で送る。既存の `api()` をそのまま使えるため。サーバーは本文を 40MB で打ち切る。
- 文字は1行だけ（改行なし）。

## Review Focus（仕様が黙っているが、実際に起きやすいこと）

1. 保存先に書けない（権限なし・フォルダの場所に同名のファイルがある・ネットワーク切断）→ エラーの文言が出て、描画が残る。（Task 2・5）
2. 壊れた・大きすぎる・JPEG でないデータが送られてくる → 400/413 を返し、保存フォルダには何も作らない。（Task 1・3）
3. 背景PDFの名前に `..` やサブフォルダが含まれる → 404（フォルダの外は読ませない）。（Task 3）
4. 同じ秒に2回保存 → 上書きせず連番を付ける。日本語の名前（`_自動保存`）で保存・一覧できる。（Task 1）
5. 2本指・パームタッチ（指が複数）や、文字入力中に別の場所を押す → 描きかけが壊れない。（Task 5）

## ファイル構成

| ファイル | 役目 |
|---|---|
| 新規 `whiteboard.py` | JPEG の読み取り、1ページPDFの組み立て、保存（名前・連番・一時ファイル経由の書き込み） |
| 新規 `static/js/whiteboard-core.mjs` | 道具・色・太さの定数、描いた記録（元に戻す/やり直し/全部消す）、図形の計算。DOM を使わない |
| 新規 `static/js/whiteboard.js` | 描画画面の操作・背景PDF・保存・操作なし戻り |
| 変更 `config.py` | 設定3項目の既定・読み込み・確認・保存 |
| 変更 `app.py` | 設定の受け渡し、`/api/whiteboard/*` の3つ、背景PDFフォルダの用意、本文の大きさ上限 |
| 変更 `static/board.html` / `static/board.css` | ボタン・描画画面・設定欄 |
| 変更 `static/js/board.js` / `standby.js` / `admin-settings.js` | 組み込み・スリープ抑止・設定欄 |
| 新規 `tests/test_whiteboard.py` `tests/test_whiteboard_settings.py` `tests/test_whiteboard_api.py` `tests/js/whiteboard-core.test.mjs` | 試験 |
| 変更 `tests/test_admin_settings.py` `tests/test_static.py` ほか | 既存の試験の期待値を新しい項目に合わせる |
| 変更 `README.md` `docs/manual/取扱説明書.md` | 説明 |

---

### Task 1: PDFを作って保存する部品 `whiteboard.py`

**Files:**
- Create: `whiteboard.py`
- Test: `tests/test_whiteboard.py`

**Interfaces:**
- Produces（Task 3 が使う）:
  - `class ImageError(ValueError)`
  - `decode_image(text) -> bytes`（base64 → JPEG のバイト列。不正は ImageError）
  - `jpeg_info(data) -> (幅, 高さ, 色の数)`（不正は ImageError）
  - `jpeg_to_pdf(jpeg) -> bytes`
  - `file_name(now, auto) -> str`
  - `save_pdf(folder, jpeg, auto=False, now=None) -> str`（書いたファイル名。書けないときは OSError）
  - `MAX_IMAGE_BYTES = 30 * 1024 * 1024`

- [ ] **Step 1: 失敗するテストを書く** — `tests/test_whiteboard.py`

```python
import base64
import re
from datetime import datetime

import pytest

import whiteboard as wb


def fake_jpeg(w=1920, h=1080, comps=3):
    """PDF に包む試験用の、最小の JPEG 見出し（SOI + SOF0 + EOI）。画像として開くことはしない。"""
    sof = (
        b"\xff\xc0" + (8 + 3 * comps).to_bytes(2, "big") + b"\x08"
        + h.to_bytes(2, "big") + w.to_bytes(2, "big") + bytes([comps])
        + b"".join(bytes([i + 1, 0x11, 0]) for i in range(comps))
    )
    return b"\xff\xd8" + sof + b"\xff\xd9"


NOW = datetime(2026, 11, 2, 21, 30, 0)


def test_jpeg_info_reads_size_and_components():
    assert wb.jpeg_info(fake_jpeg(1920, 1080, 3)) == (1920, 1080, 3)
    assert wb.jpeg_info(fake_jpeg(10, 20, 1)) == (10, 20, 1)


@pytest.mark.parametrize("data", [b"", b"abc", b"\xff\xd8", b"\xff\xd8\xff\xd9", b"%PDF-1.4", b"\xff\xd8\xff\xc0\x00\x11\x08\x00"])
def test_jpeg_info_rejects_broken_data(data):
    with pytest.raises(wb.ImageError):
        wb.jpeg_info(data)


def test_pdf_is_well_formed():
    jpeg = fake_jpeg()
    pdf = wb.jpeg_to_pdf(jpeg)
    assert pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF")
    start = int(re.search(rb"startxref\n(\d+)\n", pdf)[1])
    assert pdf[start:start + 4] == b"xref"
    entries = [line for line in pdf[start:].split(b"\n") if line.endswith(b" n ")]
    assert len(entries) == 5
    for num, line in enumerate(entries, 1):
        head = f"{num} 0 obj".encode()
        off = int(line[:10])
        assert pdf[off:off + len(head)] == head
    assert jpeg in pdf
    assert int(re.search(rb"/Length (\d+) >>\nstream\n\xff\xd8", pdf)[1]) == len(jpeg)
    assert b"/Count 1" in pdf and b"/DCTDecode" in pdf and b"/DeviceRGB" in pdf
    m = re.search(rb"/MediaBox \[0 0 ([\d.]+) ([\d.]+)\]", pdf)
    assert float(m[1]) == pytest.approx(841.89)
    assert float(m[2]) == pytest.approx(841.89 * 1080 / 1920, abs=0.01)


def test_gray_jpeg_uses_device_gray_and_four_components_are_rejected():
    assert b"/DeviceGray" in wb.jpeg_to_pdf(fake_jpeg(10, 10, 1))
    with pytest.raises(wb.ImageError):
        wb.jpeg_to_pdf(fake_jpeg(10, 10, 4))


def test_decode_image():
    jpeg = fake_jpeg()
    assert wb.decode_image(base64.b64encode(jpeg).decode()) == jpeg
    for bad in (None, 5, "***not base64***", "abc", "x" * (wb.MAX_IMAGE_BYTES * 2)):
        with pytest.raises(wb.ImageError):
            wb.decode_image(bad)


def test_file_name_is_date_time_with_auto_suffix():
    assert wb.file_name(NOW, False) == "2026-11-02_21-30-00.pdf"
    assert wb.file_name(NOW, True) == "2026-11-02_21-30-00_自動保存.pdf"


def test_save_pdf_writes_and_numbers_duplicates(tmp_path):
    folder = tmp_path / "深い" / "保存先"  # 無いフォルダは作る。日本語の場所でも書ける
    a = wb.save_pdf(folder, fake_jpeg(), now=NOW)
    b = wb.save_pdf(folder, fake_jpeg(), now=NOW)  # 同じ秒 → 上書きしない
    c = wb.save_pdf(folder, fake_jpeg(), auto=True, now=NOW)
    assert (a, b, c) == ("2026-11-02_21-30-00.pdf", "2026-11-02_21-30-00_2.pdf", "2026-11-02_21-30-00_自動保存.pdf")
    assert sorted(p.name for p in folder.iterdir()) == sorted([a, b, c])  # 一時ファイルが残らない
    assert (folder / a).read_bytes().startswith(b"%PDF-1.4")


def test_save_pdf_with_bad_image_does_not_touch_the_folder(tmp_path):
    folder = tmp_path / "out"
    with pytest.raises(wb.ImageError):
        wb.save_pdf(folder, b"not a jpeg", now=NOW)
    assert not folder.exists()


def test_save_pdf_raises_oserror_when_folder_cannot_be_made(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(OSError):
        wb.save_pdf(blocker, fake_jpeg(), now=NOW)
```

- [ ] **Step 2: 失敗を確かめる**

Run: `.venv/Scripts/python.exe -m pytest tests/test_whiteboard.py -q`
Expected: `ModuleNotFoundError: No module named 'whiteboard'`

- [ ] **Step 3: 実装する** — `whiteboard.py`

```python
"""ホワイトボードの保存。標準ライブラリだけで、JPEG 画像を1ページの PDF に包んで保存先に書く。"""
import base64
import binascii
import os
from datetime import datetime
from pathlib import Path

MAX_IMAGE_BYTES = 30 * 1024 * 1024
PAGE_WIDTH_PT = 841.89  # A4 横の幅。高さは画像の縦横比で決める
_SOF = (0xC0, 0xC1, 0xC2)  # 画像の大きさが書かれている印（ベースライン・拡張・プログレッシブ）


class ImageError(ValueError):
    """送られてきた画像が使えない（日本語の理由つき）。"""


def decode_image(text):
    if not isinstance(text, str) or not text:
        raise ImageError("画像がありません")
    if len(text) > MAX_IMAGE_BYTES * 4 // 3 + 8:
        raise ImageError("画像が大きすぎます")
    try:
        return base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        raise ImageError("画像の形式が正しくありません") from None


def jpeg_info(data):
    """JPEG の (幅, 高さ, 色の数)。JPEG でない・壊れているときは ImageError。"""
    broken = ImageError("JPEG画像ではない、または壊れています")
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        raise broken
    i, n = 2, len(data)
    while i + 4 <= n:
        if data[i] != 0xFF:
            raise broken
        marker = data[i + 1]
        if marker == 0xFF:  # 詰め物
            i += 1
            continue
        if marker == 0x01 or 0xD0 <= marker <= 0xD8:  # 長さのない印
            i += 2
            continue
        if marker in _SOF:
            if i + 10 > n:
                raise broken
            h = int.from_bytes(data[i + 5:i + 7], "big")
            w = int.from_bytes(data[i + 7:i + 9], "big")
            if w < 1 or h < 1:
                raise broken
            return w, h, data[i + 9]
        if marker == 0xDA:  # 大きさの印より先に画像本体が始まった
            raise broken
        i += 2 + int.from_bytes(data[i + 2:i + 4], "big")
    raise broken


def jpeg_to_pdf(jpeg):
    w, h, comps = jpeg_info(jpeg)
    if comps not in (1, 3):
        raise ImageError(f"対応していない画像です（色の数 {comps}）")
    space = b"/DeviceRGB" if comps == 3 else b"/DeviceGray"
    page_h = PAGE_WIDTH_PT * h / w
    box = b"[0 0 %.2f %.2f]" % (PAGE_WIDTH_PT, page_h)
    content = b"q %.2f 0 0 %.2f 0 0 cm /Im0 Do Q" % (PAGE_WIDTH_PT, page_h)
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox " + box + b" /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace %s /BitsPerComponent 8 /Filter /DCTDecode /Length %d >>\nstream\n"
        % (w, h, space, len(jpeg)) + jpeg + b"\nendstream",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for num, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % num + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


def file_name(now, auto):
    return now.strftime("%Y-%m-%d_%H-%M-%S") + ("_自動保存" if auto else "") + ".pdf"


def save_pdf(folder, jpeg, auto=False, now=None):
    """PDF にして folder に書き、書いたファイル名を返す。画像が使えなければ ImageError（フォルダには触れない）、
    書けなければ OSError。同じ名前があれば上書きせず _2, _3… を付ける。一時ファイルに書いてから名前を付け替える。"""
    pdf = jpeg_to_pdf(jpeg)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    stem = file_name(now or datetime.now(), auto)[:-4]
    dest, n = folder / (stem + ".pdf"), 1
    while dest.exists():
        n += 1
        dest = folder / f"{stem}_{n}.pdf"
    tmp = folder / (dest.name + ".tmp")
    try:
        with open(tmp, "wb") as f:
            f.write(pdf)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, dest)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    return dest.name
```

- [ ] **Step 4: 通ることを確かめる**

Run: `.venv/Scripts/python.exe -m pytest tests/test_whiteboard.py -q`
Expected: 全部 PASS

---

### Task 2: 設定3項目（保存フォルダ・背景用PDFフォルダ・操作なし戻り秒）

**Files:**
- Modify: `config.py`（DEFAULTS・定数・`load_config`・`clean_admin_settings`・`save_admin_settings`）
- Modify: `app.py`（`build_runtime`・`ensure_folders`・`/api/admin-settings` GET・`/api/board` の settings・`_changed_groups`）
- Create: `tests/test_whiteboard_settings.py`
- Modify: `tests/test_admin_settings.py`（`NEW_GET` に3項目を足す）

**Interfaces:**
- Produces: config のキー `whiteboard_save_folder`（既定 `"whiteboard"`）、`whiteboard_pdf_folder`（既定 `"whiteboard_pdfs"`）、`whiteboard_idle_seconds`（既定 `180`、30〜3600 の整数）。
  `rt()` に `wb_save_dir` と `wb_pdf_dir`（Path）。`/api/board` の `settings.whiteboard_idle_seconds`。`/api/admin-settings` の GET/POST に同じ3キー（トップレベル）。

- [ ] **Step 1: 失敗するテストを書く** — `tests/test_whiteboard_settings.py`

```python
import json
from datetime import date

import pytest

from app import create_app
from config import clean_admin_settings, load_config

BASE = {"documents": {"buttons": [{"label": "a", "folder": "documents/x"}]}, "telop": {"speed": 100}}


def make(tmp_path, config=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    if config is not None:
        (tmp_path / "config.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return create_app(tmp_path, today_func=lambda: date(2026, 11, 2)).test_client()


def test_defaults_are_returned_and_board_gets_idle_seconds(tmp_path):
    c = make(tmp_path)
    got = c.get("/api/admin-settings").get_json()
    assert got["whiteboard_save_folder"] == "whiteboard"
    assert got["whiteboard_pdf_folder"] == "whiteboard_pdfs"
    assert got["whiteboard_idle_seconds"] == 180
    assert c.get("/api/board").get_json()["settings"]["whiteboard_idle_seconds"] == 180


def test_pdf_folder_is_made_at_startup_but_save_folder_is_not(tmp_path):
    make(tmp_path)
    assert (tmp_path / "whiteboard_pdfs").is_dir()
    assert not (tmp_path / "whiteboard").exists()  # 保存先は、最初に保存するときに作る（ネットワークの場所を起動時に触らない）


def test_post_saves_the_three_values(tmp_path):
    c = make(tmp_path)
    body = {**BASE, "whiteboard_save_folder": "//server/share/ホワイト", "whiteboard_pdf_folder": "D:/背景", "whiteboard_idle_seconds": 90}
    r = c.post("/api/admin-settings", json=body)
    assert r.status_code == 200, r.get_json()
    got = c.get("/api/admin-settings").get_json()
    assert (got["whiteboard_save_folder"], got["whiteboard_pdf_folder"], got["whiteboard_idle_seconds"]) == ("//server/share/ホワイト", "D:/背景", 90)
    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert saved["whiteboard_idle_seconds"] == 90


def test_empty_folder_means_default_and_missing_keys_keep_current(tmp_path):
    c = make(tmp_path, {"whiteboard_save_folder": "mine", "whiteboard_idle_seconds": 60})
    clean = clean_admin_settings({**BASE, "whiteboard_save_folder": "  ", "whiteboard_pdf_folder": ""})
    assert clean["whiteboard_save_folder"] == "whiteboard" and clean["whiteboard_pdf_folder"] == "whiteboard_pdfs"
    assert "whiteboard_idle_seconds" not in clean_admin_settings(BASE)  # 古い画面は送らない → いまのまま
    assert c.post("/api/admin-settings", json=BASE).status_code == 200
    assert c.get("/api/admin-settings").get_json()["whiteboard_save_folder"] == "mine"


@pytest.mark.parametrize("bad", [29, 3601, 0, -5, 90.5, "90", None, True, [90]])
def test_idle_seconds_must_be_30_to_3600(bad):
    with pytest.raises(ValueError, match="30〜3600"):
        clean_admin_settings({**BASE, "whiteboard_idle_seconds": bad})


@pytest.mark.parametrize("ok", [30, 180, 3600])
def test_idle_seconds_edges_are_accepted(ok):
    assert clean_admin_settings({**BASE, "whiteboard_idle_seconds": ok})["whiteboard_idle_seconds"] == ok


@pytest.mark.parametrize("key", ["whiteboard_save_folder", "whiteboard_pdf_folder"])
def test_folders_reject_parent_marks_non_text_and_long_paths(key):
    for bad in ("a/../b", "..", 5, ["x"], "x" * 261):
        with pytest.raises(ValueError):
            clean_admin_settings({**BASE, key: bad})
    assert clean_admin_settings({**BASE, key: "x" * 260})[key] == "x" * 260


def test_bad_values_in_config_json_fall_back_with_a_warning(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"whiteboard_idle_seconds": 5, "whiteboard_save_folder": 3}), encoding="utf-8")
    cfg = load_config(p)
    assert cfg["whiteboard_idle_seconds"] == 180 and cfg["whiteboard_save_folder"] == "whiteboard"
    assert any("whiteboard_idle_seconds" in w for w in cfg["_warnings"])
```

- [ ] **Step 2: 失敗を確かめる**

Run: `.venv/Scripts/python.exe -m pytest tests/test_whiteboard_settings.py -q`
Expected: FAIL（KeyError など）

- [ ] **Step 3: `config.py` を直す**

`DEFAULTS` の `"custom_holidays_file": ...` の次に追加:

```python
    "whiteboard_save_folder": "whiteboard",
    "whiteboard_pdf_folder": "whiteboard_pdfs",
    "whiteboard_idle_seconds": 180,
```

定数（`MAX_STAY = 3600` の次）:

```python
MIN_WB_IDLE = 30
MAX_WB_IDLE = 3600
```

`_stay` の次に追加:

```python
def _wb_idle(v):
    return v if isinstance(v, int) and not isinstance(v, bool) and MIN_WB_IDLE <= v <= MAX_WB_IDLE else _BAD
```

`load_config` の `take(user, "custom_holidays_file", ...)` の次に追加:

```python
    take(user, "whiteboard_save_folder", "whiteboard_save_folder", _path, cfg)
    take(user, "whiteboard_pdf_folder", "whiteboard_pdf_folder", _path, cfg)
    take(user, "whiteboard_idle_seconds", "whiteboard_idle_seconds", _wb_idle, cfg, "秒")
```

`_admin_seconds` の次に追加:

```python
def _admin_folder(v, label, default):
    if not isinstance(v, str):
        raise ValueError(f"{label}は文字で入力してください")
    v = v.strip() or default  # 空欄は既定の場所
    if _path(v) is _BAD:
        raise ValueError(f"{label}を正しく入力してください（{MAX_PATH}文字以内）")
    if ".." in re.split(r"[\\/]+", v):
        raise ValueError(f"{label}に「..」は使えません")
    return v
```

`clean_admin_settings` の `if "links" in body:` の前に追加:

```python
    for key, label in (("whiteboard_save_folder", "ホワイトボードの保存フォルダ"), ("whiteboard_pdf_folder", "ホワイトボードの背景用PDFフォルダ")):
        if key in body:
            clean[key] = _admin_folder(body[key], label, DEFAULTS[key])
    if "whiteboard_idle_seconds" in body:
        n = _wb_idle(body["whiteboard_idle_seconds"])
        if n is _BAD:
            raise ValueError(f"ホワイトボードの操作なし戻り（秒）は {MIN_WB_IDLE}〜{MAX_WB_IDLE} の整数で入力してください")
        clean["whiteboard_idle_seconds"] = n
```

`save_admin_settings` の `for key in ("accident_seconds", "edit_lock_seconds", "custom_holidays_file"):` を次に変える:

```python
    for key in ("accident_seconds", "edit_lock_seconds", "custom_holidays_file", "whiteboard_save_folder", "whiteboard_pdf_folder", "whiteboard_idle_seconds"):
```

- [ ] **Step 4: `app.py` を直す**

`build_runtime` の `SimpleNamespace(...)` に追加（`telop_dir=...` の行の次）:

```python
            wb_save_dir=_resolve(base, cfg["whiteboard_save_folder"]),
            wb_pdf_dir=_resolve(base, cfg["whiteboard_pdf_folder"]),
```

`ensure_folders` の `targets.append((r.telop_dir, "お知らせ"))` の次に追加:

```python
        targets.append((r.wb_pdf_dir, "ホワイトボードの背景PDF"))
```

`api_get_admin_settings` の返す辞書の `"custom_holidays_file": ...` の次に追加:

```python
                "whiteboard_save_folder": cfg["whiteboard_save_folder"],
                "whiteboard_pdf_folder": cfg["whiteboard_pdf_folder"],
                "whiteboard_idle_seconds": cfg["whiteboard_idle_seconds"],
```

`api_board` の `"settings"` に追加（`"documents_idle_seconds": ...` の次）:

```python
                    "whiteboard_idle_seconds": cfg["whiteboard_idle_seconds"],
```

`_changed_groups` の `if "custom_holidays_file" in clean ...` の次に追加:

```python
    for key, label in (("whiteboard_save_folder", "ホワイトボードの保存フォルダ"), ("whiteboard_pdf_folder", "ホワイトボードの背景用PDFフォルダ"), ("whiteboard_idle_seconds", "ホワイトボードの操作なし戻り")):
        if key in clean and clean[key] != old[key]:
            out.append(f"{label}（{clean[key]}）")
```

- [ ] **Step 5: 既存の試験の期待値を直す**

`tests/test_admin_settings.py` の `NEW_GET` に追加:

```python
    "whiteboard_save_folder": "whiteboard",
    "whiteboard_pdf_folder": "whiteboard_pdfs",
    "whiteboard_idle_seconds": 180,
```

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 新しい試験は PASS。**既存の試験で、設定の辞書全体・作られるフォルダの一覧・`settings` の全体を比べているものが落ちたら**、その期待値に新しい項目を足す（`tests/test_api.py` の `s = b["settings"]` 付近など）。足すのは期待値だけで、挙動は変えない。全部 PASS になるまで直す。

---

### Task 3: サーバーの3つの入口（背景PDFの一覧・取得、保存）

**Files:**
- Modify: `app.py`
- Create: `tests/test_whiteboard_api.py`

**Interfaces:**
- Consumes: Task 1 の `whiteboard`、Task 2 の `rt().wb_pdf_dir` / `rt().wb_save_dir`。
- Produces（Task 5 が使う）:
  - `GET /api/whiteboard/pdfs` → `["a.pdf", ...]`（自然順）
  - `GET /api/whiteboard/pdf/<name>` → PDF の中身。一覧に無い名前は 404
  - `POST /api/whiteboard/save` 本文 `{"image": "<base64のJPEG>", "auto": false}` → `{"ok": true, "name": "2026-11-02_21-30-00.pdf"}`。画像が使えない 400、書けない 500（`{"error": "保存先に書き込めませんでした（…）"}`）、本文が 40MB 超 413。

- [ ] **Step 1: 失敗するテストを書く** — `tests/test_whiteboard_api.py`

```python
import base64
import json
import re
from datetime import date

from app import create_app
from tests.test_whiteboard import fake_jpeg


def make(tmp_path, config=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    if config is not None:
        (tmp_path / "config.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return create_app(tmp_path, today_func=lambda: date(2026, 11, 2)).test_client()


def payload(**extra):
    return {"image": base64.b64encode(fake_jpeg()).decode(), **extra}


def test_pdf_list_and_file_only_from_the_folder(tmp_path):
    c = make(tmp_path)
    assert c.get("/api/whiteboard/pdfs").get_json() == []
    folder = tmp_path / "whiteboard_pdfs"
    (folder / "10_ひな形.pdf").write_bytes(b"%PDF-1.4 ten")
    (folder / "2_ひな形.pdf").write_bytes(b"%PDF-1.4 two")
    (folder / "memo.txt").write_text("x", encoding="utf-8")
    (folder / "sub").mkdir()
    (folder / "sub" / "x.pdf").write_bytes(b"%PDF-1.4 sub")
    assert c.get("/api/whiteboard/pdfs").get_json() == ["2_ひな形.pdf", "10_ひな形.pdf"]
    assert c.get("/api/whiteboard/pdf/2_ひな形.pdf").data == b"%PDF-1.4 two"
    for name in ("sub/x.pdf", "../config.json", "..%5Cconfig.json", "memo.txt", "none.pdf"):
        assert c.get("/api/whiteboard/pdf/" + name).status_code == 404, name


def test_save_writes_pdf_into_the_configured_folder(tmp_path):
    out = tmp_path / "出力"
    c = make(tmp_path, {"whiteboard_save_folder": str(out)})
    r = c.post("/api/whiteboard/save", json=payload())
    assert r.status_code == 200
    name = r.get_json()["name"]
    assert re.fullmatch(r"\d{4}-\d\d-\d\d_\d\d-\d\d-\d\d\.pdf", name)
    assert (out / name).read_bytes().startswith(b"%PDF-1.4")
    auto = c.post("/api/whiteboard/save", json=payload(auto=True)).get_json()["name"]
    assert auto.endswith("_自動保存.pdf") and (out / auto).is_file()


def test_save_default_folder_is_relative_to_the_app(tmp_path):
    c = make(tmp_path)
    name = c.post("/api/whiteboard/save", json=payload()).get_json()["name"]
    assert (tmp_path / "whiteboard" / name).is_file()


def test_save_rejects_bad_images_without_making_the_folder(tmp_path):
    c = make(tmp_path)
    for body in (None, {}, {"image": ""}, {"image": "***"}, {"image": base64.b64encode(b"hello").decode()}, payload(auto="yes"), []):
        r = c.post("/api/whiteboard/save", json=body)
        assert r.status_code == 400, body
        assert "error" in r.get_json()
    assert not (tmp_path / "whiteboard").exists()


def test_save_reports_a_write_failure_and_keeps_the_app_alive(tmp_path):
    blocker = tmp_path / "ふさがれた場所"
    blocker.write_text("x", encoding="utf-8")  # フォルダの場所に同名のファイルがある
    c = make(tmp_path, {"whiteboard_save_folder": str(blocker)})
    r = c.post("/api/whiteboard/save", json=payload())
    assert r.status_code == 500
    assert r.get_json()["error"].startswith("保存先に書き込めませんでした")
    assert c.get("/api/health").status_code == 200


def test_too_large_body_is_413_json(tmp_path):
    c = make(tmp_path)
    r = c.post("/api/whiteboard/save", data=b'{"image": "' + b"A" * (41 * 1024 * 1024) + b'"}', content_type="application/json")
    assert r.status_code == 413
    assert "error" in r.get_json()
    assert not (tmp_path / "whiteboard").exists()
```

- [ ] **Step 2: 失敗を確かめる**

Run: `.venv/Scripts/python.exe -m pytest tests/test_whiteboard_api.py -q`
Expected: FAIL（404 など）。`from tests.test_whiteboard import fake_jpeg` が読めない場合は、`tests/__init__.py` が無いので `tests/test_whiteboard_api.py` の先頭を `from test_whiteboard import fake_jpeg` に変える（pytest は tests フォルダを import パスに入れる）。

- [ ] **Step 3: `app.py` を直す**

import に追加（`import telop` の次）:

```python
import whiteboard as wb
```

`create_app` の中、`app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0` の次に追加:

```python
    app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024  # ホワイトボードの画像など。これより大きい本文は 413 で断る
```

`api_messages` に追加:

```python
        413: "送った内容が大きすぎます",
```

`return app` の直前（`api_doc_pdf` の次）に追加:

```python
    # ---- ホワイトボード ----
    wb_lock = threading.Lock()

    @app.get("/api/whiteboard/pdfs")
    def api_wb_pdfs():
        return jsonify(acc.list_pdfs(rt().wb_pdf_dir))

    @app.get("/api/whiteboard/pdf/<path:name>")
    def api_wb_pdf(name):
        return send_listed_pdf(rt().wb_pdf_dir, name)

    @app.post("/api/whiteboard/save")
    def api_wb_save():
        body = json_body()
        if body is None:
            return bad("保存の内容が正しくありません")
        auto = body.get("auto", False)
        if not isinstance(auto, bool):
            return bad("保存の内容が正しくありません")
        folder = rt().wb_save_dir
        try:
            jpeg = wb.decode_image(body.get("image"))
            with wb_lock:
                name = wb.save_pdf(folder, jpeg, auto)
        except wb.ImageError as e:
            return bad(str(e))
        except OSError as e:
            log.error("ホワイトボードを保存できませんでした: %s（%s）", folder, e)
            return bad(f"保存先に書き込めませんでした（{e.strerror or e}）", 500)
        log.info("ホワイトボードを保存しました: %s", name)
        return jsonify({"ok": True, "name": name})
```

- [ ] **Step 4: 通ることを確かめる**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 全部 PASS

---

### Task 4: 描いた記録と図形の計算（`whiteboard-core.mjs`）

**Files:**
- Create: `static/js/whiteboard-core.mjs`
- Test: `tests/js/whiteboard-core.test.mjs`

**Interfaces:**
- Produces（Task 5 が使う）:
  - 定数 `COLORS`（8色）、`WIDTHS = [3, 8, 16]`、`TEXT_SIZES = [24, 40, 64]`、`ERASER_SCALE = 4`、`DRAW_TYPES`（Set）
  - `createHistory()` → `{ push(op), undo(), redo(), clear(), visible(), hasInk(), canUndo(), canRedo() }`（`undo/redo/clear` は動いたら true）
  - `normRect(x1, y1, x2, y2)` → `{x, y, w, h}`
  - `arrowHead(x1, y1, x2, y2, width)` → `[[x, y], [x, y]]`
  - `thin(points, minDist = 2)` → 近すぎる点を間引く（最初と最後は残す）

- [ ] **Step 1: 失敗するテストを書く** — `tests/js/whiteboard-core.test.mjs`

```js
import test from "node:test";
import assert from "node:assert/strict";
import { COLORS, WIDTHS, TEXT_SIZES, createHistory, normRect, arrowHead, thin } from "../../static/js/whiteboard-core.mjs";

const pen = { type: "pen", color: "#111827", width: 3, points: [[0, 0], [5, 5]] };
const rect = { type: "rect", color: "#DC2626", width: 8, x: 1, y: 1, w: 10, h: 10 };
const erase = { type: "erase", color: "#000", width: 8, points: [[0, 0]] };

test("constants: 8 colors, 3 widths, 3 text sizes", () => {
  assert.equal(COLORS.length, 8);
  assert.equal(new Set(COLORS).size, 8);
  assert.equal(WIDTHS.length, 3);
  assert.equal(TEXT_SIZES.length, 3);
});

test("undo and redo walk the history; a new op drops the redo stack", () => {
  const h = createHistory();
  assert.equal(h.undo(), false);
  assert.equal(h.redo(), false);
  h.push(pen);
  h.push(rect);
  assert.deepEqual(h.visible(), [pen, rect]);
  assert.equal(h.undo(), true);
  assert.deepEqual(h.visible(), [pen]);
  assert.equal(h.canRedo(), true);
  assert.equal(h.redo(), true);
  assert.deepEqual(h.visible(), [pen, rect]);
  h.undo();
  h.push(erase);
  assert.equal(h.canRedo(), false);
  assert.deepEqual(h.visible(), [pen, erase]);
});

test("clear hides everything before it and can be undone", () => {
  const h = createHistory();
  assert.equal(h.clear(), false); // 何も無いときは記録しない
  h.push(pen);
  h.push(rect);
  assert.equal(h.clear(), true);
  assert.deepEqual(h.visible(), []);
  assert.equal(h.hasInk(), false);
  h.push(rect);
  assert.deepEqual(h.visible(), [rect]);
  h.undo();
  h.undo(); // clear を取り消す
  assert.deepEqual(h.visible(), [pen, rect]);
  assert.equal(h.hasInk(), true);
});

test("hasInk ignores eraser-only history", () => {
  const h = createHistory();
  assert.equal(h.hasInk(), false);
  h.push(erase);
  assert.equal(h.hasInk(), false);
  h.push({ type: "text", color: "#000", size: 24, x: 0, y: 0, text: "あ" });
  assert.equal(h.hasInk(), true);
});

test("normRect orders corners", () => {
  assert.deepEqual(normRect(10, 20, 4, 8), { x: 4, y: 8, w: 6, h: 12 });
  assert.deepEqual(normRect(1, 2, 3, 4), { x: 1, y: 2, w: 2, h: 2 });
});

test("arrowHead: both barbs are the same distance from the tip and point back along the line", () => {
  const [a, b] = arrowHead(0, 0, 100, 0, 8);
  const da = Math.hypot(a[0] - 100, a[1]);
  const db = Math.hypot(b[0] - 100, b[1]);
  assert.ok(Math.abs(da - db) < 1e-9);
  assert.ok(da >= 14);
  assert.ok(a[0] < 100 && b[0] < 100);
  assert.ok(a[1] * b[1] < 0); // 線をはさんで反対側
});

test("thin keeps first and last points and drops near neighbours", () => {
  const pts = [[0, 0], [0.5, 0.5], [1, 1], [10, 10], [10.2, 10.1]];
  assert.deepEqual(thin(pts, 2), [[0, 0], [10, 10], [10.2, 10.1]]);
  assert.deepEqual(thin([[3, 3]], 2), [[3, 3]]);
  assert.deepEqual(thin([[3, 3], [3, 3]], 2), [[3, 3]]);
  assert.deepEqual(thin([], 2), []);
});
```

- [ ] **Step 2: 失敗を確かめる**

Run: `node --test tests/js/whiteboard-core.test.mjs`
Expected: FAIL（モジュールが無い）

- [ ] **Step 3: 実装する** — `static/js/whiteboard-core.mjs`

```js
// ホワイトボードの、画面に依存しない部分（node でも試せる）。描いたものは「記録（op）」の並びとして持ち、画面は記録を順に描き直す。
export const COLORS = ["#111827", "#DC2626", "#EA580C", "#CA8A04", "#16A34A", "#2563EB", "#9333EA", "#6B7280"];
export const WIDTHS = [3, 8, 16]; // 細い・ふつう・太い（線の太さ。文字の大きさは TEXT_SIZES の同じ番号）
export const TEXT_SIZES = [24, 40, 64];
export const ERASER_SCALE = 4; // 消しゴムは線の太さのこの倍
export const DRAW_TYPES = new Set(["pen", "line", "arrow", "rect", "ellipse", "text"]);

// 記録の並び。clear は「ここまでを消した」印。undo/redo は印も1回分として数える
export function createHistory() {
  const ops = [];
  let redoStack = [];
  const visible = () => {
    let from = 0;
    for (let i = ops.length - 1; i >= 0; i--) {
      if (ops[i].type === "clear") {
        from = i + 1;
        break;
      }
    }
    return ops.slice(from);
  };
  return {
    push(op) {
      ops.push(op);
      redoStack = [];
    },
    undo() {
      const op = ops.pop();
      if (op) redoStack.push(op);
      return !!op;
    },
    redo() {
      const op = redoStack.pop();
      if (op) ops.push(op);
      return !!op;
    },
    clear() {
      if (visible().length === 0) return false;
      ops.push({ type: "clear" });
      redoStack = [];
      return true;
    },
    visible,
    hasInk: () => visible().some(op => DRAW_TYPES.has(op.type)),
    canUndo: () => ops.length > 0,
    canRedo: () => redoStack.length > 0,
  };
}

export function normRect(x1, y1, x2, y2) {
  return { x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1), h: Math.abs(y2 - y1) };
}

// 矢印の先の2本の線の端（先端 x2,y2 から、線の向きの後ろへ開く）
export function arrowHead(x1, y1, x2, y2, width) {
  const angle = Math.atan2(y2 - y1, x2 - x1);
  const len = Math.max(14, width * 4);
  const spread = Math.PI / 7;
  return [
    [x2 - len * Math.cos(angle - spread), y2 - len * Math.sin(angle - spread)],
    [x2 - len * Math.cos(angle + spread), y2 - len * Math.sin(angle + spread)],
  ];
}

// 手書きの点を間引く。最初と最後は必ず残す
export function thin(points, minDist = 2) {
  if (points.length <= 1) return points.slice();
  const out = [points[0]];
  for (let i = 1; i < points.length - 1; i++) {
    const [px, py] = out[out.length - 1];
    if (Math.hypot(points[i][0] - px, points[i][1] - py) >= minDist) out.push(points[i]);
  }
  const last = points[points.length - 1];
  const [lx, ly] = out[out.length - 1];
  if (last[0] !== lx || last[1] !== ly) out.push(last);
  return out;
}
```

- [ ] **Step 4: 通ることを確かめる**

Run: `node --test tests/js/*.test.mjs`
Expected: 全部 PASS（既存 55 + 新規）

---

### Task 5: 画面（ボタン・描画画面・設定欄・組み込み）

**Files:**
- Modify: `static/board.html`（ボタン・描画画面・設定欄）
- Modify: `static/board.css`
- Create: `static/js/whiteboard.js`
- Modify: `static/js/board.js`（組み込み）、`static/js/standby.js`（スリープ抑止）、`static/js/admin-settings.js`（設定欄）
- Modify: `tests/test_static.py`（配信と配線の確認）

**Interfaces:**
- Consumes: Task 3 の3つの入口、Task 4 の部品、`links.js` の `createStayTimer`、`picker.js` の `pickOption` / `inputText` / `confirmBox` / `alertBox`、`api()`。
- Produces: `whiteboard.js` の `initWhiteboard({ onOpen, onClose })`、`setWhiteboardIdle(seconds)`、`isWhiteboardOpen()`、`closeWhiteboard(resume = true)`。`standby.js` の `setBusyCheck(fn)`。

- [ ] **Step 1: 失敗するテストを書く** — `tests/test_static.py` の末尾に追加

```python
def test_whiteboard_is_served_and_wired(tmp_path):
    c = create_app(tmp_path).test_client()
    for path in ["/js/whiteboard.js", "/js/whiteboard-core.mjs"]:
        assert c.get(path).status_code == 200, path
    html = c.get("/").get_data(as_text=True)
    for ident in ["wb-open", "whiteboard", "wb-bar", "wb-stage", "wb-bg-canvas", "wb-ink", "wb-preview", "wb-text", "wb-undo", "wb-redo", "wb-clear", "wb-bg", "wb-save", "wb-close", "wb-warn", "wb-continue", "wb-msg", "wb-save-folder", "wb-pdf-folder", "wb-idle-seconds"]:
        assert f'id="{ident}"' in html, ident
    board = c.get("/js/board.js").get_data(as_text=True)
    assert "initWhiteboard" in board and "setWhiteboardIdle(state.settings.whiteboard_idle_seconds)" in board
    assert "setBusyCheck(isWhiteboardOpen)" in board
    assert "setBusyCheck" in c.get("/js/standby.js").get_data(as_text=True)
    admin = c.get("/js/admin-settings.js").get_data(as_text=True)
    for ident in ["wb-save-folder", "wb-pdf-folder", "wb-idle-seconds", "whiteboard_idle_seconds"]:
        assert ident in admin, ident
```

Run: `.venv/Scripts/python.exe -m pytest tests/test_static.py -q`
Expected: 新しい試験が FAIL（404）

- [ ] **Step 2: `static/board.html` を直す**

(a) `<div id="doc-buttons"></div>` の次の行に追加:

```html
        <div id="wb-buttons"><button id="wb-open" class="doc-btn wb-open" type="button"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg><span class="doc-label">ホワイトボード</span></button></div>
```

(b) `<div id="link-view" ...>` の `</div>`（iframe の次の閉じ）の後ろ、`<div id="settings" ...>` の前に追加:

```html
  <div id="whiteboard" class="overlay" hidden>
    <div id="wb-bar">
      <div class="wb-group">
        <button class="wb-btn wb-tool" data-tool="pen" type="button">ペン</button>
        <button class="wb-btn wb-tool" data-tool="line" type="button">直線</button>
        <button class="wb-btn wb-tool" data-tool="arrow" type="button">矢印</button>
        <button class="wb-btn wb-tool" data-tool="rect" type="button">四角</button>
        <button class="wb-btn wb-tool" data-tool="ellipse" type="button">丸</button>
        <button class="wb-btn wb-tool" data-tool="text" type="button">文字</button>
        <button class="wb-btn wb-tool" data-tool="eraser" type="button">消しゴム</button>
      </div>
      <div class="wb-group" id="wb-colors"></div>
      <div class="wb-group">
        <button class="wb-btn wb-width" data-width="0" type="button" aria-label="細い"><span class="wb-dot" style="--d:.35rem"></span></button>
        <button class="wb-btn wb-width" data-width="1" type="button" aria-label="ふつう"><span class="wb-dot" style="--d:.8rem"></span></button>
        <button class="wb-btn wb-width" data-width="2" type="button" aria-label="太い"><span class="wb-dot" style="--d:1.4rem"></span></button>
      </div>
      <div class="wb-group">
        <button id="wb-undo" class="wb-btn" type="button">元に戻す</button>
        <button id="wb-redo" class="wb-btn" type="button">やり直し</button>
        <button id="wb-clear" class="wb-btn" type="button">全部消す</button>
      </div>
      <div class="wb-group">
        <button id="wb-bg" class="wb-btn" type="button">背景PDF</button>
        <button id="wb-save" class="wb-btn wb-primary" type="button">保存</button>
        <button id="wb-close" class="wb-btn" type="button">閉じる</button>
      </div>
      <div id="wb-warn" class="link-warn" hidden>
        <span>あと30秒で戻ります</span>
        <button id="wb-continue" class="opt" type="button">続ける</button>
      </div>
      <div id="wb-msg" class="status-line" role="alert" hidden></div>
    </div>
    <div id="wb-stage">
      <canvas id="wb-bg-canvas"></canvas>
      <canvas id="wb-ink"></canvas>
      <canvas id="wb-preview"></canvas>
      <input id="wb-text" type="text" maxlength="100" autocomplete="off" hidden>
    </div>
  </div>

```

(c) 設定欄: `<p class="setting-title">リンクボタン（最大2つ）</p>` の直前に追加:

```html
        <p class="setting-title">ホワイトボード</p>
        <div class="field-line">
          <label for="wb-save-folder">保存フォルダ</label>
          <input id="wb-save-folder" class="f-folder" type="text" maxlength="260" placeholder="空欄=whiteboardフォルダ">
        </div>
        <div class="field-line">
          <label for="wb-pdf-folder">背景用のPDFフォルダ</label>
          <input id="wb-pdf-folder" class="f-folder" type="text" maxlength="260" placeholder="空欄=whiteboard_pdfsフォルダ">
        </div>
        <div class="field-line">
          <label for="wb-idle-seconds">操作なしで掲示板に戻る（秒）</label>
          <input id="wb-idle-seconds" type="number" min="30" max="3600" step="1" inputmode="numeric">
          <span>30〜3600。戻る前に、描いてあれば自動で保存します</span>
        </div>
        <p class="hint">保存フォルダは、このアプリを動かしているPC（サーバー）から見た場所で書きます。//server/share/ホワイトボード のようなネットワークの場所も使えます（ドライブ文字は避けてください）。PDFは日付と時刻の名前で保存されます。</p>
```

- [ ] **Step 3: `static/board.css` に追加**（`#link-frame { ... }` の行の次あたり）

```css
#wb-buttons { display: flex; margin-top: .6rem; flex: none; }
#wb-buttons .wb-open { flex: 1; color: var(--chip-on-text); background: var(--card); border: 2px solid var(--chip-on-border); }
#picker { z-index: 30; }
#whiteboard { flex-direction: column; align-items: stretch; justify-content: flex-start; z-index: 25; background: #FFFFFF; user-select: none; -webkit-user-select: none; }
#wb-bar { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem 1.2rem; flex: none; padding: .6rem 1rem; background: var(--card); border-bottom: 2px solid var(--border); }
.wb-group { display: flex; align-items: center; gap: .4rem; }
.wb-btn { min-width: 4.5rem; min-height: 3.6rem; padding: 0 .9rem; font-size: 1.4rem; font-weight: 700; color: var(--text); background: var(--btn-bg); border: 2px solid var(--border); border-radius: .6rem; }
.wb-btn.current { color: var(--chip-on-text); background: var(--chip-on-bg); border-color: var(--chip-on-border); }
.wb-btn:disabled { opacity: .4; }
.wb-primary { color: var(--accent-text); background: var(--accent); border-color: var(--accent); }
.wb-dot { display: block; width: var(--d); height: var(--d); background: currentColor; border-radius: 50%; margin: 0 auto; }
.wb-color { width: 3.4rem; height: 3.4rem; padding: 0; border: 3px solid var(--border); border-radius: 50%; }
.wb-color.current { border-color: var(--text); box-shadow: 0 0 0 3px var(--chip-on-border); }
#wb-bar .link-warn { margin: 0; }
#wb-bar .status-line { margin: 0; }
#wb-stage { position: relative; flex: 1; min-height: 0; overflow: hidden; background: #FFFFFF; touch-action: none; }
#wb-stage canvas { position: absolute; left: 0; top: 0; touch-action: none; }
#wb-text { position: absolute; z-index: 2; min-width: 12rem; padding: 0; margin: 0; line-height: 1.2; font-family: "Meiryo", "メイリオ", "Yu Gothic UI", sans-serif; background: rgba(255, 255, 255, .85); border: 1px dashed #2563EB; outline: none; user-select: text; -webkit-user-select: text; }
#wb-text[hidden], #wb-warn[hidden], #wb-msg[hidden] { display: none; }
```

- [ ] **Step 4: `static/js/standby.js` を直す**

`let cfg = ...` の行の前に追加:

```js
let extraBusy = () => false; // ホワイトボードなど、links.js 以外で「操作中と見なす」画面があるとき
export function setBusyCheck(fn) {
  extraBusy = fn;
}
```

`if (isLinkOpen()) {` を `if (isLinkOpen() || extraBusy()) {` に変え、直前のコメントの次に1行足す: `// ホワイトボードも同じ（描いている間は、スリープに入らない）`。

- [ ] **Step 5: `static/js/whiteboard.js` を作る**

```js
import * as pdfjsLib from "/pdfjs/pdf.mjs";
import { api } from "./api.js";
import { pickOption, inputText, confirmBox, alertBox } from "./picker.js";
import { createStayTimer } from "./links.js";
import { COLORS, WIDTHS, TEXT_SIZES, ERASER_SCALE, createHistory, normRect, arrowHead, thin } from "./whiteboard-core.mjs";

pdfjsLib.GlobalWorkerOptions.workerSrc = "/pdfjs/pdf.worker.mjs";

const $ = id => document.getElementById(id);
const MAX_RATIO = 2; // 描画用の細かさ（画面の細かさの上限）
const MAX_PIXELS = 16e6;
const JPEG_QUALITY = 0.92;
const SAVE_TIMEOUT_MS = 60000;
const LOAD_TIMEOUT_MS = 20000;
const MAX_PAGE_BUTTONS = 40;
const NO_BACKGROUND = "__none__";
const FONT = '"Meiryo", "メイリオ", "Yu Gothic UI", sans-serif';

let idleSeconds = 180;
let isOpen = false;
let busy = false; // 保存中
let hooks = { onOpen() {}, onClose() {} };
let tool = "pen";
let color = COLORS[0];
let widthIdx = 1;
let history = createHistory();
let saved = true; // 開いた直後、または最後の保存のあとに描き足していない
let bgDoc = null;
let bgPage = null;
let bgName = "";
let bgTask = null;
let ratio = 1;
let cssW = 1;
let cssH = 1;
let drag = null; // 描いている最中の指（1本だけ見る）: { id, start, last, points }
let textAt = null; // 文字入力中の場所: { x, y, size, color }
let lastActivity = 0;

const stage = $("wb-stage");
const bgCanvas = $("wb-bg-canvas");
const ink = $("wb-ink");
const preview = $("wb-preview");

export function isWhiteboardOpen() {
  return isOpen;
}

export function setWhiteboardIdle(seconds) {
  const n = Number(seconds);
  if (Number.isFinite(n) && n >= 30) idleSeconds = n;
}

// ---- 操作なしで戻る（30秒前に警告 → 描いてあれば自動保存して戻る） ----
const timer = createStayTimer({
  onWarn: () => {
    $("wb-warn").hidden = false;
  },
  onExpire: autoReturn,
});

async function autoReturn() {
  if (!isOpen) return;
  if (busy) {
    timer.start(idleSeconds);
    return;
  }
  commitText();
  if (history.hasInk() && !saved) {
    try {
      await doSave(true);
    } catch (e) {
      // 保存できないときは戻らない（描いたものを失わない）
      $("wb-warn").hidden = true;
      say("自動保存できませんでした: " + e.message + "。保存先を確かめてください", true);
      timer.start(idleSeconds);
      return;
    }
  }
  closeWhiteboard();
}

function onActivity() {
  if (!isOpen) return;
  lastActivity = Date.now();
  $("wb-warn").hidden = true;
  timer.start(idleSeconds);
}

// ---- 画面の下の知らせ ----
function say(text, error = false) {
  const box = $("wb-msg");
  box.textContent = text ? (error ? "⚠ " : "") + text : "";
  box.classList.toggle("error", !!text && error);
  box.hidden = !text;
}

// ---- 描画 ----
function ctxOf(canvas) {
  const x = canvas.getContext("2d");
  x.setTransform(ratio, 0, 0, ratio, 0, 0);
  return x;
}

function strokePath(ctx, pts) {
  if (pts.length === 0) return;
  if (pts.length === 1) {
    ctx.beginPath();
    ctx.arc(pts[0][0], pts[0][1], ctx.lineWidth / 2, 0, Math.PI * 2);
    ctx.fill();
    return;
  }
  ctx.beginPath();
  ctx.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length - 1; i++) {
    const mx = (pts[i][0] + pts[i + 1][0]) / 2;
    const my = (pts[i][1] + pts[i + 1][1]) / 2;
    ctx.quadraticCurveTo(pts[i][0], pts[i][1], mx, my);
  }
  const last = pts[pts.length - 1];
  ctx.lineTo(last[0], last[1]);
  ctx.stroke();
}

function drawOp(ctx, op) {
  if (op.type === "clear") return;
  ctx.save();
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.strokeStyle = op.color;
  ctx.fillStyle = op.color;
  ctx.lineWidth = op.width;
  switch (op.type) {
    case "pen":
      strokePath(ctx, op.points);
      break;
    case "erase":
      ctx.globalCompositeOperation = "destination-out"; // 描いた層だけを消す（背景のPDFは別の層）
      ctx.lineWidth = op.width * ERASER_SCALE;
      strokePath(ctx, op.points);
      break;
    case "line":
    case "arrow":
      ctx.beginPath();
      ctx.moveTo(op.x1, op.y1);
      ctx.lineTo(op.x2, op.y2);
      if (op.type === "arrow") {
        for (const [hx, hy] of arrowHead(op.x1, op.y1, op.x2, op.y2, op.width)) {
          ctx.moveTo(op.x2, op.y2);
          ctx.lineTo(hx, hy);
        }
      }
      ctx.stroke();
      break;
    case "rect":
      ctx.strokeRect(op.x, op.y, op.w, op.h);
      break;
    case "ellipse":
      ctx.beginPath();
      ctx.ellipse(op.x + op.w / 2, op.y + op.h / 2, Math.max(op.w / 2, 0.5), Math.max(op.h / 2, 0.5), 0, 0, Math.PI * 2);
      ctx.stroke();
      break;
    case "text":
      ctx.font = `${op.size}px ${FONT}`;
      ctx.textBaseline = "top";
      ctx.fillText(op.text, op.x, op.y);
      break;
  }
  ctx.restore();
}

function replay() {
  const ctx = ctxOf(ink);
  ctx.clearRect(0, 0, cssW, cssH);
  for (const op of history.visible()) drawOp(ctx, op);
}

function sizeCanvases() {
  cssW = Math.max(1, Math.floor(stage.clientWidth));
  cssH = Math.max(1, Math.floor(stage.clientHeight));
  ratio = Math.min(window.devicePixelRatio || 1, MAX_RATIO, Math.sqrt(MAX_PIXELS / (cssW * cssH)));
  for (const c of [bgCanvas, ink, preview]) {
    c.width = Math.max(1, Math.floor(cssW * ratio));
    c.height = Math.max(1, Math.floor(cssH * ratio));
    c.style.width = cssW + "px";
    c.style.height = cssH + "px";
  }
}

async function renderBackground() {
  if (bgTask) {
    bgTask.cancel();
    bgTask = null;
  }
  const ctx = bgCanvas.getContext("2d");
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.fillStyle = "#FFFFFF";
  ctx.fillRect(0, 0, bgCanvas.width, bgCanvas.height);
  if (!bgPage) return;
  const base = bgPage.getViewport({ scale: 1 });
  const fit = Math.min(bgCanvas.width / base.width, bgCanvas.height / base.height);
  const vp = bgPage.getViewport({ scale: fit });
  const ox = (bgCanvas.width - vp.width) / 2;
  const oy = (bgCanvas.height - vp.height) / 2;
  const task = bgPage.render({ canvasContext: ctx, viewport: vp, transform: [1, 0, 0, 1, ox, oy] });
  bgTask = task;
  try {
    await task.promise;
  } catch (e) {
    if (!(e && e.name === "RenderingCancelledException")) throw e;
  } finally {
    if (bgTask === task) bgTask = null;
  }
}

function relayout() {
  if (!isOpen) return;
  commitText();
  sizeCanvases();
  replay();
  renderBackground().catch(e => say("背景を表示できません", true));
}

// ---- 道具の選択 ----
function syncButtons() {
  for (const b of document.querySelectorAll(".wb-tool")) b.classList.toggle("current", b.dataset.tool === tool);
  for (const b of document.querySelectorAll(".wb-width")) b.classList.toggle("current", Number(b.dataset.width) === widthIdx);
  for (const b of document.querySelectorAll(".wb-color")) b.classList.toggle("current", b.dataset.color === color);
  $("wb-undo").disabled = !history.canUndo();
  $("wb-redo").disabled = !history.canRedo();
  $("wb-clear").disabled = history.visible().length === 0;
}

function record(op) {
  history.push(op);
  saved = false;
  syncButtons();
}

// ---- 文字 ----
function startText([x, y]) {
  commitText();
  const input = $("wb-text");
  const size = TEXT_SIZES[widthIdx];
  textAt = { x, y, size, color };
  input.style.left = x + "px";
  input.style.top = y + "px";
  input.style.fontSize = size + "px";
  input.style.color = color;
  input.value = "";
  input.hidden = false;
  setTimeout(() => input.focus(), 0);
}

function commitText() {
  const input = $("wb-text");
  if (input.hidden || !textAt) return;
  const at = textAt;
  const text = input.value.trim();
  textAt = null;
  input.hidden = true;
  if (!text) return;
  const op = { type: "text", color: at.color, size: at.size, x: at.x, y: at.y, text };
  record(op);
  drawOp(ctxOf(ink), op);
}

$("wb-text").addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.isComposing) {
    e.preventDefault();
    commitText();
  } else if (e.key === "Escape") {
    textAt = null;
    $("wb-text").hidden = true;
  }
});
$("wb-text").addEventListener("blur", commitText);

// ---- 指・ペンの動き ----
const pos = e => {
  const r = stage.getBoundingClientRect();
  return [e.clientX - r.left, e.clientY - r.top];
};

function currentOp() {
  const w = WIDTHS[widthIdx];
  const [x1, y1] = drag.start;
  const [x2, y2] = drag.last;
  switch (tool) {
    case "pen":
      return { type: "pen", color, width: w, points: thin(drag.points) };
    case "eraser":
      return { type: "erase", color, width: w, points: thin(drag.points) };
    case "line":
    case "arrow":
      return Math.hypot(x2 - x1, y2 - y1) < 3 ? null : { type: tool, color, width: w, x1, y1, x2, y2 };
    case "rect":
    case "ellipse": {
      const r = normRect(x1, y1, x2, y2);
      return r.w < 3 && r.h < 3 ? null : { type: tool, color, width: w, ...r };
    }
  }
  return null;
}

stage.addEventListener("pointerdown", e => {
  if (!isOpen || busy || drag) return; // 2本目の指・保存中は見ない
  if (e.pointerType === "mouse" && e.button !== 0) return;
  const p = pos(e);
  if (tool === "text") {
    e.preventDefault();
    startText(p);
    return;
  }
  commitText();
  stage.setPointerCapture(e.pointerId);
  drag = { id: e.pointerId, start: p, last: p, points: [p] };
  if (tool === "pen" || tool === "eraser") {
    drawOp(ctxOf(ink), { type: tool === "pen" ? "pen" : "erase", color, width: WIDTHS[widthIdx], points: [p] });
  }
});

stage.addEventListener("pointermove", e => {
  if (!drag || e.pointerId !== drag.id) return;
  if (Date.now() - lastActivity > 1000) onActivity(); // 長い1画の途中で「操作なし」にならないように
  const p = pos(e);
  drag.last = p;
  if (tool === "pen" || tool === "eraser") {
    const prev = drag.points[drag.points.length - 1];
    if (Math.hypot(p[0] - prev[0], p[1] - prev[1]) < 1.5) return;
    drag.points.push(p);
    drawOp(ctxOf(ink), { type: tool === "pen" ? "pen" : "erase", color, width: WIDTHS[widthIdx], points: drag.points.slice(-3) });
  } else {
    const ctx = ctxOf(preview);
    ctx.clearRect(0, 0, cssW, cssH);
    const op = currentOp();
    if (op) drawOp(ctx, op);
  }
});

function endDrag(e, commit) {
  if (!drag || e.pointerId !== drag.id) return;
  const op = commit ? currentOp() : null;
  drag = null;
  ctxOf(preview).clearRect(0, 0, cssW, cssH);
  if (op) record(op);
  replay(); // 画面を記録どおりに描き直す（途中の線の細かな差を消す）
}
stage.addEventListener("pointerup", e => endDrag(e, true));
stage.addEventListener("pointercancel", e => endDrag(e, false));

// ---- 背景のPDF ----
async function loadPdf(name) {
  const task = pdfjsLib.getDocument({ url: `/api/whiteboard/pdf/${encodeURIComponent(name)}`, cMapUrl: "/pdfjs/cmaps/", cMapPacked: true });
  let tid;
  const timeout = new Promise((_, reject) => {
    tid = setTimeout(() => {
      task.destroy();
      reject(new Error("読み込みがタイムアウトしました"));
    }, LOAD_TIMEOUT_MS);
  });
  try {
    return await Promise.race([task.promise, timeout]);
  } finally {
    clearTimeout(tid);
  }
}

async function pickPage(count) {
  if (count <= 1) return 1;
  if (count <= MAX_PAGE_BUTTONS) {
    const v = await pickOption({
      title: `何ページ目を背景にしますか？（全${count}ページ）`,
      options: Array.from({ length: count }, (_, i) => ({ value: i + 1, label: `${i + 1}ページ` })),
      allowClear: false,
    });
    return v === undefined ? null : v;
  }
  const r = await inputText({ title: `何ページ目を背景にしますか？（1〜${count}）`, value: "1" });
  if (!r) return null;
  const n = Number(r.text);
  if (!Number.isInteger(n) || n < 1 || n > count) {
    await alertBox(`1〜${count} の数を入れてください`);
    return null;
  }
  return n;
}

function dropBackground() {
  if (bgTask) {
    bgTask.cancel();
    bgTask = null;
  }
  bgPage = null;
  bgName = "";
  if (bgDoc) {
    bgDoc.destroy();
    bgDoc = null;
  }
}

async function chooseBackground() {
  let names;
  try {
    names = await api("GET", "/api/whiteboard/pdfs");
  } catch (e) {
    say("背景PDFの一覧を読み込めません: " + e.message, true);
    return;
  }
  const options = [{ value: NO_BACKGROUND, label: "背景なし（白紙）" }, ...names.map(n => ({ value: n, label: n.replace(/\.pdf$/i, "") }))];
  const name = await pickOption({
    title: names.length ? "背景にするPDF" : "背景用のフォルダにPDFがありません",
    options,
    current: bgName || NO_BACKGROUND,
    allowClear: false,
  });
  if (name === undefined) return;
  if (name === NO_BACKGROUND) {
    dropBackground();
    await renderBackground();
    return;
  }
  say("読み込んでいます…");
  let doc;
  try {
    doc = await loadPdf(name);
    const pageNo = await pickPage(doc.numPages);
    if (pageNo === null) {
      doc.destroy();
      say("");
      return;
    }
    const page = await doc.getPage(pageNo);
    dropBackground();
    bgDoc = doc;
    bgPage = page;
    bgName = name;
    await renderBackground();
    say("");
  } catch (e) {
    if (doc) doc.destroy();
    say("PDFを読み込めません: " + e.message, true);
  }
}

// ---- 保存 ----
function compositeBase64() {
  const c = document.createElement("canvas");
  c.width = bgCanvas.width;
  c.height = bgCanvas.height;
  const x = c.getContext("2d");
  x.fillStyle = "#FFFFFF";
  x.fillRect(0, 0, c.width, c.height);
  x.drawImage(bgCanvas, 0, 0);
  x.drawImage(ink, 0, 0);
  return c.toDataURL("image/jpeg", JPEG_QUALITY).split(",")[1];
}

async function doSave(auto) {
  commitText();
  busy = true;
  $("wb-save").disabled = true;
  try {
    const r = await api("POST", "/api/whiteboard/save", { image: compositeBase64(), auto }, SAVE_TIMEOUT_MS);
    saved = true;
    return r;
  } finally {
    busy = false;
    $("wb-save").disabled = false;
  }
}

// ---- 開く・閉じる ----
function openWhiteboard() {
  if (isOpen) return;
  isOpen = true;
  hooks.onOpen();
  history = createHistory();
  saved = true;
  drag = null;
  textAt = null;
  $("wb-text").hidden = true;
  say("");
  $("wb-warn").hidden = true;
  $("whiteboard").hidden = false;
  sizeCanvases();
  replay();
  syncButtons();
  renderBackground().catch(() => {});
  lastActivity = Date.now();
  timer.start(idleSeconds);
}

export function closeWhiteboard(resume = true) {
  if (!isOpen) return;
  isOpen = false;
  timer.stop();
  drag = null;
  textAt = null;
  $("wb-text").hidden = true;
  $("wb-warn").hidden = true;
  $("whiteboard").hidden = true;
  dropBackground();
  history = createHistory();
  for (const c of [bgCanvas, ink, preview]) {
    c.width = 0;
    c.height = 0;
  }
  if (resume) hooks.onClose();
}

async function requestClose() {
  commitText();
  if (history.hasInk() && !saved) {
    const ok = await confirmBox("保存しないで閉じますか？ 描いた内容は消えます。", "閉じる");
    if (!ok) return;
  }
  closeWhiteboard();
}

export function initWhiteboard({ onOpen, onClose }) {
  hooks = { onOpen, onClose };
  const box = $("wb-colors");
  for (const c of COLORS) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "wb-color";
    b.dataset.color = c;
    b.style.background = c;
    b.setAttribute("aria-label", "色 " + c);
    b.addEventListener("click", () => {
      color = c;
      syncButtons();
    });
    box.appendChild(b);
  }
  for (const b of document.querySelectorAll(".wb-tool")) {
    b.addEventListener("click", () => {
      commitText();
      tool = b.dataset.tool;
      syncButtons();
    });
  }
  for (const b of document.querySelectorAll(".wb-width")) {
    b.addEventListener("click", () => {
      widthIdx = Number(b.dataset.width);
      syncButtons();
    });
  }
  $("wb-undo").addEventListener("click", () => {
    commitText();
    if (history.undo()) {
      saved = false;
      replay();
      syncButtons();
    }
  });
  $("wb-redo").addEventListener("click", () => {
    commitText();
    if (history.redo()) {
      saved = false;
      replay();
      syncButtons();
    }
  });
  $("wb-clear").addEventListener("click", () => {
    commitText();
    if (history.clear()) {
      saved = false;
      replay();
      syncButtons();
    }
  });
  $("wb-bg").addEventListener("click", chooseBackground);
  $("wb-save").addEventListener("click", async () => {
    if (busy) return;
    say("保存しています…");
    try {
      const r = await doSave(false);
      say(`保存しました（${r.name}）`);
    } catch (e) {
      say("保存できませんでした: " + e.message, true);
    }
  });
  $("wb-close").addEventListener("click", requestClose);
  $("wb-continue").addEventListener("click", onActivity);
  $("wb-open").addEventListener("click", openWhiteboard);
  for (const ev of ["pointerdown", "keydown", "touchstart"]) {
    document.addEventListener(ev, onActivity, { capture: true, passive: true });
  }
  let resizeTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(relayout, 200);
  });
}
```

- [ ] **Step 6: `static/js/board.js` を直す**

import に追加（`import { renderLinkButtons, ... }` の次）:

```js
import { initWhiteboard, isWhiteboardOpen, setWhiteboardIdle } from "./whiteboard.js";
```

`import { initStandby, setStandbyConfig } from "./standby.js";` を次に変える:

```js
import { initStandby, setStandbyConfig, setBusyCheck } from "./standby.js";
```

`renderLinkButtons(state.links);` の次に追加:

```js
  setWhiteboardIdle(state.settings.whiteboard_idle_seconds);
```

`initStandby(() => {` の直前に追加:

```js
// ホワイトボードを開いている間は、災害事例を止め、スリープに入らない（閉じて掲示板が見えてから災害事例を再開する）
initWhiteboard({
  onOpen: () => {
    closeDocuments();
    pauseAccident();
  },
  onClose: resumeAccident,
});
setBusyCheck(isWhiteboardOpen);
```

- [ ] **Step 7: `static/js/admin-settings.js` を直す**

`SECONDS_FIELDS` の次に追加:

```js
const WB_MIN_IDLE = 30;
const WB_MAX_IDLE = 3600;
```

`load()` の `$("holidays-file").value = ...` の次に追加:

```js
    $("wb-save-folder").value = s.whiteboard_save_folder || "";
    $("wb-pdf-folder").value = s.whiteboard_pdf_folder || "";
    $("wb-idle-seconds").value = s.whiteboard_idle_seconds ?? "";
```

`collect()` の `// テロップフォルダ・会社の休日ファイルが空欄なら...` の直前に追加:

```js
  const wbRaw = $("wb-idle-seconds").value.trim();
  const wbIdle = Number(wbRaw);
  if (wbRaw === "" || !Number.isInteger(wbIdle) || wbIdle < WB_MIN_IDLE || wbIdle > WB_MAX_IDLE) {
    return { error: `ホワイトボードの操作なし戻り（秒）は ${WB_MIN_IDLE}〜${WB_MAX_IDLE} の整数で入力してください`, focus: $("wb-idle-seconds") };
  }
```

`body` の `custom_holidays_file: ...,` の次に追加:

```js
      whiteboard_save_folder: $("wb-save-folder").value.trim(),
      whiteboard_pdf_folder: $("wb-pdf-folder").value.trim(),
      whiteboard_idle_seconds: wbIdle,
```

- [ ] **Step 8: 自動試験を通す**

Run: `.venv/Scripts/python.exe -m pytest -q` と `node --test tests/js/*.test.mjs`
Expected: 全部 PASS。`tests/test_admin_key.py` が設定欄の範囲 `html[html.index('id="settings"'):html.index('id="standby"')]` を調べているので、新しい入力欄が既存の検査（例: 入力欄の数や属性）に当たらないか確かめる。当たったら期待値だけを直す。

- [ ] **Step 9: 実際のブラウザで確かめる**（Edge ヘッドレス + manual-screenshots スキルの `scripts/cdp.py`）

確認用の場所は scratchpad の `wb-demo`（新規）。見本データは `tv4k-demo` の登録リストをコピーして使う。`config.json` は `{"whiteboard_save_folder": "<scratchpad>/wb-demo/out", "whiteboard_idle_seconds": 40, "standby": {"start":"03:00","end":"03:01"}}`。背景用フォルダに `tests/make_sample_pdfs.py` で作ったPDFを2〜3枚（1つは複数ページ）置く。サーバーは `mcp__terminal__run_in_terminal` で未使用のポート（例 5142）で起動する。

確かめること（1つずつ結果を書く。確かめられなかったものは「未検証」と書く）:
1. 1920×1080 で掲示板が崩れていない（`ホワイトボード` ボタンが出て、右の列があふれない）。`document.querySelector('main').scrollHeight` などを前後で比べ、足りなければボタンの高さ・余白を詰める。ライト/ダークの両方。
2. ボタンを押すと全画面の白い画面。道具バーが画面外に出ず、2行以内に収まる。
3. ペン・直線・矢印・四角・丸・消しゴムを `Input.dispatchMouseEvent` で操作して描ける。**タッチ**（`Emulation.setTouchEmulationEnabled` + `Input.dispatchTouchEvent`）でも、ペンが描ける。2本指を同時に置いても、描きかけの線が壊れない。
4. 文字: 押して入力 → Enter で出る。入力中に別の場所を押すと、前の文字が確定して新しい入力窓が開く。
5. 元に戻す・やり直し・全部消す→元に戻す。消しゴムで背景PDFが消えない。
6. 背景PDF: 一覧に出る→複数ページのPDFは、ページ選択が出る→選んだページが背景になる。「背景なし」に戻せる。
7. 保存: 保存フォルダに `日付_時刻.pdf` ができ、Edge で開いて見た目が画面と同じ（カラー）。同じ秒の2回目は `_2`。
8. 操作なし: 10秒後に「あと30秒で戻ります」が出て、触ると消える。40秒放置すると `…_自動保存.pdf` ができて掲示板に戻る。白紙のときは保存せず戻る。保存済みで放置したときも二重に保存しない。
9. 保存先が書けないとき（保存フォルダの場所に同名のファイルを置く）: 手動保存は赤字のエラーで描画が残る。自動保存は戻らず、描画が残る。
10. 歯車の設定に3項目が出て、保存→再読み込みで値が残る。範囲外の秒数は赤字で止まる。
11. ホワイトボードを開いている間、スリープ時間帯でもスリープ画面に入らない（`standby` を一時的に今の時刻にして確かめる）。

終わったらサーバーのターミナルタブを閉じる（`stop_terminal_tab` の `close:true`）。scratchpad の確認用フォルダの削除は、対象と理由を言って承認を取る。

---

### Task 6: 説明書と最後の全体確認

**Files:**
- Modify: `README.md`、`docs/manual/取扱説明書.md`

- [ ] **Step 1:** `README.md` の機能一覧に「ホワイトボード」（描画・背景PDF・PDF保存・自動保存）を1項目足し、設定の説明に3項目を足す。`docs/manual/取扱説明書.md` に、使い方（ボタン→道具→保存→閉じる）、背景PDFの置き場所、保存先（サーバーから見た場所・ネットワークも可・ドライブ文字は避ける）、操作なし戻りと自動保存を、非エンジニア向けの言葉で書く。既存の節の書き方・見出しの深さに合わせる。画面写真と説明書PDFの作り直しは v0.3.0 の公開時にまとめて行うので、ここでは触らない（説明書に「写真は公開時に更新」と書き足さない）。

- [ ] **Step 2: 全体の確認**

Run: `.venv/Scripts/python.exe -m pytest -q` と `node --test tests/js/*.test.mjs`
Expected: 全部 PASS。`tests/test_line_endings.py`（LF）も通ること。

- [ ] **Step 3: 報告**（完了／未完了／要確認を分けて書く）
- 完了: 各タスクと、Task 5 の確認項目ごとの結果。
- 未検証: 実物のタッチパネルでの操作、実際のネットワーク共有への書き込み、画面の文字入力でWindowsのタッチキーボードが出るか。
- 残り: v0.3.0 の公開（版番号・説明書の写真とPDF・Release）は別の依頼で行う。
- ファイルが1000行を超えたものがあれば、分割の提案を添える（承認なしに分割しない）。
