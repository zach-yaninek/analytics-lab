"""Command line: ipa-trends (or python -m ipa_trends) run / reconcile / inspect / next-runs / selftest / make-fixture.

Exit codes (errors.exit_code_for): 0 = OK or skipped; 1 = a runtime check (C01) or the privacy scan (P01) failed;
2 = an input, parameter or output-folder problem (E01-E31); 3 = unexpected (E99: its traceback goes to a private log
on this computer, never to the console). A `run` that stops also leaves OUTPUT_DIR/failed/<stamp>/error.txt (code,
stage, exit code) when OUTPUT_DIR is known, except inside a git repository that does not ignore it.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from . import config as CFG
from .errors import CODE_RE, NotebookError, PrivacyError, TrendsError, stage_for

HERE = Path(__file__).resolve().parent
TRENDS = HERE.parent
NOTEBOOK = TRENDS / 'ticket_trends.ipynb'


def _overrides(args):
    overrides, sources = {}, {}
    if getattr(args, 'params', None):
        f = CFG.load_file(args.params)
        overrides.update(f)
        sources.update({k: f'file {Path(args.params).name}' for k in f})
    s = CFG.parse_sets(getattr(args, 'set', None))
    overrides.update(s)
    sources.update({k: '--set' for k in s})
    return overrides, sources


def _params(args):
    overrides, sources = _overrides(args)
    return CFG.resolve(overrides, sources=sources)


def cmd_run(args):
    P = _params(args)
    args.resolved = P                                # for the failure record (main)
    if args.only_if_new and _already_published(P):
        print('Nothing new: the latest published run used these inputs and parameters (--only-if-new).')
        return 0
    if args.engine == 'notebook':
        return run_notebook(P, args)
    from .engine import run
    r = run(P, publish=True, verbose=not args.quiet)
    _print_result(r)
    return 0


def _already_published(P):
    from . import inputs as INP
    from .publish import input_key
    latest = P.output_dir / 'latest' / 'manifest.json'
    if not latest.exists():
        return False
    try:
        old = json.loads(latest.read_text(encoding='utf-8'))
        warn = INP.Warnings()
        case, snaps = INP.find_inputs(P, warn)
        inputs = {'case_export': {'sha256': INP.file_sha256(case)},
                  'equipment_lists': [{'sha256': INP.file_sha256(p)} for _, p in snaps]}
        return old.get('input_key') == input_key(P.public(), inputs)
    except (OSError, ValueError, TrendsError):
        return False


def _print_result(r):
    s = r.summary
    print()
    if s.get('latest_label'):
        print(f"Latest final {s.get('period_noun', 'period')}: {s['latest_label']} "
              f"(baseline: {len(s.get('baseline_labels', []))} of {s.get('baseline_intended')} periods)")
        if 'fleet_rate_latest' in s:
            print(f"Fleet: {s['fleet_rate_latest']:.2f} unplanned tickets per 100 installed machine-months "
                  f"(baseline {s['fleet_rate_baseline']:.2f}; {s['fleet_status'].replace('_', ' ')})")
        print(f"Flags: {s.get('flags', 0)}   watch list: {s.get('watch', 0)}   cohort call-outs: "
              f"{s.get('cohort_call_outs', 0)}")
    else:
        print('No reporting period is final yet; rates only.')
    for w in r.warnings:
        print(f"  {w['code']}: {w['message']}" + (f"  [{w['fix']}]" if w.get('fix') else ''))
    if r.paths:
        print(f"Outputs: {r.paths.get('run_dir')}" + ('' if r.paths.get('latest_dir') else
                                                      ' (a back-run: latest/ was not changed)'))
        print(f"distribution_ready: {r.paths.get('distribution_ready')}")
    from .notebook import next_run_lines
    for line in next_run_lines(s, bold=False):
        print(line)


def run_notebook(P, args):
    """Execute ticket_trends.ipynb headless with these parameters (papermill if installed, else nbclient).

    The notebook reports its own run through IPA_TRENDS_RESULT (notebook.run_and_show) and only stages it. This
    scans the executed notebook's outputs and then publishes the run, with the notebook saved in that run's folder;
    if the scan finds a real identifier, nothing is published (P01). When the notebook stops, its code gives the
    exit code, and the failure record keeps the executed notebook if its outputs pass the scan."""
    import tempfile
    from . import notebook as NB
    # the parameters set in the file or on the command line are injected, and the notebook keeps its own values for
    # the others; BASE_DIR always, so that relative paths name the same folders as here
    params = {k: v for k, v in P.public().items() if P.sources.get(k, 'default') != 'default'}
    params['BASE_DIR'] = str(P.base_dir)
    tmp = Path(tempfile.mkdtemp(prefix='ipa_trends_nb_'))
    out_nb, handoff = tmp / 'executed.ipynb', tmp / 'result.json'
    keep = False
    try:
        try:
            import papermill as pm
        except ImportError:
            pm = None
        before = os.environ.get(NB.RESULT_ENV)
        os.environ[NB.RESULT_ENV] = str(handoff)                 # the kernel inherits it
        failure = None
        try:
            if pm is not None:
                pm.execute_notebook(str(NOTEBOOK), str(out_nb), parameters=params, cwd=str(TRENDS),
                                    progress_bar=False, kernel_name=args.kernel)
            else:
                from . import nbexec
                nbexec.execute(NOTEBOOK, out_nb, params, cwd=TRENDS, kernel_name=args.kernel)
        except Exception as e:                    # noqa: BLE001 - the executor wraps the cell's exception
            failure = e
        finally:
            if before is None:
                os.environ.pop(NB.RESULT_ENV, None)
            else:
                os.environ[NB.RESULT_ENV] = before
        try:
            reported = json.loads(handoff.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            reported = {}
        # the notebook's own parameters (its cell plus what was injected) decide what is scanned and where it goes
        PN = _notebook_params(reported, P)
        if failure is not None or not reported.get('ok'):
            err = _notebook_error(failure, reported, executed=out_nb.exists())
            keep = _file_failure(PN, err, out_nb, _scan(PN, out_nb) if out_nb.exists() else -1)
            raise err from None
        from . import engine
        try:
            hits = int(engine.scan_notebook(PN, out_nb))
        except TrendsError as e:
            keep = _file_failure(PN, e, out_nb, None)
            raise
        if hits:
            err = PrivacyError('P01', f'the executed notebook would show real identifiers in {hits} place(s), so '
                                      'nothing was published', 'tell the MIT team (the number of places, not what '
                                                               'they show)', stage='notebook privacy scan')
            keep = _file_failure(PN, err, out_nb, hits)
            raise err
        latest = bool(reported.get('latest_dir'))
        try:
            from .publish import place_run
            run_dir = place_run(Path(reported['staged']), PN.output_dir, reported['run_id'], latest=latest)
        except TrendsError as e:
            keep = _file_failure(PN, e, out_nb, hits)
            raise
        saved, keep = _save_notebook(out_nb, run_dir)
        if not args.quiet:
            print(f"Published run {reported['run_id']} to {run_dir}"
                  + (' and latest/' if latest else ' (a back-run: latest/ was not changed)'))
        _print_result(SimpleNamespace(summary=reported.get('summary') or {}, warnings=reported.get('warnings') or [],
                                      paths={'run_dir': run_dir, 'latest_dir': reported.get('latest_dir'),
                                             'distribution_ready': reported.get('distribution_ready')}))
        print(saved)
        return 0
    finally:
        if not keep:
            shutil.rmtree(tmp, ignore_errors=True)


def _notebook_params(reported, P):
    """The parameters the notebook ran with (its cell plus what was injected), from what it reported; P when it
    reported none (it stopped before resolving them, so it read no input)."""
    if reported.get('params'):
        try:
            return CFG.resolve(reported['params'], base_dir=P.base_dir)
        except Exception:                        # noqa: BLE001
            pass
    return P


def _coded():
    """Names of TrendsError and its subclasses: the notebook stopped on a coded error when its exception is one."""
    names, todo = set(), [TrendsError]
    while todo:
        cls = todo.pop()
        names.add(cls.__name__)
        todo += cls.__subclasses__()
    return names


def _notebook_error(failure, reported, executed=True):
    """The notebook's failure as a NotebookError: the whole code in its error text, that text itself, and the stage
    the notebook reported. Anything but a coded error is E99, its traceback in a private log and only its type shown
    (its message can quote a cell value). `executed`: there is an executed notebook to look at."""
    ename = getattr(failure, 'ename', None)
    evalue = str(getattr(failure, 'evalue', '') or '')
    m = CODE_RE.search(evalue) if ename in _coded() else None
    if m:
        code, text = m.group(1), evalue.strip()
    elif failure is None:
        code, text = 'E99', 'E99: the notebook ran to the end without reporting a run (does it still call ' \
                            'notebook.run_and_show?)'
    else:
        from .engine import _private_log
        try:
            saved = f'the full traceback is in a private log on this computer: {_private_log(failure)}'
        except Exception:                        # noqa: BLE001 - never fall back to showing the exception
            saved = 'its traceback could not be saved to a private log on this computer'
        what = ename or type(failure).__name__
        head = (f'the notebook stopped on an unexpected {what}; the executed notebook shows where, and ' if executed
                else f'the notebook could not be run (unexpected {what}); ')
        code, text = 'E99', f'E99: {head}{saved}\n  Fix: send the error code and stage (not the log) to the MIT team'
    stage = reported.get('stage') if reported.get('code') == code else None
    return NotebookError(code, text, stage=stage or stage_for(code, 'notebook'))


def _scan(P, path):
    """Places in the executed notebook's outputs that show a real identifier (None when it cannot be scanned)."""
    from . import engine
    try:
        return int(engine.scan_notebook(P, path))
    except Exception:                            # noqa: BLE001 - e.g. the inputs that stopped the run
        return None


