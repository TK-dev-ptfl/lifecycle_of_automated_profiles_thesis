// Study flow: information and consent -> free browsing -> tasks ->
// questionnaire -> debrief. Recording runs only during the two browsing
// phases. Design and reasons: docs/STUDY.md.

import { makeContent } from './content.js';

const $ = s => document.querySelector(s);
const show = id => { for (const el of document.querySelectorAll('[data-stage]')) el.hidden = el.dataset.stage !== id; scrollTo(0, 0); };

// Minimum free-browsing time before "Continue" unlocks. Long enough for
// several reading/scrolling cycles and a few spontaneous actions; short enough
// not to lose people. See docs/STUDY.md, "Phase 1".
const FREE_MIN_S = 90;

// The guided tasks: the same acts the bot cohorts perform, so human and bot
// sessions can be compared act for act (docs/STUDY.md, "Phase 2").
const TASKS = [
  { id: 'scroll10', text: 'Scroll past at least 10 posts', done: s => s.maxIndex >= 10 },
  { id: 'like3', text: 'Like 3 posts you actually like', done: s => s.likes >= 3 },
  { id: 'comment1', text: 'Write a comment on any post', done: s => s.comments >= 1 },
  { id: 'post1', text: 'Write a short post of your own', done: s => s.posts >= 1 },
  { id: 'profile1', text: "Open someone's profile", done: s => s.profiles >= 1 },
  { id: 'follow1', text: 'Follow one person', done: s => s.follows >= 1 },
];

let cfg, session, recorder, captcha, feed;
const state = { likes: 0, comments: 0, posts: 0, profiles: 0, follows: 0, maxIndex: 0, phase: null, phaseStarted: {}, tasksDone: {} };
let toastTimer;
const toast = msg => { const t = $('#toast'); t.textContent = msg; t.classList.add('show'); clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove('show'), 1600); };

async function api(path, body) {
  const r = await fetch(path, { method: 'POST', headers: { 'content-type': 'application/json', ...(session ? { 'x-session-token': session.writeToken } : {}) },
    body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}

async function init() {
  cfg = await (await fetch('/api/config')).json();
  for (const el of document.querySelectorAll('[data-cfg]')) {
    el.textContent = cfg[el.dataset.cfg] || el.textContent;
    if (el.tagName === 'A' && cfg.contact) el.href = cfg.contact.includes('@') ? 'mailto:' + cfg.contact : cfg.contact;
  }
  $('#consent').addEventListener('submit', e => e.preventDefault());
  $('#recaptcha-note').hidden = !cfg.recaptchaSiteKey;
  $('#webrtc-note').hidden = !cfg.webrtc;
  $('#storage-github').hidden = cfg.storage !== 'github';
  $('#storage-local').hidden = cfg.storage === 'github';
  const boxes = [...document.querySelectorAll('#consent input[type=checkbox]')];
  const sync = () => { $('#start').disabled = !boxes.every(b => b.checked); };
  boxes.forEach(b => b.addEventListener('change', sync)); sync();
  $('#start').addEventListener('click', begin);
  $('#delete-form').addEventListener('submit', async e => {
    e.preventDefault();
    const code = $('#delete-code').value.trim();
    const r = await fetch('/api/delete', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ code }) });
    $('#delete-result').textContent = r.ok ? 'Your data has been deleted.' : 'No session found for that code.';
  });
  show('welcome');
}

async function begin() {
  $('#start').disabled = true;
  const q = new URLSearchParams(location.search);
  try {
    session = await api('/api/session', {
      consent: true, adult: true, consentVersion: cfg.consentVersion,
      cohort: q.get('cohort') || 'human', cohortKey: q.get('key') || undefined, runLabel: q.get('run') || undefined,
    });
  } catch (e) {
    $('#start-error').textContent = 'Could not start: ' + e.message; $('#start').disabled = false; return;
  }
  // Imported only now, so nothing is recorded before consent.
  const { Recorder } = await import('./recorder.js');
  const { Feed } = await import('./feed.js');
  const base = `/api/session/${session.sessionId}`;
  recorder = new Recorder({ endpoint: base + '/batch', token: session.writeToken });
  recorder.start();

  const seed = parseInt(session.sessionId.slice(0, 8), 16);
  recorder.emit('seed', Math.round(performance.now() * 10) / 10, seed);
  feed = new Feed({ root: $('#app'), content: makeContent(seed), recorder, toast, onAction });
  show('app');
  feed.start();
  phase('free');

  // The page is usable at once; the slower measurements run alongside.
  import('./device.js').then(m => m.snapshot()).then(snap => api(base + '/device', snap)).catch(() => null);
  if (cfg.recaptchaSiteKey) {
    const { Captcha } = await import('./captcha.js');
    captcha = new Captcha({ siteKey: cfg.recaptchaSiteKey, endpoint: base + '/recaptcha', token: session.writeToken });
    captcha.load().then(ok => ok && captcha.run('page_load', true));
  }
  if (cfg.webrtc && session.webrtcSalt) {
    import('./webrtc.js').then(m => m.webrtcCheck({ salt: session.webrtcSalt, endpoint: base + '/webrtc', token: session.writeToken }));
  }
  $('#withdraw').addEventListener('click', withdraw);
}

