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


def test_jpeg_to_pdf_many_pages():
    pdf = wb.jpeg_to_pdf([fake_jpeg(), fake_jpeg(20, 10), fake_jpeg()])
    assert pdf.count(b"/Type /Page ") == 3 and b"/Count 3" in pdf
    assert pdf.count(b"/Filter /DCTDecode") == 3
