"""The narrow slices of Playwright the behaviour primitives actually need.

Primitives depend on these instead of on playwright.Page, which is what makes
them testable: a test passes a recorder implementing the same three or four
methods and then asserts on the sequence of calls. Playwright's real Mouse,
Keyboard and Page satisfy these structurally - nothing has to be registered or
adapted.

Kept deliberately minimal. Every method added here is one a fake has to
implement, so the cost of a wide protocol lands on every test.
"""
from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class MouseLike(Protocol):
    async def move(self, x: float, y: float, *, steps: int = 1) -> None: ...
    async def down(self, **kwargs: Any) -> None: ...
    async def up(self, **kwargs: Any) -> None: ...


@runtime_checkable
class KeyboardLike(Protocol):
    async def type(self, text: str, *, delay: Optional[float] = None) -> None: ...
    async def press(self, key: str, *, delay: Optional[float] = None) -> None: ...


@runtime_checkable
class ViewportPageLike(Protocol):
    """A page the behaviour layer can steer a cursor around.

    viewport_size is a property on Playwright's Page, and `mouse`/`keyboard` are
    attributes rather than methods - declared here as such so a fake looks the
    same shape.
    """

    mouse: MouseLike
    keyboard: KeyboardLike

    @property
    def viewport_size(self) -> Optional[dict]: ...

    async def evaluate(self, expression: str, arg: Any = None) -> Any: ...
