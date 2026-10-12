'use strict';
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const state = { chapters: [], lessons: [], filter: 'all', cls: 8, subject: 'science', health: null, open: null, tab: 'script', details: null };
const STAGES = ['scope', 'evidence', 'plan', 'script', 'narration', 'visuals', 'render', 'assemble', 'done'];
const STAGE_SHORT = { scope: 'Request', evidence: 'Sources', plan: 'Plan', script: 'Script', narration: 'Voice', visuals: 'Pictures', render: 'Animate', assemble: 'Assemble', done: 'Ready' };
const STATUS_TEXT = { queued: 'Queued', running: 'In progress', succeeded: 'Ready', failed: 'Failed', interrupted: 'Interrupted', cancelled: 'Cancelled' };
const CH_STATUS = { planned: 'Planned', recording: 'Recording voice…', recorded: 'Voice recorded', drawing: 'Drawing picture…', drawn: 'Picture ready', coding: 'Coding scene…', rendering: 'Rendering…', reviewing: 'Reviewing…', animating: 'Animating…', ready: 'Ready', failed: 'Failed' };
const ROUTE_LABEL = { image: 'PICTURE', diagram: 'DIAGRAM', coded: 'CODED', slide: 'SLIDES' };
const money = (v) => (v ? `$${v < 0.01 ? v.toFixed(4) : v.toFixed(2)}` : '$0');

async function api(path, options = {}) {
  const res = await fetch(path, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, ...options });
  if (res.status === 401) { showSignin(); throw new Error('Sign in to continue'); }
  const body = res.headers.get('content-type')?.includes('json') ? await res.json() : null;
  if (!res.ok) throw new Error(body?.detail || `Request failed (${res.status})`);
  return body;
}

// ---------------------------------------------------------------- sign in
function showSignin() { $('#signin').hidden = false; $('#app').hidden = true; }
$('#signin-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const err = $('#signin-error'); err.hidden = true;
  try {
    await api('/api/session', { method: 'POST', body: JSON.stringify({ token: $('#access-key').value }) });
    $('#signin').hidden = true; boot();
  } catch (x) { err.textContent = x.message; err.hidden = false; }
});
$('#signout').addEventListener('click', async () => { await api('/api/session', { method: 'DELETE' }); showSignin(); });

// ---------------------------------------------------------------- composer
const SUBJECT_LABEL = { science: 'Science', physics: 'Physics', chemistry: 'Chemistry', biology: 'Biology', maths: 'Maths' };
function renderChips() {
  $('#class-chips').innerHTML = [6, 7, 8, 9, 10, 11, 12].map((c) => `<button type="button" role="radio" aria-checked="${c === state.cls}" data-cls="${c}">Class ${c}</button>`).join('');
  const subjects = Object.keys(SUBJECT_LABEL).filter((k) => state.chapters.some((c) => c.class === state.cls && c.subject === k));
  if (subjects.length && !subjects.includes(state.subject)) state.subject = subjects[0];
  $('#subject-chips').innerHTML = subjects.map((k) => `<button type="button" role="radio" aria-checked="${k === state.subject}" data-subject="${k}">${SUBJECT_LABEL[k]}</button>`).join('');
  const options = state.chapters.filter((c) => c.class === state.cls && c.subject === state.subject);
  const current = $('#chapter').value;
  $('#chapter').innerHTML = '<option value="">No chapter (use web research)</option>' + options.map((c) =>
    `<option value="${c.id}">Ch ${c.chapter} · ${esc(c.title)}</option>`).join('');
  if (options.some((c) => c.id === current)) $('#chapter').value = current;
  updateRule();
}
$('#class-chips').addEventListener('click', (e) => { const b = e.target.closest('[data-cls]'); if (b) { state.cls = +b.dataset.cls; $('#chapter').value = ''; renderChips(); } });
$('#subject-chips').addEventListener('click', (e) => { const b = e.target.closest('[data-subject]'); if (b) { state.subject = b.dataset.subject; $('#chapter').value = ''; renderChips(); } });
$('#chapter').addEventListener('change', updateRule);
$('#web').addEventListener('change', updateRule);
function updateRule() {
  const chapter = $('#chapter').value, web = $('#web').checked, open = $('#class-level').value === 'open';
  const note = $('#ground-rule');
  note.classList.toggle('warn', !chapter && !web && !open);
  note.textContent = chapter && web ? 'Textbook first; the web only fills gaps.' : chapter ? 'Grounded in this chapter only.'
    : web ? 'Grounded in web sources. Choose the level below.'
    : open ? 'No sources: with no level limit the planner teaches from its own knowledge; reviewers still check every fact.'
    : 'Pick a chapter, turn on web research, or both (or choose No level limit below to skip sources).';
  // With a chapter the level defaults to the chapter's class but can be raised (or opened up) for stress tests.
  const fromChapter = $('#class-from-chapter');
  fromChapter.disabled = !chapter;
  if (chapter && !fromChapter.dataset.touched) $('#class-level').value = '';
  if (!chapter && $('#class-level').value === '') $('#class-level').value = String(state.cls);
}
const fmtLen = (s) => (s < 60 ? `about ${s} s` : `about ${Math.floor(s / 60)} min${s % 60 ? ` ${s % 60} s` : ''}`);
$('#length').addEventListener('input', () => { $('#length-out').textContent = fmtLen(+$('#length').value); });

