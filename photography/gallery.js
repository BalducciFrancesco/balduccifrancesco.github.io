// Albums from gallery/gallery.json (built by build_gallery.py), in albums.json order.
// gallery.html shows the album cards; gallery.html?album=<id> shows one album, its photos
// in groups (an event, a place...). Moving between albums happens in place, without
// reloading the page, so it is instant.

// The fullscreen viewer loads on its own: if the CDN is unreachable the grid still works,
// and a click simply opens the photo.
const PHOTOSWIPE = 'https://cdn.jsdelivr.net/npm/photoswipe@5.4.4/dist/photoswipe.esm.min.js';
const lightboxModule = import('https://cdn.jsdelivr.net/npm/photoswipe@5.4.4/dist/photoswipe-lightbox.esm.min.js')
    .then((m) => m.default)
    .catch(() => null);

const view = document.getElementById('view');
const intro = document.getElementById('intro');
const tabs = document.getElementById('album-tabs');
const back = document.querySelector('.back-link');
const emptyNote = document.querySelector('.gallery-empty');

let albums = [];
let lightbox = null;

const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
};

// "1/250s · f/2.8 · ISO 400 · 35mm"
const settingsLine = (p) => [p.exposure, p.aperture, p.iso, p.focal].filter(Boolean).join(' · ');
// "Canon EOS 5D Mark III · EF50mm f/1.8 STM" or "Pentax Spotmatic F · Kodak Vision3 250D"
const gearLine = (p) => [p.camera, p.lens, p.film].filter(Boolean).join(' · ');
// "2025-06" -> "June 2025"
const formatMonth = (yearMonth) => {
    const [year, month] = (yearMonth || '').split('-').map(Number);
    if (!year || !month) return yearMonth || '';
    return new Date(year, month - 1).toLocaleDateString('en-GB', { month: 'long', year: 'numeric' });
};
const albumUrl = (album) => (album ? `?album=${encodeURIComponent(album.id)}` : 'gallery.html');
// "DTU · August 2026"; a date that is not year-month ("Summer 2026") is shown as written
const groupLine = (g) => [g.place, /^\d{4}-\d{2}$/.test(g.date || '') ? formatMonth(g.date) : g.date].filter(Boolean).join(' · ');
const allPhotos = (album) => album.groups.flatMap((g) => g.photos);

// Groups are shown newest first: by their year-month date, or by their latest photo when
// the date is free text ("Summer 2026"). Photos outside any group stay on top.
const groupMonth = (g) => (/^\d{4}-\d{2}$/.test(g.date || '') ? g.date : g.photos.map((p) => p.date || '').sort().at(-1) || '');
const newestFirst = (a, b) => (!a.title - !b.title) * -1 || groupMonth(b).localeCompare(groupMonth(a));

const thumbImg = ({ thumb, thumbWidth, thumbHeight }, alt, eager) => {
    const img = el('img');
    img.src = thumb;
    img.width = thumbWidth;
    img.height = thumbHeight;
    img.alt = alt;
    img.loading = eager ? 'eager' : 'lazy';
    img.decoding = 'async';
    return img;
};

/* Progressive reveal: once an item is on screen and its image has loaded it joins a
   queue that shows one item at a time, in page order, a beat apart. Images already in
   the browser cache (a revisited or prefetched album) appear at once, so moving back
   and forth between albums never waits on the animation. */
const queue = [];
let revealing = false;

function revealNext() {
    queue.sort((a, b) => (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1));
    const node = queue.shift();
    if (!node) {
        revealing = false;
        return;
    }
    node.classList.add('is-visible');
    revealing = true;
    setTimeout(revealNext, 60);
}

const observer = new IntersectionObserver((entries) => {
    entries.filter((e) => e.isIntersecting).forEach(({ target }) => {
        observer.unobserve(target);
        const img = target.querySelector('img');
        if (img.complete && img.naturalWidth) {
            target.classList.add('is-visible');
            return;
        }
        const ready = () => {
            queue.push(target);
            if (!revealing) revealNext();
        };
        img.addEventListener('load', ready, { once: true });
        img.addEventListener('error', ready, { once: true });
    });
}, { threshold: 0.05 });

