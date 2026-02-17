#!/usr/bin/env python3
"""
Generate equal-tempered interval tables for the intervalEncyclopedia.

By default this outputs all steps for every EDO from 1 to 4800.
"""

from __future__ import annotations

import argparse
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Tuple

from cli_output import (
    Reporter,
    add_output_control_args,
    create_reporter,
    validate_output_control_args,
)


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


def prime_factorization_for_tempered_step(step: int, edo: int) -> str:
    # Only step 0 and step edo are rational powers of 2 within the generated range.
    if step == 0:
        return "1"
    if step == edo:
        return "2"
    return "-"


def ordinal_suffix(value: int) -> str:
    if 10 <= (value % 100) <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")


def edo_interval_name(step: int, edo: int) -> str:
    ordinal = f"{step}{ordinal_suffix(step)}"
    base_name = f"{ordinal} scale degree of {edo}-TET"
    if step == 0:
        return f"Unison of {edo}-TET (degree 0)"
    if step == edo:
        return f"Octave of {edo}-TET ({base_name})"
    return base_name


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
        default=4800,
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
        default=24,
        help="Decimal places for ratio and cent outputs.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tempered-intervals.txt"),
        help="Output text file path.",
    )
    add_output_control_args(parser)
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
    validate_output_control_args(args)


def write_output(
    output_path: Path,
    min_edo: int,
    max_edo: int,
    include_unison: bool,
    include_octave: bool,
    precision: int,
    reporter: Reporter,
) -> int:
    total_rows = count_rows(min_edo, max_edo, include_unison, include_octave)
    reporter.info(f"Writing {total_rows} equal-tempered rows...")
    with output_path.open("w", encoding="utf-8") as handle:
        handle.write("# intervalEncyclopedia - Equal Tempered Intervals\n")
        handle.write(
            f"# generated_utc={datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
        )
        handle.write(f"# min_edo={min_edo}\n")
        handle.write(f"# max_edo={max_edo}\n")
        handle.write(f"# include_unison={include_unison}\n")
        handle.write(f"# include_octave={include_octave}\n")
        handle.write(f"# total_rows={total_rows}\n")
        handle.write("edo\tstep\tinterval_name\tratio\tprime_factorization\tcents\texpression\n")

        progress = reporter.progress(total=total_rows, label="Tempered rows")
        written = 0
        for edo, step, ratio, cents in generate_rows(
            min_edo=min_edo,
            max_edo=max_edo,
            include_unison=include_unison,
            include_octave=include_octave,
        ):
            expression = f"2^({step}/{edo})"
            interval_name = edo_interval_name(step=step, edo=edo)
            prime_factorization = prime_factorization_for_tempered_step(step=step, edo=edo)
            handle.write(
                f"{edo}\t{step}\t{interval_name}\t{ratio:.{precision}f}\t"
                f"{prime_factorization}\t{cents:.{precision}f}\t{expression}\n"
            )
            written += 1
            progress.update(written)

        progress.finish()

    return total_rows


def main() -> None:
    args = parse_args()
    validate_args(args)
    reporter = create_reporter(args)

    include_unison = not args.exclude_unison
    include_octave = not args.exclude_octave
    total = write_output(
        output_path=args.output,
        min_edo=args.min_edo,
        max_edo=args.max_edo,
        include_unison=include_unison,
        include_octave=include_octave,
        precision=args.precision,
        reporter=reporter,
    )
    reporter.print_result(f"Wrote {total} rows to {args.output}")


if __name__ == "__main__":
    main()
