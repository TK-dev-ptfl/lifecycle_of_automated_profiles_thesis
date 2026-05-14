def reply_comment(context: dict, comment_id: str, text: str) -> dict:
    reddit = context["reddit"]
    try:
        comment = reddit.comment(id=comment_id)
        reply = comment.reply(text)
        return {
            "ok": True,
            "status_code": 200,
            "data": {"comment_id": comment_id, "reply_id": getattr(reply, "id", None)},
        }
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", 500)
        return {"ok": False, "status_code": int(status), "error": str(exc)}
