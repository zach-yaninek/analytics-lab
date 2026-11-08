#!/usr/bin/env python3
"""IPA's Electronics case list: every ticket behind the Electronics finding of slides 4a-4e, as an Excel workbook.

Slides 4a-4c found Electronics tickets more common on machines under 4 years old than on older ones, which IPA did
not expect, and IPA asked which service cases these are. This builds the list, locally, into deliverables/
(gitignored); it is never committed. It holds every unplanned ticket of request type GROUP ('Electronics': Trouble
Code Electronics; Monitoring tickets apart, as on the slides) on Part A's machines, one row per IPA case: 1,605
tickets, 875 on machines under 4 and 730 on machines 4+.

Data, as verification/followups.py's Part A has it: followups.load(), then the machine and ticket frames as main()
and part_a() build them (6,750 unplanned tickets on 8,946 listed machines, 1 Aug 2025 - 31 Aug 2026; under 4 = age
bands <1, 1-2 and 2-4; comparison models = the models with 100+ machine-months in each age group). Real identifiers,
in memory only: the case number by inverting followups' case map (case_id pseudonym -> cleaned case number); the
serial number from followups' frames; the account from IPA's installed-base list (common.load_equipment); Dispatch #,
Status, Date/Time Opened and Trouble Closed Date/Time from the case export, by case number. No free text (Trouble
Reported, Trouble Resolution, Administrative Notes) and no Case Owner.

Sheets (values, not formulas; Arial; bold filled headers, frozen panes and filters on the list sheets):
  Read me              the privacy notice; what the list is; how its counts tie to the slides; how to filter; why the
                       'extra' tickets cannot be singled out; definitions
  Summary              the slides' numbers recomputed from the list: machines, machine-months and tickets by age group;
                       GROUP tickets by Category with rates, ratios and extra tickets (4a, 4b); FOCUS tickets by
                       install cohort, pooled over the comparison models and for each big 2.0 model (4d); the halves
                       (4e); Category x Sub Category
  Touchscreen 2022-23  slide 4d's cluster: FOCUS tickets on FOCUS_COHORT installs of the comparison models
  Electronics cases    every ticket, one row per case
  Machines             one row per machine with a GROUP ticket: its tickets by Category

Checks (printed as counts; any failure stops the build, deletes the temporary file and leaves any earlier output as
it was):
  - data: Part A's 6,750 tickets; the comparison models = ag_support.csv's; machines and machine-months by age group
    = ag_band_rates.csv and ag_type_rates.csv; GROUP tickets by Category x age group = ag_type_rates.csv (its Category
    rows, and its group row with the blank Category); extra tickets, crude and within model = ag_decomposition.csv;
    FOCUS tickets, machines and machine-months by install cohort = ag_install_pooled.csv, and on each big model =
    ag_install_year.csv; under-4 tickets, machine-months and gaps by half = ag_halves.csv; GROUP tickets by model and
    age group = ag_by_model.csv; the Sub Category rows add up to their Categories;
  - identifiers: the case map inverts one to one; the listed case numbers are unique and each is in the case export
    exactly once; the export's Status and opening and closing times, by case number, = the case table's; every
    machine has a serial number and an account on IPA's list, and real and pseudonymous identifiers pair up;
  - workbook, read back with openpyxl: the sheets and their row counts as written; the identifier columns as
    intended; 'Touchscreen 2022-23' = the matching rows of 'Electronics cases'; no case free text (40+ characters) in
    any cell; the real workbook holds no pseudonym (T#####, S#####, M#####, Customer NNN), sits under deliverables/
    and is gitignored (git check-ignore).

Pseudonymous copy (--pseudo OUT_DIR): the same workbook with the repository's pseudonyms (case_id, serial_id,
Customer NNN) in place of case numbers, serial numbers and accounts, and Dispatch # blank, for checking the layout
without opening a real identifier; it must hold no real identifier (followups.real_sets plus the listed dispatch
numbers, scanned as followups.py scans its outputs).

Inputs:  data/raw/ (the case export and IPA's installed-base list, through verification/common.py);
         verification/outputs/fu/ (the telemetry map followups.load() reads); verification/outputs/followups/ag_*.csv
         (the committed results: the checks, and the 95% intervals the Summary shows)
Output:  deliverables/IPA_Electronics_Cases.xlsx (never commit), or OUT_DIR/IPA_Electronics_Cases_PSEUDO.xlsx
Requires pandas, numpy and openpyxl, and git for the ignore check. No message prints a real identifier: counts,
labels and pseudonyms only; an unexpected error is reported by its type and line, without its message.

Run:  cd /home/user/analytics-lab && python3 -I viz/deliverables/build_electronics_cases.py [--pseudo OUT_DIR]
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
import traceback
import zipfile
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE), str(ROOT / 'verification')]  # python3 -I leaves the script directory off sys.path
import names  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from openpyxl import Workbook, load_workbook  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402

import common  # noqa: E402
import fleet_exposure as FX  # noqa: E402
import followups as F  # noqa: E402

GROUP = 'Electronics'          # the request type listed (followups' 'group'); a Door list sets GROUP = 'Door' and
FOCUS = 'Touchscreen'          # ... FOCUS (slide 4d's cluster: its own sheet, Summary tables and machine column),
FOCUS_COHORT = '2022-23'       # ... the cluster's install cohort,
CATEGORIES = ('Touchscreen', 'Computer Board', 'Power Supply', 'Badge Reader')  # ... the Machines sheet's columns,
BIG_MODELS = ('LVD-Remote-2.0', 'MV-2.0', 'LVRR-WP-2.0')  # ... slide 4d's big 2.0 models (shown one by one),
MIX_MODEL = 'LVD-Remote-2.0'   # ... and slide 4c's model whose young machines' tickets are more often GROUP
PART_A_TICKETS = 6750          # slide 4's population (followups.py pins it)
RESULTS = common.OUTPUTS / 'followups'
OUT_REAL = names.DELIVERABLES / f'IPA_{GROUP}_Cases.xlsx'
PSEUDO_FILE = f'IPA_{GROUP}_Cases_PSEUDO.xlsx'
RAW_FIELDS = ('Case Number', 'Date/Time Opened', 'Dispatch #', 'Status', 'Trouble Closed Date/Time')  # nothing else
FREE_TEXT = ('Trouble Reported', 'Trouble Resolution', 'Administrative Notes')  # read only to check none is written
FREE_TEXT_MIN = 40             # free-text values this long are looked for in the workbook's cells
NOTICE_REAL = 'Contains IPA case numbers, serial numbers and customer names: for the project team and IPA only.'
NOTICE_PSEUDO = ("Review copy: the project's pseudonyms stand in for case numbers, serial numbers and customer names, "
                 'and Dispatch # is blank.')

U4, O4 = F.AGE_LABELS                                    # 'Under 4', '4+'
AGES = list(F.AGE_LABELS)
COHORTS = [f'{a}-{str(b)[2:]}' for a, b in F.INSTALL_COHORTS]
BEFORE, AFTER = f'Before {F.INSTALL_COHORTS[0][0]}', f'After {F.INSTALL_COHORTS[-1][1]}'
NO_CATEGORY = '(no Category)'
README, SUMMARY, MACHINES = 'Read me', 'Summary', 'Machines'
CLUSTER, CASES = f'{FOCUS} {FOCUS_COHORT}', f'{GROUP} cases'
DATETIME, DATE = 'yyyy-mm-dd hh:mm', 'yyyy-mm-dd'
COUNT, MONTHS, RATE, SIGNED = '#,##0', '#,##0.0', '0.00', '+#,##0;-#,##0;0'

# The list sheets' columns: header, field (an identifier: (real field, pseudonymous field); None leaves it blank),
# width, number format.
CASE_COLUMNS = (
    ('Case Number', ('case_number', 'case_id'), 11, '@'),
    ('Opened', 'ts', 17, DATETIME),
    ('Closed', 'closed', 17, DATETIME),
    ('Status', 'status', 15, None),
    ('Dispatch #', ('dispatch', None), 14, '@'),
    ('Account', ('account', 'customer'), 44, None),
    ('Serial Number', ('serial', 'serial_id'), 10, '@'),
    ('Model', 'model', 15, None),
    ('Install date', 'install_date', 11, DATE),
    ('Install year', 'install_year', 9, '0'),
    ('Install cohort', 'cohort', 11, None),
    ('Age group', 'age_group', 9, None),
    ('Age band (years)', 'age_band', 9, None),
    ('Age at ticket (years)', 'age_at_ticket', 10, '0.0'),
    ('Trouble Code', 'trouble_code', 11, None),
    ('Category', 'category', 15, None),
    ('Sub Category', 'subcategory', 30, None),
    ('Half', 'half', 6, None),
    ('Comparison model', 'comparison', 11, None),
    (f"Machine's {GROUP} tickets", 'machine_group', 12, '0'),
    (f"Machine's {FOCUS} tickets", 'machine_focus', 12, '0'),
)
MACHINE_COLUMNS = (
    ('Serial Number', ('serial', 'serial_id'), 10, '@'),
    ('Account', ('account', 'customer'), 44, None),
    ('Model', 'model', 15, None),
    ('Install date', 'install_date', 11, DATE),
    ('Install cohort', 'cohort', 10, None),
    ('Age group', 'age_group', 8, None),
    ('Comparison model', 'comparison', 11, None),
    (f'{GROUP} tickets', 'n_group', 11, '0'),
    *((c, f'n:{c}', 13, '0') for c in CATEGORIES),
    (f'Other {GROUP} tickets', 'n_other', 11, '0'),
    ('All unplanned tickets', 'n_all', 11, '0'),
)

ARIAL = 'Arial'
FONT = Font(name=ARIAL, size=10)
BOLD = Font(name=ARIAL, size=10, bold=True)
TITLE = Font(name=ARIAL, size=14, bold=True)
HEADING = Font(name=ARIAL, size=11, bold=True, color='1F3864')
NOTE = Font(name=ARIAL, size=9, italic=True, color='595959')
NOTICE = Font(name=ARIAL, size=10, bold=True, color='9C0006')
NOTICE_FILL = PatternFill('solid', fgColor='FFE4E1')
HEAD_FILL = PatternFill('solid', fgColor='D9E1F2')
WRAP = Alignment(wrap_text=True, vertical='top')
INDENT = Alignment(horizontal='left', indent=2)
HEAD_RIGHT = Alignment(wrap_text=True, vertical='bottom', horizontal='right')
HEAD_ALIGN = Alignment(wrap_text=True, vertical='bottom')
AFTER_IGNORED = ('<smartTags', '<drawing', '<legacyDrawing', '<picture', '<oleObjects', '<controls',
                 '<webPublishItems', '<tableParts', '<extLst', '</worksheet>')  # elements ignoredErrors precedes


class BuildError(Exception):
    """A step or check failed; the message names counts, labels and pseudonyms only."""


def fail(message):
    raise BuildError(message) from None


class Checks:
    """Print each check as '[ok]' or '[FAIL]' with its counts; remember the failures."""

    def __init__(self):
        self.failed = []

    def __call__(self, name, ok, detail):
        print(f"  [{'ok' if ok else 'FAIL'}] {name}: {detail}")
        if not ok:
            self.failed.append(name)

    def stop_if_failed(self, stage):
        if self.failed:
            fail(f'{len(self.failed)} {stage} check(s) failed: {", ".join(self.failed)}')


def close(a, b):
    """Equal to the committed results' precision (10 significant digits)."""
    return bool(np.allclose(np.asarray(a, float), np.asarray(b, float), rtol=1e-8, atol=1e-9, equal_nan=True))