$('#create').addEventListener('submit', async (e) => {
  e.preventDefault();
  const err = $('#create-error'); err.hidden = true;
  const chapter = $('#chapter').value || null;
  const body = {
    topic: $('#topic').value, chapter, web_research: $('#web').checked,
    class_level: levelValue($('#class-level').value),
    mode: $('input[name=mode]:checked').value, duration_seconds: +$('#length').value,
    voice: $('#voice').value, notes: $('#notes').value, include_history: $('#history').checked,
  };
  if ($('#config').value) body.config = $('#config').value;
  if (body.topic.trim().length < 3) { err.textContent = 'Describe what the lesson should teach.'; err.hidden = false; $('#topic').focus(); return; }
  if (!chapter && !body.web_research && body.class_level !== 'open') { err.textContent = 'Pick a chapter, turn on web research, or both (or choose No level limit to skip sources).'; err.hidden = false; return; }
  const btn = $('#create-btn'); btn.disabled = true; btn.textContent = 'Creating…';
  try {
    const lesson = await api('/api/lessons', { method: 'POST', body: JSON.stringify(body) });
    $('#topic').value = ''; $('#notes').value = '';
    await refresh(); openLesson(lesson.id);
  } catch (x) { err.textContent = x.message; err.hidden = false; }
  finally { btn.disabled = false; btn.textContent = 'Create lesson'; }
});

// ---------------------------------------------------------------- library
function levelValue(v) { return v === '' ? null : v === 'open' ? 'open' : +v; }
function levelName(v) { return v === 'open' ? 'No level limit' : `Class ${v}`; }
$('#class-level').addEventListener('change', () => { $('#class-from-chapter').dataset.touched = '1'; updateRule(); });
function chapterCite(req) {
  if (!req.chapter) return `${req.web_research ? 'Web research' : 'No sources'} · ${levelName(req.class_level)}`;
  const c = state.chapters.find((x) => x.id === req.chapter);
  return c ? `Class ${c.class} · ${SUBJECT_LABEL[c.subject] || c.subject} · Ch ${c.chapter} ${c.title}` : req.chapter;
}
function stageIndex(lesson) { const i = STAGES.indexOf(lesson.progress?.stage); return i < 0 ? 0 : i; }
function progressPct(lesson) {
  if (lesson.status === 'succeeded') return 100;
  const i = stageIndex(lesson);
  const chapters = lesson.chapters || [];
  const within = chapters.length ? chapters.filter((c) => ['ready'].includes(c.status)).length / chapters.length : 0;
  return Math.min(97, Math.round(((i + (i >= 4 ? within : .4)) / (STAGES.length - 1)) * 100));
}
function ago(t) {
  const s = Math.max(1, Math.round(Date.now() / 1000 - t));
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return new Date(t * 1000).toLocaleDateString();
}
function matches(l) {
  if (state.filter === 'active') return ['queued', 'running'].includes(l.status);
  if (state.filter === 'ready') return l.status === 'succeeded';
  if (state.filter === 'attention') return ['failed', 'interrupted', 'cancelled'].includes(l.status);
  return true;
}
function renderCards() {
  const list = state.lessons.filter(matches);
  $('#empty').hidden = state.lessons.length > 0;
  $('#cards').innerHTML = list.map((l) => {
    const active = ['queued', 'running'].includes(l.status);
    const thumb = l.files?.poster
      ? `<div class="thumb"><img src="${l.files.poster}" alt="" loading="lazy"></div>`
      : `<div class="thumb pending ${['failed', 'interrupted', 'cancelled'].includes(l.status) ? 'failed' : ''}"><div class="orbit"></div></div>`;
    const note = l.status === 'failed' || l.status === 'interrupted' ? (l.error || '') : (l.progress?.message || '');
    return `<button class="card" data-id="${l.id}">${thumb}<div class="card-body">
      <p class="cite">${esc(chapterCite(l.request))}</p>
      <h3>${esc(l.title || l.request.topic)}</h3>
      ${l.config?.preset ? `<p class="cite">${esc(l.config.preset)}${l.usage?.cost ? ' · ' + money(l.usage.cost) : ''}${l.production_seconds ? ' · ' + duration(l.production_seconds) + (['queued', 'running'].includes(l.status) ? ' so far' : '') : ''}</p>` : ''}
      <div class="status-row"><span class="pill ${l.status}">${STATUS_TEXT[l.status] || l.status}</span><span class="time">${ago(l.updated)}</span></div>
      ${active ? `<div class="progress" aria-hidden="true"><span style="width:${progressPct(l)}%"></span></div>` : ''}
      ${note && l.status !== 'succeeded' ? `<p class="progress-note">${esc(note)}</p>` : ''}
    </div></button>`;
  }).join('');
}
$('#cards').addEventListener('click', (e) => { const c = e.target.closest('.card'); if (c) openLesson(c.dataset.id); });
$('.filters').addEventListener('click', (e) => {
  const b = e.target.closest('[data-filter]'); if (!b) return;
  state.filter = b.dataset.filter;
  $$('.filters button').forEach((x) => x.setAttribute('aria-selected', String(x === b)));
  renderCards();
});

// ---------------------------------------------------------------- lesson detail
async function openLesson(id) {
  state.open = id; state.tab = 'script'; state.details = null;
  $$('.tabs button').forEach((x) => x.setAttribute('aria-selected', String(x.dataset.tab === 'script')));
  const dlg = $('#detail');
  if (!dlg.open) dlg.showModal();
  history.replaceState(null, '', '#' + id);
  await renderDetail(true);
}
$('#detail-close').addEventListener('click', () => $('#detail').close());
$('#detail').addEventListener('close', () => { state.open = null; history.replaceState(null, '', location.pathname); });
$('.tabs').addEventListener('click', (e) => {
  const b = e.target.closest('[data-tab]'); if (!b) return;
  state.tab = b.dataset.tab;
  $$('.tabs button').forEach((x) => x.setAttribute('aria-selected', String(x === b)));
  renderTab();
});

