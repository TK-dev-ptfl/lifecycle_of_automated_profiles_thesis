# References

What each source is used for in Social Lab. Full entries are in
[references.bib](references.bib); keys shared with the thesis bibliography
(`../../literatura.bib`) are identical.

The bibliographic details were checked on 2026-10-16/19 against the publisher,
Crossref or DBLP records, or the paper itself. The burstiness formula was checked in
the EPL paper; the JA4 algorithm and its test vectors in the FoxIO specification.

## Movement and pointing

| Key | Used for |
|---|---|
| fitts1954information | Movement time grows with log2 of distance over width. Every click becomes a pointing trial (RQ-M2). |
| mackenzie1992fitts | The Shannon form ID = log2(D/W + 1) and direction-dependent target width used in `clicks.csv`. |
| wobbrock2008error | Endpoint spread depends on speed and target size: the basis for measuring aim scatter normalised by width. |
| morasso1981spatial | Aimed hand movements are near-straight with a single-peaked speed profile (straightness, peak position). |
| flash1985coordination | Minimum-jerk model: symmetric bell-shaped speed, peak at mid-movement. The analysis tests use it as a known-answer movement. |
| meyer1988optimality | Aimed movements are a primary submovement plus corrections; basis of the submovement count. |

## Cursor, gaze and reading

| Key | Used for |
|---|---|
| chen2001mouse | Early evidence that cursor and gaze correlate during web browsing (RQ-M4). |
| rodden2008eyemouse | Three cursor habits while reading results: following vertically, following horizontally, marking (RQ-M4; text selection as marking). |
| huang2012gaze | Gaze and cursor align only in some behaviours (reading, hesitating, scrolling, clicking). Why "reads with cursor" must be measured, not assumed. |
| lagun2016attention | Viewport time as a measure of attention in online reading (RQ-R1). |
| grusky2017viewport | Viewport-time attention models over 1.2 M news sessions, validated by recovering reading rate; the `ly` + `sc` + `iv` data allow its Gaussian model to be fitted (RQ-R1). |
| brysbaert2019reading | Meta-analysis of 190 studies: 238 wpm silent reading of non-fiction, slower in a second language. The comparison value for the fitted reading rate, and why the questionnaire asks about English. |

## Typing

| Key | Used for |
|---|---|
| killourhy2009keystroke | Keystroke dynamics benchmark (51 typists); hold and inter-key timing as behavioural features; the current `key_hold_ms` prior (RQ-K1). |
| dhakal2018typing | 136 M keystrokes from 168,000 volunteers: rollover is common and marks fast typists; hand alternation and inter-key intervals shape typing speed; 5 characters per word convention (RQ-K2, K4). |

## Activity over time

| Key | Used for |
|---|---|
| barabasi2005bursts | Human activity has bursts and heavy-tailed waiting times, unlike a fixed-rate process (RQ-E3). |
| goh2008burstiness | Burstiness B = (σ − m)/(σ + m) and memory M; human activity sits at high B, low M (RQ-E3). |
| nwala2023bloc | Behaviour as a sequence of action symbols (BLOC); the action string follows the idea with its own alphabet (RQ-E3). |

## Behavioural bot detection

| Key | Used for |
|---|---|
| ahmed2007mouse | Mouse dynamics as a behavioural biometric. Also why the traces are personal data (STUDY.md, ethics). |
| chu2013blog | Bots detected by passive mouse and keystroke biometrics on a real web application. |
| antal2021sapimouse | SapiMouse dataset (120 users), the export format of `export.mjs`, and the comparison for desktop-task kinematics. |
| iliou2021webbots | Web bots, including advanced ones that imitate humans, detected by mouse behaviour. |
| acien2022becaptcha | Synthetic human-like trajectories and their detection: why kinematics beyond straightness are needed. |

## Fingerprints and network

| Key | Used for |
|---|---|
| eckersley2010unique | Browser fingerprints are highly identifying. Why only within-session consistency of canvas is stored, not its hash. |
| laperdrix2016beauty | Modern fingerprint attributes and their correlations (RQ-H1). |
| gomezboix2018hiding | Two million fingerprints: far fewer unique than earlier studies found. Real attribute combinations cluster, which is what the fingerprint generator should sample from (RQ-H1). |
| laperdrix2020survey | Overview of fingerprinting attributes and defences. |
| venugopalan2024fpinconsistent | Inconsistency between attributes (page vs. worker, UA vs. platform) is the main signal anti-bot services use against evasive bots (RQ-H3). |
| jarad2026tls | TLS (JA4) fingerprints separate automated clients at the handshake (RQ-N1). |
| foxio_ja4 | The JA4 specification implemented in `server/tls-fingerprint.mjs`, and its test vectors. |

## Commercial detectors

| Key | Used for |
|---|---|
| google_recaptcha_v3 | What reCAPTCHA v3 returns (a score per action), and how tokens are verified. |
| akrout2019recaptcha | reCAPTCHA v3 was beaten by an RL agent moving the cursor: why its score is not ground truth. |
| searles2023captcha | Large-scale evaluation of modern CAPTCHAs; contested effectiveness. |
| fingerprintjs_botd | BotD, the in-page detector included in the snapshot. |

## Statistics and specifications

| Key | Used for |
|---|---|
| mann1947test | Rank test behind the AUC (RQ-V1). |
| hanley1982auc | AUC interpretation and its standard error, used for the sample-size guidance. |
| whatwg_dom | `isTrusted`: which events came from real input. |
| w3c_pointerevents3 | Coalesced samples, pressure values, pointer types. |
| ip_api | The network-type lookup for addresses. |
