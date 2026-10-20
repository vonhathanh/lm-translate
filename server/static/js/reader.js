(function () {
  var d = document.documentElement, KEY = 'reader';
  function load() { try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { return {}; } }
  function save(s) { try { localStorage.setItem(KEY, JSON.stringify(s)); } catch (e) {} }
  var state = load();
  var size = state.size || parseInt(getComputedStyle(d).getPropertyValue('--read-size'), 10) || 18;

  var bar = document.getElementById('bar'), nav = document.getElementById('nav'),
      prog = document.getElementById('progress'), aa = document.getElementById('aa'),
      panel = document.getElementById('settings');

  /* Settings panel */
  function setPanel(open) { panel.hidden = !open; aa.setAttribute('aria-expanded', open); }
  aa.addEventListener('click', function (e) { e.stopPropagation(); setPanel(panel.hidden); });
  document.addEventListener('click', function (e) { if (!panel.contains(e.target)) setPanel(false); });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') setPanel(false);
    var a = e.key === 'ArrowLeft' ? 'a[rel=prev]' : e.key === 'ArrowRight' ? 'a[rel=next]' : null;
    if (a && !/input|textarea/i.test(e.target.tagName)) { var l = nav.querySelector(a); if (l) location.href = l.href; }
  });

  function markTheme() {
    var t = d.dataset.theme || 'light';
    panel.querySelectorAll('[data-theme-set]').forEach(function (b) {
      b.setAttribute('aria-pressed', b.dataset.themeSet === t);
    });
  }
  panel.addEventListener('click', function (e) {
    var b = e.target.closest('button'); if (!b) return;
    if (b.dataset.size) {
      size = Math.min(30, Math.max(14, size + 2 * Number(b.dataset.size)));
      d.style.setProperty('--read-size', size + 'px'); state.size = size;
    }
    if (b.dataset.themeSet) { d.dataset.theme = b.dataset.themeSet; state.theme = b.dataset.themeSet; markTheme(); }
    save(state);
  });
  markTheme();

  /* Reading progress + hide bars while scrolling down, show when scrolling up */
  var lastY = window.scrollY, ticking = false;
  function onScroll() {
    var y = window.scrollY, max = d.scrollHeight - window.innerHeight;
    prog.style.width = (max > 0 ? Math.min(100, y / max * 100) : 0) + '%';
    var hide = y > lastY && y > 120 && panel.hidden;
    if (Math.abs(y - lastY) > 8) {
      bar.classList.toggle('is-hidden', hide); nav.classList.toggle('is-hidden', hide); lastY = y;
    }
    ticking = false;
  }
  window.addEventListener('scroll', function () {
    if (!ticking) { ticking = true; requestAnimationFrame(onScroll); }
  }, { passive: true });
  onScroll();
})();
