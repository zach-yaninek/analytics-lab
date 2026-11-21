"""The run: inputs -> population and exposure -> rates -> comparisons and cohort contrasts -> tables.

run(params) returns a RunResult holding only aggregate tables (by period, model, family, install cohort, age and
issue), warnings, checks and facts. Real account names and serials exist only inside the run, for the account
bootstrap, matching and the privacy scan, and are dropped before it returns.
"""
import datetime as dt
import getpass
import os
import re
import stat
import tempfile
import traceback
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import __version__, METHOD_VERSION
from . import cadence as CAD
from . import cohorts as COH
from . import compare as CMP
from . import config as CFG
from . import exposure as EXP
from . import inputs as INP
from . import privacy as PRIV
from . import rates as RT
from . import stats
from .definitions import fleet_exposure_copy as FX
from .definitions import followups_copy as FU
from .errors import TrendsError, stage_for


@dataclass
class RunResult:
    """What a run produced. Every table is an aggregate; nothing identifies a customer, site, machine or case."""
    params: dict
    tables: dict
    facts: dict
    warnings: list
    checks: list
    summary: dict
    paths: dict = field(default_factory=dict)

    def __repr__(self):
        s = self.summary
        return (f"RunResult(latest={s.get('latest_label')!r}, frequency={s.get('rerun_frequency')!r}, "
                f"flags={s.get('flags', 0)}, cohort_call_outs={s.get('cohort_call_outs', 0)}, "
                f"warnings={len(self.warnings)}, tables={sorted(self.tables)})")


class Context:
    """Frames shared by the comparison and cohort modules during one run (in memory only)."""

    def __init__(self, **kw):
        self.__dict__.update(kw)

    def estimate_tau2(self, latest_pos, cells):
        return estimate_tau2(self, latest_pos, cells)


# ------------------------------------------------------------------------------------------------ tau^2
def _final_before(grid, latest_pos, mask=None):
    ok = (grid.index < latest_pos) & (grid.status == 'final')
    if mask is not None:
        ok &= np.asarray(mask, bool)
    return [int(i) for i in grid.index[ok]]


def estimate_tau2(ctx, latest_pos, cells, min_periods=6):
    """tau^2 for the 'head' family (all tickets and request groups) and the 'category' family, from the final
    periods before the latest one: at the run's own period length when there are at least 6, otherwise on monthly
    periods (unscaled, which is conservative for longer periods). The latest period never enters its own yardstick."""
    out, facts = {}, {}
    est = _final_before(ctx.grid, latest_pos)
    if len(est) >= min_periods:
        grid, mp, basis = ctx.grid, ctx.mp, ctx.cadence.canonical
    elif ctx.grid.period_start[latest_pos] - pd.DateOffset(months=3) >= ctx.d0:
        grid, mp = monthly_frames(ctx, ctx.grid.period_start[latest_pos])
        basis = '1M'
        est = [int(i) for i in grid.index[grid.status == 'final']]
    else:                                        # no history before the latest period: nothing to estimate from
        grid, mp, basis, est = ctx.grid, ctx.mp, ctx.cadence.canonical, []
    est_lab = [p for p in est if grid.label_ok[p]]
    f, _, _ = stats.day_factors(ctx.t, grid, est if est else list(grid.index))
    for fam in ('head', 'category'):
        sub_cells = cells[(cells.tau_family == fam) & ~cells.issue.isin(CMP.NOT_TESTED_ISSUES)
                          & ~cells.stratum.isin(CMP.NOT_TESTED_STRATA)]
        O_list, E_list, D_list = [], [], []
        # all-ticket cells use every final period; issue-level cells only those with complete Category labels
        for (dim, lvl_all), g in sub_cells.groupby(['stratum_dim', sub_cells.issue_level == 'all']):
            pos = est if lvl_all else est_lab
            if len(pos) < 3:
                continue
            col = RT.DIM_COLUMN[dim]
            keys = sorted(set(g.issue_key))
            sub = mp[mp.period_pos.isin(pos)]
            agg = sub.groupby([sub[col].astype(str), 'period_pos'])[keys + ['months']].sum()
            present = set(agg.index.get_level_values(0))
            fb = f[pos]
            for r in g.itertuples():
                if r.stratum not in present:
                    continue
                a = agg.loc[r.stratum].reindex(pos, fill_value=0)
                o, mo = a[r.issue_key].to_numpy(float), a.months.to_numpy(float)
                if mo.sum() <= 0 or o.sum() <= 0 or (mo <= 0).any():
                    continue
                fbar = np.sum(mo * fb) / mo.sum()
                O_list.append(o)
                E_list.append(o.sum() / mo.sum() * mo * fb / fbar)     # expected under a constant rate
                D_list.append(r.deff)
        tau2, tf = stats.tau2_dl(O_list, E_list, D_list, ctx.params.TAU2_FLOOR)
        out[fam] = tau2
        facts[fam] = {**tf, 'periods': len(est), 'periods_with_complete_labels': len(est_lab), 'basis': basis}
        if not tf['estimable']:
            ctx.warn.add('W14', f'between-period variation ({fam}) could not be estimated from the history; a '
                                f'conservative default ({tau2:g}) is used', 'longer exports give better estimates')
    return out, facts


