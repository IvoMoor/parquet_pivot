# Parquet Pivot

Excel-style PivotTable for Parquet files. Everything runs locally in the browser (DuckDB-WASM); data is never uploaded.

## Just use it
Double-click **app.html** (Chrome or Edge). Keep the `lib/` folder next to it.

## Install as an app (double-click `.parquet` files to open them here)
Browsers only allow installing / file associations from a secure origin, which `file://` is not. One-time setup:
1. Double-click **serve.cmd** (needs Python; it serves this folder on `http://localhost:8765`, local only).
   Any static host works too (IIS, nginx, an intranet site over https) - the app is just static files.
2. In Edge/Chrome open the page, then menu > Apps > *Install this site as an app*.
3. In Explorer: right-click a `.parquet` file > Open with > *Parquet Pivot* > Always.
After installing, the app is cached by its service worker and starts even when the server is not running.

## Sheets (tabs)
Excel-style tabs at the bottom: `+` new sheet, double-click to rename, right-click for Rename / Duplicate / Close,
or the **Duplicate** button. Each sheet has its own file(s) and layout. Opening a file when the current sheet already
has data opens it in a new sheet.

## Save View / Open View
*Save View* writes a `.ppview` file with all sheets (fields, filters, sort, layout, collapsed items, names) and the
names of the data files. *Open View* restores it; the app re-opens the files automatically when the browser still has
permission (installed app / Chrome-Edge file handles) and otherwise asks you to locate them once.

## Export
*Copy*: selection (Ctrl+C) or the entire PivotTable with headers (paste into Excel).
*Export*: Excel (.xlsx, formatted, merged headers, frozen panes) or CSV.

## Calculations
*Calculations > Calculated Field*: formulas on aggregated values, e.g. `[Sum of amount] / [Sum of qty]`, `SUM([amount]) * 0.21`,
`IF([Sum of amount] > 1000, 1, 0)` (SAP BW: calculated key figure).
*Calculations > Restricted Measure*: a field aggregated only where conditions hold, e.g. Sum of amount where region is North (restricted key figure).
Both show up in the field list under "Calculations" and are dragged into Values; double-click / right-click to edit.

## Conditional formatting
Highlight cell rules, hide rows, top/bottom N or %, data bars, color scales, icon sets - per measure, for values only, values + subtotals, or everything.
Rules are saved with the view; Excel export keeps fills / font colors (data bars and icons are screen-only).

## Hiding rows by value (Conditional Formatting > Hide Rows Rule)
Instead of colouring cells, a rule can *hide the rows* whose value meets a condition, e.g. hide countries whose row total of
"Sum of amount" is less than 1,000,000. Evaluate it on the row total, on any value in the row, or on every value in the row, for
detail rows only or also subtotal rows. Several rules combine (a row is hidden if any rule hides it).
It is always visible: an amber banner above the grid shows how many rows are hidden and lists the rules (click x to remove one),
and the Conditional Formatting button is highlighted.
Hidden rows are only removed from the display (and from copy/export); totals and subtotals still include them.

## Ribbon
The chevron at the right end (or Ctrl+F1) collapses the ribbon to a compact icon-only toolbar; every command stays available (hover for the name).

Rebuilding the DuckDB runtime in `lib/` (only to change versions): see `tools/build-lib.js`.


## Nested columns (STRUCT, LIST, MAP)
Columns that contain structures show a small arrow in the field list; open it to see every field inside (`addr.city`, `items[].sku`, `items[].tags[]`, `attrs[].key` ...). These fields can be used as rows, columns, filters and values like any other field. A list (`[]`) is expanded so that each list item becomes its own record when the field is used; records with an empty list stay as one (blank) record. Measures from outside the list are therefore repeated per item. The status bar says "list items expanded to rows" while this applies.

## More features
- **Field list**: drag the left edge of the pane to change its width and the bar above "Drag fields between areas" to change the height of the areas (double-click a bar to reset).
- **Sorting**: right-click a member > Sort, or the *Sort…* dialog (levels, "Then by", copy/move/delete level). A level can sort on member labels or on the values of a measure, optionally in one specific column. Right-click a value cell for Largest to Smallest / Smallest to Largest in that column.
- **Subtotals** are off by default. Right-click a member > *Add / Remove subtotal for <field>*, or Subtotals ▾ > Show Subtotals for all fields.
- **Filter from a member**: right-click a member > *Filter: include value* / *Filter: exclude value* (applied directly) or *Filter…* (opens the dialog). In the filter dialog, *Paste a list of values…* (or paste several lines into the search box) selects exactly those members; duplicates are removed.
- **Number format**: right-click a value cell > Number Format….
- **Copy a column**: right-click a column header (or the row-label header) > Copy entire column / Copy distinct values.
- **Settings** (ribbon): grid font size, totals first or last, and the text shown for empty values.

