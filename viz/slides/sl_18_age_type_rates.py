#!/usr/bin/env python3
"""Slide chart 18 (follow-up to slide 4): unplanned-ticket rates by request type, machines under 4 vs 4+ years.

Rate per 100 installed machine-months by request group and age group (docs/09 §4 A1), descriptive and not adjusted
for model: one row per request group, sorted by the under-4 rate, with the 4+ rate as a gray ring, the under-4 rate
as a blue dot, and the crude rate ratio (under 4 ÷ 4+) in the right-hand column. The note gives all unplanned
tickets (the 'all' row).

Input:  verification/outputs/followups/ag_type_rates.csv, followups_summary.json
Output: viz/figures/slides/sl_18_age_type_rates.png (half card, tall)
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

import deck_style as S  # noqa: E402
import followup_terms as T  # noqa: E402

PNG = 'sl_18_age_type_rates.png'
TERMS = ['under4', 'rate', 'request_group', 'crude']
DOT = 90  # marker area (pt^2): about 9.5 pt across


def ratio_text(v, nd=1):
    return f'×{v:.{nd}f}'


def plot(out_dir=S.FIG_DIR):
    t = pd.read_csv(T.FU / 'ag_type_rates.csv')
    # Highest under-4 rate at the top (y = row index, so the highest comes last); ties broken by name, A at the top.
    d = (t[t.level == 'group'].sort_values(['under4_rate_per_100', 'type'], ascending=[True, False])
         .reset_index(drop=True))
    a = t[t.level == 'all'].iloc[0]
    s = T.summary()
    pins = {c['check']: c['actual'] for c in s['checks']['list']}
    S.check('sl_18 ten request groups', 10, len(d))
    S.check('sl_18 the groups are the summary\'s ten', 1, int(sorted(d.type) == sorted(s['definitions']['groups'])))
    S.check('sl_18 groups sum to the all row, under 4', a.under4_tickets, d.under4_tickets.sum())
    S.check('sl_18 groups sum to the all row, 4+', a.plus4_tickets, d.plus4_tickets.sum())
    S.check('sl_18 every row on the same months, under 4', 0, float(np.ptp(t.under4_months)), 1e-6)
    S.check('sl_18 every row on the same months, 4+', 0, float(np.ptp(t.plus4_months)), 1e-6)

    # The definition's numbers: 6,750 tickets on 8,946 listed machines.
    rate_text = T.terms()['rate'][1]
    m = re.search(r'([\d,]+) tickets on ([\d,]+) listed machines', rate_text)
    S.check('sl_18 definition: 6,750 tickets = the all row', a.under4_tickets + a.plus4_tickets,
            int(m.group(1).replace(',', '')))
    S.check('sl_18 definition: 6,750 tickets = the pinned fx_summary', pins['pin fx_summary tickets'],
            int(m.group(1).replace(',', '')))
    S.check('sl_18 definition: 8,946 listed machines = the pinned fx_summary', pins['pin fx_summary machines_exposed'],
            int(m.group(2).replace(',', '')))
    S.check('sl_18 definition: under 4 = the young bands <1, 1-2, 2-4', 1,
            int(s['definitions']['young_bands'] == ['<1', '1-2', '2-4']
                and '(<1, 1-2 and 2-4 years)' in T.terms()['under4'][1]))
    S.check('sl_18 definition: Aug 2025 to Aug 2026 = the period', 1,
            int(s['definitions']['period'] == ['2025-08-01', '2026-08-31']
                and '(Aug 2025 to Aug 2026)' in T.terms()['under4'][1]))

    # The note: all unplanned tickets, recomputed from tickets and months.
    u_all = 100 * a.under4_tickets / a.under4_months
    p_all = 100 * a.plus4_tickets / a.plus4_months
    note = f'All tickets: {u_all:.1f} vs {p_all:.1f} per 100 ({ratio_text(u_all / p_all, 2)})'
    S.check('sl_18 note: all tickets under 4 (8.0)', u_all, float(note.split()[2]), 0.05)
    S.check('sl_18 note: all tickets 4+ (4.8)', p_all, float(note.split()[4]), 0.05)
    S.check('sl_18 note: rate ratio (x1.66)', u_all / p_all, float(note.split('×')[1].rstrip(')')), 0.005)
    S.check('sl_18 note: under-4 rate = the CSV', u_all, a.under4_rate_per_100, 1e-9)
    S.check('sl_18 note: 4+ rate = the CSV', p_all, a.plus4_rate_per_100, 1e-9)
    S.check('sl_18 note: ratio = the CSV', u_all / p_all, a.rate_ratio, 1e-9)

    fig, ax = S.figure(S.HALF_TALL)
    n = len(d)
    XV = 3.42                                    # the value column (right-aligned)
    for i, r in d.iterrows():
        u = 100 * r.under4_tickets / r.under4_months
        p = 100 * r.plus4_tickets / r.plus4_months
        S.check(f'sl_18 {r.type} under-4 rate = 100 x tickets / months', u, r.under4_rate_per_100, 1e-9)
        S.check(f'sl_18 {r.type} 4+ rate = 100 x tickets / months', p, r.plus4_rate_per_100, 1e-9)
        S.check(f'sl_18 {r.type} rate ratio = the CSV', u / p, r.rate_ratio, 1e-9)
        label = ratio_text(u / p)
        S.check(f'sl_18 {r.type} label {label}', u / p, float(label[1:]), 0.05)
        ax.plot([p, u], [i, i], color=S.GRAY_LIGHT, lw=2, solid_capstyle='butt', zorder=1)
        ax.scatter(p, i, s=DOT, facecolor=S.WHITE, edgecolor=S.GRAY, linewidth=2, zorder=2)
        ax.scatter(u, i, s=DOT, color=S.BLUE, edgecolor=S.WHITE, linewidth=1.2, zorder=3)
        ax.text(XV, i, label, va='center', ha='right', fontsize=S.SMALL, color=S.INK2)
    S.check('sl_18 rows sorted by the under-4 rate', 1, int(d.under4_rate_per_100.is_monotonic_increasing))
    S.check('sl_18 every mark left of the value column (below 3)', 1,
            int(d[['under4_rate_per_100', 'plus4_rate_per_100']].max().max() < 3))

    ax.text(XV, n - 1 + 1.15, note, ha='right', va='center', fontsize=S.SMALL, color=S.INK2,
            bbox={'boxstyle': 'square,pad=0.1', 'facecolor': S.WHITE, 'edgecolor': 'none'})  # masks the grid
    ax.set_xlim(0, XV + 0.04)
    ax.set_xticks([0, 0.5, 1, 1.5, 2, 2.5])
    ax.set_xticklabels(['0', '0.5', '1', '1.5', '2', '2.5'])
    ax.set_yticks(np.arange(n))
    ax.set_yticklabels(d.type)
    ax.set_ylim(-0.6, n - 1 + 1.6)
    S.style_axes(ax, grid='x', baseline=None)
    ax.set_xlabel('Unplanned tickets per 100 installed machine-months')
    handles = [Line2D([], [], ls='', marker='o', ms=9.5, mfc=S.BLUE, mec=S.WHITE, mew=1.2, label='under 4 years'),
               Line2D([], [], ls='', marker='o', ms=9.5, mfc=S.WHITE, mec=S.GRAY, mew=2, label='4+ years')]
    ax.legend(handles=handles, loc='lower left', bbox_to_anchor=(0, 1.0), ncol=2, handlelength=1.0,
              handletextpad=0.4, columnspacing=1.4, borderaxespad=0.2, fontsize=S.SMALL)
    S.definitions(fig, T.items(TERMS))
    return [S.save(fig, Path(out_dir) / PNG)]


if __name__ == '__main__':
    plot()
