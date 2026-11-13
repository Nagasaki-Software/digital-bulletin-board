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
    assert holidays.count("holidayTd(") == 4 and "formatRangeOrDash(r.start_time, r.end_time)" in holidays
    assert "formatRange(r.start_time" not in holidays.replace("formatRangeOrDash(", "")
    assert "td(r.construction" not in holidays and "td(r.person" not in holidays and "td(r.work" not in holidays
    assert "td(r.leader" not in holidays
    assert 'import { formatRange, formatRangeOrDash, orDash, contactText, visibleHolidayRows, worksFor } from "./timeutil.mjs"' in js
    css = c.get("/board.css").get_data(as_text=True)
    assert "td.dash { color: var(--muted); }" in css


def test_holiday_table_hides_dash_only_rows_when_the_day_has_an_entry(tmp_path):
    c = create_app(tmp_path).test_client()
    js = c.get("/js/board.js").get_data(as_text=True)
    assert "visibleHolidayRows(state.holiday_rows)" in js
    # 「―」だけの行が減った分の、空き行の数え方も、見えている行で数える
    assert "holidayRows.length" in js and "state.holiday_rows.length" not in js
    assert "export function visibleHolidayRows" in c.get("/js/timeutil.mjs").get_data(as_text=True)


def test_clock_is_right_of_the_date_and_started_from_board_js(tmp_path):
    c = create_app(tmp_path).test_client()
    html = c.get("/").get_data(as_text=True)
    head = html[html.index('id="head-left"'):html.index('id="top-right"')]
    # 日付の右に時刻。日付は描画のたびに書き換わるので、時刻は別の部品に置く
    assert head.index('id="date-title"') < head.index('id="clock"')
    assert c.get("/js/clock.js").status_code == 200
    board = c.get("/js/board.js").get_data(as_text=True)
    assert 'import { initClock } from "./clock.js"' in board and "initClock();" in board
    # 時計はこのパソコンの時計を読むだけ。サーバーには問い合わせない
    clock = c.get("/js/clock.js").get_data(as_text=True)
    assert "fetch" not in clock and "api(" not in clock


def test_accident_frame_has_prev_next_buttons(tmp_path):
    c = create_app(tmp_path).test_client()
    html = c.get("/").get_data(as_text=True)
    frame = html[html.index('id="accident-frame"'):html.index("<h2>作業ジャンル</h2>")]
    # equipment-inspection の文書表示と同じ ❮ ❯。資料が無いときは出さない（最初は hidden）
    assert 'id="accident-prev"' in frame and "&#10094;" in frame and 'aria-label="前の資料"' in frame
    assert 'id="accident-next"' in frame and "&#10095;" in frame and 'aria-label="次の資料"' in frame
    assert frame.count("accident-nav") == 2 and frame.count("hidden>") >= 2
    js = c.get("/js/accident.js").get_data(as_text=True)
    assert 'prevBtn.addEventListener("click", () => step(-1))' in js
    assert 'nextBtn.addEventListener("click", () => step(1))' in js
    # ボタンを押したとき、枠のタップ判定（左右半分）でもう一度進めない
    assert 'e.target.closest(".accident-nav")' in js
    css = c.get("/board.css").get_data(as_text=True)
    assert ".accident-nav[hidden]" in css and "#accident-prev { left: 1rem; }" in css and "#accident-next { right: 1rem; }" in css


def test_accident_tag_and_counter_are_outside_the_frame(tmp_path):
    html = create_app(tmp_path).test_client().get("/").get_data(as_text=True)
    head = html[html.index('id="accident-head"'):html.index('id="accident-frame"')]
    frame = html[html.index('id="accident-frame"'):html.index("<h2>作業ジャンル</h2>")]
    # ジャンルのタグとページ番号は、資料に重ならないよう、枠の外（すぐ上）に置く
    assert 'id="accident-tag"' in head and 'id="accident-count"' in head
    assert 'id="accident-tag"' not in frame and 'id="accident-count"' not in frame
    assert 'id="accident-bar"' in frame