def cohort_of(year):
    for (a, b), label in zip(F.INSTALL_COHORTS, COHORTS):
        if a <= year <= b:
            return label
    return BEFORE if year < F.INSTALL_COHORTS[0][0] else AFTER


def timestamp(value):
    """A case-export date-time as the case table reads it (to the second); NaT when blank."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return pd.NaT
    return (pd.to_datetime(value) if isinstance(value, str) else pd.Timestamp(value)).floor('s')


def same_times(a, b):
    a, b = pd.to_datetime(a), pd.to_datetime(b)
    return int(((a == b) | (a.isna() & b.isna())).sum())


# ----------------------------------------------------------------------------------------------------------------
# Data: Part A's machines and tickets, and the GROUP tickets with their real identifiers
# ----------------------------------------------------------------------------------------------------------------
def load(check):
    """Part A's frames as followups.main() and part_a() build them; the GROUP tickets with real and pseudonymous
    identifiers (in memory only); and what the privacy checks need."""
    raw, maps, cases, conn, sc, eq, m_all, t_all = F.load(common.XLS, common.EQUIPMENT, common.OUTPUTS / 'fu')
    conn.close()
    m = FX.add_rate_groups(m_all[~m_all.third_party].copy().reset_index(drop=True))   # followups.main()
    t = t_all[t_all.serial.isin(set(m.serial))].copy()
    mx = m[m.months > 0].reset_index(drop=True)                                        # followups.part_a()
    mx['age_group'] = np.where(mx.age_band.isin(F.YOUNG_BANDS), U4, O4)
    tp = t[t.serial.isin(set(mx.serial))].copy()
    check('Part A tickets (slide 4 population)', len(tp) == PART_A_TICKETS,
          f'{len(tp):,} unplanned tickets on {len(mx):,} listed machines ({PART_A_TICKETS:,} expected)')
    if mx.install_date.isna().any():
        fail(f'{int(mx.install_date.isna().sum())} listed machine(s) without an install date')

    months = mx.groupby(['model', 'age_group']).months.sum().unstack().reindex(columns=AGES).fillna(0.0)
    support = sorted(months.index[(months[U4] >= F.MIN_SUPPORT_MONTHS) & (months[O4] >= F.MIN_SUPPORT_MONTHS)])
    mx['in_support'] = mx.model.isin(support)
    mx['comparison'] = np.where(mx.in_support, 'Yes', 'No')
    mx['install_year'] = mx.install_date.dt.year.astype(int)
    mx['cohort'] = mx.install_year.map(cohort_of)
    mx['age_band'] = mx.age_band.astype(str)
    mx['account'] = mx.serial.map(dict(zip(eq.serial, eq.account)))   # the account on IPA's list
    by = mx.set_index('serial')
    for c in ('serial_id', 'customer', 'account', 'model', 'install_date', 'install_year', 'cohort', 'age_group',
              'age_band', 'in_support', 'comparison'):
        tp[c] = tp.serial.map(by[c])                    # the machine's, from IPA's list (as Part A groups them)
    tp['half'] = np.where(tp.ts < F.SPLIT, 'H1', 'H2')

    # The GROUP tickets and their real identifiers.
    e = tp[tp.group == GROUP].copy()
    inverse = {v: k for k, v in maps['case'].items()}
    check('case map inverts one to one', len(inverse) == len(maps['case']) and e.case_id.isin(set(inverse)).all(),
          f"{len(maps['case']):,} case numbers, {len(inverse):,} pseudonyms; "
          f'{int(e.case_id.isin(set(inverse)).sum()):,} of {len(e):,} listed pseudonyms map back')
    e['case_number'] = e.case_id.map(inverse)
    rx = pd.DataFrame({f: raw[f] for f in RAW_FIELDS})
    rx['Case Number'] = rx['Case Number'].map(common.clean)
    once = rx['Case Number'].value_counts()
    check('case numbers unique, each in the case export once',
          e.case_number.is_unique and bool(e.case_number.map(once).eq(1).all()),
          f'{e.case_number.nunique():,} distinct of {len(e):,} listed; {int(e.case_number.map(once).eq(1).sum()):,} '
          f'found exactly once among the export\'s {len(rx):,} rows')
    rx = rx.drop_duplicates('Case Number', keep=False).set_index('Case Number')
    e['dispatch'] = e.case_number.map(rx['Dispatch #'].map(common.clean))
    e['status'] = e.case_number.map(rx['Status'].map(common.clean))
    e['closed'] = e.case_number.map(rx['Trouble Closed Date/Time'].map(timestamp))
    opened = e.case_number.map(rx['Date/Time Opened'].map(timestamp))
    status_same = int((e.status == sc.set_index('case_id').status.reindex(e.case_id).to_numpy()).sum())
    check('case export by case number = the case table', status_same == len(e) and same_times(opened, e.ts) == len(e)
          and same_times(e.closed, e.closed_at) == len(e),
          f'Status {status_same:,}, opened {same_times(opened, e.ts):,}, closed {same_times(e.closed, e.closed_at):,} '
          f'of {len(e):,} the same')
    pairs = (e.serial.map(maps['serial']).eq(e.serial_id) & e.account.map(maps['account']).eq(e.customer)
             & e.case_number.map(maps['case']).eq(e.case_id))
    check('machines on IPA\'s list; real and pseudonymous identifiers pair up',
          bool(e.serial.notna().all() and e.account.notna().all() and pairs.all()),
          f'{int(e.serial.notna().sum()):,} serial numbers, {int(e.account.notna().sum()):,} accounts, '
          f'{int(pairs.sum()):,} pairs of {len(e):,}')

    e['age_at_ticket'] = ((e.ts - e.install_date).dt.days / 365.25).round(1)
    e['machine_group'] = e.serial.map(e.serial.value_counts())
    e['machine_focus'] = e.serial.map(e[e.ctype == FOCUS].serial.value_counts()).fillna(0).astype(int)
    counts = e.category.fillna('').value_counts()
    if FOCUS not in counts or FOCUS not in CATEGORIES:
        fail(f'FOCUS ({FOCUS}) is not a Category of the {GROUP} tickets or not in CATEGORIES')
    cat_order = [FOCUS] + sorted((c for c in counts.index if c not in (FOCUS, '')), key=lambda c: (-counts[c], c))
    rank = {c: i for i, c in enumerate(cat_order + [''])}
    cohort_rank = {c: i for i, c in enumerate([BEFORE] + COHORTS + [AFTER])}
    e = e.assign(_c=e.category.fillna('').map(rank), _a=e.age_group.map({U4: 0, O4: 1}),
                 _k=e.cohort.map(cohort_rank))
    e = e.sort_values(['_c', '_a', '_k', 'model', 'ts', 'case_id'], kind='mergesort').reset_index(drop=True)

    free = {v for f in FREE_TEXT for v in raw[f].map(common.clean).dropna().astype(str) if len(v) >= FREE_TEXT_MIN}
    private = {'maps': maps, 'free_text': free, 'dispatch': set(e.dispatch.dropna().astype(str))}
    n_monitoring = int(((tp.cgroup == GROUP) & tp.monitoring).sum())
    check.stop_if_failed('identifier')
    return mx, tp, e, support, cat_order, n_monitoring, private


def machines_frame(e, tp):
    """One row per machine with a GROUP ticket: its tickets by Category; most FOCUS tickets first."""
    g = e.groupby('serial')
    mf = g[['serial_id', 'account', 'customer', 'model', 'install_date', 'cohort', 'age_group', 'comparison']].first()
    mf['n_group'] = g.size()
    for c in CATEGORIES:
        mf[f'n:{c}'] = e[e.ctype == c].groupby('serial').size().reindex(mf.index, fill_value=0)
    mf['n_other'] = mf.n_group - mf[[f'n:{c}' for c in CATEGORIES]].sum(axis=1)
    mf['n_all'] = tp.groupby('serial').size().reindex(mf.index)
    keys = [f'n:{FOCUS}', 'n_group', 'n_all', 'model', 'serial_id']
    return mf.reset_index().sort_values(keys, ascending=[False, False, False, True, True], kind='mergesort') \
        .reset_index(drop=True)


# ----------------------------------------------------------------------------------------------------------------
# The Summary's tables, recomputed from the list, and checked against the committed results
# ----------------------------------------------------------------------------------------------------------------
def by_model_age(frame, models, value=None):
    """Tickets (or the sum of value) by model x age group: a models x [Under 4, 4+] frame."""
    g = frame.groupby(['model', 'age_group'])
    s = g.size() if value is None else g[value].sum()
    return s.unstack().reindex(index=models, columns=AGES).fillna(0.0).astype(float)


def summary(mx, tp, e, support, cat_order, check):
    """The Summary's five tables as DataFrames, each checked against verification/outputs/followups/."""
    rates = pd.read_csv(RESULTS / 'ag_type_rates.csv')
    decomp = pd.read_csv(RESULTS / 'ag_decomposition.csv')
    pooled = pd.read_csv(RESULTS / 'ag_install_pooled.csv')
    years = pd.read_csv(RESULTS / 'ag_install_year.csv')
    halves = pd.read_csv(RESULTS / 'ag_halves.csv')
    bym = pd.read_csv(RESULTS / 'ag_by_model.csv')
    sup_csv = pd.read_csv(RESULTS / 'ag_support.csv')
    bands = pd.read_csv(RESULTS / 'ag_band_rates.csv')
    models = sorted(mx.model.unique())
    sup = np.isin(models, support)
    M = by_model_age(mx, models, 'months')
    my, mo = M[U4].sum(), M[O4].sum()
    young = mx.age_group.eq(U4)
    out = {}

    check('comparison models = ag_support.csv', support == sorted(set(sup_csv.model[sup_csv.in_support])),
          f'{len(support)} models with {F.MIN_SUPPORT_MONTHS}+ machine-months in each age group')
    band = bands[bands.type == 'All unplanned tickets'].assign(g=lambda d: np.where(
        d.age_band.isin(F.YOUNG_BANDS), U4, O4)).groupby('g')[['machines', 'months', 'tickets']].sum()
    grow = rates[(rates.level == 'group') & (rates.type == GROUP)].iloc[0]
    pop = pd.DataFrame({U4: [int(young.sum()), my, int(tp.age_group.eq(U4).sum()), int(e.age_group.eq(U4).sum())],
                        O4: [int((~young).sum()), mo, int(tp.age_group.eq(O4).sum()), int(e.age_group.eq(O4).sum())]},
                       index=["Machines on IPA's list", 'Machine-months', 'Unplanned tickets', f'{GROUP} tickets'])
    pop['All'] = pop[U4] + pop[O4]
    pop.loc[f'{GROUP} per 100 machine-months'] = 100 * pop.iloc[3] / pop.iloc[1]
    check('machines, machine-months and tickets by age group = ag_band_rates.csv, ag_type_rates.csv',
          close(pop.iloc[:3, :2].T.to_numpy(), band.loc[AGES].to_numpy())
          and close([my, mo], [grow.under4_months, grow.plus4_months]),
          f'{pop.iat[0, 0]:,.0f} and {pop.iat[0, 1]:,.0f} machines, {my:,.2f} and {mo:,.2f} machine-months, '
          f'{pop.iat[2, 0]:,.0f} and {pop.iat[2, 1]:,.0f} tickets')
    out['population'] = pop

    # Table 2: GROUP tickets by Category and age group.
    rows = []
    for label, sel in [(GROUP, e.index == e.index)] + [(c, e.ctype == c) for c in cat_order] \
            + [(NO_CATEGORY, e.ctype == F.NO_CAT)]:
        T = by_model_age(e[sel], models)
        ty, to = T[U4].sum(), T[O4].sum()
        csv = rates[(rates.level == 'group') & (rates.type == GROUP)] if label == GROUP else \
            rates[(rates.level == 'category') & (rates.group == GROUP) & (rates.type == label)]
        dec = decomp[(decomp.level == 'group') & (decomp.type == GROUP)] if label == GROUP else \
            decomp[(decomp.level == 'category') & (decomp.group == GROUP) & (decomp.type == label)]
        within = float((T.loc[sup, U4] - M.loc[sup, U4] * T.loc[sup, O4] / M.loc[sup, O4]).sum())
        rows.append({'Category': label, 'u4': ty, 'o4': to, 'r_u4': 100 * ty / my, 'r_o4': 100 * to / mo,
                     'ratio': (ty / my) / (to / mo) if to else np.nan,
                     'lo': csv.rate_ratio_lo.iloc[0] if len(csv) else np.nan,
                     'hi': csv.rate_ratio_hi.iloc[0] if len(csv) else np.nan,
                     'expected': my * to / mo, 'extra': ty - my * to / mo,
                     'within': within if len(dec) else np.nan,
                     'csv_row': csv, 'dec_row': dec, 'within_all': within})
    cat = pd.DataFrame(rows)
    shown = cat[cat.csv_row.map(len) > 0]
    check(f'{GROUP} tickets by Category x age group = ag_type_rates.csv',
          len(shown) == len(cat) - 1 and all(close([r.u4, r.o4], [r.csv_row.under4_tickets.iloc[0],
                                                                   r.csv_row.plus4_tickets.iloc[0]])
                                             and close(r.ratio, r.csv_row.rate_ratio.iloc[0])
                                             for r in shown.itertuples())
          and cat.u4.iloc[0] == cat.u4.iloc[1:].sum() and cat.o4.iloc[0] == cat.o4.iloc[1:].sum(),
          f'{len(shown) - 1} Categories and the group row ({cat.u4.iloc[0]:,.0f} and {cat.o4.iloc[0]:,.0f}; '
          f'{cat.u4.iloc[-1]:,.0f} and {cat.o4.iloc[-1]:,.0f} with no Category)')
    dec_rows = cat[cat.dec_row.map(len) > 0]
    check('extra tickets, crude and within model = ag_decomposition.csv',
          len(dec_rows) > 0 and all(close([r.extra, r.within_all], [r.dec_row.extra_tickets.iloc[0],
                                                                      r.dec_row.within_model_age_tickets.iloc[0]])
                                    for r in dec_rows.itertuples()),
          ', '.join(f'{r.Category} {r.extra:+,.0f} / {r.within_all:+,.0f}' for r in dec_rows.itertuples()))
    out['categories'] = cat.drop(columns=['csv_row', 'dec_row', 'within_all'])

    # Table 3: FOCUS by install cohort, comparison models pooled and each big model.
    fe = e[e.ctype == FOCUS]
    rows = []
    for c in COHORTS:
        msel = mx.in_support & mx.cohort.eq(c)
        rows.append({'cohort': c, 'machines': int(msel.sum()), 'months': mx.months[msel].sum(),
                     'tickets': int((fe.in_support & fe.cohort.eq(c)).sum()),
                     'u4_share': float(young[msel].mean()) if msel.any() else np.nan})
    coh = pd.DataFrame(rows)
    coh['rate'] = 100 * coh.tickets / coh.months
    coh['ratio'] = coh.rate / coh.rate.iloc[-1]
    csv = pooled[(pooled.category == FOCUS) & (pooled.unit == 'cohort')].set_index('install').reindex(coh.cohort)
    coh['lo'], coh['hi'] = csv.ratio_lo.to_numpy(), csv.ratio_hi.to_numpy()
    coh.loc[coh.index[-1], ['lo', 'hi']] = np.nan     # the reference cohort: ratio 1 by definition
    check(f'{FOCUS} by install cohort (comparison models) = ag_install_pooled.csv',
          close(coh[['machines', 'months', 'tickets', 'rate', 'u4_share', 'ratio']].to_numpy(),
                csv[['machines', 'months', 'tickets', 'rate_per_100', 'under4_share_of_machines',
                     'ratio_to_newest_cohort']].to_numpy()),
          ', '.join(f'{r.cohort} {r.tickets}' for r in coh.itertuples()) + f' tickets')
    out['cohorts'] = coh
    rows = []
    yr = years[(years.category == FOCUS) & years.model.isin(BIG_MODELS)].assign(
        cohort=lambda d: d.install_year.map(cohort_of)).groupby(['model', 'cohort'])[['machines', 'months',
                                                                                      'tickets']].sum()
    for model in BIG_MODELS:
        for c in COHORTS:
            msel = mx.model.eq(model) & mx.cohort.eq(c)
            rows.append({'model': model, 'cohort': c, 'machines': int(msel.sum()), 'months': mx.months[msel].sum(),
                         'tickets': int((fe.model.eq(model) & fe.cohort.eq(c)).sum())})
    big = pd.DataFrame(rows)
    big['rate'] = 100 * big.tickets / big.months
    ref = yr.reindex(pd.MultiIndex.from_frame(big[['model', 'cohort']])).fillna(0.0)
    check(f'{FOCUS} by install cohort on the big models = ag_install_year.csv',
          close(big[['machines', 'months', 'tickets']].to_numpy(), ref.to_numpy()),
          '; '.join(f'{m} ' + ', '.join(f'{r.cohort} {r.tickets}' for r in big[big.model == m].itertuples())
                    for m in BIG_MODELS))
    out['big_models'] = big

    # Table 4: the halves, comparison models, for the Categories of GROUP that ag_halves.csv holds.
    rows = []
    for c in halves[halves.group == GROUP].category:
        for h, col in (('H1', 'months_h1'), ('H2', 'months_h2')):
            T = by_model_age(e[(e.ctype == c) & e.half.eq(h)], models)
            Mh = by_model_age(mx, models, col)
            n, mm = T.loc[sup, U4].sum(), Mh.loc[sup, U4].sum()
            same = (Mh.loc[sup, U4] * T.loc[sup, O4] / Mh.loc[sup, O4]).sum()
            rows.append({'category': c, 'half': h, 'tickets': n, 'months': mm, 'rate': 100 * n / mm,
                         'same': 100 * same / mm, 'gap': 100 * (n - same) / mm})
    hv = pd.DataFrame(rows)
    ref = halves.set_index('category')
    want = [[ref.at[r.category, f'{r.half.lower()}_{k}'] for k in ('under4_tickets_support', 'under4_months_support',
                                                                   'under4_rate_per_100_support',
                                                                   'same_model_4plus_rate_per_100',
                                                                   'within_model_age_per_100')]
            for r in hv.itertuples()]
    check('under-4 tickets, machine-months and gaps by half = ag_halves.csv',
          len(hv) > 0 and close(hv[['tickets', 'months', 'rate', 'same', 'gap']].to_numpy(), want),
          '; '.join(f'{c} ' + ' / '.join(f'{r.half} {r.tickets:.0f}' for r in hv[hv.category == c].itertuples())
                    for c in hv.category.unique()))
    out['halves'] = hv

    # Table 5: each Category, then its Sub Categories (most tickets first, blank last).
    sub = e.assign(c=e.category.fillna(NO_CATEGORY), s=e.subcategory.fillna('(blank)'))
    rows = []
    for c in cat_order + [NO_CATEGORY]:
        x = sub[sub.c == c]
        n = x.groupby(['s', 'age_group']).size().unstack().reindex(columns=AGES).fillna(0).astype(int).reset_index()
        n = n.assign(t=n[U4] + n[O4], b=n.s.eq('(blank)')).sort_values(['b', 't', 's'], ascending=[True, False, True],
                                                                       kind='mergesort')
        rows.append({'label': c, 'level': 'category', U4: int(x.age_group.eq(U4).sum()),
                     O4: int(x.age_group.eq(O4).sum())})
        if not n.b.all():                      # a Category whose Sub Category is always blank gets no sub rows
            rows += [{'label': lab, 'level': 'sub', U4: a, O4: b}
                     for lab, a, b in n[['s', U4, O4]].itertuples(index=False, name=None)]
    t5 = pd.DataFrame(rows)
    t5['r_u4'], t5['r_o4'] = 100 * t5[U4] / my, 100 * t5[O4] / mo
    tops = t5[t5.level == 'category'].set_index('label')[[U4, O4]]
    subs = t5.assign(c=t5.label.where(t5.level == 'category').ffill())
    subs = subs[subs.level == 'sub'].groupby('c')[[U4, O4]].sum()
    check('Sub Category rows add up to their Categories, the Categories to the list',
          bool((subs == tops.reindex(subs.index)).all().all()) and tops.sum().tolist() == cat[['u4', 'o4']].iloc[0]
          .tolist(), f'{len(t5) - len(tops)} Sub Category rows under {len(subs)} of {len(tops)} Categories')
    out['subcategories'] = t5

    # Tickets by model and age group behind slide 4c.
    T = by_model_age(e, models)
    got = [T.at[r.model, r.age_group] for r in bym.itertuples()]
    check(f'{GROUP} tickets by model and age group = ag_by_model.csv',
          close(got, bym[f'tickets_{GROUP}']),
          f'{len(bym)} rows, {bym.model.nunique()} models, {int(sum(got)):,} tickets')
    allt = by_model_age(tp, models)
    out['mix'] = {'u4': T.at[MIX_MODEL, U4], 'o4': T.at[MIX_MODEL, O4], 'all_u4': allt.at[MIX_MODEL, U4],
                  'all_o4': allt.at[MIX_MODEL, O4]}
    return out


