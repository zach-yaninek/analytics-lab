#!/usr/bin/env python3
"""Slide version of chart 8 (viz/high_ticket/htm_08_chronic_categories_heatmap.py): unplanned tickets by category for
the chronic-outlier machines with the most tickets.

Same columns, colour ramp, cell counts and colour bar as the full chart, cut to the 10 machines with the most tickets
(the full chart shows 30, too many rows for a slide). Row labels drop the ticket totals and column labels drop the
category totals; those, the definition and the rows not shown go to the speaker notes.

Output:  viz/figures/slides/htm_08_chronic_categories_heatmap.png
Run:     cd /home/user/analytics-lab && python3 -I viz/slides/htm_08_chronic_categories_heatmap_slide.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# python3 -I leaves the script directory off sys.path
sys.path[:0] = [str(HERE), str(HERE.parent / 'style'), str(HERE.parent / 'high_ticket')]
import numpy as np  # noqa: E402
from matplotlib.colors import BoundaryNorm, ListedColormap  # noqa: E402

import htm  # noqa: E402
import htm_08_chronic_categories_heatmap as full  # noqa: E402
import ipa_style as style  # noqa: E402
import slides  # noqa: E402

N_ROWS = 10  # machines with the most tickets (full chart: 30)


def plot(out_dir=slides.FIG_DIR):
    S = htm.summary()
    cc = htm.load('chronic_categories')
    cc['category'] = cc.category.replace({'[Missing]': 'Category missing'})
    mach = cc.groupby(['machine_id', 'model', 'total_tickets'], as_index=False).size()
    mach = mach.sort_values(['total_tickets', 'machine_id'], ascending=[False, True], kind='mergesort')
    style.check('slide D3 chronic outliers (category table)', S['D3_classes']['chronic_outlier'], len(mach))

    tot = cc.groupby('category').tickets.sum().reset_index()
    tot = tot.sort_values(['tickets', 'category'], ascending=[False, True], kind='mergesort')
    cols = tot.category.head(full.N_COLS).tolist()
    cc['col'] = cc.category.where(cc.category.isin(cols), 'Other')
    dom = cc.groupby('machine_id').tickets.max() / cc.groupby('machine_id').total_tickets.first()
    n_dom = int((dom >= full.DOMINANT).sum())
    rows, rest = mach.head(N_ROWS), mach.iloc[N_ROWS:]
    piv = cc[cc.machine_id.isin(rows.machine_id)].pivot_table(index='machine_id', columns='col', values='tickets',
                                                              aggfunc='sum', fill_value=0)
    piv = piv.reindex(index=rows.machine_id, columns=cols + ['Other'], fill_value=0)
    style.check('slide heatmap rows sum to totals', 0,
                int(abs(piv.sum(axis=1).to_numpy() - rows.total_tickets.to_numpy()).sum()))
    vals = piv.to_numpy()
    # The full chart's colour scale (one ramp step per count, up to the largest cell of its rows), so a count has the
    # same colour on both charts.
    full_rows = cc[cc.machine_id.isin(mach.head(full.N_ROWS).machine_id)]
    vmax = int(full_rows.groupby(['machine_id', 'col']).tickets.sum().max())

    fig, ax = slides.figure()
    idx = np.linspace(0, len(style.BLUE_RAMP) - 1, vmax).round().astype(int)
    cmap = ListedColormap([style.ZERO_CELL] + [style.BLUE_RAMP[i] for i in idx])
    norm = BoundaryNorm(np.arange(-0.5, vmax + 1.5), cmap.N)
    mesh = ax.pcolormesh(np.arange(vals.shape[1] + 1), np.arange(vals.shape[0] + 1), vals, cmap=cmap, norm=norm,
                         edgecolors=style.SURFACE, linewidth=2.0)
    for i in range(vals.shape[0]):
        for j in range(vals.shape[1]):
            v = int(vals[i, j])
            if v:
                dark = idx[v - 1] >= full.WHITE_FROM
                ax.text(j + 0.5, i + 0.5, str(v), ha='center', va='center', fontsize=9.5,
                        color='white' if dark else style.INK, weight='bold' if dark else 'normal')
    ax.set_ylim(vals.shape[0], 0)
    ax.set_xlim(0, vals.shape[1])
    ax.set_yticks(np.arange(vals.shape[0]) + 0.5)
    ax.set_yticklabels([f'{r.machine_id} · {r.model}' for r in rows.itertuples()], color=style.INK2, fontsize=9.5)
    ax.xaxis.tick_top()
    ax.set_xticks(np.arange(vals.shape[1]) + 0.5)
    ax.set_xticklabels(cols + ['Other'], rotation=40, ha='left', rotation_mode='anchor', color=style.INK2,
                       fontsize=9.5)
    style.style_axes(ax, grid=None, baseline=None)
    cb = fig.colorbar(mesh, ax=ax, location='right', shrink=0.6, anchor=(0.0, 1.0), aspect=16, pad=0.03,
                      ticks=range(0, vmax + 1, 2 if vmax > 8 else 1))
    cb.outline.set_visible(False)
    cb.ax.tick_params(which='both', length=0, labelsize=9, colors=style.MUTED)
    cb.set_label('tickets', color=style.MUTED, fontsize=10)

    lo, hi = int(rest.total_tickets.min()), int(rest.total_tickets.max())
    cut = int(rows.total_tickets.iloc[-1])
    tie = (f' Of the {int((mach.total_tickets == cut).sum())} machines with {cut} tickets, the '
           f'{int((rows.total_tickets == cut).sum())} with the lowest machine ids are shown.' if hi == cut else '')
    col_n = dict(zip(tot.category, tot.tickets))
    talk = [htm.chronic_definition(S),
            f'Rows: the {len(rows)} chronic-outlier machines with the most unplanned tickets '
            f'({rows.total_tickets.max()} to {cut}), case-export serials, {htm.period_text(S, "case_export_period")}. '
            f'Not shown: {len(rest)} chronic outliers with {lo} to {hi} tickets.{tie}',
            f'Columns: the {full.N_COLS} most frequent categories across all {len(mach)} chronic outliers ('
            + ', '.join(f'{c} {col_n[c]}' for c in cols)
            + f'); Other pools {len(tot) - len(cols)} further categories ({int(tot.tickets.iloc[full.N_COLS:].sum())} '
              f'tickets).']
    return [slides.finish(fig, Path(out_dir) / full.PNG,
                          f'One category makes up half or more of the tickets on {n_dom} of {len(mach)} chronic '
                          f'outliers',
                          f'Unplanned tickets by category, the {len(rows)} chronic outliers with the most tickets',
                          talk)]


if __name__ == '__main__':
    plot()
