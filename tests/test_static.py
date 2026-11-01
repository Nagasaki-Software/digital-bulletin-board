from app import create_app


def test_index_and_assets_are_served(tmp_path):
    c = create_app(tmp_path).test_client()
    r = c.get("/")
    assert r.status_code == 200
    assert "デジタル掲示板" in r.get_data(as_text=True)
    for path in ["/board.css", "/js/board.js", "/js/api.js", "/js/picker.js", "/js/timeutil.mjs", "/js/theme.js"]:
        assert c.get(path).status_code == 200, path
    assert "javascript" in c.get("/js/timeutil.mjs").content_type


def test_pdfjs_and_accident_module_are_served(tmp_path):
    c = create_app(tmp_path).test_client()
    for path in ["/js/accident.js", "/pdfjs/pdf.mjs", "/pdfjs/pdf.worker.mjs", "/pdfjs/LICENSE"]:
        assert c.get(path).status_code == 200, path
    assert "javascript" in c.get("/pdfjs/pdf.mjs").content_type
    assert "javascript" in c.get("/pdfjs/pdf.worker.mjs").content_type
    assert "accident.js" in c.get("/js/board.js").get_data(as_text=True)


def test_edit_button_default_is_wired_from_server_setting(tmp_path):
    c = create_app(tmp_path).test_client()
    board = c.get("/js/board.js").get_data(as_text=True)
    lock = c.get("/js/lock.js").get_data(as_text=True)
    assert "setDefaultEditButton(state.settings.default_edit_button)" in board
    assert "resolveEditMode" in lock
    assert "AbortSignal" in c.get("/js/api.js").get_data(as_text=True)


def test_construction_column_is_wired_in_both_tables(tmp_path):
    c = create_app(tmp_path).test_client()
    html = c.get("/").get_data(as_text=True)
    schedule = html[html.index('id="schedule"'):html.index('id="holidays"')]
    holidays = html[html.index('id="holidays"'):html.index('id="btn-add-holiday"')]
    # 本日の作業予定: 工事件名が一番左。休日出勤予定: 日付 → 工事件名 → 氏名・会社名の順
    assert schedule.index('c-constr') < schedule.index('c-company') < schedule.index('c-act')
    assert holidays.index('c-date') < holidays.index('c-constr') < holidays.index('c-person')
    assert schedule.count("工事件名") == 1 and holidays.count("工事件名") == 1
    assert "工事内容" not in html
    js = c.get("/js/board.js").get_data(as_text=True)
    assert 'editSchedule(r, "construction")' in js and 'editHoliday(r, "construction")' in js
    assert "state.masters.constructions" in js or "m.constructions" in js