# ----------------------------------------------------------------------------------------------------------------
# Workbook
# ----------------------------------------------------------------------------------------------------------------
def plain(v):
    """A value openpyxl writes as intended: NaN, NaT and infinity -> empty, Timestamp -> datetime, numpy -> Python."""
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime()
    v = v.item() if isinstance(v, np.generic) else v
    return None if isinstance(v, float) and not np.isfinite(v) else v


def field_values(frame, field, real):
    if isinstance(field, tuple):
        field = field[0] if real else field[1]
    return [None] * len(frame) if field is None else [plain(v) for v in frame[field].tolist()]


def list_sheet(wb, title, frame, columns, real):
    """A list sheet: header row (bold, filled), one row per frame row, frozen panes, a filter on every column."""
    ws = wb.create_sheet(title)
    for j, (head, _, width, _) in enumerate(columns, 1):
        cell = ws.cell(1, j, head)
        cell.font, cell.fill, cell.alignment = BOLD, HEAD_FILL, HEAD_ALIGN
        ws.column_dimensions[get_column_letter(j)].width = width
    for j, (_, field, _, fmt) in enumerate(columns, 1):
        for i, v in enumerate(field_values(frame, field, real), 2):
            cell = ws.cell(i, j, v)
            cell.font = FONT
            if fmt:
                cell.number_format = fmt
    ws.freeze_panes = 'B2'
    ws.auto_filter.ref = f'A1:{get_column_letter(len(columns))}{len(frame) + 1}'
    ws.print_options.gridLines = True
    print_setup(ws, title_rows='1:1')
    return ws


