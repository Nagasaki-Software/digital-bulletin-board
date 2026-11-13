"""取扱説明書.md を PDF にする。

Markdown を HTML にしてから、Windows に入っている Edge の印刷機能で PDF にする。
追加のインストールは要らない。Markdown は、この説明書で使っている書き方
（見出し・段落・箇条書き・番号付き・表・引用・画像・コード・太字・リンク）だけに対応する。

使い方（アプリのフォルダで）:
    .venv\\Scripts\\python.exe docs\\manual\\make_pdf.py
"""
import html
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "取扱説明書.md"
OUTPUT = HERE / "取扱説明書.pdf"
EDGE_CANDIDATES = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
]

CSS = """
@page { size: A4; margin: 16mm 15mm 18mm 15mm; }
body { font-family: "Meiryo", "Yu Gothic", sans-serif; font-size: 10pt; line-height: 1.75;
       color: #1f2937; }
h1 { font-size: 22pt; color: #1f3a5f; border-bottom: 3px solid #1f3a5f; padding-bottom: 6px; }
h2 { font-size: 15pt; color: #fff; background: #1f3a5f; padding: 6px 12px; margin-top: 0;
     break-before: page; }
h3 { font-size: 12pt; color: #1f3a5f; border-left: 5px solid #e8772e; padding-left: 8px;
     margin-top: 22px; }
h4 { font-size: 10.5pt; color: #1f3a5f; margin: 14px 0 4px; }
h1, h2, h3, h4 { break-after: avoid; }
p:has(+ table) { break-after: avoid; }   /* 表の前置きの1文を表と離さない */
p { margin: 6px 0; }
a { color: #1f5fa8; text-decoration: none; }
table { border-collapse: collapse; width: 100%; margin: 8px 0 12px; break-inside: avoid;
        font-size: 9.5pt; }
th, td { border: 1px solid #c5ccd6; padding: 4px 8px; vertical-align: top; text-align: left; }
th { background: #eef2f7; color: #1f3a5f; }
img { max-width: 100%; max-height: 220mm; border: 1px solid #c5ccd6; display: block; margin: 8px auto 2px;
      break-inside: avoid; }
figure { margin: 8px 0; break-inside: avoid; }
blockquote { margin: 10px 0; padding: 6px 12px; background: #fff7ed;
             border-left: 5px solid #e8772e; break-inside: avoid; }
blockquote p { margin: 3px 0; }
code { font-family: Consolas, "Meiryo", monospace; background: #eef2f7; padding: 0 4px;
       border-radius: 3px; font-size: 9pt; }
pre { background: #eef2f7; padding: 8px 12px; border-radius: 4px; break-inside: avoid; }
pre code { padding: 0; background: none; }
em { color: #6b7280; font-style: normal; font-size: 9pt; display: block; text-align: center; }
hr { display: none; }
li { margin: 2px 0; }
"""


def slug(text: str) -> str:
    """GitHub と同じ規則で見出しのアンカーを作る（目次のリンクを PDF でも効かせるため）"""
    text = text.strip().lower()
    kept = "".join(ch for ch in text
                   if ch in " -_" or unicodedata.category(ch)[0] in "LMN")
    return kept.replace(" ", "-")


def inline(text: str) -> str:
    """行の中の書式を HTML にする。コードの中身には他の書式を効かせない。
    コードは先に印へ置き換えておき、太字などを当てたあとで戻す（**`名前`** のような
    太字の中のコードを扱うため）。"""
    codes = []

    def keep(m):
        codes.append(f"<code>{html.escape(m.group(1))}</code>")
        return f"\x00{len(codes) - 1}\x00"

    s = re.sub(r"`([^`]+)`", keep, text)
    s = html.escape(s, quote=False)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], s)


def table(lines: list) -> str:
    rows = [[c.strip() for c in line.strip().strip("|").split("|")] for line in lines]
    head, body = rows[0], rows[2:]
    out = ["<table><thead><tr>"]
    out += [f"<th>{inline(c)}</th>" for c in head]
    out.append("</tr></thead><tbody>")
    for r in body:
        out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def dedent(lines: list, n: int) -> list:
    return [line[n:] if line[:n].strip() == "" else line.lstrip() for line in lines]


