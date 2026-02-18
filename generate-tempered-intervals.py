#!/usr/bin/env python3
"""
Generate equal-division-of-the-octave (EDO) interval tables for intervalEncyclopedia.

By default this outputs all steps for every EDO from 1 to 96.
"""

from __future__ import annotations

import argparse
import csv
import heapq
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List, Tuple

from cli_output import (
    Reporter,
    add_output_control_args,
    create_reporter,
    validate_output_control_args,
)


OUTPUT_FORMAT_CHOICES = ("auto", "txt", "csv", "json")
SORT_CHOICES = ("ratio", "edo-step")


def infer_output_format(output_path: Path, requested_format: str) -> str:
    if requested_format != "auto":
        return requested_format
    suffix = output_path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".json":
        return "json"
    return "txt"


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


def generate_rows_sorted_by_ratio(
    min_edo: int, max_edo: int, include_unison: bool, include_octave: bool
) -> Iterator[Tuple[int, int, float, float]]:
    # Each EDO contributes a monotonic ratio sequence, so a k-way merge yields
    # globally sorted rows without materializing the full dataset.
    heap: List[Tuple[float, float, int, int, int]] = []
    for edo in range(min_edo, max_edo + 1):
        start_step = 0 if include_unison else 1
        end_step = edo if include_octave else edo - 1
        if end_step < start_step:
            continue
        step = start_step
        ratio = 2.0 ** (step / edo)
        cents = 1200.0 * step / edo
        heapq.heappush(heap, (ratio, cents, edo, step, end_step))

    while heap:
        ratio, cents, edo, step, end_step = heapq.heappop(heap)
        yield edo, step, ratio, cents
        next_step = step + 1
        if next_step <= end_step:
            next_ratio = 2.0 ** (next_step / edo)
            next_cents = 1200.0 * next_step / edo
            heapq.heappush(heap, (next_ratio, next_cents, edo, next_step, end_step))