def test_empty_schedule_rows_add_a_row_and_open_the_picker(tmp_path):
    js = create_app(tmp_path).test_client().get("/js/board.js").get_data(as_text=True)
    assert "addRowAndEdit" in js and "FILLER_FIELDS" in js
    # 責任者の欄は、先に所属・会社名が要るので、会社の選択窓を開く（作業者数の欄はテンキー）
    assert '\nconst FILLER_FIELDS = ["construction", "company", "company", "workers", "work", "times"];' in js


def test_empty_holiday_rows_add_a_holiday_row_not_a_schedule_row(tmp_path):
    js = create_app(tmp_path).test_client().get("/js/board.js").get_data(as_text=True)
    # 休日出勤の空の行は、休日出勤の行を足す（前は本日の作業予定に足していた）。列は 日付・工事件名・所属・責任者・作業内容・就業予定
    assert '\nconst HOLIDAY_FILLER_FIELDS = ["date", "construction", "person", "person", "work", "times"];' in js
    assert "fillerRow(7, HOLIDAY_FILLER_FIELDS, addHolidayAndEdit)" in js
    add = js[js.index("async function addHolidayAndEdit"):]
    add = add[:add.index("\n}\n")]
    assert '"/api/holiday-rows"' in add and '"/api/schedule"' not in add
    assert "editHoliday(row, field)" in add and "editTimes(`/api/holiday-rows/${row.id}`, row)" in add


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


def test_free_text_limit_is_the_same_on_screen_and_server(tmp_path):
    import app as app_module

    js = create_app(tmp_path).test_client().get("/js/picker.js").get_data(as_text=True)
    assert f"export const FREE_TEXT_MAX = {app_module.FREE_TEXT_MAX};" in js
    assert "その他（手入力）" in js


def test_documents_can_be_shown_six_at_a_time(tmp_path):
    c = create_app(tmp_path).test_client()
    html = c.get("/").get_data(as_text=True)
    js = c.get("/js/documents.js").get_data(as_text=True)
    css = c.get("/board.css").get_data(as_text=True)
    for needle in ['id="doc-grid-view"', 'id="doc-grid"', 'id="grid-prev"', 'id="grid-next"', 'id="grid-range"']:
        assert needle in html, needle
    # 3×2 のマス・6枚ずつ・1ページ目だけ・マスを押すと1枚表示（戻ると 3×2）
    assert "grid-template-columns: 1fr 1fr 1fr; grid-template-rows: 1fr 1fr" in css
    assert "const GRID_SIZE = 6;" in js
    assert "6枚ずつ表示（3×2）" in js
    assert "d.getPage(1)" in js
    assert "openFile(name, true)" in js and "if (fromGrid) showGrid(gridStart);" in js
    # 閉じる・フォルダを開き直す・1枚表示へ切り替えるときに、読み込み中のマスを止める
    assert js.count("cancelGrid();") >= 4


def test_whiteboard_background_can_line_up_six_pdfs(tmp_path):
    c = create_app(tmp_path).test_client()
    js = c.get("/js/whiteboard.js").get_data(as_text=True)
    assert 'const GRID_NAME = "PDFを6枚ずつ並べる（3×2）";' in js
    assert "const GRID_COLS = 3;" in js and "const GRID_ROWS = 2;" in js
    assert '{ value: "pdfgrid", label: GRID_NAME }' in js
    # 7つ目からは次のページ。描いたPDFはすぐ閉じ、ページを替えたら描きかけをやめる
    assert "names.slice(i, i + per)" in js and "if (d) d.destroy();" in js and "bgGen++;" in js
    # PDF.js は canvas 全体を白で塗るので、別の canvas に描いてから貼る
    assert "ctx.drawImage(tmp," in js


