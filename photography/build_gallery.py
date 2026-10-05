#!/usr/bin/env python3
"""Build the photo gallery: strip GPS, read EXIF, make thumbnails, write gallery.json.

Runs automatically on GitHub (.github/workflows/gallery.yml) whenever photos or
albums.json change. To run it locally instead:
    pip install pillow            # plus exiftool, which removes GPS data
    python3 photography/build_gallery.py

Each album is one folder of photos in photography/gallery/full/. The photos are
shown as they are when opened fullscreen, in file-name order (rename them, e.g.
01.jpg, 02.jpg, to choose the order):

    full/
        Parties/
            IMG_0001.jpg
        Events/
            ...

The script
  - removes GPS data from those photos in place (lossless, via exiftool),
  - writes a small copy of each to gallery/thumbs/<album>/ for the grid,
  - keeps gallery/albums.json, yours to edit: the albums in the order they
    appear on the page, each with its title, description and cover (a photo's
    file name). New folders are added at the end; your values are never
    overwritten. Optional per-photo fields (title, camera, lens, film, ...)
    go under "photos": {"IMG_0001": {"title": "..."}},
  - writes gallery/gallery.json, read by the page. Do not edit it.
"""

import hashlib
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from urllib.parse import quote, unquote

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent / "gallery"
FULL_DIR = ROOT / "full"
THUMB_DIR = ROOT / "thumbs"
ALBUMS = ROOT / "albums.json"
OUTPUT = ROOT / "gallery.json"

THUMB_HEIGHT = 600
EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}
# fullscreen photos above these sizes load slowly; the build only warns about them
LARGE_BYTES, LARGE_EDGE = 3_000_000, 3000

# EXIF tag ids
MAKE, MODEL, DATETIME = 0x010F, 0x0110, 0x0132
EXIF_IFD = 0x8769
EXPOSURE, FNUMBER, ISO, DATETIME_ORIGINAL = 0x829A, 0x829D, 0x8827, 0x9003
FOCAL, FOCAL_35MM, LENS_MAKE, LENS_MODEL = 0x920A, 0xA405, 0xA433, 0xA434


def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def clean(text):
    return str(text).strip("\x00 ").strip() if text else ""


def format_exposure(seconds):
    if seconds is None or seconds <= 0:
        return ""
    if seconds >= 1:
        return f"{seconds:g}s"
    return f"1/{round(1 / seconds)}s"


def read_exif(img):
    exif = img.getexif()
    sub = exif.get_ifd(EXIF_IFD)
    info = {}

    make, model = clean(exif.get(MAKE)), clean(exif.get(MODEL))
    # "Canon" + "Canon EOS R6" -> "Canon EOS R6", "FUJIFILM" + "X-T3" -> "FUJIFILM X-T3"
    if model:
        info["camera"] = model if make and model.lower().startswith(make.split()[0].lower()) else f"{make} {model}".strip()

    lens = clean(sub.get(LENS_MODEL))
    lens_make = clean(sub.get(LENS_MAKE))
    if lens and lens_make and not lens.lower().startswith(lens_make.lower()):
        lens = f"{lens_make} {lens}"
    if lens:
        info["lens"] = lens

    focal = number(sub.get(FOCAL))
    focal35 = number(sub.get(FOCAL_35MM))
    if focal:
        info["focal"] = f"{focal:g}mm"
        if focal35 and round(focal35) != round(focal):
            info["focal"] += f" ({focal35:g}mm eq.)"

    if (exposure := number(sub.get(EXPOSURE))) is not None:
        # snap float noise (0.0040000001) back to a clean fraction first
        info["exposure"] = format_exposure(float(Fraction(exposure).limit_denominator(8000)))
    if fnumber := number(sub.get(FNUMBER)):
        info["aperture"] = f"f/{fnumber:g}"
    iso = sub.get(ISO)
    if isinstance(iso, tuple):
        iso = iso[0] if iso else None
    if iso:
        info["iso"] = f"ISO {iso}"

    raw_date = clean(sub.get(DATETIME_ORIGINAL) or exif.get(DATETIME))
    try:
        info["date"] = datetime.strptime(raw_date, "%Y:%m:%d %H:%M:%S").strftime("%Y-%m")
    except ValueError:
        pass

    return {k: v for k, v in info.items() if v}


def strip_gps():
    """Remove GPS tags (EXIF and XMP) from every photo, without re-encoding it."""
    if not shutil.which("exiftool"):
        print("WARNING: exiftool is not installed, GPS data was NOT removed")
        return
    exts = [arg for ext in EXTENSIONS for arg in ("-ext", ext.lstrip("."))]
    subprocess.run(
        ["exiftool", "-q", "-q", "-r", "-overwrite_original", *exts,
         "-gps:all=", "-xmp-exif:gps*=", str(FULL_DIR)],
        check=True,
    )


