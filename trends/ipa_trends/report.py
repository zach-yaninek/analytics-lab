"""The report layer: charts, report.html, report.pdf and the email text for one run.

    build(result, tables, P, stage_dir, run_id) -> {'texts': [...], 'files': {...}, 'charts': [...]}

publish.publish calls build() inside its private staging folder, before the privacy scan. 'texts' holds every string
written: the text drawn on each chart, the visible text of report.html, the PDF's text pages and both email files,
so the scan covers all of it. Only the public aggregate tables are read: period labels, install cohorts, model and
family names, issue names and numbers.

  charts/*.png         IPA style (ipa_trends/style, copied from viz/style), 150 dpi; titles state the finding and
                       the footers carry the definitions; the time charts show the last HISTORY_MONTHS months (always
                       with the baseline and latest periods), while the tables and texts keep every period
  report.html          self-contained: inline CSS, charts as data URIs, no JavaScript, every value escaped
  report.pdf           matplotlib only: text summary pages (US Letter landscape), one page per chart, definitions
  email_summary.txt    at most 15 lines to paste into a message; email_summary.html is the same with inline styles
                       and no images

Charts and the PDF need matplotlib and MAKE_CHARTS 'auto' or True; without them the report and the email say so.
MAKE_REPORT False draws the charts only. With MAKE_CHARTS 'auto' a chart that fails is left out with a note; with
True the error stops the run. Wording: flags are screening flags for follow-up, not proof of a problem.
"""
import base64
import contextlib
import html
import io
import math
import textwrap
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

import numpy as np
import pandas as pd

from . import METHOD_VERSION, __version__
from . import cadence as CAD
from . import cohorts as COH
from . import style as STYLE
from .definitions import followups_copy as FU
from .inputs import UNKNOWN, UNMAPPED
from .rates import DIM_LABEL

FILES = {'report_html': 'report.html', 'report_pdf': 'report.pdf', 'email_txt': 'email_summary.txt',
         'email_html': 'email_summary.html'}
FLAGGED = ('higher', 'lower')
WATCH = ('watch_higher', 'watch_lower')
STANDS = ('stands_out_higher', 'stands_out_lower')
NOT_ISSUES = (FU.NO_CAT, UNMAPPED)
UNLISTED_NOTE = 0.05        # an unlisted share above this is mentioned in the email and the key messages
MAX_FOREST_ROWS = 15
MAX_EMAIL_LINES = 15
PAGE = (11.0, 8.5)          # US Letter landscape, inches
# months of final history an interior cohort's same-age check needs: the cohort rule's own constant
SAME_AGE_HISTORY_MONTHS = getattr(COH, 'SAME_AGE_HISTORY_MONTHS', 24)


class _Skip(Exception):
    """A chart that has nothing to show; the message says why (shown in the report)."""


@dataclass
class Chart:
    name: str
    rel: str
    path: Path
    title: str
    caption: str


# ================================================================================================ entry point
def build(result, tables, P, stage_dir, run_id):
    """Write charts/*.png, report.html, report.pdf and the email text into stage_dir; return what was written."""
    stage = Path(stage_dir)
    R = _Run(result, tables, P, run_id)
    S = STYLE.load() if P.MAKE_CHARTS in ('auto', True) else None
    if P.MAKE_CHARTS is False:
        R.no_charts = 'charts are switched off (MAKE_CHARTS = False)'
    elif S is None:
        R.no_charts = 'matplotlib is not installed'
    charts = _draw_charts(S, R, stage / 'charts') if S is not None else []
    texts = [t for drawn in S.TEXTS.values() for t in drawn] if S is not None else []
    files = {}
    if P.MAKE_REPORT:
        files['report_html'] = FILES['report_html']
        if S is not None:
            texts += _write_pdf(S, R, charts, stage / FILES['report_pdf'])
            files['report_pdf'] = FILES['report_pdf']
        texts += _write_html(R, charts, stage / FILES['report_html'])
        texts += _write_email(R, stage, pdf=S is not None)
        files['email_txt'], files['email_html'] = FILES['email_txt'], FILES['email_html']
    return {'texts': [t for t in texts if isinstance(t, str) and t.strip()], 'files': files,
            'charts': [c.rel for c in charts]}


# ================================================================================================ the run's facts
def _table(tables, name, need=None):
    df = tables.get(name) if isinstance(tables, dict) else None
    if df is None or len(df) == 0 or (need is not None and need not in df.columns):
        return pd.DataFrame()
    return df.reset_index(drop=True)


def _finite(v):
    try:
        return v is not None and bool(np.isfinite(float(v)))
    except (TypeError, ValueError):
        return False


def _r(v):
    """A rate for a chart label: 18.7, 3.93, 0.41."""
    return '' if not _finite(v) else (f'{v:.1f}' if abs(v) >= 10 else f'{v:.2f}')


def _n(k, noun, plural=None):
    return f'{k:,} {noun if k == 1 else (plural or noun + "s")}'


def _pct(ratio):
    return 100 * (float(ratio) - 1)


def _interval(lo, hi):
    if not (_finite(lo) and _finite(hi)):
        return ''
    return f'{_pct(lo):+.0f}% to {_pct(hi):+.0f}%'


def _share(v):
    """0.173 -> '17%', 0.05 -> '5%', 0.025 -> '2.5%'."""
    p = 100 * float(v)
    return f'{p:.0f}%' if p >= 9.95 or abs(p - round(p)) < 0.05 else f'{p:.1f}%'


def _cohort_phrase(label):
    """'<label> installs', 'installs before <year>', 'installs from <month year>'."""
    s = str(label)
    if s.startswith('Before '):
        return f'installs before {s[7:]}'
    if s.startswith('From '):
        return f'installs from {s[5:]}'
    return f'{s} installs'


def _text(v, default=''):
    """A text field, or `default` when it is missing (NaN, None or blank)."""
    return v if isinstance(v, str) and v.strip() else default


def _cap(text):
    return text[:1].upper() + text[1:]


def _and(items):
    """'A', 'A and B', 'A, B and C'."""
    items = [str(i) for i in items]
    return ' and '.join(items) if len(items) <= 2 else ', '.join(items[:-1]) + ' and ' + items[-1]


def _kind(cadence):
    """'Monthly report', 'Quarterly report', 'Report every 5 months'."""
    adj = str(cadence.adjective)
    return f'Report {adj}' if ' ' in adj else f'{adj[:1].upper()}{adj[1:]} report'


def _baseline_phrase(cadence, used, intended):
    """The baseline a cell was compared with: 'the previous four quarters', or 'three of the previous four quarters
    (those with complete Category labels)' when the cell's baseline left out periods whose Category labels are
    incomplete. `used`: the cell's baseline_periods_used; `intended`: the run's full baseline (its final periods).
    Behaves exactly like compare.baseline_phrase."""
    used, intended = int(used), int(intended)
    if used <= 0:
        return 'no baseline'
    if used >= intended:
        return cadence.previous(used)
    word = CAD.NUMBER_WORDS[used] if used < len(CAD.NUMBER_WORDS) else str(used)
    return f'{word} of {cadence.previous(intended)} (those with complete Category labels)'


def _x(v):
    """A ratio threshold: 1.5 -> '1.5x', 1.25 -> '1.25x', 0.667 -> '0.67x', 0.8 -> '0.8x'."""
    return f'{float(v):.2f}'.rstrip('0').rstrip('.') + 'x'


def _issue_noun(issue):
    return 'Unplanned' if issue == 'All unplanned tickets' else str(issue)


