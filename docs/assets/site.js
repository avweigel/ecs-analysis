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

  /* One table-filter menu for the whole site.

     The crop table grew a per-column filter and the explorer's table wanted
     the same thing; two implementations of the same popover is how two pages
     that should feel identical stop feeling identical. `values(key)` returns
     the options, `state(key)` the live Set of chosen ones, and `onchange` is
     called after every toggle. */
  function filterMenu(opts) {
    var el = document.getElementById('fmenu'), key = null;
    if (!el) {
      el = document.createElement('div');
      el.id = 'fmenu'; el.className = 'fmenu'; el.hidden = true;
      document.body.appendChild(el);
    }
    function paint() {
      if (!key) return;
      var set = opts.state(key), vals = opts.values(key);
      el.innerHTML = '<div class="fhead"><b>' + (opts.label(key)) + '</b>' +
        '<button type="button" data-all="1">All</button>' +
        '<button type="button" data-none="1">Clear</button></div>' +
        vals.map(function (v) {
          return '<label><input type="checkbox" data-v="' +
            String(v.value).replace(/"/g, '&quot;') + '"' +
            (set.has(v.value) ? ' checked' : '') + '><span>' + v.value +
            '</span><span class="c">' + v.n + '</span></label>';
        }).join('');
    }
    el.onclick = function (ev) {
      if (!key) return;
      var set = opts.state(key);
      if (ev.target.closest('[data-all]')) {
        opts.values(key).forEach(function (v) { set.add(v.value); });
      } else if (ev.target.closest('[data-none]')) {
        set.clear();
      } else {
        var box = ev.target.closest('input[type=checkbox]');
        if (!box) return;
        box.checked ? set.add(box.dataset.v) : set.delete(box.dataset.v);
      }
      opts.onchange();
      paint();
    };
    function close() { el.hidden = true; key = null; }
    document.addEventListener('click', function (ev) {
      if (ev.target.closest('#fmenu') || ev.target.closest('.fbtn')) return;
      close();
    });
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape') close();
    });
    addEventListener('scroll', close, true);
    return {
      open: function (k, btn) {
        if (key === k) { close(); return; }
        key = k; paint(); el.hidden = false;
        var r = btn.getBoundingClientRect();
        el.style.left = Math.max(8, Math.min(r.left - 6, innerWidth - 268)) + 'px';
        el.style.top = (r.bottom + 5) + 'px';
      },
      close: close,
      isOpen: function (k) { return key === k; }
    };
  }

  window.ECS = {
    filterMenu: filterMenu,
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
