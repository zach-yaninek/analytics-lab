"""Helpers shared by the replication notebooks in this folder.

Each notebook replicates one group of findings in the report's Results section:

1. With RERUN = True (the default), it copies the committed outputs (verification/outputs/) to a scratch folder and
   re-runs the analysis scripts there on IPA's files in data/raw/. Those files are gitignored, so only someone who has
   them can re-run. The scripts write into the scratch folder (IPA_OUTPUTS) and their private name tables into a
   scratch copy of data/private/ (IPA_PRIVATE), and high_ticket_machines.py skips its figures (IPA_SKIP_FIGURES), so
   nothing in the repository or in data/ changes. The scratch folders are deleted when the notebook's kernel exits.
2. It lists every file the re-run wrote and whether it matches the committed file of the same name.
3. It recomputes each number the report states from those tables and checks it against the report's text.

With RERUN = False, a notebook skips steps 1 and 2 and recomputes the numbers from the committed outputs.

The notebooks read only pseudonymous, aggregate tables. The raw files are read by the scripts, in a separate process,
so real names never enter the notebook.
"""
import atexit
import filecmp
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
VERIFICATION = ROOT / 'verification'
COMMITTED = VERIFICATION / 'outputs'
RAW = ROOT / 'data' / 'raw'
PRIVATE = ROOT / 'data' / 'private'
RAW_FILES = ('IPA_CaseHistory_Aug 2025-Aug2026.xlsx', 'IPA_Active_Equipment_list_2026-10-19.xlsx')
# JSON keys that hold run times or other run-to-run noise, ignored when comparing outputs
VOLATILE_KEYS = {'seconds', 'elapsed', 'elapsed_s', 'runtime', 'runtime_s', 'duration', 'duration_s', 'timestamp',
                 'generated', 'generated_at', 'run_at', 'time'}

# A script's own summary line ('67/67 checks pass', 'Done in 69 s: 154 checks passed, 0 failed.', ...)
SUMMARY = re.compile(r'checks? pass|^PASS\b|^Done\b', re.IGNORECASE)

_started = {}
_private = {}

# Show table cells in full, so the comparison table names every column or key that differs
pd.set_option('display.max_colwidth', None)


def raw_inputs_present():
    """True when IPA's case export and installed-base list are in data/raw/."""
    return all((RAW / name).exists() for name in RAW_FILES)


def outputs(rerun):
    """The folder the notebook reads its tables from.

    rerun=True: a fresh scratch copy of verification/outputs/ for the scripts to rewrite.
    rerun=False: the committed outputs themselves (nothing is re-run).
    """
    if not rerun:
        print('RERUN is False: reading the committed outputs in verification/outputs/.')
        return COMMITTED
    if not raw_inputs_present():
        raise FileNotFoundError("IPA's files are not in data/raw/. Set RERUN = False to use the committed outputs.")
    scratch = Path(tempfile.mkdtemp(prefix='ipa_outputs_'))
    shutil.copytree(COMMITTED, scratch, dirs_exist_ok=True)
    private = Path(tempfile.mkdtemp(prefix='ipa_private_'))
    if PRIVATE.exists():  # some scripts read private inputs (e.g. a hand-made review), so they get a copy
        shutil.copytree(PRIVATE, private, dirs_exist_ok=True)
    for folder in (scratch, private):
        atexit.register(shutil.rmtree, folder, ignore_errors=True)
    _private[str(scratch)] = private
    _started[str(scratch)] = time.time()
    print('RERUN is True: the scripts write into a scratch copy of verification/outputs/.')
    return scratch


def rerun(out, script, *args, timeout=7200):
    """Run a script on IPA's files, writing into `out`, and print its exit status and its own check summary.

    script: a file in verification/ ('followups.py'), or a path from the repository root
    ('viz/deliverables/build_electronics_cases.py').
    """
    if Path(out) == COMMITTED:
        raise ValueError('rerun() writes into a scratch copy only; call outputs(True) first.')
    path = ROOT / script if '/' in script else VERIFICATION / script
    env = dict(os.environ, IPA_OUTPUTS=str(out), IPA_PRIVATE=str(_private[str(out)]), IPA_SKIP_FIGURES='1',
               MPLBACKEND='Agg')
    start = time.time()
    proc = subprocess.run([sys.executable, '-I', str(path), *args], cwd=ROOT, env=env, capture_output=True, text=True,
                          timeout=timeout)
    print(f'{script} {" ".join(args)}'.strip() + f': exit status {proc.returncode}, {time.time() - start:.0f} s')
    summary = [line.strip() for line in proc.stdout.splitlines() if SUMMARY.search(line.strip())]
    for line in summary[-1:]:
        print('   ', line)
    if proc.returncode != 0:
        tail = '\n'.join((proc.stderr or proc.stdout).splitlines()[-20:])
        raise RuntimeError(f'{script} failed with exit status {proc.returncode}:\n{tail}')


