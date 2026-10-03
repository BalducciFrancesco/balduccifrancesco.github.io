import PhotoSwipeLightbox from 'https://cdn.jsdelivr.net/npm/photoswipe@5.4.4/dist/photoswipe-lightbox.esm.min.js';

const view = document.getElementById('view');
const intro = document.getElementById('intro');
const emptyNote = document.querySelector('.gallery-empty');

const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
};

// "1/250s · f/2.8 · ISO 400 · 35mm"
const settingsLine = (p) => [p.exposure, p.aperture, p.iso, p.focal].filter(Boolean).join(' · ');
// "Fujifilm X-T3 · XF35mmF2 R WR" or "Pentax Spotmatic F · Kodak Vision3 250D"
const gearLine = (p) => [p.camera, p.lens, p.film].filter(Boolean).join(' · ');
// "Copenhagen · June 2025"
const albumLine = (a) => [a.place, a.date].filter(Boolean).join(' · ');
const categoryId = (name) => name.toLowerCase().replace(/[^a-z0-9]+/g, '-');

const formatDate = (iso) => {
    if (!iso) return '';
    const date = new Date(iso + 'T00:00:00');
    return isNaN(date) ? iso : date.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
};

const thumbImg = ({ thumb, thumbWidth, thumbHeight }, alt) => {
    const img = el('img');
    img.src = thumb;
    img.width = thumbWidth;
    img.height = thumbHeight;
    img.alt = alt;
    img.loading = 'lazy';
    img.decoding = 'async';
    return img;
};

/* Progressive reveal: once an item is on screen and its image has loaded it joins
   a queue, and the queue shows one item at a time, in page order, a beat apart. */
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
    setTimeout(revealNext, 90);
}

const observer = new IntersectionObserver((entries) => {
    entries.filter((e) => e.isIntersecting).forEach(({ target }) => {
        observer.unobserve(target);
        const img = target.querySelector('img');
        const ready = () => {
            queue.push(target);
            if (!revealing) revealNext();
        };
        if (img.complete) ready();
        else {
            img.addEventListener('load', ready, { once: true });
            img.addEventListener('error', ready, { once: true });
        }
    });
}, { threshold: 0.1 });

const reveal = (nodes) => nodes.forEach((node) => observer.observe(node));

/* Index: albums grouped by category, most recent first */

function albumCard(album) {
    const card = el('a', 'album-card');
    card.href = `?album=${encodeURIComponent(album.id)}`;

    const cover = el('div', 'album-cover');
    cover.append(thumbImg(album.cover, album.title));

    const info = el('div', 'album-info');
    info.append(el('h4', 'album-title', album.title));
    if (albumLine(album)) info.append(el('p', 'album-meta', albumLine(album)));

    card.append(cover, info);
    return card;
}

function renderIndex(albums) {
    const categories = new Map();
    albums.forEach((a) => categories.set(a.category, [...(categories.get(a.category) || []), a]));

    categories.forEach((list, name) => {
        const section = el('section', 'category');
        section.id = categoryId(name);

        const heading = el('h3', 'category-title', name);

        const grid = el('div', 'album-grid');
        grid.append(...list.map(albumCard));
        section.append(heading, grid);
        view.append(section);
    });
    reveal([...view.querySelectorAll('.album-card')]);

    // sections are built after load, so the browser could not jump to #category itself
    if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView();
}

/* Album: header, justified grid, fullscreen viewer */

function captionFor(p, album) {
    const caption = el('div', 'photo-caption');
    if (p.title) caption.append(el('p', 'caption-title', p.title));
    if (settingsLine(p)) caption.append(el('p', 'caption-settings', settingsLine(p)));
    const where = [album.place, formatDate(p.date)].filter(Boolean).join(', ');
    const meta = [gearLine(p), where].filter(Boolean).join(' — ');
    if (meta) caption.append(el('p', 'caption-meta', meta));
    return caption;
}

function photoItem(p, album) {
    const link = el('a', 'fj-gallery-item');
    link.href = p.src;
    link.dataset.pswpWidth = p.width;
    link.dataset.pswpHeight = p.height;
    link.append(thumbImg(p, p.title || album.title), captionFor(p, album));
    if (settingsLine(p)) link.append(el('span', 'thumb-settings', settingsLine(p)));
    return link;
}

function renderAlbum(album) {
    document.title = `${album.title} - Francesco Balducci`;
    intro.hidden = true;

    // the toolbar arrow leads back to this album's category instead of the portfolio
    const back = document.querySelector('.back-link');
    back.href = `gallery.html#${categoryId(album.category)}`;
    back.setAttribute('aria-label', 'Back to all albums');

    const header = el('section', 'album-header');
    header.append(el('h2', 'album-heading', album.title));
    if (albumLine(album)) header.append(el('p', 'album-meta', albumLine(album)));
    if (album.description) header.append(el('p', 'album-description', album.description));

    const gallery = el('div', 'fj-gallery');
    gallery.id = 'gallery';
    gallery.append(...album.photos.map((p) => photoItem(p, album)));
    view.append(header, gallery);

    const small = window.innerWidth < 640;
    fjGallery(gallery, {
        itemSelector: '.fj-gallery-item',
        rowHeight: small ? 200 : 320,
        gutter: small ? 4 : 8,
        lastRow: 'left',
        transitionDuration: '0s',
    });
    reveal([...gallery.children]);
    initLightbox();
}

function initLightbox() {
    const lightbox = new PhotoSwipeLightbox({
        gallery: '#gallery',
        children: 'a',
        pswpModule: () => import('https://cdn.jsdelivr.net/npm/photoswipe@5.4.4/dist/photoswipe.esm.min.js'),
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

fetch('gallery/gallery.json')
    .then((res) => (res.ok ? res.json() : []))
    .catch(() => [])
    .then((albums) => {
        const wanted = new URLSearchParams(location.search).get('album');
        const album = albums.find((a) => a.id === wanted);
        emptyNote.hidden = albums.length > 0;
        if (album) renderAlbum(album);
        else renderIndex(albums);
    });
