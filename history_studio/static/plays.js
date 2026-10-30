// Plays: drive a Linkwork verb in the browser (see ~/linkwork/src/play/plays.ts). Predict, then challenges, then free play.
// The compiler runs here, from the plain-JS mirror the studio serves at lw/, so nothing is asked of the server.
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const dark = () => document.documentElement.dataset.theme === 'dark' || (document.documentElement.dataset.theme !== 'light' && matchMedia('(prefers-color-scheme: dark)').matches);
const SAVE = 'plays:progress';
const saved = () => { try { return JSON.parse(localStorage.getItem(SAVE)) || {}; } catch { return {}; } };
function remember(id, won) { try { const all = saved(); all[id] = {...all[id], ...won}; localStorage.setItem(SAVE, JSON.stringify(all)); } catch { /* progress is a convenience */ } }

/** The chapter page's cards. */
export async function cardsFor(chapter) {
  const { playsFor } = await import('../lw/play/plays.js');
  const done = saved();
  return playsFor(chapter).map((p) => ({ id: p.id, title: p.title, intro: p.intro, won: done[p.id]?.won || 0, total: p.challenges.length }));
}

export async function showPlay(view, id, back) {
  const lw = await import('../lw/index.js');
  const play = lw.PLAYS.find((p) => p.id === id);
  if (!play) { view.innerHTML = '<p class="empty">That is not here.</p>'; return; }
  let values = lw.startValues(play), marks = [], timer = 0, challenge = null;
  view.innerHTML = `
    <nav class="crumbs"><a href="${esc(back)}">Back to the chapter</a></nav>
    <section class="chapter-head"><span class="chapter-no">Try it yourself</span><h1>${esc(play.title)}</h1><p>${esc(play.intro)}</p></section>
    <div class="play">
      <div class="play-picture" id="pic" role="img" aria-label="${esc(play.title)}"></div>
      <div class="play-side">
        <div class="panel" id="task" aria-live="polite"></div>
        <div class="panel" id="controls" hidden></div>
        <div class="panel play-readings" id="readings" hidden></div>
      </div>
    </div>`;
  const $ = (x) => view.querySelector(x), pic = $('#pic'), task = $('#task'), controls = $('#controls'), readings = $('#readings');
  const stop = () => { cancelAnimationFrame(timer); timer = 0; };

  function sceneFor(v) {
    const r = lw.compile({ ...play.spec(v), theme: dark() ? 'dark' : 'light' });
    if (!r.scene) throw new Error(String(r.errors));
    const s = r.scene, target = challenge && play.target?.(challenge);
    if (target) s.props.push({ id: 'target', type: 'polyline', plane: 'p', points: [[target.x - target.half, 0], [target.x + target.half, 0]], style: { stroke: 'good', width: 16 }, layer: 6 });
    marks.forEach(([x, y], i) => s.props.push({ id: `mark${i}`, type: 'circle', plane: 'p', x, y, r: 9, style: { fill: 'accent' }, layer: 6 }));
    return s;
  }
  // The verb's side panel repeats the readings beside it and is too small on a phone: show the drawing, its left 62%
  const draw = (s, t) => { pic.innerHTML = lw.svg(s, Math.min(t, s.duration)).replace(/viewBox="0 0 (\d+) (\d+)"/, (_, w, h) => `viewBox="0 0 ${Math.round(w * 0.62)} ${h}"`); };
  const aim = () => { stop(); draw(sceneFor(values), play.setup); };
  const last = () => { stop(); draw(sceneFor(values), 1e6); };
  /** Plays a run from the start; a tap on the picture skips to its end. */
  const run = (v) => new Promise((done) => {
    stop();
    const s = sceneFor(v), began = performance.now();
    const finish = () => { stop(); pic.onclick = null; draw(s, s.duration); done(); };
    pic.onclick = finish;
    const tick = (now) => { const t = (now - began) / 1000 * 1.4; if (t >= s.duration) return finish(); draw(s, t); timer = requestAnimationFrame(tick); };
    timer = requestAnimationFrame(tick);
  });
  const showReadings = (lists) => {
    readings.hidden = false;
    readings.innerHTML = lists.map(({ head, rows }) => `${head ? `<h3>${esc(head)}</h3>` : ''}<dl>${rows.map(([a, b]) => `<dt>${esc(a)}</dt><dd>${esc(b)}</dd>`).join('')}</dl>`).join('');
  };
  const named = (v) => play.controls.map((c) => `${v[c.id]}${c.unit ? ` ${c.unit}` : ''}`).join(', ');

  function drawControls(onChange, go) {
    controls.hidden = false;
    controls.innerHTML = play.controls.map((c) => (c.kind === 'slider'
      ? `<label class="play-control"><span>${esc(c.label)} <b data-out="${c.id}">${values[c.id]} ${esc(c.unit)}</b></span>
           <input type="range" data-id="${c.id}" min="${c.min}" max="${c.max}" step="${c.step}" value="${values[c.id]}"></label>`
      : `<label class="play-control"><span>${esc(c.label)}</span><select data-id="${c.id}">${c.options.map((o) => `<option${o === values[c.id] ? ' selected' : ''}>${esc(o)}</option>`).join('')}</select></label>`)).join('')
      + (go ? '<button class="btn" id="go">Try it</button>' : '');
    controls.querySelectorAll('[data-id]').forEach((el) => el.addEventListener('input', () => {
      const c = play.controls.find((x) => x.id === el.dataset.id);
      values = { ...values, [c.id]: c.kind === 'slider' ? +el.value : el.value };
      const out = controls.querySelector(`[data-out="${c.id}"]`);
      if (out) out.textContent = `${values[c.id]} ${c.unit}`;
      onChange();
    }));
    if (go) controls.querySelector('#go').addEventListener('click', go);
  }

  async function predict() {
    challenge = null; marks = []; controls.hidden = true; readings.hidden = true;
    values = { ...values, ...play.predict.runs[0] };
    aim();
    task.innerHTML = `<h2>What will happen?</h2><p class="sub">Decide before you see it.</p><p>${esc(play.predict.question)}</p>
      <div class="play-options">${play.predict.options.map((o, i) => `<button class="btn ghost" data-pick="${i}">${esc(o.text)}</button>`).join('')}</div>`;
    task.querySelectorAll('[data-pick]').forEach((b) => b.addEventListener('click', async () => {
      const right = play.predict.options[+b.dataset.pick].right;
      task.querySelectorAll('[data-pick]').forEach((x) => { x.disabled = true; });
      b.classList.add('picked');
      const lists = [];
      for (const r of play.predict.runs) {
        values = { ...values, ...r };
        await run(values);
        if (play.mark) marks.push(play.mark(values));
        lists.push({ head: named(values), rows: play.reading(values) });
        showReadings(lists);
      }
      remember(play.id, { predicted: true });
      task.innerHTML = `<h2>${right ? 'You called it' : 'Not this time'}</h2><p>${esc(play.predict.why)}</p><button class="btn" id="next">Take the challenge</button>`;
      task.querySelector('#next').addEventListener('click', () => setChallenge(0));
    }));
  }

  function setChallenge(i) {
    if (i >= play.challenges.length) return freePlay();
    challenge = play.challenges[i]; marks = []; readings.hidden = true;
    values = { ...lw.startValues(play), ...challenge.start };
    let tries = 0;
    task.innerHTML = `<h2>Challenge ${i + 1} of ${play.challenges.length}</h2><p>${esc(challenge.text)}</p><p class="sub" id="say">Set it up, then try it.</p>`;
    const go = async () => {
      const button = controls.querySelector('#go');
      button.disabled = true; tries += 1;
      await run(values);
      if (play.mark) marks.push(play.mark(values));
      showReadings([{ rows: play.reading(values) }]);
      button.disabled = false;
      if (!challenge.hit(values)) { task.querySelector('#say').textContent = `Try ${tries}: ${challenge.hint(values)}`; return; }
      remember(play.id, { won: Math.max(saved()[play.id]?.won || 0, i + 1) });
      task.innerHTML = `<h2>Done in ${tries === 1 ? 'one try' : `${tries} tries`}</h2><p>${esc(challenge.text)}</p><button class="btn" id="next">${i + 1 < play.challenges.length ? 'Next challenge' : 'Free play'}</button>`;
      task.querySelector('#next').addEventListener('click', () => setChallenge(i + 1));
    };
    drawControls(aim, go);
    aim();
  }

  function freePlay() {
    challenge = null; marks = [];
    task.innerHTML = '<h2>Free play</h2><p class="sub">The picture and the numbers follow you as you move anything.</p><button class="btn ghost" id="again">Start again</button>';
    task.querySelector('#again').addEventListener('click', predict);
    const update = () => { last(); showReadings([{ rows: play.reading(values) }]); };
    drawControls(update);
    update();
  }

  predict();
}
