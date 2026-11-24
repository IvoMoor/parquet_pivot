#!/usr/bin/env python3
"""
Parquet Pivot - updater (standard library only, so it also works while duckdb is being replaced).

  python update.py --auto
        Called by start-native.cmd before the engine starts. If "Install updates automatically" is
        switched on in the application, it installs a newer Parquet Pivot and/or DuckDB. Never fails the start.
  python update.py --apply app,duckdb --wait-pid <pid> -- <server.py options>
        Called by the engine when you press "Update" in the application: waits until the engine has
        exited, installs the updates, and starts the engine again.

What it contacts (no personal data is sent, only a generic User-Agent):
  raw.githubusercontent.com / github.com   the Parquet Pivot repository (app version, source zip)
  pypi.org                                 the newest published DuckDB version
"""
import argparse, io, json, os, re, shutil, subprocess, sys, time, urllib.error, urllib.request, zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = 'IvoMoor/parquet_pivot'
BRANCH = 'main'
RAW_APP = 'https://raw.githubusercontent.com/%s/%s/app.html' % (REPO, BRANCH)
ZIP_URL = 'https://github.com/%s/archive/refs/heads/%s.zip' % (REPO, BRANCH)
PYPI_URL = 'https://pypi.org/pypi/duckdb/json'
UA = 'ParquetPivot-updater'
META = re.compile(r'<meta\s+name="app-version"\s+content="([^"]+)"')


def settings_dir():
    base = os.environ.get('APPDATA') or os.path.join(os.path.expanduser('~'), '.config')
    return os.path.join(base, 'ParquetPivot')


