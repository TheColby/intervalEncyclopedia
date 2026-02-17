#!/usr/bin/env python3
"""
Generate equal-tempered interval tables for the Interval Thesaurus.

By default this outputs all steps for every EDO from 1 to 512.
"""

from __future__ import annotations

import argparse
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Tuple


def generate_rows(
    min_edo: int, max_edo: int, include_unison: bool, include_octave: bool
) -> Iterator[Tuple[int, int, float, float]]:
    for edo in range(min_edo, max_edo + 1):
        start_step = 0 if include_unison else 1
        end_step = edo if include_octave else edo - 1
        for step in range(start_step, end_step + 1):
            ratio = 2.0 ** (step / edo)
            cents = 1200.0 * step / edo
            yield edo, step, ratio, cents


def count_rows(
    min_edo: int, max_edo: int, include_unison: bool, include_octave: bool
) -> int:
    total = 0
    for edo in range(min_edo, max_edo + 1):
        start_step = 0 if include_unison else 1
        end_step = edo if include_octave else edo - 1
        if end_step >= start_step:
            total += end_step - start_step + 1
    return total


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate equal-tempered interval ratios up to a target EDO."
    )
    parser.add_argument(
        "--min-edo",
        type=int,
        default=1,
        help="Smallest equal division of the octave to include.",
    )
    parser.add_argument(
        "--max-edo",
        type=int,
        default=512,
        help="Largest equal division of the octave to include.",
    )
    parser.add_argument(
        "--exclude-unison",
        action="store_true",
        help="Exclude step 0 (1/1).",
    )
    parser.add_argument(
        "--exclude-octave",
        action="store_true",
        help="Exclude step N (2/1).",
    )
    parser.add_argument(
        "--precision",
        type=int,
        default=15,
        help="Decimal places for ratio and cent outputs.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tempered-intervals.txt"),
        help="Output text file path.",
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.min_edo < 1:
        raise ValueError("--min-edo must be >= 1.")
    if args.max_edo < args.min_edo:
        raise ValueError("--max-edo must be >= --min-edo.")
    if args.precision < 0:
        raise ValueError("--precision must be >= 0.")

    include_unison = not args.exclude_unison
    include_octave = not args.exclude_octave
    if not include_unison and not include_octave and args.min_edo == 1 and args.max_edo == 1:
        raise ValueError("With EDO=1, excluding both unison and octave leaves no rows.")


def write_output(
    output_path: Path,
    min_edo: int,
    max_edo: int,
    include_unison: bool,
    include_octave: bool,
    precision: int,
) -> int:
    total_rows = count_rows(min_edo, max_edo, include_unison, include_octave)
    with output_path.open("w", encoding="utf-8") as handle:
        handle.write("# Interval Thesaurus - Equal Tempered Intervals\n")
        handle.write(
            f"# generated_utc={datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
        )
        handle.write(f"# min_edo={min_edo}\n")
        handle.write(f"# max_edo={max_edo}\n")
        handle.write(f"# include_unison={include_unison}\n")
        handle.write(f"# include_octave={include_octave}\n")
        handle.write(f"# total_rows={total_rows}\n")
        handle.write("edo\tstep\tratio\tcents\texpression\n")

        for edo, step, ratio, cents in generate_rows(
            min_edo=min_edo,
            max_edo=max_edo,
            include_unison=include_unison,
            include_octave=include_octave,
        ):
            expression = f"2^({step}/{edo})"
            handle.write(
                f"{edo}\t{step}\t{ratio:.{precision}f}\t{cents:.{precision}f}\t{expression}\n"
            )

    return total_rows


def main() -> None:
    args = parse_args()
    validate_args(args)

    include_unison = not args.exclude_unison
    include_octave = not args.exclude_octave
    total = write_output(
        output_path=args.output,
        min_edo=args.min_edo,
        max_edo=args.max_edo,
        include_unison=include_unison,
        include_octave=include_octave,
        precision=args.precision,
    )
    print(f"Wrote {total} rows to {args.output}")


if __name__ == "__main__":
    main()
