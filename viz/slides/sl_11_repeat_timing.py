#!/usr/bin/env python3
"""Slide chart 11: how soon repeat contacts follow (executive summary finding 8).

Cumulative share of the 1,574 30-day repeat contacts (unplanned tickets followed by another unplanned ticket on the
same machine within 30 days, Zac's definition) by days from the index ticket to the follow-up. 40% come within a
week. The 23.6% repeat rate (1,574 of 6,665 eligible tickets) and its 22.0% sensitivity go on the slide beside it.

Input:  verification/outputs/audit_case_repeat_gap_bins.csv, repro_sql_repeat_summary.csv
Output: viz/figures/slides/sl_11_repeat_timing.png (wide card)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pandas as pd  # noqa: E402

import deck_style as S  # noqa: E402

PNG = 'sl_11_repeat_timing.png'
DAYS = {'(0,1h]': 1 / 24, '(1h,4h]': 4 / 24, '(4h,1d]': 1, '(1d,2d]': 2, '(2d,7d]': 7, '(7d,14d]': 14, '(14d,30d]': 30}


def plot(out_dir=S.FIG_DIR):
    g = pd.read_csv(S.OUT / 'audit_case_repeat_gap_bins.csv')
    r = pd.read_csv(S.OUT / 'repro_sql_repeat_summary.csv').iloc[0]
    g = g[g.gap_bin.isin(DAYS)]
    total = int(g.repeats.sum())
    x = [0.0] + [DAYS[b] for b in g.gap_bin]
    y = [0.0] + list(100 * g.cum_repeats / total)
    week = 100 * int(g.loc[g.gap_bin == '(2d,7d]', 'cum_repeats'].iloc[0]) / total
    S.check('sl_11 repeats = Zac repeat_tickets (1,574)', int(r.repeat_tickets), total)
    S.check('sl_11 repeat rate 23.6%', 23.6, round(float(r.repeat_pct), 1))
    S.check('sl_11 within 7 days = 40%', 40, round(week))
    S.check('sl_11 cumulative reaches 100%', 100, y[-1], 1e-9)

    fig, ax = S.figure(S.WIDE)
    ax.axvspan(0, 7, color='#EAF0F7', zorder=0)
    ax.plot(x, y, color=S.BLUE, lw=3, marker='o', ms=8, zorder=3)
    for d, v in zip(x, y):
        if d in (2, 7, 14, 30):
            ax.text(d + (0.4 if d < 30 else -0.4), v - 3 if d != 30 else v - 6, f'{v:.0f}%', ha='left' if d < 30 else 'right',
                    va='top', fontsize=S.FONT, weight='bold' if d == 7 else 'normal',
                    color=S.INK if d == 7 else S.INK2)
    ax.text(3.5, 92, 'First week:\n40% of repeats', ha='center', va='top', fontsize=S.FONT, color=S.BLUE,
            weight='bold')
    ax.set_xlim(0, 31)
    ax.set_xticks([0, 2, 7, 14, 21, 30])
    ax.set_xticklabels(['0', '2', '7', '14', '21', '30 days'])
    ax.set_ylim(0, 104)
    ax.set_yticks([0, 25, 50, 75, 100])
    S.pct_axis(ax.yaxis)
    S.style_axes(ax, grid='y', baseline='bottom')
    ax.set_xlabel(f'Days from the ticket to the follow-up ({total:,} repeat contacts)')
    ax.set_ylabel('Share of repeats, cumulative')
    return [S.save(fig, Path(out_dir) / PNG)]


if __name__ == '__main__':
    plot()
