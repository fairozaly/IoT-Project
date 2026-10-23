(function () {
  'use strict';
  const grid = document.getElementById('fd-cards');
  const fanStatus = document.getElementById('fanStatus');
  const stopButton = document.getElementById('stopFan');
  const fanApproval = document.getElementById('fanApproval');
  const fanError = document.getElementById('fanError');
  if (!grid) return;
  const error = document.getElementById('fd-error');
  const update = document.getElementById('fd-update');
  const history = new Map();
  const cards = new Map();
  const MAX_SAMPLES = 9;
  const REFRESH_DELAY = 3000;
  const REQUEST_TIMEOUT = 8000;
  const palette = ['#a7d9fa', '#0879c5', '#23a2a3', '#735bcc', '#f39a4e', '#a25b86'];
  const svgNS = 'http://www.w3.org/2000/svg';

  let fanRunning = null;
  function renderFan(state) {
    fanRunning = state ? state.running : null;
    const label = state ? (fanRunning ? 'Running' : 'Stopped') : 'Unknown';
    if (state) {
      if (!state.mail_configured) {
        fanApproval.textContent = 'Configure the sender mailbox to enable email approval.';
      } else if (state.pending) {
        fanApproval.textContent = 'Waiting for email approval from ' + state.recipient + '. Reply yes to start the fan.';
      } else {
        fanApproval.textContent = 'Fan approval email: ' + state.recipient;
      }
    }
    fanStatus.textContent = 'Fan: ' + label.toLowerCase();
    document.querySelectorAll('.fd-fan-status').forEach(function (node) {
      node.textContent = label;
    });
  }
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function metric(label, unit, maximum, ticks) {
    const outer = el('div', 'fd-metric');
    const canvas = el('canvas', 'fd-gauge');
    canvas.setAttribute('role', 'meter');
    canvas.setAttribute('aria-label', label);
    canvas.setAttribute('aria-valuemin', '0');
    canvas.setAttribute('aria-valuemax', String(maximum));
    const valueText = el('strong');
    outer.append(el('span', '', label), canvas, valueText);
    const gauge = new RadialGauge({
      renderTo: canvas,
      width: 220,
      height: 220,
      minValue: 0,
      maxValue: maximum,
      majorTicks: ticks,
      minorTicks: 2,
      units: unit,
      value: 0,
      valueBox: false,
      borders: false,
      colorPlate: 'transparent',
      colorNumbers: '#526b80',
      colorNeedle: label === 'Temperature' ? '#e56b46' : '#0879c5',
      highlights: [{from: 0, to: maximum, color: 'rgba(8,121,197,0.12)'}],
      animationDuration: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 700,
      animationRule: 'linear'
    }).draw();
    return {element: outer, canvas: canvas, gauge: gauge, valueText: valueText, unit: unit, maximum: maximum};
  }

  function updateMetric(metric, value) {
    const available = Number.isFinite(value);
    metric.valueText.textContent = available ? value.toFixed(1) + ' ' : '— ';
    metric.valueText.appendChild(el('small', '', metric.unit));
    metric.canvas.hidden = !available;
    if (available) {
      const position = Math.max(0, Math.min(metric.maximum, value));
      metric.gauge.value = position;
      metric.canvas.setAttribute('aria-valuenow', String(position));
      metric.canvas.setAttribute('aria-valuetext', value.toFixed(1) + ' ' + metric.unit);
    } else {
      metric.canvas.removeAttribute('aria-valuenow');
    }
  }
  function showCards(readings) {
    const names = new Set(readings.map(function (item) { return item.name; }));
    for (const [name, card] of cards) {
      if (!names.has(name)) {
        card.temperature.gauge.destroy();
        card.humidity.gauge.destroy();
        card.element.remove();
        cards.delete(name);
      }
    }
    const empty = grid.querySelector('.fd-empty');
    if (empty) empty.remove();
    if (!readings.length) {
      grid.appendChild(el('div', 'fd-empty', 'No refrigerator readings yet.'));
      return;
    }
    readings.forEach(function (item) {
      let card = cards.get(item.name);
      if (!card) {
        const article = el('article', 'fd-fridge');
        const head = el('div', 'fd-fridge-head');
        const name = el('div', 'fd-name');
        const icon = el('span', 'fd-icon', '▦');
        icon.setAttribute('aria-hidden', 'true');
        name.append(icon, el('h2', '', item.name));
        head.append(name, el('span', 'fd-status', 'DATA AVAILABLE'));
        article.appendChild(head);
        const temperature = metric('Temperature', '°C', 50, [0, 10, 20, 30, 40, 50]);
        const humidity = metric('Humidity', '%', 100, [0, 20, 40, 60, 80, 100]);
        const metrics = el('div', 'fd-metrics');
        metrics.append(temperature.element, humidity.element);
        article.appendChild(metrics);
        const fanMeta = el('div', 'fd-meta');
        fanMeta.append(el('span', '', 'Fan status'), el('strong', 'fd-fan-status', 'Unknown'));
        article.appendChild(fanMeta);
        grid.appendChild(article);
        card = {element: article, temperature: temperature, humidity: humidity};
        cards.set(item.name, card);
      }
      updateMetric(card.temperature, item.temperature);
      updateMetric(card.humidity, item.humidity);
      card.element.querySelector('.fd-fan-status').textContent = fanRunning === null ? 'Unknown' : (fanRunning ? 'Running' : 'Stopped');
    });
  }
  function readingTime(timestamp) {
    if (!timestamp) return NaN;
    let text = String(timestamp).replace(' ', 'T');
    if (!/([zZ]|[+-]\d{2}:?\d{2})$/.test(text)) text += 'Z';
    return Date.parse(text);
  }

  function record(readings) {
    readings.forEach(function (item) {
      if (!history.has(item.name)) history.set(item.name, []);
      const samples = history.get(item.name);
      const last = samples[samples.length - 1];
      if (last && last.reading_id === item.reading_id) return;
      const time = readingTime(item.timestamp);
      samples.push({
        time: Number.isFinite(time) ? new Date(time) : new Date(),
        reading_id: item.reading_id,
        temperature: item.temperature,
        humidity: item.humidity
      });
      if (samples.length > MAX_SAMPLES) samples.shift();
    });
  }
  function fillFilter(id, readings) {
    const select = document.getElementById(id);
    const previous = select.value;
    select.replaceChildren(new Option('All refrigerators', 'all'));
    readings.forEach(function (item) {
      select.add(new Option(item.name, item.name));
    });
    if ([...select.options].some(option => option.value === previous)) select.value = previous;
  }
  function svgNode(tag, attrs, text) {
    const node = document.createElementNS(svgNS, tag);
    Object.entries(attrs || {}).forEach(function ([name, value]) {
      node.setAttribute(name, String(value));
    });
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function draw(metricName, filterId, chartId, legendId) {
    const svg = document.getElementById(chartId);
    const legend = document.getElementById(legendId);
    const filter = document.getElementById(filterId).value;
    svg.replaceChildren();
    legend.replaceChildren();
    const allNames = Array.from(history.keys());
    const names = allNames.filter(function (name) {
      return filter === 'all' || filter === name;
    });
    const plot = {left: 48, right: 638, top: 15, bottom: 226};
    const values = names.flatMap(name => history.get(name).map(sample => sample[metricName])).filter(Number.isFinite);
    const max = metricName === 'humidity' ? Math.max(100, ...values) : Math.max(40, ...values);
    const top = Math.ceil(max / 10) * 10;
    const bottom = Math.floor(Math.min(0, ...values) / 10) * 10;
    const range = top - bottom;
    const plotHeight = plot.bottom - plot.top;
    const zeroY = plot.bottom + bottom / range * plotHeight;
    for (let y = 0; y <= 4; y++) {
      const yPosition = plot.top + y * plotHeight / 4;
      const label = Math.round(top - range * y / 4);
      svg.appendChild(svgNode('line', {
        x1: plot.left, y1: yPosition, x2: plot.right, y2: yPosition,
        stroke: '#ccdce8', 'stroke-dasharray': '6 6'
      }));
      svg.appendChild(svgNode('text', {
        x: plot.left - 9, y: yPosition + 4, 'text-anchor': 'end'
      }, String(label)));
    }
    names.forEach(function (name) {
      const swatch = el('span');
      const dot = el('i');
      dot.style.background = palette[allNames.indexOf(name) % palette.length];
      swatch.append(dot, document.createTextNode(name));
      legend.appendChild(swatch);
    });
    const sampleCount = Math.max(1, ...names.map(name => history.get(name).length));
    if (!values.length) {
      svg.appendChild(svgNode('text', {
        x: 340, y: 126, 'text-anchor': 'middle'
      }, 'Waiting for readings...'));
      return;
    }
    const slots = Math.max(sampleCount, 2);
    const slotWidth = (plot.right - plot.left) / slots;
    names.forEach(function (name, seriesIndex) {
      const points = history.get(name);
      points.forEach(function (point, i) {
        const barWidth = Math.min(28, slotWidth * 0.65 / names.length);
        const value = point[metricName];
        if (!Number.isFinite(value)) return;
        const groupCenter = plot.left + (i + 0.5) * slotWidth;
        const offset = (seriesIndex - (names.length - 1) / 2) * barWidth;
        const x = groupCenter + offset;
        const valueY = plot.bottom - (value - bottom) / range * plotHeight;
        const bar = svgNode('rect', {
          x: x - barWidth / 2,
          y: Math.min(valueY, zeroY),
          width: barWidth,
          height: Math.abs(valueY - zeroY),
          fill: palette[allNames.indexOf(name) % palette.length],
          rx: 1
        });
        const unit = metricName === 'temperature' ? '°C' : '%';
        const tooltip = name + ': ' + value.toFixed(1) + unit +
          ' at ' + point.time.toLocaleTimeString();
        bar.appendChild(svgNode('title', {}, tooltip));
        svg.appendChild(bar);
      });
    });
    const first = history.get(names[0]);
    for (let i = 0; i < sampleCount; i++) {
      const timestamp = first[i] && first[i].time;
      if (!timestamp) continue;
      const label = timestamp.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
      svg.appendChild(svgNode('text', {
        x: plot.left + (i + 0.5) * slotWidth, y: 248, 'text-anchor': 'middle'
      }, label));
    }
  }
  function redraw() {
    draw('temperature', 'fd-temp-filter', 'fd-temp-chart', 'fd-temp-legend');
    draw('humidity', 'fd-humidity-filter', 'fd-humidity-chart', 'fd-humidity-legend');
  }
  async function fetchJson(url, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(function () {
      controller.abort();
    }, REQUEST_TIMEOUT);
    try {
      const response = await fetch(url, {...options, cache: 'no-store', signal: controller.signal});
      if (response.status === 401) window.location.assign('/signin');
      if (!response.ok) throw new Error('HTTP ' + response.status);
      return await response.json();
    } finally {
      clearTimeout(timeout);
    }
  }

  async function refresh() {
    try {
      const readings = await fetchJson('/api/readings');
      showCards(readings);
      record(readings);
      fillFilter('fd-temp-filter', readings);
      fillFilter('fd-humidity-filter', readings);
      redraw();

      const latestTime = Math.max(...readings.map(item => readingTime(item.timestamp)));
      if (!readings.length) {
        update.textContent = 'Waiting for readings';
      } else if (!Number.isFinite(latestTime) || Date.now() - latestTime > 15000) {
        update.textContent = 'No recent data';
      } else {
        update.textContent = 'Updated ' + new Date(latestTime).toLocaleTimeString();
      }
      error.hidden = true;
    } catch (err) {
      error.hidden = false;
      error.textContent = 'Unable to refresh readings (' + err.message + '). Displaying the last available data.';
      update.textContent = 'Update failed';
    } finally {
      setTimeout(refresh, REFRESH_DELAY);
    }
  }

  async function refreshFan() {
    try {
      const state = await fetchJson('/api/fan');
      renderFan(state);
    } catch (err) {
      renderFan(null);
    } finally {
      setTimeout(refreshFan, REFRESH_DELAY);
    }
  }

  if (stopButton) stopButton.addEventListener('click', async function () {
    stopButton.disabled = true;
    fanError.hidden = true;
    try {
      const state = await fetchJson('/api/fan/stop', {
        method: 'POST'
      });
      renderFan(state);
    } catch (err) {
      fanError.textContent = 'Unable to stop fan (' + err.message + '). Try again.';
      fanError.hidden = false;
    } finally {
      stopButton.disabled = false;
    }
  });

  grid.replaceChildren();
  document.getElementById('fd-temp-filter').addEventListener('change', redraw);
  document.getElementById('fd-humidity-filter').addEventListener('change', redraw);
  redraw();
  refresh();
  refreshFan();
})();
