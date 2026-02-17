# Code Reference

This document is the technical companion to `/Users/cleider/dev/intervalEncoclopedia/README.md`.

It describes implementation details, data flow, algorithms, complexity, and function-level behavior for:

- `/Users/cleider/dev/intervalEncoclopedia/cli_output.py`
- `/Users/cleider/dev/intervalEncoclopedia/generate-just-intervals.py`
- `/Users/cleider/dev/intervalEncoclopedia/generate-tempered-intervals.py`
- `/Users/cleider/dev/intervalEncoclopedia/generate-historical-intervals.py`
- `/Users/cleider/dev/intervalEncoclopedia/generate-master-encyclopedia.py`
- `/Users/cleider/dev/intervalEncoclopedia/generate-musical-intervals-csv.py`

## 1) Shared Output Layer (`cli_output.py`)

### Purpose

Centralize CLI UX behavior so every generator shares:

- consistent verbosity semantics,
- consistent progress bar controls,
- stable argument names and validation.

### Core Types

- `OutputControls(verbosity, progress_enabled, progress_width)`
- `ProgressBar(total, label, enabled, width, stream, min_interval_seconds)`
- `Reporter(controls)`

### Progress Computation

Progress bar fill ratio:

$$
\rho = \frac{\text{current}}{\text{total}}, \quad 0 \le \rho \le 1.
$$

Character fill count (`width = W`):

$$
\text{filled} = \lfloor W\rho \rfloor.
$$

Render throttling avoids excessive terminal writes with minimum render interval $\Delta t_{\min}$.

### Verbosity Mapping

`create_output_controls` maps semantic levels to numeric tiers:

$$
\text{quiet}=0,\ \text{normal}=1,\ \text{verbose}=2,\ \text{debug}=3.
$$

If no explicit `--verbosity` is set:

- `--quiet` forces $0$,
- otherwise base level is $1 + \#(-v)$ clipped to $3$.

### Public API Summary

- `add_output_control_args(parser)`
- `validate_output_control_args(args)`
- `create_output_controls(args)`
- `create_reporter(args)`

All generators call these functions during parse/validation/setup.

### Format inference pattern

Generator scripts that emit files expose `--output-format` and support `auto` inference from extension.

For output path $p$:

$$
\text{format}(p)=
\begin{cases}
\texttt{csv}, & p \text{ ends with } .\texttt{csv} \\
\texttt{json}, & p \text{ ends with } .\texttt{json} \\
\texttt{txt}, & \text{otherwise}
\end{cases}
$$

The musical table exporter uses the same pattern but defaults to `csv` when extension is not `.json`.

## 2) Just Intervals (`generate-just-intervals.py`)

### Goal

Generate all reduced rational intervals in the octave band:

$$
1 \le \frac{n}{d} < 2
$$

subject to:

$$
1 \le n,d \le H, \quad \gcd(n,d)=1
$$

where $H$ is `--max-harmonic` (alias `--harmonic-limit`).

### Mathematical Definitions

Cents:

$$
\operatorname{cents}\left(\frac{n}{d}\right)=1200\log_2\left(\frac{n}{d}\right).
$$

Largest prime factor metric:

$$
\operatorname{LP}(n,d)=\max(P(n),P(d)).
$$

Odd limit:

$$
\operatorname{odd\_limit}(n,d)=\max(\operatorname{odd}(n),\operatorname{odd}(d)).
$$

### Algorithmic Core

#### Stern-Brocot traversal

`generate_coprime_octave_reduced_ratios` performs iterative in-order traversal in the interval $[1/1,2/1)$ using mediants:

$$
\frac{a}{b} \oplus \frac{c}{d} = \frac{a+c}{b+d}.
$$

This yields sorted reduced fractions without storing the full set in memory.

#### Largest-prime-factor table

`build_largest_prime_factor_table(limit)` creates LPF lookup using sieve-like updates across multiples of each prime candidate.

This enables near-constant-time factorization step transitions in `integer_factorization`.

### Function-level Notes

- `reduced_harmonic_ratio(harmonic)`
  - maps harmonic $h/1$ to octave-reduced coprime ratio in $[1,2)$.
- `build_harmonic_label_table(max_harmonic)`
  - aggregates harmonic aliases (`3rd harmonic`, etc.) by reduced ratio key.
- `row_passes_prime_filter(...)`
  - enforces optional prime-limit criterion.
- `count_filtered_rows(...)`
  - pre-count pass used to initialize deterministic progress totals.
- `write_output(...)`
  - single streaming write pass with `txt`, `csv`, or `json` serialization.

### Output serializers

- text:
  metadata header plus tab-delimited rows.
