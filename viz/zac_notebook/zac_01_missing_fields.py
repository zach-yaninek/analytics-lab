#!/usr/bin/env python3
"""How often each ticket field is missing in the case export: Zac's field-completeness chart, in the IPA style.

Recreates figure 01_missing_fields.png of Zac's notebook (cell 13, query field_completeness): for six ticket fields,
the share of all tickets in the case export with the field missing (blank or whitespace only), before any exclusion.
Same population (every ticket), same six fields, order (largest share on top) and percentages as his chart; the
form adds the ticket counts, labels the two always-filled fields and draws the field the title names in blue.
"Missing" follows Zac's import (cell 4), which stores blank or whitespace-only values as NULL; cell 13 counts them.

Inputs:  zac_data.load('field_completeness')   field, missing, missing_pct (Zac's SQL, cell 13)
         zac_data.load('record_quality')       ticket count and period of the case export (cell 11)
         zac_data.load('service_groups')       Zac's service groups (cell 15), for consistency checks
         verification/outputs/audit_case_field_completeness_by_subset.csv   missing counts by ticket subset
Output:  viz/figures/zac_01_missing_fields.png
Run:     cd /home/user/analytics-lab && python3 -I viz/zac_notebook/zac_01_missing_fields.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]  # python3 -I leaves the script directory off sys.path
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import ipa_style as style  # noqa: E402
import zac_data  # noqa: E402

# Audit table columns for the fields it also counts (field -> column of missing tickets).
AUDIT_COLUMNS = {'Trouble Code': 'trouble_code_missing', 'Trouble Code Category': 'category_missing',
                 'Trouble Code Sub Category': 'subcategory_missing', 'Trouble Resolution': 'resolution_missing'}
SUBCATEGORY = 'Trouble Code Sub Category'
# Service groups (cell 15) whose tickets never carry a Sub Category, with how the note names them.
GROUP_TEXT = {'No Trouble Found': 'No Trouble Found', 'Cancelled request': 'cancelled-request'}


def plot(out_dir=zac_data.FIG_DIR):
    out_dir = Path(out_dir)
    f = zac_data.load('field_completeness')
    rq = zac_data.load('record_quality')
    sg = zac_data.load('service_groups').set_index('service_group').cases
    audit = pd.read_csv(zac_data.OUTPUTS / 'audit_case_field_completeness_by_subset.csv').set_index('subset')
    n = int(rq.cases.iloc[0])

    # Checks: Zac's percentages are over every ticket in the export; counts agree with the audit and his groups.
    f['pct'] = 100 * f.missing / n
    style.check('zac_01 missing_pct = missing / all tickets', 0, float((f.pct - f.missing_pct).abs().max()), 1e-9)
    style.check('zac_01 ticket count = service_groups total', n, int(sg.sum()))
    by_field = f.set_index('field').missing
    style.check('zac_01 missing counts = audit (all tickets)', 0,
                sum(abs(int(by_field[k]) - int(audit.loc['All tickets', c])) for k, c in AUDIT_COLUMNS.items()))
    style.check('zac_01 Trouble Code missing = "Missing trouble code" group', int(sg['Missing trouble code']),
                int(by_field['Trouble Code']))
    # The Sub Category note: both groups are blank on every ticket, and the audit's subsets are Zac's groups.
    for g in GROUP_TEXT:
        style.check(f'zac_01 Sub Category blank on every {g} ticket (audit)', int(audit.loc[g, 'tickets']),
                    int(audit.loc[g, 'subcategory_missing']))
        style.check(f'zac_01 audit {g} tickets = service_groups', int(sg[g]), int(audit.loc[g, 'tickets']))

    d = f.sort_values(['pct', 'field'], ascending=[True, False], kind='mergesort')  # largest share on top
    top, second = d.iloc[-1], d.iloc[-2]

    fig, ax = style.figure(10, 5.8)
    y = np.arange(len(d))
    colors = [style.BLUE if fld == top.field else style.GRAY_LIGHT for fld in d.field]
    ax.barh(y, d.pct, height=0.5, color=colors, linewidth=0)
    for yi, row in zip(y, d.itertuples()):
        label = f'{row.pct:.1f}%  ({row.missing:,} tickets)' if row.missing else '0%  (never missing)'
        ax.text(row.pct + d.pct.max() * 0.01, yi, label, va='center', ha='left', fontsize=9.5,
                color=style.INK if row.field == top.field else style.INK2,
                weight='bold' if row.field == top.field else 'normal')
    ax.set_yticks(y)
    ax.set_yticklabels(d.field, color=style.INK2)
    ax.set_ylim(-0.6, len(d) - 0.4)
    ax.set_xlim(0, 5 * np.ceil(d.pct.max() * 1.4 / 5))  # whole 5% steps, so the top label ends inside the grid
    style.style_axes(ax, grid='x', baseline='left')
    style.pct_axis(ax.xaxis)
    ax.set_xlabel('Tickets with the field missing (% of all tickets)')

    # Sub Category is always blank on No Trouble Found and cancelled tickets (checked above).
    blank_n = sum(int(sg[g]) for g in GROUP_TEXT)
    sub_n = int(by_field[SUBCATEGORY])
    blank_txt = ' and '.join(f'{text} ({int(sg[g]):,})' for g, text in GROUP_TEXT.items())

    style.frame(
        fig,
        f'{top.field.removeprefix("Trouble Code ")} is missing on {top.pct:.0f}% of tickets; every other field on '
        f'{second.pct:.1f}% or less',
        f'Share of all {n:,} tickets in the case export ({zac_data.period_text(rq)}) with each field missing, '
        f'before any exclusions; ticket counts in brackets. Blue = {top.field}, the field missing most often.',
        notes=[f'{SUBCATEGORY} is blank on every {blank_txt} ticket: {blank_n:,} of its {sub_n:,} missing values '
               f'({style.pct(blank_n / sub_n, 0)}).',
               f'The {int(by_field["Trouble Code"]):,} tickets without a Trouble Code are the same tickets as Zac\'s '
               f'"Missing trouble code" service group.',
               'Source: verification/outputs/repro_sql_field_completeness.csv (Zac\'s SQL, notebook cell 13); '
               'total and period from repro_sql_record_quality.csv; subsets from '
               'audit_case_field_completeness_by_subset.csv.'],
        definitions=['Missing = the field is empty or whitespace only in the case export (Zac\'s import, notebook '
                     'cell 4, stores these as NULL; cell 13 counts them). Trouble Reported and Trouble Resolution are '
                     'free text: only whether they are filled in is counted.'])
    return [style.save(fig, out_dir / 'zac_01_missing_fields.png')]


if __name__ == '__main__':
    plot()