async function renderDetail(full) {
  const id = state.open; if (!id) return;
  const lesson = await api(`/api/lessons/${id}`);
  if (full || !state.details || ['queued', 'running'].includes(lesson.status)) state.details = await api(`/api/lessons/${id}/details`);
  $('#detail-title').textContent = lesson.title || lesson.request.topic;
  $('#detail-cite').textContent = chapterCite(lesson.request);
  // player
  const player = $('#player');
  if (lesson.status === 'succeeded' && lesson.files.video) {
    if (!player.querySelector('video')) {
      // Captions are burned into the video; adding the VTT track as well would show them twice.
      player.innerHTML = `<video controls preload="metadata" poster="${lesson.files.poster || ''}" src="${lesson.files.video}"></video>`;
    }
  } else {
    const failed = ['failed', 'interrupted', 'cancelled'].includes(lesson.status);
    player.innerHTML = `<div class="wait">${failed ? '' : '<div class="orbit"></div>'}<strong>${failed ? STATUS_TEXT[lesson.status] : esc(lesson.progress?.label || 'Waiting to start')}</strong>
      <span>${esc(failed ? (lesson.error || 'Stopped') : (lesson.progress?.message || ''))}</span></div>`;
  }
  // actions
  const acts = [];
  if (lesson.files.video) acts.push(`<a class="btn small primary" href="${lesson.files.video}" download>Download video</a>`);
  if (lesson.files.captions) acts.push(`<a class="btn small" href="${lesson.files.captions}" download>Caption file (.vtt)</a>`);
  if (['queued', 'running'].includes(lesson.status)) acts.push(`<button class="btn small" data-act="cancel">Cancel</button>`);
  if (['failed', 'interrupted', 'cancelled'].includes(lesson.status)) acts.push(`<button class="btn small primary" data-act="resume">Resume from saved work</button>`);
  if (!['queued', 'running'].includes(lesson.status)) acts.push(`<button class="btn small ghost danger" data-act="delete">Delete</button>`);
  $('#detail-actions').innerHTML = acts.join('');
  // stepper
  const now = stageIndex(lesson);
  $('#stepper').innerHTML = STAGES.slice(0, 8).map((s, i) => {
    let cls = lesson.status === 'succeeded' || i < now ? 'done' : i === now ? (['failed', 'interrupted'].includes(lesson.status) ? 'fail' : 'now') : '';
    return `<li class="${cls}">${STAGE_SHORT[s]}</li>`;
  }).join('');
  // chapters
  const chapters = lesson.chapters || [];
  const idle = !['queued', 'running'].includes(lesson.status);
  $('#chapter-list').innerHTML = chapters.length ? chapters.map((c) => `<li><div><span class="route">${ROUTE_LABEL[c.route] || c.route}${c.history ? ' · HISTORY' : ''}${c.complexity && c.route === 'coded' ? ' · ' + esc(c.complexity) : ''}</span>
    <h3>${esc(c.title)}</h3><span class="ch-status">${esc(CH_STATUS[c.status] || c.status)}${c.detail ? ' · ' + esc(c.detail) : ''}</span>
    ${idle && c.status === 'ready' ? `<button class="btn ghost small redo" data-redo="${c.id}">${c.route === 'image' ? 'Redraw picture' : c.route === 'coded' ? 'Redo scene' : 'Redo diagram'}</button>` : ''}</div></li>`).join('')
    : '<li class="muted" style="display:block">Chapters appear once the lesson is planned.</li>';
  renderTab(lesson);
}
$('#detail-actions').addEventListener('click', async (e) => {
  const b = e.target.closest('[data-act]'); if (!b) return;
  const id = state.open, act = b.dataset.act;
  if (act === 'delete') {
    if (b.dataset.confirm !== '1') { b.dataset.confirm = '1'; b.textContent = 'Click again to delete'; return; }
    await api(`/api/lessons/${id}`, { method: 'DELETE' }); $('#detail').close(); await refresh(); return;
  }
  b.disabled = true;
  try { await api(`/api/lessons/${id}/${act}`, { method: 'POST' }); } catch (x) { alertInline(x.message); }
  await refresh(); await renderDetail(true);
});
$('#chapter-list').addEventListener('click', async (e) => {
  const b = e.target.closest('[data-redo]'); if (!b) return;
  if (b.dataset.confirm !== '1') { b.dataset.confirm = '1'; b.textContent = 'Click again to redo'; return; }
  b.disabled = true; b.textContent = 'Queued…';
  try { await api(`/api/lessons/${state.open}/chapters/${b.dataset.redo}/redo`, { method: 'POST' }); }
  catch (x) { alertInline(x.message); }
  await refresh(); await renderDetail(true);
});
function alertInline(msg) { $('#detail-actions').insertAdjacentHTML('beforeend', `<p class="error">${esc(msg)}</p>`); }

