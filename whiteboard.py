"""ホワイトボードの保存。標準ライブラリだけで、JPEG 画像を1枚1ページの PDF に包んで保存先に書く。"""
import base64
import binascii
import os
from datetime import datetime
from pathlib import Path

MAX_IMAGE_BYTES = 30 * 1024 * 1024
MAX_PAGES = 50
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


def jpeg_to_pdf(jpegs):
    """JPEG（1枚の bytes、または bytes のリスト）を、1枚1ページの PDF にする。"""
    if isinstance(jpegs, (bytes, bytearray)):
        jpegs = [jpegs]
    if not jpegs:
        raise ImageError("画像がありません")
    if len(jpegs) > MAX_PAGES:
        raise ImageError(f"ページが多すぎます（{MAX_PAGES}ページまで）")
    objs = [b"", b""]  # 1: カタログ、2: ページ一覧（あとで入れる）
    kids = []
    for jpeg in jpegs:
        w, h, comps = jpeg_info(jpeg)
        if comps not in (1, 3):
            raise ImageError(f"対応していない画像です（色の数 {comps}）")
        space = b"/DeviceRGB" if comps == 3 else b"/DeviceGray"
        page_h = PAGE_WIDTH_PT * h / w
        box = b"[0 0 %.2f %.2f]" % (PAGE_WIDTH_PT, page_h)
        content = b"q %.2f 0 0 %.2f 0 0 cm /Im0 Do Q" % (PAGE_WIDTH_PT, page_h)
        page_no = len(objs) + 1
        kids.append(b"%d 0 R" % page_no)
        objs += [
            b"<< /Type /Page /Parent 2 0 R /MediaBox " + box + b" /Resources << /XObject << /Im0 %d 0 R >> >> /Contents %d 0 R >>" % (page_no + 1, page_no + 2),
            b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace %s /BitsPerComponent 8 /Filter /DCTDecode /Length %d >>\nstream\n"
            % (w, h, space, len(jpeg)) + jpeg + b"\nendstream",
            b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        ]
    objs[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objs[1] = b"<< /Type /Pages /Kids [" + b" ".join(kids) + b"] /Count %d >>" % len(kids)
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


def save_pdf(folder, jpegs, auto=False, now=None):
    """PDF にして folder に書き、書いたファイル名を返す。画像が使えなければ ImageError（フォルダには触れない）、
    書けなければ OSError。同じ名前があれば上書きせず _2, _3… を付ける。一時ファイルに書いてから名前を付け替える。"""
    pdf = jpeg_to_pdf(jpegs)
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


IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png")
MAX_SAVED_LIST = 60  # 「保存した内容」の一覧に出す件数（新しい順）


def _files(folder, suffixes):
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return [p.name for p in folder.iterdir() if p.is_file() and p.suffix.lower() in suffixes]


def list_images(folder):
    """背景に使える写真（jpg / jpeg / png）の名前。名前順。"""
    from accident import natural_key

    return sorted(_files(folder, IMAGE_SUFFIXES), key=natural_key)


def list_saved(folder):
    """保存先にある PDF の名前。日付時刻の名前なので、名前の降順＝新しい順。"""
    return sorted(_files(folder, (".pdf",)), reverse=True)[:MAX_SAVED_LIST]
