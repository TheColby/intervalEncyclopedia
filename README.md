# intervalEncyclopedia

`intervalEncyclopedia` generates a large-scale, reproducible corpus of musical intervals across three major families:

1. just (rational) intervals,
2. equal-tempered intervals,
3. historical/esoteric interval systems (including irrational and non-octave families).

The repository is designed for both computational analysis and publication workflows (plain-text volumes and stitched master tome output).

## Why This Exists

Most interval references are either:

- musically practical but narrow (small catalogs), or
- mathematically broad but difficult to reproduce from code.

This project intentionally provides both scale and reproducibility:

- deterministic generation from explicit formulas,
- script-level control over limits and filters,
- machine-readable tabular outputs,
- provenance-aware source imports for named intervals.

## Mathematical Foundations

All generators treat an interval as a frequency ratio $r = f_2 / f_1$ with $r > 0$.

### Cents Mapping

Every ratio is mapped to cents by:

$$
\mathrm{cents}(r) = 1200\log_2(r).
$$

Inverse mapping:

$$
r = 2^{\mathrm{cents}/1200}.
$$

### Octave Reduction

For any positive ratio $r$, octave reduction to $[1,2)$ is:

$$
r' = 2^k r, \quad k \in \mathbb{Z}, \quad 1 \le r' < 2.
$$

Equivalent integer form for rational $r = p/q$ uses repeated factors of $2$ until the same bound is reached.

### Prime Factorization Column

For rational intervals $r = p/q$ (in lowest terms), the prime factorization column reports:

$$
r = \frac{\prod_i p_i^{a_i}}{\prod_j q_j^{b_j}}.
$$

For irrational expressions (for example $2^{7/12}$), factorization is undefined and represented with `-`.

### Just-Interval Constraints

For harmonic bound $H$, generated reduced ratios satisfy:

$$
1 \le \frac{n}{d} < 2, \quad 1 \le n,d \le H, \quad \gcd(n,d)=1.
$$

Useful measures exported per row:

- largest prime:
$$
\max\big(P(n),P(d)\big)
$$
where $P(x)$ is the largest prime factor of $x$,
- odd limit:
$$
\max\big(\mathrm{odd}(n),\mathrm{odd}(d)\big),
$$
with $\mathrm{odd}(x)$ obtained by removing all powers of $2$ from $x$.

### Equal Temperament (EDO)

For $N$-EDO and scale degree $k$:

$$
r_{N,k} = 2^{k/N}, \quad c_{N,k} = 1200\frac{k}{N}.
$$

With defaults (`--min-edo 1 --max-edo 96`, including unison and octave), row count is:

$$
\sum_{N=1}^{96}(N+1) = \frac{96(96+3)}{2} = 4{,}752.
$$

### Historical/Esoteric Families

Several families are generated as equal divisions of a period $P$:

$$
r_{P,N,k} = P^{k/N}, \quad k=1,\ldots,N-1.
$$

Used period values include:

- octave: $P=2$,
- tritave: $P=3$,
- consonant divisions: $P \in \{3/2, 5/4, 7/6\}$.

Carlos scales use fixed cents step $s$:

$$
r_m = 2^{ms/1200}, \quad m \in \mathbb{N}, \quad r_m < 2.
$$

## Repository Layout

- `/Users/cleider/dev/intervalEncoclopedia/generate-just-intervals.py`
- `/Users/cleider/dev/intervalEncoclopedia/generate-tempered-intervals.py`
- `/Users/cleider/dev/intervalEncoclopedia/generate-historical-intervals.py`
- `/Users/cleider/dev/intervalEncoclopedia/generate-master-encyclopedia.py`
- `/Users/cleider/dev/intervalEncoclopedia/generate-musical-intervals-csv.py`
- `/Users/cleider/dev/intervalEncoclopedia/cli_output.py`
- `/Users/cleider/dev/intervalEncoclopedia/sources/`

Detailed code-level reference:

- `/Users/cleider/dev/intervalEncoclopedia/docs/CODE_REFERENCE.md`

## Requirements

- Python 3.9+
- no third-party dependencies for core generators

## Quick Start

Generate all default volumes and assemble master output:

