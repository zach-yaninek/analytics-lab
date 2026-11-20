"""Parameters: the defaults, parameter files, command-line overrides, and validation.

DEFAULTS is the only source of default values; the notebook's parameters cell holds exactly these literals (a test
checks it). Precedence: DEFAULTS < parameter file (YAML or JSON) < --set K=V on the command line, or < values
edited in the notebook / injected by papermill.

Every problem is collected and reported together, with "did you mean" suggestions for misspelt names, so a typo
such as RERUN_FREQUENCEY stops the run instead of silently running quarterly.
"""
import datetime as dt
import difflib
import json
import os
import re
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from .cadence import Cadence, parse_frequency
from .errors import ConfigError

PACKAGE_DIR = Path(__file__).resolve().parent
TRENDS_DIR = PACKAGE_DIR.parent
DIMENSIONS = ('install_cohort', 'family', 'model', 'age_group', 'age_band', 'service_status', 'country')

DEFAULTS = {
    # ---- Inputs (relative paths are read from BASE_DIR, which defaults to the trends/ folder)
    'CASE_EXPORTS': 'data/raw/IPA_CaseHistory_*.xlsx',
    'CASE_SHEET': 'ipa_repair cases',
    'EQUIPMENT_LISTS': 'data/raw/IPA_Active_Equipment_list_*.xlsx',
    'EQUIPMENT_SHEET': 'Equipment list - Monthly Report',
    'EQUIPMENT_LIST_DATES': {},
    'EXTRACTED_AT': None,
    'DATA_START': None,
    'DATA_END': None,
    'COLUMN_ALIASES': {},
    'CATEGORY_ALIASES': {},
    'REQUEST_TYPES_LOCAL': None,
    'UNMAPPED_POLICY': 'separate',
    'CASE_CLOCK_TZ': 'America/New_York',
    'DATE_FORMAT': None,
    'BASE_DIR': None,
    'OUTPUT_DIR': 'data/output',
    # ---- Cadence: RERUN_FREQUENCY is how often the notebook is rerun and the length of every reporting period
    'RERUN_FREQUENCY': 'quarterly',
    'YEAR_START_MONTH': 1,
    'FISCAL_YEAR_NAMED_BY': 'end',
    'ANCHOR_DATE': None,
    'PERIOD_EDGES': None,
    'LATEST_PERIOD': None,
    'BASELINE_MONTHS': None,
    'HISTORY_MONTHS': None,
    'LABEL_LAG_DAYS': 14,
    'MAX_OPEN_SHARE': 0.02,
    'MAX_BLANK_CATEGORY_SHARE': 0.05,
    'MAX_UNMAPPED_SHARE': 0.05,
    # ---- Breakdowns
    'STRATIFY_BY': ['install_cohort', 'family', 'model'],
    'CATEGORY_DIMS': ['fleet', 'install_cohort'],
    'INSTALL_COHORT_WIDTH': '1 year',
    'INSTALL_COHORT_START': '2016-01-01',
    'INSTALL_COHORT_EDGES': None,
    'MODEL_FILTER': None,
    'POOL_SMALL_STRATA': True,
    'MIN_TYPE_MONTHS': 100,
    'MIN_CELL_MONTHS': 100,
    'THIRD_PARTY_PLANS': ['Vogeltronix'],
    'MISSING_INSTALL_DATE': 'exclude',
    # ---- Call-outs (conservative screening flags)
    'Q_CUT': 0.05,
    'WATCH_Q': 0.20,
    'MIN_CHANGE': 0.20,
    'MIN_CONTRAST': 0.50,
    'CONTRAST_MONTHS': 12,
    'MIN_EXPECTED': 10,
    'MIN_BASELINE_TICKETS': 20,
    'MIN_ACCOUNTS': 10,
    'TAU2_FLOOR': 0.001,
    'N_BOOT': 2000,
    'SEED': 15072,
    'COHORT_MAP_ISSUES': 'auto',
    # ---- Outputs
    'MAKE_CHARTS': 'auto',
    'MAKE_REPORT': True,
    'REPORT_TITLE': 'IPA service-ticket trends',
}
NAME_RE = re.compile(r'^[A-Z][A-Z0-9_]*$')