def print_setup(ws, title_rows=None):
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    if title_rows:
        ws.print_title_rows = title_rows


def readme_rows(mx, tp, e, support, cat_order, n_monitoring, s, real):
    """The Read me sheet: (kind, label, text) rows, every number taken from the list."""
    cat = s['categories'].set_index('Category')
    g, fc = cat.loc[GROUP], cat.loc[FOCUS]
    second = next(c for c in cat_order if c != FOCUS)
    coh = s['cohorts'].set_index('cohort')
    hv = s['halves']
    mix = s['mix']
    nf = e[(e.ctype == FOCUS) & e.cohort.eq(FOCUS_COHORT)]
    cluster = nf[nf.in_support]
    neg = int((e.age_at_ticket < 0).sum())
    codes = ', '.join(sorted(e.trouble_code.dropna().unique()))
    cats = ', '.join(c for c in cat_order)
    newest, previous = COHORTS[-1], COHORTS[COHORTS.index(FOCUS_COHORT) - 1]
    h = {c: hv[hv.category == c].set_index('half') for c in hv.category.unique()}
    first, *others = h
    halves = (f"young machines' {first} tickets went from {h[first].at['H1', 'tickets']:.0f} in the first half of the "
              f"year to {h[first].at['H2', 'tickets']:.0f} in the second, and their gap to older machines of the same "
              f"models from {h[first].at['H1', 'gap']:.2f} to {h[first].at['H2', 'gap']:.2f} per 100 machine-months"
              + ''.join(f"; {c}: {h[c].at['H1', 'tickets']:.0f} to {h[c].at['H2', 'tickets']:.0f} tickets, gap "
                        f"{h[c].at['H1', 'gap']:.2f} to {h[c].at['H2', 'gap']:.2f}" for c in others))
    fu4 = e[(e.ctype == FOCUS) & e.age_group.eq(U4)]
    top = cat.loc[cat_order, 'within'].idxmax()
    rows = [
        ('notice', None, NOTICE_REAL if real else NOTICE_PSEUDO),
        ('title', None, f'IPA {GROUP} service cases, 1 Aug 2025 to 31 Aug 2026'),
        ('item', 'Built', f"{date.today():%d %b %Y} by viz/deliverables/build_electronics_cases.py, from IPA's case "
                          'export (Aug 2025 to Aug 2026) and installed-base list (19 Oct 2026), with the selection '
                          'of verification/followups.py (Part A).'),
        ('blank', None, None),
        ('heading', None, 'What this is'),
        ('item', None, f'Every unplanned service case of request type {GROUP} on the machines behind slides 4a to 4e '
                       f'of the update deck: {len(e):,} cases, {g.u4:,.0f} on machines under 4 years old and '
                       f'{g.o4:,.0f} on machines 4 years old or older. One row per case, with IPA\'s case number, '
                       "so that each case can be looked up in IPA's systems."),
        ('item', None, f'The slides found {GROUP} tickets more common on young machines, {g.r_u4:.2f} against '
                       f'{g.r_o4:.2f} per 100 machine-months ({g.ratio:.2f} times), mostly because of {FOCUS}: '
                       f'{fc.u4:,.0f} tickets on young machines against {fc.o4:,.0f} on older ones '
                       f'({fc.ratio:.1f} times the rate). The next largest Category, {second}, runs at '
                       f'{cat.at[second, "ratio"]:.2f} times the older machines\' rate.'),
        ('blank', None, None),
        ('heading', None, 'Sheets'),
        ('item', SUMMARY, "The slides' numbers recomputed from this list, to show how the list ties to them "
                          '(tables 1 to 5).'),
        ('item', CLUSTER, f"Slide 4d's cluster: the {len(cluster):,} {FOCUS} tickets on machines installed in "
                          f'{FOCUS_COHORT}, on the {len(support)} comparison models; the same rows as in '
                          f"'{CASES}', in the same order."),
        ('item', CASES, f'All {len(e):,} cases, one row per case: the case, the machine, its age, the Category; '
                        f'sorted by Category ({FOCUS} first), age group (under 4 first), install cohort, model and '
                        'opening time.'),
        ('item', MACHINES, f'The {e.serial.nunique():,} machines with at least one {GROUP} ticket, one row each: '
                           f'their {GROUP} tickets by Category and all their unplanned tickets in the year, sorted '
                           f'by {FOCUS} tickets, then {GROUP} tickets, most first.'),
        ('blank', None, None),
        ('heading', None, 'How the counts tie to the slides'),
        ('item', 'Slide 4a', f'{GROUP}: {g.u4:,.0f} tickets on under-4 machines over {s["population"].iat[1, 0]:,.0f} '
                             f'machine-months ({g.r_u4:.2f} per 100) and {g.o4:,.0f} on 4+ machines over '
                             f'{s["population"].iat[1, 1]:,.0f} ({g.r_o4:.2f}): {g.ratio:.2f} times (95% interval '
                             f'{g.lo:.2f} to {g.hi:.2f}). Summary, tables 1 and 2.'),
        ('item', 'Slide 4b', f'Against the same models\' 4+ rates, young machines have {g.within:+,.0f} {GROUP} '
                             f'tickets; {FOCUS} accounts for {fc.within:+,.0f} of them'
                             + (', the most of any Category' if top == FOCUS else '') + '. Summary, table 2.'),
        ('item', 'Slide 4c', f"On {MIX_MODEL}, {GROUP} is {mix['u4'] / mix['all_u4']:.0%} of young machines' tickets "
                             f"({mix['u4']:,.0f} of {mix['all_u4']:,.0f}) against {mix['o4'] / mix['all_o4']:.0%} on "
                             f"older ones ({mix['o4']:,.0f} of {mix['all_o4']:,.0f}). The list's tickets by model and "
                             'age group are the ones behind the slide.'),
        ('item', 'Slide 4d', f'{FOCUS} tickets on the comparison models, by install cohort: '
                             + ', '.join(f'{coh.at[c, "tickets"]:,} ({c})' for c in COHORTS)
                             + f'. Per 100 machine-months, {FOCUS_COHORT} installs run '
                             f'{coh.at[FOCUS_COHORT, "rate"]:.2f} against {coh.at[newest, "rate"]:.2f} for {newest} '
                             f'and {coh.at[previous, "rate"]:.2f} for {previous}. Summary, table 3; the '
                             f"{len(cluster):,} tickets are in sheet '{CLUSTER}'."),
        ('item', 'Slide 4e', f'On the comparison models, {halves}. Summary, table 4.'),
        ('blank', None, None),
        ('heading', None, 'How to filter'),
        ('item', None, 'Each list sheet has a filter arrow on every column heading (Data > Filter in Excel). Pick '
                       'values in one or more columns to show only those rows; Data > Clear shows every row again.'),
        ('item', 'Example', f"In '{CASES}', Category = {FOCUS} and Install cohort = {FOCUS_COHORT}: the {len(nf):,} "
                            + (f"tickets of slide 4d's cluster (sheet '{CLUSTER}')." if len(nf) == len(cluster) else
                               f'tickets; add Comparison model = Yes for the {len(cluster):,} of slide 4d\'s '
                               f"cluster (sheet '{CLUSTER}').")),
        ('item', 'Example', f'Category = {FOCUS} and Age group = Under 4: the {len(fu4):,} {FOCUS} tickets on young '
                            f'machines (slides 4a and 4b); add Half = H2 for the {int(fu4.half.eq("H2").sum()):,} '
                            'of the second half.'),
        ('item', 'Example', f'Comparison model = Yes keeps the {int(e.in_support.sum()):,} tickets on the '
                            f'{len(support)} comparison models, which the within-model figures use.'),
        ('item', 'Example', f"In '{MACHINES}', the machines at the top had the most {FOCUS} tickets; filter a model "
                            'or an account to see its machines.'),
        ('blank', None, None),
        ('heading', None, "Which tickets are the 'extra' ones?"),
        ('item', None, f'They cannot be singled out: the excess is a difference between rates. Young machines had '
                       f'{fc.u4:,.0f} {FOCUS} tickets; at older machines\' rate ({fc.r_o4:.2f} per 100 '
                       f'machine-months) they would have had about {fc.expected:,.0f}, so about {fc.extra:,.0f} are '
                       f'extra. But each of the {fc.u4:,.0f} is a real case, and any of them could be among the '
                       f'{fc.expected:,.0f}. So the list shows every ticket, on young and older machines alike, to '
                       'compare them: which machines, which Sub Categories, when.'),
        ('blank', None, None),
        ('heading', None, 'Definitions'),
        ('item', 'Unplanned ticket', "A case in IPA's case export opened 1 Aug 2025 to 31 Aug 2026, except planned "
                                     'work (Preventative Maintenance and Installation trouble codes, Install Cases), '
                                     'cancelled requests and duplicate cases, on a machine on IPA\'s installed-base '
                                     'list of 19 Oct 2026 (machines on a third-party plan left out): slide 4\'s '
                                     f'{len(tp):,} tickets on {len(mx):,} machines.'),
        ('item', f'Request type {GROUP}', f'Trouble Code {codes}, with any Category ({cats} or none). A ticket raised '
                                          "by the daily monitoring poll ('Monitoring - Daily/Poll') counts as request "
                                          'type Monitoring instead, as on the slides, and is not listed '
                                          f'({n_monitoring} with Trouble Code {codes}).'),
        ('item', 'Machine-months', "The months a machine was on IPA's list in the year: from its install date (or its "
                                   'first ticket, if earlier), but no earlier than 1 Aug 2025, to 31 Aug 2026. Rates '
                                   'are tickets per 100 machine-months.'),
        ('item', 'Age group', "Under 4 or 4+: the machine's age at the midpoint of its machine-months, from the "
                              "install date on IPA's list; under 4 = slide 4's first three bars (age bands <1, 1-2 "
                              'and 2-4 years). A machine keeps its age group all year.'),
        ('item', 'Age band', "The machine's slide-4 age band on the same midpoint age: <1, 1-2, 2-4, 4-6, 6-8, 8-10 "
                             'or 10+ years.'),
        ('item', 'Age at ticket', "Years from the install date to the case's opening"
                                  + (f"; negative for {neg} case{'s' if neg != 1 else ''} opened before the install "
                                     "date on IPA's list." if neg else '.')),
        ('item', 'Comparison model', f'Yes for the {len(support)} models with 100 or more machine-months in each age '
                                     'group, which the within-model comparisons (slides 4a right, 4b and 4e) and '
                                     f'slide 4d use: {", ".join(support)}.'),
        ('item', 'Install cohort', f"By install year on IPA's list: {', '.join(COHORTS)}; earlier installs are "
                                   f"'{BEFORE}'."),
        ('item', 'Half', 'H1 = opened 1 Aug 2025 to 14 Feb 2026; H2 = opened 15 Feb to 31 Aug 2026 (slide 4e).'),
        ('item', 'Account, Model, Install date', "From IPA's installed-base list, for the machine's serial number (the "
                                                 'account on the case can differ).'),
        ('item', "Machine's tickets", f"The machine's unplanned {GROUP} (or {FOCUS}) tickets in the year, all of them "
                                      'in this list: machines with repeated tickets stand out.'),
        ('item', 'Case export fields', "Case Number, Opened (Date/Time Opened), Closed (Trouble Closed Date/Time), "
                                       "Status and Dispatch #: as in IPA's case export."),
    ]
    return rows


