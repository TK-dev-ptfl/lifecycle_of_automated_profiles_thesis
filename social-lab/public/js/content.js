// Synthetic feed content, generated from a per-session seed so the analysis
// can reproduce exactly what each participant was shown (the seed is stored
// with the session). No real people, no real posts.
//
// Post length is varied on purpose: reading time can only be related to text
// length (Brysbaert 2019; Grusky et al. 2017) if lengths differ. Measured over
// 1,500 generated posts: 39 % short (6-25 words), 42 % medium (26-60), 19 %
// long (61-145), 35 % with an image. Change the targets in post() and this
// line together.

export function rng(seed) {
  // mulberry32
  let a = seed >>> 0;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const FIRST = ['Maya', 'Tomás', 'Ines', 'Kofi', 'Lena', 'Arjun', 'Sofia', 'Noah', 'Yuki', 'Rita', 'Omar', 'Clara', 'Diego', 'Hana',
  'Felix', 'Amara', 'Jonas', 'Leila', 'Marco', 'Priya', 'Elias', 'Zoe', 'Rui', 'Nadia', 'Petra', 'Ivan', 'Mira', 'Oskar'];
const LAST = ['Ferreira', 'Okafor', 'Lindqvist', 'Tanaka', 'Moreau', 'Kaur', 'Silva', 'Novak', 'Haddad', 'Brennan', 'Costa', 'Ito',
  'Mendes', 'Varga', 'Adeyemi', 'Rossi', 'Kovac', 'Berg', 'Duarte', 'Nyström'];
const BIOS = ['Coffee, cycling, and too many houseplants.', 'Amateur baker. Professional overthinker.', 'Teacher by day, guitarist by night.',
  'Trying to run a marathon before I turn 40.', 'Software person. Opinions about tabs.', 'Photographing my city one corner at a time.',
  'Learning Portuguese, badly but daily.', 'Board games and long walks.', 'Nurse. Night shifts. Strong tea.', 'Collector of very small notebooks.'];

// Each entry is one unit. A sentence that only makes sense after another is
// kept together with it, so no post opens on a dangling follow-up.
const TOPICS = {
  food: [
    'Tried making ramen broth from scratch this weekend. Twelve hours of simmering later, it was worth every minute.',
    'The bakery downstairs started selling cardamom buns and my budget is in trouble.',
    'My grandmother\'s apple cake recipe is written in pencil with three crossed-out versions.',
    'I finally understand why people get obsessed with sourdough. The trick, apparently, is patience and a warm kitchen.',
    'Does anyone actually measure the salt, or do we all just guess?',
    'Dinner tonight was whatever was left in the fridge, and somehow it was great.',
    'The market had the first pumpkins of the season today.',
    'Burnt the garlic again.',
  ],
  outdoors: [
    'Ran my first 10k this morning. Slow, sweaty and very happy about it.',
    'Saw a heron fishing in the canal on the way to work.',
    'The sunset tonight looked like someone spilled orange juice across the river.',
    'Took the long way home just to finish the album I was listening to.',
    'There is a bench by the lake that nobody seems to know about.',
    'The first cold morning of the year always surprises me.',
    'Our hiking group got completely lost and ended up finding the best viewpoint of the trip.',
    'It rained all day and I loved every minute of it.',
  ],
  home: [
    'Finally fixed the squeaky door hinge that has been haunting me since March.',
    'Repainted the kitchen a soft green and it feels like a different flat.',
    'Planted tomatoes on the balcony. If anyone has tips for keeping pigeons away, I am listening.',
    'The cat has decided my keyboard is the warmest place in the house. Productivity is at zero but morale is high.',
    'Reorganised the bookshelf by colour. It looks wonderful and I can no longer find anything.',
    'Bought a second-hand armchair and it is now my favourite place in the world.',
    'The neighbours are learning the trumpet.',
  ],
  work: [
    'Three hours of debugging to find a missing comma. Going for a walk now.',
    'Our team shipped the thing we have been working on all quarter. Celebrating with questionable office pizza.',
    'Is it just me or did this week last about a month?',
    'Moved the monitor to eye level and my neck already feels better.',
    'The best meetings are the ones that end ten minutes early.',
    'Started writing down one thing I learned each day, and the list is longer than I expected.',
    'Inbox zero, for about four minutes.',
  ],
  culture: [
    'Went to a tiny jazz bar last night and the trio played for two hours straight.',
    'Learning to play the cello at 34. My neighbours are being very patient about it.',
    'Reminder that you are allowed to leave a book unfinished.',
    'Commute podcast recommendations? I have run out of everything.',
    'The second season was better than the first, which almost never happens.',
    'Started journaling again and I am on day four, which is a personal record.',
    'Saw a street musician play a song I had not heard since school.',
    'Finished a thousand-piece puzzle and immediately regretted not gluing it.',
  ],
};
const TOPIC_KEYS = Object.keys(TOPICS);
const LINKERS = ['Honestly,', 'Also,', 'Anyway,', 'To be fair,', 'Funny thing is,', 'Not going to lie,', 'In other news,'];
const COMMENTS = ['So relatable', 'This made my day', 'Need the recipe!', 'Congrats!', 'Same here honestly', 'Love this', 'Ha, exactly',
  'Where was this?', 'You inspired me to try it', 'Saving this for later', 'Ten out of ten', 'Tell me more', 'Absolutely beautiful',
  'I had the exact same week', 'This is the content I am here for', 'Okay now I want to try this too'];
const TRENDS = [['Morning runs', '4,210 posts'], ['Balcony gardens', '2,880 posts'], ['Ramen at home', '1,945 posts'],
  ['Rainy Sunday', '12.4K posts'], ['Jazz bars', '980 posts'], ['First cold morning', '3,302 posts']];

const words = s => s.split(/\s+/).filter(Boolean).length;

export function makeContent(seed) {
  const r = rng(seed);
  const pick = a => a[Math.floor(r() * a.length)];
  const int = (a, b) => a + Math.floor(r() * (b - a + 1));

  const people = Array.from({ length: 40 }, (_, i) => {
    const f = pick(FIRST), l = pick(LAST);
    return { id: 'u' + i, name: `${f} ${l}`, handle: (f + l.slice(0, 3)).normalize('NFD').replace(/[^\w]/g, '').toLowerCase() + int(1, 99),
      initials: f[0] + l[0], hue: int(0, 359), bio: pick(BIOS), followers: int(40, 9000), following: int(30, 900) };
  });

  function body(target) {
    const topic = pick(TOPIC_KEYS);
    const out = [];
    let n = 0, guard = 0;
    const used = new Set();
    while (n < target && guard++ < 60) {
      const base = pick(TOPICS[r() < 0.8 ? topic : pick(TOPIC_KEYS)]);
      // Each sentence at most once per post, with or without a connective.
      if (used.has(base)) continue;
      // Stay near the target length: skip a sentence that would overshoot it
      // by more than a few words (the first sentence is always taken).
      if (out.length && n + words(base) > target + 6) continue;
      used.add(base);
      const s = out.length && r() < 0.25 ? pick(LINKERS) + ' ' + base[0].toLowerCase() + base.slice(1) : base;
      out.push(s); n += words(s);
    }
    // Long posts get paragraph breaks, as long posts do.
    if (n > 60) { const cut = Math.ceil(out.length / 2); return out.slice(0, cut).join(' ') + '\n\n' + out.slice(cut).join(' '); }
    return out.join(' ');
  }

  function post(i) {
    const roll = r();
    const target = roll < 0.5 ? int(8, 25) : roll < 0.85 ? int(26, 60) : int(61, 140);
    const text = body(target);
    const hasMedia = r() < 0.35;
    const h = int(0, 359);
    return {
      id: 'p' + i, author: pick(people), text, words: words(text), chars: text.length,
      ago: pick(['2m', '9m', '24m', '1h', '3h', '5h', '8h', '1d', '2d']),
      likes: int(0, 2400), reposts: int(0, 300),
      comments: Array.from({ length: int(0, 5) }, () => ({ who: pick(people), text: pick(COMMENTS) })),
      media: hasMedia ? { h, h2: (h + int(40, 140)) % 360, x1: int(10, 90), y1: int(10, 90), x2: int(10, 90), y2: int(10, 90), angle: int(0, 180) } : null,
    };
  }

  let next = 0;
  return {
    seed, people, trends: TRENDS,
    nextPosts(n) { return Array.from({ length: n }, () => post(next++)); },
    // A profile's posts come from their own generator, so opening a profile
    // does not shift the main feed: the seed alone reproduces the feed.
    postsBy(person, n) {
      const own = makeContent((seed ^ (Number(person.id.slice(1)) + 1) * 2654435761) >>> 0);
      return own.nextPosts(n).map((p, i) => ({ ...p, id: `${person.id}-p${i}`, author: person }));
    },
  };
}
