#!/usr/bin/env python3
"""Slide chart 3: models' ticket rates against the fleet's once machine age is allowed for.

Slide version of the age-standardised results behind viz/fleet_exposure/fx_02_rate_by_model.py (its footer note on
the age-standardised ratios), from the same model table. Age-standardised ratio = a model's unplanned tickets over
the tickets its machines would generate at the fleet's rate for their age (joint model + age fit), with its 95%
interval; 1 = in line with the fleet age for age. One dot per model with its interval; blue = interval wholly above
1, gray = interval includes 1. Rows: the three models with the most tickets, the three small models whose
age-standardised interval is above 1, and alEx LC-D (above the fleet on the crude rate of fx_02, not once age is
allowed for), sorted by ratio. Every model shown has its own rate (at least 100 installed machine-months); the card
header counts the blue models against all 27 such models, checked here.

Input:  verification/outputs/fleet/fx_model_rates.csv, verification/outputs/fleet/fx_summary.json
Output: viz/figures/slides/sl_03_model_ratio.png (half card)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import deck_style as S  # noqa: E402

PNG = 'sl_03_model_ratio.png'
MODELS = ['LVD-Remote-2.0', 'LVRR-WP-2.0', 'MV-2.0', 'scrubBank 480', 'alEx SD 2.0', 'SD-64', 'alEx LC-D']
# The numbers drawn (ratio, 95% interval), as in the executive summary and the fx_02 footer note.
EXPECTED = {'LVD-Remote-2.0': (1.16, 1.05, 1.28), 'LVRR-WP-2.0': (1.12, 1.01, 1.25), 'MV-2.0': (0.93, 0.84, 1.04),
            'scrubBank 480': (2.58, 1.75, 3.79), 'alEx SD 2.0': (1.82, 1.32, 2.37), 'SD-64': (1.55, 1.06, 2.18),
            'alEx LC-D': (1.05, 0.83, 1.32)}
MACHINES = {'LVD-Remote-2.0': 1452, 'LVRR-WP-2.0': 1305, 'MV-2.0': 1151, 'scrubBank 480': 58, 'alEx SD 2.0': 98,
            'SD-64': 89, 'alEx LC-D': 551}  # machine counts drawn (as on the fx_02 axis labels)


def plot(out_dir=S.FIG_DIR):
    fleet = S.OUT / 'fleet'
    summary = json.loads((fleet / 'fx_summary.json').read_text())
    D, F = summary['definitions'], summary['fleet']
    m = pd.read_csv(fleet / 'fx_model_rates.csv')

    # Same logic as fx_02: models with their own rate; ratio = tickets / age-only expected; class = interval vs 1.
    S.check('sl_03 own rate = at least min_type_months (100) installed months', 0,
            int((m.own_rate != (m.months >= D['min_type_months'])).sum()))
    S.check('sl_03 age-standardised ratio = tickets / age-only expected', 0,
            float((m.tickets / m.expected_age_only - m.age_std_ratio).abs().max()), 1e-9)
    S.check('sl_03 age-only expected tickets add up to the fleet\'s tickets (6,750)', 6750,
            m.expected_age_only.sum(), 1e-6)
    S.check('sl_03 model machines = exposed machines (8,946)', 8946, m.machines.sum())
    S.check('sl_03 exposed machines (summary) = 8,946', 8946, F['machines_exposed'])
    d = m.set_index('model').loc[MODELS]
    for name, k in MACHINES.items():
        S.check(f'sl_03 {name}: {k:,} machines', k, d.loc[name, 'machines'])
    S.check('sl_03 every model shown has its own rate', 1, int(d.own_rate.all()))
    cls = np.select([d.age_std_lo > 1, d.age_std_hi < 1], ['above', 'below'], 'not different')
    S.check('sl_03 class = age-standardised interval against 1', 0, int((cls != d.age_std_vs_fleet).sum()))
    busy = m.sort_values(['tickets', 'model'], ascending=[False, True], kind='mergesort').model.head(3).tolist()
    S.check('sl_03 first three = the three models with the most tickets', 1, int(busy == MODELS[:3]))
    own_above = m[m.own_rate & (m.age_std_vs_fleet == 'above')].model
    S.check('sl_03 all five models above the fleet age for age are shown', 1, int(set(own_above) <= set(MODELS)))
    # The card header: "5 of 27 models" = above age for age, of the models with their own rate (as fx_02 counts).
    S.check('sl_03 header: 27 models with their own rate', 27, int(m.own_rate.sum()))
    S.check('sl_03 header: 5 of them above the fleet age for age', 5, len(own_above))
    S.check('sl_03 header: the 5 blue models are those 5', 1,
            int(set(own_above) == set(d.index[d.age_std_lo > 1])))
    S.check('sl_03 alEx LC-D: above on the crude rate (fx_02), not age-standardised', 1,
            int(d.loc['alEx LC-D', 'vs_fleet'] == 'above' and d.loc['alEx LC-D', 'age_std_vs_fleet'] != 'above'))
    for name, (r, lo, hi) in EXPECTED.items():
        S.check(f'sl_03 {name}: ratio {r:.2f}', r, d.loc[name, 'age_std_ratio'], 0.005)
        S.check(f'sl_03 {name}: interval low {lo:.2f}', lo, d.loc[name, 'age_std_lo'], 0.005)
        S.check(f'sl_03 {name}: interval high {hi:.2f}', hi, d.loc[name, 'age_std_hi'], 0.005)

    d = d.sort_values('age_std_ratio', kind='mergesort')  # highest on top
    n = len(d)
    y = np.arange(n)
    hot = (d.age_std_lo > 1).to_numpy()

    fig, ax = S.figure(S.HALF)
    ax.axvline(1, color=S.INK2, lw=1.2, zorder=1)
    for yi, (name, r), h in zip(y, d.iterrows(), hot):
        col = S.BLUE if h else S.GRAY
        ax.hlines(yi, r.age_std_lo, r.age_std_hi, color=col if h else S.GRAY_LIGHT, lw=3.2, zorder=2)
        ax.scatter(r.age_std_ratio, yi, s=120, color=col, edgecolors=S.WHITE, linewidths=1.5, zorder=3)
        label = f'{r.age_std_ratio:.2f}×'
        S.check(f'sl_03 {name}: drawn label {label}', float(label[:-1]), r.age_std_ratio, 0.005)
        S.check(f'sl_03 {name}: drawn label = expected', EXPECTED[name][0], float(label[:-1]))
        ax.text(r.age_std_hi + 0.06, yi, label, va='center', ha='left', fontsize=S.FONT,
                color=S.INK if h else S.INK2, weight='bold' if h else 'normal')
    ax.text(1.04, n - 0.45, 'Fleet = 1', va='center', ha='left', fontsize=S.SMALL, color=S.INK2)
    # Row labels: the model (bold for the three busiest) over its machine count, which explains the interval widths.
    ax.set_yticks(y)
    ax.set_yticklabels([])
    for yi, (name, r) in zip(y, d.iterrows()):
        ax.annotate(name, (0, yi), xycoords=('axes fraction', 'data'), xytext=(-12, 2), textcoords='offset points',
                    ha='right', va='bottom', fontsize=S.FONT, color=S.INK if name in busy else S.INK2,
                    weight='bold' if name in busy else 'normal')
        ax.annotate(f'{int(r.machines):,} machines', (0, yi), xycoords=('axes fraction', 'data'), xytext=(-12, -2),
                    textcoords='offset points', ha='right', va='top', fontsize=S.SMALL, color=S.INK2)
    ax.set_ylim(-0.6, n - 0.1)
    ax.set_xlim(0.5, 4.5)
    ax.set_xticks([1, 2, 3, 4])
    ax.xaxis.set_major_formatter(lambda v, _: f'{v:g}×')
    S.style_axes(ax, grid='x', baseline=None)
    ax.set_xlabel('Ratio to the fleet\'s ticket rate, age for age (95% interval)')
    return [S.save(fig, Path(out_dir) / PNG)]


if __name__ == '__main__':
    plot()
