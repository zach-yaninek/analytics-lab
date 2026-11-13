#!/usr/bin/env python3
"""IPA's Electronics case list: the service cases behind the Electronics finding of slides 4a-4e, as an Excel workbook
laid out for IPA's engineers to find and work through them.

Slides 4a-4c found Electronics tickets more common on machines under 4 years old than on older ones, which IPA did
not expect. The excess is FOCUS ('Touchscreen'), mostly Sub Category CORE_SUB ('Connector Reseat/Replace'), on the
four 2.0 models' machines installed in 2022-23. This builds the list, locally, into deliverables/ (gitignored); it is
never committed. It holds every unplanned ticket of request type GROUP ('Electronics': Trouble Code Electronics;
Monitoring tickets apart, as on the slides) on Part A's machines, one row per IPA case: 1,605 tickets, 875 on machines
under 4 and 730 on machines 4+, with IPA's own case notes.

Data, as verification/followups.py's Part A has it: followups.load(), then the machine and ticket frames as main()
and part_a() build them (6,750 unplanned tickets on 8,946 listed machines, 1 Aug 2025 - 31 Aug 2026; under 4 = age
bands <1, 1-2 and 2-4; comparison models = the models with 100+ machine-months in each age group). Real identifiers
and case notes, in memory only: the case number by inverting followups' case map (case_id pseudonym -> cleaned case
number); the serial number from followups' frames; the account and the field-service vendor (Service Plan) from
IPA's installed-base list (common.load_equipment); Dispatch #, Status, Date/Time Opened, Trouble Closed Date/Time,
Trouble Reported and Trouble Resolution from the case export, by case number. A case note is written as the export
has it, cleaned (common.clean), line breaks as LF, the characters XML cannot hold removed (openpyxl's
ILLEGAL_CHARACTERS_RE) and cut at TEXT_CAP characters; Administrative Notes and Case Owner are read for the checks
only and never written. No message prints a note.

Sheets (values, not formulas; Arial; bold filled headers, frozen panes and filters on the list sheets):
  Read me          privacy notice; what this is; what the list shows (rates per installed machine-month by request
                   type; FOCUS and CORE_SUB; the rest of GROUP against all tickets, crude and within model; FOCUS
                   tickets on the comparison models' machines installed in the two EDGE windows); where to start
                   (with the SPIKE lead, and how much of slide 4e's SPIKE gap it explains); what would settle it; how
                   the counts tie to slides 4a-4e, with the filters; definitions; columns. Every number is the builder's
  Summary          1 machines, machine-months and tickets by age group; 2 GROUP tickets by Category with rates,
                   ratios and extra tickets (4a, 4b); 3 FOCUS tickets by install cohort, comparison models pooled and
                   each big 2.0 model (4d); 4 the halves (4e); 5 Category x Sub Category, with each row's tickets
                   expected at the same models' 4+ rates and the extra (slide 4b's method); 6 FOCUS and CORE_SUB
                   tickets by install quarter on the four 2.0 models, pooled and each, to line up with IPA's change
                   dates; 7 subset sizes (tickets, machines, accounts) and where each sits in the workbook; 8 CORE_SUB
                   tickets within model on each comparison model: expected at the model's own 4+ rate, and the extra
  Start here       the FOCUS tickets on machines under 4 (411), by model, install date, serial number and opening:
                   the machine's FOCUS history in the year, the Core subset flag, the case notes, and four empty
                   'IPA:' columns for IPA's engineers
  Touchscreen 4+   the FOCUS tickets on machines 4+ (139): the same columns but Core subset and the IPA columns
  All Electronics  every GROUP ticket, one row per case
  Machines         one row per machine with a GROUP ticket: its tickets by Category, its FOCUS dates

Checks (printed as counts; any failure stops the build, deletes the temporary file and leaves any earlier output as
it was):
  - data: Part A's 6,750 tickets; the comparison models = ag_support.csv's; machines and machine-months by age group
    = ag_band_rates.csv and ag_type_rates.csv; tickets and crude ratios by request type = ag_type_rates.csv; GROUP
    tickets by Category x age group = ag_type_rates.csv; extra tickets, crude and within model, = ag_decomposition.csv
    (Categories, the group and all tickets); the within-model rate ratios of GROUP and FOCUS (Mantel-Haenszel over the
    comparison models, followups.mh_rate, as the Read me gives them) = ag_type_adjusted.csv; FOCUS by install cohort =
    ag_install_pooled.csv and on each big model = ag_install_year.csv; under-4 tickets, machine-months and gaps by
    half = ag_halves.csv; GROUP tickets by model and age group = ag_by_model.csv; table 5's rows add up to their
    Categories, whose extra tickets within model = ag_decomposition.csv; table 6's install quarters add up, per model
    and year, to ag_install_year.csv's FOCUS machines, machine-months and tickets; the subsets of table 7 nest as
    stated, and FOCUS on FOCUS_COHORT installs of the comparison models = ag_install_pooled.csv; table 8's models add
    up to table 5's CORE_SUB row; FOCUS by install month on the comparison models (the Read me's EDGE windows) adds
    up, per install year, to ag_install_pooled.csv, and the later window's rate is the higher;
  - identifiers: the case map inverts one to one; the listed case numbers are unique and each is in the case export
    exactly once; the export's Status and opening and closing times, by case number, = the case table's; every
    machine has a serial number and an account on IPA's list, and real and pseudonymous identifiers pair up; every
    listed case's notes are read from its own row of the export;
  - workbook, read back with openpyxl: the sheets and their row counts as written; the identifier columns of every
    list sheet as intended; 'Start here' and 'Touchscreen 4+' = the matching rows of 'All Electronics', cell for
    cell, in the stated order, with each machine's FOCUS history consistent; Category FOCUS, cohort FOCUS_COHORT and
    comparison model in 'All Electronics' = ag_install_pooled.csv (slide 4d's cluster); the Core subset and SPIKE
    flags, and the 'Machines' columns, as computed; the IPA columns empty; the case notes cell for cell as in the
    export (pseudonymous copy: same-length placeholders), and no other list-sheet cell of 40+ characters but account
    names; no cell equal to an Administrative Notes value of 40+ characters (a case's own Trouble Reported or
    Resolution text that equals one is allowed, in its column) or to a Case Owner value; the real workbook holds no
    pseudonym (T#####, S#####, M#####, Customer NNN) outside the notes, sits under deliverables/ and is gitignored
    (git check-ignore).

Pseudonymous copy (--pseudo OUT_DIR): the same workbook with the repository's pseudonyms (case_id, serial_id,
Customer NNN) in place of case numbers, serial numbers and accounts, Dispatch # blank, and each case note replaced by
a placeholder of the same length (every character but whitespace -> 'x'), for checking the layout without opening a
real identifier or note; it must hold no real identifier (followups.real_sets plus the listed dispatch numbers,
scanned as followups.py scans its outputs) and no real note, Administrative Notes or Case Owner value.

Aggregate tables (--tables): no workbook. After the data checks, the counts the report quotes go to
verification/outputs/electronics/ as CSVs of labels and counts, for the replication notebooks:
  ec_counts.csv   GROUP tickets on the list, by age group, and FOCUS tickets on machines under 4 on the four 2.0 models
  ec_subsets.csv  Summary table 7: each subset's tickets, machines and accounts
  ec_edge.csv     the Read me's step: FOCUS tickets per 100 machine-months on the comparison models' machines installed
                  in each EDGE window

Inputs:  data/raw/ (the case export and IPA's installed-base list, through verification/common.py);
         verification/outputs/fu/ (the telemetry map followups.load() reads); verification/outputs/followups/ag_*.csv
         (the committed results: the checks, and the 95% intervals the Summary shows)
Output:  deliverables/IPA_Electronics_Cases.xlsx (never commit), OUT_DIR/IPA_Electronics_Cases_PSEUDO.xlsx, or (with
         --tables) verification/outputs/electronics/ec_*.csv
Requires pandas, numpy and openpyxl, and git for the ignore check. No message prints a real identifier or a note:
counts, labels and pseudonyms only; an unexpected error is reported by its type and line, without its message.

Run:  cd /home/user/analytics-lab && python3 -I viz/deliverables/build_electronics_cases.py [--pseudo OUT_DIR | --tables]
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import traceback
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE), str(ROOT / 'verification')]  # python3 -I leaves the script directory off sys.path
import names  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from openpyxl import Workbook, load_workbook  # noqa: E402
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402
XML_INVALID = re.compile('[\ufffe\uffff\ud800-\udfff]')  # also not XML; openpyxl's pattern lets them through

import common  # noqa: E402
import fleet_exposure as FX  # noqa: E402
import followups as F  # noqa: E402

GROUP = 'Electronics'          # the request type listed (followups' 'group'); a Door list sets GROUP = 'Door' and
FOCUS = 'Touchscreen'          # ... FOCUS (the Category behind the finding: 'Start here', its own Summary tables),
FOCUS_COHORT = '2022-23'       # ... the install cohort of slide 4d's cluster and of the core subset,
CORE_SUB = 'Connector Reseat/Replace'                                 # ... the core subset's FOCUS Sub Category,
CORE_SHORT = 'Connector'                                              # ... (its short name in narrow headers),
CORE_MODELS = ('LVD-Remote-2.0', 'MV-2.0', 'LVRR-WP-2.0', 'SV-48-2.0')  # ... and models (the four 2.0 models),
CATEGORIES = ('Touchscreen', 'Computer Board', 'Power Supply', 'Badge Reader')  # ... the Machines sheet's columns,
BIG_MODELS = ('LVD-Remote-2.0', 'MV-2.0', 'LVRR-WP-2.0')  # ... slide 4d's big 2.0 models (shown one by one),
MIX_MODEL = 'LVD-Remote-2.0'   # ... slide 4c's model whose young machines' tickets are more often GROUP,
SPIKE = ('Computer Board', '2025-10')   # ... and the under-4 tickets of this Category opened in this month (flagged)
QUARTERS = [f'{y} Q{q}' for y in range(2021, 2025) for q in range(1, 5)]   # Summary table 6's install quarters
REPEAT_DAYS = (30, 90)         # 'Another within N days'
MANY = 3                       # the Read me points to machines with this many FOCUS tickets or more
# The Read me's two install windows (first and last install month) either side of the step in FOCUS tickets on the
# comparison models' machines: descriptive, the edge was found by looking at the data.
EDGE = (('2022-01', '2022-04'), ('2022-05', '2022-08'))
ALIKE = 0.1                    # two ratios within 10% of each other read 'about in line' ('about as much as')
PART_A_TICKETS = 6750          # slide 4's population (followups.py pins it)
RESULTS = common.OUTPUTS / 'followups'
TABLES = common.OUTPUTS / 'electronics'   # --tables: the aggregate tables the replication notebooks read
OUT_REAL = names.DELIVERABLES / f'IPA_{GROUP}_Cases.xlsx'
PSEUDO_FILE = f'IPA_{GROUP}_Cases_PSEUDO.xlsx'
NOTES = ('Trouble Reported', 'Trouble Resolution')         # IPA's case notes: written (pseudonymous copy: x's)
NOT_WRITTEN = ('Administrative Notes', 'Case Owner')        # read only to check that none is written
RAW_FIELDS = ('Case Number', 'Date/Time Opened', 'Dispatch #', 'Status', 'Trouble Closed Date/Time', *NOTES)
TEXT_CAP = 32000               # characters kept of a note (an Excel cell holds 32,767)
LONG = 40                      # text cells this long are tested against the notes and Administrative Notes
NOTICE_REAL = ('Contains IPA case numbers, serial numbers, customer names and case notes: for the project team and '
               'IPA only.')
NOTICE_PSEUDO = ("Review copy: pseudonyms in place of case numbers, serial numbers and customer names; Dispatch # "
                 "blank; case notes as x's.")

U4, O4 = F.AGE_LABELS                                    # 'Under 4', '4+'
AGES = list(F.AGE_LABELS)
COHORTS = [f'{a}-{str(b)[2:]}' for a, b in F.INSTALL_COHORTS]
BEFORE, AFTER = f'Before {F.INSTALL_COHORTS[0][0]}', f'After {F.INSTALL_COHORTS[-1][1]}'
FOCUS_YEARS = next((a, b) for (a, b), c in zip(F.INSTALL_COHORTS, COHORTS) if c == FOCUS_COHORT)
NO_CATEGORY = '(no Category)'
NUMBER_WORDS = dict(enumerate(('no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten')))
V2 = f'{NUMBER_WORDS[len(CORE_MODELS)]} 2.0 models'      # 'four 2.0 models'
CI = f'{1 - F.ALPHA:.0%}'                                 # the intervals' level, '95%'
POOLED = f'All {V2}'
SPIKE_MONTH = pd.Period(SPIKE[1], 'M')
SPIKE_MON, SPIKE_MONTH_NAME = SPIKE_MONTH.strftime('%b %Y'), SPIKE_MONTH.strftime('%B %Y')   # 'Oct 2025', ...
SPIKE_LABEL = f'{SPIKE_MON} {SPIKE[0]}'
EDGE_MONTHS = [(pd.Period(a, 'M'), pd.Period(b, 'M')) for a, b in EDGE]
README, SUMMARY, START, MACHINES = 'Read me', 'Summary', 'Start here', 'Machines'
OLDER, CASES = f'{FOCUS} {O4}', f'All {GROUP}'
LIST_SHEETS = (START, OLDER, CASES, MACHINES)
CASE_SHEETS = (START, OLDER, CASES)
DATETIME, DATE = 'yyyy-mm-dd hh:mm', 'yyyy-mm-dd'
COUNT, MONTHS, RATE, SIGNED = '#,##0', '#,##0.0', '0.00', '+#,##0;-#,##0;0'
PERIOD_START, LAST_DAY = FX.PERIOD_START, FX.PERIOD_END - pd.Timedelta(days=1)
H1_END = F.SPLIT - pd.Timedelta(days=1)
LIST_DATE = pd.Timestamp(re.search(r'\d{4}-\d{2}-\d{2}', common.EQUIPMENT.name).group())

# The list sheets' columns: header, field (an identifier or note: (real field, pseudonymous field); None leaves it
# blank), width, number format.
IPA_COLUMNS = (('IPA: root cause', None, 24, None), ('IPA: part or revision', None, 22, None),
               ('IPA: fix or field campaign', None, 24, None), ('IPA: fix date', None, 12, DATE))
IPA_HEADS = tuple(c[0] for c in IPA_COLUMNS)
CENTERED = {'Install quarter', 'Install cohort', 'Age group', 'Age band (years)', 'Half', 'Comparison model',
            'Core subset', 'Core 2.0 model', SPIKE_LABEL, 'Core machine',
            *(f'Another within {d} days' for d in REPEAT_DAYS)}
COLUMN = {c[0]: c for c in (
    ('Case Number', ('case_number', 'case_id'), 11, '@'),
    ('Opened', 'ts', 17, DATETIME),
    ('Closed', 'closed', 17, DATETIME),
    ('Status', 'status', 14, None),
    ('Dispatch #', ('dispatch', None), 12, '@'),
    ('Account', ('account', 'customer'), 40, None),
    ('Field-service vendor', 'service_plan', 15, None),
    ('Serial Number', ('serial', 'serial_id'), 10, '@'),
    ('Model', 'model', 15, None),
    ('Core 2.0 model', 'v2', 7, None),
    ('Install date', 'install_date', 12, DATE),
    ('Install quarter', 'quarter', 9, None),
    ('Install year', 'install_year', 8, '0'),
    ('Install cohort', 'cohort', 9, None),
    ('Age group', 'age_group', 8, None),
    ('Age band (years)', 'age_band', 8, None),
    ('Age at ticket (years)', 'age_at_ticket', 9, '0.0'),
    ('Trouble Code', 'trouble_code', 11, None),
    ('Category', 'category', 14, None),
    ('Sub Category', 'subcategory', 25, None),
    ('Half', 'half', 6, None),
    ('Comparison model', 'comparison', 10, None),
    ('Core subset', 'core_yn', 7, None),
    (SPIKE_LABEL, 'spike_yn', 11, None),
    (f"Machine's {GROUP} tickets", 'machine_group', 10, '0'),
    (f"Machine's {FOCUS} tickets", 'machine_focus', 11, '0'),
    ('Ticket # on machine', 'focus_k', 8, '0'),
    (f'Days since previous {FOCUS} ticket', 'focus_prev', 11, '0.0'),
    (f'Days to next {FOCUS} ticket', 'focus_next', 11, '0.0'),
    *((f'Another within {d} days', f'within_{d}', 9, None) for d in REPEAT_DAYS),
    ('Trouble Reported', ('reported', 'reported_x'), 60, '@'),
    ('Trouble Resolution', ('resolution', 'resolution_x'), 60, '@'),
    *IPA_COLUMNS,
)}
START_COLUMNS = tuple(COLUMN[h] for h in (
    'Case Number', 'Opened', 'Model', 'Install date', 'Install quarter', 'Serial Number', 'Account',
    'Field-service vendor', 'Sub Category', 'Core subset', f"Machine's {FOCUS} tickets", 'Ticket # on machine',
    f'Days since previous {FOCUS} ticket', f'Days to next {FOCUS} ticket',
    *(f'Another within {d} days' for d in REPEAT_DAYS), *NOTES, 'Closed', 'Status', 'Dispatch #', 'Install cohort',
    'Age band (years)', 'Age at ticket (years)', 'Half', 'Comparison model', *IPA_HEADS))
OLDER_COLUMNS = tuple(c for c in START_COLUMNS if c[0] not in ('Core subset', *IPA_HEADS))
CASE_COLUMNS = tuple(COLUMN[h] for h in (
    'Case Number', 'Opened', 'Closed', 'Status', 'Dispatch #', 'Account', 'Field-service vendor', 'Serial Number',
    'Model', 'Core 2.0 model', 'Install date', 'Install quarter', 'Install year', 'Install cohort', 'Age group',
    'Age band (years)', 'Age at ticket (years)', 'Trouble Code', 'Category', 'Sub Category', 'Half',
    'Comparison model', 'Core subset', SPIKE_LABEL, f"Machine's {GROUP} tickets", f"Machine's {FOCUS} tickets",
    *NOTES))
MACHINE_COLUMNS = (
    ('Serial Number', ('serial', 'serial_id'), 10, '@'),
    ('Account', ('account', 'customer'), 40, None),
    ('Field-service vendor', 'service_plan', 15, None),
    ('Model', 'model', 15, None),
    ('Install date', 'install_date', 12, DATE),
    ('Install quarter', 'quarter', 9, None),
    ('Install cohort', 'cohort', 9, None),
    ('Age group', 'age_group', 8, None),
    ('Comparison model', 'comparison', 10, None),
    ('Core machine', 'core_machine', 8, None),
    (f'{GROUP} tickets', 'n_group', 10, '0'),
    (FOCUS, f'n:{FOCUS}', 11, '0'),
    (f'{CORE_SUB} tickets', 'n_core_sub', 13, '0'),
    (f'First {FOCUS} ticket', 'first_focus', 11, DATE),
    (f'Last {FOCUS} ticket', 'last_focus', 11, DATE),
    *((c, f'n:{c}', 11, '0') for c in CATEGORIES if c != FOCUS),
    (f'Other {GROUP} tickets', 'n_other', 10, '0'),
    ('All unplanned tickets', 'n_all', 10, '0'),
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
IPA_FILL = PatternFill('solid', fgColor='FFF2CC')       # the IPA columns' headers: a fill of their own
WRAP = Alignment(wrap_text=True, vertical='top')
INDENT = Alignment(horizontal='left', indent=2)
HEAD_RIGHT = Alignment(wrap_text=True, vertical='bottom', horizontal='right')
HEAD_ALIGN = Alignment(wrap_text=True, vertical='bottom')
HEAD_CENTER = Alignment(wrap_text=True, vertical='bottom', horizontal='center')
CENTER = Alignment(horizontal='center')
PAD = Alignment(horizontal='left', indent=2)
SUMMARY_WIDTHS = [44] + [12] * 10   # the Summary's column widths (its widest table has 11 columns)
NOTE_CHARS = 1.2               # characters of a Summary note per unit of column width (notes wrap to their table)
LIST_SCALE = 70                # the list sheets' print scale, %
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


def quarter_of(dates):
    """'2022 Q2' for each date."""
    return dates.dt.year.astype(int).astype(str) + ' Q' + dates.dt.quarter.astype(int).astype(str)


def day(ts):
    """'1 Aug 2025'."""
    return f'{ts.day} {ts:%b %Y}'


def and_join(items):
    items = [str(i) for i in items]
    return items[0] if len(items) == 1 else ', '.join(items[:-1]) + ' and ' + items[-1]


def months_label(first, last):
    """'January to April 2022' (or 'November 2021 to February 2022') for two monthly Periods."""
    return (f"{first.strftime('%B')} to {last.strftime('%B %Y')}" if first.year == last.year
            else f"{first.strftime('%B %Y')} to {last.strftime('%B %Y')}")


def wrap_even(text, width):
    """text in lines of at most width characters: as few lines as textwrap gives, as even in length as they allow."""
    lines = textwrap.wrap(text, width)
    for w in range(-(-len(text) // max(len(lines), 1)), width):
        even = textwrap.wrap(text, w)
        if len(even) == len(lines):
            return even
    return lines


def against(x, ref, alike='about in line with'):
    """How ratio x reads against ratio ref: alike when within ALIKE of it, else 'more than' or 'less than'."""
    return alike if abs(x / ref - 1) <= ALIKE else ('more than' if x > ref else 'less than')


def timestamp(value):
    """A case-export date-time as the case table reads it (to the second); NaT when blank."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return pd.NaT
    return (pd.to_datetime(value) if isinstance(value, str) else pd.Timestamp(value)).floor('s')


