def upvote_post(context: dict, post_id: str) -> dict:
    reddit = context["reddit"]
    try:
        submission = reddit.submission(id=post_id)
        submission.upvote()
        return {"ok": True, "status_code": 200, "data": {"post_id": post_id, "upvoted": True}}
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", 500)
        return {"ok": False, "status_code": int(status), "error": str(exc)}
