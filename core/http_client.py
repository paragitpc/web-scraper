from __future__ import annotations

import asyncio
import random
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_TIMEOUT = 60.0
DEFAULT_DELAY = 1.5
DEFAULT_JITTER = 0.5


def default_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": "es-UY,es;q=0.9,en;q=0.8",
    }
    if extra:
        headers.update(extra)
    return headers


def make_async_client(
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    follow_redirects: bool = True,
    http2: bool = False,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers=default_headers(headers),
        timeout=httpx.Timeout(timeout),
        follow_redirects=follow_redirects,
        http2=http2,
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception_type(
        (httpx.TransportError, httpx.TimeoutException, httpx.RemoteProtocolError)
    ),
    reraise=True,
)
async def fetch(
    client: httpx.AsyncClient,
    url: str,
    method: str = "GET",
    **kwargs: Any,
) -> httpx.Response:
    return await client.request(method, url, **kwargs)


async def polite_sleep(delay: float, jitter: float = DEFAULT_JITTER) -> None:
    if delay <= 0:
        return
    extra = random.uniform(0, jitter) if jitter > 0 else 0
    await asyncio.sleep(delay + extra)


def is_pdf(content: bytes) -> bool:
    return content.startswith(b"%PDF")


def is_html(content_type: str) -> bool:
    ct = content_type.lower()
    return "html" in ct or "xhtml" in ct


def looks_empty_or_error(
    content: bytes,
    content_type: str,
    min_bytes: int = 256,
) -> bool:
    if len(content) < min_bytes:
        return True
    ct = content_type.lower()
    if "text/plain" in ct and len(content) < 4096:
        return True
    return False
