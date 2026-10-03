#!/usr/bin/env python3
"""Build the photo gallery: strip GPS, read EXIF, make thumbnails, write gallery.json.

Runs automatically on GitHub (.github/workflows/gallery.yml) whenever photos or
albums.json change. To run it locally instead:
    pip install pillow            # plus exiftool, which removes GPS data
    python3 photography/build_gallery.py

Photos go in photography/gallery/full/, one folder per category and one
sub-folder per album. They are shown as they are when opened fullscreen:

    full/
        Portraits/
            Anna in Nyhavn/       <- album, its folder name is the default title
                IMG_0001.jpg
        Parties/
            Roskilde 2025/
                ...

The script
  - removes GPS data from those photos in place (lossless, via exiftool),
  - writes a small copy of each to gallery/thumbs/<album>/ for the grid,
  - keeps gallery/albums.json, yours to edit: title, place, date, description
    and cover of each album, plus optional per-photo fields (title, camera,
    lens, film, ...). New albums get an empty entry; your values are never
    overwritten,
  - writes gallery/gallery.json, read by the page. Do not edit it.

An album's date is worked out from the photos' EXIF dates (e.g. "June 2025")
unless you write one in albums.json, e.g. "Summer 2025".
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
ALBUM_FIELDS = {"title": "", "place": "", "date": "", "description": "", "cover": "", "photos": {}}

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
        info["taken"] = datetime.strptime(raw_date, "%Y:%m:%d %H:%M:%S").isoformat()
    except ValueError:
        pass

    return {k: v for k, v in info.items() if v}


def album_date(photos):
    """'18 June 2025', 'June 2025', 'May – June 2025' or 'December 2024 – January 2025'."""
    days = sorted(p["taken"][:10] for p in photos if p.get("taken"))
    if not days:
        return ""
    first, last = (datetime.fromisoformat(d) for d in (days[0], days[-1]))
    if first == last:
        return f"{first.day} {first:%B %Y}"
    if (first.year, first.month) == (last.year, last.month):
        return f"{first:%B %Y}"
    if first.year == last.year:
        return f"{first:%B} – {last:%B %Y}"
    return f"{first:%B %Y} – {last:%B %Y}"


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


def file_hash(path):
    return hashlib.sha1(path.read_bytes()).hexdigest()


def build_photo(src, album_id, overrides, previous):
    pid = src.stem
    thumb = THUMB_DIR / album_id / f"{pid}.jpg"
    digest = file_hash(src)
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
            copy.convert("RGB").save(thumb, "JPEG", quality=85, optimize=True, progressive=True)
            thumb_w, thumb_h = copy.size

    photo = {"id": pid, **exif, **{k: v for k, v in overrides.get(pid, {}).items() if v}}
    if photo.get("taken"):
        photo["date"] = photo["taken"][:10]
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
    if not FULL_DIR.is_dir():
        sys.exit(f"No photos folder at {FULL_DIR}")
    strip_gps()

    editable = json.loads(ALBUMS.read_text()) if ALBUMS.exists() else {}
    # thumbnails of unchanged photos are reused, keyed by the photo's path
    previous = {}
    if OUTPUT.exists():
        for album in json.loads(OUTPUT.read_text()):
            for p in album["photos"]:
                previous[ROOT.parent / unquote(p["src"])] = p
    albums, written = [], set()

    for category_dir in sorted(d for d in FULL_DIR.iterdir() if d.is_dir()):
        for album_dir in sorted(d for d in category_dir.iterdir() if d.is_dir()):
            album_id = slugify(album_dir.name)
            if any(a["id"] == album_id for a in albums):
                sys.exit(f"Two albums are both called '{album_dir.name}': rename one of them")

            # new albums get a stub to fill in; keys added later get their defaults
            meta = editable.setdefault(album_id, {})
            for key, default in ALBUM_FIELDS.items():
                meta.setdefault(key, album_dir.name if key == "title" else default)

            sources = [p for p in album_dir.iterdir() if p.suffix.lower() in EXTENSIONS]
            photos = [build_photo(src, album_id, meta["photos"], previous) for src in sources]
            if not photos:
                continue
            photos.sort(key=lambda p: (p.get("taken", "9999"), p["id"]))
            written |= {ROOT.parent / unquote(p["thumb"]) for p in photos}

            cover = next((p for p in photos if p["id"] == meta["cover"]), photos[0])
            dates = [p["taken"] for p in photos if p.get("taken")]
            albums.append({
                "id": album_id,
                "category": category_dir.name,
                "title": meta["title"],
                "place": meta["place"],
                "date": meta["date"] or album_date(photos),
                "description": meta["description"],
                "sortDate": max(dates) if dates else "",
                "cover": {k: cover[k] for k in ("thumb", "thumbWidth", "thumbHeight")},
                "photos": photos,
            })
            print(f"  {category_dir.name} / {meta['title']}: {len(photos)} photos")

        for loose in (p for p in category_dir.iterdir() if p.suffix.lower() in EXTENSIONS):
            print(f"  skipped {loose.relative_to(FULL_DIR)}: photos go inside an album folder")

    # remove thumbnails of photos or albums that no longer exist
    for path in sorted(THUMB_DIR.rglob("*"), reverse=True) if THUMB_DIR.exists() else []:
        if path.is_file() and path not in written:
            path.unlink()
        elif path.is_dir() and not any(path.iterdir()):
            path.rmdir()

    albums.sort(key=lambda a: a["sortDate"], reverse=True)
    ALBUMS.write_text(json.dumps(editable, indent=2, ensure_ascii=False) + "\n")
    OUTPUT.write_text(json.dumps(albums, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {len(albums)} albums to {OUTPUT.relative_to(ROOT.parent.parent)}")


if __name__ == "__main__":
    main()
