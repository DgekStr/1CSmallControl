// Переключатель темы: светлая / тёмная / как в системе.
// Выбор хранится в localStorage («portal-theme»), атрибут ставится ещё в <head>,
// чтобы не было вспышки белым при загрузке.
(function () {
  var KEY = 'portal-theme';
  var mq = window.matchMedia('(prefers-color-scheme: light)');

  function resolve(mode) {
    return mode === 'auto' ? (mq.matches ? 'light' : 'dark') : mode;
  }

  function paint(mode) {
    document.documentElement.dataset.theme = resolve(mode);
    document.querySelectorAll('[data-theme-set]').forEach(function (btn) {
      btn.classList.toggle('active', btn.dataset.themeSet === mode);
      btn.setAttribute('aria-pressed', String(btn.dataset.themeSet === mode));
    });
  }

  paint(localStorage.getItem(KEY) || 'auto');

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-theme-set]');
    if (!btn) return;
    var mode = btn.dataset.themeSet;
    localStorage.setItem(KEY, mode);
    paint(mode);
  });

  var onChange = function () { paint(localStorage.getItem(KEY) || 'auto'); };
  if (mq.addEventListener) mq.addEventListener('change', onChange);
  else if (mq.addListener) mq.addListener(onChange);
})();