def same_times(a, b):
    a, b = pd.to_datetime(a), pd.to_datetime(b)
    return int(((a == b) | (a.isna() & b.isna())).sum())


def note_text(value):
    """A case note as written: cleaned, line breaks as LF, the characters XML cannot hold removed, cut at TEXT_CAP."""
    v = common.clean(value)
    if v is None:
        return None
    v = ILLEGAL_CHARACTERS_RE.sub('', v.replace('\r\n', '\n').replace('\r', '\n'))
    v = XML_INVALID.sub('', v)[:TEXT_CAP]
    return v or None


def placeholder(text):
    """The pseudonymous copy's stand-in for a note: the same length, every character but whitespace -> 'x'."""
    return ''.join(c if c.isspace() else 'x' for c in text) if isinstance(text, str) else None


# ----------------------------------------------------------------------------------------------------------------
# Data: Part A's machines and tickets, and the GROUP tickets with their real identifiers and notes
# ----------------------------------------------------------------------------------------------------------------
def load(check):
    """Part A's frames as followups.main() and part_a() build them; the GROUP tickets with real and pseudonymous
    identifiers and the case notes (in memory only); and what the privacy checks need."""
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
    mx['quarter'] = quarter_of(mx.install_date)
    mx['age_band'] = mx.age_band.astype(str)
    mx['account'] = mx.serial.map(dict(zip(eq.serial, eq.account)))   # the account on IPA's list
    by = mx.set_index('serial')
    for c in ('serial_id', 'customer', 'account', 'service_plan', 'model', 'install_date', 'install_year', 'cohort',
              'quarter', 'age_group', 'age_band', 'in_support', 'comparison'):
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

    # The case notes (IPA's own records), by case number, and their same-length placeholders.
    found, changed = {}, 0
    for f, col in zip(NOTES, ('reported', 'resolution')):
        cleaned = e.case_number.map(rx[f].map(common.clean))
        e[col] = e.case_number.map(rx[f].map(note_text))
        e[f'{col}_x'] = e[col].map(placeholder)
        found[f] = int(e[col].notna().sum())
        changed += int((cleaned.notna() & (cleaned.astype(object) != e[col].astype(object))).sum())
    check('case notes read from each listed case\'s own row of the export',
          bool(e.case_number.isin(rx.index).all()),
          ', '.join(f'{f} {n:,}' for f, n in found.items()) + f' of {len(e):,} cases; {changed} changed (characters '
          f'XML cannot hold, or over {TEXT_CAP:,} characters)')

    e['age_at_ticket'] = ((e.ts - e.install_date).dt.days / 365.25).round(1)
    e['machine_group'] = e.serial.map(e.serial.value_counts())
    e['machine_focus'] = e.serial.map(e[e.ctype == FOCUS].serial.value_counts()).fillna(0).astype(int)
    e['v2'] = np.where(e.model.isin(CORE_MODELS), 'Yes', 'No')
    e['core'] = (e.ctype.eq(FOCUS) & e.subcategory.eq(CORE_SUB) & e.model.isin(CORE_MODELS)
                 & e.cohort.eq(FOCUS_COHORT) & e.age_group.eq(U4))
    e['spike'] = e.ctype.eq(SPIKE[0]) & e.age_group.eq(U4) & e.ts.dt.to_period('M').eq(SPIKE_MONTH)
    e['core_yn'], e['spike_yn'] = np.where(e.core, 'Yes', 'No'), np.where(e.spike, 'Yes', 'No')
    counts = e.category.fillna('').value_counts()
    if FOCUS not in counts or FOCUS not in CATEGORIES:
        fail(f'FOCUS ({FOCUS}) is not a Category of the {GROUP} tickets or not in CATEGORIES')
    cat_order = [FOCUS] + sorted((c for c in counts.index if c not in (FOCUS, '')), key=lambda c: (-counts[c], c))
    rank = {c: i for i, c in enumerate(cat_order + [''])}
    cohort_rank = {c: i for i, c in enumerate([BEFORE] + COHORTS + [AFTER])}
    e = e.assign(_c=e.category.fillna('').map(rank), _a=e.age_group.map({U4: 0, O4: 1}),
                 _k=e.cohort.map(cohort_rank))
    e = e.sort_values(['_c', '_a', '_k', 'model', 'ts', 'case_id'], kind='mergesort').reset_index(drop=True)
    e = e.join(focus_history(e))

    def strings(f, minimum=0):
        return {v for v in raw[f].map(common.clean).dropna().astype(str) if len(v) >= minimum}
    notes = set().union(*(strings(f, LONG) for f in NOTES))
    admin = strings('Administrative Notes', LONG)
    private = {'maps': maps, 'dispatch': set(e.dispatch.dropna().astype(str)),
               'notes': notes | {note_text(v) for v in notes},                # every note of 40+ characters
               'admin': admin | {note_text(v) for v in admin}, 'owners': strings('Case Owner')}
    info = {'n_monitoring': int(((tp.cgroup == GROUP) & tp.monitoring).sum()), 'notes_changed': changed}
    check.stop_if_failed('identifier')
    return mx, tp, e, support, cat_order, info, private


