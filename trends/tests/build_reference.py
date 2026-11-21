#!/usr/bin/env python3
"""Freeze the reconciliation targets from the committed verification outputs (MIT side; run when they change).

  python3 -I trends/tests/build_reference.py           write ipa_trends/reference/reconcile_2025-08_2026-08.json
  python3 -I trends/tests/build_reference.py --check   exit 1 if the frozen file differs from the outputs

The values are aggregates already committed under verification/outputs/ (no identifiers).
"""
import argparse
import json
import sys
from pathlib import Path

TRENDS = Path(__file__).resolve().parents[1]
ROOT = TRENDS.parent
sys.path.insert(0, str(TRENDS))

from ipa_trends import reconcile  # noqa: E402

OUTPUTS = ROOT / 'verification' / 'outputs'


def build():
    ref = reconcile.build_reference(OUTPUTS)
    audit = dict(line.split(',', 1) for line in (OUTPUTS / 'audit_case_workbook.csv').read_text().splitlines()[1:]
                 if ',' in line)
    ref['inputs'] = {'case_export_file': 'IPA_CaseHistory_Aug 2025-Aug2026.xlsx',
                     'case_export_sha256': audit.get('sha256 here', '').strip(),
                     'equipment_file': 'IPA_Active_Equipment_list_2026-10-19.xlsx', 'equipment_date': '2026-10-19'}
    ref['window'] = ['2025-08-01', '2026-08-31']
    ref['split'] = '2026-02-15'
    ref['source'] = 'verification/outputs (fleet_exposure.py, followups.py, reproduce_sql.py)'
    return ref


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--check', action='store_true')
    a = p.parse_args(argv)
    if not OUTPUTS.exists():
        print('verification/outputs not found: this runs only in the MIT repository')
        return 0
    ref = build()
    text = json.dumps(ref, indent=1, sort_keys=True, default=str) + '\n'
    if a.check:
        same = reconcile.REFERENCE.exists() and reconcile.REFERENCE.read_text(encoding='utf-8') == text
        print('reference is up to date' if same else 'reference differs from verification/outputs')
        return 0 if same else 1
    reconcile.REFERENCE.parent.mkdir(parents=True, exist_ok=True)
    reconcile.REFERENCE.write_text(text, encoding='utf-8')
    n = sum(len(v) if isinstance(v, list) else 1 for v in ref.values())
    print(f'wrote {reconcile.REFERENCE.relative_to(ROOT)} ({n} entries)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
