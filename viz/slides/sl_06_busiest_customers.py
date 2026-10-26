#!/usr/bin/env python3
"""Slide chart 6: the 15 customers with the most unplanned tickets, observed against expected from their fleets.

Slide version of viz/fleet_exposure/fx_06_busiest_customers.py. A customer with many tickets is not necessarily a
problem customer: it may simply have many machines, or models and ages that generate tickets at a high fleet rate.
One row per customer, busiest on top: a gray ring at expected tickets (what its machines would generate at fleet
rates for their model and age, the model + age fit), a filled dot at observed unplanned tickets on listed machines,
both counts at the outer ends. Dot colour, as in fx_06: blue = consistent outlier, light blue = flagged (Poisson rule)
but not consistent, gray = not flagged. The busiest, Customer 029 (114 against 102 expected), is in line with its
fleet; Customer 171, one ticket behind, has 113 against 59 expected.

Left out against the page chart: the machine counts in the row labels and the STR column (STR = observed / expected,
the ratio of the two numbers drawn on each row). Pseudonymous version only: no real-name variant is drawn here.

Input:  verification/outputs/fleet/fx_customer_rates.csv  (one row per customer: tickets, expected, STR, flags)
        verification/outputs/fleet/fx_machine_flags.csv   (every machine with a ticket: independent check of tickets)
        verification/outputs/fleet/fx_summary.json        (flag thresholds, fleet totals, customer flag counts)
Output: viz/figures/slides/sl_06_busiest_customers.png (half card)
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

import deck_style as S  # noqa: E402

PNG = 'sl_06_busiest_customers.png'
FLEET = S.OUT / 'fleet'
TOP_N = 15                # customers shown: the most unplanned tickets, as in fx_06
CLASSES = [  # (key, dot colour, legend label): fx_06's classes in the deck palette
    ('consistent', S.BLUE, 'Consistent outlier'),
    ('flagged', S.LIGHT, 'Flagged, not consistent'),
    ('not_flagged', S.GRAY, 'Not flagged'),
]
COLOUR = {key: colour for key, colour, _ in CLASSES}
# Numbers the card header and the speaker notes quote: customer -> (observed, expected as drawn).
QUOTED = {'Customer 029': (114, 102), 'Customer 171': (113, 59)}


def poisson_upper(k, mu):
    """P(X >= k) for X ~ Poisson(mu), from log-space terms (fx_06's recomputation)."""
    k = int(k)
    if k <= 0:
        return 1.0
    if mu <= 0:
        return 0.0
    log_term = lambda j: -mu + j * math.log(mu) - math.lgamma(j + 1)  # noqa: E731
    if k <= mu:
        return max(0.0, 1.0 - sum(math.exp(log_term(j)) for j in range(k)))
    total, j = 0.0, k
    while True:
        t = math.exp(log_term(j))
        total += t
        if t < total * 1e-16 or j > k + 20_000:
            return total
        j += 1


def bh(p):
    """Benjamini-Hochberg q-values."""
    p = np.asarray(p, float)
    n = len(p)
    order = np.argsort(p, kind='mergesort')
    q = np.minimum.accumulate((p[order] * n / np.arange(1, n + 1))[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.minimum(q, 1.0)
    return out


def class_of(row):
    if row.consistent_outlier:
        return 'consistent'
    return 'flagged' if row.poisson_flagged else 'not_flagged'


def checks(summ, cr, mf):
    """fx_06's consistency checks on the customer table; returns the TOP_N rows in drawing order."""
    d, F, C = summ['definitions'], summ['fleet'], summ['customers']
    S.check('sl_06 customers = population accounts', F['accounts'], len(cr))
    S.check('sl_06 customer tickets sum to the fleet', F['tickets'], int(cr.tickets.sum()))
    S.check('sl_06 expected sums to observed (fit property)', F['tickets'], float(cr.expected.sum()), 1e-6)
    by_cust = mf.groupby('customer').tickets.sum().reindex(cr.customer).fillna(0).to_numpy()
    S.check('sl_06 customer tickets = sum of its machines\' tickets', 0,
            int(np.abs(by_cust - cr.tickets.to_numpy()).max()))
    pos = cr.expected > 0
    S.check('sl_06 STR = tickets / expected', 0, float((cr.tickets[pos] / cr.expected[pos] - cr.STR[pos]).abs().max()),
            1e-9)

    # Flags recomputed: Poisson upper tail, BH over customers with expected > 0, >= min tickets.
    p = np.array([poisson_upper(o, e) for o, e in zip(cr.tickets[pos], cr.expected[pos])])
    S.check('sl_06 Poisson p recomputed', 0, float(np.abs(p - cr.p_poisson[pos].to_numpy()).max()), 1e-9)
    flag = np.zeros(len(cr), bool)
    flag[pos.to_numpy()] = (cr.tickets[pos].to_numpy() >= d['min_flag_tickets']) & (bh(p) < d['q_cut'])
    S.check('sl_06 flagged customers recomputed = poisson_flagged', 0, int((flag != cr.poisson_flagged.to_numpy()).sum()))
    S.check('sl_06 flagged customers = summary', C['poisson_flagged'], int(flag.sum()))
    # Consistent rule recomputed from the variant count and each half's Poisson p.
    p1 = np.array([poisson_upper(o, e) if e > 0 else np.nan for o, e in zip(cr.O_h1, cr.E_h1)])
    p2 = np.array([poisson_upper(o, e) if e > 0 else np.nan for o, e in zip(cr.O_h2, cr.E_h2)])
    cons = (cr.variants_flagged.to_numpy() >= d['min_variants']) & (p1 < 0.05) & (p2 < 0.05)
    S.check('sl_06 consistent outliers recomputed = consistent_outlier', 0,
            int((cons != cr.consistent_outlier.to_numpy()).sum()))
    S.check('sl_06 consistent outliers = summary', C['consistent_outliers'], int(cons.sum()))

    # The TOP_N: most tickets (ties broken by customer); no tie at the boundary.
    top = cr.sort_values(['tickets', 'customer'], ascending=[False, True], kind='mergesort').head(TOP_N)
    S.check('sl_06 top rows = CSV order', 1, int(top.customer.tolist() == cr.customer.head(TOP_N).tolist()))
    S.check('sl_06 no tie at the top-N boundary', 1,
            int(cr.tickets.nlargest(TOP_N).min() > cr.tickets.nlargest(TOP_N + 1).min()))
    S.check('sl_06 every row has expected > 0', 1, int((top.expected > 0).all()))
    S.check('sl_06 consistent outliers shown are flagged', 0, int((top.consistent_outlier & ~top.poisson_flagged).sum()))
    rows = top.index.to_numpy()
    S.check('sl_06 flagged among the top 15 (10) = recomputed', 10, int(flag[rows].sum()))
    S.check('sl_06 flagged among the top 15 = CSV', int(top.poisson_flagged.sum()), int(flag[rows].sum()))
    S.check('sl_06 consistent among the top 15 (6) = recomputed', 6, int(cons[rows].sum()))
    S.check('sl_06 consistent among the top 15 = CSV', int(top.consistent_outlier.sum()), int(cons[rows].sum()))
    # Each row against the machine table: tickets equal; expected at least the expected on machines with a ticket.
    mt = mf.groupby('customer').agg(o=('tickets', 'sum'), e=('expected', 'sum')).reindex(top.customer).fillna(0)
    S.check('sl_06 each drawn observed count = machine-table sum', 0,
            int(np.abs(mt.o.to_numpy() - top.tickets.to_numpy()).max()))
    S.check('sl_06 each expected >= expected on machines with a ticket', 0,
            int((top.expected.to_numpy() < mt.e.to_numpy() - 1e-9).sum()))
    # Each drawn expected count (no decimals) = tickets / STR, from another column.
    S.check('sl_06 each drawn expected count = tickets / STR (rounded)', 0,
            float(np.abs(np.round(top.expected) - np.round(top.tickets / top.STR)).max()))
    # The busiest is in line with its fleet: not flagged, and the 95% interval of its STR includes 1.
    b = top.iloc[0]
    S.check('sl_06 busiest is unique', 1, int(top.tickets.iloc[0] > top.tickets.iloc[1]))
    S.check('sl_06 busiest not flagged and its STR interval includes 1', 1,
            int((not b.poisson_flagged) and b.STR_lo <= 1 <= b.STR_hi))
    return top


def plot(out_dir=S.FIG_DIR):
    summ = json.loads((FLEET / 'fx_summary.json').read_text())
    cr = pd.read_csv(FLEET / 'fx_customer_rates.csv')
    mf = pd.read_csv(FLEET / 'fx_machine_flags.csv')
    top = checks(summ, cr, mf)
    n = len(top)
    cls = [class_of(r) for r in top.itertuples()]

    # The numbers drawn, as text, against the CSV.
    obs_txt = [f'{o}' for o in top.tickets]
    exp_txt = [f'{e:.0f}' for e in top.expected]
    for c, o, e, ot, et in zip(top.customer, top.tickets, top.expected, obs_txt, exp_txt):
        S.check(f'sl_06 {c} observed as drawn', float(ot), o)
        S.check(f'sl_06 {c} expected as drawn', float(et), e, 0.5)
    drawn = dict(zip(top.customer, zip(obs_txt, exp_txt)))
    for c, (o, e) in QUOTED.items():
        S.check(f'sl_06 {c} observed (card header)', o, float(drawn[c][0]))
        S.check(f'sl_06 {c} expected (card header)', e, float(drawn[c][1]))

    fig, ax = S.figure(S.HALF)
    y = np.arange(n)[::-1]  # busiest on top
    for yi, o, e, k, ot, et in zip(y, top.tickets, top.expected, cls, obs_txt, exp_txt):
        ax.plot([e, o], [yi, yi], color=S.GRAY_LIGHT, lw=2.2, solid_capstyle='butt', zorder=1)
        ax.scatter([e], [yi], s=95, facecolor=S.WHITE, edgecolor=S.GRAY, linewidth=2, zorder=2)
        ax.scatter([o], [yi], s=110, color=COLOUR[k], linewidth=0, zorder=3)
        right = o >= e
        ax.annotate(ot, xy=(o, yi), xytext=(8 if right else -8, 0), textcoords='offset points', va='center',
                    ha='left' if right else 'right', fontsize=S.SMALL, color=S.INK,
                    weight='bold' if k == 'consistent' else 'normal')
        ax.annotate(et, xy=(e, yi), xytext=(-8 if right else 8, 0), textcoords='offset points', va='center',
                    ha='right' if right else 'left', fontsize=S.SMALL, color=S.INK2)

    ax.set_ylim(-0.6, n - 0.4)
    ax.set_xlim(0, 130)
    ax.set_xticks([0, 25, 50, 75, 100, 125])
    ax.set_yticks(y)
    ax.set_yticklabels(top.customer, color=S.INK, fontsize=S.TICK)
    S.style_axes(ax, grid='x', baseline='left')
    period = ' to '.join(pd.Timestamp(x).strftime('%b %Y') for x in summ['definitions']['period'])
    S.check('sl_06 period drawn = Aug 2025 to Aug 2026', 1, int(period == 'Aug 2025 to Aug 2026'))
    ax.set_xlabel(f'Unplanned tickets, {period}')
    present = set(cls)
    handles = [Line2D([], [], marker='o', ls='', markersize=10, markerfacecolor=col, markeredgewidth=0, label=lab)
               for key, col, lab in CLASSES if key in present]
    handles.append(Line2D([], [], marker='o', ls='', markersize=9, markerfacecolor=S.WHITE, markeredgecolor=S.GRAY,
                          markeredgewidth=2, label='Expected from its fleet'))
    # The bottom rows have the fewest tickets, so the lower right of the plot is empty.
    ax.legend(handles=handles, loc='lower right', handlelength=1.0, handletextpad=0.5, borderaxespad=0.2, labelspacing=0.35,
              frameon=True, facecolor=S.WHITE, edgecolor='none', framealpha=1)
    return [S.save(fig, Path(out_dir) / PNG)]


if __name__ == '__main__':
    plot()