def test_uhd_screen_uses_smaller_text_and_three_equipment_rows(tmp_path):
    c = create_app(tmp_path).test_client()
    css = c.get("/board.css").get_data(as_text=True)
    js = c.get("/js/board.js").get_data(as_text=True)
    # 4K では文字を 85%、機器使用予定を3行分にする（HD は今のまま）
    assert "html.uhd { font-size: calc(100vw / 180 * 0.85); }" in css
    assert "html.uhd #equipment-wrap { max-height: calc(3.5rem + 3 * 4.25rem + 6px); }" in css
    # 4K では連絡事項も3行分にする
    assert "html.uhd #notices { max-height: calc(3 * 3.5rem + 6px); }" in css
    assert 'classList.toggle("uhd", isUhd(screen.width, devicePixelRatio))' in js
    assert "uhd() ? 3 : 2" in js
    # 本日の作業予定：作業内容を狭くし、工事件名を広げる（作業者数の列を足したあとの幅）
    assert "#schedule .c-work { width: 18.1%; }" in css
    assert "#schedule .c-constr { width: 22.4%; }" in css


def test_schedule_has_workers_column_with_a_number_pad(tmp_path):
    c = create_app(tmp_path).test_client()
    html = c.get("/").get_data(as_text=True)
    js = c.get("/js/board.js").get_data(as_text=True)
    picker = c.get("/js/picker.js").get_data(as_text=True)
    css = c.get("/board.css").get_data(as_text=True)
    schedule = html[html.index('id="schedule"'):html.index('id="equipment"')]
    # 責任者の右に作業者数。休日出勤の表には足さない
    assert schedule.index('class="c-leader"') < schedule.index('class="c-workers"') < schedule.index('class="c-work"')
    assert html.count('class="c-workers"') == 1
    assert '"名"' in js and "editWorkers(r)" in js
    assert "export function inputNumber(" in picker
    assert "#schedule .c-workers {" in css
    # 本日の作業予定の列幅の合計は 100%
    import re
    widths = re.findall(r"#schedule \.c-[a-z]+ \{ width: ([0-9.]+)%; \}", css)
    assert len(widths) == 7 and abs(sum(map(float, widths)) - 100) < 0.01


def test_settings_screen_has_the_three_data_folders(tmp_path):
    c = create_app(tmp_path).test_client()
    html = c.get("/").get_data(as_text=True)
    js = c.get("/js/admin-settings.js").get_data(as_text=True)
    for ident, key in (("accident-folder", "accident_folder"), ("companies-folder", "companies_folder"), ("constructions-folder", "constructions_folder")):
        assert f'id="{ident}"' in html, ident
        assert f'$("{ident}").value = s.{key} || "";' in js, ident
        assert f'{key}: $("{ident}").value.trim(),' in js, ident


def test_buttons_change_on_screen_before_the_server_answers(tmp_path):
    c = create_app(tmp_path).test_client()
    js = c.get("/js/board.js").get_data(as_text=True)
    assert c.get("/js/optimistic.mjs").status_code == 200
    save = js[js.index("async function save("):]
    save = save[:save.index("\n}\n")]
    # 押した値を先に画面へ出してから保存する。保存中は、3秒ごとの取り直しで古い内容に戻さない
    assert save.index("applyLocal(state, method, url, body)") < save.index("await api(method, url, body)")
    assert "saving++" in save and "saving--" in save
    assert "if (!saving && (r.rev !== lastRev" in js[js.index("async function poll("):]


def test_accident_pdfs_are_reused_while_unchanged(tmp_path):
    js = create_app(tmp_path).test_client().get("/js/accident.js").get_data(as_text=True)
    # 一度読んだ PDF は、ファイルが同じ（url の版が同じ）あいだ使い回す。ジャンルを変えても、表示中の資料が残っていれば続ける
    assert "const DOC_CACHE_MAX = 6;" in js
    assert "docCache.get(url)" in js
    assert "files.findIndex(f => f.url === current)" in js


def test_server_handles_eight_requests_at_once():
    import app as app_module
    src = open(app_module.__file__, encoding="utf-8").read()
    assert "threads=8" in src and "threads=4" not in src


def test_time_windows_have_colored_numbered_titles(tmp_path):
    c = create_app(tmp_path).test_client()
    js = c.get("/js/board.js").get_data(as_text=True)
    picker = c.get("/js/picker.js").get_data(as_text=True)
    css = c.get("/board.css").get_data(as_text=True)
    # 表の欄は1行（8:00～17:00）のまま。押すと、青い「① 開始時刻」、続けてオレンジの「② 終了時刻」の窓が出る
    edit = js[js.index("async function editTimes("):]
    edit = edit[:edit.index("\n}\n")]
    assert '"① 開始時刻を選ぶ", titleCls: "title-start"' in edit
    assert "`② 終了時刻を選ぶ（開始 ${start}）`, titleCls: \"title-end\"" in edit
    assert "titleCls" in picker
    assert ".panel h3.title-start { background: #1D4ED8; }" in css and ".panel h3.title-end { background: #C2410C; }" in css
    assert ".tcell" not in css


