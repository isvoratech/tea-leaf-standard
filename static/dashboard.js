const $ = id => document.getElementById(id);
let cfg, mode = 'day', timer, embedKey = '', refreshVersion = 0, trendPoints = [];
let trendState = 'loading';
let trendEstates = [];
let selectedEstate = null;

// Number of days shown in the daily trend (Day view). Change here if needed.
const TREND_DAYS = 30;

const SESSION_LABELS = { morning: 'Morning', noon: 'Noon', evening: 'Evening' };

function dashboardApi(path) {
  return LS.api(path, { headers: embedKey ? { 'X-Embed-Key': embedKey } : {} });
}


// ---------------------------------------------------------------- estate dropdown
async function loadTrendEstates() {
  // Keep only the first #trendEstate (the one in the date bar) - duplicate ids break it.
  [...document.querySelectorAll('#trendEstate')].slice(1)
    .forEach(s => (s.closest('label.estate-chart-control') || s).remove());

  const select = $('trendEstate');
  if (!select) return;

  select.addEventListener('change', onEstateChange);

  try {
    trendEstates = await LS.api('estates');
  } catch (e) {
    console.error('Could not load estate list', e);
    return;
  }

  select.innerHTML = '<option value="">All estates</option>';

  const addGroup = (label, list) => {
    if (!list.length) return;
    const group = document.createElement('optgroup');
    group.label = label;
    list.forEach(e => {
      const option = document.createElement('option');
      option.value = String(e.id);
      option.textContent = e.name;
      group.appendChild(option);
    });
    select.appendChild(group);
  };

  addGroup('High Grown', trendEstates.filter(e => e.region === 'HG'));
  addGroup('Low Grown', trendEstates.filter(e => e.region === 'LG'));
}

function onEstateChange() {
  const value = $('trendEstate').value;
  selectedEstate = trendEstates.find(e => String(e.id) === value) || null;
  applyEstateSeriesDefaults();
  refresh();
}


function ensureEstateSeriesControl() {
  const controls = $('seriesControls');
  let label = $('estateSeriesLabel');

  if (!selectedEstate) {
    if (label) label.remove();
    return;
  }

  if (!label) {
    label = document.createElement('label');
    label.id = 'estateSeriesLabel';

    const input = document.createElement('input');
    input.type = 'checkbox';
    input.value = 'ESTATE';
    input.checked = true;

    const text = document.createElement('span');
    text.className = 'estate-series-name';

    label.appendChild(input);
    label.appendChild(text);
    controls.appendChild(label);
  }

  label.querySelector('.estate-series-name').textContent = selectedEstate.name;
  label.querySelector('input').checked = true;
}


function applyEstateSeriesDefaults() {
  const baseInputs = [
    ...$('seriesControls').querySelectorAll('input[value="ALL"],input[value="HG"],input[value="LG"]')
  ];

  // All estates: Company + HG + LG.  One estate: only that estate's line;
  // the user can tick the others to compare.
  baseInputs.forEach(input => { input.checked = !selectedEstate; });

  ensureEstateSeriesControl();
  renderCharts();
}


// ---------------------------------------------------------------- boot / login
async function boot() {
  $('btnOut').onclick = LS.logout;
  const params = new URLSearchParams(location.search);
  embedKey = params.get('key') || '';
  if (embedKey) {
    params.delete('key');
    history.replaceState(null, '', location.pathname + (params.size ? '?' + params : ''));
    $('btnOut').classList.add('hidden');
  }
  cfg = await LS.api('config');
  await loadTrendEstates();
  if (embedKey) return start({ full_name: 'CEO', role: 'viewer' });
  if (!LS.store.get('token')) return showLogin();
  try {
    const me = await LS.api('me');
    if (!['ceo', 'admin'].includes(me.role)) { location.href = './'; return; }
    start(me);
  } catch (e) { showLogin(); }
}

