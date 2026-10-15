'use strict';
const view = document.getElementById('view');
const state = { catalog: null, voices: null, cls: null, timer: null };

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const minutes = (m) => (m < 1.25 ? 'about a minute' : `about ${Math.round(m)} min`);

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options });
  if (response.status === 401) { showLogin(); throw new Error('signed out'); }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || 'Something went wrong');
  return body;
}

function chrome(on, nav) {
  document.getElementById('top').hidden = !on;
  document.getElementById('foot').hidden = !on;
  document.querySelectorAll('[data-nav]').forEach((a) => a.classList.toggle('on', a.dataset.nav === nav));
}

function stopPolling() { clearTimeout(state.timer); state.timer = null; }

/* ---------------------------------------------------------------- sign in */
function showLogin() {
  stopPolling();
  chrome(false);
  view.innerHTML = `
    <div class="login"><form class="sheet" id="login">
      <div class="mark">H</div>
      <h1>History Studio</h1>
      <p>Short films for every idea in your history textbook. Enter your access code to begin.</p>
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
      await api('/api/login', { method: 'POST', body: JSON.stringify({ code: document.getElementById('code').value }) });
      route();
    } catch (err) { error.textContent = err.message === 'signed out' ? '' : err.message; }
  });
}

/* ---------------------------------------------------------------- chapters */
async function loadCatalog(force) {
  if (!state.catalog || force) state.catalog = await api('/api/catalog');
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
      <div class="eyebrow">NCERT · Classes 8 to 12</div>
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
    </div>`;
  view.querySelectorAll('[data-concept]').forEach((b) => b.addEventListener('click', () => {
    const concept = chapter.concepts.find((c) => c.id === b.dataset.concept);
    if (concept.film) location.hash = `#/film/${concept.film}`;
    else confirmFilm(chapter, concept);
  }));
}

