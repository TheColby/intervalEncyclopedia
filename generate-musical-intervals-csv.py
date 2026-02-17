#!/usr/bin/env python3
"""
Export the Wikipedia "List of musical intervals" table to CSV.

Source page:
https://en.wikipedia.org/wiki/List_of_pitch_intervals
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Sequence

from cli_output import (
    Reporter,
    add_output_control_args,
    create_reporter,
    validate_output_control_args,
)


OUTPUT_FORMAT_CHOICES = ("auto", "csv", "json")


def infer_output_format(output_path: Path, requested_format: str) -> str:
    if requested_format != "auto":
        return requested_format
    if output_path.suffix.lower() == ".json":
        return "json"
    return "csv"


@dataclass
class TableCell:
    text: str
    rowspan: int = 1
    colspan: int = 1


@dataclass
class ParsedTable:
    caption: str
    classes: List[str]
    rows: List[List[TableCell]]


def parse_positive_int(value: str | None, default: int = 1) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def normalize_text(value: str) -> str:
    collapsed = re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()
    return collapsed


def strip_reference_markers(value: str) -> str:
    return re.sub(r"\[\d+\]", "", value).strip()


def clean_interval_name(value: str) -> str:
    # The page uses "play ⓘ" before names in this column.
    cleaned = re.sub(r"^(?:play\s*ⓘ?\s*)+", "", value, flags=re.IGNORECASE)
    return cleaned.strip()


class WikiTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: List[ParsedTable] = []
        self._table_stack: List[Dict[str, object]] = []

    def handle_starttag(self, tag: str, attrs: Sequence[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "table":
            classes = attrs_dict.get("class", "") or ""
            self._table_stack.append(
                {
                    "caption_parts": [],
                    "classes": classes.split(),
                    "rows": [],
                    "current_row": None,
                    "current_cell": None,
                    "in_caption": False,
                    "skip_ref_depth": 0,
                }
            )
            return

        if not self._table_stack:
            return

        table = self._table_stack[-1]
        if tag == "caption":
            table["in_caption"] = True
            return

        current_row = table.get("current_row")
        if tag == "tr":
            table["current_row"] = []
            return
        if tag in ("th", "td") and isinstance(current_row, list):
            table["current_cell"] = {
                "parts": [],
                "rowspan": parse_positive_int(attrs_dict.get("rowspan"), default=1),
                "colspan": parse_positive_int(attrs_dict.get("colspan"), default=1),
            }
            return

        current_cell = table.get("current_cell")
        if isinstance(current_cell, dict):
            if tag == "br":
                current_cell["parts"].append(" / ")
                return
            if tag == "img":
                alt_text = normalize_text(attrs_dict.get("alt", "") or "")
                if alt_text:
                    current_cell["parts"].append(alt_text)
                return
            if tag == "sup":
                classes = (attrs_dict.get("class", "") or "").split()
                if "reference" in classes:
                    table["skip_ref_depth"] = int(table["skip_ref_depth"]) + 1

    def handle_endtag(self, tag: str) -> None:
        if not self._table_stack:
            return

        table = self._table_stack[-1]
        if tag == "table":
            completed = self._table_stack.pop()
            rows = completed["rows"] if isinstance(completed["rows"], list) else []
            classes = completed["classes"] if isinstance(completed["classes"], list) else []
            caption_parts = (
                completed["caption_parts"] if isinstance(completed["caption_parts"], list) else []
            )
            caption = normalize_text("".join(str(part) for part in caption_parts))
            self.tables.append(ParsedTable(caption=caption, classes=classes, rows=rows))
            return

        if tag == "caption":
            table["in_caption"] = False
            return

        if tag == "sup" and int(table.get("skip_ref_depth", 0)) > 0:
            table["skip_ref_depth"] = int(table["skip_ref_depth"]) - 1
            return

        if tag in ("th", "td"):
            current_cell = table.get("current_cell")
            current_row = table.get("current_row")
            if isinstance(current_cell, dict) and isinstance(current_row, list):
                text = normalize_text("".join(current_cell["parts"]))
                if text:
                    text = strip_reference_markers(text)
                current_row.append(
                    TableCell(
                        text=text,
                        rowspan=int(current_cell.get("rowspan", 1)),
                        colspan=int(current_cell.get("colspan", 1)),
                    )
                )
            table["current_cell"] = None
            return

        if tag == "tr":
            current_row = table.get("current_row")
            if isinstance(current_row, list) and current_row:
                rows = table.get("rows")
                if isinstance(rows, list):
                    rows.append(current_row)
            table["current_row"] = None

    def handle_data(self, data: str) -> None:
        if not self._table_stack:
            return
        table = self._table_stack[-1]

        if table.get("in_caption"):
            caption_parts = table.get("caption_parts")
            if isinstance(caption_parts, list):
                caption_parts.append(data)
            return

        if int(table.get("skip_ref_depth", 0)) > 0:
            return

        current_cell = table.get("current_cell")
        if isinstance(current_cell, dict):
            current_cell["parts"].append(data)


def expand_rowspan_colspan(rows: List[List[TableCell]]) -> List[List[str]]:
    expanded: List[List[str]] = []
    active_spans: Dict[int, tuple[int, str]] = {}
    max_columns = 0

    for raw_row in rows:
        row_map: Dict[int, str] = {}

        next_spans: Dict[int, tuple[int, str]] = {}
        for column, (remaining, value) in active_spans.items():
            row_map[column] = value
            if remaining > 1:
                next_spans[column] = (remaining - 1, value)
        active_spans = next_spans

        column_index = 0
        for cell in raw_row:
            while column_index in row_map:
                column_index += 1

            for offset in range(cell.colspan):
                target_column = column_index + offset
                row_map[target_column] = cell.text
                if cell.rowspan > 1:
                    active_spans[target_column] = (cell.rowspan - 1, cell.text)

            column_index += cell.colspan

        width = (max(row_map.keys()) + 1) if row_map else 0
        max_columns = max(max_columns, width)
        row_list = [""] * width
        for column, value in row_map.items():
            row_list[column] = value
        expanded.append(row_list)

    for row in expanded:
        if len(row) < max_columns:
            row.extend([""] * (max_columns - len(row)))

    return expanded


def find_target_table(tables: List[ParsedTable], caption: str) -> ParsedTable:
    target = caption.casefold()
    for table in tables:
        if target in table.caption.casefold():
            return table

    for table in tables:
        classes = {entry.casefold() for entry in table.classes}
        if "wikitable" not in classes:
            continue
        expanded = expand_rowspan_colspan(table.rows)
        if not expanded:
            continue
        header = [normalize_text(cell).casefold() for cell in expanded[0]]
        if "cents" in header and any("freq." in cell for cell in header):
            return table

    raise ValueError(f'Could not find table with caption containing "{caption}".')


def find_header_row(rows: List[List[str]]) -> int:
    for index, row in enumerate(rows):
        lowered = [normalize_text(cell).casefold() for cell in row]
        if "cents" in lowered and any("interval name" in cell for cell in lowered):
            return index
    raise ValueError("Could not locate the header row in the selected table.")


def dedupe_headers(raw_headers: List[str]) -> List[str]:
    counters: Dict[str, int] = {}
    output: List[str] = []
    for index, value in enumerate(raw_headers):
        header = normalize_text(value)
        if not header:
            header = f"column_{index + 1}"
        count = counters.get(header, 0) + 1
        counters[header] = count
        if count > 1:
            header = f"{header}_{count}"
        output.append(header)
    return output


def build_records(headers: List[str], rows: List[List[str]]) -> List[Dict[str, str]]:
    records: List[Dict[str, str]] = []
    for row in rows:
        if not any(normalize_text(cell) for cell in row):
            continue
        padded = row + [""] * (len(headers) - len(row))
        record = dict(zip(headers, padded))
        if "Interval name" in record:
            record["Interval name"] = clean_interval_name(record["Interval name"])
        records.append(record)
    return records


def write_csv(
    output: Path,
    headers: List[str],
    records: List[Dict[str, str]],
    reporter: Reporter,
) -> int:
    reporter.info(f"Writing CSV rows to {output}...")
    progress = reporter.progress(total=max(1, len(records)), label="CSV rows")
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for index, record in enumerate(records, start=1):
            writer.writerow(record)
            progress.update(index)

    progress.finish()
    return len(records)


def write_json(
    output: Path,
    headers: List[str],
    records: List[Dict[str, str]],
    source_url: str,
    table_caption: str,
    reporter: Reporter,
) -> int:
    reporter.info(f"Writing JSON rows to {output}...")
    payload = {
        "metadata": {
            "title": "List of musical intervals table export",
            "source_url": source_url,
            "table_caption": table_caption,
            "output_format": "json",
            "total_rows": len(records),
        },
        "columns": headers,
        "rows": records,
    }
    with output.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return len(records)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            'Export the "List of musical intervals" table from '
            "Wikipedia's List_of_pitch_intervals page."
        )
    )
    parser.add_argument(
        "--url",
        default="https://en.wikipedia.org/wiki/List_of_pitch_intervals",
        help="Source page URL.",
    )
    parser.add_argument(
        "--table-caption",
        default="List of musical intervals",
        help="Target table caption (substring match, case-insensitive).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("musical-intervals.csv"),
        help="Output path (.csv/.json or set --output-format).",
    )
    parser.add_argument(
        "--output-format",
        choices=OUTPUT_FORMAT_CHOICES,
        default="auto",
        help="Output format. Use 'auto' to infer from file extension.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=30.0,
        help="HTTP timeout in seconds.",
    )
    add_output_control_args(parser)
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.timeout_seconds <= 0:
        raise ValueError("--timeout-seconds must be > 0.")
    validate_output_control_args(args)


def download_html(url: str, timeout_seconds: float) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "intervalEncyclopedia/1.0 (table export script)"},
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = response.read()
    return payload.decode("utf-8", errors="replace")


def main() -> None:
    args = parse_args()
    validate_args(args)
    reporter = create_reporter(args)

    reporter.info(f"Downloading HTML from {args.url}...")
    html = download_html(args.url, timeout_seconds=args.timeout_seconds)
    reporter.info("Parsing HTML tables...")
    parser = WikiTableParser()
    parser.feed(html)
    parser.close()

    reporter.info("Locating target interval table...")
    table = find_target_table(parser.tables, args.table_caption)
    expanded_rows = expand_rowspan_colspan(table.rows)
    header_index = find_header_row(expanded_rows)
    headers = dedupe_headers(expanded_rows[header_index])
    data_rows = expanded_rows[header_index + 1 :]

    records = build_records(headers, data_rows)
    output_format = infer_output_format(args.output, args.output_format)
    if output_format == "csv":
        row_count = write_csv(args.output, headers, records, reporter=reporter)
    elif output_format == "json":
        row_count = write_json(
            args.output,
            headers,
            records,
            source_url=args.url,
            table_caption=args.table_caption,
            reporter=reporter,
        )
    else:
        raise ValueError(f"Unsupported output format: {output_format}")
    reporter.print_result(f"Wrote {row_count} rows to {args.output}")
    if reporter.verbosity >= 2:
        print(f"Columns: {', '.join(headers)}")


if __name__ == "__main__":
    main()
