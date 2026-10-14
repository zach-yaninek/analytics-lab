#!/usr/bin/env python3
"""Slide version of chart 7 (viz/high_ticket/htm_07_chronic_outliers_by_customer.py): chronic-outlier machines by
customer, against each customer's devices in the exposure population.

Same bars, colours, "k of n" labels and row order as the full chart, cut to the customers with 3 or more chronic
outliers (the full chart shows those with 2 or more, too many rows for a slide). The definition, the customers not
shown and the customer note go to the speaker notes.

Two versions, as for the full chart:
  pseudonymous (Customer NNN), always;
  real customer names, when private=True and the gitignored name table exists. It is written to deliverables/
  (gitignored), must never be committed, and carries the privacy warning as a muted footer line.

Outputs: viz/figures/slides/htm_07_chronic_outliers_by_customer.png
         deliverables/htm_chronic_outliers_by_customer_slide_REALNAMES.png   (private=True only)
Run:     cd /home/user/analytics-lab && python3 -I viz/slides/htm_07_chronic_outliers_by_customer_slide.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# python3 -I leaves the script directory off sys.path
sys.path[:0] = [str(HERE), str(HERE.parent / 'style'), str(HERE.parent / 'high_ticket')]
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import htm  # noqa: E402
import htm_07_chronic_outliers_by_customer as full  # noqa: E402
import ipa_style as style  # noqa: E402
import slides  # noqa: E402

REAL_PNG = 'htm_chronic_outliers_by_customer_slide_REALNAMES.png'
MULTI = 3      # customers with this many chronic outliers or more are shown ...
MAX_ROWS = 10  # ... up to this many rows (then the top MAX_ROWS)
BAR_H = 0.5    # bar thickness as a share of the row pitch


def draw(S, c, path, names=None):
    """Draw one version. c: customers with at least one chronic outlier, in row order."""
    n_cust, n_mach = len(c), int(c.chronic_outlier_machines.sum())
    singles = int((c.chronic_outlier_machines == 1).sum())
    multi = c[c.chronic_outlier_machines >= MULTI]
    by_rule = 0 < len(multi) <= MAX_ROWS
    shown = multi if by_rule else c.head(MAX_ROWS)
    rest = c.iloc[len(shown):]
    labels = shown.customer.tolist()
    if names is not None:
        labels = [names.get(x, x) for x in labels]

    fig, ax = slides.figure()
    y = np.arange(len(shown))[::-1]
    ax.barh(y, shown.exposure_devices, height=BAR_H, color=style.BAR_BACKGROUND, linewidth=0,
            label='Customer\'s devices')
    ax.barh(y, shown.chronic_outlier_machines, height=BAR_H, color=style.BLUE, linewidth=0, label='Chronic outliers')
    for yi, k, tot in zip(y, shown.chronic_outlier_machines, shown.exposure_devices):
        ax.annotate(f'{k} of {tot}', xy=(tot, yi), xytext=(6, 0), textcoords='offset points', va='center',
                    ha='left', fontsize=9.5, color=style.INK2)
    ax.set_ylim(-0.6, len(shown) - 0.4)
    ax.set_xlim(0, shown.exposure_devices.max() * 1.16)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, color=style.INK2)
    style.style_axes(ax, grid='x', baseline='left')
    ax.set_xlabel('Devices')
    ax.legend(loc='lower right', handlelength=1.4, frameon=True, facecolor=style.SURFACE, edgecolor='none',
              framealpha=1)

    which = (f'the {len(shown)} customers with {MULTI} or more' if by_rule
             else f'the {len(shown)} customers with the most')
    k_rest = rest.chronic_outlier_machines.value_counts().sort_index(ascending=False)
    rest_txt = '; '.join(f'{n} with {k}' for k, n in k_rest.items()) if len(rest) else 'none'
    talk = [htm.chronic_definition(S),
            f'{n_mach} chronic-outlier machines across {n_cust} customers (tickets counted over the case export, '
            f'{htm.period_text(S, "case_export_period")}; rate test over {htm.period_text(S)}). Bars: each '
            f'customer\'s devices in the exposure population (customer hosts).',
            f'Not shown, by number of chronic outliers: {rest_txt}.',
            'Customer = the device location\'s customer (ticket account where missing).']
    return slides.finish(fig, path,
                         f'Chronic outliers are spread thinly: {singles} of {n_cust} customers have just one',
                         f'Chronic-outlier machines among all devices, {which}', talk,
                         warning=full.PRIVACY_WARNING if names is not None else None)


def plot(out_dir=slides.FIG_DIR, private=True):
    """Draw the pseudonymous slide into out_dir and, when private=True, the real-name slide into slides.DELIVERABLES
    (whatever out_dir is; pass private=False for test runs)."""
    S = htm.summary()
    cu = htm.load('customer_chronic')
    style.check('slide D3 chronic outliers (customer table)', S['D3_classes']['chronic_outlier'],
                int(cu.chronic_outlier_machines.sum()))
    c = cu[cu.chronic_outlier_machines > 0].sort_values(
        ['chronic_outlier_machines', 'exposure_devices', 'customer'], ascending=[False, False, True], kind='mergesort')
    written = [draw(S, c, Path(out_dir) / full.PNG)]
    if private:
        if full.NAMES.exists():
            pn = pd.read_csv(full.NAMES)
            written.append(draw(S, c, slides.DELIVERABLES / REAL_PNG,
                                names=dict(zip(pn.customer, pn.real_account_name))))
        else:
            print(f'  real-name variant skipped: {full.NAMES.relative_to(htm.ROOT)} not found')
    return written


if __name__ == '__main__':
    plot()