def test_picker_window_and_buttons_are_bigger(tmp_path):
    css = create_app(tmp_path).test_client().get("/board.css").get_data(as_text=True)
    assert ".panel { display: flex; flex-direction: column; min-width: 46rem; max-width: 90vw; max-height: 90vh;" in css
    assert ".options { display: grid; grid-template-columns: repeat(auto-fill, minmax(18rem, 1fr));" in css
    assert ".opt { min-height: 5.5rem; padding: 0 1.2rem; font-size: 2rem;" in css
    assert ".panel h3 { margin: 0 0 1.2rem; font-size: 2.3rem;" in css


def test_documents_buttons_are_at_the_bottom_and_the_list_in_the_middle(tmp_path):
    c = create_app(tmp_path).test_client()
    html = c.get("/").get_data(as_text=True)
    css = c.get("/board.css").get_data(as_text=True)
    docs = html[html.index('id="documents"'):html.index('id="settings"')]
    # 上の見出しはファイル名だけ。ボタンは画面の下の帯に（左＝ページの操作、右＝一覧へ・閉じる）
    head = docs[:docs.index("</div>")]
    assert "docs-close" not in head and "docs-back" not in head
    foot = docs[docs.index('class="docs-foot"'):]
    assert foot.index('id="doc-nav"') < foot.index('id="docs-back"') < foot.index('id="docs-close"')
    for ident in ["doc-prev", "doc-page", "doc-next", "doc-zoom-out", "doc-zoom-in", "doc-pages-grid", "grid-prev", "grid-range", "grid-next", "grid-single"]:
        assert f'id="{ident}"' in foot, ident
    # 一覧（6枚ずつ表示とPDFの名前）は画面のまん中
    assert "#doc-list { display: flex; align-items: center; justify-content: center;" in css


def test_a_pdf_can_be_shown_six_pages_at_a_time(tmp_path):
    js = create_app(tmp_path).test_client().get("/js/documents.js").get_data(as_text=True)
    assert "async function showPageGrid(start)" in js
    assert '$("doc-pages-grid").addEventListener("click"' in js
    # ページのマスを押すと、そのページを1枚で開く。「1枚ずつ表示」で戻る
    assert "showViewerAt(n)" in js and '$("grid-single").addEventListener("click"' in js
    assert 'gridMode === "pages"' in js


def test_documents_can_remember_the_page_and_zoom_per_device(tmp_path):
    c = create_app(tmp_path).test_client()
    html = c.get("/").get_data(as_text=True)
    js = c.get("/js/documents.js").get_data(as_text=True)
    assert c.get("/js/docmemory.mjs").status_code == 200
    local = html[html.index("この端末だけ"):html.index("全端末共通")]
    assert 'name="doc-memory" value="on"' in local and 'name="doc-memory" value="off"' in local
    assert 'const MEMORY_KEY = "dbb.docMemory";' in js and 'const POS_KEY = "dbb.docPos";' in js
    # 覚えるのは、閉じる・一覧へ戻る・別の文書を開く・操作なしで戻るとき。PDF の指紋が違えば1ページ目から
    assert js.count("saveCurrentPos()") >= 3
    assert "doc.fingerprints[0]" in js


def test_a_folder_with_one_pdf_opens_it_without_the_list(tmp_path):
    js = create_app(tmp_path).test_client().get("/js/documents.js").get_data(as_text=True)
    assert "if (files.length === 1) {" in js and "openFile(files[0]);" in js
    # 1件だけのときは「一覧へ」を押しても同じPDFに戻るだけなので、出さない
    assert '$("docs-back").hidden = view === "list" || (view === "viewer" && !fromGrid && folderFiles.length === 1);' in js
