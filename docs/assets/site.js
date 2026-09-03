/* Shared chrome: theme toggle (persisted), nav highlighting, tooltip helper. */
(function () {
  var KEY = 'ecs-theme';
  try {
    var saved = localStorage.getItem(KEY);
    if (saved) document.documentElement.setAttribute('data-theme', saved);
  } catch (e) {}

  function label() {
    var t = document.documentElement.getAttribute('data-theme');
    if (t === 'dark') return 'Dark';
    if (t === 'light') return 'Light';
    return 'Auto';
  }

  window.ECS = {
    mountTheme: function (btn) {
      if (!btn) return;
      btn.textContent = label();
      btn.title = 'Theme: auto follows your system setting';
      btn.addEventListener('click', function () {
        var t = document.documentElement.getAttribute('data-theme');
        var next = t === 'dark' ? 'light' : (t === 'light' ? '' : 'dark');
        if (next) document.documentElement.setAttribute('data-theme', next);
        else document.documentElement.removeAttribute('data-theme');
        try { next ? localStorage.setItem(KEY, next) : localStorage.removeItem(KEY); } catch (e) {}
        btn.textContent = label();
        document.dispatchEvent(new CustomEvent('ecs:theme'));
      });
    },
    tip: function (html, ev) {
      var t = document.getElementById('tip'); if (!t) return;
      if (html === null) { t.style.opacity = 0; return; }
      t.innerHTML = html; t.style.opacity = 1;
      if (ev) {
        var r = t.getBoundingClientRect();
        t.style.left = Math.min(ev.clientX + 14, innerWidth - r.width - 10) + 'px';
        t.style.top = Math.max(8, ev.clientY - r.height - 12) + 'px';
      }
    }
  };

  document.addEventListener('DOMContentLoaded', function () {
    window.ECS.mountTheme(document.getElementById('themetog'));
    document.addEventListener('mousemove', function (e) {
      var t = document.getElementById('tip');
      if (t && t.style.opacity === '1') {
        var r = t.getBoundingClientRect();
        t.style.left = Math.min(e.clientX + 14, innerWidth - r.width - 10) + 'px';
        t.style.top = Math.max(8, e.clientY - r.height - 12) + 'px';
      }
    });
  });
})();
