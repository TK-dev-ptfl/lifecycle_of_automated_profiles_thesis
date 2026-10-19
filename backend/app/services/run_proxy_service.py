"""Choosing a proxy for a behaviour test run, without touching the pool.

The proxy table belongs to the identity pipeline, which runs it on strict
bookkeeping: a proxy is claimed by one identity, consumed, and never handed to
another account (see models.proxy and identity_service). A behaviour run is not
an account - it reads a page and leaves - so it must not take part in any of
that. Everything here is read-only: nothing is claimed, consumed, assigned or
marked, whatever the outcome.

What a run needs from a proxy is different too: not "an IP nobody has used",
but one that works right now, and whose location is known so the fingerprint
can be placed there. So candidates are probed with a geo lookup *through* the
proxy, which answers both questions at once.
"""
from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from typing import Callable, Iterable, Optional
from urllib.parse import quote

import httpx
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.proxy import Proxy, ProxyProtocol, ProxyType

# Plain HTTP on purpose: it is the free endpoint, and through a proxy the
# answer is the proxy's exit, which is the only thing being asked.
GEO_URL = "http://ip-api.com/json/?fields=status,countryCode,timezone,query,isp,proxy,hosting"
PROBE_TIMEOUT_S = 10.0
# ip-api allows 45 requests a minute; probing in small batches and stopping at
# the first batch with a live proxy stays far inside that.
PROBE_BATCH = 6
MAX_PROBED = 30


@dataclass(frozen=True)
class RunProxy:
    """A working proxy and where it comes out."""

    playwright: dict          # Playwright's proxy config, credentials included
    label: str                # provider and host:port, for logs - no credentials
    provider: str
    kind: str                 # residential | mobile | datacenter
    exit_ip: str
    country_code: str
    timezone: str
    isp: str
    flagged_hosting: bool     # ip-api thinks this is a datacenter address

    def summary(self) -> dict:
        return {
            "provider": self.provider, "kind": self.kind, "exit_ip": self.exit_ip,
            "country": self.country_code, "timezone": self.timezone, "isp": self.isp,
            "hosting": self.flagged_hosting,
        }


def rank(proxies: Iterable[Proxy], identity: str) -> list[Proxy]:
    """Candidates in the order they should be tried for this identity.

    Best kinds first - the paid Webshare list, then residential and mobile,
    then datacenter, each with healthy-on-record ahead of not. Within a tier the
    order is a hash of identity and proxy, so an identity keeps coming back to
    the same proxy run after run (one person, one connection) while different
    identities spread across the list.

    Left out: rotating endpoints, whose exit changes per connection so no time
    zone can be matched to them and a page sees its visitor's IP jump mid-visit;
    and SOCKS proxies with credentials, which Chromium cannot authenticate to.
    """
    def tier(p: Proxy) -> int:
        if p.provider == "webshare":
            base = 0
        elif p.type in (ProxyType.residential, ProxyType.mobile):
            base = 2
        else:
            base = 4
        return base + (0 if p.is_healthy else 1)

    def stickiness(p: Proxy) -> bytes:
        return hashlib.sha256(f"{identity}|{p.host}:{p.port}".encode("utf-8")).digest()

    usable = [
        p for p in proxies
        if not p.is_rotating and not (p.protocol == ProxyProtocol.socks5 and p.username)
    ]
    return sorted(usable, key=lambda p: (tier(p), stickiness(p)))


def playwright_config(proxy: Proxy) -> dict:
    config = {"server": f"{proxy.protocol.value}://{proxy.host}:{proxy.port}"}
    if proxy.username:
        config["username"] = proxy.username
    if proxy.password:
        config["password"] = proxy.password
    return config


def _probe(proxy: Proxy) -> Optional[dict]:
    """Geo lookup through the proxy; None if it does not answer properly."""
    auth = ""
    if proxy.username:
        auth = f"{quote(proxy.username, safe='')}:{quote(proxy.password or '', safe='')}@"
    url = f"{proxy.protocol.value}://{auth}{proxy.host}:{proxy.port}"
    try:
        with httpx.Client(proxy=url, timeout=PROBE_TIMEOUT_S) as client:
            data = client.get(GEO_URL).json()
    except Exception:
        return None
    if data.get("status") != "success" or not data.get("countryCode") or not data.get("timezone"):
        return None
    return data


async def choose(identity: str, log: Callable[[str], None] = lambda _m: None) -> RunProxy:
    """The first working proxy for this identity, in rank() order.

    Raises rather than returning None: a run that cannot get a proxy must not
    quietly go out on the host's own address instead.
    """
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(Proxy))).scalars().all()
    candidates = rank(rows, identity)[:MAX_PROBED]
    if not candidates:
        raise RuntimeError("the proxy list has no usable proxies (rotating and SOCKS-with-auth are skipped)")

    for start in range(0, len(candidates), PROBE_BATCH):
        batch = candidates[start:start + PROBE_BATCH]
        results = await asyncio.gather(*(asyncio.to_thread(_probe, p) for p in batch))
        for proxy, geo in zip(batch, results):
            label = f"{proxy.provider} {proxy.host}:{proxy.port}"
            if geo is None:
                log(f"proxy {label} did not answer; trying the next")
                continue
            return RunProxy(
                playwright=playwright_config(proxy),
                label=label,
                provider=proxy.provider,
                kind=proxy.type.value,
                exit_ip=geo.get("query", ""),
                country_code=geo["countryCode"].upper(),
                timezone=geo["timezone"],
                isp=geo.get("isp", ""),
                flagged_hosting=bool(geo.get("hosting")),
            )
    raise RuntimeError(f"none of the {len(candidates)} best proxies in the list answered")
