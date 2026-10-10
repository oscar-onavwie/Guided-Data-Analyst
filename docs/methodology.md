# How the analysis works

Everything below is implemented in deterministic Python (`backend/app/`). The same input always gives the same output. No AI is involved in any calculation.

## 1. Reading the file (`parsing.py`)

- Files are parsed **in memory**; nothing is written to disk by the app.
- CSV: decoded as UTF-8 (with or without BOM), falling back to Windows-1252. The delimiter (`,` `;` tab `|`) is detected automatically.
- XLSX: opened with `openpyxl` in read-only, `data_only` mode. Formula cells give their **last saved value**; formulas and macros are never executed. `.xls`, `.xlsm` and `.xlsb` are rejected with a message explaining how to convert them.
- Every cell is read **as text first**. Leading/trailing spaces are trimmed and counted.
- These values mean *missing* (case-insensitive): blank, `NA`, `N/A`, `null`, `none`, `nan`, `#N/A`, `-`, `--`. **`0` is never treated as missing, and missing is never treated as `0`.**
- The first non-blank row is the header. Blank headers become `column_N`; duplicates become `name (2)`. Completely blank rows and completely empty unnamed columns are removed. **Every one of these changes is reported** to the user.
- Limits (configurable): file size, rows, columns and total cells. A ZIP-bomb guard rejects workbooks that expand beyond 400 MB.

## 2. Type inference (`inference.py`)

For each column, in order:

| Type | Rule |
|---|---|
| empty | no values |
| boolean | only true/false/yes/no/y/n |
| numeric | ≥ 95% of values parse as numbers after removing `£ $ € ¥`, thousands separators (`1,234`), a trailing `%`, and reading `(12)` as −12 |
| datetime | values look like dates **and** ≥ 95% parse with one consistent format (or a documented mix) |
| text | > 90% unique and more than 20 distinct values (free text, codes) |
| categorical | everything else |

Values that do not fit the chosen type are **invalid**: counted, shown as examples, and excluded from calculations.

**Dates.** Formats are tried in a fixed order; day-first comes before month-first, so `03/04/2025` is **3 April** (UK). If *every* value is ambiguous, a potential issue says so. Values with a time-zone offset are converted to UTC. Dates outside 1677–2262 (pandas' range) are treated as invalid.

**Roles.** `identifier` (name like `id`, `*_id`, `ref`, `code`, or values counting 1, 2, 3 …), `date`, `measure` (numeric to analyse), `dimension` (category to group by). Identifiers are never summed or averaged.

## 3. Profile and data quality (`profiling.py`)

- **Duplicate rows**: rows identical in every column to an earlier row (the first copy is not counted). Counted, **never removed**.
- **Constant columns**: one distinct value in all non-missing rows.
- **Confirmed issues** (objectively true): missing values, invalid values, duplicates, constant columns, renamed headers, empty columns.
- **Potential issues** (investigate): outliers, negative values in a mostly-positive measure (≤ 10% negative), labels differing only by case/spacing (`North`/`north`), placeholder labels (`Unknown`, `TBC`), sentinel numbers at the edge of the range (`999`, `-1`), future dates, pre-1900 dates, ambiguous or mixed date formats, trimmed whitespace.

## 4. Statistics (`analysis.py`)

| Statistic | Method |
|---|---|
| Mean, median, min, max, sum | over valid values only; `count` reports how many were used |
| Standard deviation | sample SD (n − 1), same as Excel `STDEV.S`; not shown for n < 2 |
| Quartiles | linear interpolation, same as Excel `QUARTILE.INC` |
| Potential outliers | Tukey's fences: below Q1 − 1.5×IQR or above Q3 + 1.5×IQR; "extreme" beyond 3×IQR. Not applied when IQR = 0 |
| Histogram | equal-width bins, Sturges' rule (⌈log₂n⌉ + 1), between 5 and 20 bins |
| Category frequencies | % of non-missing values; top 10 plus an "Other" bucket |
| Time series | automatic period: ≤ 45 days → day, ≤ 180 → week (Mon–Sun), ≤ 4 years → month, ≤ 12 → quarter, else year. Empty periods are **gaps** (no value), not zeros. The first/last period is flagged *partial* if the data does not cover all of it |
| Correlation | Pearson's r on rows where both values exist; only with ≥ 10 such rows and neither column constant. Strength: \|r\| ≥ 0.7 strong, ≥ 0.4 moderate |
| Group comparison | count, mean, median, sum per group. **Share of total only when every value ≥ 0** (negatives make shares meaningless) |
| Scatter | up to 500 points; larger datasets use a fixed-seed random sample so the chart is reproducible |

All divisions go through `safe_div`, which returns "not available" instead of failing on a zero denominator.

## 5. Findings (`findings.py`)

Each rule fires only when its threshold is met. Every finding carries a title, description, the evidence (value **and** how it was calculated), columns, period, *why it may matter* (interpretation, labelled as such), a caveat and a follow-up question.

`score = weight(kind) × magnitude × 100`

| Kind | Weight | Fires when | Magnitude |
|---|---|---|---|
| trend | 0.9 | average of the last third of complete periods differs from the first third by ≥ 20% (needs ≥ 4 complete periods and a positive base; partial periods excluded) | min(1, \|change\|) |
| concentration | 0.8 | one category ≥ 40% of the total, or ≤ 20% of categories hold ≥ 80% (≥ 3 categories, ≥ 10 rows) | top share |
| missing_data | 0.7 | a column is ≥ 20% missing | min(1, % / 60) |
| group_difference | 0.7 | highest vs lowest group average differ by ≥ 0.8 overall SDs (groups with ≥ 5 values) | min(1, SDs / 2) |
| correlation | 0.6 | \|r\| ≥ 0.5 with ≥ 10 pairs | \|r\| |
| duplicates | 0.6 | ≥ 1% of rows are duplicates | min(1, % / 10) |
| outliers | 0.5 | values beyond the fences make up ≤ 10% of the column | 0.6 if any extreme, else 0.3 |
| negative_values | 0.4 | ≤ 10% of a measure is negative | 0.5 |

Language rules: correlations are *associations*; unusual values are *potential outliers*; no finding claims a cause (a test enforces this). If nothing passes a threshold, the app says so rather than inventing insights.

## 6. Report (`reports.py`)

The HTML report is rendered with Jinja2 (auto-escaping on) from the same objects the app displays, with static SVG charts so it works offline as a single file. It is served with a strict Content-Security-Policy (no scripts). CSV exports prefix text cells starting with `=`, `+`, `-` or `@` with `'` to prevent spreadsheet formula injection; numbers, including negatives, are untouched.
