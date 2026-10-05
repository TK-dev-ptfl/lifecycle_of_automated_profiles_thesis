from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost/botdb"
    REDIS_URL: str = "redis://localhost:6379"
    SECRET_KEY: str = "change_me_to_a_secure_random_string_at_least_32_chars"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    # Webshare (webshare.io) is the one paid proxy source wired up, and it can be
    # used two different ways - both optional, and they combine.
    #
    # 1. An API key lists the account's individual proxies, each a fixed IP.
    #    Dashboard -> API -> Keys.
    WEBSHARE_API_KEY: str = ""
    # 2. The rotating ("backbone") endpoint: one hostname that hands out a
    #    different exit IP on every connection, authenticated with the proxy
    #    username/password from Dashboard -> Proxy -> Connection. This needs no
    #    API key, and one endpoint serves every identity - see is_rotating on the
    #    Proxy model for why that doesn't break "never reuse an IP".
    WEBSHARE_PROXY_HOST: str = "p.webshare.io"
    WEBSHARE_PROXY_PORT: int = 80
    WEBSHARE_PROXY_USERNAME: str = ""
    WEBSHARE_PROXY_PASSWORD: str = ""
    # 3. An explicit list of the account's proxies, for a plan that has no API
    #    key and no backbone access. Paste exactly what Webshare's
    #    Dashboard -> Proxy -> List -> Download gives you, which is one
    #    "ip:port:username:password" per line; "ip:port" alone also works and
    #    falls back to WEBSHARE_PROXY_USERNAME/PASSWORD. Newlines or commas.
    WEBSHARE_PROXY_LIST: str = ""
    # Webshare's own IP echo service. Used to verify the rotating endpoint and
    # report which exit IP it handed out, which is also the cheapest proof that
    # it really is rotating.
    WEBSHARE_ECHO_URL: str = "https://ipv4.webshare.io/"

    FIRST_SUPERUSER: str = "admin"
    FIRST_SUPERUSER_PASSWORD: str = "admin123"


settings = Settings()
