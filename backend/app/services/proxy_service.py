from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from sqlalchemy import case, delete as sa_delete, func, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
import httpx
from bs4 import BeautifulSoup
from app.config import settings
from app.models.proxy import Proxy
from app.models.proxy_provider import ProxyProvider
from app.schemas.proxy import ProxyCreate, ProxyUpdate
from app.utilities.proxy_health import check_proxy_health


def fetch_proxies_from_free_proxy_list() -> list[dict]:
    """
    Fetch proxies from free-proxy-list.net synchronously.
    Returns a list of proxy dictionaries.
    """

    url = "https://free-proxy-list.net/en/"

    headers = {
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/147.0.0.0 Safari/537.36"
        )
    }

    try:
        with httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers=headers,
        ) as client:

            response = client.get(url)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        table = soup.find(
            "table",
            class_="table table-striped table-bordered"
        )

        if not table:
            return []

        tbody = table.find("tbody")

        if not tbody:
            return []

        proxies = []

        rows = tbody.find_all("tr")

        for row in rows:
            cells = row.find_all("td")

            # Expected columns:
            # IP | Port | Code | Country | Anonymity | Google | HTTPS | Last Checked
            if len(cells) < 8:
                continue

            try:
                ip = cells[0].get_text(strip=True)
                port = cells[1].get_text(strip=True)
                code = cells[2].get_text(strip=True)
                country = cells[3].get_text(strip=True)
                anonymity = cells[4].get_text(strip=True).lower()

                if not ip or ip == "0.0.0.0":
                    continue

                port_num = int(port)

                # Map anonymity level to proxy type
                if "elite" in anonymity:
                    proxy_type = "datacenter"
                elif "anonymous" in anonymity:
                    proxy_type = "residential"
                else:
                    proxy_type = "mobile"

                proxy_dict = {
                    "host": ip,
                    "port": port_num,
                    "protocol": "http",  # Free Proxy List only provides HTTP proxies
                    "type": proxy_type,
                    "country": code if code else (country[:2].upper() if country else "UN"),
                    "provider": "free-proxy-list",
                }

                proxies.append(proxy_dict)

            except (ValueError, IndexError, AttributeError):
                continue

        return proxies

    except Exception as e:
        print(f"Error fetching proxies from free-proxy-list.net: {e}")
        return []


PROXYSCRAPE_URL = (
    "https://api.proxyscrape.com/v4/free-proxy-list/get"
    "?request=display_proxies&proxy_format=protocolipport&format=text"
)


def fetch_proxies_from_proxyscrape() -> list[dict]:
    """
    Fetch proxies from proxyscrape.com synchronously. The protocolipport
    text format returns one "protocol://ip:port" per line with no
    country/anonymity data at all (unlike free-proxy-list.net's HTML table) -
    country is left as the same "UN" (unknown) placeholder already used
    elsewhere for a missing country, and type is left as datacenter rather
    than guessing residential/mobile with literally nothing to base that on;
    these can still surface as a last-resort candidate (see
    identity_service._select_and_test_proxy) same as any other datacenter
    proxy, just not preferred over ones we have better information about.
    Returns a list of proxy dictionaries in the same shape as
    fetch_proxies_from_free_proxy_list's, so both sources merge and import
    identically.
    """
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.get(PROXYSCRAPE_URL)
            response.raise_for_status()

        proxies = []

        for line in response.text.splitlines():
            line = line.strip()
            if not line or "://" not in line:
                continue

            protocol, _, hostport = line.partition("://")
            protocol = protocol.strip().lower()
            # Only protocols our own Proxy model actually represents (see
            # ProxyProtocol) - this feed can also return socks4, which isn't
            # one of them, so those lines are skipped rather than silently
            # mislabeled as socks5 (a different protocol Chromium would then
            # try to speak to a proxy that doesn't understand it).
            if protocol not in ("http", "socks5"):
                continue

            host, _, port_str = hostport.strip().rpartition(":")
            if not host or not port_str.isdigit():
                continue

            proxies.append({
                "host": host,
                "port": int(port_str),
                "protocol": protocol,
                "type": "datacenter",
                "country": "UN",
                "provider": "proxyscrape",
            })

        return proxies

    except Exception as e:
        print(f"Error fetching proxies from proxyscrape.com: {e}")
        return []


