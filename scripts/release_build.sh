#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON:-python3}"
MASTER_SCRIPT="$ROOT_DIR/generate-master-encyclopedia.py"

PDF_STYLE_ARGS=(
  --paper-size 11x17
  --orientation landscape
  --overflow-policy abort
  --no-progress
  --check-rendering-conventions
)

echo "Regenerating chapter sources and master text..."
"$PYTHON_BIN" "$MASTER_SCRIPT" \
  --regenerate-all \
  --output "$ROOT_DIR/the-interval-encoclpaedia.txt" \
  --output-format txt \
  --no-progress \
  --check-rendering-conventions

echo "Building chapter-index PDF..."
"$PYTHON_BIN" "$MASTER_SCRIPT" \
  --skip-generation \
  --output "$ROOT_DIR/the-interval-encoclpaedia-11x17-landscape.pdf" \
  --output-format pdf \
  "${PDF_STYLE_ARGS[@]}"

echo "Building tuning PDF..."
"$PYTHON_BIN" "$MASTER_SCRIPT" \
  --skip-generation \
  --output "$ROOT_DIR/the-tuning-encyclopedia.pdf" \
  --output-format pdf \
  "${PDF_STYLE_ARGS[@]}"

echo "Release build complete."
