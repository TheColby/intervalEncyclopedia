#!/usr/bin/env python3
"""
Generate a master intervalEncyclopedia file by stitching all source volumes.

This script can optionally regenerate missing source files (or all source
files) by calling the three generator scripts in this workspace.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
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


OUTPUT_FORMAT_CHOICES = ("auto", "txt", "csv", "json")


def infer_data_format(path: Path, requested_format: str = "auto") -> str:
    if requested_format != "auto":
        return requested_format
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".json":
        return "json"
    return "txt"


@dataclass(frozen=True)
class Volume:
    tag: str
    title: str
    source_path: Path
    source_format: str
    content: str
    total_rows: str


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
    source_format = infer_data_format(source_path)
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
    with output_path.open("w", encoding="utf-8") as handle:
        handle.write("# intervalEncyclopedia - Master Tome\n")
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
            "title": "intervalEncyclopedia - Master Tome",
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
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_master(
    output_path: Path,
    volumes: List[Volume],
    output_format: str,
    reporter: Reporter,
) -> None:
    resolved_format = infer_data_format(output_path, requested_format=output_format)
    if resolved_format == "txt":
        write_master_txt(output_path=output_path, volumes=volumes, reporter=reporter)
        return
    if resolved_format == "csv":
        write_master_csv(output_path=output_path, volumes=volumes, reporter=reporter)
        return
    if resolved_format == "json":
        write_master_json(output_path=output_path, volumes=volumes, reporter=reporter)
        return
    raise ValueError(f"Unsupported output format: {resolved_format}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Assemble intervalEncyclopedia source volumes into a single master file."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("interval-encyclopedia-master.txt"),
        help="Master output path (.txt/.csv/.json or set --output-format).",
    )
    parser.add_argument(
        "--output-format",
        choices=OUTPUT_FORMAT_CHOICES,
        default="auto",
        help="Master output format. Use 'auto' to infer from output file extension.",
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

    root = Path(__file__).resolve().parent
    just_script = root / "generate-just-intervals.py"
    tempered_script = root / "generate-tempered-intervals.py"
    historical_script = root / "generate-historical-intervals.py"
    forwarded_output_switches = build_forwarded_output_switches(args)
    just_output_format = infer_data_format(args.just_input)
    tempered_output_format = infer_data_format(args.tempered_input)
    historical_output_format = infer_data_format(args.historical_input)

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
    write_master(args.output, volumes, output_format=args.output_format, reporter=reporter)

    reporter.print_result(f"Wrote master tome to {args.output}")


if __name__ == "__main__":
    main()
