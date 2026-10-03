# Francesco Balducci Portfolio

Minimalistic portfolio using plain old and simple **HTML**, **CSS**, and ~~JavaScript~~.

***Because sometimes less is more.***

## Photo gallery

`photography/gallery.html` is a justified grid ([fjGallery](https://github.com/nk-o/flickr-justified-gallery)) with a fullscreen viewer ([PhotoSwipe](https://photoswipe.com/)) that shows each photo's settings.

1. Put full-resolution JPEGs in `photography/gallery/originals/` (git-ignored).
2. Run `pip install pillow && python3 photography/build_gallery.py`.
3. Optionally edit `photography/gallery/photos.json` to add a `title`, `album` (filter chips appear once there are two albums), or `camera`/`lens`/`film` for film scans that have no EXIF. Hand edits survive later runs.
4. Commit `photos.json` together with `gallery/full/` and `gallery/thumbs/`. Their metadata is stripped, so GPS location is never published.