WEBSHARE_URL = "https://proxy.webshare.io/api/v2/proxy/list/"
# Webshare pages its list; 100 is its own maximum per page. More than a few
# hundred proxies is far more than this pipeline needs at once, so the fetcher
# stops after this many pages rather than walking an entire large plan.
WEBSHARE_MAX_PAGES = 5


def webshare_rotating_endpoint() -> Optional[dict]:
    """Webshare's rotating ("backbone") endpoint as a single proxy entry, or None
    when no proxy credentials are configured.

    One hostname, a different exit IP on every connection - which is why it comes
    back with is_rotating set. That flag is what stops the pipeline retiring it
    after one signup: see the Proxy model, and
    identity_service._claim_and_consume_free_proxy.
    """
    if not (settings.WEBSHARE_PROXY_USERNAME and settings.WEBSHARE_PROXY_PASSWORD):
        return None
    return {
        "host": settings.WEBSHARE_PROXY_HOST,
        "port": settings.WEBSHARE_PROXY_PORT,
        "username": settings.WEBSHARE_PROXY_USERNAME,
        "password": settings.WEBSHARE_PROXY_PASSWORD,
        "protocol": "http",
        "type": "residential",
        # The exit IP changes per connection, so no single country describes it.
        "country": "UN",
        "provider": "webshare",
        "is_rotating": True,
    }


def verify_webshare_rotating_endpoint() -> Optional[str]:
    """Calls Webshare's IP echo through the rotating endpoint and returns the
    exit IP it reported, or None if it didn't work.

    Purely diagnostic - it's the cheapest way to confirm the credentials are
    right, and calling it twice showing two different IPs is the cheapest proof
    the endpoint really is rotating.
    """
    entry = webshare_rotating_endpoint()
    if entry is None:
        return None
    proxy_url = f"http://{entry['username']}:{entry['password']}@{entry['host']}:{entry['port']}/"
    try:
        with httpx.Client(proxy=proxy_url, timeout=20.0, follow_redirects=True) as client:
            response = client.get(settings.WEBSHARE_ECHO_URL)
            response.raise_for_status()
            return response.text.strip()
    except Exception as e:
        print(f"Webshare rotating endpoint check failed: {e}")
        return None


def fetch_proxies_from_webshare() -> list[dict]:
    """Everything Webshare can give us, from either or both of its two modes.

    - The rotating endpoint (proxy username/password, no API key): one entry,
      flagged is_rotating, reusable across identities because each connection
      exits from a different IP.
    - The API list (API key): the account's individual fixed-IP proxies.

    Webshare is the only source that returns credentials at all, which is why
    check_proxy_health and _proxy_to_playwright_config both had to learn to pass
    those through. Its proxies also come with a real type, so they're preferred
    by candidate selection rather than landing in the datacenter last-resort
    bucket.

    Returns [] (with a printed reason) rather than raising when nothing is
    configured or a call fails, so a refresh keeps whatever the other sources
    produced - same contract as the free fetchers.
    """
    proxies: list[dict] = []

    rotating = webshare_rotating_endpoint()
    if rotating is not None:
        proxies.append(rotating)

    if not settings.WEBSHARE_API_KEY:
        if not proxies:
            print(
                "Webshare: nothing configured, skipping. Set WEBSHARE_PROXY_USERNAME/"
                "WEBSHARE_PROXY_PASSWORD for the rotating endpoint, or WEBSHARE_API_KEY "
                "to list individual proxies (backend/.env)."
            )
        return proxies

    try:
        with httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={"Authorization": f"Token {settings.WEBSHARE_API_KEY}"},
        ) as client:
            for page in range(1, WEBSHARE_MAX_PAGES + 1):
                response = client.get(
                    WEBSHARE_URL,
                    params={"mode": "direct", "page": page, "page_size": 100},
                )
                response.raise_for_status()
                payload = response.json()

                for entry in payload.get("results") or []:
                    # Webshare marks a proxy it knows to be down; no reason to
                    # import one just to health-check it and throw it away.
                    if entry.get("valid") is False:
                        continue
                    host = entry.get("proxy_address")
                    port = entry.get("port")
                    if not host or not isinstance(port, int):
                        continue
                    proxies.append({
                        "host": host,
                        "port": port,
                        "username": entry.get("username") or None,
                        "password": entry.get("password") or None,
                        "protocol": "http",
                        # Webshare sells these as residential; anything else it
                        # returns is still better-attested than a scraped list.
                        "type": "residential",
                        "country": (entry.get("country_code") or "UN").upper(),
                        "provider": "webshare",
                    })

                if not payload.get("next"):
                    break

        return proxies

    except Exception as e:
        # Keep whatever the rotating endpoint contributed - an expired API key
        # shouldn't take the rest of Webshare down with it.
        print(f"Error fetching the Webshare proxy list: {e}")
        return proxies


