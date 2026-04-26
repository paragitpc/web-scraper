from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.cli import base_parser, out_path, print_summary
from core.http_client import fetch, make_async_client, parse_impo_json_body, polite_sleep
from core.storage import LocalStorage, sha256_bytes

SOURCE = "impo_decretos"
URL_TEMPLATE = "https://www.impo.com.uy/bases/decretos/{n}-{y}?json=true"


def relative_dir(y: int, n: int) -> str:
    return f"{SOURCE}/{y:04d}/{n:05d}-{y:04d}"


def data_path_for(y: int, n: int) -> str:
    return f"{relative_dir(y, n)}/data.json"


def norm_has_content(data: object) -> bool:
    if not isinstance(data, dict):
        return False
    if (data.get("leyenda") or "").strip():
        return True
    arts = data.get("articulos")
    if isinstance(arts, list) and len(arts) > 0:
        return True
    return False


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

    rel_json = data_path_for(y, n)
    if storage.exists(rel_json):
        return "skip_exists"

    url = URL_TEMPLATE.format(n=n, y=y)

    try:
        r = await fetch(client, url)
    except Exception as exc:
        print(f"  [error] dec {key}: {type(exc).__name__}: {exc}")
        return "error"

    if r.status_code == 404:
        storage.append_index_record(
            source=SOURCE,
            key=key,
            url=url,
            relative_path="",
            size_bytes=0,
            sha256="",
            extra={"status": "not_found"},
        )
        return "not_found"

    if r.status_code != 200:
        return "http_error"

    parsed = parse_impo_json_body(r.content)
    if parsed is None or not norm_has_content(parsed):
        storage.append_index_record(
            source=SOURCE,
            key=key,
            url=url,
            relative_path="",
            size_bytes=0,
            sha256="",
            extra={"status": "empty"},
        )
        return "empty"

    assert isinstance(parsed, dict)
    written = storage.save_json(rel_json, parsed)
    raw = written.read_bytes()
    digest = sha256_bytes(raw)
    title = (parsed.get("leyenda") or None) if isinstance(parsed.get("leyenda"), str) else None
    extra: dict = {"year": y, "number": n}
    if title:
        extra["title"] = title.strip()[:500]
    if parsed.get("anioNorma") is not None:
        extra["anioNorma"] = parsed.get("anioNorma")
    if parsed.get("nroNorma") is not None:
        extra["nroNorma"] = parsed.get("nroNorma")

    storage.append_index_record(
        source=SOURCE,
        key=key,
        url=url,
        relative_path=rel_json,
        size_bytes=len(raw),
        sha256=digest,
        extra=extra,
    )
    print(f"  [ok] dec {key}")
    return "ok"


async def run(
    from_year: int,
    to_year: int,
    from_n: int,
    to_n: int,
    base_dir: Path,
    delay: float,
) -> dict[str, int]:
    storage = LocalStorage(base_dir)
    already_done = storage.load_index_keys(SOURCE)
    stats: dict[str, int] = {}

    async with make_async_client(
        headers={"Accept": "application/json, */*"},
    ) as client:
        for y in range(from_year, to_year + 1):
            for n in range(from_n, to_n + 1):
                result = await process_decree(client, n, y, storage, already_done)
                stats[result] = stats.get(result, 0) + 1
                if result not in {"skip_done", "skip_exists"}:
                    await polite_sleep(delay)

    return stats


def main() -> None:
    parser = base_parser("Scraper IMPO Decretos (JSON)")
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
