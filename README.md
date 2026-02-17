# intervalEncyclopedia

`intervalEncyclopedia` is a generator-based reference project for building and typesetting **The Interval Encyclopedia**:

- Just intervals (octave-reduced) from bounded integer terms.
- Equal-tempered intervals up to high EDO values.
- Large historical/esoteric irrational interval corpus from multiple generator families.
- A stitched multi-volume master text file for downstream LaTeX or publishing workflows.

## Requirements

- Python 3.9+ (no third-party dependencies)

## Files

- `generate-just-intervals.py`
- `generate-tempered-intervals.py`
- `generate-historical-intervals.py`
- `generate-master-encyclopedia.py`

## Quick Start

Generate all three source volumes plus master:

```bash
python3 generate-master-encyclopedia.py \
  --regenerate-all \
  --max-harmonic 16384 \
  --max-edo 4800 \
  --output interval-encyclopedia-master.txt
```

## Script Usage

### Common output controls (all generators)

Each generator script supports the same output/progress switches:

- `-q`, `--quiet`: suppress informational output.
- `-v`, `--verbose`: increase verbosity (repeat, for example `-vv`).
- `--verbosity quiet|normal|verbose|debug`: explicit verbosity override.
- `--progress`: force-enable progress bars.
- `--no-progress`: disable progress bars.
- `--progress-width N`: progress bar width (minimum `10`, default `30`).

### 1) Just intervals

```bash
python3 generate-just-intervals.py --max-harmonic 16384 --output just-intervals.txt
```

Useful options:

- `--max-harmonic N`: include all harmonics up to `N` and use that as the integer-term bound (default `16384`).
- `--harmonic-limit N`: legacy alias for `--max-harmonic N`.
- `--max-prime N`: keep only rows whose largest prime factor is `<= N`.
- `--max-rows N`: write first `N` rows (preview/testing).
- `--precision N`: decimals for cent values (default `24`).

Output columns:

- `ratio`: reduced ratio in `[1/1, 2/1)`.
- `prime_factorization`: multiplicative prime form of the reduced ratio (for example `3 / 2`, `5 / 4`, `3 * 5 / 2^3`).
- `cents`: `1200 * log2(ratio)`.
- `largest_prime`: largest prime factor in numerator or denominator.
- `odd_limit`: `max(odd_part(numerator), odd_part(denominator))`.
- `common_name`: conventional interval names (`P4`, `P5`, etc.) and harmonic labels where applicable (example: `3/2 -> Perfect fifth (P5); 3rd harmonic`).

### 2) Equal tempered intervals

```bash
python3 generate-tempered-intervals.py --max-edo 4800 --output tempered-intervals.txt
```

Useful options:

- `--min-edo N`: lower EDO bound (default `1`).
- `--max-edo N`: upper EDO bound (default `4800`).
- `--exclude-unison`: omit step `0`.
- `--exclude-octave`: omit step `N`.
- `--precision N`: decimals for ratio and cent values (default `24`).

Output columns:

- `edo`
- `step`
- `interval_name` (for example `12th scale degree of 13-TET`)
- `ratio`
- `prime_factorization` (`1` for unison, `2` for octave, otherwise `-` for irrational ET steps)
- `cents`
- `expression` (for example `2^(7/12)`)

### 3) Historical and esoteric irrationals

```bash
python3 generate-historical-intervals.py --output historical-intervals.txt
```

Useful options:

- `--sort-by value|name|slug`
- `--precision N`: decimals for ratio and cent values (default `24`).
- `--extra-json path.json`: append custom interval entries.
- `--scribd-source path.tsv`: TSV source for Scribd "List of intervals" imports (default `sources/scribd-list-of-intervals.tsv`).
- `--exclude-scribd`: skip the built-in Scribd import.
- `--miraheze-source path.tsv`: TSV source for Microtonal Encyclopedia (Miraheze) imports (default `sources/microtonal-miraheze-missing-intervals.tsv`).
- `--exclude-miraheze`: skip the built-in Microtonal Encyclopedia (Miraheze) import.
- `--huygens-fokker-source path.tsv`: TSV source for Huygens-Fokker Bohlen-Pierce imports (default `sources/huygens-fokker-bpsite-intervals.tsv`).
- `--exclude-huygens-fokker`: skip the built-in Huygens-Fokker import.
- `--min-octave-edo N`, `--max-octave-edo N`: octave EDO sweep bounds (defaults `5..200`).
- `--min-tritave-edt N`, `--max-tritave-edt N`: tritave EDT sweep bounds (defaults `5..120`).
- `--min-consonance-divisions N`, `--max-consonance-divisions N`: equal-division bounds for `3/2`, `5/4`, and `7/6` families (defaults `5..120`).

Default behavior imports interval aliases from:

- `sources/scribd-list-of-intervals.tsv` (Scribd "List of intervals")
- `sources/microtonal-miraheze-missing-intervals.tsv` (Microtonal Encyclopedia / Miraheze)
- `sources/huygens-fokker-bpsite-intervals.tsv` (Huygens-Fokker Bohlen-Pierce interval tables)

Output columns:

- `slug`
- `name`
- `ratio`
- `prime_factorization` (computed for rows with explicit rational expressions, otherwise `-`)
- `cents`
- `expression`
- `tradition`
- `note`

`--extra-json` format example:

```json
[
  {
    "slug": "example_interval",
    "name": "Example Interval",
    "expression": "sqrt(7)/2",
    "value": 1.3228756555,
    "tradition": "custom",
    "note": "Added by user"
  }
]
```

### 4) Master tome assembler

```bash
python3 generate-master-encyclopedia.py \
  --regenerate-all \
  --max-harmonic 16384 \
  --max-edo 4800 \
  --output interval-encyclopedia-master.txt
```

Behavior:

- Generates missing source files automatically.
- With `--regenerate-all`, always rebuilds all sources first.
- With `--skip-generation`, fails if any source file is missing.
- Embeds explicit volume markers in master output:
  - `%%<VOLUME:JUST:BEGIN>` ... `%%<VOLUME:JUST:END>`
  - `%%<VOLUME:TEMPERED:BEGIN>` ... `%%<VOLUME:TEMPERED:END>`
  - `%%<VOLUME:HISTORICAL:BEGIN>` ... `%%<VOLUME:HISTORICAL:END>`

## Scale Notes

- A full just-interval run at `--harmonic-limit 16384` produces a very large corpus (tens of millions of rows).
- A full tempered run at `--max-edo 4800` produces **11,527,200 rows** (including unison and octave steps).

## Project Goal

This repository is designed to support iterative generation of a massive scholarly interval reference corpus that can later be transformed into structured LaTeX volumes.

### 5) Website table CSV (List of musical intervals)

```bash
python3 generate-musical-intervals-csv.py --output musical-intervals.csv
```

This exporter downloads the table captioned **"List of musical intervals"** from:

- [https://en.wikipedia.org/wiki/List_of_pitch_intervals](https://en.wikipedia.org/wiki/List_of_pitch_intervals)

It writes a CSV with the same table columns (for example: `Cents`, `Note (from C)`, `Freq. ratio`, `Prime factors`, `Interval name`, `TET`, `Limit`, `M`, `S`) and includes all table rows.
