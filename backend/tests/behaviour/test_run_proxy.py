"""Proxy choice for behaviour runs: order only - no network, no database."""
from __future__ import annotations

from app.models.proxy import Proxy, ProxyProtocol, ProxyType
from app.services.run_proxy_service import playwright_config, rank


def proxy(host, *, provider="proxyscrape", type=ProxyType.datacenter, healthy=True,
          rotating=False, protocol=ProxyProtocol.http, username=None) -> Proxy:
    return Proxy(host=host, port=8080, provider=provider, type=type, is_healthy=healthy,
                 is_rotating=rotating, protocol=protocol, username=username,
                 password="pw" if username else None, country="US")


def test_paid_list_first_then_residential_then_datacenter():
    ranked = rank([
        proxy("dc"),
        proxy("res", provider="free-proxy-list", type=ProxyType.residential),
        proxy("ws", provider="webshare", type=ProxyType.residential),
        proxy("dc-dead", healthy=False),
    ], "identity-a")
    assert [p.host for p in ranked] == ["ws", "res", "dc", "dc-dead"]


def test_rotating_and_socks_with_credentials_are_left_out():
    ranked = rank([
        proxy("rot", provider="webshare", rotating=True),
        proxy("socks-auth", protocol=ProxyProtocol.socks5, username="u"),
        proxy("socks-open", protocol=ProxyProtocol.socks5),
    ], "identity-a")
    assert [p.host for p in ranked] == ["socks-open"]


def test_an_identity_keeps_to_the_same_proxy_and_identities_spread_out():
    pool = [proxy(f"ws-{i}", provider="webshare") for i in range(10)]
    assert rank(pool, "identity-a")[0].host == rank(list(reversed(pool)), "identity-a")[0].host
    firsts = {rank(pool, f"identity-{i}")[0].host for i in range(30)}
    assert len(firsts) > 3


def test_playwright_config_carries_credentials_only_when_there_are_some():
    assert playwright_config(proxy("h")) == {"server": "http://h:8080"}
    assert playwright_config(proxy("h", username="u")) == {
        "server": "http://h:8080", "username": "u", "password": "pw",
    }
