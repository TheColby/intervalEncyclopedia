#!/usr/bin/env python3
"""
Generate octave-reduced just intervals for the intervalEncyclopedia.

This script lists reduced ratios in the half-open range [1/1, 2/1),
derived from coprime integer pairs within a harmonic bound.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Tuple

from cli_output import (
    Reporter,
    add_output_control_args,
    create_reporter,
    validate_output_control_args,
)


COMMON_NAMES: Dict[Tuple[int, int], Tuple[str, str]] = {
    (1, 1): ("Unison", "P1"),
    (16, 15): ("Minor second", "m2"),
    (10, 9): ("Minor second", "m2"),
    (9, 8): ("Major second", "M2"),
    (6, 5): ("Minor third", "m3"),
    (5, 4): ("Major third", "M3"),
    (4, 3): ("Perfect fourth", "P4"),
    (45, 32): ("Tritone", "A4"),
    (64, 45): ("Tritone", "d5"),
    (3, 2): ("Perfect fifth", "P5"),
    (8, 5): ("Minor sixth", "m6"),
    (5, 3): ("Major sixth", "M6"),
    (9, 5): ("Minor seventh", "m7"),
    (16, 9): ("Minor seventh", "m7"),
    (15, 8): ("Major seventh", "M7"),
}

OUTPUT_FORMAT_CHOICES = ("auto", "txt", "csv", "json")


def infer_output_format(output_path: Path, requested_format: str) -> str:
    if requested_format != "auto":
        return requested_format
    suffix = output_path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".json":
        return "json"
    return "txt"


def ordinal(value: int) -> str:
    if 10 <= (value % 100) <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


def reduced_harmonic_ratio(harmonic: int) -> Tuple[int, int]:
    """
    Return the octave-reduced ratio for harmonic/1 in [1/1, 2/1), reduced to coprime terms.
    """
    octave_divisor = 1 << (harmonic.bit_length() - 1)
    numerator = harmonic
    denominator = octave_divisor
    divisor = math.gcd(numerator, denominator)
    return numerator // divisor, denominator // divisor


def build_harmonic_label_table(
    max_harmonic: int,
    reporter: Reporter | None = None,
) -> Dict[Tuple[int, int], str]:
    """
    Map each octave-reduced ratio to all harmonic labels up to max_harmonic.
    """
    progress = None
    if reporter is not None:
        reporter.verbose("Building harmonic label table...")
        progress = reporter.progress(total=max_harmonic, label="Harmonic labels")

    labels_by_ratio: Dict[Tuple[int, int], List[str]] = {}
    for harmonic in range(1, max_harmonic + 1):
        ratio = reduced_harmonic_ratio(harmonic)
        labels_by_ratio.setdefault(ratio, []).append(f"{ordinal(harmonic)} harmonic")
        if progress is not None:
            progress.update(harmonic)

    if progress is not None:
        progress.finish()

    return {ratio: ", ".join(labels) for ratio, labels in labels_by_ratio.items()}


def interval_common_name(
    numerator: int,
    denominator: int,
    harmonic_labels: Dict[Tuple[int, int], str],
) -> str | None:
    conventional = COMMON_NAMES.get((numerator, denominator))
    harmonic = harmonic_labels.get((numerator, denominator))

    parts: List[str] = []
    if conventional is not None:
        long_name, short_name = conventional
        parts.append(f"{long_name} ({short_name})")
    if harmonic is not None:
        parts.append(harmonic)

    if not parts:
        return None
    return "; ".join(parts)


def build_largest_prime_factor_table(
    limit: int,
    reporter: Reporter | None = None,
) -> List[int]:
    progress = None
    if reporter is not None:
        reporter.verbose("Building largest-prime-factor table...")
        progress = reporter.progress(total=limit, label="LPF table")

    table = [0] * (limit + 1)
    if limit >= 1:
        table[1] = 1
    for candidate in range(2, limit + 1):
        if table[candidate] == 0:
            for multiple in range(candidate, limit + 1, candidate):
                table[multiple] = candidate
        if progress is not None:
            progress.update(candidate)

    if progress is not None:
        progress.finish()

    return table


def integer_factorization(value: int, lpf_table: List[int]) -> List[Tuple[int, int]]:
    if value < 1:
        raise ValueError("Factorization input must be >= 1.")
    if value == 1:
        return []

    factors: List[Tuple[int, int]] = []
    remaining = value
    while remaining > 1:
        prime = lpf_table[remaining]
        exponent = 0
        while remaining % prime == 0:
            remaining //= prime
            exponent += 1
        factors.append((prime, exponent))
    return factors


def format_integer_factorization(value: int, lpf_table: List[int]) -> str:
    factors = integer_factorization(value, lpf_table)
    if not factors:
        return "1"
    parts: List[str] = []
    for prime, exponent in factors:
        if exponent == 1:
            parts.append(str(prime))
        else:
            parts.append(f"{prime}^{exponent}")
    return " * ".join(parts)


def format_ratio_prime_factorization(
    numerator: int,
    denominator: int,
    lpf_table: List[int],
) -> str:
    numerator_text = format_integer_factorization(numerator, lpf_table)
    denominator_text = format_integer_factorization(denominator, lpf_table)
    if denominator == 1:
        return numerator_text
    if numerator == 1:
        return f"1 / {denominator_text}"
    return f"{numerator_text} / {denominator_text}"


def odd_part(value: int) -> int:
    while value > 0 and (value % 2 == 0):
        value //= 2
    return value


def generate_coprime_octave_reduced_ratios(harmonic_limit: int) -> Iterator[Tuple[int, int]]:
    """
    Yield coprime ratios in [1/1, 2/1), sorted ascending.

    This uses an in-order Stern-Brocot traversal with a hard cap on both
    numerator and denominator so the generator can stream very large outputs
    without materializing all rows in memory.
    """
    yield (1, 1)

    # Stack entries are (left_num, left_den, right_num, right_den, state).
    # state=0 => descend left first, state=1 => emit mediant and descend right.
    stack: List[Tuple[int, int, int, int, int]] = [(1, 1, 2, 1, 0)]
    while stack:
        left_num, left_den, right_num, right_den, state = stack.pop()
        mediant_num = left_num + right_num
        mediant_den = left_den + right_den

        if mediant_num > harmonic_limit or mediant_den > harmonic_limit:
            continue

        if state == 0:
            stack.append((left_num, left_den, right_num, right_den, 1))
            stack.append((left_num, left_den, mediant_num, mediant_den, 0))
            continue

        yield (mediant_num, mediant_den)
        stack.append((mediant_num, mediant_den, right_num, right_den, 0))


def cents_from_ratio(numerator: int, denominator: int) -> float:
    return 1200.0 * math.log2(numerator / denominator)


def row_passes_prime_filter(
    numerator: int,
    denominator: int,
    largest_prime_factor: List[int],
    max_prime: int | None,
) -> bool:
    if max_prime is None:
        return True
    interval_prime = max(largest_prime_factor[numerator], largest_prime_factor[denominator])
    return interval_prime <= max_prime


def count_filtered_rows(
    harmonic_limit: int,
    lpf_table: List[int],
    max_prime: int | None,
    max_rows: int | None,
) -> int:
    total = 0
    for numerator, denominator in generate_coprime_octave_reduced_ratios(harmonic_limit):
        if not row_passes_prime_filter(numerator, denominator, lpf_table, max_prime):
            continue
        total += 1
        if max_rows is not None and total >= max_rows:
            break
    return total


def output_metadata(
    *,
    harmonic_limit: int,
    max_prime: int | None,
    total_rows: int,
    output_format: str,
) -> Dict[str, str | int]:
    return {
        "title": "intervalEncyclopedia - Just Intervals",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "harmonic_limit": harmonic_limit,
        "max_prime_filter": max_prime if max_prime is not None else "none",
        "total_rows": total_rows,
        "output_format": output_format,
    }


def iter_formatted_rows(
    *,
    harmonic_limit: int,
    max_prime: int | None,
    max_rows: int | None,
    precision: int,
    lpf_table: List[int],
    harmonic_labels: Dict[Tuple[int, int], str],
) -> Iterator[Dict[str, str]]:
    written = 0
    for numerator, denominator in generate_coprime_octave_reduced_ratios(harmonic_limit):
        if not row_passes_prime_filter(numerator, denominator, lpf_table, max_prime):
            continue
        written += 1
        interval_prime = max(lpf_table[numerator], lpf_table[denominator])
        interval_odd_limit = max(odd_part(numerator), odd_part(denominator))
        common_name = interval_common_name(
            numerator=numerator,
            denominator=denominator,
            harmonic_labels=harmonic_labels,
        ) or "-"
        prime_factorization = format_ratio_prime_factorization(
            numerator=numerator,
            denominator=denominator,
            lpf_table=lpf_table,
        )
        cents = cents_from_ratio(numerator, denominator)
        ratio_decimal = numerator / denominator
        yield {
            "ratio": f"{numerator}/{denominator}",
            "ratio_decimal": f"{ratio_decimal:.{precision}f}",
            "prime_factorization": prime_factorization,
            "cents": f"{cents:.{precision}f}",
            "largest_prime": str(interval_prime),
            "odd_limit": str(interval_odd_limit),
            "common_name": common_name,
        }
        if max_rows is not None and written >= max_rows:
            break


def write_output(
    output_path: Path,
    harmonic_limit: int,
    max_prime: int | None,
    max_rows: int | None,
    precision: int,
    lpf_table: List[int],
    harmonic_labels: Dict[Tuple[int, int], str],
    output_format: str,
    reporter: Reporter,
) -> int:
    reporter.info("Counting filtered rows...")
    total = count_filtered_rows(
        harmonic_limit=harmonic_limit,
        lpf_table=lpf_table,
        max_prime=max_prime,
        max_rows=max_rows,
    )
    resolved_format = infer_output_format(output_path=output_path, requested_format=output_format)
    reporter.info(f"Writing {total} just-interval rows ({resolved_format})...")

    metadata = output_metadata(
        harmonic_limit=harmonic_limit,
        max_prime=max_prime,
        total_rows=total,
        output_format=resolved_format,
    )
    columns = [
        "ratio",
        "ratio_decimal",
        "prime_factorization",
        "cents",
        "largest_prime",
        "odd_limit",
        "common_name",
    ]
    progress = reporter.progress(total=total, label="Just intervals")

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        if resolved_format == "txt":
            handle.write(f"# {metadata['title']}\n")
            handle.write(f"# generated_utc={metadata['generated_utc']}\n")
            handle.write(f"# harmonic_limit={metadata['harmonic_limit']}\n")
            handle.write(f"# max_prime_filter={metadata['max_prime_filter']}\n")
            handle.write(f"# total_rows={metadata['total_rows']}\n")
            handle.write(f"# output_format={metadata['output_format']}\n")
            handle.write("\t".join(columns) + "\n")
            for index, row in enumerate(
                iter_formatted_rows(
                    harmonic_limit=harmonic_limit,
                    max_prime=max_prime,
                    max_rows=max_rows,
                    precision=precision,
                    lpf_table=lpf_table,
                    harmonic_labels=harmonic_labels,
                ),
                start=1,
            ):
                handle.write("\t".join(row[column] for column in columns) + "\n")
                progress.update(index)
        elif resolved_format == "csv":
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            for index, row in enumerate(
                iter_formatted_rows(
                    harmonic_limit=harmonic_limit,
                    max_prime=max_prime,
                    max_rows=max_rows,
                    precision=precision,
                    lpf_table=lpf_table,
                    harmonic_labels=harmonic_labels,
                ),
                start=1,
            ):
                writer.writerow(row)
                progress.update(index)
        elif resolved_format == "json":
            handle.write("{\n")
            handle.write(f'  "metadata": {json.dumps(metadata, ensure_ascii=False)},\n')
            handle.write(f'  "columns": {json.dumps(columns, ensure_ascii=False)},\n')
            handle.write('  "rows": [\n')
            first = True
            for index, row in enumerate(
                iter_formatted_rows(
                    harmonic_limit=harmonic_limit,
                    max_prime=max_prime,
                    max_rows=max_rows,
                    precision=precision,
                    lpf_table=lpf_table,
                    harmonic_labels=harmonic_labels,
                ),
                start=1,
            ):
                if first:
                    handle.write(f"    {json.dumps(row, ensure_ascii=False)}")
                    first = False
                else:
                    handle.write(f",\n    {json.dumps(row, ensure_ascii=False)}")
                progress.update(index)
            if not first:
                handle.write("\n")
            handle.write("  ]\n")
            handle.write("}\n")
        else:
            raise ValueError(f"Unsupported output format: {resolved_format}")

    progress.finish()

    return total


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate octave-reduced just intervals from a harmonic bound."
    )
    parser.add_argument(
        "--max-harmonic",
        "--harmonic-limit",
        dest="harmonic_limit",
        type=int,
        default=320,
        help=(
            "Upper bound for harmonic coverage and integer terms used to derive just ratios "
            "(default: 320)."
        ),
    )
    parser.add_argument(
        "--max-prime",
        type=int,
        default=None,
        help="Optional prime-limit filter; keep rows where max prime factor <= this value.",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Optional hard cap on written rows (useful for previews).",
    )
    parser.add_argument(
        "--precision",
        type=int,
        default=24,
        help="Decimal places for cent values.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("just-intervals.txt"),
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
    if args.harmonic_limit < 1:
        raise ValueError("--max-harmonic/--harmonic-limit must be >= 1.")
    if args.max_prime is not None and args.max_prime < 2:
        raise ValueError("--max-prime must be >= 2 when provided.")
    if args.max_rows is not None and args.max_rows < 1:
        raise ValueError("--max-rows must be >= 1 when provided.")
    if args.precision < 0:
        raise ValueError("--precision must be >= 0.")
    validate_output_control_args(args)


def main() -> None:
    args = parse_args()
    validate_args(args)
    reporter = create_reporter(args)

    lpf_table = build_largest_prime_factor_table(args.harmonic_limit, reporter=reporter)
    harmonic_labels = build_harmonic_label_table(args.harmonic_limit, reporter=reporter)
    total = write_output(
        output_path=args.output,
        harmonic_limit=args.harmonic_limit,
        max_prime=args.max_prime,
        max_rows=args.max_rows,
        precision=args.precision,
        lpf_table=lpf_table,
        harmonic_labels=harmonic_labels,
        output_format=args.output_format,
        reporter=reporter,
    )

    reporter.print_result(f"Wrote {total} rows to {args.output}")


if __name__ == "__main__":
    main()
