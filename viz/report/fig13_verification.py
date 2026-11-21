#!/usr/bin/env python3
"""Report figure 13 (Results, Verification): every case-export number reproduced exactly, on the full database 65 of
66 checks passed (the one failure was a sort-order bug in our comparison script), independent rebuilds matched the 113
chronic outliers and all 33,515 compared values of the association study, the chronic-outlier count runs from 62 to
133 with the statistical cut-off, and the association results' 45 review points were all upheld and applied, with no
headline result changed.

(a) The share that matched. Solid bars are recounted from the committed tables: the case-export rows (values, printed
    tables, and checks) of each of the three reproductions of the midterm's numbers, its SQL run verbatim
    (reproduce_sql.py), a clean-room rebuild from its method text (reproduce_cleanroom.py), and a re-derivation
    section by section in its notebook's order (01_excel_reproducibility.py), leaving out the workbook's checksum and
    the rows that need the telemetry database or whose value the midterm did not print, as notebook 08 does; then,
    under a heading of their own (the Methods keep the two apart), the checks of the midterm's telemetry results that
    have an expected value in the record of the full-database run (db/db_summary.json), by status. The one
    failed check is red. Sorting the run's table as the midterm did reproduces all 15 printed rows, none of which the
    saved order reproduces, so the failure is the sort-order bug in our comparison script that docs/02 records, and
    the note says so in docs/02's words. Hatched bars are records: counts that a committed document gives for a check
    whose code is not in the repository (docs/05: the rebuild reproduced the same 113 IDs; docs/07: each of two builds
    matched all 33,515 compared cells). They are drawn hatched so that no record reads as a recount, under a heading
    that says only the rebuilds whose records give a count are drawn. The association review is a line of text in
    the paragraph's words, not a bar: its 45 points are problems the reviewers raised, not values that matched, so
    they have no place on the share-matched scale. docs/08 records that none of the 45 was refuted and all are applied
    (the subject of commit eeee532, which applied them, counts the same 45), and the headline results are recounted:
    the pooled specificity ratio and H1 at 7 and 30 days in the committed tables equal the values pinned before the
    review (assoc/as_summary.json) and the tables of commit 472f27b, which set the pins, as notebook 08 compares them;
    commit eeee532 records the same.
(b) Chronic outliers (top 5% by unplanned tickets and a rate outlier) at q < 0.01, 0.05, and 0.10, recounted from each
    device's tickets and months active with the top-5% cut held fixed (notebook 08). The counts equal the review's in
    docs/05 at q < 0.01 and 0.10 and the rebuild's at q < 0.05, the cut-off used throughout (cobalt). As in the set's
    other categorical bar panels, no left spine and no tick marks under the bars.

Not drawn: the rebuilds whose records give no count (the fleet rates before a statistical review's six changes, the
follow-ups' headline numbers, and every sheet of the case list).

Inputs: verification/outputs/repro_sql_claims.csv, repro_clean_claims.csv, 01_excel_reproducibility.csv (one row per
compared claim), db/db_summary.json, db/db_pilot_last_codes_head_vs_expected.csv and db_pilot_last_distinct_codes.csv
(the failed comparison), htm_device_exposure.csv (one row per telemetry device; read without its customer and host
columns), htm_machine_counts.csv (one row per machine with an unplanned ticket) and htm_summary.json (the cut-offs and
the device population), assoc/as_pairs.csv and as_item2_breakdowns.csv (row counts the docs/07 record names),
assoc/as_summary.json, as_h2a.csv, and as_h1.csv (the pinned headline results, also read as committed in 472f27b); the
records in docs/02, docs/05, docs/07, docs/08, and the messages of commits eeee532 and 472f27b, read with git.
Notebook 08 checks the same numbers.
"""
import io
import json
import math
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.text import Text  # noqa: E402

import report_style as S  # noqa: E402

NAME = 'fig13_verification'
LABEL = 'fig:verification'
SHORT = 'Verification'

CUTS = [0.01, 0.05, 0.10]     # Benjamini-Hochberg cut-offs: the review's two and the one used throughout
USED = 0.05
TOP_SHARE = 0.05              # top 5% of machines by unplanned tickets, ties included
# The three case-export reproductions of the midterm's numbers, under a heading that names the midterm: (row name,
# table, column renames); a row's status says whether it matches
REPRODUCTIONS = [
    ('Its SQL, verbatim', 'repro_sql_claims.csv',
     {'claim_id': 'item', 'zac_value': 'printed', 'our_value': 'recomputed'}),
    ('Clean-room rebuild', 'repro_clean_claims.csv',
     {'claim_id': 'item', 'zac_value': 'printed', 'our_value': 'recomputed'}),
    ('Section by section', '01_excel_reproducibility.csv', {'metric': 'item', 'zac_printed': 'printed'}),
]
HATCH = '//////'
PINNED = '472f27b'            # the commit that unblinded the association outputs and pinned the headline results
REVIEWED = 'eeee532'          # the commit that applied the review's findings
NUMBER_WORD = {0: 'no', 1: 'one', 2: 'two', 3: 'three'}


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