async function confirmFilm(chapter, concept) {
  if (!state.voices) state.voices = await api('/api/voices').catch(() => ({ voices: [] }));
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
      ${voices.length ? `<label class="chapter-no" for="voice">Narrator</label>
        <select class="field" id="voice" style="text-align:left;letter-spacing:0;margin-top:8px">
          ${voices.map((v) => `<option value="${esc(v.id)}">${esc(v.label)}</option>`).join('')}
        </select>` : ''}
      <p class="error" id="sheet-error"></p>
      <div class="actions">
        <button class="btn ghost" data-close>Not now</button>
        <button class="btn" data-make>Make this film</button>
      </div>
    </div>`;
  document.body.appendChild(back);
  const close = () => back.remove();
  back.addEventListener('click', (e) => { if (e.target === back || e.target.hasAttribute('data-close')) close(); });
  back.querySelector('[data-make]').addEventListener('click', async (e) => {
    e.target.disabled = true;
    e.target.textContent = 'Starting…';
    try {
      const voice = back.querySelector('#voice')?.value;
      const made = await api('/api/films', { method: 'POST', body: JSON.stringify({ chapter: chapter.id, concept: concept.id, ...(voice ? { voice } : {}) }) });
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
  return `<aside class="steps"><h3>${f.status === 'done' ? 'Your film is ready' : f.status === 'waiting' ? 'Waiting to start' : 'Making your film'}</h3>
    ${f.phases.map((p, i) => {
      const cls = f.status === 'waiting' ? '' : i < at ? 'done' : i === at && f.status === 'making' ? 'now' : '';
      return `<div class="step ${cls}"><span class="ring">✓</span><span><b>${esc(p.title)}</b>${cls === 'now' ? `<span>${esc(p.line)}</span>` : ''}</span></div>`;
    }).join('')}</aside>`;
}

function nowPanel(f) {
  if (f.status === 'failed') return `<div class="panel"><h2>This film hit a snag</h2><p class="sub">Something went wrong while making it. The studio team will look at it; you can try another idea meanwhile.</p></div>`;
  if (f.status === 'waiting') return `<div class="panel now-line"><div class="spinner"></div><div><h2>In the queue</h2><p class="sub">${f.ahead ? `${f.ahead} film${f.ahead > 1 ? 's' : ''} ahead of yours. ` : ''}Films are made one at a time; yours starts soon.</p></div></div>`;
  if (f.status !== 'making') return '';
  const p = f.phases.find((x) => x.key === f.phase) || f.phases[0];
  const n = f.phases.indexOf(p) + 1;
  return `<div class="panel now-line"><div class="spinner"></div><div><span class="step-count">Step ${n} of ${f.phases.length}</span><h2>${esc(p.title)}</h2><p class="sub">${esc(p.line)}</p></div></div>`;
}

function filmHtml(f) {
  const parts = [];
  if (f.video) parts.push(`<div class="player"><video controls preload="metadata" src="${f.video}" ${f.scenes[0] ? `poster="${f.scenes[0].src}"` : ''}></video></div>`);
  parts.push(nowPanel(f));
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

async function showFilm(id) {
  chrome(true, '');
  let first = true;
  const tick = async () => {
    let f;
    try { f = await api(`/api/films/${id}`); } catch (err) {
      if (first) view.innerHTML = `<p class="empty">${esc(err.message)}</p>`;
      return;
    }
    const playing = view.querySelector('video, audio') && [...view.querySelectorAll('video, audio')].some((m) => !m.paused);
    const signature = JSON.stringify([f.status, f.phase, f.scenes.length, !!f.ideas, !!f.storyline, !!f.video, f.ahead]);
    if (first || (signature !== view.dataset.signature && !playing)) {
      view.dataset.signature = signature;
      view.innerHTML = `
        <nav class="crumbs"><a href="#/">Chapters</a><span>›</span><a href="#/chapter/${esc(f.chapter_id || '')}">${esc(f.chapter)}</a></nav>
        <section class="film-head"><span class="chapter-no">Chapter ${f.chapter_no} · ${minutes(f.minutes)}</span>
          <h1>${esc(f.concept)}</h1><p>${esc(f.summary)}</p></section>
        <div class="film">${stepsHtml(f)}<div class="stage">${filmHtml(f)}</div></div>`;
      first = false;
    }
    if (f.status === 'waiting' || f.status === 'making') state.timer = setTimeout(tick, 5000);
  };
  await tick();
}

/* ---------------------------------------------------------------- library */
async function showLibrary() {
  chrome(true, 'library');
  const data = await api('/api/library');
  view.innerHTML = `
    <section class="hero"><div class="eyebrow">The studio's films</div><h1>Films made so far</h1>
      <p>Every film made in the studio, newest first.</p></section>
    ${data.films.length ? `<div class="grid">${data.films.map((f) => `
      <a class="card" href="#/film/${f.film}">
        <div class="cover" ${f.cover ? `style="background-image:url('${f.cover}')"` : ''}></div>
        <span class="chapter-no">Chapter ${f.chapter_no} · ${esc(f.chapter)}</span>
        <h3>${esc(f.concept)}</h3>
        <div class="meta"><span>${minutes(f.minutes)}</span>${f.status === 'done' ? '<span class="badge ready">Ready</span>' : '<span class="badge making"><i class="dot"></i>Being made</span>'}</div>
      </a>`).join('')}</div>` : '<p class="empty">No films yet. Pick a chapter and make the first one.</p>'}`;
}

/* ---------------------------------------------------------------- routing */
async function route() {
  stopPolling();
  const session = await api('/api/session');
  if (!session.signed_in) return showLogin();
  const parts = location.hash.replace(/^#\/?/, '').split('/');
  window.scrollTo(0, 0);
  try {
    if (parts[0] === 'chapter') await showChapter(parts[1]);
    else if (parts[0] === 'film') await showFilm(parts[1]);
    else if (parts[0] === 'library') await showLibrary();
    else await showHome();
  } catch (err) {
    if (err.message !== 'signed out') view.innerHTML = `<p class="empty">${esc(err.message)}</p>`;
  }
}

document.getElementById('logout').addEventListener('click', async () => { await api('/api/logout', { method: 'POST' }); showLogin(); });
window.addEventListener('hashchange', route);
route();
