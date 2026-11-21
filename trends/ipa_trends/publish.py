"""Publishing a run: tables, schema, manifest, charts, report and email text, after every check and the privacy scan.

Everything is first written to a private temporary folder outside OUTPUT_DIR (a OneDrive- or SharePoint-synced
OUTPUT_DIR would otherwise upload files before they are scanned). Only when the privacy scan passes are the files
copied, one at a time with os.replace and retries (Excel and OneDrive lock files), into OUTPUT_DIR/runs/<run_id>/
and then OUTPUT_DIR/latest/, with manifest.json written last. A failed run writes only failed/<stamp>/error.txt
(codes and counts). Rerunning the same inputs with the same parameters reproduces the same run_id and files.
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
from .errors import PrivacyError, TrendsError

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
    'changes': ['latest_period_key', 'latest_label', 'baseline_labels', 'baseline_periods_used', 'stratum_dim',
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
        if name == 'cohort_contrasts' and len(df):
            df['window_label'] = s.get('cohort_window')
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


def input_key(params_public, inputs):
    """Hash of the parameters and the input files' bytes: --only-if-new skips a run whose key has been published."""
    h = hashlib.sha256(json.dumps(params_public, sort_keys=True, default=str).encode())
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


def _atomic_copy(src, dst, retries=6):
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + '.partial')
    for i in range(retries):
        try:
            shutil.copyfile(src, tmp)
            os.replace(tmp, dst)
            return
        except PermissionError:
            time.sleep(0.25 * 2 ** i)
    raise TrendsError('E30', f'could not replace {dst.name}: it is probably open in Excel or locked by OneDrive',
                      'close the file and run again; distribution_ready stays false until then')


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def publish(result, private, P, out=print):
    """Write and publish a run; returns {'run_dir', 'latest_dir', 'files'}."""
    t0 = time.time()
    real = private['real']
    run_id, ikey = make_run_id(result)
    defs = definitions_hash()
    stage = Path(tempfile.mkdtemp(prefix='ipa_trends_'))
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
            'method_version': METHOD_VERSION, 'definitions_hash': defs, 'parameters': result.params,
            'parameter_sources': P.sources, 'inputs': _public_inputs(result.facts['inputs']),
            'data_window': result.facts['data_window'], 'extracted_at': result.facts['extracted_at'],
            'extracted_at_source': result.facts['extracted_at_source'], 'summary': result.summary,
            'facts': {k: v for k, v in result.facts.items() if k not in ('inputs',)},
            'warnings': result.warnings, 'checks': {'passed': len(result.checks), 'failed': 0},
            'distribution_ready': bool(ready),
            'next_run_after': (result.summary.get('next_runs') or [{}])[0].get('due'),
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
        latest_dir = P.output_dir / 'latest'
        _guard_git(P.output_dir)
        _place(stage, run_dir)
        if P.LATEST_PERIOD is None:
            _place(stage, latest_dir, clear=True)
        out(f'Published run {run_id} to {run_dir}' + ('' if P.LATEST_PERIOD else ' and latest/'))
        return {'run_dir': run_dir, 'latest_dir': latest_dir if P.LATEST_PERIOD is None else None,
                'files': [str(p.relative_to(stage)) for p in files] + ['manifest.json'], 'run_id': run_id,
                'distribution_ready': bool(ready), **{k: run_dir / v for k, v in report_files.items()}}
    except TrendsError as e:
        _failed(P, e)
        raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def _place(stage, target, clear=False):
    """Copy staged files into target one by one (manifest last); remove stale files when clear=True."""
    files = sorted((p for p in stage.rglob('*') if p.is_file()), key=lambda p: p.name == 'manifest.json')
    rel = {str(p.relative_to(stage)) for p in files}
    if clear and target.exists():
        for old in target.rglob('*'):
            if old.is_file() and str(old.relative_to(target)) not in rel:
                old.unlink()
    for p in files:
        _atomic_copy(p, target / p.relative_to(stage))


def _failed(P, e):
    try:
        d = P.output_dir / 'failed' / f'{dt.datetime.now():%Y%m%dT%H%M%S}'
        d.mkdir(parents=True, exist_ok=True)
        (d / 'error.txt').write_text(f'{e.code}\n{e.message.split(":")[0]}\n', encoding='utf-8')
    except OSError:
        pass


def _guard_git(output_dir):
    """Refuse to write outputs into a git work tree unless git ignores the folder (they hold IPA's data)."""
    import subprocess
    probe = Path(output_dir) / 'manifest.json'
    try:
        top = subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=_existing_parent(output_dir),
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return
    if top.returncode != 0:
        return                                   # not in a git work tree
    ign = subprocess.run(['git', 'check-ignore', '-q', str(probe)], cwd=_existing_parent(output_dir),
                         capture_output=True, timeout=10)
    if ign.returncode != 0:
        raise TrendsError('E31', 'OUTPUT_DIR is inside a git repository and not ignored by git, so outputs could be '
                                 'committed', 'set OUTPUT_DIR to a folder outside the repository, or under data/')


def _existing_parent(p):
    p = Path(p)
    while not p.exists() and p != p.parent:
        p = p.parent
    return p


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
