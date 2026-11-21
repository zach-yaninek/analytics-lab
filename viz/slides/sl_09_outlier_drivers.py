#!/usr/bin/env python3
"""Slide chart 9: what drives each consistent-outlier customer's excess tickets.

Slide version of viz/fleet_exposure/fx_12_outlier_drivers.py, with the same data and the same pattern rule. For each
of the 18 consistent-outlier customers: its machines (x, log scale) against the share of its excess unplanned
tickets (observed - expected, the model + age fit) that sits on its two machines with the most excess (y). The two
lines are the analysis' rule (verification/fleet_exposure.py, 'Drivers of outlier customers'): under 10 machines =
small fleet; otherwise the top 2 machines hold at least half of the excess = a few machines, else spread across the
fleet. Each region carries its customer count. Blue = the two groups the finding is about (small fleets, and larger
fleets with the excess spread); gray = a few machines. A share above 100% means the rest of the customer's machines
are together below expected. Two pairs of customers sit on (nearly) the same spot: Customer 587 and Customer 644 (8
machines, 62% each) and Customer 171 and Customer 641 (68 and 69 machines, 24% and 26%); each pair's dots are drawn a
few points left and right of their positions so both show, their data values unchanged.

Left out against the page chart: the per-customer rows with names, bars, net excess and top-2 share labels, the
pattern and top-category columns, and the title, subtitle and footer (card header and speaker notes).
Pseudonymous version only: no customer is named on this chart.

Input:  verification/outputs/fleet/fx_outlier_drivers.csv  (per consistent outlier: machines, tickets, expected,
                                                            excess, top2_machines_excess, top2_share_of_excess,
                                                            pattern)
        verification/outputs/fleet/fx_customer_rates.csv   (per customer: tickets, expected, machines,
                                                            consistent_outlier; independent check of the rows)
        verification/outputs/fleet/fx_machine_flags.csv   (every machine with a ticket: tickets, expected;
                                                            independent recomputation of the top-2 excess)
        verification/outputs/fleet/fx_summary.json        (consistent-outlier count)
Output: viz/figures/slides/sl_09_outlier_drivers.png (wide card)
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator  # noqa: E402
from matplotlib.transforms import ScaledTranslation  # noqa: E402

import deck_style as S  # noqa: E402

PNG = 'sl_09_outlier_drivers.png'
FLEET = S.OUT / 'fleet'
SMALL, FEW, SPREAD = 'small fleet', 'a few machines', 'spread across fleet'  # the analysis' pattern labels
FEW_SHARE = 0.5           # the analysis' rule: 'a few machines' = top-2 machines hold at least this share
COLOUR = {'small': S.BLUE, 'spread': S.BLUE, 'few': S.GRAY}
DOT = 110                 # marker area (pt^2)
DODGE_PT = 5.5            # two dots on (nearly) the same spot are drawn this far left and right of it ...
SAME_LOG_X, SAME_Y = 0.01, 2.5  # ... when their machines differ by under this (log10) and shares by under this (pts)
XLIM, YLIM = (2.4, 100), (0, 128)
XTICKS = [3, 5, 10, 20, 50, 100]


def small_threshold(patterns):
    """The machine count in the analysis' small-fleet label, e.g. 'small fleet (<10 machines)' -> 10."""
    labels = {p for p in patterns if p.startswith(SMALL)}
    if len(labels) != 1:
        raise ValueError(f'expected one small-fleet label, got {sorted(labels)}')
    return int(re.search(r'<\s*(\d+)', labels.pop()).group(1))


def pattern_rule(machines, share, small_n):
    """The analysis' pattern rule, written from its definition so the CSV labels are tested, not copied (fx_12)."""
    if machines < small_n:
        return 'small'
    return 'few' if share >= FEW_SHARE else 'spread'


def pattern_key(label):
    return 'small' if label.startswith(SMALL) else {FEW: 'few', SPREAD: 'spread'}[label]


