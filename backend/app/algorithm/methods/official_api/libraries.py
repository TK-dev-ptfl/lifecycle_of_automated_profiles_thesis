"""Centralized imports and client init for official_api methods."""

from __future__ import annotations

from .credentials import (
    REDDIT_CLIENT_ID,
    REDDIT_CLIENT_SECRET,
    REDDIT_PASSWORD,
    REDDIT_REFRESH_TOKEN,
    REDDIT_USER_AGENT,
    REDDIT_USERNAME,
)


def get_reddit_client():
    try:
        import praw
    except ImportError as exc:
        raise RuntimeError("praw is required for official_api methods. Install dependencies from backend/requirements.txt.") from exc

    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET or not REDDIT_USER_AGENT:
        raise ValueError(
            "Missing Reddit credentials. Set REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, and REDDIT_USER_AGENT."
        )

    auth_kwargs = {}
    if REDDIT_REFRESH_TOKEN:
        auth_kwargs["refresh_token"] = REDDIT_REFRESH_TOKEN
    elif REDDIT_USERNAME and REDDIT_PASSWORD:
        auth_kwargs["username"] = REDDIT_USERNAME
        auth_kwargs["password"] = REDDIT_PASSWORD

    return praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        user_agent=REDDIT_USER_AGENT,
        **auth_kwargs,
    )


def submission_to_dict(submission) -> dict:
    return {
        "id": submission.id,
        "title": submission.title,
        "author": str(submission.author) if submission.author else None,
        "score": submission.score,
        "url": submission.url,
        "selftext": submission.selftext,
        "num_comments": submission.num_comments,
        "subreddit": str(submission.subreddit),
        "permalink": submission.permalink,
    }
