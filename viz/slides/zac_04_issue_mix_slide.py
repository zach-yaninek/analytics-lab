#!/usr/bin/env python3
"""Slide version of Zac's figure 4 (viz/zac_notebook/zac_04_issue_mix.py): the most frequent recorded categories among
unplanned tickets.

Same categories, bars and colours as the full chart. The value labels keep the shares and drop the ticket counts;
the definition of unplanned tickets, the population and the notes go to the speaker notes.

Output:  viz/figures/slides/zac_04_issue_mix.png
Run:     cd /home/user/analytics-lab && python3 -I viz/slides/zac_04_issue_mix_slide.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# python3 -I leaves the script directory off sys.path
sys.path[:0] = [str(HERE), str(HERE.parent / 'style'), str(HERE.parent / 'zac_notebook')]
import numpy as np  # noqa: E402

import ipa_style as style  # noqa: E402
import slides  # noqa: E402
import zac_04_issue_mix as full  # noqa: E402
import zac_data  # noqa: E402


def plot(out_dir=slides.FIG_DIR):
    im, rq = zac_data.load('issue_mix'), zac_data.load('record_quality')
    total = int(im.cases.sum())
    style.check('slide zac_04 share_pct = cases / unplanned total', 0,
                float((100 * im.cases / total - im.share_pct).abs().max()), 1e-9)
    ranked = im.sort_values(['cases', 'category'], ascending=[False, True], kind='mergesort')
    shown, rest = ranked.head(full.TOP_N), ranked.iloc[full.TOP_N:]
    lead, runner = shown.iloc[0], shown.iloc[1]

    d = shown.iloc[::-1]  # most tickets on top
    fig, ax = slides.figure()
    y = np.arange(len(d))
    ax.barh(y, d.cases, height=0.5, linewidth=0,
            color=[style.BLUE if c == lead.category else style.GRAY_LIGHT for c in d.category])
    for yi, row in zip(y, d.itertuples()):
        is_lead = row.category == lead.category
        ax.text(row.cases + d.cases.max() * 0.01, yi, f'{row.share_pct:.1f}%', va='center', ha='left', fontsize=9.5,
                color=style.INK if is_lead else style.INK2, weight='bold' if is_lead else 'normal')
    ax.set_yticks(y)
    ax.set_yticklabels(d.category, color=style.INK2)
    ax.set_ylim(-0.6, len(d) - 0.4)
    ax.set_xlim(0, d.cases.max() * 1.1)
    style.style_axes(ax, grid='x', baseline='left')
    style.thousands_axis(ax.xaxis)
    ax.set_xlabel('Unplanned tickets')

    period = zac_data.period_text(rq)
    n_named = int((im.category != full.MISSING).sum())
    talk = [zac_data.UNPLANNED_DEFINITION,
            f'Population: all {total:,} unplanned tickets, {period}. Bars show ticket counts, labels the share of '
            f'unplanned tickets; together the {full.TOP_N} rows hold {style.pct(shown.cases.sum() / total, 0)}.',
            f'{full.MISSING} = no category recorded (Zac keeps these as their own row). {full.NTF} = no fault was '
            f'found, recorded as a category.',
            f'Not shown: the other {len(rest)} of the {n_named} recorded categories, {int(rest.cases.sum()):,} tickets '
            f'({style.pct(rest.cases.sum() / total)}); the largest, {rest.category.iloc[0]}, has '
            f'{int(rest.cases.iloc[0]):,}.']
    return [slides.finish(fig, Path(out_dir) / 'zac_04_issue_mix.png',
                          f'{lead.category} leads with {lead.share_pct:.1f}% of unplanned tickets, '
                          f'{lead.cases / runner.cases:.1f}× the next category',
                          f'Unplanned tickets by Trouble Code Category, the {full.TOP_N} most frequent, {period}',
                          talk)]


if __name__ == '__main__':
    plot()
