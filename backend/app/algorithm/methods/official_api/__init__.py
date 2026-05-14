from .get_data import get_data
from .get_post import get_post
from .get_comments import get_comments
from .reply_comment import reply_comment
from .upvote_post import upvote_post
from .libraries import get_reddit_client


def build_context() -> dict:
    return {"reddit": get_reddit_client()}


__all__ = ["get_data", "get_post", "get_comments", "upvote_post", "reply_comment"]