class _Run:
    """The run's summary, tables and wording, shared by the charts, the report and the email."""

    def __init__(self, result, tables, P, run_id):
        self.result, self.P, self.run_id = result, P, run_id
        self.s = result.summary or {}
        self.facts = result.facts or {}
        self.warnings = list(result.warnings or [])
        self.cad = P.cadence
        self.latest = self.s.get('latest_label')
        self.no_charts = None
        self.chart_notes = []
        self.periods = _table(tables, 'periods', 'period_key')
        self.rates = _table(tables, 'rates', 'rate_per_100')
        self.changes = _table(tables, 'changes', 'status')
        self.contrasts = _table(tables, 'cohort_contrasts', 'status')
        self.dq = _table(tables, 'data_quality', 'period_key')
        self.strata = _table(tables, 'strata', 'stratum_dim')
        self.defs_hash = next((str(df.definitions_hash.iloc[0]) for df in (tables or {}).values()
                               if isinstance(df, pd.DataFrame) and len(df) and 'definitions_hash' in df), '')
        p = self.periods
        labels = [str(v) for v in p.label] if len(p) else []
        status = [str(v) for v in p.status] if len(p) else []
        roles = [str(v) for v in p.role] if len(p) and 'role' in p else [''] * len(labels)
        latest = roles.index('latest') if 'latest' in roles else None
        baseline = [i for i, r in enumerate(roles) if r == 'baseline']
        # the time charts' period axis (labels, status and positions below refer to it): the last HISTORY_MONTHS
        # months, always with the baseline and latest periods; tables and texts keep every period
        self.view = self._history(baseline + ([latest] if latest is not None else []))
        self.hidden_periods = len(labels) - len(self.view)
        self.labels = [labels[i] for i in self.view]
        self.status = [status[i] for i in self.view]
        self.view_keys = [str(p.period_key.iloc[i]) for i in self.view]
        self.latest_pos = self.view.index(latest) if latest is not None else None
        self.baseline_pos = [self.view.index(i) for i in baseline]
        src = self.rates if len(self.rates) else (self.changes if len(self.changes) else self.contrasts)
        self.issue_order = {k: i for i, k in enumerate(dict.fromkeys(src.issue_key))} if len(src) else {}
        self.k = len(self.s.get('baseline_labels') or [])
        self.previous = self.cad.previous(self.k) if self.k else 'the baseline'
        # baseline periods left out of issue-level comparisons because their Category labels are incomplete
        self.dropped = [labels[i] for i in baseline if 'label_ok' in p and p.label_ok.iloc[i] in (False, 'False')]
        self.window = self.s.get('cohort_window') or ''
        self.window_n = len((self.facts.get('cohorts') or {}).get('window') or [])
        self.fleet = self.change_row('fleet', 'all')
        self.flags = self._sorted_changes(FLAGGED)
        self.watch = self._sorted_changes(WATCH)
        self.stands = self._stands()
        self.window_text = self.window or 'the cohort window'
        self.window_note = self._window_note()

    def _history(self, keep):
        """Positions of the periods on the time charts' axis: those starting in the last HISTORY_MONTHS months of the
        grid, extended back to the earliest period in `keep` (the baseline and the latest period)."""
        p = self.periods
        if p.empty:
            return []
        months = getattr(self.P, 'history_months', None)
        if not months or 'period_start' not in p or 'period_end' not in p:
            return list(range(len(p)))
        start, end = pd.to_datetime(p.period_start), pd.to_datetime(p.period_end)
        last = len(p) - 1
        if getattr(self.P, 'LATEST_PERIOD', None) and keep:
            last = max(keep)            # a back-run reports as of its latest period: later periods stay off the axis
        cut = end.iloc[last] - pd.DateOffset(months=int(months))
        first = min([i for i in range(last + 1) if start.iloc[i] >= cut] + list(keep) + [last])
        return list(range(first, last + 1))

    def _window_note(self):
        """'' or 'for issues, only the 3 final quarters with complete Category labels' when the issue-level cohort
        rows were compared over fewer window periods than all tickets (their own window_label, when it differs, is
        added)."""
        cc = self.contrasts
        if cc.empty or not self.window_n or not {'issue_level', 'window_periods'} <= set(cc.columns):
            return ''
        short = cc[(cc.issue_level != 'all') & (cc.window_periods.astype(float) < self.window_n)]
        if short.empty:
            return ''
        r = short.iloc[0]
        own = self.row_window(r)
        k = int(r.window_periods) if _finite(r.window_periods) else 0
        if k == 0:
            return f'issues are not compared: no final {self.noun} in the window has complete Category labels'
        named = own.replace(' (incomplete Category labels)', '')         # 'A to B except C' says it once
        return (f'for issues, only the {_n(k, "final " + self.noun, "final " + self.plural)} with complete Category '
                f'labels' + (f': {named}' if own != self.window_text else ''))

    def _order(self, df):
        """Catalog order of each row's issue (the public tables carry no order column; the rates table lists
        issues in catalog order)."""
        return df.issue_key.map(self.issue_order).fillna(len(self.issue_order)).astype(int)

    # ---- rows
    def change_row(self, dim, key, stratum=None):
        c = self.changes
        if c.empty:
            return None
        m = (c.stratum_dim == dim) & (c.issue_key == key)
        if stratum is not None:
            m &= c.stratum == stratum
        return c[m].iloc[0] if m.any() else None

    def _sorted_changes(self, statuses):
        c = self.changes
        if c.empty:
            return c
        f = c[c.status.isin(statuses)].copy()
        f['_fleet'] = (f.stratum_dim != 'fleet').astype(int)
        f['_o'] = self._order(f)
        return f.sort_values(['_fleet', 'q_value', '_o'], kind='mergesort').drop(columns=['_fleet', '_o'])

    def _stands(self):
        cc = self.contrasts
        if cc.empty:
            return cc
        st = cc[cc.status.isin(STANDS)].copy()
        st['_strength'] = -np.abs(np.log(st.crude_ratio.astype(float).clip(lower=1e-9)))
        st['_o'] = self._order(st)
        return st.sort_values(['_strength', '_o'], kind='mergesort').drop(columns=['_strength', '_o'])

    def series(self, dim, key, stratum=None, every=False):
        """Rates of one cell for each period of the time charts' axis (every period with every=True), in period
        order (NaN where the period has no row)."""
        out = self.periods[['period_key', 'label', 'status']].copy()
        out['role'] = self.periods.role if 'role' in self.periods else ''
        if not every:
            out = out.iloc[self.view]
        rt = self.rates
        sub = rt[(rt.stratum_dim == dim) & (rt.issue_key == key)] if len(rt) else rt
        if stratum is not None and len(sub):
            sub = sub[sub.stratum == stratum]
        sub = sub.drop_duplicates('period_key').set_index('period_key') if len(sub) else sub
        for col, src in (('rate', 'rate_per_100'), ('lo', 'ci_lo'), ('hi', 'ci_hi'), ('months', 'machine_months'),
                         ('tickets', 'tickets')):
            out[col] = out.period_key.map(sub[src]).astype(float) if len(sub) else np.nan
        return out.reset_index(drop=True)

    def cohort_order(self):
        order = [str(c) for c in (self.facts.get('cohort_bins') or [])]
        if not order and len(self.strata):
            order = [str(c) for c in self.strata[self.strata.stratum_dim == 'install_cohort'].stratum]
        return [c for c in order if c != UNKNOWN]

    def cohort_issues(self, limit=5):
        """Issues for the cohort charts: COHORT_MAP_ISSUES when it is a list; otherwise issues with a cohort that
        stands out (strongest first), then the issues whose crude ratios spread most across cohorts."""
        cc = self.contrasts
        if cc.empty:
            return []
        names = cc.drop_duplicates('issue_key')
        names = names.assign(_o=self._order(names)).sort_values('_o', kind='mergesort')
        cand = names[(names.issue_key != 'all') & ~names.issue.isin(NOT_ISSUES)]
        want = self.P.COHORT_MAP_ISSUES
        if isinstance(want, (list, tuple)):
            keys, unknown = [], []
            for w in want:
                hit = cand[cand.issue.astype(str).str.lower() == str(w).strip().lower()]
                keys += [k for k in hit.issue_key if k not in keys]
                if hit.empty:
                    unknown.append(str(w))
            note = f'COHORT_MAP_ISSUES names no issue of this run: {", ".join(unknown)}.'
            if unknown and note not in self.chart_notes:
                self.chart_notes.append(note)
            return keys[:limit]
        keys = []
        for k in self.stands.issue_key if len(self.stands) else []:
            if k in set(cand.issue_key) and k not in keys:
                keys.append(k)
        el = cc[cc.eligible.astype(bool) & cc.issue_key.isin(set(cand.issue_key))
                & np.isfinite(cc.crude_ratio.astype(float)) & (cc.crude_ratio.astype(float) > 0)]
        spread = []
        for k, g in el.groupby('issue_key', sort=False):
            if len(g) >= 2:
                lr = np.log(g.crude_ratio.astype(float))
                spread.append((-(lr.max() - lr.min()), self.issue_order.get(k, 0), k))
        keys += [k for _, _, k in sorted(spread) if k not in keys]
        return keys[:limit]

    def issue_name(self, key):
        for df in (self.contrasts, self.changes, self.rates):
            if len(df) and 'issue_key' in df:
                m = df.issue_key == key
                if m.any():
                    return str(df.issue[m].iloc[0])
        return str(key)

    # ---- wording
    @property
    def noun(self):
        return self.cad.noun

    @property
    def plural(self):
        return self.cad.plural

    def stratum_text(self, r, style='paren'):
        """'' for the fleet; ' (install cohort <label>)' or 'Install cohort: <label>'."""
        if r.stratum_dim == 'fleet':
            return '' if style == 'paren' else 'Fleet'
        s = str(r.stratum)
        if s.startswith('Other models ('):
            s = 'other models (pooled)'
        dim = DIM_LABEL.get(r.stratum_dim, str(r.stratum_dim))
        return f' ({dim.lower()} {s})' if style == 'paren' else f'{dim}: {s}'

    def vs(self, ratio, previous=None):
        p = _pct(ratio)
        previous = previous or self.previous
        if round(abs(p)) == 0:
            return f'level with {previous}'
        return f'{abs(p):.0f}% {"above" if p > 0 else "below"} {previous}'

    def baseline_text(self, r):
        """The baseline one change row was compared with, from its own baseline_periods_used: issue-level rows leave
        out baseline periods whose Category labels are incomplete."""
        used = getattr(r, 'baseline_periods_used', None)
        return _baseline_phrase(self.cad, used, self.k) if _finite(used) else self.previous

    def baseline_summary(self, rows):
        """The baselines of these change rows: one phrase, or one for all unplanned tickets and one for issues."""
        rows = rows if rows is not None else self.changes
        phrases = {}
        for r in rows.itertuples():
            phrases.setdefault('all' if r.issue_key == 'all' else 'issues', self.baseline_text(r))
        distinct = list(dict.fromkeys(phrases.values()))
        if len(distinct) <= 1:
            return distinct[0] if distinct else self.previous
        return f'{phrases["all"]} for all unplanned tickets; {phrases["issues"]} for issues'

    def sustained_text(self, r):
        """'' or 'also flagged last quarter' / 'also on the watch list last quarter': a sustained cell was flagged
        or on the watch list in the same direction in the previous period (its previous_status says which)."""
        s = getattr(r, 'sustained', False)
        if not (isinstance(s, (bool, np.bool_)) and bool(s)):
            return ''
        prev = _text(getattr(r, 'previous_status', None))
        if prev in FLAGGED:
            return f'also flagged last {self.noun}'
        if prev in WATCH:
            return f'also on the watch list last {self.noun}'
        return f'also flagged or on the watch list last {self.noun}'

    def beyond(self, rows=None):
        """Tested cells left unflagged although their interval excludes no change, as (many, small, watch): over the
        practical threshold but not after the correction for testing many cells; under the threshold; on the watch
        list."""
        rows = self.changes if rows is None else rows
        many = small = watch = 0
        for r in rows.itertuples() if len(rows) else ():
            if r.status in FLAGGED or r.status == 'not_tested' or self.quiet(r) == 'normal':
                continue
            if r.status in WATCH:
                watch += 1
            elif self.quiet(r) == 'many':
                many += 1
            else:
                small += 1
        return many, small, watch

    def history_note(self, source='rates.csv'):
        """'' or a note that the chart leaves out the periods before its axis starts (HISTORY_MONTHS)."""
        if not self.hidden_periods or not self.labels:
            return ''
        return (f'{_cap(self.plural)} before {self.labels[0]} are not shown (HISTORY_MONTHS); {source} holds every '
                f'{self.noun}.')

    def quiet(self, r):
        """Why a tested cell was not flagged: 'normal' (its interval includes no change), 'small' (clearly
        changed but under the practical threshold) or 'many' (over the threshold, but not after the correction for
        testing many cells)."""
        if not (_finite(r.ci_lo) and _finite(r.ci_hi)) or r.ci_lo <= 1 <= r.ci_hi:
            return 'normal'
        return 'small' if abs(_pct(r.change_ratio)) < 100 * self.P.MIN_CHANGE else 'many'

    def quiet_text(self, r):
        why = self.quiet(r)
        if why == 'normal':
            return f'within normal {self.cad.variation}'
        if why == 'small':
            return f'under the {100 * self.P.MIN_CHANGE:g}% practical threshold, so not flagged'
        return 'not flagged: with this many cells tested, it could still be chance'

    def defs(self, baseline=True, issues=False):
        out = [("Installed machine-month: one machine on IPA's equipment list for 30.4 days (365.25/12); machines "
               "count from their install date (or first ticket) until the data end or removal."),
               ('Unplanned ticket: every case except planned work (preventative maintenance, installation), cancelled '
               'requests and duplicates.')]
        if baseline:
            latest = self.latest or f'the latest final {self.noun}'
            out.append(f'Baseline: the final {self.plural} in the {self.P.baseline_months} months before {latest}'
                       + (self.dropped_note() if issues else '') + '.')
        return out

    def dropped_note(self):
        """'' or '; issue-level comparisons leave out 2024 Q1 (Category labels incomplete)'."""
        if not self.dropped:
            return ''
        return f'; issue-level comparisons leave out {_and(self.dropped)} (Category labels incomplete)'

    def dropped_text(self):
        """'2024 Q1 is left out of issue-level baselines (Category labels incomplete)'."""
        verb = 'is' if len(self.dropped) == 1 else 'are'
        return f'{_and(self.dropped)} {verb} left out of issue-level baselines (Category labels incomplete)'

    def hollow_note(self):
        return (f'Hollow markers: {self.plural} that are not final yet (provisional, in progress or partial); their '
                'rates can still change.')

    def ci_note(self, change=False):
        base = (f"95% intervals: account bootstrap ({self.P.N_BOOT:,} resamples of IPA's accounts, so tickets that "
                'cluster at a few sites widen the interval); cells with fewer than 10 accounts or no tickets use the '
                'wider of the bootstrap and Byar intervals.')
        if change:
            base = (f"95% intervals of the change: account bootstrap ({self.P.N_BOOT:,} resamples of IPA's accounts) "
                    f'plus the between-{self.noun} variance estimated from the history.')
        return base

    def fleet_line(self):
        """One sentence on the fleet rate against its baseline (key messages, PDF and email)."""
        if self.latest is None:
            return (f'No reporting {self.noun} is final yet, so nothing is compared; every rate shown can still '
                    'change.')
        r = self.fleet
        if r is None or not _finite(r.rate_latest):
            return f'The fleet rate for {self.latest} is not available.'
        rate = f'{r.rate_latest:.2f} unplanned tickets per 100 installed machine-months in {self.latest}'
        if r.status == 'not_tested' or not _finite(r.change_ratio):
            why = _text(r.not_tested_reason, 'not tested')
            base = f' (baseline {r.rate_baseline:.2f})' if _finite(r.rate_baseline) else ''
            return f'Fleet: {rate}{base}; not compared: {why}.'
        ci = f'95% interval {_interval(r.ci_lo, r.ci_hi)}'
        if r.status in FLAGGED:
            verdict = (f'beyond normal {self.cad.variation}: a screening flag for follow-up, not proof of a '
                       'problem')
        elif r.status in WATCH:
            verdict = 'larger than usual, but it could still be chance (watch list)'
        else:
            verdict = self.quiet_text(r)
        extra = self.sustained_text(r)
        return (f'Fleet: {rate}, {self.vs(r.change_ratio, self.baseline_text(r))} ({ci}), {verdict}'
                + (f'; {extra}' if extra else '') + '.')

    def none_flagged(self):
        """The sentence for a run with no flag: nothing beyond normal variation; nothing flagged although some
        intervals exclude no change; or nothing could be tested."""
        tested = int(self.s.get('tested', 0) or 0)
        if tested == 0:
            why = _text(self.fleet.not_tested_reason if self.fleet is not None else None, 'too little final history')
            return f'No change could be tested in {self.latest}: {why}.'
        many, small, watch = self.beyond()
        if not (many or small or watch):
            return (f'No change in {self.latest} was beyond normal {self.cad.variation} '
                    f'({_n(tested, "issue and breakdown cell")} tested).')
        thr = f'{100 * self.P.MIN_CHANGE:g}%'
        parts = [f'No change in {self.latest} was flagged (a flag needs a q-value below {self.P.Q_CUT:g} after '
                 f'correcting for {_n(tested, "tested cell")}, and a change of at least {thr})']
        if many:
            parts.append(f'{_n(many, "change")} with {"an interval" if many == 1 else "intervals"} excluding no change '
                         'could still be chance')
        if small:
            parts.append(f'{_n(small, "change")} beyond normal {self.cad.variation} {"was" if small == 1 else "were"} '
                         f'under the {thr} practical threshold')
        return '; '.join(parts) + '.'

    def change_item(self, r):
        """A flagged or watch-list cell in one line (email, PDF)."""
        extra = self.sustained_text(r)
        base = self.baseline_text(r)
        ci = f'95% interval {_interval(r.ci_lo, r.ci_hi)}'
        return (f'{r.issue}{self.stratum_text(r)}: {r.rate_latest:.2f} per 100 installed machine-months, '
                f'{self.vs(r.change_ratio, base)}' + (f'; {ci}' if base.endswith(')') else f' ({ci})')
                + (f'; {extra}' if extra else '') + '.')

    def row_window(self, r):
        """The cohort window one contrast row was compared over (its own window_label), else the run's."""
        return _text(getattr(r, 'window_label', None), self.window_text)

    def window_phrase(self):
        """The run's cohort window, with the issue-level window when it is shorter: '2025 Q4 to 2026 Q3' or
        '2024 Q1 to 2024 Q4 (for issues, only the 3 final quarters with complete Category labels)'."""
        return self.window_text + (f' ({self.window_note})' if self.window_note else '')

    def cohort_item(self, r):
        """A cohort call-out in one line, over the row's own window (window_label): the engine's sentence when it
        names that window, else the same facts written here."""
        s = getattr(r, 'sentence', None)
        own = self.row_window(r)
        if isinstance(s, str) and s and own in s:
            return s
        text = (f'{r.issue}, {_cohort_phrase(r.install_cohort)}: {r.rate_per_100:.2f} per 100 installed '
                f'machine-months over {own}, {r.crude_ratio:.1f}x the rest of the fleet')
        newer, older, same = (getattr(r, k, None) for k in ('newer_ratio', 'older_ratio', 'same_age_ratio'))
        if getattr(r, 'position', '') == 'newest':
            text += f' and {same:.1f}x other cohorts at the same age' if _finite(same) else ''
        elif _finite(newer) and _finite(older):
            text += f' ({newer:.1f}x newer installs, {older:.1f}x older installs)'
        return text + '.'

    def not_final(self):
        """[(label, status, reason)] for the periods that are not final."""
        p = self.periods
        if p.empty:
            return []
        nf = p[p.status != 'final']
        return [(str(r.label), str(r.status).replace('_', ' '), str(r.status_reason or ''))
                for r in nf.itertuples()]

    def not_final_text(self):
        """'2026 Q4 (in progress) is not final yet' or '8 months are not final yet, the latest ...'."""
        nf = self.not_final()
        if len(nf) > 3:
            return (f'{len(nf)} {self.plural} are not final yet, the latest '
                    + ' and '.join(f'{lab} ({st})' for lab, st, _ in nf[-2:]))
        if nf:
            return (', '.join(f'{lab} ({st})' for lab, st, _ in nf) + (' is' if len(nf) == 1 else ' are')
                    + ' not final yet')
        return ''

    def data_notes(self):
        """Short data caveats: periods not final, the unlisted share, warnings, charts not drawn."""
        notes = []
        if self.not_final():
            notes.append(_cap(self.not_final_text()) + '.')
        if self.latest is not None and self.dropped:
            notes.append(self.dropped_text() + '.')
        u = self.s.get('latest_unlisted_share')
        if self.latest is not None and _finite(u) and u > UNLISTED_NOTE:
            notes.append(f'{_share(u)} of {self.latest} tickets were on machines missing from the equipment list, '
                         'so they are not in the rates.')
        if self.warnings:
            codes = sorted({str(w.get('code')) for w in self.warnings})
            notes.append(f'{_n(len(self.warnings), "data warning")} ({", ".join(codes)}); see Data quality.')
        if self.no_charts:
            notes.append(f'Charts and the PDF were not made because {self.no_charts}.')
        return notes

    def key_messages(self):
        """3-6 plain bullets for the top of the report."""
        out = [self.fleet_line()]
        if self.latest is None:
            for lab, st, why in self.not_final()[-3:]:
                out.append(f'{lab} is {st}' + (f': {why}.' if why else '.'))
            if self.warnings:
                out.append(f'{_n(len(self.warnings), "data warning")}; see Data quality.')
            return out[:6]
        L = self.latest
        nflag = len(self.flags)
        if nflag:
            heads = [f'{r.issue}{self.stratum_text(r)} {_pct(r.change_ratio):+.0f}%' for r in
                     self.flags.head(4).itertuples()]
            more = f' and {nflag - 4} more' if nflag > 4 else ''
            out.append(f'{_n(nflag, "change")} flagged for follow-up in {L}: {"; ".join(heads)}{more}. These are '
                       'screening flags for follow-up, not proof of a problem.')
        else:
            out.append(self.none_flagged())
        if len(self.stands):
            top = self.cohort_item(self.stands.iloc[0])         # the item names its own window
            n = len(self.stands)
            if n > 1:
                out.append(f'{n} install-cohort call-outs. The strongest: {top}')
            else:
                out.append(f'One install-cohort call-out: {top}')
        elif len(self.contrasts):
            out.append(f'No install cohort stands out from the rest of the fleet over {self.window_phrase()}.')
        if len(self.watch):
            one = len(self.watch) == 1
            out.append(f'{_n(len(self.watch), "more change")} {"is" if one else "are"} on the watch list: reported, '
                       f'not flagged, because {"it" if one else "they"} could still be chance.')
        notes = self.data_notes()
        if notes:
            out.append('Data caveats: ' + ' '.join(notes))
        return out[:6]

    def category_scope(self):
        """Where Category-level rates exist (CATEGORY_DIMS): 'for the fleet and by install cohort', or ''."""
        dims = list(getattr(self.P, 'CATEGORY_DIMS', None) or [])
        others = [DIM_LABEL.get(d, d).lower() for d in dims if d != 'fleet']
        parts = (['for the fleet'] if 'fleet' in dims else []) + ([f'by {_and(others)}'] if others else [])
        return ' and '.join(parts)

    def group_definition(self):
        """What a request group is: one of the analysed groups, or one of the two never-tested groups."""
        n = len(FU.PRIMARY)
        nine = CAD.NUMBER_WORDS[n] if n < len(CAD.NUMBER_WORDS) else str(n)
        return (f"the ticket's Trouble Code and Category mapped by the project's request-type reference to one of "
                f'{nine} analysed groups (monitoring-template tickets form the Monitoring group). Tickets with a '
                f'blank Category whose Trouble Code does not decide the group form a separate group, {FU.NO_CAT}, and '
                f'combinations missing from the reference an {UNMAPPED} group; neither is tested.')

    def cohort_rule(self, form='full'):
        """The install-cohort call-out rule in words, with this run's thresholds (cohorts.contrasts applies it):
        'full' (method), 'definition', 'lede' (the report's cohort section) or 'short' (chart footer)."""
        P = self.P
        hi, side = 1 + P.MIN_CONTRAST, 1 + P.MIN_CONTRAST / 2
        months = SAME_AGE_HISTORY_MONTHS
        peak = f'at least {_x(hi)} the rest of the fleet and at least {_x(side)} both newer and older installs'
        same_age = (f'when at least {months} months of final history exist and the same-age ratio can be estimated, '
                    f'the cohort must also be at least {_x(side)} machines of the same age in other cohorts')
        thin = getattr(COH, 'NEWER_SIDE_MIN_EXPECTED', 40)
        newest = (f'the newest cohort with at least {P.MIN_EXPECTED:g} tickets expected, and any cohort whose newer '
                  f'installs would expect fewer than {thin:g} tickets (too few to compare with), is compared with the '
                  f'rest of the fleet and with machines of the same age in other cohorts (at least {_x(hi)} each); '
                  'newer cohorts are still filling up and are shown but not compared')
        together = (f'All the comparisons a call-out needs must hold together: its q-value (the Benjamini-Hochberg-'
                    f'corrected largest p-value of those comparisons) must be below {P.Q_CUT:g}.')
        mirror = f"'Lower' is the mirror image (at most {_x(1 / hi)} and {_x(1 / side)})."
        if form == 'short':
            return (f'Install cohort: machines grouped by install date. A cohort stands out when it is {peak} (a peak; '
                    f'with at least {months} months of final history, also at least {_x(side)} machines of the same '
                    f'age elsewhere); the newest cohort with enough expected tickets (or with too few newer installs '
                    f'to compare with) needs at least {_x(hi)} both the rest of the fleet and machines of the same age '
                    'in other cohorts. The q-value (the Benjamini-Hochberg-'
                    f'corrected largest p-value of those comparisons) must be below {P.Q_CUT:g}.')
        if form == 'definition':
            return (f'A cohort with newer and older installs: {peak} (a peak in the install-date profile) and, when at '
                    f'least {months} months of final history exist and the same-age ratio can be estimated, at least '
                    f'{_x(side)} machines of the same age in other cohorts. The newest cohort with at least '
                    f'{P.MIN_EXPECTED:g} tickets expected, and a cohort whose newer installs are too few to compare '
                    f'with: at least {_x(hi)} both the rest of the fleet and machines of the same age in other cohorts '
                    '(newer cohorts are still filling up and are not compared). All the '
                    'comparisons must hold together: the q-value (the '
                    f'Benjamini-Hochberg-corrected largest of their p-values) is below {P.Q_CUT:g}. {mirror}')
        if form == 'lede':
            return (f'A cohort stands out when its rate is {peak}: a peak in the install-date profile. A peak rules '
                    'out an age effect that rises or falls steadily with machine age, but a rise confined to certain '
                    f'ages (a wear-out window) could still produce one; the same-age check rules that out: {same_age}. '
                    f'{_cap(newest)}. {together}')
        return (f"Install cohorts: each cohort's rate over the last {P.CONTRAST_MONTHS} months of final {self.plural} "
                'is compared with the rest of the fleet and with all newer and all older installs, and, over the '
                'whole final history, with machines of the same age in other cohorts. A cohort with both newer and '
                f'older installs stands out when it is {peak}: a peak in the install-date profile. A peak rules out an '
                'age effect that rises or falls steadily with machine age, but not a rise confined to certain ages (a '
                f'wear-out window); the same-age check rules that out: {same_age}. {_cap(newest)}. The oldest, pooled '
                f'cohort and machines with an unknown install date are never called out. {together} {mirror}')

    def history_months(self):
        """{'all': months, 'labels': months}: the span of the final periods up to the latest one, behind the cohort
        comparison of all unplanned tickets and of issues (whose periods need complete Category labels). The
        cohorts' own figures when the engine reports them, else counted from the periods table; {} without a latest
        final period."""
        info = (self.facts.get('cohorts') or {}).get('history_months')
        if isinstance(info, dict) and info and all(_finite(v) for v in info.values()):
            return {str(k): int(v) for k, v in info.items()}
        p = self.periods
        if self.latest is None or p.empty or not {'period_start', 'period_end', 'status', 'role'} <= set(p.columns):
            return {}
        roles = [str(v) for v in p.role]
        if 'latest' not in roles:
            return {}
        final = (np.arange(len(p)) <= roles.index('latest')) & (p.status.astype(str) == 'final').to_numpy()
        sets = {'all': final}
        if 'label_ok' in p:
            sets['labels'] = final & p.label_ok.isin([True, 'True']).to_numpy()
        out = {}
        for name, m in sets.items():
            idx = np.flatnonzero(m)
            if len(idx):            # whole months from the first period's start to the last one's (exclusive) end
                a, b = pd.Timestamp(p.period_start.iloc[idx[0]]), pd.Timestamp(p.period_end.iloc[idx[-1]])
                out[name] = int((b.year - a.year) * 12 + b.month - a.month - (b.day < a.day))
        return out

    def same_age_note(self, gaps_only=False):
        """'' or whether this run's final history is long enough for the same-age check of cohorts with newer and
        older installs (gaps_only: only when it is not, for all unplanned tickets or for issues)."""
        h = self.history_months()
        if self.contrasts.empty or not h:
            return ''
        need = SAME_AGE_HISTORY_MONTHS
        m_all = h.get('all', min(h.values()))
        issues = 'issue_level' in self.contrasts and (self.contrasts.issue_level != 'all').any()
        m_lab = h.get('labels', m_all) if issues else m_all
        if min(m_all, m_lab) >= need:
            return '' if gaps_only else f'This run has {m_all} months of final history, so the same-age check applies.'
        if m_all >= need:
            return (f'This run has {m_all} months of final history, but only {m_lab} with complete Category labels, '
                    'so for issues the same-age check does not apply yet: a peak in an issue could still reflect '
                    'machine age (a wear-out window).')
        return (f'This run has only {m_all} months of final history, so the same-age check does not apply yet: a '
                'peak could still reflect machine age (a wear-out window).')

    def method_items(self):
        P = self.P
        thr = f'{100 * P.MIN_CHANGE:g}%'
        dims = ', '.join(DIM_LABEL.get(d, d).lower() for d in P.STRATIFY_BY)
        scope = self.category_scope()
        issues = ('issues are all unplanned tickets, the request groups and, '
                  f'{scope} only, the Categories under them' if scope else
                  'issues are all unplanned tickets and the request groups')
        return [
            (f'Rates: unplanned tickets per 100 installed machine-months for every {self.noun}, for the fleet and by '
             f'{dims}; {issues}.'),
            (f'Changes: the latest final {self.noun} against its baseline (the final {self.plural} in the '
             f'{P.baseline_months} months before it; issue-level comparisons use only those with complete Category '
             'labels) as a crude rate ratio, adjusted only for the mix of business days (not standardised for age or '
             'model mix).'),
            (f"Uncertainty: a paired account bootstrap ({P.N_BOOT:,} resamples of IPA's accounts) plus the "
             f'between-{self.noun} variance estimated from the history, which gives 95% intervals.'),
            (f'Flags: one Benjamini-Hochberg correction over every tested cell in the run; a change is flagged when '
             f'its q-value is below {P.Q_CUT:g} and it is at least {thr} up or down (the practical threshold), and '
             f'goes on the watch list when the q-value is below {P.WATCH_Q:g}. A cell is tested only when at least '
             f'{P.MIN_EXPECTED:g} tickets are expected and the baseline has {P.MIN_BASELINE_TICKETS:g} tickets from '
             f'{P.MIN_ACCOUNTS:g} accounts.'),
            ('Survivorship check: an increase is flagged only if it remains after adding back the tickets on machines '
             'missing from the equipment list; otherwise it goes on the watch list.'),
            self.cohort_rule('full'),
            (f'Only final {self.plural} are compared: a {self.noun} is final once it has ended, {P.LABEL_LAG_DAYS} '
             f'days have passed for its labels to settle, and no more than {_share(P.MAX_OPEN_SHARE)} of its tickets '
             'were still open when exported.'),
        ]

    def definition_items(self):
        P = self.P
        thr = f'{100 * P.MIN_CHANGE:g}%'
        cohorts = ('Machines grouped by install date at the INSTALL_COHORT_EDGES dates, oldest first.'
                   if P.INSTALL_COHORT_EDGES is not None else
                   f'Machines grouped by install date, one {P.cohort_width.noun} per cohort, oldest first.')
        return [
            ('Installed machine-month', ("One machine on IPA's equipment list for 30.4 days (365.25/12). Machines "
                                         'count from their install date (or first ticket) until the data end or '
                                         'removal.')),
            ('Unplanned ticket', ('Every case except planned work (preventative maintenance, installation), cancelled '
                                  'requests and duplicates.')),
            ('Rate', 'Unplanned tickets per 100 installed machine-months.'),
            ('Baseline', (f'The final {self.plural} in the {P.baseline_months} months before the latest final '
                          f'{self.noun}; issue-level comparisons use only those with complete Category labels'
                          + (f' (this run leaves out {_and(self.dropped)})' if self.dropped else '') + '.')),
            ('Final, provisional, in progress, partial',
             (f'Final: the {self.noun} has ended, its labels have had {P.LABEL_LAG_DAYS} days to settle and few '
              'tickets were still open when exported. Provisional: ended but not settled. In progress: the data end '
              'inside it. Partial: it starts before the data.')),
            ('Flagged (higher or lower)', (f'A change from the baseline of at least {thr}, beyond normal '
                                           f'{self.cad.variation} after the correction for testing many cells '
                                           f'(q-value below {P.Q_CUT:g}): a screening flag for follow-up, not proof '
                                           'of a problem.')),
            ('Watch list', (f'A change of at least {thr} with weaker evidence (q-value below {P.WATCH_Q:g}); reported '
                            'only, because it could still be chance.')),
            ('Sustained', (f'Flagged, or on the watch list, in the same direction in the previous {self.noun} too; '
                           'the report says which.')),
            ('Request group', _cap(self.group_definition())),
            ('Install cohort', cohorts),
            ('Crude ratio', "A cohort's rate over the rest of the fleet's rate in the same months."),
            ('Newer / older installs', ("A cohort's rate over the rate of all cohorts installed after it / "
                                        'before it.')),
            ('Same-age ratio', ("A cohort's tickets over those expected from machines of the same age in other "
                                'cohorts, over the whole final history. It decides for the newest cohort with enough '
                                f'expected tickets, and for the other cohorts once at least {SAME_AGE_HISTORY_MONTHS} '
                                'months of final history exist.')),
            ('Stands out', self.cohort_rule('definition')),
            ('Unlisted tickets', ('Tickets on machines missing from every equipment list. They are not in the rates; '
                                  'the survivorship check puts them back for increases.')),
            ('95% interval', 'The range of rates or changes compatible with the data, from the account bootstrap.'),
        ]