```bash
python3 /Users/cleider/dev/intervalEncoclopedia/generate-master-encyclopedia.py \
  --regenerate-all \
  --output /Users/cleider/dev/intervalEncoclopedia/interval-encyclopedia-master.txt
```

## Common CLI Output Controls

All generator scripts share:

- `-q`, `--quiet`
- `-v`, `--verbose` (repeatable)
- `--verbosity quiet|normal|verbose|debug`
- `--progress`
- `--no-progress`
- `--progress-width N`

## CSV and JSON I/O Support

All generator scripts now support explicit output-format selection plus extension-based auto detection.

- Use `--output-format auto` to infer from `--output` file extension.
- For the volume generators, `.txt`, `.csv`, and `.json` are supported output extensions.
- For the master script, `.txt`, `.csv`, `.json`, `.tex`, and `.pdf` are supported output extensions.
- For the musical table exporter, `.csv` and `.json` are supported output extensions.

I/O matrix:

- `generate-just-intervals.py`:
  outputs: `txt`, `csv`, `json`; inputs: parameter-driven generation.
- `generate-tempered-intervals.py`:
  outputs: `txt`, `csv`, `json`; inputs: parameter-driven generation.
- `generate-historical-intervals.py`:
  outputs: `txt`, `csv`, `json`; imported source inputs: `.tsv`, `.csv`, `.json`; extra interval input: `--extra-source` (`.tsv`, `.csv`, `.json`) plus legacy alias `--extra-json`.
- `generate-master-encyclopedia.py`:
  outputs: `txt`, `csv`, `json`, `latex`, `pdf`; source volume inputs: `.txt`, `.csv`, `.json`.
- `generate-musical-intervals-csv.py`:
  outputs: `csv`, `json`; inputs: HTML table from `--url`.

## Volume I: Just Intervals

Run:

```bash
python3 /Users/cleider/dev/intervalEncoclopedia/generate-just-intervals.py \
  --max-harmonic 320 \
  --output /Users/cleider/dev/intervalEncoclopedia/just-intervals.txt
```

Main options:

- `--max-harmonic N` (alias `--harmonic-limit N`)
- `--max-prime N`
- `--max-rows N`
- `--precision N`
- `--output path`
- `--output-format auto|txt|csv|json`

Output columns:

- `ratio`
- `prime_factorization`
- `cents`
- `largest_prime`
- `odd_limit`
- `common_name`

Algorithm notes:

- ordered Stern-Brocot traversal for reduced rationals,
- sieve-based largest-prime-factor table,
- optional prime-limit post-filter.

## Volume II: Equal Tempered Intervals

Run:

```bash
python3 /Users/cleider/dev/intervalEncoclopedia/generate-tempered-intervals.py \
  --min-edo 1 \
  --max-edo 96 \
  --output /Users/cleider/dev/intervalEncoclopedia/tempered-intervals.txt
```

Main options:

- `--min-edo N`
- `--max-edo N`
- `--exclude-unison`
- `--exclude-octave`
- `--precision N`
- `--output path`
- `--output-format auto|txt|csv|json`

Output columns:

- `edo`
- `step`
- `interval_name`
- `ratio`
- `prime_factorization`
- `cents`
- `expression`

Naming convention example:

$$
2^{12/13} \Rightarrow \text{"12th scale degree of 13-TET"}.
$$

## Volume III: Historical and Esoteric Intervals

Run:

```bash
python3 /Users/cleider/dev/intervalEncoclopedia/generate-historical-intervals.py \
  --output /Users/cleider/dev/intervalEncoclopedia/historical-intervals.txt
```

Main options:

- `--sort-by value|name|slug`
- `--precision N`
- `--output-format auto|txt|csv|json`
- `--extra-source path.{tsv,csv,json}` (legacy alias: `--extra-json path.json`)
- `--scribd-source path.{tsv,csv,json}`, `--exclude-scribd`
- `--miraheze-source path.{tsv,csv,json}`, `--exclude-miraheze`
- `--huygens-fokker-source path.{tsv,csv,json}`, `--exclude-huygens-fokker`
- `--min-octave-edo N`, `--max-octave-edo N`
- `--min-tritave-edt N`, `--max-tritave-edt N`
- `--min-consonance-divisions N`, `--max-consonance-divisions N`

