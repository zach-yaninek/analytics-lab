#!/usr/bin/env python3
"""Slide version of Zac's figure 7 (viz/zac_notebook/zac_07_repeat_contact.py): repeat-contact rate for the ten
highest-volume models.

Same models, order, bars, values, colours and all-models line as the full chart. The model labels drop the ticket
counts; the definitions, the leading model's concentration and the models not shown go to the speaker notes.

Output:  viz/figures/slides/zac_07_repeat_contact.png
Run:     cd /home/user/analytics-lab && python3 -I viz/slides/zac_07_repeat_contact_slide.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# python3 -I leaves the script directory off sys.path
sys.path[:0] = [str(HERE), str(HERE.parent / 'style'), str(HERE.parent / 'zac_notebook')]
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import ipa_style as style  # noqa: E402
import slides  # noqa: E402
import zac_07_repeat_contact as full  # noqa: E402
import zac_data  # noqa: E402


def plot(out_dir=slides.FIG_DIR):
    rm, rs = zac_data.load('repeat_by_model'), zac_data.load('repeat_summary').iloc[0]
    robust = pd.read_csv(zac_data.OUTPUTS / 'audit_case_repeat_by_model_robustness.csv').set_index('model')
    eligible, repeats = int(rm.eligible_tickets.sum()), int(rm.repeat_tickets.sum())
    overall = 100 * repeats / eligible
    style.check('slide zac_07 overall rate = repeat_summary repeat_pct', rs.repeat_pct, overall, 1e-9)
    ranked = rm.sort_values('eligible_tickets', ascending=False, kind='mergesort')
    shown, rest = ranked.head(full.TOP_N), ranked.iloc[full.TOP_N:]
    by_rate = shown.sort_values(['repeat_pct', 'model'], ascending=[False, True], kind='mergesort')
    lead = by_rate.iloc[0]
    rb = robust.loc[lead.model]

    d = by_rate.iloc[::-1]  # highest rate on top
    is_lead = (d.model == lead.model).to_numpy()
    fig, ax = slides.figure()
    y = np.arange(len(d))
    xmax = d.repeat_pct.max() * 1.15
    pad, label_w = xmax * 0.01, xmax * 0.075  # value-label offset and approximate width (5 characters), data units
    ax.axvline(overall, color=style.INK2, lw=1, zorder=1)
    ax.barh(y, d.repeat_pct, height=full.BAR_H, color=np.where(is_lead, style.BLUE, style.GRAY_LIGHT), linewidth=0,
            zorder=2)
    ax.text(overall + pad, len(d) - 0.45, f'All models: {overall:.1f}%', va='bottom', ha='left', fontsize=9.5,
            color=style.INK2)
    for yi, row, hl in zip(y, d.itertuples(), is_lead):
        # Right of the bar end, unless that lands on the all-models line: then inside the bar end (as the full chart).
        on_line = row.repeat_pct < overall < row.repeat_pct + 2 * pad + label_w
        x, ha = (row.repeat_pct - pad, 'right') if on_line else (row.repeat_pct + pad, 'left')
        ax.text(x, yi, f'{row.repeat_pct:.1f}%', va='center', ha=ha, fontsize=9.5,
                color=style.SURFACE if on_line and hl else style.INK if hl else style.INK2,
                weight='bold' if hl else 'normal')
    ax.set_yticks(y)
    ax.set_yticklabels(d.model, color=style.INK2)
    ax.set_ylim(-0.6, len(d) + 0.1)
    ax.set_xlim(0, xmax)
    style.style_axes(ax, grid='x', baseline='left')
    style.pct_axis(ax.xaxis)
    ax.set_xlabel('Unplanned tickets followed by another within 30 days')

    talk = [zac_data.UNPLANNED_DEFINITION, zac_data.REPEAT_DEFINITION,
            f'Shown: the {full.TOP_N} models with the most eligible index tickets '
            f'({int(shown.eligible_tickets.sum()):,} of {eligible:,}; case export {zac_data.period_text()}), sorted by '
            f'rate. Eligible tickets per model: '
            + ', '.join(f'{r.model} {r.eligible_tickets:,}' for r in by_rate.itertuples()) + '.',
            f'All-models rate: {repeats:,} repeats among {eligible:,} eligible tickets on {int(rs.machines):,} '
            f'machines. Per ticket, so machines with many tickets count many times.',
            f'{int(rb.repeats_top3_machines)} of {lead.model}\'s {int(lead.repeat_tickets)} repeats are on '
            f'{full.TOP_MACHINES} of its {int(rb.machines)} machines; without them its rate is '
            f'{rb.repeat_pct_without_top3_machines:.1f}%.',
            f'Not shown: the other {len(rest)} models, {int(rest.eligible_tickets.sum()):,} eligible tickets with a '
            f'repeat rate of {100 * rest.repeat_tickets.sum() / rest.eligible_tickets.sum():.1f}% together.']
    return [slides.finish(fig, Path(out_dir) / full.PNG,
                          f'Busiest {full.TOP_N} models: {lead.model} repeats most, {lead.repeat_pct:.1f}% vs '
                          f'{overall:.1f}% overall',
                          f'Repeat-contact rate, the {full.TOP_N} models with the most unplanned tickets, '
                          f'{zac_data.period_text()}', talk)]


if __name__ == '__main__':
    plot()
