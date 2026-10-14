#!/usr/bin/env python3
"""Zac's figure 3: the 10 machine models with the most tickets in the full case export (raw counts).

Recreates 03_model_workload.png from Zac's notebook (cell 17: his model_workload query over `cases`, every ticket in
the case export, and his bar() helper from cell 9 on models.head(10)). Same population (all tickets, including
planned work, cancelled requests and duplicate cases), same selection (top 10 by tickets, ties broken by model as in
his ORDER BY) and same metric (tickets per model). Added: each model's share of all tickets, blue for the three
models his notebook sums ("The top 3 models account for ...") and a definitions line saying the counts are not
adjusted for how many machines of each model are installed.

Inputs:  zac_data.load('model_workload')  verification/outputs/repro_sql_model_workload.csv (model, cases,
                                          affected_machines, share_pct; one row per model)
         zac_data.load('record_quality')  repro_sql_record_quality.csv (ticket and model totals, period)
         zac_data.load('service_groups')  repro_sql_service_groups.csv (ticket total, cross-check)
Output:  viz/figures/zac_03_model_workload.png
Run:     cd /home/user/analytics-lab && python3 -I viz/zac_notebook/zac_03_model_workload.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]  # python3 -I leaves the script directory off sys.path
import numpy as np  # noqa: E402

import ipa_style as style  # noqa: E402
import zac_data  # noqa: E402

TOP_N = 10        # Zac's selection: models.head(10) (notebook cell 17)
N_HIGHLIGHT = 3   # Zac's cell 17 summary: "The top 3 models account for ...% of all tickets"
PNG = 'zac_03_model_workload.png'
FIXED_IN = 3.6    # figure height for the title band, x axis and footer
ROW_IN = 0.36     # figure height added per bar (constrained layout sets the final row pitch)
BAR_H = 0.5       # bar thickness as a share of the row pitch
NOT_ADJUSTED = (
    'Not adjusted for fleet size: these are raw ticket counts, so a model can rank high simply because many of its '
    'machines are installed. The case export does not record installed machines per model, so per-machine rates by '
    'model cannot be computed from it.')


def plot(out_dir=zac_data.FIG_DIR):
    out_dir = Path(out_dir)
    mw, rq, sg = zac_data.load('model_workload'), zac_data.load('record_quality'), zac_data.load('service_groups')
    # Zac's ranking: ORDER BY cases DESC, model (cell 17).
    d = mw.sort_values(['cases', 'model'], ascending=[False, True], kind='mergesort').reset_index(drop=True)
    total = int(d.cases.sum())
    top, rest = d.head(TOP_N), d.iloc[TOP_N:]
    lead = top.head(N_HIGHLIGHT)

    # Checks: the models cover every ticket once; shares and the top-3 sum agree with Zac's columns.
    style.check('zac_03 tickets = record_quality cases', int(rq.cases.iloc[0]), total)
    style.check('zac_03 tickets = service_groups cases', int(sg.cases.sum()), total)
    style.check('zac_03 models = record_quality models', int(rq.models.iloc[0]), len(d))
    style.check('zac_03 top 10 = Zac\'s table order', 1, int(top.model.tolist() == mw.model.head(TOP_N).tolist()))
    style.check('zac_03 no tie at the top-10 cutoff', 1, int(d.cases.iloc[TOP_N - 1] > d.cases.iloc[TOP_N]))
    style.check('zac_03 bracketed shares = share_pct', 0,
                float((100 * top.cases / total - top.share_pct).abs().max()), 1e-9)
    style.check('zac_03 top-3 share = sum of share_pct (Zac\'s cell 17 print)', 100 * lead.cases.sum() / total,
                lead.share_pct.sum(), 1e-9)

    p = top.iloc[::-1]  # most tickets on top
    is_lead = p.model.isin(lead.model).to_numpy()
    fig, ax = style.figure(10, FIXED_IN + ROW_IN * len(p))
    y = np.arange(len(p))
    ax.barh(y, p.cases, height=BAR_H, color=np.where(is_lead, style.BLUE, style.GRAY_LIGHT), linewidth=0)
    for yi, n in zip(y, p.cases):
        ax.text(n + p.cases.max() * 0.01, yi, f'{n:,}  ({style.pct(n / total)})', va='center', ha='left',
                fontsize=9.5, color=style.INK2,
                bbox=dict(boxstyle='square,pad=0.15', fc=style.SURFACE, ec='none'))  # hides gridlines behind text
    ax.set_yticks(y)
    ax.set_yticklabels(p.model, color=style.INK2)
    ax.set_ylim(-0.6, len(p) - 0.4)
    ax.set_xlim(0, p.cases.max() * 1.2)   # headroom for the value labels
    style.style_axes(ax, grid='x', baseline='left')
    style.thousands_axis(ax.xaxis)
    ax.set_xlabel('Tickets, full case export')

    biggest_rest = rest.iloc[0]
    style.frame(
        fig,
        f'Top {N_HIGHLIGHT} of {len(d)} models hold {style.pct(lead.cases.sum() / total)} of all tickets; '
        f'{lead.model.iloc[0]} alone has {style.pct(lead.cases.iloc[0] / total)}',
        f'The {TOP_N} models with the most tickets among all {total:,} in the case export '
        f'({zac_data.period_text(rq)}; planned work, cancelled and duplicate cases included). '
        f'Together they hold {style.pct(top.cases.sum() / total)}. '
        f'Share of all tickets in brackets; blue = the top {N_HIGHLIGHT}.',
        notes=[f'Model = the model recorded on the ticket. Not shown: the other {len(rest)} models, '
               f'{int(rest.cases.sum()):,} tickets ({style.pct(rest.cases.sum() / total)}) in all; the largest is '
               f'{biggest_rest.model} ({int(biggest_rest.cases):,} tickets).',
               'Chart zac_05 compares telemetry machine types by ticket rate, with its own ticket population and '
               'denominator (zac_05_machine_type_rates.png).',
               'Source: verification/outputs/repro_sql_model_workload.csv (Zac\'s SQL, notebook cell 17); totals from '
               'repro_sql_record_quality.csv.'],
        definitions=[NOT_ADJUSTED])
    return [style.save(fig, out_dir / PNG)]


if __name__ == '__main__':
    plot()
