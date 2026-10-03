# Francesco Balducci Portfolio

Minimalistic portfolio using plain old and simple **HTML**, **CSS**, and ~~JavaScript~~.

***Because sometimes less is more.***

## Photo gallery

`photography/gallery.html` lists albums grouped by category; each album opens as a justified grid ([fjGallery](https://github.com/nk-o/flickr-justified-gallery)) with a fullscreen viewer ([PhotoSwipe](https://photoswipe.com/)) that shows each photo's settings.

1. Commit photos to `photography/gallery/full/<Category>/<Album>/`, e.g. `full/Portraits/Anna in Nyhavn/IMG_0001.jpg`. They are shown as they are when opened fullscreen, so export them at the size you want people to see.
2. On push, the **Build photo gallery** GitHub Action (`.github/workflows/gallery.yml`) removes GPS data from the photos, makes the thumbnails, updates `gallery.json` and commits the result. Run `git pull` afterwards to get its commit.
3. Fill in `photography/gallery/albums.json` (new albums appear there after the first build): each album's `place`, and optionally `title`, `date` (worked out from EXIF when empty, e.g. "June 2025"), `description` and `cover` (a photo's file name without extension). Per-photo extras such as `title`, or `camera`/`film` for film scans without EXIF, go under `photos`: `{"scan01": {"film": "Kodak Vision3 250D"}}`. Pushing the edit rebuilds the gallery; your values are never overwritten.

The Action strips GPS from the photos it commits, but the copy you pushed first stays in git history, so turn location off when exporting if it matters. To build locally instead: `pip install pillow`, install [exiftool](https://exiftool.org/), then `python3 photography/build_gallery.py`.
