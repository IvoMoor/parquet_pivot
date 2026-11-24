# Parquet Pivot – usability review, missing features, deployment & confidentiality

Written from a read-through of the app as it is today (browser engine + optional native engine).
Statements like "not found" mean: I looked for it in the code and did not find it.

## 1. Usability: where Excel users will stumble

| # | Observation | Suggestion | Effort |
|---|---|---|---|
| 1 | **No Undo/Redo.** Excel users press Ctrl+Z after every mis-drop of a field. | Keep a history of the layout state (rows/cols/values/filters/cfg) and bind Ctrl+Z / Ctrl+Y plus two ribbon buttons. The layout is already one serialisable object, so snapshots are cheap. | S |
| 2 | **Show Values As has only 3 options** (% of grand / column / row total). | Add: % of parent row/column, difference from, % difference from, running total, rank, index. Needs a "base field/item" picker like Excel. | M |
| 3 | **Few aggregations.** Count, distinct count, sum, avg, min, max, stdev, var exist. | Add median, mode, first/last, product, quantiles (DuckDB has them for free). | S |
| 4 | **No grouping.** Excel users group dates (Years/Quarters/Months exist as derived fields) but also group numbers into bins and group arbitrary text items manually ("North+South = Domestic"). | Number binning (start/end/step) as a derived field; manual item groups stored in the layout and compiled to a CASE expression. | M |
| 5 | **No Slicers / Timelines.** They are the most visible Excel pivot feature for report consumers. | Slicer panel: button list for a field's members (multi-select with Ctrl), connected to the same filter state; timeline = range slider on a date field. Reuses the existing filter model. | M |
| 6 | **No charts (PivotChart).** | Start with a simple bar/line/pie from the visible grid (SVG/canvas, no library), "chart this selection" and an option to keep it docked below the grid. | M |
| 7 | **Filter dialog is powerful but heavy** for the common case ("pick 3 values"). | Add the Excel-style quick popup (search box + checkbox list + Select all) opened by the funnel/arrow; keep the current dialog as "More filters…". | S |
| 8 | **Top 10 only exists as conditional formatting**, and as display-only. | A real Top/Bottom N filter (by a value field, with "others" optional) in the filter dialog. | S |
| 9 | **No GETPIVOTDATA / referencing from Excel.** Copy-paste gives static values. | Keep as is for now; exporting to .xlsx already gives formatted values. Optionally "Export as live Excel pivot" is not feasible; document the limitation. | – |
| 10 | **Value Field Settings** is separate from Number Format and Show Values As in Excel terms. | Combine into one dialog with tabs "Summarize by" / "Show values as" / "Number format", like Excel. | S |
| 11 | **Calculated Item** (a calculated member inside a field) is missing; Calculated Field exists. | Lower priority; rarely used compared to calculated fields. | M |
| 12 | **Refresh / data-changed handling.** After a file changes on disk the pivot is stale. | "Refresh" button (exists in ribbon) should re-read file metadata and detect changes; show a "data changed on disk" hint. | S |
| 13 | **Big result sets are hard to explore**: no per-column search, no freeze of selected columns, no column auto-fit command. | Double-click on a column border = auto-fit (Excel muscle memory), Ctrl+F in the grid. | S |
| 14 | **Discoverability of advanced features** (SQL views, SQL filter, SQL column). | Keep them under "Advanced", add a one-line tooltip with an example, and a sample-query gallery inside the SQL editor (join, filter, aggregate, date bucket). | S |
| 15 | **Errors are raw DuckDB messages.** | Translate the five most common ones ("column not found", "type mismatch", "division by zero", "out of memory", "file not readable") into plain language, keep the raw text under "Details". | S |
| 16 | **Keyboard**: arrow keys / Ctrl+C work in the grid, but there is no Ctrl+Z, Ctrl+F, Alt+Down on a field button, F2 rename. | Add the common ones; list them in a "Keyboard shortcuts" help dialog. | S |
| 17 | **Accessibility/themes**: only light theme, fixed font sizes in dialogs. | Optional dark theme, larger UI zoom setting. | M |

Quick wins (all "S"): Undo/Redo, more aggregations, quick filter popup, Top N filter, tabbed Value Field Settings, auto-fit columns, friendlier errors, shortcuts list.

