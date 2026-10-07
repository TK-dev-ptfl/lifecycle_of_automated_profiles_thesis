"""Fakes that record what a behaviour primitive did, instead of doing it.

This is what makes the primitives atomically testable: they take the protocols in
app.behaviour.protocols, so a test can pass one of these and then assert on the
exact sequence produced - how many points a path has, that it is not a straight
line, that a press was held, that keystroke gaps vary. None of that is observable
from watching a real browser, and all of it is what separates human-looking input
from the kind that gets flagged.

Sleeps are recorded rather than performed, so a test that exercises three seconds
of human hesitation runs in microseconds.
"""
from __future__ import annotations

from typing import Any, Optional


class RecordingMouse:
    """Records moves, presses and releases in order."""

    def __init__(self) -> None:
        self.events: list[tuple] = []

    async def move(self, x: float, y: float, *, steps: int = 1) -> None:
        self.events.append(("move", x, y))

    async def down(self, **kwargs: Any) -> None:
        self.events.append(("down",))

    async def up(self, **kwargs: Any) -> None:
        self.events.append(("up",))

    @property
    def path(self) -> list[tuple[float, float]]:
        return [(e[1], e[2]) for e in self.events if e[0] == "move"]

    @property
    def kinds(self) -> list[str]:
        return [e[0] for e in self.events]


class RecordingKeyboard:
    def __init__(self) -> None:
        self.pressed: list[str] = []
        self.typed: list[str] = []

    async def press(self, key: str, *, delay: Optional[float] = None) -> None:
        self.pressed.append(key)

    async def type(self, text: str, *, delay: Optional[float] = None) -> None:
        self.typed.append(text)


class RecordingPage:
    """Enough of a Page for the behaviour layer: a mouse, a keyboard, a viewport
    and evaluate() for scrolling."""

    def __init__(self, width: int = 1366, height: int = 900) -> None:
        self.mouse = RecordingMouse()
        self.keyboard = RecordingKeyboard()
        self._size = {"width": width, "height": height}
        self.evaluated: list[tuple[str, Any]] = []

    @property
    def viewport_size(self) -> Optional[dict]:
        return dict(self._size)

    async def evaluate(self, expression: str, arg: Any = None) -> Any:
        self.evaluated.append((expression, arg))
        return None


class RecordingSleeper:
    """Collects every requested sleep without waiting, so timing behaviour is
    assertable and the suite stays fast."""

    def __init__(self) -> None:
        self.waits: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)

    @property
    def total(self) -> float:
        return sum(self.waits)
