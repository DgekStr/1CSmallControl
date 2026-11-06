/* Уведомления регламентных работ в веб-клиенте 1С: плашка и окно с обратным отсчётом. */
(function () {
  var BOX_ID = 'maint-banner';
  var MODAL_ID = 'maint-modal';
  var shownFor = null;

  function fmtTime(sec) {
    sec = Math.max(0, sec | 0);
    var m = Math.floor(sec / 60), s = sec % 60;
    return (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
  }

  function banner() {
    var box = document.getElementById(BOX_ID);
    if (!box) {
      box = document.createElement('div');
      box.id = BOX_ID;
      box.style.cssText = 'position:fixed;left:0;right:0;top:0;z-index:2147483646;' +
        'padding:10px 16px;font:14px/1.4 Arial,sans-serif;color:#fff;text-align:center;' +
        'box-shadow:0 2px 10px rgba(0,0,0,.35);display:none';
      document.body.appendChild(box);
    }
    return box;
  }

  function toast(text, color) {
    var box = banner();
    box.textContent = text;
    box.style.background = color;
    box.style.display = 'block';
  }

  function closeModal() {
    var m = document.getElementById(MODAL_ID);
    if (m) m.remove();
  }

  function showCountdown(st) {
    if (document.getElementById(MODAL_ID)) {
      var left = document.getElementById('maint-left');
      if (left) left.textContent = fmtTime(st.seconds_left);
      return;
    }
    var wrap = document.createElement('div');
    wrap.id = MODAL_ID;
    wrap.style.cssText = 'position:fixed;inset:0;z-index:2147483647;background:rgba(15,23,42,.72);' +
      'display:flex;align-items:center;justify-content:center;font:14px/1.5 Arial,sans-serif';

    var card = document.createElement('div');
    card.style.cssText = 'background:#fff;color:#111827;max-width:460px;width:calc(100% - 40px);' +
      'border-radius:14px;padding:24px 26px;box-shadow:0 20px 50px rgba(0,0,0,.45)';

    card.innerHTML =
      '<div style="font-size:20px;font-weight:700;margin-bottom:10px">Срочные регламентные работы</div>' +
      '<div style="margin-bottom:14px">Закройте 1С. Отключение через ' +
      '<b id="maint-left" style="color:#b91c1c">' + fmtTime(st.seconds_left) + '</b>' +
      '. После отключения несохранённые данные будут потеряны.</div>' +
      '<div style="display:flex;gap:10px;justify-content:flex-end;margin-top:8px">' +
      '<button id="maint-dismiss" style="padding:9px 16px;border-radius:8px;border:1px solid #d1d5db;' +
      'background:#fff;color:#111827;cursor:pointer">Закрыть</button>' +
      '<button id="maint-exit" style="padding:9px 16px;border-radius:8px;border:0;' +
      'background:#b91c1c;color:#fff;cursor:pointer;font-weight:600">Закрыть 1С</button>' +
      '</div>';

    wrap.appendChild(card);
    document.body.appendChild(wrap);

    document.getElementById('maint-dismiss').onclick = function () {
      wrap.style.display = 'none';
    };
    document.getElementById('maint-exit').onclick = function () {
      try { window.open('', '_self'); window.close(); } catch (e) { /* браузер может запретить */ }
      setTimeout(function () { window.location.href = '/maintenance'; }, 150);
    };
  }

  function poll() {
    fetch('/api/maint', { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (st) {
        var box = banner();
        if (!st || st.phase === 'none' || st.phase === 'planned') {
          box.style.display = 'none';
          return;
        }
        if (st.phase === 'soon') {
          toast('Через ' + st.minutes_left + ' мин — регламентные работы до ' + st.ends_at +
                '. Сохраните данные и выйдите из 1С.', '#b45309');
          return;
        }
        if (st.phase === 'grace') {
          toast('Срочные регламентные работы: отключение через ' + fmtTime(st.seconds_left), '#b91c1c');
          if (shownFor !== st.id) {
            shownFor = st.id;
            showCountdown(st);
          } else if (document.getElementById(MODAL_ID)) {
            var left = document.getElementById('maint-left');
            if (left) left.textContent = fmtTime(st.seconds_left);
          }
          return;
        }
        if (st.phase === 'active') {
          closeModal();
          toast('Идут регламентные работы до ' + st.ends_at + '. Вход и сохранение недоступны.', '#7f1d1d');
        }
      })
      .catch(function () { /* сеть недоступна — ждём следующего опроса */ });
  }

  document.addEventListener('DOMContentLoaded', function () {
    poll();
    setInterval(poll, 10000);
  });
})();
