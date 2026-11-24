#!/usr/bin/env python3
"""
Parquet Pivot - optional native engine.

Runs DuckDB natively (64-bit, all CPU cores, spills to disk) and serves app.html on
http://127.0.0.1:<port>/ . The page detects the engine automatically and uses it instead of
the in-browser engine, so there is no 3 GB limit.  Parquet files are read from wherever they
are on this computer (or a network share) - nothing is copied or uploaded.

    python server.py                       start and open the browser
    python server.py "D:\\data\\sales.parquet"   ...and open that file straight away
    python server.py --memory 48GB --threads 16 --port 8765 --no-browser

Needs:  pip install duckdb
Security: listens on 127.0.0.1 only, every API call needs a random token that is handed to the
page by this server, and requests with a foreign Host/Origin header are rejected.
"""
import argparse, datetime, decimal, json, math, mimetypes, os, secrets, subprocess, sys, tempfile, threading, uuid
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import duckdb
except ImportError:
    sys.exit("The 'duckdb' package is missing.  Install it with:  python -m pip install duckdb")

ROOT = os.path.dirname(os.path.abspath(__file__))
TOKEN = secrets.token_urlsafe(24)
LOCK = threading.Lock()
CON = None
MAX_BODY = 32 * 1024 * 1024
STATIC_OK = ('app.html', 'manifest.json', 'sw.js', 'icon-192.png', 'icon-512.png')


def conv(v):
    """Make a DuckDB value JSON-safe."""
    if v is None or isinstance(v, (str, bool)):
        return v
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return None if (math.isnan(v) or math.isinf(v)) else v
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (datetime.datetime,)):
        return v.isoformat(sep=' ')
    if isinstance(v, (datetime.date, datetime.time)):
        return v.isoformat()
    if isinstance(v, datetime.timedelta):
        return str(v)
    if isinstance(v, (bytes, bytearray, memoryview)):
        return bytes(v).hex()
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, (list, tuple)):
        return [conv(x) for x in v]
    if isinstance(v, dict):
        return {str(k): conv(x) for k, x in v.items()}
    return str(v)


def run_sql(sql):
    with LOCK:
        cur = CON.execute(sql)
        if cur.description is None:
            return {"cols": [], "rows": []}
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    return {"cols": cols, "rows": [[conv(x) for x in r] for r in rows]}


_PICK_CODE = r"""
import sys, json
import tkinter as tk
from tkinter import filedialog
a = json.loads(sys.argv[1])
root = tk.Tk(); root.withdraw()
try:
    root.attributes('-topmost', True)
except Exception:
    pass
types = [('Data files', ' '.join('*' + e for e in a['exts'])), ('All files', '*.*')] if a['exts'] else [('All files', '*.*')]
if a['multiple']:
    r = filedialog.askopenfilenames(title=a['title'], filetypes=types)
else:
    r = filedialog.askopenfilename(title=a['title'], filetypes=types)
if isinstance(r, str):
    r = [r] if r else []
print(json.dumps(list(r)))
"""


def pick_files(title, exts, multiple):
    """Shows the operating system's own 'open file' dialog on this computer and returns the chosen paths."""
    arg = json.dumps({"title": str(title or 'Select file')[:200], "exts": [str(e) for e in (exts or [])][:20], "multiple": bool(multiple)})
    out = subprocess.run([sys.executable, '-c', _PICK_CODE, arg], capture_output=True, text=True, timeout=900)
    if out.returncode != 0 or not out.stdout.strip():
        raise RuntimeError("The file dialog is not available on this computer.")
    paths = json.loads(out.stdout.strip().splitlines()[-1])
    res = []
    for pth in paths:
        try:
            size = os.path.getsize(pth)
        except OSError:
            size = 0
        res.append({"path": os.path.normpath(pth), "name": os.path.basename(pth), "size": size})
    return {"files": res}


_SAVE_CODE = r"""
import sys, json
import tkinter as tk
from tkinter import filedialog
a = json.loads(sys.argv[1])
root = tk.Tk(); root.withdraw()
try:
    root.attributes('-topmost', True)
except Exception:
    pass
r = filedialog.asksaveasfilename(title=a['title'], initialfile=a['name'], defaultextension=a['ext'], filetypes=[('*' + a['ext'], '*' + a['ext']), ('All files', '*.*')])
print(json.dumps(r or ''))
"""


