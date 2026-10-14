#!/usr/bin/env python3
"""Slide version of Zac's figure 2 (viz/zac_notebook/zac_02_customer_workload.py): the 10 customers with the most
tickets in the full case export.

Same customers, bars, colours and median-customer context bar as the full chart. The value labels keep the ticket
counts and drop the shares; the customer definition, the workload note and the population go to the speaker notes.

Two versions, as for the full chart:
  pseudonymous (Customer NNN), always;
  real account names, when private=True and the gitignored workbook is present. It is written to deliverables/
  (gitignored), must never be committed, and carries the privacy warning as a muted footer line.

Outputs: viz/figures/slides/zac_02_customer_workload.png
         deliverables/zac_02_customer_workload_slide_REALNAMES.png   (private=True only)
Run:     cd /home/user/analytics-lab && python3 -I viz/slides/zac_02_customer_workload_slide.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# python3 -I leaves the script directory off sys.path
sys.path[:0] = [str(HERE), str(HERE.parent / 'style'), str(HERE.parent / 'zac_notebook')]
import numpy as np  # noqa: E402

import ipa_style as style  # noqa: E402
import slides  # noqa: E402
import zac_02_customer_workload as full  # noqa: E402
import zac_data  # noqa: E402

REAL_PNG = 'zac_02_customer_workload_slide_REALNAMES.png'


def draw(top, total, n_cust, median, period, path, names=None):
    """Draw one version. top: Zac's top 10 rows (most tickets first)."""
    labels = top.customer.tolist()
    if names is not None:
        labels = [names.get(c, c) for c in labels]
    labels.append('Median customer')
    counts = top.cases.tolist() + [median]
    colors = [style.BLUE] * len(top) + [style.GRAY_LIGHT]

    fig, ax = slides.figure()
    # The context bar sits one extra row below the top 10, so it does not read as an eleventh customer.
    y = np.r_[np.arange(len(top))[::-1] + 1.0, -0.3]
    ax.barh(y, counts, height=full.BAR_H, color=colors, linewidth=0)
    for yi, n in zip(y, counts):
        ax.text(n + max(counts) * 0.012, yi, f'{n:,g}', va='center', ha='left', fontsize=9.5, color=style.INK2)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, color=style.INK2)
    ax.get_yticklabels()[-1].set_color(style.MUTED)
    ax.set_ylim(-0.9, len(top) + 0.6)
    ax.set_xlim(0, max(counts) * 1.1)
    style.style_axes(ax, grid='x', baseline='left')
    style.thousands_axis(ax.xaxis)
    ax.set_xlabel('Tickets')

    talk = [zac_data.CUSTOMER_DEFINITION,
            zac_data.WORKLOAD_NOTE,
            f'Population: all {total:,} tickets in the case export ({period}), including planned work, cancelled '
            f'requests and duplicate cases. Gray bar = the median customer of the {n_cust} with tickets.']
    return slides.finish(
        fig, path,
        f'No customer dominates: the top {full.TOP_N} of {n_cust} with tickets hold '
        f'{style.pct(top.cases.sum() / total)} of tickets',
        f'Tickets per customer, the {full.TOP_N} customers with the most, {period}', talk,
        warning=full.PRIVACY_WARNING if names is not None else None)


def plot(out_dir=slides.FIG_DIR, private=True):
    """Draw the pseudonymous slide into out_dir and, when private=True, the real-name slide into slides.DELIVERABLES
    (whatever out_dir is; pass private=False for test runs)."""
    cw, rq = zac_data.load('customer_workload'), zac_data.load('record_quality')
    d = cw.sort_values(['cases', 'customer'], ascending=[False, True], kind='mergesort').reset_index(drop=True)
    total, n_cust = int(d.cases.sum()), len(d)
    style.check('slide zac_02 tickets = record_quality cases', int(rq.cases.iloc[0]), total)
    top = d.head(full.TOP_N)
    median = float(d.cases.median())
    period = zac_data.period_text(rq)
    written = [draw(top, total, n_cust, median, period, Path(out_dir) / full.PNG)]
    if private:
        names = zac_data.real_customer_names()
        if names is None:
            print(f'  real-name variant skipped: {zac_data.WORKBOOK.relative_to(zac_data.ROOT)} not found')
        else:
            written.append(draw(top, total, n_cust, median, period, slides.DELIVERABLES / REAL_PNG, names=names))
    return written


if __name__ == '__main__':
    plot()
