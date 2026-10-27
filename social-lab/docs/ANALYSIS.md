# Analysis: how every measurement is computed

`node analysis/analyze.mjs` turns raw sessions into `analysis/out/`.

| File | Content |
|---|---|
| `sessions.csv` | one row per session, all metrics below |
| `strokes.csv` | every aimed mouse movement |
| `clicks.csv` | every click as a Fitts trial |
| `posts.csv` | every post shown |
| `summary.md` | human reference ranges, automation-flag base rates, pooled fits, separation by cohort |

Definitions here match `analysis/metrics.mjs`; the tests in `test/metrics.test.mjs`
check them on synthetic sessions with known answers. Field codes refer to
[DATA_DICTIONARY.md](DATA_DICTIONARY.md); RQ numbers to [STUDY.md](STUDY.md).

A missing measurement is an empty cell, never 0. A session with no typing has no
`key_hold_ms`; it does not have a hold time of zero.

## Constants

| Constant | Value | Why |
|---|---|---|
| Stroke gap | 300 ms | A pause longer than this ends a movement. Same cut as the backend's mouse classifier, so strokes are comparable with its training data. |
| Minimum stroke | 40 px and 6 samples | Shorter movements are adjustments, not aimed movements. |
| Resampling grid | 16 ms | Speeds are computed on a fixed grid, so a 1000 Hz mouse and a 60 Hz event stream give comparable numbers. |
| Visible | ≥ 50 % of the post in the viewport | Common viewability threshold; a quarter-visible post is not being read. |
| Typing episode gap | 5 s | Longer gaps start a new episode (a new thought). |
| Inter-key interval cap | 3 s | Longer gaps are pauses, not keystroke intervals. |

## Session context

| Column | Definition |
|---|---|
| `cohort`, `run_label` | Ground-truth label (STUDY.md, cohorts). |
| `device_reported`, `hand`, `typing_style`, `english_l1`, `age`, `social_use`, `natural_rating` | Questionnaire answers. |
| `completed`, `tasks_done` | Reached the end; number of the six tasks done. |
| `free_phase_s`, `task_phase_s` | Phase durations from `ph` events. |
| `hidden_share` | Hidden-tab time / session time, from `vs`. |
| `tab_switches` | Number of times the tab became hidden. |
| `text_selections` | `se` events with a non-empty selection. |

## Pointer: RQ-M1, kinematics (`strokes.csv`, `stroke_*`)

**Samples.** Trusted mouse `pm` events. When an event carries coalesced samples, those
are used instead, i.e. the device's own rate.

**Strokes.** Cut at the 300 ms gap; kept only if ≥ 6 samples and ≥ 40 px from start to
end.

For each stroke, speeds v_i are computed on the path linearly resampled to 16 ms:

| Column | Definition |
|---|---|
| `duration_ms` | last − first sample time |
| `distance_px` | straight-line distance from start to end |
| `path_px` | sum of sample-to-sample distances |
| `straightness` | distance / path; 1 = ruler-straight |
| `peak_speed`, `mean_speed` | max and mean of v (px/ms) |
| `speed_cv` | standard deviation / mean of v. Near 0 for constant-speed scripted motion. |
| `peak_position` | index of the peak / (n − 1). Minimum-jerk movement peaks at 0.5 [flash1985coordination]. |
| `end_speed_ratio` | mean v over the last 10 % / peak. Near 0 when the hand decelerates into a target; high when the motion just stops. |
| `submovements` | Speed maxima (on a 1-2-1 smoothed profile) above 20 % of the peak, each separated from the previous one by a dip below 70 % of the smaller maximum; at least 1. A primary movement plus corrections [meyer1988optimality]. |
| `turn_mean` | mean absolute heading change between consecutive samples ≥ 1 px apart (radians) |

Session columns `stroke_*` are the medians over that session's strokes.

## Pointer: RQ-M2 and M3, clicks (`clicks.csv`, `click_*`, `fitts_*`)

Every trusted left-button mouse `pd` is a trial.

| Column | Definition |
|---|---|
| `press_ms` | next `pu` of the same button − `pd` |
| `hovered_first` | an `ho` event naming the same target kind occurred between the previous press and this one |
| `moved` | a stroke ended within 1.5 s before the press. False = the click had no preceding movement. |
| `D` | distance from the stroke's start to the target centre |
| `W` | target extent along the approach direction u: \|u_x\|·w + \|u_y\|·h (direction-dependent width [mackenzie1992fitts]) |
| `ID` | log2(D / W + 1) bits (Shannon formulation) |
| `MT` | press time − stroke start (ms) |
| `along`, `across` | press point − target centre, projected on u and its normal, divided by W and by the perpendicular extent. Their standard deviations are the endpoint spread [wobbrock2008error]. |
| `overshoot` | the cursor's furthest projection along u exceeded D + W/2 + 2 px before the press |
| `settle_ms` | press time − the moment the cursor last entered the target and stayed in it |

