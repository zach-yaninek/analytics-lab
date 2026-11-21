"""Publishing a run: tables, schema, manifest, charts, report and email text, after every check and the privacy scan.

Everything is first written to a private temporary folder outside OUTPUT_DIR (a OneDrive- or SharePoint-synced
OUTPUT_DIR would otherwise upload files before they are scanned). Only when the privacy scan passes are the files
copied, in a fixed order with os.replace and retries (Excel and OneDrive lock files), into OUTPUT_DIR/runs/<run_id>/
with manifest.json last. Then OUTPUT_DIR/latest/ is replaced as a whole: the run is copied to latest.new/ beside it
and the folders are swapped by renaming, so a locked file leaves latest/ as it was (E30) and latest/ never mixes two
runs; its manifest.json is copied in last. A back-run (LATEST_PERIOD) leaves latest/ alone. A failed run writes only
failed/<stamp>/error.txt (code, stage and exit code; see record_failure). Rerunning the same inputs with the same
parameters reproduces the same run_id and files.
"""
import datetime as dt
import hashlib
import json
import os
import platform
import re
import shutil
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import __version__, METHOD_VERSION
from . import privacy as PRIV
from .errors import OutputError, PrivacyError, stage_for

SCHEMA_VERSION = '1.0'
DEFINITIONS_DIR = Path(__file__).resolve().parent / 'definitions'
TABLES = ('periods', 'rates', 'rates_final', 'changes', 'cohort_contrasts', 'data_quality', 'strata', 'unmapped')
BLOCKING = ('W09',)


def definitions_hash():
    """Hash of every copied definition and the request-type reference, plus the method version."""
    h = hashlib.sha256(METHOD_VERSION.encode())
    for p in sorted(DEFINITIONS_DIR.glob('*')):
        if p.suffix in ('.py', '.csv'):
            h.update(p.name.encode() + b'\0' + p.read_bytes())
    return h.hexdigest()[:12]


def slug(s):
    s = str(s)
    if s.startswith('Other models ('):
        return 'other_models'
    return re.sub(r'[^0-9a-z]+', '_', s.lower()).strip('_') or 'blank'


COLUMNS = {
    'periods': ['period_key', 'period_start', 'period_end', 'label', 'label_long', 'days', 'covered_days', 'status',
                'status_reason', 'role', 'unplanned_tickets_all_serials', 'open_tickets', 'open_share',
                'blank_category_share', 'label_ok'],
    'rates': ['period_key', 'period_start', 'period_end', 'period_label', 'status', 'stratum_dim', 'stratum',
              'stratum_key', 'issue_level', 'issue_group', 'issue', 'issue_key', 'tickets', 'machine_months',
              'avg_installed_machines', 'machines', 'machines_with_ticket', 'accounts', 'rate_per_100', 'ci_lo',
              'ci_hi', 'ci_method', 'ratio_to_fleet', 'ratio_lo', 'ratio_hi', 'vs_fleet', 'meets_min_exposure'],
    'changes': ['latest_period_key', 'latest_label', 'baseline_labels', 'baseline_periods_used', 'baseline_set',
                'stratum_dim',
                'stratum', 'stratum_key', 'issue_level', 'issue_group', 'issue', 'issue_key', 'tickets_latest',
                'months_latest', 'rate_latest', 'tickets_baseline', 'months_baseline', 'rate_baseline',
                'expected_latest', 'day_factor_latest', 'day_factor_baseline', 'change_ratio', 'ci_lo', 'ci_hi',
                'crude_ratio', 'sd_log', 'tau2', 'undefined_draws_share', 'accounts_with_tickets_baseline', 'z',
                'p_value', 'q_value', 'eligible', 'not_tested_reason', 'status', 'survivor_ratio', 'survivor_note',
                'sustained', 'previous_status', 'mdc_pct', 'sentence'],
    'cohort_contrasts': ['window_label', 'install_cohort', 'issue_level', 'issue_group', 'issue', 'issue_key',
                         'window_periods', 'machines', 'accounts', 'machine_months', 'tickets', 'rate_per_100',
                         'ci_lo', 'ci_hi', 'ci_method', 'rate_rest', 'crude_ratio', 'crude_lo', 'crude_hi',
                         'q_crude', 'p_call', 'q_call', 'expected_crude', 'position', 'newer_ratio', 'newer_lo', 'newer_hi',
                         'older_ratio', 'older_lo', 'older_hi', 'same_age_ratio', 'same_age_lo', 'same_age_hi',
                         'same_age_dropped_share', 'mean_age_years', 'top_models', 'eligible', 'not_tested_reason',
                         'status', 'basis', 'persisting', 'sentence'],
}


