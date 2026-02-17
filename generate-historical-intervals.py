#!/usr/bin/env python3
"""
Generate historically significant irrational intervals for the Interval Thesaurus.

The defaults are curated and intentionally editable; treat this as a seed corpus.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List


@dataclass(frozen=True)
class HistoricalInterval:
    slug: str
    name: str
    expression: str
    value: float
    tradition: str
    note: str


def plastic_constant() -> float:
    # Real root of x^3 - x - 1 = 0.
    return ((9 + math.sqrt(69)) / 18) ** (1 / 3) + ((9 - math.sqrt(69)) / 18) ** (1 / 3)


def default_intervals() -> List[HistoricalInterval]:
    phi = (1 + math.sqrt(5)) / 2
    return [
        HistoricalInterval(
            slug="sqrt2_tritone",
            name="Geometric Tritone",
            expression="sqrt(2)",
            value=math.sqrt(2),
            tradition="Greek geometry, later common in equal temperament discourse",
            note="Geometric mean of 1/1 and 2/1.",
        ),
        HistoricalInterval(
            slug="phi_divine",
            name="Golden Ratio",
            expression="(1 + sqrt(5)) / 2",
            value=phi,
            tradition="Pythagorean and Platonic geometry, later esoteric theory",
            note="Linked to pentagonal proportion and speculative tuning systems.",
        ),
        HistoricalInterval(
            slug="plastic_constant",
            name="Plastic Constant",
            expression="real_root(x^3 - x - 1)",
            value=plastic_constant(),
            tradition="20th century architectural proportion, modern speculative theory",
            note="Appears in recursive proportion systems used by some contemporary theorists.",
        ),
        HistoricalInterval(
            slug="sqrt3",
            name="Square Root of 3",
            expression="sqrt(3)",
            value=math.sqrt(3),
            tradition="Classical geometry and monochord extrapolation",
            note="A geometric constant occasionally proposed in scalar construction.",
        ),
        HistoricalInterval(
            slug="sqrt_3_over_2",
            name="Root Three Halves",
            expression="sqrt(3/2)",
            value=math.sqrt(3 / 2),
            tradition="Medieval and Renaissance geometric means",
            note="Geometric mean between 1/1 and 3/2.",
        ),
        HistoricalInterval(
            slug="cube_root_two",
            name="Cube Root of 2",
            expression="2^(1/3)",
            value=2 ** (1 / 3),
            tradition="Renaissance proportion studies, later equal-step systems",
            note="Defines the equal division of the octave into 3 parts.",
        ),
        HistoricalInterval(
            slug="two_thirds_power",
            name="Two to Two Thirds",
            expression="2^(2/3)",
            value=2 ** (2 / 3),
            tradition="Triadic equal-step proposals",
            note="Second step of the 3-EDO partition.",
        ),
        HistoricalInterval(
            slug="edo12_semitone",
            name="12-EDO Semitone",
            expression="2^(1/12)",
            value=2 ** (1 / 12),
            tradition="17th-20th century Western keyboard temperament",
            note="Canonical equal-tempered semitone.",
        ),
        HistoricalInterval(
            slug="edo19_step",
            name="19-EDO Step",
            expression="2^(1/19)",
            value=2 ** (1 / 19),
            tradition="Renaissance temperament experiments and modern xenharmonics",
            note="Discussed as an alternative meantone-compatible equal temperament.",
        ),
        HistoricalInterval(
            slug="edo31_step",
            name="31-EDO Step",
            expression="2^(1/31)",
            value=2 ** (1 / 31),
            tradition="Huygens and post-meantone theorists",
            note="Known for close approximations to quarter-comma meantone relations.",
        ),
        HistoricalInterval(
            slug="edo53_step",
            name="53-EDO Step",
            expression="2^(1/53)",
            value=2 ** (1 / 53),
            tradition="Mercator and later precision temperament theory",
            note="Famous for strong fifth and comma approximations.",
        ),
        HistoricalInterval(
            slug="quarter_tone_24edo",
            name="24-EDO Quarter Tone",
            expression="2^(1/24)",
            value=2 ** (1 / 24),
            tradition="20th century microtonal modernism",
            note="Common reference in quarter-tone composition practice.",
        ),
        HistoricalInterval(
            slug="sixth_tone_72edo",
            name="72-EDO Sixth Tone",
            expression="2^(1/72)",
            value=2 ** (1 / 72),
            tradition="Alois Haba and fine-grained microtonal systems",
            note="A fine subdivision often used in pedagogical microtonal charts.",
        ),
        HistoricalInterval(
            slug="bp_13th_tritave_step",
            name="Bohlen-Pierce Step (13-Tritave)",
            expression="3^(1/13)",
            value=3 ** (1 / 13),
            tradition="Late 20th century non-octave tuning theory",
            note="Equal step in 13-division tritave systems (3:1 period).",
        ),
        HistoricalInterval(
            slug="bp_12th_tritave_step",
            name="Bohlen-Pierce Step (12-Tritave)",
            expression="3^(1/12)",
            value=3 ** (1 / 12),
            tradition="Non-octave equal-step variants",
            note="Alternative tritave partition explored in electronic tuning design.",
        ),
        HistoricalInterval(
            slug="pi_over_2",
            name="Pi over Two",
            expression="pi / 2",
            value=math.pi / 2,
            tradition="Esoteric and speculative numerological acoustics",
            note="A mathematically prominent constant occasionally used in symbolic tunings.",
        ),
        HistoricalInterval(
            slug="e_over_2",
            name="Euler over Two",
            expression="e / 2",
            value=math.e / 2,
            tradition="Modern mathematically driven tuning proposals",
            note="Used in some algorithmic and conceptual interval studies.",
        ),
    ]


def cents_from_ratio(value: float) -> float:
    return 1200.0 * math.log2(value)


def clean_field(text: str) -> str:
    return text.replace("\t", " ").replace("\n", " ").strip()


def read_extra_json(path: Path) -> List[HistoricalInterval]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError("Extra interval JSON must be a list of objects.")

    records: List[HistoricalInterval] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"JSON item {index} is not an object.")
        try:
            record = HistoricalInterval(
                slug=str(item["slug"]),
                name=str(item["name"]),
                expression=str(item["expression"]),
                value=float(item["value"]),
                tradition=str(item.get("tradition", "user-supplied")),
                note=str(item.get("note", "")),
            )
        except KeyError as error:
            raise ValueError(f"JSON item {index} is missing required key: {error}") from error
        records.append(record)
    return records


def build_interval_corpus(extra_json: Path | None) -> List[HistoricalInterval]:
    intervals = default_intervals()
    if extra_json is not None:
        intervals.extend(read_extra_json(extra_json))
    return [entry for entry in intervals if 1.0 < entry.value < 2.0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate curated irrational intervals between 1/1 and 2/1."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("historical-intervals.txt"),
        help="Output text file path.",
    )
    parser.add_argument(
        "--precision",
        type=int,
        default=15,
        help="Decimal places for ratio and cent values.",
    )
    parser.add_argument(
        "--sort-by",
        choices=("value", "name", "slug"),
        default="value",
        help="Sort key for output rows.",
    )
    parser.add_argument(
        "--extra-json",
        type=Path,
        default=None,
        help="Optional JSON file with additional interval objects.",
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.precision < 0:
        raise ValueError("--precision must be >= 0.")


def sort_intervals(intervals: List[HistoricalInterval], sort_by: str) -> List[HistoricalInterval]:
    if sort_by == "name":
        return sorted(intervals, key=lambda item: item.name.lower())
    if sort_by == "slug":
        return sorted(intervals, key=lambda item: item.slug.lower())
    return sorted(intervals, key=lambda item: item.value)


def write_output(
    output_path: Path,
    intervals: Iterable[HistoricalInterval],
    precision: int,
    sort_by: str,
    used_extra_json: bool,
) -> int:
    rows = list(intervals)
    with output_path.open("w", encoding="utf-8") as handle:
        handle.write("# Interval Thesaurus - Historical and Esoteric Irrationals\n")
        handle.write(
            f"# generated_utc={datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
        )
        handle.write(f"# sort_by={sort_by}\n")
        handle.write(f"# used_extra_json={used_extra_json}\n")
        handle.write(f"# total_rows={len(rows)}\n")
        handle.write("slug\tname\tratio\tcents\texpression\ttradition\tnote\n")

        for interval in rows:
            cents = cents_from_ratio(interval.value)
            handle.write(
                f"{clean_field(interval.slug)}\t"
                f"{clean_field(interval.name)}\t"
                f"{interval.value:.{precision}f}\t"
                f"{cents:.{precision}f}\t"
                f"{clean_field(interval.expression)}\t"
                f"{clean_field(interval.tradition)}\t"
                f"{clean_field(interval.note)}\n"
            )

    return len(rows)


def main() -> None:
    args = parse_args()
    validate_args(args)
    intervals = build_interval_corpus(args.extra_json)
    ordered = sort_intervals(intervals, args.sort_by)
    total = write_output(
        output_path=args.output,
        intervals=ordered,
        precision=args.precision,
        sort_by=args.sort_by,
        used_extra_json=args.extra_json is not None,
    )
    print(f"Wrote {total} rows to {args.output}")


if __name__ == "__main__":
    main()
