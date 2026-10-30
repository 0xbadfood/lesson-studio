'use strict';
const STUDIO = window.STUDIO || {name: 'History Studio', mark: 'H', subject: 'history', key_ideas: false};
const view = document.getElementById('view');
if (STUDIO.solve) document.getElementById('nav-solve').hidden = false;
const state = { catalog: null, voices: null, cls: null, timer: null, ideaTimer: null, activityTimer: null, questionTimer: null };

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const minutes = (m) => (m < 1.25 ? 'about a minute' : `about ${Math.round(m)} min`);

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options });
  if (response.status === 401) { showLogin(); throw new Error('signed out'); }
  const body = await response.json().catch(() => ({}));
  // FastAPI's validation errors are a list of objects: show their messages, not "[object Object]"
  const detail = Array.isArray(body.detail) ? body.detail.map((d) => d.msg || String(d)).join('; ') : body.detail;
  if (!response.ok) throw new Error(detail || 'Something went wrong');
  return body;
}

function chrome(on, nav) {
  document.getElementById('top').hidden = !on;
  document.getElementById('foot').hidden = !on;
  document.querySelectorAll('[data-nav]').forEach((a) => a.classList.toggle('on', a.dataset.nav === nav));
}

function stopPolling() {
  clearTimeout(state.timer); state.timer = null; clearTimeout(state.ideaTimer); state.ideaTimer = null;
  clearTimeout(state.activityTimer); state.activityTimer = null;
  clearTimeout(state.questionTimer); state.questionTimer = null;
}

/* ---------------------------------------------------------------- sign in */
function showLogin() {
  stopPolling();
  chrome(false);
  view.innerHTML = `
    <div class="login"><form class="sheet" id="login">
      <div class="mark">${STUDIO.mark}</div>
      <h1>${STUDIO.name}</h1>
      <p>Short films for every idea in your ${STUDIO.subject} textbook. Enter your access code to begin.</p>
      <input class="field" id="code" autocomplete="one-time-code" placeholder="xxxx-xxxx-xxxx" aria-label="Access code" required>
      <p class="error" id="error"></p>
      <button class="btn" style="width:100%">Enter the studio</button>
    </form></div>`;
  document.getElementById('code').focus();
  document.getElementById('login').addEventListener('submit', async (e) => {
    e.preventDefault();
    const error = document.getElementById('error');
    error.textContent = '';
    try {
      await api('api/login', { method: 'POST', body: JSON.stringify({ code: document.getElementById('code').value }) });
      route();
    } catch (err) { error.textContent = err.message === 'signed out' ? '' : err.message; }
  });
}

/* ---------------------------------------------------------------- chapters */
async function loadCatalog(force) {
  if (!state.catalog || force) state.catalog = await api('api/catalog');
  return state.catalog;
}

function badge(concept) {
  if (concept.ready) return '<span class="badge ready"><i class="dot"></i>Ready to watch</span>';
  if (concept.film) return '<span class="badge making"><i class="dot"></i>Being made</span>';
  return '';
}

async function showHome() {
  chrome(true, 'home');
  const data = await loadCatalog(true);
  const available = data.classes.map((c) => c.class);
  if (!available.includes(state.cls)) state.cls = available[0];
  const current = data.classes.find((c) => c.class === state.cls);
  view.innerHTML = `
    <section class="hero">
      <div class="eyebrow">NCERT · Classes 6 to 12</div>
      <h1>Every chapter, told as a story.</h1>
      <p>Choose your class and a chapter, then pick an idea. We turn it into a short narrated film, true to your textbook.</p>
    </section>
    <div class="classes" role="tablist" aria-label="Class">
      ${data.all_classes.map((n) => `
        <button class="class ${n === state.cls ? 'on' : ''}" data-class="${n}" ${available.includes(n) ? '' : 'disabled'} role="tab">
          <b>${n}</b><span>${available.includes(n) ? 'Class ' + n : 'Coming soon'}</span></button>`).join('')}
    </div>
    ${(current ? current.subjects : []).map((s) => `
      <div class="section-title"><h2>${esc(s.name)}</h2><span>${esc(s.chapters[0]?.book || '')}</span></div>
      <div class="grid">
        ${s.chapters.map((ch) => {
          const ready = ch.concepts.filter((c) => c.ready).length;
          return `<a class="card" href="#/chapter/${ch.id}">
            <span class="chapter-no">Chapter ${ch.number}</span>
            <h3>${esc(ch.title)}</h3>
            <div class="meta"><span>${ch.concepts.length} ideas</span>${ready ? `<span class="badge ready">${ready} ready</span>` : ''}</div>
          </a>`;
        }).join('')}
      </div>`).join('')}`;
  view.querySelectorAll('[data-class]').forEach((b) => b.addEventListener('click', () => { state.cls = +b.dataset.class; showHome(); }));
}

function findChapter(data, id) {
  for (const c of data.classes) for (const s of c.subjects) for (const ch of s.chapters) if (ch.id === id) return { cls: c.class, subject: s, chapter: ch };
  return null;
}

async function showChapter(id) {
  chrome(true, 'home');
  const data = await loadCatalog(true);
  const found = findChapter(data, id);
  if (!found) { view.innerHTML = '<p class="empty">That chapter is not here yet.</p>'; return; }
  const { cls, subject, chapter } = found;
  view.innerHTML = `
    <nav class="crumbs"><a href="#/">Class ${cls}</a><span>›</span><span>${esc(subject.name)}</span></nav>
    <section class="chapter-head">
      <span class="chapter-no">Chapter ${chapter.number} · ${esc(chapter.book)}</span>
      <h1>${esc(chapter.title)}</h1>
      <p>${chapter.concepts.length} ideas from this chapter. Each one becomes its own film, as long as it needs to be.</p>
    </section>
    <div class="concepts">
      ${chapter.concepts.map((c, i) => `
        <button class="card concept" data-concept="${c.id}">
          <span class="num">${i + 1}</span>
          <span><h3>${esc(c.name)}</h3><p>${esc(c.summary)}</p>
            <span class="meta"><span>${minutes(c.minutes)}</span>${badge(c)}</span></span>
          <span class="go">${c.ready ? 'Watch ›' : c.film ? 'See progress ›' : 'Make film ›'}</span>
        </button>`).join('')}
    </div>
    <div id="plays"></div>`;
    if (STUDIO.plays) showPlayCards(id);
  view.querySelectorAll('[data-concept]').forEach((b) => b.addEventListener('click', () => {
    const concept = chapter.concepts.find((c) => c.id === b.dataset.concept);
    if (concept.film) location.hash = `#/film/${concept.film}`;
    else confirmFilm(chapter, concept);
  }));
}

