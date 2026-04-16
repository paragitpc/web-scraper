from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.cli import base_parser, add_id_range, out_path, print_summary
from core.http_client import fetch, make_async_client, polite_sleep
from core.storage import LocalStorage, sha256_text


SOURCE = "impo_leyes"
URL_TEMPLATE = "https://www.impo.com.uy/bases/leyes-originales/{n}-2025"
URL_TEMPLATE_FALLBACK = "https://www.impo.com.uy/bases/leyes/{n}"
NOT_FOUND_MARKERS = (
    "no existe la norma",
    "no se encontr",
    "página no encontrada",
)
MIN_BODY_TEXT = 250


def relative_path_for(n: int) -> str:
    bucket = (n // 1000) * 1000
    return f"{SOURCE}/{bucket:05d}/{n:05d}.html"


def text_path_for(n: int) -> str:
    bucket = (n // 1000) * 1000
    return f"{SOURCE}/{bucket:05d}/{n:05d}.txt"


def extract_text(html: str) -> tuple[str, str | None]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    title = None
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)
    body = soup.get_text("\n", strip=True)
    return body, title


async def fetch_law(client: httpx.AsyncClient, n: int) -> tuple[int, str, str]:
    url = URL_TEMPLATE.format(n=n)
    r = await fetch(client, url)
    if r.status_code == 200 and len(r.text) > MIN_BODY_TEXT:
        return r.status_code, r.text, url
    url2 = URL_TEMPLATE_FALLBACK.format(n=n)
    try:
        r2 = await fetch(client, url2)
        if r2.status_code == 200:
            return r2.status_code, r2.text, url2
    except Exception:
        pass
    return r.status_code, r.text, url


async def process_id(
    client: httpx.AsyncClient,
    n: int,
    storage: LocalStorage,
    already_done: set[str],
) -> str:
    key = str(n)
    if key in already_done:
        return "skip_done"

    rel_html = relative_path_for(n)
    if storage.exists(rel_html):
        return "skip_exists"

    try:
        status, body, url = await fetch_law(client, n)
    except Exception as exc:
        print(f"  [error] ley {n}: {type(exc).__name__}: {exc}")
        return "error"

    if status == 404:
        storage.append_index_record(
            source=SOURCE, key=key, url=url, relative_path="",
            size_bytes=0, sha256="", extra={"status": "not_found"},
        )
        return "not_found"

    if status != 200:
        return "http_error"

    text, title = extract_text(body)

    if any(m in text.lower() for m in NOT_FOUND_MARKERS) or len(text) < MIN_BODY_TEXT:
        storage.append_index_record(
            source=SOURCE, key=key, url=url, relative_path="",
            size_bytes=0, sha256="", extra={"status": "empty"},
        )
        return "empty"

    storage.save_text(rel_html, body)
    storage.save_text(text_path_for(n), text)

    digest = sha256_text(text)
    storage.append_index_record(
        source=SOURCE,
        key=key,
        url=url,
        relative_path=rel_html,
        size_bytes=len(body.encode("utf-8")),
        sha256=digest,
        extra={"title": title} if title else None,
    )
    print(f"  [ok] ley {n}  ({len(text):,} chars)")
    return "ok"


async def run(from_id: int, to_id: int, base_dir: Path, delay: float) -> dict[str, int]:
    storage = LocalStorage(base_dir)
    already_done = storage.load_index_keys(SOURCE)
    stats: dict[str, int] = {}

    async with make_async_client(headers={"Accept": "text/html,*/*"}) as client:
        for n in range(from_id, to_id + 1):
            result = await process_id(client, n, storage, already_done)
            stats[result] = stats.get(result, 0) + 1
            if result not in {"skip_done", "skip_exists"}:
                await polite_sleep(delay)

    return stats


def main() -> None:
    parser = base_parser("Scraper IMPO Leyes")
    add_id_range(parser, default_min=1)
    args = parser.parse_args()
    base_dir = out_path(args)
    print(f"range: {args.from_id} .. {args.to_id}   out: {base_dir}   delay: {args.delay}s")
    stats = asyncio.run(run(args.from_id, args.to_id, base_dir, args.delay))
    print_summary(stats)


if __name__ == "__main__":
    main()
