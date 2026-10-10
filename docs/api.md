# API reference

Base URL (local): `http://localhost:8000`. Interactive docs: `http://localhost:8000/docs`. Machine-readable spec: [`openapi.json`](openapi.json).

All errors use one shape:

```json
{ "error": { "code": "sheet_required", "message": "This workbook has several worksheets. Choose which one to analyse.", "details": { "sheets": ["Data", "Notes"] } } }
```

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Liveness check |
| GET | `/api/config` | Upload limits, data-retention statement, whether AI is available |
| GET | `/api/demo-datasets` | List the built-in synthetic datasets |
| POST | `/api/demo-datasets/{key}` | Load a demo dataset (`small-business`, `retail`, `workforce`) → `DatasetSummary` |
| POST | `/api/files/sheets` | Multipart `file` → worksheet names (empty list for CSV) |
| POST | `/api/datasets` | Multipart `file` (+ optional `sheet`) → `DatasetSummary` with a 50-row preview |
| GET | `/api/datasets/{id}` | Dataset summary |
| DELETE | `/api/datasets/{id}` | Remove the dataset from server memory |
| GET | `/api/datasets/{id}/preview?offset=0&limit=50` | Page through raw rows (max 200 per page) |
| GET | `/api/datasets/{id}/profile` | Column profiles, duplicate count, confirmed and potential issues |
| GET | `/api/datasets/{id}/analysis` | Numeric summaries, histograms, box plots, category frequencies, date ranges, correlation matrix and default charts |
| POST | `/api/datasets/{id}/explore/grouped` | `{category_column, value_column}` → per-group count/mean/median/sum/share |
| POST | `/api/datasets/{id}/explore/scatter` | `{x, y}` → up to 500 points and Pearson r |
| POST | `/api/datasets/{id}/explore/timeseries` | `{date_column, value_column?, agg: count\|sum\|mean, granularity: auto\|day\|week\|month\|quarter\|year}` |
| GET | `/api/datasets/{id}/findings` | Ranked findings with evidence, caveats and the ranking method |
| GET | `/api/datasets/{id}/report.html?download=true` | Self-contained HTML report (`download=false` opens it for printing to PDF) |
| GET | `/api/datasets/{id}/export/{table}.csv` | `column_profile`, `data_issues`, `findings`, `numeric_summary`, `category_frequencies`, `grouped_summary`, `time_series`, `correlations` |
| POST | `/api/datasets/{id}/ai-explanation` | `{consent: true}` → AI commentary (503 `ai_not_configured` unless enabled) |

## Common error codes

| HTTP | Code | Meaning |
|---|---|---|
| 413 | `file_too_large`, `too_many_rows`, `too_many_columns`, `too_many_cells` | Over a configured limit |
| 415 | `unsupported_file_type`, `unsupported_excel_format` | Not `.csv` / `.xlsx` |
| 422 | `empty_file`, `no_rows`, `malformed_csv`, `binary_file`, `invalid_excel_file`, `sheet_required`, `sheet_not_found` | File problems |
| 422 | `not_numeric`, `not_categorical`, `not_a_date_column`, `invalid_request`, `consent_required` | Bad request for this dataset |
| 404 | `dataset_not_found`, `column_not_found`, `demo_not_found`, `unknown_export`, `export_unavailable` | Missing resource (datasets expire) |
| 502/503 | `ai_unavailable`, `ai_error`, `ai_invalid_response`, `ai_not_configured` | Optional AI layer only; analysis is unaffected |
