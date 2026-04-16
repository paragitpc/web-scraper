from __future__ import annotations
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.cli import base_parser, out_path, print_summary
from core.discovery_scraper import DiscoveryScraper


class ParlamentoProyectos(DiscoveryScraper):
    """Parlamento - proyectos de ley en trámite."""
    SOURCE = "parlamento_proyectos"
    START_URLS = [
        "https://parlamento.gub.uy/documentosyleyes",
    ]
    ALLOWED_DOMAIN = "parlamento.gub.uy"
    URL_PATTERNS = ["documentosyleyes", "leyes", "proyecto", ".pdf"]
    MIN_BODY_TEXT = 150


def main() -> None:
    parser = base_parser("Scraper Parlamento - Proyectos y Leyes")
    args = parser.parse_args()
    base_dir = out_path(args)
    print(f"out: {base_dir}   delay: {args.delay}s")
    scraper = ParlamentoProyectos(base_dir=base_dir, delay=args.delay)
    stats = asyncio.run(scraper.run())
    print_summary(stats)


if __name__ == "__main__":
    main()
