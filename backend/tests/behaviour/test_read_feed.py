"""ReadFeed against a simulated feed.

What matters about reading a feed is not that the items come back - any scraper
does that - but the order things happen in: nothing is read before it has been
on screen, the page moves by wheel notches between reads, and a feed that stops
yielding posts ends the goal instead of being scrolled forever.
"""
from __future__ import annotations

import pytest

from app.behaviour.adapters.simulated import SimElement, SimulatedEnvironment
from app.behaviour.environment import Target
from app.behaviour.executor import Actor
from app.behaviour.goals import FeedSchema, ReadFeed
from app.behaviour.profile import AVERAGE

SCHEMA = FeedSchema(item=Target("post", "feed posts"), fields={"author": "author", "body": "body"})
POST_HEIGHT = 260


def feed(posts: int) -> SimulatedEnvironment:
    elements = [
        SimElement(
            f"post-{i}", x=380, y=80 + i * (POST_HEIGHT + 16), width=600, height=POST_HEIGHT,
            kind="text", group="post",
            fields={"author": f"author {i}", "body": f"post number {i} says a few words here"},
        )
        for i in range(posts)
    ]
    return SimulatedEnvironment(elements, page_height=80 + posts * (POST_HEIGHT + 16) + 400)


class Watching(Actor):
    """Records where each read post was on screen at the moment it was read."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.read_at: list[tuple[int, float]] = []

    async def _read_item(self, item):
        self.read_at.append((item.index, item.box.y))
        return await super()._read_item(item)


@pytest.mark.asyncio
async def test_reads_the_number_asked_for_in_feed_order():
    env = feed(20)
    actor = Actor(env=env, profile=AVERAGE)
    items = await actor.read_feed(ReadFeed(SCHEMA, want=6))

    assert [i["author"] for i in items] == [f"author {n}" for n in range(6)]
    assert actor.collected == items


@pytest.mark.asyncio
async def test_nothing_is_read_before_it_is_on_screen():
    env = feed(20)
    actor = Watching(env=env, profile=AVERAGE)
    await actor.read_feed(ReadFeed(SCHEMA, want=10))

    assert len(actor.read_at) == 10
    for _, y in actor.read_at:
        assert -POST_HEIGHT < y < env.height, "read a post that was off screen"


@pytest.mark.asyncio
async def test_the_page_moves_by_wheel_notches_between_reads():
    env = feed(20)
    await Actor(env=env, profile=AVERAGE).read_feed(ReadFeed(SCHEMA, want=10))

    scrolls = [e for e in env.events if e[0] == "scroll"]
    assert env.scroll_y > env.height, "ten tall posts cannot all fit on one screen"
    assert len(scrolls) > 5
    assert all(abs(e[1]) <= 130 for e in scrolls), "one notch at a time, never one jump"


@pytest.mark.asyncio
async def test_a_short_feed_ends_the_goal_instead_of_scrolling_forever():
    env = feed(4)
    items = await Actor(env=env, profile=AVERAGE).read_feed(ReadFeed(SCHEMA, want=50))

    assert len(items) == 4


@pytest.mark.asyncio
async def test_the_cursor_stays_on_screen_while_reading():
    env = feed(20)
    await Actor(env=env, profile=AVERAGE.with_(reads_with_cursor=0.5)).read_feed(
        ReadFeed(SCHEMA, want=10)
    )
    for x, y in env.path:
        assert 0 <= x <= env.width and 0 <= y <= env.height


@pytest.mark.asyncio
async def test_reading_a_long_post_takes_longer_than_a_short_one():
    async def time_to_read(body: str) -> float:
        env = SimulatedEnvironment([
            SimElement("p", x=380, y=100, width=600, height=200, kind="text", group="post",
                       fields={"author": "a", "body": body}),
        ])
        total = 0.0
        for _ in range(20):
            start = env.now()
            await Actor(env=env, profile=AVERAGE).read_feed(ReadFeed(SCHEMA, want=1))
            total += env.now() - start
        return total

    short = await time_to_read("ok")
    long = await time_to_read(" ".join(["word"] * 120))
    assert long > short * 3