def blocks(lines: list) -> str:
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped == "---":
            i += 1
        elif stripped.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("```"):
                j += 1
            code = "\n".join(lines[i + 1:j])
            out.append(f"<pre><code>{html.escape(code)}</code></pre>")
            i = j + 1
        elif m := re.match(r"(#{1,4}) (.+)", line):
            level, text = len(m.group(1)), m.group(2)
            out.append(f'<h{level} id="{slug(text)}">{inline(text)}</h{level}>')
            i += 1
        elif m := re.match(r"!\[([^\]]*)\]\(([^)]+)\)", stripped):
            src = (HERE / m.group(2)).as_uri()
            img = f'<img src="{src}" alt="{html.escape(m.group(1))}">'
            i += 1
            # 直後の *説明文* は写真と同じページに置く（ページの変わり目で離れないように）
            j = i
            while j < len(lines) and not lines[j].strip():
                j += 1
            cap = lines[j].strip() if j < len(lines) else ""
            if re.fullmatch(r"\*[^*].*\*", cap):
                out.append(f"<figure>{img}{inline(cap)}</figure>")
                i = j + 1
            else:
                out.append(img)
        elif stripped.startswith(">"):
            j = i
            inner = []
            while j < len(lines) and lines[j].strip().startswith(">"):
                inner.append(re.sub(r"^\s*>\s?", "", lines[j]))
                j += 1
            out.append(f"<blockquote>{blocks(inner)}</blockquote>")
            i = j
        elif stripped.startswith("|"):
            j = i
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            out.append(table(lines[i:j]))
            i = j
        elif re.match(r"(- |\d+\. )", stripped):
            ordered = bool(re.match(r"\d+\. ", stripped))
            tag = "ol" if ordered else "ul"
            items, j = [], i
            while j < len(lines):
                m = re.match(r"(\s*)(- |\d+\. )(.*)", lines[j])
                if not m or len(m.group(1)) > 0:
                    break
                indent = len(m.group(2))
                body = [m.group(3)]
                j += 1
                # 続きの行（字下げされた行・空行のあとの字下げ）は同じ項目に入れる
                while j < len(lines) and (lines[j].strip() == "" or lines[j].startswith(" " * indent)):
                    if lines[j].strip() == "" and (j + 1 >= len(lines)
                                                   or not lines[j + 1].startswith(" " * indent)):
                        break
                    body.append(lines[j])
                    j += 1
                first, rest = body[0], dedent(body[1:], indent)
                inner = inline(first) + (blocks(rest) if rest else "")
                items.append(f"<li>{inner}</li>")
                while j < len(lines) and lines[j].strip() == "":
                    nxt = lines[j + 1].strip() if j + 1 < len(lines) else ""
                    if re.match(r"\d+\. " if ordered else r"- ", nxt):
                        j += 1
                    else:
                        break
            out.append(f"<{tag}>{''.join(items)}</{tag}>")
            i = j
        else:
            j = i
            para = []
            while j < len(lines) and lines[j].strip() and not re.match(
                    r"\s*(#|>|\||```|- |\d+\. |!\[)", lines[j]):
                para.append(lines[j].strip())
                j += 1
            if not para:
                para, j = [stripped], i + 1
            out.append(f"<p>{inline(' '.join(para))}</p>")
            i = j
    return "\n".join(out)


def main():
    text = SOURCE.read_text(encoding="utf-8")
    body = blocks(text.splitlines())
    doc = (f'<!doctype html><html lang="ja"><head><meta charset="utf-8">'
           f"<title>デジタル掲示板 取扱説明書</title><style>{CSS}</style></head>"
           f"<body>{body}</body></html>")
    edge = next((p for p in EDGE_CANDIDATES if p.exists()), None)
    if edge is None:
        sys.exit("Edge が見つかりません。PDF にするには Microsoft Edge が必要です。")
    started = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        page =Path(tmp) / "manual.html"
        page.write_text(doc, encoding="utf-8")
        subprocess.run([str(edge), "--headless=new", "--disable-gpu", "--no-first-run",
                        f"--user-data-dir={Path(tmp) / 'profile'}",
                        "--no-pdf-header-footer", "--allow-file-access-from-files",
                        f"--print-to-pdf={OUTPUT}", page.as_uri()],
                       check=True, timeout=120)
        # Edge は PDF の書き出しを終える前に戻ることがある。書き終わるまで一時フォルダを消さずに待つ
        deadline = time.time() + 180
        last = -1
        while time.time() < deadline:
            if OUTPUT.exists() and OUTPUT.stat().st_mtime >= started:
                size = OUTPUT.stat().st_size
                if size > 0 and size == last:
                    break
                last = size
            time.sleep(2)
        else:
            sys.exit("PDF が作成されませんでした")
    print("作成しました:", OUTPUT)


if __name__ == "__main__":
    main()