def save_dialog(title, name, ext):
    """Shows the operating system's own 'save as' dialog on this computer and returns the chosen path ('' = cancelled)."""
    arg = json.dumps({"title": str(title or 'Save')[:200], "name": str(name or '')[:200], "ext": str(ext or '')[:12]})
    out = subprocess.run([sys.executable, '-c', _SAVE_CODE, arg], capture_output=True, text=True, timeout=900)
    if out.returncode != 0 or not out.stdout.strip():
        raise RuntimeError("The file dialog is not available on this computer.")
    pth = json.loads(out.stdout.strip().splitlines()[-1])
    return {"path": os.path.normpath(pth) if pth else ""}


def decimal_sep():
    """Decimal separator of the user's regional settings (what Excel uses unless it is overridden in its own options)."""
    try:
        if os.name == 'nt':
            import ctypes
            buf = ctypes.create_unicode_buffer(16)
            if ctypes.windll.kernel32.GetLocaleInfoEx(None, 0x0E, buf, 16) > 0 and buf.value:  # LOCALE_SDECIMAL, user default
                return buf.value
        import locale
        locale.setlocale(locale.LC_NUMERIC, '')
        return locale.localeconv().get('decimal_point') or '.'
    except Exception:
        return None


def list_dir(path):
    """Folders and parquet files in a directory (or the drives / roots when path is empty)."""
    places = []
    home = os.path.expanduser('~')
    for label, p in (('Home', home), ('Desktop', os.path.join(home, 'Desktop')),
                     ('Documents', os.path.join(home, 'Documents')), ('Downloads', os.path.join(home, 'Downloads'))):
        if os.path.isdir(p):
            places.append({"name": label, "path": p})
    if not path:
        roots = []
        if os.name == 'nt':
            import string
            for L in string.ascii_uppercase:
                d = L + ':\\'
                if os.path.exists(d):
                    roots.append({"name": d, "dir": True, "size": 0})
        else:
            roots.append({"name": '/', "dir": True, "size": 0})
        return {"path": "", "parent": None, "sep": os.sep, "entries": roots, "places": places}
    path = os.path.abspath(path)
    if not os.path.isdir(path):
        raise ValueError("Not a folder: " + path)
    entries = []
    with os.scandir(path) as it:
        for e in it:
            try:
                if e.is_dir():
                    entries.append({"name": e.name, "dir": True, "size": 0})
                elif e.name.lower().endswith(('.parquet', '.pq', '.csv', '.tsv', '.txt', '.json', '.jsonl', '.ndjson', '.xlsx')) and not e.name.startswith('~$'):
                    st = e.stat()
                    entries.append({"name": e.name, "dir": False, "size": st.st_size, "mtime": st.st_mtime})
            except OSError:
                pass
            if len(entries) > 20000:
                break
    entries.sort(key=lambda x: (not x["dir"], x["name"].lower()))
    parent = os.path.dirname(path)
    if parent == path:
        parent = ""
    return {"path": path, "parent": parent, "sep": os.sep, "entries": entries, "places": places}


def lib_path():
    base = os.environ.get('APPDATA') or os.path.join(os.path.expanduser('~'), '.config')
    return os.path.join(base, 'ParquetPivot', 'library.json')


