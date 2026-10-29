#!/usr/bin/env python3
"""Slide chart 30 (follow-up to slide 5): the 30-day pairing matrix of the four models with the most repeats.

Small multiples (docs/09 §5 B6): one group-level pairing matrix per model, for the four models (by the ticket's model)
with the most repeats within 30 days in rp_by_model.csv ('Other models' left out). Rows = the index ticket's request
type, columns = the next ticket's type, on six groups: Door, Mechanical, Electronics, No Trouble Found, Monitoring and
Rest (Network, Software, Operator error, Other and Not categorised). Cell = share of the row's repeats (each row sums
to 100%), shaded white to blue, the diagonal outlined in navy; cells with fewer than 5 pairs have lighter text, in
italic, and INK2 where that stays legible on the cell (contrast 3:1 or more). Panel title: the model and its
repeats.

Input:  verification/outputs/followups/rp_model_matrices.csv (unit_kind 'model', window '30 days'), rp_by_model.csv,
        rp_pairs.csv, followups_summary.json
Output: viz/figures/slides/sl_30_model_matrices.png (full card, tall)
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import deck_style as S  # noqa: E402
import followup_terms as T  # noqa: E402
from sl_24_repeat_pairings_7d import draw_cells, pct_drawn  # noqa: E402

PNG = 'sl_30_model_matrices.png'
TERMS = ['pairing_panel', 'rest_panel', 'repeat', 'matrix_models']
N_PANELS = 4
OWN = ['Door', 'Mechanical', 'Electronics', 'No Trouble Found', 'Monitoring']   # groups with their own row/column
ROWS = OWN + ['Rest']
SHORT = ['Door', 'Mech.', 'Electr.', 'NTF', 'Monit.', 'Rest']
SMALL_CELL = 5          # fewer pairs than this: lighter text


def six(group):
    return group if group in OWN else 'Rest'


def plot(out_dir=S.FIG_DIR):
    mm = pd.read_csv(T.FU / 'rp_model_matrices.csv')
    mm = mm[(mm.unit_kind == 'model') & (mm.window == '30 days')]
    bym = pd.read_csv(T.FU / 'rp_by_model.csv')
    p = pd.read_csv(T.FU / 'rp_pairs.csv')
    groups = T.summary()['definitions']['groups']
    S.check('sl_30 every group in the matrices is one of the ten', 0,
            len((set(mm.index_group) | set(mm.next_group)) - set(groups)))
    S.check('sl_30 small_cell flag = fewer than 5 pairs', 0, int((mm.small_cell != (mm.pairs < SMALL_CELL)).sum()))

    ranked = bym[~bym.pooled.astype(bool) & (bym.model != 'Other models')].sort_values('repeats_30', ascending=False)
    models = ranked.model.head(N_PANELS).tolist()
    S.check('sl_30 four panels', N_PANELS, len(models))
    S.check('sl_30 no tie at the cut: the 4th model has more repeats than the 5th', 1,
            int(ranked.repeats_30.iloc[N_PANELS - 1] > ranked.repeats_30.iloc[N_PANELS]))
    S.check('sl_30 the four = the four largest model matrices in rp_model_matrices.csv', 1,
            int(mm.groupby('unit').pairs.sum().nlargest(N_PANELS).index.tolist() == models))

    fig, ax0 = S.figure(S.FULL_TALL)
    ax0.remove()
    axes = fig.subplots(1, N_PANELS)
    fig.get_layout_engine().set(wspace=0.08)       # a clear gap between the panels
    for k, (ax, model) in enumerate(zip(axes, models)):
        tag = f'sl_30 {model}'
        x = mm[mm.unit == model]
        counts = (x.assign(i=x.index_group.map(six), n=x.next_group.map(six))
                  .pivot_table(index='i', columns='n', values='pairs', aggfunc='sum')
                  .reindex(index=ROWS, columns=ROWS).fillna(0).astype(int))
        n = int(counts.to_numpy().sum())
        S.check(f'{tag} panel total = rp_by_model.csv repeats_30', bym.set_index('model').repeats_30[model], n)
        r = p[(p.model == model) & p.repeat_30]
        from_pairs = pd.crosstab(r.index_group.map(six), r.next_group.map(six)).reindex(
            index=ROWS, columns=ROWS, fill_value=0)
        S.check(f'{tag} matrix = rp_pairs.csv repeats, every cell', 0,
                int(np.abs(from_pairs.to_numpy() - counts.to_numpy()).max()))
        row_tot = counts.to_numpy().sum(axis=1, keepdims=True)
        with np.errstate(invalid='ignore', divide='ignore'):
            shares = np.where(row_tot > 0, counts.to_numpy() / np.where(row_tot > 0, row_tot, 1), np.nan)
        drawn = draw_cells(ax, shares, counts.to_numpy(), ink_small=SMALL_CELL)
        for i, gi in enumerate(ROWS):
            if row_tot[i, 0]:
                S.check(f'{tag} {gi} row sums to 100%', 1, float(np.nansum(shares[i])), 1e-9)
            for j, gj in enumerate(ROWS):
                txt = drawn[(i, j)]
                if txt:
                    S.check(f'{tag} {gi} -> {gj} share of the row', 100 * shares[i, j], pct_drawn(txt), 0.5)
                else:
                    S.check(f'{tag} {gi} -> {gj} blank = no pairs', 0, int(counts.iloc[i, j]))

        for i, gi in enumerate(ROWS):               # each row's repeats, right of the matrix
            n_txt = f'{int(row_tot[i, 0]):,}'
            S.check(f'{tag} {gi} row repeats', int(from_pairs.loc[gi].sum()), int(n_txt.replace(',', '')))
            ax.annotate(n_txt, xy=(1, i + 0.5), xycoords=('axes fraction', 'data'), xytext=(5, 0),
                        textcoords='offset points', ha='left', va='center_baseline', fontsize=S.DEF, color=S.INK2)
        ax.annotate('n', xy=(1, 1), xycoords='axes fraction', xytext=(5, 4), textcoords='offset points', ha='left',
                    va='bottom', fontsize=S.DEF, color=S.INK2)
        title = f'{model} ({n:,} repeats)'
        S.check(f'{tag} title repeats', bym.set_index('model').repeats_30[model],
                int(re.search(r'\(([\d,]+) repeats\)', title).group(1).replace(',', '')))
        ax.set_title(title, fontsize=S.FONT, color=S.INK, pad=10)
        ax.set_xticks(np.arange(len(ROWS)) + 0.5)
        ax.set_xticklabels(SHORT, fontsize=S.SMALL)
        ax.xaxis.tick_top()
        ax.xaxis.set_label_position('top')
        ax.tick_params(axis='x', pad=4)
        ax.set_xlabel('Next ticket', fontsize=S.SMALL, labelpad=5)
        if k == 0:
            ax.set_yticks(np.arange(len(ROWS)) + 0.5)
            ax.set_yticklabels(SHORT)
            ax.tick_params(axis='y', pad=8)
            for t in ax.get_yticklabels():
                t.set_verticalalignment('center_baseline')
            # 'Index ticket' heads the row labels, level with the column labels.
            ax.annotate('Index ticket', xy=(0, 1), xycoords='axes fraction', xytext=(-8, 4),
                        textcoords='offset points', ha='right', va='bottom', fontsize=S.SMALL, color=S.INK2)
        else:
            ax.set_yticks([])
        S.style_axes(ax, grid=None, baseline=None)

    # The definitions' numbers.
    t = T.terms()
    S.check('sl_30 definition: the four with the most repeats within 30 days', 1,
            int('the four with the most repeats within 30 days' in t['matrix_models'][1]))
    m = re.search(r'within (\d+) days \(7-day: within (\d+)\) .* before (\d+) Aug 2026 \(([\d,]+)\)', t['repeat'][1])
    S.check('sl_30 definition: within 30 days', 30, int(m.group(1)))
    S.check('sl_30 definition: 6,665 eligible', len(p), int(m.group(4).replace(',', '')))
    S.check('sl_30 every 30-day repeat within 30 days', 0, int((p[p.repeat_30].gap_days > 30).sum()))
    S.definitions(fig, T.items(TERMS))
    return [S.save(fig, Path(out_dir) / PNG)]


if __name__ == '__main__':
    plot()
