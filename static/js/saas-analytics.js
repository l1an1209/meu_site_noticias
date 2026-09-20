(function () {
  if (!document.getElementById('pup-analytics-csrf')) return;
  var csrfForm = document.getElementById('pup-analytics-csrf');
  var tokenInput = csrfForm && csrfForm.querySelector('[name=csrfmiddlewaretoken]');
  var token = tokenInput ? tokenInput.value : '';
  var collectUrl = '/a/collect/';

  function send(tipo, extra) {
    extra = extra || {};
    var body = {
      tipo: tipo,
      path: extra.path || (location.pathname + (location.hash || '')),
      referrer: document.referrer || '',
      utm_source: extra.utm_source,
      utm_medium: extra.utm_medium,
      utm_campaign: extra.utm_campaign,
      utm_content: extra.utm_content,
      utm_term: extra.utm_term,
      fbclid: extra.fbclid,
      fbp: extra.fbp,
      fbc: extra.fbc,
      eid: extra.eid,
      plano: extra.plano
    };
    var params = new URLSearchParams(location.search);
    ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'fbclid'].forEach(function (k) {
      if (!body[k] && params.get(k)) body[k] = params.get(k);
    });
    try {
      var fbp = document.cookie.split('; ').find(function (c) { return c.indexOf('_fbp=') === 0; });
      var fbc = document.cookie.split('; ').find(function (c) { return c.indexOf('_fbc=') === 0; });
      if (fbp) body.fbp = fbp.slice(5);
      if (fbc) body.fbc = fbc.slice(5);
    } catch (e) {}
    fetch(collectUrl, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': token
      },
      body: JSON.stringify(body)
    }).catch(function () {});
  }

  send('page_view');

  document.addEventListener('click', function (ev) {
    var el = ev.target.closest('[data-pup-event]');
    if (!el) return;
    send(el.getAttribute('data-pup-event'), {
      path: el.getAttribute('href') || location.pathname,
      plano: el.getAttribute('data-plano') || el.getAttribute('data-checkout-plano') || ''
    });
  });

  setInterval(function () { send('heartbeat'); }, 15000);
})();
