#!/usr/bin/env python3
"""Zac's figure 10: what follows an eligible unplanned ticket within 30 days, as one 100% bar.

Recreates 10_repeat_composition.png from Zac's notebook (cell 32, from his repeat_summary table, cell 31). Same
population (unplanned index tickets opened before 2 Aug 2026, each with a full 30-day window), same three parts and
the same shares of eligible tickets: no repeat within 30 days; a repeat whose category differs from the index
ticket's or is missing on either ticket; a repeat with the same recorded category (his same_category_30 needs both
categories recorded and equal). Added: the IPA palette (gray context for no repeat, blue and orange for the two repeat
parts, his order and colour roles), direct labels with counts instead of a legend, and a bracket over the two repeat
parts with their total (his printed repeat rate). Dropped: his 0 to 100 axis, since every segment carries its share.

Inputs:  zac_data.load('repeat_summary')    eligible_tickets, machines, repeat_tickets, same_category_repeats,
                                            repeat_pct, same_category_repeat_pct (Zac's SQL, cell 31)
         zac_data.load('repeat_by_model')   the same tickets by model (cell 31), for the totals check
         verification/outputs/audit_case_repeat_gap_bins.csv      repeats by days to the follow-up (totals check)
         verification/outputs/audit_case_repeat_composition.csv   repeats whose follow-up has no category
         verification/outputs/repro_clean_repeat_summary.csv      independent clean-room re-derivation (checks)
Output:  viz/figures/zac_10_repeat_composition.png
Run:     cd /home/user/analytics-lab && python3 -I viz/zac_notebook/zac_10_repeat_composition.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]  # python3 -I leaves the script directory off sys.path
import pandas as pd  # noqa: E402

import ipa_style as style  # noqa: E402
import zac_data  # noqa: E402

PNG = 'zac_10_repeat_composition.png'
BAR = 0.36         # bar thickness in y data units (the bar is centred on y = 0; y limits set below)
BRACKET = 0.52     # y of the bracket's horizontal line over the two repeat parts (its legs drop to the bar top)
LABEL_ROWS = (-0.62, -1.12)  # y of the label rows under the bar for the two repeat parts


def plot(out_dir=zac_data.FIG_DIR):
    out_dir = Path(out_dir)
    r = zac_data.load('repeat_summary').iloc[0]
    rm = zac_data.load('repeat_by_model')
    gaps = pd.read_csv(zac_data.OUTPUTS / 'audit_case_repeat_gap_bins.csv')
    comp = pd.read_csv(zac_data.OUTPUTS / 'audit_case_repeat_composition.csv').set_index('repeat_composition').repeats
    clean = pd.read_csv(zac_data.OUTPUTS / 'repro_clean_repeat_summary.csv').iloc[0]  # re-derived without his code

    # Zac's three parts of the eligible tickets (cell 32).
    eligible, repeats, same = int(r.eligible_tickets), int(r.repeat_tickets), int(r.same_category_repeats)
    parts = [('No repeat within 30 days', eligible - repeats, style.GRAY_LIGHT),
             ('Repeat, different or missing category', repeats - same, style.BLUE),
             ('Repeat, same recorded category', same, style.ORANGE)]
    shares = [100 * n / eligible for _, n, _ in parts]
    starts = [sum(shares[:i]) for i in range(len(shares))]  # left end of each segment

    # Checks: parts and shares against Zac's columns, the by-model table and the verification audits.
    style.check('zac_10 shares sum to 100%', 100, sum(shares), 1e-9)
    style.check('zac_10 repeat share = repeat_pct', r.repeat_pct, shares[1] + shares[2], 1e-9)
    style.check('zac_10 same-category share = same_category_repeat_pct', r.same_category_repeat_pct, shares[2], 1e-9)
    style.check('zac_10 eligible tickets = repeat_by_model total', eligible, int(rm.eligible_tickets.sum()))
    style.check('zac_10 repeats = repeat_by_model total', repeats, int(rm.repeat_tickets.sum()))
    style.check('zac_10 repeats = audit gap bins', repeats, int(gaps.repeats.sum()))
    style.check('zac_10 same-category repeats = audit gap bins', same, int(gaps.same_category.sum()))
    style.check('zac_10 repeats = audit composition (source of the 116)', repeats, int(comp['repeats']))
    for col in ('eligible_tickets', 'repeat_tickets', 'same_category_repeats'):
        style.check(f'zac_10 {col} = clean-room reproduction', int(clean[col]), int(r[col]))

    fig, ax = style.figure(10, 5.0)
    fig.get_layout_engine().set(w_pad=0.12)  # no tick labels: start the bar at the text margin (frame() lets tick
    #                                          labels overhang it by 0.12 in)
    for (_, _, color), share, start in zip(parts, shares, starts):
        ax.barh(0, share, left=start, height=BAR, color=color, linewidth=0)
        ax.text(start + share / 2, 0, f'{share:.1f}%', ha='center', va='center', fontsize=10, weight='bold',
                color='white' if color == style.BLUE else style.INK)  # white on orange is too faint (3.2:1)

    # Direct labels: no repeat above its segment; the two repeat parts under the bar, each on its own row with an
    # elbow leader to the middle of its segment (the orange part is too narrow to hold its label).
    top = BAR / 2
    ax.text(0, top + 0.12, f'{parts[0][0]}: {parts[0][1]:,} tickets', ha='left', va='bottom', fontsize=9.5,
            color=style.INK2)
    for i, row in zip((1, 2), LABEL_ROWS):
        mid = starts[i] + shares[i] / 2  # the label ends 1.2 points (x units) left of its leader
        ax.annotate(f'{parts[i][0]}: {parts[i][1]:,} tickets', xy=(mid, -top), xytext=(mid - 1.2, row),
                    ha='right', va='center', fontsize=9.5, color=style.INK2,
                    arrowprops={'arrowstyle': '-', 'color': style.MUTED, 'lw': 0.8, 'shrinkA': 3, 'shrinkB': 0,
                                'relpos': (1, 0.5), 'connectionstyle': 'angle,angleA=0,angleB=90,rad=0'})

    # Bracket over the two repeat parts: Zac's repeat rate.
    x0, x1 = starts[1], 100
    ax.plot([x0, x0, x1, x1], [top + 0.06, BRACKET, BRACKET, top + 0.06], color=style.MUTED, lw=0.8,
            solid_capstyle='butt', solid_joinstyle='miter')
    ax.text(x1, BRACKET + 0.08, f'Repeat contact within 30 days: {repeats:,} tickets ({r.repeat_pct:.1f}%)',
            ha='right', va='bottom', fontsize=9.5, weight='bold', color=style.INK)

    ax.set_xlim(0, 100)
    ax.set_ylim(LABEL_ROWS[-1] - 0.3, BRACKET + 0.4)
    ax.set_xticks([])  # no 0 to 100% scale: each segment carries its share
    ax.set_yticks([])
    style.style_axes(ax, grid=None, baseline=None)

    style.frame(
        fig,
        f'{r.repeat_pct:.1f}% of unplanned tickets have a 30-day repeat; {r.same_category_repeat_pct:.1f}% a '
        f'same-category one',
        f'Shares of the {eligible:,} eligible unplanned index tickets ({int(r.machines):,} machines; case export '
        f'{zac_data.period_text()}) by what followed on the same machine within 30 days. Of the {repeats:,} repeat '
        f'contacts, {same:,} '
        f'({style.pct(same / repeats, 0)}) share the index ticket\'s recorded category; {repeats - same:,} have '
        f'another or none.',
        notes=[f'Same recorded category = both tickets have a category and it is the same (Zac\'s rule). Different '
               f'or missing = the categories differ or either ticket has none; among them are the '
               f'{int(comp["followup_category_missing"])} repeats whose follow-up has no category. Per ticket, so '
               f'machines with many tickets count many times.',
               'Source: verification/outputs/repro_sql_repeat_summary.csv (Zac\'s SQL, notebook cells 31 and 32); '
               'follow-ups without a category from verification/outputs/audit_case_repeat_composition.csv.'],
        definitions=[zac_data.UNPLANNED_DEFINITION, zac_data.REPEAT_DEFINITION])
    return [style.save(fig, out_dir / PNG)]


if __name__ == '__main__':
    plot()
