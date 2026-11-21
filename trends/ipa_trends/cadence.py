"""Reporting periods for a rerun frequency that is a free parameter: any whole number of months.

RERUN_FREQUENCY is both how often the notebook is rerun and the length of every reporting period. Everything that
depends on it is derived here: period edges (always counted from a fixed anchor, so nothing drifts between runs),
labels, statuses, baselines, sentence nouns and the dates the next runs are due. The install-cohort width uses the
same parser. Explicit PERIOD_EDGES give a CustomPeriods cadence, whose wording says 'period' whatever the periods'
length. Nothing elsewhere in the package is written for quarters; a test checks for quarter and year literals
outside this module.

Quarterly and monthly are the intended settings (the cadences proposed to IPA). Weeks are refused: weekly cells
hold too few tickets to tell a change from noise.
"""
import math
import re
from dataclasses import dataclass

import pandas as pd

from .errors import ConfigError

NAMED = {'monthly': 1, 'month': 1, 'bimonthly': 2, 'bi-monthly': 2, 'every two months': 2, 'quarterly': 3,
         'quarter': 3, 'four-monthly': 4, 'every four months': 4, 'semiannual': 6, 'semi-annual': 6,
         'semiannually': 6, 'half-yearly': 6, 'half yearly': 6, 'halfyearly': 6, 'annual': 12, 'annually': 12,
         'yearly': 12, 'year': 12}
NOUNS = {1: ('month', 'months', 'monthly'), 2: ('two-month period', 'two-month periods', 'bimonthly'),
         3: ('quarter', 'quarters', 'quarterly'), 4: ('four-month period', 'four-month periods', 'four-monthly'),
         6: ('half-year', 'half-years', 'half-yearly'), 12: ('year', 'years', 'yearly')}
NUMBER_WORDS = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten']
MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
MONTHS_LONG = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
               'November', 'December']
_FREE = re.compile(r'^\s*(\d+)\s*(m|mo|mos|mon|months?|y|yr|yrs|years?)?\s*$', re.I)
_WEEKS = re.compile(r'week|wk|fortnight|daily|\bdays?\b|^\s*\d*\s*[wd]\s*$', re.I)
_OFFSET = re.compile(r'^\s*\d*\s*(?:M|MS|ME|Q|QS|QE|A|AS|Y|YS|YE|BQ|BQS|BM|BMS|BA|BAS|SM|SMS)(?:-[A-Za-z]{3})?\s*$')
DEFAULT_ANCHOR_YEAR = 2000
STATUSES = ('partial', 'in_progress', 'provisional', 'final')


@dataclass(frozen=True)
class Cadence:
    """A period length in whole months."""
    months: int

    @property
    def canonical(self):
        return f'{self.months}M'

    @property
    def noun(self):
        return NOUNS.get(self.months, (f'{self.months}-month period',))[0]

    @property
    def plural(self):
        return NOUNS.get(self.months, (None, f'{self.months}-month periods'))[1]

    @property
    def adjective(self):
        return NOUNS.get(self.months, (None, None, f'every {self.months} months'))[2]

    @property
    def variation(self):
        """'quarter-to-quarter variation', 'month-to-month variation', 'period-to-period variation'."""
        if self.months in (1, 3, 12):
            return f'{self.noun}-to-{self.noun} variation'
        return 'period-to-period variation'

    def previous(self, k):
        """'the previous four quarters', 'the previous quarter', 'the previous 12 months'."""
        if k == 1:
            return f'the previous {self.noun}'
        number = NUMBER_WORDS[k] if k < len(NUMBER_WORDS) else str(k)
        return f'the previous {number} {self.plural}'


@dataclass(frozen=True)
class CustomPeriods(Cadence):
    """The cadence when PERIOD_EDGES gives explicit periods (a 4-4-5 calendar, half-years, reconciliation): the
    wording says 'period' whatever their length ('the previous four periods', 'period-to-period variation',
    'Report (custom periods)'), and baselines count the explicit periods. `months`, and so `canonical`, stay those
    of RERUN_FREQUENCY, which key the run id and the dashboard."""
    edges: tuple = ()

    @property
    def noun(self):
        return 'period'

    @property
    def plural(self):
        return 'periods'

    @property
    def adjective(self):
        return '(custom periods)'

    @property
    def variation(self):
        return 'period-to-period variation'

    def starts(self):
        """The start of every explicit period (the last edge only closes the last period)."""
        return sorted({pd.Timestamp(e).normalize() for e in self.edges})[:-1]