- CSV:
  RFC4180-style rows through `csv.DictWriter`.
- JSON:
  envelope with `metadata`, `columns`, and `rows`.

### Complexity

Let $R(H)$ be number of generated rows at bound $H$.

- traversal and write are $\Theta(R(H))$,
- LPF table is approximately $O(H\log\log H)$ by sieve behavior,
- memory is dominated by LPF table and harmonic-label map.

## 3) Equal Tempered Intervals (`generate-tempered-intervals.py`)

### Goal

Enumerate equal-tempered steps across a configured EDO range.

For EDO $N$ and step $k$:

$$
r_{N,k}=2^{k/N}, \quad c_{N,k}=1200\frac{k}{N}.
$$

### Row domain

Per EDO $N$, the step range is:

- $k=0..N$ by default,
- $k=1..N$ if unison excluded,
- $k=0..N-1$ if octave excluded,
- $k=1..N-1$ if both excluded.

### Ordering policy

Default output order is global ratio sorting:

$$
r_1 \le r_2 \le \dots \le r_m,
$$

controlled by `--sort-by ratio` (default).  
Legacy grouped order remains available via `--sort-by edo-step`.

### Naming policy

`edo_interval_name(step, edo)` produces human labels, for example:

$$
2^{12/13} \mapsto \text{"12th scale degree of 13-TET"}.
$$

Special cases:

- step $0$: unison label,
- step $N$: octave label.

### Prime factorization policy

For this table:

- step $0 \Rightarrow 1$,
- step $N \Rightarrow 2$,
- all other steps are irrational and return `-`.

### Complexity

Total rows:

$$
\sum_{N=N_{\min}}^{N_{\max}} \#\text{steps}(N).
$$

With defaults and included endpoints:

$$
\sum_{N=1}^{96}(N+1)=4{,}752.
$$

Runtime is linear in row count; memory usage is streaming/constant aside from minimal buffers.

### Output serializers

`write_output(...)` supports `txt`, `csv`, and `json` with the same row schema:

- text: metadata header and tab-delimited rows,
- CSV: structured columns via `csv.DictWriter`,
- JSON: object with `metadata`, `columns`, and `rows`.

## 4) Historical and Esoteric Intervals (`generate-historical-intervals.py`)

### Goal

Build a mixed corpus combining:

- seeded mathematical constants,
- equal-division families (octave, tritave, consonant periods),
- Carlos scale families,
- source-imported named rational intervals,
- optional user additions from `.tsv`, `.csv`, or `.json`.

Final set is bounded to $[1,2]$ and deduplicated by slug.

Default generated-family ranges are intentionally moderate:

- octave EDO max: `64`,
- tritave EDT max: `32`,
- consonance-family max: `32`.

### Key Data Models

- `HistoricalInterval`
  - `slug`, `name`, `expression`, `value`, `tradition`, `note`,
    `subgroup_monzo`, `fjs_name`, `comma_size`, `xen_url`
- `Annotation`
  - family metadata templates for generated rows
- `CarlosScale`
  - cents-per-step definitions for alpha/beta/gamma families

### Family formulas

General equal division of period $P$:

$$
r_{P,N,k}=P^{k/N}, \quad k=1,\ldots,N-1.
$$

Implemented families:

- octave EDO ($P=2$),
- tritave EDT ($P=3$),
- ED(3/2), ED(5/4), ED(7/6).

Carlos progression for cents step $s$:

$$
r_m=2^{ms/1200}, \quad r_m<2.
$$

### Rational import normalization

Input sources use ratio tokens parsed as:

$$
\frac{p}{q}, \quad p,q \in \mathbb{Z}_{>0}.
$$

Then octave reduction enforces project range:

$$
r' = 2^k\frac{p}{q}, \quad 1 \le r' \le 2.
$$

### Prime factorization behavior

`interval_prime_factorization` attempts parse of `expression` into rational forms:

- exact `p/q`,
- exact integer,
- `p/q (from a/b)` reduced-origin notation.

If parsing fails (irrational expressions), output is `-`.

### Source readers

- `infer_source_format(path)`
- `load_ratio_name_records(path)` for `.tsv`, `.csv`, `.json`
- source-specific wrappers:
  - `read_scribd_interval_tsv(path)`
  - `read_miraheze_interval_tsv(path)`
  - `read_huygens_fokker_interval_tsv(path)`
  - `read_xenharmonic_wiki_interval_tsv(path)`

