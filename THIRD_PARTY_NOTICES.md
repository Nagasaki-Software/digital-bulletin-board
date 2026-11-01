# 同梱しているソフトウェアのライセンス

| 名前 | 場所 | 作者 | ライセンス |
|---|---|---|---|
| PDF.js（v4.10.38） | `static/pdfjs/`（`cmaps/` を除く） | Mozilla Foundation | Apache License 2.0（全文は `static/pdfjs/LICENSE`） |
| PDF.js 同梱の文字データ（CMap） | `static/pdfjs/cmaps/` | Adobe Systems Incorporated | BSD 3-Clause 形式（全文は `static/pdfjs/cmaps/LICENSE`） |

PDF.js の各ファイルの先頭にある著作権表示は、変更せずに残しています。

## 初回セットアップで入る部品

`初回セットアップ.bat` が、インターネット（PyPI）からダウンロードします。このリポジトリには含まれていません。下の表は、開発に使った環境に入っている各部品の配布情報（`.venv/Lib/site-packages/*.dist-info`）を写したものです。ライセンスの全文は、各部品に同梱されています（インストール後は、同じ場所の `LICENSE` ファイル）。

| 部品 | 確認したバージョン | ライセンス | 確認した場所 |
|---|---|---|---|
| Flask | 3.1.3 | BSD-3-Clause | `flask-3.1.3.dist-info/METADATA`、`licenses/LICENSE.txt` |
| waitress | 3.0.2 | ZPL 2.1 | `waitress-3.0.2.dist-info/METADATA`、`LICENSE.txt` |
| jpholiday | 1.0.3 | MIT | `jpholiday-1.0.3.dist-info/METADATA`、`licenses/LICENSE` |
| pytest（テスト用。動かすだけなら不要） | 9.2.0 | MIT | `pytest-9.2.0.dist-info/METADATA`、`licenses/LICENSE` |

Flask と一緒に自動で入る部品（Werkzeug、Jinja2、Click、ItsDangerous、MarkupSafe、Blinker）は、配布情報の表示では BSD 系または MIT です（Werkzeug・Click・MarkupSafe は `BSD-3-Clause` の表示を確認、Jinja2・ItsDangerous は BSD License、Blinker は MIT License の分類表示を確認）。ライセンス全文までは確認していません（未確認）。

## 確認していないこと（未確認）

- 各部品の最新版のライセンス表示。部品はインストールの時点の最新版が入るため、上の表と変わる可能性があります。ライセンスは、配布元の表示が正です
- PDF.js の `cmaps/LICENSE` の著作権者表記（Adobe Systems Incorporated、1990-2009）は、ファイルの先頭を読んで写しました。BSD 3-Clause と呼んでいるのは、条文の形からの判断です
