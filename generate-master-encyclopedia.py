#!/usr/bin/env python3
"""
Generate the master "The Interval Encoclpaedia" file by stitching all source volumes.

This script can optionally regenerate missing source files (or all source
files) by calling the three generator scripts in this workspace.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Sequence

from cli_output import (
    Reporter,
    add_output_control_args,
    create_reporter,
    validate_output_control_args,
)


MASTER_TITLE = "The Interval Encoclpaedia"
LATEX_ENGINE_CHOICES = ("auto", "lualatex", "xelatex", "pdflatex")
ORIENTATION_CHOICES = ("portrait", "landscape")
OVERFLOW_POLICY_CHOICES = ("ask", "keep", "abort", "fit", "larger-page")
OUTPUT_FORMAT_CHOICES = ("auto", "txt", "csv", "json", "latex", "pdf")
TABLE_FONT_SIZE_CHOICES = ("tiny", "scriptsize", "footnotesize", "small", "normalsize")
LATEX_MATH_COLUMNS = {"ratio", "prime_factorization", "expression"}
LATEX_MATH_DECIMAL_COLUMNS = {"ratio"}
LATEX_WIDE_TEXT_COLUMNS = {
    "title",
    "name",
    "interval_name",
    "common_name",
    "tradition",
    "note",
    "source_file",
    "content",
}
LATEX_NUMERIC_COLUMNS = {
    "ratio_decimal",
    "edo",
    "step",
    "cents",
    "cents_min",
    "cents_max",
    "value",
    "largest_prime",
    "odd_limit",
    "total_rows",
}
LATEX_COLUMN_WEIGHT_MULTIPLIERS = {
    "name": 1.35,
    "interval_name": 1.35,
    "note": 2.00,
    "source_file": 1.35,
    "expression": 1.35,
    "prime_factorization": 1.35,
    "ratio": 1.15,
    "subgroup_monzo": 1.20,
    "xen_url": 1.25,
}
MATH_DIGIT_BREAK_GROUP = 3
MATH_LONG_NUMBER_BREAK_THRESHOLD = 9
SOFT_BREAK_PUNCTUATION = set("/-_:;=+|,[]()<>")
LATEX_DIMENSION_PATTERN = re.compile(r"^\d+(?:\.\d+)?(?:in|mm|cm|pt)$", re.IGNORECASE)
ENCYCLOPEDIA_PATTERN = re.compile(r"encyclopedia", re.IGNORECASE)
URL_PATTERN = re.compile(r"https?://\S+")
URL_TRAILING_PUNCTUATION = ".,;:!?)]}"
COLUMN_LABEL_OVERRIDES = {
    "slug": "Source ID",
    "ratio_decimal": "Ratio (decimal, high precision)",
    "cents": "cents (exact)",
    "cents_min": "cents (minimum)",
    "cents_max": "cents (maximum)",
}
IMPORT_SLUG_LABELS = {
    "scribd": "Scribd",
    "miraheze": "Miraheze",
    "huygens_fokker": "Huygens-Fokker",
    "xen_wiki": "Xenharmonic Wiki",
}
IMPORT_SLUG_PATTERN = re.compile(
    r"^(scribd|miraheze|huygens_fokker|xen_wiki)_(\d{4})$"
)
PAPER_SIZE_CANONICAL_TO_GEOMETRY = {
    "us-letter": ("letterpaper",),
    "us-legal": ("legalpaper",),
    "a4": ("a4paper",),
    "a3": ("a3paper",),
    "a5": ("a5paper",),
    "b5": ("b5paper",),
    "executive": ("executivepaper",),
    # Explicit dimensions for maximal compatibility across TeX distributions.
    "11x17": ("paperwidth=11in", "paperheight=17in"),
}
PAPER_SIZE_ALIAS_TO_CANONICAL = {
    "letter": "us-letter",
    "usletter": "us-letter",
    "us-letter": "us-letter",
    "legal": "us-legal",
    "uslegal": "us-legal",
    "us-legal": "us-legal",
    "a4": "a4",
    "a3": "a3",
    "a5": "a5",
    "b5": "b5",
    "executive": "executive",
    "11x17": "11x17",
    "tabloid": "11x17",
    "ledger": "11x17",
}
RENDERING_BANNED_PHRASES = (
    "Continued on next page",
    "Systematic step",
    "Imported from Scribd List of intervals without octave reduction.",
)
RENDERING_REQUIRED_TOKENS = (
    r"\rowcolors{2}{tablezebra}{white}",
    r"\chapter{Chapter Index}",
    r"\url{http",
)


def infer_output_format(path: Path, requested_format: str = "auto") -> str:
    if requested_format != "auto":
        return requested_format
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".json":
        return "json"
    if suffix in (".tex", ".latex"):
        return "latex"
    if suffix == ".pdf":
        return "pdf"
    return "txt"


def infer_source_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".json":
        return "json"
    return "txt"


def normalize_paper_size(paper_size: str) -> str:
    key = re.sub(r"[^a-z0-9x]", "", paper_size.casefold())
    canonical = PAPER_SIZE_ALIAS_TO_CANONICAL.get(key)
    if canonical is None:
        supported = ", ".join(sorted(PAPER_SIZE_CANONICAL_TO_GEOMETRY.keys()))
        raise ValueError(
            f"Unsupported --paper-size '{paper_size}'. Supported values include: {supported}."
        )
    return canonical


def validate_dimension_text(value: str, flag_name: str) -> str:
    stripped = value.strip()
    if not LATEX_DIMENSION_PATTERN.fullmatch(stripped):
        raise ValueError(
            f"{flag_name} must be a positive size with units (for example 11in, 279mm, 21.0cm, 792pt)."
        )
    return stripped


def resolve_page_layout(
    *,
    paper_size: str,
    orientation: str,
    page_width: str | None,
    page_height: str | None,
    page_margin: str,
) -> PageLayout:
    margin = validate_dimension_text(page_margin, "--page-margin")

    if page_width is not None or page_height is not None:
        if page_width is None or page_height is None:
            raise ValueError("Provide both --page-width and --page-height when using custom page sizes.")
        width = validate_dimension_text(page_width, "--page-width")
        height = validate_dimension_text(page_height, "--page-height")
        options = [f"paperwidth={width}", f"paperheight={height}", orientation, f"margin={margin}"]
        return PageLayout(
            geometry_options=",".join(options),
            paper_label=f"{width} x {height}",
            orientation=orientation,
            margin=margin,
        )

    canonical_paper = normalize_paper_size(paper_size)
    geometry_paper_options = list(PAPER_SIZE_CANONICAL_TO_GEOMETRY[canonical_paper])
    options = [*geometry_paper_options, orientation, f"margin={margin}"]
    return PageLayout(
        geometry_options=",".join(options),
        paper_label=canonical_paper,
        orientation=orientation,
        margin=margin,
    )


@dataclass(frozen=True)
class Chapter:
    tag: str
    title: str
    source_path: Path
    source_format: str
    content: str
    total_rows: str


@dataclass(frozen=True)
class PageLayout:
    geometry_options: str
    paper_label: str
    orientation: str
    margin: str


@dataclass(frozen=True)
class LatexTableStyle:
    font_size: str
    fit_font_size: str
    tabcolsep_pt: float
    fit_tabcolsep_pt: float
    arraystretch: float
    extra_row_height_pt: float
    row_strut_ex: float
    usable_width: float
    fit_usable_width: float
    min_column_width: float
    emergency_stretch_em: float
    break_long_tokens: bool
    break_chunk: int
    max_decimals: int | None
    trim_trailing_zeros: bool
    zebra: bool
    zebra_black_pct: float
    header_shade: bool
    header_black_pct: float
    weight_text: float
    weight_math: float
    weight_numeric: float
    weight_other: float


@dataclass(frozen=True)
class PdfCompileResult:
    engine: str
    overflow_warnings: List[str]


def parse_total_rows_text(content: str) -> str:
    for line in content.splitlines():
        if line.startswith("# total_rows="):
            return line.split("=", 1)[1].strip()
    return "unknown"


def parse_total_rows_csv(content: str) -> str:
    rows = list(csv.reader(content.splitlines()))
    if not rows:
        return "0"
    data_rows = 0
    for row in rows[1:]:
        if any(cell.strip() for cell in row):
            data_rows += 1
    return str(data_rows)


def parse_total_rows_json(content: str) -> str:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return "unknown"

    if isinstance(payload, dict):
        metadata = payload.get("metadata")
        if isinstance(metadata, dict) and "total_rows" in metadata:
            return str(metadata["total_rows"])
        rows = payload.get("rows")
        if isinstance(rows, list):
            return str(len(rows))
        return "unknown"

    if isinstance(payload, list):
        return str(len(payload))
    return "unknown"


def run_generator(command: Sequence[str], label: str, reporter: Reporter) -> None:
    reporter.info(f"Running {label} generator...")
    reporter.debug(f"Command: {' '.join(command)}")
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"{label} generator failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
    if completed.stdout.strip() and reporter.verbosity >= 2:
        print(completed.stdout.strip(), file=sys.stderr)


def ensure_source(
    path: Path,
    label: str,
    command: Sequence[str],
    regenerate_all: bool,
    skip_generation: bool,
    reporter: Reporter,
) -> None:
    if regenerate_all:
        run_generator(command, label, reporter)
        return

    if path.exists():
        reporter.verbose(f"Using existing {label} source: {path}")
        return

    if skip_generation:
        raise FileNotFoundError(
            f"Missing required source file: {path}. "
            "Either create it first or remove --skip-generation."
        )

    run_generator(command, label, reporter)


def read_volume(tag: str, title: str, source_path: Path) -> Chapter:
    source_format = infer_source_format(source_path)
    text = source_path.read_text(encoding="utf-8").rstrip("\n")
    if source_format == "txt":
        total_rows = parse_total_rows_text(text)
    elif source_format == "csv":
        total_rows = parse_total_rows_csv(text)
    elif source_format == "json":
        total_rows = parse_total_rows_json(text)
    else:
        total_rows = "unknown"

    return Chapter(
        tag=tag,
        title=title,
        source_path=source_path,
        source_format=source_format,
        content=text,
        total_rows=total_rows,
    )


def write_master_txt(output_path: Path, volumes: List[Chapter], reporter: Reporter) -> None:
    reporter.info(f"Writing master tome (txt) with {len(volumes)} volumes...")
    generated_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    progress = reporter.progress(total=max(1, len(volumes) * 2), label="Master assembly")
    completed_steps = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        handle.write(f"# {MASTER_TITLE}\n")
        handle.write(f"# generated_utc={generated_utc}\n")
        handle.write(f"# volumes={len(volumes)}\n")
        handle.write("# format=tabular-source-plus-volume-markers\n")
        handle.write("#\n")
        handle.write("# volume_index\n")
        handle.write("tag\ttitle\tsource_file\tsource_format\ttotal_rows\n")
        for volume in volumes:
            handle.write(
                f"{volume.tag}\t{volume.title}\t{volume.source_path}\t"
                f"{volume.source_format}\t{volume.total_rows}\n"
            )
            completed_steps += 1
            progress.update(completed_steps)

        handle.write("\n# volume_contents\n")
        for volume in volumes:
            handle.write(f"\n%%<VOLUME:{volume.tag}:BEGIN>\n")
            handle.write(f"# volume_title={volume.title}\n")
            handle.write(f"# source_file={volume.source_path}\n")
            handle.write(f"# source_format={volume.source_format}\n")
            handle.write(f"# total_rows={volume.total_rows}\n")
            handle.write(volume.content)
            handle.write("\n%%<VOLUME:{0}:END>\n".format(volume.tag))
            completed_steps += 1
            progress.update(completed_steps)

    progress.finish()


def write_master_csv(output_path: Path, volumes: List[Chapter], reporter: Reporter) -> None:
    reporter.info(f"Writing master table (csv) with {len(volumes)} volume rows...")
    columns = ["tag", "title", "source_file", "source_format", "total_rows", "content"]
    progress = reporter.progress(total=max(1, len(volumes)), label="Master CSV rows")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for index, volume in enumerate(volumes, start=1):
            writer.writerow(
                {
                    "tag": volume.tag,
                    "title": volume.title,
                    "source_file": str(volume.source_path),
                    "source_format": volume.source_format,
                    "total_rows": volume.total_rows,
                    "content": volume.content,
                }
            )
            progress.update(index)
    progress.finish()


def write_master_json(output_path: Path, volumes: List[Chapter], reporter: Reporter) -> None:
    reporter.info(f"Writing master object (json) with {len(volumes)} volumes...")
    generated_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "metadata": {
            "title": MASTER_TITLE,
            "generated_utc": generated_utc,
            "volumes": len(volumes),
            "output_format": "json",
        },
        "volumes": [
            {
                "tag": volume.tag,
                "title": volume.title,
                "source_file": str(volume.source_path),
                "source_format": volume.source_format,
                "total_rows": volume.total_rows,
                "content": volume.content,
            }
            for volume in volumes
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def latex_escape_char(char: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return replacements.get(char, char)


def escape_latex_plain_text(text: str, table_style: LatexTableStyle | None = None) -> str:
    if table_style is None or not table_style.break_long_tokens:
        return "".join(latex_escape_char(char) for char in text)

    chunk = max(2, table_style.break_chunk)
    output: List[str] = []
    run_length = 0
    for char in text:
        output.append(latex_escape_char(char))
        if char.isalnum():
            run_length += 1
            if run_length >= chunk:
                output.append(r"\allowbreak{}")
                run_length = 0
            continue
        if char in SOFT_BREAK_PUNCTUATION:
            output.append(r"\allowbreak{}")
        run_length = 0
    return "".join(output)


def split_url_suffix(url: str) -> tuple[str, str]:
    trimmed = url.rstrip(URL_TRAILING_PUNCTUATION)
    if not trimmed:
        return url, ""

    # Keep balanced parentheses when URL path legitimately ends with ')'.
    suffix = url[len(trimmed) :]
    while suffix.startswith(")") and trimmed.count("(") > trimmed.count(")"):
        trimmed += ")"
        suffix = suffix[1:]
    return trimmed, suffix


def normalize_url_for_latex(url: str) -> str:
    return url.replace("{", "%7B").replace("}", "%7D")


def latex_escape_with_hyperlinks(
    text: str, table_style: LatexTableStyle | None = None
) -> str:
    rendered = typeset_encyclopaedia_spelling(text)
    parts: List[str] = []
    cursor = 0
    for match in URL_PATTERN.finditer(rendered):
        start, end = match.span()
        if start > cursor:
            parts.append(escape_latex_plain_text(rendered[cursor:start], table_style))
        raw_url = match.group(0)
        clean_url, trailing = split_url_suffix(raw_url)
        if clean_url:
            parts.append(rf"\url{{{normalize_url_for_latex(clean_url)}}}")
        if trailing:
            parts.append(escape_latex_plain_text(trailing, table_style))
        cursor = end
    if cursor < len(rendered):
        parts.append(escape_latex_plain_text(rendered[cursor:], table_style))
    return "".join(parts)


def latex_escape(text: str) -> str:
    return latex_escape_with_hyperlinks(text, table_style=None)


def latex_escape_table_text(text: str, table_style: LatexTableStyle) -> str:
    return latex_escape_with_hyperlinks(text, table_style=table_style)


def encyclopedia_replacement(match: re.Match[str]) -> str:
    token = match.group(0)
    replacement = "encyclopaedia"
    if token.isupper():
        return replacement.upper()
    if token.islower():
        return replacement
    if token[0].isupper() and token[1:].islower():
        return replacement.capitalize()
    return replacement


def typeset_encyclopaedia_spelling(text: str) -> str:
    return ENCYCLOPEDIA_PATTERN.sub(encyclopedia_replacement, str(text))


def sanitize_verbatim_text(text: str) -> str:
    # Strip NUL characters because they break TeX tokenization.
    return text.replace("\x00", "")


def normalize_cell_text(value: str) -> str:
    return str(value).replace("\x00", "").replace("\t", " ").replace("\n", " ").strip()


def find_unwrapped_http_urls(document: str) -> List[str]:
    unwrapped: List[str] = []
    for match in re.finditer(r"https?://[^\s}]+", document):
        start = match.start()
        prefix = document[max(0, start - 5) : start]
        if prefix == r"\url{":
            continue
        unwrapped.append(match.group(0))
    return unwrapped


def validate_rendering_conventions(document: str) -> None:
    failures: List[str] = []
    for phrase in RENDERING_BANNED_PHRASES:
        if phrase in document:
            failures.append(f"found banned phrase: {phrase!r}")

    for token in RENDERING_REQUIRED_TOKENS:
        if token not in document:
            failures.append(f"missing required token: {token!r}")

    if r"\chapter{Volume Index}" in document:
        failures.append("found legacy chapter title '\\chapter{Volume Index}'")

    unwrapped_urls = find_unwrapped_http_urls(document)
    if unwrapped_urls:
        preview = ", ".join(unwrapped_urls[:3])
        failures.append(f"found unwrapped URL(s): {preview}")

    if failures:
        bullet_lines = "\n".join(f"- {failure}" for failure in failures)
        raise RuntimeError(
            "Rendering convention checks failed.\n"
            f"{bullet_lines}\n"
            "Regenerate sources/output after fixing the table rendering pipeline."
        )


def run_rendering_convention_checks(
    *,
    volumes: List[Volume],
    page_layout: PageLayout,
    table_style: LatexTableStyle,
    reporter: Reporter,
) -> None:
    reporter.info("Running rendering convention checks...")
    check_document = build_latex_document(
        volumes=volumes,
        generated_utc="rendering-check",
        page_layout=page_layout,
        table_style=table_style,
    )
    validate_rendering_conventions(check_document)
    reporter.info("Rendering convention checks passed.")


def json_value_to_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def parse_volume_rows(volume: Chapter) -> tuple[List[str], List[dict[str, str]]]:
    if volume.source_format == "txt":
        columns: List[str] = []
        rows: List[dict[str, str]] = []
        for raw_line in volume.content.splitlines():
            line = raw_line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            if not columns:
                columns = [normalize_cell_text(part) for part in line.split("\t")]
                continue
            parts = line.split("\t")
            if len(parts) < len(columns):
                parts.extend([""] * (len(columns) - len(parts)))
            elif len(parts) > len(columns):
                parts = parts[: len(columns)]
            rows.append(
                {column: normalize_cell_text(parts[index]) for index, column in enumerate(columns)}
            )
        return columns, rows

    if volume.source_format == "csv":
        reader = csv.DictReader(io.StringIO(volume.content))
        columns = [normalize_cell_text(name) for name in (reader.fieldnames or [])]
        rows = []
        for raw_row in reader:
            row = {column: normalize_cell_text(raw_row.get(column, "")) for column in columns}
            rows.append(row)
        return columns, rows

    if volume.source_format == "json":
        try:
            payload = json.loads(volume.content)
        except json.JSONDecodeError:
            return [], []

        columns: List[str] = []
        raw_rows: List[object] = []

        if isinstance(payload, dict):
            raw_columns = payload.get("columns")
            if isinstance(raw_columns, list):
                columns = [normalize_cell_text(item) for item in raw_columns]

            rows_candidate = payload.get("rows")
            if not isinstance(rows_candidate, list):
                rows_candidate = payload.get("data")
            if isinstance(rows_candidate, list):
                raw_rows = rows_candidate
        elif isinstance(payload, list):
            raw_rows = payload

        if not columns and raw_rows and isinstance(raw_rows[0], dict):
            columns = [normalize_cell_text(key) for key in raw_rows[0].keys()]

        rows: List[dict[str, str]] = []
        for raw_row in raw_rows:
            if isinstance(raw_row, dict):
                if not columns:
                    columns = [normalize_cell_text(key) for key in raw_row.keys()]
                row = {
                    column: normalize_cell_text(json_value_to_text(raw_row.get(column, "")))
                    for column in columns
                }
                rows.append(row)
                continue

            if isinstance(raw_row, list):
                if not columns:
                    columns = [f"column_{index + 1}" for index in range(len(raw_row))]
                values = [normalize_cell_text(json_value_to_text(value)) for value in raw_row]
                if len(values) < len(columns):
                    values.extend([""] * (len(columns) - len(values)))
                elif len(values) > len(columns):
                    values = values[: len(columns)]
                rows.append({column: values[index] for index, column in enumerate(columns)})

        return columns, rows

    return [], []


def tokenize_math_expression(text: str) -> List[str]:
    pattern = re.compile(
        r"""\s*(
            [0-9]+(?:\.[0-9]+)? |
            [A-Za-z_][A-Za-z0-9_]* |
            [()+\-*/^,]
        )""",
        re.VERBOSE,
    )
    tokens: List[str] = []
    index = 0
    while index < len(text):
        match = pattern.match(text, index)
        if not match:
            return []
        token = match.group(1)
        tokens.append(token)
        index = match.end()
    return tokens


class MathParser:
    def __init__(self, tokens: List[str]):
        self.tokens = tokens
        self.index = 0

    def peek(self) -> str | None:
        if self.index >= len(self.tokens):
            return None
        return self.tokens[self.index]

    def consume(self, expected: str | None = None) -> str:
        token = self.peek()
        if token is None:
            raise ValueError("Unexpected end of math expression.")
        if expected is not None and token != expected:
            raise ValueError(f"Expected '{expected}' but found '{token}'.")
        self.index += 1
        return token

    def parse(self) -> object:
        node = self.parse_sum()
        if self.peek() is not None:
            raise ValueError(f"Unexpected trailing token '{self.peek()}'.")
        return node

    def parse_sum(self) -> object:
        node = self.parse_term()
        while self.peek() in {"+", "-"}:
            operator = self.consume()
            right = self.parse_term()
            node = ("binop", operator, node, right)
        return node

    def parse_term(self) -> object:
        node = self.parse_power()
        while self.peek() in {"*", "/"}:
            operator = self.consume()
            right = self.parse_power()
            node = ("binop", operator, node, right)
        return node

    def parse_power(self) -> object:
        node = self.parse_unary()
        if self.peek() == "^":
            self.consume("^")
            exponent = self.parse_power()
            node = ("pow", node, exponent)
        return node

    def parse_unary(self) -> object:
        if self.peek() == "-":
            self.consume("-")
            operand = self.parse_unary()
            return ("neg", operand)
        return self.parse_primary()

    def parse_primary(self) -> object:
        token = self.peek()
        if token is None:
            raise ValueError("Expected primary expression but found end of input.")

        if token == "(":
            self.consume("(")
            node = self.parse_sum()
            self.consume(")")
            return ("group", node)

        if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", token):
            self.consume()
            return ("num", token)

        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token):
            identifier = self.consume()
            if self.peek() == "(":
                self.consume("(")
                args: List[object] = []
                if self.peek() != ")":
                    args.append(self.parse_sum())
                    while self.peek() == ",":
                        self.consume(",")
                        args.append(self.parse_sum())
                self.consume(")")
                return ("func", identifier, args)
            return ("ident", identifier)

        raise ValueError(f"Unexpected token '{token}' in primary expression.")


def math_identifier_to_latex(identifier: str) -> str:
    lowered = identifier.casefold()
    if lowered == "pi":
        return r"\pi"
    if lowered == "phi":
        return r"\varphi"
    if lowered == "e":
        return "e"
    escaped = latex_escape(identifier).replace(r"\_", r"\allowbreak{}\_")
    return rf"\mathrm{{{escaped}}}"


def insert_soft_breaks_in_digits(digits: str, *, from_right: bool) -> str:
    if len(digits) <= MATH_LONG_NUMBER_BREAK_THRESHOLD:
        return digits
    if from_right:
        groups: List[str] = []
        cursor = digits
        while cursor:
            groups.append(cursor[-MATH_DIGIT_BREAK_GROUP :])
            cursor = cursor[: -MATH_DIGIT_BREAK_GROUP]
        groups.reverse()
        return r"\allowbreak{}".join(groups)
    groups = [
        digits[index : index + MATH_DIGIT_BREAK_GROUP]
        for index in range(0, len(digits), MATH_DIGIT_BREAK_GROUP)
    ]
    return r"\allowbreak{}".join(groups)


def format_math_number_token(token: str) -> str:
    if "." in token:
        whole, fractional = token.split(".", 1)
        whole_text = insert_soft_breaks_in_digits(whole, from_right=True)
        fractional_text = insert_soft_breaks_in_digits(fractional, from_right=False)
        return f"{whole_text}.{fractional_text}"
    return insert_soft_breaks_in_digits(token, from_right=True)


def needs_parentheses(parent_op: str, child_node: object, is_right: bool = False) -> bool:
    if not isinstance(child_node, tuple) or not child_node:
        return False
    node_type = child_node[0]
    if node_type == "group":
        return False
    if parent_op == "/":
        return node_type == "binop"
    if parent_op == "^":
        return node_type in {"binop", "neg"}
    if parent_op == "*" and node_type == "binop":
        child_op = child_node[1]
        return child_op in {"+", "-"}
    if parent_op in {"+", "-"} and node_type == "binop":
        child_op = child_node[1]
        if child_op in {"+", "-"}:
            return parent_op == "-" and is_right
    return False


def ast_to_latex(node: object) -> str:
    if not isinstance(node, tuple) or not node:
        raise ValueError("Invalid expression AST node.")

    node_type = node[0]
    if node_type == "num":
        return format_math_number_token(node[1])
    if node_type == "ident":
        return math_identifier_to_latex(node[1])
    if node_type == "group":
        return rf"\left({ast_to_latex(node[1])}\right)"
    if node_type == "neg":
        operand = node[1]
        operand_text = ast_to_latex(operand)
        if isinstance(operand, tuple) and operand and operand[0] == "binop":
            operand_text = rf"\left({operand_text}\right)"
        return "-" + operand_text
    if node_type == "pow":
        base = node[1]
        exponent = node[2]
        base_text = ast_to_latex(base)
        if needs_parentheses("^", base):
            base_text = rf"\left({base_text}\right)"
        exponent_text = ast_to_latex(exponent)
        return rf"{base_text}^{{{exponent_text}}}"
    if node_type == "func":
        name = node[1]
        args = node[2]
        if name.casefold() == "sqrt" and len(args) == 1:
            return rf"\sqrt{{{ast_to_latex(args[0])}}}"
        args_text = ", ".join(ast_to_latex(argument) for argument in args)
        return rf"{math_identifier_to_latex(name)}\left({args_text}\right)"
    if node_type == "binop":
        operator = node[1]
        left = node[2]
        right = node[3]
        if operator == "/":
            left_text = ast_to_latex(left)
            right_text = ast_to_latex(right)
            if needs_parentheses("/", left):
                left_text = rf"\left({left_text}\right)"
            if needs_parentheses("/", right, is_right=True):
                right_text = rf"\left({right_text}\right)"
            return rf"{left_text}\allowbreak{{}}\mathbin{{/}}\allowbreak{{}}{right_text}"
        left_text = ast_to_latex(left)
        right_text = ast_to_latex(right)
        if needs_parentheses(operator, left):
            left_text = rf"\left({left_text}\right)"
        if needs_parentheses(operator, right, is_right=True):
            right_text = rf"\left({right_text}\right)"
        if operator == "*":
            return rf"{left_text}\allowbreak{{}} \cdot \allowbreak{{}} {right_text}"
        return rf"{left_text}\allowbreak{{}} {operator} \allowbreak{{}} {right_text}"

    raise ValueError(f"Unsupported expression AST node type: {node_type}")


def parse_math_to_latex(text: str) -> str | None:
    tokens = tokenize_math_expression(text)
    if not tokens:
        return None
    try:
        parser = MathParser(tokens)
        ast = parser.parse()
        return ast_to_latex(ast)
    except ValueError:
        return None


def maybe_typeset_math(text: str, table_style: LatexTableStyle | None = None) -> str:
    normalized = normalize_cell_text(text)
    if not normalized:
        return ""
    if normalized == "-":
        return "-"

    from_match = re.fullmatch(r"(.+?)\s*\(from\s+(.+)\)\s*", normalized)
    if from_match:
        primary_math = parse_math_to_latex(from_match.group(1).strip())
        source_math = parse_math_to_latex(from_match.group(2).strip())
        if primary_math is not None and source_math is not None:
            return rf"\({primary_math}\) (from \({source_math}\))"

    parsed = parse_math_to_latex(normalized)
    if parsed is None:
        escaped = (
            latex_escape_table_text(normalized, table_style)
            if table_style is not None
            else latex_escape(normalized)
        )
        return rf"\texttt{{{escaped}}}"
    return rf"\({parsed}\)"


def canonical_column_name(column: str) -> str:
    return normalize_cell_text(column).casefold().replace(" ", "_")


def display_column_label(column: str) -> str:
    canonical = canonical_column_name(column)
    return COLUMN_LABEL_OVERRIDES.get(canonical, normalize_cell_text(column))


def humanize_slug_value(value: str) -> str:
    match = IMPORT_SLUG_PATTERN.fullmatch(value)
    if match is None:
        return value
    slug_prefix, index_text = match.groups()
    label = IMPORT_SLUG_LABELS.get(slug_prefix, slug_prefix.replace("_", " ").title())
    return f"{label} #{int(index_text)}"


def filter_columns_for_volume_chapter(volume: Chapter, columns: Sequence[str]) -> List[str]:
    # Chapter-specific table policy: hide historical "tradition" column in Chapter 4.
    if volume.tag != "HISTORICAL":
        return list(columns)
    return [column for column in columns if canonical_column_name(column) != "tradition"]


def format_numeric_cell_text(value: str, table_style: LatexTableStyle) -> str:
    if table_style.max_decimals is None:
        return value
    match = re.fullmatch(r"(-?\d+)\.(\d+)", value)
    if match is None:
        return value
    whole, fractional = match.groups()
    if table_style.max_decimals >= 0:
        fractional = fractional[: table_style.max_decimals]
    if table_style.trim_trailing_zeros:
        fractional = fractional.rstrip("0")
    if not fractional:
        return whole
    return f"{whole}.{fractional}"


def render_latex_cell(column: str, value: str, table_style: LatexTableStyle) -> str:
    normalized = normalize_cell_text(value)
    if normalized == "-":
        return "-"
    canonical = canonical_column_name(column)
    if canonical == "slug":
        normalized = humanize_slug_value(normalized)
    if canonical in LATEX_NUMERIC_COLUMNS or canonical in LATEX_MATH_DECIMAL_COLUMNS:
        normalized = format_numeric_cell_text(normalized, table_style)
    if canonical in LATEX_MATH_COLUMNS:
        return maybe_typeset_math(normalized, table_style=table_style)
    return latex_escape_table_text(normalized, table_style)


def latex_column_weight(canonical_column: str, table_style: LatexTableStyle) -> float:
    if canonical_column in LATEX_WIDE_TEXT_COLUMNS:
        base_weight = table_style.weight_text
    elif canonical_column in LATEX_MATH_COLUMNS:
        base_weight = table_style.weight_math
    elif canonical_column in LATEX_NUMERIC_COLUMNS:
        base_weight = table_style.weight_numeric
    else:
        base_weight = table_style.weight_other
    return base_weight * LATEX_COLUMN_WEIGHT_MULTIPLIERS.get(canonical_column, 1.0)


def latex_column_alignment(canonical_column: str) -> str:
    if canonical_column in LATEX_NUMERIC_COLUMNS:
        return r"\RaggedLeft\arraybackslash\hspace{0pt}"
    return r"\RaggedRight\arraybackslash\hspace{0pt}"


def allocate_column_widths(
    columns: Sequence[str],
    *,
    usable_width: float,
    minimum_width: float,
    table_style: LatexTableStyle,
) -> List[float]:
    if not columns:
        return []

    canonical_columns = [canonical_column_name(column) for column in columns]
    weights = [latex_column_weight(canonical_column, table_style) for canonical_column in canonical_columns]
    weight_total = sum(weights)
    if weight_total <= 0:
        return [usable_width / len(columns)] * len(columns)

    raw_widths = [usable_width * (weight / weight_total) for weight in weights]
    safe_minimum = max(0.0, minimum_width)
    if safe_minimum * len(columns) >= usable_width:
        safe_minimum = usable_width / (len(columns) * 1.2)

    widths = [max(raw_width, safe_minimum) for raw_width in raw_widths]
    total_width = sum(widths)
    if total_width <= usable_width:
        return widths

    excess = total_width - usable_width
    adjustable = [max(0.0, width - safe_minimum) for width in widths]
    adjustable_total = sum(adjustable)
    if adjustable_total <= 0:
        return [usable_width / len(columns)] * len(columns)

    normalized_widths: List[float] = []
    for width, room in zip(widths, adjustable):
        reduction = excess * (room / adjustable_total)
        normalized_widths.append(max(safe_minimum, width - reduction))

    correction = usable_width - sum(normalized_widths)
    if normalized_widths:
        normalized_widths[-1] = max(safe_minimum, normalized_widths[-1] + correction)
    return normalized_widths


def latex_column_spec_for_columns(
    columns: Sequence[str],
    *,
    usable_width: float = 0.98,
    minimum_width: float = 0.04,
    tabcolsep_pt: float = 4.0,
    table_style: LatexTableStyle,
) -> str:
    if not columns:
        return "@{}l@{}"

    canonical_columns = [canonical_column_name(column) for column in columns]
    widths = allocate_column_widths(
        columns,
        usable_width=usable_width,
        minimum_width=minimum_width,
        table_style=table_style,
    )
    intercolumn_pt_total = max(0.0, 2.0 * max(0, len(columns) - 1) * tabcolsep_pt)
    per_column_adjustment_pt = intercolumn_pt_total / len(columns)
    columns_spec: List[str] = []
    for canonical_column, width in zip(canonical_columns, widths):
        columns_spec.append(
            rf">{{{latex_column_alignment(canonical_column)}}}p{{\dimexpr{width:.5f}\linewidth-{per_column_adjustment_pt:.4f}pt\relax}}"
        )
    return "@{}" + "".join(columns_spec) + "@{}"


def build_latex_table_for_volume(
    volume: Chapter,
    table_style: LatexTableStyle,
    compact_tables: bool = False,
) -> List[str]:
    columns, rows = parse_volume_rows(volume)
    columns = filter_columns_for_volume_chapter(volume, columns)
    if not columns:
        return [
            r"\section*{Source Content}",
            r"\begin{Verbatim}[fontsize=\footnotesize]",
            sanitize_verbatim_text(volume.content),
            r"\end{Verbatim}",
        ]

    usable_width = table_style.fit_usable_width if compact_tables else table_style.usable_width
    table_font_size = table_style.fit_font_size if compact_tables else table_style.font_size
    table_font_command = rf"\{table_font_size}"
    tabcolsep_value = (
        table_style.fit_tabcolsep_pt if compact_tables else table_style.tabcolsep_pt
    )
    tabcolsep = f"{tabcolsep_value:.2f}pt"
    header_cells = (
        " & ".join(
            latex_escape_table_text(display_column_label(column), table_style) for column in columns
        )
        + r" \\"
    )
    if table_style.header_shade:
        header_cells = r"\rowcolor{tableheader}" + " " + header_cells

    lines: List[str] = [
        r"\section*{Tabular Content}",
        r"\begingroup",
        table_font_command,
        rf"\setlength{{\tabcolsep}}{{{tabcolsep}}}",
    ]
    if table_style.zebra:
        lines.append(r"\rowcolors{2}{tablezebra}{white}")
    lines.extend(
        [
            rf"\begin{{longtable}}{{{latex_column_spec_for_columns(columns, usable_width=usable_width, minimum_width=table_style.min_column_width, tabcolsep_pt=tabcolsep_value, table_style=table_style)}}}",
            r"\toprule",
            header_cells,
            r"\midrule",
            r"\endfirsthead",
            r"\toprule",
            header_cells,
            r"\midrule",
            r"\endhead",
            r"\endfoot",
            r"\bottomrule",
            r"\endlastfoot",
        ]
    )

    for row in rows:
        cells = [
            rf"\TableRowStrut{{}} {render_latex_cell(column, row.get(column, ''), table_style)}"
            for column in columns
        ]
        lines.append(" & ".join(cells) + r" \\")

    lines.extend([r"\end{longtable}", r"\endgroup"])
    return lines


def build_latex_volume_index_table(
    volumes: List[Chapter],
    table_style: LatexTableStyle,
    compact_tables: bool,
) -> List[str]:
    columns = ["tag", "title", "source_file", "source_format", "total_rows"]
    usable_width = table_style.fit_usable_width if compact_tables else table_style.usable_width
    table_font_size = table_style.fit_font_size if compact_tables else table_style.font_size
    table_font_command = rf"\{table_font_size}"
    tabcolsep_value = (
        table_style.fit_tabcolsep_pt if compact_tables else table_style.tabcolsep_pt
    )
    tabcolsep = f"{tabcolsep_value:.2f}pt"

    header_cells = "Tag & Title & Source File & Source Format & Total Rows \\\\"
    if table_style.header_shade:
        header_cells = r"\rowcolor{tableheader}" + " " + header_cells

    lines: List[str] = [r"\begingroup", table_font_command, rf"\setlength{{\tabcolsep}}{{{tabcolsep}}}"]
    if table_style.zebra:
        lines.append(r"\rowcolors{2}{tablezebra}{white}")
    lines.extend(
        [
            rf"\begin{{longtable}}{{{latex_column_spec_for_columns(columns, usable_width=usable_width, minimum_width=table_style.min_column_width, tabcolsep_pt=tabcolsep_value, table_style=table_style)}}}",
            r"\toprule",
            header_cells,
            r"\midrule",
            r"\endfirsthead",
            r"\toprule",
            header_cells,
            r"\midrule",
            r"\endhead",
            r"\endfoot",
            r"\bottomrule",
            r"\endlastfoot",
        ]
    )

    for volume in volumes:
        row_cells = [
            rf"\TableRowStrut{{}} {latex_escape(volume.tag)}",
            rf"\TableRowStrut{{}} {latex_escape(volume.title)}",
            rf"\TableRowStrut{{}} \texttt{{{latex_escape_table_text(str(volume.source_path), table_style)}}}",
            rf"\TableRowStrut{{}} {latex_escape(volume.source_format)}",
            rf"\TableRowStrut{{}} {latex_escape(volume.total_rows)}",
        ]
        lines.append(" & ".join(row_cells) + r" \\")

    lines.extend([r"\end{longtable}", r"\endgroup"])
    return lines


def build_latex_document(
    volumes: List[Chapter],
    generated_utc: str,
    page_layout: PageLayout,
    table_style: LatexTableStyle,
    compact_tables: bool = False,
) -> str:
    zebra_pct = f"{table_style.zebra_black_pct:.3f}".rstrip("0").rstrip(".")
    header_pct = f"{table_style.header_black_pct:.3f}".rstrip("0").rstrip(".")
    lines: List[str] = [
        r"\documentclass[11pt,oneside]{book}",
        rf"\usepackage[{page_layout.geometry_options}]{{geometry}}",
        r"\usepackage{iftex}",
        r"\ifPDFTeX",
        r"  \usepackage[utf8]{inputenc}",
        r"  \usepackage[T1]{fontenc}",
        r"  \usepackage{lmodern}",
        r"\else",
        r"  \usepackage{fontspec}",
        r"  \setmainfont{TeX Gyre Pagella}",
        r"  \setsansfont{TeX Gyre Heros}",
        r"  \setmonofont{Latin Modern Mono}",
        r"\fi",
        r"\usepackage{amsmath}",
        r"\usepackage{microtype}",
        r"\usepackage{array}",
        r"\usepackage{booktabs}",
        r"\usepackage{longtable}",
        r"\usepackage[table]{xcolor}",
        r"\usepackage{ragged2e}",
        r"\usepackage[hidelinks]{hyperref}",
        r"\usepackage{fancyhdr}",
        r"\usepackage{fancyvrb}",
        r"\setlength{\parindent}{0pt}",
        r"\setlength{\parskip}{0.55em}",
        r"\setlength{\LTleft}{0pt}",
        r"\setlength{\LTright}{0pt}",
        r"\setlength{\LTpre}{4pt}",
        r"\setlength{\LTpost}{4pt}",
        rf"\setlength{{\emergencystretch}}{{{table_style.emergency_stretch_em:.2f}em}}",
        rf"\renewcommand{{\arraystretch}}{{{table_style.arraystretch:.3f}}}",
        rf"\setlength{{\extrarowheight}}{{{table_style.extra_row_height_pt:.2f}pt}}",
        rf"\newcommand{{\TableRowStrut}}{{\rule{{0pt}}{{{table_style.row_strut_ex:.3f}ex}}}}",
        rf"\definecolor{{tablezebra}}{{gray}}{{{1.0 - (table_style.zebra_black_pct / 100.0):.6f}}}",
        rf"\definecolor{{tableheader}}{{gray}}{{{1.0 - (table_style.header_black_pct / 100.0):.6f}}}",
        r"\pagestyle{fancy}",
        r"\fancyhf{}",
        r"\fancyhead[L]{\nouppercase{\leftmark}}",
        r"\fancyfoot[C]{\thepage}",
        r"\renewcommand{\headrulewidth}{0.4pt}",
        r"\renewcommand{\footrulewidth}{0pt}",
        r"\fancypagestyle{plain}{%",
        r"  \fancyhf{}",
        r"  \fancyfoot[C]{\thepage}",
        r"  \renewcommand{\headrulewidth}{0pt}",
        r"}",
        rf"\title{{{latex_escape(MASTER_TITLE)}}}",
        rf"\author{{{latex_escape('intervalEncyclopedia generator')}}}",
        rf"\date{{Generated {latex_escape(generated_utc)}}}",
        r"\begin{document}",
        r"\frontmatter",
        r"\maketitle",
        r"\thispagestyle{plain}",
        r"\clearpage",
        r"\tableofcontents",
        r"\clearpage",
        r"\chapter*{Edition Notes}",
        r"\addcontentsline{toc}{chapter}{Edition Notes}",
        latex_escape(
            "This document is generated automatically from the three source volumes of intervalEncyclopedia."
        ),
        r"\begin{itemize}",
        rf"  \item Edition title: {latex_escape(MASTER_TITLE)}",
        rf"  \item Generation timestamp (UTC): {latex_escape(generated_utc)}",
        rf"  \item Paper layout: {latex_escape(page_layout.paper_label)} ({latex_escape(page_layout.orientation)})",
        rf"  \item Chapter count: {len(volumes)}",
        rf"  \item Table font size: \texttt{{{latex_escape(table_style.fit_font_size if compact_tables else table_style.font_size)}}}",
        rf"  \item Table spacing: tabcolsep={table_style.fit_tabcolsep_pt if compact_tables else table_style.tabcolsep_pt:.2f}pt, arraystretch={table_style.arraystretch:.3f}, extrarowheight={table_style.extra_row_height_pt:.2f}pt",
        rf"  \item Decimal render policy: max\_decimals={table_style.max_decimals}, trim\_trailing\_zeros={latex_escape(str(table_style.trim_trailing_zeros))}",
        rf"  \item Optional row styling: zebra={latex_escape(str(table_style.zebra))} ({zebra_pct}\% black), header\_shade={latex_escape(str(table_style.header_shade))} ({header_pct}\% black)",
        r"\end{itemize}",
        r"\mainmatter",
        r"\chapter{Chapter Index}",
    ]
    lines.extend(
        build_latex_volume_index_table(
            volumes=volumes,
            table_style=table_style,
            compact_tables=compact_tables,
        )
    )

    for volume in volumes:
        lines.extend(
            [
                rf"\chapter{{{latex_escape(volume.title)}}}",
                r"\begin{itemize}",
                rf"  \item Tag: \texttt{{{latex_escape(volume.tag)}}}",
                rf"  \item Source file: \texttt{{{latex_escape(str(volume.source_path))}}}",
                rf"  \item Source format: {latex_escape(volume.source_format)}",
                rf"  \item Total rows: {latex_escape(volume.total_rows)}",
                r"\end{itemize}",
            ]
        )
        lines.extend(
            build_latex_table_for_volume(
                volume,
                table_style=table_style,
                compact_tables=compact_tables,
            )
        )

    lines.extend([r"\end{document}", ""])
    return "\n".join(lines)


def write_master_latex(
    output_path: Path,
    volumes: List[Chapter],
    page_layout: PageLayout,
    table_style: LatexTableStyle,
    reporter: Reporter,
) -> None:
    reporter.info(f"Writing master document (latex) with {len(volumes)} volumes...")
    generated_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    document = build_latex_document(
        volumes=volumes,
        generated_utc=generated_utc,
        page_layout=page_layout,
        table_style=table_style,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        handle.write(document)


def resolve_latex_engines(requested_engine: str) -> List[str]:
    if requested_engine != "auto":
        if shutil.which(requested_engine) is None:
            raise RuntimeError(
                f"Requested LaTeX engine '{requested_engine}' is not available in PATH."
            )
        return [requested_engine]

    engines = [engine for engine in ("lualatex", "xelatex", "pdflatex") if shutil.which(engine)]
    if not engines:
        raise RuntimeError(
            "No LaTeX engine found. Install lualatex, xelatex, or pdflatex to build PDF output."
        )
    return engines


def run_latex_pass(engine: str, tex_path: Path, reporter: Reporter) -> subprocess.CompletedProcess[str]:
    command = [
        engine,
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-file-line-error",
        tex_path.name,
    ]
    reporter.debug(f"Running LaTeX command: {' '.join(command)} (cwd={tex_path.parent})")
    completed = subprocess.run(
        command,
        cwd=tex_path.parent,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        stdout_tail = "\n".join(completed.stdout.splitlines()[-80:])
        stderr_tail = "\n".join(completed.stderr.splitlines()[-80:])
        raise RuntimeError(
            "LaTeX compilation failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout (tail):\n{stdout_tail}\n"
            f"stderr (tail):\n{stderr_tail}"
        )
    return completed


def extract_overflow_warnings(log_text: str) -> List[str]:
    warnings: List[str] = []
    seen: set[str] = set()
    for line in log_text.splitlines():
        if "Overfull \\hbox" not in line and "Overfull \\vbox" not in line:
            continue
        normalized = " ".join(line.strip().split())
        if normalized in seen:
            continue
        seen.add(normalized)
        warnings.append(normalized)
    return warnings


def report_overflow_warnings(
    warnings: Sequence[str],
    *,
    output_path: Path,
    page_layout: PageLayout,
    compact_tables: bool,
) -> None:
    mode_label = "compact fit mode" if compact_tables else "normal mode"
    print(
        "ERROR: PDF typesetting overflow detected. "
        f"Text does not fully fit the page for '{output_path}'.",
        file=sys.stderr,
    )
    print(
        f"ERROR: Layout={page_layout.paper_label} ({page_layout.orientation}), "
        f"margin={page_layout.margin}, table_mode={mode_label}. "
        f"Overfull warnings={len(warnings)}.",
        file=sys.stderr,
    )
    sample_count = min(5, len(warnings))
    for warning_line in warnings[:sample_count]:
        print(f"ERROR: {warning_line}", file=sys.stderr)
    if len(warnings) > sample_count:
        print(
            f"ERROR: ... {len(warnings) - sample_count} additional overflow warning(s) omitted.",
            file=sys.stderr,
        )


def choose_overflow_action(overflow_policy: str) -> str:
    if overflow_policy != "ask":
        return overflow_policy

    print(
        "PDF overflow detected. Do you want to make text fit, use a larger page, "
        "keep the current PDF, or abort?",
        file=sys.stderr,
    )
    if not sys.stdin.isatty():
        print(
            "ERROR: Non-interactive session; cannot ask for overflow resolution. "
            "Re-run with --overflow-policy keep|fit|larger-page|abort.",
            file=sys.stderr,
        )
        return "abort"

    while True:
        response = input("Choose [f]it / [l]arger-page / [k]eep / [a]bort: ").strip().casefold()
        if response in {"f", "fit"}:
            return "fit"
        if response in {"l", "larger", "larger-page"}:
            return "larger-page"
        if response in {"k", "keep"}:
            return "keep"
        if response in {"a", "abort"}:
            return "abort"
        print("Please enter f, l, k, or a.", file=sys.stderr)


def compile_pdf_document(
    *,
    document: str,
    output_path: Path,
    latex_engine: str,
    latex_runs: int,
    reporter: Reporter,
) -> PdfCompileResult:
    engines = resolve_latex_engines(latex_engine)
    compile_errors: List[str] = []
    for engine in engines:
        try:
            with tempfile.TemporaryDirectory(prefix="interval-encoclpaedia-") as temp_dir:
                temp_dir_path = Path(temp_dir)
                tex_path = temp_dir_path / "the-interval-encoclpaedia.tex"
                tex_path.write_text(document, encoding="utf-8")

                final_completed: subprocess.CompletedProcess[str] | None = None
                for pass_index in range(1, latex_runs + 1):
                    reporter.info(f"Compiling PDF ({engine}), pass {pass_index}/{latex_runs}...")
                    final_completed = run_latex_pass(engine=engine, tex_path=tex_path, reporter=reporter)

                compiled_pdf_path = tex_path.with_suffix(".pdf")
                if not compiled_pdf_path.exists():
                    raise RuntimeError(
                        f"LaTeX engine did not produce expected PDF: {compiled_pdf_path}"
                    )

                log_path = tex_path.with_suffix(".log")
                log_text = ""
                if log_path.exists():
                    log_text = log_path.read_text(encoding="utf-8", errors="replace")
                if final_completed is not None:
                    log_text = f"{log_text}\n{final_completed.stdout}\n{final_completed.stderr}"
                overflow_warnings = extract_overflow_warnings(log_text)

                shutil.copy2(compiled_pdf_path, output_path)
                reporter.info(f"Compiled PDF successfully with {engine}.")
                return PdfCompileResult(engine=engine, overflow_warnings=overflow_warnings)
        except RuntimeError as error:
            compile_errors.append(f"{engine}: {error}")
            if latex_engine != "auto":
                raise
            reporter.verbose(f"Engine {engine} failed; trying next available engine.")

    raise RuntimeError(
        "Failed to compile PDF with all available engines.\n" + "\n\n".join(compile_errors)
    )


def write_master_pdf(
    output_path: Path,
    volumes: List[Chapter],
    page_layout: PageLayout,
    table_style: LatexTableStyle,
    latex_engine: str,
    latex_runs: int,
    overflow_policy: str,
    keep_pdf_tex: bool,
    reporter: Reporter,
) -> None:
    reporter.info(f"Writing master document (pdf) with {len(volumes)} volumes...")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    current_layout = page_layout
    compact_tables = False
    document = ""

    while True:
        generated_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        document = build_latex_document(
            volumes=volumes,
            generated_utc=generated_utc,
            page_layout=current_layout,
            table_style=table_style,
            compact_tables=compact_tables,
        )

        compile_result = compile_pdf_document(
            document=document,
            output_path=output_path,
            latex_engine=latex_engine,
            latex_runs=latex_runs,
            reporter=reporter,
        )

        if not compile_result.overflow_warnings:
            break

        report_overflow_warnings(
            compile_result.overflow_warnings,
            output_path=output_path,
            page_layout=current_layout,
            compact_tables=compact_tables,
        )
        action = choose_overflow_action(overflow_policy)
        if action == "keep":
            reporter.info("Keeping PDF output despite overflow warnings.")
            break
        if action == "abort":
            raise RuntimeError(
                "Aborted: overflow warnings indicate text did not fully fit on the page."
            )
        if action == "fit":
            if compact_tables:
                raise RuntimeError(
                    "Compact fit mode is already enabled but overflow warnings still remain."
                )
            compact_tables = True
            reporter.info("Retrying with compact table mode to fit content.")
            continue
        if action == "larger-page":
            larger_layout = resolve_page_layout(
                paper_size="11x17",
                orientation="landscape",
                page_width=None,
                page_height=None,
                page_margin=current_layout.margin,
            )
            if larger_layout.geometry_options == current_layout.geometry_options:
                raise RuntimeError(
                    "Already using 11x17 landscape layout; cannot auto-enlarge further."
                )
            current_layout = larger_layout
            compact_tables = False
            reporter.info(
                "Retrying with larger page layout (11x17 landscape) to reduce overflow."
            )
            continue
        raise RuntimeError(f"Unsupported overflow action: {action}")

    if keep_pdf_tex:
        sidecar_tex = output_path.with_suffix(".tex")
        sidecar_tex.write_text(document, encoding="utf-8")
        reporter.info(f"Wrote sidecar LaTeX source to {sidecar_tex}")


def write_master(
    output_path: Path,
    volumes: List[Chapter],
    output_format: str,
    page_layout: PageLayout,
    table_style: LatexTableStyle,
    latex_engine: str,
    latex_runs: int,
    overflow_policy: str,
    keep_pdf_tex: bool,
    reporter: Reporter,
) -> None:
    resolved_format = infer_output_format(output_path, requested_format=output_format)
    if resolved_format == "txt":
        write_master_txt(output_path=output_path, volumes=volumes, reporter=reporter)
        return
    if resolved_format == "csv":
        write_master_csv(output_path=output_path, volumes=volumes, reporter=reporter)
        return
    if resolved_format == "json":
        write_master_json(output_path=output_path, volumes=volumes, reporter=reporter)
        return
    if resolved_format == "latex":
        write_master_latex(
            output_path=output_path,
            volumes=volumes,
            page_layout=page_layout,
            table_style=table_style,
            reporter=reporter,
        )
        return
    if resolved_format == "pdf":
        write_master_pdf(
            output_path=output_path,
            volumes=volumes,
            page_layout=page_layout,
            table_style=table_style,
            latex_engine=latex_engine,
            latex_runs=latex_runs,
            overflow_policy=overflow_policy,
            keep_pdf_tex=keep_pdf_tex,
            reporter=reporter,
        )
        return
    raise ValueError(f"Unsupported output format: {resolved_format}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Assemble source volumes into the master The Interval Encoclpaedia file."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("the-interval-encoclpaedia.txt"),
        help="Master output path (.txt/.csv/.json/.tex/.pdf or set --output-format).",
    )
    parser.add_argument(
        "--output-format",
        choices=OUTPUT_FORMAT_CHOICES,
        default="auto",
        help="Master output format. Use 'auto' to infer from output file extension.",
    )
    parser.add_argument(
        "--latex-engine",
        choices=LATEX_ENGINE_CHOICES,
        default="auto",
        help="LaTeX engine for PDF output (auto prefers lualatex, then xelatex, then pdflatex).",
    )
    parser.add_argument(
        "--latex-runs",
        type=int,
        default=2,
        help="Number of LaTeX compilation passes when --output-format pdf is used.",
    )
    parser.add_argument(
        "--pdf-keep-tex",
        action="store_true",
        help="When generating PDF, also write a sidecar .tex file next to the PDF output.",
    )
    parser.add_argument(
        "--overflow-policy",
        choices=OVERFLOW_POLICY_CHOICES,
        default="ask",
        help=(
            "How to handle PDF overflow warnings when text does not fit the page: "
            "ask, keep, abort, fit, or larger-page."
        ),
    )
    parser.add_argument(
        "--paper-size",
        default="us-letter",
        help=(
            "Paper size preset for LaTeX/PDF output "
            "(for example: us-letter, us-legal, a4, a3, a5, b5, executive, 11x17)."
        ),
    )
    parser.add_argument(
        "--orientation",
        choices=ORIENTATION_CHOICES,
        default="portrait",
        help="Page orientation for LaTeX/PDF output.",
    )
    parser.add_argument(
        "--page-width",
        default=None,
        help="Custom page width with unit (for example 11in, 420mm). Requires --page-height.",
    )
    parser.add_argument(
        "--page-height",
        default=None,
        help="Custom page height with unit (for example 17in, 297mm). Requires --page-width.",
    )
    parser.add_argument(
        "--page-margin",
        default="1in",
        help="Page margin for LaTeX/PDF output, with unit (default: 1in).",
    )
    parser.add_argument(
        "--table-font-size",
        choices=TABLE_FONT_SIZE_CHOICES,
        default="scriptsize",
        help="LaTeX table font size in normal mode (default: scriptsize).",
    )
    parser.add_argument(
        "--table-fit-font-size",
        choices=TABLE_FONT_SIZE_CHOICES,
        default="tiny",
        help="LaTeX table font size in overflow fit mode (default: tiny).",
    )
    parser.add_argument(
        "--table-tabcolsep-pt",
        type=float,
        default=3.0,
        help="LaTeX table horizontal cell padding in pt for normal mode (default: 3.0).",
    )
    parser.add_argument(
        "--table-fit-tabcolsep-pt",
        type=float,
        default=1.5,
        help="LaTeX table horizontal cell padding in pt for fit mode (default: 1.5).",
    )
    parser.add_argument(
        "--table-arraystretch",
        type=float,
        default=1.25,
        help="LaTeX table row stretch multiplier (default: 1.25).",
    )
    parser.add_argument(
        "--table-extra-row-height-pt",
        type=float,
        default=0.9,
        help="Extra row height added to every table row in pt (default: 0.9).",
    )
    parser.add_argument(
        "--table-row-strut-ex",
        type=float,
        default=3.0,
        help="Minimum row strut height in ex units applied to each cell (default: 3.0).",
    )
    parser.add_argument(
        "--table-usable-width",
        type=float,
        default=0.995,
        help="Fraction of linewidth allocated to longtable columns in normal mode (default: 0.995).",
    )
    parser.add_argument(
        "--table-fit-usable-width",
        type=float,
        default=0.995,
        help="Fraction of linewidth allocated to longtable columns in fit mode (default: 0.995).",
    )
    parser.add_argument(
        "--table-min-column-width",
        type=float,
        default=0.04,
        help="Minimum linewidth fraction for any table column (default: 0.04).",
    )
    parser.add_argument(
        "--table-emergency-stretch-em",
        type=float,
        default=6.0,
        help="LaTeX emergencystretch value in em to reduce overfull boxes (default: 6.0).",
    )
    parser.add_argument(
        "--table-break-long-tokens",
        dest="table_break_long_tokens",
        action="store_true",
        help="Insert soft breakpoints into long text tokens in LaTeX/PDF tables.",
    )
    parser.add_argument(
        "--no-table-break-long-tokens",
        dest="table_break_long_tokens",
        action="store_false",
        help="Disable long-token soft break insertion in LaTeX/PDF tables.",
    )
    parser.set_defaults(table_break_long_tokens=True)
    parser.add_argument(
        "--table-break-chunk",
        type=int,
        default=4,
        help="Character chunk size for inserted long-token soft breaks (default: 4).",
    )
    parser.add_argument(
        "--table-max-decimals",
        type=int,
        default=24,
        help=(
            "Maximum fractional digits shown for plain decimal numeric fields in LaTeX/PDF tables "
            "(default: 24; set to a large value to preserve more digits)."
        ),
    )
    parser.add_argument(
        "--table-trim-trailing-zeros",
        dest="table_trim_trailing_zeros",
        action="store_true",
        help="Trim trailing zeros from rendered decimal values in LaTeX/PDF tables.",
    )
    parser.add_argument(
        "--no-table-trim-trailing-zeros",
        dest="table_trim_trailing_zeros",
        action="store_false",
        help="Keep trailing zeros in rendered decimal values in LaTeX/PDF tables.",
    )
    parser.set_defaults(table_trim_trailing_zeros=True)
    parser.add_argument(
        "--table-zebra",
        dest="table_zebra",
        action="store_true",
        help="Enable alternating light-gray row shading in LaTeX/PDF tables.",
    )
    parser.add_argument(
        "--no-table-zebra",
        dest="table_zebra",
        action="store_false",
        help="Disable alternating row shading in LaTeX/PDF tables.",
    )
    parser.set_defaults(table_zebra=True)
    parser.add_argument(
        "--table-zebra-black-pct",
        type=float,
        default=6.0,
        help="Black percentage for zebra stripe shading (default: 6.0).",
    )
    parser.add_argument(
        "--table-header-shade",
        action="store_true",
        help="Enable header-row background shading in LaTeX/PDF tables.",
    )
    parser.add_argument(
        "--table-header-black-pct",
        type=float,
        default=7.5,
        help="Black percentage for header-row shading (default: 7.5).",
    )
    parser.add_argument(
        "--table-weight-text",
        type=float,
        default=2.6,
        help="Relative width weight for wide text-like columns (default: 2.6).",
    )
    parser.add_argument(
        "--table-weight-math",
        type=float,
        default=1.8,
        help="Relative width weight for math columns (default: 1.8).",
    )
    parser.add_argument(
        "--table-weight-numeric",
        type=float,
        default=1.2,
        help="Relative width weight for numeric columns (default: 1.2).",
    )
    parser.add_argument(
        "--table-weight-other",
        type=float,
        default=1.5,
        help="Relative width weight for all other columns (default: 1.5).",
    )

    parser.add_argument(
        "--just-input",
        type=Path,
        default=Path("just-intervals.txt"),
        help="Input path for just intervals source.",
    )
    parser.add_argument(
        "--tempered-input",
        type=Path,
        default=Path("tempered-intervals.txt"),
        help="Input path for equal-division-of-the-octave (EDO) intervals source.",
    )
    parser.add_argument(
        "--historical-input",
        type=Path,
        default=Path("historical-intervals.txt"),
        help="Input path for historical irrational intervals source.",
    )

    parser.add_argument(
        "--regenerate-all",
        action="store_true",
        help="Always regenerate all three source files before assembly.",
    )
    parser.add_argument(
        "--skip-generation",
        action="store_true",
        help="Do not generate missing sources; fail if any source file is absent.",
    )

    parser.add_argument(
        "--max-harmonic",
        "--harmonic-limit",
        dest="harmonic_limit",
        type=int,
        default=320,
        help="Passed to generate-just-intervals.py when generating sources.",
    )
    parser.add_argument(
        "--max-prime",
        type=int,
        default=None,
        help="Optional prime-limit filter passed to generate-just-intervals.py.",
    )
    parser.add_argument(
        "--max-edo",
        type=int,
        default=96,
        help="Passed to generate-tempered-intervals.py when generating sources.",
    )
    parser.add_argument(
        "--historical-extra-json",
        type=Path,
        default=None,
        help="Optional extra source passed to historical generator (legacy alias).",
    )
    parser.add_argument(
        "--historical-extra-source",
        type=Path,
        default=None,
        help="Optional extra source passed to generate-historical-intervals.py.",
    )
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python executable used to invoke source generator scripts.",
    )
    parser.add_argument(
        "--check-rendering-conventions",
        action="store_true",
        help=(
            "Run LaTeX rendering regression checks (chapter labels, hyperlink wrapping, "
            "zebra rows, and banned phrase guardrails) before writing output."
        ),
    )
    add_output_control_args(parser)

    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.harmonic_limit < 1:
        raise ValueError("--max-harmonic/--harmonic-limit must be >= 1.")
    if args.max_prime is not None and args.max_prime < 2:
        raise ValueError("--max-prime must be >= 2 when provided.")
    if args.max_edo < 1:
        raise ValueError("--max-edo must be >= 1.")
    if args.latex_runs < 1:
        raise ValueError("--latex-runs must be >= 1.")
    if args.table_tabcolsep_pt <= 0:
        raise ValueError("--table-tabcolsep-pt must be > 0.")
    if args.table_fit_tabcolsep_pt <= 0:
        raise ValueError("--table-fit-tabcolsep-pt must be > 0.")
    if args.table_arraystretch <= 0:
        raise ValueError("--table-arraystretch must be > 0.")
    if args.table_extra_row_height_pt < 0:
        raise ValueError("--table-extra-row-height-pt must be >= 0.")
    if args.table_row_strut_ex <= 0:
        raise ValueError("--table-row-strut-ex must be > 0.")
    if not (0 < args.table_usable_width <= 1):
        raise ValueError("--table-usable-width must be in the range (0, 1].")
    if not (0 < args.table_fit_usable_width <= 1):
        raise ValueError("--table-fit-usable-width must be in the range (0, 1].")
    if not (0 < args.table_min_column_width < 1):
        raise ValueError("--table-min-column-width must be in the range (0, 1).")
    if args.table_emergency_stretch_em < 0:
        raise ValueError("--table-emergency-stretch-em must be >= 0.")
    if args.table_break_chunk < 2:
        raise ValueError("--table-break-chunk must be >= 2.")
    if args.table_max_decimals < 0:
        raise ValueError("--table-max-decimals must be >= 0.")
    if not (0 <= args.table_zebra_black_pct < 100):
        raise ValueError("--table-zebra-black-pct must be in the range [0, 100).")
    if not (0 <= args.table_header_black_pct < 100):
        raise ValueError("--table-header-black-pct must be in the range [0, 100).")
    if args.table_weight_text <= 0:
        raise ValueError("--table-weight-text must be > 0.")
    if args.table_weight_math <= 0:
        raise ValueError("--table-weight-math must be > 0.")
    if args.table_weight_numeric <= 0:
        raise ValueError("--table-weight-numeric must be > 0.")
    if args.table_weight_other <= 0:
        raise ValueError("--table-weight-other must be > 0.")
    # Validate page layout options up front so PDF/LaTeX modes fail early with clear messages.
    resolve_page_layout(
        paper_size=args.paper_size,
        orientation=args.orientation,
        page_width=args.page_width,
        page_height=args.page_height,
        page_margin=args.page_margin,
    )
    if args.historical_extra_json is not None and args.historical_extra_source is not None:
        raise ValueError("Use only one of --historical-extra-json or --historical-extra-source.")
    extra_source = args.historical_extra_source or args.historical_extra_json
    if extra_source is not None and not extra_source.exists():
        raise FileNotFoundError(f"Historical extra source file not found: {extra_source}.")
    validate_output_control_args(args)


def resolve_table_style(args: argparse.Namespace) -> LatexTableStyle:
    return LatexTableStyle(
        font_size=args.table_font_size,
        fit_font_size=args.table_fit_font_size,
        tabcolsep_pt=args.table_tabcolsep_pt,
        fit_tabcolsep_pt=args.table_fit_tabcolsep_pt,
        arraystretch=args.table_arraystretch,
        extra_row_height_pt=args.table_extra_row_height_pt,
        row_strut_ex=args.table_row_strut_ex,
        usable_width=args.table_usable_width,
        fit_usable_width=args.table_fit_usable_width,
        min_column_width=args.table_min_column_width,
        emergency_stretch_em=args.table_emergency_stretch_em,
        break_long_tokens=args.table_break_long_tokens,
        break_chunk=args.table_break_chunk,
        max_decimals=args.table_max_decimals,
        trim_trailing_zeros=args.table_trim_trailing_zeros,
        zebra=args.table_zebra,
        zebra_black_pct=args.table_zebra_black_pct,
        header_shade=args.table_header_shade,
        header_black_pct=args.table_header_black_pct,
        weight_text=args.table_weight_text,
        weight_math=args.table_weight_math,
        weight_numeric=args.table_weight_numeric,
        weight_other=args.table_weight_other,
    )


def build_forwarded_output_switches(args: argparse.Namespace) -> List[str]:
    switches: List[str] = []
    if args.verbosity is not None:
        switches.extend(["--verbosity", args.verbosity])
    else:
        if args.quiet:
            switches.append("--quiet")
        if args.verbose:
            switches.extend(["-v"] * int(args.verbose))

    if args.progress:
        switches.append("--progress")
    elif args.no_progress:
        switches.append("--no-progress")

    if args.progress_width != 30:
        switches.extend(["--progress-width", str(args.progress_width)])
    return switches


def main() -> None:
    args = parse_args()
    validate_args(args)
    reporter = create_reporter(args)
    table_style = resolve_table_style(args)
    page_layout = resolve_page_layout(
        paper_size=args.paper_size,
        orientation=args.orientation,
        page_width=args.page_width,
        page_height=args.page_height,
        page_margin=args.page_margin,
    )

    root = Path(__file__).resolve().parent
    just_script = root / "generate-just-intervals.py"
    tempered_script = root / "generate-tempered-intervals.py"
    historical_script = root / "generate-historical-intervals.py"
    forwarded_output_switches = build_forwarded_output_switches(args)
    just_output_format = infer_source_format(args.just_input)
    tempered_output_format = infer_source_format(args.tempered_input)
    historical_output_format = infer_source_format(args.historical_input)

    just_command = [
        str(args.python),
        str(just_script),
        "--max-harmonic",
        str(args.harmonic_limit),
        "--output",
        str(args.just_input),
        "--output-format",
        just_output_format,
        *forwarded_output_switches,
    ]
    if args.max_prime is not None:
        just_command.extend(["--max-prime", str(args.max_prime)])

    tempered_command = [
        str(args.python),
        str(tempered_script),
        "--max-edo",
        str(args.max_edo),
        "--output",
        str(args.tempered_input),
        "--output-format",
        tempered_output_format,
        *forwarded_output_switches,
    ]

    historical_command = [
        str(args.python),
        str(historical_script),
        "--output",
        str(args.historical_input),
        "--output-format",
        historical_output_format,
        *forwarded_output_switches,
    ]
    historical_extra_source = args.historical_extra_source or args.historical_extra_json
    if historical_extra_source is not None:
        historical_command.extend(["--extra-source", str(historical_extra_source)])

    source_progress = reporter.progress(total=3, label="Source prep")
    ensure_source(
        path=args.just_input,
        label="just",
        command=just_command,
        regenerate_all=args.regenerate_all,
        skip_generation=args.skip_generation,
        reporter=reporter,
    )
    source_progress.update(1)
    ensure_source(
        path=args.tempered_input,
        label="tempered",
        command=tempered_command,
        regenerate_all=args.regenerate_all,
        skip_generation=args.skip_generation,
        reporter=reporter,
    )
    source_progress.update(2)
    ensure_source(
        path=args.historical_input,
        label="historical",
        command=historical_command,
        regenerate_all=args.regenerate_all,
        skip_generation=args.skip_generation,
        reporter=reporter,
    )
    source_progress.update(3)
    source_progress.finish()

    volumes = [
        read_volume("JUST", "Just Intervals", args.just_input),
        read_volume("TEMPERED", "Equal-Division (EDO) Intervals", args.tempered_input),
        read_volume(
            "HISTORICAL",
            "Historical and Esoteric Irrational Intervals",
            args.historical_input,
        ),
    ]
    if args.check_rendering_conventions:
        run_rendering_convention_checks(
            volumes=volumes,
            page_layout=page_layout,
            table_style=table_style,
            reporter=reporter,
        )
    write_master(
        args.output,
        volumes,
        output_format=args.output_format,
        page_layout=page_layout,
        table_style=table_style,
        latex_engine=args.latex_engine,
        latex_runs=args.latex_runs,
        overflow_policy=args.overflow_policy,
        keep_pdf_tex=args.pdf_keep_tex,
        reporter=reporter,
    )

    reporter.print_result(f"Wrote master tome to {args.output}")


if __name__ == "__main__":
    main()