def build_photo(src, album_id, overrides, previous):
    pid = src.stem
    thumb = THUMB_DIR / album_id / f"{pid}.jpg"
    digest = hashlib.sha1(src.read_bytes()).hexdigest()
    with Image.open(src) as img:
        exif = read_exif(img)
        img = ImageOps.exif_transpose(img)  # browsers rotate by EXIF too, so use the upright size
        width, height = img.size
        old = previous.get(src)
        if old and old.get("hash") == digest and thumb.exists():
            thumb_w, thumb_h = old["thumbWidth"], old["thumbHeight"]
        else:
            copy = img.copy()
            copy.thumbnail((THUMB_HEIGHT * 4, THUMB_HEIGHT), Image.LANCZOS)
            thumb.parent.mkdir(parents=True, exist_ok=True)
            # no exif= argument, so the thumbnail carries no metadata at all
            copy.convert("RGB").save(thumb, "JPEG", quality=82, optimize=True, progressive=True)
            thumb_w, thumb_h = copy.size

    if src.stat().st_size > LARGE_BYTES or max(width, height) > LARGE_EDGE:
        print(f"  note: {src.relative_to(FULL_DIR)} is {src.stat().st_size / 1e6:.1f} MB, "
              f"{width}x{height}; around 2400px and under 1 MB opens faster")

    photo = {"id": pid, **exif, **{k: v for k, v in overrides.get(pid, {}).items() if v}}
    return photo | {
        "src": quote(src.relative_to(ROOT.parent).as_posix()),
        "width": width,
        "height": height,
        "thumb": quote(thumb.relative_to(ROOT.parent).as_posix()),
        "thumbWidth": thumb_w,
        "thumbHeight": thumb_h,
        "hash": digest,
    }


def main():
    FULL_DIR.mkdir(parents=True, exist_ok=True)
    strip_gps()

    editable = json.loads(ALBUMS.read_text()) if ALBUMS.exists() else []
    folders = {slugify(d.name): d for d in sorted(FULL_DIR.iterdir()) if d.is_dir()}
    # new folders get an entry at the end, to fill in and move where you want them
    for album_id, folder in folders.items():
        if not any(a.get("id") == album_id for a in editable):
            editable.append({"id": album_id, "title": folder.name, "description": "", "cover": ""})

    # thumbnails of unchanged photos are reused, keyed by the photo's path
    previous = {}
    if OUTPUT.exists():
        for album in json.loads(OUTPUT.read_text()):
            for p in album["photos"]:
                previous[ROOT.parent / unquote(p["src"])] = p

    albums, written = [], set()
    for meta in editable:
        folder = folders.get(meta.get("id"))
        if not folder:
            print(f"  albums.json lists '{meta.get('id')}' but there is no folder for it in gallery/full/")
            continue
        overrides = meta.get("photos", {})
        sources = sorted((p for p in folder.iterdir() if p.suffix.lower() in EXTENSIONS), key=lambda p: p.name.lower())
        photos = [build_photo(src, meta["id"], overrides, previous) for src in sources]
        if not photos:
            continue
        written |= {ROOT.parent / unquote(p["thumb"]) for p in photos}

        cover_name = Path(meta.get("cover") or "").stem
        cover = next((p for p in photos if p["id"] == cover_name), None)
        if cover_name and not cover:
            print(f"  {meta['title']}: cover '{meta['cover']}' is not in the album, using the first photo")
        cover = cover or photos[0]
        albums.append({
            "id": meta["id"],
            "title": meta.get("title") or folder.name,
            "description": meta.get("description", ""),
            "cover": {k: cover[k] for k in ("thumb", "thumbWidth", "thumbHeight")},
            "photos": photos,
        })
        print(f"  {meta.get('title') or folder.name}: {len(photos)} photos")

    for loose in (p for p in FULL_DIR.iterdir() if p.suffix.lower() in EXTENSIONS):
        print(f"  skipped {loose.name}: photos go inside an album folder")

    # remove thumbnails of photos or albums that no longer exist
    for path in sorted(THUMB_DIR.rglob("*"), reverse=True) if THUMB_DIR.exists() else []:
        if path.is_file() and path not in written:
            path.unlink()
        elif path.is_dir() and not any(path.iterdir()):
            path.rmdir()

    ALBUMS.write_text(json.dumps(editable, indent=2, ensure_ascii=False) + "\n")
    OUTPUT.write_text(json.dumps(albums, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {len(albums)} albums to {OUTPUT.relative_to(ROOT.parent.parent)}")


if __name__ == "__main__":
    main()