def select_row_generator(
    sort_by: str,
    min_edo: int,
    max_edo: int,
    include_unison: bool,
    include_octave: bool,
) -> Iterator[Tuple[int, int, float, float]]:
    if sort_by == "ratio":
        return generate_rows_sorted_by_ratio(
            min_edo=min_edo,
            max_edo=max_edo,
            include_unison=include_unison,
            include_octave=include_octave,
        )
    return generate_rows(
        min_edo=min_edo,
        max_edo=max_edo,
        include_unison=include_unison,
        include_octave=include_octave,
    )


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
    base_name = f"{ordinal} scale degree of {edo}-EDO"
    if step == 0:
        return f"Unison of {edo}-EDO (degree 0)"
    if step == edo:
        return f"Octave of {edo}-EDO ({base_name})"
    return base_name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate equal-division-of-the-octave interval ratios up to a target EDO."
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
        default=96,
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
        "--sort-by",
        choices=SORT_CHOICES,
        default="ratio",
        help="Row ordering: globally by ratio (default) or grouped by EDO/step.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tempered-intervals.txt"),
        help="Output path (.txt/.csv/.json or set --output-format).",
    )
    parser.add_argument(
        "--output-format",
        choices=OUTPUT_FORMAT_CHOICES,
        default="auto",
        help="Output format. Use 'auto' to infer from file extension.",
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
    sort_by: str,
    output_format: str,
    reporter: Reporter,
) -> int:
    total_rows = count_rows(min_edo, max_edo, include_unison, include_octave)
    resolved_format = infer_output_format(output_path=output_path, requested_format=output_format)
    reporter.info(f"Writing {total_rows} EDO rows ({resolved_format})...")

    metadata = {
        "title": "intervalEncyclopedia - Equal Division of the Octave (EDO) Intervals",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "min_edo": min_edo,
        "max_edo": max_edo,
        "include_unison": include_unison,
        "include_octave": include_octave,
        "sort_by": sort_by,
        "total_rows": total_rows,
        "output_format": resolved_format,
    }
    columns = [
        "edo",
        "step",
        "interval_name",
        "ratio",
        "prime_factorization",
        "cents",
        "expression",
    ]
    progress = reporter.progress(total=total_rows, label="Tempered rows")
    row_iterator = select_row_generator(
        sort_by=sort_by,
        min_edo=min_edo,
        max_edo=max_edo,
        include_unison=include_unison,
        include_octave=include_octave,
    )

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        if resolved_format == "txt":
            handle.write(f"# {metadata['title']}\n")
            handle.write(f"# generated_utc={metadata['generated_utc']}\n")
            handle.write(f"# min_edo={metadata['min_edo']}\n")
            handle.write(f"# max_edo={metadata['max_edo']}\n")
            handle.write(f"# include_unison={metadata['include_unison']}\n")
            handle.write(f"# include_octave={metadata['include_octave']}\n")
            handle.write(f"# sort_by={metadata['sort_by']}\n")
            handle.write(f"# total_rows={metadata['total_rows']}\n")
            handle.write(f"# output_format={metadata['output_format']}\n")
            handle.write("\t".join(columns) + "\n")

            for written, (edo, step, ratio, cents) in enumerate(row_iterator, start=1):
                expression = f"2^({step}/{edo})"
                interval_name = edo_interval_name(step=step, edo=edo)
                prime_factorization = prime_factorization_for_tempered_step(step=step, edo=edo)
                handle.write(
                    f"{edo}\t{step}\t{interval_name}\t{ratio:.{precision}f}\t"
                    f"{prime_factorization}\t{cents:.{precision}f}\t{expression}\n"
                )
                progress.update(written)
        elif resolved_format == "csv":
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()

            for written, (edo, step, ratio, cents) in enumerate(row_iterator, start=1):
                expression = f"2^({step}/{edo})"
                interval_name = edo_interval_name(step=step, edo=edo)
                prime_factorization = prime_factorization_for_tempered_step(step=step, edo=edo)
                writer.writerow(
                    {
                        "edo": str(edo),
                        "step": str(step),
                        "interval_name": interval_name,
                        "ratio": f"{ratio:.{precision}f}",
                        "prime_factorization": prime_factorization,
                        "cents": f"{cents:.{precision}f}",
                        "expression": expression,
                    }
                )
                progress.update(written)
        elif resolved_format == "json":
            handle.write("{\n")
            handle.write(f'  "metadata": {json.dumps(metadata, ensure_ascii=False)},\n')
            handle.write(f'  "columns": {json.dumps(columns, ensure_ascii=False)},\n')
            handle.write('  "rows": [\n')
            first = True
            for written, (edo, step, ratio, cents) in enumerate(row_iterator, start=1):
                expression = f"2^({step}/{edo})"
                interval_name = edo_interval_name(step=step, edo=edo)
                prime_factorization = prime_factorization_for_tempered_step(step=step, edo=edo)
                row = {
                    "edo": str(edo),
                    "step": str(step),
                    "interval_name": interval_name,
                    "ratio": f"{ratio:.{precision}f}",
                    "prime_factorization": prime_factorization,
                    "cents": f"{cents:.{precision}f}",
                    "expression": expression,
                }
                if first:
                    handle.write(f"    {json.dumps(row, ensure_ascii=False)}")
                    first = False
                else:
                    handle.write(f",\n    {json.dumps(row, ensure_ascii=False)}")
                progress.update(written)
            if not first:
                handle.write("\n")
            handle.write("  ]\n")
            handle.write("}\n")
        else:
            raise ValueError(f"Unsupported output format: {resolved_format}")

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
        sort_by=args.sort_by,
        output_format=args.output_format,
        reporter=reporter,
    )
    reporter.print_result(f"Wrote {total} rows to {args.output}")


if __name__ == "__main__":
    main()
