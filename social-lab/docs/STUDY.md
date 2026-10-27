# Study design

Social Lab is a dummy social network ("Hearth") that records how real people use
a social feed: pointer, keyboard, scrolling, reading and engagement, plus what their
browser, machine and connection reveal about them. It exists for two purposes:

1. **Calibrate** the behaviour algorithm (`backend/app/behaviour`). Every number in
   `BehaviourProfile` and the motor primitives is currently a literature value or a
   guess. This study replaces them with distributions measured on real people, on a
   social feed, doing the same acts the bots do.
2. **Evaluate** detection. Measure how each bot-detection signal behaves on real
   people: its false-positive rate. Then, with bot runs labelled as their own cohort,
   measure how well each signal separates bots from people.

The data dictionary ([DATA_DICTIONARY.md](DATA_DICTIONARY.md)) lists every recorded
field with what it tells and which question it serves. [ANALYSIS.md](ANALYSIS.md)
defines every derived measurement. Sources are in [REFERENCES.md](REFERENCES.md).

## Principle: nothing without a question

A field is recorded only if a research question below needs it. Each question
states three things:
- **what** is measured;
- **why** it matters: the behavioural or technical basis, with a source;
- **where** the answer goes: which algorithm parameter it calibrates, or which
  detector signal it evaluates.

Fields that would be easy to collect but answer none of these are listed under
"Deliberately not collected" in the data dictionary.

## Research questions

### Pointer (M)

**RQ-M1: Kinematics of aimed movements.** For each aimed mouse movement:
- straightness;
- peak and mean speed;
- where along the movement the speed peaks;
- how sharply it decelerates at the end;
- how many corrective submovements it contains;
- how much its heading jitters.

*Basis.* Aimed human movements are near-straight with a bell-shaped speed profile
[morasso1981spatial; flash1985coordination]. They consist of a primary submovement
plus optional corrections whose number grows with required precision
[meyer1988optimality]. Bot-detection work separates humans from bots on exactly these
kinematics [ahmed2007mouse; chu2013blog; iliou2021webbots; acien2022becaptcha].
SapiMouse records them for desktop drag tasks, not for a social feed
[antal2021sapimouse].

*Used for.* `BehaviourProfile.path_curviness`, the velocity profile in
`primitives/mouse.py`, and the overshoot logic. It is also a social-feed reference for
the mouse classifier, which was trained on other tasks.

