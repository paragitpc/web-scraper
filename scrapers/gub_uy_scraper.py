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

SOURCE_PREFIX = "gub_uy"
BASE = "https://www.gub.uy"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
DEFAULT_DELAY = 1.5

ORGANISMS = {
    "mef": {
        "base_path": "/ministerio-economia-finanzas",
        "sections": [
            ("noticias",      "/comunicacion/noticias",      9),
            ("publicaciones", "/comunicacion/publicaciones", 9),
            ("ain",           "/auditoria-interna-nacion",   1),
            ("defensa_competencia", "/defensa-de-la-competencia", 1),
            ("tesoreria",     "/tesoreria-general-nacion",   1),
            ("defensa_consumidor", "/unidad-defensa-consumidor", 1),
        ]
    },
    "bps": {
        "base_path": "/banco-de-prevision-social",
        "sections": [
            ("noticias",      "/comunicacion/noticias",      10),
            ("publicaciones", "/comunicacion/publicaciones", 5),
            ("normativa",     "/normativa",                  5),
        ]
    },
    "mtss": {
        "base_path": "/ministerio-trabajo-seguridad-social",
        "sections": [
            ("noticias",          "/comunicacion/noticias",                              10),
            ("publicaciones",     "/comunicacion/publicaciones",                         5),
            ("comunicados",       "/comunicacion/comunicados",                           5),
            ("convocatorias",     "/comunicacion/convocatorias",                         3),
            ("normativa",         "/institucional/normativa",                            5),
            ("consejos_salarios", "/tematica/consejos-salarios-negociacion-colectiva",   3),
            ("tramites",          "/tramites-y-servicios/tramites",                      1),
            ("transparencia",     "/institucional/transparencia",                        1),
            ("info_gestion",      "/institucional/informacion-gestion",                  1),
        ]
    },
    "senaclaft": {
        "base_path": "/sistema-nacional-antilavado-activos",
        "sections": [
            ("noticias",      "/comunicacion/noticias",      5),
            ("normativa",     "/normativa",                  5),
            ("publicaciones", "/comunicacion/publicaciones", 3),
        ]
    },
    "urcdp": {
        "base_path": "/unidad-reguladora-control-datos-personales",
        "sections": [
            ("noticias",      "/comunicacion/noticias",      5),
            ("normativa",     "/normativa",                  5),
            ("resoluciones",  "/resoluciones",               5),
        ]
    },
}

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=20),
    retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
    reraise=True,
)
async def fetch(client: httpx.AsyncClient, url: str) -> httpx.Response:
    return await client.get(url, follow_redirects=True)


def extract_article_links(html: str, base_path: str) -> list[str]:
    pattern = r'href="(' + re.escape(base_path) + r'/[^"?#]+)"'
    links = re.findall(pattern, html)
    links = [l for l in links if l.count('/') >= 4]
    links = [l for l in links if not any(x in l for x in ['css','js','png','ico','jpg','favicon','ayudanos','mapa-sitio','terminos','privacidad','accesibilidad'])]
    return list(dict.fromkeys(links))


async def process_url(client, url, rel_path, storage, already_done):
    key = url.replace(BASE, "").strip("/").replace("/", "_")
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
        source=SOURCE_PREFIX + "_" + rel_path.split("/")[1],
        key=key,
        url=url,
        relative_path=str(saved.relative_to(storage.base_dir)),
        size_bytes=len(content),
        sha256=digest,
    )
    print(f"  [ok] {url} ({len(content):,} bytes)")
    return "ok"


async def run(base_dir, delay, organisms):
    storage = LocalStorage(base_dir)
    already_done = storage.load_index_keys(SOURCE_PREFIX)
    stats = {}

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,*/*",
        "Accept-Language": "es-UY,es;q=0.9",
    }

    async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
        for org_name, org_config in organisms.items():
            base_path = org_config["base_path"]
            print(f"\n{'='*50}")
            print(f"ORGANISMO: {org_name} ({base_path})")

            for sec_name, sec_path, max_pages in org_config["sections"]:
                print(f"\n  --- {sec_name} (max_pages={max_pages}) ---")

                for page_num in range(max_pages):
                    url = BASE + base_path + sec_path
                    if page_num > 0:
                        url += f"?page={page_num}"

                    rel_path = f"{SOURCE_PREFIX}/{org_name}/{sec_name}/index_page_{page_num}.html"
                    result = await process_url(client, url, rel_path, storage, already_done)
                    stats[result] = stats.get(result, 0) + 1
                    if result not in ("skip",):
                        await asyncio.sleep(delay)

                    if storage.exists(rel_path):
                        html = open(base_dir / rel_path, encoding="utf-8", errors="replace").read()
                        article_links = extract_article_links(html, base_path)
                        for art_path in article_links:
                            art_url = BASE + art_path
                            art_slug = art_path.strip("/").replace("/", "_")
                            art_rel = f"{SOURCE_PREFIX}/{org_name}/{sec_name}/articles/{art_slug}.html"
                            result2 = await process_url(client, art_url, art_rel, storage, already_done)
                            stats[result2] = stats.get(result2, 0) + 1
                            if result2 not in ("skip",):
                                await asyncio.sleep(delay)

    return stats


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--organisms", default="all")
    parser.add_argument("--out", default="data/output")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    return parser.parse_args()


def main():
    args = parse_args()
    base_dir = Path(args.out).expanduser().resolve()

    if args.organisms == "all":
        orgs = ORGANISMS
    else:
        names = args.organisms.split(",")
        orgs = {k: v for k, v in ORGANISMS.items() if k in names}

    print(f"gub.uy scraper  organisms={list(orgs.keys())}  delay={args.delay}s")
    stats = asyncio.run(run(base_dir, args.delay, orgs))

    print("\nsummary:")
    for k, v in sorted(stats.items()):
        print(f"  {k:15s} {v}")


if __name__ == "__main__":
    main()
