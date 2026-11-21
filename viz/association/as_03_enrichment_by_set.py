#!/usr/bin/env python3
"""Association chart 3: per code set, how much more often its codes appear only before the ticket (H1 sets, 7 days).

One row per code set tested under docs/07 §4 step 3 (at least 30 tickets and 10 discordant pairs on machine types
that log the set): the matched odds ratio b/c with its 95% account-cluster bootstrap interval, on a log axis, and the
two shares (ticket window, control). Blue = enriched (b > c and Benjamini-Hochberg q <= 0.05); gray = not. An
interval with no upper end (all discordant pairs one way, e.g. Packer 33 to 0) is drawn to the right edge with an
arrow. Sets below the threshold are named in the footer.

Inputs:  verification/outputs/assoc/as_sets.csv, as_h1.csv
Output:  viz/figures/as_03_enrichment_by_set.png
Run:     cd /home/user/analytics-lab && python3 -I viz/association/as_03_enrichment_by_set.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]
import numpy as np  # noqa: E402

import assoc  # noqa: E402
import ipa_style as style  # noqa: E402

PNG = 'as_03_enrichment_by_set.png'
LO, HI = 0.5, 100.0


def plot(out_dir=assoc.FIG_DIR):
    out_dir = Path(out_dir)
    s = assoc.load('sets')
    s = s[s.k == assoc.K7]
    h1 = assoc.load('h1')
    h1 = h1[h1.k == assoc.K7].iloc[0]
    xw = __import__('pandas').read_csv(assoc.ROOT / 'verification' / 'reference' / 'crosswalk_v0.csv', dtype=str,
                                       keep_default_na=False)
    cat = {r.target_codes: r.category for r in xw.itertuples() if r.target_codes}
    tested = s[s.tested == 1].copy().sort_values('mor', kind='mergesort')
    rest = s[s.tested == 0]
    style.check('as_03 H1 = sum b / sum c', h1.estimate, h1.sum_b / h1.sum_c, 1e-9)
    style.check('as_03 tested sets meet A12', 1, int(((tested.n_pairs >= 30) & (tested.b + tested.c >= 10)).all()))
    style.check('as_03 enriched = b > c and q <= 0.05', 0,
                int((tested.enriched != ((tested.b > tested.c) & (tested.bh_q <= 0.05)).astype(int)).sum()))
    n_enr = int(tested.enriched.sum())
    weak = tested[tested.enriched == 0]
    weak_txt = ', '.join(cat[x] for x in weak.set)
    title = (f'{n_enr} of {len(tested)} code sets are clearly more often present before their tickets'
             + (f'; {weak_txt} {"is" if len(weak) == 1 else "are"} not shown to be' if len(weak) else ''))

    n = len(tested)
    fig, ax = style.figure(max(11.0, 0.12 * len(title) + 2 * style.MARGIN), 3.4 + 0.5 * n)
    y = np.arange(n)
    ax.axvline(1, color=style.INK2, lw=1)
    for yi, r in zip(y, tested.itertuples()):
        hot = r.enriched == 1
        col = style.BLUE if hot else style.GRAY
        if np.isinf(r.mor):  # all discordant pairs one way: no point estimate, an unbounded arrow from the 50 tick
            ax.annotate('', xy=(HI * 1.3, yi), xytext=(50, yi), arrowprops=dict(arrowstyle='->', color=col, lw=1.8))
            ax.text(50, yi + 0.28, 'unbounded', ha='left', va='bottom', fontsize=8.5, color=col)
        else:
            x_hi = assoc.x_of(r.mor_hi, LO, HI)
            ax.hlines(yi, assoc.x_of(r.mor_lo, LO, HI), x_hi, color=col if hot else style.GRAY_LIGHT, lw=2)
            if np.isinf(r.mor_hi):
                ax.annotate('', xy=(HI * 1.3, yi), xytext=(HI, yi),
                            arrowprops=dict(arrowstyle='->', color=col, lw=1.5))
            ax.scatter(assoc.x_of(r.mor, LO, HI), yi, s=55, color=col, edgecolors=style.SURFACE, linewidths=1.2,
                       zorder=3)
        mor = 'b/c = ' + (f'{int(r.b)}/0' if np.isinf(r.mor) else f'{r.mor:.1f}')
        ax.text(HI * 1.6, yi, f'{mor}   {r.pT:.0%} vs {r.pC:.0%}   (n = {int(r.n_pairs)})', va='center', ha='left',
                fontsize=9.5, color=style.INK if hot else style.INK2)
    ax.set_yticks(y)
    ax.set_yticklabels([assoc.set_label(cat[x], x) for x in tested.set], color=style.INK2)
    ax.set_xscale('log')
    ax.set_xlim(LO, HI * 25)
    ax.set_xticks([0.5, 1, 2, 5, 10, 20, 50, 100])
    ax.set_xticklabels(['0.5', '1', '2', '5', '10', '20', '50', '100'])
    ax.set_ylim(-0.7, n - 0.3)
    style.style_axes(ax, grid='x', baseline=None)
    ax.set_xlabel('Matched odds ratio (log scale)')
    left = '; '.join(f'{cat[r.set]} ({int(r.n_pairs)} tickets, {int(r.b + r.c)} discordant)' for r in rest.itertuples())
    style.frame(
        fig, title,
        f'H1 and the per-set step of the protocol, final 7 days. Over all {int(h1.n_pairs):,} tickets whose code set '
        f'their machine type logs, {int(h1.sum_b)} have it only before the ticket and {int(h1.sum_c)} only in the '
        f'control: matched odds ratio {h1.estimate:.1f} (95% {h1.ci_lo:.1f} to {h1.ci_hi:.1f}). Shares on the right: '
        f'ticket window vs control.',
        definitions=[assoc.MOR_DEFINITION, assoc.TARGET_DEFINITION, assoc.CONTROL_DEFINITION],
        notes=[f'Below the reporting threshold (30 tickets, 10 discordant pairs): {left}. Controls are chosen to be '
               f'ticket-free, which pushes these ratios up (docs/07 A3); H1 was expected to be positive.',
               'Blue: b > c and Benjamini-Hochberg q <= 0.05 across the tested sets (Durkalski test on account '
               'clusters). 95% intervals: bootstrap over account clusters.',
               assoc.source('sets', 'h1')])
    return [style.save(fig, out_dir / PNG)]


if __name__ == '__main__':
    plot()