These readers preserve provenance fields in notes where present.  
Xenharmonic Wiki imports additionally carry optional metadata fields:
`subgroup_monzo`, `fjs_name`, `comma_size`, and `xen_url`.
Reference site: [Xenharmonic Wiki](https://en.xen.wiki/).

### Output serializers

`write_output(...)` supports:

- text with metadata header and tab-delimited rows,
- CSV with explicit column names,
- JSON with `metadata`, `columns`, and `rows`.

### Validation gates

- range validations for each generated family,
- source-file existence checks unless explicitly excluded,
- output-control consistency from shared CLI layer.

### Complexity

If generated-family row count is $G$ and imported-source row count is $S$:

- build and write are $\Theta(G+S)$,
- sorting adds $O((G+S)\log(G+S))$.

## 5) Master Assembly (`generate-master-encyclopedia.py`)

### Goal

Orchestrate source generation and produce the stitched master **The Interval Encoclpaedia** in text, data, or typeset-book formats.

### Pipeline

1. Parse args and validate.
2. Build child-command lists for three source generators.
3. Ensure/regen sources (`ensure_source`).
4. Read volumes and parse row totals from `txt`, `csv`, or `json`.
5. Serialize to the selected output format (`txt`, `csv`, `json`, `latex`, or `pdf`).

### Marker format

Each embedded section is wrapped:

$$
\texttt{\%\%<VOLUME:TAG:BEGIN>} \quad ... \quad \texttt{\%\%<VOLUME:TAG:END>}
$$

This enables deterministic extraction/re-splitting.

### Forwarded CLI controls

`build_forwarded_output_switches` forwards verbosity/progress controls from master script to child generator calls, ensuring consistent UX and logging behavior.

### Subprocess contract

`run_generator` captures stdout/stderr and raises a detailed `RuntimeError` on non-zero exit, including command and captured streams.

### Input and output formats

- input volumes:
  `read_volume(...)` auto-detects `.txt`, `.csv`, `.json`.
- output formats:
  - `write_master_txt(...)`: marker-based stitched tome,
  - `write_master_csv(...)`: one row per volume with embedded `content`,
  - `write_master_json(...)`: top-level metadata and per-volume objects,
  - `write_master_latex(...)`: page-numbered LaTeX book source,
  - `write_master_pdf(...)`: compiled, page-numbered PDF book via LaTeX engine.

`parse_total_rows_text`, `parse_total_rows_csv`, and `parse_total_rows_json` normalize total row extraction across source types.

### LaTeX and PDF rendering

LaTeX output is generated by `build_latex_document(...)` and includes:

- frontmatter and table of contents,
- volume index as a longtable,
- per-volume chapters with metadata and tabular rows,
- page numbering via `fancyhdr` (`\fancyfoot[C]{\thepage}` and plain-page override).

Page layout is configurable for LaTeX/PDF modes:

- preset size via `--paper-size` (`us-letter`, `us-legal`, `a4`, `11x17`, etc.),
- orientation via `--orientation portrait|landscape`,
- arbitrary dimensions via `--page-width` and `--page-height`,
- margin via `--page-margin`.

For volume tables, `ratio`, `prime_factorization`, and `expression` fields are parsed and rendered in math mode.  
Example transformation:

$$
\texttt{3^2 * 2^3 / 71}
\;\mapsto\;
\frac{3^{2}\cdot2^{3}}{71}.
$$

PDF output uses the same LaTeX document source and compiles with one of:

$$
\texttt{lualatex} \rightarrow \texttt{xelatex} \rightarrow \texttt{pdflatex}
$$

when `--latex-engine auto` is selected. The `--latex-runs` value controls compilation passes (default `2`).

Column alignment details:

- table columns are generated with proportional `p{...}` widths and tabcolsep-aware width adjustment,
- numeric fields use right-aligned cells,
- text and expression fields use ragged-right cells,
- alignment rules are applied consistently across volume tables and the volume index,
- longtable headers are repeated with consistent `booktabs` rules across page breaks,
- each data row uses a configurable row strut to prevent row collisions.

Advanced LaTeX/PDF table style controls are resolved into a `LatexTableStyle` object and applied in both `.tex` and `.pdf` output modes. Key controls include:

- typography and spacing:
  `--table-font-size`, `--table-fit-font-size`,
  `--table-tabcolsep-pt`, `--table-fit-tabcolsep-pt`,
  `--table-arraystretch`, `--table-extra-row-height-pt`, `--table-row-strut-ex`,
- width and fitting behavior:
  `--table-usable-width`, `--table-fit-usable-width`, `--table-min-column-width`,
  `--table-weight-text`, `--table-weight-math`, `--table-weight-numeric`, `--table-weight-other`,
  `--table-emergency-stretch-em`,
- wrapping and numeric formatting:
  `--table-break-long-tokens`, `--no-table-break-long-tokens`, `--table-break-chunk`,
  `--table-max-decimals`, `--table-trim-trailing-zeros`, `--no-table-trim-trailing-zeros`,
- optional table shading:
  `--table-zebra`, `--table-zebra-black-pct`,
  `--table-header-shade`, `--table-header-black-pct`.

## 6) Musical Interval Table Export (`generate-musical-intervals-csv.py`)

### Goal

Download the Wikipedia interval table and export it in machine-readable form.

### Parsing pipeline

1. `download_html(...)` fetches source page HTML.
2. `WikiTableParser` captures all `<table>` elements.
3. `find_target_table(...)` selects by caption substring.
4. `expand_rowspan_colspan(...)` normalizes rectangular grid.
5. `dedupe_headers(...)` stabilizes column names.
6. `build_records(...)` creates row dictionaries.

### Output serializers

- CSV:
  `write_csv(...)` with stable headers.
- JSON:
  `write_json(...)` with `metadata`, `columns`, and `rows`.

Supported output formats are `csv` and `json` via `--output-format` (`auto` by extension).

## 7) Data Schemas

### Just table

Columns:

1. `ratio`
2. `ratio_decimal`
3. `prime_factorization`
4. `cents`
5. `largest_prime`
6. `odd_limit`
7. `common_name`

### Tempered table

Columns:

1. `edo`
2. `step`
3. `interval_name`
4. `ratio`
5. `prime_factorization`
6. `cents`
7. `expression`

### Historical table

Columns:

1. `slug`
2. `name`
3. `ratio`
4. `prime_factorization`
5. `cents`
6. `expression`
7. `subgroup_monzo`
8. `fjs_name`
9. `comma_size`
10. `xen_url`
11. `tradition`
12. `note`

### Master CSV table

Columns:

1. `tag`
2. `title`
3. `source_file`
4. `source_format`
5. `total_rows`
6. `content`

### Master JSON object

Top-level keys:

1. `metadata`
2. `volumes`

Each `volumes[i]` contains:

1. `tag`
2. `title`
3. `source_file`
4. `source_format`
5. `total_rows`
6. `content`

### Master LaTeX/PDF structure

Document-level elements:

1. title page: `The Interval Encoclpaedia`,
2. table of contents,
3. volume index chapter,
4. one chapter per source volume with verbatim content blocks,
5. centered page numbers in the footer.

## 8) Determinism and Reproducibility

Each generated file includes a metadata header with parameters and total rows. Given identical script versions and arguments, row content is deterministic.

Caveat:

- timestamps (`generated_utc`) are expected to differ run-to-run.

## 9) Practical Extension Points

### Add a new historical source importer

1. Add parser support for `.tsv`, `.csv`, and/or `.json` rows.
2. Add parser arguments (`--new-source`, `--exclude-new-source`).
3. Integrate into `build_interval_corpus`.
4. Update validation and README/docs.

### Add a new generated family

1. Define `Annotation` fallback/landmarks.
2. Call `generate_equal_division_family` with period ratio and expression.
3. Update documentation and expected size behavior.

### Add a new output field

1. Implement field computation function.
2. Update header row and write format.
3. Keep backward compatibility considerations explicit in docs.

## 10) Verification Checklist

Minimum sanity checks after code changes:

```bash
python3 -m py_compile \
  /Users/cleider/dev/intervalEncoclopedia/cli_output.py \
  /Users/cleider/dev/intervalEncoclopedia/generate-just-intervals.py \
  /Users/cleider/dev/intervalEncoclopedia/generate-tempered-intervals.py \
  /Users/cleider/dev/intervalEncoclopedia/generate-historical-intervals.py \
  /Users/cleider/dev/intervalEncoclopedia/generate-master-encyclopedia.py \
  /Users/cleider/dev/intervalEncoclopedia/generate-musical-intervals-csv.py

python3 /Users/cleider/dev/intervalEncoclopedia/generate-master-encyclopedia.py \
  --regenerate-all \
  --max-harmonic 1024 \
  --max-edo 128 \
  --output /tmp/interval-encyclopedia-master-smoke.txt \
  --no-progress

python3 /Users/cleider/dev/intervalEncoclopedia/generate-master-encyclopedia.py \
  --regenerate-all \
  --output /tmp/interval-encyclopedia-master-smoke.json \
  --output-format json \
  --no-progress

python3 /Users/cleider/dev/intervalEncoclopedia/generate-master-encyclopedia.py \
  --skip-generation \
  --output /tmp/the-interval-encoclpaedia-smoke.pdf \
  --output-format pdf \
  --latex-engine auto \
  --latex-runs 2 \
  --pdf-keep-tex \
  --no-progress
```

The smoke profile keeps runtime manageable while exercising all major code paths.
