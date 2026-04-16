from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.cli import base_parser, out_path, print_summary
from core.discovery_scraper import DiscoveryScraper
import asyncio


class BPSNormativa(DiscoveryScraper):
    SOURCE = "bps_normativa"
    START_URLS = [
        "https://www.bps.gub.uy/3623/normativa.html",
    ]
    ALLOWED_DOMAIN = "bps.gub.uy"
    URL_PATTERNS = [".pdf", "/normativa", "/instructivo", "/resolucion"]
    MIN_BODY_TEXT = 200
    MAX_DEPTH = 1


def main() -> None:
    parser = base_parser("Scraper BPS Normativa")
    args = parser.parse_args()
    base_dir = out_path(args)
    print(f"out: {base_dir}   delay: {args.delay}s")
    scraper = BPSNormativa(base_dir=base_dir, delay=args.delay)
    stats = asyncio.run(scraper.run())
    print_summary(stats)


if __name__ == "__main__":
    main()
