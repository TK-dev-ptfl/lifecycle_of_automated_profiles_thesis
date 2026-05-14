from .libraries import datetime


def get_post(source: str, limit: int = 25) -> dict:
    return {
        "provider": "headless_browser",
        "action": "get_post",
        "source": source,
        "limit": limit,
        "timestamp": datetime.utcnow().isoformat(),
    }
