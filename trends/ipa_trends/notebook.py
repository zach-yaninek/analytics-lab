"""What the notebook shows after a run, so ticket_trends.ipynb stays a parameters cell and two lines of code.

Everything displayed comes from the run's privacy-scanned aggregate tables and charts (published, or staged for
`ipa-trends run --engine notebook`, which publishes them once the executed notebook has passed the scan too).
"""
import json
import os
from pathlib import Path

import pandas as pd

# set by `ipa-trends run --engine notebook` to a file for this run's result (see run_and_show)
RESULT_ENV = 'IPA_TRENDS_RESULT'


def _display():
    try:
        from IPython.display import HTML, Image, Markdown, display
        return display, Markdown, Image, HTML
    except ImportError:                      # plain Python: print instead
        def display(x):
            print(x if not hasattr(x, 'to_string') else x.to_string())
        return display, (lambda s: s), (lambda filename: f'[chart] {filename}'), (lambda s: s)


def run_and_show(params):
    """Run, publish and show the results. Returns the RunResult (aggregate tables only).

    When the environment variable IPA_TRENDS_RESULT names a file (`ipa-trends run --engine notebook` sets it), the
    run is staged in a folder beside that file instead of published, and its run_id, folders, parameters and
    summary are written to the file, or its error code and stage if it stops: the command line then scans the
    executed notebook and publishes the run, with the notebook in its run folder, only if the scan passes."""
    from . import config
    from .engine import run, unexpected
    from .errors import TrendsError, stage_for
    handoff = os.environ.get(RESULT_ENV)
    if not handoff:
        try:
            result = run(params, publish=True)
        except TrendsError as e:             # say where the failure was recorded (or why it was not)
            if e.failure_record:
                print(e.failure_record[1])
            raise
        show(result)
        return result
    handoff = Path(handoff)
    P = None
    try:
        P = params if isinstance(params, config.Params) else config.resolve(params)
        result = run(P, publish=True, staging=handoff.parent / 'stage')
    except Exception as e:                   # noqa: BLE001 - reported to the command line, then raised
        err = e if isinstance(e, TrendsError) else unexpected(e, 'parameters')
        _hand_off(handoff, {'ok': False, 'code': err.code, 'stage': err.stage or stage_for(err.code),
                            'exit_code': err.exit_code, 'params': P.public() if P is not None else None,
                            'output_dir': str(P.output_dir) if P is not None else None})
        if err is e:
            raise
        raise err from None
    show(result)
    paths = result.paths
    _hand_off(handoff, {'ok': True, 'run_id': paths['run_id'], 'output_dir': str(P.output_dir),
                        'run_dir': str(paths['run_dir']), 'staged': str(paths['staged']),
                        'latest_dir': str(paths['latest_dir']) if paths.get('latest_dir') else None,
                        'distribution_ready': bool(paths.get('distribution_ready')), 'params': P.public(),
                        'summary': result.summary, 'warnings': result.warnings})
    return result


def _hand_off(path, doc):
    Path(path).write_text(json.dumps(doc, indent=2, default=str), encoding='utf-8')


def show(result):
    display, Markdown, Image, HTML = _display()
    s = result.summary
    lines = [f"### {s.get('latest_label') or 'No final period yet'} ({s.get('frequency_name')} run)"]
    if s.get('latest_label'):
        if 'fleet_rate_latest' in s:
            lines.append(f"**Fleet:** {s['fleet_rate_latest']:.2f} unplanned tickets per 100 installed "
                         f"machine-months (baseline {s['fleet_rate_baseline']:.2f}: "
                         f"{s['fleet_status'].replace('_', ' ')}).")
        lines.append(f"**Flagged changes:** {s.get('flags', 0)} &nbsp; **Watch list:** {s.get('watch', 0)} "
                     f"&nbsp; **Install cohorts that stand out:** {s.get('cohort_call_outs', 0)}")
    else:
        lines.append('No reporting period is final yet, so nothing is compared; the rates below are period-to-date.')
    for p in s.get('not_yet_final', []):
        lines.append(f"- {p['label']} is {p['status'].replace('_', ' ')}: {p['reason']}")
    paths = result.paths or {}
    if paths.get('run_dir'):
        where = ('(also copied to `latest/`)' if paths.get('latest_dir') else
                 '(a back-run: `latest/` was not changed; send the files from this run folder)')
        lines.append(f"**Outputs:** `{paths['run_dir']}` {where}. "
                     f"Ready to distribute: **{'yes' if paths.get('distribution_ready') else 'no'}**.")
    lines += next_run_lines(s)
    display(Markdown('\n\n'.join(lines)))

    ch = result.tables.get('changes', pd.DataFrame())
    if len(ch):
        flags = ch[ch.status.isin(['higher', 'lower'])]
        if len(flags):
            display(Markdown('#### Flagged changes (screening flags for follow-up, not proof of a problem)'))
            for t in flags.sentence:
                display(Markdown(f'- {t}'))
    co = result.tables.get('cohort_contrasts', pd.DataFrame())
    if len(co):
        st = co[co.status.str.startswith('stands_out')]
        if len(st):
            display(Markdown('#### Install cohorts that stand out'))
            for t in st.sentence:
                display(Markdown(f'- {t}'))
    charts = Path(paths.get('staged') or paths.get('run_dir') or '.', 'charts')   # staged: not yet copied
    if paths.get('run_dir') and charts.exists():
        for png in sorted(charts.glob('*.png')):
            display(Image(filename=str(png)))
    if result.warnings:
        display(Markdown('#### Data-quality notes\n' + '\n'.join(
            f"- **{w['code']}** {w['message']}" + (f" *Fix:* {w['fix']}" if w.get('fix') else '')
            for w in result.warnings)))


def next_run_lines(summary, bold=True):
    """'Next run due' and the periods that need a newer export, from a run's summary (also used by the CLI)."""
    b = '**' if bold else ''
    out = []
    if summary.get('next_runs'):
        nxt = summary['next_runs'][0]
        out.append(f"{b}Next run due:{b} {nxt['due']} (for {nxt['label']}).")
    for p in summary.get('needs_newer_export', []):
        out.append(f"{b}{p['label']} needs a newer export:{b} {p['reason']}.")
    return out