# One line per parameter: shown in the notebook's parameters cell and in trends/README.md.
COMMENTS = {
    'CASE_EXPORTS': 'case report(s) from Salesforce (.xlsx); the newest match is used',
    'CASE_SHEET': "sheet holding the cases (if missing and only one other sheet exists, that one is read)",
    'EQUIPMENT_LISTS': 'every equipment-list snapshot (Monthly Report); keep them all',
    'EQUIPMENT_SHEET': 'sheet holding the equipment list',
    'EQUIPMENT_LIST_DATES': "{'file name': 'YYYY-MM-DD'} for lists whose file name has no date",
    'EXTRACTED_AT': "'YYYY-MM-DD' the case report was exported (default: the workbook's created date)",
    'DATA_START': "'YYYY-MM-DD' first day the export covers (default: the first ticket's day)",
    'DATA_END': "'YYYY-MM-DD' last day the export covers (default: the last ticket's day)",
    'COLUMN_ALIASES': "{'renamed header': 'expected header'} if IPA renames a column",
    'CATEGORY_ALIASES': "{'new Category name': 'old Category name'} so a renamed Category keeps its series",
    'REQUEST_TYPES_LOCAL': 'CSV adding new Trouble Code x Category combinations to the request groups',
    'UNMAPPED_POLICY': "'separate': unmapped combinations form their own, never-tested group",
    'CASE_CLOCK_TZ': 'time zone of the case times in the export (US Eastern for IPA)',
    'DATE_FORMAT': "e.g. '%m/%d/%Y %I:%M %p' when dates are stored as text (default: detected)",
    'BASE_DIR': 'folder relative paths are read from (default: the trends folder)',
    'OUTPUT_DIR': 'where runs are written (runs/<run_id>/ and latest/)',
    'RERUN_FREQUENCY': "how often this is rerun = length of each period: 'quarterly', 'monthly', '2 months'...",
    'YEAR_START_MONTH': 'first month of the reporting year (10 for an October fiscal year)',
    'FISCAL_YEAR_NAMED_BY': "'end': the year starting Oct 2026 is FY2027",
    'ANCHOR_DATE': "'YYYY-MM-DD' a date that starts a period, for unusual calendars",
    'PERIOD_EDGES': "explicit period edges ['YYYY-MM-DD', ...] (overrides RERUN_FREQUENCY)",
    'LATEST_PERIOD': 'report an earlier final period as the latest (back-runs); never overwrites latest/',
    'BASELINE_MONTHS': 'months of baseline before the latest period (default: 12, or one period if longer)',
    'HISTORY_MONTHS': 'months of history in the charts (default: 24, or three periods if longer)',
    'LABEL_LAG_DAYS': 'days after a period ends before it counts as final (Categories are filled at close)',
    'MAX_OPEN_SHARE': 'a period with more of its tickets still open stays provisional',
    'MAX_BLANK_CATEGORY_SHARE': 'above this share of blank Categories, issue-level comparisons skip the period',
    'MAX_UNMAPPED_SHARE': 'above this share of unmapped tickets, affected groups are not tested',
    'STRATIFY_BY': "breakdowns: 'install_cohort', 'family', 'model', 'age_group', 'service_status', ...",
    'CATEGORY_DIMS': 'breakdowns that also get Category-level rates',
    'INSTALL_COHORT_WIDTH': "width of install cohorts: '1 year', '6 months', 'quarterly'...",
    'INSTALL_COHORT_START': "first cohort start; earlier installs are pooled ('Before 2016')",
    'INSTALL_COHORT_EDGES': "explicit cohort edges ['2016-01-01', '2019-01-01', ...] (overrides the width)",
    'MODEL_FILTER': 'only these models (reconciliation)',
    'POOL_SMALL_STRATA': 'pool models with too few machines into one "Other models" series',
    'MIN_TYPE_MONTHS': 'machine-months a model needs over 396 days for its own series (100 = 7.7 machines)',
    'MIN_CELL_MONTHS': 'cells with fewer machine-months are shown hollow',
    'THIRD_PARTY_PLANS': 'service plans whose service does not reach the case export (excluded)',
    'MISSING_INSTALL_DATE': "'exclude' machines without an install date, or 'data_start'",
    'Q_CUT': 'false-discovery rate for a flag',
    'WATCH_Q': 'false-discovery rate for the watch list (report only)',
    'MIN_CHANGE': 'smallest change worth flagging (0.20 = 20%)',
    'MIN_CONTRAST': 'smallest cohort difference worth calling out (0.50 = 50% higher)',
    'CONTRAST_MONTHS': 'months of final periods in the install-cohort comparison',
    'MIN_EXPECTED': 'fewest expected tickets in the latest period for a test',
    'MIN_BASELINE_TICKETS': 'fewest baseline tickets for a test',
    'MIN_ACCOUNTS': 'fewest accounts with baseline tickets for a test',
    'TAU2_FLOOR': 'smallest between-period variance assumed (log scale)',
    'N_BOOT': 'bootstrap draws (2000 as in the analysis IPA saw)',
    'SEED': 'random seed (15072 as in the analysis IPA saw)',
    'COHORT_MAP_ISSUES': "'auto' or a list of issue names for the cohort charts",
    'MAKE_CHARTS': "'auto': charts when matplotlib is installed",
    'MAKE_REPORT': 'write report.html, report.pdf and the email text',
    'REPORT_TITLE': 'title of the report and email',
}
assert set(COMMENTS) == set(DEFAULTS)


