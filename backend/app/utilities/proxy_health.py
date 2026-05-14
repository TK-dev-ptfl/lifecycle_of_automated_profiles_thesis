import time
import httpx


def check_proxy_health(
    host: str,
    port: int,
    protocol: str = "http",
    timeout: int = 10,
) -> bool:
    """
    Test whether a proxy is alive and usable.
    Returns True if proxy is healthy, False otherwise.
    """

    proxy_url = f"{protocol}://{host}:{port}"

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