# Every source this system knows how to pull from, keyed by the string its
# fetcher writes into Proxy.provider. That key is the join between a pooled
# proxy and its provider row, which is what lets the Proxies page group by
# source and switch a whole source off.
# `fetch` is the NAME of the fetcher, resolved on this module at call time
# rather than captured here as a function object. Late binding on purpose: a
# reference frozen at import can't be patched, which silently made the fetchers
# untestable (and let the test suite hit the live network).
PROXY_SOURCES: dict[str, dict] = {
    "free-proxy-list": {
        "display_name": "free-proxy-list.net",
        "kind": "free",
        "fetch": "fetch_proxies_from_free_proxy_list",
    },
    "proxyscrape": {
        "display_name": "proxyscrape.com",
        "kind": "free",
        "fetch": "fetch_proxies_from_proxyscrape",
    },
    "webshare": {
        "display_name": "Webshare",
        "kind": "paid",
        "fetch": "fetch_proxies_from_webshare",
    },
}


def _source_fetcher(key: str):
    return globals()[PROXY_SOURCES[key]["fetch"]]

# Proxies added by hand on the Proxies page. Not fetchable, but it gets a
# provider row all the same so it can be grouped and switched off like any
# other source.
MANUAL_PROVIDER_KEY = "custom"


async def seed_proxy_providers(db: AsyncSession) -> None:
    """Creates the provider rows for every known source, once. Idempotent, and
    deliberately does not touch is_enabled on rows that already exist - that's
    the user's setting, and a server restart must not silently switch a source
    they turned off back on."""
    existing = set((await db.execute(select(ProxyProvider.key))).scalars().all())

    wanted = [
        (key, meta["display_name"], meta["kind"]) for key, meta in PROXY_SOURCES.items()
    ] + [(MANUAL_PROVIDER_KEY, "Added manually", "manual")]

    for key, display_name, kind in wanted:
        if key not in existing:
            db.add(ProxyProvider(key=key, display_name=display_name, kind=kind, is_enabled=True))
    await db.commit()


async def get_proxy_providers(db: AsyncSession) -> list[dict]:
    """Every provider with its on/off state and how many proxies it currently
    accounts for, which is what the Proxies page groups by.

    Providers with no row of their own (a one-off string typed into the Add
    Proxy form) are still listed, as enabled - see disabled_provider_keys for
    why absence means enabled rather than unknown."""
    rows = (await db.execute(select(ProxyProvider).order_by(ProxyProvider.key))).scalars().all()
    by_key = {row.key: row for row in rows}

    counts = await db.execute(
        select(
            Proxy.provider,
            func.count(Proxy.id),
            func.sum(case((Proxy.consumed_at.isnot(None), 1), else_=0)),
            func.sum(case(((Proxy.consumed_at.is_(None)) & (Proxy.is_healthy.is_(True)), 1), else_=0)),
        ).group_by(Proxy.provider)
    )
    stats = {
        provider: {
            "total": total or 0,
            "retired": int(retired or 0),
            "available": (total or 0) - int(retired or 0),
            "available_healthy": int(healthy or 0),
        }
        for provider, total, retired, healthy in counts.all()
    }

    providers = []
    for key in sorted(set(by_key) | set(stats)):
        row = by_key.get(key)
        meta = PROXY_SOURCES.get(key, {})
        providers.append({
            "key": key,
            "display_name": row.display_name if row else key,
            "kind": row.kind if row else "manual",
            "is_enabled": row.is_enabled if row else True,
            "can_fetch": key in PROXY_SOURCES,
            # Surfaced so the page can explain a paid source sitting at zero
            # rather than leaving it looking broken.
            "needs_api_key": key == "webshare" and not settings.WEBSHARE_API_KEY,
            **stats.get(key, {"total": 0, "retired": 0, "available": 0, "available_healthy": 0}),
        })
    return providers