def monthly_frames(ctx, before):
    """A monthly grid and machine-month frame ending before `before`, for estimating tau^2 when the run's own
    periods are too few (computed once and cached on the context)."""
    if getattr(ctx, '_monthly', None) is not None and ctx._monthly[0] == before:
        return ctx._monthly[1], ctx._monthly[2]
    P = ctx.params
    end = min(before, ctx.d1)
    grid = CAD.period_grid(CAD.Cadence(1), ctx.d0, end, P.YEAR_START_MONTH, P.FISCAL_YEAR_NAMED_BY)
    grid = grid[grid.period_end <= end].reset_index(drop=True)
    grid = label_quality(grid, ctx.unplanned_window, P)
    grid = CAD.assign_statuses(grid, ctx.d0, ctx.d1, ctx.extracted_at, P.LABEL_LAG_DAYS,
                               dict(zip(grid.period_key, grid.open_share)), P.MAX_OPEN_SHARE)
    grid['label_ok'] = grid.blank_category_share <= blank_category_limit(grid, P)
    mp, _ = EXP.machine_periods(ctx.pop, ctx.t, grid, ctx.catalog, ctx.dims)
    mp['model_stratum'] = mp.model.map(ctx.model_stratum)
    if ctx.params.MODEL_FILTER:
        mp = mp[mp.model.isin(ctx.params.MODEL_FILTER)]
    ctx._monthly = (before, grid, mp)
    return grid, mp


# ------------------------------------------------------------------------------------------------ period quality
def blank_category_limit(grid, params):
    """A period's Category labels count as incomplete above MAX_BLANK_CATEGORY_SHARE, or above twice the typical
    (median) share of blank Categories if that is higher: some tickets are genuinely never categorised (about 2-5%
    a month), so the gate looks for labels that are missing beyond the usual level, not for any blank at all."""
    typical = float(grid.blank_category_share.median()) if len(grid) else 0.0
    return max(params.MAX_BLANK_CATEGORY_SHARE, 2 * typical)


def label_quality(grid, unplanned, params):
    """Open share and blank-Category share of each period's unplanned tickets (all serials)."""
    pos = EXP.ticket_periods(unplanned, grid)
    u = unplanned.assign(_p=pos)
    u = u[u._p >= 0]
    g = u.groupby('_p')
    n = g.size().reindex(grid.index, fill_value=0)
    open_ = g.is_open.sum().reindex(grid.index, fill_value=0)
    nm = u[~u.monitoring]
    blank = nm.groupby('_p').apply(lambda x: (x.ctype == FU.NO_CAT).mean(), include_groups=False) \
        .reindex(grid.index, fill_value=0.0)
    out = grid.copy()
    out['unplanned_tickets_all_serials'] = n.to_numpy()
    out['open_tickets'] = open_.to_numpy()
    out['open_share'] = np.where(n > 0, open_ / n.clip(lower=1), 0.0)
    out['blank_category_share'] = blank.to_numpy()
    return out


