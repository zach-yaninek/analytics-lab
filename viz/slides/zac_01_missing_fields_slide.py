#!/usr/bin/env python3
"""Slide version of Zac's figure 1 (viz/zac_notebook/zac_01_missing_fields.py): how often each ticket field is
missing in the case export.

Same fields, order, bars and colours as the full chart. The value labels keep the percentages and drop the ticket
counts; the definition of missing, the population and the notes go to the speaker notes.

Output:  viz/figures/slides/zac_01_missing_fields.png
Run:     cd /home/user/analytics-lab && python3 -I viz/slides/zac_01_missing_fields_slide.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# python3 -I leaves the script directory off sys.path
sys.path[:0] = [str(HERE), str(HERE.parent / 'style'), str(HERE.parent / 'zac_notebook')]
import numpy as np  # noqa: E402

import ipa_style as style  # noqa: E402
import slides  # noqa: E402
import zac_01_missing_fields as full  # noqa: E402
import zac_data  # noqa: E402


def plot(out_dir=slides.FIG_DIR):
    f = zac_data.load('field_completeness')
    rq = zac_data.load('record_quality')
    sg = zac_data.load('service_groups').set_index('service_group').cases
    n = int(rq.cases.iloc[0])
    f['pct'] = 100 * f.missing / n
    style.check('slide zac_01 missing_pct = missing / all tickets', 0, float((f.pct - f.missing_pct).abs().max()), 1e-9)
    d = f.sort_values(['pct', 'field'], ascending=[True, False], kind='mergesort')  # largest share on top
    top, second = d.iloc[-1], d.iloc[-2]

    fig, ax = slides.figure()
    y = np.arange(len(d))
    ax.barh(y, d.pct, height=0.5, color=[style.BLUE if fld == top.field else style.GRAY_LIGHT for fld in d.field],
            linewidth=0)
    for yi, row in zip(y, d.itertuples()):
        is_top = row.field == top.field
        ax.text(row.pct + d.pct.max() * 0.01, yi, f'{row.pct:.1f}%' if row.missing else '0%', va='center',
                ha='left', fontsize=9.5, color=style.INK if is_top else style.INK2,
                weight='bold' if is_top else 'normal')
    ax.set_yticks(y)
    ax.set_yticklabels(d.field, color=style.INK2)
    ax.set_ylim(-0.6, len(d) - 0.4)
    ax.set_xlim(0, 5 * np.ceil(d.pct.max() * 1.15 / 5))  # whole 5% steps, so the top label ends inside the grid
    style.style_axes(ax, grid='x', baseline='left')
    style.pct_axis(ax.xaxis)
    ax.set_xlabel('Tickets with the field missing')

    by_field = f.set_index('field').missing
    blank_n = sum(int(sg[g]) for g in full.GROUP_TEXT)
    sub_n = int(by_field[full.SUBCATEGORY])
    blank_txt = ' and '.join(f'{text} ({int(sg[g]):,})' for g, text in full.GROUP_TEXT.items())
    talk = ['Missing = the field is empty or whitespace only in the case export (Zac\'s import stores these as '
            'NULL). Trouble Reported and Trouble Resolution are free text: only whether they are filled in is '
            'counted.',
            f'Population: all {n:,} tickets in the case export ({zac_data.period_text(rq)}), before any exclusions. '
            f'{top.field}: {int(top.missing):,} tickets.',
            f'{full.SUBCATEGORY} is blank on every {blank_txt} ticket: {blank_n:,} of its {sub_n:,} missing values '
            f'({style.pct(blank_n / sub_n, 0)}).',
            f'The {int(by_field["Trouble Code"]):,} tickets without a Trouble Code are the same tickets as Zac\'s '
            f'"Missing trouble code" service group.']
    return [slides.finish(fig, Path(out_dir) / 'zac_01_missing_fields.png',
                          f'{top.field.removeprefix("Trouble Code ")} is missing on {top.pct:.0f}% of tickets; every '
                          f'other field on {second.pct:.1f}% or less',
                          f'Share of all tickets with each field missing, {zac_data.period_text(rq)}', talk)]


if __name__ == '__main__':
    plot()