async def set_proxy_provider_enabled(db: AsyncSession, key: str, is_enabled: bool) -> Optional[ProxyProvider]:
    """Turns a provider on or off. Creates the row if this provider only existed
    as a string on some proxies until now, so an ad-hoc source can be switched
    off too."""
    row = (await db.execute(select(ProxyProvider).where(ProxyProvider.key == key))).scalar_one_or_none()
    if row is None:
        known = await db.execute(select(Proxy.provider).where(Proxy.provider == key).limit(1))
        if known.scalar_one_or_none() is None and key not in PROXY_SOURCES:
            return None
        meta = PROXY_SOURCES.get(key, {})
        row = ProxyProvider(
            key=key,
            display_name=meta.get("display_name", key),
            kind=meta.get("kind", "manual"),
        )
        db.add(row)
    row.is_enabled = is_enabled
    await db.commit()
    await db.refresh(row)
    return row


async def disabled_provider_keys(db: AsyncSession) -> set[str]:
    """Providers explicitly switched off.

    Returns what to EXCLUDE rather than what to allow, on purpose: a provider
    with no row - a proxy added by hand under some new name, or a source added
    to the code before its row is seeded - is then treated as usable instead of
    silently invisible. Only an explicit "off" hides anything."""
    rows = await db.execute(select(ProxyProvider.key).where(ProxyProvider.is_enabled.is_(False)))
    return set(rows.scalars().all())


async def get_proxies(
    db: AsyncSession,
    type: Optional[str] = None,
    country: Optional[str] = None,
    is_healthy: Optional[bool] = None,
    assigned: Optional[bool] = None,
    retired: Optional[bool] = None,
    provider: Optional[str] = None,
) -> list:
    """retired filters on consumed_at: True = only proxies permanently out of
    circulation (used by a pipeline, or retired after failing in real use),
    False = only ones still available. Those rows are kept forever so a later
    scrape can't re-import the same address (see the Proxy model), which means
    they accumulate - retired=False is what keeps the Proxies page showing the
    pool that actually matters rather than a graveyard."""
    q = select(Proxy)
    if type:
        q = q.where(Proxy.type == type)
    if country:
        q = q.where(Proxy.country == country)
    if is_healthy is not None:
        q = q.where(Proxy.is_healthy == is_healthy)
    if assigned is True:
        q = q.where(Proxy.assigned_bot_id.isnot(None))
    elif assigned is False:
        q = q.where(Proxy.assigned_bot_id.is_(None))
    if retired is True:
        q = q.where(Proxy.consumed_at.isnot(None))
    elif retired is False:
        q = q.where(Proxy.consumed_at.is_(None))
    if provider:
        q = q.where(Proxy.provider == provider)
    result = await db.execute(q)
    return result.scalars().all()


