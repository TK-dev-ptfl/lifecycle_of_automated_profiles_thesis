def get_comments(context: dict, post_id: str, limit: int = 50, sort: str = "top") -> list[dict]:
    reddit = context["reddit"]
    try:
        submission = reddit.submission(id=post_id)
        submission.comment_sort = sort
        submission.comments.replace_more(limit=0)

        comments = []
        for comment in submission.comments.list()[:limit]:
            comments.append(
                {
                    "id": comment.id,
                    "author": str(comment.author) if comment.author else None,
                    "body": comment.body,
                    "score": comment.score,
                    "created_utc": comment.created_utc,
                }
            )
        return {"ok": True, "status_code": 200, "data": comments}
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", 500)
        return {"ok": False, "status_code": int(status), "error": str(exc)}
