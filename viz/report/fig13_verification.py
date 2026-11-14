#!/usr/bin/env python3
"""Report figure 13 (Results, Verification): every case-export number reproduced exactly, on the full database 65 of
66 checks passed (the one failure was a sort-order bug in our comparison script), independent rebuilds matched the 113
chronic outliers and all 33,515 compared values of the association study, the association results' 45 review points
were all upheld, and the chronic-outlier count runs from 62 to 133 with the statistical cut-off.

(a) The share that matched (or, for the review, was upheld). Solid bars are recounted from the committed tables: the
    case-export rows (values, printed tables, and checks) of each of the three reproductions, the midterm's SQL run
    verbatim (reproduce_sql.py), a clean-room rebuild from its method text (reproduce_cleanroom.py), and its
    notebook's sections (01_excel_reproducibility.py), leaving out the workbook's checksum and the rows that need the
    telemetry database or whose value the midterm did not print, as notebook 08 does; then the checks with an expected
    value in the record of the full-database run (db/db_summary.json), by status. The one failed check is red. Sorting
    the run's table as the midterm did reproduces all 15 printed rows, none of which the saved order reproduces, so the
    failure is the sort-order bug that docs/02 records. Hatched bars are records: counts that a committed document
    gives for a check whose code is not in the repository (docs/05: the rebuild reproduced the same 113 IDs; docs/07:
    each of two builds matched all 33,515 compared cells; docs/08: none of the 45 findings was refuted and all are
    applied, as the subject of commit eeee532 also counts). They are drawn hatched so that no record reads as a recount.
(b) Chronic outliers (top 5% by unplanned tickets and a rate outlier) at q < 0.01, 0.05, and 0.10, recounted from each
    device's tickets and months active with the top-5% cut held fixed (notebook 08). The counts equal the review's in
    docs/05 at q < 0.01 and 0.10 and the rebuild's at q < 0.05, the cut-off used throughout (cobalt).

Not drawn: the rebuilds whose records give no count (the fleet rates before a statistical review's six changes, the
follow-ups' headline numbers, and every sheet of the case list) and the headline results' pins, which the paragraph
states in words.

Inputs: verification/outputs/repro_sql_claims.csv, repro_clean_claims.csv, 01_excel_reproducibility.csv (one row per
compared claim), db/db_summary.json, db/db_pilot_last_codes_head_vs_expected.csv and db_pilot_last_distinct_codes.csv
(the failed comparison), htm_device_exposure.csv (one row per telemetry device; read without its customer and host
columns), htm_machine_counts.csv (one row per machine with an unplanned ticket) and htm_summary.json (the cut-offs and
the device population), assoc/as_pairs.csv and as_item2_breakdowns.csv (row counts the docs/07 record names); the
records in docs/02, docs/05, docs/07, docs/08, and the message of commit eeee532, read with git. Notebook 08 checks the
same numbers.
"""
import json
import math
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import report_style as S  # noqa: E402

NAME = 'fig13_verification'
LABEL = 'fig:verification'
SHORT = 'Verification'

CUTS = [0.01, 0.05, 0.10]     # Benjamini-Hochberg cut-offs: the review's two and the one used throughout
USED = 0.05
TOP_SHARE = 0.05              # top 5% of machines by unplanned tickets, ties included
# The three case-export reproductions: (row name, table, column renames); a row's status says whether it matches
REPRODUCTIONS = [
    ('Midterm SQL', 'repro_sql_claims.csv', {'claim_id': 'item', 'zac_value': 'printed', 'our_value': 'recomputed'}),
    ('Clean room', 'repro_clean_claims.csv', {'claim_id': 'item', 'zac_value': 'printed', 'our_value': 'recomputed'}),
    ('Notebook sections', '01_excel_reproducibility.csv', {'metric': 'item', 'zac_printed': 'printed'}),
]
HATCH = '//////'


# ----------------------------------------------------------------------------------------------------------------
# Records: committed documents and commit messages, quoted as notebook 08 quotes them
# ----------------------------------------------------------------------------------------------------------------
def flat(text):
    """A document or commit message as one line: single spaces, without quote marks, bold markers, or list dashes."""
    text = ' '.join(line.lstrip('> ') for line in text.splitlines())
    return ' '.join(text.replace('**', '').split()).replace(' - ', ' ')


def quote(doc, pattern):
    """The text of a committed document (path from the repository root) that matches the pattern."""
    m = re.search(pattern, flat((S.ROOT / doc).read_text(encoding='utf-8')))
    S.check(f'fig13 record found: {doc}', 1, int(m is not None))
    return m