Session columns:
- `click_press_ms` (median), `click_press_cv`, `click_settle_ms`;
- `click_hovered_share`, `click_overshoot_share`, `click_without_movement_share`;
- `endpoint_along_sd`, `endpoint_across_sd`;
- `fitts_a_ms`, `fitts_b_ms_per_bit`, `fitts_r2`: ordinary least squares MT = a + b·ID over trials with D ≥ 2W (shorter "movements" are corrections, not pointing);
- `throughput_bits_s`: mean of ID / MT(s).

`summary.md` also fits MT on ID pooled over all human clicks.

## Pointer: RQ-M4, the idle hand

`restlessness`: the session from phase 1 onwards is cut into 1 s windows. Windows
overlapping hidden time, or within 1 s of any press, are dropped. The value is the
share of the remaining windows containing at least one mouse sample. This is the
quantity `BehaviourProfile.restlessness` models. `idle_windows` is the denominator.

## Pointer: RQ-M5, devices and sampling (in the hardware block)

| Column | Definition |
|---|---|
| `coalesced_share` | share of mouse `pm` events carrying ≥ 2 coalesced samples |
| `report_rate_hz` | median over those events of (samples − 1) / their time span |

## Keyboard: RQ-K1 to K4 (`key_*`, `iki_*`, …)

Only trusted, non-repeat `kd` in the site's text fields count. Each `kd` is paired with
the next `ku` of the same key slot.

| Column | Definition |
|---|---|
| `keys` | number of key presses |
| `key_hold_ms`, `key_hold_p10`, `key_hold_p90`, `key_hold_cv` | median, 10th and 90th percentile, and CV of hold times (ku − kd) [killourhy2009keystroke] |
| `iki_ms`, `iki_cv` | median and CV of keydown-to-keydown intervals between consecutive keys in the same field, ≤ 3 s |
| `iki_word_start_ms` | median interval from a space to the following letter |
| `iki_in_word_ms` | median interval between two letters |
| `iki_same_hand_ms`, `iki_other_hand_ms` | letter–letter intervals where both keys belong to the same hand vs. different hands [dhakal2018typing] |
| `rollover_rate` | share of consecutive pairs where the second key went down before the first came up [dhakal2018typing] |
| `backspace_rate` | backspace presses / all presses |
| `wpm` | (letters + digits + spaces + punctuation) / 5 per minute of typing-episode time. Five characters per word is the convention [dhakal2018typing]. |
| `pre_typing_ms` | median, over episodes, of first key − the last press on that field within 30 s before |
| `insert_vs_keys` | characters inserted (`in`) / character keys pressed. 1 for typing; above 1 means text arrived without keys. |
| `pasted` | any paste |

## Scrolling: RQ-S1 and S2

| Column | Definition |
|---|---|
| `wheel_events` | trusted `wh` events |
| `wheel_delta_mode` | median deltaMode (0 pixels, 1 lines, 2 pages) |
| `wheel_dy_mode`, `wheel_dy_mode_share` | most common \|deltaY\| and its share. A mouse wheel gives one dominant value; a trackpad does not. |
| `wheel_small_share` | share of \|deltaY\| < 20 px (trackpad-like) |
| `wheel_burst_notches` | median events per burst (bursts cut at 300 ms) |
| `wheel_intra_ms`, `wheel_intra_cv` | median and CV of intervals within bursts |
| `scroll_px` | total absolute scroll distance |
| `reading_pauses`, `reading_pause_ms` | number and median length of gaps > 1 s between `sc` events, not overlapping hidden time |
| `scroll_speed_px_s` | median speed between `sc` events ≤ 200 ms apart |
| `scroll_non_wheel_share` | share of `sc` events with no wheel event in the 250 ms before: scrollbar, keys, touch, or script |

## Reading and engagement: RQ-R1, R2, E1, E2 (`posts.csv`)

**Viewport time** `vt_ms` of a post is the total time its visible share (`iv`) was
≥ 0.5, counted only:
- **during phase 1** (free browsing);
- outside hidden-tab intervals;
- outside the times the profile overlay covered the feed (`profile_open` →
  `profile_close`).

Phase 2 is excluded because people work at the top of the feed there: the first posts
stay on screen for minutes while tasks are done, and counting that would turn task
time into "reading". Own posts and posts inside a profile are excluded.
First-visible times and actions come from the whole session, so `like_latency_ms`
covers both phases.

