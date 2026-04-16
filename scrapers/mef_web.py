from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.cli import base_parser, out_path, print_summary
from core.http_client import fetch, make_async_client, polite_sleep
from core.storage import LocalStorage, sha256_text, sha256_bytes


SOURCE = "mef_web"
LISTING_URL = "https://www.gub.uy/ministerio-economia-finanzas/institucional/normativa"
MIN_BODY_TEXT = 200


def slug_from_url(url: str) -> str:
    p = urlparse(url)
    s = (p.path + ("?" + p.query if p.query else "")).replace("/", "_").replace("?", "_")
    return s.strip("_")[:200] or "root"


def relative_path_for(slug: str, ext: str) -> str:
    bucket = slug[:2] if slug else "_"
    return f"{SOURCE}/{bucket}/{slug}.{ext}"


def extract_text(html: str) -> tuple[str, str | None]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()
    title = None
    h1 = soup.find("h1") or soup.find("h2")
    if h1:
        title = h1.get_text(strip=True)
    return soup.get_text("\n", strip=True), title


async def discover_links(max_pages: int = 200) -> list[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await (await browser.new_context()).new_page()
        try:
            await page.goto(LISTING_URL, wait_until="networkidle", timeout=90000)
        except Exception:
            await browser.close()
            return []

        for _ in range(max_pages):
            anchors = await page.eval_on_selector_all(
                "a[href]", "els => els.map(e => e.href)"
            )
            for href in anchors:
                if not href:
                    continue
                if "ministerio-economia-finanzas" in href and "/normativa" in href:
                    if href.lower().endswith(".pdf"):
                        found.add((href, "pdf"))
                    else:
                        found.add((href, "html"))
                elif href.lower().endswith(".pdf") and "gub.uy" in href:
                    found.add((href, "pdf"))

            next_btn = await page.query_selector(
                "a[rel='next'], a.next, a:has-text('Siguiente'), button:has-text('Siguiente')"
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


async def process_item(
    client, url: str, ext: str,
    storage: LocalStorage, already_done: set[str],
) -> str:
    slug = slug_from_url(url)
    if slug in already_done:
        return "skip_done"
    rel_path = relative_path_for(slug, ext)
    if storage.exists(rel_path):
        return "skip_exists"

    try:
        r = await fetch(client, url)
    except Exception as exc:
        print(f"  [error] {slug}: {type(exc).__name__}: {exc}")
        return "error"
    if r.status_code != 200:
        return "http_error"

    if ext == "pdf":
        if len(r.content) < 1024 or not r.content.startswith(b"%PDF"):
            return "empty"
        storage.save_bytes(rel_path, r.content)
        storage.append_index_record(
            source=SOURCE, key=slug, url=url, relative_path=rel_path,
            size_bytes=len(r.content), sha256=sha256_bytes(r.content),
            extra={"type": "pdf"},
        )
        print(f"  [ok-pdf] {slug}  ({len(r.content):,} bytes)")
        return "ok"
    else:
        if len(r.text) < MIN_BODY_TEXT:
            return "empty"
        text, title = extract_text(r.text)
        if len(text) < MIN_BODY_TEXT:
            return "empty"
        storage.save_text(rel_path, r.text)
        storage.save_text(relative_path_for(slug, "txt"), text)
        storage.append_index_record(
            source=SOURCE, key=slug, url=url, relative_path=rel_path,
            size_bytes=len(r.text.encode("utf-8")), sha256=sha256_text(text),
            extra={"type": "html", "title": title},
        )
        print(f"  [ok-html] {slug}  ({len(text):,} chars)")
        return "ok"


async def run(base_dir: Path, delay: float, max_pages: int) -> dict[str, int]:
    storage = LocalStorage(base_dir)
    already_done = storage.load_index_keys(SOURCE)
    stats: dict[str, int] = {}

    print("discovering MEF links...")
    items = await discover_links(max_pages=max_pages)
    print(f"discovered: {len(items)}")
    stats["discovered"] = len(items)

    async with make_async_client() as client:
        for url, ext in items:
            result = await process_item(client, url, ext, storage, already_done)
            stats[result] = stats.get(result, 0) + 1
            if result not in {"skip_done", "skip_exists"}:
                await polite_sleep(delay)
    return stats


def main() -> None:
    parser = base_parser("Scraper MEF web (gub.uy/ministerio-economia-finanzas)")
    parser.add_argument("--max-pages", type=int, default=50)
    args = parser.parse_args()
    base_dir = out_path(args)
    print(f"out: {base_dir}   delay: {args.delay}s   max_pages: {args.max_pages}")
    stats = asyncio.run(run(base_dir, args.delay, args.max_pages))
    print_summary(stats)


if __name__ == "__main__":
    main()
