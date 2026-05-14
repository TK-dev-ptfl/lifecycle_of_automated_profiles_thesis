from .libraries import datetime


def reply_comment(comment_id: str, text: str) -> dict:
    return {
        "provider": "classical_browser",
        "action": "reply_comment",
        "comment_id": comment_id,
        "text": text,
        "timestamp": datetime.utcnow().isoformat(),
    }
