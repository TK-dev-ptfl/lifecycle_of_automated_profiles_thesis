from .libraries import datetime


def get_data(source: str, limit: int = 25) -> dict:
    return {
        "provider": "http_requests",
        "action": "get_data",
        "source": source,
        "limit": limit,
        "timestamp": datetime.utcnow().isoformat(),
    }