def checks(summ, dr, cr, mf):
    """fx_12's checks against the customer and machine tables; returns the consistent outliers with the
    recomputed excess, top-2 share and pattern."""
    n_cons = summ['customers']['consistent_outliers']
    c = dr[dr.consistent_outlier].copy()
    S.check('sl_09 consistent outliers in drivers = summary (18)', n_cons, len(c))
    S.check('sl_09 consistent outliers in customer table = summary', n_cons, int(cr.consistent_outlier.sum()))
    S.check('sl_09 drivers rows = consistent outliers of the customer table', 1,
            int(set(c.customer) == set(cr.customer[cr.consistent_outlier])))
    ci = cr.set_index('customer').loc[c.customer]
    S.check('sl_09 tickets = customer table', 0, int(np.abs(ci.tickets.to_numpy() - c.tickets.to_numpy()).max()))
    S.check('sl_09 expected = customer table', 0, float(np.abs(ci.expected.to_numpy() - c.expected.to_numpy()).max()),
            1e-6)
    S.check('sl_09 machines = customer table', 0, int(np.abs(ci.machines.to_numpy() - c.machines.to_numpy()).max()))
    excess = ci.tickets.to_numpy() - ci.expected.to_numpy()
    S.check('sl_09 excess = tickets - expected (customer table)', 0, float(np.abs(excess - c.excess.to_numpy()).max()),
            1e-6)
    S.check('sl_09 every excess is positive', 1, int((excess > 0).all()))

    # Machine table: tickets per customer, and the two machines with the most excess.
    mf = mf.assign(excess=mf.tickets - mf.expected)
    by_cust = mf.groupby('customer').tickets.sum().reindex(c.customer).fillna(0).to_numpy()
    S.check('sl_09 tickets = sum of the machines\' tickets', 0, int(np.abs(by_cust - c.tickets.to_numpy()).max()))
    top2, second = [], []
    for cust in c.customer:
        ex = np.sort(mf.excess[mf.customer == cust].to_numpy())[::-1]
        top2.append(float(ex[:2].sum()))
        second.append(float(ex[1]) if len(ex) > 1 else -np.inf)
    top2 = np.array(top2)
    S.check('sl_09 the top-2 machines all have positive excess', 1, int((np.array(second) > 0).all()))
    S.check('sl_09 top-2 excess recomputed from the machine table', 0,
            float(np.abs(top2 - c.top2_machines_excess.to_numpy()).max()), 1e-6)
    share = top2 / excess
    S.check('sl_09 top-2 share = top-2 excess / excess', 0, float(np.abs(share - c.top2_share_of_excess.to_numpy()).max()),
            1e-9)

    small_n = small_threshold(dr.pattern)
    S.check('sl_09 small-fleet threshold (10 machines)', 10, small_n)
    rule = [pattern_rule(m, s, small_n) for m, s in zip(ci.machines, share)]
    S.check('sl_09 pattern rule reproduces every CSV pattern', 0,
            sum(r != pattern_key(p) for r, p in zip(rule, c.pattern)))
    # The lines are drawn at the thresholds: no customer sits on one.
    S.check('sl_09 no customer at exactly the small-fleet threshold', 0, int((c.machines == small_n).sum()))
    S.check('sl_09 no top-2 share exactly at the threshold', 0, int((np.abs(share - FEW_SHARE) < 1e-12).sum()))
    c['excess_chk'], c['share_chk'], c['rule'] = excess, share, rule
    c['key'] = [pattern_key(p) for p in c.pattern]
    return c, small_n