def parse_frequency(value, name='RERUN_FREQUENCY', max_months=24):
    """A Cadence from 'quarterly', 'monthly', '5 months', '3M', '1 year', or an integer number of months.

    Raises ConfigError (E20) for weeks, days, pandas offset aliases and anything outside 1..max_months."""
    def fail(message, fix):
        raise ConfigError([('E20', f'{name} = {value!r}: {message}', fix)])

    examples = "write 'quarterly', 'monthly', or a number of months such as '2 months'"
    if isinstance(value, bool) or value is None:
        fail('not a frequency', examples)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if float(value) != int(value):
            fail('use a whole number of months', examples)
        months = int(value)
    elif isinstance(value, str):
        s = ' '.join(value.strip().lower().split())
        free = _FREE.match(s)
        if s in NAMED:
            months = NAMED[s]
        elif _WEEKS.search(s):
            fail('periods shorter than a month are not supported: weekly cells hold too few tickets to tell a change '
                 'from noise', "use 'monthly' or 'quarterly'")
        elif free:                                   # '3M', '3 months', '1 year', '2y'
            months = int(free.group(1)) * (12 if (free.group(2) or 'm').startswith('y') else 1)
        elif _OFFSET.match(value.strip()):           # 'M', 'Q', 'QS-OCT', 'MS', 'A' ...
            fail('pandas offset aliases are not accepted (their meaning changed between pandas versions and they hide '
                 'the anchor)', examples + '; set YEAR_START_MONTH for a fiscal year')
        else:
            fail('not recognised', examples)
    else:
        fail('not recognised', examples)
    if not 1 <= months <= max_months:
        fail(f'must be between 1 and {max_months} months', examples)
    return Cadence(months)


def make_anchor(year_start_month=1, anchor_date=None):
    """The fixed date every period edge is counted from: ANCHOR_DATE, or the 1st of YEAR_START_MONTH in 2000."""
    if anchor_date is not None:
        a = pd.Timestamp(anchor_date).normalize()
        if a.day > 28:
            raise ConfigError([('E21', f'ANCHOR_DATE {a:%Y-%m-%d} falls after the 28th, so some months have no such day',
                                'choose a day from 1 to 28')])
        return a
    return pd.Timestamp(DEFAULT_ANCHOR_YEAR, int(year_start_month), 1)


def _edge(anchor, k, months):
    return anchor + pd.DateOffset(months=k * months)


def period_edges(cadence, start, end, anchor):
    """Edges [e_0, e_1, ...] of whole periods covering [start, end), counted from the anchor."""
    n = cadence.months
    k = math.floor(((start.year - anchor.year) * 12 + (start.month - anchor.month)) / n)
    while _edge(anchor, k, n) > start:
        k -= 1
    while _edge(anchor, k + 1, n) <= start:
        k += 1
    edges = [_edge(anchor, k, n)]
    while edges[-1] < end:
        k += 1
        edges.append(_edge(anchor, k, n))
    return edges


def months_spanned(start, end):
    """Whole months from start to end when both fall on the 1st of a month, else None."""
    if start.day == 1 and end.day == 1:
        return (end.year - start.year) * 12 + end.month - start.month
    return None


def _year_prefix(start, year_start_month, named_by):
    if year_start_month == 1:
        return str(start.year)
    fy_start = start.year if start.month >= year_start_month else start.year - 1
    return f"FY{fy_start + 1 if named_by == 'end' else fy_start}"


def range_label(start, end, long=False):
    """'Jun-Aug 2026', 'Nov 2025-Jan 2026', 'Aug 2026'; day ranges when the edges are not month starts."""
    last = end - pd.Timedelta(days=1)
    names = MONTHS_LONG if long else MONTHS
    if months_spanned(start, end) is not None:
        a, b = names[start.month - 1], names[last.month - 1]
        if (start.year, start.month) == (last.year, last.month):
            return f'{a} {start.year}'
        if start.year == last.year:
            return f'{a}-{b} {start.year}'
        return f'{a} {start.year}-{b} {last.year}'
    if start.year == last.year:
        return f'{start.day} {names[start.month - 1]}-{last.day} {names[last.month - 1]} {last.year}'
    return f'{start.day} {names[start.month - 1]} {start.year}-{last.day} {names[last.month - 1]} {last.year}'


def period_label(start, end, year_start_month=1, named_by='end', long=False):
    """Short label for [start, end): 'Aug 2026', '2026 Q2', 'FY2027 Q1', '2026 H1', '2026', '2016-18', ranges."""
    n = months_spanned(start, end)
    if n == 1:
        return f'{MONTHS_LONG[start.month - 1]} {start.year}' if long else f'{MONTHS[start.month - 1]} {start.year}'
    # aligned: the period starts on a boundary of the reporting year for its length (quarters on quarter starts...)
    aligned = bool(n) and ((start.month - year_start_month) % 12) % min(n, 12) == 0
    if aligned and n in (3, 6, 12):
        prefix = _year_prefix(start, year_start_month, named_by)
        idx = ((start.month - year_start_month) % 12) // n + 1
        short = {3: f'{prefix} Q{idx}', 6: f'{prefix} H{idx}', 12: prefix}[n]
        calendar_year = n == 12 and year_start_month == 1
        return f'{short} ({range_label(start, end)})' if long and not calendar_year else short
    if aligned and n % 12 == 0 and year_start_month == 1:
        last = end - pd.Timedelta(days=1)
        return f'{start.year}-{str(last.year)[2:]}' if last.year // 100 == start.year // 100 \
            else f'{start.year}-{last.year}'
    return range_label(start, end, long=long)


