from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.cli import base_parser, out_path, print_summary
from core.http_client import fetch, make_async_client, polite_sleep
from core.storage import LocalStorage, sha256_text, sha256_bytes


SOURCE = "dgi_web"
BASE = "https://www.dgi.gub.uy"

# AJUSTAR: las URLs reales pueden cambiar. Verificar contra el sitio.
SECTIONS = {
    "calendario": f"{BASE}/wdgi/page?2,principal,calendario,O,es,0,",
    "cotizaciones": f"{BASE}/wdgi/page?2,principal,cotizaciones,O,es,0,",
    "formularios": f"{BASE}/wdgi/page?2,principal,formularios,O,es,0,",
    "instructivos": f"{BASE}/wdgi/page?2,principal,instructivos,O,es,0,",
}

MIN_BODY_TEXT = 150


def section_path(section: str, slug: str, ext: str = "html") -> str:
    safe = slug.replace("/", "_").replace("?", "_").strip("_")[:200]
    return f"{SOURCE}/{section}/{safe}.{ext}"


def slug_from_url(url: str) -> str:
    parsed = urlparse(url)
    base = parsed.path.replace("/", "_")
    if parsed.query:
        base += "_" + parsed.query.replace("&", "_").replace("=", "-")
    return base.strip("_")[:200] or "root"


def extract_text(html: str) -> tuple[str, str | None]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    title = None
    h1 = soup.find("h1") or soup.find("h2") or soup.find("title")
    if h1:
        title = h1.get_text(strip=True)
    return soup.get_text("\n", strip=True), title


async def discover_in_section(section_url: str, max_depth: int = 2) -> list[tuple[str, str]]:
    """Devuelve lista de (url, ext) — ext es 'pdf' o 'html'."""
    found: set[tuple[str, str]] = set()
    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(section_url, 0)]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await (await browser.new_context()).new_page()

        while queue:
            url, depth = queue.pop(0)
            if url in visited or depth > max_depth:
                continue
            visited.add(url)
            try:
                await page.goto(url, wait_until="networkidle", timeout=60000)
            except Exception:
                continue

            anchors = await page.eval_on_selector_all(
                "a[href]", "els => els.map(e => e.href)"
            )
            for href in anchors:
                if not href or href.startswith("javascript:"):
                    continue
                if "dgi.gub.uy" not in href:
                    continue
                if href.lower().endswith(".pdf"):
                    found.add((href, "pdf"))
                elif "page?" in href or "wdgi" in href:
                    found.add((href, "html"))
                    if depth < max_depth:
                        queue.append((href, depth + 1))

        await browser.close()
    return sorted(found)


async def process_item(
    client, url: str, ext: str, section: str,
    storage: LocalStorage, already_done: set[str],
) -> str:
    slug = f"{section}__{slug_from_url(url)}"
    if slug in already_done:
        return "skip_done"
    rel_path = section_path(section, slug_from_url(url), ext=ext)
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
            extra={"section": section, "type": "pdf"},
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
        storage.save_text(section_path(section, slug_from_url(url), ext="txt"), text)
        storage.append_index_record(
            source=SOURCE, key=slug, url=url, relative_path=rel_path,
            size_bytes=len(r.text.encode("utf-8")), sha256=sha256_text(text),
            extra={"section": section, "type": "html", "title": title},
        )
        print(f"  [ok-html] {slug}  ({len(text):,} chars)")
        return "ok"


async def run(sections: list[str], base_dir: Path, delay: float, max_depth: int) -> dict[str, int]:
    storage = LocalStorage(base_dir)
    already_done = storage.load_index_keys(SOURCE)
    stats: dict[str, int] = {}

    all_items: list[tuple[str, str, str]] = []
    for section in sections:
        if section not in SECTIONS:
            print(f"  [skip] unknown section: {section}")
            continue
        print(f"discovering section: {section}")
        items = await discover_in_section(SECTIONS[section], max_depth=max_depth)
        for url, ext in items:
            all_items.append((url, ext, section))
        print(f"  found: {len(items)}")
        stats[f"discovered_{section}"] = len(items)

    async with make_async_client() as client:
        for url, ext, section in all_items:
            result = await process_item(client, url, ext, section, storage, already_done)
            stats[result] = stats.get(result, 0) + 1
            if result not in {"skip_done", "skip_exists"}:
                await polite_sleep(delay)
    return stats


def main() -> None:
    parser = base_parser("Scraper DGI website (calendario, cotizaciones, formularios, instructivos)")
    parser.add_argument(
        "--sections", nargs="+", default=list(SECTIONS.keys()),
        help=f"Secciones a scrapear. Default: todas. Disponibles: {list(SECTIONS.keys())}",
    )
    parser.add_argument("--max-depth", type=int, default=2)
    args = parser.parse_args()
    base_dir = out_path(args)
    print(f"sections: {args.sections}   out: {base_dir}   delay: {args.delay}s   max_depth: {args.max_depth}")
    stats = asyncio.run(run(args.sections, base_dir, args.delay, args.max_depth))
    print_summary(stats)


if __name__ == "__main__":
    main()