def lib_read():
    try:
        with open(lib_path(), 'r', encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def lib_write(d):
    if not isinstance(d, dict):
        raise ValueError("Library must be an object")
    p = lib_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


class Handler(BaseHTTPRequestHandler):
    server_version = "ParquetPivot/1"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    # ---- helpers
    def _host_ok(self):
        host = (self.headers.get('Host') or '').split(':')[0].lower()
        if host not in ('127.0.0.1', 'localhost', '[::1]'):
            return False
        org = self.headers.get('Origin')
        if org:
            o = urllib.parse.urlparse(org)
            if (o.hostname or '').lower() not in ('127.0.0.1', 'localhost', '::1'):
                return False
        return True

    def _send(self, code, body, ctype='application/json; charset=utf-8', extra=None):
        if isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, separators=(',', ':'), allow_nan=False))

    def _authed(self):
        return secrets.compare_digest(self.headers.get('X-PP-Token') or '', TOKEN)

    # ---- GET
    def do_GET(self):
        if not self._host_ok():
            return self._send(403, 'Forbidden', 'text/plain')
        u = urllib.parse.urlparse(self.path)
        p = urllib.parse.unquote(u.path)
        if p.startswith('/api/'):
            if not self._authed():
                return self._json(401, {"error": "Not authorised"})
            try:
                if p == '/api/info':
                    with LOCK:
                        threads = int(CON.execute("select current_setting('threads')").fetchone()[0])
                        mem = str(CON.execute("select current_setting('memory_limit')").fetchone()[0])
                    return self._json(200, {"version": duckdb.__version__, "threads": threads, "memory": mem, "platform": sys.platform, "decimal": decimal_sep()})
                if p == '/api/lib':
                    return self._json(200, lib_read())
                if p == '/api/ls':
                    q = urllib.parse.parse_qs(u.query)
                    return self._json(200, list_dir((q.get('path') or [''])[0]))
            except Exception as ex:  # noqa
                return self._json(400, {"error": str(ex)})
            return self._json(404, {"error": "Unknown call"})
        if p in ('/', ''):
            p = '/app.html'
        rel = p.lstrip('/')
        ok = rel in STATIC_OK or (rel.startswith('lib/') and rel.endswith('.js') and '..' not in rel)
        full = os.path.realpath(os.path.join(ROOT, rel))
        if not ok or not full.startswith(ROOT) or not os.path.isfile(full):
            return self._send(404, 'Not found', 'text/plain')
        with open(full, 'rb') as f:
            data = f.read()
        ctype = mimetypes.guess_type(full)[0] or 'application/octet-stream'
        if rel.endswith('.js'):
            ctype = 'text/javascript'
        if rel == 'manifest.json':
            ctype = 'application/manifest+json'
        if rel == 'app.html':
            html = data.decode('utf-8')
            tag = '<script>window.__PP_NATIVE={token:%s};</script>\n' % json.dumps(TOKEN)
            i = html.find('<script')
            html = html[:i] + tag + html[i:] if i >= 0 else tag + html
            data = html.encode('utf-8')
            ctype = 'text/html; charset=utf-8'
        self._send(200, data, ctype)

    # ---- POST
    def do_POST(self):
        if not self._host_ok():
            return self._send(403, 'Forbidden', 'text/plain')
        if not self.path.startswith('/api/') or not self._authed():
            return self._json(401, {"error": "Not authorised"})
        try:
            n = int(self.headers.get('Content-Length') or 0)
            if n > MAX_BODY:
                return self._json(413, {"error": "Request too large"})
            body = json.loads(self.rfile.read(n) or b'{}')
            if self.path in ('/api/query', '/api/exec'):
                return self._json(200, run_sql(str(body.get('sql', ''))))
            if self.path == '/api/lib':
                lib_write(body)
                return self._json(200, {"ok": True})
            if self.path == '/api/pick':
                return self._json(200, pick_files(body.get('title'), body.get('exts'), body.get('multiple')))
            if self.path == '/api/saveas':
                return self._json(200, save_dialog(body.get('title'), body.get('name'), body.get('ext')))
            if self.path == '/api/cancel':
                try:
                    CON.interrupt()
                except Exception:
                    pass
                return self._json(200, {"ok": True})
        except duckdb.Error as ex:
            return self._json(400, {"error": str(ex)})
        except Exception as ex:  # noqa
            return self._json(400, {"error": str(ex)})
        return self._json(404, {"error": "Unknown call"})


def main():
    global CON
    ap = argparse.ArgumentParser(description="Parquet Pivot native engine")
    ap.add_argument('files', nargs='*', help='Parquet files to open in the browser right away')
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--memory', help='DuckDB memory limit, e.g. 24GB (default: 80%% of the RAM)')
    ap.add_argument('--threads', type=int, help='number of worker threads (default: all cores)')
    ap.add_argument('--no-browser', action='store_true')
    a = ap.parse_args()

    CON = duckdb.connect(':memory:')
    CON.execute("SET preserve_insertion_order=false")
    tmp = os.path.join(tempfile.gettempdir(), 'parquet_pivot_spill')
    os.makedirs(tmp, exist_ok=True)
    CON.execute("SET temp_directory='%s'" % tmp.replace("'", "''"))
    if a.memory:
        CON.execute("SET memory_limit='%s'" % a.memory.replace("'", ""))
    if a.threads:
        CON.execute("SET threads=%d" % a.threads)

    srv = None
    for port in range(a.port, a.port + 25):
        try:
            srv = ThreadingHTTPServer(('127.0.0.1', port), Handler)
            break
        except OSError:
            continue
    if srv is None:
        sys.exit("No free port found near %d." % a.port)
    srv.daemon_threads = True
    url = 'http://127.0.0.1:%d/app.html' % port
    if a.files:
        url += '?' + '&'.join('open=' + urllib.parse.quote(os.path.abspath(f), safe='') for f in a.files)
    info = CON.execute("select current_setting('threads'), current_setting('memory_limit')").fetchone()
    print("Parquet Pivot native engine  (DuckDB %s, %s threads, memory limit %s)" % (duckdb.__version__, info[0], info[1]))
    print("Open  %s" % url)
    print("Close this window (or press Ctrl+C) to stop the engine.")
    if not a.no_browser:
        import webbrowser
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
