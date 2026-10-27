// The social network itself: feed, composer, comments, profiles. Every
// interactive element carries data-t (what kind of target it is) and, inside a
// post, data-p (which post), so the recorder can say what a click or hover
// was aimed at and how big it was (Fitts' law analysis needs the target size).
//
// Besides the raw input, this module records what the participant was shown
// and when it was on screen:
//   it   an item rendered: post id, word count, characters, media, comments
//   ly   where a post sits on the page (top, height); re-emitted when its size
//        changes (comments opened), so viewport position can be reconstructed
//   iv   how much of a post is in the viewport, at every quarter step
//   act  what the participant did, in social-media terms (like, comment, ...)

const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const fmt = n => n >= 1000 ? (n / 1000).toFixed(n >= 10000 ? 0 : 1) + 'K' : String(n);
const wordCount = s => s.trim().split(/\s+/).filter(Boolean).length;
const now = () => Math.round(performance.now() * 10) / 10;

const ICON = {
  like: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/></svg>',
  cmt: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M4 5h16v11H9l-5 4z"/></svg>',
  rep: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3l3 3-3 3M20 6H8a4 4 0 0 0-4 4v1M7 21l-3-3 3-3M4 18h12a4 4 0 0 0 4-4v-1"/></svg>',
  save: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M6 3h12v18l-6-4-6 4z"/></svg>',
  share: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 15V3M7 8l5-5 5 5M5 13v7h14v-7"/></svg>',
  more: '<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="1.8"/><circle cx="12" cy="12" r="1.8"/><circle cx="19" cy="12" r="1.8"/></svg>',
};

const avatar = (p, cls = '') => `<span class="av ${cls}" style="--h:${p.hue}" aria-hidden="true">${esc(p.initials)}</span>`;
const mediaStyle = m => `background:radial-gradient(circle at ${m.x1}% ${m.y1}%, hsl(${m.h2} 80% 70% / .9), transparent 45%),`
  + `radial-gradient(circle at ${m.x2}% ${m.y2}%, hsl(${(m.h2 + 60) % 360} 70% 60% / .8), transparent 40%),`
  + `linear-gradient(${m.angle}deg, hsl(${m.h} 60% 45%), hsl(${m.h2} 55% 30%))`;

const ME = { id: 'me', name: 'You', handle: 'you', initials: 'YO', hue: 255 };

export class Feed {
  constructor({ root, content, recorder, onAction, toast }) {
    Object.assign(this, { root, content, rec: recorder, onAction, toast });
    this.shown = 0;
    this.posts = new Map();
    this.$feed = root.querySelector('#feed');
    this.$sentinel = root.querySelector('#sentinel');
  }

  emit(...e) { this.rec && this.rec.emit(...e); }

  act(name, postId = '', extra = null) {
    this.emit('act', now(), name, postId, extra);
    this.onAction && this.onAction(name, postId, extra);
  }

  start() {
    this.view = new IntersectionObserver(entries => {
      for (const e of entries) this.emit('iv', Math.round(e.time * 10) / 10, e.target.dataset.post, Math.round(e.intersectionRatio * 100) / 100);
    }, { threshold: [0, 0.25, 0.5, 0.75, 1] });
    this.layout = new ResizeObserver(entries => {
      for (const e of entries) {
        const r = e.target.getBoundingClientRect();
        this.emit('ly', now(), e.target.dataset.post, Math.round(r.top + scrollY), Math.round(r.height));
      }
    });

    this.root.querySelector('#trends').innerHTML = this.content.trends.map(([t, n]) =>
      `<button class="trend" data-t="trend"><b>${esc(t)}</b><span>${esc(n)}</span></button>`).join('');
    this.root.querySelector('#who').innerHTML = this.content.people.slice(0, 3).map(p =>
      `<div class="who">${avatar(p)}<div><b>${esc(p.name)}</b><span>@${esc(p.handle)}</span></div>`
      + `<button class="pill quiet" data-t="follow" data-p="${p.id}" aria-pressed="false">Follow</button></div>`).join('');

    this.add(8);
    new IntersectionObserver(es => {
      if (es.some(e => e.isIntersecting)) setTimeout(() => this.add(6), 250 + Math.random() * 350);
    }, { rootMargin: '600px' }).observe(this.$sentinel);

    this.root.addEventListener('click', e => this.click(e));
    this.root.addEventListener('keydown', e => {
      if (e.key === 'Enter' && e.target.dataset.field === 'reply') { e.preventDefault(); this.sendReply(e.target.closest('.post')); }
      if (e.key === 'Enter' && e.target.dataset.field === 'search') { e.preventDefault(); this.act('search_submit', '', { chars: e.target.value.length }); this.toast('Search is not part of this study'); }
    });
  }

