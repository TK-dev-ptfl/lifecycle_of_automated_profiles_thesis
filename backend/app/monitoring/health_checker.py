from typing import Any
from uuid import UUID


class HealthChecker:
    """Periodically probes each bot's account to verify it is still accessible."""

    async def check_bot(self, bot: Any) -> dict:
        """Probe the bot's account on its platform."""
        raise NotImplementedError

    async def check_all(self) -> list[dict]:
        """Run check_bot for every non-stopped bot."""
        raise NotImplementedError

    async def record_result(self, bot_id: UUID, result: dict) -> None:
        """Persist health check result, update bot.status if changed."""
        raise NotImplementedError
