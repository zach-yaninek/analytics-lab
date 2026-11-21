#!/usr/bin/env python3
"""Zac's figure 2: the 10 customers with the most tickets in the full case export.

Recreates 02_customer_workload.png from Zac's notebook (cell 17: his customer_workload query over `cases`, every
ticket in the case export, and his bar() helper from cell 9 on customers.head(10)). Same population (all tickets,
including planned work, cancelled requests and duplicate cases), same selection (top 10 by tickets, ties broken by
customer label as in his ORDER BY) and same metric (tickets per customer). Added: each customer's share of all
tickets (2 decimals, as in his cell 17 table, so 92 and 91 tickets do not both read 1.2%) and a gray context bar
for the median customer. The customers are the accounts with at least one ticket (a case export has no others), so
the title says "845 with tickets".

Two versions are drawn from the same data:
  pseudonymous (Customer NNN), always;
  real account names, when private=True and the gitignored workbook is present (zac_data.real_customer_names()).
  It is written to deliverables/ (gitignored) and must never be committed; its privacy warning is the first line
  of the footer.

Shared text lives in zac_data.py: the customer definition (CUSTOMER_DEFINITION, from the team's review of account
names and addresses in docs/03_customer_fleet_ownership.md section 3.1), the workload note (WORKLOAD_NOTE) and the
period (period_text). zac_08_customer_concentration.py draws the same definition and note.

Inputs:  zac_data.load('customer_workload')  verification/outputs/repro_sql_customer_workload.csv (customer, cases,
                                             affected_machines, share_pct; one row per customer with a ticket)
         zac_data.load('record_quality')     repro_sql_record_quality.csv (ticket and customer totals, period)
         zac_data.load('service_groups')     repro_sql_service_groups.csv (ticket total, cross-check)
         zac_data.load('claims')             repro_sql_claims.csv (Zac's printed cell 17 values, cross-check)
         zac_data.real_customer_names()      real-name version only (gitignored workbook)
Outputs: viz/figures/zac_02_customer_workload.png
         deliverables/zac_02_customer_workload_REALNAMES.png   (private=True only)
Run:     cd /home/user/analytics-lab && python3 -I viz/zac_notebook/zac_02_customer_workload.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]  # python3 -I leaves the script directory off sys.path
import numpy as np  # noqa: E402

import ipa_style as style  # noqa: E402
import zac_data  # noqa: E402

TOP_N = 10        # Zac's selection: customers.head(10) (notebook cell 17)
PNG = 'zac_02_customer_workload.png'
REAL_PNG = 'zac_02_customer_workload_REALNAMES.png'
ROW_IN = 0.34     # inches per bar row
BAR_H = 0.5       # bar thickness as a share of the row pitch
PRIVACY_WARNING = 'Contains IPA customer names: for the project team and IPA only.'  # the variant goes to IPA
SOURCE = ('Source: verification/outputs/repro_sql_customer_workload.csv (Zac\'s SQL, notebook cell 17); totals from '
          'repro_sql_record_quality.csv. Customer definition: the team\'s review of account names and addresses '
          '(docs/03_customer_fleet_ownership.md, section 3.1).')


def zac_printed(claim_id):
    """A value Zac's notebook printed, as recorded by verification/reproduce_sql.py (repro_sql_claims.csv)."""
    claims = zac_data.load('claims')
    return claims.loc[claims.claim_id == claim_id, 'zac_value'].iloc[0]


