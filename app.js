/* PRIN 2026: every number below is computed from the published unit records. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const fmt = new Intl.NumberFormat('it-IT');
  const dec = new Intl.NumberFormat('it-IT', {maximumFractionDigits: 1});
  const currency = (n) => `${fmt.format(n)} €`;
  const compact = (n) => n >= 1e6 ? `${dec.format(n / 1e6)} mln €` : n >= 1e3 ? `${dec.format(n / 1e3)} mila €` : currency(n);
  const escape = (v) => String(v ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const fold = (v) => String(v ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  const area = (u) => u.program === 'hybrid' ? 'HYB' : u.sector.slice(0, 2);
  const programName = (p) => p === 'hybrid' ? 'PRIN Hybrid' : 'PRIN 2026';
  const sectorName = (s) => ({CYB: 'Cybersicurezza', IA: 'Intelligenza artificiale'})[s] || s;
  const areaName = (a) => ({PE: 'Scienze fisiche e ingegneristiche', LS: 'Scienze della vita', SH: 'Scienze sociali e umanistiche', HYB: 'Trasversale · Hybrid'})[a] || a;
  const safeSource = (s) => { try { const u = new URL(s); return u.protocol === 'https:' && u.hostname === 'www.mur.gov.it' ? u.href : ''; } catch { return ''; } };
  const state = {data: null, filtered: [], ranking: [], focus: null};
  const controls = {search: $('search'), program: $('program'), area: $('area'), sector: $('sector'), role: $('role'), sort: $('sort')};

  function dateLabel(iso) {
    if (!iso) return 'Data da verificare';
    const d = new Date(`${iso.slice(0,10)}T12:00:00Z`);
    return Number.isNaN(d.getTime()) ? iso : new Intl.DateTimeFormat('it-IT', {day:'numeric', month:'long', year:'numeric', timeZone:'Europe/Rome'}).format(d);
  }
  function checkLabel(iso) {
    if (!iso) return 'Fotografia iniziale in attesa del primo aggiornamento automatico';
    const d = new Date(iso);
    return `Ultimo controllo: ${new Intl.DateTimeFormat('it-IT', {dateStyle:'medium',timeStyle:'short',timeZone:'Europe/Rome'}).format(d)}`;
  }
  function query() {
    const p = new URLSearchParams(location.search);
    if (p.has('program')) controls.program.value = p.get('program');
    if (!controls.program.value) controls.program.value = 'all';
    refreshOptions();
    if (p.has('area')) controls.area.value = p.get('area');
    if (!controls.area.value) controls.area.value = 'all';
    refreshOptions();
    for (const name of ['search','sector','role','sort']) if (p.has(name)) {
      controls[name].value = p.get(name);
      if (!controls[name].value && name !== 'search') controls[name].value = name === 'sort' ? 'funding' : 'all';
    }
  }
  function syncQuery() {
    if (location.protocol === 'file:') return; // Standalone offline preview.
    const p = new URLSearchParams();
    for (const [k, input] of Object.entries(controls)) if (input.value && input.value !== 'all' && !(k === 'sort' && input.value === 'funding')) p.set(k, input.value);
    if (state.focus) p.set('sede', state.focus);
    history.replaceState(null, '', location.pathname + (p.size ? `?${p}` : '') + location.hash);
  }
  function sourceStats() {
    const d = state.data;
    const warnings = d.warnings || [];
    const check = checkLabel(d.checkedAt);
    $('statusLine').innerHTML = `<span class="status-badge ${warnings.length ? 'attention' : ''}">${warnings.length ? 'Copertura parziale' : 'Risultati acquisiti'}</span> Dati al ${escape(dateLabel(d.asOf))} · ${d.sources.length} allegati · ${escape(check)}`;
    $('coverageLabel').textContent = `${d.coverage.ordinary.length} settori PRIN · ${d.coverage.hybrid.length} linee Hybrid`;
    $('sourceDate').textContent = `Dati al ${dateLabel(d.asOf)} · ${d.sources.length} documenti`;
    $('sourceState').textContent = `${d.provenance} ${check}.`;
    $('docCount').textContent = `(${d.sources.length})`;
    $('documents').innerHTML = [...d.sources].sort((a,b) => a.program.localeCompare(b.program) || a.sector.localeCompare(b.sector,'it',{numeric:true})).map(s => {
      const url = safeSource(s.pdf);
      return url ? `<a href="${escape(url)}" target="_blank" rel="noopener noreferrer">${escape(programName(s.program))} · ${escape(sectorName(s.sector))} · DD ${escape(s.decreto)} ↗</a>` : '';
    }).join('');
    $('sourceWarnings').hidden = !warnings.length;
    $('sourceWarnings').innerHTML = warnings.length ? `<strong>Documenti da verificare</strong><ul>${warnings.map(w => `<li>${escape(w)}</li>`).join('')}</ul>` : '';
  }
  function options(select, values, label, titles = {}) {
    const prev = select.value;
    select.replaceChildren();
    select.add(new Option(label, 'all'));
    for (const value of values) select.add(new Option(titles[value] || sectorName(value), value));
    select.value = values.includes(prev) ? prev : 'all';
  }
  function refreshOptions() {
    const p = controls.program.value;
    const list = state.data.units.filter(u => p === 'all' || u.program === p);
    const areas = [...new Set(list.map(area))].sort((a,b) => ['PE','LS','SH','HYB'].indexOf(a) - ['PE','LS','SH','HYB'].indexOf(b));
    options(controls.area, areas, 'Tutte le aree', Object.fromEntries(areas.map(a => [a, areaName(a)])));
    const narrowed = list.filter(u => controls.area.value === 'all' || area(u) === controls.area.value);
    const sectors = [...new Set(narrowed.map(u => u.sector))].sort((a,b) => a.localeCompare(b,'it',{numeric:true}));
    options(controls.sector, sectors, 'Tutti i settori / linee');
  }
  function group(units) {
    const map = new Map();
    for (const u of units) {
      const key = u.cf || fold(u.ateneo).replace(/\W/g, '');
      if (!map.has(key)) map.set(key, {key, names:new Map(), units:[], projects:new Set(), pi:new Set(), ru:new Set(), piFunding:0, ruFunding:0});
      const row = map.get(key);
      row.units.push(u);
      row.names.set(u.ateneo, (row.names.get(u.ateneo) || 0) + 1);
      row.projects.add(`${u.program}/${u.project}`);
      row[u.role === 'PI' ? 'pi' : 'ru'].add(`${u.program}/${u.project}`);
      row[u.role === 'PI' ? 'piFunding' : 'ruFunding'] += Number(u.mur);
    }
    return [...map.values()].map(r => {
      r.name = [...r.names].sort((a,b) => b[1]-a[1] || a[0].length-b[0].length)[0][0];
      r.funding = r.piFunding + r.ruFunding;
      return r;
    });
  }
  function sortRows(rows) {
    const kind = controls.sort.value;
    rows.sort((a,b) => kind === 'name' ? a.name.localeCompare(b.name, 'it') :
      (kind === 'projects' ? b.projects.size - a.projects.size : kind === 'pi' ? b.pi.size - a.pi.size : b.funding - a.funding) || b.funding-a.funding || a.name.localeCompare(b.name,'it'));
  }
  function filteredUnits() {
    const {program, area: areaInput, sector, role, search} = controls;
    const term = fold(search.value.trim());
    return state.data.units.filter(u =>
      (program.value === 'all' || u.program === program.value) &&
      (areaInput.value === 'all' || area(u) === areaInput.value) &&
      (sector.value === 'all' || u.sector === sector.value) &&
      (role.value === 'all' || u.role === role.value) &&
      (!term || fold([u.ateneo,u.cf,u.responsabile,u.project,u.unit,u.titolo].join(' ')).includes(term))
    );
  }
  function renderKpis(units, rows) {
    const projects = new Set(units.map(u => `${u.program}/${u.project}`)).size;
    const total = units.reduce((sum,u) => sum + Number(u.mur), 0);
    $('kpiProjects').textContent = fmt.format(projects);
    $('kpiFunding').textContent = compact(total);
    $('kpiFunding').title = currency(total);
    $('kpiInstitutions').textContent = fmt.format(rows.length);
    $('kpiUnits').textContent = fmt.format(units.length);
    $('rolesHint').textContent = `${fmt.format(units.filter(u=>u.role==='PI').length)} PI · ${fmt.format(units.filter(u=>u.role==='RU').length)} RU`;
    $('matchSummary').innerHTML = `<strong>${fmt.format(rows.length)} sedi</strong> · ${fmt.format(projects)} progetti · ${currency(total)}`;
  }
  function renderChart(rows) {
    const top = [...rows].sort((a,b) => b.funding-a.funding);
    $('chartTag').textContent = `${fmt.format(top.length)} sedi`;
    const max = top[0]?.funding || 1;
    $('chart').innerHTML = top.length ? top.map(r => `<div class="bar-row"><div class="bar-head"><button type="button" data-key="${escape(r.key)}" title="${escape(r.name)}">${escape(r.name)}</button><strong>${escape(compact(r.funding))}</strong></div><div class="bar-track" role="img" aria-label="${escape(r.name)}: ${escape(currency(r.piFunding))} come PI, ${escape(currency(r.ruFunding))} come RU"><span class="bar-piece pi" style="width:${(100*r.piFunding/max).toFixed(2)}%"></span><span class="bar-piece ru" style="width:${(100*r.ruFunding/max).toFixed(2)}%"></span></div></div>`).join('') : '<p class="empty">Nessuna sede corrisponde ai filtri.</p>';
  }
  function renderTable(rows) {
    const part = rows;
    $('rankBody').innerHTML = part.length ? part.map((r,i) => `<tr><td class="rank-no">${i+1}</td><td><button type="button" class="inst-button" data-key="${escape(r.key)}">${escape(r.name)}<span class="inst-sub">CF ${escape(r.key)}</span></button></td><td class="num">${fmt.format(r.projects.size)}</td><td class="num">${fmt.format(r.pi.size)}</td><td class="num">${fmt.format(r.ru.size)}</td><td class="num money-col">${escape(currency(r.funding))}<span class="funding-split">PI ${escape(compact(r.piFunding))} · RU ${escape(compact(r.ruFunding))}</span></td><td><button type="button" class="row-arrow" data-key="${escape(r.key)}" aria-label="Apri ${escape(r.name)}">↗</button></td></tr>`).join('') : '<tr><td colspan="7" class="empty">Nessuna sede trovata. Prova ad allargare i filtri.</td></tr>';
    $('showing').textContent = `Mostrate ${fmt.format(part.length)} di ${fmt.format(rows.length)} sedi`;
  }
  function render() {
    if (!state.data) return;
    state.filtered = filteredUnits();
    state.ranking = group(state.filtered);
    sortRows(state.ranking);
    renderKpis(state.filtered,state.ranking);
    renderChart(state.ranking);
    renderTable(state.ranking);
    $('exportBtn').disabled = state.filtered.length === 0;
    syncQuery();
  }
  function detail(key) {
    const row = state.ranking.find(r => r.key === key);
    if (!row) return;
    state.focus = key;
    $('detailTitle').textContent = row.name;
    $('detailSubtitle').textContent = `Codice fiscale ${row.key} · risultati con i filtri correnti`;
    const projects = new Map();
    for (const u of row.units) {
      const k = `${u.program}/${u.project}`;
      if (!projects.has(k)) projects.set(k, {title:u.titolo || u.project, program:u.program, sector:u.sector, code:u.project, units:[], amount:0});
      const project = projects.get(k);
      project.units.push(u);
      project.amount += Number(u.mur);
    }
    const list = [...projects.values()].sort((a,b) => b.amount-a.amount);
    $('detailContent').innerHTML = `<div class="detail-metrics"><div><strong>${fmt.format(row.projects.size)}</strong><span>progetti distinti</span></div><div><strong>${fmt.format(row.pi.size)} / ${fmt.format(row.ru.size)}</strong><span>come PI / RU</span></div><div><strong>${escape(compact(row.funding))}</strong><span>contributo MUR</span></div></div><p class="detail-split">Contributo come PI: <strong>${escape(currency(row.piFunding))}</strong> · Come RU: <strong>${escape(currency(row.ruFunding))}</strong></p><p class="detail-heading">Progetti e unità (${list.length})</p>` + list.map(p => `<article class="project-card"><div class="project-top"><div><strong>${escape(p.title)}</strong><small>${escape(programName(p.program))} · ${escape(sectorName(p.sector))} · ${escape(p.code)}</small></div><span class="project-amount">${escape(currency(p.amount))}</span></div>${p.units.map(u => `<div class="project-bottom"><span><span class="role-chip ${u.role==='RU'?'ru':''}">${escape(u.role)}</span> ${escape(u.responsabile)} · ${escape(u.unit)}</span>${safeSource(u.source) ? `<a href="${escape(safeSource(u.source))}" target="_blank" rel="noopener noreferrer">Tabella B ↗</a>` : ''}</div>`).join('')}</article>`).join('');
    const dialog = $('detailDialog');
    dialog.showModal();
    syncQuery();
  }
  function toast(message) {
    const el = $('toast'); el.textContent = message; el.classList.add('visible');
    clearTimeout(toast.timer); toast.timer = setTimeout(()=>el.classList.remove('visible'),2800);
  }
  function exportCsv() {
    const headers = ['Bando','Area','Settore o linea','Codice progetto','Titolo','Codice unità','Ruolo','Sede','Codice fiscale','Responsabile','Contributo MUR (EUR)','Decreto','PDF ufficiale'];
    const safe = value => { let s = String(value ?? ''); if (/^[\s]*[=+\-@]/.test(s)) s = "'"+s; return `"${s.replaceAll('"','""')}"`; };
    const lines = [headers,...state.filtered.map(u => [programName(u.program),areaName(area(u)),sectorName(u.sector),u.project,u.titolo,u.unit,u.role,u.ateneo,u.cf,u.responsabile,u.mur,u.decreto,u.source])].map(row=>row.map(safe).join(';'));
    const blob = new Blob(['\ufeff'+lines.join('\r\n')], {type:'text/csv;charset=utf-8'});
    const url = URL.createObjectURL(blob), a = document.createElement('a');
    a.href = url; a.download = `prin-2026-sedi-${state.data.asOf}.csv`; a.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
    toast('CSV della selezione scaricato');
  }
  async function loadData(initial=false) {
    try {
      const initialSeat = initial ? new URLSearchParams(location.search).get('sede') : null;
      const response = await fetch(`./data/prin.json?v=${Date.now()}`, {cache:'no-store'});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (!Array.isArray(data.units) || !Array.isArray(data.sources) || !data.coverage) throw new Error('Formato dati non riconosciuto');
      const changed = JSON.stringify([data.checkedAt,data.asOf,data.warnings]) !== JSON.stringify([state.data?.checkedAt,state.data?.asOf,state.data?.warnings]);
      state.data = data;
      if (initial) query();
      refreshOptions(); sourceStats(); render();
      if (initialSeat) {
        detail(initialSeat);
      } else if (changed && !initial) toast('Risultati aggiornati');
    } catch (err) {
      if (initial) {
        $('statusLine').textContent = 'Dati temporaneamente non disponibili';
        $('rankBody').innerHTML = '<tr><td colspan="7" class="empty">Impossibile caricare i dati. Riprova più tardi.</td></tr>';
        $('sourceState').textContent = 'Il file dei risultati non è raggiungibile.';
      } else toast('Controllo aggiornamenti non riuscito; resta visibile l’ultima versione');
      console.error('PRIN data load:',err);
    }
  }
  for (const [name,input] of Object.entries(controls)) {
    input.addEventListener(name === 'search' ? 'input' : 'change', () => {
      if (!state.data) return;
      if (name === 'program' || name === 'area') refreshOptions();
      render();
    });
  }
  $('resetBtn').addEventListener('click',()=>{for(const [k,input] of Object.entries(controls)) input.value = k === 'search' ? '' : k === 'sort' ? 'funding' : 'all'; refreshOptions();render();});
  $('exportBtn').addEventListener('click',exportCsv);
  for (const id of ['chart','rankBody']) $(id).addEventListener('click',e => {const target=e.target.closest('[data-key]');if(target) detail(target.dataset.key);});
  $('closeDialog').addEventListener('click',()=>$('detailDialog').close());
  $('detailDialog').addEventListener('close',()=>{state.focus=null;syncQuery();});
  $('shareBtn').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(location.href);toast('Link ai filtri copiato');}catch{toast('Copia il link dalla barra degli indirizzi');}});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden && state.data?.checkedAt && Date.now()-Date.parse(state.data.checkedAt)>30*60*1000)loadData();});
  setInterval(()=>{if(!document.hidden) loadData();},30*60*1000);
  loadData(true);
})();