def plot(out_dir=S.FIG_DIR):
    summ = json.loads((FLEET / 'fx_summary.json').read_text())
    dr = pd.read_csv(FLEET / 'fx_outlier_drivers.csv')
    cr = pd.read_csv(FLEET / 'fx_customer_rates.csv')
    mf = pd.read_csv(FLEET / 'fx_machine_flags.csv')
    c, small_n = checks(summ, dr, cr, mf)
    n = len(c)

    # Counts drawn: from the CSV patterns, checked against the rule recomputed from the customer and machine tables.
    count = {k: int((c.key == k).sum()) for k in ('small', 'few', 'spread')}
    for k, drawn in (('small', 9), ('few', 3), ('spread', 6)):
        S.check(f'sl_09 drawn {k} count ({drawn})', drawn, count[k])
        S.check(f'sl_09 {k} count (recomputed rule)', count[k], sum(r == k for r in c.rule))
    S.check('sl_09 drawn larger fleets (9)', 9, n - count['small'])
    S.check('sl_09 drawn consistent outliers (18)', 18, n)
    tot_t, tot_e = int(c.tickets.sum()), float(c.expected.sum())
    exp_txt = f'{tot_e:.0f}'
    S.check('sl_09 drawn total tickets (737)', 737, tot_t)
    S.check('sl_09 total tickets = customer table', tot_t,
            int(cr.set_index('customer').loc[c.customer].tickets.sum()))
    S.check('sl_09 drawn total expected (318)', 318, float(exp_txt))
    S.check('sl_09 drawn total expected = tickets - excess (customer table)', float(exp_txt),
            tot_t - float(c.excess_chk.sum()), 0.5)

    fig, ax = S.figure(S.WIDE)
    ax.set_xscale('log')
    ax.set_xlim(*XLIM)
    ax.set_ylim(*YLIM)
    # The rule's lines: 10 machines (full height), and 50% for the larger fleets only.
    ax.axvline(small_n, color=S.INK2, lw=1.2, zorder=2)
    ax.plot([small_n, XLIM[1]], [FEW_SHARE * 100] * 2, color=S.INK2, lw=1.2, zorder=2)

    # Dots; two on (nearly) the same spot are drawn side by side, the one with fewer machines (or the lower share)
    # on the left. The data values are unchanged; only the marker is shifted, in points.
    x, y = c.machines.to_numpy(float), 100 * c.share_chk.to_numpy()
    dodge = np.zeros(n)
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            if abs(np.log10(x[i] / x[j])) < SAME_LOG_X and abs(y[i] - y[j]) < SAME_Y:
                left, right = sorted((i, j), key=lambda k: (x[k], y[k]))
                dodge[left], dodge[right] = -DODGE_PT, DODGE_PT
                pairs.append({c.customer.iloc[i], c.customer.iloc[j]})
    S.check('sl_09 dodged pairs = Customer 587/644 and 171/641', 1,
            int(sorted(map(sorted, pairs)) == [['Customer 171', 'Customer 641'], ['Customer 587', 'Customer 644']]))
    S.check('sl_09 no dot in two dodged pairs', 2 * len(pairs), int((dodge != 0).sum()))
    for i in range(n):
        tr = ax.transData + ScaledTranslation(dodge[i] / 72, 0, fig.dpi_scale_trans)
        ax.scatter([x[i]], [y[i]], s=DOT, color=COLOUR[c.key.iloc[i]], edgecolor=S.WHITE, linewidth=1.0, zorder=4,
                   transform=tr, clip_on=False)

    # Region labels, in the empty corner of each region.
    def region(xy, ha, va, big, small, colour):
        """A bold count line over a smaller rule line, anchored at xy by its top (va='top') or bottom corner."""
        side = 0 if ha == 'left' else 1
        kw = dict(ha=ha, zorder=6)
        if va == 'top':
            t = ax.annotate(big, xy=xy, va='top', fontsize=S.FONT + 2, color=colour, weight='bold', **kw)
            t2 = ax.annotate(small, xy=(side, 0), xycoords=t, xytext=(0, -3), textcoords='offset points', va='top',
                             fontsize=S.SMALL, color=S.INK2, **kw)
        else:
            t2 = ax.annotate(small, xy=xy, va='bottom', fontsize=S.SMALL, color=S.INK2, **kw)
            t = ax.annotate(big, xy=(side, 1), xycoords=t2, xytext=(0, 3), textcoords='offset points', va='bottom',
                            fontsize=S.FONT + 2, color=colour, weight='bold', **kw)
        return [t, t2]

    labels = []
    labels += region((2.6, 3), 'left', 'bottom', f'{count["small"]} small fleets', f'under {small_n} machines',
                     S.BLUE)
    labels += region((95, 124), 'right', 'top', f'{count["few"]} driven by a few machines',
                     'top 2 machines hold half or more', S.INK2)
    labels += region((95, 3), 'right', 'bottom', f'{count["spread"]} with the excess spread',
                     'top 2 machines hold under half', S.BLUE)
    total = ax.text(2.6, 124, f'All {n}: {tot_t} unplanned tickets\nagainst {exp_txt} expected', ha='left', va='top',
                    fontsize=S.SMALL, color=S.INK, linespacing=1.15, zorder=6)
    labels.append(total)

    ax.xaxis.set_major_locator(FixedLocator(XTICKS))
    ax.xaxis.set_minor_locator(NullLocator())
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:g}'))
    ax.set_yticks([0, 25, 50, 75, 100])
    S.pct_axis(ax.yaxis)
    S.style_axes(ax, grid='y', baseline='bottom')
    ax.set_xlabel("Machines in the customer's fleet (log scale)")
    ax.set_ylabel('Share of excess on top 2 machines')

    # No dot under a label (display coordinates, after layout).
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    pts = ax.transData.transform(np.column_stack([x, y])) + np.column_stack([dodge / 72 * fig.dpi, np.zeros(n)])
    rad = np.sqrt(DOT) / 2 / 72 * fig.dpi
    under = 0
    for t in labels:
        bb = t.get_window_extent(r).padded(rad)
        under += int(((pts[:, 0] > bb.x0) & (pts[:, 0] < bb.x1) & (pts[:, 1] > bb.y0) & (pts[:, 1] < bb.y1)).sum())
    S.check('sl_09 no dot under a label', 0, under)
    boxes = [t.get_window_extent(r) for t in labels]
    overlaps = sum(boxes[i].overlaps(boxes[j]) for i in range(len(boxes)) for j in range(i + 1, len(boxes)))
    S.check('sl_09 labels do not overlap', 0, overlaps)
    # Every dot shows: no two dot centres closer than 60% of a dot's diameter.
    d = np.hypot(pts[:, None, 0] - pts[None, :, 0], pts[:, None, 1] - pts[None, :, 1]) + np.eye(n) * 1e9
    S.check('sl_09 every dot visible (centres at least 0.6 diameters apart)', 1, int(d.min() >= 0.6 * 2 * rad))
    return [S.save(fig, Path(out_dir) / PNG)]


if __name__ == '__main__':
    plot()
