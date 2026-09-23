from typing import Optional
from urllib.parse import quote

import httpx


def check_proxy_health(
    host: str,
    port: int,
    protocol: str = "http",
    timeout: int = 10,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> bool:
    """
    Test whether a proxy is alive and usable.
    Returns True if proxy is healthy, False otherwise.

    username/password, when the proxy has them, are embedded in the proxy
    URL (the only way httpx's `proxy=` string accepts proxy auth) - without
    this, a proxy that actually requires authentication would either be
    silently let through on IP whitelisting alone or, more commonly, just
    fail here every time regardless of whether the credentials on file are
    correct, since none were ever being sent.
    """
    auth = f"{quote(username, safe='')}:{quote(password, safe='')}@" if username else ""
    proxy_url = f"{protocol}://{auth}{host}:{port}"

    test_url = "https://httpbin.org/ip"

    try:
        with httpx.Client(
            proxy=proxy_url,
            timeout=timeout,
            follow_redirects=True,
        ) as client:
            response = client.get(test_url)
            return response.status_code == 200

    except Exception:
        return False