Default generated-family maxima are `64` (octave EDO), `32` (tritave EDT), and `32` (consonance families).

Default source imports:

- `/Users/cleider/dev/intervalEncoclopedia/sources/scribd-list-of-intervals.tsv`
- `/Users/cleider/dev/intervalEncoclopedia/sources/microtonal-miraheze-missing-intervals.tsv`
- `/Users/cleider/dev/intervalEncoclopedia/sources/huygens-fokker-bpsite-intervals.tsv`

Output columns:

- `slug`
- `name`
- `ratio`
- `prime_factorization`
- `cents`
- `expression`
- `tradition`
- `note`

## Master Assembly

Run:

```bash
python3 /Users/cleider/dev/intervalEncoclopedia/generate-master-encyclopedia.py \
  --regenerate-all \
  --output /Users/cleider/dev/intervalEncoclopedia/the-tuning-encyclopedia.txt
```

Behavior:

- regenerates all sources with `--regenerate-all`,
- can fail fast on missing sources with `--skip-generation`,
- supports `--output-format auto|txt|csv|json|latex|pdf`,
- accepts mixed source formats for `--just-input`, `--tempered-input`, and `--historical-input` (`.txt`, `.csv`, `.json`),
- forwards `--historical-extra-source` to the historical generator (legacy alias: `--historical-extra-json`),
- supports PDF compile controls with `--latex-engine`, `--latex-runs`, and `--pdf-keep-tex`,
- supports page layout controls for LaTeX/PDF:
  `--paper-size`, `--orientation`, `--page-width`, `--page-height`, `--page-margin`,
- supports standard presets including `us-letter`, `us-legal`, `a4`, and `11x17` (plus `a3`, `a5`, `b5`, `executive`),
- allows arbitrary page sizes with `--page-width` and `--page-height` (unit required, e.g. `11in`, `279mm`),
- renders interval expressions mathematically in LaTeX/PDF output (for example prime factorizations and symbolic expressions are typeset as equations),
- uses aligned fixed-width LaTeX table columns for all volume/index tables in LaTeX/PDF output,
- writes volume markers only for text master output:
  `%%<VOLUME:JUST:BEGIN>` ... `%%<VOLUME:JUST:END>`,
  `%%<VOLUME:TEMPERED:BEGIN>` ... `%%<VOLUME:TEMPERED:END>`,
  `%%<VOLUME:HISTORICAL:BEGIN>` ... `%%<VOLUME:HISTORICAL:END>`.

Generate a page-numbered LaTeX book:

```bash
python3 /Users/cleider/dev/intervalEncoclopedia/generate-master-encyclopedia.py \
  --skip-generation \
  --output /Users/cleider/dev/intervalEncoclopedia/the-tuning-encyclopedia.tex \
  --output-format latex
```

Generate a page-numbered PDF book:

```bash
python3 /Users/cleider/dev/intervalEncoclopedia/generate-master-encyclopedia.py \
  --skip-generation \
  --output /Users/cleider/dev/intervalEncoclopedia/the-tuning-encyclopedia.pdf \
  --output-format pdf \
  --latex-engine auto \
  --latex-runs 2 \
  --pdf-keep-tex
```

Generate a landscape 11x17 PDF:

```bash
python3 /Users/cleider/dev/intervalEncoclopedia/generate-master-encyclopedia.py \
  --skip-generation \
  --output /Users/cleider/dev/intervalEncoclopedia/the-tuning-encyclopedia-11x17-landscape.pdf \
  --output-format pdf \
  --paper-size 11x17 \
  --orientation landscape
```

Generate a custom-size PDF (arbitrary page dimensions):

```bash
python3 /Users/cleider/dev/intervalEncoclopedia/generate-master-encyclopedia.py \
  --skip-generation \
  --output /Users/cleider/dev/intervalEncoclopedia/the-tuning-encyclopedia-custom.pdf \
  --output-format pdf \
  --page-width 14in \
  --page-height 8.5in \
  --orientation landscape \
  --page-margin 0.75in
```

## Musical Table Export

Run:

