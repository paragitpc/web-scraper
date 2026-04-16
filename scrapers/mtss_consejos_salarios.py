from __future__ import annotations
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.cli import base_parser, out_path, print_summary
from core.discovery_scraper import DiscoveryScraper


class MTSSConsejosSalarios(DiscoveryScraper):
    """Convenios colectivos y escalas de Consejos de Salarios."""
    SOURCE = "mtss_consejos_salarios"
    START_URLS = [
        "https://www.gub.uy/ministerio-trabajo-seguridad-social/politicas-y-gestion/consejos-salarios",
    ]
    ALLOWED_DOMAIN = "gub.uy"
    URL_PATTERNS = ["consejos-salarios", "convenio", "grupo-", ".pdf"]
    MIN_BODY_TEXT = 150


def main() -> None:
    parser = base_parser("Scraper MTSS Consejos de Salarios")
    args = parser.parse_args()
    base_dir = out_path(args)
    print(f"out: {base_dir}   delay: {args.delay}s")
    scraper = MTSSConsejosSalarios(base_dir=base_dir, delay=args.delay)
    stats = asyncio.run(scraper.run())
    print_summary(stats)


if __name__ == "__main__":
    main()
