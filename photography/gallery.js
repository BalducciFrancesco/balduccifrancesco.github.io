// Curated albums from gallery/albums.json, grouped by category in the order they are
// listed there. Each card opens the album's shared Amazon Photos folder.

const view = document.getElementById('view');
const emptyNote = document.querySelector('.gallery-empty');

const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
};

// "Copenhagen · June 2025"
const albumLine = (a) => [a.place, a.date].filter(Boolean).join(' · ');
const categoryId = (name) => name.toLowerCase().replace(/[^a-z0-9]+/g, '-');

/* Progressive reveal: once a card is on screen and its cover has loaded it joins
   a queue, and the queue shows one card at a time, in page order, a beat apart. */
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

function albumCard(album) {
    const card = el('a', 'album-card');
    card.href = album.url;
    card.target = '_blank';
    card.rel = 'noopener';

    const cover = el('div', 'album-cover');
    const img = el('img');
    img.src = `gallery/covers/${album.cover}`;
    img.alt = album.title;
    img.loading = 'lazy';
    img.decoding = 'async';
    cover.append(img);

    const info = el('div', 'album-info');
    const title = el('h4', 'album-title', album.title);
    title.append(el('span', 'album-link', '↗'));
    info.append(title);
    if (albumLine(album)) info.append(el('p', 'album-meta', albumLine(album)));

    card.append(cover, info);
    return card;
}

function render(albums) {
    const categories = new Map();
    albums.forEach((a) => categories.set(a.category, [...(categories.get(a.category) || []), a]));

    categories.forEach((list, name) => {
        const section = el('section', 'category');
        section.id = categoryId(name);
        const grid = el('div', 'album-grid');
        grid.append(...list.map(albumCard));
        section.append(el('h3', 'category-title', name), grid);
        view.append(section);
    });
    view.querySelectorAll('.album-card').forEach((card) => observer.observe(card));
}

fetch('gallery/albums.json')
    .then((res) => (res.ok ? res.json() : []))
    .catch(() => [])
    .then((albums) => {
        // an album shows up once it has both a link and a cover
        const ready = albums.filter((a) => a.url && a.cover);
        emptyNote.hidden = ready.length > 0;
        render(ready);
    });