def _file_failure(P, err, out_nb, hits):
    """Record a notebook run that stopped (err.failure_record). The executed notebook goes beside error.txt only if
    its outputs passed the privacy scan (hits == 0) and the run did not stop on the privacy scan (P01: the leak can
    sit in its parameters cell, which the scan does not read); otherwise it is deleted with the temporary folder.
    When it could not be scanned (None) or has no record to go with, it stays in the temporary folder, which the note
    names. -1: there is no executed notebook. Returns True when the temporary folder must be kept."""
    from .publish import record_failure
    clean = hits == 0 and err.code != 'P01'
    path, note = record_failure(P.output_dir, err, files={'executed_notebook.ipynb': out_nb} if clean else None)
    keep = hits is None or (clean and path is None)
    if keep:
        why = 'could not be checked for real identifiers' if hits is None else 'has no failure record to go with'
        note += f'. The executed notebook {why}, so it stays outside OUTPUT_DIR: {out_nb}'
    elif hits > 0:
        note += f'. The executed notebook would show real identifiers in {hits} place(s), so it was deleted'
    elif hits == 0 and not clean:
        note += '. The executed notebook may hold what the privacy scan found, so it was deleted'
    err.failure_record = (path, note)
    return keep


def _save_notebook(out_nb, run_dir):
    """(the line to print, keep the temporary folder) after copying the executed notebook into its run folder."""
    from .publish import _atomic_copy
    dest = Path(run_dir) / 'executed_notebook.ipynb'
    try:
        _atomic_copy(out_nb, dest)
        return f'Executed notebook saved to {dest}', False
    except OSError as e:
        return f'The executed notebook could not be saved in {run_dir} ({type(e).__name__}); it is at {out_nb}', True


