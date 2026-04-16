from __future__ import annotations
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.cli import base_parser, out_path, print_summary
from core.discovery_scraper import DiscoveryScraper


class INEIndicadores(DiscoveryScraper):
    """INE - IPC, UR, URA, BPC, IMS y otros indicadores económicos."""
    SOURCE = "ine_indicadores"
    START_URLS = [
        "https://www.ine.gub.uy/ipc-indice-de-precios-del-consumo",
        "https://www.ine.gub.uy/ur-unidad-reajustable",
        "https://www.ine.gub.uy/ims-indice-medio-de-salarios",
    ]
    ALLOWED_DOMAIN = "ine.gub.uy"
    URL_PATTERNS = [".pdf", ".xls", "ipc", "ur", "ims", "bpc"]
    MIN_BODY_TEXT = 100


def main() -> None:
    parser = base_parser("Scraper INE - Indicadores")
    args = parser.parse_args()
    base_dir = out_path(args)
    print(f"out: {base_dir}   delay: {args.delay}s")
    scraper = INEIndicadores(base_dir=base_dir, delay=args.delay)
    stats = asyncio.run(scraper.run())
    print_summary(stats)


if __name__ == "__main__":
    main()