def write_readme(ws, rows):
    ws.title = README
    ws.sheet_view.showGridLines = False
    ws.column_dimensions['A'].width, ws.column_dimensions['B'].width = 26, 112
    for r, (kind, label, text) in enumerate(rows, 1):
        if kind == 'title':
            ws.cell(r, 1, text).font = TITLE
        elif kind == 'notice':
            ws.cell(r, 1, text).font = NOTICE
            ws.cell(r, 1).fill = ws.cell(r, 2).fill = NOTICE_FILL
        elif kind == 'heading':
            ws.cell(r, 1, text).font = HEADING
        elif kind == 'item':
            if label:
                cell = ws.cell(r, 1, label)
                cell.font, cell.alignment = BOLD, WRAP
            cell = ws.cell(r, 2, text)
            cell.font, cell.alignment = FONT, WRAP
    print_setup(ws)
    return len(rows)


def write_block(ws, row, title, header, rows, formats, notes=(), styles=None):
    """One Summary table: title, notes, header row, data rows ('bold' or 'indent' per row in styles). Returns the
    next free row (after a blank one)."""
    ws.cell(row, 1, title).font = HEADING
    for note in notes:
        row += 1
        ws.cell(row, 1, note).font = NOTE
    row += 1
    for j, (h, fmt) in enumerate(zip(header, formats), 1):
        cell = ws.cell(row, j, h)
        cell.font, cell.fill, cell.alignment = BOLD, HEAD_FILL, HEAD_RIGHT if fmt else HEAD_ALIGN
    for i, values in enumerate(rows):
        row += 1
        style = styles[i] if styles else None
        for j, (v, fmt) in enumerate(zip(values, formats), 1):
            cell = ws.cell(row, j, plain(v))
            cell.font = BOLD if style == 'bold' else FONT
            if fmt:
                cell.number_format = fmt
            if j == 1 and style == 'indent':
                cell.alignment = INDENT
    return row + 2


