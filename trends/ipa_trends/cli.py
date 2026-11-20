"""Command line: ipa-trends (or python -m ipa_trends) run / reconcile / inspect / next-runs / selftest / make-fixture.

Exit codes: 0 = OK or skipped; 1 = a runtime check or the privacy scan failed; 2 = an input or parameter problem;
3 = an unexpected error (its traceback goes to a private log on this computer, never to the console).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import config as CFG
from .errors import TrendsError

HERE = Path(__file__).resolve().parent
TRENDS = HERE.parent
NOTEBOOK = TRENDS / 'ticket_trends.ipynb'


def _params(args):
    overrides, sources = {}, {}
    if getattr(args, 'params', None):
        f = CFG.load_file(args.params)
        overrides.update(f)
        sources.update({k: f'file {Path(args.params).name}' for k in f})
    s = CFG.parse_sets(getattr(args, 'set', None))
    overrides.update(s)
    sources.update({k: '--set' for k in s})
    return CFG.resolve(overrides, sources=sources)


def cmd_run(args):
    P = _params(args)
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
        print(f"Latest final {s['frequency_name']} period: {s['latest_label']} "
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
        print(f"Outputs: {r.paths.get('run_dir')}")
        print(f"distribution_ready: {r.paths.get('distribution_ready')}")
    if s.get('next_runs'):
        print(f"Next run due: {s['next_runs'][0]['due']} (for {s['next_runs'][0]['label']})")


def run_notebook(P, args):
    """Execute ticket_trends.ipynb headless with these parameters (papermill if installed, else nbclient), scan
    the executed notebook's outputs, and save it in the run folder."""
    import tempfile
    from . import engine
    # only the parameters set in the file or on the command line are injected; the notebook keeps its defaults
    params = {k: v for k, v in P.public().items() if P.sources.get(k, 'default') != 'default'}
    out_nb = Path(tempfile.mkdtemp(prefix='ipa_trends_nb_')) / 'executed.ipynb'
    try:
        import papermill as pm
        pm.execute_notebook(str(NOTEBOOK), str(out_nb), parameters=params, cwd=str(TRENDS), progress_bar=False,
                            kernel_name=args.kernel)
    except ImportError:
        from . import nbexec
        nbexec.execute(NOTEBOOK, out_nb, params, cwd=TRENDS, kernel_name=args.kernel)
    except Exception as e:                                # noqa: BLE001 - papermill wraps the cell's exception
        text = str(e)
        code = next((c for c in ('E0', 'E1', 'E2', 'E3', 'C01', 'P01', 'E99') if c in text), 'E99')
        print(f'{code}: the notebook stopped (see the executed notebook for the parameter or input message)',
              file=sys.stderr)
        return 2 if code.startswith('E0') or code.startswith('E2') else 1 if code in ('C01', 'P01') else 3
    hits = engine.scan_notebook(P, out_nb)
    if hits:
        print(f'P01: the executed notebook would show real identifiers in {hits} place(s); it was not saved',
              file=sys.stderr)
        return 1
    latest = P.output_dir / 'latest' / 'manifest.json'
    if latest.exists():
        run_id = json.loads(latest.read_text(encoding='utf-8'))['run_id']
        dest = P.output_dir / 'runs' / run_id / 'executed_notebook.ipynb'
        dest.write_bytes(out_nb.read_bytes())
        print(f'Executed notebook saved to {dest}')
    return 0


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
        return e.exit_code
    except Exception as e:                       # noqa: BLE001
        from .engine import _private_log
        log = _private_log(e)
        print(f'E99: unexpected {type(e).__name__}; the traceback is in a private log on this computer: {log}',
              file=sys.stderr)
        return 3


if __name__ == '__main__':
    sys.exit(main())
