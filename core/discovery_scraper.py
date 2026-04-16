from __future__ import annotations

import asyncio
import re
import sys
from abc import abstractmethod
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.http_client import fetch, make_async_client, polite_sleep
from core.storage import LocalStorage, sha256_bytes, sha256_text


class DiscoveryScraper:
    """Base class for sites where URLs are discovered (not predictable).

    Subclasses must define:
        SOURCE: str
        START_URLS: list[str]
        ALLOWED_DOMAIN: str
        URL_PATTERNS: list[str]  (substrings that identify item URLs)
    Optional:
        MIN_BODY_TEXT: int = 200
        MAX_DEPTH: int = 1
        FOLLOW_PAGINATION: bool = True
    """

    SOURCE: str = ""
    START_URLS: list[str] = []
    ALLOWED_DOMAIN: str = ""
    URL_PATTERNS: list[str] = []
    MIN_BODY_TEXT: int = 200
    MAX_DEPTH: int = 1
    FOLLOW_PAGINATION: bool = True
    PAGINATION_SELECTORS: tuple[str, ...] = (
        "a[rel='next']",
        "a.next",
        "a:has-text('Siguiente')",
        "a:has-text('Próxima')",
        "li.next a",
    )

    def __init__(self, base_dir: str | Path, delay: float = 1.5) -> None:
        if not self.SOURCE:
            raise ValueError("subclass must set SOURCE")
        self.delay = delay
        self.storage = LocalStorage(base_dir)

    def slug_from_url(self, url: str) -> str:
        p = urlparse(url)
        s = (p.path + ("_" + p.query if p.query else "")).replace("/", "_").replace("?", "_").replace("&", "_").replace("=", "-")
        return re.sub(r"[^A-Za-z0-9._-]", "_", s).strip("_")[:200] or "root"

    def detect_ext(self, url: str) -> str:
        return "pdf" if url.lower().split("?")[0].endswith(".pdf") else "html"

    def relative_path(self, slug: str, ext: str) -> str:
        bucket = slug[:2] if slug else "_"
        return f"{self.SOURCE}/{bucket}/{slug}.{ext}"

    def url_matches(self, url: str) -> bool:
        if not url or url.startswith("javascript:") or url.startswith("mailto:"):
            return False
        if self.ALLOWED_DOMAIN and self.ALLOWED_DOMAIN not in url:
            return False
        if not self.URL_PATTERNS:
            return True
        return any(pat in url for pat in self.URL_PATTERNS)

    def extract_text(self, html: str) -> tuple[str, str | None]:
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
            tag.decompose()
        title = None
        h = soup.find("h1") or soup.find("h2") or soup.find("title")
        if h:
            title = h.get_text(strip=True)
        return soup.get_text("\n", strip=True), title

    async def discover(self) -> list[str]:
        found: set[str] = set()
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await (await browser.new_context()).new_page()

            for start_url in self.START_URLS:
                try:
                    await page.goto(start_url, wait_until="networkidle", timeout=90000)
                except Exception as e:
                    print(f"  [discover-error] {start_url}: {e}")
                    continue

                page_count = 0
                while True:
                    page_count += 1
                    anchors = await page.eval_on_selector_all(
                        "a[href]", "els => els.map(e => e.href)"
                    )
                    for href in anchors:
                        if self.url_matches(href):
                            found.add(href)

                    if not self.FOLLOW_PAGINATION:
                        break

                    next_btn = None
                    for sel in self.PAGINATION_SELECTORS:
                        try:
                            next_btn = await page.query_selector(sel)
                            if next_btn:
                                break
                        except Exception:
                            continue
                    if not next_btn:
                        break
                    try:
                        await next_btn.click()
                        await page.wait_for_load_state("networkidle", timeout=60000)
                    except Exception:
                        break

            await browser.close()
        return sorted(found)

    async def fetch_and_store(self, client, url: str, already_done: set[str]) -> str:
        slug = self.slug_from_url(url)
        if slug in already_done:
            return "skip_done"
        ext = self.detect_ext(url)
        rel = self.relative_path(slug, ext)
        if self.storage.exists(rel):
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
            self.storage.save_bytes(rel, r.content)
            self.storage.append_index_record(
                source=self.SOURCE, key=slug, url=url, relative_path=rel,
                size_bytes=len(r.content), sha256=sha256_bytes(r.content),
                extra={"type": "pdf"},
            )
            print(f"  [ok-pdf] {slug}  ({len(r.content):,} bytes)")
            return "ok"

        if len(r.text) < self.MIN_BODY_TEXT:
            return "empty"
        text, title = self.extract_text(r.text)
        if len(text) < self.MIN_BODY_TEXT:
            return "empty"

        self.storage.save_text(rel, r.text)
        self.storage.save_text(self.relative_path(slug, "txt"), text)
        self.storage.append_index_record(
            source=self.SOURCE, key=slug, url=url, relative_path=rel,
            size_bytes=len(r.text.encode("utf-8")), sha256=sha256_text(text),
            extra={"type": "html", "title": title},
        )
        print(f"  [ok-html] {slug}  ({len(text):,} chars)")
        return "ok"

    async def run(self) -> dict[str, int]:
        already_done = self.storage.load_index_keys(self.SOURCE)
        stats: dict[str, int] = {}

        print(f"[{self.SOURCE}] discovering...")
        urls = await self.discover()
        print(f"[{self.SOURCE}] discovered: {len(urls)}")
        stats["discovered"] = len(urls)

        async with make_async_client() as client:
            for url in urls:
                result = await self.fetch_and_store(client, url, already_done)
                stats[result] = stats.get(result, 0) + 1
                if result not in {"skip_done", "skip_exists"}:
                    await polite_sleep(self.delay)
        return stats


def run_discovery_scraper(scraper_cls, args) -> None:
    scraper = scraper_cls(base_dir=args.out, delay=args.delay)
    if hasattr(args, "max_pages"):
        if hasattr(scraper, "MAX_PAGES_OVERRIDE"):
            pass
    stats = asyncio.run(scraper.run())
    from core.cli import print_summary
    print_summary(stats)