# ------------------------------------------------------------------------------------------------ value checkers
class _Problem(Exception):
    def __init__(self, message, fix=None, code='E22'):
        super().__init__(message)
        self.message, self.fix, self.code = message, fix, code


def _maybe_json(v):
    """papermill turns tuples into lists and command lines give strings: accept JSON text for lists and dicts."""
    if isinstance(v, str) and v.strip()[:1] in '[{':
        try:
            return json.loads(v)
        except json.JSONDecodeError as e:
            raise _Problem(f'could not read {v[:40]!r} as a list or mapping ({e.msg})')
    return v


def _date(v, allow_none=True):
    if v is None or (isinstance(v, str) and v.strip().lower() in ('', 'none', 'null')):
        if allow_none:
            return None
        raise _Problem('a date is required')
    if isinstance(v, (dt.date, pd.Timestamp)):
        return pd.Timestamp(v).normalize()
    if isinstance(v, str) and re.fullmatch(r'\s*\d{4}-\d{2}-\d{2}\s*', v):
        return pd.Timestamp(v.strip())
    raise _Problem(f'{v!r} is not a date', "write dates as 'YYYY-MM-DD' (in quotes in YAML)")


def _dates(v, allow_none=True):
    v = _maybe_json(v)
    if v is None:
        if allow_none:
            return None
        raise _Problem('a list of dates is required')
    if not isinstance(v, (list, tuple)) or len(v) < 2:
        raise _Problem('needs a list of at least two dates', "for example ['2025-08-01', '2026-02-15', '2026-09-01']")
    out = [_date(x, allow_none=False) for x in v]
    if len(set(out)) != len(out) or out != sorted(out):
        raise _Problem('dates must be distinct and in increasing order')
    return out


def _str_list(v, allow_none=False, choices=None):
    v = _maybe_json(v)
    if v is None and allow_none:
        return None
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, (list, tuple)) or not all(isinstance(x, str) for x in v):
        raise _Problem('needs a list of text values')
    if choices is not None:
        bad = [x for x in v if x not in choices]
        if bad:
            raise _Problem(f'unknown value(s) {bad}', f'choose from {list(choices)}')
    return list(v)


