#!/usr/bin/env python3
"""Slide chart 4: unplanned tickets per 100 installed machine-months by machine age, with 95% intervals.

Slide version of viz/fleet_exposure/fx_03_rate_by_age.py, from the same age-band table (years since install at the
midpoint of each machine's exposure, Aug 2025 to Aug 2026). One bar per band, youngest on the left, its rate on the
bar and its 95% interval as a whisker (cluster bootstrap over accounts); the line is the fleet rate, 6.2. Blue = the
bands under 4 years old, each with its interval wholly above the fleet rate (about 8 per 100 together); navy = the
oldest band, 10 years or older (2.5); light gray = the bands between.

Input:  verification/outputs/fleet/fx_age_rates.csv, verification/outputs/fleet/fx_summary.json
Output: viz/figures/slides/sl_04_age_rates.png (half card)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import MultipleLocator  # noqa: E402

import deck_style as S  # noqa: E402

PNG = 'sl_04_age_rates.png'
YOUNG = ['<1', '1-2', '2-4']  # the bands under 4 years old
OLD = '10+'
BAR_W = 0.56
EXPECTED = {'<1': 8.4, '1-2': 7.8, '2-4': 7.9, '4-6': 5.0, '6-8': 5.5, '8-10': 5.6, '10+': 2.5}  # fx_03 labels


def plot(out_dir=S.FIG_DIR):
    fleet = S.OUT / 'fleet'
    summary = json.loads((fleet / 'fx_summary.json').read_text())
    F, D = summary['fleet'], summary['definitions']
    a = pd.read_csv(fleet / 'fx_age_rates.csv')
    f = F['rate_per_100']

    # Same population and logic as fx_03: the bands, in order, cover the exposed fleet; rate = 100 x tickets / months;
    # the drawn interval is the cluster bootstrap.
    S.check('sl_04 age bands = analysis age bands, in order', 1, int(a.age_band.tolist() == D['age_bands']))
    S.check('sl_04 band tickets = fleet tickets (6,750)', 6750, a.tickets.sum())
    S.check('sl_04 band months = fleet installed machine-months', F['months'], a.months.sum(), 1e-6)
    S.check('sl_04 band machines = exposed machines (8,946)', 8946, a.machines.sum())
    S.check('sl_04 fleet rate = 100 x tickets / months', f, 100 * F['tickets'] / F['months'], 1e-9)
    S.check('sl_04 fleet rate drawn (6.2)', 6.2, f, 0.05)
    a['rate'] = 100 * a.tickets / a.months
    S.check('sl_04 rate_per_100 column = 100 x tickets / months', 0, float((a.rate - a.rate_per_100).abs().max()),
            1e-9)
    S.check('sl_04 every band: cluster-bootstrap interval', 0, int((a.ci_method != 'cluster bootstrap').sum()))
    S.check('sl_04 drawn intervals = bootstrap columns', 0,
            float(max((a.ci_lo - a.boot_lo).abs().max(), (a.ci_hi - a.boot_hi).abs().max())), 1e-12)
    a = a.set_index('age_band')
    drawn = pd.Series(np.select([a.ci_lo > f, a.ci_hi < f], ['above', 'below'], 'not different'), index=a.index)
    S.check('sl_04 blue bands = the bands whose interval is wholly above the fleet line', 1,
            int(drawn[drawn == 'above'].index.tolist() == YOUNG))
    S.check('sl_04 oldest band: interval wholly below the fleet line', 1, int(drawn[OLD] == 'below'))
    S.check('sl_04 oldest band has the lowest rate', 1, int(a.rate.idxmin() == OLD))
    young = a.loc[YOUNG]
    S.check('sl_04 under 4 years together: about 8 per 100 (8.0)', 8.0,
            round(100 * young.tickets.sum() / young.months.sum(), 1))
    S.check('sl_04 youngest band / oldest band = 3.3x (fx_03 title)', 3.3, round(a.rate['<1'] / a.rate[OLD], 1))

    fig, ax = S.figure(S.HALF)
    n = len(a)
    x = np.arange(n)
    colour = [S.BLUE if b in YOUNG else S.NAVY if b == OLD else S.GRAY_LIGHT for b in a.index]
    ax.axhline(f, color=S.INK2, lw=1.2, zorder=2.5)  # over the bars, under the whiskers and labels
    ax.bar(x, a.rate, width=BAR_W, color=colour, linewidth=0, zorder=2)
    ax.errorbar(x, a.rate, yerr=[a.rate - a.ci_lo, a.ci_hi - a.rate], fmt='none', ecolor=S.INK2, elinewidth=1.5,
                capsize=5, capthick=1.5, zorder=3)
    for xi, (band, r) in zip(x, a.iterrows()):
        label = f'{r.rate:.1f}'
        S.check(f'sl_04 drawn rate {band} ({label})', float(label), r.rate, 0.05)
        S.check(f'sl_04 drawn rate {band} = fx_03 label', EXPECTED[band], float(label))
        hot = band in YOUNG or band == OLD
        ax.text(xi + BAR_W / 2 + 0.05, r.rate, label, ha='left', va='center', fontsize=S.FONT,
                color=S.INK if hot else S.INK2, weight='bold' if hot else 'normal', zorder=4)
    ax.text(n - 0.45, f + 0.12, f'Fleet {f:.1f}', ha='right', va='bottom', fontsize=S.SMALL, color=S.INK2)
    ax.set_xticks(x)
    ax.set_xticklabels([b.replace('-', '–') for b in a.index], fontsize=S.FONT, color=S.INK)
    ax.set_xlim(-0.55, n - 0.45)
    ax.set_ylim(0, 10.2)
    ax.yaxis.set_major_locator(MultipleLocator(2.5))
    ax.yaxis.set_major_formatter(lambda v, _: f'{v:g}')
    S.style_axes(ax, grid='y', baseline='bottom')
    ax.set_xlabel('Machine age, years since install')
    ax.set_ylabel('Unplanned tickets per 100\ninstalled machine-months')
    return [S.save(fig, Path(out_dir) / PNG)]


if __name__ == '__main__':
    plot()