def draw(top, total, n_cust, median, period, path, names=None):
    """Draw one version of the chart. top: Zac's top 10 rows (most tickets first)."""
    top_share = top.cases.sum() / total
    labels = top.customer.tolist()
    if names is not None:
        labels = [names.get(c, c) for c in labels]
    labels.append(f'Median customer (of {n_cust})')
    counts = top.cases.tolist() + [median]
    colors = [style.BLUE] * len(top) + [style.GRAY_LIGHT]
    # 2 decimals, as in Zac's cell 17 table, so near-equal counts (92, 91) show different shares.
    texts = [f'{n:,g}  ({style.pct(n / total, 2)})' for n in counts]

    # Extra width for long names: about 0.075 in per character of the longest label at the 10 pt tick size.
    label_w = 0.075 * max(len(s) for s in labels) + 0.3
    fig, ax = style.figure(10 + max(0.0, label_w - 2.0), 3.6 + ROW_IN * (len(labels) + 1))
    # The context bar sits one extra row below the top 10, so it does not read as an eleventh customer.
    y = np.r_[np.arange(len(top))[::-1] + 1.0, -0.3]
    ax.barh(y, counts, height=BAR_H, color=colors, linewidth=0)
    # A surface-coloured box behind each value label keeps the x grid lines from running through the text.
    for yi, n, t in zip(y, counts, texts):
        ax.text(n + max(counts) * 0.012, yi, t, va='center', ha='left', fontsize=9.5, color=style.INK2,
                bbox=dict(boxstyle='square,pad=0.2', fc=style.SURFACE, ec='none'))
    ax.set_yticks(y)
    ax.set_yticklabels(labels, color=style.INK2)
    ax.get_yticklabels()[-1].set_color(style.MUTED)
    ax.set_ylim(-0.9, len(top) + 0.6)
    ax.set_xlim(0, max(counts) * 1.25)
    style.style_axes(ax, grid='x', baseline='left')
    style.thousands_axis(ax.xaxis)
    ax.set_xlabel('Tickets, full case export')

    if names is None:
        notes = [zac_data.WORKLOAD_NOTE + ' Customer NNN labels are stable pseudonyms for the account names.', SOURCE]
        definitions = [zac_data.CUSTOMER_DEFINITION]
    else:
        notes = [zac_data.WORKLOAD_NOTE + ' Account names from the case export.',
                 SOURCE]
        definitions = [PRIVACY_WARNING, zac_data.CUSTOMER_DEFINITION]
    style.frame(
        fig,
        f'No customer dominates: the top {TOP_N} of {n_cust} with tickets hold {style.pct(top_share)} of tickets',
        f'The {TOP_N} customers with the most tickets, out of all {total:,} tickets in the case export ({period}), '
        f'including planned work, cancelled requests and duplicate cases. Share of all tickets in brackets; gray '
        f'bar = the median customer.',
        notes=notes, definitions=definitions)
    return style.save(fig, path)


def plot(out_dir=zac_data.FIG_DIR, private=True):
    """Draw the pseudonymous chart into out_dir and, when private=True, the real-name chart into
    zac_data.DELIVERABLES (whatever out_dir is; pass private=False for test runs)."""
    out_dir = Path(out_dir)
    cw, rq, sg = zac_data.load('customer_workload'), zac_data.load('record_quality'), zac_data.load('service_groups')
    # Zac's ranking: ORDER BY cases DESC, customer (cell 17).
    d = cw.sort_values(['cases', 'customer'], ascending=[False, True], kind='mergesort').reset_index(drop=True)
    total, n_cust = int(d.cases.sum()), len(d)
    top = d.head(TOP_N)
    median = float(d.cases.median())
    shown = [f'{c}|{n}|{100 * n / total:.2f}' for c, n in zip(top.customer, top.cases)]
    printed = ['|'.join(r.strip().split('|')[i] for i in (0, 1, 3))   # label|tickets|share (drop machines)
               for r in zac_printed('C17_customer_workload_top10').split(';')]

    style.check('zac_02 tickets = record_quality cases', int(rq.cases.iloc[0]), total)
    style.check('zac_02 tickets = service_groups cases', int(sg.cases.sum()), total)
    style.check('zac_02 customers = record_quality customers', int(rq.customers.iloc[0]), n_cust)
    style.check('zac_02 top 10 (label, tickets, share) = Zac\'s printed table', 1, int(shown == printed))
    style.check('zac_02 top-10 share = Zac\'s printed share', float(zac_printed('C17_top10_customer_share')),
                round(100 * top.cases.sum() / total, 1), 1e-9)
    style.check('zac_02 bracketed shares = share_pct', 0, float((100 * top.cases / total - top.share_pct).abs().max()),
                1e-9)
    style.check('zac_02 no tie at the top-10 cutoff', 1, int(d.cases.iloc[TOP_N - 1] > d.cases.iloc[TOP_N]))

    period = zac_data.period_text(rq)
    written = [draw(top, total, n_cust, median, period, out_dir / PNG)]
    if private:
        names = zac_data.real_customer_names()
        if names is None:
            print(f'  real-name variant skipped: {zac_data.WORKBOOK.relative_to(zac_data.ROOT)} not found')
        else:
            written.append(draw(top, total, n_cust, median, period, zac_data.DELIVERABLES / REAL_PNG, names=names))
    return written


if __name__ == '__main__':
    plot()
