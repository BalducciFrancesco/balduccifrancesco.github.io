#!/usr/bin/env python3
"""Build the photo gallery: resize originals, read their EXIF, write photos.json.

Usage:
    pip install pillow
    python3 photography/build_gallery.py [originals_dir]

Drop full-resolution JPEGs into photography/gallery/originals/ (git-ignored),
then run this script. For each photo it writes:
    gallery/full/<name>.jpg   long edge <= FULL_SIZE, shown in the lightbox
    gallery/thumbs/<name>.jpg height <= THUMB_HEIGHT, shown in the grid
Both copies are re-encoded without metadata, so GPS data never gets published.

photos.json is merged, not overwritten: fields you add or edit by hand
(title, album, camera, lens, film, ...) are kept on the next run, and EXIF
only fills the fields that are still empty. That is also how film scans,
which have no EXIF, get their details. Photos are listed newest first;
entries whose original was removed are dropped.
"""

import json
import sys
from datetime import datetime
from fractions import Fraction
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent / "gallery"
FULL_DIR = ROOT / "full"
THUMB_DIR = ROOT / "thumbs"
MANIFEST = ROOT / "photos.json"

FULL_SIZE = 2400
THUMB_HEIGHT = 600
EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}

# EXIF tag ids
MAKE, MODEL, DATETIME = 0x010F, 0x0110, 0x0132
EXIF_IFD = 0x8769
EXPOSURE, FNUMBER, ISO, DATETIME_ORIGINAL = 0x829A, 0x829D, 0x8827, 0x9003
FOCAL, FOCAL_35MM, LENS_MAKE, LENS_MODEL = 0x920A, 0xA405, 0xA433, 0xA434


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
        info["date"] = datetime.strptime(raw_date, "%Y:%m:%d %H:%M:%S").strftime("%Y-%m-%d")
    except ValueError:
        pass

    return {k: v for k, v in info.items() if v}


def save_resized(img, dest, size):
    copy = img.copy()
    copy.thumbnail(size, Image.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # no exif= argument, so the output carries no metadata at all
    copy.convert("RGB").save(dest, "JPEG", quality=85, optimize=True, progressive=True)
    return copy.size


def main():
    originals = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "originals"
    if not originals.is_dir():
        sys.exit(f"No originals folder at {originals}")

    existing = {}
    if MANIFEST.exists():
        existing = {p["id"]: p for p in json.loads(MANIFEST.read_text())}

    photos = []
    sources = sorted(p for p in originals.iterdir() if p.suffix.lower() in EXTENSIONS)
    for src in sources:
        pid = src.stem
        with Image.open(src) as img:
            exif = read_exif(img)
            img = ImageOps.exif_transpose(img)  # bake rotation in, since the metadata is dropped
            width, height = save_resized(img, FULL_DIR / f"{pid}.jpg", (FULL_SIZE, FULL_SIZE))
            thumb_w, thumb_h = save_resized(img, THUMB_DIR / f"{pid}.jpg", (THUMB_HEIGHT * 4, THUMB_HEIGHT))

        entry = {"id": pid, "title": "", "album": ""}
        entry.update(exif)
        entry.update({k: v for k, v in existing.get(pid, {}).items() if v})  # hand edits win
        entry.update({
            "src": f"gallery/full/{pid}.jpg",
            "width": width,
            "height": height,
            "thumb": f"gallery/thumbs/{pid}.jpg",
            "thumbWidth": thumb_w,
            "thumbHeight": thumb_h,
        })
        photos.append(entry)
        print(f"  {pid}: {width}x{height}  " + " · ".join(str(exif.get(k, "")) for k in ("exposure", "aperture", "iso")))

    for pid in existing.keys() - {p["id"] for p in photos}:
        for folder in (FULL_DIR, THUMB_DIR):
            (folder / f"{pid}.jpg").unlink(missing_ok=True)

    photos.sort(key=lambda p: (p.get("date", ""), p["id"]), reverse=True)
    MANIFEST.write_text(json.dumps(photos, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {len(photos)} photos to {MANIFEST.relative_to(ROOT.parent.parent)}")


if __name__ == "__main__":
    main()