async function confirmFilm(chapter, concept) {
  if (!state.voices) state.voices = await api('api/voices').catch(() => ({ voices: [] }));
  const voices = state.voices.voices || [];
  const back = document.createElement('div');
  back.className = 'sheet-back';
  back.innerHTML = `
    <div class="sheet" role="dialog" aria-modal="true" aria-labelledby="sheet-title">
      <span class="chapter-no">Chapter ${chapter.number} · ${esc(chapter.title)}</span>
      <h2 id="sheet-title">${esc(concept.name)}</h2>
      <p>${esc(concept.summary)}</p>
      <ul>
        <li>Follows your textbook, section by section, and covers the whole idea.</li>
        <li>Runs ${minutes(concept.minutes)}, narrated, with illustrated scenes.</li>
        <li>Takes a while to make. You can watch it take shape, or come back later.</li>
      </ul>
      ${voices.length ? `<label class="chapter-no" for="voice">Narrator · ${voices.length} voices</label>
        <div class="voice-row">
          <select class="field" id="voice">
            ${['male', 'female', 'other'].filter((g) => voices.some((v) => v.gender === g)).map((g) => `
              <optgroup label="${g === 'male' ? 'Male voices' : g === 'female' ? 'Female voices' : 'Other voices'}">
                ${voices.filter((v) => v.gender === g).map((v) => `<option value="${esc(v.id)}">${esc(v.label)}</option>`).join('')}
              </optgroup>`).join('')}
          </select>
          <button class="btn ghost listen" type="button" data-listen aria-label="Play a sample of this voice">▶ Listen</button>
        </div>` : ''}
      <p class="error" id="sheet-error"></p>
      <div class="actions">
        <button class="btn ghost" data-close>Not now</button>
        <button class="btn" data-make>Make this film</button>
      </div>
    </div>`;
  document.body.appendChild(back);
  const sample = new Audio();
  const close = () => { sample.pause(); back.remove(); };
  const listen = back.querySelector('[data-listen]');
  if (listen) {
    const select = back.querySelector('#voice');
    const reset = () => { listen.textContent = '▶ Listen'; };
    sample.addEventListener('ended', reset);
    select.addEventListener('change', () => { sample.pause(); reset(); });
    listen.addEventListener('click', () => {
      if (!sample.paused) { sample.pause(); reset(); return; }
      sample.src = voices.find((v) => v.id === select.value).sample;
      sample.play();
      listen.textContent = '■ Stop';
    });
  }
  back.addEventListener('click', (e) => { if (e.target === back || e.target.hasAttribute('data-close')) close(); });
  back.querySelector('[data-make]').addEventListener('click', async (e) => {
    e.target.disabled = true;
    e.target.textContent = 'Starting…';
    try {
      const voice = back.querySelector('#voice')?.value;
      const made = await api('api/films', { method: 'POST', body: JSON.stringify({ chapter: chapter.id, concept: concept.id, ...(voice ? { voice } : {}) }) });
      close();
      location.hash = `#/film/${made.film}`;
    } catch (err) {
      back.querySelector('#sheet-error').textContent = err.message;
      e.target.disabled = false;
      e.target.textContent = 'Make this film';
    }
  });
}

/* ---------------------------------------------------------------- film */
function stepsHtml(f) {
  const keys = f.phases.map((p) => p.key);
  const at = f.status === 'done' ? keys.length : Math.max(0, keys.indexOf(f.phase));
  return `<aside class="steps"><h3>${f.status === 'done' ? 'Your film is ready' : f.status === 'waiting' ? 'Waiting to start' : f.status === 'stopped' ? 'Stopped' : f.status === 'failed' ? 'Could not finish' : 'Making your film'}</h3>
    ${f.phases.map((p, i) => {
      const cls = ['waiting', 'stopped', 'failed'].includes(f.status) ? '' : i < at ? 'done' : i === at && f.status === 'making' ? 'now' : '';
      return `<div class="step ${cls}"><span class="ring">✓</span><span><b>${esc(p.title)}</b>${cls === 'now' ? `<span>${esc(p.line)}</span>` : ''}</span></div>`;
    }).join('')}</aside>`;
}

function nowPanel(f) {
  if (f.status === 'failed') return `<div class="panel"><h2>This film hit a snag</h2><p class="sub">Something went wrong while making it. Making it again carries on from where it stopped, with any fixes made since; Behind the scenes shows what went wrong.</p>
      <button class="btn" id="again" type="button">Make it again</button></div>`;
  if (f.status === 'stopped') return `<div class="panel"><h2>You stopped this film</h2><p class="sub">Nothing is lost: making it again carries on from where it stopped.</p>
      <button class="btn" id="again" type="button">Make it again</button></div>`;
  const stop = '<button class="btn ghost stop" id="stop" type="button">Stop</button>';
  if (f.status === 'waiting') return `<div class="panel now-line"><div class="spinner"></div><div><h2>In the queue</h2><p class="sub">${f.ahead ? `${f.ahead} film${f.ahead > 1 ? 's' : ''} ahead of yours. ` : ''}Films are made one at a time; yours starts soon.</p></div>${stop}</div>`;
  if (f.status !== 'making') return '';
  const p = f.phases.find((x) => x.key === f.phase) || f.phases[0];
  const n = f.phases.indexOf(p) + 1;
  return `<div class="panel now-line"><div class="spinner"></div><div><span class="step-count">Step ${n} of ${f.phases.length}</span><h2>${esc(p.title)}</h2><p class="sub">${esc(p.line)}</p></div>${stop}</div>`;
}

