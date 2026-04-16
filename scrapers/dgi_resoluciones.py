from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.cli import base_parser, out_path, print_summary
from core.http_client import fetch, make_async_client, polite_sleep
from core.storage import LocalStorage, sha256_text


SOURCE = "dgi_resoluciones"
LISTING_URL = "https://www.impo.com.uy/bases/resoluciones-dgi"
DETAIL_PREFIX = "/bases/resoluciones-dgi/"
MIN_BODY_TEXT = 200


def relative_path_for(slug: str) -> str:
    safe = slug.replace("/", "_").strip("_")
    bucket = safe[:2] if safe else "_"
    return f"{SOURCE}/{bucket}/{safe}.html"


def text_path_for(slug: str) -> str:
    safe = slug.replace("/", "_").strip("_")
    bucket = safe[:2] if safe else "_"
    return f"{SOURCE}/{bucket}/{safe}.txt"


def slug_from_url(url: str) -> str:
    parts = url.rstrip("/").split("/")
    return f"{parts[-2]}-{parts[-1]}" if len(parts) >= 2 else parts[-1]


def extract_text(html: str) -> tuple[str, str | None]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    title = None
    h1 = soup.find("h1") or soup.find("h2")
    if h1:
        title = h1.get_text(strip=True)
    return soup.get_text("\n", strip=True), title


async def discover_links(max_pages: int = 1000) -> list[str]:
    found: set[str] = set()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await (await browser.new_context()).new_page()
        await page.goto(LISTING_URL, wait_until="networkidle", timeout=90000)
        for _ in range(max_pages):
            anchors = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
            for href in anchors:
                if DETAIL_PREFIX in href:
                    found.add(href)
            next_btn = await page.query_selector(
                "a[rel='next'], a:has-text('Siguiente'), a:has-text('Próxima')"
            )
            if not next_btn:
                break
            try:
                await next_btn.click()
                await page.wait_for_load_state("networkidle", timeout=60000)
            except Exception:
                break
        await browser.close()
    return sorted(found)


async def process_url(client, url, storage: LocalStorage, already_done: set[str]) -> str:
    slug = slug_from_url(url)
    if slug in already_done:
        return "skip_done"
    rel_html = relative_path_for(slug)
    if storage.exists(rel_html):
        return "skip_exists"

    try:
        r = await fetch(client, url)
    except Exception as exc:
        print(f"  [error] {slug}: {type(exc).__name__}: {exc}")
        return "error"
    if r.status_code != 200 or len(r.text) < MIN_BODY_TEXT:
        return "empty"

    text, title = extract_text(r.text)
    if len(text) < MIN_BODY_TEXT:
        return "empty"

    storage.save_text(rel_html, r.text)
    storage.save_text(text_path_for(slug), text)
    storage.append_index_record(
        source=SOURCE, key=slug, url=url, relative_path=rel_html,
        size_bytes=len(r.text.encode("utf-8")), sha256=sha256_text(text),
        extra={"title": title} if title else None,
    )
    print(f"  [ok] {slug}  ({len(text):,} chars)")
    return "ok"


async def run(base_dir: Path, delay: float, max_pages: int) -> dict[str, int]:
    storage = LocalStorage(base_dir)
    already_done = storage.load_index_keys(SOURCE)
    stats: dict[str, int] = {}

    print("discovering links...")
    urls = await discover_links(max_pages=max_pages)
    print(f"discovered: {len(urls)}")
    stats["discovered"] = len(urls)

    async with make_async_client(headers={"Accept": "text/html,*/*"}) as client:
        for url in urls:
            result = await process_url(client, url, storage, already_done)
            stats[result] = stats.get(result, 0) + 1
            if result not in {"skip_done", "skip_exists"}:
                await polite_sleep(delay)
    return stats


def main() -> None:
    parser = base_parser("Scraper DGI Resoluciones (via IMPO)")
    parser.add_argument("--max-pages", type=int, default=200)
    args = parser.parse_args()
    base_dir = out_path(args)
    print(f"out: {base_dir}   delay: {args.delay}s   max_pages: {args.max_pages}")
    stats = asyncio.run(run(base_dir, args.delay, args.max_pages))
    print_summary(stats)


if __name__ == "__main__":
    main()
