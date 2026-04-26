from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.storage import LocalStorage, sha256_bytes

SOURCE = "dgi_web"
BASE = "https://www.gub.uy"
BASE_DGI = BASE + "/direccion-general-impositiva"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
DEFAULT_DELAY = 1.5

SECTIONS = [
    ("noticias",        "/comunicacion/noticias",                           9),
    ("publicaciones",   "/comunicacion/publicaciones",                      9),
    ("boletines",       "/comunicacion/boletines",                          8),
    ("estadisticas",    "/datos-y-estadisticas/estadisticas",               6),
    ("datos",           "/datos-y-estadisticas/datos",                      2),
    ("tramites",        "/tramites-dgi",                                    1),
    ("trib_int",        "/tributacion-internacional",                       1),
    ("dj_formularios",  "/tematica/declaraciones-juradas-formularios-simuladores", 1),
    ("beneficios",      "/Beneficiostributarios",                           1),
    ("concursos",       "/politicas-y-gestion/concursos",                   1),
    ("adquisiciones",   "/institucional/adquisiciones",                     1),
    ("transparencia",   "/institucional/transparencia",                     1),
    ("info_gestion",    "/institucional/informacion-gestion",               1),
    ("plan_estrategico","/institucional/plan-estrategico",                  1),
    ("estructura",      "/institucional/estructura-del-organismo",          1),
    ("historia",        "/institucional/creacion-evolucion-historica",      1),
    ("cometidos",       "/institucional/cometidos",                         1),
    ("otros_sitios",    "/otros-sitios-dgi",                                1),
    ("formularios",     "/tematica/formularios-solicitudes",                1),
    ("calendario",      "/comunicacion/calendario-actividades",             1),
]

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=20),
    retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
    reraise=True,
)
async def fetch(client: httpx.AsyncClient, url: str) -> httpx.Response:
    return await client.get(url, follow_redirects=True)


def extract_links(html: str, section_path: str) -> list[str]:
    pattern = r'href="(' + re.escape(section_path) + r'/[^"?#]+)"'
    links = re.findall(pattern, html)
    return list(dict.fromkeys(links))


def slug_from_path(path: str) -> str:
    return path.strip("/").replace("/", "_")


async def process_page(
    client: httpx.AsyncClient,
    url: str,
    rel_path: str,
    storage: LocalStorage,
    already_done: set,
) -> str:
    key = slug_from_path(url.replace(BASE, ""))
    if key in already_done or storage.exists(rel_path):
        return "skip"

    try:
        r = await fetch(client, url)
    except Exception as e:
        print(f"  [error] {url}: {e}")
        return "error"

    if r.status_code != 200:
        return "http_error"

    content = r.content
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
    print(f"  [ok] {url} ({len(content):,} bytes)")
    return "ok"


async def run(base_dir: Path, delay: float, sections: list) -> dict:
    storage = LocalStorage(base_dir)
    already_done = storage.load_index_keys(SOURCE)
    stats: dict = {}

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,*/*",
        "Accept-Language": "es-UY,es;q=0.9",
    }

    async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
        for sec_name, sec_path, max_pages in sections:
            print(f"\n=== {sec_name} (max_pages={max_pages}) ===")

            # Descargar paginas del listado
            for page_num in range(max_pages):
                url = BASE_DGI + sec_path
                if page_num > 0:
                    url += f"?page={page_num}"

                rel_path = f"{SOURCE}/{sec_name}/index_page_{page_num}.html"
                result = await process_page(client, url, rel_path, storage, already_done)
                stats[result] = stats.get(result, 0) + 1
                if result not in ("skip",):
                    await asyncio.sleep(delay)

                # Extraer links de articulos individuales
                if storage.exists(rel_path):
                    html = open(base_dir / rel_path, encoding="utf-8", errors="replace").read()
                    article_links = extract_links(html, "/direccion-general-impositiva" + sec_path)

                    for art_path in article_links:
                        art_url = BASE + art_path
                        art_slug = slug_from_path(art_path)
                        art_rel = f"{SOURCE}/{sec_name}/articles/{art_slug}.html"
                        result2 = await process_page(client, art_url, art_rel, storage, already_done)
                        stats[result2] = stats.get(result2, 0) + 1
                        if result2 not in ("skip",):
                            await asyncio.sleep(delay)

    return stats


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/output")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    parser.add_argument("--sections", default="all")
    return parser.parse_args()


def main():
    args = parse_args()
    base_dir = Path(args.out).expanduser().resolve()

    if args.sections == "all":
        secs = SECTIONS
    else:
        names = args.sections.split(",")
        secs = [s for s in SECTIONS if s[0] in names]

    print(f"DGI web scraper  sections={len(secs)}  delay={args.delay}s")
    stats = asyncio.run(run(base_dir, args.delay, secs))

    print("\nsummary:")
    for k, v in sorted(stats.items()):
        print(f"  {k:15s} {v}")


if __name__ == "__main__":
    main()