def focus_history(e):
    """Each FOCUS ticket's place among its machine's FOCUS tickets of the year: its number, the days since the
    previous one and to the next, and whether the next opens within each of REPEAT_DAYS."""
    f = e[e.ctype == FOCUS].sort_values(['serial', 'ts', 'case_id'], kind='mergesort')
    ts = f.groupby('serial', sort=False).ts
    out = pd.DataFrame({'focus_k': (ts.cumcount() + 1).astype('Int64'),
                        'focus_prev': (f.ts - ts.shift(1)).dt.total_seconds() / 86400,
                        'focus_next': (ts.shift(-1) - f.ts).dt.total_seconds() / 86400}, index=f.index)
    for d in REPEAT_DAYS:
        out[f'within_{d}'] = np.where(out.focus_next <= d, 'Yes', 'No')
    return out


def by_machine(frame, real):
    """FOCUS tickets in the order of 'Start here': model (ignoring case, as Excel sorts), install date, serial number,
    opening (the copy's own identifiers, so that each copy reads sorted)."""
    serial, case = ('serial', 'case_number') if real else ('serial_id', 'case_id')
    keys = ['_m', 'install_date', serial, 'ts', case]
    return (frame.assign(_m=frame.model.str.casefold()).sort_values(keys, kind='mergesort').drop(columns='_m')
            .reset_index(drop=True))


def machines_frame(e, tp):
    """One row per machine with a GROUP ticket: its tickets by Category, its FOCUS dates; most FOCUS tickets first."""
    g = e.groupby('serial')
    mf = g[['serial_id', 'account', 'customer', 'service_plan', 'model', 'install_date', 'quarter', 'cohort',
            'age_group', 'comparison']].first()
    mf['n_group'] = g.size()
    for c in CATEGORIES:
        mf[f'n:{c}'] = e[e.ctype == c].groupby('serial').size().reindex(mf.index, fill_value=0)
    mf['n_other'] = mf.n_group - mf[[f'n:{c}' for c in CATEGORIES]].sum(axis=1)
    focus = e[e.ctype == FOCUS].groupby('serial')
    mf['n_core_sub'] = e[(e.ctype == FOCUS) & e.subcategory.eq(CORE_SUB)].groupby('serial').size() \
        .reindex(mf.index, fill_value=0)
    mf['first_focus'] = focus.ts.min().dt.normalize().reindex(mf.index)
    mf['last_focus'] = focus.ts.max().dt.normalize().reindex(mf.index)
    mf['core_machine'] = np.where(mf.index.isin(set(e.serial[e.core])), 'Yes', 'No')
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


def within_model(frame, models, M, sup):
    """Slide 4b's method: under-4 tickets on the comparison models, the tickets expected over the same machine-months
    at each model's own 4+ rate, and the extra (tickets - expected)."""
    T = by_model_age(frame, models)
    n = float(T.loc[sup, U4].sum())
    expected = float((M.loc[sup, U4] * T.loc[sup, O4] / M.loc[sup, O4]).sum())
    return n, expected, n - expected


def mh_ratio(frame, models, M, sup):
    """The follow-up's within-model rate ratio ('times the same models' 4+ rates'; followups.mh_rate with the
    comparison models as strata): each model's young machines' rate against its own 4+ machines' rate, pooled."""
    T = by_model_age(frame, models)
    return float(F.mh_rate(T.loc[sup, [U4]].to_numpy(), T.loc[sup, [O4]].to_numpy(), M.loc[sup, U4].to_numpy(),
                           M.loc[sup, O4].to_numpy())[0])


def summary(mx, tp, e, support, cat_order, check):
    """The Summary's eight tables as DataFrames, and the Read me's other numbers, each checked against
    verification/outputs/followups/ where the follow-up has them."""
    rates = pd.read_csv(RESULTS / 'ag_type_rates.csv')
    adjusted = pd.read_csv(RESULTS / 'ag_type_adjusted.csv')
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

    # The request types' crude ratios (slide 4a, left) and all tickets within model, for the Read me.
    rows = []
    for name in F.PRIMARY:
        x = tp[tp.group == name]
        u, o = int(x.age_group.eq(U4).sum()), int(x.age_group.eq(O4).sum())
        csv = rates[(rates.level == 'group') & (rates.type == name)].iloc[0]
        rows.append({'type': name, 'u4': u, 'o4': o, 'ratio': (u / my) / (o / mo), 'lo': csv.rate_ratio_lo,
                     'want': [csv.under4_tickets, csv.plus4_tickets, csv.rate_ratio]})
    types = pd.DataFrame(rows)
    all_ratio = (pop.iat[2, 0] / my) / (pop.iat[2, 1] / mo)
    all_within = within_model(tp, models, M, sup)
    dec_all = decomp[decomp.level == 'all'].iloc[0]
    check('tickets and crude ratios by request type, all tickets within model = ag_type_rates.csv, '
          'ag_decomposition.csv',
          all(close([r.u4, r.o4, r.ratio], r.want) for r in types.itertuples())
          and close(all_ratio, rates[rates.level == 'all'].rate_ratio.iloc[0])
          and close(all_within[2], dec_all.within_model_age_tickets),
          f'{len(types)} types, {int((types.lo > 1).sum())} with the 95% interval above 1; all tickets '
          f'{all_ratio:.2f} times, within model {all_within[0]:,.0f} against {all_within[1]:,.1f} expected')
    out['types'], out['all_ratio'], out['all_within'] = types.drop(columns='want'), all_ratio, all_within

    # The within-model rate ratios the Read me gives (all tickets, GROUP, FOCUS and the rest of GROUP).
    foc = e.ctype.eq(FOCUS)
    mh = {'all': mh_ratio(tp, models, M, sup), 'group': mh_ratio(e, models, M, sup),
          'focus': mh_ratio(e[foc], models, M, sup), 'rest': mh_ratio(e[~foc], models, M, sup)}
    adj = adjusted[adjusted.variant == 'primary']
    want = [adj[(adj.level == 'group') & (adj.type == GROUP)].rate_ratio_mh,
            adj[(adj.level == 'category') & (adj.group == GROUP) & (adj.type == FOCUS)].rate_ratio_mh]
    check(f'within-model rate ratios of {GROUP} and {FOCUS} (Mantel-Haenszel) = ag_type_adjusted.csv',
          all(len(w) == 1 for w in want) and close([mh['group'], mh['focus']], [w.iloc[0] for w in want]),
          f"{GROUP} {mh['group']:.2f}, {FOCUS} {mh['focus']:.2f}; all tickets {mh['all']:.2f}, {GROUP} without "
          f"{FOCUS} {mh['rest']:.2f}")
    out['mh'] = mh

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
        within = within_model(e[sel], models, M, sup)[2]
        rows.append({'Category': label, 'u4': ty, 'o4': to, 'r_u4': 100 * ty / my, 'r_o4': 100 * to / mo,
                     'ratio': (ty / my) / (to / mo) if to else np.nan,
                     'lo': csv.rate_ratio_lo.iloc[0] if len(csv) else np.nan,
                     'hi': csv.rate_ratio_hi.iloc[0] if len(csv) else np.nan,
                     'expected': my * to / mo, 'extra': ty - my * to / mo,
                     'within': within,
                     'csv_row': csv, 'dec_row': dec, 'within_all': within})
    cat = pd.DataFrame(rows)
    shown = cat[cat.csv_row.map(len) > 0]
    same = all(close([r.u4, r.o4, r.ratio], r.csv_row[['under4_tickets', 'plus4_tickets', 'rate_ratio']].iloc[0])
               for r in shown.itertuples())
    check(f'{GROUP} tickets by Category x age group = ag_type_rates.csv',
          len(shown) == len(cat) - 1 and same
          and cat.u4.iloc[0] == cat.u4.iloc[1:].sum() and cat.o4.iloc[0] == cat.o4.iloc[1:].sum(),
          f'{len(shown) - 1} Categories and the group row ({cat.u4.iloc[0]:,.0f} and {cat.o4.iloc[0]:,.0f}; '
          f'{cat.u4.iloc[-1]:,.0f} and {cat.o4.iloc[-1]:,.0f} with no Category)')
    dec_rows = cat[cat.dec_row.map(len) > 0]
    same = all(close([r.extra, r.within_all], r.dec_row[['extra_tickets', 'within_model_age_tickets']].iloc[0])
               for r in dec_rows.itertuples())
    check('extra tickets, crude and within model = ag_decomposition.csv', len(dec_rows) > 0 and same,
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
          ', '.join(f'{r.cohort} {r.tickets}' for r in coh.itertuples()) + ' tickets')
    out['cohorts'] = coh
    out['cluster_csv'] = int(csv.at[FOCUS_COHORT, 'tickets'])      # slide 4d's cluster, as the follow-up has it
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

    # Table 5: each Category, then its Sub Categories (most tickets first, blank last), with slide 4b's method.
    sub = e.assign(c=e.category.fillna(NO_CATEGORY), s=e.subcategory.fillna('(blank)'))
    rows = []
    for c in cat_order + [NO_CATEGORY]:
        x = sub[sub.c == c]
        n = x.groupby(['s', 'age_group']).size().unstack().reindex(columns=AGES).fillna(0).astype(int).reset_index()
        n = n.assign(t=n[U4] + n[O4], b=n.s.eq('(blank)')).sort_values(['b', 't', 's'], ascending=[True, False, True],
                                                                       kind='mergesort')
        wm = ('n_sup', 'expected', 'extra')
        rows.append({'label': c, 'level': 'category', 'parent': c, U4: int(x.age_group.eq(U4).sum()),
                     O4: int(x.age_group.eq(O4).sum()), **dict(zip(wm, within_model(x, models, M, sup)))})
        if not n.b.all():                      # a Category whose Sub Category is always blank gets no sub rows
            rows += [{'label': lab, 'level': 'sub', 'parent': c, U4: a, O4: b,
                      **dict(zip(wm, within_model(x[x.s == lab], models, M, sup)))}
                     for lab, a, b in n[['s', U4, O4]].itertuples(index=False, name=None)]
    t5 = pd.DataFrame(rows)
    t5['r_u4'], t5['r_o4'] = 100 * t5[U4] / my, 100 * t5[O4] / mo
    tops = t5[t5.level == 'category'].set_index('label')
    subs = t5[t5.level == 'sub'].groupby('parent')[[U4, O4, 'n_sup', 'expected', 'extra']].sum()
    top = tops.reindex(subs.index)
    check('Sub Category rows add up to their Categories, the Categories to the list',
          bool((subs[[U4, O4]] == top[[U4, O4]]).all().all()) and close(subs.iloc[:, 2:], top[list(subs.columns[2:])])
          and tops[[U4, O4]].sum().tolist() == cat[['u4', 'o4']].iloc[0].tolist(),
          f'{len(t5) - len(tops)} Sub Category rows under {len(subs)} of {len(tops)} Categories; tickets, and '
          'tickets expected at the same models\' 4+ rates')
    dec_cat = decomp[(decomp.level == 'category') & (decomp.group == GROUP)].set_index('type')
    conn = t5[(t5.level == 'sub') & (t5.parent == FOCUS) & (t5.label == CORE_SUB)]
    check(f"table 5's extra within model: Categories = ag_decomposition.csv; {CORE_SUB} by the same method",
          len(dec_cat) > 0 and dec_cat.index.isin(tops.index).all() and len(conn) == 1
          and close(tops.loc[dec_cat.index, 'extra'], dec_cat.within_model_age_tickets),
          f'{len(dec_cat)} Categories; {CORE_SUB}: ' + ('missing' if len(conn) != 1 else
                                                        f'{conn.n_sup.iloc[0]:,.0f} under-4 tickets on the comparison '
                                                        f'models, {conn.expected.iloc[0]:,.1f} expected at the same '
                                                        f"models' 4+ rates, {conn.extra.iloc[0]:+,.1f}"))
    within2 = cat.set_index('Category').within_all
    check("table 5's Category rows = table 2's extra within model",
          bool(tops.index.isin(within2.index).all()) and close(tops.extra, within2.reindex(tops.index)),
          f'{len(tops)} Categories')
    out['subcategories'] = t5
    out['connector'] = conn.iloc[0] if len(conn) == 1 else None

    # Tickets by model and age group behind slide 4c.
    T = by_model_age(e, models)
    got = [T.at[r.model, r.age_group] for r in bym.itertuples()]
    check(f'{GROUP} tickets by model and age group = ag_by_model.csv',
          close(got, bym[f'tickets_{GROUP}']),
          f'{len(bym)} rows, {bym.model.nunique()} models, {int(sum(got)):,} tickets')
    allt = by_model_age(tp, models)
    out['mix'] = {'u4': T.at[MIX_MODEL, U4], 'o4': T.at[MIX_MODEL, O4], 'all_u4': allt.at[MIX_MODEL, U4],
                  'all_o4': allt.at[MIX_MODEL, O4]}

    out['quarters'] = quarter_table(mx, e, years, support, check)
    out['subsets'] = subset_table(e, out['cluster_csv'], check)
    out['connector_models'] = connector_table(e, models, M, sup, out['connector'], check)
    out['edge'] = edge_table(mx, e, pooled, check)
    out['facts'] = facts(e, out, M)
    return out


