(function () {
  'use strict';
  const grid = document.getElementById('fd-cards');
  if (!grid) return;
  const error = document.getElementById('fd-error');
  const update = document.getElementById('fd-update');
  const history = new Map();
  const MAX_SAMPLES = 9;
  const palette = ['#a7d9fa', '#0879c5', '#23a2a3', '#735bcc', '#f39a4e', '#a25b86'];
  const svgNS = 'http://www.w3.org/2000/svg';

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function metric(label, value, unit) {
    const outer = el('div', 'fd-metric');
    outer.appendChild(el('span', '', label));
    const strong = el('strong', '', Number.isFinite(value) ? value.toFixed(1) + ' ' : '— ');
    strong.appendChild(el('small', '', unit));
    outer.appendChild(strong);
    return outer;
  }
  function addMeta(card, label, value) {
    const line = el('div', 'fd-meta');
    line.append(el('span', '', label), el('strong', '', value));
    card.appendChild(line);
  }
  function showCards(readings) {
    grid.replaceChildren();
    if (!readings.length) {
      grid.appendChild(el('div', 'fd-empty', 'No refrigerator readings yet.'));
      return;
    }
    readings.forEach(function (item) {
      const card = el('article', 'fd-fridge');
      const head = el('div', 'fd-fridge-head');
      const name = el('div', 'fd-name');
      const icon = el('span', 'fd-icon', '▦');
      icon.setAttribute('aria-hidden', 'true');
      name.append(icon, el('h2', '', item.name));
      head.append(name, el('span', 'fd-status', 'DATA AVAILABLE'));
      card.appendChild(head);
      const metrics = el('div', 'fd-metrics');
      metrics.append(metric('Temperature', item.temperature, '°C'), metric('Humidity', item.humidity, '%'));
      card.appendChild(metrics);
      addMeta(card, 'Current threshold', 'Not available');
      addMeta(card, 'Fan status', 'Unknown');
      grid.appendChild(card);
    });
  }
  function record(readings) {
    const now = new Date();
    readings.forEach(function (item) {
      if (!history.has(item.name)) history.set(item.name, []);
      const values = history.get(item.name);
      values.push({time: now, temperature: item.temperature, humidity: item.humidity});
      if (values.length > MAX_SAMPLES) values.shift();
    });
  }
  function fillFilter(id, readings) {
    const select = document.getElementById(id);
    const previous = select.value;
    select.replaceChildren(new Option('All refrigerators', 'all'));
    readings.forEach(function (item) {select.add(new Option(item.name, item.name));});
    if ([...select.options].some(o => o.value === previous)) select.value = previous;
  }
  function svgNode(tag, attrs, text) {
    const node = document.createElementNS(svgNS, tag);
    Object.entries(attrs || {}).forEach(function ([k,v]) {node.setAttribute(k, String(v));});
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function draw(metricName, filterId, chartId, legendId) {
    const svg = document.getElementById(chartId);
    const legend = document.getElementById(legendId);
    const filter = document.getElementById(filterId).value;
    svg.replaceChildren(); legend.replaceChildren();
    const names = [...history.keys()].filter(name => filter === 'all' || filter === name);
    const plot = {left:48, right:638, top:15, bottom:226};
    const values = names.flatMap(name => history.get(name).map(p => p[metricName])).filter(Number.isFinite);
    const max = metricName === 'humidity' ? Math.max(100, ...values, 10) : Math.max(40, ...values, 10);
    const top = Math.ceil(max / 10) * 10;
    for (let y = 0; y <= 4; y++) {
      const yy = plot.top + y * (plot.bottom - plot.top) / 4;
      svg.appendChild(svgNode('line', {x1:plot.left,y1:yy,x2:plot.right,y2:yy,stroke:'#ccdce8','stroke-dasharray':'6 6'}));
      svg.appendChild(svgNode('text', {x:plot.left - 9,y:yy + 4,'text-anchor':'end'}, String(Math.round(top * (4-y)/4))));
    }
    names.forEach(function (name) {
      const swatch = el('span');
      const dot = el('i');
      dot.style.background = palette[[...history.keys()].indexOf(name) % palette.length];
      swatch.append(dot, document.createTextNode(name));legend.appendChild(swatch);
    });
    const sampleCount = Math.max(1,...names.map(n=>history.get(n).length));
    if (!values.length) {
      svg.appendChild(svgNode('text',{x:340,y:126,'text-anchor':'middle'},'Waiting for readings...'));
      return;
    }
    const slots = Math.max(sampleCount, 2);
    const slotWidth = (plot.right - plot.left) / slots;
    names.forEach(function (name, seriesIndex) {
      const points = history.get(name);
      points.forEach(function (point, i) {
        const barWidth = Math.min(28,slotWidth*.65/Math.max(1,names.length));
        const value = point[metricName];
        if (!Number.isFinite(value)) return;
        const x = plot.left + (i + .5)*slotWidth + (seriesIndex - (names.length-1)/2)*barWidth;
        const barHeight = Math.max(0,Math.min(value/top,1)) * (plot.bottom - plot.top);
        const bar = svgNode('rect',{x:x-barWidth/2,y:plot.bottom-barHeight,width:barWidth,height:barHeight,fill:palette[[...history.keys()].indexOf(name)%palette.length],rx:1});
        bar.appendChild(svgNode('title',{},name + ': ' + value.toFixed(1) + (metricName === 'temperature' ? '°C' : '%') + ' at ' + point.time.toLocaleTimeString()));
        svg.appendChild(bar);
      });
    });
    const first = history.get(names[0]);
    for(let i=0;i<sampleCount;i++) {
      const timestamp = first[i] && first[i].time;
      if(!timestamp) continue;
      svg.appendChild(svgNode('text',{x:plot.left+(i+.5)*slotWidth,y:248,'text-anchor':'middle'},timestamp.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})));
    }
  }
  function redraw() {
    draw('temperature', 'fd-temp-filter', 'fd-temp-chart', 'fd-temp-legend');
    draw('humidity', 'fd-humidity-filter', 'fd-humidity-chart', 'fd-humidity-legend');
  }
  async function refresh() {
    try {
      const response = await fetch('/api/readings', {cache:'no-store'});
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const data = await response.json();
      if (!Array.isArray(data)) throw new Error('Unexpected API response');
      const readings = data.filter(item=>item && typeof item.name==='string').map(item=>({
        name:item.name,
        temperature: item.temperature === null ? NaN : Number(item.temperature),
        humidity: item.humidity === null ? NaN : Number(item.humidity)
      }));
      showCards(readings);
      record(readings);
      fillFilter('fd-temp-filter', readings);
      fillFilter('fd-humidity-filter', readings);
      redraw();
      update.textContent = 'Updated ' + new Date().toLocaleTimeString();
      error.hidden = true;
    } catch (e) {
      error.hidden = false;
      error.textContent = 'Unable to refresh readings (' + e.message + '). Displaying the last available data.';
      update.textContent = 'Update failed';
    }
  }
  document.getElementById('fd-temp-filter').addEventListener('change', redraw);
  document.getElementById('fd-humidity-filter').addEventListener('change', redraw);
  redraw();
  refresh();
  setInterval(refresh,3000);
})();
