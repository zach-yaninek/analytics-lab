#!/usr/bin/env python3
"""Fleet chart 9: do model differences hold in both halves of the period, once machine age is allowed for?

Chart 2 compares models over the whole period. A model that really runs hotter or cooler than the fleet should do
so in each half on its own, not just on the pooled year. This chart splits the period at its midpoint and shows, for
every model with at least MIN_MACHINES machines, the age-standardised ratio to the fleet in each half: a hollow dot
for the first half and a filled dot for the second, each on its own thin 95% interval line (first half just above
the row's centre, second half just below), joined by a thin connector so each model reads as one dumbbell. Models
are sorted by the full-period age-standardised ratio, highest on top; the vertical line at 1 is the fleet. Blue =
the 95% interval lies above 1 in both halves, orange = below 1 in both halves, gray = not clear of 1 in both. Each
half's ratio comes from the analysis' own model + age fit within that half (F4, F7 of verification/
fleet_exposure.py), so 1 is the fleet's rate in that half. The x axis is logarithmic, because these are ratios
(0.5x and 2x sit the same distance from 1), and the axis label says so. The value label right of each row gives
the two ratios, first half -> second half. The title names the models beyond 1 in both halves; the subtitle counts
how many models keep their side of 1 on the point estimate alone and how many are clear of 1 in one half only.

The drawn text avoids the defined word for this rule ('consistent', which run_all ties to the customer and machine
definition): the footer note says what "in both halves" means for models instead.

Inputs:  verification/outputs/fleet/fx_outlier_models.csv  one row per rate group (models with their own rate,
                                                           plus the pooled 'Other models' row, left out here):
                                                           machines, accounts, tickets, expected_age_only,
                                                           age_std_ratio, and per half (_h1, _h2) tickets,
                                                           expected_age_only, age_std_ratio, age_std_lo/hi,
                                                           age_std_vs_fleet; consistent (the both-halves class)
         verification/outputs/fleet/fx_summary.json        period and split (half dates), fleet tickets per half,
                                                           n_boot, min_clusters, pool label, and the models the
                                                           analysis lists as above / below in both halves
Output:  viz/figures/fx_09_model_persistence.png
Run:     cd /home/user/analytics-lab && python3 -I viz/fleet_exposure/fx_09_model_persistence.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]  # python3 -I leaves the script directory off sys.path
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator  # noqa: E402

import fleet  # noqa: E402
import ipa_style as style  # noqa: E402

PNG = 'fx_09_model_persistence.png'
MIN_MACHINES = 50         # models shown: at least this many machines (smaller models have very wide half intervals)
ROW_IN = 0.40             # inches per model row (two interval lines per row)
OFFSET = 0.17             # first half drawn this far above the row centre, second half this far below (row units)
TITLE_IN_PER_CHAR = 0.12  # approximate width of one title character (15 pt bold), for the figure width
TICK_IN_PER_CHAR = 0.075  # approximate width of one y tick-label character (10 pt)
LABEL_IN = 0.95           # approximate width of a value label such as '2.65 → 2.56' (9.5 pt) plus its offset
LABEL_PAD_PT = 6          # value-label offset from the interval end, points
TICKS = [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10]
ABOVE, BELOW, NEITHER = 'consistently above', 'consistently below', 'not consistent'  # CSV values (never drawn)
CLASSES = [  # CSV class, dot / interval colour, legend text
    (ABOVE, style.BLUE, style.BLUE, 'Above the fleet in both halves: 95% interval above 1 in each'),
    (BELOW, style.ORANGE, style.ORANGE, 'Below the fleet in both halves: 95% interval below 1 in each'),
    (NEITHER, style.GRAY, style.GRAY_LIGHT, 'Not clear of 1 in both halves'),
]


def names(items):
    """'A', 'A and B', 'A, B and C'."""
    items = list(items)
    return items[0] if len(items) == 1 else ', '.join(items[:-1]) + ' and ' + items[-1]


def ratio_text(r):
    """2 decimals; 3 below 0.1, so small ratios keep two significant digits (0.025, not 0.02)."""
    return f'{r:.3f}' if r < 0.1 else f'{r:.2f}'


def side_text(models, side):
    """'only scrubBank 480 is above', 'A-LC and A-MC are below', 'no model is above'."""
    if not len(models):
        return f'no model is {side}'
    return f'{names(models)} {"is" if len(models) == 1 else "are"} {side}'


def plot(out_dir=fleet.FIG_DIR):
    out_dir = Path(out_dir)
    S = fleet.summary()
    D, F = S['definitions'], S['fleet']
    h1_text, h2_text = fleet.half_texts(S)
    om = fleet.load('outlier_models')
    pool = om.rate_group == D['pool_label']
    style.check('fx_09 one pooled row (summary pool label)', 1, int(pool.sum()))
    m = om[~pool].copy()

    # ---- checks: each half's ratios are scaled so the fleet is 1 in that half ----
    for h in ('h1', 'h2'):
        style.check(f'fx_09 fleet tickets {h} = all rate groups', F[f'tickets_{h}'], om[f'tickets_{h}'].sum(), 1e-6)
        style.check(f'fx_09 fleet ratio {h} = 1 (all rate groups)', 1.0,
                    om[f'tickets_{h}'].sum() / om[f'expected_age_only_{h}'].sum(), 1e-9)
        style.check(f'fx_09 ratio {h} = tickets / age-only reference', 0,
                    float((m[f'tickets_{h}'] / m[f'expected_age_only_{h}'] - m[f'age_std_ratio_{h}']).abs().max()),
                    1e-9)
        cls = np.select([m[f'age_std_lo_{h}'] > 1, m[f'age_std_hi_{h}'] < 1], ['above', 'below'], 'not different')
        style.check(f'fx_09 class {h} = interval against 1', 0, int((cls != m[f'age_std_vs_fleet_{h}']).sum()))
        style.check(f'fx_09 ratio {h} inside its interval', 0,
                    int(((m[f'age_std_ratio_{h}'] < m[f'age_std_lo_{h}']) |
                         (m[f'age_std_ratio_{h}'] > m[f'age_std_hi_{h}'])).sum()))
    style.check('fx_09 fleet tickets = first half + second half', F['tickets'], F['tickets_h1'] + F['tickets_h2'])
    style.check('fx_09 model tickets = first half + second half', 0,
                float((m.tickets - m.tickets_h1 - m.tickets_h2).abs().max()), 1e-9)
    style.check('fx_09 full-period ratio = tickets / age-only reference', 0,
                float((m.tickets / m.expected_age_only - m.age_std_ratio).abs().max()), 1e-9)
    both = np.select([(m.age_std_lo_h1 > 1) & (m.age_std_lo_h2 > 1), (m.age_std_hi_h1 < 1) & (m.age_std_hi_h2 < 1)],
                     [ABOVE, BELOW], NEITHER)
    style.check('fx_09 both-halves class = both intervals against 1', 0, int((both != m.consistent).sum()))
    style.check('fx_09 every class has a colour', 1, int(set(m.consistent) <= {c[0] for c in CLASSES}))
    style.check('fx_09 above in both halves = summary list', 1,
                int(sorted(m.rate_group[m.consistent == ABOVE]) == sorted(S['models']['consistently_above'])))
    style.check('fx_09 below in both halves = summary list', 1,
                int(sorted(m.rate_group[m.consistent == BELOW]) == sorted(S['models']['consistently_below'])))
    style.check('fx_09 pooled row is not beyond 1 in both halves', 1, int((om[pool].consistent == NEITHER).all()))

    # ---- selection and counts drawn ----
    d = m[m.machines >= MIN_MACHINES].sort_values(['age_std_ratio', 'rate_group'], ascending=[True, False],
                                                  kind='mergesort')  # highest ratio on top
    rest = m[m.machines < MIN_MACHINES]
    n = len(d)
    style.check('fx_09 shown + small + pooled = all rate groups', len(om), n + len(rest) + int(pool.sum()))
    # Machine and ticket counts drawn (tick labels, the not-shown note) add up to the fleet's.
    style.check('fx_09 machines shown + small + pooled = fleet machines with exposure', F['machines_exposed'],
                int(d.machines.sum() + rest.machines.sum() + om[pool].machines.sum()))
    style.check('fx_09 tickets shown + small + pooled = fleet tickets', F['tickets'],
                d.tickets.sum() + rest.tickets.sum() + om[pool].tickets.sum(), 1e-6)
    style.check('fx_09 no model under the machine cut is beyond 1 in both halves', 0,
                int((rest.consistent != NEITHER).sum()))
    above = d[d.consistent == ABOVE].sort_values('age_std_ratio', ascending=False)
    below = d[d.consistent == BELOW].sort_values('age_std_ratio', ascending=False)
    n_neither = int((d.consistent == NEITHER).sum())
    style.check('fx_09 classes add up to the models shown', n, len(above) + len(below) + n_neither)
    style.check('fx_09 above in both halves (drawn intervals)', len(above),
                int(((d.age_std_lo_h1 > 1) & (d.age_std_lo_h2 > 1)).sum()))
    style.check('fx_09 below in both halves (drawn intervals)', len(below),
                int(((d.age_std_hi_h1 < 1) & (d.age_std_hi_h2 < 1)).sum()))
    # Point estimates on the same side of 1 in both halves, and models clear of 1 in one half only.
    same_side = int((np.sign(np.log(d.age_std_ratio_h1)) == np.sign(np.log(d.age_std_ratio_h2))).sum())
    style.check('fx_09 same side of 1 in both halves (recount)', same_side,
                int((((d.age_std_ratio_h1 > 1) & (d.age_std_ratio_h2 > 1)) |
                     ((d.age_std_ratio_h1 < 1) & (d.age_std_ratio_h2 < 1))).sum()))
    clear1 = (d.age_std_vs_fleet_h1 != 'not different').to_numpy()
    clear2 = (d.age_std_vs_fleet_h2 != 'not different').to_numpy()
    one_half = int((clear1 ^ clear2).sum())
    style.check('fx_09 clear of 1 in one half only (intervals)', one_half,
                int((((d.age_std_lo_h1 > 1) | (d.age_std_hi_h1 < 1)) ^
                     ((d.age_std_lo_h2 > 1) | (d.age_std_hi_h2 < 1))).sum()))
    opposite = int((clear1 & clear2 & (d.consistent == NEITHER).to_numpy()).sum())  # clear both times, flipped
    style.check('fx_09 every model shown has tickets in each half (no zero ratio drawn)', 0,
                int(((d.tickets_h1 == 0) | (d.tickets_h2 == 0)).sum()))
    weak = d[(d.accounts < D['min_clusters']) | (d.tickets_h1 == 0) | (d.tickets_h2 == 0)]
    # Half dates drawn in the legend, recomputed from the period and the split.
    start, end, split = (pd.Timestamp(x) for x in (*D['period'], D['split']))
    last1 = split - pd.Timedelta(days=1)
    style.check('fx_09 first-half dates = period start to the day before the split', 1,
                int(h1_text == f'{start.day} {start:%b %Y} to {last1.day} {last1:%b %Y}'))
    style.check('fx_09 second-half dates = split to period end', 1,
                int(h2_text == f'{split.day} {split:%b} to {end.day} {end:%b %Y}'))
    style.check('fx_09 split = midpoint of the period (days)', 0,
                abs((split - start).days - (end + pd.Timedelta(days=1) - split).days), 1)

    # ---- title ----
    only = 'only ' if len(above) else ''
    title = (f'After allowing for age, {only}{side_text(above.rate_group, "above")} the fleet in both halves; '
             f'{side_text(below.rate_group, "below")}')

    # ---- geometry: log x axis wide enough for the value labels right of the widest intervals ----
    labels = [f'{t}  ·  {k:,} machines' for t, k in zip(d.rate_group, d.machines)]
    fig_w = max(10.0, TITLE_IN_PER_CHAR * len(title) + 2 * style.MARGIN)
    axes_in = fig_w - 2 * style.MARGIN - TICK_IN_PER_CHAR * max(len(s) for s in labels) - 0.3
    lows = d[['age_std_lo_h1', 'age_std_lo_h2']].to_numpy()
    highs = d[['age_std_hi_h1', 'age_std_hi_h2']].to_numpy()
    points = d[['age_std_ratio_h1', 'age_std_ratio_h2']].to_numpy()
    positive = np.concatenate([lows[lows > 0], points.ravel()])
    L = np.log10(positive.min() / 1.6)  # left edge (decades); intervals reaching 0 run to it
    w = LABEL_IN / axes_in  # label width as a share of the axes width
    top_hi = np.log10(highs.max(axis=1))
    H = float(max(np.log10(5), ((top_hi - w * L) / (1 - w)).max()))  # right edge: room for the widest label
    xlo, xhi = 10 ** L, 10 ** H
    to_zero = d.rate_group[(lows == 0).any(axis=1)].tolist()

    # ---- draw ----
    fig, ax = style.figure(fig_w, 4.9 + ROW_IN * n)
    y = np.arange(n)
    ax.axvline(1, color=style.INK2, lw=1, zorder=1)
    color_of = {c: (dot, line) for c, dot, line, _ in CLASSES}
    for yi, r in zip(y, d.itertuples()):
        dot, line = color_of[r.consistent]
        y1, y2 = yi + OFFSET, yi - OFFSET
        ax.plot([r.age_std_ratio_h1, r.age_std_ratio_h2], [y1, y2], color=line, lw=1, zorder=2)  # the dumbbell
        ax.hlines([y1, y2], [max(r.age_std_lo_h1, xlo), max(r.age_std_lo_h2, xlo)],
                  [r.age_std_hi_h1, r.age_std_hi_h2], color=line, lw=1.6, zorder=2)
        ax.plot(r.age_std_ratio_h1, y1, 'o', ms=6.5, mfc=style.SURFACE, mec=dot, mew=1.6, zorder=3)
        ax.plot(r.age_std_ratio_h2, y2, 'o', ms=6.5, mfc=dot, mec=style.SURFACE, mew=0.8, zorder=3)
        hot = r.consistent != NEITHER
        ax.annotate(f'{ratio_text(r.age_std_ratio_h1)} → {ratio_text(r.age_std_ratio_h2)}',
                    xy=(max(r.age_std_hi_h1, r.age_std_hi_h2), yi), xytext=(LABEL_PAD_PT, 0),
                    textcoords='offset points', va='center', ha='left', fontsize=9.5,
                    color=style.INK if hot else style.INK2, weight='bold' if hot else 'normal')
    ax.text(1, n - 0.45, '  Fleet = 1', va='bottom', ha='left', fontsize=9.5, color=style.INK2)
    ax.set_xscale('log')
    ax.xaxis.set_major_locator(FixedLocator([t for t in TICKS if xlo <= t <= xhi]))
    ax.xaxis.set_minor_locator(NullLocator())
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:g}×'))
    ax.set_xlim(xlo, xhi)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, color=style.INK2)
    ax.set_ylim(-0.7, n + 0.25)
    style.style_axes(ax, grid='x', baseline=None)
    ax.set_xlabel('Age-standardised ratio to the fleet (log scale: 0.5× and 2× are the same distance from 1)')
    handles = [Line2D([], [], color=line, lw=1.6, marker='o', ms=6.5, mfc=dot, mec=style.SURFACE,
                      label=f'{text} ({int((d.consistent == cls).sum())})') for cls, dot, line, text in CLASSES]
    handles += [Line2D([], [], color=style.GRAY_LIGHT, lw=1.6, marker='o', ms=6.5, mfc=style.SURFACE,
                       mec=style.GRAY, mew=1.6, label=f'First half, {h1_text} (hollow, upper line)'),
                Line2D([], [], color=style.GRAY_LIGHT, lw=1.6, marker='o', ms=6.5, mfc=style.GRAY,
                       mec=style.SURFACE, label=f'Second half, {h2_text} (filled, lower line)')]
    ax.legend(handles=handles, loc='upper left', handlelength=2.2, frameon=True, facecolor=style.SURFACE,
              edgecolor='none', framealpha=1)

    # ---- text ----
    both_txt = (f'only {len(above) + len(below)} are clear of 1 on the same side in both ({opposite} on opposite '
                f'sides)' if opposite else f'only {len(above) + len(below)} are clear of 1 in both')
    subtitle = (f'Age-standardised ratio of each model\'s tickets to the fleet\'s, first half and second half of '
                f'{fleet.period_text(S)}, with 95% intervals: the {n} models with at least {MIN_MACHINES} machines, '
                f'sorted by the full-period ratio. {same_side} of the {n} sit on the same side of 1 in both halves, '
                f'but {both_txt}; {one_half} more are clear of 1 in one half only.')
    weak_txt = (f'; for {names(weak.rate_group.tolist())} (fewer than {D["min_clusters"]} accounts or no tickets in '
                f'a half), the wider of that and Byar\'s Poisson interval' if len(weak) else '')
    zero_txt = (f' The lower ends for {names(to_zero)} reach 0 and run to the left edge.' if to_zero else '')
    rule_note = (f'Above (below) the fleet in both halves = the model\'s 95% interval lies wholly above (below) 1 in '
                 f'each half. Each half\'s ratio comes from a model + age fit within that half, so 1 = the fleet in '
                 f'that half. Intervals: cluster bootstrap over accounts ({S["n_boot"]:,} draws), since tickets '
                 f'cluster within accounts{weak_txt}.{zero_txt}')
    rest_note = (f'Not shown: {len(rest)} models with fewer than {MIN_MACHINES} machines '
                 f'({int(rest.machines.sum())} machines, {int(rest.tickets.sum())} tickets) and the pooled group of '
                 f'small models ({int(om[pool].machines.sum())} machines, {int(om[pool].tickets.sum())} tickets); '
                 f'none is beyond 1 in both halves. '
                 + fleet.source('outlier_models').rstrip('.') + '; half dates and draws from fx_summary.json.')
    style.frame(fig, title, subtitle, definitions=[fleet.AGE_STD_DEFINITION], notes=[rule_note, rest_note])
    return [style.save(fig, out_dir / PNG)]


if __name__ == '__main__':
    plot()