function reveal(nodes) {
    observer.disconnect();
    queue.length = 0;
    nodes.forEach((node) => observer.observe(node));
}

/* Background loading, so the next album is ready before it is opened */

const prefetched = new Set();
function prefetch(album, count = 12) {
    allPhotos(album).slice(0, count).forEach(({ thumb }) => {
        if (prefetched.has(thumb)) return;
        prefetched.add(thumb);
        const img = new Image();
        img.fetchPriority = 'low';
        img.src = thumb;
    });
}
const whenIdle = (fn) => (window.requestIdleCallback ? requestIdleCallback(fn, { timeout: 2000 }) : setTimeout(fn, 800));

/* Index: one large card per album. Hovering a card (or, on touch screens, scrolling it
   into view) plays its photos like stories, to invite a click. */

const STORY_FRAME_MS = 1300;

function story(card, album) {
    const cover = card.querySelector('.album-cover');
    const bars = card.querySelector('.story-bars');
    let frames = null;
    let timer = null;
    let index = 0;

    const show = (i) => {
        index = i;
        frames.forEach((f, k) => f.classList.toggle('active', k === i));
        [...bars.children].forEach((bar, k) => {
            bar.classList.toggle('done', k < i);
            bar.classList.toggle('playing', k === i);
        });
    };

    const play = () => {
        if (timer || album.preview.length < 2) return;
        if (!frames) {
            // the first frame is the cover already on the card; the others are created on first play
            frames = [cover.querySelector('img'), ...album.preview.slice(1).map((src) => {
                const img = el('img', 'story-frame');
                img.src = src;
                img.alt = '';
                img.decoding = 'async';
                cover.append(img);
                return img;
            })];
        }
        card.classList.add('is-playing');
        show(0);
        timer = setInterval(() => show((index + 1) % frames.length), STORY_FRAME_MS);
    };

    const stop = () => {
        clearInterval(timer);
        timer = null;
        card.classList.remove('is-playing');
        if (frames) show(0);
    };

    return { play, stop };
}

const touchOnly = window.matchMedia('(hover: none)').matches;
const storyViewer = new IntersectionObserver((entries) => {
    entries.forEach(({ target, isIntersecting }) => (isIntersecting ? target.story.play() : target.story.stop()));
}, { threshold: 0.7 });

function albumCard(album) {
    const card = el('a', 'album-card');
    card.href = albumUrl(album);

    const cover = el('div', 'album-cover');
    const img = thumbImg(album.cover, album.title, true);
    img.classList.add('story-frame', 'active');
    const bars = el('div', 'story-bars');
    album.preview.forEach(() => bars.append(el('span')));
    bars.style.setProperty('--frame', `${STORY_FRAME_MS}ms`);
    cover.append(img, bars);

    const info = el('div', 'album-info');
    info.append(el('h3', 'album-title', album.title));
    if (album.description) info.append(el('p', 'album-card-description', album.description));
    const cta = el('span', 'album-cta', `View ${album.count} photos`);
    cta.append(el('span', 'album-cta-arrow', '→'));
    info.append(cta);

    card.append(cover, info);
    card.story = story(card, album);
    if (touchOnly) storyViewer.observe(card);
    card.addEventListener('pointerenter', () => {
        prefetch(album);
        card.story.play();
    });
    card.addEventListener('pointerleave', () => card.story.stop());
    return card;
}

function renderIndex() {
    document.title = 'Francesco Balducci - Photography';
    intro.hidden = false;
    tabs.hidden = true;
    back.href = '../index.html';
    back.setAttribute('aria-label', 'Back to portfolio');
    lightbox?.destroy();
    lightbox = null;

    const grid = el('div', 'album-grid');
    // even rows: four albums sit 2 x 2, otherwise up to three across
    grid.style.setProperty('--cols', albums.length === 4 ? 2 : Math.min(albums.length, 3));
    grid.append(...albums.map(albumCard));
    view.replaceChildren(grid);
    reveal([...grid.children]);
    // the story frames and each album's first photos, so hovering and opening feel instant
    whenIdle(() => albums.forEach((a) => {
        a.preview.forEach((src) => { new Image().src = src; });
        prefetch(a, 8);
    }));
}

