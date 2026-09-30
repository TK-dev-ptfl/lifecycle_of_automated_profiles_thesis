from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, DateTime, Enum as SAEnum, Integer, String, func, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import enum


class ProxyProtocol(str, enum.Enum):
    http = "http"
    socks5 = "socks5"


class ProxyType(str, enum.Enum):
    residential = "residential"
    datacenter = "datacenter"
    mobile = "mobile"


class Proxy(Base):
    __tablename__ = "proxies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    host: Mapped[str] = mapped_column(String(256), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    password: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    protocol: Mapped[ProxyProtocol] = mapped_column(SAEnum(ProxyProtocol), default=ProxyProtocol.http)
    type: Mapped[ProxyType] = mapped_column(SAEnum(ProxyType), default=ProxyType.datacenter)
    country: Mapped[str] = mapped_column(String(64), nullable=False)
    city: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    assigned_bot_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("bots.id", use_alter=True), nullable=True)
    is_healthy: Mapped[bool] = mapped_column(Boolean, default=True)
    last_checked: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Set the moment a pipeline actually hands this proxy to Playwright (see
    # identity_service._select_and_test_proxy) - permanent, never cleared.
    # Unlike the old delete-on-consume behavior, the row survives so its
    # host:port stays known to the dedup check in
    # proxy_service.import_proxies_from_free_list forever, which is what
    # actually stops a later scrape from re-importing (and a later pipeline
    # from re-using) the exact same IP once it's been used once.
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # A rotating ("backbone") endpoint: one host:port that hands out a DIFFERENT
    # exit IP on every connection, rather than being one fixed IP.
    #
    # This is the one exception to "a proxy is used by exactly one identity and
    # then retired". That rule exists so two accounts never share an IP - and a
    # rotating endpoint honours it by construction, since consecutive identities
    # get different exit IPs even though they dial the same hostname. Treating it
    # like a fixed proxy would retire it after the very first signup and make the
    # whole subscription useless, so it is deliberately never locked to an
    # identity and never consumed (see identity_service._claim_and_consume_free_proxy).
    is_rotating: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    bot: Mapped[Optional[Bot]] = relationship("Bot", back_populates="proxy", foreign_keys=[assigned_bot_id])
