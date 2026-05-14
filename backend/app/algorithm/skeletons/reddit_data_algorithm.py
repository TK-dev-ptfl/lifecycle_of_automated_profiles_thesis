from app.algorithm.methods import MethodWrapper


class RedditDataAlgorithm:
    """Example algorithm that composes provider-specific methods via wrapper."""

    def __init__(self, method_type: str = "official"):
        self.actions = MethodWrapper(method_type)

    def run(self, limit: int = 10) -> dict:
        feed_response = self.actions.get_data(limit=limit)
        return {
            "mode": self.actions.method_type,
            "feed": feed_response,
        }
