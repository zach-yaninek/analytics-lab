#!/usr/bin/env python3
"""Zac's figure 9: which categories make up each model's unplanned tickets (heatmap of within-model shares).

Recreates 09_model_issue_heatmap.png from Zac's notebook (cell 21, on his model_issue_mix query of cell 20 over
service_cases, the unplanned tickets of cell 15). Same population (unplanned tickets), same selection (the 8 models
with the most unplanned tickets; the 7 categories with the most unplanned tickets over all models, the rest pooled as
Other) and the same metric (share of each model's unplanned tickets, so every row sums to 100%). Rows keep his order
(most tickets first) and are labelled with model and n.

Form changes within the IPA style: a discrete one-hue blue ramp (style.BLUE_RAMP, one step per 5 points) for the
named categories; the pooled Other column as plain numbers, not coloured, so the remainder does not dominate the
colour scale; pale gray cells (style.ZERO_CELL, also shown on the colour bar, as in htm_08) for categories with no
tickets on that model; non-zero shares that round to 0% shown as <1% (Zac: 0%); and a bottom row for all models
together, as the reference mix each model can be compared with.

Inputs:  zac_data.load('model_issue_heatmap')  verification/outputs/repro_sql_model_issue_heatmap.csv (model, n and
                                               the % of each category, Zac's cell 21 table)
         zac_data.load('model_issue_mix')      repro_sql_model_issue_mix.csv (model, category, cases; cell 20): the
                                               table is recomputed from it, zero cells and the all-models row
         zac_data.load('issue_mix')            repro_sql_issue_mix.csv (category shares of all unplanned tickets)
         zac_data.load('model_workload')       repro_sql_model_workload.csv (all tickets per model, cross-check)
         zac_data.load('service_groups')       repro_sql_service_groups.csv (unplanned total, cross-check)
         zac_data.load('record_quality')       repro_sql_record_quality.csv (period of the case export)
Output:  viz/figures/zac_09_model_issue_heatmap.png
Run:     cd /home/user/analytics-lab && python3 -I viz/zac_notebook/zac_09_model_issue_heatmap.py
"""
import math
import sys
import textwrap
from pathlib import Path
from typing import NamedTuple

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]  # python3 -I leaves the script directory off sys.path
import numpy as np  # noqa: E402
from matplotlib.colors import BoundaryNorm, ListedColormap  # noqa: E402

import ipa_style as style  # noqa: E402
import zac_data  # noqa: E402

N_MODELS = 8      # Zac's selection: groupby('model').cases.sum().nlargest(8) (cell 21)
N_CATS = 7        # Zac's selection: groupby('category').cases.sum().nlargest(7), the rest 'Other categories' (cell 21)
OTHER = 'Other categories'
MISSING = '[Missing]'   # Zac's label for tickets with no category; pooled in Other
PNG = 'zac_09_model_issue_heatmap.png'
PLANNED_GROUPS = ['Planned work', 'Cancelled request', 'Duplicate case']  # excluded from service_cases (cell 15)
STEP = 5          # percentage points per colour step
WHITE_FROM = 8    # BLUE_RAMP index from which cell text is white bold: the first step where white text has more
                  # contrast than ink (#256abf: 5.4:1 against 3.6:1); check if the ramp changes
BANDS_IN = 3.75   # figure height for the title band, the column headers and the footer
ROW_IN = 0.46     # figure height added per heatmap row
GAP = 0.3         # gap (in cells) before the Other column and before the all-models row


class Row(NamedTuple):
    """One heatmap row: centre y, the named categories' shares (%) and counts, and the pooled Other share and count."""
    y: float
    share: np.ndarray
    n: np.ndarray
    other_share: float
    other_n: int


def ordinal(k):
    """8 -> '8th', 2 -> '2nd', 11 -> '11th'."""
    suffix = 'th' if 10 <= k % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(k % 10, 'th')
    return f'{k}{suffix}'


def zac_table(mix):
    """Zac's cell 21 on model_issue_mix: ticket counts for the top models x top categories + Other, in his order."""
    heat_models = mix.groupby('model').cases.sum().nlargest(N_MODELS).index
    cats = mix.groupby('category').cases.sum().nlargest(N_CATS).index
    w = mix[mix.model.isin(heat_models)].copy()
    w['display_category'] = w.category.where(w.category.isin(cats), OTHER)
    return w.pivot_table(index='model', columns='display_category', values='cases', aggfunc='sum',
                         fill_value=0).reindex(index=heat_models, columns=list(cats) + [OTHER], fill_value=0)


def label(val, cases):
    """Cell text: whole percent as in Zac's chart, but '<1%' when a category has tickets and rounds to 0%."""
    return '<1%' if cases and round(val) == 0 else f'{val:.0f}%'


