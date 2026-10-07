"""An in-memory world: elements, a viewport, a scroll offset, a cursor, focus.

No browser, no network, and a virtual clock - so a run that includes two minutes
of human hesitation completes in microseconds, and every assertion is about what
actually happened rather than about what was called.

This is where the behaviour layer gets developed. A real page can tell you a
click "succeeded"; only a world you fully control can tell you the click landed
inside the element you meant, that the cursor path never left the viewport, that
the text went into the focused field, and that a careful profile really did take
longer than a brisk one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.behaviour.environment import Box, Observation, Point, Target


@dataclass
class SimElement:
    """One thing in the simulated world.

    Coordinates are in page space; the viewport scrolls over them, so an element
    below the fold has a viewport box that is off screen until scrolled to - which
    is what makes scroll-to-target behaviour testable at all.
    """

    name: str
    x: float
    y: float
    width: float
    height: float
    kind: str = "button"          # button | input | text
    value: str = ""               # for inputs: what has been typed
    text: str = ""
    clicks: int = 0
    page_box: Box = field(init=False)

    def __post_init__(self) -> None:
        self.page_box = Box(self.x, self.y, self.width, self.height)


class SimulatedEnvironment:
    """A minimal page you can reason about completely.

    Records every mouse, keyboard and scroll event, so a test can assert on the
    shape of the interaction (how the cursor got somewhere) as well as its outcome
    (what ended up clicked or typed).
    """

    def __init__(
        self,
        elements: Optional[list[SimElement]] = None,
        *,
        width: float = 1366,
        height: float = 900,
        page_height: float = 3000,
    ) -> None:
        self.elements = {e.name: e for e in (elements or [])}
        self.width = width
        self.height = height
        self.page_height = page_height

        self.scroll_y = 0.0
        self.cursor: Point = (0.0, 0.0)
        self.pressed = False
        self.focused: Optional[str] = None

        self.mouse = _SimMouse(self)
        self.keyboard = _SimKeyboard(self)

        # A virtual clock. Nothing here blocks, so an hour of simulated idling
        # costs nothing - and elapsed time is still measurable and assertable.
        self._clock = 0.0
        self.events: list[tuple] = []

    # --- Environment -------------------------------------------------------
    def viewport(self) -> Box:
        return Box(0, self.scroll_y, self.width, self.height)

    async def observe(self, target: Target) -> Observation:
        element = self.elements.get(target.query)
        if element is None:
            return Observation(exists=False)

        box = self.viewport_box_of(element)
        # Visible means "inside the viewport right now", which is the whole point
        # of modelling scroll: an element below the fold exists but cannot be
        # clicked until it is scrolled into view.
        visible = box.y + box.height > 0 and box.y < self.height
        return Observation(
            exists=True,
            visible=visible,
            box=box if visible else None,
            value=element.value,
            text=element.text,
            extra={"clicks": element.clicks, "kind": element.kind},
        )

    async def scroll_by(self, dy: float) -> None:
        self.scroll_y = max(0.0, min(self.page_height - self.height, self.scroll_y + dy))
        self.events.append(("scroll", dy, self.scroll_y))

    async def sleep(self, seconds: float) -> None:
        self._clock += max(0.0, seconds)

    def now(self) -> float:
        return self._clock

    # --- helpers for tests and adapters ------------------------------------
    def viewport_box_of(self, element: SimElement) -> Box:
        """An element's box in viewport coordinates, i.e. after scrolling."""
        return Box(element.x, element.y - self.scroll_y, element.width, element.height)

    def element_at(self, point: Point) -> Optional[SimElement]:
        """What a click at this viewport point would actually hit.

        Last match wins, mirroring how a later-painted element sits on top - so a
        click that lands on an overlapping element is attributed the way a real
        one would be.
        """
        hit = None
        for element in self.elements.values():
            if self.viewport_box_of(element).contains(point):
                hit = element
        return hit

    @property
    def path(self) -> list[Point]:
        return [(e[1], e[2]) for e in self.events if e[0] == "move"]

    @property
    def clicked(self) -> list[str]:
        return [e[1] for e in self.events if e[0] == "click"]

    @property
    def typed(self) -> list[tuple[str, str]]:
        return [(e[1], e[2]) for e in self.events if e[0] == "key"]


class _SimMouse:
    def __init__(self, env: SimulatedEnvironment) -> None:
        self.env = env

    async def move(self, x: float, y: float, *, steps: int = 1) -> None:
        self.env.cursor = (x, y)
        self.env.events.append(("move", x, y))

    async def down(self, **_kwargs) -> None:
        self.env.pressed = True
        self.env.events.append(("down", *self.env.cursor))

    async def up(self, **_kwargs) -> None:
        self.env.pressed = False
        element = self.env.element_at(self.env.cursor)
        self.env.events.append(("up", *self.env.cursor))
        if element is not None:
            element.clicks += 1
            # Releasing over an element is what focuses it, same as a real page -
            # which is how typing ends up in the right field without the
            # algorithm ever naming one.
            self.env.focused = element.name
            self.env.events.append(("click", element.name))
        else:
            self.env.events.append(("click", None))


class _SimKeyboard:
    def __init__(self, env: SimulatedEnvironment) -> None:
        self.env = env

    async def press(self, key: str, *, delay: Optional[float] = None) -> None:
        self.env.events.append(("key", self.env.focused, key))
        element = self.env.elements.get(self.env.focused or "")
        if element is None or element.kind != "input":
            return
        if key == "Backspace":
            element.value = element.value[:-1]
        elif len(key) == 1:
            element.value += key

    async def type(self, text: str, *, delay: Optional[float] = None) -> None:
        for char in text:
            await self.press(char)
