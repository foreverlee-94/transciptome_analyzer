# Lung Metadata Explorer

A tool that reads metadata out of large local single-cell h5ad datasets and
turns it into a static HTML report you can search, sort, and filter in a
browser.

## Data it covers

| Collection | Path (configurable, see below) | Files | Notes |
|---|---|---|---|
| CZI CELLxGENE Lung datasets | `CZI_LUNG_DATA_DIR` (default: `D:\CZI-CellXGene-Lung-datasets`) | 120 h5ad files | Standard CELLxGENE schema (disease/tissue/assay/cell_type, etc.) |
| Tahoe-100M drug-perturbation screen | `TAHOE_DATA_DIR` (default: `D:\tahoe-100m-dataset`) | 14 plate h5ad files | 50 cell lines × drug screening (drug/cell_line/plate, etc.) |

The two collections have completely different schemas, so the report keeps
them in separate tabs.

## Pointing this at your own data

The dataset paths are **not hardcoded** — they're read from environment
variables, with the paths above only used as fallback defaults if the
variables aren't set. Point the tool at your own copies of these datasets
(or a different drive/folder layout) like this:

```bash
# bash / Git Bash
export CZI_LUNG_DATA_DIR="/d/my-czi-lung-datasets"
export TAHOE_DATA_DIR="/d/my-tahoe-100m-dataset"
uv run python main.py
```

```powershell
# PowerShell
$env:CZI_LUNG_DATA_DIR = "D:\my-czi-lung-datasets"
$env:TAHOE_DATA_DIR = "D:\my-tahoe-100m-dataset"
uv run python main.py
```

Only one of the two collections is required — if a directory doesn't exist,
that collection is simply reported as empty (0 datasets) instead of failing
the whole run.

## Core design: never read the expression matrix

h5ad is an HDF5 container. This project opens the file with `h5py` and reads
only the lightweight parts of `obs`/`var`/`uns` (category lists, scalar
values, shape attributes) — it never touches the expression matrix (`X`,
`raw.X`) or per-cell arrays like `BARCODE`, which can have billions of
elements. As a result, metadata extraction finishes in 0.02–0.3 seconds per
file even for datasets larger than 45GB (up to 300GB+).

## Usage

```bash
uv sync                 # install dependencies (h5py)
uv run python main.py   # extract metadata.json + build report.html
```

Open the generated `report.html` in a browser. The data is embedded directly
in the HTML so it works offline, with no CDN or network dependency.

- `extract_metadata.py`: scans both collections and writes `metadata.json`.
- `generate_report.py`: reads `metadata.json` and builds `report.html` (tabbed UI).

## Report contents

### CZI CELLxGENE Lung tab
- Summary stats, a search box, dropdown filters for disease/assay/organism, a sortable table
- Click a row to open a detail modal (full cell type list, tissue, sex, developmental stage, citation, etc.)

The disease/condition filter uses the real `obs_disease` values read from
inside each h5ad file, not the value parsed from the filename. Some source
filenames are truncated (e.g. `small-cell-lung-carc`), which used to leak
empty/truncated fragments into the filter — reading the actual data avoids
that entirely.

### Tahoe-100M tab
- A per-plate (file) table: cell count, gene count, drug count, cell line count, sample (well) count, QC pass rate, etc.
- **A cell-line reference table.** Every Tahoe-100M plate pools the same 50 cell lines, so a plate-level "tissue" filter can never actually narrow anything down. Instead, this report builds a separate cell-line-level table enriched with the official tissue-of-origin/disease annotation looked up from [Cellosaurus](https://www.cellosaurus.org), so filtering by "tissue origin = lung" actually works (15 of the 50 cell lines are lung-derived).

## References

- CZI CELLxGENE Discover: https://cellxgene.cziscience.com
- Tahoe-100M: a drug-perturbation single-cell screen from Vevo Therapeutics / Parse Biosciences
- Cellosaurus: https://www.cellosaurus.org
