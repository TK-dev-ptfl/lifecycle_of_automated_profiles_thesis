from .libraries import datetime


def get_post(source: str, limit: int = 25) -> dict:
    return {
        "provider": "unofficial_api",
        "action": "get_post",
        "source": source,
        "limit": limit,
        "timestamp": datetime.utcnow().isoformat(),
    }
