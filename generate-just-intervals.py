#!/usr/bin/env python3
"""
Generate octave-reduced just intervals for the Interval Thesaurus.

This script lists reduced ratios in the half-open range [1/1, 2/1),
derived from coprime integer pairs within a harmonic bound.
"""

from __future__ import annotations

import argparse
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Tuple


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


def is_power_of_two(value: int) -> bool:
    return value > 0 and (value & (value - 1) == 0)


def ordinal(value: int) -> str:
    if 10 <= (value % 100) <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


def harmonic_common_name(numerator: int, denominator: int) -> str | None:
    # Ratios of the form odd/power_of_two are octave-reduced harmonics.
    if denominator == 1 and numerator == 1:
        return "1st harmonic"
    if is_power_of_two(denominator):
        return f"{ordinal(numerator)} harmonic"
    return None


def interval_common_name(numerator: int, denominator: int) -> str | None:
    conventional = COMMON_NAMES.get((numerator, denominator))
    harmonic = harmonic_common_name(numerator, denominator)

    parts: List[str] = []
    if conventional is not None:
        long_name, short_name = conventional
        parts.append(f"{long_name} ({short_name})")
    if harmonic is not None:
        parts.append(harmonic)

    if not parts:
        return None
    return "; ".join(parts)


def build_largest_prime_factor_table(limit: int) -> List[int]:
    table = [0] * (limit + 1)
    if limit >= 1:
        table[1] = 1
    for candidate in range(2, limit + 1):
        if table[candidate] == 0:
            for multiple in range(candidate, limit + 1, candidate):
                table[multiple] = candidate
    return table


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


def write_output(
    output_path: Path,
    harmonic_limit: int,
    max_prime: int | None,
    max_rows: int | None,
    precision: int,
    lpf_table: List[int],
) -> int:
    total = count_filtered_rows(
        harmonic_limit=harmonic_limit,
        lpf_table=lpf_table,
        max_prime=max_prime,
        max_rows=max_rows,
    )

    with output_path.open("w", encoding="utf-8") as handle:
        handle.write("# Interval Thesaurus - Just Intervals\n")
        handle.write(
            f"# generated_utc={datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
        )
        handle.write(f"# harmonic_limit={harmonic_limit}\n")
        handle.write(f"# max_prime_filter={max_prime if max_prime is not None else 'none'}\n")
        handle.write(f"# total_rows={total}\n")
        handle.write("ratio\tcents\tlargest_prime\todd_limit\tcommon_name\n")

        written = 0
        for numerator, denominator in generate_coprime_octave_reduced_ratios(harmonic_limit):
            if not row_passes_prime_filter(numerator, denominator, lpf_table, max_prime):
                continue
            written += 1
            interval_prime = max(lpf_table[numerator], lpf_table[denominator])
            interval_odd_limit = max(odd_part(numerator), odd_part(denominator))
            common_name = interval_common_name(numerator, denominator) or "-"
            cents = cents_from_ratio(numerator, denominator)
            handle.write(
                f"{numerator}/{denominator}\t{cents:.{precision}f}\t"
                f"{interval_prime}\t{interval_odd_limit}\t{common_name}\n"
            )
            if max_rows is not None and written >= max_rows:
                break

    return total


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate octave-reduced just intervals from a harmonic bound."
    )
    parser.add_argument(
        "--harmonic-limit",
        type=int,
        default=4096,
        help="Upper bound for integer terms used to derive just ratios (default: 4096).",
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
        default=6,
        help="Decimal places for cent values.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("just-intervals.txt"),
        help="Output text file path.",
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.harmonic_limit < 1:
        raise ValueError("--harmonic-limit must be >= 1.")
    if args.max_prime is not None and args.max_prime < 2:
        raise ValueError("--max-prime must be >= 2 when provided.")
    if args.max_rows is not None and args.max_rows < 1:
        raise ValueError("--max-rows must be >= 1 when provided.")
    if args.precision < 0:
        raise ValueError("--precision must be >= 0.")


def main() -> None:
    args = parse_args()
    validate_args(args)

    lpf_table = build_largest_prime_factor_table(args.harmonic_limit)
    total = write_output(
        output_path=args.output,
        harmonic_limit=args.harmonic_limit,
        max_prime=args.max_prime,
        max_rows=args.max_rows,
        precision=args.precision,
        lpf_table=lpf_table,
    )

    print(f"Wrote {total} rows to {args.output}")


if __name__ == "__main__":
    main()
