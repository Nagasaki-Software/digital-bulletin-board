import sys
from pathlib import Path


def make_pdf(texts, width=842, height=595):
    objs = [None, None, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for text in texts:
        content = f"BT /F1 56 Tf 60 {height // 2} Td ({text}) Tj ET".encode("latin-1")
        page_id = len(objs) + 1
        content_id = len(objs) + 2
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] /Contents {content_id} 0 R "
            f"/Resources << /Font << /F1 3 0 R >> >> >>".encode()
        )
        objs.append(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
        kids.append(f"{page_id} 0 R")
    objs[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>".encode()
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("使い方: make_sample_pdfs.py <災害事例フォルダ> <文書フォルダ>  (誤上書きを避けるため省略不可)")
    accident = Path(sys.argv[1])
    docs = Path(sys.argv[2])
    accident.mkdir(parents=True, exist_ok=True)
    docs.mkdir(parents=True, exist_ok=True)
    samples = {
        "溶接作業_サンプル1.pdf": ["WELDING SAMPLE 1"],
        "溶接作業_サンプル2.pdf": ["WELDING SAMPLE 2 P1", "WELDING SAMPLE 2 P2"],
        "高所作業_サンプル1.pdf": ["HIGH PLACE SAMPLE 1"],
        "電気配線_サンプル1.pdf": ["WIRING SAMPLE 1"],
        "溶接作業＋高所作業_サンプル複合.pdf": ["WELDING AND HIGH PLACE"],
        "その他_サンプル1.pdf": ["OTHER SAMPLE 1"],
    }
    for name, texts in samples.items():
        (accident / name).write_bytes(make_pdf(texts))
    (docs / "手順書サンプル.pdf").write_bytes(make_pdf(["MANUAL SAMPLE P1", "MANUAL SAMPLE P2"], 595, 842))
    print("見本PDFを作りました:", accident, docs)
