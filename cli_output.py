#!/usr/bin/env python3
"""
Shared CLI output controls for intervalEncyclopedia generators.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from typing import TextIO


VERBOSITY_CHOICES = ("quiet", "normal", "verbose", "debug")


@dataclass(frozen=True)
class OutputControls:
    verbosity: int
    progress_enabled: bool
    progress_width: int


class ProgressBar:
    def __init__(
        self,
        *,
        total: int,
        label: str,
        enabled: bool,
        width: int,
        stream: TextIO = sys.stderr,
        min_interval_seconds: float = 0.1,
    ) -> None:
        self.total = max(total, 1)
        self.label = label
        self.enabled = enabled
        self.width = max(width, 10)
        self.stream = stream
        self.min_interval_seconds = max(min_interval_seconds, 0.01)
        self.current = 0
        self._last_render = 0.0
        self._started = False
        self._finished = False

    def update(self, current: int) -> None:
        if self._finished:
            return
        self.current = max(0, min(current, self.total))
        if not self.enabled:
            return

        now = time.monotonic()
        if (
            self._started
            and self.current < self.total
            and (now - self._last_render) < self.min_interval_seconds
        ):
            return
        self._render(now)

    def advance(self, step: int = 1) -> None:
        self.update(self.current + step)

    def finish(self) -> None:
        if self._finished:
            return
        if self.current < self.total:
            self.update(self.total)
        elif self.enabled and not self._started:
            self._render(time.monotonic())
        if self.enabled and self._started:
            self.stream.write("\n")
            self.stream.flush()
        self._finished = True

    def _render(self, now: float) -> None:
        ratio = self.current / self.total
        filled = int(self.width * ratio)
        bar = ("#" * filled) + ("-" * (self.width - filled))
        line = (
            f"\r{self.label} [{bar}] {ratio * 100:6.2f}% "
            f"({self.current}/{self.total})"
        )
        self.stream.write(line)
        self.stream.flush()
        self._last_render = now
        self._started = True


class Reporter:
    def __init__(self, controls: OutputControls) -> None:
        self.controls = controls
        self.verbosity = controls.verbosity

    def info(self, message: str) -> None:
        if self.verbosity >= 1:
            print(message, file=sys.stderr)

    def verbose(self, message: str) -> None:
        if self.verbosity >= 2:
            print(message, file=sys.stderr)

    def debug(self, message: str) -> None:
        if self.verbosity >= 3:
            print(message, file=sys.stderr)

    def progress(self, *, total: int, label: str) -> ProgressBar:
        return ProgressBar(
            total=total,
            label=label,
            enabled=self.controls.progress_enabled and self.verbosity >= 1,
            width=self.controls.progress_width,
        )

    def print_result(self, message: str) -> None:
        if self.verbosity >= 1:
            print(message)


def add_output_control_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress informational output.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity level; repeat for more detail (for example: -vv).",
    )
    parser.add_argument(
        "--verbosity",
        choices=VERBOSITY_CHOICES,
        default=None,
        help="Explicit verbosity level (overrides --quiet/-v).",
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        help="Force-enable progress bars.",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable progress bars.",
    )
    parser.add_argument(
        "--progress-width",
        type=int,
        default=30,
        help="Progress bar width in characters (default: 30).",
    )


def validate_output_control_args(args: argparse.Namespace) -> None:
    if args.progress and args.no_progress:
        raise ValueError("Choose only one of --progress or --no-progress.")
    if args.progress_width < 10:
        raise ValueError("--progress-width must be >= 10.")


def create_output_controls(args: argparse.Namespace) -> OutputControls:
    verbosity_map = {"quiet": 0, "normal": 1, "verbose": 2, "debug": 3}
    if args.verbosity is not None:
        verbosity = verbosity_map[args.verbosity]
    elif args.quiet:
        verbosity = 0
    else:
        verbosity = min(3, 1 + int(args.verbose or 0))

    if args.no_progress:
        progress_enabled = False
    elif args.progress:
        progress_enabled = True
    else:
        progress_enabled = sys.stderr.isatty() and verbosity >= 1

    return OutputControls(
        verbosity=verbosity,
        progress_enabled=progress_enabled,
        progress_width=args.progress_width,
    )


def create_reporter(args: argparse.Namespace) -> Reporter:
    return Reporter(create_output_controls(args))
