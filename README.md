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
\operatorname{cents}(r) = 1200\log_2(r).
$$

Inverse mapping:

$$
r = 2^{\operatorname{cents}/1200}.
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
\max\big(\operatorname{odd}(n),\operatorname{odd}(d)\big),
$$
with $\operatorname{odd}(x)$ obtained by removing all powers of $2$ from $x$.

### Equal Temperament (EDO)

For $N$-EDO and scale degree $k$:

$$
r_{N,k} = 2^{k/N}, \quad c_{N,k} = 1200\frac{k}{N}.
$$

With defaults (`--min-edo 1 --max-edo 4800`, including unison and octave), row count is:

$$
\sum_{N=1}^{4800}(N+1) = \frac{4800(4800+3)}{2} = 11{,}527{,}200.
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
  --max-harmonic 16384 \
  --max-edo 4800 \
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

## Volume I: Just Intervals

Run:

```bash
python3 /Users/cleider/dev/intervalEncoclopedia/generate-just-intervals.py \
  --max-harmonic 16384 \
  --output /Users/cleider/dev/intervalEncoclopedia/just-intervals.txt
```

Main options:

- `--max-harmonic N` (alias `--harmonic-limit N`)
- `--max-prime N`
- `--max-rows N`
- `--precision N`
- `--output path`

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
  --max-edo 4800 \
  --output /Users/cleider/dev/intervalEncoclopedia/tempered-intervals.txt
```

Main options:

- `--min-edo N`
- `--max-edo N`
- `--exclude-unison`
- `--exclude-octave`
- `--precision N`
- `--output path`

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
- `--extra-json path.json`
- `--scribd-source path.tsv`, `--exclude-scribd`
- `--miraheze-source path.tsv`, `--exclude-miraheze`
- `--huygens-fokker-source path.tsv`, `--exclude-huygens-fokker`
- `--min-octave-edo N`, `--max-octave-edo N`
- `--min-tritave-edt N`, `--max-tritave-edt N`
- `--min-consonance-divisions N`, `--max-consonance-divisions N`

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
  --max-harmonic 16384 \
  --max-edo 4800 \
  --output /Users/cleider/dev/intervalEncoclopedia/interval-encyclopedia-master.txt
```

Behavior:

- regenerates all sources with `--regenerate-all`,
- can fail fast on missing sources with `--skip-generation`,
- writes volume markers:
  - `%%<VOLUME:JUST:BEGIN>` ... `%%<VOLUME:JUST:END>`
  - `%%<VOLUME:TEMPERED:BEGIN>` ... `%%<VOLUME:TEMPERED:END>`
  - `%%<VOLUME:HISTORICAL:BEGIN>` ... `%%<VOLUME:HISTORICAL:END>`

## Output Size and Growth

For current defaults:

- just rows: $40{,}799{,}669$
- tempered rows: $11{,}527{,}200$
- historical rows: $46{,}535$
- combined rows: $52{,}373{,}404$

Empirical growth intuition:

- just corpus scales approximately quadratically in harmonic bound $H$,
- tempered corpus scales quadratically in max EDO $N$ via $\Theta(N^2)$ from cumulative steps,
- historical corpus scales mostly with configured division ranges and imported source tables.

A heuristic for just intervals at large $H$ is:

$$
\#\text{rows}(H) \approx \frac{3}{2\pi^2}H^2,
$$

which matches the constrained Stern-Brocot region (ratio band $[1,2)$) times coprimality density.

## Data Integrity and Reproducibility

Each output includes header metadata:

- generation timestamp,
- effective bounds/flags,
- total row count.

This allows deterministic regeneration and simple downstream validation.

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
  /Users/cleider/dev/intervalEncoclopedia/generate-master-encyclopedia.py
```

## License / Attribution

Use your repository license terms for distribution. Source tables in `/Users/cleider/dev/intervalEncoclopedia/sources/` preserve provenance fields where available.