def _strip_volatile(obj):
    if isinstance(obj, dict):
        return {k: _strip_volatile(v) for k, v in obj.items() if k not in VOLATILE_KEYS}
    if isinstance(obj, list):
        return [_strip_volatile(v) for v in obj]
    return obj


def _flatten(obj, prefix=''):
    """{'a': {'b': 1}} -> {'a.b': 1}, leaving out the run-time keys."""
    if isinstance(obj, dict):
        flat = {}
        for k, v in obj.items():
            if k not in VOLATILE_KEYS:
                flat.update(_flatten(v, f'{prefix}{k}.'))
        return flat
    return {prefix[:-1]: obj}


def _named(kind, names):
    """'DIFFERENT (columns a, b, c)': every column or key that differs."""
    return f"DIFFERENT ({kind} {', '.join(sorted(names))})"


def _same_values(fresh, committed):
    """'same values' when a file differs from the committed one only in formatting or run times; otherwise
    'DIFFERENT', naming the columns or keys that differ."""
    if fresh.suffix == '.csv':
        a, b = pd.read_csv(fresh), pd.read_csv(committed)
        if list(a.columns) != list(b.columns) or len(a) != len(b):
            return f'DIFFERENT ({len(a)} vs. {len(b)} rows; columns {"same" if list(a.columns) == list(b.columns) else "differ"})'
        cols = []
        for c in a.columns:
            x, y = a[c], b[c]
            if pd.api.types.is_numeric_dtype(x) and pd.api.types.is_numeric_dtype(y):
                same = np.isclose(x.to_numpy(float), y.to_numpy(float), rtol=1e-9, atol=1e-12, equal_nan=True).all()
            else:
                same = (x.isna() & y.isna() | (x.astype(str) == y.astype(str))).all()
            if not same:
                cols.append(c)
        return _named('column' if len(cols) == 1 else 'columns', cols) if cols else 'same values'
    if fresh.suffix == '.json':
        a, b = (json.loads(p.read_text()) for p in (fresh, committed))
        if a == b:
            return 'same values'
        fa, fb = _flatten(a), _flatten(b)
        keys = [k for k in set(fa) | set(fb) if fa.get(k, '<missing>') != fb.get(k, '<missing>')]
        return _named('key' if len(keys) == 1 else 'keys', keys) if keys else 'same values (run times differ)'
    return 'DIFFERENT'


def compare(out):
    """Every file the re-run wrote, and whether it matches the committed file of the same name."""
    if Path(out) == COMMITTED:
        print('Nothing was re-run (RERUN is False).')
        return None
    start = _started[str(out)]
    rows = []
    for path in sorted(Path(out).rglob('*')):
        if not path.is_file() or path.stat().st_mtime < start:
            continue
        rel = path.relative_to(out)
        committed = COMMITTED / rel
        if not committed.exists():
            status = 'not in the committed outputs'
        elif filecmp.cmp(path, committed, shallow=False):
            status = 'identical'
        else:
            status = _same_values(path, committed)
        rows.append({'file written by the re-run': str(rel), 'compared with the committed file': status})
    table = pd.DataFrame(rows)
    if table.empty:
        print('The re-run wrote no files.')
        return table
    counts = table['compared with the committed file'].str.split(' (', n=1, regex=False).str[0].value_counts()
    print(f'{len(table)} files written: ' + ', '.join(f'{n} {s}' for s, n in counts.items()) + '.')
    return table


def read_csv(out, name, **kw):
    """A table from the outputs folder, e.g. read_csv(OUT, 'fleet/fx_summary.csv')."""
    return pd.read_csv(Path(out) / name, **kw)


def read_json(out, name):
    return json.loads((Path(out) / name).read_text())


# Formatting, so a recomputed value can be compared with the report's text as printed
def num(x, nd=0):
    """3041 -> '3,041'; 0.4567, 2 -> '0.46'."""
    if isinstance(x, float) and math.isnan(x):
        return 'nan'
    return f'{x:,.{nd}f}'


def pct(share, nd=0):
    """0.4234 -> '42%'; 0.329, 1 -> '32.9%'."""
    return f'{100 * share:.{nd}f}%'


def span(lo, hi, nd=0):
    """(725, 837) -> '725–837'; (2.31, 4.84, 1) -> '2.3–4.8'."""
    return f'{lo:,.{nd}f}–{hi:,.{nd}f}'


def check(claims):
    """Compare recomputed values with the report.

    claims: (what the report says, the value as the report prints it, the recomputed value formatted the same way).
    Shows the table, then raises if any value differs.
    """
    table = pd.DataFrame(claims, columns=['Finding', 'Report', 'Recomputed'])
    table['Match'] = (table['Report'].astype(str) == table['Recomputed'].astype(str)).map({True: 'yes', False: 'NO'})
    try:
        from IPython.display import display
        display(table)
    except ImportError:
        print(table.to_string(index=False))
    bad = int((table['Match'] == 'NO').sum())
    if bad:
        raise AssertionError(f'{bad} of {len(table)} values differ from the report.')
    print(f'All {len(table)} values match the report.')
    return table