def write_summary(ws, s, support):
    ws.sheet_view.showGridLines = False
    for j, width in enumerate([38] + [12] * 10, 1):
        ws.column_dimensions[get_column_letter(j)].width = width
    ws.cell(1, 1, "Summary: the slides' numbers, recomputed from this list").font = TITLE
    ws.cell(2, 1, 'Rates are tickets per 100 machine-months. 95% intervals: the follow-up analysis\'s account '
                  'bootstrap.').font = NOTE
    pop = s['population']
    first = 4 + 2                                          # title, header, then the data rows
    row = write_block(ws, 4, '1. Machines, machine-months and tickets by age group, 1 Aug 2025 to 31 Aug 2026 '
                      '(slide 4)', ['', U4, O4, 'All'],
                      [[k, *v] for k, v in zip(pop.index, pop.to_numpy().tolist())],
                      [None, COUNT, COUNT, COUNT])
    for r, fmt in ((first + 1, MONTHS), (first + 4, RATE)):  # the machine-months and rate rows
        for j in (2, 3, 4):
            ws.cell(r, j).number_format = fmt
    cat = s['categories']
    row = write_block(
        ws, row, f'2. {GROUP} tickets by Category and age group (slides 4a and 4b)',
        ['Category', f'Tickets, {U4.lower()}', f'Tickets, {O4}', f'Per 100 machine-months, {U4.lower()}',
         f'Per 100 machine-months, {O4}', f'Ratio, {U4.lower()} / {O4}', 'Ratio, 95% interval from', 'to',
         f'{U4} tickets expected at the {O4} rate', f'Extra {U4.lower()} tickets (crude)',
         'Extra within model (slide 4b)'],
        cat[['Category', 'u4', 'o4', 'r_u4', 'r_o4', 'ratio', 'lo', 'hi', 'expected', 'extra', 'within']]
        .to_numpy().tolist(),
        [None, COUNT, COUNT, RATE, RATE, RATE, RATE, RATE, COUNT, SIGNED, SIGNED],
        notes=[f'Expected = under-4 machine-months x the 4+ machines\' rate; extra = tickets - expected. Extra within '
               f"model: against each model's own 4+ rate, over the {len(support)} comparison models (slide 4b); shown "
               'where the follow-up reports it.',
               'An interval end is blank where the follow-up has none (too few tickets, or no Category row).'])
    coh = s['cohorts']
    row = write_block(
        ws, row, f'3. {FOCUS} tickets by install cohort, the {len(support)} comparison models (slide 4d)',
        ['Install cohort', 'Machines', 'Machine-months', f'{FOCUS} tickets', 'Per 100 machine-months',
         f'Ratio to {COHORTS[-1]}', 'Ratio, 95% interval from', 'to', f'Share of machines {U4.lower()}'],
        coh[['cohort', 'machines', 'months', 'tickets', 'rate', 'ratio', 'lo', 'hi', 'u4_share']].to_numpy().tolist(),
        [None, COUNT, MONTHS, COUNT, RATE, RATE, RATE, RATE, '0%'],
        notes=["Machines of both age groups, by install year on IPA's list."])
    big = s['big_models']
    row = write_block(ws, row - 1, '    The same on each big 2.0 model',
                      ['Model', 'Install cohort', 'Machines', 'Machine-months', f'{FOCUS} tickets',
                       'Per 100 machine-months'],
                      big[['model', 'cohort', 'machines', 'months', 'tickets', 'rate']].to_numpy().tolist(),
                      [None, None, COUNT, MONTHS, COUNT, RATE])
    hv = s['halves']
    row = write_block(
        ws, row, f"4. Young machines' tickets by half, the {len(support)} comparison models (slide 4e)",
        ['Category', 'Half', f'Tickets, {U4.lower()}', f'Machine-months, {U4.lower()}', 'Per 100 machine-months',
         "Same models' 4+ machines, per 100", 'Gap, per 100 (slide 4e)'],
        hv[['category', 'half', 'tickets', 'months', 'rate', 'same', 'gap']].to_numpy().tolist(),
        [None, None, COUNT, MONTHS, RATE, RATE, RATE],
        notes=['H1 = 1 Aug 2025 to 14 Feb 2026, H2 = 15 Feb to 31 Aug 2026. Same models\' 4+ machines: their rate in '
               'the same half, weighted to the young machines\' models. Gap = the difference.'])
    t5 = s['subcategories']
    row = write_block(
        ws, row, f'5. {GROUP} tickets by Category and Sub Category',
        ['Category, then its Sub Categories', f'Tickets, {U4.lower()}', f'Tickets, {O4}',
         f'Per 100 machine-months, {U4.lower()}', f'Per 100 machine-months, {O4}'],
        t5[['label', U4, O4, 'r_u4', 'r_o4']].to_numpy().tolist(), [None, COUNT, COUNT, '0.000', '0.000'],
        styles=['bold' if v == 'category' else 'indent' for v in t5.level])
    print_setup(ws)
    return row - 2


