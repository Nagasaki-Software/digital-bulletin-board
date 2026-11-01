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


def test_natural_key_does_not_crash_on_non_decimal_digits():
    names = ["事例1②", "事例²", "事例10", "事例2", "③"]
    assert len(sorted(names, key=acc.natural_key)) == 5
