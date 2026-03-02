#!/usr/bin/env python3
"""
Generate historical and esoteric irrational intervals for the intervalEncyclopedia.

The default corpus intentionally scales into tens of thousands of rows by combining:
- Octave equal divisions (EDO), including landmark historical systems.
- Tritave equal divisions (EDT/ED3), including Bohlen-Pierce landmarks.
- Equal divisions of consonant intervals (3/2, 5/4, 7/6).
- Wendy Carlos alpha/beta/gamma non-octave families.
- Imported ratio/name corpora from Scribd, Miraheze, Huygens-Fokker, and Xenharmonic Wiki.
- Geometric and mathematical constants used in speculative tuning practice.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from cli_output import (
    Reporter,
    add_output_control_args,
    create_reporter,
    validate_output_control_args,
)


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


def infer_source_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix == ".csv":
        return "csv"
    return "tsv"


@dataclass(frozen=True)
class HistoricalInterval:
    slug: str
    name: str
    expression: str
    value: float
    tradition: str
    note: str
    subgroup_monzo: str = ""
    fjs_name: str = ""
    comma_size: str = ""
    xen_url: str = ""
    cents_min: str = ""
    cents_max: str = ""
    culture: str = ""
    aliases: str = ""


@dataclass(frozen=True)
class Annotation:
    tradition: str
    note_template: str


@dataclass(frozen=True)
class CarlosScale:
    slug: str
    name: str
    cents_per_step: float
    tradition: str
    note: str


OCTAVE_EDO_LANDMARKS: Dict[int, Annotation] = {
    12: Annotation(
        tradition="17th-20th century Western keyboard temperament",
        note_template="Canonical 12-EDO lattice used across common-practice and modern repertoire.",
    ),
    19: Annotation(
        tradition="Renaissance and early-modern alternate equal temperament theory",
        note_template="19-EDO division discussed in post-just and meantone-adjacent traditions.",
    ),
    22: Annotation(
        tradition="South Asian sruti discourse and modern equalized reinterpretations",
        note_template="22-way equalized survey companion to historical shruti frameworks.",
    ),
    24: Annotation(
        tradition="Arabic/Turkish quarter-tone pedagogy and 20th-century microtonal modernism",
        note_template="24-EDO quarter-tone aligned division for comparative tuning analysis.",
    ),
    31: Annotation(
        tradition="Huygens and Fokker 31-tone theory",
        note_template="31-EDO division known for near-meantone behavior and comma handling.",
    ),
    41: Annotation(
        tradition="Fine-grained equal temperament proposals in historical and modern microtonality",
        note_template="41-EDO division from high-resolution comma-oriented temperament studies.",
    ),
    53: Annotation(
        tradition="Jing Fang and Mercator/Holder precision temperament lineage",
        note_template="53-EDO division famous for strong fifth and comma approximations.",
    ),
    72: Annotation(
        tradition="Carrillo/Haba ultra-chromatic systems and later pedagogical microtonality",
        note_template="72-EDO sixth-tone granularity used in advanced micro-interval practice.",
    ),
    87: Annotation(
        tradition="Fokker-era high-resolution temperament search",
        note_template="87-EDO appears in historical error-minimization and comparison tables.",
    ),
    94: Annotation(
        tradition="Fokker-era high-resolution temperament search",
        note_template="94-EDO appears in historical error-minimization and comparison tables.",
    ),
}

TRITAVE_EDT_LANDMARKS: Dict[int, Annotation] = {
    13: Annotation(
        tradition="Bohlen-Pierce non-octave tritave system",
        note_template="13-EDT step from the canonical Bohlen-Pierce equal tritave framework.",
    ),
    39: Annotation(
        tradition="Paul Erlich triple Bohlen-Pierce extension",
        note_template="39-EDT step from triple Bohlen-Pierce expansions.",
    ),
}

OCTAVE_EDO_FALLBACK = Annotation(
    tradition="Contemporary xenharmonic equal-division cataloging (EDO)",
    note_template="Step {step} in {divisions}-EDO.",
)

TRITAVE_EDT_FALLBACK = Annotation(
    tradition="Contemporary xenharmonic equal tritave cataloging (EDT/ED3)",
    note_template="Step {step} in {divisions}-EDT (3:1 period family).",
)

FIFTH_ED_FALLBACK = Annotation(
    tradition="Meantone and circulating-temperament consonance tempering studies",
    note_template="Equal division of the perfect fifth (3/2), step {step} of {divisions}.",
)

THIRD_ED_FALLBACK = Annotation(
    tradition="Third-tempering and consonance-splitting microtonal studies",
    note_template="Equal division of the major third (5/4), step {step} of {divisions}.",
)

SEPTIMAL_ED_FALLBACK = Annotation(
    tradition="Esoteric septimal microtonal experimentation",
    note_template="Equal division of the septimal minor third (7/6), step {step} of {divisions}.",
)


def plastic_constant() -> float:
    # Real root of x^3 - x - 1 = 0.
    return ((9 + math.sqrt(69)) / 18) ** (1 / 3) + ((9 - math.sqrt(69)) / 18) ** (1 / 3)


def seed_constants() -> List[HistoricalInterval]:
    phi = (1 + math.sqrt(5)) / 2
    return [
        HistoricalInterval(
            slug="sqrt2_tritone",
            name="Geometric Tritone",
            expression="sqrt(2)",
            value=math.sqrt(2),
            tradition="Greek geometry and equal-temperament discourse",
            note="Geometric mean between 1/1 and 2/1.",
        ),
        HistoricalInterval(
            slug="phi_divine",
            name="Golden Ratio",
            expression="(1 + sqrt(5)) / 2",
            value=phi,
            tradition="Pythagorean/Platonic geometry and later esoteric tuning theory",
            note="Pentagonal proportion constant used in speculative interval construction.",
        ),
        HistoricalInterval(
            slug="plastic_constant",
            name="Plastic Constant",
            expression="real_root(x^3 - x - 1)",
            value=plastic_constant(),
            tradition="20th-century proportion theory and modern algorithmic tuning",
            note="Appears in recursive and morphic proportion systems.",
        ),
        HistoricalInterval(
            slug="sqrt3",
            name="Square Root of 3",
            expression="sqrt(3)",
            value=math.sqrt(3),
            tradition="Classical geometry and monochord extrapolation",
            note="A geometric constant occasionally used as an octave-reduced interval source.",
        ),
        HistoricalInterval(
            slug="sqrt_3_over_2",
            name="Root Three Halves",
            expression="sqrt(3/2)",
            value=math.sqrt(3 / 2),
            tradition="Medieval and Renaissance geometric means",
            note="Geometric mean between unison and perfect fifth.",
        ),
        HistoricalInterval(
            slug="cube_root_two",
            name="Cube Root of 2",
            expression="2^(1/3)",
            value=2 ** (1 / 3),
            tradition="Renaissance proportion studies and equal-step constructions",
            note="Defines an equal division of the octave into three parts.",
        ),
        HistoricalInterval(
            slug="two_thirds_power",
            name="Two to Two Thirds",
            expression="2^(2/3)",
            value=2 ** (2 / 3),
            tradition="Triadic equal-step proposals",
            note="Second step of the 3-way equal octave partition.",
        ),
        HistoricalInterval(
            slug="sqrt_pi_over_2",
            name="Root Pi over Two",
            expression="sqrt(pi / 2)",
            value=math.sqrt(math.pi / 2),
            tradition="Modern speculative mathematical tuning",
            note="Square-root reduction of pi-based symbolic interval proposals.",
        ),
        HistoricalInterval(
            slug="sqrt_e_over_2",
            name="Root Euler over Two",
            expression="sqrt(e / 2)",
            value=math.sqrt(math.e / 2),
            tradition="Algorithmic/computational tuning experiments",
            note="Square-root reduction of e-based symbolic interval proposals.",
        ),
        HistoricalInterval(
            slug="pi_over_2",
            name="Pi over Two",
            expression="pi / 2",
            value=math.pi / 2,
            tradition="Esoteric and numerological acoustics",
            note="Pi-derived interval used in symbolic and conceptual tuning systems.",
        ),
        HistoricalInterval(
            slug="e_over_2",
            name="Euler over Two",
            expression="e / 2",
            value=math.e / 2,
            tradition="Modern mathematically driven tuning proposals",
            note="e-derived interval used in conceptual interval studies.",
        ),
    ]


def carlos_scales() -> List[CarlosScale]:
    return [
        CarlosScale(
            slug="alpha",
            name="Carlos Alpha Scale",
            cents_per_step=78.0,
            tradition="Wendy Carlos non-octave scale systems",
            note="Alpha scale step chain from Carlos tuning experiments.",
        ),
        CarlosScale(
            slug="beta",
            name="Carlos Beta Scale",
            cents_per_step=63.8,
            tradition="Wendy Carlos non-octave scale systems",
            note="Beta scale step chain from Carlos tuning experiments.",
        ),
        CarlosScale(
            slug="gamma",
            name="Carlos Gamma Scale",
            cents_per_step=35.1,
            tradition="Wendy Carlos non-octave scale systems",
            note="Gamma scale step chain from Carlos tuning experiments.",
        ),
    ]


def cents_from_ratio(value: float) -> float:
    return 1200.0 * math.log2(value)


def clean_field(text: str) -> str:
    return text.replace("\t", " ").replace("\n", " ").strip()


def parse_optional_float(value: Any) -> str:
    text = str(value).strip()
    if not text:
        return ""
    return f"{float(text):.12f}".rstrip("0").rstrip(".")


def read_extra_intervals(path: Path) -> List[HistoricalInterval]:
    source_format = infer_source_format(path)

    if source_format == "json":
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        items: Any
        if isinstance(payload, dict):
            if isinstance(payload.get("rows"), list):
                items = payload["rows"]
            elif isinstance(payload.get("data"), list):
                items = payload["data"]
            else:
                raise ValueError(
                    "Extra JSON must be a list, or an object with 'rows' or 'data' list."
                )
        elif isinstance(payload, list):
            items = payload
        else:
            raise ValueError("Extra JSON must be a list of objects.")

        records: List[HistoricalInterval] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"Extra JSON item {index} is not an object.")
            try:
                record = HistoricalInterval(
                    slug=str(item["slug"]).strip(),
                    name=str(item["name"]).strip(),
                    expression=str(item["expression"]).strip(),
                    value=float(item["value"]),
                    tradition=str(item.get("tradition", "user-supplied")).strip(),
                    note=str(item.get("note", "")).strip(),
                    subgroup_monzo=str(item.get("subgroup_monzo", "")).strip(),
                    fjs_name=str(item.get("fjs_name", "")).strip(),
                    comma_size=str(item.get("comma_size", "")).strip(),
                    xen_url=str(item.get("xen_url", "")).strip(),
                    cents_min=parse_optional_float(item.get("cents_min", "")),
                    cents_max=parse_optional_float(item.get("cents_max", "")),
                    culture=str(item.get("culture", "")).strip(),
                    aliases=str(item.get("aliases", "")).strip(),
                )
            except KeyError as error:
                raise ValueError(f"Extra JSON item {index} is missing required key: {error}") from error
            records.append(record)
        return records

    delimiter = "," if source_format == "csv" else "\t"
    records: List[HistoricalInterval] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        for line_number, raw_parts in enumerate(reader, start=1):
            if not raw_parts:
                continue
            if raw_parts[0].lstrip().startswith("#"):
                continue
            parts = [part.strip() for part in raw_parts]
            if not any(parts):
                continue
            if parts[0].lower() == "slug":
                continue
            if len(parts) < 4:
                raise ValueError(
                    f"Extra source parse error at line {line_number}: expected at least "
                    "'slug, name, expression, value'."
                )
            records.append(
                HistoricalInterval(
                    slug=parts[0],
                    name=parts[1] or "(unnamed interval)",
                    expression=parts[2],
                    value=float(parts[3]),
                    tradition=parts[4] if len(parts) > 4 and parts[4] else "user-supplied",
                    note=parts[5] if len(parts) > 5 else "",
                    subgroup_monzo=parts[6] if len(parts) > 6 else "",
                    fjs_name=parts[7] if len(parts) > 7 else "",
                    comma_size=parts[8] if len(parts) > 8 else "",
                    xen_url=parts[9] if len(parts) > 9 else "",
                    cents_min=parse_optional_float(parts[10]) if len(parts) > 10 else "",
                    cents_max=parse_optional_float(parts[11]) if len(parts) > 11 else "",
                    culture=parts[12] if len(parts) > 12 else "",
                    aliases=parts[13] if len(parts) > 13 else "",
                )
            )
    return records


def read_extra_json(path: Path) -> List[HistoricalInterval]:
    # Backward-compatible alias for existing CLI option naming.
    return read_extra_intervals(path)


def parse_ratio_fraction(text: str) -> Fraction:
    match = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", text)
    if not match:
        raise ValueError(f"Invalid ratio token: {text}")
    numerator = int(match.group(1))
    denominator = int(match.group(2))
    if denominator == 0:
        raise ValueError(f"Invalid ratio token with zero denominator: {text}")
    return Fraction(numerator, denominator)


def integer_factorization(value: int) -> List[tuple[int, int]]:
    if value < 1:
        raise ValueError("Factorization input must be >= 1.")
    if value == 1:
        return []

    factors: List[tuple[int, int]] = []
    remaining = value
    divisor = 2
    while divisor * divisor <= remaining:
        exponent = 0
        while remaining % divisor == 0:
            remaining //= divisor
            exponent += 1
        if exponent > 0:
            factors.append((divisor, exponent))
        divisor = 3 if divisor == 2 else divisor + 2
    if remaining > 1:
        factors.append((remaining, 1))
    return factors


def format_integer_factorization(value: int) -> str:
    factors = integer_factorization(value)
    if not factors:
        return "1"

    parts: List[str] = []
    for prime, exponent in factors:
        if exponent == 1:
            parts.append(str(prime))
        else:
            parts.append(f"{prime}^{exponent}")
    return " * ".join(parts)


def format_ratio_prime_factorization(numerator: int, denominator: int) -> str:
    numerator_text = format_integer_factorization(numerator)
    denominator_text = format_integer_factorization(denominator)
    if denominator == 1:
        return numerator_text
    if numerator == 1:
        return f"1 / {denominator_text}"
    return f"{numerator_text} / {denominator_text}"


def fraction_to_subgroup_monzo(value: Fraction) -> str:
    numerator_factors = dict(integer_factorization(value.numerator))
    denominator_factors = dict(integer_factorization(value.denominator))
    primes = sorted(set(numerator_factors) | set(denominator_factors))
    if not primes:
        return "<0> @ [1]"

    exponents: List[str] = []
    for prime in primes:
        exponent = numerator_factors.get(prime, 0) - denominator_factors.get(prime, 0)
        exponents.append(str(exponent))
    basis = ",".join(str(prime) for prime in primes)
    return f"<{' '.join(exponents)}> @ [{basis}]"


def parse_rational_expression(text: str) -> Fraction | None:
    fraction_match = re.fullmatch(
        r"\s*(\d+)\s*/\s*(\d+)\s*(?:\(\s*from\s+\d+\s*/\s*\d+\s*\))?\s*",
        text,
    )
    if fraction_match:
        numerator = int(fraction_match.group(1))
        denominator = int(fraction_match.group(2))
        if denominator == 0:
            return None
        return Fraction(numerator, denominator)

    integer_match = re.fullmatch(r"\s*(\d+)\s*", text)
    if integer_match:
        return Fraction(int(integer_match.group(1)), 1)
    return None


def interval_prime_factorization(interval: HistoricalInterval) -> str:
    ratio = parse_rational_expression(interval.expression)
    if ratio is None:
        return "-"
    return format_ratio_prime_factorization(ratio.numerator, ratio.denominator)


def octave_reduce_fraction(value: Fraction) -> Fraction:
    reduced = value
    while reduced > 2:
        reduced /= 2
    while reduced < 1:
        reduced *= 2
    return reduced


def format_source_provenance(source_page: str, source_url: str) -> str:
    if source_page and source_url:
        return f" Source page: {source_page} ({source_url})."
    if source_page:
        return f" Source page: {source_page}."
    if source_url:
        return f" Source: {source_url}."
    return ""


def load_ratio_name_records(
    path: Path,
    *,
    source_label: str,
) -> List[dict[str, str]]:
    source_format = infer_source_format(path)
    records: List[dict[str, str]] = []

    if source_format == "json":
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        items: Any
        if isinstance(payload, dict):
            if isinstance(payload.get("rows"), list):
                items = payload["rows"]
            elif isinstance(payload.get("data"), list):
                items = payload["data"]
            else:
                raise ValueError(
                    f"{source_label} JSON must be a list, or an object with 'rows' or 'data'."
                )
        elif isinstance(payload, list):
            items = payload
        else:
            raise ValueError(f"{source_label} JSON must be a list or object.")

        for index, item in enumerate(items, start=1):
            if isinstance(item, dict):
                ratio_text = str(item.get("ratio", "")).strip()
                interval_name = str(item.get("name", "")).strip()
                source_page = str(item.get("source_page", "")).strip()
                source_url = str(item.get("source_url", "")).strip()
                subgroup_monzo = str(item.get("subgroup_monzo", "")).strip()
                fjs_name = str(item.get("fjs_name", "")).strip()
                xen_url = str(item.get("xen_url", "")).strip()
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                ratio_text = str(item[0]).strip()
                interval_name = str(item[1]).strip()
                source_page = str(item[2]).strip() if len(item) > 2 else ""
                source_url = str(item[3]).strip() if len(item) > 3 else ""
                subgroup_monzo = str(item[4]).strip() if len(item) > 4 else ""
                fjs_name = str(item[5]).strip() if len(item) > 5 else ""
                xen_url = str(item[6]).strip() if len(item) > 6 else ""
            else:
                raise ValueError(f"{source_label} JSON item {index} has unsupported shape.")

            if not ratio_text:
                raise ValueError(f"{source_label} JSON item {index} is missing ratio.")
            records.append(
                {
                    "ratio": ratio_text,
                    "name": interval_name,
                    "source_page": source_page,
                    "source_url": source_url,
                    "subgroup_monzo": subgroup_monzo,
                    "fjs_name": fjs_name,
                    "xen_url": xen_url,
                }
            )
        return records

    delimiter = "," if source_format == "csv" else "\t"
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        for line_number, raw_parts in enumerate(reader, start=1):
            if not raw_parts:
                continue
            if raw_parts[0].lstrip().startswith("#"):
                continue
            parts = [part.strip() for part in raw_parts]
            if not any(parts):
                continue
            if parts[0].lower() == "ratio":
                continue
            if len(parts) < 2:
                raise ValueError(
                    f"{source_label} parse error at line {line_number}: "
                    "expected at least 'ratio,name'."
                )
            ratio_text = parts[0]
            interval_name = parts[1]
            source_page = parts[2] if len(parts) > 2 else ""
            source_url = parts[3] if len(parts) > 3 else ""
            subgroup_monzo = parts[4] if len(parts) > 4 else ""
            fjs_name = parts[5] if len(parts) > 5 else ""
            xen_url = parts[6] if len(parts) > 6 else ""
            records.append(
                {
                    "ratio": ratio_text,
                    "name": interval_name,
                    "source_page": source_page,
                    "source_url": source_url,
                    "subgroup_monzo": subgroup_monzo,
                    "fjs_name": fjs_name,
                    "xen_url": xen_url,
                }
            )
    return records


def build_ratio_import_rows(
    *,
    records: List[dict[str, str]],
    slug_prefix: str,
    tradition: str,
    note_without_reduction: str,
    note_with_reduction: str,
    include_xen_metadata: bool = False,
) -> List[HistoricalInterval]:
    rows: List[HistoricalInterval] = []
    for row_count, record in enumerate(records, start=1):
        ratio_text = record.get("ratio", "").strip()
        raw_interval_name = record.get("name", "").strip()
        source_page = record.get("source_page", "").strip()
        source_url = record.get("source_url", "").strip()
        subgroup_monzo = record.get("subgroup_monzo", "").strip()
        fjs_name = record.get("fjs_name", "").strip()
        xen_url = record.get("xen_url", "").strip()
        interval_name = raw_interval_name or "(unnamed interval)"
        ratio_fraction = parse_ratio_fraction(ratio_text)
        reduced_fraction = octave_reduce_fraction(ratio_fraction)
        reduced_text = f"{reduced_fraction.numerator}/{reduced_fraction.denominator}"

        if reduced_fraction == ratio_fraction:
            expression = ratio_text
            reduction_note = note_without_reduction
        else:
            expression = f"{reduced_text} (from {ratio_text})"
            reduction_note = note_with_reduction

        provenance = format_source_provenance(source_page=source_page, source_url=source_url)
        row_subgroup_monzo = ""
        row_fjs_name = ""
        row_xen_url = ""
        row_comma_size = ""
        if include_xen_metadata:
            row_subgroup_monzo = subgroup_monzo
            if not row_subgroup_monzo:
                row_subgroup_monzo = fraction_to_subgroup_monzo(reduced_fraction)
            row_fjs_name = fjs_name or interval_name
            row_xen_url = xen_url or source_url
            if "comma" in interval_name.casefold():
                row_comma_size = f"{cents_from_ratio(float(reduced_fraction)):.24f}"

        rows.append(
            HistoricalInterval(
                slug=f"{slug_prefix}_{row_count:04d}",
                name=interval_name,
                expression=expression,
                value=float(reduced_fraction),
                tradition=tradition,
                note=f"{reduction_note}{provenance}",
                subgroup_monzo=row_subgroup_monzo,
                fjs_name=row_fjs_name,
                comma_size=row_comma_size,
                xen_url=row_xen_url,
            )
        )

    return rows


def read_scribd_interval_tsv(path: Path) -> List[HistoricalInterval]:
    return build_ratio_import_rows(
        records=load_ratio_name_records(path, source_label="Scribd source"),
        slug_prefix="scribd",
        tradition="Scribd List of intervals compilation (historical/esoteric mixed sources)",
        note_without_reduction="Imported from Scribd List of intervals.",
        note_with_reduction=(
            "Imported from Scribd List of intervals and octave-reduced to project range."
        ),
    )


def read_miraheze_interval_tsv(path: Path) -> List[HistoricalInterval]:
    return build_ratio_import_rows(
        records=load_ratio_name_records(path, source_label="Miraheze source"),
        slug_prefix="miraheze",
        tradition="Microtonal Encyclopedia (miraheze.org) interval pages",
        note_without_reduction=(
            "Imported from Microtonal Encyclopedia (Miraheze) without octave reduction."
        ),
        note_with_reduction=(
            "Imported from Microtonal Encyclopedia (Miraheze) and octave-reduced to project range."
        ),
    )


def read_huygens_fokker_interval_tsv(path: Path) -> List[HistoricalInterval]:
    return build_ratio_import_rows(
        records=load_ratio_name_records(path, source_label="Huygens-Fokker source"),
        slug_prefix="huygens_fokker",
        tradition="Huygens-Fokker Bohlen-Pierce Site (huygens-fokker.org/bpsite) interval tables",
        note_without_reduction=(
            "Imported from Huygens-Fokker Bohlen-Pierce interval tables without octave reduction."
        ),
        note_with_reduction=(
            "Imported from Huygens-Fokker Bohlen-Pierce interval tables and octave-reduced "
            "to project range."
        ),
    )


def read_xenharmonic_wiki_interval_tsv(path: Path) -> List[HistoricalInterval]:
    return build_ratio_import_rows(
        records=load_ratio_name_records(path, source_label="Xenharmonic Wiki source"),
        slug_prefix="xen_wiki",
        tradition="Xenharmonic Wiki (en.xen.wiki) interval pages",
        note_without_reduction=(
            "Imported from Xenharmonic Wiki interval pages without octave reduction."
        ),
        note_with_reduction=(
            "Imported from Xenharmonic Wiki interval pages and octave-reduced to project range."
        ),
        include_xen_metadata=True,
    )


def read_world_intervals(path: Path, source_label: str) -> List[HistoricalInterval]:
    rows = read_extra_intervals(path)
    normalized: List[HistoricalInterval] = []
    for row in rows:
        note = row.note.strip()
        if note:
            note = f"{note} Source: {source_label}."
        else:
            note = f"Imported from {source_label}."
        normalized.append(
            HistoricalInterval(
                slug=row.slug,
                name=row.name,
                expression=row.expression,
                value=row.value,
                tradition=row.tradition,
                note=note,
                subgroup_monzo=row.subgroup_monzo,
                fjs_name=row.fjs_name,
                comma_size=row.comma_size,
                xen_url=row.xen_url,
                cents_min=row.cents_min,
                cents_max=row.cents_max,
                culture=row.culture,
                aliases=row.aliases,
            )
        )
    return normalized


def format_power_expression(base_expression: str, step: int, divisions: int) -> str:
    if "/" in base_expression:
        return f"({base_expression})^({step}/{divisions})"
    return f"{base_expression}^({step}/{divisions})"


def generate_equal_division_family(
    *,
    slug_prefix: str,
    system_label: str,
    period_ratio: float,
    period_expression: str,
    min_divisions: int,
    max_divisions: int,
    fallback_annotation: Annotation,
    landmark_annotations: Dict[int, Annotation] | None = None,
    reporter: Reporter | None = None,
) -> List[HistoricalInterval]:
    rows: List[HistoricalInterval] = []
    annotations = landmark_annotations or {}
    total_steps = sum((divisions - 1) for divisions in range(min_divisions, max_divisions + 1))
    progress = None
    if reporter is not None:
        reporter.verbose(
            f"Generating {system_label} family ({min_divisions}..{max_divisions} divisions)..."
        )
        progress = reporter.progress(total=total_steps, label=f"{system_label} family")
    generated = 0

    for divisions in range(min_divisions, max_divisions + 1):
        annotation = annotations.get(divisions, fallback_annotation)
        for step in range(1, divisions):
            value = period_ratio ** (step / divisions)
            rows.append(
                HistoricalInterval(
                    slug=f"{slug_prefix}_{divisions:04d}_{step:04d}",
                    name=f"{divisions}-{system_label} Step {step}",
                    expression=format_power_expression(period_expression, step, divisions),
                    value=value,
                    tradition=annotation.tradition,
                    note=annotation.note_template.format(step=step, divisions=divisions),
                )
            )
            generated += 1
            if progress is not None:
                progress.update(generated)

    if progress is not None:
        progress.finish()

    return rows


def count_carlos_intervals() -> int:
    total = 0
    for scale in carlos_scales():
        step_ratio = 2 ** (scale.cents_per_step / 1200.0)
        step = 1
        while True:
            value = step_ratio**step
            if value >= 2.0:
                break
            total += 1
            step += 1
    return total


def generate_carlos_intervals(reporter: Reporter | None = None) -> List[HistoricalInterval]:
    rows: List[HistoricalInterval] = []
    progress = None
    if reporter is not None:
        reporter.verbose("Generating Carlos alpha/beta/gamma families...")
        progress = reporter.progress(total=count_carlos_intervals(), label="Carlos family")
    generated = 0
    for scale in carlos_scales():
        step_ratio = 2 ** (scale.cents_per_step / 1200.0)
        step = 1
        while True:
            value = step_ratio**step
            if value >= 2.0:
                break
            rows.append(
                HistoricalInterval(
                    slug=f"carlos_{scale.slug}_{step:04d}",
                    name=f"{scale.name} Step {step}",
                    expression=f"2^({step}*{scale.cents_per_step:.6f}/1200)",
                    value=value,
                    tradition=scale.tradition,
                    note=scale.note,
                )
            )
            generated += 1
            if progress is not None:
                progress.update(generated)
            step += 1

    if progress is not None:
        progress.finish()

    return rows


def dedupe_by_slug(intervals: Iterable[HistoricalInterval]) -> List[HistoricalInterval]:
    seen: set[str] = set()
    rows: List[HistoricalInterval] = []
    for interval in intervals:
        if interval.slug in seen:
            continue
        seen.add(interval.slug)
        rows.append(interval)
    return rows


def build_interval_corpus(args: argparse.Namespace, reporter: Reporter) -> List[HistoricalInterval]:
    reporter.info("Building historical interval corpus...")
    rows: List[HistoricalInterval] = []
    rows.extend(seed_constants())
    rows.extend(
        generate_equal_division_family(
            slug_prefix="edo",
            system_label="EDO",
            period_ratio=2.0,
            period_expression="2",
            min_divisions=args.min_octave_edo,
            max_divisions=args.max_octave_edo,
            fallback_annotation=OCTAVE_EDO_FALLBACK,
            landmark_annotations=OCTAVE_EDO_LANDMARKS,
            reporter=reporter,
        )
    )
    rows.extend(
        generate_equal_division_family(
            slug_prefix="edt",
            system_label="EDT",
            period_ratio=3.0,
            period_expression="3",
            min_divisions=args.min_tritave_edt,
            max_divisions=args.max_tritave_edt,
            fallback_annotation=TRITAVE_EDT_FALLBACK,
            landmark_annotations=TRITAVE_EDT_LANDMARKS,
            reporter=reporter,
        )
    )
    rows.extend(
        generate_equal_division_family(
            slug_prefix="ed_fifth",
            system_label="ED(3/2)",
            period_ratio=3.0 / 2.0,
            period_expression="3/2",
            min_divisions=args.min_consonance_divisions,
            max_divisions=args.max_consonance_divisions,
            fallback_annotation=FIFTH_ED_FALLBACK,
            reporter=reporter,
        )
    )
    rows.extend(
        generate_equal_division_family(
            slug_prefix="ed_third",
            system_label="ED(5/4)",
            period_ratio=5.0 / 4.0,
            period_expression="5/4",
            min_divisions=args.min_consonance_divisions,
            max_divisions=args.max_consonance_divisions,
            fallback_annotation=THIRD_ED_FALLBACK,
            reporter=reporter,
        )
    )
    rows.extend(
        generate_equal_division_family(
            slug_prefix="ed_septimal",
            system_label="ED(7/6)",
            period_ratio=7.0 / 6.0,
            period_expression="7/6",
            min_divisions=args.min_consonance_divisions,
            max_divisions=args.max_consonance_divisions,
            fallback_annotation=SEPTIMAL_ED_FALLBACK,
            reporter=reporter,
        )
    )
    rows.extend(generate_carlos_intervals(reporter=reporter))
    if not args.exclude_scribd:
        reporter.verbose(f"Importing Scribd intervals from {args.scribd_source}...")
        rows.extend(read_scribd_interval_tsv(args.scribd_source))
    if not args.exclude_miraheze:
        reporter.verbose(f"Importing Miraheze intervals from {args.miraheze_source}...")
        rows.extend(read_miraheze_interval_tsv(args.miraheze_source))
    if not args.exclude_huygens_fokker:
        reporter.verbose(
            f"Importing Huygens-Fokker intervals from {args.huygens_fokker_source}..."
        )
        rows.extend(read_huygens_fokker_interval_tsv(args.huygens_fokker_source))
    if not args.exclude_xen_wiki:
        reporter.verbose(f"Importing Xenharmonic Wiki intervals from {args.xen_wiki_source}...")
        rows.extend(read_xenharmonic_wiki_interval_tsv(args.xen_wiki_source))
    if not args.exclude_indian:
        reporter.verbose(f"Importing Indian classical intervals from {args.indian_source}...")
        rows.extend(
            read_world_intervals(
                args.indian_source,
                source_label="Indian classical interval source",
            )
        )
    if not args.exclude_greek:
        reporter.verbose(f"Importing Greek intervals from {args.greek_source}...")
        rows.extend(
            read_world_intervals(
                args.greek_source,
                source_label="Greek interval source",
            )
        )
    if not args.exclude_middle_east:
        reporter.verbose(f"Importing Middle Eastern intervals from {args.middle_east_source}...")
        rows.extend(
            read_world_intervals(
                args.middle_east_source,
                source_label="Middle Eastern interval source",
            )
        )
    if not args.exclude_world:
        reporter.verbose(f"Importing world-music intervals from {args.world_source}...")
        rows.extend(
            read_world_intervals(
                args.world_source,
                source_label="World music interval source",
            )
        )

    effective_extra_source = args.extra_source or args.extra_json
    if effective_extra_source is not None:
        reporter.verbose(f"Importing extra intervals from {effective_extra_source}...")
        rows.extend(read_extra_intervals(effective_extra_source))

    bounded = [entry for entry in rows if 1.0 <= entry.value <= 2.0]
    reporter.info("De-duplicating by slug and applying [1/1, 2/1] bounds...")
    return dedupe_by_slug(bounded)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate historical/esoteric irrational intervals between 1/1 and 2/1."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("historical-intervals.txt"),
        help="Output path. Supports .txt/.csv/.json (or set --output-format).",
    )
    parser.add_argument(
        "--output-format",
        choices=OUTPUT_FORMAT_CHOICES,
        default="auto",
        help="Output format. Use 'auto' to infer from file extension.",
    )
    parser.add_argument(
        "--precision",
        type=int,
        default=24,
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
        help="Optional JSON file with additional interval objects (legacy alias).",
    )
    parser.add_argument(
        "--extra-source",
        type=Path,
        default=None,
        help=(
            "Optional extra interval source in JSON/CSV/TSV with columns "
            "slug,name,expression,value[,tradition,note,subgroup_monzo,fjs_name,comma_size,"
            "xen_url,cents_min,cents_max,culture,aliases]."
        ),
    )
    parser.add_argument(
        "--scribd-source",
        type=Path,
        default=Path(__file__).resolve().parent / "sources" / "scribd-list-of-intervals.tsv",
        help="Source for imported Scribd rows (.tsv/.csv/.json).",
    )
    parser.add_argument(
        "--exclude-scribd",
        action="store_true",
        help="Skip built-in Scribd interval import.",
    )
    parser.add_argument(
        "--miraheze-source",
        type=Path,
        default=(
            Path(__file__).resolve().parent
            / "sources"
            / "microtonal-miraheze-missing-intervals.tsv"
        ),
        help="Source for imported Microtonal Encyclopedia (Miraheze) rows (.tsv/.csv/.json).",
    )
    parser.add_argument(
        "--exclude-miraheze",
        action="store_true",
        help="Skip built-in Microtonal Encyclopedia (Miraheze) interval import.",
    )
    parser.add_argument(
        "--huygens-fokker-source",
        type=Path,
        default=(
            Path(__file__).resolve().parent / "sources" / "huygens-fokker-bpsite-intervals.tsv"
        ),
        help="Source for imported Huygens-Fokker rows (.tsv/.csv/.json).",
    )
    parser.add_argument(
        "--exclude-huygens-fokker",
        action="store_true",
        help="Skip built-in Huygens-Fokker Bohlen-Pierce interval import.",
    )
    parser.add_argument(
        "--xen-wiki-source",
        type=Path,
        default=(
            Path(__file__).resolve().parent / "sources" / "xenharmonic-wiki-missing-intervals.tsv"
        ),
        help="Source for imported Xenharmonic Wiki rows (.tsv/.csv/.json).",
    )
    parser.add_argument(
        "--exclude-xen-wiki",
        action="store_true",
        help="Skip built-in Xenharmonic Wiki interval import.",
    )
    parser.add_argument(
        "--indian-source",
        type=Path,
        default=Path(__file__).resolve().parent / "sources" / "indian-classical-intervals.tsv",
        help="Source for imported Indian classical interval names (.tsv/.csv/.json).",
    )
    parser.add_argument(
        "--exclude-indian",
        action="store_true",
        help="Skip built-in Indian classical interval import.",
    )
    parser.add_argument(
        "--greek-source",
        type=Path,
        default=Path(__file__).resolve().parent / "sources" / "greek-intervals.tsv",
        help="Source for imported Greek interval names (.tsv/.csv/.json).",
    )
    parser.add_argument(
        "--exclude-greek",
        action="store_true",
        help="Skip built-in Greek interval import.",
    )
    parser.add_argument(
        "--middle-east-source",
        type=Path,
        default=Path(__file__).resolve().parent / "sources" / "middle-east-intervals.tsv",
        help="Source for imported Middle Eastern interval names (.tsv/.csv/.json).",
    )
    parser.add_argument(
        "--exclude-middle-east",
        action="store_true",
        help="Skip built-in Middle Eastern interval import.",
    )
    parser.add_argument(
        "--world-source",
        type=Path,
        default=Path(__file__).resolve().parent / "sources" / "world-music-famous-intervals.tsv",
        help=(
            "Source for imported cross-regional world-music interval names "
            "(.tsv/.csv/.json)."
        ),
    )
    parser.add_argument(
        "--exclude-world",
        action="store_true",
        help="Skip built-in cross-regional world-music interval import.",
    )
    parser.add_argument(
        "--min-octave-edo",
        type=int,
        default=5,
        help="Minimum EDO division for the octave-family sweep.",
    )
    parser.add_argument(
        "--max-octave-edo",
        type=int,
        default=64,
        help="Maximum EDO division for the octave-family sweep.",
    )
    parser.add_argument(
        "--min-tritave-edt",
        type=int,
        default=5,
        help="Minimum EDT division for the tritave-family sweep.",
    )
    parser.add_argument(
        "--max-tritave-edt",
        type=int,
        default=32,
        help="Maximum EDT division for the tritave-family sweep.",
    )
    parser.add_argument(
        "--min-consonance-divisions",
        type=int,
        default=5,
        help="Minimum equal divisions for consonance families (3/2, 5/4, 7/6).",
    )
    parser.add_argument(
        "--max-consonance-divisions",
        type=int,
        default=32,
        help="Maximum equal divisions for consonance families (3/2, 5/4, 7/6).",
    )
    add_output_control_args(parser)
    return parser.parse_args()


def validate_range(minimum: int, maximum: int, label: str) -> None:
    if minimum < 1:
        raise ValueError(f"{label}: minimum must be >= 1.")
    if maximum < minimum:
        raise ValueError(f"{label}: maximum must be >= minimum.")


def validate_args(args: argparse.Namespace) -> None:
    if args.precision < 0:
        raise ValueError("--precision must be >= 0.")
    if args.extra_json is not None and args.extra_source is not None:
        raise ValueError("Use only one of --extra-json or --extra-source.")
    effective_extra_source = args.extra_source or args.extra_json
    if effective_extra_source is not None and not effective_extra_source.exists():
        raise FileNotFoundError(f"Extra source file not found: {effective_extra_source}.")
    if not args.exclude_scribd and not args.scribd_source.exists():
        raise FileNotFoundError(
            f"Scribd source file not found: {args.scribd_source}. "
            "Use --exclude-scribd to skip import."
        )
    if not args.exclude_miraheze and not args.miraheze_source.exists():
        raise FileNotFoundError(
            f"Miraheze source file not found: {args.miraheze_source}. "
            "Use --exclude-miraheze to skip import."
        )
    if not args.exclude_huygens_fokker and not args.huygens_fokker_source.exists():
        raise FileNotFoundError(
            f"Huygens-Fokker source file not found: {args.huygens_fokker_source}. "
            "Use --exclude-huygens-fokker to skip import."
        )
    if not args.exclude_xen_wiki and not args.xen_wiki_source.exists():
        raise FileNotFoundError(
            f"Xenharmonic Wiki source file not found: {args.xen_wiki_source}. "
            "Use --exclude-xen-wiki to skip import."
        )
    if not args.exclude_indian and not args.indian_source.exists():
        raise FileNotFoundError(
            f"Indian source file not found: {args.indian_source}. "
            "Use --exclude-indian to skip import."
        )
    if not args.exclude_greek and not args.greek_source.exists():
        raise FileNotFoundError(
            f"Greek source file not found: {args.greek_source}. "
            "Use --exclude-greek to skip import."
        )
    if not args.exclude_middle_east and not args.middle_east_source.exists():
        raise FileNotFoundError(
            f"Middle East source file not found: {args.middle_east_source}. "
            "Use --exclude-middle-east to skip import."
        )
    if not args.exclude_world and not args.world_source.exists():
        raise FileNotFoundError(
            f"World source file not found: {args.world_source}. "
            "Use --exclude-world to skip import."
        )
    validate_range(args.min_octave_edo, args.max_octave_edo, "octave EDO range")
    validate_range(args.min_tritave_edt, args.max_tritave_edt, "tritave EDT range")
    validate_range(
        args.min_consonance_divisions,
        args.max_consonance_divisions,
        "consonance division range",
    )
    validate_output_control_args(args)


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
    used_extra_source: bool,
    output_format: str,
    reporter: Reporter,
) -> int:
    rows = list(intervals)
    resolved_format = infer_output_format(output_path=output_path, requested_format=output_format)
    reporter.info(f"Writing {len(rows)} historical rows ({resolved_format})...")

    metadata = {
        "title": "intervalEncyclopedia - Historical and Esoteric Irrationals",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sort_by": sort_by,
        "used_extra_source": used_extra_source,
        "total_rows": len(rows),
        "output_format": resolved_format,
    }
    columns = [
        "slug",
        "name",
        "ratio",
        "prime_factorization",
        "cents",
        "cents_min",
        "cents_max",
        "expression",
        "subgroup_monzo",
        "fjs_name",
        "comma_size",
        "xen_url",
        "culture",
        "aliases",
        "tradition",
        "note",
    ]
    progress = reporter.progress(total=len(rows), label="Historical rows")

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        if resolved_format == "txt":
            handle.write(f"# {metadata['title']}\n")
            handle.write(f"# generated_utc={metadata['generated_utc']}\n")
            handle.write(f"# sort_by={metadata['sort_by']}\n")
            handle.write(f"# used_extra_source={metadata['used_extra_source']}\n")
            handle.write(f"# total_rows={metadata['total_rows']}\n")
            handle.write(f"# output_format={metadata['output_format']}\n")
            handle.write("\t".join(columns) + "\n")
            for written, interval in enumerate(rows, start=1):
                prime_factorization = interval_prime_factorization(interval)
                cents = cents_from_ratio(interval.value)
                subgroup_monzo = interval.subgroup_monzo
                ratio = parse_rational_expression(interval.expression)
                if not subgroup_monzo and ratio is not None:
                    subgroup_monzo = fraction_to_subgroup_monzo(ratio)
                comma_size = interval.comma_size
                if not comma_size and "comma" in interval.name.casefold():
                    comma_size = f"{cents:.{precision}f}"
                handle.write(
                    f"{clean_field(interval.slug)}\t"
                    f"{clean_field(interval.name)}\t"
                    f"{interval.value:.{precision}f}\t"
                    f"{clean_field(prime_factorization)}\t"
                    f"{cents:.{precision}f}\t"
                    f"{clean_field(interval.cents_min)}\t"
                    f"{clean_field(interval.cents_max)}\t"
                    f"{clean_field(interval.expression)}\t"
                    f"{clean_field(subgroup_monzo)}\t"
                    f"{clean_field(interval.fjs_name)}\t"
                    f"{clean_field(comma_size)}\t"
                    f"{clean_field(interval.xen_url)}\t"
                    f"{clean_field(interval.culture)}\t"
                    f"{clean_field(interval.aliases)}\t"
                    f"{clean_field(interval.tradition)}\t"
                    f"{clean_field(interval.note)}\n"
                )
                progress.update(written)
        elif resolved_format == "csv":
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            for written, interval in enumerate(rows, start=1):
                prime_factorization = interval_prime_factorization(interval)
                cents = cents_from_ratio(interval.value)
                subgroup_monzo = interval.subgroup_monzo
                ratio = parse_rational_expression(interval.expression)
                if not subgroup_monzo and ratio is not None:
                    subgroup_monzo = fraction_to_subgroup_monzo(ratio)
                comma_size = interval.comma_size
                if not comma_size and "comma" in interval.name.casefold():
                    comma_size = f"{cents:.{precision}f}"
                writer.writerow(
                    {
                        "slug": clean_field(interval.slug),
                        "name": clean_field(interval.name),
                        "ratio": f"{interval.value:.{precision}f}",
                        "prime_factorization": clean_field(prime_factorization),
                        "cents": f"{cents:.{precision}f}",
                        "cents_min": clean_field(interval.cents_min),
                        "cents_max": clean_field(interval.cents_max),
                        "expression": clean_field(interval.expression),
                        "subgroup_monzo": clean_field(subgroup_monzo),
                        "fjs_name": clean_field(interval.fjs_name),
                        "comma_size": clean_field(comma_size),
                        "xen_url": clean_field(interval.xen_url),
                        "culture": clean_field(interval.culture),
                        "aliases": clean_field(interval.aliases),
                        "tradition": clean_field(interval.tradition),
                        "note": clean_field(interval.note),
                    }
                )
                progress.update(written)
        elif resolved_format == "json":
            handle.write("{\n")
            handle.write(f'  "metadata": {json.dumps(metadata, ensure_ascii=False)},\n')
            handle.write(f'  "columns": {json.dumps(columns, ensure_ascii=False)},\n')
            handle.write('  "rows": [\n')
            first = True
            for written, interval in enumerate(rows, start=1):
                prime_factorization = interval_prime_factorization(interval)
                cents = cents_from_ratio(interval.value)
                subgroup_monzo = interval.subgroup_monzo
                ratio = parse_rational_expression(interval.expression)
                if not subgroup_monzo and ratio is not None:
                    subgroup_monzo = fraction_to_subgroup_monzo(ratio)
                comma_size = interval.comma_size
                if not comma_size and "comma" in interval.name.casefold():
                    comma_size = f"{cents:.{precision}f}"
                row = {
                    "slug": clean_field(interval.slug),
                    "name": clean_field(interval.name),
                    "ratio": f"{interval.value:.{precision}f}",
                    "prime_factorization": clean_field(prime_factorization),
                    "cents": f"{cents:.{precision}f}",
                    "cents_min": clean_field(interval.cents_min),
                    "cents_max": clean_field(interval.cents_max),
                    "expression": clean_field(interval.expression),
                    "subgroup_monzo": clean_field(subgroup_monzo),
                    "fjs_name": clean_field(interval.fjs_name),
                    "comma_size": clean_field(comma_size),
                    "xen_url": clean_field(interval.xen_url),
                    "culture": clean_field(interval.culture),
                    "aliases": clean_field(interval.aliases),
                    "tradition": clean_field(interval.tradition),
                    "note": clean_field(interval.note),
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

    return len(rows)


def main() -> None:
    args = parse_args()
    validate_args(args)
    reporter = create_reporter(args)
    intervals = build_interval_corpus(args, reporter=reporter)
    reporter.info("Sorting intervals...")
    ordered = sort_intervals(intervals, args.sort_by)
    total = write_output(
        output_path=args.output,
        intervals=ordered,
        precision=args.precision,
        sort_by=args.sort_by,
        used_extra_source=(args.extra_source is not None or args.extra_json is not None),
        output_format=args.output_format,
        reporter=reporter,
    )
    reporter.print_result(f"Wrote {total} rows to {args.output}")


if __name__ == "__main__":
    main()
