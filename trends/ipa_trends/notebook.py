"""What the notebook shows after a run, so ticket_trends.ipynb stays a parameters cell and two lines of code.

Everything displayed comes from the published, privacy-scanned aggregate tables and charts.
"""
from pathlib import Path

import pandas as pd


def _display():
    try:
        from IPython.display import HTML, Image, Markdown, display
        return display, Markdown, Image, HTML
    except ImportError:                      # plain Python: print instead
        def display(x):
            print(x if not hasattr(x, 'to_string') else x.to_string())
        return display, (lambda s: s), (lambda filename: f'[chart] {filename}'), (lambda s: s)


def run_and_show(params):
    """Run, publish and show the results. Returns the RunResult (aggregate tables only)."""
    from .engine import run
    result = run(params, publish=True)
    show(result)
    return result


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
        lines.append(f"**Outputs:** `{paths['run_dir']}` (also copied to `latest/`). "
                     f"Ready to distribute: **{'yes' if paths.get('distribution_ready') else 'no'}**.")
    if s.get('next_runs'):
        lines.append(f"**Next run due:** {s['next_runs'][0]['due']} (for {s['next_runs'][0]['label']}).")
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
    run_dir = paths.get('run_dir')
    if run_dir and Path(run_dir, 'charts').exists():
        for png in sorted(Path(run_dir, 'charts').glob('*.png')):
            display(Image(filename=str(png)))
    if result.warnings:
        display(Markdown('#### Data-quality notes\n' + '\n'.join(
            f"- **{w['code']}** {w['message']}" + (f" *Fix:* {w['fix']}" if w.get('fix') else '')
            for w in result.warnings)))
