#!/usr/bin/env python3
"""Slide chart 1: what the non-success telemetry is made of (full database, all 118.0 M transactions).

Replaces the midterm deck's "Four-fifths of failures are stock-outs or mechanical issues" chart, which counted door
events as mechanical. Here each of the team's provisional buckets stands on its own, as in the executive summary
(finding 5): stock-outs and door events are most of the non-success transactions; mechanical and electronic fault
codes are about a ninth. Shares of the 7.88 M non-success transactions; Undefined and Malformed (0.06%) are left out.

Input:  verification/outputs/db/db_telemetry_buckets.csv
Output: viz/figures/slides/sl_01_nonsuccess_mix.png (half card)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import deck_style as S  # noqa: E402

PNG = 'sl_01_nonsuccess_mix.png'
ROWS = [('Stock-out', 'Stock-out', S.BLUE), ('Door issue', 'Door issue', S.BLUE),
        ('Mechanical fault', 'Mechanical fault', S.NAVY), ('User behavior', 'User behavior', S.GRAY_LIGHT),
        ('Incomplete transaction', 'Incomplete', S.GRAY_LIGHT), ('Operational status', 'Operational', S.GRAY_LIGHT),
        ('Electronics/software/comms', 'Electronics', S.NAVY)]


def plot(out_dir=S.FIG_DIR):
    b = pd.read_csv(S.OUT / 'db' / 'db_telemetry_buckets.csv').set_index('bucket')
    total = b.transactions.sum()
    non = total - b.loc['Success', 'transactions']
    share = {k: b.loc[k, 'transactions'] / non * 100 for k, _, _ in ROWS}
    S.check('sl_01 all transactions = 118,047,569', 118047569, total)
    S.check('sl_01 stock-out + door share of non-success (69.1%)', 69.1,
            round(share['Stock-out'] + share['Door issue'], 1))
    S.check('sl_01 mechanical + electronics share of all transactions (0.75%)', 0.75,
            round((b.loc['Mechanical fault', 'transactions'] + b.loc['Electronics/software/comms', 'transactions'])
                  / total * 100, 2))
    S.check('sl_01 non-success share of all transactions (6.7%)', 6.7, round(non / total * 100, 1))

    fig, ax = S.figure(S.HALF)
    y = np.arange(len(ROWS))[::-1]
    for yi, (key, label, col) in zip(y, ROWS):
        v = share[key]
        ax.barh(yi, v, height=0.62, color=col, zorder=2)
        n = b.loc[key, 'transactions']
        ax.text(v + 0.8, yi, f'{v:.1f}%', va='center', ha='left', fontsize=S.FONT, color=S.INK, weight='bold')
        ax.annotate(f'{n / 1e6:.2f} M' if n >= 1e5 else f'{n / 1e3:.0f} k', (v, yi), xytext=(66, 0),
                    textcoords='offset points', va='center', ha='left', fontsize=S.SMALL, color=S.INK2)
    ax.set_yticks(y)
    ax.set_yticklabels([r[1] for r in ROWS], color=S.INK, fontsize=S.FONT)
    ax.set_xlim(0, 52)
    ax.set_xticks([0, 10, 20, 30, 40, 50])
    S.pct_axis(ax.xaxis)
    S.style_axes(ax, grid='x', baseline='left')
    ax.set_xlabel(f'Share of the {non / 1e6:.2f} M non-success transactions')
    return [S.save(fig, Path(out_dir) / PNG)]


if __name__ == '__main__':
    plot()