## 2. Missing pivot features (beyond usability)

- Show values as: see #2. Also **"Show items with no data"** (cross join of dimensions) and **"Show in outline form / repeat labels / blank row after each item"** (some exist).
- **Multiple value fields on rows** (values placed in the rows axis instead of columns).
- **Sort by custom list** (Mon, Tue, … / Low, Medium, High): store a list per field.
- **Drill-down to detail** exists (Show Details, first 1,000 records). Add "export all details" and column selection.
- **Pivot from several sheets / data model**: relationships between files (join keys) so one pivot spans sales + customers without writing SQL. The SQL view covers this for experts; a "relationships" dialog with two dropdowns would cover it for everyone.
- **Parameters / what-if**: named parameters (e.g. FX rate) usable in calculated fields and SQL columns.
- **Scheduled/refreshable reports**: open a `.ppview` and have it re-run against a newer file with the same schema (works today by re-opening; make it explicit with a "Re-point to another file" command).
- **Print / PDF** of the pivot with repeating headers.

## 3. Data sources beyond Parquet

DuckDB already reads most of these; the work is UI + packaging.

| Source | Engine support | Notes |
|---|---|---|
| **CSV / TSV / JSON / NDJSON** | built in, both engines | Highest value. Needs a type-detection preview step (delimiter, header, date format, decimal separator) because Excel users have messy CSVs. |
| **Excel (.xlsx)** | DuckDB `excel` extension (`read_xlsx`) | **Not built in.** The extension is normally downloaded from extensions.duckdb.org on first use, which breaks offline use and the "nothing leaves the machine" story. Ship the extension file(s) inside `lib/` and load them from there (DuckDB supports a local extension repository / `LOAD '<path>'`) so no network is needed. Sheet and range picker in the Data Manager. |
| **Multiple files / folders / globs** | built in | `read_parquet('folder/*.parquet', hive_partitioning=true)`; add "Open folder as one table" and partitioned datasets. |
| **SQLite / DuckDB database files** | `sqlite`/native `.duckdb` attach | Native engine only; useful for local analysts. |
| **Remote files (https, S3, Azure, GCS)** | `httpfs` extension | Data would flow *to* the laptop only; the pivot still runs locally. Make it opt-in, off in the "locked-down" configuration (see §5), and bundle the extension the same way. Credentials must live in the OS keychain/browser memory, never in a `.ppview`. |
| **Databases (Postgres, MySQL, …)** | extensions, native engine | Later; adds credential handling and "query pushdown" questions. |
| **Arrow IPC / Feather, Excel-style clipboard paste** | possible | Paste-from-clipboard as a table is a very Excel-like entry point. |

Recommended order: CSV → folders/globs → Excel (with bundled extension) → remote (opt-in).

## 4. Collaboration without moving data

Because data must never leave the client, collaboration has to be about **definitions, not data**:

