import PhotoSwipeLightbox from 'https://cdn.jsdelivr.net/npm/photoswipe@5.4.4/dist/photoswipe-lightbox.esm.min.js';

const gallery = document.getElementById('gallery');
const albumsNav = document.querySelector('.albums');
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

const formatDate = (iso) => {
    if (!iso) return '';
    const date = new Date(iso + 'T00:00:00');
    return isNaN(date) ? iso : date.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
};

function captionFor(p) {
    const caption = el('div', 'photo-caption');
    if (p.title) caption.append(el('p', 'caption-title', p.title));
    if (settingsLine(p)) caption.append(el('p', 'caption-settings', settingsLine(p)));
    const meta = [gearLine(p), formatDate(p.date)].filter(Boolean).join(' — ');
    if (meta) caption.append(el('p', 'caption-meta', meta));
    return caption;
}

function itemFor(p) {
    const link = el('a', 'fj-gallery-item');
    link.href = p.src;
    link.dataset.pswpWidth = p.width;
    link.dataset.pswpHeight = p.height;

    const img = el('img');
    img.src = p.thumb;
    img.width = p.thumbWidth;
    img.height = p.thumbHeight;
    img.alt = p.title || 'Photograph';
    img.loading = 'lazy';
    img.decoding = 'async';
    img.addEventListener('load', () => link.classList.add('is-loaded'), { once: true });
    if (img.complete) link.classList.add('is-loaded');

    link.append(img, captionFor(p));
    if (settingsLine(p)) link.append(el('span', 'thumb-settings', settingsLine(p)));
    return link;
}

function render(photos) {
    if (gallery.fjGallery) fjGallery(gallery, 'destroy');
    gallery.replaceChildren(...photos.map(itemFor));
    emptyNote.hidden = photos.length > 0;
    fjGallery(gallery, {
        itemSelector: '.fj-gallery-item',
        rowHeight: window.innerWidth < 640 ? 200 : 320,
        gutter: window.innerWidth < 640 ? 4 : 8,
        lastRow: 'left',
        transitionDuration: '0s',
    });
}

function renderAlbums(photos) {
    const albums = [...new Set(photos.map((p) => p.album).filter(Boolean))];
    if (albums.length < 2) return;

    const select = (button, album) => {
        albumsNav.querySelectorAll('button').forEach((b) => b.classList.toggle('active', b === button));
        render(album ? photos.filter((p) => p.album === album) : photos);
    };

    ['All', ...albums].forEach((name, i) => {
        const button = el('button', i === 0 ? 'album active' : 'album', name);
        button.type = 'button';
        button.addEventListener('click', () => select(button, i === 0 ? null : name));
        albumsNav.append(button);
    });
    albumsNav.hidden = false;
}

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

fetch('gallery/photos.json')
    .then((res) => (res.ok ? res.json() : []))
    .catch(() => [])
    .then((photos) => {
        renderAlbums(photos);
        render(photos);
    });