def prepare_tables(result, run_id, defs_hash):
    """Public tables with stable keys and the run columns on every row."""
    t = result.tables
    out = {}
    s = result.summary
    for name in ('periods', 'rates', 'changes', 'cohort_contrasts', 'data_quality', 'strata', 'unmapped'):
        df = t.get(name, pd.DataFrame())
        df = df.copy() if df is not None else pd.DataFrame()
        if name in ('rates', 'changes') and len(df):
            df['stratum_key'] = df.stratum.map(slug)
        if name == 'changes' and len(df):
            df['latest_period_key'] = s.get('latest_period_key')
            df['latest_label'] = s.get('latest_label')
            df['baseline_labels'] = '; '.join(s.get('baseline_labels', []))
            cmp_, plabels = (result.facts or {}).get('comparison') or {}, t.get('periods', pd.DataFrame())
            if 'baseline_set' in df and 'label' in plabels:        # each row's own baseline ('all' or 'labels')
                plabels = list(plabels.label)
                own = {k: '; '.join(str(plabels[p]) for p in cmp_.get(src) or [])
                       for k, src in (('all', 'baseline_positions'), ('labels', 'baseline_label_positions'))}
                df['baseline_labels'] = df.baseline_set.map(own).fillna(df.baseline_labels)
        if name == 'cohort_contrasts' and len(df):
            df['window_label'] = df['window_label'] if 'window_label' in df else s.get('cohort_window')
        if name in COLUMNS and len(df):
            df = df[[c for c in COLUMNS[name] if c in df.columns]]
        for c in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[c]):
                df[c] = df[c].dt.strftime('%Y-%m-%d')
        df.insert(0, 'definitions_hash', defs_hash)
        df.insert(0, 'method_version', METHOD_VERSION)
        df.insert(0, 'rerun_frequency', result.params['RERUN_FREQUENCY'])
        df.insert(0, 'run_id', run_id)
        df.insert(0, 'schema_version', SCHEMA_VERSION)
        out[name] = df.reset_index(drop=True)
    r = out['rates']
    out['rates_final'] = r[r.status == 'final'].reset_index(drop=True) if len(r) else r
    return out


def schema(tables):
    doc = {'schema_version': SCHEMA_VERSION,
           'dashboard_key': ['rerun_frequency', 'period_start', 'stratum_dim', 'stratum_key', 'issue_level',
                             'issue_group', 'issue'],
           'notes': 'Replace, never append: every run restates past periods (labels arrive late, lists change). '
                    'rates_final.csv holds final periods only and is the dashboard feed.',
           'tables': {}}
    for name, df in tables.items():
        doc['tables'][name] = {c: str(df[c].dtype) for c in df.columns}
    return doc


LOCATION_PARAMS = ('CASE_EXPORTS', 'EQUIPMENT_LISTS', 'OUTPUT_DIR', 'BASE_DIR')


def input_key(params_public, inputs):
    """Hash of the parameters and the input files' bytes: --only-if-new skips a run whose key has been published.
    Where files are read from or written to does not change the key; the files' contents do."""
    analysis = {k: v for k, v in params_public.items() if k not in LOCATION_PARAMS}
    h = hashlib.sha256(json.dumps(analysis, sort_keys=True, default=str).encode())
    h.update(inputs['case_export']['sha256'].encode())
    for e in inputs['equipment_lists']:
        h.update(e['sha256'].encode())
    h.update(__version__.encode())
    return h.hexdigest()[:16]


