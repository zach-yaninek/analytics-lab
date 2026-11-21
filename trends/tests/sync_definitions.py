#!/usr/bin/env python3
"""Keep trends/ipa_trends/definitions/ identical to the definitions in verification/ (MIT side only).

The trend notebook ships without verification/, so the definitions it relies on (the unplanned-ticket view, the
request-type mapping, installed machine-months, rates and their intervals, the privacy scan) are copied verbatim,
node by node, from the scripts that produced the numbers IPA has already seen.

  python3 -I trends/tests/sync_definitions.py           check: every copied node equals its source (exit 1 if not)
  python3 -I trends/tests/sync_definitions.py --write   regenerate the copies from verification/

Nodes are compared as syntax trees (ast.dump), so comments and blank lines may differ but code and docstrings may
not. Tuple assignments (for example `NO_CAT, MONITORING, NTF = ...`) are handled. The request-type reference CSV is
compared byte for byte.
"""
import argparse
import ast
import filecmp
import shutil
import sys
from pathlib import Path

TRENDS = Path(__file__).resolve().parents[1]
ROOT = TRENDS.parent
VERIFICATION = ROOT / 'verification'
DEFS = TRENDS / 'ipa_trends' / 'definitions'

# target module -> (source file, header imports, names copied in source order)
COPIES = {
    'common_copy.py': ('common.py', 'import pandas as pd\n',
                       ['EQUIP_KEEP', 'EQUIP_DATES', 'EQUIP_PRIVATE_COLUMNS', 'clean', '_timestamp', 'CASE_VIEWS']),
    'flags_copy.py': ('flags.py', 'import re\n', ['TEMPLATE_RE', '_text', 'monitoring_template']),
    'htm_copy.py': ('high_ticket_machines.py', 'import math\n\nimport numpy as np\n',
                    ['SEED', 'MIN_TYPE_MONTHS', 'Q_CUT', 'poisson_sf', 'bh']),
    'fleet_exposure_copy.py': ('fleet_exposure.py',
                               'import re\n\nimport numpy as np\nimport pandas as pd\n\n'
                               'from . import htm_copy as H\n',
                               ['SEED', 'N_BOOT', 'MIN_TYPE_MONTHS', 'MIN_CLUSTERS', 'Q_CUT', 'MONTH_DAYS',
                                'AGE_EDGES', 'AGE_LABELS', 'POOL', 'THIRD_PARTY_PLANS', 'Z95,Z998', 'SAFE_DIGITS',
                                'norm', 'text_leaks', 'json_strings', 'byar', 'boot_weights', 'pct_ci', 'bh_q',
                                'months_between', 'age_band', 'add_rate_groups', '_cluster_sums', 'classify',
                                'group_rates']),
    'followups_copy.py': ('followups.py', 'import csv\nimport hashlib\nimport io\n\nimport numpy as np\n'
                                          'import pandas as pd\n',
                          ['REF_HASH', 'YOUNG_BANDS', 'AGE_LABELS', 'GROUPS', 'PRIMARY', 'COMPONENT',
                           'BY_TROUBLE_CODE', 'BLANK', 'NO_CAT,MONITORING,NTF', 'MIN_SUPPORT_MONTHS',
                           'MIN_EST_TICKETS,MIN_EST_ACCOUNTS', 'INSTALL_COHORTS', 'request_types_hash',
                           'assign_request_types']),
    'association_copy.py': ('association.py', 'import numpy as np\n', ['ci']),
}
CSV_COPY = (VERIFICATION / 'reference' / 'request_types_v0.csv', DEFS / 'request_types_v0.csv')


def node_name(n):
    """Name of a top-level function or assignment; tuple targets give 'A,B,C'. None for anything else."""
    if isinstance(n, ast.FunctionDef):
        return n.name
    if isinstance(n, ast.Assign) and len(n.targets) == 1:
        t = n.targets[0]
        if isinstance(t, ast.Name):
            return t.id
        if isinstance(t, ast.Tuple) and all(isinstance(e, ast.Name) for e in t.elts):
            return ','.join(e.id for e in t.elts)
    return None


def nodes(path):
    """{name: (ast node, source segment)} for the first top-level definition of each name."""
    text = Path(path).read_text(encoding='utf-8')
    lines = text.splitlines(keepends=True)
    out = {}
    for n in ast.parse(text).body:
        name = node_name(n)
        if name is not None and name not in out:
            start = min([n.lineno] + [d.lineno for d in getattr(n, 'decorator_list', [])])
            out[name] = (n, ''.join(lines[start - 1:n.end_lineno]))
    return out


def write():
    DEFS.mkdir(parents=True, exist_ok=True)
    for target, (src, header, names) in COPIES.items():
        theirs = nodes(VERIFICATION / src)
        missing = [n for n in names if n not in theirs]
        if missing:
            sys.exit(f'{src}: not found: {missing}')
        ordered = sorted(names, key=lambda n: theirs[n][0].lineno)
        body = '\n\n'.join(theirs[n][1].rstrip('\n') for n in ordered)
        doc = (f'"""Verbatim copies from verification/{src}. Do not edit by hand: regenerate with\n'
               f'trends/tests/sync_definitions.py --write (MIT side) and check with trends/tests/test_parity.py.\n'
               f'"""\n')
        (DEFS / target).write_text(doc + header + '\n\n' + body + '\n', encoding='utf-8')
        print(f'wrote {target}: {len(ordered)} definitions from {src}')
    shutil.copyfile(*CSV_COPY)
    print(f'copied {CSV_COPY[0].name}')


def check(verbose=True):
    """[(label, ok)] for every copied definition and the reference CSV."""
    results = []
    for target, (src, _, names) in COPIES.items():
        theirs, mine = nodes(VERIFICATION / src), nodes(DEFS / target)
        for name in names:
            ok = name in theirs and name in mine and ast.dump(theirs[name][0]) == ast.dump(mine[name][0])
            results.append((f'{target}:{name} == verification/{src}', ok))
        extra = sorted(set(mine) - set(names))
        results.append((f'{target}: no definitions beyond the copied ones', not extra))
    results.append(('request_types_v0.csv byte-identical', filecmp.cmp(*CSV_COPY, shallow=False)))
    if verbose:
        for label, ok in results:
            if not ok:
                print('  MISMATCH', label)
    return results


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    p.add_argument('--write', action='store_true', help='regenerate the copies from verification/')
    a = p.parse_args(argv)
    if not VERIFICATION.exists():
        print('verification/ not found: this check runs only in the MIT repository')
        return 0
    if a.write:
        write()
    res = check()
    bad = [lab for lab, ok in res if not ok]
    print(f'{len(res) - len(bad)}/{len(res)} copied definitions match their sources')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
