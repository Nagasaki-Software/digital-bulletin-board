import telop


def folder(tmp_path):
    d = tmp_path / "telop"
    d.mkdir()
    return d


def test_item_count_is_capped_across_files(tmp_path):
    d = folder(tmp_path)
    (d / "a.txt").write_text("\n".join(f"A{i}" for i in range(150)), encoding="utf-8")
    (d / "b.txt").write_text("\n".join(f"B{i}" for i in range(150)), encoding="utf-8")
    items = telop.read_items(d)
    assert len(items) == telop.MAX_ITEMS == 200
    assert items[0] == "A0" and items[149] == "A149" and items[150] == "B0" and items[-1] == "B49"


def test_exactly_at_the_cap_is_kept(tmp_path):
    d = folder(tmp_path)
    (d / "a.txt").write_text("\n".join(f"x{i}" for i in range(200)), encoding="utf-8")
    assert len(telop.read_items(d)) == 200


def test_long_item_is_truncated_to_500_chars(tmp_path):
    d = folder(tmp_path)
    (d / "a.txt").write_text("あ" * 501 + "\n" + "い" * 500 + "\n短い", encoding="utf-8")
    items = telop.read_items(d)
    assert items == ["あ" * 500, "い" * 500, "短い"]
    assert telop.MAX_CHARS == 500


def test_file_over_1mb_is_ignored(tmp_path):
    d = folder(tmp_path)
    big = d / "big.txt"
    big.write_bytes(b"x" * (1024 * 1024 + 1))
    (d / "ok.txt").write_text("読める", encoding="utf-8")
    assert telop.read_items(d) == ["読める"]
    big.write_bytes(b"y" * 1024 * 1024)  # ちょうど1MBは読む（1行・500文字に切られる）
    assert telop.read_items(d) == ["y" * 500, "読める"]


def test_utf16_with_bom_is_decoded(tmp_path):
    d = folder(tmp_path)
    (d / "le.txt").write_bytes(b"\xff\xfe" + "リトルエンディアン\r\n二行目".encode("utf-16-le"))
    (d / "be.txt").write_bytes(b"\xfe\xff" + "ビッグ\n".encode("utf-16-be"))
    (d / "sjis.txt").write_bytes("シフトJIS".encode("cp932"))
    assert telop.read_items(d) == ["ビッグ", "リトルエンディアン", "二行目", "シフトJIS"]


def test_utf16_via_api_and_signature_still_work(tmp_path):
    from app import create_app

    c = create_app(tmp_path).test_client()
    (tmp_path / "telop" / "u16.txt").write_bytes("お知らせ\n".encode("utf-16"))  # Python の utf-16 は BOM を付ける
    assert c.get("/api/telop").get_json() == {"items": ["お知らせ"]}


def test_broken_utf16_bom_file_does_not_crash(tmp_path):
    d = folder(tmp_path)
    (d / "bad.txt").write_bytes(b"\xff\xfe\x00")  # 奇数バイトの UTF-16
    assert isinstance(telop.read_items(d), list)