/* Album: tabs to every album, justified grid, fullscreen viewer */

function captionFor(p, group) {
    const caption = el('div', 'photo-caption');
    const title = [p.title, group.title].filter(Boolean).join(' — ');
    if (title) caption.append(el('p', 'caption-title', title));
    if (settingsLine(p)) caption.append(el('p', 'caption-settings', settingsLine(p)));
    const meta = [gearLine(p), formatMonth(p.date)].filter(Boolean).join(' — ');
    if (meta) caption.append(el('p', 'caption-meta', meta));
    return caption;
}

function photoTile(p, album, group, index) {
    const link = el('a', 'photo-tile');
    link.href = p.src;
    link.dataset.pswpWidth = p.width;
    link.dataset.pswpHeight = p.height;
    link.ratio = p.width / p.height;
    link.style.setProperty('--ratio', link.ratio);
    link.append(thumbImg(p, p.title || group.title || album.title, index < 8), captionFor(p, group));
    if (settingsLine(p)) link.append(el('span', 'thumb-settings', settingsLine(p)));
    return link;
}

/* Balanced justified rows: each group is split into as many rows as its photos need at
   the target height, choosing the breaks so every row spans the full width (the last one
   included), each at its own height. Redone whenever the grid's width changes. */

const targetRowHeight = () => (window.innerWidth < 640 ? 180 : 260);

// Split values into k consecutive runs whose sums are as even as possible.
function partition(values, k) {
    const n = values.length;
    const prefix = [0];
    values.forEach((v) => prefix.push(prefix.at(-1) + v));
    const ideal = prefix[n] / k;
    const cost = (i, j) => (prefix[j] - prefix[i] - ideal) ** 2;
    const best = Array.from({ length: k + 1 }, () => new Array(n + 1).fill(Infinity));
    const cut = Array.from({ length: k + 1 }, () => new Array(n + 1).fill(0));
    best[0][0] = 0;
    for (let rows = 1; rows <= k; rows++) {
        for (let end = rows; end <= n; end++) {
            for (let start = rows - 1; start < end; start++) {
                const total = best[rows - 1][start] + cost(start, end);
                if (total < best[rows][end]) {
                    best[rows][end] = total;
                    cut[rows][end] = start;
                }
            }
        }
    }
    const runs = [];
    for (let rows = k, end = n; rows > 0; rows--) {
        const start = cut[rows][end];
        runs.unshift([start, end]);
        end = start;
    }
    return runs;
}

function layoutRows(grid) {
    const width = grid.clientWidth;
    if (!width || width === grid.laidOutWidth) return;
    grid.laidOutWidth = width;

    const gap = parseFloat(getComputedStyle(grid).rowGap) || 0;
    const ratios = grid.tiles.map((t) => t.ratio);
    const total = ratios.reduce((a, b) => a + b, 0);
    const count = Math.min(ratios.length, Math.max(1, Math.round((total * targetRowHeight()) / width)));
    // a row of one or two tall photos would grow huge at full width; cap it near the screen height
    const maxHeight = window.innerHeight * 0.8;

    grid.replaceChildren(...partition(ratios, count).map(([start, end]) => {
        const row = el('div', 'photo-row');
        const sum = ratios.slice(start, end).reduce((a, b) => a + b, 0);
        const gaps = gap * (end - start - 1);
        if ((width - gaps) / sum > maxHeight) row.style.maxWidth = `${maxHeight * sum + gaps}px`;
        row.append(...grid.tiles.slice(start, end));
        return row;
    }));
}

const rowsObserver = new ResizeObserver((entries) => entries.forEach(({ target }) => layoutRows(target)));