function renderTab(lesson) {
  const d = state.details || {}, body = $('#tab-body');
  if (state.tab === 'script') {
    const plan = d.plan, script = d.script;
    if (!script) { body.innerHTML = `<p class="muted">${plan ? 'The narration is being written.' : 'The script appears after planning.'}</p>` + (plan ? planBlock(plan) : ''); return; }
    body.innerHTML = script.chapters.map((sc, i) => {
      const pc = plan.chapters[i];
      const cards = (sc.slides || []).map((c) => `<span class="cue" title="${esc(c.summary || (c.labels || []).join(' · '))}">${esc(c.kind)} · ${esc(c.heading)}</span>`).join('');
      const cues = cards + (sc.cues || []).map((c) => c.show ? `<span class="cue" title="on “${esc(c.phrase || '')}”">${esc(c.show)}</span>`
        : `<span class="cue" title="${esc(c.phrase || '')}">${esc(c.verb)}${c.object || c.target ? ' · ' + esc(c.object || c.target) : ''}${c.text ? ' “' + esc(c.text) + '”' : ''}</span>`).join('');
      return `<div class="script-ch"><p class="eyebrow">${pc.route === 'image' ? 'Picture' : pc.route === 'slide' ? (pc.history ? 'Slides · history' : 'Slides') : pc.route === 'coded' ? `Coded · ${esc(pc.complexity || '')}` : 'Diagram'} · ${esc(pc.objective)}</p><h3>${esc(pc.title)}</h3>
        ${sc.points.map((p) => `<p>${esc(p.narration)}</p>`).join('')}<div>${cues}</div></div>`;
    }).join('');
  } else if (state.tab === 'sources') {
    const items = d.evidence?.items || [];
    const notes = (d.evidence?.notes || []).map((n) => `<p class="rule-note">${esc(n)}</p>`).join('');
    body.innerHTML = notes + (items.length ? items.map((e) => `<div class="source ${e.source}"><span class="kind">${e.id} · ${e.source === 'ncert' ? 'TEXTBOOK' : 'WEB'}</span>
      <strong>${esc(e.cite)}</strong><p>${esc(e.text.slice(0, 420))}${e.text.length > 420 ? '…' : ''}</p></div>`).join('') : '<p class="muted">Sources appear after the evidence step.</p>');
  } else {
    const r = d.report;
    const events = (d.events || []).slice(-40).map((e) => `${new Date(e.updated * 1000).toLocaleTimeString()}  ${e.label || e.stage}: ${e.message || ''}`).join('\n');
    const usage = r?.model_usage || lesson?.usage?.by_connection || {};
    const config = r?.config;
    body.innerHTML = (r ? `<dl class="kv"><dt>Length</dt><dd>${r.duration_seconds} s</dd><dt>Video</dt><dd>${r.video.width}×${r.video.height}, ${r.video.codec}, full decode ${r.video.full_decode}</dd>
      ${config ? `<dt>Configuration</dt><dd>${esc(config.preset?.label || 'Custom settings')} · ${esc(config.scene_route)} route</dd>` : ''}
      ${Object.entries(usage).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v.calls} calls · ${v.input_tokens.toLocaleString()} in / ${v.output_tokens.toLocaleString()} out · ${Math.round(v.seconds)} s${v.cost ? ' · ' + money(v.cost) : ''}</dd>`).join('')}
      <dt>Human review</dt><dd>${esc(r.human_review)}</dd></dl><ul class="checklist">${r.checks.map((c) => `<li>${esc(c)}</li>`).join('')}</ul>
      ${Object.entries(r.warnings || {}).map(([ch, list]) => list.map((w) => `<p class="rule-note warn">${esc(ch)}: ${esc(w)}</p>`).join('')).join('')}` : '<p class="muted">Checks are listed when the lesson is ready.</p>')
      + `<h3>Activity</h3><div class="log">${esc(events || 'No activity yet.')}</div>`;
  }
}
function planBlock(plan) {
  return `<div class="script-ch"><h3>${esc(plan.title)}</h3><p class="muted">${esc(plan.big_idea || '')}</p>
    ${plan.chapters.map((c) => `<p><strong>${esc(c.title)}</strong> — ${esc(c.objective)} <span class="cue">${c.route}</span></p>`).join('')}</div>`;
}

// ---------------------------------------------------------------- health & polling
async function loadHealth() {
  try {
    const h = await api('/api/health');
    const names = { planner: 'Models', images: 'Pictures', voice: 'Voice', animation: 'Animation', textbooks: 'Textbooks' };
    $('#services').innerHTML = Object.entries(h.services).map(([k, ok]) => `<li class="${ok ? '' : 'down'}" title="${names[k]} ${ok ? 'available' : 'unavailable'}">${names[k] || k}</li>`).join('');
  } catch { /* shown on next poll */ }
}
async function refresh() {
  const data = await api('/api/lessons');
  state.lessons = data.lessons; renderCards();
}
let ticks = 0;
async function poll() {
  try {
    await refresh();
    if (state.open) await renderDetail(false);
    if (++ticks % 10 === 0) loadHealth();
  } catch { /* transient */ }
  const active = state.lessons.some((l) => ['queued', 'running'].includes(l.status));
  setTimeout(poll, active ? 3000 : 10000);
}

function renderConfigPicker(data) {
  const current = $('#config').value;
  const active = data.active_preset ? data.presets[data.active_preset]?.label : null;
  $('#config').innerHTML = `<option value="">Current settings${active ? ' (' + esc(active) + ')' : ''}</option>`
    + Object.entries(data.presets).map(([id, p]) => `<option value="${esc(id)}">${esc(p.label)}${p.benchmark ? ' ★' : ''}</option>`).join('');
  if ([...$('#config').options].some((o) => o.value === current)) $('#config').value = current;
}
async function boot() {
  $('#app').hidden = false;
  const cat = await api('/api/catalog');
  state.chapters = cat.chapters;
  api('/api/settings/models').then(renderConfigPicker).catch(() => {});
  renderChips(); loadHealth();
  await refresh();
  const hash = location.hash.slice(1);
  if (/^[0-9a-f]{32}$/.test(hash)) openLesson(hash);
  poll();
}
(async () => {
  try { const s = await api('/api/session'); if (s.signed_in) boot(); else showSignin(); } catch { showSignin(); }
})();

// ---------------------------------------------------------------- settings: models per step
const settingsState = { data: null };
$('#open-settings').addEventListener('click', async () => { $('#settings').showModal(); await loadSettings(); });
$('#settings-close').addEventListener('click', () => $('#settings').close());
function showSettingsTab(name) {
  if (!$(`#spanel-${name}`)) name = 'workflow';
  $$('#settings-tabs [data-stab]').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.stab === name)));
  $$('#settings .settings-panel').forEach((p) => { p.hidden = p.id !== `spanel-${name}`; });
  try { localStorage.setItem('scivid.settingsTab', name); } catch (_) {}
}
$('#settings-tabs').addEventListener('click', (e) => { const b = e.target.closest('[data-stab]'); if (b) showSettingsTab(b.dataset.stab); });
try { showSettingsTab(localStorage.getItem('scivid.settingsTab') || 'workflow'); } catch (_) { showSettingsTab('workflow'); }

