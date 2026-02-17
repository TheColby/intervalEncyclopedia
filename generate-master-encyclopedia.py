#!/usr/bin/env python3
"""
Generate a master intervalEncyclopedia file by stitching all source volumes.

This script can optionally regenerate missing source files (or all source
files) by calling the three generator scripts in this workspace.
"""

from __future__ import annotations

import argparse
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


@dataclass(frozen=True)
class Volume:
    tag: str
    title: str
    source_path: Path
    content: str
    total_rows: str


def parse_total_rows(content: str) -> str:
    for line in content.splitlines():
        if line.startswith("# total_rows="):
            return line.split("=", 1)[1].strip()
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
    text = source_path.read_text(encoding="utf-8").rstrip("\n")
    return Volume(
        tag=tag,
        title=title,
        source_path=source_path,
        content=text,
        total_rows=parse_total_rows(text),
    )


def write_master(output_path: Path, volumes: List[Volume], reporter: Reporter) -> None:
    reporter.info(f"Writing master tome with {len(volumes)} volumes...")
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
        handle.write("tag\ttitle\tsource_file\ttotal_rows\n")
        for volume in volumes:
            handle.write(
                f"{volume.tag}\t{volume.title}\t{volume.source_path}\t{volume.total_rows}\n"
            )
            completed_steps += 1
            progress.update(completed_steps)

        handle.write("\n# volume_contents\n")
        for volume in volumes:
            handle.write(f"\n%%<VOLUME:{volume.tag}:BEGIN>\n")
            handle.write(f"# volume_title={volume.title}\n")
            handle.write(f"# source_file={volume.source_path}\n")
            handle.write(f"# total_rows={volume.total_rows}\n")
            handle.write(volume.content)
            handle.write("\n%%<VOLUME:{0}:END>\n".format(volume.tag))
            completed_steps += 1
            progress.update(completed_steps)

    progress.finish()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Assemble intervalEncyclopedia source volumes into a single master file."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("interval-encyclopedia-master.txt"),
        help="Master output file path.",
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
        default=16384,
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
        default=4800,
        help="Passed to generate-tempered-intervals.py when generating sources.",
    )
    parser.add_argument(
        "--historical-extra-json",
        type=Path,
        default=None,
        help="Optional JSON passed to generate-historical-intervals.py.",
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

    just_command = [
        str(args.python),
        str(just_script),
        "--max-harmonic",
        str(args.harmonic_limit),
        "--output",
        str(args.just_input),
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
        *forwarded_output_switches,
    ]

    historical_command = [
        str(args.python),
        str(historical_script),
        "--output",
        str(args.historical_input),
        *forwarded_output_switches,
    ]
    if args.historical_extra_json is not None:
        historical_command.extend(["--extra-json", str(args.historical_extra_json)])

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
    write_master(args.output, volumes, reporter=reporter)

    reporter.print_result(f"Wrote master tome to {args.output}")


if __name__ == "__main__":
    main()