async def count_proxies(db: AsyncSession) -> dict:
    """Pool totals in one query instead of counting a full page of rows
    client-side - the retired set runs to thousands, so it must never have to be
    fetched just to be counted."""
    result = await db.execute(
        select(
            func.count(Proxy.id),
            func.sum(case((Proxy.consumed_at.isnot(None), 1), else_=0)),
            func.sum(case(((Proxy.consumed_at.is_(None)) & (Proxy.is_healthy.is_(True)), 1), else_=0)),
        )
    )
    total, retired, available_healthy = result.one()
    return {
        "total": total or 0,
        "retired": int(retired or 0),
        "available": (total or 0) - int(retired or 0),
        "available_healthy": int(available_healthy or 0),
    }


async def get_proxy(db: AsyncSession, proxy_id: UUID) -> Optional[Proxy]:
    result = await db.execute(select(Proxy).where(Proxy.id == proxy_id))
    return result.scalar_one_or_none()


async def create_proxy(db: AsyncSession, data: ProxyCreate) -> Proxy:
    proxy = Proxy(**data.model_dump())
    db.add(proxy)
    await db.flush()
    await db.refresh(proxy)
    return proxy


async def create_proxies_bulk(db: AsyncSession, proxies: list) -> list:
    created = []
    for data in proxies:
        proxy = Proxy(**data.model_dump())
        db.add(proxy)
        created.append(proxy)
    await db.flush()
    for proxy in created:
        await db.refresh(proxy)
    return created


async def update_proxy(db: AsyncSession, proxy_id: UUID, data: ProxyUpdate) -> Optional[Proxy]:
    proxy = await get_proxy(db, proxy_id)
    if not proxy:
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(proxy, field, value)
    await db.flush()
    return proxy


async def delete_proxy(db: AsyncSession, proxy_id: UUID) -> bool:
    proxy = await get_proxy(db, proxy_id)
    if not proxy:
        return False
    await db.delete(proxy)
    return True


async def test_proxy(db: AsyncSession, proxy_id: UUID, claim_for: Optional[UUID] = None) -> Optional[Proxy]:
    """Live-tests a proxy and, if claim_for is given and it comes back
    healthy, atomically claims it (assigned_bot_id) for that id in the same
    call. This closes a real race in identity generation: testing a proxy
    used to leave it fully unclaimed in the DB until a *separate*, later
    createIdentity() request reserved it - and in between, nothing stopped a
    different, already-running pipeline's own free-pool search (see
    identity_service._select_and_test_proxy) from claiming the exact same
    proxy first. claim_for is normally an identity id generated client-side
    up front (before it's actually created) specifically so the claim can
    happen the instant health is confirmed, not several awaits and one more
    HTTP round-trip later.

    The returned Proxy's assigned_bot_id reflects who *actually* ended up
    with it (refreshed after the claim attempt) - callers should check it
    equals their own claim_for, not just that is_healthy is true, since a
    concurrent claim can still win the race here same as anywhere else this
    pattern is used (see _claim_and_consume_free_proxy)."""
    proxy = await get_proxy(db, proxy_id)
    if not proxy:
        return None

    is_healthy = await asyncio.to_thread(
        check_proxy_health,
        proxy.host,
        proxy.port,
        proxy.protocol.value,
        username=proxy.username,
        password=proxy.password,
    )

    proxy.is_healthy = is_healthy
    proxy.last_checked = datetime.now(timezone.utc)

    if is_healthy and claim_for is not None:
        await db.execute(
            sa_update(Proxy)
            .where(Proxy.id == proxy_id, Proxy.assigned_bot_id.is_(None), Proxy.consumed_at.is_(None))
            .values(assigned_bot_id=claim_for)
        )

    await db.commit()
    await db.refresh(proxy)
    return proxy


# How many proxies get health-checked concurrently at once in test_all_proxies
# - one at a time against a pool of hundreds (each check up to its own 10s
# timeout) could take the better part of an hour; checking a chunk of these
# at a time cuts that down substantially.
TEST_ALL_BATCH_SIZE = 20