def ignore_text_numbers(path, sheets):
    """Mark digit-only identifiers stored as text as intended, so Excel flags no 'number stored as text' cell:
    an ignoredErrors element (its place in CT_Worksheet: before smartTags, drawing, ..., extLst) on each sheet."""
    with zipfile.ZipFile(path) as z:
        items = [(info, z.read(info.filename)) for info in z.infolist()]
    done = 0
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for info, data in items:
            ref = sheets.get(info.filename)
            if ref:
                xml = data.decode('utf-8')
                cut = min(xml.find(tag) for tag in AFTER_IGNORED if tag in xml)
                xml = (xml[:cut] + f'<ignoredErrors><ignoredError sqref="{ref}" numberStoredAsText="1"/>'
                       '</ignoredErrors>' + xml[cut:])
                data, done = xml.encode('utf-8'), done + 1
            z.writestr(info, data)
    if done != len(sheets):
        fail(f'ignoredErrors set on {done} of {len(sheets)} list sheets')


def workbook(path, mx, tp, e, mf, support, cat_order, n_monitoring, s, real):
    """Write the workbook to path. Returns {sheet: rows written (list sheets: data rows)} and the cluster's rows."""
    wb = Workbook()
    wb.properties.title = f'IPA {GROUP} cases' + ('' if real else ' (pseudonymous review copy)')
    written = {README: write_readme(wb.active, readme_rows(mx, tp, e, support, cat_order, n_monitoring, s, real))}
    written[SUMMARY] = write_summary(wb.create_sheet(SUMMARY), s, support)
    cluster = e[(e.ctype == FOCUS) & e.cohort.eq(FOCUS_COHORT) & e.in_support]
    for title, frame, columns in ((CLUSTER, cluster, CASE_COLUMNS), (CASES, e, CASE_COLUMNS),
                                  (MACHINES, mf, MACHINE_COLUMNS)):
        list_sheet(wb, title, frame, columns, real)
        written[title] = len(frame)
    wb.save(path)
    ignore_text_numbers(path, {f'xl/worksheets/sheet{i}.xml': ws.dimensions
                               for i, ws in enumerate(wb.worksheets, 1) if ws.title in (CLUSTER, CASES, MACHINES)})
    return written, cluster