def period_grid(cadence, data_start, data_end_excl, year_start_month=1, named_by='end', anchor_date=None,
                explicit_edges=None):
    """One row per reporting period that overlaps the data [data_start, data_end_excl).

    Columns: period_key (ISO start date), period_start, period_end (exclusive), label, label_long, days,
    covered_start, covered_end, covered_days, nominal_months."""
    if explicit_edges is not None:
        edges = sorted({pd.Timestamp(e).normalize() for e in explicit_edges})
    else:
        edges = period_edges(cadence, data_start, data_end_excl, make_anchor(year_start_month, anchor_date))
    rows = []
    for a, b in zip(edges[:-1], edges[1:]):
        lo, hi = max(a, data_start), min(b, data_end_excl)
        if hi <= lo:
            continue
        rows.append({'period_key': f'{a:%Y-%m-%d}', 'period_start': a, 'period_end': b,
                     'label': period_label(a, b, year_start_month, named_by),
                     'label_long': period_label(a, b, year_start_month, named_by, long=True),
                     'days': (b - a).days, 'covered_start': lo, 'covered_end': hi, 'covered_days': (hi - lo).days,
                     'nominal_months': months_spanned(a, b) if months_spanned(a, b) is not None
                     else round((b - a).days / (365.25 / 12), 2)})
    grid = pd.DataFrame(rows)
    if grid.empty:
        raise ConfigError([('E24', 'no reporting period overlaps the data', 'check PERIOD_EDGES and the export dates')])
    if grid.label.duplicated().any():           # explicit edges can repeat a short label; keep labels unique
        grid['label'] = grid.label_long
    return grid.reset_index(drop=True)


def assign_statuses(grid, data_start, data_end_excl, extracted_at, lag_days, open_share, max_open_share):
    """Status and reason per period (see STATUSES). open_share: share of each period's unplanned tickets still open
    when the export was taken, indexed by period_key. Only final periods are tested or used in baselines."""
    mature_before = pd.Timestamp(extracted_at).normalize() - pd.Timedelta(days=int(lag_days))
    status, reason = [], []
    for g in grid.itertuples():
        share = float(open_share.get(g.period_key, 0.0))
        if g.period_start < data_start:
            status.append('partial')
            reason.append(f'starts before the data: {g.covered_days} of {g.days} days covered')
        elif g.period_end > data_end_excl:
            status.append('in_progress')
            reason.append(f'the data end on {data_end_excl - pd.Timedelta(days=1):%Y-%m-%d}: '
                          f'{g.covered_days} of {g.days} days covered')
        elif g.period_end > mature_before:
            days = (pd.Timestamp(extracted_at).normalize() - g.period_end).days
            status.append('provisional')
            reason.append(f'exported {max(days, 0)} days after the period ended; labels need {lag_days} days to settle')
        elif share > max_open_share:
            status.append('provisional')
            reason.append(f'{100 * share:.1f}% of its tickets were still open when exported')
        else:
            status.append('final')
            reason.append('')
    out = grid.copy()
    out['status'], out['status_reason'] = status, reason
    out['open_share'] = [float(open_share.get(k, 0.0)) for k in out.period_key]
    return out


def latest_final(grid, latest=None):
    """Position of the latest final period, or of the period named by LATEST_PERIOD (label or ISO start)."""
    if latest is not None:
        hit = grid.index[(grid.label == str(latest)) | (grid.period_key == str(latest))]
        if not len(hit):
            raise ConfigError([('E25', f'LATEST_PERIOD {latest!r} is not a reporting period of this run',
                                'use a label or start date shown in periods.csv')])
        pos = int(hit[0])
        if grid.status[pos] != 'final':
            raise ConfigError([('E25', f'LATEST_PERIOD {latest!r} is {grid.status[pos]}, not final',
                                'choose a final period')])
        return pos
    final = grid.index[grid.status == 'final']
    return int(final[-1]) if len(final) else None


