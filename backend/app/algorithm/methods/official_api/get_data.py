from .libraries import submission_to_dict


def get_data(context: dict, limit: int = 25, sort: str = "hot") -> dict:
    reddit = context["reddit"]
    try:
        listing_fn = getattr(reddit.front, sort)
    except AttributeError:
        return {"ok": False, "status_code": 400, "error": f"Unsupported feed sort: {sort}"}

    try:
        listing = listing_fn(limit=limit)
        data = [submission_to_dict(post) for post in listing]
        return {"ok": True, "status_code": 200, "data": data}
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", 500)
        return {"ok": False, "status_code": int(status), "error": str(exc)}
