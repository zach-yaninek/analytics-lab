#!/usr/bin/env python3
"""Zac's figure 8: how concentrated the ticket workload is across customers (cumulative share curve).

Recreates 08_customer_concentration.png from Zac's notebook (cell 18). Same population (every ticket in the case
export, his `cases`), same ranking (customers by ticket count, most first) and same metric (cumulative share of
tickets against the number of customers). As he did, it marks the top 10's share and the number of customers that
together reach 50% of tickets (his k = searchsorted(cumulative share, 50) + 1); k carries the emphasis colour
because the title is about it. Added: a labelled hairline at 50% and, in the subtitle, the share of tickets from the
bottom half of customers (the 422 with the fewest tickets). The customers are the accounts with at least one ticket
(a case export has no others), so the title says "845 with tickets". No customer names or labels are drawn.

Shared text lives in zac_data.py: the customer definition (CUSTOMER_DEFINITION, from the team's review of account
names and addresses in docs/03_customer_fleet_ownership.md section 3.1), the workload note (WORKLOAD_NOTE) and the
period (period_text). zac_02_customer_workload.py draws the same definition and note.

Inputs:  zac_data.load('customer_workload')  verification/outputs/repro_sql_customer_workload.csv (customer, cases,
                                             affected_machines, share_pct; one row per customer with a ticket)
         zac_data.load('record_quality')     repro_sql_record_quality.csv (ticket and customer totals, period)
         zac_data.load('claims')             repro_sql_claims.csv (Zac's cell 18 annotations, cross-check)
Output:  viz/figures/zac_08_customer_concentration.png
Run:     cd /home/user/analytics-lab && python3 -I viz/zac_notebook/zac_08_customer_concentration.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]  # python3 -I leaves the script directory off sys.path
import numpy as np  # noqa: E402

import ipa_style as style  # noqa: E402
import zac_data  # noqa: E402

TOP_N = 10        # Zac's marked point: the top 10 customers (notebook cell 18)
HALF = 50         # Zac's marked point: customers that reach 50% of tickets (cell 18); the title says "Half"


def zac_printed(claim_id):
    """A value Zac's notebook printed or annotated, as recorded by verification/reproduce_sql.py."""
    claims = zac_data.load('claims')
    return claims.loc[claims.claim_id == claim_id, 'zac_value'].iloc[0]


def plot(out_dir=zac_data.FIG_DIR):
    cw, rq = zac_data.load('customer_workload'), zac_data.load('record_quality')
    # Zac's ranking (cell 18): customers by tickets, most first; ties do not change the curve.
    v = cw.sort_values(['cases', 'customer'], ascending=[False, True], kind='mergesort').reset_index(drop=True)
    total, n = int(v.cases.sum()), len(v)
    x = np.arange(1, n + 1)
    y = 100 * v.cases.cumsum().to_numpy() / total
    k = int(np.searchsorted(y, HALF) + 1)   # Zac's rule: the fewest customers whose cumulative share reaches 50%
    top_share, k_share = y[TOP_N - 1], y[k - 1]
    n_low = n // 2                          # the bottom half: the customers with the fewest tickets
    low_share = 100 * v.cases.tail(n_low).sum() / total

    style.check('zac_08 tickets = record_quality cases', int(rq.cases.iloc[0]), total)
    style.check('zac_08 customers = record_quality customers', int(rq.customers.iloc[0]), n)
    style.check('zac_08 k = Zac\'s annotation', int(zac_printed('C18_concentration_k')), k)
    style.check('zac_08 top-10 share = Zac\'s annotation', float(zac_printed('C18_top10_annotation')),
                round(top_share, 1), 1e-9)
    style.check('zac_08 k is the first rank reaching 50%', 1, int(y[k - 2] < HALF <= y[k - 1]))
    style.check('zac_08 curve ends at 100%', 100, y[-1], 1e-9)
    style.check('zac_08 bottom-half share = 100% - curve above it', 100 - y[n - n_low - 1], low_share, 1e-9)

    fig, ax = style.figure(10, 6.4)
    xs, ys = np.r_[0, x], np.r_[0, y]   # start the curve at the origin
    ax.fill_between(xs, ys, color=style.BLUE, alpha=0.08, linewidth=0)
    ax.plot(xs, ys, color=style.BLUE, lw=2.2, zorder=3)
    ax.axhline(HALF, color=style.MUTED, lw=0.8, zorder=2)
    ax.text(n, HALF + 1.2, f'{HALF}% of tickets', ha='right', va='bottom', fontsize=9, color=style.MUTED)
    # Blue = the point the title is about (k); the top-10 point is context in gray.
    marker = dict(s=60, edgecolors=style.SURFACE, linewidths=1.6, zorder=5)
    ax.scatter([TOP_N], [top_share], c=style.GRAY, **marker)
    ax.scatter([k], [k_share], c=style.BLUE, **marker)
    # Both labels sit in the shaded area below the curve, left-aligned near their marker, each between two grid
    # lines (40-50% and 0-20%), so neither text nor connector crosses a line; the k connector drops away steeply so
    # it does not run along the 50% hairline.
    line = dict(arrowstyle='-', color=style.MUTED, lw=0.8, shrinkA=2, shrinkB=4, relpos=(0, 0.5))  # from text's left
    ax.annotate(f'{k} customers: {HALF}% of tickets', xy=(k, k_share), xytext=(k + 15, HALF - 6),
                fontsize=10, color=style.INK, va='center', arrowprops=line)
    ax.annotate(f'Top {TOP_N} customers: {style.pct(top_share / 100)} of tickets', xy=(TOP_N, top_share),
                xytext=(TOP_N + 35, 7), fontsize=10, color=style.INK2, va='center', arrowprops=line)
    ax.set_xlim(0, n)
    ax.set_ylim(0, 102)
    ax.set_yticks(np.arange(0, 101, 20))
    style.style_axes(ax, grid='y')
    style.pct_axis(ax.yaxis)
    ax.set_xlabel('Customers, ranked by ticket count (most first)')
    ax.set_ylabel('Cumulative share of tickets')

    style.frame(
        fig,
        f'Half of all tickets come from {k} customers, {style.pct(k / n, 0)} of the {n} with tickets',
        f'Cumulative share of all {total:,} tickets in the case export ({zac_data.period_text(rq)}), including planned '
        f'work, cancelled requests and duplicate cases. Customers ranked by ticket count, most first; the bottom '
        f'half (the {n_low} customers with the fewest tickets) accounts for {style.pct(low_share / 100)} of tickets.',
        notes=[zac_data.WORKLOAD_NOTE,
               'Source: verification/outputs/repro_sql_customer_workload.csv (Zac\'s SQL, notebook cells 17 and 18); '
               'totals from repro_sql_record_quality.csv. Customer definition: the team\'s review of account names '
               'and addresses (docs/03_customer_fleet_ownership.md, section 3.1).'],
        definitions=[zac_data.CUSTOMER_DEFINITION])
    return [style.save(fig, Path(out_dir) / 'zac_08_customer_concentration.png')]


if __name__ == '__main__':
    plot()
