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


def _settings_html(tmp_path):
    html = create_app(tmp_path).test_client().get("/").get_data(as_text=True)
    return html[html.index('id="settings"'):html.index('id="standby"')]


def test_sleep_and_timing_inputs_are_in_the_shared_section(tmp_path):
    settings = _settings_html(tmp_path)
    shared = settings[settings.index("全端末共通"):]
    assert "スリープ・時間" in shared
    assert shared.index("スリープ・時間") < shared.index('id="sleep-start"') < shared.index('id="settings-save"')
    # 時刻は <input type="time">（24時間の HH:MM）。ブラウザが対応しないときは文字欄として動く
    assert 'id="sleep-start" class="f-time" type="time"' in shared
    assert 'id="sleep-end" class="f-time" type="time"' in shared
    for label in ["スリープ開始", "スリープ終了", "操作なしでスリープに戻る（秒）", "災害事例の表示秒数", "文書の操作なし戻り（秒）", "編集の自動終了（秒）"]:
        assert label in shared, label
    for needle in ['id="sleep-wake-idle"', 'id="accident-seconds"', 'id="doc-idle-seconds"', 'id="edit-lock-seconds"']:
        assert needle in shared, needle
    # 既存の「保存して適用」ボタンで保存する（専用ボタンは作らない）
    assert settings.count('id="settings-save"') == 1 and "settings-save-sleep" not in settings


def test_holidays_file_row_and_hint(tmp_path):
    shared = _settings_html(tmp_path)
    assert "会社の休日ファイル" in shared
    row = shared[shared.index('id="holidays-file"') - 80:shared.index('id="holidays-file"') + 200]
    assert 'maxlength="260"' in row and 'placeholder="data/custom_holidays.csv"' in row
    assert "equipment-inspection と共通にするには、そちらの data/custom_holidays.csv のパスを入れます（形式は同じ）" in shared


def test_ui_says_sleep_not_standby(tmp_path):
    c = create_app(tmp_path).test_client()
    assert "待機" not in c.get("/").get_data(as_text=True)
    for path in ["/board.css", "/js/board.js", "/js/standby.js", "/js/admin-settings.js", "/js/timeutil.mjs"]:
        assert "待機" not in c.get(path).get_data(as_text=True), path


def test_admin_settings_js_sends_and_reads_the_new_fields(tmp_path):
    js = create_app(tmp_path).test_client().get("/js/admin-settings.js").get_data(as_text=True)
    for needle in ["standby", "wake_idle_seconds", "accident_seconds", "idle_return_seconds", "edit_lock_seconds", "custom_holidays_file",
                   "sleep-start", "sleep-end", "holidays-file", "normalizeHHMM", "secondsValue"]:
        assert needle in js, needle


def test_front_end_applies_new_values_on_every_refresh(tmp_path):
    c = create_app(tmp_path).test_client()
    board = c.get("/js/board.js").get_data(as_text=True)
    for needle in ["setSeconds(state.settings.accident_seconds)", "setLockSeconds(state.settings.edit_lock_seconds)",
                   "setStandbyConfig(state.settings.standby)", "state.settings.documents_idle_seconds"]:
        assert needle in board, needle
    standby = c.get("/js/standby.js").get_data(as_text=True)
    assert '"08:00"' in standby and '"07:30"' not in standby
    # 表示中のスライドにも新しい秒数が効く（長い秒数から短くしても、古い秒数を待たない）
    accident = c.get("/js/accident.js").get_data(as_text=True)
    assert "export function setSeconds" in accident and "advancing" in accident


def test_empty_cells_show_a_bar_only_in_the_holiday_table(tmp_path):
    c = create_app(tmp_path).test_client()
    js = c.get("/js/board.js").get_data(as_text=True)
    schedule = js[js.index("function renderSchedule"):js.index("function renderHolidays")]
    holidays = js[js.index("function renderHolidays"):js.index("function renderGenres")]
    assert "orDash" not in schedule and "formatRangeOrDash" not in schedule and "holidayTd" not in schedule
    assert "formatRange(r.start_time, r.end_time)" in schedule
    assert holidays.count("holidayTd(") == 3 and "formatRangeOrDash(r.start_time, r.end_time)" in holidays
    assert "formatRange(r.start_time" not in holidays.replace("formatRangeOrDash(", "")
    assert "td(r.construction" not in holidays and "td(r.person" not in holidays and "td(r.work" not in holidays
    assert 'import { formatRange, formatRangeOrDash, orDash, contactText, visibleHolidayRows } from "./timeutil.mjs"' in js
    css = c.get("/board.css").get_data(as_text=True)
    assert "td.dash { color: var(--muted); }" in css


def test_holiday_table_hides_dash_only_rows_when_the_day_has_an_entry(tmp_path):
    c = create_app(tmp_path).test_client()
    js = c.get("/js/board.js").get_data(as_text=True)
    assert "visibleHolidayRows(state.holiday_rows)" in js
    # 「―」だけの行が減った分の、空き行の数え方も、見えている行で数える
    assert "holidayRows.length" in js and "state.holiday_rows.length" not in js
    assert "export function visibleHolidayRows" in c.get("/js/timeutil.mjs").get_data(as_text=True)