def read_settings():
    try:
        with open(os.path.join(settings_dir(), 'settings.json'), 'r', encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def write_settings(d):
    os.makedirs(settings_dir(), exist_ok=True)
    p = os.path.join(settings_dir(), 'settings.json')
    with open(p + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(d, f, indent=1)
    os.replace(p + '.tmp', p)


def vkey(v):
    return tuple(int(x) for x in re.findall(r'\d+', str(v or ''))[:4])


def newer(latest, current):
    return bool(latest and current) and vkey(latest) > vkey(current)


def _get(url, headers=None, timeout=8):
    h = {'User-Agent': UA}
    h.update(headers or {})
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
        return r.read()


def local_app_version():
    try:
        with open(os.path.join(ROOT, 'app.html'), 'r', encoding='utf-8') as f:
            m = META.search(f.read(16384))
        return m.group(1) if m else None
    except Exception:
        return None


def latest_app_version(timeout=8):
    data = _get(RAW_APP, {'Range': 'bytes=0-16383'}, timeout=timeout)[:16384]  # only the top of the page, where the version is
    m = META.search(data.decode('utf-8', 'replace'))
    return m.group(1) if m else None


def installed_duckdb():
    try:
        from importlib.metadata import version
        return version('duckdb')
    except Exception:
        return None


def latest_duckdb(timeout=8):
    return json.loads(_get(PYPI_URL, timeout=timeout).decode('utf-8'))['info']['version']


def check(timeout=8):
    """Versions installed here and the newest published ones. Offline is normal, not an error:
    a part that cannot be reached gets error='offline' and the other parts are skipped quickly."""
    out = {'app': {'current': local_app_version(), 'latest': None, 'available': False, 'error': None},
           'duckdb': {'current': installed_duckdb(), 'latest': None, 'available': False, 'error': None}}
    offline = False
    for k, fn in (('app', latest_app_version), ('duckdb', latest_duckdb)):
        if offline:
            out[k]['error'] = 'offline'
            continue
        try:
            out[k]['latest'] = fn(timeout)
            if not out[k]['latest']:
                raise RuntimeError('version not found')
            out[k]['available'] = newer(out[k]['latest'], out[k]['current'])
        except (urllib.error.URLError, OSError):  # no connection, DNS, proxy, timeout ...
            offline = True
            out[k]['error'] = 'offline'
        except Exception as ex:
            out[k]['error'] = str(ex)[:200]
    return out


# ---------------------------------------------------------------- installing
def update_app(log):
    if os.path.isdir(os.path.join(ROOT, '.git')) and shutil.which('git'):
        log('Updating Parquet Pivot with git pull ...')
        r = subprocess.run(['git', '-C', ROOT, 'pull', '--ff-only'], capture_output=True, text=True)
        log((r.stdout + r.stderr).strip())
        if r.returncode != 0:
            raise RuntimeError('git pull failed (local changes?): ' + (r.stderr or r.stdout).strip()[:300])
        return
    log('Downloading the new Parquet Pivot ...')
    z = zipfile.ZipFile(io.BytesIO(_get(ZIP_URL, timeout=120)))
    root_real = os.path.realpath(ROOT)
    n = 0
    for info in z.infolist():
        if info.is_dir():
            continue
        rel = info.filename.split('/', 1)[1] if '/' in info.filename else ''
        if not rel or rel.startswith('.git'):
            continue
        dest = os.path.realpath(os.path.join(ROOT, rel))
        if not (dest == root_real or dest.startswith(root_real + os.sep)):
            continue  # never write outside this folder
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with z.open(info) as src, open(dest, 'wb') as dst:
            shutil.copyfileobj(src, dst)
        n += 1
    log('Updated %d files.' % n)


def update_duckdb(log):
    log('Updating DuckDB with pip ...')
    r = subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade', '--disable-pip-version-check', 'duckdb'],
                       capture_output=True, text=True)
    log((r.stdout + r.stderr).strip()[-600:])
    if r.returncode != 0:
        raise RuntimeError('pip failed: ' + (r.stderr or r.stdout).strip()[-300:])


def install(what, log):
    """Returns (ok, message)."""
    msgs, ok = [], True
    before = {'app': local_app_version(), 'duckdb': installed_duckdb()}
    for w in what:
        try:
            (update_app if w == 'app' else update_duckdb)(log)
        except Exception as ex:
            ok = False
            msgs.append('%s: %s' % ('Parquet Pivot' if w == 'app' else 'DuckDB', ex))
    after = {'app': local_app_version(), 'duckdb': installed_duckdb()}
    if ok:
        for w, nm in (('app', 'Parquet Pivot'), ('duckdb', 'DuckDB')):
            if w in what:
                msgs.append('%s %s → %s' % (nm, before[w] or '?', after[w] or '?'))
    return ok, '; '.join(msgs)


def wait_pid(pid, timeout=60):
    """Wait until the process has exited (no os.kill on Windows: it would terminate the process)."""
    if sys.platform == 'win32':
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x00100000, False, int(pid))  # SYNCHRONIZE
        if h:
            ctypes.windll.kernel32.WaitForSingleObject(h, int(timeout * 1000))
            ctypes.windll.kernel32.CloseHandle(h)
        return
    end = time.time() + timeout
    while time.time() < end:
        try:
            os.kill(int(pid), 0)
        except OSError:
            return
        time.sleep(0.3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--auto', action='store_true')
    ap.add_argument('--apply')
    ap.add_argument('--wait-pid')
    ap.add_argument('rest', nargs=argparse.REMAINDER)
    a = ap.parse_args()
    log = lambda m: print(m, flush=True) if m else None
    if a.auto:
        try:
            if not read_settings().get('autoUpdate'):
                return
            c = check(timeout=3)  # short: a start without internet must not be delayed
            what = [k for k in ('app', 'duckdb') if c[k]['available']]
            if what:
                log('Installing updates: ' + ', '.join(what))
                ok, msg = install(what, log)
                log(('Done: ' if ok else 'Update problem: ') + msg)
        except Exception as ex:  # an update problem must never keep the application from starting
            log('Automatic update skipped: %s' % ex)
        return
    if a.apply:
        if a.wait_pid:
            wait_pid(a.wait_pid)
        what = [w for w in a.apply.split(',') if w in ('app', 'duckdb')]
        log('Parquet Pivot is updating - please wait ...')
        ok, msg = install(what, log)
        try:
            os.makedirs(settings_dir(), exist_ok=True)
            with open(os.path.join(settings_dir(), 'update-result.json'), 'w', encoding='utf-8') as f:
                json.dump({'ok': ok, 'msg': msg, 't': time.time()}, f)
        except Exception:
            pass
        log(('Done: ' if ok else 'Update problem: ') + msg)
        rest = [x for x in a.rest if x != '--']
        os.chdir(ROOT)
        sys.exit(subprocess.call([sys.executable, os.path.join(ROOT, 'server.py')] + rest))
    ap.print_help()


if __name__ == '__main__':
    main()