**RQ-M2: Pointing to targets (Fitts' law).**
- Movement time against index of difficulty, ID = log2(D/W + 1), for every click on a
  known target;
- endpoint scatter along and across the approach;
- how often the cursor overshoots.

*Basis.* Fitts' law [fitts1954information], in the Shannon formulation with
direction-dependent target width [mackenzie1992fitts]. Endpoint spread grows with
speed and target size [wobbrock2008error]. A script either ignores target size or
clicks the exact centre.

*Used for.* `aim_scatter` and `overshoot_chance`, and the timing of `ClickOn`. The
pooled a and b are the parameters a movement-time model needs.

**RQ-M3: The press.**
- How long a mouse button is held;
- how long the cursor rests on a target before pressing;
- whether the target was hovered first.

*Basis.* A physical button press takes tens of milliseconds; synthetic clicks often
take none. Our earlier validation measured a 80 ms median on SapiMouse
(`backend/tests/behaviour/test_env/VALIDATION.md`).

*Used for.* `settle_s()` and the press duration in `Actor._click_here`.

**RQ-M4: The idle hand.**
- Share of non-acting time during which the pointer moves (restlessness);
- whether the cursor tracks the post being read.

*Basis.* Cursor and gaze are related, but not simply. People follow text with the
cursor, park it, or mark items with it [chen2001mouse; rodden2008eyemouse;
huang2012gaze].

*Used for.* `restlessness` and `reads_with_cursor`, both currently guesses (0.5 and
0.3).

**RQ-M5: Input devices and sampling.**
- Which pointing devices people use;
- the device report rate, from coalesced pointer samples;
- how wheel deltas differ between mouse and trackpad.

*Basis.* The Pointer Events specification: browsers coalesce samples a device reports
faster than the frame rate [w3c_pointerevents3]. Input injected through DevTools has
one sample per event.

*Used for.*
- the realistic mix of device types for identities;
- the base rate of the "no coalesced samples" signal among humans: trackpads, and
  some browsers, may never coalesce.

### Keyboard (K)

**RQ-K1: Key hold time in free typing.** *Basis:* keystroke dynamics
[killourhy2009keystroke]. The current `key_hold_ms` prior (median 86 ms) comes from
typing a fixed password, not free text. *Used for:* `key_hold_ms` and its spread in
`derive_for`.

**RQ-K2: Rhythm and speed.**
- Inter-key intervals and their variation;
- words per minute;
- rollover: the next key pressed before the previous one is released.

*Basis.* 136 million keystrokes from 168,000 typists. Rollover is common and marks
fast typists; IKI distributions cluster into typist types [dhakal2018typing].

*Used for.* `typing_wpm`, and adding rollover to `primitives/keyboard.py`, which today
never overlaps keys.

**RQ-K3: Corrections.** Backspace rate. *Used for:* `typo_chance`.

**RQ-K4: Pauses that carry structure.**
- Time from clicking into a field to the first key;
- the interval before the first letter of a word vs. inside a word;
- same-hand vs. alternating-hand key pairs.

*Basis.* Word boundaries and hand alternation shape inter-key intervals
[dhakal2018typing].

*Used for.* The think time before `TypeInto`, and a per-word timing model in place of
today's independent per-key delays.

### Scrolling and reading (S, R)

**RQ-S1: The wheel.**
- Delta mode and size per notch;
- intervals between notches within a burst;
- notches per burst.

*Used for.* `primitives/scroll.py`: notch timing and burst length.

**RQ-S2: Scrolling and reading pauses.**
- Scroll speed during bursts;
- the number and length of pauses between bursts;
- the share of scrolling not driven by the wheel (scrollbar, keys, touch).

*Used for.* The reading-pause model in `ReadFeed`.

**RQ-R1: Reading time vs. post length.** Time each post is at least 50 % visible,
regressed on its word count.

*Basis.* Viewport time is a validated proxy for attention to page components
[lagun2016attention; grusky2017viewport]. Grusky et al. validate it by recovering
reading rates. Silent reading of non-fiction averages 238 words per minute
[brysbaert2019reading].

*Used for.* `reading_time_s`, which assumes 220 wpm. Posts span 6–145 words (39 % up to 25 words, 42 % 26–60, 19 %
longer; 35 % carry an image, measured over 1,500 generated posts) so that the slope
can be estimated. Skimming (posts passed in under 1 s) is reported
separately.

**RQ-R2: Images.** Viewport time of posts with and without an image.

### Engagement (E)

**RQ-E1: Deciding.** Time from a post becoming visible to liking it. *Used for:* the
dwell before engagement in the like and comment goals.

**RQ-E2: Choosing.** Which posts get liked: length, position in the feed. *Used for:*
the probabilistic post selector of thesis 3.3.2.

**RQ-E3: Session rhythm.**
- Inter-action intervals;
- burstiness B and memory M;
- the action sequence as a string.

*Basis.* Human activity is bursty, with heavy-tailed waiting times [barabasi2005bursts]:
high B with low M [goh2008burstiness]. Behavioural sequences as strings are the BLOC
representation [nwala2023bloc]. A bot acting on a fixed schedule has B near −1.

*Used for.* The session scheduler and the warm-up pipeline's action timing.

**RQ-E4: Unprompted engagement.** Do people like or comment when not asked to (phase
1)? *Used for:* warm-up intensity; a passive first day is the thesis's own plan
(table 3.3).

### Hardware (H)

**RQ-H1: The joint distribution of devices.** OS, browser and version, screen and
DPR, cores, memory, GPU vendor, languages and time zone, *together*.

*Basis.* Fingerprint attributes are strongly correlated [laperdrix2016beauty;
gomezboix2018hiding; laperdrix2020survey]. Detectors look for inconsistent
combinations [venugopalan2024fpinconsistent].

*Used for.* Replace independent random pools in `fingerprint.py` with combinations
sampled from real ones.

**RQ-H2: Display refresh.** Frame interval, i.e. 60/120/144 Hz. A headless browser
runs at a fixed rate.

**RQ-H3: How often real people trip each automation and consistency check.** This is
each check's false-positive rate:
- webdriver, automation globals, tampered built-ins;
- worker/iframe disagreement, unstable canvas, permission mismatch;
- BotD.

Privacy extensions and hardened browsers are expected to trip some of them; this
measures how often.

### Network (N)

**RQ-N1: TLS fingerprints of real browsers.** JA4/JA3 by browser family and version.

*Basis.* TLS fingerprints identify the client library [jarad2026tls]. JA4 is
specified by FoxIO [foxio_ja4].

*Used for.*
- knowing which JA4 each real browser produces;
- the "claims Chrome but negotiates TLS like Python" check for the HTTP-based
  communication methods (thesis 2.1.4 and 5.3).

**RQ-N2: Header order.** Request header order and values per browser. HTTP libraries
order and capitalise headers differently from browsers.

**RQ-N3: Proxy and VPN signals among humans.** The share of people on hosting, proxy
or mobile networks; time zone disagreeing with IP location; WebRTC disagreeing with
the request address.

*Why it matters.* The thesis's identities go out through proxies (3.4.2). These are
the signals a platform would use against them. Their base rate among ordinary people
decides whether a platform can afford to act on them.

**RQ-N4: Latency.** Round-trip time to the server and clock offset. Exploratory: a
proxied client has a longer RTT than its claimed location suggests.

### Commercial detectors (X)

**RQ-X1: reCAPTCHA v3 and BotD on real people.** Score distribution, and the share of
humans scored below 0.5 or flagged.

*Basis.* reCAPTCHA v3 is documented only as a score [google_recaptcha_v3]. It has been
defeated before [akrout2019recaptcha], and the effectiveness of modern CAPTCHAs is
contested [searles2023captcha]. It is a reference, never ground truth.

### Validation (V)

**RQ-V1: Which signals separate bots from people.** For each metric, the AUC between
the human cohort and each bot cohort [mann1947test; hanley1982auc]. For each session,
the share of metrics outside the human central 95 %.

This is how a change to the algorithm is judged: a better algorithm moves its
cohort's AUCs towards 0.5 and its outside-share towards the human level.

## Design

### Phases
1. **Information and consent.** Nothing is recorded until all three boxes are ticked.
   The recorder is not even loaded before that.
2. **Phase 1: free browsing**, at least 90 s, then "Continue" unlocks.
   - *Instruction:* use the feed as you normally would.
   - *Why:* ecological validity. RQ-E4, RQ-R1 and RQ-M4 need behaviour that was not
     asked for.
   - *Why 90 s:* long enough for several scroll–read cycles, short enough to keep the
     whole study under 8 minutes.
3. **Phase 2: tasks**, in any order:
   - scroll past 10 posts;
   - like 3 posts;
   - comment once;
   - post once;
   - open a profile;
   - follow someone.

   *Why:* comparability. These are the acts the bot cohorts perform, and they
   guarantee every session has clicks, typing and target acquisitions (RQ-M2, RQ-K).
4. **Questionnaire.** Seven optional items, each needed to interpret the data:

   | Item | Needed because |
   |---|---|
   | input device | trackpads move differently; RQ-M5 |
   | hand | left-handed mouse use mirrors movement asymmetries |
   | typing style | touch typists vs. visual typists differ in rhythm [dhakal2018typing] |
   | English as first language | reading rate is lower in a second language [brysbaert2019reading] |
   | age band | motor speed changes with age |
   | daily social media use | familiarity with feeds |
   | did you browse naturally (1–5) | lets unnatural sessions be excluded |

5. **Debrief and deletion code.**

### Ground truth: cohorts
Every session is `cohort=human` unless it presents the secret `COHORT_KEY`. Bot runs
open the site as `/?cohort=<label>&key=<COHORT_KEY>&run=<free text>`, for example
`cohort=behaviour-v3` or `cohort=robotic`. Participants therefore cannot mislabel
themselves, and every algorithm version becomes its own comparable cohort.

### Controls
- **Same content for everyone.** The feed is generated from a per-session seed with
  fixed length and image proportions, so differences are not caused by different
  posts. The seed is stored, so a session's feed can be regenerated.
- **Scores are hidden.** The page never sees the reCAPTCHA score or any check result.
  A participant who saw them could change behaviour, and that behaviour is what is
  being measured.
- **Same tasks for humans and bots.**

### Sample size
- **Medians and interquartile ranges** (most rows of the summary): at least **20**
  human sessions per device type.
- **Central 95 % ranges**, used by the outside-the-human-range score: at least
  **40**, because each tail needs about one observation per 40 to be estimated at all.
- **AUC precision.** With 20 humans and 20 bot sessions, an AUC of 0.75 has a
  standard error of about 0.08 by the Hanley–McNeil approximation [hanley1982auc].
  Differences smaller than about 0.15 between algorithm versions cannot be resolved
  at that size.

Recruit at least **40 mouse users**. Trackpad and touch sessions are kept, but form
their own reference.

### Exclusions (analysis time, not collection time)
- not finished;
- reported device ≠ the reference device;
- naturalness rating 1;
- hidden-tab time over 50 %;
- any hard automation flag in a "human" session. Report how many sessions this
  excluded: it is itself RQ-H3.

## Ethics and data protection

This collects behavioural data from people. Settle the following before launch.
Several are not decisions an engineer can make alone.

1. **Ethics approval.** Ask the faculty whether a study with human participants
   needs ethics committee approval. Thesis 2.5.3 currently says there is no
   interaction with real users; add a paragraph describing this consented,
   opt-in study.
2. **Lawful basis.** GDPR Art. 6(1)(a): consent, given by ticking three boxes and
   recorded with a consent version.

   Mouse and keystroke dynamics are behavioural characteristics that *can* be used
   to identify people [ahmed2007mouse; killourhy2009keystroke]. This study does not
   use them to identify anyone. Still, ask the university's data protection officer
   whether Art. 9 applies, and state the answer in the thesis.
3. **Data minimisation**, built in:
   - no IP address stored (only a network type and a daily rotating keyed hash);
   - no key identities (only categories and the hand);
   - no text content (only lengths);
   - no fonts, canvas images or audio fingerprints;
   - no cookies beyond one 30-minute cookie that links the page load to consent.
4. **Rights.** Withdraw during the session (immediate deletion), or later with the
   deletion code. Only a hash of the code is stored.
5. **Third parties.** reCAPTCHA sends data to Google; the consent text says so and
   links Google's terms. The WebRTC check contacts a Google STUN server; it is off by
   default. The IP lookup service sees the address; it can be turned off
   (`IP_LOOKUP=0`). With the Railway setup, Railway (USA) hosts the server and GitHub
   (USA) stores the sessions, encrypted with a key only the researcher holds; the
   consent text says so (it changes with the configuration).
6. **Storage.** Two options:
   - **own server:** one folder per session under `data/`, never committed;
   - **Railway setup:** each session encrypted (RSA-OAEP + AES-256-GCM) before it
     leaves the server, then stored in a private GitHub repository. The server holds
     only the public key, and the private key never leaves the researcher's machine.

   Deletion requests remove the file at once. Git history is purged monthly, as the
   consent text promises (deploy/DEPLOY_RAILWAY.md). Delete everything after the
   retention period stated in the consent text (3 years at most).
7. **Fill in before launch:** `STUDY_CONTACT`, `STUDY_RESEARCHER` and
   `STUDY_INSTITUTION`. The server refuses to start without a contact unless `DEV=1`.

## Limitations

- **Self-selected participants** recruited by one person are not a population
  sample. Report the questionnaire distribution.
- **A dummy feed is not Reddit.** Content is synthetic and nobody else reacts.
  Phase 1 behaviour is closer to natural than task behaviour, but people know they
  are being studied.
- **Viewport time includes looking away.** Grusky et al.'s Gaussian model, which
  `ly` + `sc` make possible to fit, partly addresses this; idle viewport time stays
  an upper bound on reading.
- **Timer resolution.** Browsers coarsen `performance.now()` (Chrome to 100 µs
  without cross-origin isolation, Firefox to 1 ms). Fine for movement; borderline
  for key-hold differences under 2 ms.
- **TLS fingerprints need this server to terminate TLS.** Behind a CDN or reverse
  proxy, RQ-N1 is unavailable.
- **One session per person.** Within-person variation across days is not measured.
