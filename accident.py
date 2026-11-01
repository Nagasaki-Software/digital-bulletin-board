import re
from pathlib import Path


def natural_key(name):
    return [int(t) if t.isdecimal() else t for t in re.split(r"(\d+)", name)]


def file_genres(filename, known):
    stem = Path(filename).stem
    if "_" not in stem:
        return []
    head = stem.split("_", 1)[0]
    names = [n.strip() for n in re.split(r"[＋+]", head)]
    return [n for n in names if n in known]


def _pdfs(folder):
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return [p.name for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"]


def list_pdfs(folder):
    return sorted(_pdfs(folder), key=natural_key)


def playlist(folder, genre_order, checked):
    items = []
    for name in _pdfs(folder):
        hits = [genre_order.index(g) for g in file_genres(name, genre_order) if g in checked]
        if hits:
            items.append((min(hits), natural_key(name), name))
    return [name for _, _, name in sorted(items)]
