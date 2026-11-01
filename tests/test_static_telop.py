import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import create_app


def get(tmp_path, path):
    return create_app(tmp_path).test_client().get(path)


def test_html_has_telop_strip_after_the_main_columns(tmp_path):
    html = get(tmp_path, "/").get_data(as_text=True)
    assert 'id="telop"' in html and 'id="telop-track"' in html and 'id="telop-scroll"' in html
    assert "お知らせ" in html[html.index('id="telop"'):]
    strip = html[html.index('id="telop"'):html.index('id="picker"')]
    assert " hidden" not in strip  # 常に表示（表示・非表示の設定は無い）
    assert "innerHTML" not in strip
    # 画面の下に固定され、重ね表示（設定 z-index 10・文書 20・待機 30）より下にある。本体はその分だけ低くする
    css = get(tmp_path, "/board.css").get_data(as_text=True)
    telop_rule = css[css.index("#telop {"):css.index("#telop {") + 300]
    assert "position: fixed" in telop_rule and "bottom: 0" in telop_rule and "height: 3.6rem" in telop_rule
    assert "z-index: 5" in telop_rule
    assert "#board { height: calc(100vh - 3.6rem)" in css


def test_settings_overlay_has_both_sections_and_fields(tmp_path):
    html = get(tmp_path, "/").get_data(as_text=True)
    settings = html[html.index('id="settings"'):html.index('id="standby"')]
    assert "この端末だけ" in settings and "全端末共通" in settings
    for needle in ['id="doc-count"', 'id="telop-speed"', 'id="settings-save"', 'id="settings-msg"',
                   'name="edit-button"', 'name="theme"', 'id="settings-close"']:
        assert needle in settings, needle
    assert settings.index("この端末だけ") < settings.index("全端末共通") < settings.index('id="settings-save"')
    # equipment-inspection と同じ操作: 「文書掲示」の見出し、ボタン数の数字欄、5行を常に表示、「保存して適用」
    shared = settings[settings.index("全端末共通"):]
    assert shared.index("文書掲示") < shared.index('id="doc-count"') < shared.index('id="doc-label-0"')
    assert "ボタン数（1〜5）" in shared and "テロップ速度" in shared and "px/秒" in shared
    assert 'id="doc-count" type="number" min="1" max="5"' in shared
    assert "step-btn" not in settings
    for i in range(5):
        label = f'id="doc-label-{i}" class="f-label" maxlength="100" placeholder="ラベル {i + 1}"'
        folder = f'id="doc-folder-{i}" class="f-folder" maxlength="260" placeholder="フォルダパス"'
        assert label in shared and folder in shared, i
        assert shared.index(label) < shared.index(folder)  # ラベルとフォルダが同じ行に左右に並ぶ
        if i:
            assert shared.index(f'id="doc-folder-{i - 1}"') < shared.index(f'id="doc-label-{i}"')
    assert 'id="doc-label-5"' not in shared
    assert shared.index('id="doc-folder-4"') < shared.index('id="settings-msg"') < shared.index('id="settings-save"')
    assert ">保存して適用</button>" in shared
    css = get(tmp_path, "/board.css").get_data(as_text=True)
    assert ".doc-row.off" in css and ".status-line.error" in css
    css = get(tmp_path, "/board.css").get_data(as_text=True)
    assert "overflow-y: auto" in css[css.index(".panel-body"):css.index(".panel-body") + 300]


def test_modules_are_served_and_wired(tmp_path):
    c = create_app(tmp_path).test_client()
    for path in ["/js/telop.js", "/js/telop-text.mjs", "/js/admin-settings.js"]:
        assert c.get(path).status_code == 200, path
    assert "javascript" in c.get("/js/telop-text.mjs").content_type
    board = c.get("/js/board.js").get_data(as_text=True)
    assert "telop.js" in board and "admin-settings.js" in board
    assert "state.settings.telop" in board
    telop_js = c.get("/js/telop.js").get_data(as_text=True)
    assert "innerHTML" not in telop_js  # ファイルの文字は textContent / DOM ノードだけで入れる
    admin_js = c.get("/js/admin-settings.js").get_data(as_text=True)
    assert "/api/admin-settings" in admin_js


def test_admin_settings_js_follows_equipment_inspection_operation(tmp_path):
    js = get(tmp_path, "/js/admin-settings.js").get_data(as_text=True)
    assert "⚠" in js and "disabled" in js  # 赤字の状態表示・ボタン数より後ろの行は使えない状態
    assert "ラベル ${i + 1} を入力してください" in js and "フォルダパス ${i + 1} を入力してください" in js
    assert "step-btn" not in js and "dataset.delta" not in js


def test_telop_folder_input_is_above_speed_and_saved_with_the_form(tmp_path):
    html = get(tmp_path, "/").get_data(as_text=True)
    settings = html[html.index('id="settings"'):html.index('id="standby"')]
    folder_input = 'id="telop-folder" class="f-folder" type="text" maxlength="260" placeholder="空欄=telopフォルダ"'
    assert folder_input in settings and "テロップフォルダ" in settings
    assert "equipment-inspection と共通にするには、そのサイネージの PDF フォルダ（テキストファイルを置く場所）のパスを入れます" in settings
    assert settings.index("全端末共通") < settings.index('id="telop-folder"') < settings.index('id="telop-speed"') < settings.index("文書掲示")
    js = get(tmp_path, "/js/admin-settings.js").get_data(as_text=True)
    assert 'telop-folder").value = s.telop.folder' in js
    assert 'folder: $("telop-folder").value.trim()' in js