async def test_all_proxies(db: AsyncSession) -> int:
    proxies = await get_proxies(db)
    now = datetime.now(timezone.utc)

    for batch_start in range(0, len(proxies), TEST_ALL_BATCH_SIZE):
        batch = proxies[batch_start:batch_start + TEST_ALL_BATCH_SIZE]
        healthy_flags = await asyncio.gather(*(
            asyncio.to_thread(
                check_proxy_health, proxy.host, proxy.port, proxy.protocol.value,
                username=proxy.username, password=proxy.password,
            )
            for proxy in batch
        ))
        for proxy, is_healthy in zip(batch, healthy_flags):
            proxy.is_healthy = is_healthy
            proxy.last_checked = now

    await db.flush()
    return len(proxies)


async def import_proxies_from_free_list(db: AsyncSession) -> dict:
    """
    Fetch proxies from every configured free source - currently
    free-proxy-list.net and proxyscrape.com - and import them into the
    database. Returns a dict with counts and status.

    Both fetchers are plain sync functions (httpx's sync Client, one with
    BeautifulSoup parsing) that can each take several seconds - run via
    asyncio.to_thread, concurrently, so neither blocks this process's single
    event loop or waits on the other unnecessarily. That matters more now
    than it used to: identity_service calls this at the start of every email
    pipeline run to refresh the pool with fresh candidates, and pipelines are
    meant to run fully concurrently (see
    test_two_pipelines_run_concurrently_not_one_after_another) - a blocking
    call here would stall every other pipeline for as long as the scrape
    takes.

    Each fetcher already catches its own errors and returns [] rather than
    raising, so one source being down doesn't stop the other's results from
    being imported - only reported as an overall error if *both* come back
    empty. import_proxies_from_free_list's own per-entry host:port dedup
    check (below) handles the rare case of the same proxy appearing in both
    sources transparently.
    """
    proxy_data_list = await fetch_all_free_proxies(db)

    if not proxy_data_list:
        return {'imported': 0, 'skipped': 0, 'error': 'Failed to fetch proxies from any configured source (free-proxy-list.net, proxyscrape.com)'}

    imported, skipped = await _insert_new_proxies(db, proxy_data_list)

    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        return {'imported': imported, 'skipped': skipped, 'error': str(e)}

    return {'imported': imported, 'skipped': skipped, 'message': f'Successfully imported {imported} proxies'}


async def fetch_all_free_proxies(db: Optional[AsyncSession] = None) -> list[dict]:
    """Fetches from every ENABLED source concurrently and returns the merged,
    unfiltered result. Split out of import_proxies_from_free_list so
    replace_free_proxy_pool can fetch *before* it throws the old list away - see
    the ordering note there.

    A disabled provider isn't fetched at all: leaving it out here is what stops
    a source you switched off from quietly refilling the pool every two minutes.
    With no session given, nothing is treated as disabled - the fetchers
    themselves don't need the database, and this keeps them testable in
    isolation.
    """
    disabled = await disabled_provider_keys(db) if db is not None else set()
    active = [(key, meta) for key, meta in PROXY_SOURCES.items() if key not in disabled]
    if not active:
        print("Proxy refresh: every source is switched off, fetching nothing")
        return []

    results = await asyncio.gather(*(asyncio.to_thread(_source_fetcher(key)) for key, _meta in active))
    merged: list[dict] = []
    for (key, _meta), fetched in zip(active, results):
        print(f"Proxy refresh: {key} returned {len(fetched)} proxies")
        merged.extend(fetched)
    return merged