function filmHtml(f) {
  const parts = [];
  if (f.video) {
    parts.push(`<div class="player"><video controls preload="metadata" src="${f.video}" ${f.scenes[0] ? `poster="${f.scenes[0].src}"` : ''}></video></div>`);
    const name = encodeURIComponent((f.kind === 'key_idea' ? f.idea?.title : f.concept) || 'film');
    parts.push(`<div class="video-actions"><a class="btn ghost" href="${f.video}?download=1&name=${name}" download>Download video</a>
      <button class="btn ghost" id="share-video" type="button">Share video</button><span class="sub" id="share-note"></span></div>`);
  }
  parts.push(nowPanel(f));
  if (f.status === 'done' || f.status === 'failed') parts.push(`<div class="panel"><h2>Plan the scenes again</h2>
    <p class="sub">Keeps the narration and plans the pictures and scenes afresh, then makes the video again. Pictures that come out the same are reused.</p>
    <button class="btn ghost" id="replan" type="button">Re-plan scenes</button></div>`);
  if (f.status !== 'waiting') parts.push(activityShell(f));
  if (f.kind === 'key_idea' && f.idea) parts.push(`<div class="panel"><h2>What this film makes simple</h2>
      <p class="sub">${esc(f.idea.why || '')}</p><p>${esc(f.idea.understanding || '')}</p>
      ${f.landed ? `<p class="landing ${f.landed.landed ? 'ok' : 'miss'}">${f.landed.landed ? 'A test learner got the idea' : 'A test learner did not fully get the idea'}${f.landed.score != null ? ` · ${f.landed.score}/100` : ''}${f.landed.rounds > 1 ? ` · after ${f.landed.rounds - 1} rewrite${f.landed.rounds > 2 ? 's' : ''}` : ''}</p>` : ''}</div>`);
  if (f.kind !== 'key_idea' && STUDIO.key_ideas && (f.status === 'done' || f.replanning)) parts.push('<div class="panel" id="key-ideas"></div>');
  if (STUDIO.questions && (f.status === 'done' || f.replanning)) parts.push('<div class="panel" id="questions"></div>');
  if (f.scenes.length || (f.phase === 'scenes' && f.scenes_total)) {
    const total = f.scenes_total || f.scenes.length;
    const blanks = f.status === 'making' && f.phase === 'scenes' ? Math.max(0, Math.min(3, total - f.scenes.length)) : 0;
    parts.push(`<div class="panel"><h2>The scenes</h2><p class="sub">${f.status === 'making' && f.phase === 'scenes' ? `${f.scenes.length} of ${total} painted` : `${f.scenes.length} illustrated scenes`}</p>
      ${f.status === 'making' && f.phase === 'scenes' ? `<div class="bar"><i style="width:${Math.round(100 * f.scenes.length / Math.max(1, total))}%"></i></div>` : ''}
      <div class="scenes">${f.scenes.map((s) => `<figure class="scene"><img loading="lazy" src="${s.src}" alt=""><figcaption>${esc(s.caption)}</figcaption></figure>`).join('')}
      ${'<div class="scene blank"></div>'.repeat(blanks)}</div></div>`);
  }
  if (f.storyline) parts.push(`<div class="panel"><h2>The story</h2><p class="sub">${f.storyline.length} moments, in the order you will see them</p>
      <ol class="story">${f.storyline.map((s) => `<li><span><b>${esc(s.heading)}</b><span>${esc(s.line)}</span></span></li>`).join('')}</ol>
      ${f.narration ? `<audio controls preload="none" src="${f.narration}"></audio>` : ''}</div>`);
  if (f.ideas) parts.push(`<div class="panel"><h2>Key ideas</h2><p class="sub">What the film will teach, drawn from the textbook</p>
      <div class="ideas">${f.ideas.map((i, n) => `<div class="idea" style="animation-delay:${Math.min(n, 12) * 40}ms">${esc(i)}</div>`).join('')}</div></div>`);
  if (f.passages.length) parts.push(`<div class="panel"><h2>From your textbook</h2><p class="sub">${esc(f.book)}, Chapter ${f.chapter_no}${f.pages.length ? `, pages ${esc(f.pages[0])}` : ''}</p>
      <div class="quotes">${f.passages.map((p) => `<blockquote class="quote">${esc(p)}…</blockquote>`).join('')}</div></div>`);
  if (f.notes.length && (f.ideas || f.status === 'done')) parts.push(`<div class="panel"><h2>Beyond the book</h2><p class="sub">Where the textbook leaves a gap, the film adds a little, checked against these sources</p>
      <ul class="notes">${f.notes.map((n) => `<li>${esc(n.title)} · <a href="${esc(n.url)}" target="_blank" rel="noopener">source</a></li>`).join('')}</ul></div>`);
  return parts.join('');
}

// Shares the video file itself (WhatsApp, mail, Drive...) where the browser can: the studio's own link needs its access
// code, so a link would not open for the person it is sent to. Elsewhere it says to download and send the file.
async function shareVideo(f, button) {
  const note = document.getElementById('share-note');
  const title = (f.kind === 'key_idea' ? f.idea?.title : f.concept) || 'film';
  const probe = new File([''], 'film.mp4', { type: 'video/mp4' });
  if (!navigator.canShare || !navigator.canShare({ files: [probe] })) {
    note.textContent = 'This browser cannot share files: download the video, then send the file.';
    return;
  }
  button.disabled = true;
  note.textContent = 'Preparing the video…';
  try {
    const blob = await (await fetch(f.video, { credentials: 'same-origin' })).blob();
    const file = new File([blob], `${title.replace(/[^\w ,()-]+/g, '').trim() || 'film'}.mp4`, { type: 'video/mp4' });
    note.textContent = '';
    await navigator.share({ files: [file], title });
  } catch (err) {
    if (err.name !== 'AbortError') note.textContent = `Could not share: ${err.message}`;
  } finally { button.disabled = false; if (note.textContent === 'Preparing the video…') note.textContent = ''; }
}

async function showFilm(id) {
  chrome(true, '');
  let first = true;
  const tick = async () => {
    let f;
    try { f = await api(`api/films/${id}`); } catch (err) {
      if (first) { view.innerHTML = `<p class="empty">${esc(err.message)}</p>`; return; }
      state.timer = setTimeout(tick, 5000);          // a passing hiccup (a restart, a slow read) must not end polling
      return;
    }
    const playing = view.querySelector('video, audio') && [...view.querySelectorAll('video, audio')].some((m) => !m.paused);
    const signature = JSON.stringify([f.status, f.phase, f.scenes.length, !!f.ideas, !!f.storyline, !!f.video, f.ahead]);
    if (first || (signature !== view.dataset.signature && !playing)) {
      view.dataset.signature = signature;
      view.innerHTML = `
        <nav class="crumbs"><a href="#/">Chapters</a><span>›</span><a href="#/chapter/${esc(f.chapter_id || '')}">${esc(f.chapter)}</a></nav>
        <section class="film-head">${f.kind === 'key_idea'
          ? `<span class="chapter-no">Key idea, made simple · ${minutes(f.minutes)} · from <a href="#/film/${esc(f.parent || '')}">${esc(f.concept)}</a></span>
             <h1>${esc(f.idea?.title)}</h1>`
          : `<span class="chapter-no">Chapter ${f.chapter_no} · ${minutes(f.minutes)}</span>
             <h1>${esc(f.concept)}</h1><p>${esc(f.summary)}</p>`}</section>
        <div class="film">${stepsHtml(f)}<div class="stage">${filmHtml(f)}</div></div>`;
      first = false;
      if (document.getElementById('key-ideas')) showIdeas(id);
      if (document.getElementById('activity')) showActivity(id);
      if (document.getElementById('questions')) showQuestions(id);
      const stop = document.getElementById('stop');
      if (stop) stop.onclick = async () => {
        if (!confirm('Stop making this film? You can make it again later; it carries on from where it stopped.')) return;
        stop.disabled = true;
        try { await api(`api/films/${id}/cancel`, { method: 'POST' }); } catch (err) { alert(err.message); }
        clearTimeout(state.timer); tick();
      };
      const share = document.getElementById('share-video');
      if (share) share.onclick = () => shareVideo(f, share);
      const replan = document.getElementById('replan');
      if (replan) replan.onclick = async () => {
        if (!confirm('Plan the scenes of this film again? The narration is kept; the scenes, pictures and video are made again.')) return;
        replan.disabled = true;
        try { await api(`api/films/${id}/replan`, { method: 'POST' }); } catch (err) { alert(err.message); replan.disabled = false; return; }
        clearTimeout(state.timer); tick();
      };
      const again = document.getElementById('again');
      if (again) again.onclick = async () => {
        again.disabled = true;
        try {
          const made = f.kind === 'key_idea'                // a key idea is made again from its concept film
            ? await api(`api/films/${f.parent}/ideas/${f.idea.id}`, { method: 'POST', body: '{}' })
            : await api('api/films', { method: 'POST', body: JSON.stringify({ chapter: f.chapter_id, concept: f.concept_id }) });
          if (made.film !== id) { location.hash = `#/film/${made.film}`; return; }
        } catch (err) { alert(err.message); again.disabled = false; return; }
        clearTimeout(state.timer); tick();
      };
    }
    if (f.status === 'waiting' || f.status === 'making') state.timer = setTimeout(tick, 5000);
  };
  await tick();
}