function onAction(name, postId, extra) {
  if (name === 'like') state.likes++;
  if (name === 'unlike') state.likes = Math.max(0, state.likes - 1);
  if (name === 'comment_submit') state.comments++;
  if (name === 'post_submit') state.posts++;
  if (name === 'profile_open') state.profiles++;
  if (name === 'follow') state.follows++;
  if (captcha && ['like', 'comment_submit', 'post_submit', 'follow'].includes(name)) captcha.run(name.replace('_submit', ''));
  renderTasks();
}

function phase(name) {
  state.phase = name;
  state.phaseStarted[name] = Date.now();
  recorder.emit('ph', Math.round(performance.now() * 10) / 10, name);
  const panel = $('#panel');
  if (name === 'free') {
    panel.innerHTML = `<h2>Part 1 of 2: browse</h2>
      <p>Use this feed the way you normally use social media. Scroll, read, like or comment on whatever you want, or nothing at all. There is no right way to do it.</p>
      <button class="pill" id="next" disabled>Continue to part 2</button><p class="hint" id="next-hint">Available after a minute and a half of browsing.</p>`;
    setTimeout(() => { $('#next').disabled = false; $('#next-hint').textContent = 'Continue whenever you are ready.'; }, FREE_MIN_S * 1000);
    $('#next').addEventListener('click', () => phase('tasks'));
  } else if (name === 'tasks') {
    panel.innerHTML = `<h2>Part 2 of 2: a few tasks</h2><p>Do these in any order, at your own pace.</p><ul class="tasks" id="tasks"></ul>
      <button class="pill" id="finish">Finish</button>`;
    $('#finish').addEventListener('click', finish);
    renderTasks();
  }
}

function renderTasks() {
  const posts = document.querySelectorAll('#feed .post');
  // Scrolled past = the post's top is above the viewport's bottom edge.
  posts.forEach((p, i) => { if (p.getBoundingClientRect().top < innerHeight) state.maxIndex = Math.max(state.maxIndex, i + 1); });
  if (state.phase !== 'tasks') return;
  const list = $('#tasks');
  list.innerHTML = TASKS.map(t => {
    const done = t.done(state);
    if (done && !state.tasksDone[t.id]) { state.tasksDone[t.id] = Date.now(); recorder.emit('tk', Math.round(performance.now() * 10) / 10, t.id); }
    return `<li class="${done ? 'done' : ''}"><span aria-hidden="true">${done ? '✓' : '○'}</span>${t.text}</li>`;
  }).join('');
}
addEventListener('scroll', () => renderTasks(), { passive: true });

async function finish() {
  const missing = TASKS.filter(t => !t.done(state));
  if (missing.length && !confirm(`${missing.length} task(s) not done yet. Finish anyway?`)) return;
  captcha && (await captcha.run('finish', true), captcha.stop());
  await recorder.stop();
  show('survey');
}

async function withdraw() {
  if (!confirm('Stop now and delete everything recorded in this session?')) return;
  try { if (recorder) { recorder.stopped = true; clearInterval(recorder.timer); } captcha && captcha.stop(); await api(`/api/session/${session.sessionId}/withdraw`, {}); } catch { /* shown below either way */ }
  show('withdrawn');
}

$('#survey-form')?.addEventListener('submit', async e => {
  e.preventDefault();
  const answers = Object.fromEntries(new FormData(e.target).entries());
  await api(`/api/session/${session.sessionId}/end`, {
    survey: answers,
    tasks: Object.fromEntries(TASKS.map(t => [t.id, state.tasksDone[t.id] ? state.tasksDone[t.id] - state.phaseStarted.tasks : null])),
    phase_started: state.phaseStarted, ended_at: Date.now(),
  }).catch(() => null);
  $('#code').textContent = session.deletionCode;
  show('debrief');
});

init();
