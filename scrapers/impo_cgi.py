
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from playwright.async_api import async_playwright
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.storage import LocalStorage, sha256_bytes

SOURCE = "impo_cgi"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
DEFAULT_DELAY = 2.0

CATEGORIES = {
    "1":    "todo",
    "2":    "normativa_otros",
    "3":    "avisos",
    "4":    "constitucion",
    "5":    "leyes",
    "6":    "decretos",
    "7":    "resoluciones",
    "8":    "codigos",
    "9":    "textos_ordenados",
    "10":   "normas_internacionales",
    "11":   "reglamentos",
    "379":  "asse",
    "14":   "bcu",
    "15":   "dgi",
    "12":   "intendencias",
    "16":   "suprema_corte",
    "13":   "tribunal_cuentas",
    "1108": "tca_sentencias",
}

async def get_session_and_search(playwright, category_value: str, delay: float) -> list[dict]:
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(user_agent=USER_AGENT)
    page = await context.new_page()

    print(f"  [session] obteniendo sesion...")
    await page.goto("https://www.impo.com.uy/", wait_until="networkidle", timeout=30000)
    await page.goto("https://www.impo.com.uy/bases", wait_until="networkidle", timeout=30000)
    await asyncio.sleep(3)

    frame = page.main_frame
    await frame.select_option("select", category_value)
    await asyncio.sleep(1)
    await frame.evaluate("document.querySelector('input[type=submit]').click()")
    await page.wait_for_load_state("networkidle", timeout=30000)
    await asyncio.sleep(4)

    html = await page.content()
    links = re.findall(r'href="(/bases/[^"]+)"[^>]*>', html)
    links = [l for l in links if not l.endswith("/bases")]
    links = list(dict.fromkeys(links))  # dedup preservando orden
    print(f"  [search] {len(links)} documentos encontrados")

    # Obtener cookies para httpx
    cookies = await context.cookies()
    cookie_dict = {c["name"]: c["value"] for c in cookies}

    await browser.close()
    return links, cookie_dict


async def fetch_json(url: str, cookie_dict: dict, delay: float) -> dict | None:
    headers = {
        "User-Agent": USER_AGENT,
        "Cookie": "; ".join(f"{k}={v}" for k, v in cookie_dict.items()),
    }
    async with httpx.AsyncClient(headers=headers, timeout=60.0) as client:
        full_url = f"https://www.impo.com.uy{url}?json=true"
        try:
            r = await client.get(full_url, follow_redirects=True)
            if r.status_code != 200:
                return None
            raw = r.content.decode("latin-1")
            if not raw.strip().startswith("{"):
                return None
            raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x0d]", "", raw)
            return json.loads(raw)
        except Exception as e:
            print(f"  [error] {url}: {e}")
            return None


async def run(categories: list[str], base_dir: Path, delay: float) -> dict:
    storage = LocalStorage(base_dir)
    already_done = storage.load_index_keys(SOURCE)
    stats = {"ok": 0, "skip": 0, "error": 0, "no_json": 0}

    async with async_playwright() as playwright:
        for cat_value in categories:
            cat_name = CATEGORIES.get(cat_value, f"cat_{cat_value}")
            print(f"\n=== Categoria: {cat_name} (value={cat_value}) ===")

            links, cookie_dict = await get_session_and_search(playwright, cat_value, delay)

            for url in links:
                # Clave unica basada en la URL
                key = url.strip("/").replace("/", "_")

                if key in already_done:
                    stats["skip"] += 1
                    continue

                rel_path = f"{SOURCE}/{cat_name}/{key}/data.json"
                if storage.exists(rel_path):
                    stats["skip"] += 1
                    continue

                print(f"  [fetch] {url}")
                data = await fetch_json(url, cookie_dict, delay)
                await asyncio.sleep(delay)

                if data is None:
                    stats["no_json"] += 1
                    continue

                content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
                saved = storage.save_bytes(rel_path, content)
                digest = sha256_bytes(content)
                storage.append_index_record(
                    source=SOURCE,
                    key=key,
                    url=f"https://www.impo.com.uy{url}",
                    relative_path=str(saved.relative_to(storage.base_dir)),
                    size_bytes=len(content),
                    sha256=digest,
                    extra={"category": cat_name, "tipo": data.get("tipoNorma", "")},
                )
                print(f"  [ok] {data.get('tipoNorma','')} {data.get('nroNorma','')} ({len(content):,} bytes)")
                stats["ok"] += 1

    return stats


def parse_args():
    parser = argparse.ArgumentParser(description="Scraper IMPO CGI - todas las categorias")
    parser.add_argument(
        "--categories",
        default="all",
        help="Categorias a scrapear: all, o lista separada por comas (ej: 8,9,15)",
    )
    parser.add_argument("--out", default="data/output")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    return parser.parse_args()


def main():
    args = parse_args()
    base_dir = Path(args.out).expanduser().resolve()

    if args.categories == "all":
        cats = list(CATEGORIES.keys())
    else:
        cats = [c.strip() for c in args.categories.split(",")]

    print(f"IMPO CGI scraper  categories={cats}  out={base_dir}  delay={args.delay}s")
    stats = asyncio.run(run(cats, base_dir, args.delay))

    print("\nsummary:")
    for k, v in sorted(stats.items()):
        print(f"  {k:15s} {v}")


if __name__ == "__main__":
    main()
