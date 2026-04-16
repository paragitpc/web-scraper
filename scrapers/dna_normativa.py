from __future__ import annotations
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.cli import base_parser, out_path, print_summary
from core.discovery_scraper import DiscoveryScraper


class DNANormativa(DiscoveryScraper):
    """DNA - Normativa, NCM, resoluciones."""
    SOURCE = "dna_normativa"
    START_URLS = [
        "https://www.aduanas.gub.uy/innovaportal/v/8495/3/innova.front/ncm-.html",
        "https://www.aduanas.gub.uy/innovaportal/v/2363/2/innova.front/normativa.html",
    ]
    ALLOWED_DOMAIN = "aduanas.gub.uy"
    URL_PATTERNS = ["normativa", "ncm", "resolucion", ".pdf"]
    MIN_BODY_TEXT = 150


def main() -> None:
    parser = base_parser("Scraper DNA Normativa + NCM")
    args = parser.parse_args()
    base_dir = out_path(args)
    print(f"out: {base_dir}   delay: {args.delay}s")
    scraper = DNANormativa(base_dir=base_dir, delay=args.delay)
    stats = asyncio.run(scraper.run())
    print_summary(stats)


if __name__ == "__main__":
    main()
