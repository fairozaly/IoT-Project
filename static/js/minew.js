(function () {
  'use strict';
  const root = document.getElementById('minewDashboard');
  if (!root) return;
  const $ = id => document.getElementById(id);
  const endpoint = root.dataset.endpoint || '/api/minew';
  const REFRESH_MS = 4000;
  const STALE_MS = 30000;
  let stopped = false;
  let lastRecord = null;
  const demo = new URLSearchParams(window.location.search).get('minew_demo') === '1';

  function number(value, decimals = 1) {
    return value === null || value === undefined || value === '' || !Number.isFinite(Number(value))
      ? '—' : Number(value).toFixed(decimals);
  }
  function date(value) {
    if (!value) return null;
    const d = typeof value === 'number' && value < 1e11 ? new Date(value * 1000) : new Date(value);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  function setStatus(mode, label, message) {
    const status = $('minewStatus');
    status.classList.toggle('is-live', mode === 'live');
    status.classList.toggle('is-stale', mode === 'stale');
    $('minewStatusText').textContent = label;
    $('minewNotice').hidden = !message;
    if (message) $('minewNotice').textContent = message;
  }
  function show(record, isDemo = false) {
    const updated = date(record.timestamp);
    const stale = !updated || Date.now() - updated.getTime() > STALE_MS;
    $('minewTemp').textContent = number(record.temperature);
    $('minewHumidity').textContent = number(record.humidity);
    $('minewLight').textContent = number(record.illuminance, 0);
    $('minewDevice').textContent = record.device_id || 'Not identified';
    $('minewBattery').textContent = number(record.battery_percentage, 0) === '—' ? '—' : number(record.battery_percentage, 0) + '%';
    $('minewUpdated').textContent = updated ? updated.toLocaleTimeString() : 'Unknown';
    const motion = $('minewMotion');
    motion.classList.toggle('is-active', record.motion_detected === true);
    motion.textContent = record.motion_detected === true ? 'Motion detected'
      : record.motion_detected === false ? 'No active motion' : 'Unknown';
    const lastMotion = date(record.last_motion_at);
    $('minewMotionTime').textContent = lastMotion ? 'Last motion: ' + lastMotion.toLocaleTimeString() : 'No motion event received';
    setStatus(isDemo ? 'live' : stale ? 'stale' : 'live',
      isDemo ? 'DEMO DATA' : stale ? 'Reading stale' : 'Sensor online',
      isDemo ? 'Demo mode: these values are simulated, not from the MSP01.'
        : stale ? 'The last reading is older than 30 seconds. Check your BLE gateway.' : '');
  }
  async function poll() {
    try {
      if (demo) {
        const now = new Date().toISOString();
        show({device_id:'MSP01 • simulated', temperature:22.4, humidity:45.7,
          illuminance:312, motion_detected:false, battery_percentage:89, timestamp:now}, true);
      } else {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 3500);
        let response;
        try { response = await fetch(endpoint, {cache:'no-store', signal: controller.signal}); }
        finally { clearTimeout(timeout); }
        if (!response.ok) throw new Error('HTTP ' + response.status);
        const data = await response.json();
        if (!data || !data.timestamp) {
          setStatus('waiting','Waiting for sensor','No MSP01 data received yet. Configure a BLE receiver and data endpoint.');
        } else {
          lastRecord = data;
          show(data);
        }
      }
    } catch (error) {
      setStatus('offline', lastRecord ? 'Gateway unavailable' : 'Not connected',
        'MSP01 API unavailable (' + error.message + '). Sensor values will not be simulated.');
      if (lastRecord) show({...lastRecord, timestamp:lastRecord.timestamp});
      setStatus('offline','Gateway unavailable','Cannot refresh MSP01 data. Showing last recorded values.');
    } finally {
      if (!stopped) setTimeout(poll, REFRESH_MS);
    }
  }
  window.addEventListener('pagehide', () => { stopped = true; });
  poll();
})();
