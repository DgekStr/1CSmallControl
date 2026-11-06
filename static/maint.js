/* Плашка регламентных работ в веб-клиенте 1С: опрашивает портал и показывает уведомления. */
(function () {
  var BOX_ID = 'maint-banner';
  var lastToast = null;

  function fmt(minutes) {
    if (minutes >= 60) {
      var h = Math.floor(minutes / 60), m = minutes % 60;
      return h + ' ч' + (m ? ' ' + m + ' мин' : '');
    }
    return minutes + ' мин';
  }

  function ensureBox() {
    var box = document.getElementById(BOX_ID);
    if (!box) {
      box = document.createElement('div');
      box.id = BOX_ID;
      box.style.cssText = [
        'position:fixed', 'left:0', 'right:0', 'top:0', 'z-index:2147483647',
        'padding:10px 16px', 'font:14px/1.4 Arial,sans-serif', 'color:#fff',
        'box-shadow:0 2px 10px rgba(0,0,0,.35)', 'display:none', 'text-align:center'
      ].join(';');
      document.body.appendChild(box);
    }
    return box;
  }

  function toast(text, color) {
    var box = ensureBox();
    box.textContent = text;
    box.style.background = color;
    box.style.display = 'block';
  }

  function poll() {
    fetch('/api/maint', { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (st) {
        var box = ensureBox();
        if (!st || st.phase === 'none') {
          box.style.display = 'none';
          return;
        }
        if (st.phase === 'planned') {
          box.style.display = 'none';
          return;
        }
        if (st.phase === 'soon') {
          toast('Через ' + fmt(st.minutes_left) + ' — регламентные работы до ' + st.ends_at +
                '. Сохраните данные и выйдите из 1С.', '#b45309');
          var key = 'maint-toast-' + st.id;
          if (lastToast !== key) {
            lastToast = key;
            try {
              if (window.Notification && Notification.permission === 'granted') {
                new Notification('Скоро регламентные работы', { body: st.message });
              }
            } catch (e) { /* игнорируем */ }
          }
          return;
        }
        if (st.phase === 'active') {
          toast('Идут регламентные работы до ' + st.ends_at + '. Вход и сохранение недоступны.', '#b91c1c');
        }
      })
      .catch(function () { /* сеть недоступна — молча ждём */ });
  }

  document.addEventListener('DOMContentLoaded', function () {
    poll();
    setInterval(poll, 20000);
  });
})();
