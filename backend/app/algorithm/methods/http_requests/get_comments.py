from .libraries import datetime


def get_comments(post_id: str, limit: int = 50, sort: str = "top") -> list[dict]:
    return [{
        "provider": "http_requests",
        "action": "get_comments",
        "post_id": post_id,
        "sort": sort,
        "limit": limit,
        "timestamp": datetime.utcnow().isoformat(),
    }]
