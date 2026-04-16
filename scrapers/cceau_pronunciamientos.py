from __future__ import annotations
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.cli import base_parser, out_path, print_summary
from core.discovery_scraper import DiscoveryScraper


class CCEAUPronunciamientos(DiscoveryScraper):
    """Colegio de Contadores - pronunciamientos técnicos."""
    SOURCE = "cceau_pronunciamientos"
    START_URLS = [
        "https://www.cceau.org.uy/pronunciamientos/",
    ]
    ALLOWED_DOMAIN = "cceau.org.uy"
    URL_PATTERNS = ["pronunciamiento", ".pdf"]
    MIN_BODY_TEXT = 150


def main() -> None:
    parser = base_parser("Scraper CCEAU Pronunciamientos")
    args = parser.parse_args()
    base_dir = out_path(args)
    print(f"out: {base_dir}   delay: {args.delay}s")
    scraper = CCEAUPronunciamientos(base_dir=base_dir, delay=args.delay)
    stats = asyncio.run(scraper.run())
    print_summary(stats)


if __name__ == "__main__":
    main()