# ================================================================================================ charts
def _draw_charts(S, R, folder):
    out = []
    plt = S.plt
    for name, fn, caption in CHARTS:
        before = set(plt.get_fignums())
        try:
            with contextlib.redirect_stdout(io.StringIO()):      # ipa_style.save prints the staging path
                title = fn(S, R, folder / f'{name}.png')
        except _Skip as e:
            R.chart_notes.append(f'{name}.png was not drawn: {e}.')
            continue
        except Exception as e:
            if R.P.MAKE_CHARTS is True:
                raise
            R.chart_notes.append(f'{name}.png could not be drawn ({type(e).__name__}).')
            continue
        finally:
            for num in set(plt.get_fignums()) - before:
                plt.close(num)
        out.append(Chart(name, f'charts/{name}.png', folder / f'{name}.png', title, caption(R)))
    return out


def _figure(S, w, h, nrows=1, ncols=1, **kw):
    S.apply_style()
    fig, axes = S.plt.subplots(nrows, ncols, figsize=(w, h), layout='constrained', squeeze=False, **kw)
    return fig, axes


def _figure_with_legend(S, w, h, nrows, ncols):
    """Panels sharing x under a full-width row that holds only a legend (so a wide legend cannot distort the
    columns). Returns (fig, legend axes, axes array)."""
    S.apply_style()
    fig = S.plt.figure(figsize=(w, h), layout='constrained')
    gs = fig.add_gridspec(nrows + 1, ncols, height_ratios=[0.32 / 2.3] + [1] * nrows)
    lax = fig.add_subplot(gs[0, :])
    lax.set_axis_off()
    axes = np.empty((nrows, ncols), dtype=object)
    for i in range(nrows):
        for j in range(ncols):
            axes[i, j] = fig.add_subplot(gs[i + 1, j], sharex=axes[0, 0] if (i or j) else None)
            if i < nrows - 1:
                axes[i, j].tick_params(labelbottom=False)
    return fig, lax, axes