def cmd_reconcile(args):
    from . import reconcile
    return reconcile.main(args)


def cmd_inspect(args):
    from . import inputs as INP
    P = _params(args)
    warn = INP.Warnings()
    paths = []
    if args.case:
        paths.append(('case', Path(args.case)))
    if args.equipment:
        paths.append(('equipment', Path(args.equipment)))
    if not paths:
        case, snaps = INP.find_inputs(P, warn)
        paths = [('case', case)] + [('equipment', p) for _, p in snaps]
    for kind, p in paths:
        known = INP.CASE_KNOWN if kind == 'case' else INP.EQUIP_KNOWN
        sheet = P.CASE_SHEET if kind == 'case' else P.EQUIPMENT_SHEET
        print(json.dumps(INP.inspect(p, sheet, known, P.COLUMN_ALIASES), indent=2, default=str))
    return 0


def cmd_next_runs(args):
    import pandas as pd
    from .cadence import next_runs
    P = _params(args)
    after = pd.Timestamp(args.after) if args.after else pd.Timestamp.today().normalize()
    runs, cron = next_runs(P.cadence, after - pd.Timedelta(days=P.LABEL_LAG_DAYS), P.LABEL_LAG_DAYS, args.n,
                           P.YEAR_START_MONTH, P.FISCAL_YEAR_NAMED_BY, P.ANCHOR_DATE)
    print(f'Rerun frequency: {P.cadence.adjective} ({P.cadence.canonical}); a run is due {P.LABEL_LAG_DAYS} days '
          'after each period ends, once its labels have settled.')
    for r in runs:
        print(f"  {r['label']:<22} {r['period_start']} to {r['period_end']} (exclusive)  due {r['due']}")
    if cron:
        print(f'cron (07:00 on the due days): {cron}')
    else:
        print('No single cron line fits this frequency: schedule a daily run with --only-if-new.')
    return 0


