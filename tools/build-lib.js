// Builds the offline DuckDB-WASM runtime into ../lib so app.html works from file:// (no server, no CDN).
//
// Prereqs (one-time, in any scratch folder):
//   npm pack @duckdb/duckdb-wasm@1.32.0   -> extract it, point DUCKDB_PKG at the extracted "package" folder
//   npm i apache-arrow@17.0.0 esbuild@0.19.12 --no-bin-links  -> point NODE_MODULES at that node_modules
// Usage:  set DUCKDB_PKG=...\package & set NODE_MODULES=...\node_modules & node tools\build-lib.js
var fs = require('fs'), path = require('path'), zlib = require('zlib');
var PKG = process.env.DUCKDB_PKG, NM = process.env.NODE_MODULES;
if (!PKG || !NM) { console.error('Set DUCKDB_PKG and NODE_MODULES'); process.exit(1); }
var esbuild = require(path.join(NM, 'esbuild'));
var out = path.join(__dirname, '..', 'lib');
if (!fs.existsSync(out)) fs.mkdirSync(out);
var dist = path.join(PKG, 'dist');

// 1) JS API (+ apache-arrow) as one classic script exposing global `duckdb`
esbuild.buildSync({
  stdin: { contents: "export * from " + JSON.stringify(path.join(dist, 'duckdb-browser.mjs').split(path.sep).join('/')) + ";", resolveDir: dist, loader: 'js' },
  bundle: true, format: 'iife', globalName: 'duckdb', platform: 'browser', minify: true,
  nodePaths: [NM], outfile: path.join(out, 'duckdb-api.js'), logLevel: 'info'
});

// 2) worker + wasm (gzipped) as base64 -> loadable through a plain <script> on file://
var worker = fs.readFileSync(path.join(dist, 'duckdb-browser-eh.worker.js'));
var wasm = zlib.gzipSync(fs.readFileSync(path.join(dist, 'duckdb-eh.wasm')), { level: 9 });
fs.writeFileSync(path.join(out, 'duckdb-assets.js'),
  'window.__DUCK_ASSETS={worker:"' + worker.toString('base64') + '",wasmGz:"' + wasm.toString('base64') + '"};');
console.log('done', fs.readdirSync(out).map(function (f) { return f + ' ' + fs.statSync(path.join(out, f)).size; }));
