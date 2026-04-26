from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.cli import add_id_range, base_parser, out_path, print_summary
from core.http_client import fetch, make_async_client, parse_impo_json_body, polite_sleep
from core.storage import LocalStorage, sha256_bytes

SOURCE = "impo_leyes"
URL_TEMPLATE = "https://www.impo.com.uy/bases/leyes-originales/{n}-2025?json=true"


def data_path_for(n: int) -> str:
    return f"{SOURCE}/{n:05d}/data.json"


def norm_has_content(data: object) -> bool:
    if not isinstance(data, dict):
        return False
    if (data.get("leyenda") or "").strip():
        return True
    arts = data.get("articulos")
    if isinstance(arts, list) and len(arts) > 0:
        return True
    return False


async def process_id(
    client: httpx.AsyncClient,
    n: int,
    storage: LocalStorage,
    already_done: set[str],
) -> str:
    key = str(n)
    if key in already_done:
        return "skip_done"

    rel_json = data_path_for(n)
    if storage.exists(rel_json):
        return "skip_exists"

    url = URL_TEMPLATE.format(n=n)

    try:
        r = await fetch(client, url)
    except Exception as exc:
        print(f"  [error] ley {n}: {type(exc).__name__}: {exc}")
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
    extra: dict = {}
    if title:
        extra["title"] = title.strip()[:500]
    if parsed.get("anioNorma") is not None:
        extra["year"] = parsed.get("anioNorma")
    if parsed.get("nroNorma") is not None:
        extra["number"] = parsed.get("nroNorma")

    storage.append_index_record(
        source=SOURCE,
        key=key,
        url=url,
        relative_path=rel_json,
        size_bytes=len(raw),
        sha256=digest,
        extra=extra or None,
    )
    print(f"  [ok] ley {n}")
    return "ok"


async def run(from_id: int, to_id: int, base_dir: Path, delay: float) -> dict[str, int]:
    storage = LocalStorage(base_dir)
    already_done = storage.load_index_keys(SOURCE)
    stats: dict[str, int] = {}

    async with make_async_client(
        headers={"Accept": "application/json, */*"},
    ) as client:
        for n in range(from_id, to_id + 1):
            result = await process_id(client, n, storage, already_done)
            stats[result] = stats.get(result, 0) + 1
            if result not in {"skip_done", "skip_exists"}:
                await polite_sleep(delay)

    return stats


def main() -> None:
    parser = base_parser("Scraper IMPO Leyes (JSON)")
    add_id_range(parser, default_min=1)
    args = parser.parse_args()
    base_dir = out_path(args)
    print(f"range: {args.from_id} .. {args.to_id}   out: {base_dir}   delay: {args.delay}s")
    stats = asyncio.run(run(args.from_id, args.to_id, base_dir, args.delay))
    print_summary(stats)


if __name__ == "__main__":
    main()
