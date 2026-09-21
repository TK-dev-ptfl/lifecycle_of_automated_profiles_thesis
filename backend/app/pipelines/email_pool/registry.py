"""Maps an EmailPlatform's name to its automated signup pipeline, if one
exists yet. Only Tuta is actually automated today; selecting any other
provider fails clearly instead of silently doing nothing."""
from __future__ import annotations

from typing import Callable, NamedTuple

from app.pipelines.email_pool.providers.tuta import describe_pipeline, run_tuta_signup_pipeline


class ProviderPipeline(NamedTuple):
    run: Callable
    describe: Callable[[], list[dict]]


PROVIDER_PIPELINES: dict[str, ProviderPipeline] = {
    "tuta": ProviderPipeline(run=run_tuta_signup_pipeline, describe=describe_pipeline),
}


def get_provider_pipeline(provider_name: str) -> ProviderPipeline:
    key = provider_name.strip().lower()
    if key not in PROVIDER_PIPELINES:
        available = ", ".join(sorted(PROVIDER_PIPELINES)) or "none"
        raise ValueError(
            f"No automated signup pipeline for provider '{provider_name}' yet (available: {available})"
        )
    return PROVIDER_PIPELINES[key]