```bash
python3 /Users/cleider/dev/intervalEncoclopedia/generate-musical-intervals-csv.py \
  --url https://en.wikipedia.org/wiki/List_of_pitch_intervals \
  --output /Users/cleider/dev/intervalEncoclopedia/musical-intervals.json \
  --output-format auto
```

Main options:

- `--url URL`
- `--table-caption TEXT`
- `--output path`
- `--output-format auto|csv|json`
- `--timeout-seconds N`

## Output Size and Growth

For current defaults:

- just rows: $15{,}616$
- tempered rows: $4{,}752$
- historical rows: $4{,}516$
- combined rows: $24{,}884$

At approximately $50$ rows per printed page, the default profile is about:

$$
\frac{24{,}884}{50} \approx 498\ \text{pages}.
$$

Empirical growth intuition:

- just corpus scales approximately quadratically in harmonic bound $H$,
- tempered corpus scales quadratically in max EDO $N$ via $\Theta(N^2)$ from cumulative steps,
- historical corpus scales mostly with configured division ranges and imported source tables.

A heuristic for just intervals at large $H$ is:

$$
\#\text{rows}(H) \approx \frac{3}{2\pi^2}H^2,
$$

which matches the constrained Stern-Brocot region (ratio band $[1,2)$) times coprimality density.

For full-scale corpus generation, explicitly raise limits in each source volume, then assemble:

```bash
python3 /Users/cleider/dev/intervalEncoclopedia/generate-just-intervals.py \
  --max-harmonic 16384 \
  --output /Users/cleider/dev/intervalEncoclopedia/just-intervals-large.txt

python3 /Users/cleider/dev/intervalEncoclopedia/generate-tempered-intervals.py \
  --max-edo 4800 \
  --output /Users/cleider/dev/intervalEncoclopedia/tempered-intervals-large.txt

python3 /Users/cleider/dev/intervalEncoclopedia/generate-historical-intervals.py \
  --max-octave-edo 200 \
  --max-tritave-edt 120 \
  --max-consonance-divisions 120 \
  --output /Users/cleider/dev/intervalEncoclopedia/historical-intervals-large.txt

python3 /Users/cleider/dev/intervalEncoclopedia/generate-master-encyclopedia.py \
  --skip-generation \
  --just-input /Users/cleider/dev/intervalEncoclopedia/just-intervals-large.txt \
  --tempered-input /Users/cleider/dev/intervalEncoclopedia/tempered-intervals-large.txt \
  --historical-input /Users/cleider/dev/intervalEncoclopedia/historical-intervals-large.txt \
  --output /Users/cleider/dev/intervalEncoclopedia/interval-encyclopedia-master-large.txt
```

## Data Integrity and Reproducibility

Each text output includes header metadata:

- generation timestamp,
- effective bounds/flags,
- total row count.

This allows deterministic regeneration and simple downstream validation.

JSON outputs include a top-level `metadata` object and a `rows` array with schema fields in `columns`.

## Advanced Notes

### Rational vs Irrational Representation

- Rational rows are represented exactly for expression and factorization (using integer arithmetic / `Fraction` where needed).
- Irrational rows are represented numerically as floating-point ratios with configurable decimal precision.

### Sorting Semantics

Historical output can be sorted by:

- ratio value (`value`),
- lexical name (`name`),
- lexical slug (`slug`).

### Why Prime Factorization Is Sometimes `-`

For expressions like $2^{k/N}$ with $k \notin \{0,N\}$, the ratio is irrational in the reals, so integer prime factorization is not defined.

## Development Workflow

Format and validation shortcuts:

```bash
python3 -m py_compile \
  /Users/cleider/dev/intervalEncoclopedia/cli_output.py \
  /Users/cleider/dev/intervalEncoclopedia/generate-just-intervals.py \
  /Users/cleider/dev/intervalEncoclopedia/generate-tempered-intervals.py \
  /Users/cleider/dev/intervalEncoclopedia/generate-historical-intervals.py \
  /Users/cleider/dev/intervalEncoclopedia/generate-master-encyclopedia.py \
  /Users/cleider/dev/intervalEncoclopedia/generate-musical-intervals-csv.py
```

## License / Attribution

Use your repository license terms for distribution. Source tables in `/Users/cleider/dev/intervalEncoclopedia/sources/` preserve provenance fields where available.
