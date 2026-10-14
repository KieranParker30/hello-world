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
