#!/usr/bin/env python3
"""Chart 8: unplanned tickets by category for the chronic-outlier machines with the most tickets (heatmap).

One row per chronic-outlier machine (the N_ROWS with the most tickets, labelled machine id · model · total), one
column per category (the N_COLS most frequent across all chronic outliers, with their totals, plus Other). Cells
hold ticket counts on a discrete one-hue blue ramp, one step per count; empty cells are a neutral off-surface grey.
The title states on how many chronic outliers one category makes up half or more of the tickets.

Inputs:
  verification/outputs/htm_chronic_categories.csv  machine_id, model, total_tickets, category, tickets (one row per
                                                   chronic-outlier machine and category, all chronic outliers)
  verification/outputs/htm_summary.json            definitions.q_cut, D1_workload.threshold for the chronic-outlier
                                                   definition; D3_classes, chronic_outlier_ids and
                                                   D5_episodes.chronic.tickets for the consistency checks
Output:
  viz/figures/htm_08_chronic_categories_heatmap.png

Run:  cd /home/user/analytics-lab && python3 -I viz/high_ticket/htm_08_chronic_categories_heatmap.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]  # python3 -I leaves the script directory off sys.path
import numpy as np  # noqa: E402
from matplotlib.colors import BoundaryNorm, ListedColormap  # noqa: E402

import htm  # noqa: E402
import ipa_style as style  # noqa: E402

PNG = 'htm_08_chronic_categories_heatmap.png'
N_ROWS, N_COLS = 30, 10  # machines with the most tickets; most frequent categories (the rest pooled as Other)
ROW_IN = 0.3             # inches per machine row
DOMINANT = 0.5           # "one category makes up half or more of a machine's tickets"
WHITE_FROM = 6           # BLUE_RAMP index from which cell counts are white bold (dark cells); check if the ramp changes


def plot(out_dir=htm.FIG_DIR):
    out_dir = Path(out_dir)
    S = htm.summary()
    cc = htm.load('chronic_categories')
    cc['category'] = cc.category.replace({'[Missing]': 'Category missing'})

    mach = cc.groupby(['machine_id', 'model', 'total_tickets'], as_index=False).size()
    mach = mach.sort_values(['total_tickets', 'machine_id'], ascending=[False, True], kind='mergesort')
    style.check('D3 chronic outliers (category table)', S['D3_classes']['chronic_outlier'], len(mach))
    style.check('chronic-outlier ids = summary ids', 0, len(set(mach.machine_id) ^ set(S['chronic_outlier_ids'])))
    style.check('D5 chronic-outlier tickets (category table)', S['D5_episodes']['chronic']['tickets'],
                int(mach.total_tickets.sum()))
    style.check('category tickets sum to machine totals (all chronic outliers)', 0,
                int((cc.groupby('machine_id').tickets.sum() - cc.groupby('machine_id').total_tickets.first())
                    .abs().sum()))

    tot = cc.groupby('category').tickets.sum().reset_index()
    tot = tot.sort_values(['tickets', 'category'], ascending=[False, True], kind='mergesort')
    cols = tot.category.head(N_COLS).tolist()
    n_other_cats = len(tot) - len(cols)
    cc['col'] = cc.category.where(cc.category.isin(cols), 'Other')
    dom = cc.groupby('machine_id').tickets.max() / cc.groupby('machine_id').total_tickets.first()
    n_dom = int((dom >= DOMINANT).sum())
    rows = mach.head(N_ROWS)
    rest = mach.iloc[N_ROWS:]
    piv = cc[cc.machine_id.isin(rows.machine_id)].pivot_table(index='machine_id', columns='col', values='tickets',
                                                              aggfunc='sum', fill_value=0)
    piv = piv.reindex(index=rows.machine_id, columns=cols + ['Other'], fill_value=0)
    style.check('heatmap rows sum to totals', 0,
                int(abs(piv.sum(axis=1).to_numpy() - rows.total_tickets.to_numpy()).sum()))
    vals = piv.to_numpy()
    vmax = int(vals.max())

    fig, ax = style.figure(10.5, 4.4 + ROW_IN * len(rows))
    # Discrete one-hue ramp: one step per count (1..vmax), zero = neutral off-surface cell.
    idx = np.linspace(0, len(style.BLUE_RAMP) - 1, vmax).round().astype(int)
    cmap = ListedColormap([style.ZERO_CELL] + [style.BLUE_RAMP[i] for i in idx])
    norm = BoundaryNorm(np.arange(-0.5, vmax + 1.5), cmap.N)
    mesh = ax.pcolormesh(np.arange(vals.shape[1] + 1), np.arange(vals.shape[0] + 1), vals, cmap=cmap, norm=norm,
                         edgecolors=style.SURFACE, linewidth=2.0)
    for i in range(vals.shape[0]):
        for j in range(vals.shape[1]):
            v = int(vals[i, j])
            if v:
                dark = idx[v - 1] >= WHITE_FROM
                ax.text(j + 0.5, i + 0.5, str(v), ha='center', va='center', fontsize=9.5,
                        color='white' if dark else style.INK, weight='bold' if dark else 'normal')
    ax.set_ylim(vals.shape[0], 0)
    ax.set_xlim(0, vals.shape[1])
    ax.set_yticks(np.arange(vals.shape[0]) + 0.5)
    ax.set_yticklabels([f'{r.machine_id} · {r.model} · {r.total_tickets} tickets' for r in rows.itertuples()],
                       color=style.INK2, fontsize=9.5)
    ax.xaxis.tick_top()
    ax.set_xticks(np.arange(vals.shape[1]) + 0.5)
    col_n = dict(zip(tot.category, tot.tickets))
    other_n = int(tot.tickets.iloc[N_COLS:].sum())
    ax.set_xticklabels([f'{c} ({col_n[c]})' for c in cols] + [f'Other ({other_n})'], rotation=40, ha='left',
                       rotation_mode='anchor', color=style.INK2, fontsize=9.5)
    style.style_axes(ax, grid=None, baseline=None)
    # Colour bar beside the top rows: 40% of the plot height, anchored to its top edge.
    cb = fig.colorbar(mesh, ax=ax, location='right', shrink=0.4, anchor=(0.0, 1.0), aspect=22, pad=0.03,
                      ticks=range(0, vmax + 1, 2 if vmax > 8 else 1))
    cb.outline.set_visible(False)
    cb.ax.tick_params(which='both', length=0, labelsize=9, colors=style.MUTED)
    cb.set_label('tickets', color=style.MUTED, fontsize=10)

    if len(rest) == 0:
        rest_txt = 'none.'
    else:
        lo, hi = int(rest.total_tickets.min()), int(rest.total_tickets.max())
        span = f'{lo} to {hi}' if lo < hi else f'{lo}'
        rest_txt = f'{len(rest)} chronic outliers with {span} tickets.'
        cut = int(rows.total_tickets.iloc[-1])
        if hi == cut:  # the row limit splits a tie
            rest_txt += (f' Of the {int((mach.total_tickets == cut).sum())} machines with {cut} tickets, the '
                         f'{int((rows.total_tickets == cut).sum())} with the lowest machine ids are shown.')
    style.frame(
        fig,
        f'One category makes up half or more of the tickets on {n_dom} of {len(mach)} chronic outliers',
        f'Unplanned tickets by category (case-export serials, {htm.period_text(S, "case_export_period")}) '
        f'for the {len(rows)} '
        f'chronic-outlier machines with the most tickets. Columns: the {N_COLS} most frequent categories across all '
        f'{len(mach)} chronic outliers, with their totals.',
        definitions=[htm.chronic_definition(S)],
        notes=[f'Rows sorted by total tickets, then machine id. Not shown: {rest_txt} Other = {n_other_cats} '
               f'further categories.',
               f'Source: htm_chronic_categories.csv (full table, all {len(mach)} machines); thresholds from '
               f'htm_summary.json.'])
    return [style.save(fig, out_dir / PNG)]


if __name__ == '__main__':
    plot()
