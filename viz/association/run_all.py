#!/usr/bin/env python3
"""Draw every association chart (viz/association/as_*.py) and check them.

Run:  cd /home/user/analytics-lab && python3 -I viz/association/run_all.py
Each chart script also runs on its own, e.g.  python3 -I viz/association/as_02_recency.py

Writes (150 dpi PNG): viz/figures/as_NN_<name>.png (pseudonymous: code sets, Categories, counts; no customer).

Checks, after drawing:
  1. consistency: numbers drawn on the charts agree with the CSVs and as_summary.json (style.check calls);
  2. definitions: every figure that uses a defined term carries its definition (defined_terms below);
  3. privacy: no 4+-digit token other than pseudonyms and years is drawn on any figure.
A failed check raises RuntimeError.
"""
import importlib
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]  # python3 -I leaves the script directory off sys.path
import assoc  # noqa: E402
import ipa_style as style  # noqa: E402

CHARTS = ['as_01_specificity_by_set', 'as_02_recency', 'as_03_enrichment_by_set']


def _flat(text):
    return ' '.join(text.split())


def defined_terms():
    return {'specificity ratio': [assoc.SPECIFICITY_DEFINITION], 'code set': [assoc.TARGET_DEFINITION],
            'control': [assoc.CONTROL_DEFINITION], 'matched odds ratio': [assoc.MOR_DEFINITION]}


def definition_problems(texts):
    terms = {k: [_flat(d) for d in v] for k, v in defined_terms().items()}
    every_def = {d for v in terms.values() for d in v}
    problems = []
    for path, strings in texts.items():
        flat = [_flat(s) for s in strings]
        others = [s for s in flat if s not in every_def]
        for term, defs in terms.items():
            if any(term in s.lower() for s in others) and not any(d in flat for d in defs):
                problems.append(f'{path.name}: uses "{term}" without its definition')
    return problems


def privacy_scan(paths):
    allowed = re.compile(r'^(?:[TMS]\d{5}|20(?:25|26))$')
    bad = 0
    for p in paths:
        for s in style.TEXTS.get(p, []):
            bad += sum(1 for tok in re.findall(r'[A-Za-z]*\d{4,}', s.replace(',', '')) if not allowed.match(tok)
                       and not tok.isdigit() or (tok.isdigit() and len(tok) > 5))
    return bad


def main(out_dir=assoc.FIG_DIR):
    out_dir = Path(out_dir)
    print(f'Plots -> {out_dir} ...')
    style.CHECKS.clear()
    style.TEXTS.clear()
    written = []
    for name in CHARTS:
        written += importlib.import_module(name).plot(out_dir=out_dir)
    n_ok = sum(ok for _, ok in style.CHECKS)
    print(f'  {len(written)} figures; consistency checks: {n_ok} pass, {len(style.CHECKS) - n_ok} warn')
    problems = definition_problems({p: style.TEXTS[p] for p in written})
    print(f'  definition check: {"PASS" if not problems else "FAIL"}')
    for m in problems:
        print(f'    {m}')
    leaks = privacy_scan(written)
    print(f'  privacy scan: {leaks} unexpected long numeric tokens ({"PASS" if leaks == 0 else "FAIL"})')
    if problems:
        raise RuntimeError('a figure uses a term it does not define')
    if leaks:
        raise RuntimeError('a figure contains an unexpected identifier-like token')
    if len(style.CHECKS) - n_ok:
        raise RuntimeError('a number drawn on a chart does not match the data')
    return written


if __name__ == '__main__':
    main()