async function loadSettings() {
  settingsState.data = await api('/api/settings/models');
  renderSettings();
}
function connectionOk(c, step) {
  return step.allowed_types.includes(c.type) && (!step.needs_images || c.vision);
}
function usedBy(c) {
  const d = settingsState.data;
  const names = d.steps.filter((s) => c.in_use.includes(s.id)).map((s) => s.label);
  return names.length ? 'Used by: ' + names.join(', ') : 'Not used yet';
}
function connectionOptions(step) {
  const d = settingsState.data;
  return Object.entries(d.connections).filter(([, c]) => connectionOk(c, step))
    .map(([id, c]) => `<option value="${esc(id)}" ${d.assignments[step.id] === id ? 'selected' : ''}>${esc(c.label)}</option>`).join('');
}
function renderSettings() {
  const d = settingsState.data;
  renderConfigPicker(d);
  const route = d.options.scene_route;
  $('#presets').innerHTML = Object.keys(d.presets).length ? Object.entries(d.presets).map(([id, p]) => {
    const active = d.active_preset === id;
    const lines = d.steps.filter((s) => !s.route || s.route === (p.options?.scene_route || route))
      .map((s) => `${esc(s.label)}: ${esc(d.connections[p.steps[s.id]]?.label || p.steps[s.id] || '—')}`).join('<br>');
    return `<div class="connection preset${active ? ' active' : ''}">
      <h3>${esc(p.label)}${p.benchmark ? '<span class="badge warn">benchmark</span>' : ''}${active ? '<span class="badge">current</span>' : ''}</h3>
      ${p.note ? `<p class="note muted">${esc(p.note)}</p>` : ''}
      <span class="meta">${esc((p.options?.scene_route || 'diagram'))} route</span>
      <details><summary class="muted small-text">Models per step</summary><p class="meta">${lines}</p></details>
      <div class="actions">${active ? '' : `<button class="btn small" data-apply="${esc(id)}">Apply</button>`}
        <button class="btn small ghost danger" data-pdel="${esc(id)}">Delete</button></div>
      <span class="muted small-text" data-presult="${esc(id)}"></span></div>`;
  }).join('') : '<p class="muted">No saved configurations yet.</p>';
  $('#options').innerHTML = Object.entries(d.option_specs).map(([key, spec]) => `<label for="opt-${key}">${esc(spec.label)}</label>
    <select id="opt-${key}" data-option="${key}">${spec.choices.map(([v, l]) => `<option value="${v}" ${d.options[key] === v ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>`).join('');
  const stepRow = (step) => {
    const options = connectionOptions(step);
    const badges = (step.needs_images ? '<span class="badge">images</span>' : '')
      + (step.status === 'next' ? '<span class="badge next">next</span>' : '');
    const offRoute = step.route && step.route !== route;
    return `<div class="flow-step${step.status === 'next' ? ' is-next' : ''}${offRoute ? ' off-route' : ''}">
      <div><label class="step-name" for="step-${step.id}">${esc(step.label)}</label>${badges}${step.route ? `<span class="badge route">${step.route} route</span>` : ''}
        <p class="muted small-text">${esc(step.description)}</p></div>
      <select id="step-${step.id}" data-step="${step.id}">${options || '<option value="">No suitable connection</option>'}</select></div>`;
  };
  const makers = d.stages.map((stage) => [stage, d.steps.filter((s) => s.stage === stage.id && !s.rubrics)]).filter(([, steps]) => steps.length);
  $('#steps-flow').innerHTML = makers.map(([stage, steps], i) => `<li class="flow-stage">
      <div class="flow-head"><span class="flow-num">${i + 1}</span><div><h4>${esc(stage.label)}</h4>
        <p class="muted small-text">${esc(stage.description)}</p></div></div>
      ${steps.map(stepRow).join('')}</li>`).join('');
  $('#connections').innerHTML = Object.entries(d.connections).map(([id, c]) => `<div class="connection">
      <h3>${esc(c.label)}${c.vision ? '<span class="badge">images</span>' : ''}${c.key_set === false ? '<span class="badge bad">no key</span>' : ''}</h3>
      <span class="meta">${esc(d.types[c.type]?.label || c.type)}</span>
      <span class="meta">${esc(c.model)}</span><span class="meta">${esc(c.url)}</span>
      <span class="muted small-text">${usedBy(c)}</span>
      <div class="actions"><button class="btn small" data-test="${esc(id)}">Test</button>
        <button class="btn small ghost" data-edit="${esc(id)}">Edit</button>
        <button class="btn small ghost danger" data-del="${esc(id)}">Delete</button></div>
      <span class="muted small-text" data-result="${esc(id)}"></span></div>`).join('');
  $('#c-type').innerHTML = Object.entries(d.types).map(([k, t]) => `<option value="${k}">${esc(t.label)}</option>`).join('');
  renderReviews();
  renderRuns();
  loadFindings();
}
function renderReviews() {
  const d = settingsState.data, route = d.options.scene_route;
  const kinds = Object.fromEntries((d.reviews || []).map((r) => [r.kind, r]));
  const scale = ['0 · accept anything', '1 · serious problems allowed', '2 · small flaws allowed', '3 · must be right'];
  const rubric = (r, titled) => `${titled ? `<h5>${esc(r.label)}</h5>` : ''}
    <table class="review-table"><tbody>${r.criteria.map((c) => `<tr>
      <td><strong>${esc(c.label)}</strong>${c.routes ? ` <span class="muted small-text">(${esc(c.routes.join(', '))} route)</span>` : ''}<br><span class="muted small-text">${esc(c.question)}</span></td>
      <td><select data-kind="${esc(r.kind)}" data-criterion="${esc(c.id)}" aria-label="Minimum score for ${esc(c.label)}">${scale.map((label, v) =>
        `<option value="${v}"${v === c.minimum ? ' selected' : ''}>${esc(label)}${v === c.default ? ' (default)' : ''}</option>`).join('')}</select></td>
    </tr>`).join('')}</tbody></table>`;
  $('#reviews').innerHTML = d.steps.filter((s) => s.rubrics).map((step) => {
    const own = step.rubrics.map((k) => kinds[k]).filter(Boolean), options = connectionOptions(step);
    const offRoute = step.route && step.route !== route;
    return `<div class="review-kind${offRoute ? ' off-route' : ''}">
      <div class="review-head"><div><label class="step-name" for="rstep-${step.id}">${esc(step.label)}</label>${step.needs_images ? '<span class="badge">images</span>' : ''}${step.route ? `<span class="badge route">${step.route} route</span>` : ''}
        <p class="muted small-text">${esc(step.description)}</p></div>
        <select id="rstep-${step.id}" data-step="${step.id}" aria-label="Model for ${esc(step.label)}">${options || '<option value="">No suitable connection</option>'}</select></div>
      ${own.length ? own.map((r) => rubric(r, own.length > 1)).join('') : '<p class="muted small-text">No criteria: the auditor judges other reviewers\' findings on the Reviewer accuracy tab.</p>'}
    </div>`;
  }).join('');
}

$('#save-reviews').addEventListener('click', async () => {
  const msg = $('#reviews-msg');
  try { await saveSelections();
    renderSettings(); msg.textContent = 'Saved. New lessons will use these reviewers and minimums.'; msg.classList.remove('warn'); }
  catch (x) { msg.textContent = x.message; msg.classList.add('warn'); }
  msg.hidden = false;
});

const findingsState = { data: null };
async function loadFindings() {
  const review = $('#findings-review').value, unjudged = $('#findings-unjudged').checked;
  try {
    findingsState.data = await api(`/api/findings?limit=40&review=${encodeURIComponent(review)}&judged=${unjudged ? 'no' : ''}`);
  } catch (x) { $('#findings').innerHTML = `<p class="muted">${esc(x.message)}</p>`; return; }
  renderFindings();
}

function verdictOf(marks) { return (marks?.human || marks?.auditor || {}).verdict; }

function renderFindings() {
  const d = findingsState.data; if (!d) return;
  const pct = (v) => v === null || v === undefined ? '—' : `${Math.round(v * 100)}%`;
  $('#accuracy').innerHTML = `<thead><tr><th>Reviewer</th><th>Review</th><th>Criterion</th><th>Findings</th><th>Judged</th><th>Wrong</th><th>False positives</th></tr></thead><tbody>${
    d.stats.map((r) => `<tr><td>${esc(r.reviewer)}</td><td>${esc(r.review_label)}</td><td>${esc(r.label)}</td><td>${r.findings}</td><td>${r.judged}${r.unsure ? ` (+${r.unsure} unsure)` : ''}</td><td>${r.wrong}</td><td><strong>${pct(r.false_positive_rate)}</strong></td></tr>`).join('')}</tbody>`;
  const sel = $('#findings-review');
  if (sel.options.length === 1) {
    [...new Set(d.stats.map((r) => r.review + '|' + r.review_label))].forEach((v) => { const [id, label] = v.split('|'); sel.add(new Option(label, id)); });
  }
  const a = d.audit || {};
  const msg = $('#audit-msg');
  if (a.running || a.total) { msg.hidden = false; msg.textContent = a.running ? `Auditing… ${a.done} of ${a.total}` : `Last audit: ${a.done} judged${a.errors ? `, ${a.errors} failed` : ''}.`; }
  $('#findings').innerHTML = d.findings.length ? d.findings.map((f) => {
    const v = verdictOf(f.marks), auditor = f.marks?.auditor, human = f.marks?.human;
    return `<div class="finding" data-id="${esc(f.id)}">
      <div class="finding-head"><span class="route">${esc(f.review_label)} · ${esc(f.label)}${f.score !== null ? ` ${f.score}/3 (needs ${f.minimum})` : ''}</span>
        <span class="muted small-text">${esc(f.reviewer)} · ${esc(f.lesson_title || f.lesson)}</span></div>
      ${f.has_image ? `<img class="finding-img" loading="lazy" alt="What the reviewer saw" src="/api/findings/${esc(f.id)}/image">` : ''}
      <p>${esc(f.reason)}</p>${f.fix ? `<p class="muted small-text">Fix asked: ${esc(f.fix)}</p>` : ''}
      ${auditor ? `<p class="small-text">Auditor: <strong>${esc(auditor.verdict)}</strong> — ${esc(auditor.note || '')}</p>` : ''}
      <div class="verdicts">${['right', 'wrong', 'unsure'].map((x) => `<button class="btn small${human?.verdict === x ? ' primary' : ''}" data-verdict="${x}">${x === 'right' ? 'Right' : x === 'wrong' ? 'Wrong (false positive)' : 'Unsure'}</button>`).join('')}
        ${v ? `<span class="muted small-text">Counts as: ${esc(v)}</span>` : ''}</div></div>`;
  }).join('') : '<p class="muted">No findings to show.</p>';
}

$('#findings').addEventListener('click', async (e) => {
  const b = e.target.closest('button[data-verdict]'); if (!b) return;
  const id = b.closest('.finding').dataset.id;
  try { await api(`/api/findings/${id}/label`, { method: 'POST', body: JSON.stringify({ verdict: b.dataset.verdict }) }); loadFindings(); }
  catch (x) { alert(x.message); }
});
$('#findings-review').addEventListener('change', loadFindings);
$('#findings-unjudged').addEventListener('change', loadFindings);
$('#audit-btn').addEventListener('click', async () => {
  try { await api('/api/findings/audit', { method: 'POST', body: JSON.stringify({ limit: 40 }) }); } catch (x) { alert(x.message); }
  const poll = setInterval(async () => { await loadFindings(); if (!findingsState.data?.audit?.running) clearInterval(poll); }, 5000);
  loadFindings();
});

function duration(s) { return s >= 3600 ? `${Math.floor(s / 3600)} h ${Math.round((s % 3600) / 60)} min` : `${Math.max(1, Math.round(s / 60))} min`; }

function renderRuns() {
  const fmtTime = duration;
  const rows = state.lessons.slice(0, 40).map((l) => {
    const tokens = l.usage ? `${Math.round(l.usage.input_tokens / 1000)}k / ${Math.round(l.usage.output_tokens / 1000)}k` : '—';
    const coded = (l.chapters || []).filter((c) => c.route === 'coded');
    return `<tr><td><button class="linkish" data-run="${l.id}">${esc(l.title || l.request.topic)}</button><br><span class="muted small-text">${esc(chapterCite(l.request))}</span></td>
      <td>${esc(l.config?.preset || 'Custom')}<br><span class="muted small-text">${esc(l.config?.scene_route || '')}${coded.length ? ' · ' + coded.map((c) => c.complexity?.[0] || '?').join('') : ''}</span></td>
      <td><span class="pill ${l.status}">${STATUS_TEXT[l.status] || l.status}</span></td>
      <td class="num">${money(l.usage?.cost || 0)}</td><td class="num">${tokens}</td>
      <td class="num">${l.production_seconds ? fmtTime(l.production_seconds) + (['queued', 'running'].includes(l.status) ? '…' : '') : '…'}</td></tr>`;
  }).join('');
  $('#runs').innerHTML = `<thead><tr><th>Lesson</th><th>Configuration</th><th>Status</th><th>Model cost</th><th>Tokens in / out</th><th>Time</th></tr></thead><tbody>${rows || '<tr><td colspan="6" class="muted">No lessons yet.</td></tr>'}</tbody>`;
}
$('#options').addEventListener('change', (e) => {
  const sel = e.target.closest('[data-option="scene_route"]'); if (!sel) return;
  $$('#steps-flow .flow-step, #reviews .review-kind').forEach((row) => {
    const badge = row.querySelector('.badge.route');
    row.classList.toggle('off-route', !!badge && !badge.textContent.startsWith(sel.value));
  });
});
$('#runs').addEventListener('click', (e) => { const b = e.target.closest('[data-run]'); if (b) { $('#settings').close(); openLesson(b.dataset.run); } });
$('#presets').addEventListener('click', async (e) => {
  const b = e.target.closest('button'); if (!b) return;
  const id = b.dataset.apply || b.dataset.pdel;
  if (b.dataset.pdel && b.dataset.confirm !== '1') { b.dataset.confirm = '1'; b.textContent = 'Click again to delete'; return; }
  try {
    settingsState.data = b.dataset.apply
      ? await api(`/api/settings/presets/${encodeURIComponent(id)}/apply`, { method: 'POST' })
      : await api(`/api/settings/presets/${encodeURIComponent(id)}`, { method: 'DELETE' });
    renderSettings();
  } catch (x) { $(`[data-presult="${CSS.escape(id)}"]`).textContent = x.message; }
});
// Everything the Workflow and Reviews tabs show, saved as the current settings (a configuration copies these).
async function saveSelections() {
  const options = {}, assignments = {}, rules = {};
  $$('#options select').forEach((s) => { options[s.dataset.option] = s.value; });
  $$('#steps-flow select[data-step], #reviews select[data-step]').forEach((s) => { if (s.value) assignments[s.dataset.step] = s.value; });
  $$('#reviews select[data-kind]').forEach((s) => { (rules[s.dataset.kind] = rules[s.dataset.kind] || {})[s.dataset.criterion] = +s.value; });
  await api('/api/settings/options', { method: 'PUT', body: JSON.stringify({ options }) });
  await api('/api/settings/steps', { method: 'PUT', body: JSON.stringify({ assignments }) });
  settingsState.data = await api('/api/settings/review-rules', { method: 'PUT', body: JSON.stringify({ rules }) });
}
$('#preset-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const msg = $('#p-msg');
  try {
    await saveSelections();
    settingsState.data = await api('/api/settings/presets', { method: 'POST', body: JSON.stringify({
      label: $('#p-label').value, note: $('#p-note').value, benchmark: $('#p-benchmark').checked }) });
    $('#p-label').value = ''; $('#p-note').value = ''; $('#p-benchmark').checked = false;
    msg.textContent = 'Saved with the models and review minimums chosen on the Workflow and Reviews tabs; it is now the current configuration.'; renderSettings();
  } catch (x) { msg.textContent = x.message; }
});

$('#save-steps').addEventListener('click', async () => {
  const msg = $('#steps-msg');
  try { await saveSelections();
    renderSettings(); msg.textContent = 'Saved. New lessons will use these models.'; msg.classList.remove('warn'); }
  catch (x) { msg.textContent = x.message; msg.classList.add('warn'); }
  msg.hidden = false;
});

$('#connections').addEventListener('click', async (e) => {
  const t = e.target.closest('button'); if (!t) return;
  if (t.dataset.test) {
    const out = $(`[data-result="${CSS.escape(t.dataset.test)}"]`);
    out.textContent = 'Testing…';
    const r = await api(`/api/settings/test/${encodeURIComponent(t.dataset.test)}`, { method: 'POST' });
    out.textContent = r.ok ? `Working (${r.seconds} s)` : `Failed: ${r.error || 'unexpected reply'}`;
  } else if (t.dataset.edit) {
    openConnectionForm(t.dataset.edit);
  } else if (t.dataset.del) {
    if (t.dataset.confirm !== '1') { t.dataset.confirm = '1'; t.textContent = 'Click again to delete'; return; }
    try { settingsState.data = await api(`/api/settings/connections/${encodeURIComponent(t.dataset.del)}`, { method: 'DELETE' }); renderSettings(); }
    catch (x) { $(`[data-result="${CSS.escape(t.dataset.del)}"]`).textContent = x.message; }
  }
});

function typeInfo() { return settingsState.data.types[$('#c-type').value]; }
function updateFormForType(keepUrl) {
  const kind = $('#c-type').value, info = typeInfo();
  $('#c-key-field').hidden = !info.needs_key;
  $('#c-effort-field').hidden = !['openai_responses', 'anthropic'].includes(kind);
  $('#c-vision-field').hidden = kind === 'anthropic';
  if (!keepUrl) { $('#c-url').value = info.default_url || ''; $('#c-model').value = info.default_model || ''; }
  $('#c-url').placeholder = info.default_url || 'http://10.8.0.4:18080/v1';
  $('#c-detect').hidden = !info.detects_models;
}
$('#c-type').addEventListener('change', () => updateFormForType(false));
function openConnectionForm(id) {
  const d = settingsState.data, c = id ? d.connections[id] : null;
  $('#connection-form-wrap').hidden = false;
  $('#connection-form-title').textContent = c ? `Edit ${c.label}` : 'Add connection';
  $('#c-id').value = id || '';
  $('#c-type').value = c ? c.type : 'openai_chat';
  $('#c-type').disabled = !!c;
  updateFormForType(!!c);
  $('#c-label').value = c ? c.label : '';
  if (c) { $('#c-url').value = c.url; $('#c-model').value = c.model; $('#c-effort').value = c.reasoning_effort || 'medium'; }
  $('#c-vision').checked = c ? !!c.vision : false;
  $('#c-key').value = '';
  $('#c-key-note').textContent = c && c.key_set ? 'A key is saved. Leave blank to keep it.' : '';
  settingsState.models = []; $('#c-picker').hidden = true; $('#c-filter').value = '';
  $('#c-detect-note').textContent = ''; $('#c-error').hidden = true;
  $('#connection-form-wrap').scrollIntoView({ behavior: 'smooth', block: 'start' });
}
$('#add-connection').addEventListener('click', () => openConnectionForm(null));
$('#c-cancel').addEventListener('click', () => { $('#connection-form-wrap').hidden = true; });
$('#c-detect').addEventListener('click', async () => {
  const note = $('#c-detect-note'); note.textContent = 'Asking the server…';
  try {
    const r = await api('/api/settings/detect', { method: 'POST', body: JSON.stringify({
      type: $('#c-type').value, url: $('#c-url').value, api_key: $('#c-key').value || null, id: $('#c-id').value || null }) });
    settingsState.models = r.models;
    if (r.models.length === 1) { $('#c-model').value = r.models[0]; $('#c-picker').hidden = true; }
    else { $('#c-filter').value = ''; renderModelList(); $('#c-picker').hidden = false; $('#c-filter').focus(); }
    note.textContent = r.models.length === 1 ? '1 model found and selected' : `${r.models.length} models found — search and pick one below`;
  } catch (x) { note.textContent = x.message; }
});
function renderModelList() {
  const q = $('#c-filter').value.trim().toLowerCase();
  const list = settingsState.models.filter((m) => !q || m.toLowerCase().includes(q));
  const current = $('#c-model').value;
  $('#c-model-list').innerHTML = list.slice(0, 300).map((m) => `<option value="${esc(m)}" ${m === current ? 'selected' : ''}>${esc(m)}</option>`).join('')
    + (list.length > 300 ? `<option disabled>… ${list.length - 300} more, refine the search</option>` : '')
    + (list.length ? '' : '<option disabled>No model matches</option>');
}
$('#c-filter').addEventListener('input', renderModelList);
$('#c-filter').addEventListener('keydown', (e) => {
  if (e.key === 'ArrowDown') { e.preventDefault(); $('#c-model-list').focus(); }
  if (e.key === 'Enter') { e.preventDefault(); const first = $('#c-model-list').options[0]; if (first && !first.disabled) { $('#c-model').value = first.value; renderModelList(); } }
});
$('#c-model-list').addEventListener('change', (e) => { if (e.target.value) $('#c-model').value = e.target.value; });
$('#connection-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const err = $('#c-error'); err.hidden = true;
  const body = { id: $('#c-id').value || undefined, type: $('#c-type').value, label: $('#c-label').value,
    url: $('#c-url').value, model: $('#c-model').value, vision: $('#c-type').value === 'anthropic' || $('#c-vision').checked,
    reasoning_effort: $('#c-effort').value };
  if ($('#c-key').value) body.api_key = $('#c-key').value;
  try {
    settingsState.data = await api('/api/settings/connections', { method: 'POST', body: JSON.stringify(body) });
    $('#connection-form-wrap').hidden = true; renderSettings();
  } catch (x) { err.textContent = x.message; err.hidden = false; }
});
