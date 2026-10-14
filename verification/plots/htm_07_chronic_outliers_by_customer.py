#!/usr/bin/env python3
"""Chart 7: chronic-outlier machines by customer, against each customer's devices in the exposure population.

One row per customer with 2 or more chronic outliers (or the top MAX_ROWS customers when that set is too small or too
large): a light bar for the customer's devices in the exposure population (devices on customer hosts) with the
chronic-outlier machines overlaid in blue, labelled "k of n". The title states how many of the customers holding a
chronic outlier hold just one; the footer counts the customers not shown.

Two versions are drawn from the same data:
  pseudonymous (Customer NNN), always;
  real customer names, when private=True and the gitignored name table exists. It is written to deliverables/
  (gitignored) and must never be committed; its privacy warning is the first line of the subtitle.

Inputs:
  verification/outputs/htm_customer_chronic.csv  customer, chronic_outlier_machines, workload_outsized_machines,
                                                 exposure_devices (one row per customer)
  verification/outputs/htm_summary.json          definitions.period (rate-test window) for the subtitle;
                                                 D1_workload.threshold and definitions.q_cut for the chronic-outlier
                                                 definition; D3_classes, D1_workload.outsized_machines and clustering
                                                 (chronic_customers_holding, customers_holding) for the consistency
                                                 checks
  data/private/htm_private_customer_names.csv    customer -> real_account_name (real-name version only; gitignored)
Outputs:
  verification/outputs/figures/htm_07_chronic_outliers_by_customer.png
  deliverables/htm_chronic_outliers_by_customer_REALNAMES.png   (private=True only)

Run:  cd /home/user/analytics-lab && python3 -I verification/plots/htm_07_chronic_outliers_by_customer.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import style  # noqa: E402

PNG = 'htm_07_chronic_outliers_by_customer.png'
REAL_PNG = 'htm_chronic_outliers_by_customer_REALNAMES.png'
NAMES = style.PRIVATE / 'htm_private_customer_names.csv'
MULTI = 2                    # customers with this many chronic outliers or more are shown ...
MIN_ROWS, MAX_ROWS = 10, 25  # ... unless that gives fewer than MIN_ROWS or more than MAX_ROWS rows (then top MAX_ROWS)
ROW_IN = 0.38                # inches per customer row
BAR_H = 0.4                  # bar thickness as a share of the row pitch
PRIVACY_WARNING = ('Contains IPA customer names: for the project team and IPA only. Keep in deliverables/ '
                   '(gitignored); never commit.')


def draw(S, c, path, names=None):
    """Draw one version of the chart. c: customers with at least one chronic outlier, in row order."""
    n_cust, n_mach = len(c), int(c.chronic_outlier_machines.sum())
    singles = int((c.chronic_outlier_machines == 1).sum())
    multi = c[c.chronic_outlier_machines >= MULTI]
    by_rule = MIN_ROWS <= len(multi) <= MAX_ROWS
    shown = multi if by_rule else c.head(MAX_ROWS)
    rest = c.iloc[len(shown):]
    labels = shown.customer.tolist()
    if names is not None:
        labels = [names.get(x, x) for x in labels]

    # Extra width for long names: about 0.075 in per character of the longest label at the 10 pt tick size.
    label_w = 0.075 * max(len(s) for s in labels) + 0.3
    fig, ax = style.figure(10 + max(0.0, label_w - 1.5), 3.4 + ROW_IN * len(shown))
    y = np.arange(len(shown))[::-1]
    xmax = shown.exposure_devices.max()
    ax.barh(y, shown.exposure_devices, height=BAR_H, color=style.BAR_BACKGROUND, linewidth=0,
            label='Customer\'s devices in the exposure population')
    ax.barh(y, shown.chronic_outlier_machines, height=BAR_H, color=style.BLUE, linewidth=0,
            label='Chronic-outlier machines')
    for yi, k, tot in zip(y, shown.chronic_outlier_machines, shown.exposure_devices):
        ax.annotate(f'{k} of {tot}', xy=(tot, yi), xytext=(6, 0), textcoords='offset points', va='center',
                    ha='left', fontsize=9.5, color=style.INK2)
    ax.set_ylim(-0.6, len(shown) - 0.4)
    ax.set_xlim(0, xmax * 1.16)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, color=style.INK2)
    style.style_axes(ax, grid='x', baseline='left')
    ax.set_xlabel('Devices')
    # The bottom rows are short bars, so the lower right of the plot is empty. The opaque background keeps the
    # x gridlines out of the legend text.
    ax.legend(loc='lower right', handlelength=1.4, frameon=True, facecolor=style.SURFACE, edgecolor='none',
              framealpha=1)

    which = (f'Customers with {MULTI} or more' if by_rule
             else f'The {len(shown)} customers with the most chronic outliers')
    if len(rest) == 0:
        rest_txt = 'none.'
    elif rest.chronic_outlier_machines.max() == 1:
        rest_txt = f'{len(rest)} customers with 1 chronic outlier each.'
    else:
        rest_txt = (f'{len(rest)} customers with {int(rest.chronic_outlier_machines.min())} to '
                    f'{int(rest.chronic_outlier_machines.max())} chronic outliers.')
    notes = [f'Not shown: {rest_txt} Customer = the device location\'s customer (ticket account where missing). '
             f'Rows sorted by chronic outliers, then devices.',
             'Source: htm_customer_chronic.csv'
             + (f'; names from {NAMES.relative_to(style.ROOT)}' if names is not None else '')
             + '; thresholds from htm_summary.json.']
    subtitle = [f'{n_mach} chronic-outlier machines across {n_cust} customers (tickets counted over the case export, '
                f'{style.period_text(S, "case_export_period")}; rate test over {style.period_text(S)}). '
                f'{which} shown against their devices in the '
                f'exposure population (customer hosts).']
    if names is not None:
        # First line of the subtitle, so the warning is read before the chart (frame() wraps each item separately).
        subtitle.insert(0, PRIVACY_WARNING)
    style.frame(
        fig,
        f'Chronic outliers are spread thinly: {singles} of {n_cust} customers have just one',
        subtitle,
        definitions=[style.chronic_definition(S)],
        notes=notes)
    return style.save(fig, path)


def plot(out_dir=style.FIG_DIR, private=True):
    """Draw the pseudonymous chart into out_dir and, when private=True, the real-name chart into style.DELIVERABLES.

    The real-name PNG always goes to style.DELIVERABLES, whatever out_dir is, so a test run into a scratch out_dir
    with private=True overwrites the deliverable; pass private=False for test runs."""
    out_dir = Path(out_dir)
    S = style.summary()
    cu = style.load('customer_chronic')
    style.check('D3 chronic outliers (customer table)', S['D3_classes']['chronic_outlier'],
                int(cu.chronic_outlier_machines.sum()))
    style.check('customers holding a chronic outlier', S['clustering']['chronic_customers_holding'],
                int((cu.chronic_outlier_machines > 0).sum()))
    style.check('D1 outsized machines (customer table)', S['D1_workload']['outsized_machines'],
                int(cu.workload_outsized_machines.sum()))
    style.check('customers holding an outsized machine', S['clustering']['customers_holding'],
                int((cu.workload_outsized_machines > 0).sum()))
    # The blue bar is drawn inside the device bar, and every chronic outlier is also workload-outsized.
    style.check('chronic outliers <= exposure devices per customer', 0,
                int((cu.chronic_outlier_machines > cu.exposure_devices).sum()))
    style.check('chronic outliers <= outsized machines per customer', 0,
                int((cu.chronic_outlier_machines > cu.workload_outsized_machines).sum()))

    c = cu[cu.chronic_outlier_machines > 0].sort_values(
        ['chronic_outlier_machines', 'exposure_devices', 'customer'], ascending=[False, False, True], kind='mergesort')
    written = [draw(S, c, out_dir / PNG)]
    if private:
        if NAMES.exists():
            pn = pd.read_csv(NAMES)
            written.append(draw(S, c, style.DELIVERABLES / REAL_PNG,
                                names=dict(zip(pn.customer, pn.real_account_name))))
        else:
            print(f'  real-name variant skipped: {NAMES.relative_to(style.ROOT)} not found')
    return written


if __name__ == '__main__':
    plot()
