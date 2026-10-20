'use strict';
const STUDIO = window.STUDIO || {name: 'History Studio', mark: 'H', subject: 'history', key_ideas: false};
const view = document.getElementById('view');
const state = { catalog: null, voices: null, cls: null, timer: null, ideaTimer: null };

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

function stopPolling() { clearTimeout(state.timer); state.timer = null; clearTimeout(state.ideaTimer); state.ideaTimer = null; }

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
  return `<aside class="steps"><h3>${f.status === 'done' ? 'Your film is ready' : f.status === 'waiting' ? 'Waiting to start' : f.status === 'stopped' ? 'Stopped' : f.status === 'failed' ? 'Could not finish' : 'Making your film'}</h3>
    ${f.phases.map((p, i) => {
      const cls = ['waiting', 'stopped', 'failed'].includes(f.status) ? '' : i < at ? 'done' : i === at && f.status === 'making' ? 'now' : '';
      return `<div class="step ${cls}"><span class="ring">✓</span><span><b>${esc(p.title)}</b>${cls === 'now' ? `<span>${esc(p.line)}</span>` : ''}</span></div>`;
    }).join('')}</aside>`;
}

function nowPanel(f) {
  if (f.status === 'failed') return `<div class="panel"><h2>This film hit a snag</h2><p class="sub">Something went wrong while making it. The studio team will look at it; you can try another idea meanwhile.</p></div>`;
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
  if (f.video) parts.push(`<div class="player"><video controls preload="metadata" src="${f.video}" ${f.scenes[0] ? `poster="${f.scenes[0].src}"` : ''}></video></div>`);
  parts.push(nowPanel(f));
  if (f.kind === 'key_idea' && f.idea) parts.push(`<div class="panel"><h2>What this film makes simple</h2>
      <p class="sub">${esc(f.idea.why || '')}</p><p>${esc(f.idea.understanding || '')}</p>
      ${f.landed ? `<p class="landing ${f.landed.landed ? 'ok' : 'miss'}">${f.landed.landed ? 'A test learner got the idea' : 'A test learner did not fully get the idea'}${f.landed.score != null ? ` · ${f.landed.score}/100` : ''}${f.landed.rounds > 1 ? ` · after ${f.landed.rounds - 1} rewrite${f.landed.rounds > 2 ? 's' : ''}` : ''}</p>` : ''}</div>`);
  if (f.kind !== 'key_idea' && STUDIO.key_ideas && f.status === 'done') parts.push('<div class="panel" id="key-ideas"></div>');
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
        <section class="film-head">${f.kind === 'key_idea'
          ? `<span class="chapter-no">Key idea, made simple · ${minutes(f.minutes)} · from <a href="#/film/${esc(f.parent || '')}">${esc(f.concept)}</a></span>
             <h1>${esc(f.idea?.title)}</h1>`
          : `<span class="chapter-no">Chapter ${f.chapter_no} · ${minutes(f.minutes)}</span>
             <h1>${esc(f.concept)}</h1><p>${esc(f.summary)}</p>`}</section>
        <div class="film">${stepsHtml(f)}<div class="stage">${filmHtml(f)}</div></div>`;
      first = false;
      if (document.getElementById('key-ideas')) showIdeas(id);
      const stop = document.getElementById('stop');
      if (stop) stop.onclick = async () => {
        if (!confirm('Stop making this film? You can make it again later; it carries on from where it stopped.')) return;
        stop.disabled = true;
        try { await api(`/api/films/${id}/cancel`, { method: 'POST' }); } catch (err) { alert(err.message); }
        clearTimeout(state.timer); tick();
      };
      const again = document.getElementById('again');
      if (again) again.onclick = async () => {
        again.disabled = true;
        try {
          const made = await api('/api/films', { method: 'POST', body: JSON.stringify({ chapter: f.chapter_id, concept: f.concept_id }) });
          if (made.film !== id) { location.hash = `#/film/${made.film}`; return; }
        } catch (err) { alert(err.message); again.disabled = false; return; }
        clearTimeout(state.timer); tick();
      };
    }
    if (f.status === 'waiting' || f.status === 'making') state.timer = setTimeout(tick, 5000);
  };
  await tick();
}

/* ---------------------------------------------------------------- key ideas, made simple */
async function showIdeas(film) {
  const box = document.getElementById('key-ideas');
  if (!box) return;
  clearTimeout(state.ideaTimer);
  let data;
  try { data = await api(`/api/films/${film}/ideas`); } catch (err) { box.remove(); return; }
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
      try { await api(`/api/films/${film}/ideas`, { method: 'POST' }); } catch (err) { alert(err.message); }
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
      const made = await api(`/api/films/${film}/ideas/${b.dataset.idea}`, { method: 'POST', body: '{}' });
      location.hash = `#/film/${made.film}`;
    } catch (err) { alert(err.message); b.disabled = false; b.textContent = 'Make this film'; }
  }));
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
        <h3>${esc(f.kind === 'key_idea' ? f.idea?.title : f.concept)}</h3>
        <div class="meta">${f.kind === 'key_idea' ? '<span class="badge">Key idea</span>' : ''}<span>${minutes(f.minutes)}</span>${f.status === 'done' ? '<span class="badge ready">Ready</span>' : '<span class="badge making"><i class="dot"></i>Being made</span>'}</div>
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