/* ---------------------------------------------------------------- behind the scenes */
// What the pipeline is doing, in plain words (GET /api/films/{id}/activity). Refreshes on its own timer so the
// rest of the page stays still; open or closed is remembered per browser.
function activityShell(f) {
  let open = f.status === 'making';
  try { const saved = localStorage.getItem('activity-open'); if (saved !== null) open = saved === '1'; } catch (e) { /* private mode */ }
  return `<details class="panel activity" id="activity" ${open ? 'open' : ''}><summary><h2>Behind the scenes</h2>
    <span class="sub" id="activity-line">What each step is doing, as it happens</span></summary><div id="activity-body"><p class="sub">Loading…</p></div></details>`;
}

const CHIP = { done: 'ok', succeeded: 'ok', accepted: 'ok', working: 'wait', running: 'wait', coding: 'wait', rendering: 'wait',
  repairing: 'wait', painting: 'wait', retrying: 'wait', queued: '', skipped: '', failed: 'bad', blocked: 'bad', 'needs review': 'warn' };
const chip = (s) => `<span class="chip ${CHIP[s] ?? ''}">${esc(s)}</span>`;
const secs = (n) => n == null ? '' : n >= 60 ? `${Math.floor(n / 60)}m ${String(Math.round(n % 60)).padStart(2, '0')}s` : `${Math.round(n)}s`;

function activityHtml(a) {
  const w = a.work, out = [];
  out.push(`<ol class="timeline">${a.steps.map((s) => `<li class="${s.state}"><span>${esc(s.title)}</span>${chip(s.state)}<span class="t">${secs(s.seconds)}</span>
    ${s.error ? `<p class="err">${esc(s.error)}</p>` : ''}</li>`).join('')}</ol>`);
  if (w.planning.length) out.push(`<h3>Planning, drafted and reviewed by two models</h3><table class="grid"><thead><tr><th>Step</th><th>Rounds</th><th>Review</th><th></th><th>Time</th></tr></thead><tbody>
    ${w.planning.map((l) => `<tr><td>${esc(l.label)}${l.repairs.length ? `<small>fixed ${esc(l.repairs.map((r) => r.join(', ')).join(' · '))}</small>` : ''}
      ${l.state !== 'done' && l.majors?.length ? `<small class="warn">Reviewer: ${esc(l.majors[0])}</small>` : ''}</td>
      <td>${l.rounds}</td><td>${l.score ?? ''}</td><td>${chip(l.state)}</td><td>${secs(l.seconds)}</td></tr>`).join('')}</tbody></table>`);
  if (w.narration) out.push(`<h3>Narration</h3><p>${w.narration.recorded > w.narration.done ? `${Math.min(w.narration.recorded, w.narration.points)} of ${w.narration.points} points recorded; ` : ''}${w.narration.done} of ${w.narration.points} recorded and checked against the script${w.narration.retries ? `, ${w.narration.retries} recorded again` : ''}</p>
    ${w.narration.problems.map((p) => `<small class="warn">${esc(p)}</small>`).join('')}`);
  if (w.learner) out.push(`<h3>Test learner</h3><table class="grid"><thead><tr><th>Round</th><th>Understood</th><th>Simple</th><th>Confusions</th><th></th></tr></thead><tbody>
    ${w.learner.map((r) => `<tr><td>${r.round}</td><td>${r.understood ?? r.score ?? ''}</td><td>${r.simple ?? ''}</td><td>${r.confusing ?? ''}</td><td>${chip(r.landed ? 'landed' : 'not yet')}</td></tr>`).join('')}</tbody></table>`);
  if (w.animations.length) out.push(`<h3>Animated scenes, coded and reviewed</h3><table class="grid"><thead><tr><th>Scene</th><th></th><th>Attempts</th><th>Time</th></tr></thead><tbody>
    ${w.animations.map((b) => `<tr><td><b>${esc(b.id.toUpperCase())}</b> ${esc(b.title)}<small>${esc(b.line)}</small></td><td>${chip(b.state)}</td>
      <td>${b.attempts}${b.tier ? ` · ${esc(b.tier)}` : ''}</td><td>${secs(b.seconds)}</td></tr>`).join('')}</tbody></table>`);
  if (w.pictures) {
    const p = w.pictures.summary;
    out.push(`<h3>Pictures, painted and reviewed</h3><p>${p.completed_images ?? 0} of ${p.planned_images ?? '?'} done${p.needs_review_images ? ` · ${p.needs_review_images} marked for expert review` : ''}${p.blocked_images ? ` · ${p.blocked_images} blocked` : ''}${p.workers ? ` · ${p.workers} painted at once` : ''}${w.pictures.prompts?.batch ? ` · prompts batch ${w.pictures.prompts.batch} of ${w.pictures.prompts.of}` : ''}</p>
      <table class="grid"><tbody>${w.pictures.items.map((i) => `<tr><td><b>${esc(i.id)}</b> ${esc(i.message)}${i.issue && i.state !== 'accepted' ? `<small class="warn">Reviewer: ${esc(i.issue)}</small>` : ''}</td>
        <td>${chip(i.state)}</td><td>${i.takes ? `take ${i.takes}` : ''}${i.score != null ? ` · ${i.score}` : ''}</td></tr>`).join('')}</tbody></table>`);
  }
  if (w.clips) out.push(`<h3>Motion clips</h3><p>${w.clips.made.length} of ${w.clips.planned} made</p>
    <ul class="plain">${w.clips.made.map((c) => `<li>${esc(c.scene)} on the ${esc(c.worker)}, ${secs(c.seconds)}</li>`).join('')}</ul>`);
  if (w.render) out.push(`<h3>Final cut</h3><p>${chip(w.render.state)} ${secs(w.render.seconds)}</p>`);
  if (a.log.length) out.push(`<details class="log"><summary>Activity log, newest first</summary><ol>${a.log.map((e) => `<li><time>${esc(e.at)}</time> ${esc(e.text)}</li>`).join('')}</ol></details>`);
  return out.join('');
}