def _renderer(fig):
    try:
        return fig.canvas.get_renderer()
    except AttributeError:
        return fig._get_renderer()


def _pick_title(S, fig, candidates):
    """The first candidate that fits the title band (IPA titles are one line at TITLE_PT, bold)."""
    from matplotlib.font_manager import FontProperties
    r = _renderer(fig)
    fp = FontProperties(size=S.TITLE_PT, weight='bold')
    room = (fig.get_figwidth() - 2 * S.MARGIN) * fig.dpi
    cands = [c for c in candidates if c]
    for c in cands:
        if r.get_text_width_height_descent(c, fp, ismath=False)[0] <= room:
            return c
    return cands[-1]


def _frame(S, fig, title, subtitle, notes=(), definitions=()):
    S.frame(fig, title, subtitle, notes=[n for n in notes if n], definitions=list(definitions))
    r = _renderer(fig)
    room = (fig.get_figwidth() - 2 * S.MARGIN + 0.05) * fig.dpi
    for t in fig.texts:                         # safety net: nothing may run off the page
        for _ in range(10):
            if t.get_window_extent(renderer=r).width <= room:
                break
            t.set_fontsize(t.get_fontsize() * 0.95)


def _text_width(fig, text, fontsize):
    """Width in inches of the widest line of `text` at `fontsize`."""
    from matplotlib.font_manager import FontProperties
    r = _renderer(fig)
    fp = FontProperties(size=fontsize)
    return max(r.get_text_width_height_descent(line or ' ', fp, ismath=False)[0]
               for line in str(text).split('\n')) / fig.dpi


def _axes_width(ax):
    """The axes' width in inches once the layout has run (frame() must have set the page bands)."""
    fig = ax.figure
    engine = fig.get_layout_engine()
    if engine is not None:
        engine.execute(fig)
    return ax.get_position().width * fig.get_figwidth()


def _label_step(fig, labels, fontsize, width_in, slots=None, gap=0.1):
    """Show every step-th tick label so that neighbours keep a gap (labels may hold line breaks)."""
    n = len(labels)
    if n <= 1:
        return 1
    w = [_text_width(fig, s, fontsize) for s in labels]
    spacing = width_in / (slots or n)
    for step in range(1, n + 1):
        if all((w[i] + w[i + step]) / 2 + gap <= spacing * step for i in range(n - step)):
            return step
    return n


def _period_step(ax, labels, fontsize=9.0):
    lo, hi = ax.get_xlim()
    return _label_step(ax.figure, labels, fontsize, _axes_width(ax), slots=abs(hi - lo))


def _period_ticks(ax, labels, fontsize=9.0, offset=0.0, axes=(), step=None):
    """Period labels on the x axis, thinned from the latest backwards so the latest is always labelled."""
    n = len(labels)
    if not n:
        return
    step = step or _period_step(ax, labels, fontsize)
    idx = [i for i in range(n) if (n - 1 - i) % step == 0]
    ax.set_xticks([i + offset for i in idx])
    ax.set_xticklabels([labels[i] for i in idx])
    for a in (ax,) + tuple(axes):
        a.tick_params(axis='x', labelsize=fontsize)


def _legend_above(ax, handles, labels, points=6, fontsize=9):
    """A one-row legend just above the axes, left-aligned, `points` above its top edge."""
    from matplotlib.transforms import ScaledTranslation
    tr = ax.transAxes + ScaledTranslation(0, points / 72, ax.figure.dpi_scale_trans)
    return ax.legend(handles, labels, loc='lower left', bbox_to_anchor=(0, 1), bbox_transform=tr,
                     ncol=len(handles), fontsize=fontsize, handlelength=1.8, borderaxespad=0, frameon=False)


def _dots(S, ax, x, y, final, color, s=34, z=3):
    """Final periods as filled markers, the others hollow."""
    final = np.asarray(final, bool)
    x, y = np.asarray(x, float), np.asarray(y, float)
    if final.any():
        ax.scatter(x[final], y[final], s=s, color=color, edgecolor=S.SURFACE, linewidth=1, zorder=z)
    if (~final).any():
        ax.scatter(x[~final], y[~final], s=s, facecolor=S.SURFACE, edgecolor=color, linewidth=1.5, zorder=z)


