from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from sqlalchemy import select
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


async def get_proxies(
    db: AsyncSession,
    type: Optional[str] = None,
    country: Optional[str] = None,
    is_healthy: Optional[bool] = None,
    assigned: Optional[bool] = None,
) -> list:
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
    result = await db.execute(q)
    return result.scalars().all()


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


async def test_proxy(db: AsyncSession, proxy_id: UUID) -> Optional[Proxy]:
    proxy = await get_proxy(db, proxy_id)
    if not proxy:
        return None
    
    is_healthy = await asyncio.to_thread(
        check_proxy_health,
        proxy.host,
        proxy.port,
        proxy.protocol.value,
    )
    
    proxy.is_healthy = is_healthy
    proxy.last_checked = datetime.now(timezone.utc)
    await db.flush()
    return proxy


async def test_all_proxies(db: AsyncSession) -> int:
    proxies = await get_proxies(db)
    now = datetime.now(timezone.utc)
    
    for proxy in proxies:
        is_healthy = await asyncio.to_thread(
            check_proxy_health,
            proxy.host,
            proxy.port,
            proxy.protocol.value,
        )
        proxy.is_healthy = is_healthy
        proxy.last_checked = now
    
    await db.flush()
    return len(proxies)


async def import_proxies_from_free_list(db: AsyncSession) -> dict:
    """
    Fetch proxies from free-proxy-list.net and import them into the database.
    Returns a dict with counts and status.
    """
    proxy_data_list = fetch_proxies_from_free_proxy_list()
    
    if not proxy_data_list:
        return {'imported': 0, 'skipped': 0, 'error': 'Failed to fetch proxies from free-proxy-list.net'}
    
    imported = 0
    skipped = 0
    
    for proxy_data in proxy_data_list:
        try:
            # Check if proxy already exists
            existing = await db.execute(
                select(Proxy).where(
                    (Proxy.host == proxy_data['host']) & 
                    (Proxy.port == proxy_data['port'])
                )
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue
            
            # Create new proxy
            proxy = Proxy(
                host=proxy_data['host'],
                port=proxy_data['port'],
                protocol=proxy_data['protocol'],
                type=proxy_data['type'],
                country=proxy_data['country'],
                provider=proxy_data['provider'],
                is_healthy=True,
                last_checked=datetime.now(timezone.utc)
            )
            db.add(proxy)
            imported += 1
        except Exception as e:
            print(f"Error importing proxy {proxy_data}: {e}")
            skipped += 1
            continue
    
    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        return {'imported': imported, 'skipped': skipped, 'error': str(e)}
    
    return {'imported': imported, 'skipped': skipped, 'message': f'Successfully imported {imported} proxies'}


async def cleanup_unhealthy_proxies(db: AsyncSession) -> dict:
    """
    Remove unhealthy proxies that are not assigned to any bot.
    Returns count of deleted proxies.
    """
    result = await db.execute(
        select(Proxy).where(
            (Proxy.is_healthy == False) &
            (Proxy.assigned_bot_id.is_(None))
        )
    )
    unhealthy = result.scalars().all()
    
    deleted_count = 0
    for proxy in unhealthy:
        await db.delete(proxy)
        deleted_count += 1
    
    await db.flush()
    return {'deleted': deleted_count}

