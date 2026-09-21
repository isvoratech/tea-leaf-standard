/* Leaf Standard - shared helpers (all URLs relative, so it works under any Apache prefix) */
const LS = (() => {
  const store = {
    get(k) { try { return localStorage.getItem('ls_' + k); } catch (e) { return null; } },
    set(k, v) { try { v == null ? localStorage.removeItem('ls_' + k) : localStorage.setItem('ls_' + k, v); } catch (e) {} },
  };
  const base = (() => {  // folder the page lives in
    const p = location.pathname;
    return p.endsWith('/') ? p : p.replace(/\/[^/]*$/, '/');
  })();

  async function api(path, opts = {}) {
    const headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
    const tok = store.get('token');
    if (tok) headers.Authorization = 'Bearer ' + tok;
    const res = await fetch(base + 'api/' + path, Object.assign({}, opts, { headers }));
    if (res.status === 401 && !opts.noRedirect) { store.set('token', null); store.set('user', null); }
    if (!res.ok) {
      let msg = res.statusText;
      try { const j = await res.json(); msg = typeof j.detail === 'string' ? j.detail : (j.detail || []).map(d => d.msg).join(', '); } catch (e) {}
      const err = new Error(msg); err.status = res.status; throw err;
    }
    return res.headers.get('content-type')?.includes('json') ? res.json() : res;
  }

  const T = {
    en: { title: 'Leaf Standard', sub: 'Field Diary · daily 3-round entry', login: 'Login', username: 'Username', password: 'Password',
      date: 'Date', morning: 'Morning', noon: 'Noon', evening: 'Evening', save: 'Save', update: 'Update',
      submitted: 'Submitted', pending: 'Pending', queued: 'Queued (offline)', pct: 'Leaf standard %', weights: 'Sample weights',
      good: 'Good leaf (g)', total: 'Total sample (g)', remarks: 'Remarks', logout: 'Logout', last7: 'Last 7 days',
      offline: 'No signal – saved on phone, will send automatically.', saved: 'Saved', synced: 'Offline entries sent',
      estate: 'Estate', dayavg: 'Day avg', locked: 'Locked', dashboard: 'CEO dashboard', admin: 'Users' },
    si: { title: 'දළු ප්‍රමිතිය', sub: 'ක්ෂේත්‍ර දිනපොත · දිනකට වාර 3', login: 'පිවිසෙන්න', username: 'පරිශීලක නාමය', password: 'මුරපදය',
      date: 'දිනය', morning: 'උදෑසන', noon: 'දහවල්', evening: 'සවස', save: 'සුරකින්න', update: 'යාවත්කාලීන කරන්න',
      submitted: 'යොමු කළා', pending: 'ඉතිරිය', queued: 'පෝලිමේ (නොබැඳි)', pct: 'දළු ප්‍රමිතිය %', weights: 'සාම්පල බර',
      good: 'හොඳ දළු (ග්‍රෑ)', total: 'මුළු සාම්පලය (ග්‍රෑ)', remarks: 'සටහන්', logout: 'ඉවත් වන්න', last7: 'පසුගිය දින 7',
      offline: 'සංඥා නැත – දුරකථනයේ සුරැකිණි, පසුව ස්වයංක්‍රීයව යවනු ලැබේ.', saved: 'සුරැකිණි', synced: 'නොබැඳි දත්ත යවන ලදී',
      estate: 'වත්ත', dayavg: 'දින සාමාන්‍යය', locked: 'අගුලු දමා ඇත', dashboard: 'CEO පුවරුව', admin: 'පරිශීලකයින්' },
    ta: { title: 'கொழுந்து தரம்', sub: 'கள நாட்குறிப்பு · நாளொன்றுக்கு 3 முறை', login: 'உள்நுழை', username: 'பயனர் பெயர்', password: 'கடவுச்சொல்',
      date: 'தேதி', morning: 'காலை', noon: 'மதியம்', evening: 'மாலை', save: 'சேமி', update: 'புதுப்பி',
      submitted: 'சமர்ப்பிக்கப்பட்டது', pending: 'நிலுவையில்', queued: 'வரிசையில் (இணைப்பு இல்லை)', pct: 'கொழுந்து தரம் %', weights: 'மாதிரி எடை',
      good: 'நல்ல கொழுந்து (கி)', total: 'மொத்த மாதிரி (கி)', remarks: 'குறிப்புகள்', logout: 'வெளியேறு', last7: 'கடந்த 7 நாட்கள்',
      offline: 'இணைப்பு இல்லை – தொலைபேசியில் சேமிக்கப்பட்டது, தானாக அனுப்பப்படும்.', saved: 'சேமிக்கப்பட்டது', synced: 'சேமித்த பதிவுகள் அனுப்பப்பட்டன',
      estate: 'தோட்டம்', dayavg: 'நாள் சராசரி', locked: 'பூட்டப்பட்டது', dashboard: 'CEO பலகை', admin: 'பயனர்கள்' },
  };
  let lang = store.get('lang') || 'en';
  const t = k => (T[lang] && T[lang][k]) || T.en[k] || k;
  function setLang(l) { lang = l; store.set('lang', l); document.querySelectorAll('[data-t]').forEach(el => el.textContent = t(el.dataset.t)); document.querySelectorAll('.lang button').forEach(b => b.classList.toggle('on', b.dataset.l === l)); }

  const pct = v => v == null ? '–' : (v * 100).toFixed(1) + '%';
  const iso = d => { const z = new Date(d.getTime() - d.getTimezoneOffset() * 60000); return z.toISOString().slice(0, 10); };
  const addDays = (s, n) => { const d = new Date(s + 'T00:00:00'); d.setDate(d.getDate() + n); return iso(d); };
  const nice = s => new Date(s + 'T00:00:00').toLocaleDateString('en-GB', { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' });
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const band = (v, target, warn) => v == null ? 'nil' : v >= target ? 'good' : v >= warn ? 'warn' : 'bad';

  /* Excel-style table used by dashboard + embed */
  function renderTable(el, data, { compact = false } = {}) {
    const S = ['morning', 'noon', 'evening'];
    const single = data.days === 1;
    let h = `<div class="tablewrap"><table class="ls"><thead>
      <tr><th rowspan="2">Estate</th><th colspan="3" class="grp">Leaf Standard${single ? '' : ' (period avg)'}</th><th rowspan="2">Day avg</th><th rowspan="2">Entries</th></tr>
      <tr><th>Morning</th><th>Noon</th><th>Evening</th></tr></thead><tbody>`;
    for (const r of data.rows) {
      const isAvg = r.type === 'avg';
      const cls = isAvg ? `avg${r.key === 'ALL' ? ' company' : ''}` : '';
      const miss = !isAvg && r.submitted === 0;
      const tip = !isAvg && r.remarks?.length ? ` title="${esc(r.remarks.join('\n'))}"` : '';
      h += `<tr class="${cls}"><td${tip}>${esc(r.name)}${miss ? ' <span class="missing">● no entry</span>' : ''}${tip ? ' 💬' : ''}</td>`;
      for (const s of S) h += `<td class="v ${isAvg ? '' : band(r[s], data.target, data.warn)}">${pct(r[s])}</td>`;
      h += `<td class="v ${isAvg ? '' : band(r.day_avg, data.target, data.warn)}">${pct(r.day_avg)}</td>`;
      h += `<td class="subcount">${r.submitted}/${r.expected}</td></tr>`;
    }
    h += `</tbody></table></div>
      <div class="legend"><span style="--c:var(--good-bg)">≥ ${pct(data.target)}</span><span style="--c:var(--warn-bg)">${pct(data.warn)} – ${pct(data.target)}</span><span style="--c:var(--bad-bg)">&lt; ${pct(data.warn)}</span><span style="--c:var(--avg-bg)">Averages (simple mean of estates that reported)</span></div>`;
    el.innerHTML = h;
  }

  function renderTrend(el, pts, target) {
    const W = 700, H = 220, L = 38, R = 10, Tp = 12, B = 26;
    const vals = pts.flatMap(p => [p.HG, p.LG, p.ALL]).filter(v => v != null);
    if (!vals.length) { el.innerHTML = '<p class="muted">No data in the last days.</p>'; return; }
    let lo = Math.min(...vals, target) - 0.03, hi = Math.max(...vals, target) + 0.03;
    lo = Math.max(0, Math.floor(lo * 20) / 20); hi = Math.min(1, Math.ceil(hi * 20) / 20);
    const x = i => L + (W - L - R) * (pts.length === 1 ? 0.5 : i / (pts.length - 1));
    const y = v => Tp + (H - Tp - B) * (1 - (v - lo) / (hi - lo));
    const css = getComputedStyle(document.documentElement);
    const col = { ALL: css.getPropertyValue('--brand'), HG: '#3b7dd8', LG: css.getPropertyValue('--accent') };
    let s = `<svg class="trend" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Leaf standard trend">`;
    for (let g = lo; g <= hi + 1e-9; g += 0.05) s += `<line x1="${L}" x2="${W - R}" y1="${y(g)}" y2="${y(g)}" stroke="var(--line)"/><text x="${L - 4}" y="${y(g) + 4}" text-anchor="end">${Math.round(g * 100)}%</text>`;
    s += `<line x1="${L}" x2="${W - R}" y1="${y(target)}" y2="${y(target)}" stroke="var(--bad)" stroke-dasharray="4 4"/>`;
    const step = Math.ceil(pts.length / 7);
    pts.forEach((p, i) => { if (i % step === 0 || i === pts.length - 1) s += `<text x="${x(i)}" y="${H - 8}" text-anchor="${i === pts.length - 1 ? 'end' : i === 0 ? 'start' : 'middle'}">${p.date.slice(8)}/${p.date.slice(5, 7)}</text>`; });
    for (const k of ['HG', 'LG', 'ALL']) {
      let d = '', pen = false;
      pts.forEach((p, i) => { if (p[k] == null) { pen = false; return; } d += `${pen ? 'L' : 'M'}${x(i).toFixed(1)},${y(p[k]).toFixed(1)}`; pen = true; });
      s += `<path d="${d}" fill="none" stroke="${col[k]}" stroke-width="${k === 'ALL' ? 2.6 : 1.6}" vector-effect="non-scaling-stroke"/>`;
      pts.forEach((p, i) => { if (p[k] != null) s += `<circle cx="${x(i)}" cy="${y(p[k])}" r="${k === 'ALL' ? 3 : 2}" fill="${col[k]}"><title>${p.date} ${k}: ${pct(p[k])}</title></circle>`; });
    }
    s += '</svg>';
    el.innerHTML = s + `<div class="legend"><span style="--c:${col.ALL}">Company</span><span style="--c:${col.HG}">High Grown</span><span style="--c:${col.LG}">Low Grown</span><span style="--c:var(--bad)">Target ${pct(target)} (dashed)</span></div>`;
  }

  function logout() { store.set('token', null); store.set('user', null); location.href = base; }

  return { api, store, base, t, setLang, get lang() { return lang; }, pct, iso, addDays, nice, esc, band, renderTable, renderTrend, logout };
})();