def _mix(c1, c2, t):
    """The colour a fraction t of the way from c1 to c2 ('#rrggbb')."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return '#' + ''.join(f'{round(x + (y - x) * t):02x}' for x, y in zip(a, b))


def _status_colour(S, status):
    return {'higher': S.BLUE, 'lower': S.ORANGE, 'watch_higher': S.BLUE_RAMP[3],
            'watch_lower': _mix(S.ORANGE, S.SURFACE, 0.5), 'stands_out_higher': S.BLUE,
            'stands_out_lower': S.ORANGE}.get(status, S.GRAY)


def _ylim(ax, *arrays, pad=1.18):
    vals = np.concatenate([np.asarray(a, float).ravel() for a in arrays]) if arrays else np.array([])
    vals = vals[np.isfinite(vals)]
    top = vals.max() if len(vals) else 0.0
    ax.set_ylim(0, top * pad if top > 0 else 1.0)


def _span_text(R):
    return f'{R.labels[0]} to {R.labels[-1]}' if R.labels else ''


# ------------------------------------------------------------------------------------------------ 1 fleet trend
def _fleet_titles(R):
    span = _span_text(R)
    if R.latest is None:
        return [f'Fleet ticket rate by {R.noun}: no {R.noun} is final yet', f'Fleet ticket rate, {span}']
    r = R.fleet
    neutral = f'Fleet ticket rate by {R.noun}, {span}'
    if r is None or not _finite(r.rate_latest):
        return [neutral]
    if r.status == 'not_tested' or not _finite(r.change_ratio):
        return [f'Fleet ticket rate in {R.latest}: {_r(r.rate_latest)} per 100 installed machine-months', neutral]
    p = _pct(r.change_ratio)
    word = 'above' if p > 0 else 'below'
    prev = R.baseline_text(r)
    if r.status in FLAGGED:
        return [f'Fleet ticket rate in {R.latest} was {abs(p):.0f}% {word} {prev}',
                f'Fleet ticket rate in {R.latest} was {abs(p):.0f}% {word} its baseline']
    if r.status in WATCH:
        return [f'Fleet ticket rate in {R.latest} was {abs(p):.0f}% {word} {prev}; this could still be chance',
                f'Fleet ticket rate in {R.latest}: {abs(p):.0f}% {word} its baseline, possibly chance']
    why = R.quiet(r)
    if why == 'normal' and abs(p) < 50 * R.P.MIN_CHANGE:
        return [f'Fleet ticket rate in {R.latest} was in line with {prev}',
                f'Fleet ticket rate in {R.latest} was in line with its baseline']
    if why == 'small':
        thr = f'{100 * R.P.MIN_CHANGE:g}%'
        return [f'Fleet ticket rate in {R.latest} was {abs(p):.0f}% {word} {prev}, under the {thr} threshold',
                f'Fleet ticket rate in {R.latest}: {abs(p):.0f}% {word} its baseline, under the {thr} threshold',
                f'Fleet ticket rate in {R.latest}: {abs(p):.0f}% {word} its baseline, not flagged']
    if why == 'many':
        return [f'Fleet ticket rate in {R.latest} was {abs(p):.0f}% {word} {prev}, possibly chance',
                f'Fleet ticket rate in {R.latest}: {abs(p):.0f}% {word} its baseline, possibly chance']
    return [f'Fleet ticket rate in {R.latest} was {abs(p):.0f}% {word} {prev}, within normal variation',
            f'Fleet ticket rate in {R.latest}: {abs(p):.0f}% {word} its baseline, within normal variation']


def chart_fleet_trend(S, R, path):
    d = R.series('fleet', 'all')
    if d.empty or not d.rate.notna().any():
        raise _Skip('there are no fleet rates')
    n = len(d)
    x = np.arange(n)
    rate, lo, hi = (d[c].to_numpy(float) for c in ('rate', 'lo', 'hi'))
    final = (d.status == 'final').to_numpy()
    fig, axes = _figure(S, 11, 6.8)
    ax = axes[0, 0]
    base = R.baseline_pos
    for i in base:
        ax.axvspan(i - 0.5, i + 0.5, color=S.ZERO_CELL, lw=0, zorder=0)
    ax.fill_between(x, lo, hi, color=S.BAR_BACKGROUND, lw=0, zorder=1)
    ax.plot(x, rate, color=S.GRAY, lw=1.6, zorder=2)
    _dots(S, ax, x, rate, final, S.GRAY)
    li = R.latest_pos
    _ylim(ax, hi, rate, pad=1.2)
    if li is not None and _finite(rate[li]):
        ax.plot([li, li], [lo[li], hi[li]], color=S.BLUE, lw=2.4, zorder=4, solid_capstyle='butt')
        ax.scatter([li], [rate[li]], s=90, color=S.BLUE, edgecolor=S.SURFACE, linewidth=1.5, zorder=5)
        ax.annotate(f'{R.latest}: {_r(rate[li])}', (li, hi[li] if _finite(hi[li]) else rate[li]), xytext=(0, 7),
                    textcoords='offset points', ha='right' if li >= n - 2 and n > 3 else 'center', va='bottom',
                    fontsize=10, color=S.INK, weight='bold', zorder=6)
        fr = R.fleet
        if fr is not None and _finite(fr.rate_baseline) and base:
            rb = float(fr.rate_baseline)
            ax.hlines(rb, base[0] - 0.45, base[-1] + 0.45, colors=S.INK2, linestyles=(0, (4, 3)), lw=1.3, zorder=4)
            # the label starts just before the first baseline marker and covers it (and the next one when periods
            # are narrow): put it on the side of the dashed line where fewer of those markers are
            near = rate[base[0]:min(base[0] + (1 if n <= 12 else 2), n)]
            near = near[np.isfinite(near)]
            up, down = int((near > rb).sum()), int((near <= rb).sum())
            below = bool(up > down or (up == down and len(near) and near[0] > rb))
            ax.annotate(f'Baseline {_r(rb)}', (base[0] - 0.4, rb), xytext=(0, -5 if below else 5),
                        textcoords='offset points', ha='left', va='top' if below else 'bottom', fontsize=9.5,
                        color=S.INK2, zorder=2.5)
    S.style_axes(ax, grid='y')
    ax.set_xlim(-0.6, n - 0.4)
    ax.set_ylabel('per 100 installed machine-months')
    title = _pick_title(S, fig, _fleet_titles(R))
    head = (f'Unplanned tickets per 100 installed machine-months, all machines, {_span_text(R)}, with 95% '
            'intervals (shaded band).')
    if li is not None:
        sub = (f'{head} The large marker is {R.latest}, the latest final {R.noun}; the shaded {R.plural} are its '
               f'baseline and the dashed line is the baseline rate.')
    else:
        sub = f'{head} No {R.noun} is final yet, so nothing is compared and every rate can still change.'
    notes = [R.hollow_note() if (~final).any() else '', R.ci_note(), R.history_note(),
             'Source: rates.csv (fleet, All unplanned tickets)' + (' and changes.csv.' if li is not None else '.')]
    _frame(S, fig, title, sub, notes, R.defs(baseline=li is not None))
    _period_ticks(ax, R.labels)
    S.save(fig, path)
    return title


# ------------------------------------------------------------------------------------------------ 2 group trends
def _tag(R, row):
    if row is None or row.status == 'not_tested' or not _finite(row.change_ratio):
        return 'not tested' if R.latest is not None else ''
    t = f'{_pct(row.change_ratio):+.0f}%'
    if row.status in FLAGGED:
        return t + ', flagged'
    if row.status in WATCH:
        return t + ', watch'
    return t


def chart_group_trends(S, R, path):
    groups = list(FU.PRIMARY)
    fig, axes = _figure(S, 11, 8.8, 3, 3, sharex=True)
    n = len(R.labels)
    x = np.arange(n)
    flagged, hollow = [], False
    for ax, g in zip(axes.flat, groups):
        key = f'group|{g}'
        d = R.series('fleet', key)
        row = R.change_row('fleet', key)
        st = row.status if row is not None else 'not_tested'
        col = _status_colour(S, st)
        rate, lo, hi = (d[c].to_numpy(float) for c in ('rate', 'lo', 'hi'))
        final = (d.status == 'final').to_numpy()
        hollow |= bool((~final).any())
        none = not np.nansum(d.tickets.to_numpy(float)) > 0
        if none:                                     # no tickets at all: say so instead of drawing Byar bands
            lo = hi = np.zeros(n)
            ax.text(0.5, 0.55, f'no tickets in these {R.plural}', transform=ax.transAxes, ha='center',
                    va='center', fontsize=9, color=S.MUTED)
        else:
            ax.fill_between(x, lo, hi, color=S.BAR_BACKGROUND, lw=0, zorder=1)
        ax.plot(x, rate, color=col, lw=1.8 if st in FLAGGED else 1.4, zorder=2)
        _dots(S, ax, x, rate, final, col, s=16)
        if R.latest_pos is not None and _finite(rate[R.latest_pos]):
            ax.scatter([R.latest_pos], [rate[R.latest_pos]], s=44, zorder=4, edgecolor=S.SURFACE, linewidth=1,
                       color=col if st in FLAGGED + WATCH else S.INK2)
        if st in FLAGGED:
            flagged.append((g, row))
        _ylim(ax, hi, rate, pad=1.15)
        ax.yaxis.set_major_locator(S.plt.MaxNLocator(3))
        ax.tick_params(axis='both', labelsize=8.5)
        S.style_axes(ax, grid='y')
        ax.set_title(g, loc='left', fontsize=10.5, weight='bold', color=S.INK)
        ax.set_title(_tag(R, row), loc='right', fontsize=9, color=S.INK2, fontweight='normal')
    axes[-1, 0].set_xlim(-0.6, n - 0.4)
    for ax in axes[:, 0]:
        ax.set_ylabel('per 100', fontsize=9)
    L = R.latest
    group_rows = [R.change_row('fleet', f'group|{g}') for g in groups]
    tested = [r for r in group_rows if r is not None and r.status != 'not_tested']
    many, small, watch = R.beyond(pd.DataFrame(tested)) if tested else (0, 0, 0)
    chance = [r for r in tested if r.status not in FLAGGED + WATCH and R.quiet(r) == 'many']
    if L is None:
        cands = [f'Unplanned tickets by request group, {_span_text(R)}']
    elif not tested:
        cands = [f'Unplanned tickets by request group: {L} could not be compared yet',
                 f'Unplanned tickets by request group, {_span_text(R)}']
    elif not flagged and (many or small or watch):     # some interval excludes no change: say 'not flagged'
        named = (f'{chance[0].issue} ({_pct(chance[0].change_ratio):+.0f}%)' if len(chance) == 1
                 else _n(many, 'change'))
        cands = ([f'No request group was flagged in {L}; {named} could still be chance',
                  f'No request group was flagged in {L}; {_n(many, "change")} could still be chance'] if many else
                 []) + [f'No request group was flagged for follow-up in {L}', f'No request group was flagged in {L}']
    elif not flagged:
        cands = [f'No request group changed beyond normal {R.cad.variation} in {L}',
                 f'No request group changed beyond normal variation in {L}']
    elif len(flagged) == 1:
        g, r = flagged[0]
        p = _pct(r.change_ratio)
        word = 'above' if p > 0 else 'below'
        cands = [f'{g} tickets in {L} were {abs(p):.0f}% {word} {R.baseline_text(r)}',
                 f'{g} tickets in {L} were {abs(p):.0f}% {word} their baseline']
    else:
        cands = [f'{len(flagged)} request groups changed beyond normal {R.cad.variation} in {L}',
                 f'{len(flagged)} request groups changed beyond normal variation in {L}']
    title = _pick_title(S, fig, cands)
    sub = (f'Unplanned tickets per 100 installed machine-months for each request group, all machines, '
           f'{_span_text(R)}, with 95% intervals (shaded); each panel has its own scale.')
    if L is not None:
        sub += f' Top right: the change in {L} from the baseline.'
        if flagged:
            sub += ' Highlighted: ' + ', '.join(g for g, _ in flagged) + ' (flagged for follow-up).'
    notes = []
    if L is not None:
        notes.append(f'Flagged: beyond normal {R.cad.variation} (a screening flag for follow-up, not proof of a '
                     'problem); watch: could still be chance; not tested: too few tickets or accounts, or labels '
                     'incomplete.')
    notes += [R.hollow_note() if hollow else '', R.ci_note(), R.history_note(),
              'Source: rates.csv and changes.csv (fleet).' if L is not None else 'Source: rates.csv (fleet).']
    group_def = f'Request group: {R.group_definition()}'
    defs = R.defs(baseline=L is not None, issues=True) + [group_def]
    _frame(S, fig, title, sub, notes, defs)
    _period_ticks(axes[-1, 0], R.labels, fontsize=8.5, axes=tuple(axes[-1, 1:]))
    S.save(fig, path)
    return title


# ------------------------------------------------------------------------------------------------ 3 cohort profile
def _cohort_titles(R):
    st = R.stands
    if len(st):
        r = st.iloc[0]
        noun, who = _issue_noun(r.issue), _cohort_phrase(r.install_cohort)
        ratio = float(r.crude_ratio)
        if ratio >= 1:
            size = f'{ratio:.1f}x higher' if ratio >= 2 else f'{_pct(ratio):.0f}% higher'
        else:
            size = f'{-_pct(ratio):.0f}% lower'
        return [f'{noun} tickets run {size} on {who} than on the rest of the fleet',
                f'{noun} tickets run {size} on {who} than on other machines',
                f'{noun}: {size} on {who}']
    if len(R.contrasts) and R.contrasts.eligible.astype(bool).any():
        return [f'No install cohort stands out from the rest of the fleet over {R.window_text}',
                f'No install cohort stands out over {R.window_text}']
    return [f'Ticket rates by install cohort, {R.window_text}']


def _cohort_ticks(ax, cohorts, fontsize=8.5, axes=()):
    """Install-cohort labels (two lines where needed); turned upright only when they cannot all fit."""
    fig = ax.figure
    labels = ['\n'.join(textwrap.wrap(c, 8, break_on_hyphens=False)) or c for c in cohorts]
    lo, hi = ax.get_xlim()
    width = _axes_width(ax)
    step = _label_step(fig, labels, fontsize, width, slots=abs(hi - lo), gap=0.05)
    if step > 1 and _label_step(fig, labels, fontsize - 0.5, width, slots=abs(hi - lo), gap=0.05) == 1:
        fontsize, step = fontsize - 0.5, 1
    rot = 0
    if step > 1:                                     # too many cohorts: turn the labels instead of dropping some
        labels, rot = list(cohorts), 90
        step = _label_step(fig, ['2'] * len(cohorts), fontsize * 1.4, width, slots=abs(hi - lo), gap=0.03)
    idx = [i for i in range(len(cohorts)) if i % step == 0]
    ax.set_xticks(idx)
    ax.set_xticklabels([labels[i] for i in idx])
    for a in (ax,) + tuple(axes):
        a.tick_params(axis='x', labelsize=fontsize, labelrotation=rot)


def chart_cohort_profile(S, R, path):
    cc = R.contrasts
    if R.latest is None or cc.empty:
        raise _Skip(f'install cohorts are compared only once a {R.noun} is final')
    keys = ['all'] + [k for k in R.cohort_issues(5) if k != 'all']
    order = [c for c in R.cohort_order() if c in set(cc.install_cohort.astype(str))]
    if not order:
        raise _Skip('no install cohort has machines in the cohort window')
    n = len(keys)
    ncols = 1 if n == 1 else 2
    nrows = math.ceil(n / ncols)
    fig, lax, axes = _figure_with_legend(S, 11, 2.9 + 2.35 * nrows, nrows, ncols)
    present = set()
    for ax, key in zip(axes.flat, keys):
        rows = cc[cc.issue_key == key]
        u = rows.drop_duplicates('install_cohort')
        sub = u.set_index(u.install_cohort.astype(str)).reindex(order)
        rate, lo, hi = (sub[c].to_numpy(float) for c in ('rate_per_100', 'ci_lo', 'ci_hi'))
        status = sub.status.fillna('not_tested').astype(str).to_numpy()
        eligible = sub.eligible.eq(True).to_numpy()
        months = rows.machine_months.astype(float).sum()
        fleet = 100 * rows.tickets.astype(float).sum() / months if months > 0 else np.nan
        cols = [_status_colour(S, s) if s in STANDS else (S.GRAY if e else S.GRAY_LIGHT)
                for s, e in zip(status, eligible)]
        for i in range(len(order)):
            if not _finite(rate[i]):
                continue
            ax.plot([i, i], [lo[i], hi[i]], color=cols[i], lw=1.6, zorder=2, solid_capstyle='butt')
            ax.scatter([i], [rate[i]], s=36, color=cols[i], edgecolor=S.SURFACE, linewidth=1, zorder=3)
            present.add(status[i] if status[i] in STANDS else ('eligible' if eligible[i] else 'not_tested'))
            if status[i] in STANDS:
                ax.annotate(f'{sub.crude_ratio.iloc[i]:.1f}x', (i, rate[i]), xytext=(6, 0),
                            textcoords='offset points', ha='left', va='center', fontsize=8.5, color=S.INK,
                            weight='bold', zorder=5)
        if _finite(fleet):
            ax.axhline(fleet, color=S.INK2, lw=1, ls=(0, (4, 3)), zorder=1)
        top_src = np.r_[hi[eligible], rate, [fleet]]
        _ylim(ax, top_src, pad=1.22)
        ax.yaxis.set_major_locator(S.plt.MaxNLocator(4))
        ax.tick_params(axis='y', labelsize=8.5)
        S.style_axes(ax, grid='y')
        out = [c for c, s in zip(order, status) if s in STANDS]
        ax.set_title(R.issue_name(key), loc='left', fontsize=10.5, weight='bold', color=S.INK)
        right = [f'fleet {_r(fleet)}'] if _finite(fleet) else []
        if out:
            right.append('stands out: ' + ', '.join(out[:3]) + (' ...' if len(out) > 3 else ''))
        ax.set_title('; '.join(right), loc='right', fontsize=9, color=S.INK2, fontweight='normal')
        ax.set_xlim(-0.6, len(order) - 0.4)
    shown = list(axes[-1, :])
    for i in range(n, nrows * ncols):                                    # an empty last panel
        axes.flat[i].set_visible(False)
        axes.flat[i - ncols].xaxis.set_tick_params(labelbottom=True)
        shown[i % ncols] = axes.flat[i - ncols]
    for ax in axes[:, 0]:
        ax.set_ylabel('per 100', fontsize=9)
    from matplotlib.lines import Line2D
    names = [('stands_out_higher', 'Stands out higher'), ('stands_out_lower', 'Stands out lower'),
             ('eligible', 'Not called out'), ('not_tested', 'Not tested')]
    handles = [Line2D([], [], marker='o', ls='-', color=_status_colour(S, k) if k in STANDS else
                      (S.GRAY if k == 'eligible' else S.GRAY_LIGHT), markersize=6, lw=1.6) for k, _ in names
               if k in present]
    labels = [lab for k, lab in names if k in present]
    if handles:
        lax.legend(handles, labels, loc='center left', ncol=len(handles), fontsize=9, handlelength=1.8,
                   borderaxespad=0, frameon=False)
    title = _pick_title(S, fig, _cohort_titles(R))
    sub = (f'Unplanned tickets per 100 installed machine-months by install cohort over {R.window_text} '
           f'({_n(R.window_n, "final " + R.noun, "final " + R.plural)}'
           + (f'; {R.window_note}' if R.window_note else '') + '), with 95% intervals; the dashed line is the whole '
           'fleet.')
    others = R.stands.iloc[1:4] if len(R.stands) > 1 else R.stands.iloc[0:0]
    if len(others):
        sub += ' Also standing out: ' + '; '.join(f'{r.issue} on {_cohort_phrase(r.install_cohort)} '
                                                  f'({r.crude_ratio:.1f}x)' for r in others.itertuples()) + '.'
    defs = R.defs(baseline=False) + [R.cohort_rule('short')]
    drawn = cc[cc.issue_key.isin(keys)]
    too_new = 'position' in drawn and drawn.position.eq('too_new').any()
    notes = [('Labels at the markers: the cohort rate over the rest of the fleet. ' if 'stands_out_higher' in present
              or 'stands_out_lower' in present else '') + 'Not tested: too few tickets, machines or accounts, or too '
             'few machines to compare with' + ('; the newest cohorts are still filling up and are not compared.'
                                                if too_new else '.'), R.ci_note(), 'Source: cohort_contrasts.csv.']
    _frame(S, fig, title, sub, notes, defs)
    _cohort_ticks(shown[0], order, axes=tuple(shown[1:]))
    S.save(fig, path)
    return title


# ------------------------------------------------------------------------------------------------ 4 cohort map
def chart_cohort_map(S, R, path):
    from matplotlib.colors import LinearSegmentedColormap, ListedColormap
    from matplotlib.patches import Rectangle
    if R.latest is None:
        raise _Skip(f'install cohorts are compared only once a {R.noun} is final')
    rt = R.rates[R.rates.stratum_dim == 'install_cohort'] if len(R.rates) else R.rates
    if rt.empty:
        raise _Skip('install cohort is not among the breakdowns (STRATIFY_BY)')
    keys = R.cohort_issues(5)[:4]
    if not keys:
        keys = ['all']
    pk = list(R.view_keys)
    final = np.array([s == 'final' for s in R.status])
    order = [c for c in R.cohort_order() if c in set(rt.stratum.astype(str))]
    panels = []
    for key in keys:
        sub = rt[rt.issue_key == key]
        if sub.empty:
            continue
        look = {(str(r.stratum), str(r.period_key)): (float(r.rate_per_100), bool(r.meets_min_exposure))
                for r in sub.itertuples()}
        V = np.full((len(order), len(pk)), np.nan)
        OK = np.zeros((len(order), len(pk)), bool)
        for i, c in enumerate(order):
            for j, p in enumerate(pk):
                if (c, p) in look:
                    V[i, j], OK[i, j] = look[(c, p)]
        OK &= np.isfinite(V)
        if OK.any():
            panels.append((key, V, OK))
    if not panels:
        raise _Skip(f'no install cohort reached {R.P.MIN_CELL_MONTHS:g} installed machine-months in a single '
                    f'{R.noun}')
    n = len(panels)
    ncols = 1 if n == 1 else 2
    nrows = math.ceil(n / ncols)
    C, N = len(order), len(pk)
    fig, axes = _figure(S, 11, 2.7 + max(2.6, 0.2 * C + 1.1) * nrows, nrows, ncols)
    cmap = LinearSegmentedColormap.from_list('ipa_blue', S.BLUE_RAMP)
    grey = ListedColormap([S.ZERO_CELL])
    for idx, (ax, (key, V, OK)) in enumerate(zip(axes.flat, panels)):
        xe, ye = np.arange(N + 1), np.arange(C + 1)
        ax.pcolormesh(xe, ye, np.zeros((C, N)), cmap=grey, edgecolors=S.SURFACE, linewidth=0.8)
        vals = V[OK & final[None, :]] if (OK & final[None, :]).any() else V[OK]
        vmax = float(np.nanpercentile(vals, 98)) if len(vals) else 1.0
        vmax = vmax if vmax > 0 else 1.0
        mesh = ax.pcolormesh(xe, ye, np.ma.masked_where(~OK, V), cmap=cmap, vmin=0, vmax=vmax,
                             edgecolors=S.SURFACE, linewidth=0.8)
        for j in np.flatnonzero(~final):
            ax.add_patch(Rectangle((j, 0), 1, C, fill=False, hatch='////', edgecolor=S.SURFACE, lw=0, zorder=3))
        ax.set_ylim(C, 0)
        ax.set_xlim(0, N)
        ax.set_yticks(np.arange(C) + 0.5)
        ax.set_yticklabels(order if idx % ncols == 0 else [], fontsize=8.5)
        for s in ax.spines.values():
            s.set_visible(False)
        cb = fig.colorbar(mesh, ax=ax, fraction=0.05, pad=0.02, aspect=22)
        cb.outline.set_visible(False)
        cb.ax.tick_params(labelsize=8, length=0)
        cb.set_label('per 100', fontsize=8.5, color=S.MUTED)
        ax.set_title(R.issue_name(key), loc='left', fontsize=10.5, weight='bold', color=S.INK)
    for ax in axes.flat[n:]:
        ax.set_visible(False)
    # title: which cohort had the highest rate most often (first panel, final periods, enough exposure)
    key, V, OK = panels[0]
    issue = _issue_noun(R.issue_name(key))
    wins, cols = {}, 0
    for j in np.flatnonzero(final):
        ok = OK[:, j]
        if ok.sum() >= 2:
            cols += 1
            i = int(np.nanargmax(np.where(ok, V[:, j], -np.inf)))
            wins[order[i]] = wins.get(order[i], 0) + 1
    cands = []
    if wins and cols >= 3:
        best = max(wins.items(), key=lambda kv: (kv[1], -order.index(kv[0])))
        if best[1] * 2 > cols:
            plural = R.noun if cols == 1 else R.plural
            cands = [(f'{issue} ticket rates were highest on {_cohort_phrase(best[0])} in {best[1]} of {cols} '
                     f'{plural}'), f'{issue}: highest on {_cohort_phrase(best[0])} in {best[1]} of {cols} {plural}']
    cands.append(f'{issue} ticket rates by install cohort and {R.noun}')
    title = _pick_title(S, fig, cands)
    sub = (f'Unplanned tickets per 100 installed machine-months by install cohort (rows, oldest at the top) and '
           f'{R.noun} (columns), {_span_text(R)}; darker means a higher rate, each panel on its own scale.')
    notes = [(f'Plain light cells: under {R.P.MIN_CELL_MONTHS:g} installed machine-months, too few for a rate; '
             f'hatched columns: {R.plural} not final yet. The title counts final {R.plural} with at least two '
              'cohorts shown.'), R.history_note(), 'Source: rates.csv (install cohort).']
    _frame(S, fig, title, sub, notes, R.defs(baseline=False))
    step = max(_period_step(ax, R.labels, 8.5) for ax in axes.flat[:n])     # the same labels on every panel
    for ax in axes.flat[:n]:
        _period_ticks(ax, R.labels, fontsize=8.5, offset=0.5, step=step)
    S.save(fig, path)
    return title


# ------------------------------------------------------------------------------------------------ 5 changes
def _forest_rows(R):
    """Rows of the changes chart: the fleet and its request groups (those tested), then the other flagged and
    watch-list cells, fleet-level first and strongest first (as in the report), cut to MAX_FOREST_ROWS but keeping at
    least one row of each flagged direction the title counts. Returns (head, extra, number of cells left out)."""
    c = R.changes
    head_keys = ['all'] + [f'group|{g}' for g in FU.PRIMARY]
    fleet = c[(c.stratum_dim == 'fleet') & c.issue_key.isin(head_keys)]
    fleet = fleet.set_index('issue_key').reindex([k for k in head_keys if k in set(fleet.issue_key)]).reset_index()
    head = fleet[(fleet.status != 'not_tested') & np.isfinite(fleet.change_ratio.astype(float))]
    is_head = (c.stratum_dim == 'fleet') & c.issue_key.isin(head_keys)
    extra = c[c.status.isin(FLAGGED + WATCH) & ~is_head].copy()
    extra['_f'] = (extra.stratum_dim != 'fleet').astype(int)
    extra['_w'] = extra.status.isin(WATCH).astype(int)
    extra['_o'] = R._order(extra)
    extra = extra.sort_values(['_f', '_w', 'q_value', '_o'], kind='mergesort').drop(columns=['_f', '_w', '_o'])
    room = max(0, MAX_FOREST_ROWS - len(head))
    must = [extra.index[extra.status == st][0] for st in FLAGGED
            if (extra.status == st).any() and not (head.status == st).any()]
    rest = [i for i in extra.index if i not in must]
    keep = set(must[:room] + rest[:max(0, room - len(must))])
    shown = extra[extra.index.isin(keep)].copy()
    top = set(extra.index[:room])
    shown.attrs['forced'] = [str(extra.status.loc[i]) for i in must[:room] if i not in top]   # kept for the title
    return head, shown, len(extra) - len(shown)


def chart_changes(S, R, path):
    from matplotlib.lines import Line2D
    from matplotlib.ticker import FixedLocator, NullLocator
    if R.latest is None or R.changes.empty:
        raise _Skip(f'nothing is compared until a {R.noun} is final')
    head, extra, hidden = _forest_rows(R)
    if head.empty and extra.empty:
        raise _Skip('no cell could be tested')
    rows = [('head', r) for r in head.itertuples()] + [('extra', r) for r in extra.itertuples()]
    y, pos = [], 0.0
    for i, (kind, _) in enumerate(rows):
        if i and kind == 'extra' and rows[i - 1][0] == 'head':
            pos += 0.7
        y.append(pos)
        pos += 1
    fig, axes = _figure(S, 11, 2.9 + 0.36 * len(rows) + 0.5)
    ax = axes[0, 0]
    lo_all = [float(r.ci_lo) for _, r in rows if _finite(r.ci_lo)] + [1 - R.P.MIN_CHANGE]
    hi_all = [float(r.ci_hi) for _, r in rows if _finite(r.ci_hi)] + [1 + R.P.MIN_CHANGE]
    xmin = max(0.05, min(lo_all) / 1.12)
    xmax = min(20.0, max(hi_all) * 1.12)
    ax.set_xscale('log')
    ax.set_xlim(xmin, xmax)
    ax.axvspan(1 - R.P.MIN_CHANGE, 1 + R.P.MIN_CHANGE, color=S.ZERO_CELL, lw=0, zorder=0)
    ax.axvline(1, color=S.INK2, lw=0.9, zorder=1)
    present = []
    for yy, (_, r) in zip(y, rows):
        col = _status_colour(S, r.status)
        lo, hi = float(r.ci_lo), float(r.ci_hi)
        ax.plot([max(lo, xmin), min(hi, xmax)], [yy, yy], color=col, lw=2.2, solid_capstyle='butt', zorder=2)
        ax.scatter([r.change_ratio], [yy], s=46, color=col, edgecolor=S.SURFACE, linewidth=1, zorder=3)
        ax.text(1.01, yy, f'{_pct(r.change_ratio):+.0f}%  ({_interval(lo, hi)})', transform=ax.get_yaxis_transform(),
                ha='left', va='center', fontsize=8.5, color=S.INK2, clip_on=False)
        if r.status not in present:
            present.append(r.status)
    labels = [f'{r.issue}{R.stratum_text(r)}' for _, r in rows]
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    for t, (kind, r) in zip(ax.get_yticklabels(), rows):
        t.set_color(S.INK if r.status in FLAGGED else S.INK2)
    ax.set_ylim(pos - 0.4, -0.6)
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_xlabel(f'Change in {R.latest} from the baseline (log scale)')
    S.style_axes(ax, grid='x')
    thr = f'{100 * R.P.MIN_CHANGE:g}%'
    order = ['higher', 'lower', 'watch_higher', 'watch_lower', 'no_clear_change']
    names = {'higher': 'Flagged higher', 'lower': 'Flagged lower', 'watch_higher': 'Watch, higher',
             'watch_lower': 'Watch, lower', 'no_clear_change': 'Not flagged'}
    from matplotlib.patches import Patch
    handles = [Line2D([], [], marker='o', color=_status_colour(S, s), lw=2.2, markersize=6) for s in order
               if s in present] + [Patch(color=S.ZERO_CELL, lw=0)]
    names_shown = [names[s] for s in order if s in present] + [f'Within \u00b1{thr} (practical threshold)']
    _legend_above(ax, handles, names_shown, points=8)
    nflag = int((R.changes.status.isin(FLAGGED)).sum())
    nwatch = int((R.changes.status.isin(WATCH)).sum())
    many, small, watch = R.beyond()
    if nflag == 0 and (many or small or watch):        # some interval excludes no change: say 'not flagged'
        cands = ([f'No change in {R.latest} was flagged; {_n(many, "change")} could still be chance'] if many
                 else []) + [f'No change in {R.latest} was flagged for follow-up', f'No change flagged in {R.latest}']
    elif nflag == 0:
        cands = [f'No change in {R.latest} was beyond normal {R.cad.variation}',
                 f'No change in {R.latest} was beyond normal variation', f'No change flagged in {R.latest}']
    else:
        up = int((R.changes.status == 'higher').sum())
        dn = nflag - up
        parts = 'all increases' if not dn else ('all decreases' if not up else f'{up} up, {dn} down')
        if nflag == 1:
            parts = 'an increase' if up else 'a decrease'
        cands = [(f'{_n(nflag, "change")} in {R.latest} {"was" if nflag == 1 else "were"} flagged for follow-up '
                 f'({parts})'), f'{_n(nflag, "change")} flagged for follow-up in {R.latest}']
    title = _pick_title(S, fig, cands)
    tested = int(R.s.get('tested', 0) or 0)
    base = R.baseline_summary(pd.concat([head, extra]))
    forced = extra.attrs.get('forced') or []        # directions kept although weaker than the cells left out
    if not hidden:
        which = 'the fleet and its request groups' + (', then every other flagged or watch-list cell' if len(extra)
                                                      else '')
    elif not forced:
        which = (f'the fleet and its request groups, then the {len(extra)} strongest other flagged or watch-list '
                 f'cells, fleet-wide first; {hidden} more are in the report')
    else:
        kept = _and(f'one flagged {"increase" if st == "higher" else "decrease"}' for st in forced)
        which = (f'the fleet and its request groups, then {len(extra)} other flagged or watch-list cells (fleet-wide '
                 f'first, then the strongest, with at least {kept}); {hidden} more are in the report')
    lead = ('Change in the rate from the baseline' + (f' ({base})' if '(' not in base else '')
            + f', adjusted for business days, with 95% intervals: {which}.')
    sub = (lead + (f' Baseline: {base}.' if '(' in base else '')
           + f' {_n(tested, "cell")} tested; {nwatch} on the watch list.')
    out = many - R.beyond(head)[0] if nflag == 0 else 0      # unflagged larger changes in cells not drawn
    if out > 0:
        who = f'The {_n(many, "change")}' if out == many else f'{out} of the {_n(many, "change")}'
        where = 'is in a cell' if out == 1 else 'are in cells'
        sub += f' {who} that could still be chance {where} not drawn here (changes.csv).'
    notes = [(f'Flagged: q-value below {R.P.Q_CUT:g} after one Benjamini-Hochberg correction over every tested cell, '
             f'and a change of at least {thr} (shaded band); a screening flag for follow-up, not proof of a problem. '
              f'Watch: q-value below {R.P.WATCH_Q:g}; could still be chance.'),
             R.ci_note(change=True), 'Source: changes.csv.']
    _frame(S, fig, title, sub, notes, R.defs(issues=True))
    _log_ticks(ax, xmin, xmax, FixedLocator)
    S.save(fig, path)
    return title


def _log_ticks(ax, xmin, xmax, FixedLocator, fontsize=9):
    """Change ratios as percent changes on a log axis, thinned so neighbouring labels keep a gap."""
    cand = [1, 0.8, 1.25, 0.5, 2, 0.67, 1.5, 0.33, 3, 0.2, 5, 0.1, 10, 20, 0.05]
    width = _axes_width(ax)
    span = math.log(xmax) - math.log(xmin)
    keep = []
    for t in cand:                                  # most useful first; skip any that would crowd a kept one
        if not xmin <= t <= xmax:
            continue
        lab = '0%' if t == 1 else f'{_pct(t):+.0f}%'
        w = _text_width(ax.figure, lab, fontsize)
        x = (math.log(t) - math.log(xmin)) / span * width
        if all(abs(x - kx) >= (w + kw) / 2 + 0.12 for kx, kw, _, _ in keep):
            keep.append((x, w, t, lab))
    keep.sort(key=lambda k: k[2])
    ax.xaxis.set_major_locator(FixedLocator([k[2] for k in keep]))
    ax.set_xticklabels([k[3] for k in keep])
    ax.tick_params(axis='x', labelsize=fontsize)


# ------------------------------------------------------------------------------------------------ 6 data quality
def chart_data_quality(S, R, path):
    dq = R.dq
    if dq.empty:
        raise _Skip('there is no data-quality table')
    dq = dq.set_index('period_key').reindex(list(R.view_keys))
    n = len(dq)
    x = np.arange(n)
    final = np.array([s == 'final' for s in R.status])
    P = R.P
    # the engine's own Category gate: MAX_BLANK_CATEGORY_SHARE or twice the typical share, whichever is higher
    blank = R.facts.get('blank_category_limit')
    blank = float(blank) if _finite(blank) else P.MAX_BLANK_CATEGORY_SHARE
    panels = [('open_share', 'Tickets still open when exported', P.MAX_OPEN_SHARE,
               f'{_share(P.MAX_OPEN_SHARE)} limit; above it a {R.noun} stays provisional'),
              ('blank_category_share', 'Blank Category (unplanned tickets, excluding Monitoring)', blank,
               f'{_share(P.MAX_BLANK_CATEGORY_SHARE)} or twice the typical share ({_share(blank)} in this run)'),
              ('unlisted_share', 'Tickets on machines missing from the equipment list', UNLISTED_NOTE,
               f'{_share(UNLISTED_NOTE)}; above it the email mentions the share')]
    fig, axes = _figure(S, 11, 7.9, 3, 1, sharex=True)
    over, late = {}, {}
    ended = np.array([s in ('final', 'provisional') for s in R.status])     # in-progress periods are open anyway
    for ax, (col, name, limit, label) in zip(axes[:, 0], panels):
        v = 100 * dq[col].astype(float).fillna(0).to_numpy()
        bad = v > 100 * limit + 1e-9
        if col == 'blank_category_share' and 'label_ok' in dq:      # the periods the gate actually left out
            bad = dq.label_ok.isin([False, 'False']).to_numpy()
        over[col] = int((bad & ended).sum())
        late[col] = int((bad & ~ended).sum())
        colours = np.where(bad, S.BLUE, S.GRAY_LIGHT)
        for i in range(n):
            if final[i]:
                ax.bar(x[i], v[i], width=0.62, color=colours[i], lw=0, zorder=2)
            else:
                ax.bar(x[i], v[i], width=0.62, facecolor=S.SURFACE, edgecolor=colours[i], lw=1.3, zorder=2)
        ax.axhline(100 * limit, color=S.INK2, lw=1, ls=(0, (4, 3)), zorder=3)
        ax.set_title('dashed line: ' + label, loc='right', fontsize=9, color=S.INK2, fontweight='normal')
        top = max(float(np.nanmax(v)) if n else 0.0, 100 * limit)
        ax.set_ylim(0, top * 1.35 if top > 0 else 1)
        ax.yaxis.set_major_locator(S.plt.MaxNLocator(3))
        S.pct_axis(ax.yaxis, nd=0 if top >= 3 else 1)
        ax.tick_params(axis='y', labelsize=8.5)
        S.style_axes(ax, grid='y')
        ax.set_title(name, loc='left', fontsize=10.5, weight='bold', color=S.INK)
    axes[-1, 0].set_xlim(-0.6, n - 0.4)
    u = R.s.get('latest_unlisted_share')
    if over['open_share']:
        k = over['open_share']
        cands = [f'{_n(k, R.noun, R.plural)} had too many open tickets at export to be final',
                 f'{_n(k, R.noun, R.plural)} had too many open tickets to be final']
    elif over['blank_category_share']:
        k = over['blank_category_share']
        cands = [f'{_n(k, R.noun, R.plural)} had too many blank Categories for issue-level tests']
    elif R.latest is not None and _finite(u) and u > UNLISTED_NOTE:
        cands = [f'{_share(u)} of {R.latest} tickets were on machines missing from the equipment list',
                 f'{_share(u)} of {R.latest} tickets were on unlisted machines']
    else:
        ended_only = late['open_share'] or late['blank_category_share']      # only an unfinished period is above
        every = f'every {"ended " if ended_only else ""}{R.noun}' + (' shown' if R.hidden_periods else '')
        cands = [f'Open-ticket and blank-Category shares were within limits in {every}',
                 f'Open and blank-Category shares were within limits in {every}',
                 f'Open and blank-Category shares within limits in {every}',
                 'Open-ticket and blank-Category shares were within limits']
    title = _pick_title(S, fig, cands)
    sub = (f'Share of each {R.noun}\'s unplanned tickets, {_span_text(R)}. Highlighted bars are above the dashed '
           f'line; hollow bars are {R.plural} not final yet.')
    notes = [('Open tickets: still open when the case export was taken; labels may still change. Blank Category: above '
              f'the dashed line, issue-level tests skip the {R.noun}. Unlisted tickets are not in the rates; the '
              'survivorship check puts them back before an increase is flagged.'),
             R.history_note('data_quality.csv'), 'Source: data_quality.csv.']
    _frame(S, fig, title, sub, notes, R.defs(baseline=False)[1:])
    _period_ticks(axes[-1, 0], R.labels)
    S.save(fig, path)
    return title


CHARTS = (
    ('fleet_trend', chart_fleet_trend,
     lambda R: f'Fleet rate per {R.noun} with 95% intervals: the latest final {R.noun} against its baseline.'
     if R.latest else f'Fleet rate per {R.noun} with 95% intervals; no {R.noun} is final yet.'),
    ('group_trends', chart_group_trends, lambda R: 'Rates for the nine request groups, each on its own scale.'),
    ('cohort_profile', chart_cohort_profile,
     lambda R: f'Rates by install cohort over {R.window_text}, against the whole fleet.'),
    ('cohort_map', chart_cohort_map, lambda R: f'Rates by install cohort and {R.noun} for the selected issues.'),
    ('changes', chart_changes,
     lambda R: 'Change from the baseline for the fleet and its request groups, and the other flagged or watch-list '
               'cells.'),
    ('data_quality', chart_data_quality,
     lambda R: f'Open, blank-Category and unlisted shares per {R.noun}, with their limits.'),
)


# ================================================================================================ report.html
CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { margin: 0; background: #fcfcfb; color: #0b0b0b;
       font: 15px/1.5 "Segoe UI", "Helvetica Neue", Arial, sans-serif; }
main { max-width: 1040px; margin: 0 auto; padding: 28px 16px 56px; }
h1 { font-size: 26px; line-height: 1.25; margin: 4px 0 6px; }
h2 { font-size: 19px; margin: 36px 0 8px; padding-top: 14px; border-top: 1px solid #e1e0d9; }
h3 { font-size: 15.5px; margin: 20px 0 6px; }
p { margin: 6px 0 10px; }
.kicker { color: #52514e; font-size: 13px; letter-spacing: .04em; text-transform: uppercase; margin: 0; }
.meta, .lede { color: #52514e; }
.muted { color: #898781; font-size: 13.5px; }
ul.key { padding-left: 20px; margin: 8px 0; }
ul.key li { margin: 0 0 8px; }
.notice { background: #f2f1ec; padding: 10px 14px; margin: 10px 0; }
.wrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 13.5px; margin: 8px 0 14px; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #e1e0d9; vertical-align: top; }
th { color: #52514e; font-weight: 600; border-bottom: 1px solid #c3c2b7; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.chip { display: inline-block; padding: 0 7px; border-radius: 9px; font-size: 12.5px; white-space: nowrap; }
.chip.higher { background: #cde2fb; color: #104281; }
.chip.lower { background: #fbe0d4; color: #8a3413; }
.chip.watch { background: #f2f1ec; color: #52514e; }
figure { margin: 18px 0 30px; }
figure img { display: block; width: 100%; height: auto; border: 1px solid #e1e0d9; }
figcaption { color: #52514e; font-size: 13.5px; margin-top: 6px; }
dl { margin: 6px 0; }
dt { font-weight: 600; margin-top: 8px; }
dd { margin: 2px 0 0; color: #52514e; }
code { font-family: Consolas, "Courier New", monospace; font-size: 13px; }
@media print { h2 { break-after: avoid; } figure, table { break-inside: avoid; } }
"""


