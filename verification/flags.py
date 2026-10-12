"""Canonical text flags for IPA proactive-monitoring tickets and telemetry-system mentions.

One documented rule replaces the three inconsistent first-wave counts (132 / 140 / 135):

monitoring_template(text)  -- "monitoring-template ticket" (template-start rule)
    Applied to the Trouble Reported field. True when the text BEGINS (ignoring leading
    punctuation/whitespace) with the help desk's proactive-monitoring header:
      optional '14 day' window prefix, then the word 'Monitor' or 'Monitoring', then, within
      the same clause (at most 40 characters, no '.', ';' or line break), a cadence tag
      'Daily', 'Weekly' or 'Poll'/'Polling'. Case-insensitive.
    Edge cases (counts are for the Aug 2025 - Aug 2026 export, 7,471 tickets):
      * short form: 'Monitor' instead of 'Monitoring' before the cadence tag
                                                   -> included (6 tickets; the audit_case_logic
        regex required the full word 'monitoring' and missed them -> its 132)
      * header preceded by a '14 day' window prefix -> included (11 tickets)
      * text starting with the word 'Monitor' but no cadence tag (1 ticket, not a monitoring
        header)                                    -> excluded (timestamp_semantics counted it -> its 140)
      * narrative mentions of desk monitoring later in the text (3 tickets)
                                                   -> excluded (not a template; the
        timestamp_semantics regex caught 1 of them via 'during monitoring'; a plain
        substring search for 'monitoring' catches all 3 but misses the 6 short forms -> 135)
      * Trouble Resolution / Administrative Notes are not tested (no ticket starts them with
        the header).

telemetry_mention(text)  -- "mentions a telemetry system" (broader)
    True when monitoring_template(text) is True OR the text names IPA's machine-monitoring
    software: clearView ('clear view', 'clear-view') or clariFy ('clari fy'), whole word,
    case-insensitive. 'clarify' followed by what/whether/if/how/why is read as the English
    verb and excluded. NOT included: the bare words 'monitor'/'monitoring', 'Canopy', 'IoT'
    and quoted numeric error codes (report those separately if needed).

Run: cd /home/user/analytics-lab && python3 -I verification/flags.py
Prints pseudonymous aggregates only (counts, shares, taxonomy labels, T##### ids). Free text is
read in memory and never printed or written.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

TEMPLATE_RE = re.compile(
    r'^\W*(?:14\s*-?\s*days?\s+)?monitor(?:ing)?\b[^.;\n]{0,40}?\b(?:daily|weekly|poll(?:ing)?)\b', re.I)
SYSTEM_RE = re.compile(
    r'\bclear\s*-?\s*view\b|\bclari\s*-?\s*fy\b(?!\s+(?:what|whether|if|how|why)\b)', re.I)

# First-wave patterns, kept only to reproduce and explain their counts.
LEGACY = {
    'audit_case_logic (132)': re.compile(r'monitoring\s*-?\s*(?:daily|poll|weekly)|^\s*monitoring\b', re.I),
    'timestamp_semantics (140)': re.compile(
        r'^\W*monitor(?:ing)?\b|monitor(?:ing)?\s*-?\s*\[?\s*(?:daily|poll|weekly)|during monitoring|\bday monitoring\b',
        re.I),
    "substring 'monitoring' (135)": re.compile(r'monitoring', re.I),
}
NARRATIVE_RE = re.compile(r'\bmonitoring\b', re.I)  # sensitivity only: non-template 'monitoring' wording

# Zac's 30 pilot tickets (pseudonyms as printed in notebook cell 33 output).
PILOT = ('T00705 T00783 T00951 T00957 T01157 T01287 T01629 T01795 T01796 T01797 T02128 T02229 T02268 T03075 '
         'T03079 T03326 T03959 T04699 T04907 T05185 T05506 T05683 T05924 T06107 T06354 T06445 T06663 T06672 '
         'T06712 T06912').split()
NO_TRANSACTIONS = ['T01629', 'T03959', 'T05506', 'T05683']
UNPLANNED_EXCLUDED = ('Planned work', 'Cancelled request', 'Duplicate case')


def _text(text):
    if text is None:
        return ''
    if isinstance(text, float) and text != text:  # NaN
        return ''
    return str(text)


def monitoring_template(text):
    """True if a Trouble Reported text starts with the proactive-monitoring header (see module doc)."""
    return bool(TEMPLATE_RE.search(_text(text)))


def telemetry_mention(text):
    """True if the text is a monitoring template or names clearView / clariFy (see module doc)."""
    t = _text(text)
    return bool(TEMPLATE_RE.search(t)) or bool(SYSTEM_RE.search(t))


def _pct(a, b):
    return f'{a:,}/{b:,} ({100 * a / b:.2f}%)' if b else f'{a}/0'


def _repeat(conn, population='1=1'):
    """Zac's cell-31 repeat view, optionally on a reduced population; adds the follow-up's flag."""
    import pandas as pd
    conn.executescript(f"""
    DROP VIEW IF EXISTS k5_repeat;
    CREATE VIEW k5_repeat AS WITH ordered AS (
      SELECT *, LEAD(opened_at) OVER(PARTITION BY machine_id ORDER BY opened_at,case_id) next_opened,
             LEAD(monitoring_template) OVER(PARTITION BY machine_id ORDER BY opened_at,case_id) next_template
      FROM service_cases WHERE {population})
    SELECT *, julianday(next_opened)-julianday(opened_at) gap_days,
      CASE WHEN julianday(next_opened)-julianday(opened_at) BETWEEN 0 AND 30 THEN 1 ELSE 0 END repeat_30
    FROM ordered WHERE opened_at<'2026-08-02';""")
    return pd.read_sql_query('SELECT case_id, monitoring_template, next_template, repeat_30 FROM k5_repeat', conn)


def main():
    import numpy as np
    import pandas as pd
    from common import build_cases, build_maps, case_database, load_raw

    raw = load_raw()
    maps = build_maps(raw)
    cases = build_cases(raw, maps)
    reported = raw['Trouble Reported']
    cases['monitoring_template'] = reported.map(monitoring_template).astype(int).to_numpy()
    cases['telemetry_mention'] = reported.map(telemetry_mention).astype(int).to_numpy()
    n = len(cases)
    tpl = cases.monitoring_template.astype(bool)

    print('== Canonical counts (Trouble Reported) ==')
    print('monitoring_template :', _pct(int(tpl.sum()), n))
    print('telemetry_mention   :', _pct(int(cases.telemetry_mention.sum()), n))
    any_field = cases.telemetry_mention.astype(bool).copy()
    for col in ('Trouble Resolution', 'Administrative Notes'):
        any_field |= raw[col].map(telemetry_mention).to_numpy()
    print('telemetry_mention in any of the 3 text fields:', _pct(int(any_field.sum()), n))
    narrative = reported.map(lambda x: bool(NARRATIVE_RE.search(_text(x)))).to_numpy() & ~tpl.to_numpy()
    print("non-template 'monitoring' wording (sensitivity, not flagged):", int(narrative.sum()),
          list(cases.case_id[narrative]))

    print('\n== Reconciliation with first-wave patterns ==')
    for name, rx in LEGACY.items():
        hit = reported.map(lambda x, rx=rx: bool(rx.search(_text(x)))).to_numpy()
        only_legacy = cases.case_id[hit & ~tpl.to_numpy()].tolist()
        only_canon = cases.case_id[~hit & tpl.to_numpy()].tolist()
        print(f'{name}: {int(hit.sum())}; extra vs canonical {len(only_legacy)} {only_legacy}; '
              f'missed vs canonical {len(only_canon)} {only_canon}')

    conn = case_database(cases)
    base = pd.read_sql_query('SELECT * FROM case_base', conn)
    t = base[base.monitoring_template == 1]
    print('\n== Profile of template tickets ==')
    for col in ('record_type', 'trouble_code', 'category', 'subcategory', 'service_group', 'status'):
        print(f'{col}:', t[col].fillna('[NULL]').value_counts().to_dict())
    gc = base.record_type.eq('General Case')
    print('share of all General Case tickets:', _pct(int((gc & base.monitoring_template.eq(1)).sum()), int(gc.sum())))
    print('by month:', t.month.value_counts().sort_index().to_dict())
    print('machines with >=1 template ticket:', t.machine_id.nunique())
    window = base[base.opened_at.between('2025-09-02', '2026-07-31 23:59:59')]
    print('share in pilot sampling window (before device filter):',
          _pct(int(window.monitoring_template.sum()), len(window)))

    print('\n== Pilot (Zac cell 8) ==')
    pilot = base[base.case_id.isin(PILOT)]
    picks = pilot.case_id[pilot.monitoring_template == 1].tolist()
    print('template tickets in pilot:', len(picks), 'of', len(pilot), picks)
    print('their trouble-code strata:', pilot[pilot.monitoring_template == 1].trouble_code.fillna('Missing')
          .value_counts().to_dict())
    print("among the 4 'No transactions observed':", [c for c in NO_TRANSACTIONS if c in picks])
    print('pilot tickets with telemetry_mention:', int(pilot.telemetry_mention.sum()))

    print('\n== Another ticket on the same machine in the previous 14 days ==')
    b = base[['case_id', 'machine_id', 'opened_at', 'monitoring_template', 'service_group']].copy()
    b['ts'] = pd.to_datetime(b.opened_at)
    prior = pd.Series(False, index=b.index)
    for _, g in b.groupby('machine_id'):
        times = np.sort(g.ts.to_numpy())
        k = np.searchsorted(times, g.ts.to_numpy(), side='left')  # tickets strictly earlier
        has = k > 0
        gap = np.full(len(g), np.inf)
        gap[has] = (g.ts.to_numpy()[has] - times[k[has] - 1]) / np.timedelta64(1, 'D')
        prior.loc[g.index] = gap <= 14
    b['prior14'] = prior
    unplanned = ~b.service_group.isin(UNPLANNED_EXCLUDED)
    for label, mask in [('template', b.monitoring_template == 1), ('non-template (all)', b.monitoring_template == 0),
                        ('non-template unplanned', (b.monitoring_template == 0) & unplanned)]:
        print(f'{label}:', _pct(int(b.prior14[mask].sum()), int(mask.sum())))
    late = b.ts >= b.ts.min() + pd.Timedelta(days=14)
    print('excluding the first 14 export days: template',
          _pct(int(b.prior14[late & (b.monitoring_template == 1)].sum()), int((late & (b.monitoring_template == 1)).sum())),
          '| non-template', _pct(int(b.prior14[late & (b.monitoring_template == 0)].sum()),
                                 int((late & (b.monitoring_template == 0)).sum())))

    print("\n== Zac's 30-day repeat contact (cell 31) ==")
    r0 = _repeat(conn)
    reps = r0[r0.repeat_30 == 1]
    print('baseline:', _pct(int(r0.repeat_30.sum()), len(r0)))
    idx, fol = reps.monitoring_template == 1, reps.next_template == 1
    print(f'repeats involving a template ticket: {int((idx | fol).sum())} of {len(reps):,} '
          f'({100 * (idx | fol).mean():.1f}%); as index {int(idx.sum())}, as follow-up {int(fol.sum())}, '
          f'both {int((idx & fol).sum())}')
    print('template tickets in service_cases:', int(base[~base.service_group.isin(UNPLANNED_EXCLUDED)]
                                                    .monitoring_template.sum()),
          '| eligible template index tickets:', int((r0.monitoring_template == 1).sum()),
          '| their repeat rate:', _pct(int(r0.repeat_30[r0.monitoring_template == 1].sum()),
                                       int((r0.monitoring_template == 1).sum())))
    r1 = _repeat(conn, 'monitoring_template=0')
    print('templates removed from the population:', _pct(int(r1.repeat_30.sum()), len(r1)))
    keep = r0[r0.monitoring_template == 0]
    print('templates kept as possible follow-ups, dropped as index:', _pct(int(keep.repeat_30.sum()), len(keep)))


if __name__ == '__main__':
    main()