def commit_quote(sha, pattern):
    """The text of a commit message that matches the pattern."""
    message = subprocess.run(['git', '-C', str(S.ROOT), 'log', '-1', '--format=%B', sha], capture_output=True,
                             text=True, check=True).stdout
    m = re.search(pattern, flat(message))
    S.check(f'fig13 record found: commit {sha}', 1, int(m is not None))
    return m


# ----------------------------------------------------------------------------------------------------------------
# Recounts from the committed tables (notebook 08)
# ----------------------------------------------------------------------------------------------------------------
def reads_as_printed(t):
    """'yes' where a row's recomputed value reads as the midterm printed it (as the same text, or the same once the
    working printed after it in parentheses is dropped); 'no value' where neither side holds a number or a truth
    value; 'NO' otherwise."""
    printed, recomputed = (t[c].astype(str).str.strip() for c in ('printed', 'recomputed'))
    value = lambda s: s.str.split(' (', n=1, regex=False).str[0]  # noqa: E731
    same = (printed == recomputed) | (value(printed) == value(recomputed))
    no_value = ~printed.str.contains(r'\d|True|False') & ~recomputed.str.contains(r'\d|True|False')
    return pd.Series('NO', index=t.index).mask(no_value, 'no value').mask(same, 'yes')


def case_export():
    """Each reproduction's compared rows and matches, leaving out the workbook's checksum and the rows set aside."""
    out = []
    for name, file, renames in REPRODUCTIONS:
        t = pd.read_csv(S.OUT / file).rename(columns=renames)
        if 'status' not in t:
            t['status'] = t.match.map({'yes': 'match', 'NO': 'mismatch'})
        checksum = t.item.str.contains('sha256')       # the workbook file's checksum, not a number in the export
        compared = t.status.isin(['match', 'mismatch']) & ~checksum
        matched = compared & t.status.eq('match')
        S.check(f'fig13 {file}: every row has a known status', 0, int(t.status.isna().sum()))
        S.check(f'fig13 {file}: matched rows read as printed (or record no value)', 0,
                int((matched & reads_as_printed(t).eq('NO')).sum()))
        out.append((name, int(matched.sum()), int(compared.sum())))
    return out


def database():
    """The full-database run's checks with an expected value, and the one that failed, redone in the midterm's order."""
    db = json.loads((S.OUT / 'db' / 'db_summary.json').read_text())
    checks = pd.DataFrame(db['checks'])
    S.check('fig13 check statuses = the record\'s counts', 1, int(checks.status.value_counts().to_dict()
                                                                    == db['check_counts']))
    judged = checks[checks.status.isin(['PASS', 'FAIL'])]
    S.check('fig13 every judged check has an expected value', 1, int(judged.expected.notna().all()))
    row = checks.set_index('check')
    full = (row.loc["database SHA-256 equals Zac's verified checksum", 'status'] == 'PASS'
            and row.loc['atomic transactions represented', 'status'] == 'PASS')
    n_pass, n_fail = int(judged.status.eq('PASS').sum()), int(judged.status.eq('FAIL').sum())

    # The failed comparison: the run's first 15 rows as saved vs. sorted by ticket and recency rank
    recorded = pd.read_csv(S.OUT / 'db' / 'db_pilot_last_codes_head_vs_expected.csv', dtype=str)
    run = pd.read_csv(S.OUT / 'db' / 'db_pilot_last_distinct_codes.csv', dtype=str)
    keys, values = ['case_id', 'recency_rank'], ['transaction_code', 'last_seen', 'occurrences']

    def reproduced(first15):
        both = recorded.merge(first15[keys + values], on=keys, how='left')
        return int(pd.concat([both[v] == both[f'{v}_expected'] for v in values], axis=1).all(axis=1).sum())

    as_saved = reproduced(run.head(15))
    resorted = reproduced(run.assign(rank=run.recency_rank.astype(int))
                          .sort_values(['case_id', 'rank'], kind='mergesort').head(15))
    failed = judged.check[judged.status.eq('FAIL')].tolist()
    S.check('fig13 the one failure is the printed-rows comparison', 1,
            int(failed == ['pilot_last_codes_head: printed rows reproduced']))
    S.check('fig13 the record\'s result = the saved order\'s', 1,
            int(row.loc['pilot_last_codes_head: printed rows reproduced', 'actual'] == f'{as_saved}/{len(recorded)}'))
    fix = quote('docs/02_verification_report.md', r'The one FAIL \(`pilot_last_codes_head`\) was a sort-order bug in '
                r'our comparison script, fixed in commit (\w+); re-sorted, all (\d+) rows match\.')
    S.check('fig13 re-sorted, all printed rows match (docs/02)', int(fix.group(2)), resorted)
    cause = ('sort-order bug' if int(recorded.match.eq('True').sum()) == as_saved == 0 and resorted == len(recorded)
             else 'not explained by the order')
    return n_pass, n_pass + n_fail, n_fail, full, cause