def baseline_positions(grid, latest_pos, baseline_months, cadence=None, mask=None):
    """Final periods that end within the `baseline_months` before the latest period starts.

    Returns (positions, intended, enough): `intended` is how many periods the window holds; `enough` requires at
    least half of them (and at least one). With explicit edges (CustomPeriods) `intended` counts the explicit
    periods that start inside the window, including any the data do not reach, and the window always reaches back
    to the start of the period before L (one period when periods are longer than the window, as for long
    cadences); otherwise it is baseline_months divided by the period length. `mask` (bool per period) can drop
    periods, for example those whose Category labels are incomplete."""
    start_l = grid.period_start[latest_pos]
    window = start_l - pd.DateOffset(months=int(baseline_months))
    custom = isinstance(cadence, CustomPeriods)
    if custom:
        before = [s for s in cadence.starts() if s < start_l]
        if before and before[-1] < window:           # a 53-week year, say, against a 12-month window
            window = before[-1]
    inside = (grid.period_start >= window) & (grid.period_end <= start_l) & (grid.index < latest_pos)
    if custom:
        intended = max(1, sum(1 for s in before if s >= window))
    elif cadence is not None:
        intended = int(baseline_months) // cadence.months
    else:
        intended = int(inside.sum())
    ok = inside & (grid.status == 'final')
    if mask is not None:
        ok &= mask
    pos = [int(i) for i in grid.index[ok]]
    return pos, intended, len(pos) >= max(1, math.ceil(intended / 2))


def next_runs(cadence, after, lag_days, n=4, year_start_month=1, named_by='end', anchor_date=None):
    """The next n periods ending after `after`: label, period, and the date each run is due (period end + lag).
    Also a cron hint when every due date falls on the same day of the month."""
    anchor = make_anchor(year_start_month, anchor_date)
    edges = period_edges(cadence, pd.Timestamp(after), pd.Timestamp(after) + pd.DateOffset(months=cadence.months
                                                                                            * (n + 1)), anchor)
    runs = []
    for a, b in zip(edges[:-1], edges[1:]):
        if b <= pd.Timestamp(after):
            continue
        runs.append({'label': period_label(a, b, year_start_month, named_by), 'period_start': f'{a:%Y-%m-%d}',
                     'period_end': f'{b:%Y-%m-%d}', 'due': f'{b + pd.Timedelta(days=int(lag_days)):%Y-%m-%d}'})
        if len(runs) == n:
            break
    cron = None
    if 12 % cadence.months == 0:
        year = period_edges(cadence, anchor, anchor + pd.DateOffset(months=12), anchor)[1:13 // cadence.months + 1]
        dues = [e + pd.Timedelta(days=int(lag_days)) for e in year]
        if len({d.day for d in dues}) == 1:
            months = sorted({d.month for d in dues})
            cron = f"0 7 {dues[0].day} {'*' if len(months) == 12 else ','.join(map(str, months))} *"
    return runs, cron


def cohort_bins(width, start, explicit_edges=None, year_start_month=1, named_by='end', last_install=None):
    """Install-cohort bins [(label, lo, hi)], open at both ends: 'Before <start>' ... newest cohort.

    `width` is a Cadence (from INSTALL_COHORT_WIDTH); explicit edges (INSTALL_COHORT_EDGES) override it."""
    if explicit_edges is not None:
        edges = sorted({pd.Timestamp(e).normalize() for e in explicit_edges})
    else:
        start = pd.Timestamp(start).normalize()
        stop = pd.Timestamp(last_install if last_install is not None else start).normalize()
        edges = [start]
        k = 0
        while edges[-1] <= stop:
            k += 1
            edges.append(start + pd.DateOffset(months=k * width.months))
    first = edges[0]
    head = _year_prefix(first, year_start_month, named_by) if (first.month == year_start_month and first.day == 1) \
        else f'{MONTHS[first.month - 1]} {first.year}'
    bins = [(f'Before {head}', pd.Timestamp.min, first)]
    bins += [(period_label(a, b, year_start_month, named_by), a, b) for a, b in zip(edges[:-1], edges[1:])]
    if explicit_edges is not None:
        last = edges[-1]
        tail = _year_prefix(last, year_start_month, named_by) if (last.month == year_start_month and last.day == 1) \
            else f'{MONTHS[last.month - 1]} {last.year}'
        bins.append((f'From {tail}', last, pd.Timestamp.max))
    return bins


def assign_cohorts(install_dates, bins, unknown='Unknown'):
    """Ordered categorical of cohort labels for each install date (NaT -> 'Unknown')."""
    labels = [b[0] for b in bins] + [unknown]
    out = pd.Series(unknown, index=install_dates.index, dtype=object)
    d = pd.to_datetime(install_dates)
    for lab, lo, hi in bins:
        out[(d >= lo) & (d < hi)] = lab
    return pd.Categorical(out, categories=labels, ordered=True)
