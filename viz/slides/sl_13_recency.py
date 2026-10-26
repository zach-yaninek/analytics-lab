#!/usr/bin/env python3
"""Slide chart 13: how far before a ticket its own codes appear (association item 3).

The slide version of viz/association/as_02_recency.py: share of tickets with their Category's code set present within
k before the ticket (blue) against the same machine's control window (gray). Up to 7 days the same 1,439 tickets are
used at every point; the 30-day point uses the last-10 list on 1,469 tickets and is drawn apart (hollow).

Input:  verification/outputs/assoc/as_recency.csv
Output: viz/figures/slides/sl_13_recency.png (wide card)
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'association')]
import numpy as np  # noqa: E402

import assoc  # noqa: E402
import deck_style as S  # noqa: E402

PNG = 'sl_13_recency.png'
LABELS = {0.5: '30 min', 1.0: '1 h', 2.0: '2 h', 6.0: '6 h', 24.0: '1 day', 168.0: '7 days', 720.0: '30 days'}


def plot(out_dir=S.FIG_DIR):
    r = assoc.load('recency')
    t = r[r.curve == 'target'].sort_values('k')
    for row in t.itertuples():
        S.check(f'sl_13 share at k={row.k:g} = n_T / n', row.pT, row.n_T / row.n_pairs, 1e-12)
    first, week, month = (t[t.k == k].iloc[0] for k in (0.5, assoc.K7, assoc.K30))
    S.check('sl_13 30 min: 23% vs 2%', 23 + 2 / 100, round(first.pT * 100) + round(first.pC * 100) / 100, 1e-9)
    S.check('sl_13 7 days: 68% vs 50%', 68 + 50 / 100, round(week.pT * 100) + round(week.pC * 100) / 100, 1e-9)
    S.check('sl_13 30 days: 76% vs 65%', 76 + 65 / 100, round(month.pT * 100) + round(month.pC * 100) / 100, 1e-9)
    S.check('sl_13 1,439 tickets up to 7 days', 1439, int(week.n_pairs))
    S.check('sl_13 1,469 tickets at 30 days', 1469, int(month.n_pairs))

    fig, ax = S.figure(S.WIDE)
    line = (t.k <= assoc.K7).to_numpy()
    x = np.arange(len(t), dtype=float)
    x[~line] += 0.6
    ax.plot(x[line], 100 * t.pT[line], color=S.BLUE, lw=3, marker='o', ms=9, zorder=3, label='Before the ticket')
    ax.plot(x[line], 100 * t.pC[line], color=S.GRAY, lw=3, marker='o', ms=9, zorder=2,
            label='Control: same machine, 35 days earlier')
    ax.scatter(x[~line], 100 * t.pT[~line], s=90, facecolors=S.WHITE, edgecolors=S.BLUE, linewidths=2.5, zorder=3)
    ax.scatter(x[~line], 100 * t.pC[~line], s=90, facecolors=S.WHITE, edgecolors=S.GRAY, linewidths=2.5, zorder=2)
    for xi, a, b in zip(x, t.pT, t.pC):
        ax.text(xi, 100 * a + 4, f'{a:.0%}', ha='center', va='bottom', fontsize=S.FONT, color=S.INK, weight='bold')
        ax.text(xi, 100 * b - 4.5, f'{b:.0%}', ha='center', va='top', fontsize=S.FONT, color=S.INK2)
    leg = ax.legend(loc='upper left', fontsize=S.FONT, handlelength=1.6, borderaxespad=0.2)
    for txt, col in zip(leg.get_texts(), (S.BLUE, S.INK2)):
        txt.set_color(col)
    ax.set_xticks(x)
    ax.set_xticklabels([LABELS[k] if k <= assoc.K7 else '30 days*' for k in t.k], fontsize=S.TICK)
    ax.set_xlim(-0.4, x[-1] + 0.5)
    ax.set_ylim(-9, 92)
    ax.set_yticks([0, 20, 40, 60, 80])
    S.pct_axis(ax.yaxis)
    S.style_axes(ax, grid='y', baseline=None)
    ax.set_xlabel(f'Own code set present within this long before the ticket  (*30 days: last-10 list, '
                  f'{int(month.n_pairs):,} tickets)', fontsize=S.SMALL)
    ax.set_ylabel('Share of tickets')
    return [S.save(fig, Path(out_dir) / PNG)]


if __name__ == '__main__':
    plot()
