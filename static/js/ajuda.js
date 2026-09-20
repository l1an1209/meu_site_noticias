(function () {
  var root = document.querySelector('[data-help-thread]');
  if (!root) return;
  var pollUrl = root.getAttribute('data-poll-url');
  var sendUrl = root.getAttribute('data-send-url');
  var origemLocal = root.getAttribute('data-origem') || 'cliente';
  var box = root.querySelector('[data-help-messages]');
  var statusEl = root.querySelector('[data-help-status]');
  var form = root.querySelector('[data-help-form]');
  var campo = form && form.querySelector('[name=texto]');
  var csrfInput = form && form.querySelector('[name=csrfmiddlewaretoken]');
  var timer = null;

  function lastId() {
    var items = box.querySelectorAll('[data-msg-id]');
    if (!items.length) return 0;
    return parseInt(items[items.length - 1].getAttribute('data-msg-id'), 10) || 0;
  }

  function appendMsg(msg) {
    if (!msg || box.querySelector('[data-msg-id="' + msg.id + '"]')) return;
    var el = document.createElement('article');
    el.className = 'help-bubble help-bubble--' + msg.origem;
    el.setAttribute('data-msg-id', String(msg.id));
    var p = document.createElement('p');
    p.textContent = msg.texto;
    var small = document.createElement('small');
    small.textContent = (msg.autor || 'Equipe') + ' · ' + (msg.criado_em || '');
    el.appendChild(p);
    el.appendChild(small);
    box.appendChild(el);
    box.scrollTop = box.scrollHeight;
  }

  function poll() {
    if (document.hidden) return;
    fetch(pollUrl + '?depois=' + lastId(), {
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    })
      .then(function (resp) { return resp.ok ? resp.json() : null; })
      .then(function (data) {
        if (!data || !data.ok) return;
        (data.mensagens || []).forEach(appendMsg);
        if (statusEl && data.status_label) statusEl.textContent = data.status_label;
      })
      .catch(function () {});
  }

  if (form) {
    form.addEventListener('submit', function (ev) {
      if (!window.fetch || !csrfInput) return;
      ev.preventDefault();
      var texto = (campo.value || '').trim();
      if (!texto) return;
      var body = new FormData(form);
      fetch(sendUrl, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        body: body
      })
        .then(function (resp) { return resp.ok ? resp.json() : null; })
        .then(function (data) {
          if (data && data.mensagem) {
            appendMsg(data.mensagem);
            campo.value = '';
            if (statusEl && data.status_label) statusEl.textContent = data.status_label;
          } else {
            form.submit();
          }
        })
        .catch(function () { form.submit(); });
    });
  }

  box.scrollTop = box.scrollHeight;
  timer = window.setInterval(poll, 2500);
  window.addEventListener('beforeunload', function () {
    if (timer) window.clearInterval(timer);
  });
})();