function showLogin() {
  $('loginCard').classList.remove('hidden'); $('btnOut').classList.add('hidden');
  // Google Sign-In: only reached when there is no valid saved session.
  LS.googleButton($('gBox'), cfg && cfg.google_client_id, u => {
    if (!['ceo', 'admin'].includes(u.role)) { location.href = './'; return; }
    $('loginMsg').innerHTML = '';
    $('loginCard').classList.add('hidden'); $('btnOut').classList.remove('hidden'); start(u);
  }, e => { $('loginMsg').innerHTML = `<div class="msg err">${LS.esc(e.message)}</div>`; });
}

$('loginForm').onsubmit = async ev => {
  ev.preventDefault();
  try {
    const r = await LS.api('login', { method: 'POST', body: JSON.stringify({ username: $('u').value, password: $('p').value }), noRedirect: true });
    LS.store.set('token', r.token); LS.store.set('user', JSON.stringify(r.user));
    if (!['ceo', 'admin'].includes(r.user.role)) { location.href = './'; return; }
    $('loginCard').classList.add('hidden'); $('btnOut').classList.remove('hidden'); start(r.user);
  } catch (e) { $('loginMsg').innerHTML = `<div class="msg err">${LS.esc(e.message)}</div>`; }
};

function start(me) {
  $('who').textContent = me.role === 'admin' ? 'Admin' : `${me.full_name || me.username} · ${me.role.toUpperCase()}`;
  if (me.role === 'ceo' || me.role === 'admin' || embedKey) {
    if (embedKey) $('lnkEntries').href = `admin?key=${encodeURIComponent(embedKey)}#entries`;
    $('lnkEntries').classList.remove('hidden');
  }
  if (me.role === 'admin') { $('lnkEntry').classList.remove('hidden'); $('lnkAdmin').classList.remove('hidden'); }
  $('dash').classList.remove('hidden');
  const params = new URLSearchParams(location.search);
  $('day').value = params.get('date') || cfg.today; $('day').max = cfg.today;
  $('from').value = params.get('from') || cfg.today.slice(0, 8) + '01';
  $('to').value = params.get('to') || cfg.today;
  if (params.get('from')) mode = 'per';
  updateMode();
  $('from').max = $('to').max = cfg.today;
  $('prev').onclick = () => { $('day').value = LS.addDays($('day').value, -1); refresh(); };
  $('next').onclick = () => { if ($('day').value < cfg.today) { $('day').value = LS.addDays($('day').value, 1); refresh(); } };
  $('tdy').onclick = () => { $('day').value = cfg.today; refresh(); };
  $('day').onchange = $('from').onchange = $('to').onchange = refresh;
  $('mDay').onclick = () => setMode('day'); $('mPer').onclick = () => setMode('per');
  document.querySelectorAll('[data-p]').forEach(b => b.onclick = () => {
    const t = cfg.today, p = b.dataset.p;
    $('to').value = t;
    if (p === '7') $('from').value = LS.addDays(t, -6);
    if (p === 'mtd') $('from').value = t.slice(0, 8) + '01';
    if (p === 'q') { const m = +t.slice(5, 7), qm = String(m - ((m - 1) % 3)).padStart(2, '0'); $('from').value = `${t.slice(0, 4)}-${qm}-01`; }
    refresh();
  });
  $('xls').onclick = download;
  refresh();
  clearInterval(timer);
  timer = setInterval(refresh, 120000);
}

function setMode(m) {
  mode = m;
  updateMode();
  refresh();
}

function updateMode() {
  const m = mode;
  $('mDay').classList.toggle('on', m === 'day'); $('mPer').classList.toggle('on', m === 'per');
  $('dayBox').classList.toggle('hidden', m !== 'day'); $('perBox').classList.toggle('hidden', m === 'day');
  $('mDay').setAttribute('aria-pressed', m === 'day'); $('mPer').setAttribute('aria-pressed', m === 'per');
}

function query() { return mode === 'day' ? `date=${$('day').value}` : `from=${$('from').value}&to=${$('to').value}`; }

