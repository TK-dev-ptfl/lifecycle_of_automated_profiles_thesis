"""Reddit account-creation pipeline.

    selectors.py  every Reddit DOM handle in one place - the parts most likely
                  to break when Reddit ships a UI change
    context.py    what a run carries between steps
    errors.py     step-named failures, so the dashboard says which step broke
    steps/        one module per step, importing only the context and the
                  behaviour layer - never each other
    pipeline.py   the step order, and the runner

How human the interaction looks is not decided here: that all comes from
app.behaviour, so a step reads as a statement of intent ("approach the signup
button and click it") and the mechanics of how a hand moves live in one place.
"""
from app.pipelines.reddit.pipeline import (
    PIPELINE_STEPS,
    RedditSignupResult,
    describe_pipeline,
    run_reddit_signup_pipeline,
)

__all__ = [
    "PIPELINE_STEPS",
    "RedditSignupResult",
    "describe_pipeline",
    "run_reddit_signup_pipeline",
]