def _mapping(v):
    v = _maybe_json(v)
    if v is None:
        return {}
    if not isinstance(v, dict) or not all(isinstance(k, str) and isinstance(x, str) for k, x in v.items()):
        raise _Problem("needs a mapping of text to text, for example {'Old header': 'New header'}")
    return dict(v)


def _number(lo=None, hi=None, integer=False, allow_none=False):
    def check(v):
        if v is None and allow_none:
            return None
        if isinstance(v, str):
            try:
                v = float(v) if not integer else int(v)
            except ValueError:
                raise _Problem(f'{v!r} is not a number')
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise _Problem(f'{v!r} is not a number')
        if integer and float(v) != int(v):
            raise _Problem(f'{v!r} is not a whole number')
        if (lo is not None and v < lo) or (hi is not None and v > hi):
            raise _Problem(f'{v!r} is outside {lo}..{hi}')
        return int(v) if integer else float(v)
    return check


def _choice(*options):
    def check(v):
        if v not in options:
            raise _Problem(f'{v!r} is not one of {list(options)}')
        return v
    return check


def _bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, str) and v.strip().lower() in ('true', 'false', 'yes', 'no', '1', '0'):
        return v.strip().lower() in ('true', 'yes', '1')
    raise _Problem(f'{v!r} is not True or False')


def _text(allow_none=False):
    def check(v):
        if v is None and allow_none:
            return None
        if not isinstance(v, str) or not v.strip():
            raise _Problem('needs text')
        return v
    return check


def _paths(v):
    v = _maybe_json(v)
    if isinstance(v, str):
        return [v]
    if isinstance(v, (list, tuple)) and v and all(isinstance(x, str) for x in v):
        return list(v)
    raise _Problem('needs a file path or pattern, or a list of them')


def _tz(v):
    try:
        ZoneInfo(str(v))
    except (ZoneInfoNotFoundError, ValueError):
        raise _Problem(f'{v!r} is not a time zone name', "for example 'America/New_York' or 'America/Chicago'")
    return str(v)


def _date_format(v):
    if v is None:
        return None
    if not isinstance(v, str) or '%' not in v:
        raise _Problem(f'{v!r} is not a date format', "for example '%m/%d/%Y %I:%M %p'")
    return v


def _frequency(name, max_months):
    def check(v):
        try:
            return parse_frequency(v, name, max_months)
        except ConfigError as e:
            code, message, fix = e.problems[0]
            raise _Problem(message.split(': ', 1)[-1], fix, code)
    return check


def _cohort_map_issues(v):
    v = _maybe_json(v)
    if v == 'auto':
        return v
    return _str_list(v)


def _make_charts(v):
    if v == 'auto':
        return v
    return _bool(v)


