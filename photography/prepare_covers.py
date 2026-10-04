#!/usr/bin/env python3
"""Prepare album covers for the photography page.

Runs automatically on GitHub (.github/workflows/gallery.yml) whenever covers or
albums.json change. To run it locally instead:
    pip install pillow
    python3 photography/prepare_covers.py

Albums are listed by hand in photography/gallery/albums.json, in the order they
should appear (categories follow the order of their first album):

    [
      {
        "title": "Introfest",
        "category": "Parties",
        "place": "Copenhagen",
        "date": "August 2026",
        "cover": "introfest.jpg",
        "url": "https://www.amazon.com/photos/share/..."
      }
    ]

"cover" is a file in photography/gallery/covers/. The script shrinks each cover
to at most COVER_SIZE px and re-saves it without any metadata (EXIF, GPS, XMP),
in place. An album stays hidden until it has both a cover and a url.
"""

import json
import sys
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent / "gallery"
COVERS = ROOT / "covers"
ALBUMS = ROOT / "albums.json"

COVER_SIZE = 1200
EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def prepare(path):
    with Image.open(path) as img:
        has_metadata = bool(img.getexif()) or "xmp" in img.info or "XML:com.adobe.xmp" in img.info
        if max(img.size) <= COVER_SIZE and not has_metadata:
            return False
        img = ImageOps.exif_transpose(img)  # bake rotation in, since the metadata is dropped
        img.thumbnail((COVER_SIZE, COVER_SIZE), Image.LANCZOS)
        icc = img.info.get("icc_profile")  # keeps colours right; holds no personal data
        if path.suffix.lower() in {".jpg", ".jpeg"}:
            img.convert("RGB").save(path, quality=85, optimize=True, progressive=True, icc_profile=icc)
        else:
            img.save(path, icc_profile=icc)
    return True


def main():
    COVERS.mkdir(parents=True, exist_ok=True)
    for path in sorted(p for p in COVERS.iterdir() if p.suffix.lower() in EXTENSIONS):
        if prepare(path):
            print(f"  prepared {path.name}")

    albums = json.loads(ALBUMS.read_text()) if ALBUMS.exists() else []
    problems = []
    for album in albums:
        name = album.get("title") or "(untitled)"
        if not album.get("category"):
            problems.append(f"{name}: no category")
        if album.get("cover") and not (COVERS / album["cover"]).is_file():
            problems.append(f"{name}: cover {album['cover']} is not in gallery/covers/")
        if not album.get("cover") or not album.get("url"):
            print(f"  {name}: hidden until it has a cover and a url")
    if problems:
        sys.exit("albums.json problems:\n  " + "\n  ".join(problems))
    print(f"{len(albums)} albums OK")


if __name__ == "__main__":
    main()
