/* Advero Solutions shared behaviour. No libraries.
   - Logo fallback: any img[data-logo] that fails to load becomes a text wordmark.
   - Reveal on scroll: .fade and .rise get .is-in when they enter the viewport (delays via --d in CSS).
   - Header: .is-scrolled after the page moves; phone menu toggle (Escape or a tap outside closes it).
   - Loops: a [data-loop] element plays its [data-at] steps on repeat while visible and pauses off screen;
     [data-loop-start="ms"] sets the delay before its first frame.
   - prefers-reduced-motion: everything shows at once, loops rest on their final frame. */
(function () {
  'use strict';
  var doc = document;
  var root = doc.documentElement;
  root.classList.add('js');
  var reduceQuery = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
  var reduce = !!(reduceQuery && reduceQuery.matches);
  function each(sel, fn, scope) { Array.prototype.forEach.call((scope || doc).querySelectorAll(sel), fn); }

  /* ---------- Logo fallback ---------- */
  function toWordmark(img) {
    if (!img.parentNode) return;
    var kind = img.getAttribute('data-logo') || '';
    var src = img.getAttribute('src') || '';
    var mark = doc.createElement('span');
    var cls = ['wordmark'];
    if (kind === 'footer' || kind === 'white' || /white/.test(src) || img.closest('.ink-panel')) cls.push('wordmark--white');
    if (kind === 'stacked' || /stacked/.test(src)) cls.push('wordmark--stacked');
    if (kind === 'mark' || /mark-/.test(src)) cls.push('wordmark--mark');
    mark.className = cls.join(' ');
    mark.setAttribute('role', 'img');
    mark.setAttribute('aria-label', img.getAttribute('alt') || 'Advero Solutions');
    mark.innerHTML = '<b aria-hidden="true">Advero</b><span aria-hidden="true">Solutions</span>';
    img.parentNode.replaceChild(mark, img);
  }
  each('img[data-logo]', function (img) {
    if (img.complete && img.naturalWidth === 0 && img.naturalHeight === 0) {
      /* finished loading with nothing to show: confirm with a probe (some SVGs report 0 size) */
      var probe = new Image();
      probe.onerror = function () { toWordmark(img); };
      probe.src = img.currentSrc || img.src;
    } else {
      img.addEventListener('error', function () { toWordmark(img); }, { once: true });
    }
  });

  /* ---------- Reveal on scroll ---------- */
  var revealEls = doc.querySelectorAll('.fade, .rise');
  if (reduce || !('IntersectionObserver' in window)) {
    each('.fade, .rise', function (el) { el.classList.add('is-in'); });
  } else {
    var revealer = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add('is-in'); revealer.unobserve(e.target); }
      });
    }, { threshold: 0, rootMargin: '0px 0px -10% 0px' });
    Array.prototype.forEach.call(revealEls, function (el) { revealer.observe(el); });
  }
  /* A link from another page to an id inside a not-yet-revealed .rise/.fade (the agent cards) would land on the
     transformed box and end up off by the reveal offset: reveal that one at once and scroll to it again. */
  (function () {
    var id = location.hash ? location.hash.slice(1) : '';
    var target = null;
    try { target = id && doc.getElementById(decodeURIComponent(id)); } catch (err) { target = null; }
    var wrap = target && target.closest('.rise, .fade');
    if (!wrap || wrap.classList.contains('is-in')) return;
    wrap.style.transition = 'none';
    wrap.classList.add('is-in');
    void wrap.offsetWidth;
    wrap.style.transition = '';
    target.scrollIntoView({ block: 'start', behavior: 'instant' });
  })();

  /* ---------- Header state ---------- */
  var header = doc.querySelector('.site-header');
  if (header) {
    var onScroll = function () { header.classList.toggle('is-scrolled', window.scrollY > 8); };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });

    /* phone menu */
    var toggle = header.querySelector('.nav__toggle');
    var links = header.querySelector('.nav__links');
    var setMenu = function (open) {
      header.classList.toggle('menu-open', open);
      if (toggle) {
        toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
        toggle.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
      }
    };
    if (toggle && links) {
      toggle.addEventListener('click', function () { setMenu(!header.classList.contains('menu-open')); });
      each('a', function (a) { a.addEventListener('click', function () { setMenu(false); }); }, links);
      /* a tap anywhere outside the header bar and its menu closes the menu */
      var nav = toggle.closest('.nav') || header;
      doc.addEventListener('click', function (e) {
        if (header.classList.contains('menu-open') && !nav.contains(e.target)) setMenu(false);
      });
      window.addEventListener('resize', function () { if (window.innerWidth > 960) setMenu(false); });
    }

    doc.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && header.classList.contains('menu-open')) { setMenu(false); if (toggle) toggle.focus(); }
    });
  }

  /* ---------- Mockup loops ---------- */
  each('[data-loop]', function (stage) {
    var parts = stage.querySelectorAll('[data-at]');
    var counters = stage.querySelectorAll('[data-count-to]');
    var durations = (stage.getAttribute('data-loop') || '900,1300,1500,1500,1600,1500,3400')
      .split(',').map(function (n) { return parseInt(n, 10) || 1000; });
    var last = durations.length - 1;
    var startDelay = parseInt(stage.getAttribute('data-loop-start'), 10);
    if (!(startDelay >= 0)) startDelay = 900;
    var step = -1;

    function render(n) {
      Array.prototype.forEach.call(parts, function (el) {
        var at = parseInt(el.getAttribute('data-at'), 10);
        var until = el.hasAttribute('data-until') ? parseInt(el.getAttribute('data-until'), 10) : Infinity;
        el.classList.toggle('is-on', n >= at && n < until);
      });
      Array.prototype.forEach.call(counters, function (el) {
        var at = parseInt(el.getAttribute('data-count-at'), 10);
        var value = n >= at ? el.getAttribute('data-count-to') : el.getAttribute('data-count-from');
        if (el.textContent !== value) {
          el.textContent = value;
          if (n === at && !reduce) {
            var bump = el.closest('.ui-tile__num') || el;
            bump.classList.add('is-bump');
            setTimeout(function () { bump.classList.remove('is-bump'); }, 450);
          }
        }
      });
    }

    if (reduce || !('IntersectionObserver' in window)) { render(last); return; }

    var visible = false;
    var timer = null;
    function tick() {
      timer = null;
      if (!visible || doc.hidden) return;
      step = step >= last ? 0 : step + 1;
      render(step);
      timer = setTimeout(tick, durations[step]);
    }
    function resume() { if (!timer && visible && !doc.hidden) timer = setTimeout(tick, step < 0 ? startDelay : 400); }
    render(0);
    new IntersectionObserver(function (entries) {
      visible = entries[0].isIntersecting;
      if (visible) resume(); else if (timer) { clearTimeout(timer); timer = null; }
    }, { threshold: 0.15 }).observe(stage);
    doc.addEventListener('visibilitychange', resume);
  });

  if (reduceQuery && reduceQuery.addEventListener) {
    reduceQuery.addEventListener('change', function (e) {
      if (e.matches) each('.fade, .rise', function (el) { el.classList.add('is-in'); });
    });
  }
})();