## Layout, selection and drag & drop
- Opening a Parquet file always starts with an empty pivot. Layouts come back only through **Save View / Open View**.
- **Ctrl+click / Ctrl+drag** selects several separate cell ranges. Right-click the members of one column to include or exclude all of them at once.
- **Drag fields onto the grid**: while you drag a field (or a chip) from the field list, drop zones for Filters, Rows, Columns and Values appear over the grid.
- **Tabular/outline form**: drag a dimension header to reorder it, drop it on the Filters/Columns/Values area of the field pane (or on the Filters zone) to move it, or drop it on the field list to remove it. Right-click a header for Move / Remove.
- **Expand all / Collapse to <field>** are in the context menu of row and column members and of the row-label header.
- **Settings**: default Report Layout, Subtotals, Grand Totals and Repeat Labels for new sheets (optionally also for the current sheet), banding (alternate rows/columns) and a subtle hover highlight.

## Filter dialog
Right-click a member > *Filter…* (or double-click a chip in the field pane, or drop a dimension on Filters). Choose the filter type – include/exclude values, a range or a pattern – and add members from the *Available members* list (either only those matching the other filters, or all members) to the *Current filter* list. Pattern types: contains, begins with, ends with, wildcard (`*`, `?`). Sorting lives in its own *Sort* dialog. Column headers show a small funnel / arrow when a filter or sort is active; hover a filter in the filter bar or the Filters area to see what it contains.
Dragging a field from Rows/Columns to Filters adds it to Filters (and opens the dialog) without removing it from Rows/Columns; dragging from Filters to Rows/Columns keeps the filter.
Selected cells: click the selected cell again, Ctrl+click a selected range, or press Esc to deselect.

## Native engine for huge files (optional)
The in-browser engine is capped at about 3 GB of memory. For very large Parquet files run the native DuckDB engine instead:

1. Install Python 3 once, then double-click **start-native.cmd** (it installs the `duckdb` package on first use). Options: `start-native.cmd --memory 48GB --threads 16`.
2. The browser opens http://127.0.0.1:8765/app.html. The status bar shows **Native engine • N threads**.
3. **Open Parquet** now shows a file browser of this computer: the files stay wherever they are (local disks, network shares) – no special folder, nothing is uploaded or copied. You can pick several files, type a path or glob (`D:\data\*.parquet`), or open all files of a folder.
4. Saved views remember the file path, so *Open View* reopens the data directly.
5. Dropped or double-clicked files do not reveal their location to a browser; the app then asks you to select the file in the file browser. For a Windows "Open with" on `.parquet`, choose `start-native.cmd`.

Without the server (double-click `app.html`, or `serve.cmd`) the app works exactly as before with the in-browser engine. Add `?engine=browser` to the address to force it.
The server listens on 127.0.0.1 only, requires a random token for every call and rejects foreign hosts/origins. Run `python server.py --help` for all options.

## Data Manager and SQL views

**Open Parquet** now opens the *Data Manager*:

- **Recent** – the files (and SQL views) you opened before, newest first. Click to select one or more, double-click to open one, ✕ removes an entry, **Clear history** empties the list. Only *references* are stored (path or name), never data.
- **Browse & favorites** (native engine) – folder browser with a *Favorite folders* sidebar. Open a folder and press **☆ Add to favorites**; favorites are one click away from then on. In the browser engine this tab is a plain "Choose files…" button, because a browser cannot list folders by itself.
- Native engine: history, favorites and SQL views are stored in `%APPDATA%\ParquetPivot\library.json` (survives other ports and browsers). Browser engine: stored in this browser (localStorage).

**Advanced → SQL Views** (ribbon): write a DuckDB SQL query over one or more Parquet files.
1. *Add files…* (picks from the Data Manager); every file gets an alias you use in the SQL, e.g. `SELECT s.*, c.region FROM sales s JOIN customers c ON c.id = s.customer_id`.
2. **Run preview** (Ctrl+Enter) shows the columns, types and the first 100 rows.
3. **Save** keeps the view in your library; **Save & open in PivotTable** uses the query result as the source of a new sheet. Nothing is copied – the query runs on the files when the pivot is calculated. Views are stored in saved workbook views (.ppview) too.

## Ribbon sections
- **Workbook**: *New* (sheet), *Import* / *Export* (a `.ppview` file), *Load* / *Save* (views and reports kept inside the application – only layouts are stored, never data; one sheet = view, several = report).
- **Data**: *Data Manager*, *Load Parquet / Excel / CSV / JSON*, *Create SQL View*, *Refresh*. CSV and JSON work in both engines; Excel (`.xlsx`) needs DuckDB's `excel` extension (native engine, downloaded once).
- **Layout**: report layout, subtotals, grand totals, repeat labels, show levels, field list. **Calculate & Format**, **Copy & Export**. *Settings* is the gear at the far right.
- Field list: right-click a field > *Add to Rows / Columns / Filters / Values*.
- SQL columns (Calculations > SQL Column) can force a type (text, whole/decimal number, date, …).
