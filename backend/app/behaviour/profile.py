"""The variables: what makes one simulated person move differently from another.

Everything in the behaviour layer that could be a magic number lives here
instead, as a field on a profile. Algorithms read a profile and pass concrete
numbers down to the primitives, which stay dumb - that way the primitives remain
individually testable with explicit arguments, and "how human does this feel" is
one object you can swap, persist, or derive per identity.

Why per identity and not global: a fleet whose every member moves at exactly the
same speed, pauses for exactly as long and misses targets by exactly as much is a
fleet with one fingerprint. derive_for() turns an identity id into a stable,
distinct profile, so the same account behaves consistently across sessions while
differing from its siblings.
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class BehaviourProfile:
    """One person's motor and attention characteristics.

    Frozen so a profile can't drift mid-session: a bot that gets faster as a run
    goes on is a bot whose timing is a function of the run, not of the person.
    """

    # --- motor ---------------------------------------------------------------
    # Words per minute, at the conventional five characters per word.
    typing_wpm: float = 48.0
    # Per-character chance of hitting a neighbouring key and correcting it.
    typo_chance: float = 0.0
    # How far a click may land from an element's centre, as a fraction of its
    # size. 0 would mean pixel-perfect centre clicks every time, which is a
    # stronger signal than any amount of jitter.
    aim_scatter: float = 0.34
    # How much a travel path bows away from the straight line.
    path_curviness: float = 0.22
    # Chance of flying past a distant target and correcting back.
    overshoot_chance: float = 0.75

    # --- attention -----------------------------------------------------------
    # Multiplier on every deliberate pause. 0.5 is brisk and familiar with the
    # page; 2.0 is distracted or reading carefully.
    hesitancy: float = 1.0
    # Idle gestures before committing to an action, as an inclusive range.
    wander_range: tuple[int, int] = (2, 4)
    # Seconds to keep waiting for something expected to appear.
    patience_s: float = 20.0

    # --- derived helpers -----------------------------------------------------
    def think_s(self) -> float:
        """Median pause before a deliberate action."""
        return 0.55 * self.hesitancy

    def read_s(self) -> float:
        """Median pause on seeing something new."""
        return 2.2 * self.hesitancy

    def settle_s(self) -> float:
        """Median pause around a button press - arrival, hold, release."""
        return 0.08 * self.hesitancy

    def with_(self, **changes) -> "BehaviourProfile":
        """A copy with some fields changed, for a one-off adjustment without
        mutating a shared profile."""
        return replace(self, **changes)


# Presets, as starting points rather than a taxonomy. A real fleet should use
# derive_for() so no two members are identical.
BRISK = BehaviourProfile(
    typing_wpm=72.0, hesitancy=0.55, wander_range=(1, 2), aim_scatter=0.28, typo_chance=0.0,
)
AVERAGE = BehaviourProfile()
CAREFUL = BehaviourProfile(
    typing_wpm=34.0, hesitancy=1.7, wander_range=(3, 6), aim_scatter=0.38, typo_chance=0.02,
)


def derive_for(identity_key: str, base: BehaviourProfile = AVERAGE) -> BehaviourProfile:
    """A stable, distinct profile for one identity.

    Seeded from a hash of the identity's key, so the same identity always gets
    the same profile - its behaviour is consistent across sessions, the way a
    person's is - while two identities get meaningfully different ones. Using the
    key rather than a random seed is what makes that reproducible: a run can be
    replayed, and a profile never has to be stored.

    The spread is deliberately wide on the motor traits (people differ a lot in
    typing speed and precision) and narrower on patience, which is more about the
    situation than the person.
    """
    digest = hashlib.sha256(identity_key.encode("utf-8")).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))

    return base.with_(
        typing_wpm=max(18.0, rng.gauss(base.typing_wpm, base.typing_wpm * 0.3)),
        typo_chance=max(0.0, min(0.06, rng.gauss(0.015, 0.012))),
        aim_scatter=min(0.45, max(0.15, rng.gauss(base.aim_scatter, 0.07))),
        path_curviness=min(0.4, max(0.08, rng.gauss(base.path_curviness, 0.07))),
        overshoot_chance=min(1.0, max(0.3, rng.gauss(base.overshoot_chance, 0.15))),
        hesitancy=min(2.5, max(0.4, rng.gauss(base.hesitancy, 0.35))),
        wander_range=_jitter_range(base.wander_range, rng),
        patience_s=max(8.0, rng.gauss(base.patience_s, 4.0)),
    )


def _jitter_range(base: tuple[int, int], rng: random.Random) -> tuple[int, int]:
    low = max(0, base[0] + rng.choice((-1, 0, 0, 1)))
    high = max(low, base[1] + rng.choice((-1, 0, 1, 1)))
    return (low, high)
