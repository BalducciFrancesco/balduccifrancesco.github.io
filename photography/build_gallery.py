#!/usr/bin/env python3
"""Build the photo gallery from your original photos, which never leave your computer.

    pip install pillow
    python3 photography/build_gallery.py [originals_folder]

Originals live in photography/gallery/originals/ (git-ignored), or in any folder
you pass. One folder per album, one sub-folder per group inside it (an event,
a place...). Photos placed directly in an album folder are shown before its groups:

    originals/
        Parties/
            IntroFest/
                IMG_0001.jpg
            Chateau/
                ...
        Portraits/
            ...

For every photo the script writes, without any metadata (so no GPS):
    gallery/full/<album>/<group>/<name>.jpg     at most FULL_SIZE px, shown fullscreen
    gallery/thumbs/<album>/<group>/<name>.jpg   THUMB_HEIGHT px high, shown in the grid
The camera settings are read from the original first and stored in gallery.json.
Photos are shown in file-name order, so rename them (01.jpg, 02.jpg...) to reorder.

gallery/albums.json is yours to edit: the albums in page order, each with its
title, a one-line description shown on its card, a cover (a photo's file name),
and its groups in page order, each with a title, place and date. Dates are
year-month ("2026-08") or any text ("Summer 2026"); left empty, the month the
photos were taken is used. New albums and groups are added at the end, and your
values are never overwritten. Per-photo fields (title, camera, lens, film...)
go under the album: "photos": {"IMG_0001": {"title": "..."}}.

gallery/gallery.json is what the page reads. Do not edit it. Commit full/,
thumbs/, albums.json and gallery.json; the originals stay where they are.
"""

import json
import re
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

FULL_SIZE = 2400
THUMB_HEIGHT = 800
PREVIEW_FRAMES = 6
EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}

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


