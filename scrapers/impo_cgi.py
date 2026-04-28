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
    "1": "todo", "2": "normativa_otros", "3": "avisos", "4": "constitucion",
    "5": "leyes", "6": "decretos", "7": "resoluciones", "8": "codigos",
    "9": "textos_ordenados", "10": "normas_internacionales", "11": "reglamentos",
    "379": "asse", "14": "bcu", "15": "dgi", "12": "intendencias",
    "16": "suprema_corte", "13": "tribunal_cuentas", "1108": "tca_sentencias",
}

async def get_session_and_search(playwright, category_value, delay, from_page=1, to_page=0):
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(user_agent=USER_AGENT)
    page = await context.new_page()

    print("  [session] iniciando...")
    await page.goto("https://www.impo.com.uy/", wait_until="networkidle", timeout=60000)
    await page.goto("https://www.impo.com.uy/bases", wait_until="networkidle", timeout=60000)
    await asyncio.sleep(3)

    frame = page.main_frame
    await frame.select_option("select", category_value)
    await asyncio.sleep(1)
    await frame.evaluate("document.querySelector('input[type=submit]').click()")
    await page.wait_for_load_state("networkidle", timeout=30000)
    await asyncio.sleep(4)
    await page.wait_for_load_state("domcontentloaded", timeout=60000)
    await asyncio.sleep(2)

    html = ""
    for attempt in range(10):
        try:
            html = await page.content()
            if html and len(html) > 1000:
                break
        except Exception:
            await asyncio.sleep(3)
    m = re.search(r"idconsulta=([A-Za-z0-9]+)", html)
    idconsulta = m.group(1) if m else None
    m2 = re.search(r"([0-9]+) docs", html)
    total = int(m2.group(1)) if m2 else 0
    print("  [search] total:", total, "id:", idconsulta)

    all_links = []
    page_html = html
    base_cgi = "https://www.impo.com.uy/cgi-bin/bases/consultaBasesBS.cgi"

    while True:
        links = re.findall(r'href="(/bases/[^"]+)"', page_html)
        links = [l for l in links if not l.endswith("/bases")]
        for l in links:
            if l not in all_links:
                all_links.append(l)

        if not idconsulta or len(all_links) >= total or len(links) == 0:
            break

        nf = len(all_links) + 1
        nt = len(all_links) + 50
        next_url = base_cgi + "?tipoServicio=3&realizarconsulta=SI&idconsulta=" + idconsulta + "&nrodocdesdehasta=" + str(nf) + "-" + str(nt)
        print("  [page] docs", nf, "-", nt)
        await page.goto(next_url, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(2)
        page_html = await page.content()

    print("  [search] links totales:", len(all_links))
    cookies = await context.cookies()
    cookie_dict = {c["name"]: c["value"] for c in cookies}
    await browser.close()
    return all_links, cookie_dict


async def fetch_json(url, cookie_dict):
    headers = {
        "User-Agent": USER_AGENT,
        "Cookie": "; ".join(k + "=" + v for k, v in cookie_dict.items()),
    }
    async with httpx.AsyncClient(headers=headers, timeout=120.0) as client:
        full_url = "https://www.impo.com.uy" + url + "?json=true"
        try:
            r = await client.get(full_url, follow_redirects=True)
            if r.status_code != 200:
                return None
            raw = r.content.decode("latin-1")
            if not raw.strip().startswith("{"):
                return None
            raw = re.sub(r"[\x00-\x08\x0b\x0c\x0d\x0e-\x1f]", "", raw)
            return json.loads(raw)
        except Exception as e:
            print("  [error]", url, str(e)[:60])
            return None


async def run(categories, base_dir, delay, from_page=1, to_page=0):
    storage = LocalStorage(base_dir)
    already_done = storage.load_index_keys(SOURCE)
    stats = {"ok": 0, "skip": 0, "error": 0, "no_json": 0}

    async with async_playwright() as playwright:
        for cat_value in categories:
            cat_name = CATEGORIES.get(cat_value, "cat_" + cat_value)
            print("\n=== Categoria:", cat_name, "===")

            links, cookie_dict = await get_session_and_search(playwright, cat_value, delay, from_page, to_page)

            for url in links:
                key = url.strip("/").replace("/", "_")
                if key in already_done:
                    stats["skip"] += 1
                    continue
                rel_path = SOURCE + "/" + cat_name + "/" + key + "/data.json"
                if storage.exists(rel_path):
                    stats["skip"] += 1
                    continue

                print("  [fetch]", url)
                data = await fetch_json(url, cookie_dict)
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
                    url="https://www.impo.com.uy" + url,
                    relative_path=str(saved.relative_to(storage.base_dir)),
                    size_bytes=len(content),
                    sha256=digest,
                    extra={"category": cat_name, "tipo": data.get("tipoNorma", "")},
                )
                print("  [ok]", data.get("tipoNorma", ""), data.get("nroNorma", ""), "(" + str(len(content)) + " bytes)")
                stats["ok"] += 1

    return stats


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--categories", default="1,2,3,4,7,8,9,10,11,12,13,14,15,16,379,1108")
    parser.add_argument("--out", default="data/output")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    parser.add_argument("--from-page", type=int, default=1, help="Pagina inicial (1-based)")
    parser.add_argument("--to-page", type=int, default=0, help="Pagina final (0=todas)")
    return parser.parse_args()


def main():
    args = parse_args()
    base_dir = Path(args.out).expanduser().resolve()
    cats = list(CATEGORIES.keys()) if args.categories == "all" else [c.strip() for c in args.categories.split(",")]
    print("IMPO CGI scraper  categories=" + str(cats) + "  delay=" + str(args.delay))
    stats = asyncio.run(run(cats, base_dir, args.delay, args.from_page, args.to_page))
    print("\nsummary:")
    for k, v in sorted(stats.items()):
        print(" ", k, v)


if __name__ == "__main__":
    main()