SPEC = {
    'CASE_EXPORTS': _paths, 'CASE_SHEET': _text(), 'EQUIPMENT_LISTS': _paths, 'EQUIPMENT_SHEET': _text(),
    'EQUIPMENT_LIST_DATES': _mapping, 'EXTRACTED_AT': _date, 'DATA_START': _date, 'DATA_END': _date,
    'COLUMN_ALIASES': _mapping, 'CATEGORY_ALIASES': _mapping, 'REQUEST_TYPES_LOCAL': _text(allow_none=True),
    'UNMAPPED_POLICY': _choice('separate', 'fallback'), 'CASE_CLOCK_TZ': _tz, 'DATE_FORMAT': _date_format,
    'BASE_DIR': _text(allow_none=True), 'OUTPUT_DIR': _text(),
    'RERUN_FREQUENCY': _frequency('RERUN_FREQUENCY', 24), 'YEAR_START_MONTH': _number(1, 12, integer=True),
    'FISCAL_YEAR_NAMED_BY': _choice('end', 'start'), 'ANCHOR_DATE': _date, 'PERIOD_EDGES': _dates,
    'LATEST_PERIOD': _text(allow_none=True), 'BASELINE_MONTHS': _number(1, 60, integer=True, allow_none=True),
    'HISTORY_MONTHS': _number(1, 240, integer=True, allow_none=True), 'LABEL_LAG_DAYS': _number(0, 365, integer=True),
    'MAX_OPEN_SHARE': _number(0, 1), 'MAX_BLANK_CATEGORY_SHARE': _number(0, 1), 'MAX_UNMAPPED_SHARE': _number(0, 1),
    'STRATIFY_BY': lambda v: _str_list(v, choices=DIMENSIONS),
    'CATEGORY_DIMS': lambda v: _str_list(v, choices=('fleet',) + DIMENSIONS),
    'INSTALL_COHORT_WIDTH': _frequency('INSTALL_COHORT_WIDTH', 60), 'INSTALL_COHORT_START': _date,
    'INSTALL_COHORT_EDGES': _dates, 'MODEL_FILTER': lambda v: _str_list(v, allow_none=True),
    'POOL_SMALL_STRATA': _bool, 'MIN_TYPE_MONTHS': _number(0), 'MIN_CELL_MONTHS': _number(0),
    'THIRD_PARTY_PLANS': lambda v: _str_list(v) if v not in (None, []) else [],
    'MISSING_INSTALL_DATE': _choice('exclude', 'data_start'),
    'Q_CUT': _number(0, 1), 'WATCH_Q': _number(0, 1), 'MIN_CHANGE': _number(0), 'MIN_CONTRAST': _number(0),
    'CONTRAST_MONTHS': _number(1, 120, integer=True), 'MIN_EXPECTED': _number(0), 'MIN_BASELINE_TICKETS': _number(0),
    'MIN_ACCOUNTS': _number(0, integer=True), 'TAU2_FLOOR': _number(0), 'N_BOOT': _number(100, 100000, integer=True),
    'SEED': _number(0, integer=True), 'COHORT_MAP_ISSUES': _cohort_map_issues,
    'MAKE_CHARTS': _make_charts, 'MAKE_REPORT': _bool, 'REPORT_TITLE': _text(),
}
assert set(SPEC) == set(DEFAULTS)


# ------------------------------------------------------------------------------------------------ sources
def unknown_names(names):
    """[(code, message, fix)] for names that are not parameters, with the closest real name."""
    out = []
    for n in names:
        if n not in DEFAULTS:
            close = difflib.get_close_matches(n, list(DEFAULTS), n=1, cutoff=0.6)
            fix = f'did you mean {close[0]}?' if close else 'see the parameter list in trends/README.md'
            out.append(('E22', f'{n} is not a parameter', fix))
    return out


def collect(namespace):
    """Parameters from a notebook's globals(): every ALL-CAPS name. Unknown names (a misspelt papermill -p) stop
    the run with E22 instead of being ignored."""
    found = {k: v for k, v in namespace.items() if NAME_RE.match(k) and not callable(v)}
    problems = unknown_names(found)
    if problems:
        raise ConfigError(problems)
    return found


def load_file(path):
    """Parameters from a YAML (.yaml/.yml) or JSON (.json) file."""
    path = Path(path)
    if not path.exists():
        raise ConfigError([('E22', f'parameter file {path.name} not found', 'check the --params path')])
    text = path.read_text(encoding='utf-8')
    if path.suffix.lower() in ('.yaml', '.yml'):
        try:
            import yaml
        except ImportError:
            raise ConfigError([('E22', 'reading YAML parameter files needs PyYAML',
                                'pip install pyyaml, or use a .json parameter file')])
        data = yaml.safe_load(text) or {}
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ConfigError([('E22', f'{path.name} does not hold NAME: value pairs', None)])
    problems = unknown_names(data)
    if problems:
        raise ConfigError(problems)
    return data


def parse_sets(items):
    """--set NAME=VALUE pairs; values are read as YAML (or JSON) literals when possible, else as text."""
    out = {}
    for item in items or []:
        if '=' not in item:
            raise ConfigError([('E22', f'--set {item!r} needs NAME=VALUE', None)])
        k, v = item.split('=', 1)
        k = k.strip()
        try:
            import yaml
            out[k] = yaml.safe_load(v)
        except Exception:
            try:
                out[k] = json.loads(v)
            except json.JSONDecodeError:
                out[k] = v
    problems = unknown_names(out)
    if problems:
        raise ConfigError(problems)
    return out