def quarter_table(mx, e, years, support, check):
    """Table 6: FOCUS and CORE_SUB tickets by install quarter on the four 2.0 models, pooled and each; machine-months
    over the year, as Part A has them. The quarters add up, per model and install year, to ag_install_year.csv."""
    fq = e[(e.ctype == FOCUS) & e.model.isin(CORE_MODELS)]
    rows = []
    for label, group in [(POOLED, CORE_MODELS)] + [(m, (m,)) for m in CORE_MODELS]:
        for q in QUARTERS:
            ms = mx[mx.model.isin(group) & mx.quarter.eq(q)]
            tq = fq[fq.model.isin(group) & fq.quarter.eq(q)]
            rows.append({'model': label, 'quarter': q, 'machines': len(ms), 'under4': int(ms.age_group.eq(U4).sum()),
                         'months': float(ms.months.sum()), 'tickets': len(tq),
                         'connector': int(tq.subcategory.eq(CORE_SUB).sum())})
    t6 = pd.DataFrame(rows)
    with np.errstate(divide='ignore', invalid='ignore'):
        t6['rate'] = 100 * t6.tickets / t6.months
        t6['rate_connector'] = 100 * t6.connector / t6.months
    cols = ['machines', 'under4', 'months', 'tickets']
    each = t6[t6.model != POOLED].assign(install_year=lambda d: d.quarter.str[:4].astype(int))
    got = each.groupby(['model', 'install_year'])[cols].sum()
    ref = years[(years.category == FOCUS) & years.model.isin(CORE_MODELS)].set_index(['model', 'install_year']) \
        .reindex(got.index)[['machines', 'under4_machines', 'months', 'tickets']].fillna(0.0)
    pool = t6[t6.model == POOLED].set_index('quarter')[cols + ['connector']]
    pool_ok = close(pool, each.groupby('quarter')[cols + ['connector']].sum().reindex(pool.index))
    check(f'{FOCUS} by install quarter, {QUARTERS[0]} to {QUARTERS[-1]}: per model and year = ag_install_year.csv',
          set(CORE_MODELS) <= set(support) and close(got.to_numpy(), ref.to_numpy()) and pool_ok,
          f'{len(got)} model-years; {POOLED}: {int(pool.machines.sum()):,} machines, {pool.months.sum():,.1f} '
          f'machine-months, {int(pool.tickets.sum())} {FOCUS} tickets, {int(pool.connector.sum())} {CORE_SUB}')
    return t6


def subset_table(e, cluster_csv, check):
    """Table 7: the subsets the Read me names, with tickets, machines and accounts, and where each sits."""
    foc, young = e.ctype.eq(FOCUS), e.age_group.eq(U4)
    coh = e.cohort.eq(FOCUS_COHORT)
    conn = foc & e.subcategory.eq(CORE_SUB)
    rows = [  # key, label, mask, where in the workbook, style
        ('u4', f'{GROUP}, {U4.lower()}', young, f"'{CASES}': Age group = {U4}", 'bold'),
        ('u4_focus', f'{FOCUS}, {U4.lower()}', young & foc, f"'{START}': every row", 'bold'),
        ('u4_conn', f'of which {CORE_SUB}', young & conn, f"'{START}': Sub Category = {CORE_SUB}", 'indent'),
        ('u4_coh', f'of which installed {FOCUS_COHORT}', young & foc & coh, f"'{START}': Install cohort = "
         f'{FOCUS_COHORT}', 'indent'),
        ('core', 'Core subset', e.core, f"'{START}': Core subset = Yes", 'bold'),
        *((f'core:{m}', m, e.core & e.model.eq(m), f"'{START}': Core subset = Yes, Model = {m}", 'indent')
          for m in CORE_MODELS),
        ('cluster', f'{FOCUS}, installed {FOCUS_COHORT}, any age (4d)', foc & coh & e.in_support,
         f"'{CASES}': Category = {FOCUS}, Install cohort = {FOCUS_COHORT}, Comparison model = Yes", 'bold'),
        ('u4_rest', f'{GROUP} other than {FOCUS}, {U4.lower()}', young & ~foc, f"'{CASES}': Age group = {U4}, Category "
         f'other than {FOCUS}', 'bold'),
        ('o4_focus', f'{FOCUS}, {O4}', ~young & foc, f"'{OLDER}': every row", 'bold'),
        ('spike', f'{SPIKE[0]}, {U4.lower()}, opened {SPIKE_MON}', e.spike, f"'{CASES}': {SPIKE_LABEL} = Yes",
         'bold'),
    ]
    masks = {key: mask for key, _, mask, _, _ in rows}
    t7 = pd.DataFrame([{'key': key, 'label': label, 'tickets': int(mask.sum()),
                        'machines': int(e.serial[mask].nunique()), 'accounts': int(e.customer[mask].nunique()),
                        'where': where, 'style': style} for key, label, mask, where, style in rows]).set_index('key')
    names_ok = all(e.customer[m].nunique() == e.account[m].nunique() for m in masks.values())
    nests = [('core', 'u4_conn'), ('u4_conn', 'u4_focus'), ('u4_focus', 'u4'), ('core', 'u4_coh'),
             ('u4_coh', 'u4_focus'), ('u4_coh', 'cluster'), ('spike', 'u4_rest'), ('u4_rest', 'u4')]
    nested = sum(not (masks[a] & ~masks[b]).any() for a, b in nests)
    overlap = (masks['u4_focus'] & masks['u4_rest']).any()
    parts = (masks['u4_focus'] | masks['u4_rest']).equals(masks['u4']) and not overlap
    by_model = sum(t7.at[f'core:{m}', 'tickets'] for m in CORE_MODELS) == t7.at['core', 'tickets']
    check('subsets nest as stated; slide 4d\'s cluster = ag_install_pooled.csv',
          nested == len(nests) and parts and by_model and names_ok and t7.at['cluster', 'tickets'] == cluster_csv,
          f'{nested} of {len(nests)} nestings (core within under-4 {CORE_SUB}, within under-4 {FOCUS}, within '
          f'under-4 {GROUP}, ...); core {t7.at["core", "tickets"]} tickets, {t7.at["core", "machines"]} machines, '
          f'{t7.at["core", "accounts"]} accounts; cluster {t7.at["cluster", "tickets"]} ({cluster_csv} expected); '
          f'{SPIKE_LABEL} {t7.at["spike", "tickets"]}')
    return t7


def connector_table(e, models, M, sup, conn, check):
    """Table 8: CORE_SUB tickets within model on each comparison model (slide 4b's method): under-4 and 4+ tickets and
    machine-months, the model's 4+ rate, the under-4 tickets expected at it and the extra; most extra first, under a
    first row for the comparison models together, which is table 5's CORE_SUB row."""
    T = by_model_age(e[e.ctype.eq(FOCUS) & e.subcategory.eq(CORE_SUB)], models).loc[sup]
    Ms = M.loc[sup]
    t8 = pd.DataFrame({'model': T.index, 'u4': T[U4].to_numpy(), 'm_u4': Ms[U4].to_numpy(), 'o4': T[O4].to_numpy(),
                       'm_o4': Ms[O4].to_numpy()})
    t8['r_o4'] = 100 * t8.o4 / t8.m_o4
    t8['expected'] = t8.m_u4 * t8.o4 / t8.m_o4
    t8['extra'] = t8.u4 - t8.expected
    t8 = t8.sort_values(['extra', 'model'], ascending=[False, True], kind='mergesort')
    total = t8[['u4', 'm_u4', 'o4', 'm_o4', 'expected', 'extra']].sum()
    v2 = t8[t8.model.isin(CORE_MODELS)]
    check(f"table 8: {CORE_SUB} within model, model by model, adds up to table 5's row",
          conn is not None and close(total[['u4', 'expected', 'extra']], [conn.n_sup, conn.expected, conn.extra]),
          f"{len(t8)} comparison models: {total.u4:,.0f} under-4 tickets, {total.expected:,.1f} expected at the "
          f"models' own 4+ rates, {total.extra:+,.1f}; on the {V2} {v2.extra.sum():+,.1f}")
    first = pd.DataFrame([{'model': f'All {len(t8)} comparison models', **total.to_dict(), 'r_o4': np.nan}])
    return pd.concat([first, t8], ignore_index=True)


def edge_table(mx, e, pooled, check):
    """The Read me's step: FOCUS tickets (any age) on the comparison models' machines installed in each EDGE window,
    with the machines (and how many are under 4) and their machine-months; checked through the install months of the
    windows' years, which add up to ag_install_pooled.csv's install-year rows."""
    sm, fe = mx[mx.in_support], e[e.ctype.eq(FOCUS) & e.in_support]
    sm_month, fe_month = sm.install_date.dt.to_period('M'), fe.install_date.dt.to_period('M')

    def tally(first, last):
        ms = sm[(sm_month >= first) & (sm_month <= last)]
        return {'machines': len(ms), 'under4': int(ms.age_group.eq(U4).sum()), 'months': float(ms.months.sum()),
                'tickets': int(((fe_month >= first) & (fe_month <= last)).sum())}

    w = pd.DataFrame([{'label': months_label(a, b), **tally(a, b)} for a, b in EDGE_MONTHS])
    w['rate'] = 100 * w.tickets / w.months
    ref = pooled[(pooled.category == FOCUS) & (pooled.unit == 'year')].set_index('install')
    years = sorted({p.year for pair in EDGE_MONTHS for p in pair})
    cols = ['machines', 'months', 'tickets']
    got = [pd.DataFrame([tally(p, p) for p in pd.period_range(f'{y}-01', f'{y}-12', freq='M')])[cols].sum()
           for y in years]
    want = [ref.loc[str(y), cols] if str(y) in ref.index else pd.Series(np.nan, index=cols) for y in years]
    apart = all(b < c for (_, b), (c, _) in zip(EDGE_MONTHS, EDGE_MONTHS[1:]))
    check(f'{FOCUS} by install month, comparison models: each year = ag_install_pooled.csv; a step between the windows',
          close([g.to_numpy(float) for g in got], [x.to_numpy(float) for x in want]) and apart
          and w.rate.iloc[-1] > w.rate.iloc[0],
          '; '.join(f'{y}: {g.machines:,.0f} machines, {g.months:,.1f} machine-months, {g.tickets:,.0f} tickets'
                    for y, g in zip(years, got)) + ' by month; '
          + '; '.join(f'{r.label}: {r.tickets} tickets over {r.months:,.1f} machine-months ({r.rate:.2f} per 100; '
                      f'{r.machines} machines, {r.under4} under 4)' for r in w.itertuples()))
    return w


def facts(e, s, M):
    """The Read me's numbers beyond the Summary's tables."""
    foc, young = e.ctype.eq(FOCUS), e.age_group.eq(U4)
    start = e[foc & young]
    many = start[start.machine_focus >= MANY]
    rest_young, rest_old = int((young & ~foc).sum()), int((~young & ~foc).sum())
    my, mo = M[U4].sum(), M[O4].sum()
    spike_months = e[e.ctype.eq(SPIKE[0]) & young].ts.dt.to_period('M').value_counts()
    period_months = len(pd.period_range(PERIOD_START, LAST_DAY, freq='M'))
    hv = s['halves'].set_index(['category', 'half'])
    return {
        'u4_v2': int((foc & young & e.model.isin(CORE_MODELS)).sum()),
        'many_machines': int(many.serial.nunique()), 'many_tickets': len(many),
        **{f'within_{d}': int(start[f'within_{d}'].eq('Yes').sum()) for d in REPEAT_DAYS},
        'rest_young': rest_young, 'rest_old': rest_old,
        'rest_crude': (rest_young / my) / (rest_old / mo),
        'spike_max': int(spike_months.get(SPIKE_MONTH, 0)) == int(spike_months.max()),
        'spike_average': len(e[e.ctype.eq(SPIKE[0]) & young]) / period_months,
        'spike_support': int((e.spike & e.in_support).sum()),
        'spike_h1': hv.at[(SPIKE[0], 'H1'), 'tickets'] if (SPIKE[0], 'H1') in hv.index else np.nan,
        'spike_in_h1': bool((e.ts[e.spike] < F.SPLIT).all()),
        'negative_age': int((e.age_at_ticket < 0).sum()),
        'notes': int(e.reported.notna().sum() + e.resolution.notna().sum()),
        'machines': int(e.serial.nunique()),
    }


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