def cmd_selftest(args):
    tests = TRENDS / 'tests' / 'run_tests.py'
    if not tests.exists():
        print('trends/tests/run_tests.py not found', file=sys.stderr)
        return 2
    cmd = [sys.executable, '-I', str(tests)] + (['--quick'] if args.quick else [])
    return subprocess.call(cmd, cwd=str(TRENDS))


def cmd_make_fixture(args):
    sys.path.insert(0, str(TRENDS / 'tests'))
    import make_trend_fixture as MF
    truth = MF.build(args.out, seed=args.seed, null=args.null, variant=args.variant, snapshots=args.snapshots,
                     scale=args.scale)
    print(f"Synthetic exports written to {args.out} ({truth['counts']['case_rows']} case rows)")
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog='ipa-trends', description='IPA service-ticket trends (installed machine-months).')
    sub = p.add_subparsers(dest='command', required=True)

    def with_params(sp):
        sp.add_argument('--params', help='YAML or JSON parameter file (see trends/params/)')
        sp.add_argument('--set', action='append', metavar='NAME=VALUE', help='override one parameter (repeatable)')

    r = sub.add_parser('run', help='run the analysis and publish the outputs')
    with_params(r)
    r.add_argument('--engine', choices=('direct', 'notebook'), default='direct',
                   help='direct (default) or execute ticket_trends.ipynb headless')
    r.add_argument('--kernel', default='python3', help='Jupyter kernel for --engine notebook')
    r.add_argument('--only-if-new', action='store_true',
                   help='skip when the latest published run used the same inputs and parameters')
    r.add_argument('--quiet', action='store_true')
    r.set_defaults(func=cmd_run)
    c = sub.add_parser('reconcile', help='check the engine against the numbers already shown to IPA')
    with_params(c)
    c.add_argument('--deep', action='store_true', help='also compare machine by machine with verification/ (MIT)')
    c.set_defaults(func=cmd_reconcile)
    i = sub.add_parser('inspect', help='describe input files without printing any values')
    with_params(i)
    i.add_argument('--case')
    i.add_argument('--equipment')
    i.set_defaults(func=cmd_inspect)
    n = sub.add_parser('next-runs', help='when the next runs are due for this frequency')
    with_params(n)
    n.add_argument('--n', type=int, default=4)
    n.add_argument('--after', help='YYYY-MM-DD (default today)')
    n.set_defaults(func=cmd_next_runs)
    s = sub.add_parser('selftest', help='run the test suite on synthetic data')
    s.add_argument('--quick', action='store_true')
    s.set_defaults(func=cmd_selftest)
    m = sub.add_parser('make-fixture', help='write synthetic exports for testing')
    m.add_argument('--out', required=True)
    m.add_argument('--seed', type=int, default=7)
    m.add_argument('--null', action='store_true')
    m.add_argument('--variant')
    m.add_argument('--snapshots', type=int, default=1)
    m.add_argument('--scale', type=float, default=1.0)
    m.set_defaults(func=cmd_make_fixture)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except TrendsError as e:
        print(e.text(), file=sys.stderr)
        _failure_note(args, e)
        return e.exit_code
    except Exception as e:                       # noqa: BLE001
        from .engine import unexpected
        err = unexpected(e, f'the {args.command} command')
        print(err.text(), file=sys.stderr)
        _failure_note(args, err)
        return err.exit_code


def _failure_note(args, e):
    """For `run`: record the failure in OUTPUT_DIR/failed/ unless the engine or the notebook runner already did (or
    deliberately did not), and say where, or why there is no record."""
    if args.command != 'run':
        return
    if e.failure_record is None:
        out_dir = _failure_output_dir(args)
        if out_dir is None:
            e.failure_record = (None, 'no failure record was written: OUTPUT_DIR could not be read from the '
                                      'parameters')
        else:
            from .publish import record_failure
            e.failure_record = record_failure(out_dir, e)
    print(e.failure_record[1], file=sys.stderr)


def _failure_output_dir(args):
    """OUTPUT_DIR for the failure record: from the resolved parameters, or, when they did not resolve, from
    OUTPUT_DIR and BASE_DIR in the parameter file and --set values (None when those cannot be read)."""
    P = getattr(args, 'resolved', None)
    if P is not None:
        return P.output_dir
    try:
        overrides, _ = _overrides(args)
    except Exception:                            # noqa: BLE001 - the parameter file itself is the problem
        return None
    from .engine import output_dir_of
    return output_dir_of(overrides)


if __name__ == '__main__':
    sys.exit(main())
