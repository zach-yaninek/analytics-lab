#!/usr/bin/env python3
"""The most frequent recorded categories among unplanned tickets: Zac's issue-mix chart, in the IPA style.

Recreates figure 04_issue_mix.png of Zac's notebook (cell 20, query issue_mix): the 10 largest rows of his Trouble
Code Category table over his unplanned service tickets (view service_cases, cell 15). Tickets with no category are
kept as one "[Missing]" row as in his SQL, so his top 10 rows are 9 recorded categories plus [Missing]. Same
population, same top-10 rule and the same counts as his chart; the form adds each category's share of unplanned
tickets and draws the leading category in blue ([Missing] stays an ordinary gray row, as Zac drew it).

Inputs:  zac_data.load('issue_mix')        category, cases, share_pct over service_cases (Zac's SQL, cell 20)
         zac_data.load('service_groups')   Zac's service groups (cell 15), for the unplanned total
         zac_data.load('record_quality')   period of the case export (cell 11)
         zac_data.load('model_issue_mix')  tickets by model and category (cell 20), for an independent top-10 check
         verification/outputs/audit_case_field_completeness_by_subset.csv   missing categories among unplanned tickets
Output:  viz/figures/zac_04_issue_mix.png
Run:     cd /home/user/analytics-lab && python3 -I viz/zac_notebook/zac_04_issue_mix.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]  # python3 -I leaves the script directory off sys.path
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import ipa_style as style  # noqa: E402
import zac_data  # noqa: E402

TOP_N = 10                  # Zac's selection: issues.head(10) (cell 20)
MISSING = '[Missing]'       # Zac's label for tickets with no category: COALESCE(category, '[Missing]')
NTF = 'No Trouble Found'
EXCLUDED_GROUPS = ['Planned work', 'Cancelled request', 'Duplicate case']  # not in service_cases (cell 15)


def plot(out_dir=zac_data.FIG_DIR):
    out_dir = Path(out_dir)
    im = zac_data.load('issue_mix')
    sg = zac_data.load('service_groups').set_index('service_group').cases
    rq = zac_data.load('record_quality')
    by_model = zac_data.load('model_issue_mix').groupby('category').cases.sum()  # a separate GROUP BY of cell 20
    audit = pd.read_csv(zac_data.OUTPUTS / 'audit_case_field_completeness_by_subset.csv').set_index('subset')

    # Checks: the categories cover every unplanned ticket, shares are over that total, [Missing] and NTF agree.
    total = int(im.cases.sum())
    style.check('zac_04 unplanned tickets = service_groups without planned/cancelled/duplicate',
                int(sg.drop(EXCLUDED_GROUPS).sum()), total)
    style.check('zac_04 share_pct = cases / unplanned total', 0,
                float((100 * im.cases / total - im.share_pct).abs().max()), 1e-9)
    style.check('zac_04 [Missing] = missing categories among unplanned (audit)',
                int(audit.loc['Unplanned (service_cases)', 'category_missing']),
                int(im.loc[im.category == MISSING, 'cases'].sum()))
    style.check('zac_04 No Trouble Found = service group', int(sg[NTF]), int(im.loc[im.category == NTF, 'cases'].sum()))

    ranked = im.sort_values(['cases', 'category'], ascending=[False, True], kind='mergesort')
    style.check('zac_04 no tie at the top-10 boundary', 1, int(ranked.cases.iloc[TOP_N - 1] > ranked.cases.iloc[TOP_N]))
    shown, rest = ranked.head(TOP_N), ranked.iloc[TOP_N:]
    shown_share = shown.cases.sum() / total
    style.check('zac_04 top-10 share = same categories in model_issue_mix', shown_share,
                by_model[shown.category].sum() / by_model.sum(), 1e-12)
    n_named = int((im.category != MISSING).sum())
    shown_named = int((shown.category != MISSING).sum())
    style.check('zac_04 recorded categories = model_issue_mix', n_named, int((by_model.index != MISSING).sum()))

    lead, runner = shown.iloc[0], shown.iloc[1]
    d = shown.iloc[::-1]  # most tickets on top
    colors = [style.BLUE if c == lead.category else style.GRAY_LIGHT for c in d.category]

    fig, ax = style.figure(10, 6.9)
    y = np.arange(len(d))
    ax.barh(y, d.cases, height=0.5, color=colors, linewidth=0)
    for yi, row in zip(y, d.itertuples()):
        is_lead = row.category == lead.category
        ax.text(row.cases + d.cases.max() * 0.01, yi, f'{row.cases:,}  ({row.share_pct:.1f}%)', va='center',
                ha='left', fontsize=9.5, color=style.INK if is_lead else style.INK2,
                weight='bold' if is_lead else 'normal')
    ax.set_yticks(y)
    ax.set_yticklabels(d.category, color=style.INK2)
    ax.set_ylim(-0.6, len(d) - 0.4)
    ax.set_xlim(0, d.cases.max() * 1.2)
    style.style_axes(ax, grid='x', baseline='left')
    style.thousands_axis(ax.xaxis)
    ax.set_xlabel('Unplanned tickets')

    # Zac's top 10 rows count [Missing] as one row, so say how many recorded categories they hold.
    rows_text = (f'{shown_named} most frequent of the {n_named} recorded Trouble Code Categories'
                 + (f' plus {MISSING}' if MISSING in set(shown.category) else ''))
    style.frame(
        fig,
        f'{lead.category} leads with {lead.share_pct:.1f}% of unplanned tickets, '
        f'{lead.cases / runner.cases:.1f}× the next category',
        f'Zac\'s top {TOP_N}: the {rows_text}, among all {total:,} unplanned tickets, {zac_data.period_text(rq)}; '
        f'together {style.pct(shown_share, 0)} of them. Share of unplanned tickets in brackets; blue = the leading '
        f'category.',
        notes=[f'{MISSING} = no category recorded (Zac keeps these as their own row). {NTF} = no fault was found, '
               f'recorded as a category.',
               f'Not shown: the other {n_named - shown_named} recorded categories, {int(rest.cases.sum()):,} tickets '
               f'({style.pct(rest.cases.sum() / total)}) in all; the largest, {rest.category.iloc[0]}, has '
               f'{int(rest.cases.iloc[0]):,} ({rest.share_pct.iloc[0]:.1f}%).',
               'Source: verification/outputs/repro_sql_issue_mix.csv (Zac\'s SQL, notebook cell 20); period from '
               'repro_sql_record_quality.csv.'],
        definitions=[zac_data.UNPLANNED_DEFINITION])
    return [style.save(fig, out_dir / 'zac_04_issue_mix.png')]


if __name__ == '__main__':
    plot()
