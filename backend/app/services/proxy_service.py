from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from sqlalchemy import case, delete as sa_delete, func, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
import httpx
from bs4 import BeautifulSoup
from app.models.proxy import Proxy
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


async def get_proxies(
    db: AsyncSession,
    type: Optional[str] = None,
    country: Optional[str] = None,
    is_healthy: Optional[bool] = None,
    assigned: Optional[bool] = None,
    retired: Optional[bool] = None,
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
    proxy_data_list = await fetch_all_free_proxies()

    if not proxy_data_list:
        return {'imported': 0, 'skipped': 0, 'error': 'Failed to fetch proxies from any configured source (free-proxy-list.net, proxyscrape.com)'}

    imported, skipped = await _insert_new_proxies(db, proxy_data_list)

    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        return {'imported': imported, 'skipped': skipped, 'error': str(e)}

    return {'imported': imported, 'skipped': skipped, 'message': f'Successfully imported {imported} proxies'}


async def fetch_all_free_proxies() -> list[dict]:
    """Scrapes every configured free source concurrently and returns the
    merged, unfiltered result. Split out of import_proxies_from_free_list so
    replace_free_proxy_pool can scrape *before* it throws the old list away -
    see the ordering note there."""
    proxy_data_list, proxyscrape_list = await asyncio.gather(
        asyncio.to_thread(fetch_proxies_from_free_proxy_list),
        asyncio.to_thread(fetch_proxies_from_proxyscrape),
    )
    return proxy_data_list + proxyscrape_list


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
                protocol=proxy_data['protocol'],
                type=proxy_data['type'],
                country=proxy_data['country'],
                provider=proxy_data['provider'],
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
    scraped = await fetch_all_free_proxies()
    if not scraped:
        return {
            'removed': 0, 'imported': 0, 'skipped': 0,
            'error': 'Failed to fetch proxies from any configured source (free-proxy-list.net, proxyscrape.com) - keeping the current list',
        }

    try:
        deleted = await db.execute(
            sa_delete(Proxy).where(Proxy.assigned_bot_id.is_(None), Proxy.consumed_at.is_(None))
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