async def _insert_new_proxies(db: AsyncSession, proxy_data_list: list[dict]) -> tuple[int, int]:
    """Adds every scraped entry whose host:port isn't already in the table,
    returning (imported, skipped). Does not commit - the caller owns the
    transaction, which is what lets replace_free_proxy_pool delete and
    re-insert atomically.

    The existing host:port set is read once up front rather than with a SELECT
    per entry: proxyscrape alone returns ~1800 rows per scrape, and this runs
    every two minutes on the refresher worker's cycle. Rows already deleted
    earlier in this same transaction are correctly absent from that set, so a
    proxy that was in the free pool a moment ago gets re-inserted fresh; a
    *consumed* one (see the Proxy model's consumed_at) is still there and
    still gets skipped, which is exactly what stops a used IP from ever coming
    back into circulation via a later scrape."""
    existing_rows = await db.execute(select(Proxy.host, Proxy.port))
    known: set[tuple[str, int]] = {(host, port) for host, port in existing_rows.all()}

    imported = 0
    skipped = 0
    now = datetime.now(timezone.utc)
    for proxy_data in proxy_data_list:
        try:
            key = (proxy_data['host'], proxy_data['port'])
            if key in known:
                skipped += 1
                continue
            known.add(key)
            db.add(Proxy(
                host=proxy_data['host'],
                port=proxy_data['port'],
                # Only Webshare supplies these, and without them its proxies
                # authenticate as nobody and fail every check.
                username=proxy_data.get('username'),
                password=proxy_data.get('password'),
                protocol=proxy_data['protocol'],
                type=proxy_data['type'],
                country=proxy_data['country'],
                provider=proxy_data['provider'],
                is_rotating=bool(proxy_data.get('is_rotating')),
                is_healthy=True,
                last_checked=now,
            ))
            imported += 1
        except Exception as e:
            print(f"Error importing proxy {proxy_data}: {e}")
            skipped += 1
            continue
    return imported, skipped


async def replace_free_proxy_pool(db: AsyncSession) -> dict:
    """Swaps the free part of the proxy pool for a freshly scraped one - what
    the proxy refresher worker (app.workers.proxy_refresher) runs every two
    minutes so the list on the Proxies page is never stale.

    "Free part" means unreserved AND never used: rows with an assigned_bot_id
    belong to an in-flight pipeline (or a bot) and rows with consumed_at are
    permanently retired, so both survive the swap untouched. Dropping the rest
    is the point - a free proxy's is_healthy/last_checked is worthless a few
    minutes later, and keeping dead entries around just makes every later
    search test them again.

    Scrapes first, then deletes and re-inserts inside one transaction: the
    scheduler's slots are searching this same pool concurrently, so deleting
    up front would leave them looking at an empty table for the several
    seconds the scrape takes. If both sources come back empty the existing
    list is deliberately left alone rather than replaced with nothing."""
    scraped = await fetch_all_free_proxies(db)
    if not scraped:
        return {
            'removed': 0, 'imported': 0, 'skipped': 0,
            'error': 'Failed to fetch proxies from any configured source (free-proxy-list.net, proxyscrape.com) - keeping the current list',
        }

    try:
        deleted = await db.execute(
            sa_delete(Proxy).where(
                Proxy.assigned_bot_id.is_(None),
                Proxy.consumed_at.is_(None),
                # A rotating endpoint is a standing subscription, not a scraped
                # address that goes stale - deleting and re-adding it every two
                # minutes would churn the row (and could pull it out from under a
                # run mid-flight) for no benefit.
                Proxy.is_rotating.is_(False),
            )
        )
        removed = deleted.rowcount or 0
        imported, skipped = await _insert_new_proxies(db, scraped)
        await db.commit()
    except Exception as e:
        await db.rollback()
        return {'removed': 0, 'imported': 0, 'skipped': 0, 'error': str(e)}

    return {'removed': removed, 'imported': imported, 'skipped': skipped}


async def cleanup_unhealthy_proxies(db: AsyncSession) -> dict:
    """
    Remove unhealthy proxies that are not assigned to any bot.
    Returns count of deleted proxies.

    Retired proxies (consumed_at set - used by a pipeline, or retired after
    failing in real use) are never deleted, even though they're unhealthy: their
    rows exist precisely so the host:port dedup in _insert_new_proxies keeps
    recognising them, and deleting one would let the very next scrape re-import
    the same dead or already-used address and hand it to another run.
    """
    result = await db.execute(
        select(Proxy).where(
            (Proxy.is_healthy == False) &
            (Proxy.assigned_bot_id.is_(None)) &
            (Proxy.consumed_at.is_(None))
        )
    )
    unhealthy = result.scalars().all()
    
    deleted_count = 0
    for proxy in unhealthy:
        await db.delete(proxy)
        deleted_count += 1
    
    await db.flush()
    return {'deleted': deleted_count}

