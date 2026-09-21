/* Leaf Standard widget for the Fertilizer Application CEO dashboard (any stack: React, Angular, plain HTML).

   <div id="leaf-standard"
        data-src="https://YOUR-DOMAIN/field-diary/leaf-standard/"
        data-key="LS_EMBED_KEY value"></div>
   <script src="https://YOUR-DOMAIN/field-diary/leaf-standard/static/widget.js" defer></script>

   Optional: data-date="2026-09-17"  data-compact="1"
   To sync with the fertilizer dashboard's own date picker:
     window.LeafStandardWidget.setDate('2026-09-17')
*/
(function () {
  function mount(el) {
    if (el.dataset.lsMounted) return;
    el.dataset.lsMounted = '1';
    var src = (el.dataset.src || '').replace(/\/?$/, '/');
    var q = 'key=' + encodeURIComponent(el.dataset.key || '');
    if (el.dataset.date) q += '&date=' + el.dataset.date;
    if (el.dataset.compact) q += '&compact=1';
    var f = document.createElement('iframe');
    f.src = src + 'embed?' + q;
    f.title = 'Leaf Standard';
    f.style.cssText = 'width:100%;border:0;min-height:520px;display:block';
    f.setAttribute('loading', 'lazy');
    el.appendChild(f);
    window.addEventListener('message', function (ev) {
      if (ev.source === f.contentWindow && ev.data && ev.data.type === 'leaf-standard-height') f.style.height = ev.data.height + 'px';
    });
    frames.push(f);
  }
  var frames = [];
  function scan() { document.querySelectorAll('#leaf-standard,[data-leaf-standard]').forEach(mount); }
  window.LeafStandardWidget = {
    mount: scan,
    setDate: function (d) { frames.forEach(function (f) { f.contentWindow.postMessage({ type: 'leaf-standard-date', date: d }, '*'); }); }
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', scan); else scan();
})();
