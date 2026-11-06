# Third-party licences

Files under `raw/` are third-party works redistributed under their own licences. Each directory keeps its upstream licence file, which governs those files. sd-forge's own licence (Apache-2.0, see `LICENSE`) does not apply to them.

| Directory | Upstream | Licence | Copyright holder (from its LICENSE) | Files |
|---|---|---|---|---|
| `raw/bptk-py/` | https://github.com/transentis/bptk_py | MIT | transentis labs GmbH (2024) | 79 |
| `raw/pysd/` | https://github.com/SDXorg/pysd | MIT | PySD contributors (2013-2022) | 26 |
| `raw/readsdr/` | https://github.com/jandraor/readsdr | MIT | Jair Andrade (2019) | 7 |
| `raw/sdeverywhere/` | https://github.com/climateinteractive/SDEverywhere | MIT | Todd Fincannon and Climate Interactive / New Venture Fund (2016-2024) | 201 |
| `raw/sdmr/` | https://github.com/JimDuggan/SDMR | MIT | Jim Duggan (2016) | 48 |
| `raw/simlin-stdlib/` | https://github.com/bpowers/simlin | Apache-2.0 | Bobby Powers (per AUTHORS) | 10 |
| `raw/test-models/` | https://github.com/SDXorg/test-models | MIT | The test-models Authors (2015) | 489 |

Total: 860 files.

Notes:

- Rows with `pointer:` in `MANIFEST.csv` are references only; nothing is copied. Projects that were removed from the repository for licence or provenance reasons are listed there as pointers.
- If you believe a file under `raw/` is yours and was not licensed for redistribution, open an issue and it will be removed.

## Build-time tools and dependencies, not redistributed

| Tool | Use | Licence |
|---|---|---|
| marked 12.0.2, mermaid 10.9.1 | PDF generation (`engine/docs_pdfs.js`, loaded from a CDN at build time) | MIT (each package's `package.json`) |
| Playwright (with Chromium) | browser tests and PDF/screenshot generation (`engine/docs_pdfs.js`, `engine/tests/`), installed by the user | Apache-2.0 |
| pysd 3.14.3, pytest 9.2.0 | Python dependencies (`engine/requirements.txt`), installed by the user | MIT |
| networkx 3.7, numpy 2.5.4, pandas 3.1.0, scipy 1.18.1 | Python dependencies, installed by the user | BSD-3-Clause (numpy and scipy wheels also bundle libraries under their own permissive licences) |
| xarray 2026.9.0 | Python dependency, installed by the user | Apache-2.0 |
| matplotlib 3.11.2 | Python dependency, installed by the user | matplotlib licence (PSF-based, permissive) |