1. **Share the view, not the data.** A `.ppview` already contains only layout + file names/paths (no data). Add a "View library" folder (network share, SharePoint-synced folder, Git repo) the app can open from and save to; versioned by file name + timestamp. Zero server needed.
2. **Shared SQL views and favourite folders**: export/import of the library (`library.json`) so a team can distribute standard joins and standard data locations.
3. **"Data contract" check**: a `.ppview` stores the expected columns and types; on opening it warns if the file has different columns (typical when a colleague's file differs).
4. **Comments/annotations on a view** stored inside the `.ppview` (text only).
5. **Snapshot export**: PDF/xlsx of the result is the way to share *numbers*; label it clearly as leaving the app, and optionally add a configurable disclaimer/watermark and a "minimum group size" (suppress cells with fewer than N records) for confidential data.
6. Real-time co-editing would need a server that sees at least layout state; it is possible (WebRTC peer-to-peer, no server holding data) but is the most complex item and I would not start there.

## 5. Deployment and confidentiality (the key architecture decision)

There are two engines, and they behave very differently on a VM:

| | Browser engine (DuckDB-WASM) | Native engine (`server.py`) |
|---|---|---|
| Where the data is read | in the **user's browser**, from files chosen on the user's laptop | by the **server process**, from the disk of the machine where it runs |
| Fit for "VM serves the app, data stays on the laptop" | **Yes** | **No** – on a VM it would read the *VM's* disk, so the user would first have to copy data there. Use it only when the server runs on the user's own laptop. |
| Limits | ~3–4 GB of memory in the tab, single thread unless cross-origin isolated | all cores, spills to disk |

Therefore the supported setups should be:

**A. End-user laptop (simplest, strongest guarantee).** A zip with `app.html`, `lib/`, `serve.cmd`/`start-native.cmd`. Nothing is installed on a server; the page talks only to `127.0.0.1`. For non-technical users: a signed installer (or a single `.exe` built with PyInstaller around `server.py` + duckdb) so no Python is needed. Today `start-native.cmd` needs Python and `pip install duckdb` (internet) – that is the biggest deployment obstacle.

**B. Static app on a VM / intranet web server, data stays on the client.** Serve only static files (`app.html`, `lib/`, `sw.js`, `manifest.json`); no application code runs on the VM. The browser engine reads local files through the File System Access API. To make the "data never leaves the laptop" claim *verifiable* and not just a promise:
   - Serve over **HTTPS** (also required for service worker, install-as-app, file handles).
   - Send a strict **Content-Security-Policy** that forbids all outbound connections from the page: `default-src 'self'; connect-src 'self'; img-src 'self' data:; script-src 'self' 'wasm-unsafe-eval'; frame-ancestors 'none'; form-action 'none'`. Even a bug or a malicious dependency cannot post data elsewhere. Auditors can read this one header.
   - Add **COOP/COEP headers** (`same-origin` / `require-corp`) so DuckDB-WASM can use threads (faster) – still no data leaves.
   - **No third-party requests at all** (fonts, CDNs, telemetry): everything is already in `lib/`; keep it that way and add a self-test page that lists every network request the app made (should be zero except its own files).
   - **No server-side storage**: in this mode the library (history, favourites, saved SQL) lives in browser storage; make sure the native `/api/lib` is not exposed. Offer export/import of the library for backup.
   - Make browser-engine memory limits visible (a gauge and a "file too large for the browser engine – use the local engine" message).
   - Optional **"locked-down" flag** (config or URL) that disables everything that could fetch from outside: remote files, extension downloads, `INSTALL`. The SQL editor currently accepts SELECT-like statements only; also block `read_*` on URLs and `ATTACH`/`COPY … TO` in that mode so a pasted query cannot read or write unexpected places.

**C. Windows virtual desktop (VDI/Citrix) where the user's laptop drives is mapped.** Works with A or B; the files are still on the laptop but the process runs on the VDI – confirm with security that "mapped drive" counts as "leaving the laptop"; if not, only option B in the laptop's browser qualifies.

### Security hardening checklist (native engine)
- Already: 127.0.0.1 only, random token, Host/Origin checks. Add: refuse to start with `--host 0.0.0.0` unless an explicit flag is given; log nothing about data; delete temp spill files on exit; optional restriction of browsable roots (allow-list of folders) so the file browser cannot walk the whole disk; disable `COPY … TO`, `ATTACH`, `INSTALL`, `LOAD` and `read_*` of URLs in the SQL editor by default (DuckDB `enable_external_access=false` after opening the permitted files is the robust way).
- Library file (`%APPDATA%\ParquetPivot\library.json`) contains file paths (can be sensitive): document it, offer "clear history on exit".
- Sign the executables / the zip and publish a hash so IT can whitelist it.

## 6. Suggested roadmap

1. **Now (small, high impact):** Undo/Redo, more aggregations, quick filter popup, Top N filter, tabbed Value Field Settings, auto-fit, friendlier errors.
2. **Data:** CSV/JSON import with preview, folders/globs, Excel via bundled extension.
3. **Excel parity:** Show Values As (full), slicers/timelines, number/text grouping, custom sort lists, PivotChart.
4. **Deployment:** CSP + COOP/COEP static hosting recipe (nginx/IIS snippet), self-test page, single-file Windows launcher without Python, locked-down mode.
5. **Collaboration:** view library folder, library export/import, data-contract check, comments inside `.ppview`.
6. **Later:** relationships between files, parameters, remote sources (opt-in), print/PDF.
