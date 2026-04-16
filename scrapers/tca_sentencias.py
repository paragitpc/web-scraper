from __future__ import annotations
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.cli import base_parser, out_path, print_summary
from core.discovery_scraper import DiscoveryScraper


class TCASentencias(DiscoveryScraper):
    """Tribunal de lo Contencioso Administrativo - sentencias."""
    SOURCE = "tca_sentencias"
    START_URLS = [
        "https://www.tca.gub.uy/",
    ]
    ALLOWED_DOMAIN = "tca.gub.uy"
    URL_PATTERNS = ["sentencia", "fallo", ".pdf"]
    MIN_BODY_TEXT = 150


def main() -> None:
    parser = base_parser("Scraper TCA Sentencias")
    args = parser.parse_args()
    base_dir = out_path(args)
    print(f"out: {base_dir}   delay: {args.delay}s")
    scraper = TCASentencias(base_dir=base_dir, delay=args.delay)
    stats = asyncio.run(scraper.run())
    print_summary(stats)


if __name__ == "__main__":
    main()
