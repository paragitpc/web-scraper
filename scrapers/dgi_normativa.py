from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.storage import LocalStorage, sha256_bytes


SOURCE = "dgi_normativa"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
DEFAULT_TIMEOUT = 120.0
DEFAULT_DELAY = 2.0
MIN_PDF_BYTES = 1024

PDF_DOCUMENTS = [
    (
        "to_dgi_2023",
        "https://medios.presidencia.gub.uy/legal/2024/decretos/04/mef_1273.pdf",
        "Texto Ordenado DGI 2023 - Decreto 101/024 de 04/04/2024",
    ),
]

HTML_PAGES = [
    (
        "consultas_escritas",
        "https://www.gub.uy/direccion-general-impositiva/comunicacion/publicaciones/consultas-escritas-publicaciones",
        "Requisitos consultas tributarias vinculantes y no vinculantes",
    ),
    (
        "vencimientos_2025",
        "https://www.gub.uy/direccion-general-impositiva/comunicacion/publicaciones/vencimientos-2025-calendario-general-actualizado",
        "Calendario de vencimientos 2025",
    ),
    (
        "beneficios_tributarios",
        "https://www.gub.uy/direccion-general-impositiva/Beneficiostributarios",
        "Beneficios tributarios DGI",
    ),
    (
        "tributacion_internacional",
        "https://www.gub.uy/direccion-general-impositiva/tributacion-internacional",
        "Tributacion internacional DGI",
    ),
    (
        "medios_pago",
        "https://www.gub.uy/direccion-general-impositiva/comunicacion/publicaciones/medios-pago",
        "Medios de pago DGI",
    ),
    (
        "correlacion_to2023_to1996",
        "https://www.gub.uy/direccion-general-impositiva/comunicacion/publicaciones/correlacion-articulos-entre-to-2023-to-1996",
        "Correlacion articulos TO2023 a TO1996",
    ),
    (
        "correlacion_to1996_to2023",
        "https://www.gub.uy/direccion-general-impositiva/comunicacion/publicaciones/correlacion-articulos-entre-to-1996-to-2023",
        "Correlacion articulos TO1996 a TO2023",
    ),
]


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
    reraise=True,
)
async def fetch_url(client: httpx.AsyncClient, url: str) -> httpx.Response:
    return await client.get(url, follow_redirects=True)


async def process_pdf(
    client: httpx.AsyncClient,
    key: str,
    url: str,
    description: str,
    storage: LocalStorage,
    already_done: set[str],
    delay: float,
) -> str:
    if key in already_done:
        return "skip_done"

    rel_path = f"{SOURCE}/pdf/{key}.pdf"
    if storage.exists(rel_path):
        return "skip_exists"

    print(f"  [pdf] {key} ...")
    try:
        response = await fetch_url(client, url)
    except Exception as exc:
        print(f"  [error] {key}: {type(exc).__name__}: {exc}")
        return "error"

    if response.status_code != 200:
        print(f"  [http {response.status_code}] {key}")
        return "http_error"

    content = response.content
    if len(content) < MIN_PDF_BYTES or not content.startswith(b"%PDF"):
        print(f"  [not_pdf] {key} ({len(content)} bytes)")
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
        extra={"type": "pdf", "description": description},
    )
    print(f"  [ok] {key}  ({len(content):,} bytes)")
    await asyncio.sleep(delay)
    return "ok"


async def process_html(
    client: httpx.AsyncClient,
    key: str,
    url: str,
    description: str,
    storage: LocalStorage,
    already_done: set[str],
    delay: float,
) -> str:
    if key in already_done:
        return "skip_done"

    rel_path = f"{SOURCE}/html/{key}.html"
    if storage.exists(rel_path):
        return "skip_exists"

    print(f"  [html] {key} ...")
    try:
        response = await fetch_url(client, url)
    except Exception as exc:
        print(f"  [error] {key}: {type(exc).__name__}: {exc}")
        return "error"

    if response.status_code != 200:
        print(f"  [http {response.status_code}] {key}")
        return "http_error"

    content = response.content
    if len(content) < 100:
        return "too_small"

    saved = storage.save_bytes(rel_path, content)
    digest = sha256_bytes(content)
    storage.append_index_record(
        source=SOURCE,
        key=key,
        url=url,
        relative_path=str(saved.relative_to(storage.base_dir)),
        size_bytes=len(content),
        sha256=digest,
        extra={"type": "html", "description": description},
    )
    print(f"  [ok] {key}  ({len(content):,} bytes)")
    await asyncio.sleep(delay)
    return "ok"


async def run(base_dir: Path, delay: float, mode: str) -> dict[str, int]:
    storage = LocalStorage(base_dir)
    already_done = storage.load_index_keys(SOURCE)
    stats: dict[str, int] = {}

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/pdf,*/*",
        "Accept-Language": "es-UY,es;q=0.9",
    }
    timeout = httpx.Timeout(DEFAULT_TIMEOUT)

    async with httpx.AsyncClient(headers=headers, timeout=timeout) as client:

        if mode in ("all", "pdf"):
            print(f"\n--- PDFs ({len(PDF_DOCUMENTS)}) ---")
            for key, url, desc in PDF_DOCUMENTS:
                result = await process_pdf(client, key, url, desc, storage, already_done, delay)
                stats[result] = stats.get(result, 0) + 1

        if mode in ("all", "html"):
            print(f"\n--- HTML pages ({len(HTML_PAGES)}) ---")
            for key, url, desc in HTML_PAGES:
                result = await process_html(client, key, url, desc, storage, already_done, delay)
                stats[result] = stats.get(result, 0) + 1

    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="scraper")
    parser.add_argument(
        "--mode",
        choices=["all", "pdf", "html"],
        default="all",
        help="mode",
    )
    parser.add_argument("--out", default="data/output", help="base output dir")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    base_dir = Path(args.out).expanduser().resolve()
    print(f"DGI normativa scraper  mode={args.mode}  out={base_dir}  delay={args.delay}s")

    stats = asyncio.run(run(base_dir, args.delay, args.mode))

    print("\nsummary:")
    for k in sorted(stats.keys()):
        print(f"  {k:15s} {stats[k]}")


if __name__ == "__main__":
    main()