def check_workbook(path, written, e, cluster, mf, real, private, check):
    """Read the workbook back and check it (counts only)."""
    wb = load_workbook(path, read_only=True)
    try:
        sheets = {ws.title: [list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets}
    finally:
        wb.close()
    check('sheets', list(sheets) == [README, SUMMARY, CLUSTER, CASES, MACHINES],
          f'{len(sheets)}: ' + ', '.join(f"'{t}'" for t in sheets))
    rows = {t: (len(v) - 1 if t in (CLUSTER, CASES, MACHINES) else len(v)) for t, v in sheets.items()}
    check('row counts as written', rows == written,
          ', '.join(f"'{t}' {n:,}" for t, n in rows.items()) + ' (list sheets: data rows)')
    cases, heads = sheets[CASES][1:], sheets[CASES][0]
    col = {h: i for i, h in enumerate(heads)}
    want = {'Case Number': e.case_number if real else e.case_id, 'Serial Number': e.serial if real else e.serial_id,
            'Account': e.account if real else e.customer}
    same = {k: sum(r[col[k]] == v for r, v in zip(cases, w.astype(str))) for k, w in want.items()}
    dispatch = sum(r[col['Dispatch #']] == (None if pd.isna(v) or not real else str(v))
                   for r, v in zip(cases, e.dispatch.tolist()))
    machine_ids = [r[0] for r in sheets[MACHINES][1:]]
    check('identifier columns as intended', all(n == len(e) for n in same.values()) and dispatch == len(e)
          and machine_ids == (mf.serial if real else mf.serial_id).astype(str).tolist(),
          ', '.join(f'{k} {n:,}' for k, n in same.items()) + f', Dispatch # {dispatch:,} of {len(e):,} '
          f"({'real' if real else 'pseudonyms; Dispatch # blank'}); 'Machines' {len(machine_ids):,} serial numbers")
    sub = [r for r in cases if r[col['Category']] == FOCUS and r[col['Install cohort']] == FOCUS_COHORT
           and r[col['Comparison model']] == 'Yes']
    check(f"'{CLUSTER}' = the matching rows of '{CASES}'", sheets[CLUSTER][1:] == sub and len(sub) == len(cluster),
          f'{len(sheets[CLUSTER]) - 1:,} rows, {len(sub):,} matching (Category {FOCUS}, cohort {FOCUS_COHORT}, '
          'comparison model), cell for cell and in order')
    strings = [v for t in sheets for r in sheets[t] for v in r if isinstance(v, str)] + list(sheets)
    free = sum(v in private['free_text'] for v in strings if len(v) >= FREE_TEXT_MIN)
    check('no case free text in any cell', free == 0,
          f'{free} of {len(strings):,} text cells match one of {len(private["free_text"]):,} free-text values')
    if real:
        left = sum(names.pseudonyms_left(v) for v in strings)
        check('privacy: no pseudonym in the real workbook', left == 0,
              f'{left} pseudonyms (T#####, S#####, M#####, Customer NNN) in {len(strings):,} text cells')
    else:
        real_ids = F.real_sets(private['maps'], common.EQUIPMENT)
        real_ids['digit'] |= {d for d in private['dispatch'] if d.isdigit()}
        real_ids['text'] |= {FX.norm(d) for d in private['dispatch'] if not d.isdigit() and len(FX.norm(d)) >= 4}
        leaks = FX.text_leaks(pd.DataFrame({'text': strings}), real_ids)
        ids = [r[col[k]] for r in cases for k in ('Case Number', 'Serial Number', 'Account')]
        pseudo = sum(bool(re.fullmatch(r'T\d{5}|[SM]\d{5}|Customer \d{3,4}', str(v))) for v in ids)
        check('privacy: no real identifier in the pseudonymous copy', not leaks and pseudo == len(ids),
              f"{sum(leaks.values())} real names or identifiers in {len(strings):,} text cells; {pseudo:,} of "
              f'{len(ids):,} identifier cells are pseudonyms')


def git_ignored(path):
    try:
        r = subprocess.run(['git', '-C', str(ROOT), 'check-ignore', '-q', str(path)], capture_output=True, check=False)
    except FileNotFoundError:
        fail('git not found: cannot check that the workbook is gitignored')
    return r.returncode == 0


def build(pseudo_dir=None):
    real = pseudo_dir is None
    out = OUT_REAL if real else Path(pseudo_dir).resolve() / PSEUDO_FILE
    print(f"IPA {GROUP} case list ({'real identifiers' if real else 'pseudonymous review copy'})")
    tmp = None
    try:
        check = Checks()
        mx, tp, e, support, cat_order, n_monitoring, private = load(check)
        print(f'  {len(e):,} {GROUP} tickets ({int(e.age_group.eq(U4).sum()):,} under 4, '
              f'{int(e.age_group.eq(O4).sum()):,} 4+) on {e.serial.nunique():,} machines; {n_monitoring} '
              f'Monitoring tickets with Trouble Code {GROUP} left out, as on the slides')
        s = summary(mx, tp, e, support, cat_order, check)
        check.stop_if_failed('data')
        mf = machines_frame(e, tp)

        out.parent.mkdir(parents=True, exist_ok=True)
        if real and not (out.resolve().is_relative_to(names.DELIVERABLES.resolve()) and git_ignored(out)):
            fail(f'{out.name} is not under deliverables/ or not gitignored')
        fd, name = tempfile.mkstemp(prefix=f'.{out.stem}_', suffix='.xlsx', dir=out.parent)
        os.close(fd)
        tmp = Path(name)
        if real and not git_ignored(tmp):
            fail('the temporary file in deliverables/ is not gitignored')
        written, cluster = workbook(tmp, mx, tp, e, mf, support, cat_order, n_monitoring, s, real)
        print('  written: ' + ', '.join(f"'{t}' {n:,} rows" for t, n in written.items()))
        check_workbook(tmp, written, e, cluster, mf, real, private, check)
        if real:
            check('output under deliverables/ and gitignored', git_ignored(out) and git_ignored(tmp),
                  f'deliverables/{out.name} (git check-ignore)')
        check.stop_if_failed('workbook')
        os.replace(tmp, out)
        tmp = None
        print(f'  wrote {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out} '
              f'({out.stat().st_size / 1e3:,.0f} kB)')
        return out
    except BuildError:
        raise
    except Exception as err:  # noqa: BLE001  its message could quote an identifier: type and line only
        frame = traceback.extract_tb(err.__traceback__)[-1]
        fail(f'unexpected {type(err).__name__} at {Path(frame.filename).name}:{frame.lineno} (message withheld)')
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--pseudo', metavar='OUT_DIR', help=f'build the pseudonymous copy into OUT_DIR/{PSEUDO_FILE} '
                    'instead of the real workbook')
    a = ap.parse_args()
    try:
        build(a.pseudo)
    except BuildError as err:
        print(f'FAILED: {err}')
        sys.exit(1)


if __name__ == '__main__':
    main()