def put(ws, row, col, value):
    """Write a value; text stays text even if it starts with '=' (openpyxl would take it for a formula)."""
    cell = ws.cell(row, col, value)
    if isinstance(value, str) and cell.data_type == 'f':
        cell.data_type = 's'
    return cell


def field_values(frame, field, real):
    if isinstance(field, tuple):
        field = field[0] if real else field[1]
    return [None] * len(frame) if field is None else [plain(v) for v in frame[field].tolist()]


def list_sheet(wb, title, frame, columns, real):
    """A list sheet: header row (bold, filled; the IPA columns in a fill of their own), one row per frame row,
    frozen panes, a filter on every column. A column is at least as wide as its header's longest word, so headers
    wrap between words; short codes (CENTERED) are centred."""
    ws = wb.create_sheet(title)
    for j, (head, _, width, _) in enumerate(columns, 1):
        cell = ws.cell(1, j, head)
        cell.font, cell.alignment = BOLD, HEAD_CENTER if head in CENTERED else HEAD_ALIGN
        cell.fill = IPA_FILL if head in IPA_HEADS else HEAD_FILL
        ws.column_dimensions[get_column_letter(j)].width = max(width, 1.1 * max(map(len, head.split())) + 0.5)
    for j, (head, field, _, fmt) in enumerate(columns, 1):
        for i, v in enumerate(field_values(frame, field, real), 2):
            cell = put(ws, i, j, v)
            cell.font = FONT
            if fmt:
                cell.number_format = fmt
            if head in CENTERED:
                cell.alignment = CENTER
    ws.freeze_panes = 'B2'
    ws.auto_filter.ref = ws.print_area = f'A1:{get_column_letter(len(columns))}{len(frame) + 1}'  # print: notes
    ws.print_options.gridLines = True                                                              # stop at the edge
    print_setup(ws, title_rows='1:1', title_cols='A:A', fit=False)
    return ws


def print_setup(ws, title_rows=None, title_cols=None, fit=True):
    """Landscape; fit: one page wide (Read me, Summary), else at LIST_SCALE, across then down, with the header row
    and the first column on every page (the list sheets, too wide for one legible page)."""
    ws.page_setup.orientation = 'landscape'
    if fit:
        ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
    else:
        ws.page_setup.scale, ws.page_setup.pageOrder = LIST_SCALE, 'overThenDown'
    if title_rows:
        ws.print_title_rows = title_rows
    if title_cols:
        ws.print_title_cols = title_cols


