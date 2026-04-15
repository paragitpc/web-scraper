from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.storage import LocalStorage, sha256_bytes


SOURCE = "impo_diariooficial"
URL_TEMPLATE = "https://www.impo.com.uy/diariooficial/{y:04d}/{m:02d}/{d:02d}/documentos.pdf"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
DEFAULT_TIMEOUT = 60.0
DEFAULT_DELAY = 1.5
MIN_PDF_BYTES = 1024
NO_EDITION_CONTENT_TYPES = ("text/plain", "text/html")


def daterange(start: date, end: date):
    days = (end - start).days
    for i in range(days + 1):
        yield start + timedelta(days=i)


def relative_path_for(d: date) -> str:
    return f"{SOURCE}/{d.year:04d}/{d.month:02d}/{d.isoformat()}.pdf"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
    reraise=True,
)
async def fetch_pdf(client: httpx.AsyncClient, url: str) -> httpx.Response:
    return await client.get(url, follow_redirects=True)


async def process_date(
    client: httpx.AsyncClient,
    d: date,
    storage: LocalStorage,
    already_done: set[str],
) -> str:
    key = d.isoformat()
    if key in already_done:
        return "skip_done"

    rel_path = relative_path_for(d)
    if storage.exists(rel_path):
        return "skip_exists"

    url = URL_TEMPLATE.format(y=d.year, m=d.month, d=d.day)

    try:
        response = await fetch_pdf(client, url)
    except Exception as exc:
        print(f"  [error] {key}: {type(exc).__name__}: {exc}")
        return "error"

    if response.status_code == 404:
        return "not_found"

    if response.status_code != 200:
        print(f"  [http {response.status_code}] {key}")
        return "http_error"

    content_type = response.headers.get("content-type", "").lower()
    content = response.content

    is_no_edition = (
        len(content) == 0
        or any(ct in content_type for ct in NO_EDITION_CONTENT_TYPES)
    )
    if is_no_edition:
        storage.append_index_record(
            source=SOURCE,
            key=key,
            url=url,
            relative_path="",
            size_bytes=0,
            sha256="",
            extra={"status": "no_edition"},
        )
        return "no_edition"

    if len(content) < MIN_PDF_BYTES:
        return "too_small"

    if not content.startswith(b"%PDF"):
        return "not_pdf"

    saved = storage.save_bytes(rel_path, content)
    digest = sha256_bytes(content)
    storage.append_index_record(
        source=SOURCE,
        key=key,
        url=url,
        relative_path=str(saved.relative_to(storage.base_dir)),
        size_bytes=len(content),
        sha256=digest,
    )
    print(f"  [ok] {key}  ({len(content):,} bytes)")
    return "ok"


async def run(start: date, end: date, base_dir: Path, delay: float) -> dict[str, int]:
    storage = LocalStorage(base_dir)
    already_done = storage.load_index_keys(SOURCE)
    stats: dict[str, int] = {}

    headers = {"User-Agent": USER_AGENT, "Accept": "application/pdf,*/*"}
    timeout = httpx.Timeout(DEFAULT_TIMEOUT)

    async with httpx.AsyncClient(headers=headers, timeout=timeout) as client:
        for d in daterange(start, end):
            result = await process_date(client, d, storage, already_done)
            stats[result] = stats.get(result, 0) + 1
            if result not in {"skip_done", "skip_exists"}:
                await asyncio.sleep(delay)

    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--out", default="data/output", help="base output dir")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()
    if start > end:
        raise SystemExit("start must be <= end")

    base_dir = Path(args.out).expanduser().resolve()
    print(f"range: {start} .. {end}   out: {base_dir}   delay: {args.delay}s")

    stats = asyncio.run(run(start, end, base_dir, args.delay))

    print("\nsummary:")
    for k in sorted(stats.keys()):
        print(f"  {k:15s} {stats[k]}")


if __name__ == "__main__":
    main()