def _e(v):
    return html.escape('' if v is None else str(v), quote=True)


def _html_table(headers, rows, num=()):
    """A table with escaped cells; `num` holds the indices of right-aligned numeric columns."""
    th = ''.join(f'<th{" class=num" if i in num else ""}>{_e(h)}</th>' for i, h in enumerate(headers))
    body = []
    for row in rows:
        tds = []
        for i, v in enumerate(row):
            if isinstance(v, tuple):            # (text, chip class)
                tds.append(f'<td><span class="chip {_e(v[1])}">{_e(v[0])}</span></td>')
            else:
                tds.append(f'<td{" class=num" if i in num else ""}>{_e(v)}</td>')
        body.append('<tr>' + ''.join(tds) + '</tr>')
    return (f'<div class="wrap"><table><thead><tr>{th}</tr></thead><tbody>{"".join(body)}</tbody></table>'
            '</div>')


def _chip(status):
    if status in FLAGGED:
        return ('higher' if status == 'higher' else 'lower', status)
    if status in WATCH:
        return ('watch, ' + status.split('_')[1], 'watch')
    return (str(status).replace('_', ' '), 'watch')


def _change_rows(R, df, watch=False):
    """Rows of the flags or watch-list table, and whether they carry a 'Baseline' column: each row's own baseline,
    added only when some row's baseline left out periods (issue-level rows skip baseline periods whose Category
    labels are incomplete)."""
    phrases = [R.baseline_text(r) for r in df.itertuples()]
    own = any(p != R.previous for p in phrases)
    rows = []
    for r, phrase in zip(df.itertuples(), phrases):
        extra = R.sustained_text(r)
        sustained = f'yes, {extra}' if extra else ('no' if not watch else '')
        survivor = _text(getattr(r, 'survivor_note', ''))
        note = '; '.join(['could still be chance'] + [t for t in (survivor, extra) if t])
        rows.append([_chip(r.status), r.issue, R.stratum_text(r, style='label'), f'{r.rate_latest:.2f}',
                     f'{r.rate_baseline:.2f}'] + ([phrase] if own else [])
                    + [f'{_pct(r.change_ratio):+.0f}%', _interval(r.ci_lo, r.ci_hi), note if watch else sustained])
    return rows, own


