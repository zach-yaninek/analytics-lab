"""The report layer: charts, report.html, report.pdf and the email text for one run.

    build(result, tables, P, stage_dir, run_id) -> {'texts': [...], 'files': {...}, 'charts': [...]}

publish.publish calls build() inside its private staging folder, before the privacy scan. 'texts' holds every string
written: the text drawn on each chart, the visible text of report.html, the PDF's text pages and both email files,
so the scan covers all of it. Only the public aggregate tables are read: period labels, install cohorts, model and
family names, issue names and numbers.

  charts/*.png         IPA style (ipa_trends/style, copied from viz/style), 150 dpi; titles state the finding and
                       the footers carry the definitions
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


def _kind(cadence):
    """'Monthly report', 'Quarterly report', 'Report every 5 months'."""
    adj = str(cadence.adjective)
    return f'Report {adj}' if ' ' in adj else f'{adj[:1].upper()}{adj[1:]} report'


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
        self.labels = [str(v) for v in p.label] if len(p) else []
        self.status = [str(v) for v in p.status] if len(p) else []
        roles = [str(v) for v in p.role] if len(p) and 'role' in p else [''] * len(self.labels)
        self.latest_pos = roles.index('latest') if 'latest' in roles else None
        self.baseline_pos = [i for i, r in enumerate(roles) if r == 'baseline']
        src = self.rates if len(self.rates) else (self.changes if len(self.changes) else self.contrasts)
        self.issue_order = {k: i for i, k in enumerate(dict.fromkeys(src.issue_key))} if len(src) else {}
        self.k = len(self.s.get('baseline_labels') or [])
        self.previous = self.cad.previous(self.k) if self.k else 'the baseline'
        self.window = self.s.get('cohort_window') or ''
        self.window_n = len((self.facts.get('cohorts') or {}).get('window') or [])
        self.fleet = self.change_row('fleet', 'all')
        self.flags = self._sorted_changes(FLAGGED)
        self.watch = self._sorted_changes(WATCH)
        self.stands = self._stands()
        self.window_text = self.window or 'the cohort window'

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

    def series(self, dim, key, stratum=None):
        """Rates of one cell for every period, in period order (NaN where the period has no row)."""
        out = self.periods[['period_key', 'label', 'status']].copy()
        out['role'] = self.periods.role if 'role' in self.periods else ''
        rt = self.rates
        sub = rt[(rt.stratum_dim == dim) & (rt.issue_key == key)] if len(rt) else rt
        if stratum is not None and len(sub):
            sub = sub[sub.stratum == stratum]
        sub = sub.drop_duplicates('period_key').set_index('period_key') if len(sub) else sub
        for col, src in (('rate', 'rate_per_100'), ('lo', 'ci_lo'), ('hi', 'ci_hi'), ('months', 'machine_months'),
                         ('tickets', 'tickets')):
            out[col] = out.period_key.map(sub[src]).astype(float) if len(sub) else np.nan
        out['ok'] = out.period_key.map(sub['meets_min_exposure']).eq(True) if len(sub) else False
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

    def defs(self, baseline=True):
        out = [("Installed machine-month: one machine on IPA's equipment list for 30.4 days (365.25/12); machines "
               "count from their install date (or first ticket) until the data end or removal."),
               ('Unplanned ticket: every case except planned work (preventative maintenance, installation), cancelled '
               'requests and duplicates.')]
        if baseline:
            latest = self.latest or f'the latest final {self.noun}'
            out.append(f'Baseline: the final {self.plural} in the {self.P.baseline_months} months before {latest}.')
        return out

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
        extra = f'; also flagged last {self.noun}' if bool(getattr(r, 'sustained', False)) else ''
        return f'Fleet: {rate}, {self.vs(r.change_ratio)} ({ci}), {verdict}{extra}.'

    def none_flagged(self):
        """The sentence for a run with no flag: nothing beyond normal variation, or nothing could be tested."""
        tested = int(self.s.get('tested', 0) or 0)
        if tested == 0:
            why = _text(self.fleet.not_tested_reason if self.fleet is not None else None, 'too little final history')
            return f'No change could be tested in {self.latest}: {why}.'
        return (f'No change in {self.latest} was beyond normal {self.cad.variation} '
                f'({_n(tested, "issue and breakdown cell")} tested).')

    def change_item(self, r):
        """A flagged or watch-list cell in one line (email, PDF)."""
        extra = f'; also flagged last {self.noun}' if bool(getattr(r, 'sustained', False)) else ''
        return (f'{r.issue}{self.stratum_text(r)}: {r.rate_latest:.2f} per 100 installed machine-months, '
                f'{self.vs(r.change_ratio)} (95% interval {_interval(r.ci_lo, r.ci_hi)}){extra}.')

    def cohort_item(self, r):
        s = getattr(r, 'sentence', None)
        if isinstance(s, str) and s:
            return s
        return (f'{r.issue}, {_cohort_phrase(r.install_cohort)}: {r.rate_per_100:.2f} per 100 installed '
                f'machine-months, {r.crude_ratio:.1f}x the rest of the fleet.')

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
            top = self.stands.iloc[0]
            n = len(self.stands)
            if n > 1:
                out.append(f'{n} install-cohort call-outs over {self.window_text}. The strongest: {top.sentence}')
            else:
                out.append(f'One install-cohort call-out over {self.window_text}: {top.sentence}')
        elif len(self.contrasts):
            out.append(f'No install cohort stands out from the rest of the fleet over {self.window_text}.')
        if len(self.watch):
            out.append(f'{_n(len(self.watch), "more change")} {"is" if len(self.watch) == 1 else "are"} on the '
                       'watch list: reported, not flagged, because they could still be chance.')
        notes = self.data_notes()
        if notes:
            out.append('Data caveats: ' + ' '.join(notes))
        return out[:6]

    def method_items(self):
        P = self.P
        thr = f'{100 * P.MIN_CHANGE:g}%'
        hi = 1 + P.MIN_CONTRAST
        dims = ', '.join(DIM_LABEL.get(d, d).lower() for d in P.STRATIFY_BY)
        return [
            (f'Rates: unplanned tickets per 100 installed machine-months for every {self.noun}, for the fleet and by '
             f'{dims}; issues are all unplanned tickets, nine request groups and the Categories under them.'),
            (f'Changes: the latest final {self.noun} against its baseline (the final {self.plural} in the '
             f'{P.baseline_months} months before it) as a crude rate ratio, adjusted only for the mix of business '
             'days (not standardised for age or model mix).'),
            (f"Uncertainty: a paired account bootstrap ({P.N_BOOT:,} resamples of IPA's accounts) plus the "
             f'between-{self.noun} variance estimated from the history, which gives 95% intervals.'),
            (f'Flags: one Benjamini-Hochberg correction over every tested cell in the run; a change is flagged when '
             f'its q-value is below {P.Q_CUT:g} and it is at least {thr} up or down (the practical threshold), and '
             f'goes on the watch list when the q-value is below {P.WATCH_Q:g}. A cell is tested only when at least '
             f'{P.MIN_EXPECTED:g} tickets are expected and the baseline has {P.MIN_BASELINE_TICKETS:g} tickets from '
             f'{P.MIN_ACCOUNTS:g} accounts.'),
            ('Survivorship check: an increase is flagged only if it remains after adding back the tickets on machines '
             'missing from the equipment list; otherwise it goes on the watch list.'),
            (f'Install cohorts: over the last {P.CONTRAST_MONTHS} months of final {self.plural}, each cohort is '
             'compared with the rest of the fleet (crude ratio, Benjamini-Hochberg corrected) and with all newer and '
             f'all older installs. It stands out only when its rate is at least {hi:.1f}x the rest of the fleet (or '
             f'at most {1 / hi:.2f}x) with a q-value below {P.Q_CUT:g}, and is above (or below) both newer and '
             'older installs: a peak in the install-date profile, which a steady age effect cannot produce. The '
             'newest cohort is compared instead with earlier installs at the same age.'),
            (f'Only final {self.plural} are compared: a {self.noun} is final once it has ended, {P.LABEL_LAG_DAYS} '
             f'days have passed for its labels to settle, and no more than {_share(P.MAX_OPEN_SHARE)} of its tickets '
             'were still open when exported.'),
        ]

    def definition_items(self):
        P = self.P
        hi = 1 + P.MIN_CONTRAST
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
                          f'{self.noun}.')),
            ('Final, provisional, in progress, partial',
             (f'Final: the {self.noun} has ended, its labels have had {P.LABEL_LAG_DAYS} days to settle and few '
              'tickets were still open when exported. Provisional: ended but not settled. In progress: the data end '
              'inside it. Partial: it starts before the data.')),
            ('Flagged (higher or lower)', (f'A change from the baseline beyond normal {self.cad.variation}: a '
                                           'screening flag for follow-up, not proof of a problem.')),
            ('Watch list', ('A change of the same size with weaker evidence; reported only, because it could still '
                            'be chance.')),
            ('Request group', ("The ticket's Trouble Code and Category mapped to one of nine groups by the project's "
                               'request-type reference.')),
            ('Install cohort', cohorts),
            ('Crude ratio', "A cohort's rate over the rest of the fleet's rate in the same months."),
            ('Newer / older installs', ("A cohort's rate over the rate of all cohorts installed after it / "
                                        'before it.')),
            ('Same-age ratio', ("A cohort's tickets over those expected from machines of the same age in other "
                                'cohorts, over the whole history (context; it decides only for the newest cohort).')),
            ('Stands out', (f'Crude ratio at least {hi:.1f}x (or at most {1 / hi:.2f}x) after the '
                            'Benjamini-Hochberg correction, and above (or below) both newer and older installs; '
                            'for the newest cohort, also against earlier installs at the same age.')),
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
    if r.status in FLAGGED:
        return [f'Fleet ticket rate in {R.latest} was {abs(p):.0f}% {word} {R.previous}',
                f'Fleet ticket rate in {R.latest} was {abs(p):.0f}% {word} its baseline']
    if r.status in WATCH:
        return [f'Fleet ticket rate in {R.latest} was {abs(p):.0f}% {word} {R.previous}; this could still be chance',
                f'Fleet ticket rate in {R.latest}: {abs(p):.0f}% {word} its baseline, possibly chance']
    why = R.quiet(r)
    if why == 'normal' and abs(p) < 50 * R.P.MIN_CHANGE:
        return [f'Fleet ticket rate in {R.latest} was in line with {R.previous}',
                f'Fleet ticket rate in {R.latest} was in line with its baseline']
    if why == 'small':
        thr = f'{100 * R.P.MIN_CHANGE:g}%'
        return [f'Fleet ticket rate in {R.latest} was {abs(p):.0f}% {word} {R.previous}, under the {thr} threshold',
                f'Fleet ticket rate in {R.latest}: {abs(p):.0f}% {word} its baseline, under the {thr} threshold',
                f'Fleet ticket rate in {R.latest}: {abs(p):.0f}% {word} its baseline, not flagged']
    if why == 'many':
        return [f'Fleet ticket rate in {R.latest} was {abs(p):.0f}% {word} {R.previous}, possibly chance',
                f'Fleet ticket rate in {R.latest}: {abs(p):.0f}% {word} its baseline, possibly chance']
    return [f'Fleet ticket rate in {R.latest} was {abs(p):.0f}% {word} {R.previous}, within normal variation',
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
            near = rate[base[0]:min(base[0] + 2, n)]
            below = bool(np.nanmean(near) > rb) if np.isfinite(near).any() else False
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
    notes = [R.hollow_note() if (~final).any() else '', R.ci_note(), 'Source: rates.csv (fleet, All unplanned '
             'tickets)' + (' and changes.csv.' if li is not None else '.')]
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
    if L is None:
        cands = [f'Unplanned tickets by request group, {_span_text(R)}']
    elif not tested:
        cands = [f'Unplanned tickets by request group: {L} could not be compared yet',
                 f'Unplanned tickets by request group, {_span_text(R)}']
    elif not flagged:
        cands = [f'No request group changed beyond normal {R.cad.variation} in {L}',
                 f'No request group changed beyond normal variation in {L}']
    elif len(flagged) == 1:
        g, r = flagged[0]
        p = _pct(r.change_ratio)
        word = 'above' if p > 0 else 'below'
        cands = [f'{g} tickets in {L} were {abs(p):.0f}% {word} {R.previous}',
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
    notes += [R.hollow_note() if hollow else '', R.ci_note(),
              'Source: rates.csv and changes.csv (fleet).' if L is not None else 'Source: rates.csv (fleet).']
    group_def = ("Request group: the ticket's Trouble Code and Category mapped to one of nine groups by the "
                 "project's request-type reference.")
    defs = R.defs(baseline=L is not None) + [group_def]
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
             ('eligible', 'No clear difference'), ('not_tested', 'Not tested')]
    handles = [Line2D([], [], marker='o', ls='-', color=_status_colour(S, k) if k in STANDS else
                      (S.GRAY if k == 'eligible' else S.GRAY_LIGHT), markersize=6, lw=1.6) for k, _ in names
               if k in present]
    labels = [lab for k, lab in names if k in present]
    if handles:
        lax.legend(handles, labels, loc='center left', ncol=len(handles), fontsize=9, handlelength=1.8,
                   borderaxespad=0, frameon=False)
    title = _pick_title(S, fig, _cohort_titles(R))
    sub = (f'Unplanned tickets per 100 installed machine-months by install cohort over {R.window_text} '
           f'({_n(R.window_n, "final " + R.noun, "final " + R.plural)}), with 95% intervals; the dashed line is the '
           'whole fleet.')
    others = R.stands.iloc[1:4] if len(R.stands) > 1 else R.stands.iloc[0:0]
    if len(others):
        sub += ' Also standing out: ' + '; '.join(f'{r.issue} on {_cohort_phrase(r.install_cohort)} '
                                                  f'({r.crude_ratio:.1f}x)' for r in others.itertuples()) + '.'
    hi_ = 1 + R.P.MIN_CONTRAST
    defs = R.defs(baseline=False) + [
        (f'Install cohort: machines grouped by install date. A cohort stands out when its rate is at least '
         f'{hi_:.1f}x the rest of the fleet (or at most {1 / hi_:.2f}x) after the Benjamini-Hochberg correction and '
         'above (or below) both newer and older installs; the newest cohort is compared with earlier installs at '
         'the same age.')]
    notes = [('Labels at the markers: the cohort rate over the rest of the fleet. ' if 'stands_out_higher' in present
              or 'stands_out_lower' in present else '') + 'Not tested: too few tickets, machines or accounts, or too '
             'few machines to compare with.', R.ci_note(), 'Source: cohort_contrasts.csv.']
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
    pk = list(R.periods.period_key)
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
           f'{R.noun} (columns); darker means a higher rate, each panel on its own scale.')
    notes = [(f'Plain light cells: under {R.P.MIN_CELL_MONTHS:g} installed machine-months, too few for a rate; '
             f'hatched columns: {R.plural} not final yet. The title counts final {R.plural} with at least two '
              'cohorts shown.'), 'Source: rates.csv (install cohort).']
    _frame(S, fig, title, sub, notes, R.defs(baseline=False))
    step = max(_period_step(ax, R.labels, 8.5) for ax in axes.flat[:n])     # the same labels on every panel
    for ax in axes.flat[:n]:
        _period_ticks(ax, R.labels, fontsize=8.5, offset=0.5, step=step)
    S.save(fig, path)
    return title


# ------------------------------------------------------------------------------------------------ 5 changes
def _forest_rows(R):
    c = R.changes
    head_keys = ['all'] + [f'group|{g}' for g in FU.PRIMARY]
    fleet = c[(c.stratum_dim == 'fleet') & c.issue_key.isin(head_keys)]
    fleet = fleet.set_index('issue_key').reindex([k for k in head_keys if k in set(fleet.issue_key)]).reset_index()
    head = fleet[(fleet.status != 'not_tested') & np.isfinite(fleet.change_ratio.astype(float))]
    is_head = (c.stratum_dim == 'fleet') & c.issue_key.isin(head_keys)
    extra = c[c.status.isin(FLAGGED + WATCH) & ~is_head].copy()
    extra['_w'] = extra.status.isin(WATCH).astype(int)
    extra['_o'] = R._order(extra)
    extra = extra.sort_values(['_w', 'q_value', '_o'], kind='mergesort').drop(columns=['_w', '_o'])
    room = max(0, MAX_FOREST_ROWS - len(head))
    return head, extra.head(room), max(0, len(extra) - room)


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
             'watch_lower': 'Watch, lower', 'no_clear_change': 'No clear change'}
    from matplotlib.patches import Patch
    handles = [Line2D([], [], marker='o', color=_status_colour(S, s), lw=2.2, markersize=6) for s in order
               if s in present] + [Patch(color=S.ZERO_CELL, lw=0)]
    names_shown = [names[s] for s in order if s in present] + [f'Within \u00b1{thr} (practical threshold)']
    _legend_above(ax, handles, names_shown, points=8)
    nflag = int((R.changes.status.isin(FLAGGED)).sum())
    nwatch = int((R.changes.status.isin(WATCH)).sum())
    if nflag == 0:
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
    sub = (f'Change in the rate from the baseline ({R.previous}), adjusted for business days, with 95% intervals: '
           f'the fleet and its request groups, then every flagged or watch-list cell in other breakdowns. '
           f'{_n(tested, "cell")} tested; {nwatch} on the watch list.')
    notes = [(f'Flagged: q-value below {R.P.Q_CUT:g} after one Benjamini-Hochberg correction over every tested cell, '
             f'and a change of at least {thr} (shaded band); a screening flag for follow-up, not proof of a problem. '
              f'Watch: q-value below {R.P.WATCH_Q:g}; could still be chance.'),
             R.ci_note(change=True),
             (f'{hidden} more flagged or watch-list cells are listed in the report. ' if hidden else '')
             + 'Source: changes.csv.']
    _frame(S, fig, title, sub, notes, R.defs())
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
    dq = dq.set_index('period_key').reindex(list(R.periods.period_key))
    n = len(dq)
    x = np.arange(n)
    final = np.array([s == 'final' for s in R.status])
    P = R.P
    panels = [('open_share', 'Tickets still open when exported', P.MAX_OPEN_SHARE,
               f'{_share(P.MAX_OPEN_SHARE)} limit; above it a {R.noun} stays provisional'),
              ('blank_category_share', 'Blank Category (unplanned tickets, excluding Monitoring)',
               P.MAX_BLANK_CATEGORY_SHARE, (f'{_share(P.MAX_BLANK_CATEGORY_SHARE)} limit; above it, issue-level '
                                            'tests are skipped')),
              ('unlisted_share', 'Tickets on machines missing from the equipment list', UNLISTED_NOTE,
               f'{_share(UNLISTED_NOTE)}; above it the email mentions the share')]
    fig, axes = _figure(S, 11, 7.9, 3, 1, sharex=True)
    over = {}
    ended = np.array([s in ('final', 'provisional') for s in R.status])     # in-progress periods are open anyway
    for ax, (col, name, limit, label) in zip(axes[:, 0], panels):
        v = 100 * dq[col].astype(float).fillna(0).to_numpy()
        bad = v > 100 * limit + 1e-9
        over[col] = int((bad & ended).sum())
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
        cands = [f'Open-ticket and blank-Category shares were within limits in every {R.noun}',
                 'Open-ticket and blank-Category shares were within limits']
    title = _pick_title(S, fig, cands)
    sub = (f'Share of each {R.noun}\'s unplanned tickets, {_span_text(R)}. Highlighted bars are above the dashed '
           f'line; hollow bars are {R.plural} not final yet.')
    notes = [('Open tickets: still open when the case export was taken; labels may still change. Unlisted tickets '
             'are not in the rates; the survivorship check puts them back before an increase is flagged.'),
             'Source: data_quality.csv.']
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
     lambda R: 'Change from the baseline for the fleet and its request groups, and every flagged or watch-list '
               'cell.'),
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
    rows = []
    for r in df.itertuples():
        sustained = (f'yes, also flagged last {R.noun}' if bool(getattr(r, 'sustained', False))
                     else ('no' if not watch else ''))
        survivor = _text(getattr(r, 'survivor_note', ''))
        note = 'could still be chance' + (f'; {survivor}' if survivor else '')
        rows.append([_chip(r.status), r.issue, R.stratum_text(r, style='label'), f'{r.rate_latest:.2f}',
                     f'{r.rate_baseline:.2f}', f'{_pct(r.change_ratio):+.0f}%', _interval(r.ci_lo, r.ci_hi),
                     note if watch else sustained])
    return rows


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
    parts += ['<header>', f'<p class="kicker">{_e(_kind(R.cad))}</p>', f'<h1>{_e(title)}</h1>',
              f'<p class="meta">{_e(_cap("; ".join(meta)))}.</p>', '</header>']
    parts += ['<section id="key-messages">', '<h2>Key messages</h2>', '<ul class="key">']
    parts += [f'<li>{_e(m)}</li>' for m in R.key_messages()]
    parts += ['</ul>', '</section>']

    if L is None:
        parts += ['<section id="rates">', f'<h2>Fleet rate by {_e(R.noun)}</h2>',
                  (f'<p class="notice">No reporting {_e(R.noun)} is final yet, so nothing is compared and there are no '
                  'call-outs. The rates below can still change.</p>')]
        d = R.series('fleet', 'all')
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
        heads = ['Status', 'Issue', 'Breakdown', f'Rate in {L}', 'Baseline rate', 'Change', '95% interval',
                 'Sustained']
        if len(R.flags):
            parts.append(_html_table(heads, _change_rows(R, R.flags), num=(3, 4, 5, 6)))
            parts.append('<p class="muted">Rates are unplanned tickets per 100 installed machine-months; the change '
                         'is adjusted for business days.</p>')
        else:
            parts.append(f'<p>{_e(R.none_flagged())}</p>')
        parts.append('</section>')
        # cohorts
        hi = 1 + P.MIN_CONTRAST
        parts += ['<section id="cohorts">', '<h2>Install cohorts that stand out</h2>',
                  (f'<p class="lede">Over {_e(R.window_text)}. A cohort stands out only when its rate is at least '
                   f'{hi:.1f}x the rest of the fleet (or at most {1 / hi:.2f}x) and above (or below) both newer and '
                   'older installs: a peak in the install-date profile, which a steady age effect cannot produce. '
                   'The newest cohort is compared with earlier installs at the same age.</p>')]
        if len(R.stands):
            rows = []
            for r in R.stands.itertuples():
                def _r(v, a, b):
                    return f'{v:.1f}x ({a:.1f} to {b:.1f})' if _finite(v) else 'n/a'
                rows.append([r.issue, r.install_cohort, f'{r.rate_per_100:.2f}', f'{r.rate_rest:.2f}',
                             _r(r.crude_ratio, r.crude_lo, r.crude_hi), _r(r.newer_ratio, r.newer_lo, r.newer_hi),
                             _r(r.older_ratio, r.older_lo, r.older_hi),
                             _r(r.same_age_ratio, r.same_age_lo, r.same_age_hi),
                             f'{int(r.machines):,}' if _finite(r.machines) else '', _text(r.top_models),
                             'yes' if bool(r.persisting) else 'no'])
            parts.append(_html_table(['Issue', 'Install cohort', 'Rate', 'Rest of fleet', 'vs rest (95%)',
                                      'vs newer installs', 'vs older installs', 'Same age (context)', 'Machines',
                                      'Main models', 'Also last window'], rows, num=(2, 3, 8)))
        elif len(R.contrasts):
            parts.append(f'<p>No install cohort stands out over {_e(R.window_text)}.</p>')
        else:
            parts.append('<p>Install cohorts were not compared.</p>')
        parts.append('</section>')
        # watch list
        parts += ['<section id="watch">', '<h2>Watch list</h2>',
                  (f'<p class="lede">Changes of at least {100 * P.MIN_CHANGE:g}% with weaker evidence (q-value below '
                   f'{P.WATCH_Q:g}). Reported only: these could still be chance.</p>')]
        if len(R.watch):
            heads_w = heads[:-1] + ['Note']
            parts.append(_html_table(heads_w, _change_rows(R, R.watch, watch=True), num=(3, 4, 5, 6)))
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
               ('Definitions hash', R.defs_hash), ('Rerun frequency', f'{adj} ({s.get("rerun_frequency", "")})'),
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
            if len(R.stands):
                for r in R.stands.itertuples():
                    pg.para(str(r.sentence), bullet=True, before=0.05)
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
            head = f'Install cohorts that stand out over {R.window_text}'
            if len(R.stands) > 3:
                head += f' ({len(R.stands)} in all, the first 3 shown)'
            out.append(('head', head + ':'))
            out += [('item', R.cohort_item(r)) for r in shown.itertuples()]
        elif len(R.contrasts):
            out.append(('p', f'No install cohort stands out over {R.window_text}.'))
        if len(R.watch):
            out.append(('p', f'Watch list: {len(R.watch)} more could still be chance (see the report).'))
    notes = [R.not_final_text()] if R.not_final() else []
    u = R.s.get('latest_unlisted_share')
    if L is not None and _finite(u) and u > UNLISTED_NOTE:
        notes.append(f'{_share(u)} of {L} tickets were on machines missing from the equipment list')
    if R.warnings:
        notes.append(f'{_n(len(R.warnings), "data warning")} (see the report)')
    if R.no_charts:
        notes.append(f'no charts or PDF, because {R.no_charts}')
    out.append(('p', 'Data notes: ' + ('; '.join(notes) if notes else 'none') + '.'))
    out.append(('p', (f'Full report attached ({FILES["report_pdf"] if pdf else FILES["report_html"]}). '
                      'Dashboard tables: latest/rates_final.csv')))
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