function selectedRange() {
  const from = mode === 'day' ? $('day').value : $('from').value;
  const to = mode === 'day' ? $('day').value : $('to').value;
  if (!from || !to || from > to || to > cfg.today) throw new Error('Choose valid dates in order, up to today.');
  const days = Math.round((Date.parse(to) - Date.parse(from)) / 86400000) + 1;
  if (!Number.isFinite(days) || days > 367) throw new Error('Choose a date range of at most 367 days.');
  return { from, to, trendFrom: mode === 'day' ? LS.addDays(to, -(TREND_DAYS - 1)) : from };
}


// ---------------------------------------------------------------- daily values table
function renderTrendValues() {
  const summary = $('trendDetails').querySelector('summary');
  const band = v => `<td class="v ${LS.band(v, cfg.target, cfg.warn)}">${LS.pct(v)}</td>`;

  if (selectedEstate) {
    summary.textContent = `View daily values · ${selectedEstate.name}`;

    if (trendPoints.some(p => p.ESTATE != null && !p.ESTATE_SESSIONS)) {
      $('trendValues').innerHTML = '<div class="msg err">Server is running an old version (no per-session data). Restart the Leaf Standard service.</div>';
      return;
    }

    $('trendValues').innerHTML =
      '<table class="ls"><thead><tr><th>Date</th>' +
      Object.values(SESSION_LABELS).map(l => `<th>${l}</th>`).join('') +
      '<th>Day avg</th></tr></thead><tbody>' +
      trendPoints.map(p => {
        const s = p.ESTATE_SESSIONS || {};
        return `<tr><td>${LS.esc(p.date)}</td>` +
          Object.keys(SESSION_LABELS).map(k => band(s[k])).join('') +
          band(p.ESTATE) + '</tr>';
      }).join('') +
      '</tbody></table>';
    return;
  }

  summary.textContent = 'View daily values';
  $('trendValues').innerHTML =
    '<table class="ls"><thead><tr><th>Date</th><th>Company</th><th>High Grown</th><th>Low Grown</th></tr></thead><tbody>' +
    trendPoints.map(p =>
      `<tr><td>${LS.esc(p.date)}</td><td>${LS.pct(p.ALL)}</td><td>${LS.pct(p.HG)}</td><td>${LS.pct(p.LG)}</td></tr>`
    ).join('') +
    '</tbody></table>';
}


