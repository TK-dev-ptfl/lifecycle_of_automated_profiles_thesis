from .libraries import datetime


def upvote_post(post_id: str) -> dict:
    return {
        "provider": "http_requests",
        "action": "upvote_post",
        "post_id": post_id,
        "upvoted": True,
        "timestamp": datetime.utcnow().isoformat(),
    }