def git(*args):
    """Output of a git command in the repository, whose history holds the commit records."""
    return subprocess.run(['git', '-C', str(S.ROOT), *args], capture_output=True, text=True, check=True).stdout


def commit_quote(sha, pattern):
    """The text of a commit message that matches the pattern."""
    m = re.search(pattern, flat(git('log', '-1', '--format=%B', sha)))
    S.check(f'fig13 record found: commit {sha}', 1, int(m is not None))
    return m


def at_commit(sha, name):
    """A table of verification/outputs/ as committed at an earlier commit, read from the repository's history."""
    return pd.read_csv(io.StringIO(git('show', f'{sha}:verification/outputs/{name}')))


def headline_changes():
    """The association study's headline results that changed after its review: the pooled specificity ratio (H2a)
    and H1 at 7 and 30 days, with their intervals and p-values or counts, in the committed tables against the values
    association.py pins (assoc/as_summary.json) and the tables of the commit that set the pins (notebook 08)."""
    def headline(h2a, h1):
        rows = {}
        for k in (168, 720):
            r = h2a[(h2a.k == k) & (h2a.set == 'POOLED')].iloc[0]
            rows[f'pinned pooled H2a at k={k} (estimate, interval, permutation p)'] = [r.estimate, r.ci_lo, r.ci_hi,
                                                                                      r.perm_p]
            r = h1[h1.k == k].iloc[0]
            rows[f'pinned H1 at k={k} (estimate, interval, b, c)'] = [r.estimate, r.ci_lo, r.ci_hi, r.sum_b, r.sum_c]
        return rows

    summary = json.loads((S.OUT / 'assoc' / 'as_summary.json').read_text())
    pins = {c['check']: c['expected'] for c in summary['check_list'] if c['check'].startswith('pinned ')}
    now = headline(pd.read_csv(S.OUT / 'assoc' / 'as_h2a.csv'), pd.read_csv(S.OUT / 'assoc' / 'as_h1.csv'))
    before = headline(at_commit(PINNED, 'assoc/as_h2a.csv'), at_commit(PINNED, 'assoc/as_h1.csv'))
    S.check('fig13 the pinned headline results = the headline rows, now and at the pinning commit', 1,
            int(len(pins) == 4 and set(pins) == set(now) == set(before)))
    S.check(f'fig13 the pins were set ({PINNED}) before the review was applied ({REVIEWED})', 0,
            subprocess.run(['git', '-C', str(S.ROOT), 'merge-base', '--is-ancestor', PINNED, REVIEWED]).returncode)
    commit_quote(PINNED, r'headline results pinned as checks')
    return sum(not (np.allclose(now[n], pins[n], rtol=0, atol=1e-6) and np.allclose(now[n], before[n])) for n in pins)


# ----------------------------------------------------------------------------------------------------------------
# Layout checks, at the final layout
# ----------------------------------------------------------------------------------------------------------------
def extents(fig, artists):
    """Each artist's drawn extent in display units."""
    renderer = fig.canvas.get_renderer()
    return [a.get_window_extent(renderer) for a in artists]


def unbacked_crossings(fig, ax):
    """The labels in ax that a drawn grid line passes through without a white backing to stop it."""
    box = extents(fig, [ax])[0]
    lines = [line for line in ax.xaxis.get_gridlines() + ax.yaxis.get_gridlines() if line.get_visible()]
    grid = [e for e in extents(fig, lines)        # the lines inside the panel (ticks beyond its limits are not drawn)
            if box.x0 - 1 <= e.x0 and e.x1 <= box.x1 + 1 and box.y0 - 1 <= e.y0 and e.y1 <= box.y1 + 1]
    out = []
    for text, e in zip(ax.texts, extents(fig, ax.texts)):
        patch = text.get_bbox_patch()
        backed = (patch is not None and tuple(patch.get_facecolor()[:3]) == (1.0, 1.0, 1.0)
                  and text.get_zorder() > ax.xaxis.get_zorder())        # drawn over the grid, which the axis draws
        if not backed and any(g.overlaps(e) for g in grid):
            out.append(text.get_text())
    return out