# ------------------------------------------------------------------------------------------------ the run
def run(params=None, publish=True, verbose=True, out=print, staging=None):
    """Run the analysis. `params`: a dict of overrides (or resolved Params). publish=True writes the run folder
    (tables, charts, report, email text, manifest) after every check and the privacy scan pass.

    Errors are TrendsErrors with a code, a stage and an exit code (anything unexpected becomes E99, its traceback in
    a private log). A publishing run that stops records it in OUTPUT_DIR/failed/<stamp>/error.txt (publish.
    record_failure) once OUTPUT_DIR is known. With `staging` (a folder), the run is staged there and the caller
    publishes it and records any failure (`ipa-trends run --engine notebook`, which scans the notebook first)."""
    stage, P = 'parameters', None
    try:
        P = params if isinstance(params, CFG.Params) else CFG.resolve(params or {})
        stage = 'analysis'
        result, private = _run(P, verbose, out)
        if publish:
            stage = 'publish'
            from . import publish as PUB
            result.paths = PUB.publish(result, private, P, out=out if verbose else (lambda *a, **k: None),
                                       staging=staging)
        return result
    except TrendsError as e:
        e.stage = e.stage or stage_for(e.code, stage)
        if publish and staging is None:
            _record_failure(e, P, params)
        raise
    except Exception as e:                          # noqa: BLE001
        err = unexpected(e, stage)
        if publish and staging is None:
            _record_failure(err, P, params)
        raise err from None


def unexpected(e, stage):
    """E99 for an unexpected exception: its traceback goes to a private log on this computer, and only its type and
    where it happened are shown (its message can quote a cell value)."""
    stage = f'{stage}{_where(e)}'
    try:
        saved = f'the full traceback is in a private log on this computer: {_private_log(e)}'
    except Exception:                               # noqa: BLE001 - never fall back to showing the exception
        saved = 'its traceback could not be saved to a private log on this computer'
    return TrendsError('E99', f'unexpected {type(e).__name__} during {stage}; {saved}',
                       'send the error code and stage (not the log) to the MIT team', stage=stage)


def _where(e):
    """', in module.function' for the innermost frame of this package in e's traceback ('' if there is none)."""
    try:
        here = Path(__file__).resolve().parent
        frames = [f for f in traceback.extract_tb(e.__traceback__) if Path(f.filename).resolve().is_relative_to(here)]
        return f', in {Path(frames[-1].filename).stem}.{frames[-1].name}' if frames else ''
    except Exception:                               # noqa: BLE001 - called while handling an error: never raise
        return ''


def _private_log(e):
    """Write e's traceback to a new file that only this user can read, in a folder of the temporary directory that
    only this user can open; returns its path. Raises OSError when the folder is not this user's own."""
    owner = str(os.getuid()) if hasattr(os, 'getuid') else re.sub(r'\W', '_', getpass.getuser())
    d = Path(tempfile.gettempdir()) / f'ipa_trends_logs_{owner}'
    d.mkdir(mode=0o700, exist_ok=True)
    st = os.lstat(d)
    if not stat.S_ISDIR(st.st_mode) or (hasattr(os, 'getuid') and st.st_uid != os.getuid()):
        raise OSError(f'{d} is not a folder of this user')
    if stat.S_IMODE(st.st_mode) & 0o077:
        os.chmod(d, 0o700)
    fd, path = tempfile.mkstemp(prefix=f'error_{dt.datetime.now():%Y%m%dT%H%M%S}_', suffix='.log', dir=d)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(''.join(traceback.format_exception(e)))
    return Path(path)


def output_dir_of(overrides):
    """OUTPUT_DIR as resolve() gives it, from OUTPUT_DIR and BASE_DIR alone, so that a failure can be recorded even
    when other parameters are invalid; None when those two cannot be read."""
    if isinstance(overrides, CFG.Params):
        return overrides.output_dir
    try:
        given = dict(overrides or {})
        return CFG.resolve({k: given[k] for k in ('OUTPUT_DIR', 'BASE_DIR') if k in given}).output_dir
    except Exception:                               # noqa: BLE001
        return None


def _record_failure(e, P, params):
    from .publish import record_failure
    out_dir = P.output_dir if P is not None else output_dir_of(params)
    e.failure_record = record_failure(out_dir, e) if out_dir is not None else \
        (None, 'no failure record was written: OUTPUT_DIR could not be read from the parameters')