// ---------------------------------------------------------------- refresh
async function refresh() {
  if (!cfg) return;
  const version = ++refreshVersion;
  $('loadError').innerHTML = ''; $('xls').disabled = true;
  let range;
  try { range = selectedRange(); }
  catch (e) {
    $('loadError').innerHTML = `<div class="msg err">${LS.esc(e.message)}</div>`;
    $('kpis').innerHTML = ''; $('tbl').innerHTML = ''; $('alert').innerHTML = '';
    trendPoints = []; trendState = 'invalid'; renderCharts();
    $('trendValues').innerHTML = ''; $('stamp').textContent = 'Choose valid dates to load data';
    return;
  }
  history.replaceState(null, '', '?' + query());
  $('next').disabled = $('day').value >= cfg.today;
  $('kpis').innerHTML = ''; $('tbl').innerHTML = '<p class="muted">Loading selected dates…</p>'; $('alert').innerHTML = '';
  $('stamp').textContent = 'Loading…';
  trendState = 'loading'; trendPoints = []; renderCharts(); $('trendValues').innerHTML = '';
  $('trendRange').textContent = `${LS.nice(range.trendFrom)} — ${LS.nice(range.to)}`;
  $('trendTitle').textContent = mode === 'day' ? `Daily trend · ${TREND_DAYS} days to selected date` : 'Daily trend · selected period';

  const estateParam = selectedEstate ? `&estate_id=${encodeURIComponent(selectedEstate.id)}` : '';
  const results = await Promise.allSettled([
    dashboardApi('summary?' + query()),
    dashboardApi(`trend?from=${range.trendFrom}&to=${range.to}${estateParam}`)
  ]);
  if (version !== refreshVersion) return;
  if (results.some(r => r.status === 'rejected' && r.reason.status === 401) && !embedKey) {
    clearInterval(timer); $('dash').classList.add('hidden'); showLogin(); return;
  }
  const [summary, trend] = results;
  if (summary.status === 'fulfilled') {
    const d = summary.value;
    const find = k => d.rows.find(r => r.key === k);
    const all = find('ALL'), hg = find('HG'), lg = find('LG');
    const estateCount = region => d.rows.filter(r => r.type === 'estate' && r.region === region).length;
    const tile = (l, v, s, band) => `<div class="kpi"><div class="l">${l}</div><div class="v" style="color:var(--${band === 'nil' ? 'muted' : band})">${LS.pct(v)}</div><div class="s">${s}</div></div>`;
    const st = d.status;
    $('kpis').innerHTML =
      tile('Company average', all.day_avg, `Morning ${LS.pct(all.morning)} · Noon ${LS.pct(all.noon)} · Evening ${LS.pct(all.evening)}`, LS.band(all.day_avg, d.target, d.warn)) +
      tile('High Grown', hg.day_avg, `${estateCount('HG')} active estates`, LS.band(hg.day_avg, d.target, d.warn)) +
      tile('Low Grown', lg.day_avg, `${estateCount('LG')} active estates`, LS.band(lg.day_avg, d.target, d.warn)) +
      `<div class="kpi"><div class="l">Entries received</div><div class="v">${st.submitted}<span class="subcount"> / ${st.expected}</span></div><div class="s">${st.estates_complete}/${st.estates_total} estates complete</div></div>`;
    $('alert').innerHTML = st.estates_missing.length ? `<details class="missing-panel"><summary>${st.estates_missing.length} ${st.estates_missing.length === 1 ? 'estate has' : 'estates have'} no entries in this selection</summary><p>${st.estates_missing.map(LS.esc).join(', ')}</p></details>` : '';
    $('tblTitle').textContent = d.days === 1 ? `Leaf Standard — ${LS.nice(d.from)}` : `Leaf Standard — ${LS.nice(d.from)} to ${LS.nice(d.to)} (${d.days} days, averages)`;
    LS.renderTable($('tbl'), d);
    addFactorySplits(d);
    $('xls').disabled = false;
  } else {
    $('tbl').innerHTML = `<div class="msg err">Could not load summary: ${LS.esc(summary.reason.message)}</div>`;
  }
  if (trend.status === 'fulfilled') {
    trendPoints = trend.value;
    trendState = 'ready';
    renderTrendValues();
  } else {
    trendState = 'error';
    $('loadError').innerHTML = `<div class="msg err">Could not load trend: ${LS.esc(trend.reason.message)} <button type="button" class="ghost" id="retryTrend">Retry</button></div>`;
    $('retryTrend').onclick = refresh;
  }
  renderCharts();
  $('stamp').textContent = `Updated ${new Date().toLocaleTimeString()}${results.some(r => r.status === 'rejected') ? ' · some data could not load' : ''}`;
}



// Small per-factory values under a session average, only when 2+ factories entered it.
// Small per-factory lines under a value - only when 2+ factories entered it.
function factorySplitHtml(list) {
  if (!list || list.length < 2) return '';
  return '<span class="fac-split" style="display:block;margin-top:3px;font-size:11px;font-weight:400;line-height:1.35;opacity:.85;white-space:nowrap">' +
    list.map(f => `<span style="display:block">${LS.esc(f.name)} ${LS.pct(f.value)}</span>`).join('') +
    '</span>';
}