def readme_rows(mx, tp, e, support, cat_order, info, s, real):
    """The Read me sheet: (kind, label, text) rows, every number taken from the builder's own tables."""
    cat = s['categories'].set_index('Category')
    g, fc = cat.loc[GROUP], cat.loc[FOCUS]
    k, t7, types, conn = s['facts'], s['subsets'], s['types'], s['connector']
    coh = s['cohorts'].set_index('cohort')
    hv = s['halves']
    mix = s['mix']
    pop = s['population']
    codes = ', '.join(sorted(e.trouble_code.dropna().unique()))
    newest, previous = COHORTS[-1], COHORTS[COHORTS.index(FOCUS_COHORT) - 1]
    h = {c: hv[hv.category == c].set_index('half') for c in hv.category.unique()}
    first, *others = h
    halves = (f"young machines' {first} tickets went from {h[first].at['H1', 'tickets']:.0f} in the first half of the "
              f"year to {h[first].at['H2', 'tickets']:.0f} in the second, and their gap to older machines of the same "
              f"models from {h[first].at['H1', 'gap']:.2f} to {h[first].at['H2', 'gap']:.2f} per 100 machine-months"
              + ''.join(f"; {c}: {h[c].at['H1', 'tickets']:.0f} to {h[c].at['H2', 'tickets']:.0f} tickets, gap "
                        f"{h[c].at['H1', 'gap']:.2f} to {h[c].at['H2', 'gap']:.2f}" for c in others))
    years = f'{FOCUS_YEARS[0]} or {FOCUS_YEARS[1]}' if FOCUS_YEARS[1] == FOCUS_YEARS[0] + 1 else FOCUS_COHORT
    young_words, old_words = f'machines {U4.lower()}', f'machines {O4}'

    # What the list shows.
    big = types.assign(n=types.u4 + types.o4).sort_values('n', ascending=False, kind='mergesort').head(4)
    n_types, above, clear = len(types), int((types.ratio > 1).sum()), int((types.lo > 1).sum())
    every = ('every' if clear == n_types else 'nearly every' if above >= n_types - 1
             else 'most' if above > n_types / 2 else 'only some')
    higher = f'all {n_types}' if above == n_types else f'{above} of the {n_types}'
    shown = [c for c in cat_order if c != FOCUS and cat.at[c, 'u4'] >= F.MIN_SHOWN_TICKETS
             and cat.at[c, 'o4'] >= F.MIN_SHOWN_TICKETS]
    mh, w0, w1 = s['mh'], s['edge'].iloc[0], s['edge'].iloc[-1]
    core = t7.loc['core']
    scope = '' if conn.n_sup == conn[U4] else ' on the comparison models'
    later = f'all {w1.machines:,}' if w1.under4 == w1.machines else f'{w1.under4:,} of the {w1.machines:,}'
    shows = [
        f'Per installed machine-month, {young_words} have more tickets of {every} request type than {old_words}: the '
        f'rate is higher for {higher} types, and clearly so ({CI} interval above 1) for {clear}. The '
        f'{NUMBER_WORDS[len(big)]} types with the most tickets ({and_join(big.type)}) run {big.ratio.min():.2f} to '
        f"{big.ratio.max():.2f} times the older machines' rate, and all unplanned tickets {s['all_ratio']:.2f} times. "
        f'{GROUP}, at {g.ratio:.2f} times ({g.r_u4:.2f} against {g.r_o4:.2f} per 100 machine-months), rises '
        f"{against(g.ratio, s['all_ratio'], 'about as much as')} all tickets.",
        f'{FOCUS} is the Category that stands out: {fc.u4:,.0f} tickets on {young_words} against {fc.o4:,.0f} on '
        f'{old_words}, {fc.r_u4:.2f} against {fc.r_o4:.2f} per 100 machine-months ({fc.ratio:.2f} times; {CI} interval '
        f'{fc.lo:.2f} to {fc.hi:.2f}). The other {GROUP} Categories with {F.MIN_SHOWN_TICKETS} or more tickets in '
        f"each age group run {cat.loc[shown, 'ratio'].min():.2f} to {cat.loc[shown, 'ratio'].max():.2f} times.",
        f"{conn[U4]:,} of the {fc.u4:,.0f} ({conn[U4] / fc.u4:.0%}) are Sub Category '{CORE_SUB}', against "
        f'{conn[O4]:,} of the {fc.o4:,.0f} ({conn[O4] / fc.o4:.0%}) on {old_words}.',
        f"{k['u4_v2']:,} of the {fc.u4:,.0f} are on the {V2} ({and_join(CORE_MODELS)}) and "
        f"{t7.at['u4_coh', 'tickets']:,} on machines installed in {years}. {core.tickets:,} are {CORE_SUB} tickets on "
        f'machines of the {V2} installed in {years}: the core subset, on {core.machines:,} machines at '
        f'{core.accounts:,} accounts.',
        f'On the {len(support)} comparison models, machines installed {w0.label} had {w0.tickets:,} {FOCUS} tickets '
        f'over {w0.months:,.0f} machine-months ({w0.rate:.2f} per 100) and those installed {w1.label} had '
        f'{w1.tickets:,} over {w1.months:,.0f} ({w1.rate:.2f} per 100): machines installed a few months apart are '
        f'nearly the same age ({U4.lower()}: {w0.under4:,} of the {w0.machines:,} earlier machines and {later} later '
        'ones), so a step between them points to a change in production, parts or installation around then rather '
        'than to ageing (descriptive: the edge was found by looking at the data).',
        f"The rest of {GROUP}, without {FOCUS} ({k['rest_young']:,} tickets on {young_words} and {k['rest_old']:,} on "
        f"{old_words}), rises {against(k['rest_crude'], s['all_ratio'])} all tickets on the crude view "
        f"({k['rest_crude']:.2f} times the older machines' rate, against all tickets' {s['all_ratio']:.2f}) and "
        f"{against(mh['rest'], mh['all'])} them within model ({mh['rest']:.2f} times the same models' 4+ rates, "
        f"against all tickets' {mh['all']:.2f}); {FOCUS} runs {fc.ratio:.2f} and {mh['focus']:.2f} times.",
        "Single tickets cannot be labelled 'extra': the excess is a difference between rates, not a set of cases. At "
        f"the same models' 4+ rates about {conn.expected:,.0f} of the {conn.n_sup:,.0f} {CORE_SUB} tickets on "
        f'{young_words}{scope} would be expected anyway, so about {conn.extra:,.0f} are extra (Summary table 8 gives '
        f'them model by model); but each is a real case, and any of them could be among the {conn.expected:,.0f}. '
        'So the list shows every case, on young and older machines alike.',
    ]
    by_model = ', '.join(f"{m} {t7.at[f'core:{m}', 'tickets']}" for m in CORE_MODELS)
    month = SPIKE_MONTH_NAME
    spike = t7.at['spike', 'tickets']
    sh = h.get(SPIKE[0])                       # slide 4e's halves for SPIKE's Category (ag_halves.csv's numbers)
    closed = (sh is not None and k['spike_in_h1'] and sh.at['H2', 'gap'] < sh.at['H1', 'gap']
              and sh.at['H2', 'same'] > sh.at['H1', 'same'])
    them = 'them' if k['spike_support'] == spike else f"those {k['spike_support']}"
    part = (f", which closed from {sh.at['H1', 'gap']:.2f} to {sh.at['H2', 'gap']:.2f} per 100 machine-months. The "
            f"cluster explains only part of that: without {them} the first half's gap would have been "
            f"{sh.at['H1', 'gap'] - 100 * k['spike_support'] / sh.at['H1', 'months']:.2f}, and the gap also closed "
            f'because older machines of the same models logged more {SPIKE[0]} tickets in the second half (their '
            f"rate went from {sh.at['H1', 'same']:.2f} to {sh.at['H2', 'same']:.2f} per 100)" if closed else '')
    rows = [
        ('notice', None, NOTICE_REAL if real else NOTICE_PSEUDO),
        ('title', None, f'IPA {GROUP} service cases, {day(PERIOD_START)} to {day(LAST_DAY)}'),
        ('item', 'Built', f'{day(pd.Timestamp(date.today()))} by viz/deliverables/build_electronics_cases.py, from '
                          f"IPA's case export ({PERIOD_START:%b %Y} to {LAST_DAY:%b %Y}) and installed-base list "
                          f'({day(LIST_DATE)}), with the selection of verification/followups.py (Part A).'),
        ('blank', None, None),
        ('heading', None, 'What this is'),
        ('item', None, f'Every unplanned service case of request type {GROUP} on the machines behind slides 4a to 4e '
                       f'of the update deck: {len(e):,} cases, {g.u4:,.0f} on {young_words} years old and '
                       f"{g.o4:,.0f} on {old_words}. One row per case, with IPA's case number, the machine, its age "
                       "and IPA's own case notes, so that IPA's engineers can find the cases behind the finding and "
                       'work through them.'),
        ('item', None, f"Sheets: '{START}' (the {FOCUS} tickets on {young_words}, where the finding is), '{OLDER}' "
                       f"(the same on {old_words}, to compare), '{CASES}' (all {len(e):,} cases), '{MACHINES}' (one "
                       f"row per machine) and '{SUMMARY}' (the slides' numbers recomputed from the list, and the "
                       'tables named below).'),
        ('blank', None, None),
        ('heading', None, 'What the list shows'),
        *(('item', None, text) for text in shows),
        ('blank', None, None),
        ('heading', None, 'Where to start'),
        ('item', START, f"The {len(e[e.ctype.eq(FOCUS) & e.age_group.eq(U4)]):,} {FOCUS} tickets on {young_words}, "
                        "sorted by model, install date (oldest first) and serial number, so that each machine's "
                        f"tickets sit together in order of opening; each row carries the machine's {FOCUS} history "
                        'in the year.'),
        ('item', 'Core subset = Yes', f'Filter it for the {core.tickets:,} core tickets ({core.machines:,} machines, '
                                      f'{core.accounts:,} accounts): {by_model}.'),
        ('item', 'Trouble Resolution', 'Read it for which connector or cable it was, whether it was reseated or '
                                       'replaced, and the part used; Trouble Reported has what was reported.'),
        ('item', 'Repeats', f"In '{START}', {k['many_machines']:,} {young_words} had {MANY} or more {FOCUS} tickets "
                            f"in the year ({k['many_tickets']:,} tickets; filter Machine's {FOCUS} tickets). Of its "
                            f'{fc.u4:,.0f} tickets, '
                            + ' and '.join(f"{k[f'within_{d}']:,} were followed by another on the same machine "
                                           f'within {d} days' if i == 0 else f"{k[f'within_{d}']:,} within {d}"
                                           for i, d in enumerate(REPEAT_DAYS))
                            + f" (Another within {' / '.join(map(str, REPEAT_DAYS))} days = Yes)."),
        ('item', OLDER, f"The {t7.at['o4_focus', 'tickets']:,} {FOCUS} tickets on {old_words}, in the same layout, to "
                        f'compare: {conn[O4]:,} of them are {CORE_SUB}.'),
        ('item', MACHINES, f"One row per machine with an {GROUP} ticket ({k['machines']:,}); filter Core machine = Yes "
                           f'for the {core.machines:,} machines with a core ticket.'),
        ('item', SPIKE_LABEL, f'A separate lead, apart from {FOCUS}: {spike:,} {SPIKE[0]} tickets on {young_words} '
                              f'opened in {month}' + (', the most of any month' if k['spike_max'] else '')
                              + f" (the year's monthly average is {k['spike_average']:.0f})"
                              + (f"; {'all' if k['spike_support'] == spike else k['spike_support']} of them are among "
                                 f"the {k['spike_h1']:.0f} first-half tickets behind slide 4e's {SPIKE[0]} gap{part}"
                                 if k['spike_in_h1'] else '')
                              + f". In '{CASES}', filter {SPIKE_LABEL} = Yes."),
        ('blank', None, None),
        ('heading', None, 'What would settle it'),
        ('item', None, "IPA's change records, by model: the dates of touchscreen, connector, cable or harness "
                       'revisions, of supplier or installation-kit changes, and of firmware changes. Summary table 6 '
                       f'gives {FOCUS} and {CORE_SUB} tickets per 100 machine-months by install quarter, '
                       f'{QUARTERS[0]} to {QUARTERS[-1]}, on the {V2}, to line up against those dates.'),
        ('item', None, "Within the year's data a machine's install date and its age move together (slide 4d), so the "
                       'rates alone cannot tell a change in production or installation from a failure that comes '
                       f'with age (the step between machines installed {w0.label} and {w1.label}, above, only '
                       'points to when to look); the dates of the changes can.'),
        ('item', None, f"The {NUMBER_WORDS[len(IPA_HEADS)]} columns headed 'IPA:' at the right of '{START}' are "
                       "for IPA's engineers to record, case by case, the root cause, the part or revision, the fix or "
                       'field campaign and the fix date.'),
        ('blank', None, None),
        ('heading', None, 'How the counts tie to slides 4a to 4e'),
        ('item', 'Filters', 'Each list sheet has a filter arrow on every column heading (Data > Filter in Excel): '
                            'pick values in one or more columns to show only those rows; Data > Clear shows every '
                            'row again.'),
        ('item', 'Slide 4a', f'{GROUP}: {g.u4:,.0f} tickets on {young_words} over {pop.iat[1, 0]:,.0f} machine-months '
                             f'({g.r_u4:.2f} per 100) and {g.o4:,.0f} on {old_words} over {pop.iat[1, 1]:,.0f} '
                             f'({g.r_o4:.2f}): {g.ratio:.2f} times ({CI} interval {g.lo:.2f} to {g.hi:.2f}). '
                             f"'{CASES}', Age group = {U4} or {O4}; Summary tables 1 and 2."),
        ('item', 'Slide 4b', f"Against the same models' 4+ rates, {young_words} have {g.within:+,.0f} {GROUP} "
                             f'tickets; {FOCUS} {fc.within:+,.0f}, of which {CORE_SUB} {conn.extra:+,.0f}. '
                             f"'{START}' holds the {FOCUS} tickets; Summary tables 2, 5 and 8."),
        ('item', 'Slide 4c', f"On {MIX_MODEL}, {GROUP} is {mix['u4'] / mix['all_u4']:.0%} of young machines' tickets "
                             f"({mix['u4']:,.0f} of {mix['all_u4']:,.0f}) against {mix['o4'] / mix['all_o4']:.0%} on "
                             f"older ones ({mix['o4']:,.0f} of {mix['all_o4']:,.0f}). '{CASES}', Model = {MIX_MODEL}."),
        ('item', 'Slide 4d', f'{FOCUS} tickets on the {len(support)} comparison models, by install cohort: '
                             + ', '.join(f'{coh.at[c, "tickets"]:,} ({c})' for c in COHORTS)
                             + f'. Per 100 machine-months, {FOCUS_COHORT} installs run '
                             f'{coh.at[FOCUS_COHORT, "rate"]:.2f} against {coh.at[newest, "rate"]:.2f} for {newest} '
                             f"and {coh.at[previous, 'rate']:.2f} for {previous}. The {t7.at['cluster', 'tickets']:,} "
                             f"of {FOCUS_COHORT}: '{CASES}', Category = {FOCUS}, Install cohort = {FOCUS_COHORT}, "
                             f"Comparison model = Yes ({t7.at['u4_coh', 'tickets']:,} of them on {young_words}, in "
                             f"'{START}'). Summary table 3."),
        ('item', 'Slide 4e', f"On the comparison models, {halves}. Filter Half = H1 or H2; Summary table 4."),
        ('blank', None, None),
        ('heading', None, 'Definitions'),
        ('item', 'Unplanned ticket', f"A case in IPA's case export opened {day(PERIOD_START)} to {day(LAST_DAY)}, "
                                     'except planned work (Preventative Maintenance and Installation trouble codes, '
                                     'Install Cases), cancelled requests and duplicate cases, on a machine on IPA\'s '
                                     f'installed-base list of {day(LIST_DATE)} (machines on a third-party plan left '
                                     f"out): slide 4's {len(tp):,} tickets on {len(mx):,} machines."),
        ('item', f'Request type {GROUP}', f'Trouble Code {codes}, with any Category ({", ".join(cat_order)} or none). '
                                          "A ticket raised by the daily monitoring poll ('Monitoring - Daily/Poll') "
                                          'counts as request type Monitoring instead, as on the slides, and is not '
                                          f"listed ({info['n_monitoring']} with Trouble Code {codes})."),
        ('item', 'Machine-months, rates', "The months a machine was on IPA's list in the year: from its install date "
                                          '(or its first ticket, if earlier), but no earlier than '
                                          f'{day(PERIOD_START)}, to {day(LAST_DAY)}. Rates are tickets per 100 '
                                          'machine-months.'),
        ('item', f'{U4}, {O4}', "The machine's age group, on its age at the midpoint of its machine-months, from the "
                                f"install date on IPA's list: {U4.lower()} ('young') = slide 4's first "
                                f'{NUMBER_WORDS[len(F.YOUNG_BANDS)]} bars (age bands {and_join(F.YOUNG_BANDS)} '
                                'years). A machine keeps its age group all year. Age band: '
                                f"{', '.join(map(str, FX.AGE_LABELS))} years, on the same age."),
        ('item', 'Comparison model', f'Yes for the {len(support)} models with {F.MIN_SUPPORT_MONTHS} or more '
                                     'machine-months in each age group, which the within-model comparisons (slides '
                                     f'4a right, 4b and 4e) and slide 4d use: {", ".join(support)}.'),
        ('item', "Same models' 4+ rates", "Within model (slide 4b): young machines' tickets on the comparison models "
                                          "against those each model's own 4+ machines' rate would give over the young "
                                          "machines' machine-months; the difference is the extra tickets. 'Times the "
                                          "same models' 4+ rates' is the follow-up's within-model rate ratio: each "
                                          "model's young machines' rate against its own 4+ machines' rate, pooled over "
                                          'the comparison models (Mantel-Haenszel).'),
        ('item', 'Install cohort, quarter', f"By install date on IPA's list: cohorts {', '.join(COHORTS)} (earlier "
                                            f"installs '{BEFORE}'); quarters as '{QUARTERS[0]}'."),
        ('item', 'Half', f'H1 = opened {day(PERIOD_START)} to {day(H1_END)}; H2 = opened {day(F.SPLIT)} to '
                         f'{day(LAST_DAY)} (slide 4e).'),
        ('item', 'Account, Model, Install date, Field-service vendor',
         "From IPA's installed-base list, for the machine's serial number (the account on the case can differ); "
         "Field-service vendor = the list's Service Plan."),
        ('blank', None, None),
        ('heading', None, 'Columns'),
        ('item', 'Case Number, Opened, Closed, Status, Dispatch #', "As in IPA's case export (Opened = Date/Time "
                                                                    'Opened, Closed = Trouble Closed Date/Time).'),
        ('item', ', '.join(NOTES), "IPA's own case notes, as in the case export, unwrapped (widen the column or "
                                   'select a cell to read a long one); characters a spreadsheet cannot hold are '
                                   f'removed and a note longer than {TEXT_CAP:,} characters is cut '
                                   f"({info['notes_changed']} of the {k['notes']:,} notes changed). "
                                   f'{and_join(NOT_WRITTEN)} are not included.'),
        ('item', f"Machine's {FOCUS} tickets, Ticket # on machine", f"The machine's {FOCUS} tickets in the year (all "
                                                                    'of them in this list), and their number in '
                                                                    'order of opening.'),
        ('item', 'Days since previous, Days to next', f"Days from the machine's previous {FOCUS} ticket to this one "
                                                      'and from this one to the next; blank for the first and the '
                                                      'last.'),
        ('item', 'Another within ' + ' / '.join(map(str, REPEAT_DAYS)) + ' days',
         f"Yes if the machine's next {FOCUS} ticket opened within that many days after this one. Only tickets to "
         f"{day(LAST_DAY)} count, so for a ticket opened in the year's last days a No may change later."),
        ('item', 'Core subset', f'Yes for the {FOCUS} tickets of Sub Category {CORE_SUB} on {young_words} of the '
                                f'{V2} installed in {years}.'),
        ('item', 'Core 2.0 model', f'Yes for {and_join(CORE_MODELS)} (not alEx SD 2.0, though its name has 2.0).'),
        ('item', SPIKE_LABEL, f'Yes for the {SPIKE[0]} tickets on {young_words} opened in {month}.'),
        ('item', 'Age at ticket (years)', "Years from the install date to the case's opening"
                                          + (f"; negative for {k['negative_age']} case"
                                             f"{'s' if k['negative_age'] != 1 else ''} opened before the install "
                                             "date on IPA's list." if k['negative_age'] else '.')),
        ('item', "Machine's tickets, Machines", f"The machine's unplanned {GROUP} (or {FOCUS}) tickets in the year. In "
                                                f"'{MACHINES}': Core machine = Yes if any of its tickets is in the "
                                                f'core subset; its {CORE_SUB} tickets; the opening dates of its first '
                                                f'and last {FOCUS} tickets; All unplanned tickets = every request '
                                                'type.'),
        ('item', ', '.join(IPA_HEADS), "Empty, for IPA's engineers. Sorting or filtering the sheet keeps each entry "
                                       'on its case\'s row.'),
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


def write_block(ws, row, title, header, rows, formats, notes=(), styles=None, pad=()):
    """One Summary table: title, notes (wrapped to the table's width, a line per row, so that none runs past the
    sheet's last column), header row, data rows ('bold' or 'indent' per row in styles). The columns in pad are set
    off from their left neighbour and their text runs on to the right, so the table then spans the sheet's columns:
    their header stays on one line, on a header band to the last column. Returns the next free row (after a blank
    one)."""
    ws.cell(row, 1, title).font = HEADING
    span = len(SUMMARY_WIDTHS) if pad else len(header)
    width = sum(SUMMARY_WIDTHS[:span])
    for line in (line for note in notes for line in wrap_even(note, int(NOTE_CHARS * width))):
        row += 1
        ws.cell(row, 1, line).font = NOTE
    row += 1
    for j, (h, fmt) in enumerate(zip(header, formats), 1):
        cell = ws.cell(row, j, h)
        cell.font, cell.fill, cell.alignment = BOLD, HEAD_FILL, HEAD_RIGHT if fmt else HEAD_ALIGN
        if j in pad:
            cell.alignment = Alignment(horizontal='left', vertical='bottom', indent=PAD.indent)
    for j in range(len(header) + 1, span + 1):
        ws.cell(row, j).fill = HEAD_FILL
    for i, values in enumerate(rows):
        row += 1
        style = styles[i] if styles else None
        for j, (v, fmt) in enumerate(zip(values, formats), 1):
            cell = put(ws, row, j, plain(v))
            cell.font = BOLD if style == 'bold' else FONT
            if fmt:
                cell.number_format = fmt
            if j == 1 and style == 'indent':
                cell.alignment = INDENT
            elif j in pad:
                cell.alignment = PAD
    return row + 2


def write_summary(ws, s, support):
    ws.sheet_view.showGridLines = False
    for j, width in enumerate(SUMMARY_WIDTHS, 1):
        ws.column_dimensions[get_column_letter(j)].width = width
    ws.cell(1, 1, "Summary: the slides' numbers, recomputed from this list").font = TITLE
    ws.cell(2, 1, f"Rates are tickets per 100 machine-months. {CI} intervals: the follow-up analysis's account "
                  'bootstrap.').font = NOTE
    pop = s['population']
    first = 4 + 2                                          # title, header, then the data rows
    row = write_block(ws, 4, f'1. Machines, machine-months and tickets by age group, {day(PERIOD_START)} to '
                      f'{day(LAST_DAY)} (slide 4)', ['', U4, O4, 'All'],
                      [[k, *v] for k, v in zip(pop.index, pop.to_numpy().tolist())],
                      [None, COUNT, COUNT, COUNT])
    for r, fmt in ((first + 1, MONTHS), (first + 4, RATE)):  # the machine-months and rate rows
        for j in (2, 3, 4):
            ws.cell(r, j).number_format = fmt
    cat = s['categories']
    row = write_block(
        ws, row, f'2. {GROUP} tickets by Category and age group (slides 4a and 4b)',
        ['Category', f'Tickets, {U4.lower()}', f'Tickets, {O4}', f'Per 100 machine-months, {U4.lower()}',
         f'Per 100 machine-months, {O4}', f'Ratio, {U4.lower()} / {O4}', f'Ratio, {CI} interval from', 'to',
         f'{U4} tickets expected at the {O4} rate', f'Extra {U4.lower()} tickets (crude)',
         'Extra within model (slide 4b)'],
        cat[['Category', 'u4', 'o4', 'r_u4', 'r_o4', 'ratio', 'lo', 'hi', 'expected', 'extra', 'within']]
        .to_numpy().tolist(),
        [None, COUNT, COUNT, RATE, RATE, RATE, RATE, RATE, COUNT, SIGNED, SIGNED],
        notes=[f'Expected = under-4 machine-months x the 4+ machines\' rate; extra = tickets - expected. Extra within '
               f"model: against each model's own 4+ rate, over the {len(support)} comparison models (slide 4b's "
               'method).',
               'An interval end is blank where the follow-up has none (too few tickets, or no Category row).'])
    coh = s['cohorts']
    row = write_block(
        ws, row, f'3. {FOCUS} tickets by install cohort, the {len(support)} comparison models (slide 4d)',
        ['Install cohort', 'Machines', 'Machine-months', f'{FOCUS} tickets', 'Per 100 machine-months',
         f'Ratio to {COHORTS[-1]}', f'Ratio, {CI} interval from', 'to', f'Share of machines {U4.lower()}'],
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
        notes=[f'H1 = {day(PERIOD_START)} to {day(H1_END)}, H2 = {day(F.SPLIT)} to {day(LAST_DAY)}. Same models\' 4+ '
               "machines: their rate in the same half, weighted to the young machines' models. Gap = the difference."])
    t5 = s['subcategories']
    row = write_block(
        ws, row, f'5. {GROUP} tickets by Category and Sub Category, with the extra tickets within model',
        ['Category, then its Sub Categories', f'Tickets, {U4.lower()}', f'Tickets, {O4}',
         f'Per 100 machine-months, {U4.lower()}', f'Per 100 machine-months, {O4}',
         f'Tickets, {U4.lower()}, comparison models', "Expected at the same models' 4+ rates",
         'Extra within model (slide 4b)'],
        t5[['label', U4, O4, 'r_u4', 'r_o4', 'n_sup', 'expected', 'extra']].to_numpy().tolist(),
        [None, COUNT, COUNT, '0.000', '0.000', COUNT, MONTHS, '+#,##0.0;-#,##0.0;0.0'],
        notes=[f"Expected: the tickets the young machines' machine-months on the {len(support)} comparison models "
               "would give at each model's own 4+ rate; extra = their tickets - expected (slide 4b's method; a "
               f"Category's extra is table 2's 'Extra within model'). Table 8 gives {CORE_SUB} model by model."],
        styles=['bold' if v == 'category' else 'indent' for v in t5.level])
    t6 = s['quarters']
    row = write_block(
        ws, row, f'6. {FOCUS} tickets by install quarter, {QUARTERS[0]} to {QUARTERS[-1]}, the {V2}',
        ['Models', 'Install quarter', 'Machines', f'Machines {U4.lower()}', 'Machine-months', f'{FOCUS} tickets',
         f'{CORE_SHORT} tickets', f'{FOCUS} per 100 machine-months', f'{CORE_SHORT} per 100 machine-months'],
        t6[['model', 'quarter', 'machines', 'under4', 'months', 'tickets', 'connector', 'rate', 'rate_connector']]
        .to_numpy().tolist(),
        [None, None, COUNT, COUNT, MONTHS, COUNT, COUNT, RATE, RATE],
        notes=["For lining up against the dates of IPA's changes (touchscreen, connector, cable or harness revisions, "
               'supplier or installation-kit changes, firmware), by model.',
               f"{CORE_SHORT} = Sub Category {CORE_SUB}. Machines of both age groups, by the install date on IPA's "
               'list; machine-months and tickets over the year, as in Part A.',
               "Each year's quarters add up to ag_install_year.csv. Within the year's data install date and age move "
               f'together: Machines {U4.lower()} shows where the age groups divide.'],
        styles=['bold' if m == POOLED else None for m in t6.model])
    t7 = s['subsets']
    row = write_block(
        ws, row, '7. Subset sizes: tickets, machines and accounts',
        ['Subset', 'Tickets', 'Machines', 'Accounts', 'Where in this workbook'],
        t7[['label', 'tickets', 'machines', 'accounts', 'where']].to_numpy().tolist(),
        [None, COUNT, COUNT, COUNT, None],
        notes=[f'Core subset: the {FOCUS} tickets of Sub Category {CORE_SUB} on machines {U4.lower()} of the {V2} '
               f'({and_join(CORE_MODELS)}) installed in {FOCUS_COHORT}. Indented rows lie within the bold row above '
               "them; accounts as on IPA's list."],
        styles=t7['style'].tolist(), pad=(5,))
    t8, conn = s['connector_models'], s['connector']
    row = write_block(
        ws, row, f'8. {CORE_SUB} tickets within model, on each of the {len(support)} comparison models (slide 4b)',
        ['Model', f'Tickets, {U4.lower()}', f'Machine-months, {U4.lower()}', f'Tickets, {O4}', f'Machine-months, {O4}',
         f'{O4} per 100 machine-months', f"Expected {U4.lower()}, at the model's {O4} rate",
         'Extra within model (slide 4b)'],
        t8[['model', 'u4', 'm_u4', 'o4', 'm_o4', 'r_o4', 'expected', 'extra']].to_numpy().tolist(),
        [None, COUNT, MONTHS, COUNT, MONTHS, '0.000', MONTHS, '+#,##0.0;-#,##0.0;0.0'],
        notes=[f"{FOCUS} tickets of Sub Category {CORE_SUB}. Expected = the young machines' machine-months x the "
               "model's own 4+ rate; extra = tickets - expected (slide 4b's method). Most extra first; the first row "
               f"is table 5's {CORE_SUB} row.",
               f"A single ticket cannot be called extra: of the {conn.n_sup:,.0f} young machines' {CORE_SUB} tickets, "
               f"about {conn.expected:,.0f} would be expected at the same models' 4+ rates, but any of them could be "
               'among those.'],
        styles=['bold'] + [None] * (len(t8) - 1))
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


def workbook(path, mx, tp, e, mf, support, cat_order, info, s, real):
    """Write the workbook to path. Returns {sheet: rows written (list sheets: data rows)} and the case sheets'
    frames in their written order."""
    wb = Workbook()
    wb.properties.title = f'IPA {GROUP} cases' + ('' if real else ' (pseudonymous review copy)')
    written = {README: write_readme(wb.active, readme_rows(mx, tp, e, support, cat_order, info, s, real))}
    written[SUMMARY] = write_summary(wb.create_sheet(SUMMARY), s, support)
    focus = e.ctype.eq(FOCUS)
    frames = {START: by_machine(e[focus & e.age_group.eq(U4)], real),
              OLDER: by_machine(e[focus & e.age_group.eq(O4)], real), CASES: e}
    for title, frame, columns in ((START, frames[START], START_COLUMNS), (OLDER, frames[OLDER], OLDER_COLUMNS),
                                  (CASES, e, CASE_COLUMNS), (MACHINES, mf, MACHINE_COLUMNS)):
        list_sheet(wb, title, frame, columns, real)
        written[title] = len(frame)
    wb.save(path)
    ignore_text_numbers(path, {f'xl/worksheets/sheet{i}.xml': ws.dimensions
                               for i, ws in enumerate(wb.worksheets, 1) if ws.title in LIST_SHEETS})
    return written, frames


def near(a, b):
    """Two read-back day counts the same (to about a tenth of a second), or both blank."""
    return (a is None and b is None) or (a is not None and b is not None and abs(a - b) < 1e-6)


def history_mismatches(rows):
    """The rows of a FOCUS sheet whose machine-history columns disagree with the sheet's own tickets (each machine's
    rows sit together in opening order); and the number of machines."""
    machines = defaultdict(list)
    for r in rows:
        machines[r['Serial Number']].append(r)
    bad = 0
    for rs in machines.values():
        opened = [r['Opened'] for r in rs]
        gaps = [(b - a).total_seconds() / 86400 for a, b in zip(opened, opened[1:])]
        for i, (r, prev, nxt) in enumerate(zip(rs, [None] + gaps, gaps + [None]), 1):
            to_next = r[f'Days to next {FOCUS} ticket']
            flags = all(r[f'Another within {d} days'] == ('Yes' if to_next is not None and to_next <= d else 'No')
                        for d in REPEAT_DAYS)
            bad += not (r[f"Machine's {FOCUS} tickets"] == len(rs) and r['Ticket # on machine'] == i
                        and near(r[f'Days since previous {FOCUS} ticket'], prev) and near(to_next, nxt) and flags)
    return bad, len(machines)


def check_workbook(path, written, frames, e, mf, s, real, private, check):
    """Read the workbook back and check it (counts only)."""
    wb = load_workbook(path, read_only=True)
    try:
        sheets = {ws.title: [list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets}
    finally:
        wb.close()
    check('sheets', list(sheets) == [README, SUMMARY, *LIST_SHEETS],
          f'{len(sheets)}: ' + ', '.join(f"'{t}'" for t in sheets))
    rows = {t: (len(v) - 1 if t in LIST_SHEETS else len(v)) for t, v in sheets.items()}
    check('row counts as written', rows == written,
          ', '.join(f"'{t}' {n:,}" for t, n in rows.items()) + ' (list sheets: data rows)')
    check.stop_if_failed('workbook')
    table = {t: [dict(zip(sheets[t][0], r)) for r in sheets[t][1:]] for t in LIST_SHEETS}
    t7 = s['subsets']

    # Identifiers, as intended in this copy.
    same, total = defaultdict(int), 0
    for t in CASE_SHEETS:
        f = frames[t]
        total += len(f)
        for head, rf, pf in (('Case Number', 'case_number', 'case_id'), ('Serial Number', 'serial', 'serial_id'),
                             ('Account', 'account', 'customer')):
            same[head] += sum(r[head] == v for r, v in zip(table[t], f[rf if real else pf].astype(str)))
        same['Dispatch #'] += sum(r['Dispatch #'] == (None if pd.isna(v) or not real else str(v))
                                  for r, v in zip(table[t], f.dispatch.tolist()))
    machine_ids = [r['Serial Number'] for r in table[MACHINES]]
    check('identifier columns as intended', all(n == total for n in same.values())
          and machine_ids == (mf.serial if real else mf.serial_id).astype(str).tolist(),
          ', '.join(f'{k} {n:,}' for k, n in same.items()) + f' of {total:,} rows on {len(CASE_SHEETS)} sheets '
          f"({'real' if real else 'pseudonyms; Dispatch # blank'}); '{MACHINES}' {len(machine_ids):,} serial numbers")

    # 'Start here' and 'Touchscreen 4+': the matching rows of 'All Electronics', in order, with consistent histories.
    by_case = {r['Case Number']: r for r in table[CASES]}
    missing = object()
    for t, age in ((START, U4), (OLDER, O4)):
        want = sorted(r['Case Number'] for r in table[CASES] if r['Category'] == FOCUS and r['Age group'] == age)
        got = [r['Case Number'] for r in table[t]]
        shared = [h for h in sheets[t][0] if h in sheets[CASES][0]]
        cells = sum(r[h] == by_case.get(r['Case Number'], {}).get(h, missing) for r in table[t] for h in shared)
        order = [(r['Model'].casefold(), r['Install date'], r['Serial Number'], r['Opened'], r['Case Number'])
                 for r in table[t]]
        bad, n_machines = history_mismatches(table[t])
        check(f"'{t}' = the matching rows of '{CASES}', in order",
              sorted(got) == want and cells == len(got) * len(shared) and order == sorted(order) and bad == 0,
              f'{len(got):,} rows, {len(want):,} with Category {FOCUS} and Age group {age}; {cells:,} of '
              f'{len(got) * len(shared):,} shared cells the same; sorted by model, install date, serial number and '
              f"opening; machine history consistent on {len(got) - bad:,} rows of {n_machines:,} machines")

    # Slide 4d's cluster (the old 'Touchscreen 2022-23' sheet), the flags, 'Machines' and the IPA columns.
    cluster = sum(r['Category'] == FOCUS and r['Install cohort'] == FOCUS_COHORT and r['Comparison model'] == 'Yes'
                  for r in table[CASES])
    check(f"'{CASES}' filtered to slide 4d's cluster = ag_install_pooled.csv", cluster == s['cluster_csv'],
          f'Category {FOCUS}, Install cohort {FOCUS_COHORT}, Comparison model Yes: {cluster:,} rows '
          f"({s['cluster_csv']:,} in ag_install_pooled.csv)")
    core = {r['Case Number'] for r in table[CASES] if r['Core subset'] == 'Yes'}
    core_cells = {r['Case Number'] for r in table[CASES] if r['Category'] == FOCUS and r['Sub Category'] == CORE_SUB
                  and r['Model'] in CORE_MODELS and r['Install cohort'] == FOCUS_COHORT and r['Age group'] == U4}
    core_start = {r['Case Number'] for r in table[START] if r['Core subset'] == 'Yes'}
    spike = {r['Case Number'] for r in table[CASES] if r[SPIKE_LABEL] == 'Yes'}
    spike_cells = {r['Case Number'] for r in table[CASES] if r['Category'] == SPIKE[0] and r['Age group'] == U4
                   and pd.Timestamp(r['Opened']).to_period('M') == SPIKE_MONTH}
    check(f"flags: Core subset and '{SPIKE_LABEL}' as their definitions",
          core == core_cells == core_start and len(core) == t7.at['core', 'tickets'] and spike == spike_cells
          and len(spike) == t7.at['spike', 'tickets'],
          f"Core subset {len(core):,} rows in '{CASES}', {len(core_start):,} in '{START}', {len(core_cells):,} by "
          f"their cells; '{SPIKE_LABEL}' {len(spike):,} rows, {len(spike_cells):,} by their cells")
    mrows = table[MACHINES]
    core_machines = {r['Serial Number'] for r in mrows if r['Core machine'] == 'Yes'}
    focus = e.ctype.eq(FOCUS)
    dates = sum((r[FOCUS] > 0) == (r[f'First {FOCUS} ticket'] is not None) == (r[f'Last {FOCUS} ticket'] is not None)
                and (r[FOCUS] == 0 or r[f'First {FOCUS} ticket'] <= r[f'Last {FOCUS} ticket']) for r in mrows)
    check(f"'{MACHINES}': Core machine, {CORE_SUB} tickets and {FOCUS} dates",
          core_machines == {r['Serial Number'] for r in table[START] if r['Core subset'] == 'Yes'}
          and len(core_machines) == t7.at['core', 'machines'] and dates == len(mrows)
          and sum(r[f'{CORE_SUB} tickets'] for r in mrows) == int((focus & e.subcategory.eq(CORE_SUB)).sum())
          and sum(r[FOCUS] for r in mrows) == int(focus.sum()),
          f'{len(core_machines):,} core machines; {sum(r[f"{CORE_SUB} tickets"] for r in mrows):,} {CORE_SUB} and '
          f'{sum(r[FOCUS] for r in mrows):,} {FOCUS} tickets; first and last dates on {dates:,} of {len(mrows):,} rows')
    filled = sum(r[h] is not None for r in table[START] for h in IPA_HEADS)
    check(f"the IPA columns of '{START}' empty", filled == 0,
          f'{filled} of {len(table[START]) * len(IPA_HEADS):,} cells filled ({len(IPA_HEADS)} columns)')

    # Case notes: cell for cell as intended, and nowhere else; no Administrative Notes or Case Owner value.
    strings = [(t, h, v) for t in LIST_SHEETS for r in table[t] for h, v in r.items() if isinstance(v, str)]
    strings += [(t, None, v) for t in (README, SUMMARY) for r in sheets[t] for v in r if isinstance(v, str)]
    strings += [(t, None, t) for t in sheets]
    in_notes = {(t, h) for t in CASE_SHEETS for h in NOTES}
    same = shape = cells = 0
    for t in CASE_SHEETS:
        for head, field in zip(NOTES, ('reported', 'resolution')):
            want = [plain(v) for v in frames[t][field if real else f'{field}_x'].tolist()]
            got = [r[head] for r in table[t]]
            cells += len(want)
            same += sum(a == b for a, b in zip(got, want))
            shape += sum((g is None and plain(x) is None) or (isinstance(g, str) and isinstance(x, str)
                                                              and len(g) == len(x)
                                                              and (real or re.fullmatch(r'[x\s]*', g) is not None))
                         for g, x in zip(got, frames[t][field].tolist()))
    check('case notes ' + ('as in the export' if real else "replaced by same-length x's"),
          same == cells and shape == cells,
          f"{same:,} of {cells:,} note cells as intended on {len(CASE_SHEETS)} sheets, {shape:,} of the note's length"
          + ('' if real else ", x's and whitespace only"))
    long_other = sum(len(v) >= LONG for t, h, v in strings if t in LIST_SHEETS and h not in (*NOTES, 'Account'))
    lead_notes = sum(v in private['notes'] for t, h, v in strings if t not in LIST_SHEETS)
    check('long text only in the notes columns', long_other == 0 and lead_notes == 0,
          f'{long_other} list-sheet cells of {LONG}+ characters outside {and_join(NOTES)} (and Account); '
          f"{lead_notes} '{README}' or '{SUMMARY}' cells equal to a note")
    admin_out = sum(v in private['admin'] for t, h, v in strings if (t, h) not in in_notes)
    admin_own = sum(v in private['admin'] for t, h, v in strings if (t, h) in in_notes)
    owners = sum(v in private['owners'] for t, h, v in strings)
    check(f'no {NOT_WRITTEN[0]} or {NOT_WRITTEN[1]} value in any cell', admin_out == 0 and owners == 0,
          f"{admin_out} cells equal one of {len(private['admin']):,} {NOT_WRITTEN[0]} values ({LONG}+ characters) "
          f'outside the notes; {admin_own} note cell(s) whose own text, checked above, equals one; {owners} cells '
          f"equal one of {len(private['owners'])} {NOT_WRITTEN[1]} values")

    # Privacy.
    if real:
        left = sum(names.pseudonyms_left(v) for t, h, v in strings if (t, h) not in in_notes)
        check('privacy: no pseudonym in the real workbook', left == 0,
              f'{left} pseudonyms (T#####, S#####, M#####, Customer NNN) in {len(strings):,} text cells (the notes '
              "are the export's own text, checked above)")
    else:
        real_ids = F.real_sets(private['maps'], common.EQUIPMENT)
        real_ids['digit'] |= {d for d in private['dispatch'] if d.isdigit()}
        real_ids['text'] |= {FX.norm(d) for d in private['dispatch'] if not d.isdigit() and len(FX.norm(d)) >= 4}
        leaks = FX.text_leaks(pd.DataFrame({'text': [v for _, _, v in strings]}), real_ids)
        ids = [r[h] for t in CASE_SHEETS for r in table[t] for h in ('Case Number', 'Serial Number', 'Account')]
        ids += [r[h] for r in table[MACHINES] for h in ('Serial Number', 'Account')]
        pseudo = sum(bool(re.fullmatch(r'T\d{5}|[SM]\d{5}|Customer \d{3,4}', str(v))) for v in ids)
        texts = private['notes'] | private['admin'] | private['owners']
        real_text = sum(v in texts for _, _, v in strings)
        check('privacy: no real identifier or text in the pseudonymous copy',
              not leaks and pseudo == len(ids) and real_text == 0,
              f'{sum(leaks.values())} real names or identifiers in {len(strings):,} text cells; {pseudo:,} of '
              f'{len(ids):,} identifier cells are pseudonyms; {real_text} cells equal a real note, {NOT_WRITTEN[0]} '
              f'or {NOT_WRITTEN[1]} value')


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
        mx, tp, e, support, cat_order, info, private = load(check)
        print(f'  {len(e):,} {GROUP} tickets ({int(e.age_group.eq(U4).sum()):,} under 4, '
              f'{int(e.age_group.eq(O4).sum()):,} 4+) on {e.serial.nunique():,} machines; {info["n_monitoring"]} '
              f'Monitoring tickets with Trouble Code {GROUP} left out, as on the slides')
        s = summary(mx, tp, e, support, cat_order, check)
        check.stop_if_failed('data')
        print('  subsets (tickets / machines / accounts): ' + '; '.join(
            f'{r.label} {r.tickets:,} / {r.machines:,} / {r.accounts:,}' for r in s['subsets'].itertuples()))
        mf = machines_frame(e, tp)

        out.parent.mkdir(parents=True, exist_ok=True)
        if real and not (out.resolve().is_relative_to(names.DELIVERABLES.resolve()) and git_ignored(out)):
            fail(f'{out.name} is not under deliverables/ or not gitignored')
        fd, name = tempfile.mkstemp(prefix=f'.{out.stem}_', suffix='.xlsx', dir=out.parent)
        os.close(fd)
        tmp = Path(name)
        if real and not git_ignored(tmp):
            fail('the temporary file in deliverables/ is not gitignored')
        written, frames = workbook(tmp, mx, tp, e, mf, support, cat_order, info, s, real)
        print('  written: ' + ', '.join(f"'{t}' {n:,} rows" for t, n in written.items()))
        check_workbook(tmp, written, frames, e, mf, s, real, private, check)
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
    except Exception as err:  # noqa: BLE001  its message could quote an identifier or a note: type and line only
        frame = traceback.extract_tb(err.__traceback__)[-1]
        fail(f'unexpected {type(err).__name__} at {Path(frame.filename).name}:{frame.lineno} (message withheld)')
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def tables():
    """--tables: the counts the report quotes, as CSVs of labels and counts in TABLES; no workbook."""
    print(f'IPA {GROUP} case list: aggregate tables only (no workbook)')
    try:
        check = Checks()
        mx, tp, e, support, cat_order, info, private = load(check)
        s = summary(mx, tp, e, support, cat_order, check)
        check.stop_if_failed('data')
        young = e.age_group.eq(U4)
        frames = {
            'ec_counts': pd.DataFrame([
                ('tickets', f'{GROUP} tickets on the list', len(e)),
                ('under4', f'{GROUP} tickets, {U4.lower()}', int(young.sum())),
                ('plus4', f'{GROUP} tickets, {O4}', int((~young).sum())),
                ('focus_under4_core_models', f'{FOCUS} tickets, {U4.lower()}, on the four 2.0 models ('
                 f'{", ".join(CORE_MODELS)})', s['facts']['u4_v2']),
            ], columns=['key', 'label', 'value']),
            'ec_subsets': s['subsets'].reset_index()[['key', 'label', 'tickets', 'machines', 'accounts']],
            'ec_edge': s['edge'][['label', 'machines', 'under4', 'months', 'tickets', 'rate']]
            .rename(columns={'rate': 'rate_per_100'}),
        }
        real = F.real_sets(private['maps'], common.EQUIPMENT)
        text = pd.DataFrame({'text': [str(v) for f in frames.values() for v in f.astype(str).to_numpy().ravel()]})
        leaks = sum(FX.text_leaks(text, real).values())
        check('tables hold no real identifier', leaks == 0, f'{len(text):,} cells scanned, {leaks} hits')
        check.stop_if_failed('privacy')
        TABLES.mkdir(parents=True, exist_ok=True)
        for name, frame in frames.items():
            frame.to_csv(TABLES / f'{name}.csv', index=False)
            print(f'  wrote {name}.csv ({len(frame)} rows)')
        print(f'checks pass: {GROUP} tables written to {TABLES.name}/')
    except BuildError:
        raise
    except Exception as err:  # noqa: BLE001  its message could quote an identifier or a note: type and line only
        frame = traceback.extract_tb(err.__traceback__)[-1]
        fail(f'unexpected {type(err).__name__} at {Path(frame.filename).name}:{frame.lineno} (message withheld)')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument('--pseudo', metavar='OUT_DIR', help=f'build the pseudonymous copy into OUT_DIR/{PSEUDO_FILE} '
                      'instead of the real workbook')
    mode.add_argument('--tables', action='store_true', help='write only the aggregate tables the replication '
                      'notebooks read, to verification/outputs/electronics/ (no workbook)')
    a = ap.parse_args()
    try:
        tables() if a.tables else build(a.pseudo)
    except BuildError as err:
        print(f'FAILED: {err}')
        sys.exit(1)


if __name__ == '__main__':
    main()
