from __future__ import annotations
from datetime import datetime
from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class ProxyProvider(Base):
    """One source of proxies, and whether identities are allowed to use it.

    `key` matches the string written into Proxy.provider by each fetcher, which
    is what ties a pooled proxy back to where it came from - so the page can be
    grouped by provider and a whole provider can be switched off without
    touching the proxies themselves.

    Switching one off is deliberately a *selection* filter, not a delete: the
    rows stay in the pool and keep showing on the Proxies page, they just stop
    being offered to new identities (see
    identity_service.list_free_proxy_candidates) and stop being re-fetched by
    the refresher. Turning it back on makes them eligible again immediately,
    with no re-scrape needed.
    """

    __tablename__ = "proxy_providers"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    # "free" - public list, no credentials, low reliability.
    # "paid" - account/API key required, far better hit rate.
    # "manual" - whatever was added by hand on the Proxies page.
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="free")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
