# Francesco Balducci Portfolio

Minimalistic portfolio using plain old and simple **HTML**, **CSS**, and ~~JavaScript~~.

***Because sometimes less is more.***

## Photo gallery

`photography/gallery.html` lists albums grouped by category; each album opens as a justified grid ([fjGallery](https://github.com/nk-o/flickr-justified-gallery)) with a fullscreen viewer ([PhotoSwipe](https://photoswipe.com/)) that shows each photo's settings.

1. Put full-resolution photos in `photography/gallery/originals/<Category>/<Album>/` (git-ignored), e.g. `originals/Portraits/Anna in Nyhavn/IMG_0001.jpg`.
2. Run `pip install pillow && python3 photography/build_gallery.py`.
3. Fill in `photography/gallery/albums.json`: each album's `place`, and optionally `title`, `date` (worked out from EXIF when empty, e.g. "June 2025"), `description` and `cover` (a photo's file name without extension). Per-photo extras such as `title`, or `camera`/`film` for film scans without EXIF, go under `photos`: `{"scan01": {"film": "Kodak Vision3 250D"}}`. Run the script again after editing; it never overwrites what you wrote.
4. Commit `albums.json`, `gallery.json`, `gallery/full/` and `gallery/thumbs/`. Their metadata is stripped, so GPS location is never published.
