from .libraries import datetime


def get_data(source: str, limit: int = 25) -> dict:
    return {
        "provider": "headless_browser",
        "action": "get_data",
        "source": source,
        "limit": limit,
        "timestamp": datetime.utcnow().isoformat(),
    }
