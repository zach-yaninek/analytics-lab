#!/usr/bin/env python3
"""Slide version of Zac's figure 10 (viz/zac_notebook/zac_10_repeat_composition.py): what follows an eligible
unplanned ticket within 30 days, as one 100% bar.

Same bar, segments, colours, shares, leaders and bracket as the full chart. The labels drop the ticket counts; the
definitions, the population and the notes go to the speaker notes.

Output:  viz/figures/slides/zac_10_repeat_composition.png
Run:     cd /home/user/analytics-lab && python3 -I viz/slides/zac_10_repeat_composition_slide.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# python3 -I leaves the script directory off sys.path
sys.path[:0] = [str(HERE), str(HERE.parent / 'style'), str(HERE.parent / 'zac_notebook')]
import pandas as pd  # noqa: E402

import ipa_style as style  # noqa: E402
import slides  # noqa: E402
import zac_10_repeat_composition as full  # noqa: E402
import zac_data  # noqa: E402

PAD = 0.8  # extra y units above and below the full chart's layout


def plot(out_dir=slides.FIG_DIR):
    r = zac_data.load('repeat_summary').iloc[0]
    comp = pd.read_csv(zac_data.OUTPUTS / 'audit_case_repeat_composition.csv').set_index('repeat_composition').repeats
    eligible, repeats, same = int(r.eligible_tickets), int(r.repeat_tickets), int(r.same_category_repeats)
    parts = [('No repeat within 30 days', eligible - repeats, style.GRAY_LIGHT),
             ('Repeat, different or missing category', repeats - same, style.BLUE),
             ('Repeat, same category', same, style.ORANGE)]
    shares = [100 * n / eligible for _, n, _ in parts]
    starts = [sum(shares[:i]) for i in range(len(shares))]
    style.check('slide zac_10 repeat share = repeat_pct', r.repeat_pct, shares[1] + shares[2], 1e-9)

    fig, ax = slides.figure()
    fig.get_layout_engine().set(w_pad=0.12)  # no tick labels: start the bar at the text margin (as the full chart)
    for (_, _, color), share, start in zip(parts, shares, starts):
        ax.barh(0, share, left=start, height=full.BAR, color=color, linewidth=0)
        ax.text(start + share / 2, 0, f'{share:.1f}%', ha='center', va='center', fontsize=10, weight='bold',
                color='white' if color == style.BLUE else style.INK)
    top = full.BAR / 2
    ax.text(0, top + 0.12, parts[0][0], ha='left', va='bottom', fontsize=9.5, color=style.INK2)
    for i, row in zip((1, 2), full.LABEL_ROWS):
        mid = starts[i] + shares[i] / 2
        ax.annotate(parts[i][0], xy=(mid, -top), xytext=(mid - 1.2, row), ha='right', va='center', fontsize=9.5,
                    color=style.INK2,
                    arrowprops={'arrowstyle': '-', 'color': style.MUTED, 'lw': 0.8, 'shrinkA': 3, 'shrinkB': 0,
                                'relpos': (1, 0.5), 'connectionstyle': 'angle,angleA=0,angleB=90,rad=0'})
    x0, x1 = starts[1], 100
    ax.plot([x0, x0, x1, x1], [top + 0.06, full.BRACKET, full.BRACKET, top + 0.06], color=style.MUTED, lw=0.8,
            solid_capstyle='butt', solid_joinstyle='miter')
    ax.text(x1, full.BRACKET + 0.08, f'Repeat contact within 30 days: {r.repeat_pct:.1f}%', ha='right', va='bottom',
            fontsize=9.5, weight='bold', color=style.INK)
    ax.set_xlim(0, 100)
    # The full chart's vertical layout, with PAD units of space above and below, so the 16:9 page does not
    # stretch the bar and the label rows.
    ax.set_ylim(full.LABEL_ROWS[-1] - 0.3 - PAD, full.BRACKET + 0.4 + PAD)
    ax.set_xticks([])
    ax.set_yticks([])
    style.style_axes(ax, grid=None, baseline=None)

    talk = [zac_data.UNPLANNED_DEFINITION, zac_data.REPEAT_DEFINITION,
            f'Population: {eligible:,} eligible unplanned index tickets on {int(r.machines):,} machines (case export '
            f'{zac_data.period_text()}), by what followed on the same machine within 30 days: '
            + ', '.join(f'{name.lower()} {n:,}' for name, n, _ in parts) + '.',
            f'Same category = both tickets have a category and it is the same (Zac\'s rule): {same:,} of the '
            f'{repeats:,} repeats ({style.pct(same / repeats, 0)}). Different or missing = the categories differ or '
            f'either ticket has none; among them are the {int(comp["followup_category_missing"])} repeats whose '
            f'follow-up has no category.',
            'Per ticket, so machines with many tickets count many times.']
    return [slides.finish(fig, Path(out_dir) / full.PNG,
                          f'{r.repeat_pct:.1f}% of unplanned tickets have a 30-day repeat; '
                          f'{r.same_category_repeat_pct:.1f}% a same-category one',
                          f'What follows an unplanned ticket on the same machine within 30 days, '
                          f'{zac_data.period_text()}', talk)]


if __name__ == '__main__':
    plot()