# ------------------------------------------------------------------------------------------------ resolved
class Params:
    """Validated parameters (attributes with the parameter names) plus derived values:
    cadence, cohort_width, base_dir, output_dir, baseline_months, history_months."""

    def __init__(self, values, sources, base_dir):
        self._values = values
        self.sources = sources
        for k, v in values.items():
            setattr(self, k, v)
        self.base_dir = base_dir
        self.cadence = values['RERUN_FREQUENCY']
        self.cohort_width = values['INSTALL_COHORT_WIDTH']
        n = self.cadence.months if values['PERIOD_EDGES'] is None else 1
        self.baseline_months = values['BASELINE_MONTHS'] or max(12, n)
        self.history_months = values['HISTORY_MONTHS'] or max(24, 3 * n)
        self.output_dir = self.path(values['OUTPUT_DIR'])

    def path(self, p):
        p = Path(os.path.expanduser(str(p)))
        return p if p.is_absolute() else self.base_dir / p

    def public(self):
        """JSON-ready resolved parameters (paths as given, never resolved to absolute paths)."""
        def conv(v):
            if isinstance(v, Cadence):
                return v.canonical
            if isinstance(v, pd.Timestamp):
                return f'{v:%Y-%m-%d}'
            if isinstance(v, (list, tuple)):
                return [conv(x) for x in v]
            if isinstance(v, dict):
                return {k: conv(x) for k, x in v.items()}
            return v
        out = {k: conv(v) for k, v in self._values.items() if k != 'BASE_DIR'}
        out['BASELINE_MONTHS'], out['HISTORY_MONTHS'] = self.baseline_months, self.history_months
        return out

    def __getitem__(self, k):
        return self._values[k]


def resolve(overrides=None, base_dir=None, sources=None):
    """Validate DEFAULTS updated with `overrides`; returns Params or raises ConfigError listing every problem."""
    overrides = dict(overrides or {})
    problems = unknown_names(overrides)
    values, src = {}, {}
    for name, default in DEFAULTS.items():
        raw = overrides.get(name, default)
        src[name] = (sources or {}).get(name, 'override' if name in overrides else 'default')
        try:
            values[name] = SPEC[name](raw)
        except _Problem as p:
            problems.append((p.code, f'{name}: {p.message}', p.fix))
    if not problems:
        cad = values['RERUN_FREQUENCY']
        if values['BASELINE_MONTHS'] is not None and values['PERIOD_EDGES'] is None \
                and values['BASELINE_MONTHS'] < cad.months:
            problems.append(('E25', f'BASELINE_MONTHS ({values["BASELINE_MONTHS"]}) is shorter than one period '
                                    f'({cad.months} months)', 'leave BASELINE_MONTHS empty or make it longer'))
        if values['ANCHOR_DATE'] is not None and values['ANCHOR_DATE'].day > 28:
            problems.append(('E21', 'ANCHOR_DATE falls after the 28th', 'choose a day from 1 to 28'))
        bad_dims = [d for d in values['CATEGORY_DIMS'] if d != 'fleet' and d not in values['STRATIFY_BY']]
        if bad_dims:
            problems.append(('E22', f'CATEGORY_DIMS names {bad_dims}, which STRATIFY_BY does not include',
                             'add them to STRATIFY_BY or remove them from CATEGORY_DIMS'))
        if values['WATCH_Q'] < values['Q_CUT']:
            problems.append(('E22', 'WATCH_Q is smaller than Q_CUT', 'WATCH_Q should be at least Q_CUT'))
    if problems:
        raise ConfigError(problems)
    if base_dir is None:
        base_dir = values['BASE_DIR'] or os.environ.get('IPA_TRENDS_HOME') or TRENDS_DIR
    base = Path(os.path.expanduser(str(base_dir))).resolve()
    return Params(values, src, base)