function addFactorySplits(d) {
  const trs = [...$('tbl').querySelectorAll('tbody tr')];
  const sameCount = trs.length === d.rows.length;
  const findRow = (row, i) => sameCount ? trs[i]
    : trs.find(tr => (tr.children[0]?.textContent || '').trim().startsWith(row.name));

  ['morning', 'noon', 'evening'].forEach((s, j) => {
    d.rows.forEach((row, i) => {
      const html = row.type === 'estate' ? factorySplitHtml(row.by_factory && row.by_factory[s]) : '';
      if (!html) return;
      const td = findRow(row, i)?.children[1 + j];
      if (!td || td.querySelector('.fac-split')) return;
      td.insertAdjacentHTML('beforeend', html);
    });
  });
}

// ---------------------------------------------------------------- chart
function chartCss(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

function factoryTooltip(point) {
  const f = point.ESTATE_FACTORIES || {};
  const lines = Object.keys(SESSION_LABELS)
    .filter(k => f[k] && f[k].length > 1)
    .map(k => `\n${SESSION_LABELS[k]}: ` + f[k].map(x => `${x.name} ${LS.pct(x.value)}`).join(', '));
  return LS.esc(lines.join(''));
}


function renderEstateTrend(el, pts, target, options = {}) {

  const enabled = options.series || [];

  if (!enabled.length) {
    el.innerHTML = '<p class="chart-empty">Select at least one chart series.</p>';
    return;
  }

  const isExpanded = el.id === 'expandedTrend';

  const labels = {
    ALL: 'Company',
    HG: 'High Grown',
    LG: 'Low Grown',
    ESTATE: selectedEstate ? selectedEstate.name : 'Estate'
  };

  const colors = {
    ALL: chartCss('--brand', '#2e6b3a'),
    HG: chartCss('--chart-hg', '#3478c5'),
    LG: chartCss('--chart-lg', '#a56112'),
    ESTATE: chartCss('--chart-estate', '#7c3aed')
  };

  const values = pts.flatMap(point =>
    enabled.map(key => point[key]).filter(value => value != null && Number.isFinite(value))
  );

  if (!values.length) {
    el.innerHTML = '<p class="chart-empty">No readings for the selected series.</p>';
    return;
  }

  // ---------- scale
  let lo = 0;
  let hi = 1;

  if (options.scale === 'detail') {
    lo = Math.max(0, Math.min(...values, target) - 0.03);
    hi = Math.min(1, Math.max(...values, target) + 0.03);
  }

  let interval;

  if (options.interval && options.interval !== 'auto') {
    interval = Number(options.interval) / 100;
  } else {
    const span = hi - lo;
    if (span <= 0.08) interval = 0.01;
    else if (span <= 0.16) interval = 0.02;
    else if (span <= 0.35) interval = 0.05;
    else if (span <= 0.65) interval = 0.10;
    else interval = 0.20;
  }

  if (options.scale === 'detail') {
    lo = Math.max(0, Math.floor(lo / interval) * interval);
    hi = Math.min(1, Math.ceil(hi / interval) * interval);
  }

  if (hi <= lo) hi = Math.min(1, lo + interval);

  const ticks = [];
  for (let t = lo; t <= hi + 0.00001; t += interval) ticks.push(Number(t.toFixed(4)));

  // ---------- geometry
  const AXIS = 70;      // fixed y-axis panel width (does not scroll)
  const PAD_L = 18;     // gap between axis and first point
  const R = 28;
  const TOP = 32;
  const BOTTOM = 56;

  const spacing = pts.length <= 45
    ? (isExpanded ? 64 : 54)
    : (isExpanded ? 40 : 34);

  const viewWidth = Math.max(300, (el.clientWidth || 900) - AXIS - 4);
  const W = Math.max(viewWidth, PAD_L + R + pts.length * spacing);

  const requestedHeight = Number(options.height) || 360;
  const H = isExpanded ? Math.max(requestedHeight, 320) : Math.max(requestedHeight, 420);

  const x = index => PAD_L + (W - PAD_L - R) * (pts.length <= 1 ? 0.5 : index / (pts.length - 1));
  const y = value => TOP + (H - TOP - BOTTOM) * (1 - (value - lo) / (hi - lo));

  // ---------- fixed y-axis (outside the scroller)
  let axis =
    `<svg class="trend trend-axis" width="${AXIS}" height="${H}" viewBox="0 0 ${AXIS} ${H}" ` +
    `style="display:block;flex:0 0 ${AXIS}px;width:${AXIS}px;height:${H}px" aria-hidden="true">`;

  axis +=
    `<text transform="translate(14 ${(TOP + H - BOTTOM) / 2}) rotate(-90)" text-anchor="middle" ` +
    `style="font-size:12px;font-weight:600">Leaf standard (%)</text>`;

  ticks.forEach(v => {
    axis += `<text x="${AXIS - 8}" y="${y(v) + 4}" text-anchor="end" style="font-size:12px">${Math.round(v * 100)}%</text>`;
  });

  axis += `<line x1="${AXIS - 0.5}" x2="${AXIS - 0.5}" y1="${TOP}" y2="${H - BOTTOM}" stroke="var(--line)"/>`;
  axis += '</svg>';

  // ---------- scrolling plot
  let svg =
    `<svg class="trend estate-trend" viewBox="0 0 ${W} ${H}" ` +
    `width="${W}" height="${H}" ` +
    `style="width:${W}px;height:${H}px;max-width:none;min-width:0;display:block" ` +
    `role="img" aria-label="Leaf standard trend">`;

  ticks.forEach(v => {
    const yy = y(v);
    svg += `<line x1="0" x2="${W - R}" y1="${yy}" y2="${yy}" stroke="var(--line)"/>`;
  });

  if (target >= lo && target <= hi) {
    const ty = y(target);
    svg +=
      `<line x1="0" x2="${W - R}" y1="${ty}" y2="${ty}" stroke="var(--bad)" ` +
      `stroke-width="1.5" stroke-dasharray="7 6" vector-effect="non-scaling-stroke"/>`;
  }

  const every = pts.length <= 45 ? 1 : Math.ceil(pts.length / 20);
  const months = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  pts.forEach((point, index) => {
    if (index % every !== 0 && index !== pts.length - 1) return;
    const parts = point.date.split('-');
    svg +=
      `<text class="trend-date-label" x="${x(index)}" y="${H - 20}" text-anchor="middle" ` +
      `style="font-size:11px">${LS.esc(`${parts[2]} ${months[Number(parts[1])]}`)}</text>`;
  });

  // Lines: join consecutive days only (break where a day has no reading)
  enabled.forEach(key => {

    let d = '';
    let drawing = false;

    pts.forEach((point, index) => {
      const value = point[key];

      if (value == null || !Number.isFinite(value)) {
        drawing = false;
        return;
      }

      d += (drawing ? 'L' : 'M') + `${x(index).toFixed(1)},${y(value).toFixed(1)} `;
      drawing = true;
    });

    if (d) {
      svg +=
        `<path d="${d.trim()}" fill="none" stroke="${colors[key]}" ` +
        `stroke-width="${key === 'ALL' ? 3 : key === 'ESTATE' ? 2.8 : 2}" ` +
        `stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>`;
    }

    pts.forEach((point, index) => {
      const value = point[key];
      if (value == null || !Number.isFinite(value)) return;

      svg +=
        `<circle cx="${x(index)}" cy="${y(value)}" r="${key === 'ESTATE' ? 5 : 4.2}" ` +
        `fill="${colors[key]}" stroke="var(--card)" stroke-width="1.2">` +
        `<title>${LS.esc(labels[key])} · ${LS.esc(point.date)} · ${LS.pct(value)}${key === 'ESTATE' ? factoryTooltip(point) : ''}</title>` +
        `</circle>`;
    });
  });

  // Value labels on top
  if (pts.length <= 45) {
    pts.forEach((point, index) => {
      const items = enabled
        .map(key => ({ key, value: point[key] }))
        .filter(item => item.value != null && Number.isFinite(item.value))
        .map(item => ({ ...item, ly: y(item.value) - 11 }))
        .sort((a, b) => a.ly - b.ly);

      for (let i = 1; i < items.length; i++) {
        if (items[i].ly - items[i - 1].ly < 14) items[i].ly = items[i - 1].ly + 14;
      }

      items.forEach(item => {
        svg +=
          `<text class="trend-point-value" x="${x(index)}" y="${Math.max(12, item.ly)}" ` +
          `text-anchor="middle" style="font-size:11px;font-weight:700;fill:${colors[item.key]}">` +
          `${LS.esc(LS.pct(item.value))}</text>`;
      });
    });
  }

  svg += '</svg>';

  const legend = enabled
    .map(key => `<span style="--c:${colors[key]}">${LS.esc(labels[key])}</span>`)
    .join('');

  // Axis panel stays put; only the plot scrolls sideways.
  el.innerHTML =
    `<div class="chart-frame" style="display:flex;align-items:flex-start;max-width:100%">` +
      axis +
      `<div class="chart-scroll" tabindex="0" style="flex:1 1 auto;min-width:0;overflow-x:auto">${svg}</div>` +
    `</div>` +
    `<p class="chart-axis-note muted">Percentage interval: ${Math.round(interval * 100)}%</p>` +
    `<div class="legend">${legend}` +
    `<span style="--c:var(--bad)">Target ${LS.pct(target)} · dashed line</span>` +
    `</div>`;
}


function renderCharts() {

  const options = {
    scale: $('chartScale').value,
    interval: $('chartStep').value,
    series: [...$('seriesControls').querySelectorAll('input:checked')].map(input => input.value)
  };

  for (const id of ['trend', ...($('chartDialog').open ? ['expandedTrend'] : [])]) {

    if (trendState !== 'ready') {
      $(id).innerHTML =
        `<p class="chart-empty">${
          trendState === 'loading'
            ? 'Loading trend…'
            : trendState === 'invalid'
              ? 'Choose valid dates to show the trend.'
              : 'Trend unavailable. Use Retry to load it again.'
        }</p>`;
    } else {
      renderEstateTrend($(id), trendPoints, cfg.target, {
        ...options,
        height: id === 'trend' ? 360 : Math.min(580, Math.max(300, innerHeight - 220))
      });
    }
  }

  $('expandedRange').textContent = $('trendRange').textContent;
  $('expandedScale').value = $('chartScale').value;
  $('expandedStep').value = $('chartStep').value;
}

$('chartScale').onchange = renderCharts;
$('chartStep').onchange = renderCharts;
$('expandedScale').onchange = () => { $('chartScale').value = $('expandedScale').value; renderCharts(); };
$('expandedStep').onchange = () => { $('chartStep').value = $('expandedStep').value; renderCharts(); };
$('seriesControls').onchange = renderCharts;
function expandChart() { if (!$('chartDialog').open) $('chartDialog').showModal(); renderCharts(); }
$('expandChart').onclick = expandChart;
$('trend').onclick = event => { if (event.target.closest('svg')) expandChart(); };
$('trend').onkeydown = event => {
  if (event.key === 'Enter' && event.target.classList.contains('chart-scroll')) { event.preventDefault(); expandChart(); }
};
$('closeChart').onclick = () => $('chartDialog').close();
let resizeTimer;
window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(renderCharts, 100); });

async function download() {
  $('xls').disabled = true;
  try {
    selectedRange();
    const res = await dashboardApi('export.xlsx?' + query());
    const blob = await res.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = (res.headers.get('content-disposition') || '').match(/filename="(.+)"/)?.[1] || 'Leaf_Standard.xlsx';
    a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  } catch (e) { $('loadError').innerHTML = `<div class="msg err">Export failed: ${LS.esc(e.message)}</div>`; }
  finally { $('xls').disabled = false; }
}

boot().catch(e => { $('loginCard').classList.remove('hidden'); $('loginMsg').innerHTML = `<div class="msg err">${LS.esc(e.message)}</div>`; });