def plot(out_dir=zac_data.FIG_DIR):
    out_dir = Path(out_dir)
    heat = zac_data.load('model_issue_heatmap')       # Zac's cell 21 table: model, n, % per category
    mix = zac_data.load('model_issue_mix')            # Zac's cell 20 counts: model, category, cases
    issue_mix = zac_data.load('issue_mix').set_index('category')
    workload = zac_data.load('model_workload').set_index('model')
    sg = zac_data.load('service_groups').set_index('service_group').cases
    rq = zac_data.load('record_quality')

    cats = [c for c in heat.columns if c not in ('model', 'n', OTHER)]
    counts = zac_table(mix)
    shares = heat.set_index('model')[cats + [OTHER]]   # % of each model's unplanned tickets (Zac's cell 21 table)
    n_per_model = heat.set_index('model').n
    total = int(mix.cases.sum())

    # Checks: the committed table is Zac's cell 21 on his cell 20 counts; rows are complete; totals agree.
    style.check('zac_09 heatmap = Zac\'s cell 21 recomputed from model_issue_mix', 0,
                float((100 * counts.div(counts.sum(axis=1), axis=0) - shares).abs().to_numpy().max()), 1e-9)
    style.check('zac_09 rows and columns = Zac\'s selection and order', 1,
                int(counts.index.tolist() == heat.model.tolist()
                    and counts.columns.tolist() == shares.columns.tolist()))
    style.check('zac_09 n = model\'s unplanned tickets', 0, int((counts.sum(axis=1) - n_per_model).abs().sum()))
    style.check('zac_09 rows sum to 100% before rounding', 0, float((shares.sum(axis=1) - 100).abs().max()), 1e-9)
    style.check('zac_09 unplanned tickets = service_groups without planned/cancelled/duplicate',
                int(sg.drop(PLANNED_GROUPS).sum()), total)
    style.check('zac_09 unplanned tickets = issue_mix total', int(issue_mix.cases.sum()), total)
    style.check('zac_09 unplanned <= all tickets per model (model_workload)', 0,
                int((n_per_model > workload.cases.reindex(n_per_model.index)).sum()))
    by_model = mix.groupby('model').cases.sum().sort_values(ascending=False)
    by_cat = mix.groupby('category').cases.sum().sort_values(ascending=False)
    style.check('zac_09 no tie at the top-8 model cutoff', 1,
                int(by_model.iloc[N_MODELS - 1] > by_model.iloc[N_MODELS]))
    style.check('zac_09 no tie at the top-7 category cutoff', 1, int(by_cat.iloc[N_CATS - 1] > by_cat.iloc[N_CATS]))
    style.check('zac_09 [Missing] is pooled in Other', 1, int(MISSING in by_cat.index and MISSING not in cats))

    # All-models reference row: each category's share of all unplanned tickets (Zac's issue_mix, cell 20).
    fleet = 100 * by_cat.reindex(cats) / total
    style.check('zac_09 all-models row = issue_mix share_pct', 0,
                float((fleet - issue_mix.share_pct.reindex(cats)).abs().max()), 1e-9)
    fleet_n = by_cat.reindex(cats).to_numpy()

    # Discrete colour scale: a pale bin for cells with no tickets (as in htm_08), then one blue step per STEP points.
    named = shares[cats].to_numpy()
    named_n = counts[cats].to_numpy()
    n_steps = math.ceil(named.max() / STEP)
    idx = np.linspace(0, len(style.BLUE_RAMP) - 1, n_steps).round().astype(int)
    cmap = ListedColormap([style.ZERO_CELL] + [style.BLUE_RAMP[i] for i in idx])
    norm = BoundaryNorm(np.arange(-STEP, STEP * (n_steps + 1), STEP), cmap.N)
    binned = np.where(named_n == 0, -STEP / 2, named)   # no tickets -> the pale bin below 0

    def step(val):
        return idx[min(int(val // STEP), n_steps - 1)]

    n_rows, n_cols = len(shares), len(cats)
    fleet_y = n_rows + GAP              # top edge of the all-models row
    other_x = n_cols + GAP              # left edge of the Other column
    fig, ax = style.figure(12, BANDS_IN + ROW_IN * (fleet_y + 1))
    mesh = ax.pcolormesh(np.arange(n_cols + 1), np.arange(n_rows + 1), binned, cmap=cmap, norm=norm,
                         edgecolors=style.SURFACE, linewidth=2.0)
    ax.pcolormesh(np.arange(n_cols + 1), [fleet_y, fleet_y + 1], np.array([fleet.to_numpy()]), cmap=cmap, norm=norm,
                  edgecolors=style.SURFACE, linewidth=2.0)

    rows = [Row(i + 0.5, named[i], named_n[i], shares[OTHER].iloc[i], counts[OTHER].iloc[i]) for i in range(n_rows)]
    rows.append(Row(fleet_y + 0.5, fleet.to_numpy(), fleet_n, 100 - fleet.sum(), total - fleet_n.sum()))
    for row in rows:
        for j, (val, n) in enumerate(zip(row.share, row.n)):
            dark = n > 0 and step(val) >= WHITE_FROM
            ax.text(j + 0.5, row.y, label(val, n), ha='center', va='center', fontsize=10,
                    color='white' if dark else style.INK if n else style.MUTED, weight='bold' if dark else 'normal')
        # Other: plain numbers, off the colour scale.
        ax.text(other_x + 0.5, row.y, label(row.other_share, row.other_n), ha='center', va='center', fontsize=10,
                color=style.INK2)

    ax.set_xlim(0, other_x + 1)
    ax.set_ylim(fleet_y + 1, 0)
    ax.set_yticks([row.y for row in rows])
    ax.set_yticklabels([f'{m} (n={n:,})' for m, n in n_per_model.items()]
                       + [f'All {mix.model.nunique()} models (n={total:,})'], color=style.INK2, fontsize=10)
    ax.get_yticklabels()[-1].set_color(style.MUTED)
    ax.xaxis.tick_top()
    ax.set_xticks(list(np.arange(n_cols) + 0.5) + [other_x + 0.5])
    n_other_cats = by_cat.drop(MISSING).size - N_CATS   # recorded categories pooled in Other ([Missing] aside)
    ax.set_xticklabels(['\n'.join(textwrap.wrap(c, 13)) for c in cats] + [f'Other {n_other_cats}\ncategories'],
                       color=style.INK2, fontsize=10)
    style.style_axes(ax, grid=None, baseline=None)
    # Colour bar: '0%' on the pale no-ticket bin, then the step boundaries every 10 points.
    ticks = [-STEP / 2] + list(range(2 * STEP, STEP * n_steps + 1, 2 * STEP))
    cb = fig.colorbar(mesh, ax=ax, location='right', shrink=0.62, anchor=(0.0, 1.0), aspect=16, pad=0.025)
    cb.set_ticks(ticks, labels=['0%'] + [f'{t}%' for t in ticks[1:]])
    cb.outline.set_visible(False)
    cb.ax.tick_params(which='both', length=0, labelsize=9, colors=style.MUTED)
    cb.set_label('share of the model\'s unplanned tickets', color=style.MUTED, fontsize=10)

    # Title: the largest named share, against the model where that category's share is smallest.
    i, j = np.unravel_index(named.argmax(), named.shape)
    cat, top_model = cats[j], shares.index[i]
    low_model = shares[cat].idxmin()
    style.check('zac_09 one cell holds the largest share (title)', 1, int((named == named.max()).sum() == 1))
    style.check(f'zac_09 one model has the smallest {cat} share (title)', 1,
                int((shares[cat] == shares[cat].min()).sum() == 1))
    pooled = by_cat.drop(cats)
    first_out = pooled.index[0]          # the most frequent category the top-N_CATS rule pools
    lcd = shares[OTHER].idxmax()         # the model whose Other share is largest
    lcd_top = mix[(mix.model == lcd) & ~mix.category.isin(cats)].sort_values('cases', ascending=False).iloc[0]
    lcd_n = int(counts.loc[lcd].sum())
    style.check(f'zac_09 {lcd_top.category} is most of {lcd}\'s Other', 1,
                int(lcd_top.cases > counts.loc[lcd, OTHER] / 2))
    style.frame(
        fig,
        f'{cat} is {label(named[i, j], named_n[i, j])} of {top_model}\'s unplanned tickets but '
        f'{label(shares.loc[low_model, cat], counts.loc[low_model, cat])} of {low_model}\'s',
        f'Share of each model\'s unplanned tickets by Trouble Code Category, {zac_data.period_text(rq)}. The {n_rows} '
        f'models with the most unplanned tickets, and all models together (bottom row) for comparison. Columns: the '
        f'{N_CATS} most frequent categories overall, then the rest pooled (right, not coloured).',
        notes=['n = the model\'s unplanned tickets, a raw count not adjusted for installed machines. Shares are within '
               'each model, and each row sums to 100% before rounding to whole percent.',
               f'<1% = above 0 but rounds to 0%; 0% (pale gray cell) = no tickets. Other also pools {MISSING} (no '
               f'category recorded; {int(by_cat[MISSING])} tickets across all models). {lcd}\'s Other is mostly '
               f'{lcd_top.category}: {int(lcd_top.cases)} of its {lcd_n} tickets '
               f'({style.pct(lcd_top.cases / lcd_n, 0)}). {first_out} is the '
               f'{ordinal(by_cat.index.get_loc(first_out) + 1)} most frequent category ({int(pooled.iloc[0])} tickets, '
               f'{int(by_cat.iloc[N_CATS - 1] - pooled.iloc[0])} fewer than {by_cat.index[N_CATS - 1]}), so the '
               f'top-{N_CATS} rule pools it.',
               'Source: verification/outputs/repro_sql_model_issue_heatmap.csv (Zac\'s notebook cell 21), recomputed '
               'from repro_sql_model_issue_mix.csv (Zac\'s SQL, cell 20).'],
        definitions=[zac_data.UNPLANNED_DEFINITION])
    return [style.save(fig, out_dir / PNG)]


if __name__ == '__main__':
    plot()
