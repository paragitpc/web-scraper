from __future__ import annotations

import argparse
from datetime import datetime, date
from pathlib import Path


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def base_parser(description: str = "") -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--out", default="data/output", help="base output dir")
    p.add_argument("--delay", type=float, default=1.5, help="delay between requests")
    p.add_argument("--quiet", action="store_true", help="reduce output")
    return p


def add_date_range(p: argparse.ArgumentParser) -> None:
    p.add_argument("--start", required=True, type=parse_date, help="YYYY-MM-DD")
    p.add_argument("--end", required=True, type=parse_date, help="YYYY-MM-DD")


def add_id_range(p: argparse.ArgumentParser, default_min: int = 1, default_max: int | None = None) -> None:
    p.add_argument("--from-id", type=int, default=default_min)
    if default_max is not None:
        p.add_argument("--to-id", type=int, default=default_max)
    else:
        p.add_argument("--to-id", type=int, required=True)


def add_year_range(p: argparse.ArgumentParser) -> None:
    p.add_argument("--from-year", type=int, required=True)
    p.add_argument("--to-year", type=int, required=True)


def out_path(args: argparse.Namespace) -> Path:
    return Path(args.out).expanduser().resolve()


def print_summary(stats: dict[str, int]) -> None:
    print("\nsummary:")
    for k in sorted(stats.keys()):
        print(f"  {k:18s} {stats[k]}")
