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
    en: { title: 'Daily Leaf Standard', sub: 'Field Diary · daily 3-round entry', login: 'Login', username: 'Username', password: 'Password',
      date: 'Date', morning: 'Morning', noon: 'Noon', evening: 'Evening', save: 'Save', update: 'Update',
      submitted: 'Submitted', pending: 'Pending', queued: 'Queued (offline)', pct: 'Leaf standard %', weights: 'Sample weights',
      good: 'Good leaf (g)', total: 'Total sample (g)', remarks: 'Remarks', logout: 'Logout', last7: 'Last 7 days',
      offline: 'No signal – saved on phone, will send automatically.', saved: 'Saved', synced: 'Offline entries sent',
      estate: 'Estate', dayavg: 'Day avg', locked: 'Locked', dashboard: 'CEO dashboard', admin: 'Users',
      whoTitle: 'Who is entering data?', whoSub: 'Sign in with Google once on this phone. Your name is saved with every reading you enter.',
      notYou: 'Not you?', by: 'by' },
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
      h += `<tr class="${cls}"><td>${esc(r.name)}${miss ? ' <span class="missing">● no entry</span>' : ''}</td>`;
      for (const s of S) {
        const remarks = !isAvg && r.remarks_by_session?.[s]?.length
          ? `<div class="table-remarks">${r.remarks_by_session[s].map((remark, i) => `<button type="button" class="remark-bubble" data-remark="${esc(remark)}" aria-label="Show remark ${i + 1}" title="Show remark">💬</button>`).join('')}</div>`
          : '';
        h += `<td class="v ${isAvg ? '' : band(r[s], data.target, data.warn)}">${pct(r[s])}${remarks}</td>`;
      }
      h += `<td class="v ${isAvg ? '' : band(r.day_avg, data.target, data.warn)}">${pct(r.day_avg)}</td>`;
      h += `<td class="subcount">${r.submitted}/${r.expected}</td></tr>`;
    }
    h += `</tbody></table></div>
      <div class="legend"><span style="--c:var(--good-bg)">≥ ${pct(data.target)}</span><span style="--c:var(--warn-bg)">${pct(data.warn)} – ${pct(data.target)}</span><span style="--c:var(--bad-bg)">&lt; ${pct(data.warn)}</span><span style="--c:var(--avg-bg)">Averages (simple mean of estates that reported)</span></div>`;
    el.innerHTML = h;
  }

  function renderTrend(
    el,
    pts,
    target,
    {
      scale = 'full',
      series = ['HG', 'LG', 'ALL'],
      height = 360,
      interval = 'auto',
      estateName = 'Estate'
    } = {}
  ) {

    const W = Math.max(
      620,
      Math.round(el.clientWidth || 900)
    );

    const L = 58;
    const R = 24;
    const Tp = 36;
    const B = 48;

    const keys = [
      'HG',
      'LG',
      'ALL',
      'ESTATE'
    ].filter(k => series.includes(k));

    const vals = pts
      .flatMap(p => keys.map(k => p[k]))
      .filter(v => Number.isFinite(v));

    if (!keys.length) {
      el.innerHTML =
        '<p class="chart-empty">Select at least one series to show the trend.</p>';
      return;
    }

    if (!vals.length) {
      el.innerHTML =
        '<p class="chart-empty">No readings for the selected dates and series.</p>';
      return;
    }


    const allowedSteps = [
      1, 2, 5, 10, 20
    ];

    const requestedStep =
      allowedSteps.includes(Number(interval))
        ? Number(interval)
        : null;


    let lowPercent = 0;
    let highPercent = 100;


    if (scale === 'detail') {

      lowPercent = Math.max(
        0,
        Math.min(...vals, target) * 100 - 1
      );

      highPercent = Math.min(
        100,
        Math.max(...vals, target) * 100 + 1
      );
    }


    const maxIntervals =
      Math.max(
        2,
        Math.floor(
          (height - Tp - B) / 32
        )
      );


    const stepPercent =
      requestedStep ||
      allowedSteps.find(
        n =>
          (highPercent - lowPercent) / n
          <= maxIntervals
      ) ||
      20;


    lowPercent =
      Math.floor(
        lowPercent / stepPercent
      ) * stepPercent;


    highPercent =
      Math.ceil(
        highPercent / stepPercent
      ) * stepPercent;


    if (highPercent <= lowPercent) {
      lowPercent = 0;
      highPercent = 100;
    }


    const lo = lowPercent / 100;
    const hi = highPercent / 100;


    const tickCount =
      Math.round(
        (highPercent - lowPercent) /
        stepPercent
      ) + 1;


    const H =
      Math.max(
        height,
        (tickCount - 1) * 26 +
        Tp +
        B
      );


    const x = i =>
      L +
      (W - L - R) *
      (
        pts.length === 1
          ? 0.5
          : i / (pts.length - 1)
      );


    const y = v =>
      Tp +
      (H - Tp - B) *
      (
        1 -
        (v - lo) /
        (hi - lo)
      );


    const col = {
      ALL: 'var(--brand)',
      HG: 'var(--chart-hg, #2870bd)',
      LG: 'var(--chart-lg, #a66412)',
      ESTATE: 'var(--chart-estate, #7c3aed)'
    };


    const names = {
      ALL: 'Company',
      HG: 'High Grown',
      LG: 'Low Grown',
      ESTATE: estateName || 'Estate'
    };


    let svg =
      `<svg class="trend"
        style="height:${H}px;min-width:${W}px"
        viewBox="0 0 ${W} ${H}"
        role="img"
        aria-label="Leaf standard daily trend">

        <text x="${L}" y="16">
          Leaf standard (%)
        </text>`;


    for (
      let percent = lowPercent;
      percent <= highPercent;
      percent += stepPercent
    ) {

      const g = percent / 100;

      svg +=
        `<line
          x1="${L}"
          x2="${W - R}"
          y1="${y(g)}"
          y2="${y(g)}"
          stroke="var(--line)"
        />

        <text
          class="percentage-tick"
          x="${L - 10}"
          y="${y(g) + 4}"
          text-anchor="end"
        >${percent}%</text>`;
    }


    svg +=
      `<line
        x1="${L}"
        x2="${W - R}"
        y1="${y(target)}"
        y2="${y(target)}"
        stroke="var(--bad)"
        stroke-width="1.5"
        stroke-dasharray="6 5"
      />`;


    /*
     * X-axis:
     * normal 14-day view = every date
     * long periods = spaced date labels
     */
    const indices = new Set();


    if (pts.length <= 14) {

      pts.forEach(
        (_, i) => indices.add(i)
      );

    } else {

      const labels =
        Math.min(
          pts.length,
          Math.max(
            2,
            Math.floor(
              (W - L - R) / 115
            )
          )
        );


      Array.from(
        {length: labels},
        (_, i) =>
          labels === 1
            ? 0
            : Math.round(
                i *
                (pts.length - 1) /
                (labels - 1)
              )
      ).forEach(
        i => indices.add(i)
      );
    }


    indices.forEach(i => {

      const label =
        new Date(
          pts[i].date +
          'T00:00:00'
        )
        .toLocaleDateString(
          'en-GB',
          {
            day: '2-digit',
            month: 'short'
          }
        );


      svg +=
        `<text
          class="trend-date-label"
          x="${x(i)}"
          y="${H - 18}"
          text-anchor="${
            pts.length === 1
              ? 'middle'
              : i === 0
                ? 'start'
                : i === pts.length - 1
                  ? 'end'
                  : 'middle'
          }"
        >${esc(label)}</text>`;
    });


    /*
     * Only ONE series receives visible numeric labels:
     *
     * All estates -> Company
     * Estate chosen -> selected Estate
     */
    const valueLabelKey =
      keys.includes('ESTATE')
        ? 'ESTATE'
        : 'ALL';


    for (const k of keys) {

      let path = '';
      let pen = false;


      pts.forEach((p, i) => {

        if (!Number.isFinite(p[k])) {

          pen = false;
          return;
        }


        path +=
          `${pen ? 'L' : 'M'}` +
          `${x(i).toFixed(2)},` +
          `${y(p[k]).toFixed(2)} `;

        pen = true;
      });


      svg +=
        `<path
          d="${path}"
          fill="none"
          stroke="${col[k]}"
          stroke-width="${
            k === 'ALL'
              ? 3
              : k === 'ESTATE'
                ? 2.8
                : 2
          }"
          stroke-linejoin="round"
        />`;


      pts.forEach((p, i) => {

        if (!Number.isFinite(p[k]))
          return;


        const px = x(i);
        const py = y(p[k]);


        svg +=
          `<circle
            cx="${px}"
            cy="${py}"
            r="${
              pts.length > 90
                ? 2
                : (
                    k === 'ALL' ||
                    k === 'ESTATE'
                  )
                    ? 4
                    : 3
            }"
            fill="${col[k]}"
            stroke="var(--card)"
            stroke-width="1"
          >
            <title>
              ${esc(p.date)} ·
              ${names[k]}:
              ${pct(p[k])}
            </title>
          </circle>`;


        /*
         * Small clean value:
         * ONLY company or selected estate.
         */
        if (
          k === valueLabelKey &&
          pts.length <= 90
        ) {

          svg +=
            `<text
              class="trend-point-value"
              x="${px}"
              y="${py - 11}"
              text-anchor="middle"
            >${(p[k] * 100).toFixed(1)}</text>`;
        }

      });
    }


    svg += '</svg>';


    const legend =
      [
        'ALL',
        'HG',
        'LG',
        'ESTATE'
      ]
      .filter(
        k => keys.includes(k)
      )
      .map(
        k =>
          `<span style="--c:${col[k]}">` +
          `${names[k]}` +
          `</span>`
      )
      .join('');


    el.innerHTML =
      `<div
        class="chart-scroll"
        style="max-height:${height}px;overflow:auto"
        tabindex="0"
      >${svg}</div>` +

      `<p class="chart-axis-note muted">
        Percentage interval:
        ${stepPercent}%
        ${
          H > height
            ? ' · Scroll vertically to see the full percentage scale.'
            : ''
        }
      </p>` +

      `<div class="legend">
        ${legend}
        <span style="--c:var(--bad)">
          Target ${pct(target)} · dashed line
        </span>
      </div>`;
  }

  let activeRemarkPopover = null;
  function closeRemarkPopover() {
    if (activeRemarkPopover) { activeRemarkPopover.remove(); activeRemarkPopover = null; }
  }
  function openRemarkPopover(button) {
    closeRemarkPopover();
    const pop = document.createElement('div');
    pop.className = 'remark-popover';
    pop.setAttribute('role', 'dialog');
    pop.innerHTML = `<button type="button" class="remark-close" aria-label="Close remark">×</button><div class="remark-popover-title">Remark</div><div class="remark-popover-text"></div>`;
    pop.querySelector('.remark-popover-text').textContent = button.dataset.remark || '';
    pop.querySelector('.remark-close').onclick = closeRemarkPopover;
    document.body.appendChild(pop);
    const rect = button.getBoundingClientRect();
    const width = Math.min(320, Math.max(220, window.innerWidth - 24));
    pop.style.width = `${width}px`;
    let left = Math.min(Math.max(12, rect.left + rect.width / 2 - width / 2), window.innerWidth - width - 12);
    let top = rect.bottom + 8;
    pop.style.left = `${left}px`;
    pop.style.top = `${top}px`;
    const h = pop.getBoundingClientRect().height;
    if (top + h > window.innerHeight - 12) pop.style.top = `${Math.max(12, rect.top - h - 8)}px`;
    activeRemarkPopover = pop;
  }
  document.addEventListener('click', event => {
    const bubble = event.target.closest?.('.remark-bubble');
    if (bubble) { event.preventDefault(); event.stopPropagation(); openRemarkPopover(bubble); return; }
    if (!event.target.closest?.('.remark-popover')) closeRemarkPopover();
  });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') closeRemarkPopover(); });

  /* Google Sign-In button.
     box      - element containing a .gbtn child; un-hidden once Google's script loads
     endpoint - 'google-login' (login page: linked CEO/admin accounts)
                'identify'     (after estate QR login: record who is entering data)
     Google's script is initialised once per page; the latest button's handler wins. */
  let gHandler = null, gReady = null;
  function loadGis(clientId) {
    if (gReady) return gReady;
    gReady = new Promise((resolve, reject) => {
      const go = () => {
        google.accounts.id.initialize({
          client_id: clientId,
          auto_select: true,              // returning users signed in without a click
          cancel_on_tap_outside: false,
          use_fedcm_for_prompt: true,
          callback: resp => gHandler && gHandler(resp),
        });
        resolve();
      };
      if (window.google?.accounts?.id) return go();
      const s = document.createElement('script');
      s.src = 'https://accounts.google.com/gsi/client'; s.async = true; s.defer = true;
      s.onload = go; s.onerror = () => { gReady = null; reject(new Error('Google sign-in could not load - check your connection')); };
      document.head.appendChild(s);
    });
    return gReady;
  }

  function googleButton(box, clientId, onDone, onErr, endpoint = 'google-login') {
    if (!box || !clientId) return;
    gHandler = async resp => {
      try {
        const r = await api(endpoint, { method: 'POST', body: JSON.stringify({ credential: resp.credential }), noRedirect: true });
        store.set('token', r.token); store.set('user', JSON.stringify(r.user));
        onDone(r.user);
      } catch (e) { onErr && onErr(e); }
    };
    loadGis(clientId).then(() => {
      const slot = box.querySelector('.gbtn');
      slot.innerHTML = '';
      google.accounts.id.renderButton(slot, { theme: 'outline', size: 'large', text: 'signin_with', width: 300 });
      box.classList.remove('hidden');
      google.accounts.id.prompt();
    }).catch(e => onErr && onErr(e));   // offline: password login still works
  }

  function googleForget() { try { window.google?.accounts?.id?.disableAutoSelect(); } catch (e) {} }

  function logout() { googleForget(); store.set('token', null); store.set('user', null); location.href = base; }

  return { api, store, base, t, setLang, get lang() { return lang; }, pct, iso, addDays, nice, esc, band, renderTable, renderTrend, logout, googleButton, googleForget };
})();