def overlapping_texts(fig):
    """Pairs of drawn texts (labels, notes, ticks, titles) whose extents overlap."""
    texts = [t for t in fig.findobj(Text) if t.get_visible() and t.get_text().strip() and t.figure is fig]
    boxes = extents(fig, texts)
    return [(texts[i].get_text(), texts[j].get_text()) for i in range(len(texts)) for j in range(i + 1, len(texts))
            if boxes[i].overlaps(boxes[j])]


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
    fix = quote('docs/02_verification_report.md', r'The one FAIL \(`pilot_last_codes_head`\) was (a [\w -]+? in our '
                r'[\w ]+?), fixed in commit (\w+); re-sorted, all (\d+) rows match\.')
    S.check('fig13 re-sorted, all printed rows match (docs/02)', int(fix.group(3)), resorted)
    cause = ('sort-order bug' if int(recorded.match.eq('True').sum()) == as_saved == 0 and resorted == len(recorded)
             else 'not explained by the order')
    return n_pass, n_pass + n_fail, n_fail, full, cause, fix.group(1)    # the cause in docs/02's words


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
    n_pass, n_checks, n_fail, full, cause, record_cause = database()
    by_cut, n_devices = chronic_by_cut()
    n_changed = headline_changes()

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
    review_commit = commit_quote(REVIEWED, r'Apply the item 8 skeptic review \((\d+) findings\) to the association '
                                 r'study')
    unchanged = commit_quote(REVIEWED, r'(\d+) checks pass; no headline result changed\.')
    n_rebuild = int(rebuild.group(1))
    n_cells = int(blind.group(3).replace(',', ''))
    cells_all = blind.group(1) == 'every compared cell' and blind.group(2) == 'all'
    n_points = int(review.group(2))
    points_all = review.group(1) == 'none' and review.group(3) == 'All'
    # Drawn as all matched only when the record says so (otherwise 0, and the report checks below fail)
    cells_matched = n_cells if cells_all else 0
    S.check('fig13 the review commit counts the same findings', n_points, int(review_commit.group(1)))
    S.check('fig13 the review commit records no headline change, as the recount finds', 1,
            int(unchanged is not None and n_changed == 0))
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
    S.report_check('fig13 headline results that changed after the review (recounted from the pins)', 'no',
                   NUMBER_WORD.get(n_changed, S.num(n_changed)))
    S.report_check('fig13 the failure\'s cause, in the paragraph\'s words (docs/02 record)',
                   'a sort-order bug in our comparison script', record_cause)

    fig, (ax, bx) = S.figure(2.3, ncols=2, width_ratios=[1.75, 1])   # (a) wide enough for the review's line

    # (a) share matched: recounted (solid) and recorded (hatched) bars in three groups, each headed above its first
    # bar, each count beside its bar. Rows one unit apart (about 0.135 in); a line of text is about 0.82 rows tall and
    # a bar 0.56. The case-export group; the full-database group, with the note on its failure just below its bar
    # (one line, from the bar's start, low enough to clear the bold count above its end); the recorded group; last,
    # further apart, the association review as one line of text where a bar would be: its points are problems the
    # reviewers raised, not values that matched, so they get no bar and no share.
    head = 0.96                               # from a group's heading down to its first bar
    half_text, half_bar = 0.41, 0.28
    gap = 0.5                                 # white space between a group's last bar or note and the next heading
    y_db = 2 + half_bar + gap + half_text + head
    y_note = y_db + 1.04
    y_rec = y_note + half_text + gap + half_text + head
    y_rev = y_rec + 1 + half_bar + 0.9 + half_text
    rows = [(name, m, n, 'recount', y) for (name, m, n), y in zip(reproductions, (0, 1, 2))]
    rows += [('Checks', n_pass, n_checks, 'recount', y_db)]
    rows += [('Chronic outliers', n_rebuild, n_rebuild, 'record', y_rec),
             ('Association study', cells_matched, n_cells, 'record', y_rec + 1)]
    S.label(ax, 0, -head, 'Midterm case-export numbers, three ways', va='center')
    S.label(ax, 0, y_db - head, 'Midterm telemetry results, full database', va='center')
    S.label(ax, 0, y_rec - head, 'Rebuilds whose records give a count', va='center')
    for name, m, n, kind, y in rows:
        share = m / n
        if kind == 'recount':
            ax.barh(y, share, height=0.56, color=S.COBALT, zorder=3)
        else:
            ax.barh(y, share, height=0.56, color=S.WHITE, edgecolor=S.COBALT, hatch=HATCH, lw=0.8, zorder=3)
        key = y == y_db                               # the one green readout: 65 of 66 on the full database
        text = f'{S.num(m)} of {S.num(n)}'
        drawn = [int(v.replace(',', '')) for v in text.split()[0:3:2]]      # 'm of n' -> [m, n]
        S.check(f'fig13 (a) label {name!r}: matched', m, drawn[0])
        S.check(f'fig13 (a) label {name!r}: compared', n, drawn[1])
        S.label(ax, 1.025, y, text, size=S.FONT if key else S.TICK, weight='bold' if key else 'normal',
                color=S.GREEN if key else S.TEXT)
    # The one failed check: red, at the end of the database bar, with its cause below it in docs/02's words
    ax.barh(y_db, n_fail / n_checks, left=n_pass / n_checks, height=0.56, color=S.RED, edgecolor=S.WHITE, lw=0.6,
            zorder=4)
    note = f'{S.num(n_fail)} failure: {record_cause}'
    S.check('fig13 (a) failures in the note = the failed checks', n_fail, int(note.split()[0]))
    S.check('fig13 (a) the note\'s cause = the recounted cause', 1, int(cause in note))
    note_text = S.label(ax, 0, y_note, note, ha='left', va='center')
    # The association review, in the paragraph's words: its points and what became of them, with no bar and no share
    upheld = 'all upheld and applied' if points_all else f'{review.group(1)} refuted, {review.group(3).lower()} applied'
    changed = f'{NUMBER_WORD.get(n_changed, S.num(n_changed))} headline result changed'
    review_line = f'{S.num(n_points)} points, {upheld}; {changed}'
    S.check('fig13 (a) review: points (docs/08 record; commit eeee532)', n_points, int(review_line.split()[0]))
    S.check('fig13 (a) review: all upheld and applied (docs/08 record)', 1,
            int(points_all and 'all upheld and applied' in review_line))
    S.check('fig13 (a) review: headline results changed, as drawn = as recounted from the pins', n_changed,
            {word: n for n, word in NUMBER_WORD.items()}.get(changed.split()[0], -1))
    review_text = S.label(ax, 0, y_rev, review_line)
    ax.set_yticks([r[4] for r in rows] + [y_rev], [r[0] for r in rows] + ['Association review'])
    ax.set_ylim(y_rev + 0.62, -head - 0.45)
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
    S.clean(bx, grid='y', left=False)          # as the set's other categorical bar panels: no left spine,
    bx.tick_params(axis='x', length=0)         # and no tick marks under the bars
    S.panel(bx, 'b', 'Chronic outliers by cut-off')

    S.check('fig13 (b) bars inside the axis', 1, int(max(by_cut.values()) + 12 < bx.get_ylim()[1]))
    # At the final layout: the note under the database bar starts at the bar's start and ends inside the panel; the
    # review's line sits in the panel, between the last hatched bar and the axis; no label crosses a grid line
    # unbacked; no two texts touch
    fig.canvas.draw()
    box, note_box, review_box = extents(fig, [ax, note_text, review_text])
    bar_start = ax.transData.transform((0, y_db))[0]
    S.check('fig13 (a) the note starts at the database bar\'s start (clear of the row labels)', 1,
            int(abs(note_box.x0 - bar_start) < 0.02 * fig.dpi))
    S.check('fig13 (a) the note ends inside the panel', 1, int(note_box.x1 <= box.x1))
    S.check('fig13 (a) the review line sits inside the panel, at least 0.02 in above its axis', 1,
            int(box.x0 <= review_box.x0 and review_box.x1 <= box.x1 and box.y0 + 0.02 * fig.dpi <= review_box.y0))
    S.check('fig13 (a) the review line sits below the last hatched bar', 1,
            int(review_box.y1 < ax.transData.transform((0, y_rec + 1 + 0.28))[1]))
    for letter, a in zip('ab', (ax, bx)):
        S.check(f'fig13 ({letter}) labels that cross a grid line have a white backing', '[]',
                str(unbacked_crossings(fig, a)))
    S.check('fig13 no two texts overlap', '[]', str(overlapping_texts(fig)))
    S.report_check('fig13 telemetry devices (Results, high-ticket machines)', '6,621', S.num(n_devices))

    S.export(fig, NAME, out_dir)
    return (f'Every case-export number reproduced exactly, and on the full database {S.num(n_pass)} of '
            f'{S.num(n_checks)} checks passed; the chronic-outlier count runs from {S.num(by_cut[0.01])} to '
            f'{S.num(by_cut[0.10])} with the statistical cut-off. '
            f'(a)~Recounted (solid) or as recorded (hatched); (b)~among the {S.num(n_devices)} telemetry devices.')


if __name__ == '__main__':
    print(plot())
    sys.exit(1 if S.summary() else 0)
