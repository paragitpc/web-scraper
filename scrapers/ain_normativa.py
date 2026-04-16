from __future__ import annotations
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.cli import base_parser, out_path, print_summary
from core.discovery_scraper import DiscoveryScraper


class AINNormativa(DiscoveryScraper):
    """Auditoría Interna de la Nación - normas contables, NIIF Pymes, registrales."""
    SOURCE = "ain_normativa"
    START_URLS = [
        "https://www.gub.uy/auditoria-interna-nacion/institucional/normativa",
    ]
    ALLOWED_DOMAIN = "gub.uy"
    URL_PATTERNS = ["auditoria-interna-nacion", ".pdf"]
    MIN_BODY_TEXT = 200


def main() -> None:
    parser = base_parser("Scraper AIN Normativa")
    args = parser.parse_args()
    base_dir = out_path(args)
    print(f"out: {base_dir}   delay: {args.delay}s")
    scraper = AINNormativa(base_dir=base_dir, delay=args.delay)
    stats = asyncio.run(scraper.run())
    print_summary(stats)


if __name__ == "__main__":
    main()