def _change_table(R, df, watch=False):
    rows, own = _change_rows(R, df, watch)
    heads = (['Status', 'Issue', 'Breakdown', f'Rate in {R.latest}', 'Baseline rate'] + (['Baseline'] if own else [])
             + ['Change', '95% interval', 'Note' if watch else 'Sustained'])
    return _html_table(heads, rows, num=(3, 4, 6, 7) if own else (3, 4, 5, 6))


def _write_html(R, charts, path):
    P, s, L = R.P, R.s, R.latest
    title = f'{P.REPORT_TITLE}: {L}' if L else f'{P.REPORT_TITLE}: no final {R.noun} yet'
    window = s.get('data_window') or ['', '']
    adj = str(R.cad.adjective)
    parts = ['<!DOCTYPE html>', '<html lang="en">', '<head>', '<meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width, initial-scale=1">', f'<title>{_e(title)}</title>',
             f'<style>{CSS}</style>', '</head>', '<body>', '<main>']
    meta = [f'data {window[0]} to {window[1]}', f'exported {s.get("extracted_at", "")}']
    if L:
        meta.insert(0, f'Latest final {R.noun}: {s.get("latest_label_long") or L}')
        if R.k:
            meta.append(f'baseline {s["baseline_labels"][0]} to {s["baseline_labels"][-1]} '
                        f'({_n(R.k, "final " + R.noun, "final " + R.plural)})')
        if R.dropped:
            meta.append(f'{_and(R.dropped)} left out of issue-level comparisons (Category labels incomplete)')
    parts += ['<header>', f'<p class="kicker">{_e(_kind(R.cad))}</p>', f'<h1>{_e(title)}</h1>',
              f'<p class="meta">{_e(_cap("; ".join(meta)))}.</p>', '</header>']
    parts += ['<section id="key-messages">', '<h2>Key messages</h2>', '<ul class="key">']
    parts += [f'<li>{_e(m)}</li>' for m in R.key_messages()]
    parts += ['</ul>', '</section>']

    if L is None:
        parts += ['<section id="rates">', f'<h2>Fleet rate by {_e(R.noun)}</h2>',
                  (f'<p class="notice">No reporting {_e(R.noun)} is final yet, so nothing is compared and there are no '
                  'call-outs. The rates below can still change.</p>')]
        d = R.series('fleet', 'all', every=True)
        rows = [[r.label, str(r.status).replace('_', ' '), f'{r.tickets:,.0f}' if _finite(r.tickets) else '',
                 f'{r.months:,.0f}' if _finite(r.months) else '', _r(r.rate) if _finite(r.rate) else '',
                 f'{_r(r.lo)} to {_r(r.hi)}' if _finite(r.lo) else ''] for r in d.itertuples()]
        parts += [_html_table([R.noun.capitalize(), 'Status', 'Unplanned tickets', 'Installed machine-months',
                               'Rate per 100', '95% interval'], rows, num=(2, 3, 4, 5)), '</section>']
    else:
        # call-outs
        parts += ['<section id="call-outs">', '<h2>Call-outs</h2>',
                  (f'<p class="lede">Changes from the baseline beyond normal {_e(R.cad.variation)}. These are '
                   'screening flags for follow-up, not proof of a problem.</p>')]
        rates_note = ('<p class="muted">Rates are unplanned tickets per 100 installed machine-months; the change is '
                      'adjusted for business days.</p>')
        if len(R.flags):
            parts += [_change_table(R, R.flags), rates_note]
        else:
            parts.append(f'<p>{_e(R.none_flagged())}</p>')
        parts.append('</section>')
        # cohorts
        parts += ['<section id="cohorts">', '<h2>Install cohorts that stand out</h2>',
                  f'<p class="lede">Over {_e(R.window_phrase())}. {_e(R.cohort_rule("lede"))}'
                  + (f' {_e(R.same_age_note())}' if R.same_age_note() else '') + '</p>']
        if len(R.stands):
            rows = []
            own = any(R.row_window(r) != R.window_text for r in R.stands.itertuples())   # a shorter issue window
            for r in R.stands.itertuples():
                def _r(v, a, b):
                    return f'{v:.1f}x ({a:.1f} to {b:.1f})' if _finite(v) else 'n/a'
                rows.append([r.issue, r.install_cohort] + ([R.row_window(r)] if own else [])
                            + [f'{r.rate_per_100:.2f}', f'{r.rate_rest:.2f}',
                               _r(r.crude_ratio, r.crude_lo, r.crude_hi), _r(r.newer_ratio, r.newer_lo, r.newer_hi),
                               _r(r.older_ratio, r.older_lo, r.older_hi),
                               _r(r.same_age_ratio, r.same_age_lo, r.same_age_hi),
                               f'{int(r.machines):,}' if _finite(r.machines) else '', _text(r.top_models),
                               'yes' if bool(r.persisting) else 'no'])
            parts.append(_html_table(['Issue', 'Install cohort'] + (['Window'] if own else [])
                                     + ['Rate', 'Rest of fleet', 'vs rest (95%)', 'vs newer installs',
                                        'vs older installs', 'Same age', 'Machines', 'Main models', 'Also last window'],
                                     rows, num=(3, 4, 9) if own else (2, 3, 8)))
        elif len(R.contrasts):
            parts.append(f'<p>No install cohort stands out over {_e(R.window_phrase())}.</p>')
        else:
            parts.append('<p>Install cohorts were not compared.</p>')
        parts.append('</section>')
        # watch list
        parts += ['<section id="watch">', '<h2>Watch list</h2>',
                  (f'<p class="lede">Changes of at least {100 * P.MIN_CHANGE:g}% with weaker evidence (q-value below '
                   f'{P.WATCH_Q:g}). Reported only: these could still be chance.</p>')]
        if len(R.watch):
            parts += [_change_table(R, R.watch, watch=True), rates_note]
        else:
            parts.append('<p>Nothing is on the watch list.</p>')
        parts.append('</section>')

    # charts
    parts += ['<section id="charts">', '<h2>Charts</h2>']
    if R.no_charts:
        parts.append(f'<p class="notice">Charts and the PDF were not made because {_e(R.no_charts)}. The tables in '
                     'this report and the CSV files hold the same numbers.</p>')
    for c in charts:
        data = base64.b64encode(c.path.read_bytes()).decode('ascii')
        parts.append(f'<figure><img src="data:image/png;base64,{data}" alt="{_e(c.title + ". " + c.caption)}">'
                     f'<figcaption>{_e(c.caption)}</figcaption></figure>')
    for note in R.chart_notes:
        parts.append(f'<p class="muted">{_e(note)}</p>')
    parts.append('</section>')

    # data quality
    parts += ['<section id="data-quality">', '<h2>Data quality</h2>', '<h3>Warnings</h3>']
    if R.warnings:
        rows = [[w.get('code', ''), w.get('message', ''), w.get('fix') or '',
                 'yes' if w.get('blocking') else 'no'] for w in R.warnings]
        parts.append(_html_table(['Code', 'Message', 'Fix', 'Blocks distribution'], rows))
    else:
        parts.append('<p>No warnings.</p>')
    parts.append(f'<h3>{_e(R.plural.capitalize())} not final yet</h3>')
    nf = R.not_final()
    if nf:
        parts.append(_html_table([R.noun.capitalize(), 'Status', 'Reason'], [list(t) for t in nf]))
    else:
        parts.append(f'<p>Every {_e(R.noun)} in the data is final.</p>')
    u = s.get('latest_unlisted_share')
    if L and _finite(u):
        parts.append(f'<p>{_e(_share(u))} of the unplanned tickets in {_e(L)} were on machines missing from the '
                     'equipment list. They are not in the rates; the survivorship check puts them back before an '
                     'increase is flagged.</p>')
    if len(R.dq):
        rows = []
        for r in R.dq.itertuples():
            rows.append([r.period_label, str(r.status).replace('_', ' '), f'{int(r.unplanned):,}',
                         _share(r.open_share), _share(r.blank_category_share), _share(r.unlisted_share),
                         f'{r.machine_months:,.0f}', f'{r.avg_installed_machines:,.0f}'])
        parts += [f'<h3>By {_e(R.noun)}</h3>',
                  _html_table([R.noun.capitalize(), 'Status', 'Unplanned tickets', 'Open at export',
                               'Blank Category', 'Unlisted', 'Installed machine-months', 'Machines (average)'],
                              rows, num=(2, 3, 4, 5, 6, 7))]
        limit = R.facts.get('blank_category_limit')
        if _finite(limit):
            gated = [str(r.period_label) for r in R.dq.itertuples()      # final periods: the others are not compared
                     if getattr(r, 'label_ok', True) in (False, 'False') and str(r.status) == 'final']
            which = (f' ({_and(gated)})' if len(gated) <= 6 else f' ({len(gated)} {R.plural})') if gated else ''
            parts.append(f'<p class="muted">A {_e(R.noun)} whose blank-Category share is above {_e(_share(limit))} '
                         f'({_e(_share(P.MAX_BLANK_CATEGORY_SHARE))} or twice the typical share, whichever is higher) '
                         f'is left out of issue-level comparisons{_e(which)}.</p>')
    parts.append('</section>')

    # definitions and method
    parts += ['<section id="definitions">', '<h2>Definitions</h2>', '<dl>']
    for term, text in R.definition_items():
        parts.append(f'<dt>{_e(term)}</dt><dd>{_e(text)}</dd>')
    parts += ['</dl>', '</section>', '<section id="method">', '<h2>Method in brief</h2>', '<ul>']
    parts += [f'<li>{_e(m)}</li>' for m in R.method_items()]
    parts += ['</ul>', '</section>']

    # run details
    inputs = R.facts.get('inputs') or {}
    case = Path(str((inputs.get('case_export') or {}).get('file', ''))).name
    lists = ', '.join(Path(str(e.get('file', ''))).name + (f' (list of {e["snapshot_date"]})'
                                                           if e.get('snapshot_date') else '')
                      for e in inputs.get('equipment_lists') or [])
    details = [('Run ID', R.run_id), ('Package version', __version__), ('Method version', METHOD_VERSION),
               ('Definitions hash', R.defs_hash),
               ('Rerun frequency', f'{CAD.Cadence(R.cad.months).adjective} ({s.get("rerun_frequency", "")})'
                + ('; periods from PERIOD_EDGES' if getattr(P, 'PERIOD_EDGES', None) is not None else '')),
               ('Case export', case), ('Equipment lists', lists),
               ('Data window', f'{window[0]} to {window[1]}'), ('Exported', s.get('extracted_at', '')),
               ('Bootstrap resamples', f'{P.N_BOOT:,}')]
    nxt = (s.get('next_runs') or [{}])[0]
    if nxt.get('due'):
        details.append(('Next run due', f'{nxt["due"]} (for {nxt.get("label", "")})'))
    parts += ['<section id="run">', '<h2>Run details</h2>', _html_table(['Item', 'Value'], details), '</section>']
    parts += ['</main>', '</body>', '</html>', '']
    doc = '\n'.join(parts)
    path.write_text(doc, encoding='utf-8')
    return _visible_text(doc)


