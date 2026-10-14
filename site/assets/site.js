(function () {
  var header = document.querySelector('.site-header');
  function onScroll() { if (header) header.classList.toggle('is-scrolled', window.scrollY > 8); }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  // Mega menus: hover on pointer devices, click/keyboard everywhere
  var items = document.querySelectorAll('.nav-item[data-mega]');
  function closeAll(except) {
    items.forEach(function (i) {
      if (i !== except) { i.classList.remove('is-open'); var b = i.querySelector('.nav-link'); if (b) b.setAttribute('aria-expanded', 'false'); }
    });
  }
  items.forEach(function (item) {
    var btn = item.querySelector('.nav-link');
    var t;
    btn.addEventListener('click', function () {
      var open = !item.classList.contains('is-open');
      closeAll(item);
      item.classList.toggle('is-open', open);
      btn.setAttribute('aria-expanded', String(open));
    });
    item.addEventListener('mouseenter', function () { if (matchMedia('(hover: hover)').matches) { clearTimeout(t); closeAll(item); item.classList.add('is-open'); btn.setAttribute('aria-expanded', 'true'); } });
    item.addEventListener('mouseleave', function () { if (matchMedia('(hover: hover)').matches) { t = setTimeout(function () { item.classList.remove('is-open'); btn.setAttribute('aria-expanded', 'false'); }, 160); } });
  });
  document.addEventListener('click', function (e) { if (!e.target.closest('.nav-item')) closeAll(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') { closeAll(); closeDrawer(); } });

  // Mobile drawer
  var drawer = document.querySelector('.drawer');
  function openDrawer() { if (!drawer) return; drawer.classList.add('is-open'); document.body.style.overflow = 'hidden'; }
  function closeDrawer() { if (!drawer) return; drawer.classList.remove('is-open'); document.body.style.overflow = ''; }
  document.querySelectorAll('[data-drawer-open]').forEach(function (b) { b.addEventListener('click', openDrawer); });
  document.querySelectorAll('[data-drawer-close]').forEach(function (b) { b.addEventListener('click', closeDrawer); });

  // Reveal on scroll
  var els = document.querySelectorAll('.reveal');
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { if (en.isIntersecting) { en.target.classList.add('is-in'); io.unobserve(en.target); } });
    }, { rootMargin: '0px 0px -8% 0px' });
    els.forEach(function (el) { io.observe(el); });
  } else { els.forEach(function (el) { el.classList.add('is-in'); }); }

  // Table-of-contents highlighting
  var tocLinks = document.querySelectorAll('.toc a');
  if (tocLinks.length && 'IntersectionObserver' in window) {
    var map = {};
    tocLinks.forEach(function (a) { map[a.getAttribute('href').slice(1)] = a; });
    var tio = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { tocLinks.forEach(function (a) { a.classList.remove('is-active'); }); var a = map[en.target.id]; if (a) a.classList.add('is-active'); }
      });
    }, { rootMargin: '-20% 0px -70% 0px' });
    Object.keys(map).forEach(function (id) { var h = document.getElementById(id); if (h) tio.observe(h); });
  }

  // Search panel → chalet finder with query string
  document.querySelectorAll('form[data-search]').forEach(function (f) {
    f.addEventListener('submit', function (e) {
      e.preventDefault();
      var q = new URLSearchParams(new FormData(f));
      Array.from(q.keys()).forEach(function (k) { if (!q.get(k)) q.delete(k); });
      window.location.href = f.getAttribute('action') + (q.toString() ? '?' + q.toString() : '');
    });
  });
})();

// Chalet photo lightbox
(function () {
  var lb = document.querySelector('.lightbox');
  if (!lb) return;
  var slides = lb.querySelectorAll('[data-slide]'), count = lb.querySelector('.lb-count'), i = 0, last;
  function show(n) {
    i = (n + slides.length) % slides.length;
    slides.forEach(function (s, k) {
      s.classList.toggle('is-active', k === i);
      if (Math.abs(k - i) <= 1 || k === (i + 1) % slides.length) { var im = s.querySelector('img'); if (im.dataset.src) { im.src = im.dataset.src; im.removeAttribute('data-src'); } }
    });
    count.textContent = (i + 1) + ' / ' + slides.length;
  }
  function open(n) { last = document.activeElement; lb.hidden = false; document.body.style.overflow = 'hidden'; show(n); lb.querySelector('.lb-close').focus(); }
  function close() { lb.hidden = true; document.body.style.overflow = ''; if (last) last.focus(); }
  document.querySelectorAll('[data-lightbox-open]').forEach(function (b) { b.addEventListener('click', function () { open(+b.dataset.lightboxOpen); }); });
  lb.querySelector('[data-lightbox-close]').addEventListener('click', close);
  lb.querySelector('[data-lightbox-prev]').addEventListener('click', function () { show(i - 1); });
  lb.querySelector('[data-lightbox-next]').addEventListener('click', function () { show(i + 1); });
  lb.addEventListener('click', function (e) { if (e.target === lb || e.target.classList.contains('lb-stage')) close(); });
  document.addEventListener('keydown', function (e) {
    if (lb.hidden) return;
    if (e.key === 'Escape') close(); if (e.key === 'ArrowLeft') show(i - 1); if (e.key === 'ArrowRight') show(i + 1);
  });
  var x0 = null;
  lb.addEventListener('touchstart', function (e) { x0 = e.touches[0].clientX; }, { passive: true });
  lb.addEventListener('touchend', function (e) { if (x0 === null) return; var dx = e.changedTouches[0].clientX - x0; if (Math.abs(dx) > 40) show(i + (dx < 0 ? 1 : -1)); x0 = null; });
})();
