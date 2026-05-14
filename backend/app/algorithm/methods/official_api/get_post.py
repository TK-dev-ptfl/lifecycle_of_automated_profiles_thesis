from .libraries import submission_to_dict


def get_post(context: dict, post_id: str) -> dict:
    reddit = context["reddit"]
    try:
        submission = reddit.submission(id=post_id)
        data = submission_to_dict(submission)
        return {"ok": True, "status_code": 200, "data": data}
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", 500)
        return {"ok": False, "status_code": int(status), "error": str(exc)}