async function showActivity(film) {
  const box = document.getElementById('activity');
  if (!box) return;
  clearTimeout(state.activityTimer);
  box.ontoggle = () => { try { localStorage.setItem('activity-open', box.open ? '1' : '0'); } catch (e) { /* private mode */ } };
  let a, again = true;
  try {
    a = await api(`api/films/${film}/activity`);
    const body = document.getElementById('activity-body');
    if (!body) return;
    const logOpen = body.querySelector('details.log')?.open;
    const html = activityHtml(a);
    if (body.dataset.html !== html) {
      body.innerHTML = html;
      body.dataset.html = html;
      if (logOpen) body.querySelector('details.log').open = true;
    }
    const line = document.getElementById('activity-line');
    if (line && a.started) line.textContent = `Started ${a.started} · ${a.elapsed}${a.running ? ' so far' : ''} · ${a.models.calls} model calls · planner $${a.models.planner_usd.toFixed(2)} · updated ${new Date().toLocaleTimeString()}`;
    again = a.status === 'running' || a.status === 'queued';
  } catch (err) {
    console.warn('Behind the scenes:', err);       // keep trying: a failed read must not freeze the panel
  }
  if (again && document.getElementById('activity')) state.activityTimer = setTimeout(() => showActivity(film), 4000);
}

