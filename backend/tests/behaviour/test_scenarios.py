"""The robotic scenario is a control: it must differ from the human one in how
the page is driven and in nothing else, or a score difference means nothing."""
from __future__ import annotations

from app.services.behaviour_run_service import SCENARIOS


def test_the_robotic_control_differs_from_the_human_run_only_in_style():
    human, robot = SCENARIOS["feed-lab"], SCENARIOS["feed-lab-bot"]
    assert (human.style, robot.style) == ("human", "robotic")
    assert robot.url == human.url
    assert robot.schema is human.schema
    assert robot.score_js == human.score_js


def test_the_human_like_run_performs_the_whole_task_not_just_reading():
    """If the human-like run never clicks or types, the lab's click and
    keystroke checks stay 'pending' for it while the robotic control is graded
    on them - and the comparison favours the algorithm for free."""
    from app.behaviour.goals import ClickOn, TypeInto
    from app.services.behaviour_run_service import FEED_TASK, feed_task_goals

    goals = feed_task_goals(8, FEED_TASK)
    likes = [g for g in goals if isinstance(g, ClickOn) and ".act.like" in g.target.query]
    typed = [g.text for g in goals if isinstance(g, TypeInto)]
    assert len(likes) == FEED_TASK.likes
    assert typed == [FEED_TASK.comment, FEED_TASK.post]
    assert any(isinstance(g, ClickOn) and g.target.query == "#postBtn" for g in goals)
    assert feed_task_goals(0, FEED_TASK) == []


def test_every_click_and_field_in_the_task_is_scrolled_to_first():
    """In a real browser an element below the fold still counts as visible, so
    nothing stops a click aimed off screen except a ScrollTo before it. Opening
    the comments pushes the field down; without this the comment was typed into
    nothing on a short viewport."""
    from app.behaviour.goals import ClickOn, ScrollTo, TypeInto
    from app.services.behaviour_run_service import FEED_TASK, feed_task_goals

    goals = feed_task_goals(8, FEED_TASK)
    for i, goal in enumerate(goals):
        if isinstance(goal, (ClickOn, TypeInto)):
            before = [g for g in goals[:i] if isinstance(g, ScrollTo) and g.target.query == goal.target.query]
            assert before, f"{goal.target} is acted on without being scrolled to"