def save_copy(img, dest, size, src):
    """Write a metadata-free JPEG copy, unless one newer than the original exists."""
    if dest.exists() and dest.stat().st_mtime >= src.stat().st_mtime:
        with Image.open(dest) as done:
            return done.size
    copy = img.copy()
    copy.thumbnail(size, Image.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # only the colour profile is carried over; EXIF, GPS and XMP are dropped
    copy.convert("RGB").save(dest, "JPEG", quality=85, optimize=True, progressive=True,
                             icc_profile=img.info.get("icc_profile"))
    return copy.size


def build_photo(src, folder, overrides):
    pid = src.stem
    full = FULL_DIR / folder / f"{pid}.jpg"
    thumb = THUMB_DIR / folder / f"{pid}.jpg"
    with Image.open(src) as img:
        exif = read_exif(img)
        img = ImageOps.exif_transpose(img)  # bake rotation in, since the metadata is dropped
        width, height = save_copy(img, full, (FULL_SIZE, FULL_SIZE), src)
        thumb_w, thumb_h = save_copy(img, thumb, (THUMB_HEIGHT * 4, THUMB_HEIGHT), src)
    photo = {"id": pid, **exif, **{k: v for k, v in overrides.get(pid, {}).items() if v}}
    return photo | {
        "src": quote(full.relative_to(ROOT.parent).as_posix()),
        "width": width,
        "height": height,
        "thumb": quote(thumb.relative_to(ROOT.parent).as_posix()),
        "thumbWidth": thumb_w,
        "thumbHeight": thumb_h,
    }


def images_in(folder):
    return sorted((p for p in folder.iterdir() if p.suffix.lower() in EXTENSIONS), key=lambda p: p.name.lower())


def spread(items, count):
    """Pick `count` items spread evenly across the list."""
    if len(items) <= count:
        return items
    return [items[round(i * (len(items) - 1) / (count - 1))] for i in range(count)]


def main():
    originals = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else ROOT / "originals"
    if not originals.is_dir():
        sys.exit(f"No originals folder at {originals}")

    editable = json.loads(ALBUMS.read_text()) if ALBUMS.exists() else []
    album_dirs = {slugify(d.name): d for d in sorted(originals.iterdir()) if d.is_dir()}

    # new albums and groups get an entry at the end, to fill in and move where you want
    for album_id, album_dir in album_dirs.items():
        meta = next((a for a in editable if a.get("id") == album_id), None)
        if not meta:
            meta = {"id": album_id, "title": album_dir.name, "description": "", "cover": "", "groups": []}
            editable.append(meta)
        meta.setdefault("groups", [])
        for group_dir in sorted(d for d in album_dir.iterdir() if d.is_dir()):
            if not any(g.get("id") == slugify(group_dir.name) for g in meta["groups"]):
                meta["groups"].append({"id": slugify(group_dir.name), "title": group_dir.name, "place": "", "date": ""})

    albums = []
    for meta in editable:
        album_dir = album_dirs.get(meta.get("id"))
        if not album_dir:
            print(f"  albums.json lists '{meta.get('id')}' but {originals} has no folder for it")
            continue
        overrides = meta.get("photos", {})
        group_dirs = {slugify(d.name): d for d in album_dir.iterdir() if d.is_dir()}

        # photos straight in the album folder form a first, untitled group
        sections = [({"id": "", "title": "", "place": "", "date": ""}, album_dir)]
        sections += [(g, group_dirs[g["id"]]) for g in meta["groups"] if g.get("id") in group_dirs]

        groups = []
        for group, folder in sections:
            out_folder = f"{meta['id']}/{group['id']}" if group["id"] else meta["id"]
            photos = [build_photo(src, out_folder, overrides) for src in images_in(folder)]
            if not photos:
                continue
            months = sorted(p["date"] for p in photos if p.get("date"))
            groups.append({
                "title": group.get("title", ""),
                "place": group.get("place", ""),
                "date": group.get("date") or (months[0] if months else ""),
                "photos": photos,
            })
        if not groups:
            continue

        every = [p for g in groups for p in g["photos"]]
        cover_name = Path(meta.get("cover") or "").stem
        cover = next((p for p in every if p["id"] == cover_name), None)
        if cover_name and not cover:
            print(f"  {meta['title']}: cover '{meta['cover']}' is not in the album, using the first photo")
        cover = cover or every[0]
        # the hover preview: the cover, then photos spread across the groups
        others = [p for p in every if p is not cover]
        preview = [cover] + spread(others, PREVIEW_FRAMES - 1)

        albums.append({
            "id": meta["id"],
            "title": meta.get("title") or album_dir.name,
            "description": meta.get("description", ""),
            "count": len(every),
            "cover": {k: cover[k] for k in ("thumb", "thumbWidth", "thumbHeight")},
            "preview": [p["thumb"] for p in preview],
            "groups": groups,
        })
        print(f"  {albums[-1]['title']}: {len(every)} photos in {len(groups)} group(s)")

    # remove copies of photos, groups or albums that no longer exist
    written = {ROOT.parent / unquote(p[k]) for a in albums for g in a["groups"] for p in g["photos"] for k in ("src", "thumb")}
    for folder in (FULL_DIR, THUMB_DIR):
        for path in sorted(folder.rglob("*"), reverse=True) if folder.exists() else []:
            if path.is_file() and path not in written:
                path.unlink()
            elif path.is_dir() and not any(path.iterdir()):
                path.rmdir()

    ALBUMS.write_text(json.dumps(editable, indent=2, ensure_ascii=False) + "\n")
    OUTPUT.write_text(json.dumps(albums, indent=2, ensure_ascii=False) + "\n")
    size = sum(p.stat().st_size for p in FULL_DIR.rglob("*") if p.is_file()) / 1e6 if FULL_DIR.exists() else 0
    print(f"Wrote {len(albums)} albums to {OUTPUT.relative_to(ROOT.parent.parent)} ({size:.0f} MB of photos)")


if __name__ == "__main__":
    main()