def make_run_id(result):
    key = input_key(result.params, result.facts['inputs'])
    return f"{result.facts['data_window'][1]}_{result.params['RERUN_FREQUENCY']}_{key[:8]}", key


def _write_csv(df, path):
    df.to_csv(path, index=False, float_format='%.10g', lineterminator='\n', encoding='utf-8')


RETRY_WAITS = (0.25, 0.5, 1, 2, 4)     # seconds between tries while Excel or OneDrive holds a file or folder
LOCKED = 'it is probably open in Excel, locked by OneDrive or read-only'
LOCKED_IN = 'a file in it is probably open in Excel, locked by OneDrive or read-only'


def _why(e, locked=LOCKED):
    """Why writing to OUTPUT_DIR failed, for an E30 message: a lock for PermissionError (Windows reports a file open in
    Excel that way), else the system's reason (e.g. no space left on device), never a path."""
    return locked if isinstance(e, PermissionError) else (getattr(e, 'strerror', None) or type(e).__name__)


def _retry(action):
    """Run action(), trying again after each of RETRY_WAITS while it raises PermissionError (Windows reports a
    file open in Excel, or a folder holding one, that way); the last PermissionError is raised."""
    for wait in RETRY_WAITS:
        try:
            return action()
        except PermissionError:
            time.sleep(wait)
    return action()


