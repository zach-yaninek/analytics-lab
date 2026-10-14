#!/usr/bin/env python3
"""Zac's figure 7: repeat-contact rate for the ten highest-volume models.

Recreates 07_repeat_contact.png from Zac's notebook (cell 31: his view repeat_cases over service_cases, query
repeat_by_model, and his bar() helper from cell 9 on repeat_models.head(10)). Same population (unplanned index tickets
opened before 2 Aug 2026, each with a full 30-day window), same selection (the 10 models with the most eligible
tickets, his ORDER BY eligible_tickets DESC) and the same metric (100 x tickets followed by another unplanned ticket on
the same machine within 0 to 30 days / eligible tickets), sorted by rate as he drew it, with the same one-decimal
values. Added: the model the title names in blue, each model's eligible tickets on the axis, a line at the rate over
all models (his printed "Repeat contact is observed after ...% of eligible tickets"), the leading model's rate without
its three busiest machines, and the models left out by the top-10 cut whose rates rival the leader's.

Inputs:  zac_data.load('repeat_by_model')   model, eligible_tickets, repeat_tickets, repeat_pct (Zac's SQL, cell 31)
         zac_data.load('repeat_summary')    totals over all eligible tickets (cell 31): rate, machines
         verification/outputs/audit_case_repeat_by_model_robustness.csv   machines per model, repeats on its top 3
                                            machines and the rate without them
Output:  viz/figures/zac_07_repeat_contact.png
Run:     cd /home/user/analytics-lab && python3 -I viz/zac_notebook/zac_07_repeat_contact.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]  # python3 -I leaves the script directory off sys.path
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import ipa_style as style  # noqa: E402
import zac_data  # noqa: E402

TOP_N = 10        # Zac's selection: repeat_models.head(10), ordered by eligible_tickets DESC (notebook cell 31)
N_NAMED = 3       # the subtitle names the models with the three highest rates
TOP_MACHINES = 3  # the audit's concentration measure: repeats on a model's 3 busiest machines
PNG = 'zac_07_repeat_contact.png'
ROW_IN = 0.36     # inches per bar row
BAR_H = 0.5       # bar thickness as a share of the row pitch
ORDINALS = ('first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth', 'tenth',
            'eleventh')


def plot(out_dir=zac_data.FIG_DIR):
    out_dir = Path(out_dir)
    rm, rs = zac_data.load('repeat_by_model'), zac_data.load('repeat_summary').iloc[0]
    robust = pd.read_csv(zac_data.OUTPUTS / 'audit_case_repeat_by_model_robustness.csv').set_index('model')

    # Checks: the models cover every eligible ticket and repeat once; rates are ratios; the overall rate is Zac's.
    eligible, repeats = int(rm.eligible_tickets.sum()), int(rm.repeat_tickets.sum())
    style.check('zac_07 eligible tickets = repeat_summary', int(rs.eligible_tickets), eligible)
    style.check('zac_07 repeat tickets = repeat_summary', int(rs.repeat_tickets), repeats)
    style.check('zac_07 repeat_pct = 100 x repeats / eligible', 0,
                float((100 * rm.repeat_tickets / rm.eligible_tickets - rm.repeat_pct).abs().max()), 1e-9)
    overall = 100 * repeats / eligible  # Zac's printed overall rate (cell 31)
    style.check('zac_07 overall rate = repeat_summary repeat_pct', rs.repeat_pct, overall, 1e-9)
    # The verification audit counts the same tickets and repeats for every model (it adds the machine columns).
    aud = robust.loc[rm.model]
    style.check('zac_07 audit eligible/repeats = Zac\'s table, all models', 0,
                float(np.abs(aud[['eligible_tickets', 'repeat_tickets']].to_numpy()
                             - rm[['eligible_tickets', 'repeat_tickets']].to_numpy()).max()))

    # Zac's top-10 rule: highest eligible_tickets first (cell 31).
    ranked = rm.sort_values('eligible_tickets', ascending=False, kind='mergesort')
    same_order = ranked.model.head(TOP_N).tolist() == rm.model.head(TOP_N).tolist()
    style.check('zac_07 top 10 = Zac\'s table order', 1, int(same_order))
    style.check('zac_07 no tie at the top-10 boundary', 1,
                int(ranked.eligible_tickets.iloc[TOP_N - 1] > ranked.eligible_tickets.iloc[TOP_N]))
    shown, rest = ranked.head(TOP_N), ranked.iloc[TOP_N:]
    by_rate = shown.sort_values(['repeat_pct', 'model'], ascending=[False, True], kind='mergesort')
    lead, low = by_rate.iloc[0], by_rate.iloc[-1]
    named, middle = by_rate.head(N_NAMED), by_rate.repeat_pct.iloc[N_NAMED:-1]  # middle: between those and the lowest

    # The leading model's rate without its 3 busiest machines (audit): repeats per ticket count every ticket on a
    # machine, so a few machines with many tickets can carry a small model's rate.
    rb = robust.loc[lead.model]
    k_rest = lead.repeat_tickets - rb.repeats_top3_machines  # repeats on its other machines
    n_rest = round(100 * k_rest / rb.repeat_pct_without_top3_machines)  # their tickets, implied by the audit rate
    style.check('zac_07 rate without top-3 machines = repeats left / whole tickets (audit, 2 decimals)',
                rb.repeat_pct_without_top3_machines, 100 * k_rest / n_rest, 0.005)
    # Models below the top-10 cut: the next by volume and any with a higher rate than the leader.
    nxt, cut = rest.iloc[0], shown.iloc[-1]
    nxt_rank = 1 + int((shown.repeat_pct > nxt.repeat_pct).sum())  # its place among the shown rates
    above = rest[(rest.repeat_pct > lead.repeat_pct) & (rest.model != nxt.model)]
    left_out = (f'The next by volume, {nxt.model} ({int(nxt.eligible_tickets)} tickets, '
                f'{int(cut.eligible_tickets - nxt.eligible_tickets)} fewer than {cut.model}), would rank '
                f'{ORDINALS[nxt_rank - 1]} at {nxt.repeat_pct:.1f}%.')
    left_out += ''.join(f' {t.model} tops {lead.model} at {t.repeat_pct:.1f}%, but on just {t.eligible_tickets} '
                        f'tickets from {int(robust.machines[t.model])} machines.' for t in above.itertuples())

    d = by_rate.iloc[::-1]  # highest rate on top, as in Zac's chart
    is_lead = (d.model == lead.model).to_numpy()
    fig, ax = style.figure(10, 4.3 + ROW_IN * len(d))
    y = np.arange(len(d))
    xmax = d.repeat_pct.max() * 1.15
    pad, label_w = xmax * 0.01, xmax * 0.075  # value-label offset and approximate width (5 characters), data units
    ax.axvline(overall, color=style.INK2, lw=1, zorder=1)  # under the bars, as the overall line in zac_05
    ax.barh(y, d.repeat_pct, height=BAR_H, color=np.where(is_lead, style.BLUE, style.GRAY_LIGHT), linewidth=0,
            zorder=2)
    ax.text(overall + pad, len(d) - 0.45, f'All models: {overall:.1f}%', va='bottom', ha='left', fontsize=9.5,
            color=style.INK2)
    for yi, row, hl in zip(y, d.itertuples(), is_lead):
        # Right of the bar end, unless that lands on the all-models line: then inside the bar end (same rule in zac_05).
        on_line = row.repeat_pct < overall < row.repeat_pct + 2 * pad + label_w
        x, ha = (row.repeat_pct - pad, 'right') if on_line else (row.repeat_pct + pad, 'left')
        ax.text(x, yi, f'{row.repeat_pct:.1f}%', va='center', ha=ha, fontsize=9.5,
                color=style.SURFACE if on_line and hl else style.INK if hl else style.INK2,
                weight='bold' if hl else 'normal')
    ax.set_yticks(y)
    ax.set_yticklabels([f'{m}  ·  {n:,} tickets' for m, n in zip(d.model, d.eligible_tickets)], color=style.INK2)
    ax.set_ylim(-0.6, len(d) + 0.1)
    ax.set_xlim(0, xmax)
    style.style_axes(ax, grid='x', baseline='left')
    style.pct_axis(ax.xaxis)
    ax.set_xlabel('Share of eligible index tickets followed by another unplanned ticket within 30 days')

    style.frame(
        fig,
        f'Busiest {TOP_N} models: {lead.model} repeats most, {lead.repeat_pct:.1f}% vs {overall:.1f}% overall',
        f'Repeat-contact rate for the {TOP_N} models with the most eligible unplanned index tickets '
        f'({int(shown.eligible_tickets.sum()):,} of {eligible:,}; case export {zac_data.period_text()}), sorted by '
        f'rate. {", ".join(named.model.iloc[:-1])} '
        f'and {named.model.iloc[-1]} lie {named.repeat_pct.min() - overall:.0f} to '
        f'{named.repeat_pct.max() - overall:.0f} points above the all-models rate; the next '
        f'{len(middle)} between {middle.min():.1f}% and {middle.max():.1f}%; {low.model} is lowest at '
        f'{low.repeat_pct:.1f}%. {int(rb.repeats_top3_machines)} of {lead.model}\'s {int(lead.repeat_tickets)} '
        f'repeats are on {TOP_MACHINES} of its {int(rb.machines)} machines; without them its rate is '
        f'{rb.repeat_pct_without_top3_machines:.1f}%.',
        notes=[f'Tickets = eligible index tickets per model (the denominator). The line marks the rate over all '
               f'{len(rm)} models: {repeats:,} repeats among {eligible:,} eligible tickets on {int(rs.machines):,} '
               f'machines. Per ticket, so machines with many tickets count many times.',
               f'Not shown: the other {len(rest)} models, {int(rest.eligible_tickets.sum()):,} eligible tickets '
               f'with a repeat rate of {100 * rest.repeat_tickets.sum() / rest.eligible_tickets.sum():.1f}% '
               f'together. {left_out}',
               'Source: verification/outputs/repro_sql_repeat_by_model.csv and repro_sql_repeat_summary.csv (Zac\'s '
               'SQL, notebook cell 31); machine counts, top-3-machine repeats and the rate without them from '
               'verification/outputs/audit_case_repeat_by_model_robustness.csv.'],
        definitions=[zac_data.UNPLANNED_DEFINITION, zac_data.REPEAT_DEFINITION])
    return [style.save(fig, out_dir / PNG)]


if __name__ == '__main__':
    plot()
