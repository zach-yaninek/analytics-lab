#!/usr/bin/env python3
"""Slide version of Zac's figure 9 (viz/zac_notebook/zac_09_model_issue_heatmap.py): which categories make up each
model's unplanned tickets (within-model shares).

Same rows, columns, colour steps, cell labels, pooled Other column and all-models row as the full chart. The row
labels drop the ticket counts (n) and the Other header drops its category count; the definition, the counts and the
notes go to the speaker notes.

Output:  viz/figures/slides/zac_09_model_issue_heatmap.png
Run:     cd /home/user/analytics-lab && python3 -I viz/slides/zac_09_model_issue_heatmap_slide.py
"""
import math
import sys
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
# python3 -I leaves the script directory off sys.path
sys.path[:0] = [str(HERE), str(HERE.parent / 'style'), str(HERE.parent / 'zac_notebook')]
import numpy as np  # noqa: E402
from matplotlib.colors import BoundaryNorm, ListedColormap  # noqa: E402

import ipa_style as style  # noqa: E402
import slides  # noqa: E402
import zac_09_model_issue_heatmap as full  # noqa: E402
import zac_data  # noqa: E402


def plot(out_dir=slides.FIG_DIR):
    heat, mix = zac_data.load('model_issue_heatmap'), zac_data.load('model_issue_mix')
    rq = zac_data.load('record_quality')
    cats = [c for c in heat.columns if c not in ('model', 'n', full.OTHER)]
    counts = full.zac_table(mix)
    shares = heat.set_index('model')[cats + [full.OTHER]]
    n_per_model = heat.set_index('model').n
    total = int(mix.cases.sum())
    style.check('slide zac_09 heatmap = Zac\'s cell 21 recomputed from model_issue_mix', 0,
                float((100 * counts.div(counts.sum(axis=1), axis=0) - shares).abs().to_numpy().max()), 1e-9)
    by_cat = mix.groupby('category').cases.sum().sort_values(ascending=False)
    fleet = 100 * by_cat.reindex(cats) / total
    fleet_n = by_cat.reindex(cats).to_numpy()

    # The full chart's discrete scale: a pale bin for no tickets, then one blue step per full.STEP points.
    named, named_n = shares[cats].to_numpy(), counts[cats].to_numpy()
    n_steps = math.ceil(named.max() / full.STEP)
    idx = np.linspace(0, len(style.BLUE_RAMP) - 1, n_steps).round().astype(int)
    cmap = ListedColormap([style.ZERO_CELL] + [style.BLUE_RAMP[i] for i in idx])
    norm = BoundaryNorm(np.arange(-full.STEP, full.STEP * (n_steps + 1), full.STEP), cmap.N)
    binned = np.where(named_n == 0, -full.STEP / 2, named)

    def step(val):
        return idx[min(int(val // full.STEP), n_steps - 1)]

    n_rows, n_cols = len(shares), len(cats)
    fleet_y, other_x = n_rows + full.GAP, n_cols + full.GAP
    fig, ax = slides.figure()
    mesh = ax.pcolormesh(np.arange(n_cols + 1), np.arange(n_rows + 1), binned, cmap=cmap, norm=norm,
                         edgecolors=style.SURFACE, linewidth=2.0)
    ax.pcolormesh(np.arange(n_cols + 1), [fleet_y, fleet_y + 1], np.array([fleet.to_numpy()]), cmap=cmap, norm=norm,
                  edgecolors=style.SURFACE, linewidth=2.0)
    rows = [full.Row(i + 0.5, named[i], named_n[i], shares[full.OTHER].iloc[i], counts[full.OTHER].iloc[i])
            for i in range(n_rows)]
    rows.append(full.Row(fleet_y + 0.5, fleet.to_numpy(), fleet_n, 100 - fleet.sum(), total - fleet_n.sum()))
    for row in rows:
        for j, (val, n) in enumerate(zip(row.share, row.n)):
            dark = n > 0 and step(val) >= full.WHITE_FROM
            ax.text(j + 0.5, row.y, full.label(val, n), ha='center', va='center', fontsize=10,
                    color='white' if dark else style.INK if n else style.MUTED, weight='bold' if dark else 'normal')
        ax.text(other_x + 0.5, row.y, full.label(row.other_share, row.other_n), ha='center', va='center', fontsize=10,
                color=style.INK2)

    ax.set_xlim(0, other_x + 1)
    ax.set_ylim(fleet_y + 1, 0)
    ax.set_yticks([row.y for row in rows])
    ax.set_yticklabels(list(n_per_model.index) + ['All models'], color=style.INK2, fontsize=10)
    ax.get_yticklabels()[-1].set_color(style.MUTED)
    ax.xaxis.tick_top()
    ax.set_xticks(list(np.arange(n_cols) + 0.5) + [other_x + 0.5])
    ax.set_xticklabels(['\n'.join(textwrap.wrap(c, 13)) for c in cats] + ['Other\ncategories'], color=style.INK2,
                       fontsize=10)
    style.style_axes(ax, grid=None, baseline=None)
    ticks = [-full.STEP / 2] + list(range(2 * full.STEP, full.STEP * n_steps + 1, 2 * full.STEP))
    cb = fig.colorbar(mesh, ax=ax, location='right', shrink=0.75, anchor=(0.0, 1.0), aspect=16, pad=0.025)
    cb.set_ticks(ticks, labels=['0%'] + [f'{t}%' for t in ticks[1:]])
    cb.outline.set_visible(False)
    cb.ax.tick_params(which='both', length=0, labelsize=9, colors=style.MUTED)
    cb.set_label('share of the model\'s tickets', color=style.MUTED, fontsize=10)

    i, j = np.unravel_index(named.argmax(), named.shape)
    cat, top_model = cats[j], shares.index[i]
    low_model = shares[cat].idxmin()
    period = zac_data.period_text(rq)
    n_other_cats = by_cat.drop(full.MISSING).size - full.N_CATS
    talk = [zac_data.UNPLANNED_DEFINITION,
            f'Rows: the {n_rows} models with the most unplanned tickets, {period} ('
            + ', '.join(f'{m} {n:,}' for m, n in n_per_model.items())
            + f'), and all {mix.model.nunique()} models together ({total:,}) for comparison. Raw counts, not adjusted '
              f'for installed machines.',
            'Shares are within each model; each row sums to 100% before rounding. <1% = above 0 but rounds to 0%; '
            '0% (pale gray cell) = no tickets.',
            f'Columns: the {full.N_CATS} most frequent categories overall, then Other (not coloured), which pools '
            f'{n_other_cats} further categories and {full.MISSING} (no category recorded; {int(by_cat[full.MISSING])} '
            f'tickets).']
    return [slides.finish(fig, Path(out_dir) / full.PNG,
                          f'{cat} is {full.label(named[i, j], named_n[i, j])} of {top_model}\'s unplanned tickets but '
                          f'{full.label(shares.loc[low_model, cat], counts.loc[low_model, cat])} of {low_model}\'s',
                          f'Share of each model\'s unplanned tickets by category, the {n_rows} models with the most, '
                          f'{period}', talk)]


if __name__ == '__main__':
    plot()
