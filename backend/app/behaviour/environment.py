"""The world an algorithm acts in, as a port rather than a browser.

An algorithm should be able to say "go to the thing described by this target and
click it" without knowing whether the thing is a DOM node, a canvas region, a
native control, or a rectangle in a test fixture. That is what this file defines:
the smallest surface an algorithm needs, and nothing else.

Two implementations ship in adapters/:
  - SimulatedEnvironment  an in-memory world. No browser, no network, instant.
    Everything can be developed and tested against it.
  - PlaywrightEnvironment a real page.

Because both satisfy the same protocol, moving an algorithm from the simulator to
a real site is a matter of passing a different Environment - plus the variables
(a BehaviourProfile) and the goals. Nothing in the algorithm changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Protocol, runtime_checkable

from app.behaviour.protocols import KeyboardLike, MouseLike

Point = tuple[float, float]


@dataclass(frozen=True)
class Target:
    """A description of something to act on, in whatever language the environment
    speaks.

    `query` is opaque here on purpose: the Playwright adapter reads it as a CSS
    selector, the simulator reads it as an element name, and a future adapter can
    read it as anything it likes. Keeping it opaque is what stops selector syntax
    leaking into the algorithms.

    `description` is for logs, so a trace reads "the signup button" rather than
    "#signup-button".
    """

    query: str
    description: str = ""

    def __str__(self) -> str:
        return self.description or self.query


@dataclass
class Box:
    """An axis-aligned rectangle in viewport coordinates - the one geometric fact
    an algorithm needs about a target in order to aim at it."""

    x: float
    y: float
    width: float
    height: float

    @property
    def centre(self) -> Point:
        return (self.x + self.width / 2, self.y + self.height / 2)

    def contains(self, point: Point) -> bool:
        px, py = point
        return self.x <= px <= self.x + self.width and self.y <= py <= self.y + self.height

    def as_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass
class Observation:
    """What an environment can say about a target right now."""

    exists: bool
    visible: bool = False
    box: Optional[Box] = None
    value: str = ""
    text: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def actionable(self) -> bool:
        """Present, on screen, and laid out. All three matter: an element that is
        visible to the accessibility tree but has no box cannot be aimed at, and
        clicking its coordinates would hit whatever is underneath."""
        return self.exists and self.visible and self.box is not None


@dataclass
class CollectedItem:
    """One member of a repeated structure - a post in a feed, a row in a table -
    with its fields already read.

    `index` is its position among its siblings, which is how a caller refers to
    it again without holding an element handle that may go stale on the next
    render.
    """

    index: int
    box: Optional[Box]
    fields: dict[str, str] = field(default_factory=dict)

    @property
    def visible(self) -> bool:
        return self.box is not None

    def key(self) -> str:
        """A stable identity for deduplication while scrolling.

        Built from the field values rather than the index, because the index of a
        given post changes as a feed loads more above it - counting positions
        would re-read the same post forever or skip ones that shifted.
        """
        return "|".join(f"{k}={self.fields.get(k, '')}" for k in sorted(self.fields))


@runtime_checkable
class Environment(Protocol):
    """Everything the behaviour layer is allowed to know about the outside world."""

    mouse: MouseLike
    keyboard: KeyboardLike

    def viewport(self) -> Box:
        """The visible region, in its own coordinates."""

    async def observe(self, target: Target) -> Observation:
        """Look at a target without touching it."""

    async def scroll_by(self, dy: float) -> None:
        """Scroll the view vertically by dy pixels."""

    async def sleep(self, seconds: float) -> None:
        """Wait. A real environment sleeps; a simulated one advances a clock, so
        a test can exercise minutes of hesitation instantly."""

    def now(self) -> float:
        """Seconds since this environment started, on whatever clock it keeps."""

    async def collect(
        self, target: Target, fields: Mapping[str, str]
    ) -> list["CollectedItem"]:
        """Every match of `target`, with `fields` read from inside each one.

        The one thing observe() cannot express: a feed is a repeated structure,
        and reading it means looking at many siblings and pulling the same few
        things out of each. `fields` maps a name the algorithm uses ("author",
        "body") to a query the environment understands - which keeps the
        algorithm free of any particular site's markup while still letting it ask
        for exactly what it wants.
        """
