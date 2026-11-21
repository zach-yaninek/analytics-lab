#!/usr/bin/env python3
"""Association chart 7: which tickets the Category results can speak to (a funnel).

From the 2,911 primary tickets used at 7 days: those whose Category has a code set (crosswalk v0), those whose machine
type logs that code set (docs/07 A10; the base of H1 and of every per-set result), and those of them on scrubex
machines. The footer breaks down the mapped tickets that cannot be checked, by machine family and for the three
Categories most affected. Everything comes from committed outputs; no new data.

Inputs:  verification/outputs/assoc/as_pairs.csv, as_sets.csv, as_by_type.csv; verification/reference/crosswalk_v0.csv
Output:  viz/figures/as_07_coverage.png
Run:     cd /home/user/analytics-lab && python3 -I viz/association/as_07_coverage.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import assoc  # noqa: E402
import ipa_style as style  # noqa: E402

PNG = 'as_07_coverage.png'


def family(t):
    if t.startswith('scrubex'):
        return 'scrubex'
    if t.startswith('alex') or t.startswith('alc'):
        return 'alEx'
    if t.startswith('mlc'):
        return 'mlc'
    if t.startswith('sbsx'):
        return 'sbsx'
    if t.startswith('sd'):
        return 'sd'
    return t


def plot(out_dir=assoc.FIG_DIR):
    out_dir = Path(out_dir)
    p = pd.read_csv(assoc.ASSOC / 'as_pairs.csv', dtype=str, keep_default_na=False)
    p = p[(p.in_primary == '1') & (p.determined_7d == '1')]
    S = assoc.summary()['pinned_counts']
    sets = assoc.load('sets')
    sets = sets[sets.k == assoc.K7]
    bt = assoc.load('by_type')
    bt = bt[(bt.k == assoc.K7) & (bt.set == 'own set')]
    emit = bt[bt.scope.str.startswith('emitting')].set_index('type').n_pairs
    alltypes = bt[bt.scope == 'all types'].set_index('type').n_pairs
    paired = len(p)
    mapped = int((p.target_codes != '').sum())
    checkable = int(sets.n_pairs.sum())
    scrubex = int(emit[[t for t in emit.index if t.startswith('scrubex')]].sum())
    style.check('as_07 paired = pinned 7-day pairs', S['A8 determined pairs 7d'], paired)
    style.check('as_07 mapped = pinned mapped at 7 days', S['A8 mapped 7d'], mapped)
    style.check('as_07 checkable = pinned H1 population', S['H1 population 7d'], checkable)
    style.check('as_07 checkable = sum over emitting types', checkable, int(emit.sum()))
    style.check('as_07 mapped = sum over all types', mapped, int(alltypes.sum()))
    gap = (alltypes - emit.reindex(alltypes.index).fillna(0)).astype(int)
    by_fam = gap.groupby([family(t) for t in gap.index]).sum()
    by_fam = by_fam[by_fam > 0].sort_values(ascending=False)
    n_unk = int(gap.get('Unknown', 0))
    style.check('as_07 not checkable = mapped - checkable', mapped - checkable, int(by_fam.sum()))
    xw = pd.read_csv(assoc.ROOT / 'verification' / 'reference' / 'crosswalk_v0.csv', dtype=str,
                     keep_default_na=False).set_index('category')
    per_cat = p[p.target_codes != ''].groupby('category').size()
    checked = dict(zip(sets.set, sets.n_pairs))  # n_pairs per code set: tickets on types that log it
    miss = {c: (int(n - checked.get(xw.loc[c, 'target_codes'], 0)), int(n)) for c, n in per_cat.items()}
    top = sorted(miss.items(), key=lambda kv: -kv[1][0])[:3]
    share = scrubex / checkable
    title = (f'H1 and the per-set results rest on {checkable:,} of {paired:,} tickets, {share:.0%} of them on '
             f'scrubex machines')

    stages = [(f'{paired:,} tickets with a clean control, final 7 days', paired, False),
              (f'{mapped:,} whose Category has a code set', mapped, False),
              (f'{checkable:,} whose machine type logs that code set', checkable, False),
              (f'{scrubex:,} of them on scrubex machines', scrubex, True)]
    fig, ax = style.figure(max(10.5, 0.12 * len(title) + 2 * style.MARGIN), 5.2)
    y = np.arange(len(stages))[::-1]
    for yi, (lab, v, hot) in zip(y, stages):
        ax.barh(yi, v, height=0.55, color=style.BLUE if hot else style.GRAY_LIGHT, zorder=2)
        ax.text(v + paired * 0.01, yi, f'{v / paired:.0%}', va='center', ha='left', fontsize=10,
                color=style.INK if hot else style.INK2)
    ax.set_yticks(y)
    ax.set_yticklabels([s[0] for s in stages], color=style.INK2)
    ax.set_xlim(0, paired * 1.1)
    style.thousands_axis(ax.xaxis)
    style.style_axes(ax, grid='x', baseline=None)
    ax.set_xlabel('Tickets')
    fam_txt = ', '.join(f'{f} {n}' for f, n in by_fam.items())
    cat_txt = '; '.join(f'{c} {m} of {n}' for c, (m, n) in top)
    style.frame(
        fig, title,
        f'{paired - mapped:,} tickets have a Category with no code set (Touchscreen, Curtain, No Trouble Found, power, '
        f'network and others) or no Category, so the codes cannot speak to them. Of the {mapped:,} that have one, '
        f'{mapped - checkable} cannot be checked: {mapped - checkable - n_unk} are on machine types that do not log it '
        f'and {n_unk} are of unknown type. The rest, the base of H1 and of every per-set result, are almost all on '
        f'scrubex machines.',
        definitions=[assoc.LOGS_DEFINITION, assoc.TARGET_DEFINITION, assoc.CONTROL_DEFINITION],
        notes=[f'Mapped tickets that cannot be checked, by family: {fam_txt}. Most affected Categories: {cat_txt}. '
               f'H2a, H1, the recency curve and item 4 therefore say almost nothing about alEx or mlc machines (IPA to '
               f'confirm which codes each family can emit).',
               assoc.source('pairs', 'sets', 'by_type')])
    return [style.save(fig, out_dir / PNG)]


if __name__ == '__main__':
    plot()