| Column | Definition |
|---|---|
| `posts_seen` | posts that reached ≥ 50 % visible |
| `vt_median_ms` | median viewport time of seen posts |
| `skim_share` | share of seen posts with viewport time < 1 s |
| `read_fit_s_per_word`, `read_fit_intercept_s`, `read_fit_r2`, `read_fit_n` | OLS of viewport time (s) on word count over seen text-only posts with 1 s ≤ vt ≤ 120 s [grusky2017viewport]. 60 / slope is words per minute; compare with 238 wpm [brysbaert2019reading]. The intercept is the base glance time. |
| `implied_wpm` | median of words / vt (min) over those posts with ≥ 15 words |
| `media_vt_ratio` | median vt of seen image posts / median vt of seen text posts |
| `like_latency_ms` | median of (like time − first time the post was ≥ 50 % visible) |
| `liked_words_median`, `seen_words_median`, `liked_index_median` | what was liked vs. what was seen |

## Session rhythm: RQ-E3 and E4

Social actions are `act` events of type like, repost, save, share, comment_submit,
post_submit, follow, profile_open, comments_open and media_click.

| Column | Definition |
|---|---|
| `actions`, `free_actions`, `free_actions_per_min` | counts, all and in phase 1 |
| `spontaneous_engagement` | any like, repost, comment, post or follow in phase 1 |
| `action_gap_ms` | median interval between actions |
| `burstiness` | B = (σ − m)/(σ + m) of action intervals: −1 periodic, 0 random, → 1 bursty [goh2008burstiness] |
| `memory` | M, the correlation between consecutive intervals [goh2008burstiness] |
| `action_string` | one letter per action: L like, R repost, S save, H share, C comment, P post, F follow, V profile view, O comments opened, M image. Separators give the pause before the action: none < 2 s, `.` < 10 s, `:` < 60 s, `|` longer. A BLOC-style sequence [nwala2023bloc] with this study's own alphabet. |

## Hardware: RQ-H1 to H3

`os`, `browser`, `browser_major` are parsed from the UA. `screen`, `dpr`, `cores`,
`memory_gb`, `languages`, `timezone`, `pointer_fine` and `touch_points` are copied from
the snapshot. Derived:

| Column | Definition |
|---|---|
| `gpu_vendor` | first of NVIDIA/AMD/Radeon/Intel/Apple/Adreno/Mali/SwiftShader/llvmpipe found in the WebGL renderer |
| `refresh_hz` | 1000 / median of the `fr` medians, rounded |
| `consistency_failures` | names of the failed checks: `worker_<attr>`, `shared_worker_<attr>`, `iframe_<attr>`, `canvas_unstable`, `permission_mismatch` |
| `webdriver`, `headless_ua`, `automation_leftovers`, `tampered_builtins`, `botd_bot` | from the snapshot |

## Network: RQ-N1 to N4

| Column | Definition |
|---|---|
| `ja4`, `ja3` | from the TLS record |
| `header_order` | lower-cased navigation header names, comma-joined |
| `accept_language` | the Accept-Language value |
| `ip_country`, `ip_asn`, `ip_hosting`, `ip_proxy`, `ip_mobile` | network type of the address |
| `tz_matches_ip` | browser time zone = the IP's time zone |
| `webrtc_matches` | WebRTC's address = the request's |
| `rtt_ms`, `clock_offset_ms` | medians of `net` |

## Commercial detectors: RQ-X1

`recaptcha_n`, `recaptcha_mean`, `recaptcha_min`: number, mean and minimum of
successful scores.

## Automation flags (`hard_flags`)

These are signals that are evidence of automation on their own, whatever the behaviour
looks like. They are listed, not weighted into a score.

| Flag | Fires when |
|---|---|
| `untrusted_events` | any untrusted input event |
| `webdriver`, `headless_ua`, `automation_globals`, `tampered_builtins`, `botd` | from the snapshot |
| `fingerprint_inconsistent` | any consistency failure |
| `no_coalesced_samples` | ≥ 200 mouse moves on a fine-pointer device, none with coalesced samples |
| `screen_equals_client` | every mouse press had screen offset 0 while the window has chrome (outer − inner height > 30) |
| `mouse_without_pointer_events` | > 50 mousemove events and no pointermove |

Their rate among humans is RQ-H3, reported in `summary.md`. Some, like
`fingerprint_inconsistent` and `no_coalesced_samples`, are expected to fire for some
real people (privacy extensions, trackpads), and the point is to measure how often.

## Cohort comparison: RQ-V1 (`summary.md`)

- **Human reference.** Finished `cohort=human` sessions, restricted by default to
  reported device `mouse` (`--device any` to include all).
- **Ranges.** For each numeric metric: n, median, IQR, 5th–95th percentile (type-7
  quantiles).
- **Pooled fits.** Fitts' law over all human clicks with D ≥ 2W; viewport time on
  words over all human text posts.
- **Separation.** For each other cohort and each metric, the Mann–Whitney AUC against
  the human reference [mann1947test; hanley1982auc]. Sorted by distance from 0.5;
  either direction counts.
- **Outside-range share** (`outside_human_share` in `sessions.csv`). The share of a
  session's metrics outside the human 2.5–97.5 % range. Computed only for metrics
  with ≥ 10 human values; humans are scored leave-one-out. Roughly 5 % for a human
  by construction.