  add(n) {
    if (this.shown >= 150) { this.$sentinel.textContent = "You're all caught up."; return; }
    const html = [];
    for (const p of this.content.nextPosts(n)) { this.posts.set(p.id, p); html.push(this.postHTML(p)); }
    const before = this.$feed.children.length;
    this.$feed.insertAdjacentHTML('beforeend', html.join(''));
    for (const el of [...this.$feed.children].slice(before)) this.observe(el);
    this.shown += n;
  }

  observe(el) {
    const p = this.posts.get(el.dataset.post);
    if (p) this.emit('it', now(), p.id, p.words, p.chars, p.media ? 1 : 0, p.comments.length, this.shown, p.author.id);
    this.view.observe(el); this.layout.observe(el);
  }

  postHTML(p, { own = false } = {}) {
    const a = p.author;
    return `<article class="post${own ? ' new' : ''}" data-post="${p.id}">
      <header class="ph">
        <button class="who-btn" data-t="author" data-p="${p.id}" data-user="${a.id}">${avatar(a)}<span class="who-line"><b>${esc(a.name)}</b><span>@${esc(a.handle)} · ${esc(p.ago)}</span></span></button>
        ${own ? '' : `<button class="pill quiet follow" data-t="follow" data-p="${a.id}" aria-pressed="false">Follow</button>`}
        <button class="icon" data-t="more" data-p="${p.id}" aria-label="More options">${ICON.more}</button>
      </header>
      <p class="text">${esc(p.text)}</p>
      ${p.media ? `<div class="media" style="${mediaStyle(p.media)}" role="img" aria-label="Photo" data-t="media" data-p="${p.id}"></div>` : ''}
      <div class="acts">
        <button class="act like" data-t="like" data-p="${p.id}" aria-pressed="false" aria-label="Like">${ICON.like}<span>${fmt(p.likes)}</span></button>
        <button class="act" data-t="cmt" data-p="${p.id}" aria-expanded="false" aria-label="Comments">${ICON.cmt}<span>${p.comments.length}</span></button>
        <button class="act rep" data-t="repost" data-p="${p.id}" aria-pressed="false" aria-label="Repost">${ICON.rep}<span>${fmt(p.reposts)}</span></button>
        <button class="act save" data-t="save" data-p="${p.id}" aria-pressed="false" aria-label="Save">${ICON.save}</button>
        <button class="act" data-t="share" data-p="${p.id}" aria-label="Share">${ICON.share}</button>
      </div>
      <div class="comments" hidden>
        ${p.comments.map(c => `<div class="cmt">${avatar(c.who, 'sm')}<div><b>${esc(c.who.name)}</b><p>${esc(c.text)}</p></div></div>`).join('')}
        <div class="reply"><input data-field="reply" data-t="reply" data-p="${p.id}" placeholder="Write a comment" aria-label="Write a comment" maxlength="500" autocomplete="off"><button class="pill" data-t="send" data-p="${p.id}">Reply</button></div>
      </div>
    </article>`;
  }

  toggle(b, attr = 'aria-pressed') { const on = b.getAttribute(attr) !== 'true'; b.setAttribute(attr, on); return on; }