function renderTabs(current) {
    tabs.replaceChildren(...albums.map((album) => {
        const tab = el('a', album === current ? 'album-tab active' : 'album-tab', album.title);
        tab.href = albumUrl(album);
        if (album === current) tab.setAttribute('aria-current', 'page');
        tab.addEventListener('pointerenter', () => prefetch(album), { once: true });
        return tab;
    }));
    tabs.hidden = false;
    tabs.querySelector('.active')?.scrollIntoView({ block: 'nearest', inline: 'center' });
}

function renderAlbum(album) {
    document.title = `${album.title} - Francesco Balducci`;
    intro.hidden = true;
    back.href = 'gallery.html';
    back.setAttribute('aria-label', 'Back to all albums');
    renderTabs(album);

    const header = el('section', 'album-header');
    header.append(el('h2', 'album-heading', album.title));
    if (album.description) header.append(el('p', 'album-description', album.description));

    // one gallery element around every group, so the fullscreen viewer swipes through the whole album
    const gallery = el('div', 'album-groups');
    gallery.id = 'gallery';
    let index = 0;
    album.groups.forEach((group) => {
        const section = el('section', 'photo-group');
        if (group.title) {
            const heading = el('header', 'group-header');
            heading.append(el('h3', 'group-title', group.title));
            if (groupLine(group)) heading.append(el('p', 'group-meta', groupLine(group)));
            section.append(heading);
        }
        const grid = el('div', 'photo-grid');
        grid.tiles = group.photos.map((p) => photoTile(p, album, group, index++));
        grid.append(...grid.tiles);
        rowsObserver.observe(grid);
        section.append(grid);
        gallery.append(section);
    });
    view.replaceChildren(header, gallery);

    reveal([...gallery.querySelectorAll('.photo-tile')]);
    initLightbox();
    // get the neighbouring albums ready, so the next tab opens instantly
    whenIdle(() => albums.filter((a) => a !== album).forEach((a) => prefetch(a)));
}

async function initLightbox() {
    const PhotoSwipeLightbox = await lightboxModule;
    lightbox?.destroy();
    lightbox = null;
    if (!PhotoSwipeLightbox || !document.getElementById('gallery')) return;
    lightbox = new PhotoSwipeLightbox({
        gallery: '#gallery',
        children: 'a.photo-tile',
        pswpModule: () => import(PHOTOSWIPE),
        preload: [1, 2],
        bgOpacity: 1,
        showHideAnimationType: 'zoom',
        imageClickAction: 'close',
        tapAction: 'toggle-controls',
        zoom: false,
        padding: { top: 40, bottom: 110, left: 16, right: 16 },
    });

    // Show the hidden .photo-caption of the current slide under the image
    lightbox.on('uiRegister', () => {
        lightbox.pswp.ui.registerElement({
            name: 'exif-caption',
            order: 9,
            isButton: false,
            appendTo: 'root',
            onInit: (node, pswp) => {
                pswp.on('change', () => {
                    const caption = pswp.currSlide.data.element?.querySelector('.photo-caption');
                    node.replaceChildren(...(caption ? [caption.cloneNode(true)] : []));
                });
            },
        });
    });
    lightbox.init();
}

/* Navigation inside the page: album links swap the view instead of reloading */

function show() {
    const id = new URLSearchParams(location.search).get('album');
    const album = albums.find((a) => a.id === id);
    if (album) renderAlbum(album);
    else renderIndex();
}

document.addEventListener('click', (event) => {
    const link = event.target.closest('a.album-card, a.album-tab, a.back-link[href="gallery.html"]');
    if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    history.pushState(null, '', link.getAttribute('href'));
    window.scrollTo(0, 0);
    show();
});
window.addEventListener('popstate', show);

fetch('gallery/gallery.json')
    .then((res) => (res.ok ? res.json() : []))
    .catch(() => [])
    .then((data) => {
        albums = data;
        albums.forEach((album) => album.groups.sort(newestFirst));
        emptyNote.hidden = albums.length > 0;
        show();
        // load the fullscreen viewer early, so the first photo opens without a delay
        whenIdle(() => import(PHOTOSWIPE).catch(() => {}));
    });
