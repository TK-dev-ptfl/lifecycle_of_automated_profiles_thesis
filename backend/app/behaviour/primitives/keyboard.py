"""Typing primitives.

Playwright's `type(delay=N)` uses one fixed gap for every keystroke, which is
flat where real typing is not. These produce a per-key rhythm instead, and can
make the kind of mistake a person makes.
"""
from __future__ import annotations

import random

from app.behaviour.primitives.timing import Sleeper, _real_sleep, keystroke_delay_ms, keystroke_hold_ms, pause
from app.behaviour.protocols import KeyboardLike

# Keys adjacent on a QWERTY board. A plausible typo is a neighbouring key, not a
# random letter - "gmaik" happens, "gmaiq" does not.
_NEIGHBOURS = {
    "a": "qwsz", "b": "vghn", "c": "xdfv", "d": "serfcx", "e": "wsdr",
    "f": "drtgvc", "g": "ftyhbv", "h": "gyujnb", "i": "ujko", "j": "huikmn",
    "k": "jiolm", "l": "kop", "m": "njk", "n": "bhjm", "o": "iklp",
    "p": "ol", "q": "wa", "r": "edft", "s": "awedxz", "t": "rfgy",
    "u": "yhji", "v": "cfgb", "w": "qase", "x": "zsdc", "y": "tghu",
    "z": "asx",
}


async def type_text(
    keyboard: KeyboardLike,
    text: str,
    *,
    words_per_minute: float = 48.0,
    typo_chance: float = 0.0,
    hold_ms: float = 86.0,
    sleeper: Sleeper = _real_sleep,
) -> list[str]:
    """Types `text` one key at a time with a per-key delay, returning the exact
    key sequence sent - including any typo and its correction, which is what
    makes the behaviour assertable in a test.

    typo_chance is per character. Default 0 because it is not always wanted: in a
    field with inline validation (an email that gets checked as you type) a
    transient wrong value can trip a real error state, so the caller decides.

    hold_ms is the median time each key stays down (see keystroke_hold_ms).
    The hold is part of the gap to the next key, not added to it, so the
    typing speed stays what words_per_minute says.
    """
    sent: list[str] = []

    async def stroke(key: str) -> None:
        hold = keystroke_hold_ms(hold_ms)
        gap = keystroke_delay_ms(words_per_minute)
        await keyboard.press(key, delay=hold)
        sent.append(key)
        await sleeper(max(0.0, gap - hold) / 1000.0)

    for char in text:
        if typo_chance and char.lower() in _NEIGHBOURS and random.random() < typo_chance:
            wrong = random.choice(_NEIGHBOURS[char.lower()])
            if char.isupper():
                wrong = wrong.upper()
            await stroke(wrong)
            # Noticing and fixing it takes longer than a normal keystroke.
            await pause(0.3, spread=0.4, cap_s=1.5, sleeper=sleeper)
            await stroke("Backspace")

        await stroke(char)
    return sent