  click(e) {
    const b = e.target.closest('[data-t]');
    if (!b) return;
    const t = b.dataset.t, pid = b.dataset.p || '';
    const post = b.closest('.post');
    switch (t) {
      case 'like': case 'repost': {
        const on = this.toggle(b);
        const p = this.posts.get(pid);
        if (p) { const k = t === 'like' ? 'likes' : 'reposts'; p[k] += on ? 1 : -1; b.querySelector('span').textContent = fmt(p[k]); }
        if (t === 'repost') this.toast(on ? 'Reposted' : 'Repost removed');
        this.act(on ? t : 'un' + t, pid);
        break;
      }
      case 'save': { const on = this.toggle(b); this.toast(on ? 'Saved' : 'Removed from saved'); this.act(on ? 'save' : 'unsave', pid); break; }
      case 'share': this.toast('Link copied'); this.act('share', pid); break;
      case 'more': this.toast('Post options are not part of this study'); this.act('more', pid); break;
      case 'media': this.act('media_click', pid); break;
      case 'cmt': {
        const c = post.querySelector('.comments'); c.hidden = !c.hidden; b.setAttribute('aria-expanded', !c.hidden);
        this.act(c.hidden ? 'comments_close' : 'comments_open', pid);
        break;
      }
      case 'send': this.sendReply(post); break;
      case 'follow': {
        const on = this.toggle(b); b.textContent = on ? 'Following' : 'Follow';
        this.act(on ? 'follow' : 'unfollow', pid);
        break;
      }
      case 'author': this.openProfile(b.dataset.user, pid); break;
      case 'profile-close': this.closeProfile(); break;
      case 'post-btn': this.submitPost(); break;
      case 'nav': case 'trend': this.toast('This section is not part of this study'); this.act(t + '_click', '', b.dataset.name || null); break;
      default: break;
    }
  }

  sendReply(post) {
    const input = post.querySelector('[data-field="reply"]');
    const v = input.value.trim();
    if (!v) { input.focus(); return; }
    input.closest('.reply').insertAdjacentHTML('beforebegin', `<div class="cmt">${avatar(ME, 'sm')}<div><b>You</b><p>${esc(v)}</p></div></div>`);
    input.value = '';
    const p = this.posts.get(post.dataset.post);
    const count = post.querySelector('[data-t="cmt"] span');
    count.textContent = Number(count.textContent) + 1;
    // Length only: what people write is not what this study measures.
    this.act('comment_submit', post.dataset.post, { chars: v.length, words: wordCount(v) });
    if (p) p.comments.push({ who: ME, text: v });
  }

  submitPost() {
    const ta = this.root.querySelector('[data-field="composer"]');
    const v = ta.value.trim();
    if (!v) { ta.focus(); return; }
    const p = { id: 'own' + Date.now().toString(36), author: ME, text: v, words: wordCount(v), chars: v.length, ago: 'now', likes: 0, reposts: 0, comments: [], media: null };
    this.posts.set(p.id, p);
    this.$feed.insertAdjacentHTML('afterbegin', this.postHTML(p, { own: true }));
    this.observe(this.$feed.firstElementChild);
    ta.value = '';
    this.toast('Posted');
    this.act('post_submit', p.id, { chars: v.length, words: p.words });
  }

  openProfile(userId, fromPost) {
    const person = this.content.people.find(x => x.id === userId);
    if (!person) return;
    const panel = this.root.querySelector('#profile');
    const posts = this.content.postsBy(person, 3);
    for (const p of posts) this.posts.set(p.id, p);
    panel.querySelector('.profile-body').innerHTML = `
      <div class="profile-head">${avatar(person, 'lg')}<div><h2>${esc(person.name)}</h2><span>@${esc(person.handle)}</span></div>
        <button class="pill quiet" data-t="follow" data-p="${person.id}" aria-pressed="false">Follow</button></div>
      <p class="bio">${esc(person.bio)}</p>
      <p class="stats"><b>${fmt(person.following)}</b> following · <b>${fmt(person.followers)}</b> followers</p>
      <div class="profile-posts">${posts.map(p => this.postHTML(p)).join('')}</div>`;
    panel.hidden = false;
    for (const el of panel.querySelectorAll('.post')) this.observe(el);
    panel.querySelector('[data-t="profile-close"]').focus({ preventScroll: true });
    this.act('profile_open', fromPost, { user: person.id });
  }

  closeProfile() {
    const panel = this.root.querySelector('#profile');
    for (const el of panel.querySelectorAll('.post')) { this.view.unobserve(el); this.layout.unobserve(el); }
    panel.hidden = true;
    this.act('profile_close');
  }
}
