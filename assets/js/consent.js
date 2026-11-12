(function () {
  function loadMaps() {
    document.querySelectorAll('iframe[data-src]').forEach(function (frame) {
      frame.src = frame.getAttribute('data-src');
      frame.removeAttribute('data-src');
    });
    document.querySelectorAll('.embed-consent').forEach(function (node) { node.remove(); });
  }

  function init() {
    document.querySelectorAll('iframe[data-src]').forEach(function (frame) {
      if (frame.parentNode.querySelector('.embed-consent')) return;
      var box = document.createElement('div');
      box.className = 'embed-consent';
      box.innerHTML =
        '<p>Este mapa lo sirve Google. Al cargarlo, Google puede recibir tu IP y guardar cookies. ' +
        '<a href="/politica-de-cookies/">Más información</a></p>' +
        '<button type="button" class="btn btn-secondary">Cargar mapa</button>';
      box.querySelector('button').addEventListener('click', loadMaps);
      frame.parentNode.insertBefore(box, frame);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