def poisson_sf(k, mu):
    """P(X >= k) for X ~ Poisson(mu), summed over the upper tail as high_ticket_machines.py does (notebook 08)."""
    k = int(k)
    if k <= 0:
        return 1.0
    if mu <= 0:
        return 0.0
    if k <= mu:
        return max(0.0, 1.0 - sum(math.exp(-mu + j * math.log(mu) - math.lgamma(j + 1)) for j in range(k)))
    term = math.exp(-mu + k * math.log(mu) - math.lgamma(k + 1))
    total, j = term, k
    while term > total * 1e-17 and j < k + 10_000:
        j += 1
        term *= mu / j
        total += term
    return min(1.0, total)


def bh(p):
    """Benjamini-Hochberg q-values (monotone, capped at 1)."""
    p = np.asarray(p, float)
    order = np.argsort(p, kind='mergesort')
    q = np.minimum.accumulate((p[order] * len(p) / np.arange(1, len(p) + 1))[::-1])[::-1]
    out = np.empty(len(p))
    out[order] = np.minimum(q, 1.0)
    return out


def chronic_by_cut():
    """Chronic outliers at each cut-off, recounted from each device's tickets and months active (notebook 08)."""
    devices = pd.read_csv(S.OUT / 'htm_device_exposure.csv',
                          usecols=['serial_id', 'rate_group', 'months', 'tickets_obs', 'q_bh'])
    machines = pd.read_csv(S.OUT / 'htm_machine_counts.csv',
                           usecols=['machine_id', 'unplanned_tickets', 'chronic_outlier'])
    defs = json.loads((S.OUT / 'htm_summary.json').read_text())['definitions']
    S.check('fig13 top share = high_ticket_machines.py\'s', defs['top_share'], TOP_SHARE)
    S.check('fig13 cut-off used throughout = high_ticket_machines.py\'s', defs['q_cut'], USED)
    rank = math.ceil(TOP_SHARE * len(machines))   # top 5%: at or above the count at this rank, ties included
    S.check('fig13 top-5% rank = high_ticket_machines.py\'s', defs['workload_rank'], rank)
    cut = int(machines.unplanned_tickets.sort_values(ascending=False).iloc[rank - 1])
    top5 = devices.serial_id.isin(machines.machine_id[machines.unplanned_tickets >= cut])
    group = devices.groupby('rate_group')[['tickets_obs', 'months']].sum()
    rate = (group.tickets_obs / group.months).where(group.months > 0, devices.tickets_obs.sum() / devices.months.sum())
    expected = devices.rate_group.map(rate) * devices.months
    tested = expected > 0
    p = pd.Series(np.nan, index=devices.index)
    p[tested] = [poisson_sf(y, e) for y, e in zip(devices.tickets_obs[tested], expected[tested])]
    q = pd.Series(np.nan, index=devices.index)
    q[tested] = bh(p[tested])
    S.check('fig13 q-values = high_ticket_machines.py\'s', 0,
            float(np.abs(q[tested] / devices.q_bh[tested] - 1).max()), 1e-9)
    chronic = top5 & (q < USED)
    S.check('fig13 recounted chronic outliers = the machines the script flags', 1,
            int(set(devices.serial_id[chronic]) == set(machines.machine_id[machines.chronic_outlier])))
    exposure = json.loads((S.OUT / 'htm_summary.json').read_text())['D2_exposure']
    S.check('fig13 devices = high_ticket_machines.py\'s exposure population', exposure['devices'], len(devices))
    S.check('fig13 devices tested = those with exposure (the others have no q-value)',
            exposure['devices_with_exposure'], int(tested.sum()))
    return {c: int((top5 & (q < c)).sum()) for c in CUTS}, len(devices)


