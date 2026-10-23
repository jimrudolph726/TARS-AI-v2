(function () {
  'use strict';

  var metricsTimer = null;
  var clockTimer = null;

  function setText(id, value) {
    var el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  function updateClock() {
    var value = new Intl.DateTimeFormat([], {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    }).format(new Date());
    setText('v2Clock', value);
    setText('v2MobileClock', value);
  }

  function syncConnectionState() {
    var dot = document.getElementById('connDot');
    if (!dot) return;

    var state = 'ONLINE';
    if (dot.classList.contains('disconnected')) state = 'OFFLINE';
    else if (dot.classList.contains('reconnecting')) state = 'LINKING';

    setText('v2ConnectionText', state);
    setText('v2MobileConnectionText', state);

    var mobileDot = document.querySelector('.v2-mobile-dot');
    if (mobileDot) mobileDot.dataset.state = state.toLowerCase();
  }

  function updateHeaderMetrics(data) {
    var cpu = Number(data.cpu_load);
    var ram = Number(data.ram_usage);
    var temp = Number(data.cpu_temp);
    setText('v2HeaderCpu', Number.isFinite(cpu) ? Math.round(cpu) + '%' : '--');
    setText('v2HeaderRam', Number.isFinite(ram) ? Math.round(ram) + '%' : '--');
    setText('v2HeaderTemp', Number.isFinite(temp) && temp > 0 ? Math.round(temp) + '°' : '--');
  }

  function fetchHeaderMetrics() {
    fetch('/api/system/metrics', {
      credentials: 'same-origin',
      headers: { 'Accept': 'application/json' }
    })
      .then(function (response) {
        if (!response.ok) throw new Error('metrics unavailable');
        return response.json();
      })
      .then(updateHeaderMetrics)
      .catch(function () {
        setText('v2HeaderCpu', '--');
        setText('v2HeaderRam', '--');
        setText('v2HeaderTemp', '--');
      });
  }

  document.addEventListener('DOMContentLoaded', function () {
    updateClock();
    fetchHeaderMetrics();
    syncConnectionState();

    clockTimer = window.setInterval(updateClock, 15000);
    metricsTimer = window.setInterval(fetchHeaderMetrics, 10000);

    var dot = document.getElementById('connDot');
    if (dot && window.MutationObserver) {
      new MutationObserver(syncConnectionState).observe(dot, {
        attributes: true,
        attributeFilter: ['class']
      });
    }
  });

  window.addEventListener('pagehide', function () {
    if (metricsTimer) window.clearInterval(metricsTimer);
    if (clockTimer) window.clearInterval(clockTimer);
  });
})();