// Browsers slow timers in background tabs; catch up as soon as the film page is looked at again.
document.addEventListener('visibilitychange', () => {
  const m = location.hash.match(/^#\/film\/([\w-]+)/);
  if (document.visibilityState === 'visible' && m && document.getElementById('activity')) showActivity(m[1]);
});

/* ---------------------------------------------------------------- test yourself */
// Creative questions on what the film taught (GET/POST /api/films/{id}/questions): pick an option, or show the model
// answer, to see the explanation and what the question checks. Structures are drawn by code.
const KIND_NAMES = { predict: 'Predict', explain: 'Explain why', spot_error: 'Spot the error', backwards: 'Work backwards',
  compare: 'Compare', data: 'Read the data', sequence: 'Put in order', scenario: 'In real life' };

function questionHtml(q, film) {
  const figs = (q.figures || []).map((k) => `<img class="q-fig" loading="lazy" src="media/${film}/question/${k}" alt="">`).join('');
  const options = (q.options || []).map((o) => `<button class="q-option" type="button" data-letter="${esc(String(o).trim()[0])}">${esc(o)}</button>`).join('');
  return `<article class="question" data-answer="${esc(String(q.answer).trim()[0])}">
    <div class="q-head"><span class="chip">${esc(KIND_NAMES[q.kind] || q.kind)}</span><span class="q-level">${esc(q.difficulty || '')}</span></div>
    <p class="q-stem"><b>${esc(q.id)}.</b> ${esc(q.stem)}</p>${figs}
    ${options ? `<div class="q-options">${options}</div>` : `<button class="btn ghost q-show" type="button">Show the answer</button>`}
    <div class="q-reveal" hidden>${options ? '' : `<p><b>Answer:</b> ${esc(q.answer)}</p>`}
      <p>${esc(q.explanation)}</p><p class="sub"><b>What this checks:</b> ${esc(q.targets)}</p></div></article>`;
}

async function showQuestions(film) {
  const box = document.getElementById('questions');
  if (!box) return;
  clearTimeout(state.questionTimer);
  let data;
  try { data = await api(`api/films/${film}/questions`); } catch (err) { box.remove(); return; }
  const head = '<h2>Test yourself</h2><p class="sub">Questions that check understanding, not memory: new cases, a student\'s mistake to spot, a reaction to work backwards</p>';
  if (data.state === 'finding') {
    box.innerHTML = `${head}<div class="now-line"><div class="spinner"></div><p class="sub">Choosing the ideas to test and writing the questions; each is checked before you see it (a few minutes)…</p></div>`;
    state.questionTimer = setTimeout(() => showQuestions(film), 5000);
    return;
  }
  if (data.state !== 'ready') {
    box.innerHTML = `${head}${data.state === 'failed' ? '<p class="sub">The last attempt could not finish; try again.</p>' : ''}
      <button class="btn" id="make-questions" type="button">Make 8 questions</button>`;
    box.querySelector('#make-questions').onclick = async (e) => {
      e.target.disabled = true;
      try { await api(`api/films/${film}/questions`, { method: 'POST' }); } catch (err) { alert(err.message); }
      showQuestions(film);
    };
    return;
  }
  box.innerHTML = head + data.questions.map((q) => questionHtml(q, film)).join('');
  box.querySelectorAll('.question').forEach((card) => {
    const reveal = () => { card.querySelector('.q-reveal').hidden = false; };
    card.querySelectorAll('.q-option').forEach((b) => b.onclick = () => {
      card.querySelectorAll('.q-option').forEach((o) => {
        o.disabled = true;
        if (o.dataset.letter === card.dataset.answer) o.classList.add('right');
      });
      if (b.dataset.letter !== card.dataset.answer) b.classList.add('wrong');
      reveal();
    });
    const show = card.querySelector('.q-show');
    if (show) show.onclick = () => { show.remove(); reveal(); };
  });
}

/* ---------------------------------------------------------------- key ideas, made simple */
async function showIdeas(film) {
  const box = document.getElementById('key-ideas');
  if (!box) return;
  clearTimeout(state.ideaTimer);
  let data;
  try { data = await api(`api/films/${film}/ideas`); } catch (err) { box.remove(); return; }
  const head = `<h2>Key ideas, made simple</h2><p class="sub">Short films that drill down one idea at a time, with analogies and everyday pictures</p>`;
  if (data.state === 'finding') {
    box.innerHTML = `${head}<div class="now-line"><div class="spinner"></div><p class="sub">Finding the ideas students most need made simple…</p></div>`;
    state.ideaTimer = setTimeout(() => showIdeas(film), 5000);
    return;
  }
  if (!data.ideas.length) {
    box.innerHTML = `${head}${data.state === 'failed' ? '<p class="error">Could not find the key ideas this time.</p>' : ''}
      <button class="btn" id="find-ideas" type="button">${data.state === 'failed' ? 'Try again' : 'Find key ideas'}</button>`;
    box.querySelector('#find-ideas').onclick = async (e) => {
      e.target.disabled = true;
      try { await api(`api/films/${film}/ideas`, { method: 'POST' }); } catch (err) { alert(err.message); }
      showIdeas(film);
    };
    return;
  }
  box.innerHTML = `${head}<div class="key-ideas">${data.ideas.map((i) => `
    <div class="key-idea">
      <div><h3>${esc(i.title)}</h3><p class="sub">${esc(i.why)}</p><span class="meta"><span>${minutes(i.minutes)}</span>${i.ready ? '<span class="badge ready">Ready</span>' : i.film ? '<span class="badge making"><i class="dot"></i>Being made</span>' : ''}</span></div>
      ${i.film ? `<a class="btn ghost" href="#/film/${i.film}">${i.ready ? 'Watch ›' : 'See progress ›'}</a>`
               : `<button class="btn" type="button" data-idea="${esc(i.id)}">Make this film</button>`}
    </div>`).join('')}</div>`;
  box.querySelectorAll('[data-idea]').forEach((b) => b.addEventListener('click', async () => {
    if (!confirm(`Make a short simplified film: "${data.ideas.find((i) => i.id === b.dataset.idea).title}"?`)) return;
    b.disabled = true; b.textContent = 'Starting…';
    try {
      const made = await api(`api/films/${film}/ideas/${b.dataset.idea}`, { method: 'POST', body: '{}' });
      location.hash = `#/film/${made.film}`;
    } catch (err) { alert(err.message); b.disabled = false; b.textContent = 'Make this film'; }
  }));
}

/* ---------------------------------------------------------------- library */
async function showLibrary() {
  chrome(true, 'library');
  const data = await api('api/library');
  view.innerHTML = `
    <section class="hero"><div class="eyebrow">The studio's films</div><h1>Films made so far</h1>
      <p>Every film made in the studio, newest first.</p></section>
    ${data.films.length ? `<div class="grid">${data.films.map((f) => `
      <a class="card" href="#/film/${f.film}">
        <div class="cover" ${f.cover ? `style="background-image:url('${f.cover}')"` : ''}></div>
        <span class="chapter-no">Chapter ${f.chapter_no} · ${esc(f.chapter)}</span>
        <h3>${esc(f.kind === 'key_idea' ? f.idea?.title : f.concept)}</h3>
        <div class="meta">${f.kind === 'key_idea' ? '<span class="badge">Key idea</span>' : ''}<span>${minutes(f.minutes)}</span>${f.status === 'done' ? '<span class="badge ready">Ready</span>' : '<span class="badge making"><i class="dot"></i>Being made</span>'}</div>
      </a>`).join('')}</div>` : '<p class="empty">No films yet. Pick a chapter and make the first one.</p>'}`;
}

/* ---------------------------------------------------------------- solve (Physics Studio) */
const TYPE_NAMES = { single: 'One correct option', multiple: 'One or more options', numerical: 'Numerical', match: 'Matching lists' };
const STATE_NAMES = { new: 'Not solved', queued: 'Waiting', solving: 'Solving', settled: 'Settled', unverified: 'Unverified (no key)', needs_review: 'Needs review', failed: 'Failed' };
function stateBadge(s) {
  const cls = (s === 'settled' || s === 'unverified') ? 'ready' : (s === 'solving' || s === 'queued') ? 'making' : '';
  return `<span class="badge ${cls}">${(s === 'solving' || s === 'queued') ? '<i class="dot"></i>' : ''}${esc(STATE_NAMES[s] || s)}</span>`;
}

function yearTabs(years, current) {
  const bar = document.getElementById('years');
  bar.innerHTML = years.map((y) => `<a href="#/solve/year/${y}" class="${y === current ? 'on' : ''}">${y}</a>`).join('');
  bar.hidden = false;
  const on = bar.querySelector('.on');
  if (on) on.scrollIntoView({ block: 'nearest', inline: 'nearest' });
}

async function solveYears() {
  if (!state.solveYears) {
    const data = await api('api/solve');
    state.solveYears = [...new Set(data.questions.map((q) => q.year))].sort((a, b) => b - a);
  }
  return state.solveYears;
}

async function showSolveList(year) {
  chrome(true, 'solve');
  const data = await api('api/solve');
  const years = [...new Set(data.questions.map((q) => q.year))].sort((a, b) => b - a);
  state.solveYears = years;
  year = years.includes(+year) ? +year : years[0];
  yearTabs(years, year);
  const papers = {};
  data.questions.filter((q) => q.year === year).forEach((q) => { (papers[`${q.year} · Paper ${q.paper}`] ||= []).push(q); });
  view.innerHTML = `
    <section class="hero"><div class="eyebrow">Solve</div><h1>Exam questions, solved and checked</h1>
      <p>Two student models solve each question on their own. If both match the official answer, the teacher model only reviews them; if not, the teacher solves it. An answer that still misses the official key stops for a person to review.</p></section>
    ${Object.keys(data.snags || {}).length ? `<div class="section-title"><h2>Snags: no Linkwork aid</h2><span>clips by missing family · the evidence for build a verb or leave it to manim</span></div>
      <div class="verdicts">${Object.entries(data.snags).map(([fam, n]) => `<div class="verdict"><span class="sub">${esc(fam)}</span><b>${n.clips} clip${n.clips === 1 ? '' : 's'}</b><span class="sub">${n.standard ?? 0} in standard physics (verb evidence) · ${n.manim} to manim · ${n.linkwork} found on retry</span></div>`).join('')}</div>` : ''}
    ${Object.entries(papers).map(([name, qs]) => `
      <div class="section-title"><h2>JEE Advanced ${esc(name)}</h2><span>${qs.length} questions</span></div>
      <div class="solve-list">${qs.map((q) => `
        <a class="card solve-row" href="#/solve/${esc(q.id)}">
          <span class="chapter-no">Q.${q.number}</span>
          <div><p>${esc(q.preview)}…</p><p class="sub">${esc(TYPE_NAMES[q.type] || q.type)}</p></div>
          ${stateBadge(q.state)}
        </a>`).join('')}</div>`).join('')}`;
}

function aidName(a) {
  a = a || {};
  return a.kind === 'verb' ? `Linkwork · ${a.verb}` : a.kind === 'chem_figure' ? `chemistry figure · ${a.figure?.type}` : a.kind === 'missing' ? `missing · ${a.family}` : a.kind === 'question_figure' ? 'question figure' : 'equations only';
}

function flowHtml(flow) {
  return `<ol class="flow">${flow.map((f) => `<li><span class="sub">${esc(f.at)}</span> ${esc(f.text)}</li>`).join('')}</ol>`;
}

function workingHtml(sol) {
  if (!sol) return '';
  if (sol.error) return `<p class="error">${esc(sol.error)}</p>`;
  const options = sol.options ? `<ul>${Object.entries(sol.options).map(([k, o]) => `<li><b>(${esc(k)})</b> ${o.correct ? 'true' : 'false'}: ${esc(o.why)}</li>`).join('')}</ul>` : '';
  return `<p class="sub">Answer: <b>${esc(sol.answer)}</b></p>${options}
    <ol class="steps-list">${(sol.steps || []).map((s) => `<li><b>${esc(s.title)}</b><pre>${esc(s.working)}</pre><span class="sub">${esc(s.result || '')}</span></li>`).join('')}</ol>
    ${sol.check ? `<p class="sub"><b>Check:</b> ${esc(sol.check)}</p>` : ''}`;
}

function reasoningHtml(r) {
  const t = r.teacher || {};
  const labels = t.labels || {};
  const who = (k) => labels[k] || k;
  let teacher = '';
  if (r.route === 'review') {
    const errs = Object.entries(t.step_errors || {}).map(([k, list]) => `<li><b>${esc(who(k))}</b>: ${list.length ? esc(list.join(' · ')) : 'no wrong steps found'}</li>`).join('');
    teacher = `<h3>Opus's review</h3><p>${esc(t.why || '')}</p><ul>${errs}</ul>
      ${(t.improvements || []).length ? `<p class="sub"><b>What Opus changed in the chosen solution:</b> ${esc(t.improvements.join(' · '))}</p>` : ''}`;
  } else if (r.route === 'one_right') {
    teacher = '';
  } else {
    const notes = Object.entries(t.students || {}).map(([k, v]) => `<li><b>${esc(who(k))}</b>: ${esc(v)}</li>`).join('');
    teacher = `<h3>Opus on the students' attempts</h3><ul>${notes}</ul>`;
  }
  const att = r.attempts || {};
  const students = ['haiku', 'luna'].filter((k) => att[k]).map((k) => `<details><summary>${esc(k)}'s working ${mark(r.students[k]?.right)}</summary>${workingHtml(att[k])}</details>`).join('');
  const opus = att.opus ? `<details><summary>${r.route === 'review' ? 'Opus\'s improved version (taught below)' : `Opus's own working ${mark(t.right)}`}</summary>${workingHtml(att.opus)}</details>` : '';
  return `<section class="reasoning"><h2>How it was settled</h2>${r.flow ? flowHtml(r.flow) : ''}${students}${opus}${teacher}</section>`;
}

function clipTrailHtml(trail) {
  if (!trail) return '';
  if (!trail.draft) return `<details class="reasoning"><summary>How the clips were planned</summary><p>Planned by one model alone (the one that settled the solution); code checked the plan.</p></details>`;
  const draft = (trail.draft?.clips || []).map((c) => `<li>Clip ${c.n}: ${esc(c.explains)} <span class="sub">(${esc(aidName(c.aid))})</span></li>`).join('');
  const findings = (trail.review?.findings || []).map((f) => `<li>Clip ${esc(f.clip)}: ${esc(f.problem)} <span class="sub">Fix: ${esc(f.fix)}</span></li>`).join('');
  return `<details class="reasoning"><summary>How the clips were planned</summary>
    <h3>${esc(trail.draft.by || 'haiku')}'s draft</h3><ol>${draft}</ol>
    <h3>${esc(trail.review?.by || 'luna')}'s review: ${esc(trail.review?.verdict || '')}</h3>${findings ? `<ul>${findings}</ul>` : '<p class="sub">No findings.</p>'}
    <h3>Opus settled the plan shown above</h3></details>`;
}

function mark(ok) { return ok ? '<span class="right-mark">✓</span>' : '<span class="wrong-mark">✗</span>'; }

async function showSolve(qid) {
  chrome(true, 'solve');
  clearTimeout(state.timer);
  const d = await api(`api/solve/${encodeURIComponent(qid)}`);
  yearTabs(await solveYears(), d.year);
  const r = d.record;
  const pages = Array.from({ length: d.pages }, (_, i) => `<img loading="lazy" src="api/solve/${encodeURIComponent(qid)}/page/${i}" alt="Question paper page">`).join('');
  let body = '';
  if (d.state === 'solving' || d.state === 'queued') {
    body = `<div class="now-line"><div class="spinner"></div><p class="sub">${d.state === 'queued' ? 'Waiting for the question before it…' : 'Solving: each step of the rule appears below as it happens (a few minutes)…'}</p></div>${d.flow ? flowHtml(d.flow) : ''}`;
    state.timer = setTimeout(() => showSolve(qid), 5000);
  } else if (!r) {
    body = `${d.error ? `<p class="error">${esc(d.error)}</p>` : ''}${d.flow ? flowHtml(d.flow) : ''}<button class="btn" id="solve-go" type="button">Solve this question</button>`;
  } else {
    const t = r.teacher || {};
    const keyed = r.key !== null && r.key !== undefined;
    const teacherLine = r.route === 'review'
      ? `Both students ${keyed ? 'matched the key' : 'agreed (no official key)'}, so Opus only reviewed: it chose <b>${esc(r.author)}</b>'s solution${r.improved ? ' and improved it' : ''}. ${esc(t.why || '')}`
      : r.route === 'one_right'
      ? `Only <b>${esc(r.author)}</b> matched the key, so its solution is the one and it planned the clips alone. No Opus call.`
      : `The students ${keyed ? 'both missed the key' : 'disagreed'}, so Opus solved it: <b>${esc(t.answer)}</b> ${mark(t.right)}${t.right ? ', and planned the clips alone' : ''}.`;
    const sol = r.solution;
    body = `
      <div class="verdicts">
        ${Object.entries(r.students).map(([who, s]) => `<div class="verdict"><span class="sub">Student · ${esc(who)}</span><b>${esc(s.answer ?? 'no answer')} ${mark(s.right)}</b></div>`).join('')}
        <div class="verdict"><span class="sub">Official key</span><b>${esc(r.key ?? 'none found')}</b></div>
        <div class="verdict"><span class="sub">Outcome</span><b>${stateBadge(r.status)}</b></div>
      </div>
      <p>${teacherLine}</p>
      ${r.status === 'needs_review' ? `<p class="error">${keyed ? 'No answer reached the official key.' : 'The models could not agree on an answer.'} This question needs a person to review it.</p>` : ''}
      ${r.status === 'unverified' ? '<p class="sub">No official key was found for this year: the answer is agreed by the models, not checked against a key.</p>' : ''}
      ${reasoningHtml(r)}
      ${sol ? `<h2>The solution</h2><p class="sub">Answer: ${esc(sol.answer)}. Ideas used: ${esc((sol.ideas || []).join('; '))}</p>
        <ol class="steps-list">${(sol.steps || []).map((s) => `<li><b>${esc(s.title)}</b><pre>${esc(s.working)}</pre><span class="sub">${esc(s.result || '')}</span></li>`).join('')}</ol>
        ${sol.check ? `<p class="sub"><b>Check:</b> ${esc(sol.check)}</p>` : ''}` : ''}
      ${(r.unwrap || sol?.unwrap || []).length ? `<h2>Unwrapping the question</h2><ul>${(r.unwrap || sol.unwrap).map((u) => `<li><b>${esc(u.in_the_question)}</b> is really <b>${esc(u.is_really)}</b>${u.why ? ` <span class="sub">(${esc(u.why)})</span>` : ''}</li>`).join('')}</ul>
        ${(sol?.decoys || []).length ? `<p class="sub"><b>There to confuse:</b> ${esc(sol.decoys.join(' · '))}</p>` : ''}` : ''}
      ${(r.clips || []).length ? `<h2>Clips</h2><p class="sub">What each clip explains, the book concepts it rests on, and the drawing aid it needs</p>
        ${r.clips.map((c) => {
          const a = c.aid || {};
          const d = c.decision || {};
          let aid = a.kind === 'verb' ? `Linkwork · ${a.verb}` : a.kind === 'chem_figure' ? `Chemistry figure · ${a.figure?.type}: ${a.figure?.what || ''}` : a.kind === 'question_figure' ? 'The question\'s figure' : 'Equations only';
          let cls = (a.kind === 'verb' || a.kind === 'chem_figure') ? 'ready' : '';
          let snag = '';
          if (a.kind === 'missing') {
            if (d.route === 'linkwork') { aid = `Linkwork · ${d.verb} (found on retry)`; cls = 'ready'; }
            else if (d.route === 'manim') { aid = `Going to manim · no Linkwork ${a.family}`; }
            else { aid = `Hit a snag: no Linkwork aid · ${a.family}`; cls = 'making'; }
            snag = d.route === 'linkwork' ? '' : `<div class="snag">
              ${d.retried ? `<p class="sub">Retried: still no verb fits. ${esc(d.retry_why || '')}</p>` : ''}
              ${d.route === 'manim' ? '' : `<button class="btn" type="button" data-manim="${c.n}">Proceed with manim</button>`}
              <button class="btn ghost" type="button" data-retry="${c.n}">Retry Linkwork search</button></div>`;
          }
          const role = { setup: 'The setup', unwrap: 'Unwrapping', standard: 'Standard physics' }[c.role] || '';
          return `<div class="clip"><span class="chapter-no">Clip ${c.n}${role ? ` · ${role}` : ''} · steps ${esc((c.steps || []).join(', ') || '—')}</span>
            <h3>${esc(c.explains)}</h3><span class="badge aid ${cls}">${esc(aid)}</span>
            <p class="sub">${esc((d.route === 'linkwork' && d.shows) || a.shows || '')}</p>
            <p class="sub"><b>Book:</b> ${esc((c.concept_names || c.concepts || []).join(' · '))}</p>${snag}</div>`;
        }).join('')}${clipTrailHtml(r.clip_trail)}` : ''}
      <button class="btn ghost" id="solve-go" type="button">Solve again</button>`;
  }
  view.innerHTML = `
    <section class="hero"><div class="eyebrow">JEE Advanced ${d.year} · Paper ${d.paper} · ${esc(TYPE_NAMES[d.type] || d.type)}</div>
      <h1>Question ${d.number}</h1><p><a href="#/solve/year/${d.year}">‹ All ${d.year} questions</a></p></section>
    <details class="solve-pages" ${r ? '' : 'open'}><summary>The question paper</summary>${pages}</details>
    ${body}`;
  view.querySelectorAll('[data-manim]').forEach((b) => b.onclick = async () => {
    b.disabled = true;
    try { await api(`api/solve/${encodeURIComponent(qid)}/clips/${b.dataset.manim}/manim`, { method: 'POST' }); } catch (err) { alert(err.message); }
    showSolve(qid);
  });
  view.querySelectorAll('[data-retry]').forEach((b) => b.onclick = async () => {
    if (!confirm('Retrying asks the teacher model again (a cloud call). Go ahead?')) return;
    b.disabled = true; b.textContent = 'Searching Linkwork…';
    try { await api(`api/solve/${encodeURIComponent(qid)}/clips/${b.dataset.retry}/retry`, { method: 'POST' }); } catch (err) { alert(err.message); }
    showSolve(qid);
  });
  const go = document.getElementById('solve-go');
  if (go) go.onclick = async () => {
    if (!confirm('Solving calls the cloud models (two students and the teacher). Go ahead?')) return;
    go.disabled = true;
    try { await api(`api/solve/${encodeURIComponent(qid)}`, { method: 'POST' }); } catch (err) { alert(err.message); }
    showSolve(qid);
  };
}

/* ---------------------------------------------------------------- routing */
async function showPlayCards(chapter) {
  const cards = await (await import('./plays.js')).cardsFor(chapter);
  const host = document.getElementById('plays');
  if (!host || !cards.length) return;
  host.innerHTML = `<section class="chapter-head play-head"><h2>Try it yourself</h2><p>Predict what happens, then take the challenges.</p></section>
    <div class="concepts">${cards.map((p) => `
      <a class="card concept" href="#/play/${chapter}/${esc(p.id)}">
        <span class="num">▶</span>
        <span><h3>${esc(p.title)}</h3><p>${esc(p.intro)}</p>
          <span class="meta"><span>${p.won ? `${p.won} of ${p.total} challenges done` : `${p.total} challenges`}</span></span></span>
        <span class="go">Play ›</span>
      </a>`).join('')}</div>`;
}

async function route() {
  stopPolling();
  document.getElementById('years').hidden = true;
  const session = await api('api/session');
  if (!session.signed_in) return showLogin();
  const parts = location.hash.replace(/^#\/?/, '').split('/');
  window.scrollTo(0, 0);
  try {
    if (parts[0] === 'chapter') await showChapter(parts[1]);
    else if (parts[0] === 'film') await showFilm(parts[1]);
    else if (parts[0] === 'play' && STUDIO.plays) { chrome(true, 'home'); await (await import('./plays.js')).showPlay(view, parts[2], `#/chapter/${parts[1]}`); }
    else if (parts[0] === 'library') await showLibrary();
    else if (parts[0] === 'solve' && STUDIO.solve) await (parts[1] === 'year' ? showSolveList(parts[2]) : parts[1] ? showSolve(decodeURIComponent(parts[1])) : showSolveList());
    else await showHome();
  } catch (err) {
    if (err.message !== 'signed out') view.innerHTML = `<p class="empty">${esc(err.message)}</p>`;
  }
}

// Under the learn.photovault.live shell a studio lives at /<slug>/: offer the way back to every studio.
document.getElementById('nav-all').hidden = location.pathname === '/';
document.getElementById('logout').addEventListener('click', async () => { await api('api/logout', { method: 'POST' }); showLogin(); });
window.addEventListener('hashchange', route);
route();