def _atomic_copy(src, dst):
    """Copy src over dst through dst.partial and os.replace, so dst is never half-written; the .partial file is
    removed whatever happens. Raises OSError: PermissionError when dst stays locked."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + '.partial')

    def copy():
        shutil.copyfile(src, tmp)
        os.replace(tmp, dst)
    try:
        _retry(copy)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _staged_files(stage):
    """A staged run's files in a fixed order (sorted by path), manifest.json last: a folder holding manifest.json
    holds the whole run."""
    def key(p):
        rel = p.relative_to(stage).as_posix()
        return rel == 'manifest.json', rel
    return sorted((p for p in Path(stage).rglob('*') if p.is_file()), key=key)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def publish(result, private, P, out=print, staging=None):
    """Write and publish a run; returns {'run_dir', 'latest_dir', 'files', 'run_id', 'distribution_ready', ...}.

    With `staging` (a folder), the run is only staged there, scanned and complete with its manifest, and nothing is
    written to OUTPUT_DIR: the caller publishes it with place_run(). `ipa-trends run --engine notebook` does this, so
    that the executed notebook is scanned before anything is published. The result then also holds 'staged'."""
    t0 = time.time()
    real = private['real']
    run_id, ikey = make_run_id(result)
    defs = definitions_hash()
    stage = Path(tempfile.mkdtemp(prefix='ipa_trends_')) if staging is None else Path(staging)
    stage.mkdir(parents=True, exist_ok=True)
    try:
        tables = prepare_tables(result, run_id, defs)
        for name, df in tables.items():
            _write_csv(df, stage / f'{name}.csv')
        (stage / 'schema.json').write_text(json.dumps(schema(tables), indent=2), encoding='utf-8')
        texts = []
        report_files = {}
        if P.MAKE_REPORT or P.MAKE_CHARTS:
            from . import report as REP
            built = REP.build(result, tables, P, stage, run_id)
            texts += built.get('texts', [])
            report_files = built.get('files', {})
        ready = (result.summary.get('latest_label') is not None
                 and not any(w.get('blocking') for w in result.warnings))
        manifest = {
            'schema_version': SCHEMA_VERSION, 'run_id': run_id, 'input_key': ikey,
            'generated_at': f'{dt.datetime.now():%Y-%m-%dT%H:%M:%S}', 'package_version': __version__,
            'method_version': METHOD_VERSION, 'definitions_hash': defs, 'parameters': _public_params(result.params),
            'parameter_sources': P.sources, 'inputs': _public_inputs(result.facts['inputs']),
            'data_window': result.facts['data_window'], 'extracted_at': result.facts['extracted_at'],
            'extracted_at_source': result.facts['extracted_at_source'], 'summary': result.summary,
            'facts': {k: v for k, v in result.facts.items() if k not in ('inputs',)},
            'warnings': result.warnings, 'checks': {'passed': len(result.checks), 'failed': 0},
            'distribution_ready': bool(ready),
            'next_run_after': next_run_after(result.summary, P),
            'environment': _environment()}
        # privacy scan of everything that will be published
        labels = set()
        for df in tables.values():
            for col in ('stratum', 'issue', 'issue_group', 'period_label', 'label', 'install_cohort', 'model',
                        'member', 'top_models', 'trouble_code', 'category'):
                if col in df.columns:
                    labels |= set(df[col].dropna().astype(str))
        real = PRIV.for_outputs(real, PRIV.vocabulary(labels))
        hits = {}
        for name, df in tables.items():
            hits.update(PRIV.scan_frame(df, real, name))
        from .definitions import fleet_exposure_copy as FX
        hits.update(PRIV.scan_texts(FX.json_strings(manifest), real, 'manifest'))
        hits.update(PRIV.scan_texts(texts, real, 'report and charts'))
        manifest['privacy'] = {'tables_scanned': len(tables), 'texts_scanned': len(texts),
                               'hits': int(sum(hits.values()))}
        if hits:
            raise PrivacyError('P01', f'the privacy scan found real identifiers in {len(hits)} output field(s): '
                                      f'{sorted(hits)}; nothing was published',
                               'tell the MIT team which fields were named (not their contents)')
        files = sorted(p for p in stage.rglob('*') if p.is_file())
        manifest['outputs'] = {str(p.relative_to(stage)).replace(os.sep, '/'): _sha(p) for p in files}
        manifest['elapsed_s'] = round(time.time() - t0, 1)
        (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2, default=str), encoding='utf-8')

        run_dir = P.output_dir / 'runs' / run_id
        latest = P.LATEST_PERIOD is None                  # a back-run leaves latest/ alone
        paths = {'run_dir': run_dir, 'latest_dir': P.output_dir / 'latest' if latest else None,
                 'files': [str(p.relative_to(stage)) for p in files] + ['manifest.json'], 'run_id': run_id,
                 'distribution_ready': bool(ready), **{k: run_dir / v for k, v in report_files.items()}}
        if staging is not None:
            _guard_git(P.output_dir)                      # fail early: place_run checks again
            out(f'Prepared run {run_id}; it is published to {run_dir}' + (' and latest/' if latest else '')
                + ' once the executed notebook has passed the privacy scan')
            return {**paths, 'staged': stage}
        place_run(stage, P.output_dir, run_id, latest=latest)
        out(f'Published run {run_id} to {run_dir}' + (' and latest/' if latest else
                                                      ' (a back-run: latest/ was not changed)'))
        return paths
    finally:
        if staging is None:
            shutil.rmtree(stage, ignore_errors=True)


def next_run_after(summary, P):
    """manifest.json's next_run_after: when the next run is due (YYYY-MM-DD), or None for a back-run
    (LATEST_PERIOD), which is not part of the schedule, and when no due date is known (explicit PERIOD_EDGES)."""
    if P.LATEST_PERIOD is not None:
        return None
    return (summary.get('next_runs') or [{}])[0].get('due')


def place_run(stage, output_dir, run_id, latest=True):
    """Publish a staged run: copy it into OUTPUT_DIR/runs/<run_id>/ (fixed order, manifest last) and, unless it is
    a back-run (latest=False), replace OUTPUT_DIR/latest/ with it as a whole. Returns the run folder.
    Raises OutputError E31 (OUTPUT_DIR inside a git work tree that does not ignore it) or E30 (a locked file or
    folder, or OUTPUT_DIR cannot be written), whose message says what was and was not changed."""
    output_dir = Path(output_dir)
    _guard_git(output_dir)
    run_dir = output_dir / 'runs' / run_id
    _place(stage, run_dir, f'runs/{run_id}')
    if latest:
        _swap_in(stage, output_dir / 'latest', run_id)
    return run_dir


def _place(stage, target, label):
    """Copy a staged run into `target` file by file (fixed order, manifest last), keeping files that are not part
    of it (an executed notebook saved there by an earlier run with the same run_id, which holds the same numbers)."""
    for p in _staged_files(stage):
        rel = p.relative_to(stage)
        try:
            _atomic_copy(p, target / rel)
        except OSError as e:
            raise OutputError('E30', f'could not replace {label}/{rel.as_posix()}: {_why(e)}. latest/ was not '
                                     f'updated, and {label}/ is incomplete until a run succeeds',
                              'close the file and run again' if isinstance(e, PermissionError) else
                              'check that OUTPUT_DIR can be written (free space, permissions) and run again') from None


def _swap_in(stage, target, run_id):
    """Replace the folder `target` (latest/) as a whole by a copy of the staged run, so it never mixes two runs.

    The copy, all but manifest.json, goes to latest.new/ beside it. os.replace onto an existing folder fails on
    Windows, so latest/ is first renamed aside to latest.old/, then latest.new/ is renamed to latest/ and latest.old/
    deleted. manifest.json is copied in last, as a new file, so a flow watching latest/manifest.json starts only once
    the whole run is in place (a OneDrive or SharePoint folder rename keeps the files' modified times). On Windows a
    file open in Excel (or held by OneDrive) makes renaming its folder fail: after the retries latest/ is put back as
    it was and E30 says latest/ was not updated."""
    new = target.with_name(target.name + '.new')
    old = target.with_name(target.name + '.old')
    had = target.exists()
    files = _staged_files(stage)
    manifest = files.pop() if files and files[-1].relative_to(stage).as_posix() == 'manifest.json' else None
    kept = ('latest/ was not updated (it still holds the previous run)' if had else 'latest/ was not created') + \
        f'; this run is in runs/{run_id}/'
    for leftover in ((new, old) if had else (new,)):      # without latest/, latest.old/ may be its only copy
        if leftover.exists():
            shutil.rmtree(leftover, ignore_errors=True)
            if leftover.exists():
                raise OutputError('E30', f'could not remove {leftover.name}/, left over from an earlier run: '
                                         f'{LOCKED}. {kept}', f'close its files, delete {leftover.name}/ and run '
                                                              'again')
    try:
        new.mkdir(parents=True, exist_ok=True)
        for p in files:
            _atomic_copy(p, new / p.relative_to(stage))
    except OSError as e:
        shutil.rmtree(new, ignore_errors=True)
        raise OutputError('E30', f'could not write {new.name}/ beside latest/: {_why(e)}. {kept}',
                          'check that OUTPUT_DIR can be written (free space, permissions) and run again') from None
    moved = False
    try:
        if had:
            _retry(lambda: os.replace(target, old))
            moved = True
        _retry(lambda: os.replace(new, target))
    except OSError as e:
        restored = not moved
        if moved:
            try:
                _retry(lambda: os.replace(old, target))
                restored = True
            except OSError:
                pass
        shutil.rmtree(new, ignore_errors=True)
        if not restored:
            raise OutputError('E30', f'could not replace latest/: {_why(e, LOCKED_IN)}. latest/ is missing: the '
                                     f'previous run is in {old.name}/ and this run in runs/{run_id}/',
                              f'close the files, rename {old.name}/ to latest/ (or run again)') from None
        raise OutputError('E30', f'could not replace latest/: {_why(e, LOCKED_IN)}. {kept}',
                          'close the files in latest/ and run again') from None
    shutil.rmtree(old, ignore_errors=True)       # a leftover is removed by the next run
    if manifest is not None:
        try:
            _atomic_copy(manifest, target / 'manifest.json')
        except OSError as e:
            raise OutputError('E30', f'could not write latest/manifest.json: {_why(e)}. latest/ holds this run '
                                     f'without its manifest until a run succeeds; runs/{run_id}/ holds all of it',
                              'close the file and run again') from None


def record_failure(output_dir, error, files=None):
    """Write OUTPUT_DIR/failed/<stamp>/error.txt for a run that stopped: its code, stage and exit code only (never
    the message, which can name local paths, and never a cell value). `files` ({name: path}) are copied beside it,
    e.g. the executed notebook once it has passed the privacy scan. Never raises.

    Returns (path, note): note is the line to show the analyst; path is None when nothing was written: for E31,
    for an OUTPUT_DIR inside a git work tree that does not ignore it (the record would sit in the repository), and
    when the folder cannot be written."""
    code = getattr(error, 'code', None) or 'E99'
    stage = getattr(error, 'stage', None) or stage_for(code)
    exit_code = getattr(error, 'exit_code', 3)
    in_git = 'no failure record was written: OUTPUT_DIR is inside a git repository that does not ignore it'
    if code == 'E31':
        return None, in_git
    try:
        root = Path(output_dir) / 'failed'
        if _git_exposed(root / 'error.txt'):
            return None, in_git
        stamp = f'{dt.datetime.now():%Y%m%dT%H%M%S}'
        for n in range(1, 100):
            d = root / (stamp if n == 1 else f'{stamp}_{n}')
            try:
                d.mkdir(parents=True)
                break
            except FileExistsError:
                continue
        else:
            raise FileExistsError(str(root))
        (d / 'error.txt').write_text(f'code: {code}\nstage: {stage}\nexit_code: {exit_code}\n'
                                     f'package_version: {__version__}\n', encoding='utf-8')
    except Exception as e:                       # noqa: BLE001 - a failure record must never hide the error itself
        return None, f'no failure record was written: {type(e).__name__} while writing to OUTPUT_DIR/failed/'
    copied = []
    for name, src in (files or {}).items():
        try:
            shutil.copyfile(src, d / name)
            copied.append(name)
        except OSError:
            pass
    return d / 'error.txt', f'Failure record: {d / "error.txt"}' + (f' (with {", ".join(copied)})' if copied else '')


def _git_exposed(path):
    """True when `path` lies inside a git work tree and git does not ignore it (False when git is not installed)."""
    import subprocess
    cwd = _existing_parent(Path(path).parent)
    try:
        top = subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=cwd, capture_output=True, text=True,
                             timeout=10)
        if top.returncode != 0:
            return False                         # not in a git work tree
        ign = subprocess.run(['git', 'check-ignore', '-q', str(path)], cwd=cwd, capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return ign.returncode != 0


def _guard_git(output_dir):
    """Refuse to write outputs into a git work tree unless git ignores the folder (they hold IPA's data)."""
    if _git_exposed(Path(output_dir) / 'manifest.json'):
        raise OutputError('E31', 'OUTPUT_DIR is inside a git repository and not ignored by git, so outputs could be '
                                 'committed', 'set OUTPUT_DIR to a folder outside the repository, or under data/')


def _existing_parent(p):
    p = Path(p)
    while not p.exists() and p != p.parent:
        p = p.parent
    return p


def _public_params(params):
    """Parameters for the manifest: an absolute path is shown by its last part only (it can hold a user name)."""
    def show(v):
        if isinstance(v, list):
            return [show(x) for x in v]
        if isinstance(v, str) and (v.startswith(('/', '\\', '~')) or re.match(r'^[A-Za-z]:[\\/]', v)):
            return '.../' + re.split(r'[\\/]', v.rstrip('/\\'))[-1]
        return v
    return {k: show(v) if k in LOCATION_PARAMS + ('REQUEST_TYPES_LOCAL',) else v for k, v in params.items()}


def _public_inputs(inputs):
    keep = ('file', 'bytes', 'sha256', 'content_fingerprint', 'sheet', 'header_row', 'rows', 'blank_rows',
            'non_data_rows', 'columns_missing_optional', 'created', 'snapshot_date')
    return {'case_export': {k: inputs['case_export'].get(k) for k in keep},
            'equipment_lists': [{k: e.get(k) for k in keep} for e in inputs['equipment_lists']]}


def _environment():
    import openpyxl
    env = {'python': platform.python_version(), 'pandas': pd.__version__, 'numpy': np.__version__,
           'openpyxl': openpyxl.__version__}
    try:
        import matplotlib
        env['matplotlib'] = matplotlib.__version__
    except ImportError:
        env['matplotlib'] = None
    return env
