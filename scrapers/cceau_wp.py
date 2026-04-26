from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.storage import LocalStorage, sha256_bytes

SOURCE = "cceau_wp"
BASE = "https://ccea.com.uy/wp-json/wp/v2"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
DEFAULT_DELAY = 1.0
PER_PAGE = 100

TYPES = {
    "posts":    "noticias",
    "pages":    "paginas",
    "items":    "boletin",
    "comisiones": "comisiones",
    "grupos-de-trabajo": "grupos_trabajo",
}

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=20),
    retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
    reraise=True,
)
async def fetch(client: httpx.AsyncClient, url: str) -> httpx.Response:
    return await client.get(url, follow_redirects=True)


async def scrape_type(client, wp_type, type_name, storage, already_done, delay):
    stats = {"ok": 0, "skip": 0, "error": 0}
    page = 1

    while True:
        url = f"{BASE}/{wp_type}?per_page={PER_PAGE}&page={page}&_embed=false"
        try:
            r = await fetch(client, url)
        except Exception as e:
            print(f"  [error] pagina {page}: {e}")
            break

        if r.status_code == 400:
            break
        if r.status_code != 200:
            print(f"  [http {r.status_code}] pagina {page}")
            break

        items = r.json()
        if not items:
            break

        total = int(r.headers.get("x-wp-total", 0))
        total_pages = int(r.headers.get("x-wp-totalpages", 1))
        print(f"  [page {page}/{total_pages}] {len(items)} items (total: {total})")

        for item in items:
            slug = item.get("slug", str(item.get("id", "")))
            key = f"{type_name}_{slug}"

            if key in already_done:
                stats["skip"] += 1
                continue

            rel_path = f"{SOURCE}/{type_name}/{slug}.json"
            if storage.exists(rel_path):
                stats["skip"] += 1
                continue

            content = json.dumps(item, ensure_ascii=False, indent=2).encode("utf-8")
            saved = storage.save_bytes(rel_path, content)
            digest = sha256_bytes(content)
            storage.append_index_record(
                source=SOURCE,
                key=key,
                url=item.get("link", ""),
                relative_path=str(saved.relative_to(storage.base_dir)),
                size_bytes=len(content),
                sha256=digest,
                extra={
                    "type": type_name,
                    "title": item.get("title", {}).get("rendered", "")[:100],
                    "date": item.get("date", ""),
                },
            )
            title = item.get("title", {}).get("rendered", "")[:60]
            print(f"  [ok] {slug} - {title}")
            stats["ok"] += 1
            await asyncio.sleep(delay)

        if page >= total_pages:
            break
        page += 1

    return stats


async def run(base_dir, delay, types):
    storage = LocalStorage(base_dir)
    already_done = storage.load_index_keys(SOURCE)
    total_stats = {"ok": 0, "skip": 0, "error": 0}

    headers = {"User-Agent": USER_AGENT}
    async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
        for wp_type, type_name in types.items():
            print(f"\n=== {type_name} ({wp_type}) ===")
            stats = await scrape_type(client, wp_type, type_name, storage, already_done, delay)
            for k, v in stats.items():
                total_stats[k] = total_stats.get(k, 0) + v

    return total_stats


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--types", default="all")
    parser.add_argument("--out", default="data/output")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    return parser.parse_args()


def main():
    args = parse_args()
    base_dir = Path(args.out).expanduser().resolve()

    if args.types == "all":
        types = TYPES
    else:
        names = args.types.split(",")
        types = {k: v for k, v in TYPES.items() if k in names or v in names}

    print(f"CCEAU WP scraper  types={list(types.keys())}  delay={args.delay}s")
    stats = asyncio.run(run(base_dir, args.delay, types))

    print("\nsummary:")
    for k, v in sorted(stats.items()):
        print(f"  {k:15s} {v}")


if __name__ == "__main__":
    main()
