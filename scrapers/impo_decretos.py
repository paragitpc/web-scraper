from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.cli import base_parser, out_path, print_summary
from core.http_client import fetch, make_async_client, polite_sleep
from core.storage import LocalStorage, sha256_text


SOURCE = "impo_decretos"
URL_TEMPLATE = "https://www.impo.com.uy/bases/decretos/{n}-{y}"
NOT_FOUND_MARKERS = ("no existe la norma", "no se encontr", "página no encontrada")
MIN_BODY_TEXT = 250


def relative_path_for(y: int, n: int) -> str:
    return f"{SOURCE}/{y:04d}/{n:05d}-{y:04d}.html"


def text_path_for(y: int, n: int) -> str:
    return f"{SOURCE}/{y:04d}/{n:05d}-{y:04d}.txt"


def extract_text(html: str) -> tuple[str, str | None]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    title = None
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)
    return soup.get_text("\n", strip=True), title


async def process_decree(
    client: httpx.AsyncClient,
    n: int,
    y: int,
    storage: LocalStorage,
    already_done: set[str],
) -> str:
    key = f"{n}-{y}"
    if key in already_done:
        return "skip_done"

    rel_html = relative_path_for(y, n)
    if storage.exists(rel_html):
        return "skip_exists"

    url = URL_TEMPLATE.format(n=n, y=y)

    try:
        r = await fetch(client, url)
    except Exception as exc:
        print(f"  [error] dec {key}: {type(exc).__name__}: {exc}")
        return "error"

    if r.status_code == 404:
        storage.append_index_record(
            source=SOURCE, key=key, url=url, relative_path="",
            size_bytes=0, sha256="", extra={"status": "not_found"},
        )
        return "not_found"
    if r.status_code != 200:
        return "http_error"

    text, title = extract_text(r.text)
    if any(m in text.lower() for m in NOT_FOUND_MARKERS) or len(text) < MIN_BODY_TEXT:
        storage.append_index_record(
            source=SOURCE, key=key, url=url, relative_path="",
            size_bytes=0, sha256="", extra={"status": "empty"},
        )
        return "empty"

    storage.save_text(rel_html, r.text)
    storage.save_text(text_path_for(y, n), text)

    storage.append_index_record(
        source=SOURCE,
        key=key,
        url=url,
        relative_path=rel_html,
        size_bytes=len(r.text.encode("utf-8")),
        sha256=sha256_text(text),
        extra={"title": title, "year": y, "number": n} if title else {"year": y, "number": n},
    )
    print(f"  [ok] dec {key}  ({len(text):,} chars)")
    return "ok"


async def run(
    from_year: int, to_year: int,
    from_n: int, to_n: int,
    base_dir: Path, delay: float,
) -> dict[str, int]:
    storage = LocalStorage(base_dir)
    already_done = storage.load_index_keys(SOURCE)
    stats: dict[str, int] = {}

    async with make_async_client(headers={"Accept": "text/html,*/*"}) as client:
        for y in range(from_year, to_year + 1):
            for n in range(from_n, to_n + 1):
                result = await process_decree(client, n, y, storage, already_done)
                stats[result] = stats.get(result, 0) + 1
                if result not in {"skip_done", "skip_exists"}:
                    await polite_sleep(delay)

    return stats


def main() -> None:
    parser = base_parser("Scraper IMPO Decretos")
    parser.add_argument("--from-year", type=int, required=True)
    parser.add_argument("--to-year", type=int, required=True)
    parser.add_argument("--from-n", type=int, default=1)
    parser.add_argument("--to-n", type=int, default=600)
    args = parser.parse_args()
    base_dir = out_path(args)
    print(
        f"years: {args.from_year}..{args.to_year}   nums: {args.from_n}..{args.to_n}   "
        f"out: {base_dir}   delay: {args.delay}s"
    )
    stats = asyncio.run(
        run(args.from_year, args.to_year, args.from_n, args.to_n, base_dir, args.delay)
    )
    print_summary(stats)


if __name__ == "__main__":
    main()