def plot(out_dir=S.FIG_DIR):
    reproductions = case_export()
    n_pass, n_checks, n_fail, full, cause = database()
    by_cut, n_devices = chronic_by_cut()

    # The records: the rebuilds' and the review's counts, read from the documents' text
    rebuild = quote('docs/05_high_ticket_machines.md', r'An independent clean-room build reproduced the populations, '
                    r'the outlier classes \(the same (\d+) IDs\) and the episode counts\.')
    review_cuts = quote('docs/05_high_ticket_machines.md', r'The count depends on the cut-off \(review\): q < 0\.01 '
                        r'gives (\d+), q < 0\.10 gives (\d+), and a top-2\.5% workload cut-off gives \d+\.')
    blind = quote('docs/07_association_protocol.md', r'With those readings, both builds matched `association\.py` in '
                  r'(.+?), ([^;]+?) exactly; none needed the Monte Carlo tolerances\. Each comparison covered '
                  r'([\d,]+) cells: the pairs \(([\d,]+) tickets × (\d+) fields\);[^.]* (\d+) breakdown rows;[^.]*\.')
    review = quote('docs/08_association_results.md', r'A second reviewer then tried to refute each major finding; '
                   r'(\w+) of the (\d+) findings (?:was|were) refuted\. (\w+) are applied here:')
    review_commit = commit_quote('eeee532', r'Apply the item 8 skeptic review \((\d+) findings\) to the association '
                                 r'study')
    n_rebuild = int(rebuild.group(1))
    n_cells = int(blind.group(3).replace(',', ''))
    cells_all = blind.group(1) == 'every compared cell' and blind.group(2) == 'all'
    n_points = int(review.group(2))
    points_all = review.group(1) == 'none' and review.group(3) == 'All'
    # Drawn as all matched only when the record says so (otherwise 0, and the report checks below fail)
    cells_matched, points_upheld = (n_cells if cells_all else 0), (n_points if points_all else 0)
    S.check('fig13 the review commit counts the same findings', n_points, int(review_commit.group(1)))
    pairs = pd.read_csv(S.OUT / 'assoc' / 'as_pairs.csv', usecols=[0])
    breakdowns = pd.read_csv(S.OUT / 'assoc' / 'as_item2_breakdowns.csv', usecols=[0])
    S.check('fig13 the record\'s paired tickets = as_pairs.csv', int(blind.group(4).replace(',', '')), len(pairs))
    S.check('fig13 the record\'s breakdown rows = as_item2_breakdowns.csv', int(blind.group(6)), len(breakdowns))
    S.check('fig13 recount at q < 0.05 = the rebuild\'s IDs (docs/05)', n_rebuild, by_cut[USED])
    S.check('fig13 recount at q < 0.01 = the review\'s (docs/05)', int(review_cuts.group(1)), by_cut[0.01])
    S.check('fig13 recount at q < 0.10 = the review\'s (docs/05)', int(review_cuts.group(2)), by_cut[0.10])

    every = all(m == n for _, m, n in reproductions)
    S.report_check('fig13 case-export numbers reproduced in all three reproductions', 'Every',
                   'Every' if every else f'All but {sum(n - m for _, m, n in reproductions)}')
    S.report_check('fig13 the checks ran on the full database (SHA-256 and transactions)', 'full database',
                   'full database' if full else 'not the full database')
    S.report_check('fig13 database checks passed', '65', S.num(n_pass))
    S.report_check('fig13 database checks with an expected value', '66', S.num(n_checks))
    S.report_check('fig13 database checks failed', 'one', {0: 'no', 1: 'one', 2: 'two'}.get(n_fail, S.num(n_fail)))
    S.report_check('fig13 cause of the failure', 'sort-order bug', cause)
    S.report_check('fig13 chronic outliers the rebuild matched (docs/05 record)', '113', S.num(n_rebuild))
    S.report_check('fig13 chronic outliers recounted at q < 0.05', '113', S.num(by_cut[USED]))
    S.report_check('fig13 association values compared (docs/07 record)', '33,515', S.num(n_cells))
    S.report_check('fig13 association values matched (docs/07 record)', 'all', 'all' if cells_all else blind.group(1))
    S.report_check('fig13 chronic outliers at q < 0.01', '62', S.num(by_cut[0.01]))
    S.report_check('fig13 chronic outliers at q < 0.10', '133', S.num(by_cut[0.10]))
    S.report_check('fig13 association review points (docs/08 record)', '45', S.num(n_points))
    S.report_check('fig13 review points upheld and applied (docs/08 record)', 'all',
                   'all' if points_all else f'{review.group(1)} refuted')

    fig, (ax, bx) = S.figure(2.1, ncols=2, width_ratios=[1.62, 1])

    # (a) share matched: recounted (solid) and recorded (hatched), in two groups, each headed above its first bar;
    # each count beside its bar. Rows one unit apart; the database row stands apart from the case-export group, with
    # the note on its failure just below it, then the recorded group under its heading.
    y_db, y_rec, head = 3.2, 5.95, 0.85       # head: from a group's heading down to its first bar
    rows = [(name, m, n, 'recount', y) for (name, m, n), y in zip(reproductions, (0, 1, 2))]
    rows += [('Full-database checks', n_pass, n_checks, 'recount', y_db)]
    rows += [('Chronic outliers', n_rebuild, n_rebuild, 'record', y_rec),
             ('Association study', cells_matched, n_cells, 'record', y_rec + 1),
             ('Association review', points_upheld, n_points, 'record', y_rec + 2)]
    S.label(ax, 0, -head, 'Case-export numbers, three ways', va='center')
    S.label(ax, 0, y_rec - head, 'Recorded by the rebuilds and the review', va='center')
    for name, m, n, kind, y in rows:
        share = m / n
        if kind == 'recount':
            ax.barh(y, share, height=0.56, color=S.COBALT, zorder=3)
        else:
            ax.barh(y, share, height=0.56, color=S.WHITE, edgecolor=S.COBALT, hatch=HATCH, lw=0.8, zorder=3)
        key = name == 'Full-database checks'          # the one green readout: 65 of 66 on the full database
        text = f'{S.num(m)} of {S.num(n)}' + (' upheld' if name == 'Association review' else '')
        drawn = [int(v.replace(',', '')) for v in text.split()[0:3:2]]      # 'm of n' -> [m, n]
        S.check(f'fig13 (a) label {name!r}: matched', m, drawn[0])
        S.check(f'fig13 (a) label {name!r}: compared', n, drawn[1])
        S.label(ax, 1.025, y, text, size=S.FONT if key else S.TICK, weight='bold' if key else 'normal',
                color=S.GREEN if key else S.TEXT)
    # The one failed check: red, at the end of the database bar, with its cause below it
    ax.barh(y_db, n_fail / n_checks, left=n_pass / n_checks, height=0.56, color=S.RED, edgecolor=S.WHITE, lw=0.6,
            zorder=4)
    note = f'{S.num(n_fail)} failure: a sort-order bug in our script'     # short enough to end under its bar
    S.check('fig13 (a) failures in the note = the failed checks', n_fail, int(note.split()[0]))
    S.check('fig13 (a) the note\'s cause = the recounted cause', 1, int(cause in note))
    note_text = S.label(ax, 1.0, y_db + 0.8, note, ha='right', va='center')
    ax.set_yticks([r[4] for r in rows], [r[0] for r in rows])
    ax.set_ylim(y_rec + 2.45, -head - 0.55)
    ax.set_xlim(0, 1.36)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.spines['bottom'].set_bounds(0, 1)
    S.pct_axis(ax.xaxis)
    ax.set_xlabel('Share that matched')
    S.clean(ax, left=False)
    S.panel(ax, 'a', 'What was checked and what matched')

    # (b) chronic outliers at the three cut-offs; the cut-off used throughout in cobalt
    for i, c in enumerate(CUTS):
        n = by_cut[c]
        bx.bar(i, n, width=0.6, color=S.COBALT if c == USED else S.GREY_FILL, zorder=3)
        S.check(f'fig13 (b) label at q < {c:.2f}', n, int(S.num(n).replace(',', '')))
        S.label(bx, i, n + 3, S.num(n), ha='center', va='bottom')
    bx.set_xticks(range(len(CUTS)), [f'q < {c:.2f}' for c in CUTS])
    bx.set_xlim(-0.55, len(CUTS) - 0.45)
    bx.set_ylim(0, 150)
    bx.set_yticks([0, 50, 100, 150])
    bx.set_ylabel('Chronic outliers')
    bx.set_xlabel('Statistical cut-off')
    S.clean(bx, grid='y')
    S.panel(bx, 'b', 'Chronic outliers by cut-off')

    S.check('fig13 (b) bars inside the axis', 1, int(max(by_cut.values()) + 12 < bx.get_ylim()[1]))
    fig.canvas.draw()      # the final layout, to place the note
    S.check('fig13 (a) the note starts within its bar\'s span (clear of the row labels)', 1,
            int(note_text.get_window_extent().x0 >= ax.transData.transform((0, y_db))[0]))
    S.report_check('fig13 telemetry devices (Results, high-ticket machines)', '6,621', S.num(n_devices))

    S.export(fig, NAME, out_dir)
    return (f'Every case-export number reproduced exactly, and on the full database {S.num(n_pass)} of '
            f'{S.num(n_checks)} checks passed; the chronic-outlier count runs from {S.num(by_cut[0.01])} to '
            f'{S.num(by_cut[0.10])} with the statistical cut-off. '
            f'(a)~Recounted (solid) or as recorded (hatched); (b)~among the {S.num(n_devices)} telemetry devices.')


if __name__ == '__main__':
    print(plot())
    sys.exit(1 if S.summary() else 0)
