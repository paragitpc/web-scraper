from __future__ import annotations
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.cli import base_parser, out_path, print_summary
from core.discovery_scraper import DiscoveryScraper


class BCUCirculares(DiscoveryScraper):
    SOURCE = "bcu_circulares"
    START_URLS = [
        "https://www.bcu.gub.uy/Circulares/Paginas/Default.aspx",
    ]
    ALLOWED_DOMAIN = "bcu.gub.uy"
    URL_PATTERNS = ["circular", ".pdf"]
    MIN_BODY_TEXT = 150


def main() -> None:
    parser = base_parser("Scraper BCU Circulares")
    args = parser.parse_args()
    base_dir = out_path(args)
    print(f"out: {base_dir}   delay: {args.delay}s")
    scraper = BCUCirculares(base_dir=base_dir, delay=args.delay)
    stats = asyncio.run(scraper.run())
    print_summary(stats)


if __name__ == "__main__":
    main()
