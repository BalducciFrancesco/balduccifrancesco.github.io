#!/usr/bin/env python3
"""Prepare album covers for the photography page.

Runs automatically on GitHub (.github/workflows/gallery.yml) whenever covers or
albums.json change. To run it locally instead:
    pip install pillow
    python3 photography/prepare_covers.py

Albums are listed by hand in photography/gallery/albums.json, one entry per
category with its albums, in the order they should appear on the page:

    [
      {
        "category": "events",
        "albums": [
          {
            "title": "IntroFest Fall '26",
            "place": "DTU",
            "date": "2026-08",
            "cover": "introfest.jpg",
            "url": "https://www.amazon.it/photos/share/..."
          }
        ]
      }
    ]

"date" is year and month (YYYY-MM); the page shows it as "August 2026".
"cover" is a file in photography/gallery/covers/. The script shrinks each cover
to at most COVER_SIZE px and re-saves it without any metadata (EXIF, GPS, XMP),
in place. An album stays hidden until it has both a cover and a url.
"""

import json
import re
import sys
from datetime import date
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

    categories = json.loads(ALBUMS.read_text()) if ALBUMS.exists() else []
    this_month = f"{date.today():%Y-%m}"
    problems, count = [], 0
    for category in categories:
        if not category.get("category"):
            problems.append("a category has no name")
        if not category.get("albums"):
            problems.append(f"category {category.get('category')}: no albums")
        for album in category.get("albums", []):
            count += 1
            name = album.get("title") or "(untitled)"
            when = album.get("date", "")
            if when and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", when):
                problems.append(f"{name}: date {when!r} should be year-month, e.g. 2025-06")
            elif when > this_month:
                problems.append(f"{name}: date {when} is in the future")
            if album.get("cover") and not (COVERS / album["cover"]).is_file():
                problems.append(f"{name}: cover {album['cover']} is not in gallery/covers/")
            if not album.get("cover") or not album.get("url"):
                print(f"  {name}: hidden until it has a cover and a url")
    if problems:
        sys.exit("albums.json problems:\n  " + "\n  ".join(problems))
    print(f"{len(categories)} categories, {count} albums OK")

if __name__ == "__main__":
    main()
