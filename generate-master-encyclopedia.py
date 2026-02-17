#!/usr/bin/env python3
"""
Generate the master "The Tuning Encyclopedia" file by stitching all source volumes.

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


MASTER_TITLE = "The Tuning Encyclopedia"
LATEX_ENGINE_CHOICES = ("auto", "lualatex", "xelatex", "pdflatex")
ORIENTATION_CHOICES = ("portrait", "landscape")
OUTPUT_FORMAT_CHOICES = ("auto", "txt", "csv", "json", "latex", "pdf")
LATEX_MATH_COLUMNS = {"ratio", "prime_factorization", "expression"}
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
    "edo",
    "step",
    "cents",
    "value",
    "largest_prime",
    "odd_limit",
    "total_rows",
}
LATEX_DIMENSION_PATTERN = re.compile(r"^\d+(?:\.\d+)?(?:in|mm|cm|pt)$", re.IGNORECASE)
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
        )

    canonical_paper = normalize_paper_size(paper_size)
    geometry_paper_options = list(PAPER_SIZE_CANONICAL_TO_GEOMETRY[canonical_paper])
    options = [*geometry_paper_options, orientation, f"margin={margin}"]
    return PageLayout(
        geometry_options=",".join(options),
        paper_label=canonical_paper,
        orientation=orientation,
    )


@dataclass(frozen=True)
class Volume:
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


def read_volume(tag: str, title: str, source_path: Path) -> Volume:
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

    return Volume(
        tag=tag,
        title=title,
        source_path=source_path,
        source_format=source_format,
        content=text,
        total_rows=total_rows,
    )


def write_master_txt(output_path: Path, volumes: List[Volume], reporter: Reporter) -> None:
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


def write_master_csv(output_path: Path, volumes: List[Volume], reporter: Reporter) -> None:
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


def write_master_json(output_path: Path, volumes: List[Volume], reporter: Reporter) -> None:
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


def latex_escape(text: str) -> str:
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
    return "".join(replacements.get(char, char) for char in text)


def sanitize_verbatim_text(text: str) -> str:
    # Strip NUL characters because they break TeX tokenization.
    return text.replace("\x00", "")


def normalize_cell_text(value: str) -> str:
    return str(value).replace("\x00", "").replace("\t", " ").replace("\n", " ").strip()


def json_value_to_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def parse_volume_rows(volume: Volume) -> tuple[List[str], List[dict[str, str]]]:
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
    return rf"\mathrm{{{latex_escape(identifier)}}}"


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
        return node[1]
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
            return rf"\frac{{{ast_to_latex(left)}}}{{{ast_to_latex(right)}}}"
        left_text = ast_to_latex(left)
        right_text = ast_to_latex(right)
        if needs_parentheses(operator, left):
            left_text = rf"\left({left_text}\right)"
        if needs_parentheses(operator, right, is_right=True):
            right_text = rf"\left({right_text}\right)"
        if operator == "*":
            return rf"{left_text} \cdot {right_text}"
        return rf"{left_text} {operator} {right_text}"

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


def maybe_typeset_math(text: str) -> str:
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
        return rf"\texttt{{{latex_escape(normalized)}}}"
    return rf"\({parsed}\)"


def canonical_column_name(column: str) -> str:
    return normalize_cell_text(column).casefold().replace(" ", "_")


def render_latex_cell(column: str, value: str) -> str:
    normalized = normalize_cell_text(value)
    canonical = canonical_column_name(column)
    if canonical in LATEX_MATH_COLUMNS:
        return maybe_typeset_math(normalized)
    return latex_escape(normalized)


def latex_column_weight(canonical_column: str) -> float:
    if canonical_column in LATEX_WIDE_TEXT_COLUMNS:
        return 2.6
    if canonical_column in LATEX_MATH_COLUMNS:
        return 1.8
    if canonical_column in LATEX_NUMERIC_COLUMNS:
        return 1.2
    return 1.5


def latex_column_alignment(canonical_column: str) -> str:
    if canonical_column in LATEX_NUMERIC_COLUMNS:
        return r"\raggedleft\arraybackslash"
    return r"\raggedright\arraybackslash"


def latex_column_spec_for_columns(columns: Sequence[str], usable_width: float = 0.98) -> str:
    if not columns:
        return "@{}l@{}"

    canonical_columns = [canonical_column_name(column) for column in columns]
    weights = [latex_column_weight(canonical_column) for canonical_column in canonical_columns]
    weight_total = sum(weights)
    columns_spec: List[str] = []
    for canonical_column, weight in zip(canonical_columns, weights):
        width = usable_width * (weight / weight_total)
        columns_spec.append(
            rf">{{{latex_column_alignment(canonical_column)}}}p{{{width:.5f}\linewidth}}"
        )
    return "@{}" + "".join(columns_spec) + "@{}"


def build_latex_table_for_volume(volume: Volume) -> List[str]:
    columns, rows = parse_volume_rows(volume)
    if not columns:
        return [
            r"\section*{Source Content}",
            r"\begin{Verbatim}[fontsize=\footnotesize]",
            sanitize_verbatim_text(volume.content),
            r"\end{Verbatim}",
        ]

    lines: List[str] = [
        r"\section*{Tabular Content}",
        r"\begingroup",
        r"\scriptsize",
        rf"\begin{{longtable}}{{{latex_column_spec_for_columns(columns)}}}",
        r"\toprule",
        " & ".join(latex_escape(column) for column in columns) + r" \\",
        r"\midrule",
        r"\endhead",
    ]

    for row in rows:
        cells = [render_latex_cell(column, row.get(column, "")) for column in columns]
        lines.append(" & ".join(cells) + r" \\")

    lines.extend([r"\bottomrule", r"\end{longtable}", r"\endgroup"])
    return lines


def build_latex_document(volumes: List[Volume], generated_utc: str, page_layout: PageLayout) -> str:
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
        r"\usepackage{ragged2e}",
        r"\usepackage[hidelinks]{hyperref}",
        r"\usepackage{fancyhdr}",
        r"\usepackage{fancyvrb}",
        r"\setlength{\parindent}{0pt}",
        r"\setlength{\parskip}{0.55em}",
        r"\setlength{\LTleft}{0pt}",
        r"\setlength{\LTright}{0pt}",
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
        r"\author{intervalEncyclopedia generator}",
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
        r"This document is generated automatically from the three source volumes of intervalEncyclopedia.",
        r"\begin{itemize}",
        rf"  \item Edition title: {latex_escape(MASTER_TITLE)}",
        rf"  \item Generation timestamp (UTC): {latex_escape(generated_utc)}",
        rf"  \item Paper layout: {latex_escape(page_layout.paper_label)} ({latex_escape(page_layout.orientation)})",
        rf"  \item Volume count: {len(volumes)}",
        r"\end{itemize}",
        r"\mainmatter",
        r"\chapter{Volume Index}",
        rf"\begin{{longtable}}{{{latex_column_spec_for_columns(['tag', 'title', 'source_file', 'source_format', 'total_rows'])}}}",
        r"\toprule",
        r"Tag & Title & Source File & Source Format & Total Rows \\",
        r"\midrule",
        r"\endhead",
    ]

    for volume in volumes:
        lines.append(
            rf"{latex_escape(volume.tag)} & {latex_escape(volume.title)} & "
            rf"\texttt{{{latex_escape(str(volume.source_path))}}} & "
            rf"{latex_escape(volume.source_format)} & "
            rf"{latex_escape(volume.total_rows)} \\"
        )

    lines.extend([r"\bottomrule", r"\end{longtable}"])

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
        lines.extend(build_latex_table_for_volume(volume))

    lines.extend([r"\end{document}", ""])
    return "\n".join(lines)


def write_master_latex(
    output_path: Path,
    volumes: List[Volume],
    page_layout: PageLayout,
    reporter: Reporter,
) -> None:
    reporter.info(f"Writing master document (latex) with {len(volumes)} volumes...")
    generated_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    document = build_latex_document(
        volumes=volumes,
        generated_utc=generated_utc,
        page_layout=page_layout,
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


def run_latex_pass(engine: str, tex_path: Path, reporter: Reporter) -> None:
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


def write_master_pdf(
    output_path: Path,
    volumes: List[Volume],
    page_layout: PageLayout,
    latex_engine: str,
    latex_runs: int,
    keep_pdf_tex: bool,
    reporter: Reporter,
) -> None:
    reporter.info(f"Writing master document (pdf) with {len(volumes)} volumes...")
    generated_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    document = build_latex_document(
        volumes=volumes,
        generated_utc=generated_utc,
        page_layout=page_layout,
    )
    engines = resolve_latex_engines(latex_engine)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    compile_errors: List[str] = []
    compiled = False
    for engine in engines:
        try:
            with tempfile.TemporaryDirectory(prefix="tuning-encyclopedia-") as temp_dir:
                temp_dir_path = Path(temp_dir)
                tex_path = temp_dir_path / "the-tuning-encyclopedia.tex"
                tex_path.write_text(document, encoding="utf-8")

                for pass_index in range(1, latex_runs + 1):
                    reporter.info(f"Compiling PDF ({engine}), pass {pass_index}/{latex_runs}...")
                    run_latex_pass(engine=engine, tex_path=tex_path, reporter=reporter)

                compiled_pdf_path = tex_path.with_suffix(".pdf")
                if not compiled_pdf_path.exists():
                    raise RuntimeError(
                        f"LaTeX engine did not produce expected PDF: {compiled_pdf_path}"
                    )

                shutil.copy2(compiled_pdf_path, output_path)
                reporter.info(f"Compiled PDF successfully with {engine}.")
                compiled = True
                break
        except RuntimeError as error:
            compile_errors.append(f"{engine}: {error}")
            if latex_engine != "auto":
                raise
            reporter.verbose(f"Engine {engine} failed; trying next available engine.")

    if not compiled:
        raise RuntimeError(
            "Failed to compile PDF with all available engines.\n" + "\n\n".join(compile_errors)
        )

    if keep_pdf_tex:
        sidecar_tex = output_path.with_suffix(".tex")
        sidecar_tex.write_text(document, encoding="utf-8")
        reporter.info(f"Wrote sidecar LaTeX source to {sidecar_tex}")


def write_master(
    output_path: Path,
    volumes: List[Volume],
    output_format: str,
    page_layout: PageLayout,
    latex_engine: str,
    latex_runs: int,
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
            reporter=reporter,
        )
        return
    if resolved_format == "pdf":
        write_master_pdf(
            output_path=output_path,
            volumes=volumes,
            page_layout=page_layout,
            latex_engine=latex_engine,
            latex_runs=latex_runs,
            keep_pdf_tex=keep_pdf_tex,
            reporter=reporter,
        )
        return
    raise ValueError(f"Unsupported output format: {resolved_format}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Assemble source volumes into the master The Tuning Encyclopedia file."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("the-tuning-encyclopedia.txt"),
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
        "--just-input",
        type=Path,
        default=Path("just-intervals.txt"),
        help="Input path for just intervals source.",
    )
    parser.add_argument(
        "--tempered-input",
        type=Path,
        default=Path("tempered-intervals.txt"),
        help="Input path for equal-tempered intervals source.",
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
        read_volume("JUST", "Volume I - Just Intervals", args.just_input),
        read_volume("TEMPERED", "Volume II - Equal Tempered Intervals", args.tempered_input),
        read_volume(
            "HISTORICAL",
            "Volume III - Historical and Esoteric Irrational Intervals",
            args.historical_input,
        ),
    ]
    write_master(
        args.output,
        volumes,
        output_format=args.output_format,
        page_layout=page_layout,
        latex_engine=args.latex_engine,
        latex_runs=args.latex_runs,
        keep_pdf_tex=args.pdf_keep_tex,
        reporter=reporter,
    )

    reporter.print_result(f"Wrote master tome to {args.output}")


if __name__ == "__main__":
    main()