def closed_only_check(tickets, extracted, warn, days=14, at_least=30):
    """W26 (blocking): a report filtered to closed cases would quietly undercount the most recent weeks, so some of
    the tickets opened in the `days` before the export should still be open. Every case row counts, whatever
    DATA_END says (tickets opened before an earlier DATA_END have had weeks to close); with fewer than `at_least`
    such tickets there is nothing to judge (a report filtered to an earlier date)."""
    recent = tickets[(tickets.ts >= extracted - pd.Timedelta(days=days))
                     & (tickets.ts < extracted + pd.Timedelta(days=1))]
    if len(recent) >= at_least and not recent.is_open.any():
        warn.add('W26', f'none of the {len(recent)} tickets opened in the {days} days before the export '
                        f'({extracted:%Y-%m-%d}) is still open, so the export may be filtered to closed cases and '
                        'recent periods undercounted', 'export all statuses (the report must not filter on Status)',
                 blocking=True)


def _run(P, verbose, out):
    say = out if verbose else (lambda *a, **k: None)
    warn = INP.Warnings()
    case_path, snaps = INP.find_inputs(P, warn)
    say(f'Reading {case_path.name} and {len(snaps)} equipment list(s)')
    frame, case_meta = INP.read_sheet(case_path, P.CASE_SHEET, INP.CASE_REQUIRED, INP.CASE_OPTIONAL, INP.CASE_KNOWN,
                                      P.COLUMN_ALIASES, warn, 'case export')
    tickets, unmapped, code_groups, tfacts, ticket_accounts = INP.build_tickets(frame, case_meta, P, warn)
    eq_frames, eq_meta, private = [], [], {'text': set(), 'digit': set()}
    for d, path in snaps:
        e, meta, priv = INP.read_equipment(path, P, warn)
        meta['snapshot_date'] = f'{d:%Y-%m-%d}'
        eq_frames.append((d, e))
        eq_meta.append(meta)
        private['text'] |= priv['text']
        private['digit'] |= priv['digit']
    ledger, newest = INP.build_ledger(eq_frames)

    # the data window and when the export was taken
    d0 = P.DATA_START if P.DATA_START is not None else tickets.ts.min().normalize()
    d1 = (P.DATA_END if P.DATA_END is not None else tickets.ts.max().normalize()) + pd.Timedelta(days=1)
    outside = (tickets.ts < d0) | (tickets.ts >= d1)
    if outside.any():
        warn.add('W01', f'{int(outside.sum())} ticket(s) opened outside DATA_START..DATA_END were left out')
    if P.EXTRACTED_AT is not None:
        extracted, extracted_src = P.EXTRACTED_AT, 'EXTRACTED_AT'
    elif case_meta['created']:
        extracted, extracted_src = pd.Timestamp(case_meta['created']).normalize(), 'workbook created stamp'
    else:
        extracted, extracted_src = pd.Timestamp(case_meta['modified']).normalize(), 'file modified time'
    if extracted < d1 - pd.Timedelta(days=1):
        warn.add('W24', f'the export date ({extracted:%Y-%m-%d}, from the {extracted_src}) is before the last '
                        f'ticket ({d1 - pd.Timedelta(days=1):%Y-%m-%d}); using the last ticket date instead',
                 'set EXTRACTED_AT to the date the report was exported')
        extracted = d1 - pd.Timedelta(days=1)
    # the case clock: IPA's help desk opens almost no weekday tickets before 06:00 US Eastern (docs/04 §2.2)
    wk = tickets[~outside & (tickets.ts.dt.dayofweek < 5)]
    early = float((wk.ts.dt.hour < 6).mean()) if len(wk) else 0.0
    if early > 0.02:
        warn.add('W12', f'{100 * early:.1f}% of weekday tickets were opened before 06:00, which suggests the export is '
                        'not on US Eastern time', 'export as a user whose Salesforce time zone is US Eastern, or set '
                                                  'CASE_CLOCK_TZ to the export\'s time zone')
    closed_only_check(tickets, extracted, warn)
    period_days = 31 * (P.cadence.months if P.PERIOD_EDGES is None else 1)
    if newest < d1 - pd.Timedelta(days=max(45, period_days // 2)):
        warn.add('W07', f'the newest equipment list ({newest:%Y-%m-%d}) is more than {max(45, period_days // 2)} '
                        f'days older than the case data; machines installed since are missing',
                 'add the current equipment list')
    if newest > d1 + pd.Timedelta(days=60):
        warn.add('W07', f'the newest equipment list ({newest:%Y-%m-%d}) is more than 60 days newer than the case '
                        'data; machines removed in between are missing from it', 'use the list from the export date')

    # clusters: list accounts labelled as common.build_maps / extend_maps number them
    labels = INP.account_labels(ticket_accounts, ledger.account)
    ledger['customer'] = ledger.account.map(labels)
    popres = EXP.population(ledger, tickets, d0, d1, P, warn)
    pop, t = popres['pop'], popres['t']
    bins = CAD.cohort_bins(P.cohort_width, P.INSTALL_COHORT_START, P.INSTALL_COHORT_EDGES, P.YEAR_START_MONTH,
                           P.FISCAL_YEAR_NAMED_BY, last_install=pop.install_date.max())
    pop['install_cohort'] = CAD.assign_cohorts(pop.install_date, bins)
    clusters = sorted(pop.customer.unique())
    W = FX.boot_weights(len(clusters), P.N_BOOT, P.SEED)
    # serials that would match the list only after case-folding or dropping leading zeros: counted, never joined
    # (as fleet_db_extract does), so a formatting change in either export shows up
    listed_norm = {str(s).casefold().lstrip('0') for s in ledger.serial}
    unl_serials = set(popres['unlisted'].serial)
    near = sum(1 for s in unl_serials if str(s).casefold().lstrip('0') in listed_norm)
    if near:
        warn.add('W17', f'{near} serial(s) with tickets are missing from the equipment list but would match it if case '
                        'or leading zeros were ignored; they are left out, as in the original analysis',
                 'check whether either export changed how serial numbers are written')
    # a month with far fewer case rows than usual suggests a broken or partial export
    months = tickets[~outside].groupby(tickets.ts.dt.to_period('M')).size()
    full = months.iloc[1:-1] if len(months) > 2 else months.iloc[0:0]
    low = full[full < 0.2 * months.median()]
    if len(low):
        warn.add('W03', f'{len(low)} month(s) hold under 20% of the usual number of case rows ('
                        f'{", ".join(str(m) for m in low.index)}); the export may be incomplete',
                 'export the full date range again', blocking=True)

    # the reporting grid, its label quality and statuses
    grid = CAD.period_grid(P.cadence, d0, d1, P.YEAR_START_MONTH, P.FISCAL_YEAR_NAMED_BY, P.ANCHOR_DATE,
                           P.PERIOD_EDGES)
    unplanned_window = tickets[tickets.unplanned & ~outside]
    grid = label_quality(grid, unplanned_window, P)
    grid = CAD.assign_statuses(grid, d0, d1, extracted, P.LABEL_LAG_DAYS,
                               dict(zip(grid.period_key, grid.open_share)), P.MAX_OPEN_SHARE)
    blank_limit = blank_category_limit(grid, P)
    grid['label_ok'] = grid.blank_category_share <= blank_limit
    latest_pos = CAD.latest_final(grid, P.LATEST_PERIOD)

    catalog = EXP.issue_catalog(t)
    dims = list(P.STRATIFY_BY)
    say(f'Computing exposure for {len(pop):,} machines over {len(grid)} {P.cadence.plural}')
    mp, outside_t = EXP.machine_periods(pop, t, grid, catalog, dims)
    if outside_t:
        warn.add('W25', f'{outside_t} ticket(s) fall outside the reporting periods (PERIOD_EDGES)')
    model_stratum, model_desc, pool_label = RT.pool_models(mp, grid, latest_pos, P)
    mp['model_stratum'] = mp.model.map(model_stratum)
    if P.MODEL_FILTER:
        mp = mp[mp.model.isin(P.MODEL_FILTER)].reset_index(drop=True)
    checks = list(popres['checks'])
    if not P.MODEL_FILTER:          # with a model filter the machine-period frame is a subset by design
        checks += EXP.invariants(pop, t, mp, grid, catalog, outside_t)

    say('Computing rates')
    category_dims = list(P.CATEGORY_DIMS)
    rates, rchecks = RT.rate_table(mp, grid, catalog, dims, category_dims, W, clusters, P)
    checks += rchecks
    EXP.run_checks(checks)

    model_family = ledger.drop_duplicates('model').set_index('model').family.to_dict()
    unl, unl_months = CMP.unlisted_frame(popres['unlisted'], grid, model_stratum.to_dict(), model_family)
    ctx = Context(params=P, grid=grid, mp=mp, t=t, catalog=catalog, dims=dims, category_dims=category_dims, W=W,
                  clusters=clusters, cadence=P.cadence, label_ok=grid.label_ok.to_numpy(), code_groups=code_groups,
                  unlisted=unl, unlisted_months=unl_months, warn=warn, d0=d0, d1=d1, extracted_at=extracted,
                  pop=pop, model_stratum=model_stratum.to_dict(), unplanned_window=unplanned_window)

    changes, cinfo, contrasts, kinfo = pd.DataFrame(), {}, pd.DataFrame(), {}
    if latest_pos is None:
        warn.add('W15', 'no reporting period is final yet, so nothing is compared',
                 'run again after the current period ends and its labels settle (LABEL_LAG_DAYS)')
    else:
        say(f'Comparing {grid.label[latest_pos]} with its baseline')
        changes, cinfo = CMP.comparison(ctx, latest_pos)
        prev_pos = max([p for p in range(latest_pos) if grid.status[p] == 'final'], default=None)
        prev = None
        if prev_pos is not None:
            prev, _ = CMP.comparison(ctx, prev_pos, tau2=cinfo['tau2'])
        changes = CMP.add_sustained(changes, prev)
        mon = changes[(changes.stratum_dim == 'fleet') & (changes.issue == FU.MONITORING)]
        if len(mon) and mon.tickets_latest.iloc[0] == 0 and cinfo['baseline_positions'] and \
                mon.tickets_baseline.iloc[0] / len(cinfo['baseline_positions']) >= 5:
            warn.add('W11', 'no Monitoring-template tickets in the latest period, against at least 5 per period '
                            'before: the help desk may have changed the template wording',
                     'check the Trouble Reported text of recent monitoring tickets')
        k = cinfo['baseline_positions']
        changes['sentence'] = [CMP.sentence(r, grid.label[latest_pos], P.cadence, len(k)) for r in
                               changes.itertuples()]
        if not cinfo['enough']:
            warn.add('W15', f'only {len(k)} of {cinfo["baseline_intended"]} baseline {P.cadence.plural} are final, '
                            'so no change is tested', 'a longer case export gives a full baseline')
        say('Comparing install cohorts')
        contrasts, kinfo = COH.contrasts(ctx, latest_pos)
        prevc = COH.contrasts(ctx, prev_pos)[0] if prev_pos is not None else None
        contrasts = COH.add_persisting(contrasts, prevc)
        if not contrasts.empty:
            contrasts['sentence'] = [COH.sentence(r) for r in contrasts.itertuples()]   # each row's own window

    # tables
    periods = grid.copy()
    periods['role'] = ''
    if latest_pos is not None:
        periods.loc[latest_pos, 'role'] = 'latest'
        periods.loc[cinfo.get('baseline_positions', []), 'role'] = 'baseline'
    dq = data_quality(grid, tickets[~outside], popres, t, mp, unl, unplanned_window, P)
    strata = strata_table(pop, mp, model_desc, bins, dims, grid)
    real = PRIV.real_sets(ticket_accounts | set(ledger.account), set(tickets.serial) | set(ledger.serial)
                          | set(popres['unlisted'].serial), set(tickets.case_number), private)
    summary = make_summary(P, grid, latest_pos, cinfo, kinfo, changes, contrasts, popres, dq, tfacts, extracted,
                           extracted_src, d0, d1)
    facts = {'tickets': tfacts, 'population': popres['facts'], 'comparison': _jsonable(cinfo),
             'cohorts': _jsonable(kinfo), 'data_window': [f'{d0:%Y-%m-%d}', f'{d1 - pd.Timedelta(days=1):%Y-%m-%d}'],
             'extracted_at': f'{extracted:%Y-%m-%d}', 'extracted_at_source': extracted_src,
             'inputs': {'case_export': case_meta, 'equipment_lists': eq_meta},
             'clusters': len(clusters), 'bootstrap_weights_fingerprint': PRIV.weights_fingerprint(W),
             'model_pool_label': pool_label, 'cohort_bins': [b[0] for b in bins],
             'blank_category_limit': blank_limit}
    tables = {'periods': periods, 'rates': rates, 'changes': changes, 'cohort_contrasts': contrasts,
              'data_quality': dq, 'strata': strata, 'unmapped': unmapped}
    check_rows = [{'check': c[0], 'expected': c[1], 'actual': c[2], 'passed': True} for c in checks]
    result = RunResult(params=P.public(), tables=tables, facts=facts, warnings=warn.items, checks=check_rows,
                       summary=summary)
    return result, {'real': real}


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, np.ndarray)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    return o


def data_quality(grid, tickets, popres, t, mp, unl, unplanned_window, P):
    """Per-period counts that explain and qualify the rates."""
    rows = []
    allpos = EXP.ticket_periods(tickets, grid)
    upos = EXP.ticket_periods(unplanned_window, grid)
    tpos = EXP.ticket_periods(t, grid)
    for p, g in grid.iterrows():
        a = tickets[allpos == p]
        u = unplanned_window[upos == p]
        tt = t[tpos == p]
        mpp = mp[mp.period_pos == p]
        n_u = len(u)
        n_unl = int((unl.period_pos == p).sum()) if len(unl) else 0
        rows.append({'period_key': g.period_key, 'period_label': g.label, 'status': g.status,
                     'case_rows': len(a), 'planned': int((a.service_group == 'Planned work').sum()),
                     'cancelled': int((a.service_group == 'Cancelled request').sum()),
                     'duplicate': int((a.service_group == 'Duplicate case').sum()), 'unplanned': n_u,
                     'open': int(u.is_open.sum()), 'open_share': u.is_open.mean() if n_u else 0.0,
                     'blank_category_share': g.blank_category_share, 'label_ok': bool(g.label_ok),
                     'monitoring': int(u.monitoring.sum()), 'unmapped_tickets': int(u.unmapped.sum()),
                     'unlisted_tickets': n_unl, 'unlisted_share': n_unl / n_u if n_u else 0.0,
                     'population_tickets': len(tt), 'machines_exposed': int((mpp.months > 0).sum()),
                     'machine_months': float(mpp.months.sum()),
                     'avg_installed_machines': float(mpp.months.sum()) / (g.covered_days / FX.MONTH_DAYS)})
    return pd.DataFrame(rows)


def strata_table(pop, mp, model_desc, bins, dims, grid):
    rows = []
    for _, r in model_desc.iterrows():
        rows.append({'stratum_dim': 'model', 'stratum': r.stratum, 'member': r.model, 'own_series': r.own_series,
                     'avg_installed_machines': r.avg_installed_machines,
                     'avg_installed_machines_latest': r.avg_installed_machines_latest})
    for lab, lo, hi in bins:
        rows.append({'stratum_dim': 'install_cohort', 'stratum': lab, 'member': lab,
                     'installed_from': None if lo == pd.Timestamp.min else f'{lo:%Y-%m-%d}',
                     'installed_before': None if hi == pd.Timestamp.max else f'{hi:%Y-%m-%d}',
                     'machines': int((pop.install_cohort == lab).sum())})
    rows.append({'stratum_dim': 'install_cohort', 'stratum': 'Unknown', 'member': 'Unknown',
                 'machines': int((pop.install_cohort == 'Unknown').sum())})
    for fam, n in pop.family.value_counts().items():
        rows.append({'stratum_dim': 'family', 'stratum': fam, 'member': fam, 'machines': int(n)})
    return pd.DataFrame(rows)


def make_summary(P, grid, latest_pos, cinfo, kinfo, changes, contrasts, popres, dq, tfacts, extracted, src, d0, d1):
    s = {'rerun_frequency': P.cadence.canonical, 'frequency_name': P.cadence.adjective, 'period_noun': P.cadence.noun,
         'data_window': [f'{d0:%Y-%m-%d}', f'{d1 - pd.Timedelta(days=1):%Y-%m-%d}'],
         'extracted_at': f'{extracted:%Y-%m-%d}', 'periods': len(grid),
         'final_periods': int((grid.status == 'final').sum()), 'latest_label': None}
    if latest_pos is not None:
        s['latest_label'] = grid.label[latest_pos]
        s['latest_label_long'] = grid.label_long[latest_pos]
        s['latest_period_key'] = grid.period_key[latest_pos]
        s['baseline_labels'] = [grid.label[p] for p in cinfo.get('baseline_positions', [])]
        s['baseline_intended'] = cinfo.get('baseline_intended')
        fl = changes[(changes.stratum_dim == 'fleet') & (changes.issue_key == 'all')]
        if len(fl):
            r = fl.iloc[0]
            s['fleet_rate_latest'] = float(r.rate_latest)
            s['fleet_rate_baseline'] = float(r.rate_baseline)
            s['fleet_status'] = r.status
        s['flags'] = int(changes.status.isin(['higher', 'lower']).sum())
        s['watch'] = int(changes.status.str.startswith('watch').sum())
        s['tested'] = int(changes.eligible.sum())
        s['cohort_call_outs'] = int(contrasts.status.str.startswith('stands_out').sum()) if len(contrasts) else 0
        s['cohort_window'] = kinfo.get('window_label')
        s['cohort_window_issue_level'] = kinfo.get('window_label_issue_level')
        lp = dq.iloc[latest_pos]
        s['latest_unlisted_share'] = float(lp.unlisted_share)
    open_p = grid[grid.status.isin(['provisional', 'in_progress'])]
    s['not_yet_final'] = [{'label': r.label, 'status': r.status, 'reason': r.status_reason}
                          for r in open_p.itertuples()]
    # next runs: periods due (end + LABEL_LAG_DAYS) after this export was taken, so never on or before its own date.
    # A period already due but still provisional (too many tickets open) needs a newer export instead. A back-run
    # (LATEST_PERIOD) is not part of the schedule and names neither; explicit PERIOD_EDGES have no due dates.
    lag = pd.Timedelta(days=P.LABEL_LAG_DAYS)
    s['next_runs'], s['cron_hint'] = ([], None) if P.PERIOD_EDGES is not None else CAD.next_runs(
        P.cadence, extracted - lag, P.LABEL_LAG_DAYS, 4, P.YEAR_START_MONTH, P.FISCAL_YEAR_NAMED_BY, P.ANCHOR_DATE)
    due = grid[(grid.status == 'provisional') & (grid.period_end + lag <= extracted)]
    s['needs_newer_export'] = [{'label': r.label, 'reason': r.status_reason} for r in due.itertuples()]
    if P.LATEST_PERIOD is not None:
        s['next_runs'], s['needs_newer_export'] = [], []
    s['version'], s['method_version'] = __version__, METHOD_VERSION
    return s


# ------------------------------------------------------------------------------------------------ notebook scan
def real_strings(P):
    """The inputs' real strings for the privacy scan of an executed notebook (read again; never written)."""
    from .definitions import common_copy as C
    warn = INP.Warnings()
    case, snaps = INP.find_inputs(P, warn)
    frame, _ = INP.read_sheet(case, P.CASE_SHEET, INP.CASE_REQUIRED, INP.CASE_OPTIONAL, INP.CASE_KNOWN,
                              P.COLUMN_ALIASES, warn, 'case export')
    names = set(frame['Account Name'].map(C.clean)) - {None}
    ids = set(frame['Serial #'].map(C.clean)) - {None}
    cases = set(frame['Case Number'].map(C.clean)) - {None}
    private = {'text': set(), 'digit': set()}
    for _, p in snaps:
        e, _, priv = INP.read_equipment(p, P, warn)
        names |= set(e.account)
        ids |= set(e.serial)
        private['text'] |= priv['text']
        private['digit'] |= priv['digit']
    return PRIV.real_sets(names, ids, cases, private)


def scan_notebook(P, path):
    """Number of output fields of an executed notebook that contain a real identifier."""
    import nbformat
    nb = nbformat.read(str(path), as_version=4)
    texts = []
    for cell in nb.cells:
        for o in cell.get('outputs', []):
            if 'text' in o:
                texts.append(''.join(o['text']) if isinstance(o['text'], list) else str(o['text']))
            for mime in ('text/plain', 'text/html', 'text/markdown'):
                v = o.get('data', {}).get(mime)
                if v:
                    texts.append(''.join(v) if isinstance(v, list) else str(v))
            if o.get('ename'):
                texts.append(str(o.get('evalue', '')))
    hits = PRIV.scan_texts(texts, PRIV.for_outputs(real_strings(P), PRIV.vocabulary()), 'notebook')
    return int(sum(hits.values()))