class _Visible(HTMLParser):
    """Visible text of an HTML document (and alt/title attributes), without the style sheet."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ('style', 'script'):
            self._skip += 1
        for k, v in attrs:
            if k in ('alt', 'title') and v:
                self.out.append(v)

    def handle_endtag(self, tag):
        if tag in ('style', 'script'):
            self._skip = max(0, self._skip - 1)

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.out.append(' '.join(data.split()))


def _visible_text(doc):
    p = _Visible()
    p.feed(doc)
    p.close()
    return p.out


# ================================================================================================ report.pdf
class _Pages:
    """Text pages for the PDF: paragraphs flow down US Letter landscape pages with wrapped lines."""
    M = 0.6           # margin, inches

    def __init__(self, S, pdf, header):
        self.S, self.pdf, self.header = S, pdf, header
        self.fig, self.y, self.page, self.texts = None, 0.0, 0, []

    def _new(self):
        self.close()
        W, H = PAGE
        self.fig = self.S.plt.figure(figsize=PAGE)
        self.page += 1
        self.y = self.M
        foot = f'{self.header} | page {self.page}'
        self.fig.text(self.M / W, 0.35 / H, foot, ha='left', va='bottom', fontsize=8, color=self.S.MUTED)
        self.texts.append(foot)

    def close(self):
        if self.fig is not None:
            self.pdf.savefig(self.fig)
            self.S.plt.close(self.fig)
            self.fig = None

    def para(self, text, size=10.0, color=None, weight='normal', indent=0.0, before=0.0, bullet=False, keep=0.0):
        W, H = PAGE
        S = self.S
        color = color or S.INK2
        bw = 0.2 if bullet else 0.0
        chars = max(20, int((W - 2 * self.M - indent - bw) * 72 / (size * 0.56)))
        lines = textwrap.wrap(text, chars, break_on_hyphens=False) or ['']
        lh = size * 1.42 / 72
        need = before + len(lines) * lh + keep
        if self.fig is None or self.y + need > H - self.M - 0.25:
            self._new()
            before = 0.0
        self.y += before
        x = self.M + indent
        if bullet:
            self.fig.text(x / W, 1 - self.y / H, '-', ha='left', va='top', fontsize=size, color=color)
        for line in lines:
            self.fig.text((x + bw) / W, 1 - self.y / H, line, ha='left', va='top', fontsize=size, color=color,
                          weight=weight)
            self.y += lh
        self.texts.append(text)


def _write_pdf(S, R, charts, path):
    import matplotlib.image as mpimg
    from matplotlib.backends.backend_pdf import PdfPages
    P, L = R.P, R.latest
    title = f'{P.REPORT_TITLE}: {L}' if L else f'{P.REPORT_TITLE}: no final {R.noun} yet'
    window = R.s.get('data_window') or ['', '']
    S.apply_style()
    meta = {'Title': title, 'Creator': None, 'Producer': None, 'CreationDate': None}
    texts = [title]
    with PdfPages(path, metadata=meta) as pdf:
        pg = _Pages(S, pdf, title)
        pg.para(title, size=19, color=S.INK, weight='bold')
        pg.para(f'{_kind(R.cad)}. Data {window[0]} to {window[1]}; exported '
                f'{R.s.get("extracted_at", "")}; run {R.run_id}.', size=9.5, color=S.MUTED, before=0.04)
        pg.para('Key messages', size=12.5, color=S.INK, weight='bold', before=0.22, keep=0.3)
        for m in R.key_messages():
            pg.para(m, bullet=True, before=0.05)
        if L is not None:
            pg.para('Flagged for follow-up (screening flags, not proof of a problem)', size=12.5, color=S.INK,
                    weight='bold', before=0.22, keep=0.3)
            if len(R.flags):
                for r in R.flags.itertuples():
                    pg.para(R.change_item(r), bullet=True, before=0.05)
            else:
                pg.para(R.none_flagged(), before=0.05)
            pg.para(f'Install cohorts that stand out ({R.window_text})', size=12.5, color=S.INK, weight='bold',
                    before=0.22, keep=0.3)
            if R.window_note:
                pg.para(f'{_cap(R.window_note)}.', before=0.05)
            if len(R.stands) and R.same_age_note(gaps_only=True):
                pg.para(R.same_age_note(gaps_only=True), before=0.05)
            if len(R.stands):
                for r in R.stands.itertuples():
                    pg.para(R.cohort_item(r), bullet=True, before=0.05)
            else:
                pg.para('No install cohort stands out from the rest of the fleet.', before=0.05)
            if len(R.watch):
                pg.para('Watch list (could still be chance)', size=12.5, color=S.INK, weight='bold', before=0.22,
                        keep=0.3)
                for r in R.watch.head(8).itertuples():
                    pg.para(R.change_item(r), bullet=True, before=0.05)
                if len(R.watch) > 8:
                    pg.para(f'{len(R.watch) - 8} more in report.html and changes.csv.', before=0.05)
        pg.para('Data notes', size=12.5, color=S.INK, weight='bold', before=0.22, keep=0.3)
        notes = [f'{lab} is {st}' + (f': {why}.' if why else '.') for lab, st, why in R.not_final()[-6:]]
        if len(R.not_final()) > 6:
            notes.insert(0, _cap(R.not_final_text()) + '; the latest six are listed here.')
        u = R.s.get('latest_unlisted_share')
        if L is not None and _finite(u):
            notes.append(f'{_share(u)} of the unplanned tickets in {L} were on machines missing from the equipment '
                         'list; they are not in the rates.')
        notes += [f'{w.get("code")}: {w.get("message")}' + (f'. Fix: {w["fix"]}.' if w.get('fix') else '.')
                  for w in R.warnings]
        notes += R.chart_notes
        for note in notes or ['None.']:
            pg.para(note, bullet=bool(notes), before=0.05)
        pg.close()
        # one page per chart
        W, H = PAGE
        for c in charts:
            img = mpimg.imread(c.path)
            h_px, w_px = img.shape[:2]
            box_w, box_h = W - 0.8, H - 0.8 - 0.3
            scale = min(box_w / (w_px / S.DPI), box_h / (h_px / S.DPI))
            w, h = w_px / S.DPI * scale, h_px / S.DPI * scale
            fig = S.plt.figure(figsize=PAGE)
            ax = fig.add_axes(((W - w) / 2 / W, (0.7 + (box_h - h) / 2) / H, w / W, h / H))
            ax.imshow(img, interpolation='none')
            ax.set_axis_off()
            pg.page += 1
            foot = f'{title} | page {pg.page}'
            fig.text(0.6 / W, 0.35 / H, foot, ha='left', va='bottom', fontsize=8, color=S.MUTED)
            texts.append(foot)
            pdf.savefig(fig)
            S.plt.close(fig)
        # definitions and method
        pg.para('Definitions', size=12.5, color=S.INK, weight='bold', keep=0.3)
        for term, text in R.definition_items():
            pg.para(f'{term}: {text}', size=9.5, before=0.04)
        pg.para('Method in brief', size=12.5, color=S.INK, weight='bold', before=0.22, keep=0.3)
        for m in R.method_items():
            pg.para(m, size=9.5, bullet=True, before=0.04)
        pg.para(f'Package {__version__}, method {METHOD_VERSION}, definitions {R.defs_hash}; run {R.run_id}.',
                size=8.5, color=S.MUTED, before=0.2)
        pg.close()
    return texts + pg.texts


# ================================================================================================ email
def _email_lines(R, pdf):
    """[(kind, text)] with kind in subject / p / head / item; at most MAX_EMAIL_LINES entries."""
    P, L = R.P, R.latest
    out = [('subject', f'Subject: {P.REPORT_TITLE}: {L}' if L else
            f'Subject: {P.REPORT_TITLE}: no final {R.noun} yet')]
    out.append(('p', R.fleet_line()))
    if L is not None:
        nflag = len(R.flags)
        if nflag:
            shown = R.flags.head(5)
            head = 'Flagged for follow-up (screening flags, not proof of a problem)'
            if nflag > len(shown):
                head += f'; {nflag} in all, the first {len(shown)} shown'
            out.append(('head', head + ':'))
            out += [('item', R.change_item(r)) for r in shown.itertuples()]
        else:
            out.append(('p', R.none_flagged()))
        if len(R.stands):
            shown = R.stands.head(3)
            head = f'Install cohorts that stand out over {R.window_phrase()}'
            if len(R.stands) > 3:
                head += f'; {len(R.stands)} in all, the first 3 shown'
            out.append(('head', head + ':'))
            out += [('item', R.cohort_item(r)) for r in shown.itertuples()]
        elif len(R.contrasts):
            out.append(('p', f'No install cohort stands out over {R.window_phrase()}.'))
        if len(R.watch):
            out.append(('p', f'Watch list: {len(R.watch)} more could still be chance (see the report).'))
    notes = [R.not_final_text()] if R.not_final() else []
    if L is not None and R.dropped:
        notes.append(R.dropped_text())
    u = R.s.get('latest_unlisted_share')
    if L is not None and _finite(u) and u > UNLISTED_NOTE:
        notes.append(f'{_share(u)} of {L} tickets were on machines missing from the equipment list')
    if R.warnings:
        notes.append(f'{_n(len(R.warnings), "data warning")} (see the report)')
    if R.no_charts:
        notes.append(f'no charts or PDF, because {R.no_charts}')
    out.append(('p', 'Data notes: ' + ('; '.join(notes) if notes else 'none') + '.'))
    tables = ('runs/' + str(R.run_id) + '/rates_final.csv (a back-run: latest/ was not changed)'
              if getattr(P, 'LATEST_PERIOD', None) else 'latest/rates_final.csv')
    out.append(('p', (f'Full report attached ({FILES["report_pdf"] if pdf else FILES["report_html"]}). '
                      f'Dashboard tables: {tables}')))
    while len(out) > MAX_EMAIL_LINES:          # drop the optional watch line, then the last items
        drop = next((i for i, (k, t) in enumerate(out) if t.startswith('Watch list:')), None)
        if drop is None:
            drop = max(i for i, (k, _) in enumerate(out) if k == 'item')
        out.pop(drop)
    return out


def _write_email(R, stage, pdf):
    lines = _email_lines(R, pdf)
    txt = '\n'.join(('- ' + t) if k == 'item' else t for k, t in lines) + '\n'
    (stage / FILES['email_txt']).write_text(txt, encoding='utf-8')
    style_p = 'margin:0 0 10px 0;'
    body, items = [], []

    def flush():
        if items:
            body.append('<ul style="margin:0 0 10px 0;padding-left:22px;">'
                        + ''.join(f'<li style="margin:0 0 4px 0;">{_e(t)}</li>' for t in items) + '</ul>')
            items.clear()
    for k, t in lines:
        if k == 'item':
            items.append(t)
            continue
        flush()
        if k == 'subject':
            body.append(f'<p style="{style_p}color:#52514e;">{_e(t)}</p>')
        elif k == 'head':
            body.append(f'<p style="margin:0 0 4px 0;"><strong>{_e(t)}</strong></p>')
        else:
            body.append(f'<p style="{style_p}">{_e(t)}</p>')
    flush()
    title = lines[0][1].replace('Subject: ', '', 1)
    doc = ('<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
           f'<title>{_e(title)}</title>\n</head>\n'
           '<body style="margin:0;padding:16px;background:#ffffff;color:#0b0b0b;'
           'font-family:Calibri,Segoe UI,Arial,sans-serif;font-size:14px;line-height:1.45;">\n'
           + '\n'.join(body) + '\n</body>\n</html>\n')
    (stage / FILES['email_html']).write_text(doc, encoding='utf-8')
    return [t for t in txt.splitlines() if t.strip()] + _visible_text(doc)
