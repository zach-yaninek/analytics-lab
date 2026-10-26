#!/usr/bin/env python3
"""Slide chart 2: each busy model's share of installed machine-months against its share of unplanned tickets.

Slide version of viz/fleet_exposure/fx_01_fleet_vs_ticket_share.py, from the same model table and the same totals
(unplanned tickets on listed machines, Aug 2025 to Aug 2026). Paired bars per model: light = share of installed
machine-months, blue = share of unplanned tickets; two bars of equal length = the fleet's ticket rate. Rows: the
TOP_N models with the most unplanned tickets (all of them are rows of the page chart, which lists the 10 models with
the most installed machine-months). The three busiest models (bold) together hold 42% of the machine-months and 51%
of the tickets; the card header carries that comparison, checked here.

Input:  verification/outputs/fleet/fx_model_rates.csv, verification/outputs/fleet/fx_summary.json
Output: viz/figures/slides/sl_02_model_share.png (half card)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import deck_style as S  # noqa: E402

PNG = 'sl_02_model_share.png'
TOP_N = 6        # models with the most unplanned tickets
N_BUSY = 3       # the busiest models, bold, compared in the card header
PAGE_TOP = 10    # rows of the page chart (most installed machine-months)
BAR_H, OFFSET = 0.36, 0.19


def plot(out_dir=S.FIG_DIR):
    fleet = S.OUT / 'fleet'
    F = json.loads((fleet / 'fx_summary.json').read_text())['fleet']
    m = pd.read_csv(fleet / 'fx_model_rates.csv')

    # Same population and totals as fx_01: the model table covers every listed machine with exposure and every ticket.
    S.check('sl_02 model tickets = fleet tickets (6,750)', 6750, m.tickets.sum())
    S.check('sl_02 fleet tickets (summary) = 6,750', 6750, F['tickets'])
    S.check('sl_02 model months = fleet installed machine-months', F['months'], m.months.sum(), 1e-6)
    # Shares recomputed from the counts (what the page chart draws from the share columns).
    m['pct_months'] = 100 * m.months / F['months']
    m['pct_tickets'] = 100 * m.tickets / F['tickets']
    S.check('sl_02 share_of_months column = months / fleet months', 0,
            float((m.share_of_months * 100 - m.pct_months).abs().max()), 1e-9)
    S.check('sl_02 share_of_tickets column = tickets / fleet tickets', 0,
            float((m.share_of_tickets * 100 - m.pct_tickets).abs().max()), 1e-9)

    by_tickets = m.sort_values(['tickets', 'model'], ascending=[False, True], kind='mergesort')
    S.check('sl_02 no tie at the top-N boundary', 1, int(by_tickets.tickets.iloc[TOP_N - 1] >
                                                       by_tickets.tickets.iloc[TOP_N]))
    S.check('sl_02 no tie at the busiest-models boundary', 1, int(by_tickets.tickets.iloc[N_BUSY - 1] >
                                                                by_tickets.tickets.iloc[N_BUSY]))
    rows = by_tickets.head(TOP_N)
    page_rows = m.sort_values(['months', 'model'], ascending=[False, True], kind='mergesort').head(PAGE_TOP)
    S.check('sl_02 every row shown is a row of the page chart (fx_01)', 1,
            int(set(rows.model) <= set(page_rows.model)))
    busy = rows.head(N_BUSY)
    S.check('sl_02 busiest models = LVD-Remote-2.0, LVRR-WP-2.0, MV-2.0', 1,
            int(busy.model.tolist() == ['LVD-Remote-2.0', 'LVRR-WP-2.0', 'MV-2.0']))
    # The card header's comparison (as in the page chart's title).
    S.check('sl_02 three busiest: 42% of installed machine-months', 42, round(busy.months.sum() / F['months'] * 100))
    S.check('sl_02 three busiest: 51% of unplanned tickets', 51, round(busy.tickets.sum() / F['tickets'] * 100))
    S.check('sl_02 three busiest: combined rate 1.21x the fleet\'s', 1.21,
            round((busy.tickets.sum() / busy.months.sum()) / (F['tickets'] / F['months']), 2))

    fig, ax = S.figure(S.HALF)
    y = -np.arange(TOP_N, dtype=float)
    gray, blue = rows.pct_months.to_numpy(), rows.pct_tickets.to_numpy()
    ax.barh(y + OFFSET, gray, height=BAR_H, color=S.LIGHT, linewidth=0, zorder=2,
            label='Share of installed machine-months')
    ax.barh(y - OFFSET, blue, height=BAR_H, color=S.BLUE, linewidth=0, zorder=2, label='Share of unplanned tickets')
    for r, yi, g, b in zip(rows.itertuples(), y, gray, blue):
        g_txt, b_txt = f'{g:.1f}%', f'{b:.1f}%'
        S.check(f'sl_02 {r.model}: share of months drawn ({g_txt})', float(g_txt[:-1]),
                100 * r.months / F['months'], 0.05)
        S.check(f'sl_02 {r.model}: share of tickets drawn ({b_txt})', float(b_txt[:-1]),
                100 * r.tickets / F['tickets'], 0.05)
        S.check(f'sl_02 {r.model}: drawn share = page chart label (months)', float(g_txt[:-1]),
                round(100 * r.share_of_months, 1))
        S.check(f'sl_02 {r.model}: drawn share = page chart label (tickets)', float(b_txt[:-1]),
                round(100 * r.share_of_tickets, 1))
        ax.text(g + 0.3, yi + OFFSET, g_txt, va='center', ha='left', fontsize=S.SMALL, color=S.INK2)
        ax.text(b + 0.3, yi - OFFSET, b_txt, va='center', ha='left', fontsize=S.SMALL, color=S.BLUE,
                weight='bold')
    ax.set_yticks(y)
    ax.set_yticklabels(rows.model, fontsize=S.FONT, color=S.INK2)
    for tick, name in zip(ax.get_yticklabels(), rows.model):
        if name in set(busy.model):
            tick.set_fontweight('bold')
            tick.set_color(S.INK)
    ax.set_ylim(y[-1] - 0.6, 0.6)
    ax.set_xlim(0, 25)
    ax.set_xticks([0, 5, 10, 15, 20, 25])
    S.pct_axis(ax.xaxis)
    S.style_axes(ax, grid='x', baseline='left')
    ax.legend(loc='lower right', handlelength=1.2, borderaxespad=0.2)
    ax.set_xlabel('Share of the fleet, Aug 2025 to Aug 2026')
    return [S.save(fig, Path(out_dir) / PNG)]


if __name__ == '__main__':
    plot()
